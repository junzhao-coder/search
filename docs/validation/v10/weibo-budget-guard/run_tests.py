"""Run the three access suites with UTF-8 capture and an auditable manifest.

Kept in this task's own directory on purpose: the previous task's logs live in
`weibo-verify/` and this task must not touch that directory.
"""

from __future__ import annotations

import datetime as dt
import json
import pathlib
import re
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parents[3]
PYTHON = str(REPO / ".venv" / "Scripts" / "python.exe")

MODULES = ["tests.test_access_weibo", "tests.test_access_zhihu",
           "tests.test_access_budget"]

_RAN = re.compile(r"Ran (\d+) tests? in")
_SKIP = re.compile(r"skipped=(\d+)")
_FAIL = re.compile(r"failures=(\d+)")
_ERR = re.compile(r"errors=(\d+)")


def main() -> int:
    runs = []
    for module in MODULES:
        tag = module.rsplit(".", 1)[-1]
        started = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        argv = [PYTHON, "-X", "utf8", "-m", "unittest", module, "-v"]
        proc = subprocess.run(argv, cwd=str(REPO), capture_output=True, text=True,
                              encoding="utf-8", errors="replace", timeout=900)
        finished = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        (HERE / f"{tag}_stdout.log").write_text(proc.stdout, encoding="utf-8")
        (HERE / f"{tag}_stderr.log").write_text(proc.stderr, encoding="utf-8")
        ran = _RAN.search(proc.stderr)
        runs.append({
            "module": module, "argv": argv, "cwd": str(REPO),
            "started_utc": started, "finished_utc": finished,
            "exit": proc.returncode,
            "tests_run": int(ran.group(1)) if ran else None,
            "skipped": int(_SKIP.search(proc.stderr).group(1))
            if _SKIP.search(proc.stderr) else 0,
            "failures": int(_FAIL.search(proc.stderr).group(1))
            if _FAIL.search(proc.stderr) else 0,
            "errors": int(_ERR.search(proc.stderr).group(1))
            if _ERR.search(proc.stderr) else 0,
            "verdict": proc.stderr.strip().splitlines()[-1] if proc.stderr.strip() else "",
            "stdout_log": f"{tag}_stdout.log", "stderr_log": f"{tag}_stderr.log",
        })
    total = sum(r["tests_run"] or 0 for r in runs)
    manifest = {"generated_utc": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "python": PYTHON, "total_tests": total,
                "total_skipped": sum(r["skipped"] for r in runs),
                "all_green": all(r["exit"] == 0 for r in runs)
                and sum(r["skipped"] for r in runs) == 0,
                "runs": runs}
    (HERE / "RUN_MANIFEST.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: manifest[k] for k in ("total_tests", "total_skipped", "all_green")}))
    for run in runs:
        print(f"  {run['module']:<28} exit={run['exit']} ran={run['tests_run']} "
              f"skipped={run['skipped']} failures={run['failures']} errors={run['errors']}")
    return 0 if manifest["all_green"] else 1


if __name__ == "__main__":
    sys.exit(main())
