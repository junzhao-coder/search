"""闲鱼 / 小红书 一次性人工登录 + 登录后只读搜索验证（执行者 C，任务 task-9e51…）。

纪律：
- 登录只由**用户本人**在可见窗口完成；本脚本仅开窗、轮询检测（只记 cookie **名称**，不读值）、
  检测到登录或超时后关闭/继续；不代填账号密码、不索取验证码、不读输入框内容。
- 两平台**依次**进行（闲鱼 → 小红书），不同时开窗口。
- 登录后仅做**只读搜索**：滚动 1–2 屏、取 10–20 条、缺失字段写 null；页面操作间隔 ≥8s；单平台 ≤3 次尝试；遇验证码立即停。
- 不发布/点赞/关注/私信/下单；不改业务系统；不装依赖。

用法：
  python login_and_search.py --wait 300
产物：tools/platform-login/{logs,shots,pages,data}/
"""

from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import json
import os
import pathlib
import re
import sys
import time
import traceback

BASE = pathlib.Path(__file__).resolve().parent
SHOTS = BASE / "shots"
PAGES = BASE / "pages"
DATA = BASE / "data"
LOGS = BASE / "logs"
PROFILE = BASE / "profile"
for p in (SHOTS, PAGES, DATA, LOGS, PROFILE):
    p.mkdir(parents=True, exist_ok=True)
LOG = LOGS / "login_search.log"

CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
PROXY = "127.0.0.1:10808"

PLATFORMS = {
    "xianyu": {
        "home": "https://www.goofish.com/",
        "search": "https://www.goofish.com/search?q=AI%E6%A8%A1%E6%9D%BF",
        "login_cookie_names": ["unb"],
        "logged_in_hint": ["我的订单", "个人中心", "我发布的", "退出登录"],
        "item_href_re": r"/item\?id=\d+",
        "captcha_words": ["安全验证", "滑动", "人机验证", "异常访问"],
    },
    "xiaohongshu": {
        "home": "https://www.xiaohongshu.com/explore",
        "search": "https://www.xiaohongshu.com/search_result?keyword=AI%E6%A8%A1%E6%9D%BF",
        "login_cookie_names": ["web_session"],
        "logged_in_hint": ["我", "创作中心", "发布"],
        "item_href_re": r"/explore/[0-9a-f]{16,}",
        "captcha_words": ["安全验证", "滑动验证", "人机验证", "验证码"],
    },
}

EXTRACT_JS = r"""
(platform) => {
  const hrefRe = platform === 'xianyu' ? /\/item\?id=\d+/ : /\/explore\/[0-9a-f]{16,}/;
  const seen = new Set(); const out = [];
  document.querySelectorAll('a[href]').forEach(a => {
    if (!hrefRe.test(a.getAttribute('href') || '')) return;
    const href = a.href;
    if (seen.has(href)) return;
    seen.add(href);
    let box = a.closest('[class*="card"], [class*="item"], section, li, div') || a;
    const txt = (box.innerText || a.innerText || '').replace(/\s+/g, ' ').trim();
    const price = (txt.match(/[¥￥]\s*\d+(\.\d+)?/) || [null])[0];
    out.push({ href, title: txt.slice(0, 120) || null, price: price, raw_text: txt.slice(0, 200) || null });
    if (out.length >= 40) return;
  });
  return JSON.stringify({ url: location.href, title: document.title, count: out.length,
                          body_head: (document.body ? document.body.innerText : '').slice(0, 300), items: out });
}
"""


def utc() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def log(msg: str, exit_code: int | None = None, **extra) -> None:
    rec = {"utc": utc(), "cwd": os.getcwd(), "msg": msg}
    if exit_code is not None:
        rec["exit"] = exit_code
    rec.update(extra)
    with LOG.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
    print(f"[{rec['utc']}] {msg}" + ("" if exit_code is None else f" exit={exit_code}"), flush=True)


async def cookie_names(tab) -> list[str]:
    """优先用 CDP 读取全部 cookie 名称（含 HttpOnly，如小红书 web_session）；只取名称不取值。"""
    try:
        import nodriver.cdp.network as net
        cookies = await tab.send(net.get_cookies())
        names = sorted({c.name for c in cookies if getattr(c, "name", None)})
        if names:
            return names
    except Exception:
        pass
    try:
        raw = await tab.evaluate("document.cookie", await_promise=False)
        names = []
        for part in str(raw or "").split(";"):
            if "=" in part:
                names.append(part.split("=", 1)[0].strip())
        return sorted(set(n for n in names if n))
    except Exception:
        return []


async def wait_for_login(tab, platform: str, wait_s: int) -> dict:
    cfg = PLATFORMS[platform]
    t0 = time.time()
    polls = 0
    confirm = 0
    last = {"cookie_names": [], "hit_cookies": [], "hint_hits": []}
    while time.time() - t0 < wait_s:
        polls += 1
        names = await cookie_names(tab)
        hits = [n for n in names if n in cfg["login_cookie_names"]]
        try:
            body = await tab.evaluate("(document.body?document.body.innerText:'').slice(0,4000)", await_promise=False)
        except Exception:
            body = ""
        hint_hits = [h for h in cfg["logged_in_hint"] if h in str(body)]
        last = {"cookie_names": names[:40], "hit_cookies": hits, "hint_hits": hint_hits}
        # 仅以"登录态专属 cookie 名"判定（unb / web_session），并要求连续 2 次确认，避免瞬时误判
        confirm = confirm + 1 if hits else 0
        if confirm >= 2:
            log(f"{platform} LOGIN CONFIRMED", 0, polls=polls, waited_s=round(time.time() - t0, 1), **last)
            return {"detected": True, "waited_s": round(time.time() - t0, 1), "polls": polls, **last}
        if last["cookie_names"]:
            log(f"{platform} waiting… polls={polls} hit_cookies={hits} hint_hits={hint_hits} "
                f"cookies={len(last['cookie_names'])}")
        await asyncio.sleep(3.0)
    log(f"{platform} LOGIN TIMEOUT", 1, polls=polls, waited_s=round(time.time() - t0, 1), **last)
    return {"detected": False, "waited_s": round(time.time() - t0, 1), "polls": polls, **last}


async def search_and_collect(tab, platform: str) -> dict:
    cfg = PLATFORMS[platform]
    stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    res = {"platform": platform, "url": cfg["search"], "utc": utc(), "attempts": []}
    for attempt in range(1, 4):
        res["attempts"].append({"attempt": attempt, "utc": utc()})
        try:
            await tab.get(cfg["search"])
            await asyncio.sleep(8.0)
            for i in range(2):
                await tab.evaluate("window.scrollBy(0, 900)", await_promise=False)
                await asyncio.sleep(8.0)
            raw = await tab.evaluate("(" + EXTRACT_JS + ")(\"" + platform + "\")", await_promise=False)
            data = json.loads(raw) if isinstance(raw, str) else (raw or {})
            body = str(data.get("body_head", ""))
            captcha = [w for w in cfg["captcha_words"] if w in body]
            items = data.get("items") or []
            shot = SHOTS / f"{platform}_search_{stamp}.png"
            try:
                await tab.save_screenshot(str(shot))
            except Exception as exc:
                res["screenshot_error"] = f"{type(exc).__name__}: {exc}"
            html = await tab.evaluate("document.documentElement.outerHTML", await_promise=False)
            hp = PAGES / f"{platform}_search_{stamp}.html"
            hp.write_bytes(str(html).encode("utf-8", "replace"))
            res["attempts"][-1].update({"detected_items": len(items), "captcha_words": captcha,
                                        "final_url": data.get("url"), "title": data.get("title"),
                                        "screenshot": str(shot), "html": str(hp), "exit": 0})
            res["items"] = items[:20]
            res["captcha"] = captcha
            log(f"{platform} search done attempt={attempt} items={len(items)} captcha={captcha}", 0)
            if captcha:
                res["stopped"] = "captcha"
                break
            if items:
                res["stopped"] = "ok"
                break
        except Exception as exc:
            res["attempts"][-1].update({"exit": 1, "error": f"{type(exc).__name__}: {exc}"})
            log(f"{platform} search attempt {attempt} error: {exc}", 1)
        await asyncio.sleep(8.0)
    with (DATA / f"{platform}_items.jsonl").open("w", encoding="utf-8") as fh:
        for it in res.get("items", []):
            fh.write(json.dumps({**it, "platform": platform}, ensure_ascii=False) + "\n")
    return res


async def main(wait_s: int, platforms: list[str], profile_name: str) -> int:
    global PROFILE
    PROFILE = BASE / profile_name
    PROFILE.mkdir(parents=True, exist_ok=True)
    log(f"start; wait={wait_s}s; platforms={platforms}; profile={PROFILE}")
    try:
        import nodriver as uc
    except Exception:
        log("nodriver import failed: " + traceback.format_exc()[-300:], 2)
        return 2
    browser = None
    summary = {"started_utc": utc(), "platforms": {}}
    try:
        browser = await uc.start(
            headless=False,
            browser_executable_path=CHROME,
            user_data_dir=str(PROFILE),
            browser_args=[f"--proxy-server=http://{PROXY}", "--lang=zh-CN", "--window-size=1440,900",
                          "--disable-notifications", "--no-first-run", "--no-default-browser-check"],
            sandbox=False,
        )
        log("browser started", 0)
        for platform in platforms:
            cfg = PLATFORMS[platform]
            log(f">>> ACTION REQUIRED: 请在 Chrome 窗口完成【{platform}】登录（扫码或手机号，本人操作）。"
                f"检测中，最长等待 {wait_s}s…")
            tab = await browser.get(cfg["home"])
            await asyncio.sleep(4.0)
            login = await wait_for_login(tab, platform, wait_s)
            entry = {"login": login}
            if login["detected"]:
                entry["search"] = await search_and_collect(tab, platform)
            else:
                entry["search"] = {"skipped": "login_timeout"}
            summary["platforms"][platform] = entry
            (DATA / "login_search_summary.json").write_bytes(
                json.dumps(summary, ensure_ascii=False, indent=2).encode("utf-8"))
            if platform == "xianyu":
                log("切换到小红书：保持同一浏览器，稍等…")
                await asyncio.sleep(3.0)
        summary["finished_utc"] = utc()
        (DATA / "login_search_summary.json").write_bytes(
            json.dumps(summary, ensure_ascii=False, indent=2).encode("utf-8"))
        log("done", 0)
        return 0
    except Exception:
        log("fatal: " + traceback.format_exc()[-600:], 3)
        return 3
    finally:
        try:
            if browser is not None:
                browser.stop()
        except Exception:
            pass


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--wait", type=int, default=300)
    ap.add_argument("--platforms", default="xianyu,xiaohongshu")
    ap.add_argument("--profile", default="profile")
    args = ap.parse_args()
    rc = asyncio.run(main(args.wait, [p.strip() for p in args.platforms.split(",") if p.strip()], args.profile))
    log(f"exit rc={rc}", rc)
    sys.exit(rc)
