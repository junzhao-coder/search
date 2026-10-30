"""Run a child command and save a UTF-8 (no BOM) log: cmd / cwd / UTC start / real exit / stdout / stderr.

Usage: python run_and_log_utf8.py --log <file> --cwd <dir> --label <label> -- <cmd...>
Exits with the child's real exit code.
"""

from __future__ import annotations

import datetime
import pathlib
import subprocess
import sys


def main() -> int:
    argv = sys.argv[1:]
    log_path = pathlib.Path(argv[argv.index("--log") + 1])
    cwd = argv[argv.index("--cwd") + 1]
    label = argv[argv.index("--label") + 1]
    cmd = argv[argv.index("--") + 1:]
    started = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
    proc = subprocess.run(cmd, cwd=cwd, capture_output=True, encoding="utf-8", errors="replace")
    text = "\n".join([
        f"label={label}",
        f"cmd={' '.join(cmd)}",
        f"cwd={cwd}",
        f"start_utc={started}",
        f"exit={proc.returncode}",
        "--- stdout ---",
        proc.stdout or "",
        "--- stderr ---",
        proc.stderr or "",
    ]) + "\n"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_bytes(text.encode("utf-8"))
    print(proc.stdout or "")
    if proc.stderr:
        sys.stderr.write(proc.stderr)
    print(f"[run_and_log_utf8] label={label} exit={proc.returncode} log={log_path}")
    return proc.returncode


if __name__ == "__main__":
    sys.exit(main())
