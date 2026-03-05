# PwnBox API (Step 3: No-Redis Single Session + Terminal Bridge)

This service now manages a real Docker-backed single global session **without Redis**.

## One-command local run (recommended)
From project root:
```bash
./pwnbox/scripts/up.sh
```

This script will:
- build `pwnbox-base:latest` if missing
- create/update API virtualenv
- start PwnBox API on `:8100`
- start static web server on `:8001`

Open:
- `http://127.0.0.1:8001/pwnbox/web/pwnbox.html`

Stop:
```bash
./pwnbox/scripts/down.sh
```

Quick status:
```bash
./pwnbox/scripts/status.sh
```

Live logs:
```bash
./pwnbox/scripts/logs.sh
```

## Run
```bash
cd pwnbox/api
pip install fastapi "uvicorn[standard]" docker pydantic
uvicorn main:app --host 0.0.0.0 --port 8100 --reload
```

## Endpoints
- `GET /api/pwnbox/health`
- `GET /api/pwnbox/status`
- `POST /api/pwnbox/start`
- `DELETE /api/pwnbox/stop`
- `WS /api/pwnbox/ws/{session_id}` (bridged shell via `docker exec`)

## Current behavior
- One active session globally.
- Starts/stops real Docker container (`PWNBOX_IMAGE`, default `pwnbox-base:latest`).
- Persists state to `session_state.json` for restart recovery.
- Reconciles stale state against runtime container status.
- Enforces TTL expiration (`PWNBOX_SESSION_TTL_MINUTES`, default 90).
- WebSocket terminal now proxies input/output to `/bin/sh` inside the active container.

## Env vars
- `PWNBOX_IMAGE` (default: `pwnbox-base:latest`)
- `PWNBOX_WORKDIR` (default: `/home/hacker`)
- `PWNBOX_SESSION_TTL_MINUTES` (default: `90`)
- `PWNBOX_STATE_FILE` (default: `pwnbox/api/session_state.json`)

## Web test page
A basic frontend test terminal is available at:
- `pwnbox/web/pwnbox.html`

It uses `xterm.js` and calls the API start/stop/status endpoints.

## CORS
Default allowed origins:
- `http://127.0.0.1:8001`
- `http://localhost:8001`
- `http://127.0.0.1:8000`
- `http://localhost:8000`

Override with:
- `PWNBOX_ALLOWED_ORIGINS=http://yourhost:8001,http://yourhost:8000`
