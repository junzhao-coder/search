"""C 导出：只读复用 ``daily_digest``，输出 ``reports/daily-<date>.json`` 与 ``.csv``。

约束（计划 v3 / 任务 C）
--------------------
* **只读**：以 SQLite ``mode=ro`` URI 打开目标库（不建表/不迁移/不写库、不写业务库）；
* **不联网**、不改运行代码/公共接口/契约/迁移；
* 输入库允许 ``instance/app.db``（默认），以 ``mode=ro`` 只读打开；
* **输出目录不得位于** ``ROOT/instance`` 或其子目录（写文件前校验，拒绝则不建目录/不写文件）；
* 支持 ``--db`` / ``--as-of`` / ``--limit`` / ``--out-dir``；输出文件名日期取摘要的
  ``digest_date``（即 ``as_of`` 的日期部分，保证同输入同结果）。

退出码：0 成功；2 参数/路径被拒（含 instance、库不存在、as_of 非法）；1 运行失败。
"""

from __future__ import annotations

import argparse
import csv
import json
import pathlib
import re
import sqlite3
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:                      # 直接以脚本运行 tools/export_daily.py 时可用
    sys.path.insert(0, str(ROOT))

from app.core.daily import daily_digest        # noqa: E402  (路径注入后再导入)


DEFAULT_DB = ROOT / "instance" / "app.db"
DEFAULT_OUT_DIR = ROOT / "reports"
_INSTANCE_DIR = ROOT / "instance"
_AS_OF_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
CSV_COLUMNS = ("pool", "rank", "candidate_id", "tier", "score", "daily_pick",
               "next_action", "reasons", "gaps")
_POOLS = ("top", "blocked", "observing", "exploring")


class ExportError(Exception):
    """可预期的导出失败（参数/路径/输入不合法），对应退出码 2。"""


def _resolve(path: str | pathlib.Path) -> pathlib.Path:
    return pathlib.Path(path).expanduser().resolve()


def _reject_out_dir(out_dir: pathlib.Path) -> None:
    """写文件前校验：out-dir（resolve + normcase 后）不得位于 ``ROOT/instance`` 或其子目录。"""
    import os

    target = os.path.normcase(str(out_dir.resolve()))
    guard = os.path.normcase(str(_INSTANCE_DIR.resolve()))
    if target == guard or target.startswith(guard + os.sep):
        raise ExportError(f"拒绝把输出目录放在业务库目录（instance/）内：{out_dir}；请用 --out-dir 指定其它目录")


def _open_readonly(db_path: pathlib.Path) -> sqlite3.Connection:
    if not db_path.is_file():
        raise ExportError(f"数据库不存在：{db_path}")
    uri = f"file:{db_path.as_posix()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True, timeout=5.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout=5000")
    return conn


def _validate_as_of(as_of: str) -> str:
    value = str(as_of or "").strip()
    if not _AS_OF_RE.match(value):
        raise ExportError("--as-of 必须是 ISO-8601 UTC 秒精度（例如 2026-10-20T12:00:00Z）")
    return value


def _csv_row(pool: str, item: dict) -> dict:
    row = {column: item.get(column, "") for column in CSV_COLUMNS}
    row["pool"] = pool
    for key in ("reasons", "gaps"):
        value = row.get(key, "")
        if isinstance(value, (list, dict)):
            row[key] = json.dumps(value, ensure_ascii=False)
        elif value is None:
            row[key] = ""
    return row


def write_digest_files(digest: dict, out_dir: pathlib.Path) -> tuple[pathlib.Path, pathlib.Path]:
    """把摘要写成 ``daily-<digest_date>.json`` 与同名 ``.csv``（UTF-8 无 BOM）。"""
    _reject_out_dir(out_dir)                        # 防御性复检：直接调用本函数同样受保护
    date = str(digest.get("digest_date") or "").strip()
    if not _AS_OF_RE.match(date + "T00:00:00Z"):
        raise ExportError(f"摘要缺少合法 digest_date：{date!r}")
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / f"daily-{date}.json"
    csv_path = out_dir / f"daily-{date}.csv"
    json_path.write_text(json.dumps(digest, ensure_ascii=False, indent=1), encoding="utf-8")
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(CSV_COLUMNS))
        writer.writeheader()
        for pool in _POOLS:
            for item in digest.get(pool) or []:
                writer.writerow(_csv_row(pool, item))
    return json_path, csv_path


def export(*, db_path: str | pathlib.Path = DEFAULT_DB, as_of: str, limit: int = 5,
           out_dir: str | pathlib.Path = DEFAULT_OUT_DIR) -> dict:
    """只读生成每日摘要并落盘；返回 ``{json_path, csv_path, digest}``。"""
    target = _resolve(db_path)
    out_path = _resolve(out_dir)
    _reject_out_dir(out_path)                       # 写文件前校验，拒绝则不创建/不写
    if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
        raise ExportError("--limit 必须是正整数")
    as_of_value = _validate_as_of(as_of)
    conn = _open_readonly(target)
    try:
        digest = daily_digest(conn, as_of=as_of_value, limit=limit)
    finally:
        conn.close()
    json_path, csv_path = write_digest_files(digest, out_path)
    return {"json_path": json_path, "csv_path": csv_path, "digest": digest}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="export_daily", description="只读导出每日摘要（JSON/CSV）")
    parser.add_argument("--db", default=str(DEFAULT_DB), help="SQLite 路径（默认 instance/app.db，只读）")
    parser.add_argument("--as-of", required=True,
                        help="必填：ISO-8601 UTC 时间（YYYY-MM-DDTHH:MM:SSZ）")
    parser.add_argument("--limit", type=int, default=5, help="推荐池展示上限（正整数，默认 5）")
    parser.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR), help="输出目录（默认 reports）")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result = export(db_path=args.db, as_of=args.as_of, limit=args.limit, out_dir=args.out_dir)
    except ExportError as exc:
        print(f"export_daily: {exc}", file=sys.stderr)
        return 2
    except (sqlite3.Error, OSError, ValueError) as exc:
        print(f"export_daily: 失败：{type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    digest = result["digest"]
    print(f"export_daily: ok as_of={digest['as_of']} date={digest['digest_date']} "
          f"top={digest['counts']['top']} json={result['json_path']} csv={result['csv_path']}")
    return 0


if __name__ == "__main__":                       # pragma: no cover - CLI 入口
    raise SystemExit(main())
