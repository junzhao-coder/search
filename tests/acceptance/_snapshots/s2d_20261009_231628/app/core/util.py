"""Small shared helpers (time, ids)."""

from __future__ import annotations

import datetime as _dt
import secrets
import uuid


def slug_id(prefix: str, length: int = 16) -> str:
    """``<prefix>_<hex>`` primary keys, per contract §0.1."""
    return f"{prefix}_{uuid.uuid4().hex[:length]}"


def random_token(length: int = 32) -> str:
    return secrets.token_hex(length // 2)


def now_utc() -> str:
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def today_local(offset_hours: int = 8) -> str:
    tz = _dt.timezone(_dt.timedelta(hours=offset_hours))
    return _dt.datetime.now(tz).strftime("%Y-%m-%d")


def local_date_of(offset_hours: int = 8) -> str:
    return today_local(offset_hours)
