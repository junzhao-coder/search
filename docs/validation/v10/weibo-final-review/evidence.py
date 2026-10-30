"""只读证据汇总：平台库 + state-search + argparse 顺序实测（不联网、不启浏览器）。

输出：同目录 evidence.json（机器可读），stdout 摘要。
"""

from __future__ import annotations

import contextlib
import datetime as dt
import io
import json
import pathlib
import sqlite3
import sys

ROOT = pathlib.Path(r"D:\桌面\two")
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.selection.access import weibo  # noqa: E402

OUT = ROOT / "docs" / "validation" / "v10" / "weibo-final-review"
PLATFORM = ROOT / "tools" / "selection" / "access" / "runtime" / "platform_weibo.sqlite3"
STATE = ROOT / "docs" / "validation" / "v10" / "weibo-live-prep" / "state-search" / "budget.sqlite3"


def utc(x) -> str | None:
    try:
        return dt.datetime.fromtimestamp(float(x), dt.timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%SZ")
    except (TypeError, ValueError, OSError):
        return None


def ro(path: pathlib.Path) -> sqlite3.Connection:
    con = sqlite3.connect(path.as_uri() + "?mode=ro&immutable=1", uri=True, timeout=5.0)
    con.row_factory = sqlite3.Row
    return con


def platform_facts() -> dict:
    con = ro(PLATFORM)
    try:
        batches = [dict(r) for r in con.execute("SELECT * FROM batches")]
        for b in batches:
            b["started_at_utc"] = utc(b["started_at"])
            b["window_end_utc"] = utc(float(b["started_at"]) + float(b["window_seconds"]))
        events = [{"id": r["id"], "kind": r["kind"], "at_utc": utc(r["at"]),
                   "source": r["source"], "detail": r["detail"]}
                  for r in con.execute("SELECT * FROM events ORDER BY id")]
        reservations = [{"count": r["count"], "at_utc": utc(r["at"])}
                        for r in con.execute("SELECT * FROM reservations")]
        locks = [dict(r) for r in con.execute("SELECT * FROM locks")]
        h = con.execute("SELECT payload, imported_at FROM history").fetchone()
    finally:
        con.close()
    history = None
    if h is not None:
        payload = json.loads(h["payload"])
        history = {"imported_at_utc": utc(h["imported_at"]),
                   "test_only": bool(payload.get("test_only")),
                   "rows": [{"source_key": r["source_key"],
                             "classification": r["classification"],
                             "calls": r["calls"], "records": r["records"],
                             "locked": r["locked"]} for r in payload.get("rows", [])]}
    return {"path": str(PLATFORM.relative_to(ROOT)),
            "mtime_utc": utc(PLATFORM.stat().st_mtime),
            "wal_present": pathlib.Path(str(PLATFORM) + "-wal").exists(),
            "batches": batches, "events": events, "reservations": reservations,
            "locks": locks, "history": history}


def state_facts() -> dict:
    con = ro(STATE)
    try:
        budget = dict(con.execute("SELECT * FROM budget").fetchone())
        budget["started_at_utc"] = utc(budget["started_at"])
        budget["last_call_at_utc"] = utc(budget["last_call_at"])
        ledger = [{"id": r["id"], "kind": r["kind"], "at_utc": utc(r["at"]),
                   "detail": (r["detail"] or "")[:120]}
                  for r in con.execute("SELECT * FROM ledger ORDER BY id")]
    finally:
        con.close()
    return {"path": str(STATE.relative_to(ROOT)),
            "mtime_utc": utc(STATE.stat().st_mtime),
            "wal_present": pathlib.Path(str(STATE) + "-wal").exists(),
            "budget": budget, "ledger": ledger}


def argparse_order() -> dict:
    parser = weibo.build_parser()
    base = ["--state-dir", "X", "--batch-id", "weibo-verify-1"]
    cases = {
        "option_before_subcommand": base + ["--diagnostics-dir", "diag1", "search", "kw"],
        "option_after_subcommand": base + ["search", "kw", "--diagnostics-dir", "diag1"],
    }
    out = {}
    for name, argv in cases.items():
        err = io.StringIO()
        try:
            with contextlib.redirect_stderr(err):
                args = parser.parse_args(argv)
            out[name] = {"exit": 0, "diagnostics_dir": getattr(args, "diagnostics_dir", None),
                         "keyword": getattr(args, "keyword", None)}
        except SystemExit as exc:
            lines = [ln for ln in err.getvalue().splitlines() if ln.strip()]
            out[name] = {"exit": exc.code, "stderr_last": lines[-1] if lines else ""}
    return out


def main() -> int:
    payload = {"generated_utc": utc(dt.datetime.now(dt.timezone.utc).timestamp()),
               "read_only": "sqlite mode=ro&immutable=1",
               "platform": platform_facts(), "state_search": state_facts(),
               "argparse_order": argparse_order()}
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "evidence.json").write_bytes(
        json.dumps(payload, ensure_ascii=False, indent=1).encode())
    p = payload["platform"]
    print(json.dumps({"generated_utc": payload["generated_utc"],
                      "batch": p["batches"][0] if p["batches"] else None,
                      "events": p["events"], "reservations": p["reservations"],
                      "locks": p["locks"],
                      "state_calls": payload["state_search"]["budget"]["calls"],
                      "argparse": payload["argparse_order"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
