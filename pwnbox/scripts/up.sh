#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PWNBOX_DIR="$ROOT_DIR/pwnbox"
API_DIR="$PWNBOX_DIR/api"
RUN_DIR="$PWNBOX_DIR/.run"
LOG_DIR="$PWNBOX_DIR/.run"
API_PID_FILE="$RUN_DIR/pwnbox-api.pid"
WEB_PID_FILE="$RUN_DIR/pwnbox-web.pid"
API_LOG="$LOG_DIR/pwnbox-api.log"
WEB_LOG="$LOG_DIR/pwnbox-web.log"

API_PORT="${PWNBOX_API_PORT:-8100}"
WEB_PORT="${PWNBOX_WEB_PORT:-8001}"
PWNBOX_IMAGE="${PWNBOX_IMAGE:-pwnbox-base:latest}"

mkdir -p "$RUN_DIR" "$LOG_DIR"

need_cmd() {
  command -v "$1" >/dev/null 2>&1 || { echo "[pwnbox] missing required command: $1"; exit 1; }
}

is_pid_running() {
  local pid="$1"
  [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null
}

port_in_use() {
  local port="$1"
  ss -ltn "sport = :$port" 2>/dev/null | tail -n +2 | grep -q .
}

start_api() {
  if [[ -f "$API_PID_FILE" ]]; then
    local pid
    pid="$(cat "$API_PID_FILE" || true)"
    if is_pid_running "$pid"; then
      echo "[pwnbox] API already running (pid $pid)"
      return
    fi
    rm -f "$API_PID_FILE"
  fi

  if port_in_use "$API_PORT"; then
    echo "[pwnbox] port $API_PORT is already in use. Set PWNBOX_API_PORT or free the port."
    exit 1
  fi

  if [[ ! -d "$API_DIR/.venv" ]]; then
    echo "[pwnbox] creating virtualenv..."
    python3 -m venv "$API_DIR/.venv"
  fi

  echo "[pwnbox] installing/updating API dependencies..."
  # shellcheck disable=SC1091
  source "$API_DIR/.venv/bin/activate"
  pip install -q -r "$API_DIR/requirements.txt"

  echo "[pwnbox] starting API on :$API_PORT"
  (
    cd "$API_DIR"
    nohup env PWNBOX_IMAGE="$PWNBOX_IMAGE" uvicorn main:app --host 0.0.0.0 --port "$API_PORT" --reload >"$API_LOG" 2>&1 &
    echo $! > "$API_PID_FILE"
  )
}

start_web() {
  if [[ -f "$WEB_PID_FILE" ]]; then
    local pid
    pid="$(cat "$WEB_PID_FILE" || true)"
    if is_pid_running "$pid"; then
      echo "[pwnbox] web server already running (pid $pid)"
      return
    fi
    rm -f "$WEB_PID_FILE"
  fi

  if port_in_use "$WEB_PORT"; then
    echo "[pwnbox] port $WEB_PORT is already in use. Set PWNBOX_WEB_PORT or free the port."
    exit 1
  fi

  echo "[pwnbox] starting static web server on :$WEB_PORT"
  (
    cd "$ROOT_DIR"
    nohup python3 -m http.server "$WEB_PORT" >"$WEB_LOG" 2>&1 &
    echo $! > "$WEB_PID_FILE"
  )
}

ensure_docker_image() {
  if ! docker info >/dev/null 2>&1; then
    echo "[pwnbox] docker daemon unavailable. Start Docker first."
    exit 1
  fi

  if docker image inspect "$PWNBOX_IMAGE" >/dev/null 2>&1; then
    echo "[pwnbox] image $PWNBOX_IMAGE already exists"
    return
  fi

  echo "[pwnbox] building missing image $PWNBOX_IMAGE"
  docker build -t "$PWNBOX_IMAGE" -f - "$ROOT_DIR" <<'DOCKERFILE'
FROM ubuntu:24.04
RUN apt-get update && apt-get install -y --no-install-recommends \
    bash coreutils ca-certificates python3 python3-pip curl jq \
    gcc gdb make file less vim-tiny \
 && rm -rf /var/lib/apt/lists/*
RUN if ! getent passwd 1000 >/dev/null; then useradd -m -u 1000 -s /bin/bash hacker; fi \
 && mkdir -p /home/hacker \
 && chown -R 1000:1000 /home/hacker
USER 1000:1000
WORKDIR /home/hacker
CMD ["/bin/sh","-lc","sleep infinity"]
DOCKERFILE
}

main() {
  need_cmd docker
  need_cmd python3
  need_cmd ss

  ensure_docker_image
  start_api
  start_web

  echo
  echo "[pwnbox] ready"
  echo "  API:  http://127.0.0.1:${API_PORT}"
  echo "  UI:   http://127.0.0.1:${WEB_PORT}/pwnbox/web/pwnbox.html"
  echo "  Logs: $API_LOG | $WEB_LOG"
  echo "  Stop: $PWNBOX_DIR/scripts/down.sh"
}

main "$@"
