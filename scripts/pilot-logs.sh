#!/usr/bin/env bash
set -euo pipefail

# shellcheck source=scripts/lib/pilot-common.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib/pilot-common.sh"

pilot_load_env
service="${1:-}"
if [[ -n "$service" ]]; then
  case "$service" in
    postgres|redis|minio|api|worker|beat|web|caddy|cloudflared) ;;
    *) pilot_fail "Unknown service: $service" ;;
  esac
  pilot_compose logs --tail "${PILOT_LOG_TAIL:-200}" -f "$service"
else
  pilot_compose logs --tail "${PILOT_LOG_TAIL:-200}" -f
fi
