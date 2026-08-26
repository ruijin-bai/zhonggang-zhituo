#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE_FILE="$ROOT_DIR/deploy/staging/docker-compose.yml"
ENV_FILE="${ZHITUO_STAGING_ENV_FILE:-$ROOT_DIR/deploy/staging/.env}"
PURGE=false

if [[ "${1:-}" == "--purge" ]]; then
  PURGE=true
elif [[ $# -gt 0 ]]; then
  printf 'Usage: %s [--purge]\n' "$0" >&2
  exit 2
fi

[[ -f "$ENV_FILE" ]] || {
  printf 'ERROR: Missing staging env file: %s\n' "$ENV_FILE" >&2
  exit 1
}

compose() {
  docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" "$@"
}

if [[ "$PURGE" == "true" ]]; then
  if [[ "${CONFIRM_PURGE:-}" != "YES" ]]; then
    printf 'ERROR: Refusing to delete persistent staging volumes. Re-run with CONFIRM_PURGE=YES and --purge.\n' >&2
    exit 1
  fi
  printf '==> Stopping staging and deleting persistent volumes\n'
  compose down --volumes --remove-orphans
else
  printf '==> Stopping staging; persistent volumes are retained\n'
  compose down --remove-orphans
fi
