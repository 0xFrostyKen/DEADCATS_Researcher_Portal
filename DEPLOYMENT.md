# PwnBox Deployment Blueprint (Single Session)

## 1. Purpose
This document defines how to deploy **PwnBox** for DEADCATS as a browser-based training workspace inspired by pwn.college-style infrastructure, but intentionally simplified:

- One active PwnBox session globally (v1)
- Container-isolated shell workspace
- Browser terminal access via WebSocket
- Strong defaults for security and cleanup

---

## 2. High-Level Architecture

```text
-------------------------------------------------------------
| Host Server (Ubuntu)                                      |
|                                                           |
|  Docker Engine + Docker Compose                           |
|   |                                                       |
|   |-- reverse-proxy (nginx/caddy, TLS, WS)               |
|   |-- app-api (existing DEADCATS FastAPI)                |
|   |-- app-api (DEADCATS FastAPI + integrated PwnBox)     |
|   |                                                       |
|   |-- pwnbox-user-container (ephemeral, one at a time)   |
|       - user: hacker (non-root)                          |
|       - toolset: bash/python/jq/gdb/...                  |
|       - strict CPU/RAM/PID limits                        |
|       - timeout + forced cleanup                          |
|                                                           |
-------------------------------------------------------------
```

### Inspiration Mapping (from pwn.college)
- pwn.college “workspace container” concept -> **PwnBox user container**
- pwn.college web access via browser tooling -> **xterm.js + WS bridge**
- pwn.college strict infra separation -> **logical PwnBox isolation via dedicated router + container lifecycle**
- pwn.college lifecycle control -> **session start/stop/timeout + cleanup worker**

We intentionally skip DinD and multi-node in v1.

---

## 3. Scope (v1)

### Included
- Single global session lock
- Start / status / stop APIs
- Browser terminal page (`pwnbox.html`) using `xterm.js`
- Auto-timeout and forced container removal
- Basic audit logging (start/stop/owner/IP)
- Live shell bridge over WebSocket via `docker exec`

### Excluded (for now)
- Multiple concurrent sessions
- Persistent per-user home volumes
- SSH access into PwnBox
- VSCode/desktop services
- Multi-node orchestration

---

## 4. Components

## 4.1 Existing DEADCATS API
Responsible for:
- User authentication
- Authorizing who can launch PwnBox
- UI integration (sidebar/page links)

## 4.2 Integrated PwnBox Router (`/api/pwnbox`)
Responsibilities:
- Acquire/release single session lock
- Start/stop container via Docker API/SDK
- Create PTY and bridge terminal traffic over WebSocket
- Enforce max duration + idle timeout

Recommended stack:
- FastAPI + Uvicorn
- Python Docker SDK

## 4.3 Local state file (no Redis in v1)
Used for single-session persistence/recovery on one host:
- `session_state.json` stores active session metadata
- API startup reconciles saved state with Docker runtime

## 4.4 PwnBox image
Base image includes:
- Non-root user `hacker` (UID 1000)
- Common training tools (`bash`, `python3`, `jq`, `curl`, `gcc`, `gdb`, etc.)
- Minimal writable paths only

---

## 5. Session Model (Single Session)

Only one global session can exist at any time.

Session record fields:
- `session_id`
- `owner_user_id`
- `owner_handle`
- `container_id`
- `started_at`
- `expires_at`
- `status` (`active|stopping|expired`)

Rules:
1. `POST /api/pwnbox/start` checks local session state under process lock.
2. If saved session exists and container alive -> reject with active session info.
3. On stop/timeout/crash -> remove container and clear state file.
4. Startup recovery: on `pwnbox-api` boot, reconcile `session_state.json` vs actual container state.

---

## 6. API Contract (PwnBox Service)

### `POST /api/pwnbox/start`
Starts the single session if free.

Returns:
- `201` with `{ session_id, expires_at }`
- `409` if session already active

### `GET /api/pwnbox/status`
Returns active session metadata or idle state.

### `DELETE /api/pwnbox/stop`
Stops active container and clears lock.

### `WS /api/pwnbox/ws/{session_id}`
Terminal I/O stream.
- input: keystrokes/resize
- output: shell stdout/stderr

Implementation in v1:
- WebSocket handler runs `docker exec -i <container> /bin/sh -i`
- Process stdout/stderr is streamed to browser
- Browser input is piped to process stdin

---

## 7. Security Baseline (Mandatory)

Container runtime flags:
- `--user 1000:1000`
- `--cap-drop=ALL`
- `--security-opt no-new-privileges`
- `--pids-limit=256`
- `--memory=1024m`
- `--cpus=1.0`
- `--network=none` (default in v1)
- `--read-only` (if compatible)
- `--tmpfs /tmp:rw,noexec,nosuid,size=128m`

Host/network hardening:
- Never mount Docker socket into user containers
- Firewall allowlist: `22,80,443` only
- Reverse proxy rate limit on `/api/pwnbox/start`
- Log every session action + source IP

---

## 8. Deployment Steps

## 8.1 Prepare host
- Ubuntu 22.04/24.04 LTS
- Install Docker + Compose plugin
- Configure DNS and TLS certs

## 8.2 Add services
- Ensure existing backend service has Docker daemon access
- Optional: pre-build `pwnbox-base` image (otherwise auto-build on first start)
- Set env `PWNBOX_AUTO_BUILD=true` (default) for automatic image bootstrap
- Add reverse proxy route:
  - `/api/pwnbox/*` -> existing backend service
  - WebSocket upgrade enabled

## 8.3 Integrate frontend
- New `pwnbox.html`
- Add Start/Stop/Reset controls
- Embed terminal (`xterm.js`)
- Show status banner if session is occupied

Reference starter page:
- `pwnbox/web/pwnbox.html`

## 8.4 Add cleanup worker
- Every 30–60s:
  - check expiry
  - stop stale container
  - clear stale session state file if container is gone

## 8.5 Validation checklist
- Start session from UI
- Reject second start while active
- Terminal I/O works
- Timeout cleanup works
- Restart `pwnbox-api` and verify lock/container reconciliation

---


## 8.6 Quickstart Script (for collaborators)
Use repository scripts so collaborators do not manually run many commands:

```bash
./pwnbox/scripts/up.sh
```

This will bootstrap image, API environment, and local web server automatically.

Related commands:
```bash
./pwnbox/scripts/status.sh
./pwnbox/scripts/logs.sh
./pwnbox/scripts/down.sh
```

## 9. Suggested File/Service Layout

```text
backend/
  routers/
    pwnbox.py
  pwnbox_session_state.json

pwnbox.html

docker-compose.yml (optional)
nginx.conf (optional)
```

---

## 10. Operations Runbook

### Check active session
- `GET /api/pwnbox/status`
- `docker ps --filter name=pwnbox-`

### Force cleanup
1. Stop/remove active container
2. Remove stale `session_state.json` only if container is confirmed absent
3. Confirm status endpoint returns idle

### Incident response
- If abuse suspected:
  1. Stop session immediately
  2. Capture logs (API + proxy + docker events)
  3. Rotate any exposed secrets

---

## 11. Phase-2 Roadmap (After v1 stable)
- Per-user concurrent sessions (quota controlled)
- Persistent home volumes (size-limited)
- Limited outbound network profiles per challenge
- SSH gateway into active PwnBox
- Challenge templates and reset snapshots
- Optional multi-node worker model

---

## 12. Naming
This deployment is called **PwnBox** in UI, API paths, logs, and docs.
