"""微博预算只读审计（v2）：汇总本次发现范围内的 state-dir 账本。

只读：`sqlite3` 以 `mode=ro&immutable=1` 打开，不写任何账本、不触网、不读 profile。

用法：python -X utf8 docs/validation/v10/weibo-budget-audit/audit.py
输出：同目录 audit.json（机器可读，含 scope / limits / classification）+ stdout 摘要。
"""

from __future__ import annotations

import datetime as dt
import json
import pathlib
import sqlite3

ROOT = pathlib.Path(r"D:\桌面\two")
OUT = ROOT / "docs" / "validation" / "v10" / "weibo-budget-audit"

#: 「本次发现范围」——报告里所有汇总数字都受这三行约束
SCOPE = {
    "root": str(ROOT),
    "search_root": "docs/validation/v10",
    "include_pattern": "**/budget.sqlite3",
    "path_filter": "路径含 'weibo'",
    "exclude_pattern": "路径含 'profile'",
    "note": "不覆盖 instance/、tools/**/runtime/、docs/validation/v10 之外的账本",
}

LIMITS = [
    "immutable=1 会忽略未 checkpoint 的 -wal：读到的行可能偏少（本次已确认被审目录无 -wal 文件）",
    "无抓包/无 devtools 事件日志：重定向与子资源请求数未知，digits 不能换算成 HTTP 请求数",
    "ledger 只是过程证据；额度只由 budget.calls / polls / locked 决定",
    "calls 只统计 charge()；login（含 check-session）只 charge_poll()，不计 calls",
]

OFFLINE_MARK = "network_disabled_offline_batch"


def utc(stamp) -> str | None:
    try:
        return dt.datetime.fromtimestamp(float(stamp), dt.timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%SZ")
    except (TypeError, ValueError, OSError):
        return None


def read_dir(folder: pathlib.Path) -> dict:
    uri = (folder / "budget.sqlite3").as_uri() + "?mode=ro&immutable=1"
    con = sqlite3.connect(uri, uri=True, timeout=3.0)
    try:
        calls, polls, locked, reason, source, batch = con.execute(
            "SELECT calls, polls, locked, lock_reason, lock_source, batch_id FROM budget"
        ).fetchone()
        rows = con.execute("SELECT at, kind, detail FROM ledger ORDER BY id").fetchall()
    finally:
        con.close()
    kinds: dict[str, int] = {}
    for _at, kind, _detail in rows:
        kinds[kind] = kinds.get(kind, 0) + 1
    details = " ".join(str(d) for _at, _k, d in rows)
    return {"state_dir": str(folder.relative_to(ROOT)), "batch_id": batch,
            "calls": calls, "polls": polls, "locked": bool(locked),
            "lock_reason": reason, "lock_source": source,
            "ledger_rows": len(rows), "ledger_kinds": kinds,
            "window_utc": {"first": utc(rows[0][0]) if rows else None,
                           "last": utc(rows[-1][0]) if rows else None},
            "offline_marker": OFFLINE_MARK in details}


def classify(rows: list[dict]) -> dict:
    probes = [r for r in rows if "weibo-probe" in r["state_dir"]]
    offline = [r for r in rows if r["offline_marker"]]
    logins = [r for r in rows if "login" in r["state_dir"] and "checks" not in r["state_dir"]]
    for r in probes:
        # probe1: 启动失败、未观察到导航；probe2/3: 显式浏览器搜索尝试
        r["observed_navigation"] = r["calls"] == 1 and "search_result" in r["ledger_kinds"]
    for r in logins:
        r["observed_navigation"] = r["polls"] > 0  # 窗口打开并轮询 = 发生过导航
    historical_probe_precharges = sum(r["calls"] for r in probes)
    historical_login_navigations = sum(1 for r in logins if r["observed_navigation"])
    return {
        "probe_precharges": probes,
        "offline_precharges": offline,
        "login_navigations": logins,
        "conservative_units": {
            "historical_probe_precharges": historical_probe_precharges,
            "historical_login_navigations": historical_login_navigations,
            "planned_check_session": 1,
            "planned_search": 1,
            "total": historical_probe_precharges + historical_login_navigations + 2,
            "note": ("这些是「保守计费单位」，不是已发生的导航次数，更不是 HTTP 请求数："
                     "probe1 为启动失败预扣（未观察到导航）；probe2/3 各一次显式浏览器搜索尝试；"
                     "两次登录窗为已发生的主动导航但未计入 calls；check-session 与搜索尚未执行。"),
        },
    }


def main() -> int:
    folders = sorted({p.parent for p in (ROOT / SCOPE["search_root"]).glob(SCOPE["include_pattern"])
                      if "weibo" in str(p) and "profile" not in str(p)})
    rows = [read_dir(f) for f in folders]
    summary = {
        "generated_utc": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "scope": {**SCOPE, "state_dirs": len(rows),
                  "dirs": [r["state_dir"] for r in rows]},
        "limits": LIMITS,
        "total_calls": sum(r["calls"] for r in rows),
        "total_polls": sum(r["polls"] for r in rows),
        "any_locked": any(r["locked"] for r in rows),
        "lock_scope_note": "仅限本次发现范围；不能据此断言项目历史从未触发风控",
        "rows": rows,
        "classification": classify(rows),
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "audit.json").write_bytes(
        json.dumps(summary, ensure_ascii=False, indent=1).encode())
    print(json.dumps({"generated_utc": summary["generated_utc"],
                      "state_dirs": len(rows), "total_calls": summary["total_calls"],
                      "total_polls": summary["total_polls"],
                      "any_locked": summary["any_locked"],
                      "units": summary["classification"]["conservative_units"]},
                     ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
