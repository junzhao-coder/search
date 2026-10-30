"""SQLite access: per-request connection, migrations, seeds (no ORM, no migration framework)."""

from __future__ import annotations

import pathlib
import sqlite3

from flask import current_app, g

from ..core.util import now_utc
from ..core.config import ROOT

MIGRATIONS_DIR = pathlib.Path(__file__).resolve().parent / "migrations"


class SchemaVersionError(RuntimeError):
    """库 schema 版本高于代码支持版本：拒绝启动（CONTRACT L767）。"""


def app_schema_version() -> int:
    """代码支持的 schema 上限：迁移文件名最大版本前缀（与 CONTRACT L767 对齐）。"""
    versions = [int(path.name.split("_", 1)[0]) for path in MIGRATIONS_DIR.glob("*.sql")]
    return max(versions) if versions else 0


def connect(db_path: str) -> sqlite3.Connection:
    path = pathlib.Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), isolation_level=None, timeout=5.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    return conn


def _statements(sql: str) -> list[str]:
    """Split a migration file into statements (no semicolons appear inside literals here)."""
    lines = []
    for line in sql.splitlines():
        if line.strip().startswith("--"):
            continue
        lines.append(line)
    body = "\n".join(lines)
    return [stmt.strip() for stmt in body.split(";") if stmt.strip()]


def ensure_schema(db_path: str) -> int:
    """Apply pending migrations in one transaction each; returns the schema version."""
    conn = connect(db_path)
    try:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS schema_migrations ("
            " version INTEGER PRIMARY KEY, name TEXT NOT NULL, applied_at TEXT NOT NULL)"
        )
        applied = {row["version"] for row in conn.execute("SELECT version FROM schema_migrations")}
        supported = app_schema_version()
        current = max(applied) if applied else 0
        if current > supported:                       # CONTRACT L767：库版本更高须拒绝启动
            raise SchemaVersionError(
                f"库版本高于代码支持版本：库={current} 代码支持={supported}；拒绝启动，"
                f"请使用匹配版本的应用或迁移脚本；MIGRATIONS_DIR={MIGRATIONS_DIR}")
        for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
            version = int(path.name.split("_", 1)[0])
            if version in applied:
                continue
            conn.execute("BEGIN")
            try:
                for stmt in _statements(path.read_text(encoding="utf-8")):
                    conn.execute(stmt)
                conn.execute(
                    "INSERT INTO schema_migrations(version, name, applied_at) VALUES (?,?,?)",
                    (version, path.name, now_utc()),
                )
                conn.execute("COMMIT")
            except Exception:
                conn.execute("ROLLBACK")
                raise
        row = conn.execute("SELECT MAX(version) AS v FROM schema_migrations").fetchone()
        return int(row["v"] or 0)
    finally:
        conn.close()


def schema_version(db_path: str) -> int:
    conn = connect(db_path)
    try:
        row = conn.execute("SELECT MAX(version) AS v FROM schema_migrations").fetchone()
        return int(row["v"] or 0)
    finally:
        conn.close()


def init_app(app) -> None:
    @app.teardown_appcontext
    def _close(_exc):  # pragma: no cover - trivial
        conn = g.pop("db", None)
        if conn is not None:
            conn.close()


def get_db() -> sqlite3.Connection:
    if "db" not in g:
        cfg = current_app.config["APP_CFG"]
        g.db = connect(cfg["db_path"])
    return g.db


def default_db_path() -> str:
    return str(ROOT / "instance" / "app.db")
