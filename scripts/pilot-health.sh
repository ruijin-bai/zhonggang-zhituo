#!/usr/bin/env bash
set -uo pipefail

# shellcheck source=scripts/lib/pilot-common.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib/pilot-common.sh"

pilot_require_command docker
pilot_require_command curl
pilot_load_env

failures=0

pass() {
  printf 'PASS  %s\n' "$*"
}

fail() {
  printf 'FAIL  %s\n' "$*" >&2
  failures=$((failures + 1))
}

warn() {
  printf 'WARN  %s\n' "$*"
}

check_service() {
  local service="$1"
  if pilot_running "$service"; then
    pass "$service container is running"
  else
    fail "$service container is not running"
  fi
}

for service in postgres redis minio api worker beat web caddy; do
  check_service "$service"
done
if [[ -n "${CLOUDFLARE_TUNNEL_TOKEN:-}" ]]; then
  check_service cloudflared
fi

if pilot_compose exec -T postgres pg_isready -U zhituo_owner -d zhituo >/dev/null 2>&1; then
  pass "PostgreSQL accepts connections"
else
  fail "PostgreSQL readiness failed"
fi

redis_reply="$(pilot_compose exec -T redis redis-cli -a "$REDIS_PASSWORD" --no-auth-warning ping 2>/dev/null | tr -d '\r' || true)"
if [[ "$redis_reply" == "PONG" ]]; then
  pass "Redis authenticated ping"
else
  fail "Redis authenticated ping failed"
fi

if pilot_compose exec -T api python - <<'PY' >/dev/null 2>&1
import os
import boto3

client = boto3.client(
    "s3",
    endpoint_url=os.environ["DOCUMENT_STORE_S3_ENDPOINT_URL"],
    region_name=os.environ["DOCUMENT_STORE_S3_REGION"],
)
client.head_bucket(Bucket=os.environ["DOCUMENT_STORE_S3_BUCKET"])
PY
then
  pass "MinIO TLS and document bucket"
else
  fail "MinIO TLS or document bucket check failed"
fi

if pilot_compose exec -T api python -c \
  "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health/live', timeout=5).read()" \
  >/dev/null 2>&1; then
  pass "FastAPI liveness"
else
  fail "FastAPI liveness failed"
fi

if pilot_compose exec -T api python -c \
  "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health/ready', timeout=5).read()" \
  >/dev/null 2>&1; then
  pass "FastAPI readiness (PostgreSQL and Redis)"
else
  fail "FastAPI readiness failed"
fi

web_url="http://${PILOT_BIND_ADDRESS:-127.0.0.1}:${PILOT_HTTP_PORT:-8080}/pursuit"
if curl --fail --silent --show-error \
  --user "${PILOT_BASIC_AUTH_USER:-pilot}:${PILOT_BASIC_AUTH_PASSWORD}" \
  "$web_url" >/dev/null 2>&1; then
  pass "Web -> BFF -> API authenticated request"
else
  fail "Web -> BFF -> API request failed: $web_url"
fi

worker_ping="$(pilot_compose exec -T api celery -A app.celery_app.celery_app inspect ping --timeout=10 2>&1 || true)"
if grep -Fq 'pong' <<<"$worker_ping"; then
  pass "Celery Worker ping"
else
  fail "Celery Worker did not answer ping"
fi

if pilot_running beat && pilot_compose exec -T beat test -e \
  /var/lib/zhituo/celery/celerybeat-schedule >/dev/null 2>&1; then
  pass "Celery Beat process and durable schedule"
else
  fail "Celery Beat schedule is not available"
fi

scan_summary="$(pilot_compose exec -T -e PGPASSWORD="$POSTGRES_RUNTIME_PASSWORD" postgres \
  psql -h postgres -U zhituo_runtime -d zhituo -Atc \
  "SELECT COALESCE(MAX(finished_at)::text, 'none') FROM source_scan_runs;" 2>/dev/null || true)"
if [[ -z "$scan_summary" || "$scan_summary" == "none" ]]; then
  warn "No completed source scan recorded yet"
else
  pass "Latest completed source scan: $scan_summary"
fi

if (( failures > 0 )); then
  printf '\nFAIL  Pilot health checks failed: %d\n' "$failures" >&2
  exit 1
fi

printf '\nPASS  All required Pilot health checks passed\n'
