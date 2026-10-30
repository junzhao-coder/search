"""weibo-fixes：跑 weibo + zhihu + budget 三个模块并逐模块记录 argv/cwd/UTC/exit。"""

from __future__ import annotations

import datetime as dt
import json
import os
import pathlib
import subprocess
import sys

REPO = pathlib.Path(r"D:\桌面\two")
OUT = REPO / "docs" / "validation" / "v10" / "weibo-fixes"
LOGS = OUT / "logs"

MODULES = ("tests.test_access_weibo", "tests.test_access_zhihu", "tests.test_access_budget")


def utc() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def main() -> int:
    LOGS.mkdir(parents=True, exist_ok=True)
    suites = []
    worst = 0
    for module in MODULES:
        argv = [sys.executable, "-X", "utf8", "-m", "unittest", module, "-v"]
        env = dict(os.environ)
        env.update({"PYTHONUTF8": "1", "PYTHONDONTWRITEBYTECODE": "1"})
        start = utc()
        proc = subprocess.run(argv, cwd=str(REPO), capture_output=True, text=True,
                              encoding="utf-8", errors="replace", env=env)
        end = utc()
        stem = module.split(".")[-1]
        out = LOGS / f"{stem}.stdout.txt"
        err = LOGS / f"{stem}.stderr.txt"
        out.write_text(proc.stdout or "", encoding="utf-8")
        err.write_text(proc.stderr or "", encoding="utf-8")
        combined = f"{proc.stdout or ''}\n{proc.stderr or ''}"
        summary = [ln.strip() for ln in combined.splitlines()
                   if ln.startswith("Ran ") or ln.strip() == "OK" or ln.startswith("FAILED")]
        suites.append({"name": module, "argv": argv, "cwd": str(REPO), "start_utc": start,
                       "end_utc": end, "returncode": proc.returncode, "summary_lines": summary,
                       "stdout_file": str(out), "stderr_file": str(err)})
        worst = worst or proc.returncode
    manifest = {"generated_utc": utc(), "network": "none", "browser": "none",
                "command": "python -X utf8 -m unittest <module> -v", "suites": suites}
    (OUT / "execution_manifest.json").write_bytes(
        json.dumps(manifest, ensure_ascii=False, indent=1).encode())
    print(json.dumps([(s["name"], s["returncode"], s["summary_lines"]) for s in suites],
                     ensure_ascii=True))
    return 0 if worst == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
