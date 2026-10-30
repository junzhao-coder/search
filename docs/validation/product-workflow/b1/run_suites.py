"""用真实 subprocess 跑三套测试，生成 execution_manifest.json（argv/cwd/UTC/returncode + 原始输出留档）。

退出码取自 subprocess.returncode，不手填。
"""

from __future__ import annotations

import datetime as dt
import json
import os
import pathlib
import subprocess
import sys

B1 = pathlib.Path(r"D:\桌面\two\docs\validation\product-workflow\b1")
LOGS = B1 / "logs"
ROOT = pathlib.Path(r"D:\桌面\two")
PY = ROOT / ".venv" / "Scripts" / "python.exe"
WORKBENCH = ROOT / "tools" / "workbench"


def utc() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


SUITES = (
    ("b1_workflow", [str(PY), "-X", "utf8", "-m", "unittest", "tests.test_workflow", "-v"], WORKBENCH),
    ("workbench_all", [str(PY), "-X", "utf8", "-m", "unittest", "discover", "-s", "tests", "-t", ".", "-v"], WORKBENCH),
    ("project_full", [str(PY), "-X", "utf8", "-m", "unittest", "discover", "-s", "tests", "-v"], ROOT),
)


def main() -> int:
    LOGS.mkdir(parents=True, exist_ok=True)
    manifest = {"generated_utc": utc(), "python": str(PY), "suites": []}
    for name, argv, cwd in SUITES:
        env = dict(os.environ)
        env.update({"PYTHONUTF8": "1", "PYTHONDONTWRITEBYTECODE": "1"})
        if name == "project_full":
            env["APP_DB_PATH"] = str(pathlib.Path(os.environ.get("TEMP", ".")) / "b1_full.db")
        start = utc()
        proc = subprocess.run(argv, cwd=str(cwd), capture_output=True, text=True, encoding="utf-8",
                              errors="replace", env=env)
        end = utc()
        out_file = LOGS / f"{name}.stdout.txt"
        err_file = LOGS / f"{name}.stderr.txt"
        out_file.write_text(proc.stdout or "", encoding="utf-8")
        err_file.write_text(proc.stderr or "", encoding="utf-8")
        combined = f"{proc.stdout or ''}\n{proc.stderr or ''}"
        summary = [line.strip() for line in combined.splitlines()
                   if line.startswith("Ran ") or line.strip() == "OK" or line.startswith("FAILED")]
        manifest["suites"].append({
            "name": name, "argv": argv, "cwd": str(cwd), "start_utc": start, "end_utc": end,
            "returncode": proc.returncode, "summary_lines": summary,
            "stdout_file": str(out_file), "stderr_file": str(err_file),
            "stdout_bytes": out_file.stat().st_size, "stderr_bytes": err_file.stat().st_size,
        })
        print(f"{name}: returncode={proc.returncode} {' | '.join(summary[:3])}")
    (B1 / "execution_manifest.json").write_bytes(json.dumps(manifest, ensure_ascii=False, indent=1).encode())
    failed = [s for s in manifest["suites"] if s["returncode"] != 0]
    print(json.dumps({"suites": len(manifest["suites"]), "failed": [s["name"] for s in failed]}, ensure_ascii=True))
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
