"""Configuration (env-first, no config framework)."""

from __future__ import annotations

import os
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[2]


def load_config(overrides: dict | None = None) -> dict:
    cfg = {
        # Local-only binding by default; the DSH GUI uses 19387, this app uses 5000.
        "host": os.environ.get("APP_HOST", "127.0.0.1"),
        "port": int(os.environ.get("APP_PORT", "5000")),
        # Business database lives under instance/; tests override with a temp path.
        "db_path": os.environ.get("APP_DB_PATH", str(ROOT / "instance" / "app.db")),
        # Asia/Shanghai is a fixed +08:00 offset (no DST), so no tzdata dependency is needed.
        "tz_offset_hours": int(os.environ.get("APP_TZ_OFFSET_HOURS", "8")),
        "max_body_bytes": int(os.environ.get("APP_MAX_BODY_BYTES", str(5 * 1024 * 1024))),
        "max_rows_per_batch": int(os.environ.get("APP_MAX_ROWS", "5000")),
    }
    if overrides:
        cfg.update(overrides)
    return cfg
