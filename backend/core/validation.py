from __future__ import annotations

import os
import re
from fastapi import HTTPException

_CTRL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def clean_text(value: str | None, *, field: str, max_len: int, strip: bool = True) -> str:
    if value is None:
        return ""
    text = value.strip() if strip else value
    text = _CTRL_RE.sub("", text)
    if len(text) > max_len:
        raise HTTPException(status_code=400, detail=f"{field} is too long (max {max_len} chars).")
    return text


def reject_html(value: str, *, field: str) -> str:
    if "<" in value or ">" in value:
        raise HTTPException(status_code=400, detail=f"{field} cannot contain angle brackets.")
    return value


def safe_download_name(name: str, *, fallback: str = "download.bin", max_len: int = 180) -> str:
    base = os.path.basename(name or "").strip().replace("\x00", "")
    if not base:
        return fallback
    if len(base) > max_len:
        root, ext = os.path.splitext(base)
        keep = max(1, max_len - len(ext))
        base = root[:keep] + ext
    return base


def csv_safe_cell(value) -> str:
    s = "" if value is None else str(value)
    if s and s[0] in ("=", "+", "-", "@"):
        return "'" + s
    return s
