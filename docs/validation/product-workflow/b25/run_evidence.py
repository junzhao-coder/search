"""运行证据采集：跑单测与两次 review.py，记录 argv/cwd/UTC/returncode（只读 CSV）。"""

from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys
import time

B25 = pathlib.Path(__file__).resolve().parent


def utc() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def run(argv: list[str], log_name: str) -> dict:
    started = utc()
    proc = subprocess.run(argv, cwd=str(B25), capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
    ended = utc()
    log_text = (
        f"# argv: {json.dumps(argv, ensure_ascii=False)}\n# cwd: {B25}\n# start_utc: {started}\n"
        f"# end_utc: {ended}\n# returncode: {proc.returncode}\n\n[stdout]\n{proc.stdout}\n[stderr]\n{proc.stderr}\n"
    )
    with (B25 / log_name).open("w", encoding="utf-8", newline="\n") as fh:
        fh.write(log_text)
    return {"argv": argv, "cwd": str(B25), "start_utc": started, "end_utc": ended,
            "returncode": proc.returncode, "log": log_name}


def main() -> int:
    py = sys.executable
    jobs = [
        ([py, "-X", "utf8", "-m", "unittest", "discover", "-s", "tests", "-t", ".", "-v"], "tests-run.log"),
        ([py, "-X", "utf8", "review.py", "feedback-log.csv"], "run-default.log"),
        ([py, "-X", "utf8", "review.py", "feedback-log.csv", "--json"], "run-json.log"),
    ]
    manifest = {"utc": utc(), "python": py, "runs": []}
    for argv, log in jobs:
        manifest["runs"].append(run(argv, log))
    bad = [r for r in manifest["runs"] if r["returncode"] != 0]
    manifest["all_zero"] = not bad
    with (B25 / "run-manifest.json").open("w", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    for r in manifest["runs"]:
        print(f"{r['log']}: returncode={r['returncode']}")
    print("all_zero", manifest["all_zero"])
    return 0 if manifest["all_zero"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
