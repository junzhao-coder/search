"""隔离行为检查：preflight 的源读取在「有锁」与「损坏」两种情况下是否如实标注。

只在临时目录里造两个 fixture：
1. `locked/budget.sqlite3` —— 合法库，`budget.locked=1, lock_reason='text:安全验证'`；
2. `broken/budget.sqlite3` —— 非 SQLite 字节（模拟损坏）。

然后调用 `preflight.read_budget_row`，断言：
- 有锁 fixture → `status="ok"`、`locked=True`、`lock_reason` 保留；
- 损坏 fixture → `status="unknown"`、`error` 非空（**不**当作无锁）。

不触碰任何真实账本、平台库或 profile；不联网、不启动浏览器。
用法：python -X utf8 docs/validation/v10/weibo-live-prep/checks/behavior_check.py
"""

from __future__ import annotations

import json
import pathlib
import sqlite3
import sys
import tempfile

ROOT = pathlib.Path(r"D:\桌面\two")
PREP = ROOT / "docs" / "validation" / "v10" / "weibo-live-prep"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(PREP) not in sys.path:
    sys.path.insert(0, str(PREP))

import preflight  # noqa: E402 - 复用被检查的读取函数

SCHEMA = ("CREATE TABLE budget (id INTEGER PRIMARY KEY, calls INTEGER, records INTEGER,"
          " locked INTEGER, lock_reason TEXT)")


def main() -> int:
    results = []
    with tempfile.TemporaryDirectory() as tmp:
        base = pathlib.Path(tmp)

        locked_db = base / "locked" / "budget.sqlite3"
        locked_db.parent.mkdir(parents=True)
        con = sqlite3.connect(str(locked_db))
        con.execute(SCHEMA)
        con.execute("INSERT INTO budget VALUES (1, 2, 0, 1, 'text:安全验证')")
        con.commit()
        con.close()
        locked = preflight.read_budget_row(locked_db)
        results.append({"case": "locked_source", **{k: locked[k] for k in
                        ("status", "calls", "locked", "lock_reason", "error")},
                        "pass": locked["status"] == "ok" and locked["locked"] is True
                        and locked["lock_reason"] == "text:安全验证"})

        broken_db = base / "broken" / "budget.sqlite3"
        broken_db.parent.mkdir(parents=True)
        broken_db.write_bytes(b"this is not a sqlite database" * 8)
        broken = preflight.read_budget_row(broken_db)
        results.append({"case": "corrupted_source", **{k: broken[k] for k in
                        ("status", "locked", "error")},
                        "pass": broken["status"] == "unknown" and broken["error"]
                        and broken["locked"] is None})

        missing = preflight.read_budget_row(base / "nope" / "budget.sqlite3")
        results.append({"case": "missing_source", "status": missing["status"],
                        "error": missing["error"],
                        "pass": missing["status"] == "unknown"
                        and missing["error"] == "missing"})

        wal_db = base / "wal" / "budget.sqlite3"
        wal_db.parent.mkdir(parents=True)
        wal_db.write_bytes(b"x")
        pathlib.Path(str(wal_db) + "-wal").write_bytes(b"pending")
        wal = preflight.read_budget_row(wal_db)
        results.append({"case": "wal_sidecar", "status": wal["status"],
                        "error": wal["error"],
                        "pass": wal["status"] == "unknown"
                        and wal["error"] == "wal_present"})

    ok = all(r["pass"] for r in results)
    out = {"checked": len(results), "all_pass": ok, "cases": results}
    (PREP / "checks").mkdir(parents=True, exist_ok=True)
    (PREP / "checks" / "behavior_check.json").write_bytes(
        json.dumps(out, ensure_ascii=False, indent=1).encode())
    print(json.dumps(out, ensure_ascii=False))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
