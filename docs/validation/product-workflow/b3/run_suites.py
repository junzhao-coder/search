"""B3：三套测试用真实 subprocess 执行并留痕（argv/cwd/UTC/returncode + 原始输出）。"""

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

SUITES = (
    ("b3_export", [str(PY), "-X", "utf8", "-m", "unittest", "tests.test_export", "-v"], WORKBENCH),
    ("b1_workflow", [str(PY), "-X", "utf8", "-m", "unittest", "tests.test_workflow", "-v"], WORKBENCH),
    ("workbench_all", [str(PY), "-X", "utf8", "-m", "unittest", "discover", "-s", "tests", "-t", ".", "-v"], WORKBENCH),
    ("project_full", [str(PY), "-X", "utf8", "-m", "unittest", "discover", "-s", "tests", "-v"], ROOT),
)


def utc() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def main() -> int:
    LOGS.mkdir(parents=True, exist_ok=True)
    manifest = {"generated_utc": utc(), "python": str(PY), "suites": []}
    for name, argv, cwd in SUITES:
        env = dict(os.environ)
        env.update({"PYTHONUTF8": "1", "PYTHONDONTWRITEBYTECODE": "1"})
        if name == "project_full":
            env["APP_DB_PATH"] = str(pathlib.Path(os.environ.get("TEMP", ".")) / "b3_full.db")
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
        manifest["suites"].append({"name": name, "argv": argv, "cwd": str(cwd),
                                   "start_utc": start, "end_utc": end, "returncode": proc.returncode,
                                   "summary_lines": summary, "stdout_file": str(out_file),
                                   "stderr_file": str(err_file)})
        print(f"{name}: rc={proc.returncode} {' | '.join(summary[:3])}")
    (B3 / "execution_manifest.json").write_bytes(json.dumps(manifest, ensure_ascii=False, indent=1).encode())
    failed = [s["name"] for s in manifest["suites"] if s["returncode"] != 0]
    print(json.dumps({"suites": len(manifest["suites"]), "failed": failed}, ensure_ascii=True))
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
