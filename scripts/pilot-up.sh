#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE_FILE="$ROOT_DIR/deploy/pilot/docker-compose.yml"
ENV_FILE="${ZHITUO_PILOT_ENV_FILE:-$ROOT_DIR/deploy/pilot/.env}"
RESUME=false

if [[ "${1:-}" == "--resume" ]]; then
  RESUME=true
elif [[ $# -gt 0 ]]; then
  printf 'Usage: %s [--resume]\n' "$0" >&2
  exit 2
fi

fail() {
  printf 'FAIL: %s\n' "$*" >&2
  exit 1
}

info() {
  printf '==> %s\n' "$*"
}

random_hex() {
  local bytes="${1:-32}"
  openssl rand -hex "$bytes"
}

write_env() {
  local git_sha="$1"
  local basic_password="$2"
  local basic_hash="$3"
  local secrets_dir="$4"
  local backup_dir="$5"
  umask 077
  cat > "$ENV_FILE" <<EOF
ZHITUO_API_IMAGE=zhituo-api:pilot-${git_sha}
ZHITUO_WEB_IMAGE=zhituo-web:pilot-${git_sha}
DEPLOYED_GIT_SHA=${git_sha}
PREVIOUS_GIT_SHA=
POSTGRES_OWNER_PASSWORD=$(random_hex 32)
POSTGRES_RUNTIME_PASSWORD=$(random_hex 32)
POSTGRES_BACKUP_PASSWORD=$(random_hex 32)
REDIS_PASSWORD=$(random_hex 32)
MINIO_ROOT_USER=zhituo-pilot
MINIO_ROOT_PASSWORD=$(random_hex 32)
AUTH_PROXY_SECRET=$(random_hex 40)
METRICS_TOKEN=$(random_hex 40)
MINIO_BUCKET=zhituo-pilot-documents
PILOT_SECRETS_DIR='${secrets_dir}'
PILOT_BACKUP_DIR='${backup_dir}'
PILOT_BACKUP_RETENTION_DAYS=14
PILOT_BIND_ADDRESS=127.0.0.1
PILOT_HTTP_PORT=8080
PILOT_BASIC_AUTH_USER=pilot
PILOT_BASIC_AUTH_PASSWORD=${basic_password}
PILOT_BASIC_AUTH_HASH='${basic_hash}'
PILOT_ADMIN_EMAIL=${PILOT_ADMIN_EMAIL:-pilot.owner@example.com}
PILOT_ADMIN_DISPLAY_NAME='Pilot Administrator'
PILOT_ORGANIZATION_NAME='Zhituo Pilot'
PILOT_ORGANIZATION_CODE=${PILOT_ORGANIZATION_CODE:-ZHITUO-PILOT}
CELERY_WORKER_CONCURRENCY=1
AUTHENTICATED_RATE_LIMIT_PER_MINUTE=300
SOURCE_SCAN_MIN_INTERVAL_SECONDS=300
LOG_LEVEL=INFO
AI_BASE_URL=https://api.openai.com/v1
AI_API_KEY=
AI_MODEL_EXTRACTION=
AI_MODEL_ANALYSIS=
CLOUDFLARE_TUNNEL_TOKEN=
EOF
  chmod 600 "$ENV_FILE"
}

command -v docker >/dev/null 2>&1 || fail "Docker Engine is required"
docker compose version >/dev/null 2>&1 || fail "Docker Compose v2 is required"
command -v openssl >/dev/null 2>&1 || fail "openssl is required"

git_sha="$(git -C "$ROOT_DIR" rev-parse --short=12 HEAD 2>/dev/null || true)"
[[ -n "$git_sha" ]] || fail "Pilot must be started from a Git checkout"

if [[ ! -f "$ENV_FILE" ]]; then
  info "Creating strong local Pilot credentials"
  secrets_dir="${PILOT_SECRETS_DIR:-/var/lib/zhituo/secrets}"
  backup_dir="${PILOT_BACKUP_DIR:-/var/lib/zhituo/backups}"
  if ! mkdir -p "$secrets_dir/minio/certs" "$backup_dir" 2>/dev/null; then
    secrets_dir="$ROOT_DIR/deploy/pilot/secrets"
    backup_dir="$ROOT_DIR/deploy/pilot/backups"
    mkdir -p "$secrets_dir/minio/certs" "$backup_dir"
  fi
  basic_password="$(random_hex 18)"
  basic_hash="$(docker run --rm caddy:2.10.2-alpine caddy hash-password --plaintext "$basic_password")"
  write_env "$git_sha" "$basic_password" "$basic_hash" "$secrets_dir" "$backup_dir"
  printf 'Pilot Basic Auth password (also stored in %s): %s\n' "$ENV_FILE" "$basic_password"
fi

set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a

required=(
  POSTGRES_OWNER_PASSWORD POSTGRES_RUNTIME_PASSWORD POSTGRES_BACKUP_PASSWORD
  REDIS_PASSWORD MINIO_ROOT_USER MINIO_ROOT_PASSWORD AUTH_PROXY_SECRET METRICS_TOKEN
  PILOT_SECRETS_DIR PILOT_BACKUP_DIR PILOT_BASIC_AUTH_PASSWORD PILOT_BASIC_AUTH_HASH
  PILOT_ADMIN_EMAIL
)
for name in "${required[@]}"; do
  [[ -n "${!name:-}" ]] || fail "$name is required in $ENV_FILE"
done
if grep -Eqi '=(change-me|password|admin123)([[:space:]]|$)' "$ENV_FILE"; then
  fail "$ENV_FILE contains a forbidden weak secret"
fi
if [[ "$PILOT_ADMIN_EMAIL" == *@zhituo.local ]]; then
  fail "PILOT_ADMIN_EMAIL must not use the demo zhituo.local identity"
fi

mkdir -p "$PILOT_SECRETS_DIR/minio/certs" "$PILOT_BACKUP_DIR"
chmod 700 "$PILOT_SECRETS_DIR" "$PILOT_SECRETS_DIR/minio" "$PILOT_SECRETS_DIR/minio/certs" "$PILOT_BACKUP_DIR"

cert_file="$PILOT_SECRETS_DIR/minio/certs/public.crt"
key_file="$PILOT_SECRETS_DIR/minio/certs/private.key"
if [[ ! -s "$cert_file" || ! -s "$key_file" ]]; then
  info "Generating the private MinIO TLS certificate"
  openssl req -x509 -newkey rsa:3072 -sha256 -nodes -days 825 \
    -subj "/CN=minio" \
    -addext "subjectAltName=DNS:minio,DNS:localhost,IP:127.0.0.1" \
    -keyout "$key_file" -out "$cert_file"
  chmod 600 "$key_file"
  chmod 644 "$cert_file"
fi

compose() {
  docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" "$@"
}

info "Validating Pilot Compose topology"
compose config --quiet

if [[ "$RESUME" == "false" && "${ZHITUO_PILOT_SKIP_BUILD:-false}" != "true" ]]; then
  info "Building immutable application images for $git_sha"
  docker build --pull -t "zhituo-api:pilot-${git_sha}" "$ROOT_DIR/apps/api"
  docker build --pull -f "$ROOT_DIR/apps/web/Dockerfile" -t "zhituo-web:pilot-${git_sha}" "$ROOT_DIR"
else
  info "Reusing existing application images"
  docker image inspect "$ZHITUO_API_IMAGE" >/dev/null
  docker image inspect "$ZHITUO_WEB_IMAGE" >/dev/null
fi

info "Starting persistent PostgreSQL, Redis and TLS MinIO"
compose up -d postgres redis minio
compose run --rm object-store-init

info "Applying migrations and least-privilege database roles"
compose run --rm migrate
compose run --rm database-roles

info "Creating the Pilot administrator identity without demo business data"
compose run --rm bootstrap-identity

info "Starting API, Worker, Beat, Web and loopback ingress"
compose up -d api worker beat web caddy
if [[ -n "${CLOUDFLARE_TUNNEL_TOKEN:-}" ]]; then
  info "Starting the configured outbound Cloudflare Tunnel"
  compose --profile cloudflare up -d cloudflared
fi

ZHITUO_PILOT_ENV_FILE="$ENV_FILE" bash "$ROOT_DIR/scripts/pilot-health.sh"

printf '\nPilot is running at http://%s:%s (Basic Auth required).\n' \
  "${PILOT_BIND_ADDRESS:-127.0.0.1}" "${PILOT_HTTP_PORT:-8080}"
