#!/usr/bin/env bash
set -euo pipefail
#
# migrate_weather_columns.sh — Add wind/pressure/humidity columns to nav_data
#
# Usage:
#   ./migrate_weather_columns.sh                          # uses defaults (Docker container "timescaledb")
#   ./migrate_weather_columns.sh --container mydb         # custom container name
#   ./migrate_weather_columns.sh --host db.example.com    # connect to remote host instead of Docker
#   ./migrate_weather_columns.sh --host localhost --port 5432 --user archiver --dbname perfsonar
#
# All ALTER TABLE statements are idempotent (IF NOT EXISTS).

CONTAINER="timescaledb"
HOST=""
PORT="5432"
USER="archiver"
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
-- Wind data ($RELWS / $RELWD)
ALTER TABLE nav_data ADD COLUMN IF NOT EXISTS rel_wind_speed_kts DOUBLE PRECISION;
ALTER TABLE nav_data ADD COLUMN IF NOT EXISTS rel_wind_dir_deg   DOUBLE PRECISION;
ALTER TABLE nav_data ADD COLUMN IF NOT EXISTS true_wind_speed_kts DOUBLE PRECISION;
ALTER TABLE nav_data ADD COLUMN IF NOT EXISTS true_wind_dir_deg   DOUBLE PRECISION;

-- Environmental data (bare values after $RELWD in SCS broadcast)
ALTER TABLE nav_data ADD COLUMN IF NOT EXISTS pressure_hpa DOUBLE PRECISION;
ALTER TABLE nav_data ADD COLUMN IF NOT EXISTS humidity_pct DOUBLE PRECISION;
SQL
)

echo "=== nav_data weather column migration ==="

if [[ -n "$HOST" ]]; then
    echo "Connecting to $HOST:$PORT/$DBNAME as $USER ..."
    echo "$SQL" | psql -h "$HOST" -p "$PORT" -U "$USER" -d "$DBNAME"
else
    echo "Running inside Docker container '$CONTAINER' ..."
    echo "$SQL" | docker exec -i "$CONTAINER" psql -U "$USER" -d "$DBNAME"
fi

echo ""
echo "=== Verifying columns exist ==="
VERIFY="SELECT column_name, data_type FROM information_schema.columns WHERE table_name = 'nav_data' AND column_name IN ('rel_wind_speed_kts','rel_wind_dir_deg','true_wind_speed_kts','true_wind_dir_deg','pressure_hpa','humidity_pct') ORDER BY ordinal_position;"

if [[ -n "$HOST" ]]; then
    echo "$VERIFY" | psql -h "$HOST" -p "$PORT" -U "$USER" -d "$DBNAME"
else
    echo "$VERIFY" | docker exec -i "$CONTAINER" psql -U "$USER" -d "$DBNAME"
fi

echo ""
echo "Done. All 6 weather columns are present in nav_data."
