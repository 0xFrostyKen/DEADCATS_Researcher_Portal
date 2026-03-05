#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PWNBOX_DIR="$ROOT_DIR/pwnbox"
RUN_DIR="$PWNBOX_DIR/.run"
API_PID_FILE="$RUN_DIR/pwnbox-api.pid"
WEB_PID_FILE="$RUN_DIR/pwnbox-web.pid"
API_PORT="${PWNBOX_API_PORT:-8100}"

stop_pid_file() {
  local pid_file="$1"
  local name="$2"
  if [[ ! -f "$pid_file" ]]; then
    echo "[pwnbox] $name not running (no pid file)"
    return
  fi
  local pid
  pid="$(cat "$pid_file" || true)"
  if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then
    echo "[pwnbox] stopping $name (pid $pid)"
    kill "$pid" 2>/dev/null || true
    sleep 0.3
    if kill -0 "$pid" 2>/dev/null; then
      kill -9 "$pid" 2>/dev/null || true
    fi
  else
    echo "[pwnbox] $name already stopped"
  fi
  rm -f "$pid_file"
}

# Ask API to stop active session/container first.
if command -v curl >/dev/null 2>&1; then
  curl -s -X DELETE "http://127.0.0.1:${API_PORT}/api/pwnbox/stop" >/dev/null 2>&1 || true
fi

stop_pid_file "$API_PID_FILE" "pwnbox-api"
stop_pid_file "$WEB_PID_FILE" "pwnbox-web"

echo "[pwnbox] stopped"
