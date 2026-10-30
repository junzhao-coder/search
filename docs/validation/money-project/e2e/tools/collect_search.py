#!/usr/bin/env python
"""E2E X search wrapper (f=top) with a batch-local seen file.

Does not modify x_collect.py; only overrides the module-level SEEN path so the
new batch is not suppressed by historical dedupe.
"""

from __future__ import annotations

import argparse
import asyncio
import pathlib
import sys
from urllib.parse import quote

BASE = pathlib.Path(__file__).resolve().parents[1]
TOOL_SCRIPTS = r"C:\Users\19183\.dsh\tools\x-collect\scripts"
sys.path.insert(0, TOOL_SCRIPTS)

import x_collect as xc  # noqa: E402

xc.SEEN = BASE / "data" / "x_seen.jsonl"


def main() -> int:
    parser = argparse.ArgumentParser(prog="e2e_collect_search")
    parser.add_argument("--keyword", required=True)
    parser.add_argument("--limit", type=int, default=30)
    parser.add_argument("--interval-min", type=int, default=8)
    parser.add_argument("--interval-max", type=int, default=12)
    args = parser.parse_args()
    keyword = args.keyword.strip()
    limit = min(max(args.limit, 1), 60)
    url = f"https://x.com/search?q={quote(keyword)}&f=top"
    log = xc.RunLog("search")
    log.write(f"E2E_WRAPPER keyword={keyword!r} limit={limit} seen={xc.SEEN}")
    code = asyncio.run(xc._collect_async(
        "search", url, limit, keyword, False,
        max(args.interval_min, 8), max(args.interval_max, 12), log))
    log.close(code)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
