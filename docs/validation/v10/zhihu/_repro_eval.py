"""Read-only repro: does bm._eval work against a real nodriver browser?"""
import asyncio
import traceback

import nodriver as uc

from tools.selection.access import browser as bm


async def main():
    browser = await uc.start(
        headless=False,
        user_data_dir=r"C:\Users\19183\.dsh\tools\zhihu-collect\profile",
    )
    try:
        await browser.get("https://www.zhihu.com/signin")
        try:
            value = await bm._eval(browser, "location.href")
            print("EVAL_OK", repr(value)[:120])
        except Exception:
            print("EVAL_FAILED")
            traceback.print_exc()
        print("browser_type", type(browser).__name__)
        print("has_evaluate", hasattr(browser, "evaluate"))
        print("has_tab", hasattr(browser, "tab"))
    finally:
        try:
            browser.stop()
        except Exception:
            pass


asyncio.run(main())
