"""浏览器验证：五页桌面 + 两页手机截图、整页溢出、资源/控制台错误、真实筛选/排序/清空/展开计数。

只用 nodriver 测试**新工作台**（127.0.0.1:5015），不桥接 Host、不使用任何登录 profile。
输出：docs/validation/money-project/workbench-ui/interaction_evidence.json
"""

from __future__ import annotations

import asyncio
import datetime as dt
import json
import pathlib
import sys
import traceback

UI = pathlib.Path(r"D:\桌面\two\docs\validation\money-project\workbench-ui")
SHOTS = UI / "shots"
SHOTS.mkdir(parents=True, exist_ok=True)
BASE = "http://127.0.0.1:5015"
CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"

PAGES = ["/", "/opportunities", "/sources", "/collect", "/daily"]
MOBILE_PAGES = ["/", "/opportunities"]

MEASURE = """
(() => {
  const de = document.documentElement;
  const res = performance.getEntriesByType('resource').map(r => r.name);
  const external = res.filter(u => !u.startsWith('http://127.0.0.1:5015'));
  const imgs = Array.from(document.images).map(i => i.src).filter(s => !s.startsWith('http://127.0.0.1:5015'));
  return JSON.stringify({
    url: location.href,
    title: document.title,
    scrollWidth: de.scrollWidth,
    clientWidth: de.clientWidth,
    innerWidth: window.innerWidth,
    overflowX: de.scrollWidth > window.innerWidth + 1,
    resources: res.length,
    external_resources: external,
    external_images: imgs,
    tables: document.querySelectorAll('table').length,
    rows: document.querySelectorAll('tbody tr').length,
    countText: (document.querySelector('.filter-count') || {}).textContent || null,
    firstRow: (document.querySelector('tbody tr') || {}).innerText ? document.querySelector('tbody tr').innerText.replace(/\\s+/g,' ').slice(0,90) : null,
    openDetails: document.querySelectorAll('details[open]').length,
    evidenceVisible: Array.from(document.querySelectorAll('.evidence')).filter(e => e.offsetParent !== null).length
  });
})()
"""


def utc() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


async def measure(tab) -> dict:
    raw = await tab.evaluate(MEASURE, await_promise=False)
    return json.loads(raw) if isinstance(raw, str) else {}


async def main() -> int:
    import nodriver as uc

    report = {"utc": utc(), "base": BASE, "desktop": [], "mobile": [], "interactions": {}, "console": [], "errors": []}
    browser = await uc.start(headless=True, browser_executable_path=CHROME,
                             browser_args=["--hide-scrollbars", "--no-first-run", "--no-default-browser-check",
                                           "--window-size=1440,900"], sandbox=False)
    try:
        tab = await browser.get(BASE + "/")
        await asyncio.sleep(1.5)
        try:
            await tab.send(uc.cdp.log.enable())
            tab.add_handler(uc.cdp.log.entry_added, lambda e: report["console"].append(
                {"level": str(getattr(e.entry, "level", "")), "text": str(getattr(e.entry, "text", ""))[:200]}))
            await tab.send(uc.cdp.network.enable())
            tab.add_handler(uc.cdp.network.loading_failed, lambda e: report["errors"].append(
                {"url": str(getattr(e, "request_id", "")), "error": str(getattr(e, "error_text", ""))[:120]}))
        except Exception as exc:  # 事件订阅失败不阻断测量
            report["console"].append({"level": "warn", "text": f"cdp subscribe skipped: {type(exc).__name__}"})

        # ---- 桌面 1440×900 ----
        for path in PAGES:
            await tab.get(BASE + path)
            await asyncio.sleep(1.2)
            data = await measure(tab)
            shot = SHOTS / f"desktop_{path.strip('/') or 'index'}.png"
            try:
                await tab.save_screenshot(str(shot))
                data["screenshot"] = str(shot)
            except Exception as exc:
                data["screenshot_error"] = f"{type(exc).__name__}: {exc}"
            report["desktop"].append(data)

        # ---- 手机 390×844 ----
        for path in MOBILE_PAGES:
            await tab.get(BASE + path)
            await asyncio.sleep(0.6)
            try:
                await tab.set_window_size(390, 844)
            except Exception:
                pass
            await asyncio.sleep(1.2)
            data = await measure(tab)
            shot = SHOTS / f"mobile_{path.strip('/') or 'index'}.png"
            try:
                await tab.save_screenshot(str(shot))
                data["screenshot"] = str(shot)
            except Exception as exc:
                data["screenshot_error"] = f"{type(exc).__name__}: {exc}"
            report["mobile"].append(data)
        try:
            await tab.set_window_size(1440, 900)
        except Exception:
            pass

        # ---- 真实交互（/opportunities）----
        await tab.get(BASE + "/opportunities")
        await asyncio.sleep(1.2)
        before = await measure(tab)
        inter = {"before": before}

        # 1) 关键词筛选（真实提交表单）
        try:
            await tab.evaluate(
                "(() => { const i=document.querySelector('input[name=q]'); i.value='notion'; "
                "document.querySelector('form.filters').submit(); return true; })()", await_promise=False)
            await asyncio.sleep(1.6)
            inter["after_keyword"] = await measure(tab)
        except Exception as exc:
            inter["keyword_error"] = f"{type(exc).__name__}: {exc}"

        # 2) 排序（点击表头链接 demand）
        try:
            await tab.get(BASE + "/opportunities")
            await asyncio.sleep(1.0)
            await tab.evaluate("(() => { const a=document.querySelector('th a[href*=\"sort=demand\"]'); "
                               "if(a){a.click(); return true;} return false; })()", await_promise=False)
            await asyncio.sleep(1.6)
            inter["after_sort_demand"] = await measure(tab)
            await tab.evaluate("(() => { const a=document.querySelector('th a.sorted[href*=\"sort=demand\"]'); "
                               "if(a){a.click(); return true;} return false; })()", await_promise=False)
            await asyncio.sleep(1.6)
            inter["after_sort_demand_toggle"] = await measure(tab)
        except Exception as exc:
            inter["sort_error"] = f"{type(exc).__name__}: {exc}"

        # 3) 清空条件
        try:
            await tab.get(BASE + "/opportunities?q=notion")
            await asyncio.sleep(1.0)
            before_clear = await measure(tab)
            await tab.evaluate("(() => { const a=Array.from(document.querySelectorAll('a')).find(x=>x.textContent.trim()==='清空条件'); "
                               "if(a){a.click(); return true;} return false; })()", await_promise=False)
            await asyncio.sleep(1.6)
            inter["before_clear"] = before_clear
            inter["after_clear"] = await measure(tab)
        except Exception as exc:
            inter["clear_error"] = f"{type(exc).__name__}: {exc}"

        # 4) 展开证据
        try:
            await tab.evaluate("(() => { const s=document.querySelector('tbody details summary'); "
                               "if(s){s.click(); return true;} return false; })()", await_promise=False)
            await asyncio.sleep(0.8)
            inter["after_expand"] = await measure(tab)
            shot = SHOTS / "desktop_opportunities_expanded.png"
            await tab.save_screenshot(str(shot))
            inter["expand_screenshot"] = str(shot)
        except Exception as exc:
            inter["expand_error"] = f"{type(exc).__name__}: {exc}"

        report["interactions"] = inter
    except Exception:
        report["fatal"] = traceback.format_exc()[-1200:]
    finally:
        try:
            browser.stop()
        except Exception:
            pass
        (UI / "interaction_evidence.json").write_bytes(json.dumps(report, ensure_ascii=False, indent=1).encode("utf-8"))
    print(json.dumps({"desktop": len(report["desktop"]), "mobile": len(report["mobile"]),
                      "console": len(report["console"]), "errors": len(report["errors"]),
                      "fatal": report.get("fatal", "")[:200]}, ensure_ascii=True))
    return 0 if not report.get("fatal") else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
