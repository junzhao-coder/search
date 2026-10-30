"""守卫拒绝：`platform_locked` 与 `calls_exhausted` 的隔离实测。

为什么需要这个脚本：CLI **故意**不提供 `--platform-db`/`--state-dir` 覆盖（安全属性），
所以「批次已锁」「剩余 0」两例无法用真实账本演示——真实账本里没有这两种状态，
也不允许为本任务改它。这里用**真实平台账本的临时副本**，在进程内把
`platform_budget.DEFAULT_PATH` 指到副本，再走**同一条 `cli.main` 代码路径**，
因此 exit code / stop 字段与线上一致；真实账本一个字节都不动。

用法：
    C:\\Users\\19183\\.dsh\\tools\\x-collect\\venv\\Scripts\\python.exe -X utf8 `
      docs\\validation\\v10\\browser-rpa\\checks\\guard_isolated_check.py
"""

from __future__ import annotations

import contextlib
import datetime as dt
import io
import json
import pathlib
import shutil
import sys
import tempfile

REPO = pathlib.Path(__file__).resolve().parents[5]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from tools.selection.access import platform_budget as pb  # noqa: E402
from tools.selection.rpa import cli  # noqa: E402

HERE = REPO / "docs" / "validation" / "v10" / "browser-rpa"
OUT = HERE / "logs" / "guard-isolated.json"


def _run(argv: list[str]) -> dict:
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = cli.main(argv)
    raw = buf.getvalue().strip()
    try:
        payload = json.loads(raw.splitlines()[-1]) if raw else {}
    except ValueError:
        payload = {"raw": raw}
    return {"argv": argv, "exit": code, "stop": payload.get("stop"),
            "stage": payload.get("stage"),
            "browser_started": payload.get("browser_started"),
            "batch_id": payload.get("batch_id")}


def main() -> int:
    real = pb.DEFAULT_PATH
    if not real.is_file():
        print(json.dumps({"error": "platform_ledger_missing", "path": str(real)}))
        return 2
    before = {"mtime_ns": real.stat().st_mtime_ns, "size": real.stat().st_size}
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="rpa-guard-"))
    results = []

    # 1) 已锁：副本 + lock 行
    locked_copy = tmp / "locked.sqlite3"
    shutil.copy2(real, locked_copy)
    ledger = pb.PlatformLedger(locked_copy)
    ledger.lock("test:locked_case", source="guard_isolated_check")
    ledger.close()
    pb.DEFAULT_PATH = locked_copy
    results.append({"case": "platform_locked",
                    **_run(["live-search", "--keyword", "kw", "--allow-live",
                            "--batch-id", "weibo-verify-1"])})

    # 2) 剩余 0：副本 + 新批次（3 次，2 个历史 seed）+ 用掉最后 1 次
    zero_copy = tmp / "zero.sqlite3"
    shutil.copy2(real, zero_copy)
    ledger = pb.PlatformLedger(zero_copy)
    ledger.authorize_batch("zero-1", authorized_calls=3, window_seconds=300,
                           source="guard_isolated_check",
                           seed_from=("login-window-1", "login-window-2"))
    ledger.charge("zero-1", "search", detail="guard-isolated", source="guard_isolated_check")
    summary = ledger.summary("zero-1")
    ledger.close()
    pb.DEFAULT_PATH = zero_copy
    results.append({"case": "calls_exhausted", "remaining": summary.get("remaining"),
                    "window_open": summary.get("window_open"),
                    **_run(["live-search", "--keyword", "kw", "--allow-live",
                            "--batch-id", "zero-1"])})

    after = {"mtime_ns": real.stat().st_mtime_ns, "size": real.stat().st_size}
    payload = {"generated_utc": dt.datetime.now(dt.timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ"), "isolated": True, "results": results,
        "real_ledger_before": before, "real_ledger_after": after,
        "real_ledger_unchanged": before == after,
        "note": "DEFAULT_PATH 在进程内指向临时副本；真实账本只被 stat，未被写入"}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False))
    return 0 if all(r["exit"] == 6 for r in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
