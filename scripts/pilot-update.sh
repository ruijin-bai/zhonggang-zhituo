#!/usr/bin/env bash
set -euo pipefail

# shellcheck source=scripts/lib/pilot-common.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib/pilot-common.sh"

pilot_require_command docker
pilot_require_command git
pilot_load_env

rollback=false
target_ref=""
if [[ "${1:-}" == "--rollback" ]]; then
  rollback=true
elif [[ $# -gt 1 ]]; then
  printf 'Usage: %s [<git-sha> | --rollback]\n' "$0" >&2
  exit 2
else
  target_ref="${1:-HEAD}"
fi

if [[ "$rollback" == "true" ]]; then
  [[ -n "${PREVIOUS_GIT_SHA:-}" ]] || pilot_fail "No previous deployed SHA is recorded"
  previous_short="${PREVIOUS_GIT_SHA:0:12}"
  docker image inspect "zhituo-api:pilot-${previous_short}" >/dev/null 2>&1 || \
    pilot_fail "Previous API image is not available locally"
  docker image inspect "zhituo-web:pilot-${previous_short}" >/dev/null 2>&1 || \
    pilot_fail "Previous Web image is not available locally"

  current_sha="${DEPLOYED_GIT_SHA:-}"
  pilot_set_env PREVIOUS_GIT_SHA "$current_sha"
  pilot_set_env DEPLOYED_GIT_SHA "$PREVIOUS_GIT_SHA"
  pilot_set_env ZHITUO_API_IMAGE "zhituo-api:pilot-${previous_short}"
  pilot_set_env ZHITUO_WEB_IMAGE "zhituo-web:pilot-${previous_short}"
  pilot_load_env
  pilot_compose up -d api worker beat web caddy
  ZHITUO_PILOT_ENV_FILE="$PILOT_ENV_FILE" bash "$PILOT_ROOT_DIR/scripts/pilot-health.sh"
  printf 'PASS  application images rolled back to %s\n' "$DEPLOYED_GIT_SHA"
  printf 'WARN  database migrations were not downgraded; restore a verified backup if schema rollback is required\n'
  exit 0
fi

if [[ -n "$(git -C "$PILOT_ROOT_DIR" status --porcelain)" ]]; then
  pilot_fail "Refusing update from a dirty Git checkout"
fi

if [[ "$target_ref" != "HEAD" ]]; then
  pilot_info "Fetching current main before validating target $target_ref"
  git -C "$PILOT_ROOT_DIR" fetch --prune origin main
fi
target_sha="$(git -C "$PILOT_ROOT_DIR" rev-parse "${target_ref}^{commit}")"
if [[ "$target_ref" != "HEAD" ]]; then
  git -C "$PILOT_ROOT_DIR" merge-base --is-ancestor "$target_sha" origin/main || \
    pilot_fail "Target must be reachable from origin/main"
  git -C "$PILOT_ROOT_DIR" switch --detach "$target_sha"
fi
target_short="${target_sha:0:12}"
current_sha="${DEPLOYED_GIT_SHA:-}"

if [[ "$target_short" == "${current_sha:0:12}" ]]; then
  pilot_info "Commit $target_short is already deployed; running health verification"
  ZHITUO_PILOT_ENV_FILE="$PILOT_ENV_FILE" bash "$PILOT_ROOT_DIR/scripts/pilot-health.sh"
  exit 0
fi

pilot_info "Building candidate images for $target_short"
docker build --pull -t "zhituo-api:pilot-${target_short}" "$PILOT_ROOT_DIR/apps/api"
docker build --pull -f "$PILOT_ROOT_DIR/apps/web/Dockerfile" \
  -t "zhituo-web:pilot-${target_short}" "$PILOT_ROOT_DIR"

pilot_info "Taking a pre-migration PostgreSQL and MinIO backup"
ZHITUO_PILOT_ENV_FILE="$PILOT_ENV_FILE" bash "$PILOT_ROOT_DIR/scripts/pilot-backup.sh"

changed=false
rollback_images() {
  if [[ "$changed" == "true" && -n "$current_sha" ]]; then
    local current_short="${current_sha:0:12}"
    printf 'FAIL  deployment failed; restoring previous application image references\n' >&2
    pilot_set_env DEPLOYED_GIT_SHA "$current_sha"
    pilot_set_env PREVIOUS_GIT_SHA "$target_sha"
    pilot_set_env ZHITUO_API_IMAGE "zhituo-api:pilot-${current_short}"
    pilot_set_env ZHITUO_WEB_IMAGE "zhituo-web:pilot-${current_short}"
    pilot_load_env
    pilot_compose up -d api worker beat web caddy || true
    printf 'WARN  schema was not automatically downgraded; use the printed pre-migration backup for an explicit restore\n' >&2
  fi
}
trap rollback_images ERR

pilot_set_env PREVIOUS_GIT_SHA "$current_sha"
pilot_set_env DEPLOYED_GIT_SHA "$target_sha"
pilot_set_env ZHITUO_API_IMAGE "zhituo-api:pilot-${target_short}"
pilot_set_env ZHITUO_WEB_IMAGE "zhituo-web:pilot-${target_short}"
changed=true
pilot_load_env

pilot_compose run --rm object-store-init
pilot_compose run --rm migrate
pilot_compose run --rm database-roles
pilot_compose run --rm bootstrap-identity
pilot_compose up -d api worker beat web caddy
if [[ -n "${CLOUDFLARE_TUNNEL_TOKEN:-}" ]]; then
  pilot_compose --profile cloudflare up -d cloudflared
fi

ZHITUO_PILOT_ENV_FILE="$PILOT_ENV_FILE" bash "$PILOT_ROOT_DIR/scripts/pilot-health.sh"
trap - ERR
printf 'PASS  deployed_sha=%s previous_sha=%s\n' "$target_sha" "$current_sha"
