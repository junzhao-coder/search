"""weibo-review：跑 tests.test_access_weibo 并记录 argv/cwd/UTC/exit（离线，无网络无浏览器）。"""

from __future__ import annotations

import datetime as dt
import json
import os
import pathlib
import subprocess
import sys

REPO = pathlib.Path(r"D:\桌面\two")
OUT = REPO / "docs" / "validation" / "v10" / "weibo-review"
LOGS = OUT / "logs"


def utc() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def main() -> int:
    LOGS.mkdir(parents=True, exist_ok=True)
    argv = [sys.executable, "-X", "utf8", "-m", "unittest", "tests.test_access_weibo", "-v"]
    env = dict(os.environ)
    env.update({"PYTHONUTF8": "1", "PYTHONDONTWRITEBYTECODE": "1"})
    start = utc()
    proc = subprocess.run(argv, cwd=str(REPO), capture_output=True, text=True,
                          encoding="utf-8", errors="replace", env=env)
    end = utc()
    (LOGS / "test_access_weibo.stdout.txt").write_text(proc.stdout or "", encoding="utf-8")
    (LOGS / "test_access_weibo.stderr.txt").write_text(proc.stderr or "", encoding="utf-8")
    combined = f"{proc.stdout or ''}\n{proc.stderr or ''}"
    summary = [ln.strip() for ln in combined.splitlines()
               if ln.startswith("Ran ") or ln.strip() == "OK" or ln.startswith("FAILED")]
    manifest = {"generated_utc": utc(), "network": "none", "browser": "none",
                "suites": [{"name": "tests.test_access_weibo", "argv": argv, "cwd": str(REPO),
                            "start_utc": start, "end_utc": end, "returncode": proc.returncode,
                            "summary_lines": summary,
                            "stdout_file": str(LOGS / "test_access_weibo.stdout.txt"),
                            "stderr_file": str(LOGS / "test_access_weibo.stderr.txt")}]}
    (OUT / "execution_manifest.json").write_bytes(
        json.dumps(manifest, ensure_ascii=False, indent=1).encode())
    print(json.dumps({"returncode": proc.returncode, "summary": summary,
                      "start_utc": start, "end_utc": end}, ensure_ascii=True))
    return 0 if proc.returncode == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
