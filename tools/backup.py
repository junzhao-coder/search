"""S6 备份脚本（形态 b：脚本写契约路径与命名，**设计 §2/§10 B-01**）。

- 方式：标准库 ``sqlite3.Connection.backup()``（源库以 **``mode=ro``** URI 只读打开，
  不修改源库、不产生写入）；目标文件独占创建，**同名即失败、绝不覆盖**。
- 产物：``<out-dir>/app-YYYYMMDD-HHMMSS.db``（默认 ``instance/backups/``，与 CONTRACT §6 命名一致）
  + 同名 ``.manifest.json``（清单：sha256/字节/integrity/foreign_key/表计数/3 表行级哈希/
  schema_version/源库 wal-smh 存在性/耗时）。
- 校验：``verify_manifest()`` 重新计算并与清单逐项比对（供 restore.py 与测试复用）。
- 本脚本**不启动应用、不联网、不加依赖**；单写者前提下建议先停应用（quiesce）再备份。

退出码：0 成功；2 参数/冲突/校验失败；1 运行异常。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import sqlite3
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.util import now_utc                     # noqa: E402
from app.storage.db import MIGRATIONS_DIR              # noqa: E402

DEFAULT_DB = ROOT / "instance" / "app.db"
DEFAULT_OUT_DIR = ROOT / "instance" / "backups"
MANIFEST_KIND = "sqlite_backup_manifest_v1"
#: 行级哈希覆盖的关键表（设计 §2 F-06）
HASH_TABLES = ("candidate", "demand_signal", "supply_offer")
COUNT_TABLES = ("candidate", "demand_signal", "evidence", "supply_offer", "cost_item",
                "gate_review", "review_item", "schema_migrations")
_STAMP_FORMAT = "%Y%m%d-%H%M%S"


class BackupError(Exception):
    """可预期的备份失败（参数/冲突/校验），对应退出码 2。"""


def _resolve(path: str | pathlib.Path) -> pathlib.Path:
    return pathlib.Path(path).expanduser().resolve()


def _sha256(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def app_max_schema_version() -> int:
    """应用支持的 schema 上限：迁移文件名最大版本前缀（设计 §6 F-04）。"""
    versions = [int(path.name.split("_", 1)[0]) for path in MIGRATIONS_DIR.glob("*.sql")]
    return max(versions) if versions else 0


def sidecar_files(db_path: pathlib.Path) -> list[pathlib.Path]:
    """返回同目录下的 ``-wal``/``-shm`` 旁文件（存在即视为可能有写入者/未合并）。"""
    return [path for path in (db_path.with_name(db_path.name + "-wal"),
                              db_path.with_name(db_path.name + "-shm")) if path.exists()]


def _open_ro(db_path: pathlib.Path, *, purpose: str = "只读打开") -> sqlite3.Connection:
    """**immutable=1** 只读打开：不生成 ``-wal``/``-shm`` sidecar（设计 B-07）。"""
    if not db_path.is_file():
        raise BackupError(f"源库不存在：{db_path}")
    sidecars = sidecar_files(db_path)
    if sidecars:
        raise BackupError(
            f"{purpose}检测到 WAL/SHM 旁文件（{', '.join(path.name for path in sidecars)}）："
            "immutable 只读不会产生新 sidecar，但现存的旁文件可能意味着仍有写入者或未合并；"
            "请先停止应用、人工确认无写入/已完成合并后重试（本脚本不自动删除旁文件）")
    conn = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro&immutable=1", uri=True, timeout=5.0)
    conn.row_factory = sqlite3.Row
    return conn


def _open_target(db_path: pathlib.Path) -> sqlite3.Connection:
    """目标库：必须是新文件（父目录可创建），随后以普通连接写入备份内容。"""
    if db_path.exists():
        raise BackupError(f"目标已存在，拒绝覆盖：{db_path}")
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path), isolation_level=None, timeout=5.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def _table_counts(conn: sqlite3.Connection) -> dict:
    counts = {}
    for table in COUNT_TABLES:
        exists = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone()
        counts[table] = conn.execute(f"SELECT count(*) AS n FROM {table}").fetchone()["n"] \
            if exists else None
    return counts


def _row_hashes(conn: sqlite3.Connection) -> dict:
    """3 张关键表：按 ``id`` 升序逐行 ``sha256(json(行))``，再整体 sha256（设计 §2 F-06）。"""
    result = {}
    for table in HASH_TABLES:
        exists = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone()
        if not exists:
            result[table] = {"rows": 0, "sha256": None}
            continue
        per_row = []
        for row in conn.execute(f"SELECT * FROM {table} ORDER BY id"):
            payload = json.dumps(dict(row), ensure_ascii=False, sort_keys=True, default=str)
            per_row.append(hashlib.sha256(payload.encode("utf-8")).hexdigest())
        joined = "\n".join(per_row)
        result[table] = {"rows": len(per_row),
                         "sha256": hashlib.sha256(joined.encode("utf-8")).hexdigest()}
    return result


def build_manifest(db_path: str | pathlib.Path) -> tuple[dict, dict]:
    """读取（只读打开）一个数据库并生成清单内容；返回 ``(manifest, counts)``。"""
    target = _resolve(db_path)
    if not target.is_file():
        raise BackupError(f"待校验数据库不存在：{target}")
    conn = _open_ro(target)
    try:
        integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
        foreign_keys = [dict(row) for row in conn.execute("PRAGMA foreign_key_check")]
        migrations = conn.execute(
            "SELECT MAX(version) AS v FROM schema_migrations").fetchone()["v"] \
            if conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='schema_migrations'").fetchone() else 0
        manifest = {
            "kind": MANIFEST_KIND,
            "tool": "tools/backup.py",
            "db_path": str(target),
            "sha256": _sha256(target),
            "bytes": target.stat().st_size,
            "schema_version": int(migrations or 0),
            "app_max_schema_version": app_max_schema_version(),
            "integrity_check": integrity,
            "foreign_key_check": foreign_keys,
            "table_counts": _table_counts(conn),
            "row_hashes": _row_hashes(conn),
            "created_at": now_utc(),
        }
    finally:
        conn.close()
    return manifest, manifest["table_counts"]


def verify_manifest(db_path: str | pathlib.Path, manifest: dict) -> list[str]:
    """重新计算并比对清单；返回问题列表（空=通过）。"""
    problems = []
    fresh, _counts = build_manifest(db_path)
    for key in ("sha256", "bytes", "schema_version", "integrity_check",
                "foreign_key_check", "table_counts", "row_hashes"):
        if manifest.get(key) != fresh.get(key):
            problems.append(f"{key} 不一致")
    if manifest.get("kind") != MANIFEST_KIND:
        problems.append("kind 不是 sqlite_backup_manifest_v1")
    if fresh["integrity_check"] != "ok":
        problems.append(f"integrity_check={fresh['integrity_check']}")
    if fresh["foreign_key_check"]:
        problems.append("foreign_key_check 非空")
    return problems


def _timestamp_name() -> str:
    return time.strftime(_STAMP_FORMAT, time.gmtime())


def backup(*, db_path: str | pathlib.Path = DEFAULT_DB,
           out_dir: str | pathlib.Path = DEFAULT_OUT_DIR,
           stamp: str | None = None) -> dict:
    """执行一次备份，返回 ``{backup_path, manifest_path, manifest}``。"""
    source = _resolve(db_path)
    out = _resolve(out_dir)
    started = time.monotonic()
    target = out / f"app-{stamp or _timestamp_name()}.db"
    manifest_path = target.with_suffix(".db.manifest.json")
    if target.exists() or manifest_path.exists():
        raise BackupError(f"同名备份已存在，拒绝覆盖：{target}")
    src = _open_ro(source)
    dst = None
    try:
        dst = _open_target(target)
        src.backup(dst)
        dst.close()
        dst = None
        manifest, _counts = build_manifest(target)
        manifest.update({
            "source_db": str(source),
            "backup_path": str(target),
            "source_wal_present": (source.parent / (source.name + "-wal")).exists(),
            "source_shm_present": (source.parent / (source.name + "-shm")).exists(),
            "duration_ms": int((time.monotonic() - started) * 1000),
        })
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=1),
                                 encoding="utf-8")
    except Exception:
        if dst is not None:
            dst.close()
        for path in (target, manifest_path):
            if path.exists():
                path.unlink()
        raise
    finally:
        src.close()
    return {"backup_path": target, "manifest_path": manifest_path, "manifest": manifest}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="backup", description="SQLite 备份（只读源库，绝不覆盖）")
    parser.add_argument("--db", default=str(DEFAULT_DB), help="源库（默认 instance/app.db，只读）")
    parser.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR),
                        help="备份目录（默认 instance/backups）")
    parser.add_argument("--stamp", default=None, help="文件名时间戳（默认 UTC YYYYmmdd-HHMMSS）")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result = backup(db_path=args.db, out_dir=args.out_dir, stamp=args.stamp)
    except BackupError as exc:
        print(f"backup: {exc}", file=sys.stderr)
        return 2
    except (sqlite3.Error, OSError) as exc:
        print(f"backup: 失败：{type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    manifest = result["manifest"]
    print(f"backup: ok {result['backup_path']} sha256={manifest['sha256']} "
          f"bytes={manifest['bytes']} schema={manifest['schema_version']} "
          f"manifest={result['manifest_path']}")
    return 0


if __name__ == "__main__":                       # pragma: no cover - CLI 入口
    raise SystemExit(main())
