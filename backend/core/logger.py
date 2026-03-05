import json, os, time
from datetime import datetime, timezone
from pathlib import Path

LOG_DIR = Path(__file__).parent.parent.parent / "logs"
LOG_DIR.mkdir(exist_ok=True)

RETENTION_DAYS = 7

def _write(logfile: str, entry: dict):
    entry["ts"] = datetime.now(timezone.utc).isoformat()
    with open(LOG_DIR / logfile, "a") as f:
        f.write(json.dumps(entry) + "\n")

def log_auth(handle: str, ip: str, success: bool, reason: str = ""):
    _write("auth.log", {"handle": handle, "ip": ip, "success": success, "reason": reason})

def log_admin(admin: str, action: str, target: str, detail: str = ""):
    _write("admin.log", {"admin": admin, "action": action, "target": target, "detail": detail})
    _write("alerts.log", {"level": "info", "type": "admin_action", "msg": f"{admin} → {action} on {target}"})

def log_upload(handle: str, filename: str, size: int, filetype: str):
    _write("uploads.log", {"handle": handle, "filename": filename, "size": size, "type": filetype})
    if size > 10 * 1024 * 1024:
        _write("alerts.log", {"level": "warn", "type": "large_upload", "msg": f"{handle} uploaded {filename} ({size//1024//1024}MB)"})

def log_ioc(handle: str, action: str, ioc_type: str, value: str):
    _write("iocs.log", {"handle": handle, "action": action, "ioc_type": ioc_type, "value": value})

def log_alert(level: str, alert_type: str, msg: str):
    _write("alerts.log", {"level": level, "type": alert_type, "msg": msg})

def log_new_user(handle: str, ip: str):
    _write("alerts.log", {"level": "info", "type": "new_user", "msg": f"New user registered: {handle} from {ip}"})

def purge_old_logs():
    cutoff = time.time() - (RETENTION_DAYS * 86400)
    for logfile in LOG_DIR.glob("*.log"):
        lines = []
        try:
            with open(logfile) as f:
                for line in f:
                    try:
                        entry = json.loads(line)
                        ts = datetime.fromisoformat(entry["ts"]).timestamp()
                        if ts > cutoff:
                            lines.append(line)
                    except:
                        pass
            with open(logfile, "w") as f:
                f.writelines(lines)
        except:
            pass

def read_log(logfile: str, limit: int = 100) -> list:
    path = LOG_DIR / logfile
    if not path.exists():
        return []
    try:
        with open(path) as f:
            lines = f.readlines()
    except:
        return []
    entries = []
    for line in reversed(lines[-500:]):
        try:
            entries.append(json.loads(line))
        except:
            pass
        if len(entries) >= limit:
            break
    return entries
