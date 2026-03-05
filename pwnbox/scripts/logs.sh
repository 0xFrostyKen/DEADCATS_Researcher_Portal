#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
LOG_DIR="$ROOT_DIR/pwnbox/.run"
API_LOG="$LOG_DIR/pwnbox-api.log"
WEB_LOG="$LOG_DIR/pwnbox-web.log"

mkdir -p "$LOG_DIR"
touch "$API_LOG" "$WEB_LOG"

echo "[pwnbox] tailing logs"
echo "  API: $API_LOG"
echo "  WEB: $WEB_LOG"
echo

# Use tail with labels via awk to keep it readable.
tail -n 50 -f "$API_LOG" "$WEB_LOG" | awk '
  /^==> .*pwnbox-api\.log <==$/ {ctx="[api]"; next}
  /^==> .*pwnbox-web\.log <==$/ {ctx="[web]"; next}
  {print ctx " " $0}
'
