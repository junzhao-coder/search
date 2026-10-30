"""Offline probe (no zhihu request): what does browser.get() actually return here,
and is the returned object able to answer evaluate()?

Uses a data: URL so no network call to any site is made.
"""

import asyncio
import json

import nodriver as uc


async def main():
    browser = await uc.start(
        headless=True,
        user_data_dir=r"C:\Users\19183\.dsh\tools\zhihu-collect\profile",
    )
    try:
        tab = await browser.get("data:text/html,<html><body><a href='/q/1'>x</a></body></html>")
        print("type(browser.get(...)) =", type(tab).__name__)
        print("has evaluate:", hasattr(tab, "evaluate"))
        print("has get_content:", hasattr(tab, "get_content"))
        try:
            value = await asyncio.wait_for(tab.evaluate("document.documentElement.readyState"), timeout=5)
            print("evaluate ok:", repr(value))
        except Exception as exc:
            print("evaluate FAILED:", type(exc).__name__, str(exc)[:120])
        try:
            html = await asyncio.wait_for(tab.get_content(), timeout=5)
            print("get_content ok, len:", len(html))
        except Exception as exc:
            print("get_content FAILED:", type(exc).__name__, str(exc)[:120])
        # what the page actually has
        try:
            probe = await asyncio.wait_for(
                tab.evaluate("JSON.stringify({rs:document.readyState,n:document.querySelectorAll('a[href]').length})"),
                timeout=5)
            print("probe:", probe)
        except Exception as exc:
            print("probe FAILED:", type(exc).__name__, str(exc)[:120])
    finally:
        try:
            browser.stop()
        except Exception:
            pass


asyncio.run(main())
