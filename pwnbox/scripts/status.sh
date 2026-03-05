#!/usr/bin/env bash
set -euo pipefail

API_PORT="${PWNBOX_API_PORT:-8100}"
WEB_PORT="${PWNBOX_WEB_PORT:-8001}"

echo "[pwnbox] API health:"
curl -s "http://127.0.0.1:${API_PORT}/api/pwnbox/health" || echo "unreachable"

echo
echo "[pwnbox] Session status:"
curl -s "http://127.0.0.1:${API_PORT}/api/pwnbox/status" || echo "unreachable"

echo
echo "[pwnbox] UI URL: http://127.0.0.1:${WEB_PORT}/pwnbox/web/pwnbox.html"
