"""可运行入口：``python -m tools.selection.storage <init|ingest|export|stats>``。

只操作 ``--db`` 指定的库；``ingest`` 读既有 JSONL/JSON 记录（不联网、不碰真实平台）。
"""

from __future__ import annotations

import argparse
import json
import sys

from . import compat
from .store import SCHEMA_VERSION, Storage


def _emit(payload) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def _cmd_init(args) -> int:
    with Storage(args.db) as box:
        _emit({"db": str(box.path), "schema_version": SCHEMA_VERSION, "ok": True})
    return 0


def _cmd_ingest(args) -> int:
    # 先读文件再建 run：文件坏了不会留下一条空运行。
    records = compat.read_records_file(args.records)
    items = compat.items_from_records(records, platform=args.platform)
    with Storage(args.db) as box:
        run_id = box.begin_run(args.platform, run_id=args.run_id,
                               target_native_id=args.target)
        saved = box.save(items, run_id=run_id)
        out = {"run_id": run_id, "records_read": len(records),
               "db": str(box.path), **saved}
        if args.stop:
            box.finish_run(run_id, stop_reason=args.stop, complete=args.complete,
                           declared_count=args.declared, note=args.note or "")
            out["run"] = box.run_summary(run_id)
        _emit(out)
    return 0


def _cmd_export(args) -> int:
    with Storage(args.db) as box:
        if args.full:
            result = compat.export_items(box, args.out, platform=args.platform)
        else:
            result = compat.export_compat(box, args.out, platform=args.platform,
                                          fmt=args.fmt)
        result["db"] = str(box.path)
        _emit(result)
    return 0


def _cmd_stats(args) -> int:
    with Storage(args.db) as box:
        _emit({"db": str(box.path), "counts": box.counts(),
               "runs": box.runs(limit=args.limit)})
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m tools.selection.storage",
        description="V18 单帖采集的最小隔离存储（离线，不访问真实平台）")
    sub = parser.add_subparsers(dest="command", required=True)

    init = sub.add_parser("init", help="创建/检查存储库")
    init.add_argument("--db", required=True)
    init.set_defaults(func=_cmd_init)

    ingest = sub.add_parser("ingest", help="把既有 JSONL/JSON 记录写入存储")
    ingest.add_argument("--db", required=True)
    ingest.add_argument("--platform", required=True)
    ingest.add_argument("--records", required=True, help="JSONL 或 JSON 数组")
    ingest.add_argument("--run-id", default=None, help="续跑时传回同一 ID")
    ingest.add_argument("--target", default=None, help="被采集帖子的原生 ID")
    ingest.add_argument("--stop", default=None, help="停止原因（见 STOP_REASONS）")
    ingest.add_argument("--complete", action="store_true",
                        help="仅 end_signal 可用")
    ingest.add_argument("--declared", type=int, default=None,
                        help="页面声明的评论数（未知就不要传）")
    ingest.add_argument("--note", default=None)
    ingest.set_defaults(func=_cmd_ingest)

    export = sub.add_parser("export", help="导出 23 列兼容视图或完整存储视图")
    export.add_argument("--db", required=True)
    export.add_argument("--platform", required=True)
    export.add_argument("--out", required=True)
    export.add_argument("--fmt", choices=("csv", "jsonl"), default="csv")
    export.add_argument("--full", action="store_true",
                        help="完整存储视图（JSONL，含平台/精度/原始时间）")
    export.set_defaults(func=_cmd_export)

    stats = sub.add_parser("stats", help="计数与最近运行")
    stats.add_argument("--db", required=True)
    stats.add_argument("--limit", type=int, default=10)
    stats.set_defaults(func=_cmd_stats)

    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except (ValueError, OSError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False),
              file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
