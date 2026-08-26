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

[[ -f "$ENV_FILE" ]] || fail "Missing staging env file: $ENV_FILE"
command -v docker >/dev/null 2>&1 || fail "Docker is required"
command -v curl >/dev/null 2>&1 || fail "curl is required"

set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a

compose() {
  docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" "$@"
}

retry_http() {
  local url="$1"
  local header="${2:-}"
  local attempt
  for attempt in {1..60}; do
    if [[ -n "$header" ]]; then
      if curl --fail --silent --show-error -H "$header" "$url" >/dev/null 2>&1; then
        return 0
      fi
    elif curl --fail --silent --show-error "$url" >/dev/null 2>&1; then
      return 0
    fi
    sleep 1
  done
  fail "HTTP endpoint did not become ready: $url"
}

info "Checking PostgreSQL"
compose exec -T postgres pg_isready -U zhituo -d zhituo >/dev/null

info "Checking Redis"
test "$(compose exec -T redis redis-cli ping | tr -d '\r')" = "PONG"

info "Checking MinIO"
retry_http "http://127.0.0.1:${STAGING_MINIO_API_PORT:-9000}/minio/health/live"

info "Checking Mailpit HTTP API"
retry_http "http://127.0.0.1:${STAGING_MAILPIT_PORT:-8025}/api/v1/messages"

info "Checking API readiness inside the staging network"
compose exec -T api python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health/ready', timeout=5).read()"

info "Checking Web → BFF → API → PostgreSQL"
retry_http "http://127.0.0.1:${STAGING_WEB_PORT:-3001}/pursuit" "X-Zhituo-User: admin@zhituo.local"

probe_subject="ZHITUO-STAGING-SMOKE-$(date +%s)"
info "Checking SMTP delivery into Mailpit"
compose exec -T -e SMOKE_SUBJECT="$probe_subject" api python - <<'PY'
import os
import smtplib
from email.message import EmailMessage

message = EmailMessage()
message["From"] = "zhituo-staging@example.invalid"
message["To"] = "smoke@example.invalid"
message["Subject"] = os.environ["SMOKE_SUBJECT"]
message.set_content("Zhituo staging SMTP smoke probe")
with smtplib.SMTP("mailpit", 1025, timeout=5) as client:
    client.send_message(message)
PY

for attempt in {1..20}; do
  if curl --fail --silent "http://127.0.0.1:${STAGING_MAILPIT_PORT:-8025}/api/v1/messages" | grep -Fq "$probe_subject"; then
    info "Staging smoke checks passed"
    exit 0
  fi
  sleep 1
done

fail "Mailpit did not record the SMTP smoke probe"
