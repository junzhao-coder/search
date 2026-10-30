"""B20：测试 subprocess 留痕（wizard / workbench / 原项目）。"""

from __future__ import annotations

import datetime as dt
import json
import os
import pathlib
import subprocess
import sys

OUT = pathlib.Path(r"D:\桌面\two\docs\validation\product-workflow\b20")
LOGS = OUT / "logs"
ROOT = pathlib.Path(r"D:\桌面\two")
PY = ROOT / ".venv" / "Scripts" / "python.exe"
WB = ROOT / "tools" / "workbench"

SUITES = (
    ("b20_wizard", [str(PY), "-X", "utf8", "-m", "unittest", "tests.test_wizard", "-v"], WB),
    ("workbench_all", [str(PY), "-X", "utf8", "-m", "unittest", "discover", "-s", "tests", "-t", ".", "-v"], WB),
    ("project_full", [str(PY), "-X", "utf8", "-m", "unittest", "discover", "-s", "tests", "-v"], ROOT),
)


def utc() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def main() -> int:
    LOGS.mkdir(parents=True, exist_ok=True)
    manifest = {"generated_utc": utc(), "suites": []}
    for name, argv, cwd in SUITES:
        env = dict(os.environ)
        env.update({"PYTHONUTF8": "1", "PYTHONDONTWRITEBYTECODE": "1"})
        if name == "project_full":
            env["APP_DB_PATH"] = str(pathlib.Path(os.environ.get("TEMP", ".")) / "b20_full.db")
        start = utc()
        proc = subprocess.run(argv, cwd=str(cwd), capture_output=True, text=True,
                              encoding="utf-8", errors="replace", env=env)
        end = utc()
        o, e = LOGS / f"{name}.stdout.txt", LOGS / f"{name}.stderr.txt"
        o.write_text(proc.stdout or "", encoding="utf-8")
        e.write_text(proc.stderr or "", encoding="utf-8")
        summary = [ln.strip() for ln in f"{proc.stdout or ''}\n{proc.stderr or ''}".splitlines()
                   if ln.startswith("Ran ") or ln.strip() == "OK" or ln.startswith("FAILED")]
        manifest["suites"].append({"name": name, "argv": argv, "cwd": str(cwd), "start_utc": start,
                                   "end_utc": end, "returncode": proc.returncode, "summary_lines": summary,
                                   "stdout_file": str(o), "stderr_file": str(e)})
        print(f"{name}: rc={proc.returncode} {' | '.join(summary[:3])}")
    (OUT / "execution_manifest.json").write_bytes(json.dumps(manifest, ensure_ascii=False, indent=1).encode())
    failed = [s["name"] for s in manifest["suites"] if s["returncode"] != 0]
    print(json.dumps({"suites": len(manifest["suites"]), "failed": failed}, ensure_ascii=True))
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
