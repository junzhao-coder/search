"""CLI for the independent V9 selection store (stdlib argparse)."""

from __future__ import annotations

import argparse
import json
import pathlib
import sys

from . import bilibili, categories, db, models, rounds as rounds_mod, xianyu

ROOT = pathlib.Path(__file__).resolve().parents[2]
DEFAULT_DB = ROOT / "tools" / "selection" / "runtime" / "selection.sqlite3"
DEFAULT_RAW = ROOT / "tools" / "selection" / "runtime" / "raw"


def _emit(value) -> None:
    print(json.dumps(value, ensure_ascii=False, sort_keys=True))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="V9 independent selection signal store")
    parser.add_argument("--db", default=str(DEFAULT_DB))
    parser.add_argument("--raw-dir", default=str(DEFAULT_RAW))
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="run one bounded collector")
    run.add_argument("platform", choices=["bilibili"])
    run.add_argument("--aid", type=int)
    run.add_argument("--bvid")
    run.add_argument("--budget", type=int, default=5)
    run.add_argument("--interval", type=float, default=3.0)
    run.add_argument("--include-subreply", action="store_true")
    run.add_argument("--origin", choices=models.ORIGIN_KINDS, default="real")

    imp = sub.add_parser("import", help="import a user export")
    imp.add_argument("platform", choices=["xianyu"])
    imp.add_argument("--path", required=True)
    imp.add_argument("--collected-at")
    imp.add_argument("--batch-id")
    imp.add_argument("--max-rows", type=int, default=5000)
    imp.add_argument("--max-errors", type=int, default=100)

    sub.add_parser("stats", help="show signal/run counts")

    cat = sub.add_parser("categorize", help="run rule-based categorization")
    cat.add_argument("--no-hint", action="store_true")
    cat.add_argument("--explain", action="store_true")

    sub.add_parser("cards", help="list direction cards")
    sub.add_parser("ledger", help="list categories and events")

    roundp = sub.add_parser("round", help="round state machine")
    rsub = roundp.add_subparsers(dest="round_command", required=True)
    rs = rsub.add_parser("start")
    rs.add_argument("--kind", default="bilibili")
    rs.add_argument("--platform", default="bilibili")
    rs.add_argument("--budget", type=int, default=3)
    rs.add_argument("--key", required=True)
    rp = rsub.add_parser("run")
    rp.add_argument("--round-id", type=int, required=True)
    rp.add_argument("--aid", type=int)
    rp.add_argument("--bvid")
    rp.add_argument("--budget", type=int, default=3)
    rp.add_argument("--interval", type=float, default=3.0)
    rp.add_argument("--pause-after-items", type=int)
    rsub.add_parser("status").add_argument("--round-id", type=int, required=True)
    rsub.add_parser("pause").add_argument("--round-id", type=int, required=True)
    rsub.add_parser("resume").add_argument("--round-id", type=int, required=True)
    rsub.add_parser("cancel").add_argument("--round-id", type=int, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "stats":
            conn = db.init_db(args.db)
            try:
                _emit({"ok": True, **db.stats(conn)})
            finally:
                conn.close()
            return 0
        if args.command == "run" and args.platform == "bilibili":
            result = bilibili.collect(
                db_path=args.db, raw_dir=args.raw_dir, aid=args.aid, bvid=args.bvid,
                budget=args.budget, interval=args.interval,
                include_subreply=args.include_subreply, origin_kind=args.origin)
            ok = result.get("status") in ("complete", "partial")
            _emit({"ok": ok, **result})
            if result.get("status") == "failed":
                return 3
            return 0
        if args.command == "import" and args.platform == "xianyu":
            result = xianyu.import_file(
                args.path, db_path=args.db, collected_at=args.collected_at,
                batch_id=args.batch_id, max_rows=args.max_rows, max_errors=args.max_errors)
            ok = result.get("status") in ("complete", "partial")
            _emit({"ok": ok, **result})
            if result.get("status") == "failed":
                return 3
            return 0
        if args.command == "categorize":
            conn = db.init_db(args.db)
            try:
                stats = categories.run_categorize(conn, explain=args.explain)
                card_stats = categories.make_cards(conn)
                _emit({"ok": True, **stats, "cards": card_stats})
            finally:
                conn.close()
            return 0
        if args.command == "cards":
            conn = db.init_db(args.db)
            try:
                _emit({"ok": True, "cards": categories.list_cards(conn)})
            finally:
                conn.close()
            return 0
        if args.command == "ledger":
            conn = db.init_db(args.db)
            try:
                _emit({"ok": True, "categories": categories.list_ledger(conn)})
            finally:
                conn.close()
            return 0
        if args.command == "round":
            conn = db.init_db(args.db)
            try:
                if args.round_command == "start":
                    r = rounds_mod.start(conn, kind=args.kind, platform=args.platform,
                                         budget={"max_requests": args.budget}, idempotency_key=args.key)
                    _emit({"ok": True, **r})
                    return 0
                rid = args.round_id
                if args.round_command == "status":
                    _emit({"ok": True, **rounds_mod.status(conn, rid)})
                    return 0
                if args.round_command == "pause":
                    _emit({"ok": True, **rounds_mod.pause(conn, rid)})
                    return 0
                if args.round_command == "resume":
                    _emit({"ok": True, **rounds_mod.resume(conn, rid)})
                    return 0
                if args.round_command == "cancel":
                    _emit({"ok": True, **rounds_mod.cancel(conn, rid)})
                    return 0
                if args.round_command == "run":
                    # round must be running to execute
                    if rounds_mod.status(conn, rid)["status"] == "draft":
                        rounds_mod.transition(conn, rid, "running")
                    out = bilibili.collect_round(
                        db_path=args.db, round_id=rid, raw_dir=args.raw_dir, aid=args.aid,
                        bvid=args.bvid, budget=args.budget, interval=args.interval,
                        pause_after_items=args.pause_after_items)
                    _emit({"ok": out.get("status") in ("complete", "partial", "paused"), **out})
                    return 0 if out.get("status") in ("complete", "partial", "paused") else 3
            finally:
                conn.close()
        _emit({"ok": False, "error": "unsupported_command"})
        return 2
    except Exception as exc:  # noqa: BLE001 - CLI reports a stable one-line error
        _emit({"ok": False, "error": f"{type(exc).__name__}: {exc}"})
        return 2


if __name__ == "__main__":
    sys.exit(main())
