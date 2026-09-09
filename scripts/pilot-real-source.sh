#!/usr/bin/env bash
set -euo pipefail

# shellcheck source=scripts/lib/pilot-common.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib/pilot-common.sh"

market="${1:-Zambia}"
rows="${2:-5}"
[[ "$rows" =~ ^[0-9]+$ ]] && (( rows >= 1 && rows <= 25 )) || \
  pilot_fail "Rows must be an integer between 1 and 25"

pilot_load_env

pilot_info "Ensuring the real-source tenant exists without demo data"
pilot_compose run --rm \
  -e PILOT_ORGANIZATION_NAME="Zhituo Real Source Pilot" \
  -e PILOT_ORGANIZATION_CODE="REAL-SOURCE-PILOT" \
  bootstrap-identity

pilot_info "Running the persisted World Bank source path for $market"
PILOT_REAL_SOURCE_MARKET="$market" PILOT_REAL_SOURCE_ROWS="$rows" \
  pilot_compose --profile ops run --rm real-source-pilot

printf 'PASS  World Bank -> SourceSubscription -> SourceFetch -> SourceDocument -> CandidateProcessing -> OpportunityDraft\n'
