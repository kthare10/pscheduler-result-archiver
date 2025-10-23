#!/usr/bin/env bash
set -euo pipefail

# Usage:
#   ./archiver_update_config.sh /path/to/config.yml [--no-up]
#
# Example:
#   ./archiver_update_config.sh pscheduler-result-archiver/config.yml
#   ./archiver_update_config.sh pscheduler-result-archiver/config.yml --no-up
#
# Behavior:
#   - Generates a random 64-hex token
#   - Updates (or inserts) runtime.bearer_token in the given config.yml
#   - Prints ARCHIVER_TOKEN=<token>
#   - Runs docker compose up -d (unless --no-up)

if [[ $# -lt 1 ]]; then
  echo "Usage: $0 /path/to/config.yml [--no-up]" >&2
  exit 1
fi

CONFIG_PATH="$1"
DO_UP="yes"
if [[ "${2:-}" == "--no-up" ]]; then
  DO_UP="no"
fi

if [[ ! -f "$CONFIG_PATH" ]]; then
  echo "ERROR: File not found: $CONFIG_PATH" >&2
  exit 2
fi

CONFIG_DIR="$(dirname "$CONFIG_PATH")"
CONFIG_ABS="$(realpath "$CONFIG_PATH")"
TOKEN="$(openssl rand -hex 32)"
export TOKEN

echo "Updating config: $CONFIG_ABS"
cp -a "$CONFIG_ABS" "${CONFIG_ABS}.bak.$(date +%s)"

# --- Update runtime.bearer_token in YAML ---
if grep -Eq '^[[:space:]]*runtime:[[:space:]]*$' "$CONFIG_ABS"; then
  if awk '
      BEGIN{in=0; found=0}
      /^runtime:[[:space:]]*$/ {in=1; next}
      in==1 && /^[^[:space:]]/ {in=0}
      in==1 && /^[[:space:]]*bearer_token:/ {found=1}
      END{exit(found?0:1)}
    ' "$CONFIG_ABS"; then
    # Replace existing token
    awk -v tok="$TOKEN" '
      BEGIN{in=0}
      /^runtime:[[:space:]]*$/ {in=1; print; next}
      in==1 && /^[^[:space:]]/ {in=0}
      in==1 && /^[[:space:]]*bearer_token:/ {
        sub(/bearer_token:[[:space:]].*$/, "bearer_token: " tok)
      }
      {print}
    ' "$CONFIG_ABS" > "$CONFIG_ABS.new" && mv "$CONFIG_ABS.new" "$CONFIG_ABS"
  else
    # Insert token immediately after runtime:
    awk -v tok="$TOKEN" '
      BEGIN{added=0}
      /^runtime:[[:space:]]*$/ {
        print
        if(!added){print "  bearer_token: " tok; added=1}
        next
      }
      {print}
    ' "$CONFIG_ABS" > "$CONFIG_ABS.new" && mv "$CONFIG_ABS.new" "$CONFIG_ABS"
  fi
else
  # No runtime block: append one
  {
    echo ""
    echo "runtime:"
    echo "  bearer_token: $TOKEN"
  } >> "$CONFIG_ABS"
fi

# --- Show updated runtime block ---
echo "----- runtime block after update -----"
awk '
  BEGIN{in=0}
  /^[[:space:]]*runtime:[[:space:]]*$/ {in=1; print; next}
  in && /^[^[:space:]]/ {in=0}
  in {print}
' "$CONFIG_ABS" || true
echo "-------------------------------------"

# --- Print token for notebook capture ---
echo "ARCHIVER_TOKEN=$TOKEN"

# --- Optionally run docker compose ---
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
