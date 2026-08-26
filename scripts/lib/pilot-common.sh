#!/usr/bin/env bash

set -euo pipefail

PILOT_ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PILOT_COMPOSE_FILE="$PILOT_ROOT_DIR/deploy/pilot/docker-compose.yml"
PILOT_ENV_FILE="${ZHITUO_PILOT_ENV_FILE:-$PILOT_ROOT_DIR/deploy/pilot/.env}"

pilot_fail() {
  printf 'FAIL: %s\n' "$*" >&2
  exit 1
}

pilot_info() {
  printf '==> %s\n' "$*"
}

pilot_require_command() {
  command -v "$1" >/dev/null 2>&1 || pilot_fail "$1 is required"
}

pilot_load_env() {
  [[ -f "$PILOT_ENV_FILE" ]] || pilot_fail "Missing Pilot env file: $PILOT_ENV_FILE"
  set -a
  # shellcheck disable=SC1090
  source "$PILOT_ENV_FILE"
  set +a
}

pilot_compose() {
  docker compose --env-file "$PILOT_ENV_FILE" -f "$PILOT_COMPOSE_FILE" "$@"
}

pilot_set_env() {
  local key="$1"
  local value="$2"
  local temp_file
  temp_file="$(mktemp "${PILOT_ENV_FILE}.XXXXXX")"
  awk -v key="$key" -v value="$value" '
    BEGIN { found = 0 }
    index($0, key "=") == 1 { print key "=" value; found = 1; next }
    { print }
    END { if (!found) print key "=" value }
  ' "$PILOT_ENV_FILE" > "$temp_file"
  chmod 600 "$temp_file"
  mv "$temp_file" "$PILOT_ENV_FILE"
}

pilot_running() {
  local service="$1"
  pilot_compose ps --status running --services | grep -Fxq "$service"
}
