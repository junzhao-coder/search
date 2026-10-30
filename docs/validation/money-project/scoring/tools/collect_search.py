#!/usr/bin/env python
"""Read-only X search wrapper (f=top) for the scoring task.

Copied from topic-crawler/tools/collect_search.py; the tool's fixed structured
RISK_JS is used as-is. x_collect.py is not modified.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from urllib.parse import quote

TOOL_SCRIPTS = r"C:\Users\19183\.dsh\tools\x-collect\scripts"
sys.path.insert(0, TOOL_SCRIPTS)

import x_collect as xc  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(prog="collect_search")
    parser.add_argument("--keyword", required=True)
    parser.add_argument("--limit", type=int, default=30)
    parser.add_argument("--interval-min", type=int, default=8)
    parser.add_argument("--interval-max", type=int, default=12)
    args = parser.parse_args()
    limit = min(max(args.limit, 1), 60)
    keyword = args.keyword.strip()
    url = f"https://x.com/search?q={quote(keyword)}&f=top"
    log = xc.RunLog("search")
    log.write(f"WRAPPER_F_TOP keyword={keyword!r} limit={limit}")
    code = asyncio.run(xc._collect_async(
        "search", url, limit, keyword, False,
        max(args.interval_min, 8), max(args.interval_max, 12), log))
    log.close(code)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
