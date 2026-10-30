"""Run a command with UTF-8-captured stdout/stderr and a command/cwd/UTC/exit log.

Usage: python run_proc.py --label <label> --cwd <dir> --out-dir <dir> --exe <exe> [--timeout 120] -- <args...>

Writes: <out-dir>/<label>.out.txt, .err.txt, .log (UTF-8, no BOM, LF).
"""

from __future__ import annotations

import argparse
import datetime as dt
import os
import pathlib
import subprocess
import sys
import time

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:  # pragma: no cover
    pass


def decode(data: bytes) -> str:
    for encoding in ("utf-8", "utf-8-sig", "gb18030"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--label", required=True)
    parser.add_argument("--cwd", required=True)
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--exe", required=True)
    parser.add_argument("--timeout", type=float, default=120.0)
    parser.add_argument("args", nargs=argparse.REMAINDER)
    ns = parser.parse_args()
    args = ns.args[1:] if ns.args and ns.args[0] == "--" else ns.args
    out_dir = pathlib.Path(ns.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    started = dt.datetime.now(dt.timezone.utc)
    env = dict(os.environ)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTHONUTF8"] = "1"
    command_text = " ".join([ns.exe] + args)
    try:
        proc = subprocess.run([ns.exe] + args, cwd=ns.cwd, env=env, capture_output=True,
                              timeout=ns.timeout)
        code = proc.returncode
        out_text = decode(proc.stdout)
        err_text = decode(proc.stderr)
        raw_out, raw_err = proc.stdout, proc.stderr
        timed_out = False
    except subprocess.TimeoutExpired as exc:
        code = 124
        raw_out = exc.stdout or b""
        raw_err = exc.stderr or b""
        out_text = decode(raw_out)
        err_text = decode(raw_err) + f"\n[TIMEOUT after {ns.timeout}s]"
        timed_out = True
    finished = dt.datetime.now(dt.timezone.utc)
    (out_dir / f"{ns.label}.out.txt").write_bytes(out_text.encode("utf-8"))
    (out_dir / f"{ns.label}.err.txt").write_bytes(err_text.encode("utf-8"))
    (out_dir / f"{ns.label}.raw.out").write_bytes(raw_out)
    (out_dir / f"{ns.label}.raw.err").write_bytes(raw_err)
    header = [
        f"label={ns.label}",
        f"cmd={command_text}",
        f"cwd={ns.cwd}",
        f"start_utc={started.strftime('%Y-%m-%dT%H:%M:%SZ')}",
        f"end_utc={finished.strftime('%Y-%m-%dT%H:%M:%SZ')}",
        f"exit={code}",
        f"timed_out={timed_out}",
        "---- stdout ----",
    ]
    log = "\n".join(header) + "\n" + out_text + "\n---- stderr ----\n" + err_text + "\n"
    (out_dir / f"{ns.label}.log").write_bytes(log.encode("utf-8"))
    print(f"label={ns.label} exit={code} out_bytes={len(raw_out)} err_bytes={len(raw_err)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
