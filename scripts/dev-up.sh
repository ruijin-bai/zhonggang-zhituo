#!/usr/bin/env bash
#
# One-command local demo bootstrap (competition build).
#
# Starts the API on SQLite + the Web UI with zero Docker dependency, seeds the demo
# opportunities, and runs a health check. Production keeps PostgreSQL + migrations; this
# script is for local development, demos and reviewer reproductions only.
#
# Usage:
#   bash scripts/dev-up.sh            # API :8002, Web :3001
#   API_PORT=8001 bash scripts/dev-up.sh
#   WEB_PORT=3002 bash scripts/dev-up.sh
#
# NOTE: 默认端口刻意错开「智眸工笔」项目（其前端占 :3000、后端占 :8001），
#       避免本机两个项目同时开发时端口冲突。Ctrl+C stops both services.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

PY="$ROOT/apps/api/.venv/Scripts/python.exe"
DB_FILE="$ROOT/data/zhituo.db"
API_PORT="${API_PORT:-8002}"
WEB_PORT="${WEB_PORT:-3001}"

if [ ! -f "$PY" ]; then
  echo "error: backend virtualenv not found at $PY" >&2
  echo "bootstrap it with:" >&2
  echo "  cd apps/api && python -m venv .venv && .venv/Scripts/python.exe -m pip install -e ." >&2
  exit 1
fi

if [ ! -d "$ROOT/node_modules" ]; then
  echo "error: frontend deps missing; run: npm ci" >&2
  exit 1
fi

# SQLite demo database. RLS/queue are PostgreSQL-only; inline jobs keep the demo independent
# of Redis. These are exported as env so they override any stale values in a local .env.
#
# SQLAlchemy's sqlite URL needs forward slashes on Windows, so normalize the path (cygpath -m
# yields a mixed-style path like D:/foo/bar.db) and fall back to replacing backslashes.
if command -v cygpath >/dev/null 2>&1; then
  DB_URL_PATH="$(cygpath -m "$DB_FILE")"
else
  DB_URL_PATH="$(printf '%s' "$DB_FILE" | sed 's#\\#/#g')"
fi
export DATABASE_URL="sqlite:///$DB_URL_PATH"
export DATA_BACKEND=database
export DATABASE_RLS_ENABLED=false
export JOB_MODE=inline
export APP_ENV=development
export AUTH_MODE=development_header
export DEV_USER_EMAIL=admin@zhituo.local

echo "[1/4] initializing SQLite demo database ..."
(cd apps/api && "$PY" -m app.cli init-db)

echo "[2/4] starting API on http://127.0.0.1:$API_PORT ..."
(cd apps/api && "$PY" -m uvicorn app.main:app --host 127.0.0.1 --port "$API_PORT") &
API_PID=$!

echo "[3/4] starting Web on http://127.0.0.1:$WEB_PORT ..."
# The Web BFF (server-api.ts) reads API_BASE_URL at request time; pinning it here so the
# server-side fetch targets the API port we just started, not the hardcoded 8000 default.
export API_BASE_URL="http://127.0.0.1:$API_PORT"
(cd apps/web && npm run dev -- --port "$WEB_PORT") &
WEB_PID=$!

cleanup() {
  # Tear down by port rather than PID: on Windows `npm run dev` spawns child node
  # processes, so killing the recorded PID leaves orphans. dev-down.sh finds whatever
  # is listening on the two ports and force-stops it.
  API_PORT="$API_PORT" WEB_PORT="$WEB_PORT" bash "$ROOT/scripts/dev-down.sh" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

echo "[4/4] waiting for API health ..."
for _ in $(seq 1 40); do
  if curl -sf "http://127.0.0.1:$API_PORT/health" >/dev/null 2>&1; then
    echo ""
    echo "  API  healthy:  http://127.0.0.1:$API_PORT/health"
    echo "  Web  UI:       http://127.0.0.1:$WEB_PORT"
    echo "  (Ctrl+C to stop both services)"
    break
  fi
  sleep 1
done

wait
