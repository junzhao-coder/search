"""只读预检（v3）：微博「登录后 1 次搜索」执行前条件核对。

本版修正（回应退回意见）：
- 每个历史源**直接用只读 SQLite 查** `budget.calls/records/locked/lock_reason`，
  不再用 `fingerprint()` 里并不存在的 `locked` 字段（旧版恒为 None）；
- `-wal/-shm` 侧车存在、缺表、损坏、读取错误 → 该源 `status="unknown"` 并记录 `error`；
  **只有全部源都 ok 且无人 locked 时**，才允许得出"未发现锁"的结论；
- 平台库读取同样先看 `-wal/-shm`（`immutable=1` 会忽略 WAL → 标 unknown）。

只读：不创建/不修改任何账本、平台库或 profile；不联网、不启动浏览器、不读 cookie。

用法：python -X utf8 docs/validation/v10/weibo-live-prep/preflight.py
退出码：0 = 全部源可读；3 = 存在 unknown（结论不完整）。
"""

from __future__ import annotations

import datetime as dt
import json
import pathlib
import sqlite3
import sys
import time

ROOT = pathlib.Path(r"D:\桌面\two")
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.selection.access import platform_budget as pb  # noqa: E402 - 只读常量/路径

OUT = ROOT / "docs" / "validation" / "v10" / "weibo-live-prep"
PLATFORM_DB = pb.DEFAULT_PATH
PROFILE = ROOT / "docs" / "validation" / "v10" / "weibo-login" / "profile"
BATCH = "weibo-live-1"


def utc(stamp) -> str | None:
    try:
        return dt.datetime.fromtimestamp(float(stamp), dt.timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%SZ")
    except (TypeError, ValueError, OSError):
        return None


def sidecars(path: pathlib.Path) -> list[str]:
    out = []
    for suffix in ("-wal", "-shm"):
        side = pathlib.Path(str(path) + suffix)
        if side.exists() and side.stat().st_size > 0:
            out.append(str(side))
    return out


def read_budget_row(db: pathlib.Path) -> dict:
    """只读读一行 budget；任何不确定都返回 status=unknown + error，绝不猜。"""
    result: dict = {"db_path": str(db), "status": "unknown", "calls": None,
                    "records": None, "locked": None, "lock_reason": None,
                    "error": None, "sidecars": sidecars(db)}
    if not db.is_file():
        result["error"] = "missing"
        return result
    if result["sidecars"]:
        result["error"] = "wal_present"      # immutable=1 会忽略 WAL，读数不可信
        return result
    try:
        con = sqlite3.connect(db.as_uri() + "?mode=ro&immutable=1", uri=True, timeout=3.0)
    except sqlite3.Error as exc:
        result["error"] = f"open_failed:{type(exc).__name__}"
        return result
    try:
        row = con.execute(
            "SELECT calls, records, locked, lock_reason FROM budget WHERE id=1").fetchone()
        if row is None:
            result["error"] = "budget_row_missing"
            return result
        result.update({"status": "ok", "calls": row[0], "records": row[1],
                       "locked": bool(row[2]), "lock_reason": row[3]})
    except sqlite3.Error as exc:            # 缺表 / 损坏 / 只读失败
        result["error"] = f"read_failed:{type(exc).__name__}:{str(exc)[:80]}"
    finally:
        con.close()
    return result


def source_facts() -> list[dict]:
    out = []
    for spec in pb.HISTORY_SOURCES:
        path = pb.canonical_source_path(spec["path"])
        entry = {"source_key": spec["source_key"], "path": spec["path"],
                 "classification": spec["classification"], "exists": path.is_file()}
        entry.update(read_budget_row(path))
        entry["source_key"] = spec["source_key"]
        entry["path"] = spec["path"]
        entry["classification"] = spec["classification"]
        out.append(entry)
    return out


def platform_facts() -> dict:
    if not PLATFORM_DB.is_file():
        return {"path": str(PLATFORM_DB.relative_to(ROOT)), "exists": False,
                "status": "absent",
                "note": "平台账本尚未创建：历史未导入、批次未授权（本预检不会创建）"}
    out: dict = {"path": str(PLATFORM_DB.relative_to(ROOT)), "exists": True,
                 "status": "unknown", "sidecars": sidecars(PLATFORM_DB)}
    if out["sidecars"]:
        out["error"] = "wal_present"        # 平台读数同样不可信
        return out
    try:
        con = sqlite3.connect(PLATFORM_DB.as_uri() + "?mode=ro&immutable=1",
                              uri=True, timeout=5.0)
        con.row_factory = sqlite3.Row
    except sqlite3.Error as exc:
        out["error"] = f"open_failed:{type(exc).__name__}"
        return out
    try:
        history = con.execute("SELECT payload, imported_at FROM history WHERE site=?",
                              ("weibo",)).fetchone()
        lock = con.execute("SELECT reason, source FROM locks WHERE site=?",
                           ("weibo",)).fetchone()
        batch = con.execute("SELECT * FROM batches WHERE batch_id=?", (BATCH,)).fetchone()
        kinds = dict(con.execute(
            "SELECT kind, COUNT(*) FROM events WHERE site=? GROUP BY kind",
            ("weibo",)).fetchall())
    except sqlite3.Error as exc:
        out["error"] = f"read_failed:{type(exc).__name__}"
        return out
    finally:
        con.close()
    out.update({"status": "ok", "locked": bool(lock),
                "lock_reason": lock["reason"] if lock else None,
                "lock_source": lock["source"] if lock else None,
                "event_kinds": kinds})
    if history is None:
        out["history_imported"] = False
    else:
        payload = json.loads(history["payload"])
        rows = payload.get("rows", [])
        out.update({
            "history_imported": True,
            "history_imported_at": utc(history["imported_at"]),
            "history_pre_deducted_calls": sum(r["calls"] for r in rows
                                              if r["classification"] == pb.HISTORY_PRE_DEDUCTED),
            "history_uncharged_navigations": sum(
                1 for r in rows if r["classification"] == pb.HISTORY_UNCHARGED_NAV),
            "history_offline_checks": sum(1 for r in rows
                                          if r["classification"] == pb.HISTORY_OFFLINE_CHECK),
            "history_test_only": bool(payload.get("test_only")),
        })
    if batch is None:
        out["batch_authorized"] = False
    else:
        now = time.time()
        seed = int(batch["seed_used"] or 0)
        window_end = float(batch["started_at"]) + float(batch["window_seconds"])
        used = seed + sum(v for k, v in kinds.items() if k in pb.CALL_KINDS)
        out.update({"batch_authorized": True,
                    "authorized_calls": int(batch["authorized_calls"]),
                    "seed_used": seed, "seed_source": batch["seed_source"],
                    "records_cap": int(batch["records_cap"]),
                    "window_seconds": float(batch["window_seconds"]),
                    "started_at": utc(batch["started_at"]),
                    "window_open": now < window_end,
                    "window_left_s": round(window_end - now, 1),
                    "used": used,
                    "remaining": max(0, int(batch["authorized_calls"]) - used)})
    return out


def main() -> int:
    sources = source_facts()
    platform = platform_facts()
    ok = [s for s in sources if s["status"] == "ok"]
    unknown = [s for s in sources if s["status"] != "ok"]
    locked = [s for s in ok if s["locked"]]
    no_lock_conclusion = (len(unknown) == 0 and len(locked) == 0)
    payload = {
        "generated_utc": utc(time.time()),
        "platform_api": {
            "DEFAULT_PATH": str(PLATFORM_DB.relative_to(ROOT)),
            "MAX_AUTHORIZED_CALLS": pb.MAX_AUTHORIZED_CALLS,
            "MAX_SECONDS": pb.MAX_SECONDS,
            "MIN_INTERVAL": pb.MIN_INTERVAL,
            "MAX_RECORDS": pb.MAX_RECORDS,
            "call_kinds": list(pb.CALL_KINDS),
            "history_sources": len(pb.HISTORY_SOURCES),
        },
        "sources": sources,
        "sources_summary": {
            "total": len(sources), "ok": len(ok), "unknown": len(unknown),
            "locked": [s["source_key"] for s in locked],
            "unknown_keys": [s["source_key"] for s in unknown],
            "no_lock_conclusion_allowed": no_lock_conclusion,
            "note": ("只有全部源 status=ok 且无人 locked 时，才允许说「未发现锁」；"
                     "unknown 一律不当作无锁"),
        },
        "platform": platform,
        "profile": {"path": str(PROFILE.relative_to(ROOT)), "exists": PROFILE.is_dir(),
                    "note": "只判断目录存在；未打开、未读 cookie"},
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "preflight.json").write_bytes(
        json.dumps(payload, ensure_ascii=False, indent=1).encode())
    print(json.dumps({"generated_utc": payload["generated_utc"],
                      "sources_summary": payload["sources_summary"],
                      "platform": {k: platform.get(k) for k in
                                   ("exists", "status", "error", "history_imported",
                                    "batch_authorized", "locked", "window_open",
                                    "remaining")},
                      "profile_exists": payload["profile"]["exists"]},
                     ensure_ascii=False))
    return 0 if no_lock_conclusion else 3


if __name__ == "__main__":
    raise SystemExit(main())
