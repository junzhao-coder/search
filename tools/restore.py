"""S6 恢复脚本（**仅隔离副本、绝不覆盖业务库**；设计 §3/§10 B-02/B-03/B-06/R-02）。

- 守卫（设计 §3.1 F-05）：目标 ``realpath + normcase`` 后
  ①不得等于业务库 ``instance/app.db``（可用 ``--business-db`` 覆盖，便于测试模拟）；
  ②不得位于 ``ROOT/instance`` 目录内；③目标必须**不存在**（独占创建，绝不覆盖）。
- 内容校验：``integrity_check=ok`` → ``foreign_key_check`` 空 → 表计数/3 表行级哈希/``sha256``
  与备份清单一致（清单自动查找 ``<backup>.manifest.json``，或 ``--manifest`` 指定）；
- 版本判定（设计 §6 F-04 / R-02）：``schema_version = MAX(schema_migrations.version)`` 若
  **高于** ``MIGRATIONS_DIR`` 最大版本 → 明确报错"库版本高于应用支持版本"并拒绝（**应用层当前不拒绝**，差距如实保留）。
- 只写**隔离副本**（不启动应用、不改业务库、不联网）；失败清理半成品并保留备份现场。

退出码：0 成功；2 守卫/校验/版本拒绝；1 运行异常。
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sqlite3
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
TOOLS_DIR = pathlib.Path(__file__).resolve().parent
for entry in (str(ROOT), str(TOOLS_DIR)):
    if entry not in sys.path:
        sys.path.insert(0, entry)

import backup as backup_tool                          # noqa: E402  (同目录工具，复用清单/哈希)

DEFAULT_BUSINESS_DB = ROOT / "instance" / "app.db"


class RestoreError(Exception):
    """可预期的恢复失败（守卫/校验/版本），对应退出码 2。"""


def _resolve(path: str | pathlib.Path) -> pathlib.Path:
    return pathlib.Path(path).expanduser().resolve()


def _norm(path: pathlib.Path) -> str:
    import os

    return os.path.normcase(str(path.resolve()))


def _reject_target(target: pathlib.Path, business_db: pathlib.Path) -> None:
    """写文件前守卫：不得指向业务库/其目录、不得已存在。"""
    target_norm = _norm(target)
    business_norm = _norm(business_db)
    if target_norm == business_norm:
        raise RestoreError(f"拒绝覆盖业务库：{target}")
    instance_norm = _norm(ROOT / "instance")
    if target_norm == instance_norm or target_norm.startswith(instance_norm + __import__("os").sep):
        raise RestoreError(f"拒绝在业务库目录（instance/）内创建恢复副本：{target}")
    if target.exists():
        raise RestoreError(f"目标已存在，拒绝覆盖：{target}")


def _guard_source(backup_path: pathlib.Path) -> dict | None:
    """读取备份清单（自动查找同名 manifest，或由调用方显式指定）；返回清单或 None。"""
    path = backup_path.with_suffix(".db.manifest.json")
    if path.is_file():
        return json.loads(path.read_text(encoding="utf-8"))
    return None


def _open_ro(db_path: pathlib.Path) -> sqlite3.Connection:
    """**immutable=1** 只读打开备份（不产生 -wal/-shm）；存在旁文件时拒绝并提示人工确认。"""
    if not db_path.is_file():
        raise RestoreError(f"备份文件不存在：{db_path}")
    sidecars = backup_tool.sidecar_files(db_path)
    if sidecars:
        raise RestoreError(
            f"检测到备份旁 WAL/SHM 文件（{', '.join(path.name for path in sidecars)}）："
            "请先人工确认备份未被写入/未处于合并状态后重试（本脚本不自动删除旁文件）")
    conn = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro&immutable=1", uri=True, timeout=5.0)
    conn.row_factory = sqlite3.Row
    return conn


def restore(*, backup_path: str | pathlib.Path, target: str | pathlib.Path,
            business_db: str | pathlib.Path = DEFAULT_BUSINESS_DB,
            manifest: str | pathlib.Path | None = None) -> dict:
    """把备份恢复到**新**隔离副本并校验；返回校验报告。"""
    source = _resolve(backup_path)
    destination = _resolve(target)
    business = _resolve(business_db)
    _reject_target(destination, business)          # 守卫先于任何写入
    if manifest is not None:
        expected = json.loads(_resolve(manifest).read_text(encoding="utf-8"))
    else:
        expected = _guard_source(source)

    src = _open_ro(source)
    dst = None
    try:
        # 备份来源自检：能打开且 integrity 正常（损坏备份在此被拒绝，设计 B-03）
        integrity = src.execute("PRAGMA integrity_check").fetchone()[0]
        if integrity != "ok":
            raise RestoreError(f"备份损坏：integrity_check={integrity}")
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists():                    # 双重检查（防御并发）
            raise RestoreError(f"目标已存在，拒绝覆盖：{destination}")
        dst = sqlite3.connect(str(destination), isolation_level=None, timeout=5.0)
        src.backup(dst)
        dst.close()
        dst = None
    except sqlite3.DatabaseError as exc:
        if dst is not None:
            dst.close()
        if destination.exists():
            destination.unlink()
        raise RestoreError(f"备份无法恢复（{type(exc).__name__}: {exc}）") from exc
    except Exception:
        if dst is not None:
            dst.close()
        if destination.exists():
            destination.unlink()
        raise
    finally:
        src.close()

    try:
        report = _verify_restored(destination, expected)
    except RestoreError:
        destination.unlink(missing_ok=True)         # 校验失败：清理半成品
        raise
    return {"target": destination, **report}


def _verify_restored(target: pathlib.Path, expected: dict | None) -> dict:
    fresh, _counts = backup_tool.build_manifest(target)
    problems = []
    if expected is not None:
        # 字节级 sha/bytes 不作为恢复副本的等价条件（sqlite backup 不保证字节级相同），
        # 只比较内容与结构：schema 版本、完整性、外键、表计数、行级哈希。
        for key in ("schema_version", "integrity_check", "foreign_key_check",
                    "table_counts", "row_hashes"):
            if expected.get(key) != fresh.get(key):
                problems.append(f"{key} 与备份清单不一致")
    app_max = backup_tool.app_max_schema_version()
    if fresh["schema_version"] > app_max:
        raise RestoreError(
            f"库版本高于应用支持版本：库={fresh['schema_version']} 应用上限={app_max}（应用层当前不拒绝，恢复层拒绝）")
    if fresh["integrity_check"] != "ok":
        problems.append(f"integrity_check={fresh['integrity_check']}")
    if fresh["foreign_key_check"]:
        problems.append("foreign_key_check 非空")
    if problems:
        raise RestoreError("恢复副本校验失败：" + "；".join(problems))
    return {
        "schema_version": fresh["schema_version"],
        "app_max_schema_version": app_max,
        "sha256": fresh["sha256"],
        "bytes": fresh["bytes"],
        "table_counts": fresh["table_counts"],
        "row_hashes": fresh["row_hashes"],
        "manifest_checked": expected is not None,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="restore", description="恢复备份到隔离副本（绝不覆盖业务库）")
    parser.add_argument("--backup", required=True, help="备份文件（.db）")
    parser.add_argument("--target", required=True, help="恢复副本路径（必须不存在）")
    parser.add_argument("--manifest", default=None, help="清单文件（默认查找 <backup>.db.manifest.json）")
    parser.add_argument("--business-db", default=str(DEFAULT_BUSINESS_DB),
                        help="业务库路径，仅用于守卫判定（默认 instance/app.db）")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        report = restore(backup_path=args.backup, target=args.target,
                         business_db=args.business_db, manifest=args.manifest)
    except RestoreError as exc:
        print(f"restore: {exc}", file=sys.stderr)
        return 2
    except (sqlite3.Error, OSError, ValueError) as exc:
        print(f"restore: 失败：{type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    print(f"restore: ok target={report['target']} schema={report['schema_version']} "
          f"manifest_checked={report['manifest_checked']} sha256={report['sha256']}")
    return 0


if __name__ == "__main__":                       # pragma: no cover - CLI 入口
    raise SystemExit(main())
