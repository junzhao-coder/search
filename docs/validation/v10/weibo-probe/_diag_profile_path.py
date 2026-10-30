"""Local-only diagnosis (NO weibo request): does a *relative* empty profile path
break nodriver launch, while an absolute one works?

Uses about:blank only. Nothing is sent to any site.
"""

import asyncio
import pathlib
import traceback

import nodriver as uc

CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
REL = "docs\\validation\\v10\\weibo-probe\\profile_empty"
ABS = str(pathlib.Path(r"D:\桌面\two\docs\validation\v10\weibo-probe\profile_empty").resolve())
BLANK = "about:blank"


async def attempt(label: str, user_data_dir: str, headless: bool) -> None:
    try:
        browser = await asyncio.wait_for(
            uc.start(headless=headless, user_data_dir=user_data_dir,
                     browser_executable_path=CHROME), timeout=40)
    except Exception as exc:  # noqa: BLE001
        print(f"{label}: LAUNCH_FAILED {type(exc).__name__}: {str(exc).strip()[:160]}")
        return
    try:
        tab = await asyncio.wait_for(browser.get(BLANK), timeout=15)
        print(f"{label}: OK type(tab)={type(tab).__name__}")
    except Exception as exc:  # noqa: BLE001
        print(f"{label}: NAV_FAILED {type(exc).__name__}: {str(exc).strip()[:160]}")
    finally:
        try:
            browser.stop()
        except Exception:
            pass


async def main() -> None:
    await attempt("relative + visible", REL, False)
    await attempt("absolute + visible", ABS, False)


asyncio.run(main())
