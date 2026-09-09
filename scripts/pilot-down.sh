#!/usr/bin/env bash
set -euo pipefail

# shellcheck source=scripts/lib/pilot-common.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib/pilot-common.sh"

PURGE=false
if [[ "${1:-}" == "--purge" ]]; then
  PURGE=true
elif [[ $# -gt 0 ]]; then
  printf 'Usage: %s [--purge]\n' "$0" >&2
  exit 2
fi

pilot_load_env
if [[ "$PURGE" == "true" ]]; then
  [[ "${CONFIRM_PILOT_PURGE:-}" == "DELETE-PILOT-DATA" ]] || \
    pilot_fail "Set CONFIRM_PILOT_PURGE=DELETE-PILOT-DATA before deleting Pilot volumes"
  pilot_info "Stopping Pilot and deleting all named volumes"
  pilot_compose --profile cloudflare down --volumes --remove-orphans
else
  pilot_info "Stopping Pilot; all persistent volumes are retained"
  pilot_compose --profile cloudflare down --remove-orphans
fi
