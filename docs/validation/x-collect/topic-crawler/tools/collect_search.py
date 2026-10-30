#!/usr/bin/env python
"""Run x_collect's search collector with a selector-based risk check.

Why this wrapper exists: x_collect's built-in RISK_JS matches the word
"Challenge" case-insensitively anywhere in the page body. A normal tweet in
the "web scraping" results contained the phrase "face several challenges",
which produced a false exit=3 RISK_CONTROL after ~6 items (see
../raw/attempts/). This wrapper does NOT modify x_collect.py; it imports the
same module and replaces only the risk predicate with UI-element checks
(alert/toast/captcha iframe), then calls the same `_collect_async` with the
same limits, dedupe, extraction, and logging.

Read-only: no posting/liking/following/DM, no cookie values printed.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from urllib.parse import quote

TOOL_SCRIPTS = r"C:\Users\19183\.dsh\tools\x-collect\scripts"
sys.path.insert(0, TOOL_SCRIPTS)

import x_collect as xc  # noqa: E402

xc.RISK_JS = r"""
(() => {
  const toast = document.querySelector('[role="alert"], [data-testid="toast"]');
  if (toast) {
    const t = toast.innerText || '';
    if (/Something went wrong|Rate limit|Too Many Requests|Try again|Challenge|captcha/i.test(t)) return true;
  }
  const frame = document.querySelector(
    'iframe[src*="arkose" i], iframe[src*="captcha" i], iframe[title*="captcha" i]'
  );
  return !!frame;
})()
"""


def main() -> int:
    parser = argparse.ArgumentParser(prog="collect_search")
    parser.add_argument("--keyword", required=True)
    parser.add_argument("--limit", type=int, default=40)
    parser.add_argument("--interval-min", type=int, default=8)
    parser.add_argument("--interval-max", type=int, default=12)
    args = parser.parse_args()
    limit = min(max(args.limit, 1), 60)
    keyword = args.keyword.strip()
    url = f"https://x.com/search?q={quote(keyword)}&f=top"
    log = xc.RunLog("search")
    log.write(f"WRAPPER_RISK_SELECTOR keyword={keyword!r} limit={limit}")
    code = asyncio.run(xc._collect_async(
        "search", url, limit, keyword, False,
        max(args.interval_min, 8), max(args.interval_max, 12), log))
    log.close(code)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
