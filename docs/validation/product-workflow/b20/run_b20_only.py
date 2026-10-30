"""B20 专项单跑（subprocess + 留痕），写 execution_manifest_b20_only.json。"""

from __future__ import annotations

import datetime as dt
import json
import os
import pathlib
import subprocess
import sys

B20 = pathlib.Path(r"D:\桌面\two\docs\validation\product-workflow\b20")
LOGS = B20 / "logs"
ROOT = pathlib.Path(r"D:\桌面\two")
PY = ROOT / ".venv" / "Scripts" / "python.exe"
WB = ROOT / "tools" / "workbench"


def utc() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def main() -> int:
    LOGS.mkdir(parents=True, exist_ok=True)
    argv = [str(PY), "-X", "utf8", "-m", "unittest", "tests.test_wizard", "-v"]
    env = dict(os.environ)
    env.update({"PYTHONUTF8": "1", "PYTHONDONTWRITEBYTECODE": "1"})
    start = utc()
    proc = subprocess.run(argv, cwd=str(WB), capture_output=True, text=True,
                          encoding="utf-8", errors="replace", env=env)
    end = utc()
    o, e = LOGS / "b20_only.stdout.txt", LOGS / "b20_only.stderr.txt"
    o.write_text(proc.stdout or "", encoding="utf-8")
    e.write_text(proc.stderr or "", encoding="utf-8")
    summary = [ln.strip() for ln in f"{proc.stdout or ''}\n{proc.stderr or ''}".splitlines()
               if ln.startswith("Ran ") or ln.strip() == "OK" or ln.startswith("FAILED")]
    manifest = {"generated_utc": utc(), "suites": [{
        "name": "b20_wizard", "argv": argv, "cwd": str(WB), "start_utc": start, "end_utc": end,
        "returncode": proc.returncode, "summary_lines": summary,
        "stdout_file": str(o), "stderr_file": str(e)}]}
    (B20 / "execution_manifest_b20_only.json").write_bytes(json.dumps(manifest, ensure_ascii=False, indent=1).encode())
    print(json.dumps({"rc": proc.returncode, "summary": summary}, ensure_ascii=True))
    return 0 if proc.returncode == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
