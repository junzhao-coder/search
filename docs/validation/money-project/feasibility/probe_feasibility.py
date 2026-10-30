"""闲鱼 / 小红书 只读采集可行性探针（执行者 C，计划 v6 B1）。

只读：仅导航与读取 DOM/内嵌 JSON；不点击关注/点赞/私信/购买；不导入 Cookie；不代登录。
频率：页面操作间隔 >= 8s；每平台 <= 3 次尝试；遇验证码/滑块立即停。
产物（均在任务 scope 内，因 Flow 写入守卫不允许写到 DSH_HOME\tools\browse-probe）：
  shots/ 截图、data/ JSONL、logs/probe.log（UTC+每步 exit）、pages/ HTML 存证、profile/ 独立 Chrome profile。
"""

from __future__ import annotations

import asyncio
import datetime as dt
import json
import os
import pathlib
import sys
import time
import traceback

BASE = pathlib.Path(__file__).resolve().parent
SHOTS = BASE / "shots"
DATA = BASE / "data"
LOGS = BASE / "logs"
PAGES = BASE / "pages"
PROFILE = BASE / "profile"
for p in (SHOTS, DATA, LOGS, PAGES, PROFILE):
    p.mkdir(parents=True, exist_ok=True)
LOG = LOGS / "probe.log"

CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
PROXY = "127.0.0.1:10808"
GAP = 8.0
MAX_ATTEMPTS = 3

TARGETS = {
    "xianyu": [
        ("home", "https://www.goofish.com/"),
        ("search", "https://www.goofish.com/search?q=%E5%91%A8%E4%BC%9A%E7%BA%AA%E8%A6%81"),
    ],
    "xiaohongshu": [
        ("search", "https://www.xiaohongshu.com/search_result?keyword=%E5%91%A8%E4%BC%9A%E7%BA%AA%E8%A6%81&source=web_search_result_notes"),
        ("explore", "https://www.xiaohongshu.com/explore"),
    ],
}

JS = r"""
(() => {
  const t = document.body ? document.body.innerText : "";
  const q = (s) => document.querySelectorAll(s).length;
  const pick = (s, n) => Array.from(document.querySelectorAll(s)).slice(0, n).map(e => ({
      text: (e.innerText || "").replace(/\s+/g, " ").trim().slice(0, 300),
      href: e.querySelector("a") ? e.querySelector("a").href : null
  }));
  const loginHints = ["登录", "扫码", "手机号", "验证码登录", "登录后", "请先登录", "立即登录"];
  const captchaHints = ["安全验证", "滑动", "验证码", "captcha", "人机验证", "异常访问"];
  return {
    url: location.href,
    title: document.title,
    body_len: t.length,
    body_head: t.slice(0, 600),
    login_hint: loginHints.filter(k => t.includes(k)),
    captcha_hint: captchaHints.filter(k => t.includes(k)),
    counts: {
      cards_goofish: q('[class*="feeds"] [class*="item"], [class*="feed-item"], [class*="cardWarp"]'),
      cards_xhs: q('section.note-item, .note-item, [class*="note-item"]'),
      links: q("a")
    },
    has_initial_state: typeof window.__INITIAL_STATE__ !== "undefined",
    has_next_data: typeof window.__NEXT_DATA__ !== "undefined",
    items: pick('section.note-item, .note-item, [class*="feed-item"], [class*="cardWarp"]', 20)
  };
})()
"""


def utc() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def log(line: str, exit_code: int | None = None) -> None:
    rec = {"utc": utc(), "cwd": os.getcwd(), "line": line}
    if exit_code is not None:
        rec["exit"] = exit_code
    with LOG.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
    print(f"[{rec['utc']}] {line}" + ("" if exit_code is None else f" exit={exit_code}"), flush=True)


async def main() -> int:
    log(f"probe start; chrome={CHROME}; proxy={PROXY}; profile={PROFILE}")
    try:
        import nodriver as uc
    except Exception:
        log("nodriver import failed: " + traceback.format_exc()[-300:], 2)
        return 2
    browser = None
    results = {"started_utc": utc(), "platforms": {}}
    try:
        browser = await uc.start(
            headless=False,
            browser_executable_path=CHROME,
            user_data_dir=str(PROFILE),
            browser_args=[
                f"--proxy-server=http://{PROXY}",
                "--lang=zh-CN",
                "--window-size=1440,900",
                "--disable-notifications",
                "--no-first-run",
                "--no-default-browser-check",
            ],
            sandbox=False,
        )
        log("browser started", 0)
        for platform, attempts in TARGETS.items():
            pres = {"attempts": [], "items": [], "blocked": None}
            for idx, (label, url) in enumerate(attempts[:MAX_ATTEMPTS]):
                if idx > 0:
                    await asyncio.sleep(GAP)
                stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
                step = {"platform": platform, "label": label, "url": url, "utc": utc()}
                try:
                    tab = await browser.get(url)
                    await asyncio.sleep(6.0)
                    raw = await tab.evaluate(JS, await_promise=False)
                    data = raw if isinstance(raw, dict) else (json.loads(raw) if isinstance(raw, str) else {})
                    step.update({
                        "final_url": data.get("url"), "title": data.get("title"),
                        "body_len": data.get("body_len"), "body_head": data.get("body_head"),
                        "login_hint": data.get("login_hint"), "captcha_hint": data.get("captcha_hint"),
                        "counts": data.get("counts"), "has_initial_state": data.get("has_initial_state"),
                        "has_next_data": data.get("has_next_data"),
                    })
                    items = data.get("items") or []
                    pres["items"].extend([{**it, "platform": platform, "source_url": data.get("url")} for it in items])
                    shot = SHOTS / f"{platform}_{label}_{stamp}.png"
                    try:
                        await tab.save_screenshot(str(shot))
                        step["screenshot"] = str(shot)
                    except Exception as exc:
                        step["screenshot_error"] = f"{type(exc).__name__}: {exc}"
                    try:
                        html = await tab.evaluate("document.documentElement.outerHTML", await_promise=False)
                        hp = PAGES / f"{platform}_{label}_{stamp}.html"
                        hp.write_bytes(str(html).encode("utf-8", "replace"))
                        step["html"] = str(hp)
                    except Exception as exc:
                        step["html_error"] = f"{type(exc).__name__}: {exc}"
                    if step.get("login_hint"):
                        pres["blocked"] = pres["blocked"] or "login_wall"
                    if step.get("captcha_hint"):
                        pres["blocked"] = "captcha"
                        step["stop_reason"] = "captcha"
                    step["exit"] = 0
                except Exception as exc:
                    step["exit"] = 1
                    step["error"] = f"{type(exc).__name__}: {exc}"
                    log(f"{platform}/{label} error: {step['error']}", 1)
                pres["attempts"].append(step)
                log(f"{platform}/{label} done exit={step.get('exit')} items={len(pres['items'])} "
                    f"login={step.get('login_hint')} captcha={step.get('captcha_hint')}", step.get("exit"))
                if step.get("stop_reason") == "captcha":
                    break
            results["platforms"][platform] = {"attempts": pres["attempts"], "item_count": len(pres["items"]),
                                              "blocked": pres["blocked"]}
            with (DATA / f"{platform}.jsonl").open("w", encoding="utf-8") as fh:
                for it in pres["items"]:
                    fh.write(json.dumps(it, ensure_ascii=False) + "\n")
        results["finished_utc"] = utc()
        (DATA / "probe_summary.json").write_bytes(json.dumps(results, ensure_ascii=False, indent=2).encode("utf-8"))
        log("probe finished", 0)
        return 0
    except Exception:
        log("probe fatal: " + traceback.format_exc()[-500:], 3)
        (DATA / "probe_summary.json").write_bytes(
            json.dumps({"fatal": traceback.format_exc()[-2000:], "started_utc": results.get("started_utc")},
                       ensure_ascii=False, indent=2).encode("utf-8"))
        return 3
    finally:
        try:
            if browser is not None:
                browser.stop()
        except Exception:
            pass


if __name__ == "__main__":
    t0 = time.time()
    rc = asyncio.run(main())
    log(f"probe exit rc={rc} elapsed={time.time()-t0:.1f}s", rc)
    sys.exit(rc)
