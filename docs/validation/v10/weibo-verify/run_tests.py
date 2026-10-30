"""Run the three access test modules with UTF-8 capture and a machine-readable manifest.

Why a runner instead of a shell redirect: PowerShell `*>` writes UTF-16LE, which
shows up as a binary log for reviewers. This writes plain UTF-8 (no BOM) for both
streams and records exact argv/cwd/UTC/exit/skip counts next to them.
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

MODULES = [
    "tests.test_access_weibo",
    "tests.test_access_zhihu",
    "tests.test_access_budget",
]

#: one extra run so the JS-executing class has its own recorded count
FOCUS = "tests.test_access_weibo.SignedInJsTests"

_RAN = re.compile(r"Ran (\d+) tests? in")
_SKIP = re.compile(r"skipped=(\d+)")
_FAIL = re.compile(r"failures=(\d+)")
_ERR = re.compile(r"errors=(\d+)")


def _run(args: list[str], tag: str) -> dict:
    started = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    proc = subprocess.run(args, cwd=str(REPO), capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=900)
    finished = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    (HERE / f"{tag}_stdout.log").write_text(proc.stdout, encoding="utf-8")
    (HERE / f"{tag}_stderr.log").write_text(proc.stderr, encoding="utf-8")
    tail = proc.stderr.strip().splitlines()[-1] if proc.stderr.strip() else ""
    ran = _RAN.search(proc.stderr)
    return {
        "tag": tag,
        "argv": args,
        "cwd": str(REPO),
        "started_utc": started,
        "finished_utc": finished,
        "exit": proc.returncode,
        "tests_run": int(ran.group(1)) if ran else None,
        "skipped": int(_SKIP.search(proc.stderr).group(1)) if _SKIP.search(proc.stderr) else 0,
        "failures": int(_FAIL.search(proc.stderr).group(1)) if _FAIL.search(proc.stderr) else 0,
        "errors": int(_ERR.search(proc.stderr).group(1)) if _ERR.search(proc.stderr) else 0,
        "verdict": tail,
        "stdout_log": f"{tag}_stdout.log",
        "stderr_log": f"{tag}_stderr.log",
    }


def main() -> int:
    runs = []
    for module in MODULES:
        runs.append(_run([PYTHON, "-X", "utf8", "-m", "unittest", module, "-v"],
                         module.rsplit(".", 1)[-1]))
    runs.append(_run([PYTHON, "-X", "utf8", "-m", "unittest", FOCUS, "-v"], "signed_in_js"))

    total = sum(r["tests_run"] or 0 for r in runs[:len(MODULES)])
    skipped = sum(r["skipped"] for r in runs[:len(MODULES)])
    failed = any(r["exit"] != 0 for r in runs)
    manifest = {
        "generated_utc": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "python": PYTHON,
        "modules": MODULES,
        "total_tests_across_modules": total,
        "total_skipped": skipped,
        "node_js_class_tests": runs[-1]["tests_run"],
        "node_js_class_skipped": runs[-1]["skipped"],
        "all_green": not failed and skipped == 0,
        "runs": runs,
    }
    (HERE / "RUN_MANIFEST.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: manifest[k] for k in ("total_tests_across_modules",
                                               "total_skipped",
                                               "node_js_class_tests",
                                               "all_green")}))
    for run in runs:
        print(f"  {run['tag']:<20} exit={run['exit']} ran={run['tests_run']} "
              f"skipped={run['skipped']} failures={run['failures']} errors={run['errors']}")
    return 0 if manifest["all_green"] else 1


if __name__ == "__main__":
    sys.exit(main())
