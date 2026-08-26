#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE_FILE="$ROOT_DIR/deploy/staging/docker-compose.yml"
ENV_FILE="${ZHITUO_STAGING_ENV_FILE:-$ROOT_DIR/deploy/staging/.env}"

fail() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

info() {
  printf '==> %s\n' "$*"
}

random_secret() {
  if command -v openssl >/dev/null 2>&1; then
    openssl rand -hex 24
  elif command -v python3 >/dev/null 2>&1; then
    python3 -c 'import secrets; print(secrets.token_urlsafe(36))'
  else
    fail "openssl or python3 is required to generate staging secrets"
  fi
}

command -v docker >/dev/null 2>&1 || fail "Docker is required"
docker compose version >/dev/null 2>&1 || fail "Docker Compose v2 is required"

if [[ ! -f "$ENV_FILE" ]]; then
  info "Creating local staging environment: $ENV_FILE"
  umask 077
  cat > "$ENV_FILE" <<EOF
ZHITUO_API_IMAGE=zhituo-api:staging
ZHITUO_WEB_IMAGE=zhituo-web:staging
POSTGRES_PASSWORD=$(random_secret)
MINIO_ROOT_USER=zhituo-staging
MINIO_ROOT_PASSWORD=$(random_secret)
STAGING_WEB_PORT=3001
STAGING_POSTGRES_PORT=55432
STAGING_SMTP_PORT=1025
STAGING_MAILPIT_PORT=8025
STAGING_MINIO_API_PORT=9000
STAGING_MINIO_CONSOLE_PORT=9001
CELERY_WORKER_CONCURRENCY=2
EOF
fi

if grep -Eq '(^|=)change-me' "$ENV_FILE"; then
  fail "$ENV_FILE still contains change-me placeholders"
fi

set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a

: "${ZHITUO_API_IMAGE:?ZHITUO_API_IMAGE is required}"
: "${ZHITUO_WEB_IMAGE:?ZHITUO_WEB_IMAGE is required}"
: "${POSTGRES_PASSWORD:?POSTGRES_PASSWORD is required}"
: "${MINIO_ROOT_USER:?MINIO_ROOT_USER is required}"
: "${MINIO_ROOT_PASSWORD:?MINIO_ROOT_PASSWORD is required}"

compose() {
  docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" "$@"
}

info "Validating staging Compose topology"
compose config --quiet

if [[ "${ZHITUO_STAGING_SKIP_BUILD:-false}" != "true" ]]; then
  info "Building staging images from the current checkout"
  docker build -t "$ZHITUO_API_IMAGE" "$ROOT_DIR/apps/api"
  docker build -f "$ROOT_DIR/apps/web/Dockerfile" -t "$ZHITUO_WEB_IMAGE" "$ROOT_DIR"
else
  info "Reusing prebuilt staging images"
  docker image inspect "$ZHITUO_API_IMAGE" >/dev/null
  docker image inspect "$ZHITUO_WEB_IMAGE" >/dev/null
fi

info "Starting persistent infrastructure"
compose up -d postgres redis minio mailpit

info "Ensuring the S3-compatible staging bucket exists"
compose run --rm object-store-init

info "Applying database migrations"
compose run --rm migrate

if [[ "${ZHITUO_STAGING_SKIP_SEED:-false}" != "true" ]]; then
  info "Applying deterministic internal staging seed"
  compose --profile demo run --rm seed
fi

info "Starting API, Worker, Beat and Web"
compose up -d api worker beat web

info "Running staging smoke checks"
ZHITUO_STAGING_ENV_FILE="$ENV_FILE" "$ROOT_DIR/scripts/staging-smoke.sh"

cat <<EOF

Staging is running with persistent Docker volumes.
Web:           http://127.0.0.1:${STAGING_WEB_PORT:-3001}
Mailpit:       http://127.0.0.1:${STAGING_MAILPIT_PORT:-8025}
MinIO console: http://127.0.0.1:${STAGING_MINIO_CONSOLE_PORT:-9001}

Normal shutdown keeps PostgreSQL, Redis, MinIO and Mailpit data:
  bash scripts/staging-down.sh
EOF
