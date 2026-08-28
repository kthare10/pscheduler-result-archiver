#!/usr/bin/env bash
set -euo pipefail
#
# migrate_ships_table.sh — Create and seed the "ships" mapping table
#
# ps_test_results.src (pScheduler test runner) and nav_data.vessel_id (NMEA
# listener) name the same ship differently. Dashboards join through "ships" to
# correlate a vessel's network metrics with its own navigation data.
#
# Usage:
#   ./migrate_ships_table.sh                              # uses defaults (Docker container "timescaledb")
#   ./migrate_ships_table.sh --container mydb             # custom container name
#   ./migrate_ships_table.sh --host db.example.com        # connect to remote host instead of Docker
#   ./migrate_ships_table.sh --host localhost --port 5432 --user archiver --dbname perfsonar
#
# The CREATE and the seed rows are idempotent; re-running only refreshes the
# display names and fills in a vessel_id that was previously NULL.
#
# To register a new ship later:
#   INSERT INTO ships (src, vessel_id, display_name)
#   VALUES ('<ps_test_results.src>', '<nav_data.vessel_id>', 'R/V Whatever')
#   ON CONFLICT (src) DO UPDATE SET vessel_id = EXCLUDED.vessel_id,
#                                   display_name = EXCLUDED.display_name;

CONTAINER="timescaledb"
HOST=""
PORT="5432"
USER="grafana_writer"
DBNAME="perfsonar"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --container) CONTAINER="$2"; shift 2 ;;
        --host)      HOST="$2";      shift 2 ;;
        --port)      PORT="$2";      shift 2 ;;
        --user)      USER="$2";      shift 2 ;;
        --dbname)    DBNAME="$2";    shift 2 ;;
        -h|--help)
            sed -n '3,22p' "$0"
            exit 0
            ;;
        *) echo "Unknown option: $1"; exit 1 ;;
    esac
done

SQL=$(cat <<'SQL'
CREATE TABLE IF NOT EXISTS ships (
    src          TEXT PRIMARY KEY,
    vessel_id    VARCHAR(64),
    display_name TEXT NOT NULL,
    notes        TEXT
);

CREATE INDEX IF NOT EXISTS idx_ships_vessel_id ON ships (vessel_id);

-- Seed the currently-reporting ships. COALESCE keeps an existing vessel_id
-- if this script is re-run after one has been filled in by hand.
INSERT INTO ships (src, vessel_id, display_name, notes) VALUES
    ('renci-vm',       'rv-thompson', 'R/V Thompson', 'Reporting since 2026-04-07'),
    ('shp-compass-ci', NULL,          'R/V Sikuliaq', 'Reporting since 2026-08-25; vessel_id pending NMEA listener')
ON CONFLICT (src) DO UPDATE
    SET vessel_id    = COALESCE(EXCLUDED.vessel_id, ships.vessel_id),
        display_name = EXCLUDED.display_name;
SQL
)

# Post-condition. Every dashboard query joins "ships", so a migration that
# fails here leaves all three dashboards broken -- this must abort the script
# rather than let it print "Done."
VERIFY_SQL=$(cat <<'SQL'
DO $$
DECLARE
    n_ships integer;
BEGIN
    IF to_regclass('public.ships') IS NULL THEN
        RAISE EXCEPTION 'ships table was not created';
    END IF;

    SELECT count(*) INTO n_ships FROM ships;
    IF n_ships = 0 THEN
        RAISE EXCEPTION 'ships table is empty; dashboards would show no vessels';
    END IF;

    -- Smoke-test the two joins every dashboard depends on.
    PERFORM COALESCE(s.display_name, r.src)
    FROM (SELECT DISTINCT src FROM ps_test_results) r
    LEFT JOIN ships s ON s.src = r.src;

    PERFORM 1 FROM nav_data n
    WHERE n.vessel_id IN (SELECT vessel_id FROM ships WHERE vessel_id IS NOT NULL)
    LIMIT 1;

    RAISE NOTICE 'post-condition OK: % ship(s) registered', n_ships;
END $$;
SQL
)

echo "=== ships mapping table migration ==="

# ON_ERROR_STOP is essential: without it psql exits 0 even when every
# statement failed, and "set -e" would happily report success.
run_sql() {
    if [[ -n "$HOST" ]]; then
        psql -v ON_ERROR_STOP=1 -h "$HOST" -p "$PORT" -U "$USER" -d "$DBNAME" "$@"
    else
        docker exec -i "$CONTAINER" psql -v ON_ERROR_STOP=1 -U "$USER" -d "$DBNAME" "$@"
    fi
}

if [[ -n "$HOST" ]]; then
    echo "Connecting to $HOST:$PORT/$DBNAME as $USER ..."
else
    echo "Running inside Docker container '$CONTAINER' ..."
fi

# --single-transaction so a partial failure rolls back rather than leaving a
# table with no rows in it.
if ! echo "$SQL" | run_sql --single-transaction; then
    echo "" >&2
    echo "MIGRATION FAILED - the ships table was not created/seeded." >&2
    echo "All three Grafana dashboards join this table and will be broken." >&2
    exit 1
fi

if ! echo "$VERIFY_SQL" | run_sql; then
    echo "" >&2
    echo "POST-CONDITION FAILED - migration reported success but the ships" >&2
    echo "table is not usable by the dashboards." >&2
    exit 1
fi

echo ""
echo "=== Registered ships ==="
echo "SELECT src, vessel_id, display_name, notes FROM ships ORDER BY display_name;" | run_sql

echo ""
echo "=== Measurement sources with no ships row (invisible in dashboards) ==="
echo "SELECT DISTINCT r.src FROM ps_test_results r LEFT JOIN ships s ON s.src = r.src WHERE s.src IS NULL ORDER BY 1;" | run_sql

echo ""
echo "=== Vessels reporting nav data in the last 7 days with no ship link ==="
# Windowed to 7 days on purpose: nav_data is very large, and an unbounded
# DISTINCT over vessel_id scans the whole table.
echo "SELECT DISTINCT n.vessel_id FROM nav_data n LEFT JOIN ships s ON s.vessel_id = n.vessel_id WHERE s.vessel_id IS NULL AND n.ts > now() - INTERVAL '7 days' ORDER BY 1;" | run_sql

echo ""
echo "Done."
