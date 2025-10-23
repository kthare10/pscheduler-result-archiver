#!/usr/bin/env bash
set -euo pipefail

# Usage:
#   ./archiver_update_config.sh /path/to/config.yml [--token <VALUE>] [--no-up]
#
# Behavior:
#   - If runtime.bearer_token exists, KEEP it (do not replace), print it.
#   - Else, use --token VALUE if provided; otherwise generate a 64-hex token and insert it.
#   - Prints ARCHIVER_TOKEN=<token>
#   - Runs docker compose up -d in the config directory unless --no-up is passed.

if [[ $# -lt 1 ]]; then
  echo "Usage: $0 /path/to/config.yml [--token <VALUE>] [--no-up]" >&2
  exit 1
fi

CONFIG_PATH="$1"; shift || true
DO_UP="yes"
TOKEN=""

# Parse optional flags
while (( "$#" )); do
  case "$1" in
    --no-up)
      DO_UP="no"
      shift
      ;;
    --token)
      if [[ -n "${2:-}" ]]; then
        TOKEN="$2"
        shift 2
      else
        echo "ERROR: --token requires a value" >&2
        exit 1
      fi
      ;;
    --token=*)
      TOKEN="${1#--token=}"
      shift
      ;;
    *)
      echo "ERROR: Unknown option: $1" >&2
      exit 1
      ;;
  esac
done

if [[ ! -f "$CONFIG_PATH" ]]; then
  echo "ERROR: File not found: $CONFIG_PATH" >&2
  exit 2
fi

CONFIG_DIR="$(dirname "$CONFIG_PATH")"
CONFIG_ABS="$(realpath "$CONFIG_PATH")"

echo "Updating config: $CONFIG_ABS"
cp -a "$CONFIG_ABS" "${CONFIG_ABS}.bak.$(date +%s)"

# Try to read existing token from runtime block (if present)
EXISTING_TOKEN="$(
  awk '
    BEGIN{in=0}
    /^[[:space:]]*runtime:[[:space:]]*$/ {in=1; next}
    in==1 && /^[^[:space:]]/ {in=0}
    in==1 && /^[[:space:]]*bearer_token:/ {
      line=$0
      sub(/^[^:]*:[[:space:]]*/, "", line)  # strip "bearer_token: "
      gsub(/^[[:space:]]+|[[:space:]]+$/, "", line)
      gsub(/^"|"$/, "", line)                # strip surrounding quotes if any
      print line
      exit
    }
  ' "$CONFIG_ABS"
)"

if [[ -n "$EXISTING_TOKEN" ]]; then
  # Preserve existing token; ignore provided --token
  echo "Existing bearer_token found in runtime block; preserving it."
  EFFECTIVE_TOKEN="$EXISTING_TOKEN"
else
  # No existing token; use provided one or generate
  if [[ -z "$TOKEN" ]]; then
    TOKEN="$(openssl rand -hex 32)"
  fi
  EFFECTIVE_TOKEN="$TOKEN"

  # Insert token
  if grep -Eq '^[[:space:]]*runtime:[[:space:]]*$' "$CONFIG_ABS"; then
    # Insert immediately after `runtime:` if bearer_token not present
    awk -v tok="$EFFECTIVE_TOKEN" '
      BEGIN{added=0}
      /^[[:space:]]*runtime:[[:space:]]*$/ {
        print
        if(!added){print "  bearer_token: " tok; added=1}
        next
      }
      {print}
    ' "$CONFIG_ABS" > "$CONFIG_ABS.new" && mv "$CONFIG_ABS.new" "$CONFIG_ABS"
  else
    # No runtime block: append minimal block
    {
      echo ""
      echo "runtime:"
      echo "  bearer_token: $EFFECTIVE_TOKEN"
    } >> "$CONFIG_ABS"
  fi
fi

# Show updated runtime block (for visibility)
echo "----- runtime block after update -----"
awk '
  BEGIN{in=0}
  /^[[:space:]]*runtime:[[:space:]]*$/ {in=1; print; next}
  in && /^[^[:space:]]/ {in=0}
  in {print}
' "$CONFIG_ABS" || true
echo "-------------------------------------"

# Print token for notebook capture
echo "ARCHIVER_TOKEN=$EFFECTIVE_TOKEN"

# Optionally run docker compose
if [[ "$DO_UP" == "yes" ]]; then
  cd "$CONFIG_DIR"
  if docker compose version >/dev/null 2>&1; then
    docker compose up -d
  elif command -v docker-compose >/dev/null 2>&1; then
    docker-compose up -d
  else
    echo "WARNING: docker compose not found; skipping compose up" >&2
  fi
fi
