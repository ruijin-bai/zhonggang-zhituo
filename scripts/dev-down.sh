#!/usr/bin/env bash
#
# Stop the local demo services started by dev-up.sh. Finds whatever process is listening on
# the API/Web ports and force-kills it, which is more reliable than PID files on Windows where
# `npm run dev` spawns child processes.
#
# Usage:
#   bash scripts/dev-down.sh            # kills :8002 and :3001
#   API_PORT=8001 bash scripts/dev-down.sh
#
# NOTE: 默认端口刻意错开「智眸工笔」项目，避免误杀其 :3000/:8001 服务。

set -uo pipefail

API_PORT="${API_PORT:-8002}"
WEB_PORT="${WEB_PORT:-3001}"

for port in "$API_PORT" "$WEB_PORT"; do
  # netstat -ano | grep LISTENING | last column is the owning PID
  pids=$(netstat -ano 2>/dev/null | grep "LISTENING" | grep ":$port " | awk '{print $NF}' | sort -u)
  if [ -z "$pids" ]; then
    echo "port $port: no listener"
    continue
  fi
  for pid in $pids; do
    echo "port $port: killing pid $pid"
    # Stop-Process is used instead of taskkill because MSYS path-conversion mangles
    # taskkill's /PID and /F flags under Git Bash.
    powershell -NoProfile -Command "Stop-Process -Id $pid -Force -ErrorAction SilentlyContinue" 2>/dev/null || true
  done
done
