#!/usr/bin/env bash
set -euo pipefail
#
# migrate_rain_columns.sh — Add precipitation columns to nav_data
#
# Usage:
#   ./migrate_rain_columns.sh                          # uses defaults (Docker container "timescaledb")
#   ./migrate_rain_columns.sh --container mydb         # custom container name
#   ./migrate_rain_columns.sh --host db.example.com    # connect to remote host instead of Docker
#   ./migrate_rain_columns.sh --host localhost --port 5432 --user archiver --dbname perfsonar
#
# All ALTER TABLE statements are idempotent (IF NOT EXISTS).

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
            sed -n '3,11p' "$0"
            exit 0
            ;;
        *) echo "Unknown option: $1"; exit 1 ;;
    esac
done

SQL=$(cat <<'SQL'
-- Precipitation (optical rain gauge); accumulation resets at 0000 UTC
ALTER TABLE nav_data ADD COLUMN IF NOT EXISTS rain_rate_mmhr DOUBLE PRECISION;
ALTER TABLE nav_data ADD COLUMN IF NOT EXISTS rain_accum_mm  DOUBLE PRECISION;
SQL
)

# Post-condition. Dashboards will read these columns, so a migration that
# silently did nothing must abort rather than claim both columns are present.
VERIFY_SQL=$(cat <<'SQL'
DO $$
DECLARE
    n_cols integer;
BEGIN
    SELECT count(*) INTO n_cols
    FROM information_schema.columns
    WHERE table_schema = 'public'
      AND table_name = 'nav_data'
      AND column_name IN ('rain_rate_mmhr','rain_accum_mm');

    IF n_cols <> 2 THEN
        RAISE EXCEPTION 'expected 2 rain columns on nav_data, found %', n_cols;
    END IF;

    RAISE NOTICE 'post-condition OK: both rain columns present';
END $$;
SQL
)

echo "=== nav_data rain column migration ==="

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

# --single-transaction so a partial failure leaves nav_data unchanged rather
# than half-migrated. Adding a nullable column with no default is a
# metadata-only operation, so the exclusive lock is held only briefly.
if ! echo "$SQL" | run_sql --single-transaction; then
    echo "" >&2
    echo "MIGRATION FAILED - the rain columns were not added to nav_data." >&2
    exit 1
fi

if ! echo "$VERIFY_SQL" | run_sql; then
    echo "" >&2
    echo "POST-CONDITION FAILED - migration reported success but nav_data is" >&2
    echo "missing one or more rain columns." >&2
    exit 1
fi

echo ""
echo "=== Rain columns on nav_data ==="
echo "SELECT column_name, data_type FROM information_schema.columns WHERE table_schema = 'public' AND table_name = 'nav_data' AND column_name IN ('rain_rate_mmhr','rain_accum_mm') ORDER BY ordinal_position;" | run_sql

echo ""
echo "Done. Both rain columns are present in nav_data."
