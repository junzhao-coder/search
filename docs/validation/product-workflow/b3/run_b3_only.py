"""B3 专项单跑（真实 subprocess + 留痕），写 execution_manifest_b3_only.json。"""

from __future__ import annotations

import datetime as dt
import json
import os
import pathlib
import subprocess
import sys

B3 = pathlib.Path(r"D:\桌面\two\docs\validation\product-workflow\b3")
LOGS = B3 / "logs"
ROOT = pathlib.Path(r"D:\桌面\two")
PY = ROOT / ".venv" / "Scripts" / "python.exe"
WORKBENCH = ROOT / "tools" / "workbench"


def utc() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def main() -> int:
    LOGS.mkdir(parents=True, exist_ok=True)
    argv = [str(PY), "-X", "utf8", "-m", "unittest", "tests.test_export", "-v"]
    env = dict(os.environ)
    env.update({"PYTHONUTF8": "1", "PYTHONDONTWRITEBYTECODE": "1"})
    start = utc()
    proc = subprocess.run(argv, cwd=str(WORKBENCH), capture_output=True, text=True,
                          encoding="utf-8", errors="replace", env=env)
    end = utc()
    out_file = LOGS / "b3_only.stdout.txt"
    err_file = LOGS / "b3_only.stderr.txt"
    out_file.write_text(proc.stdout or "", encoding="utf-8")
    err_file.write_text(proc.stderr or "", encoding="utf-8")
    combined = f"{proc.stdout or ''}\n{proc.stderr or ''}"
    summary = [line.strip() for line in combined.splitlines()
               if line.startswith("Ran ") or line.strip() == "OK" or line.startswith("FAILED")]
    manifest = {"generated_utc": utc(), "suites": [{
        "name": "b3_export", "argv": argv, "cwd": str(WORKBENCH), "start_utc": start, "end_utc": end,
        "returncode": proc.returncode, "summary_lines": summary,
        "stdout_file": str(out_file), "stderr_file": str(err_file)}]}
    (B3 / "execution_manifest_b3_only.json").write_bytes(json.dumps(manifest, ensure_ascii=False, indent=1).encode())
    print(json.dumps({"rc": proc.returncode, "summary": summary}, ensure_ascii=True))
    return 0 if proc.returncode == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
