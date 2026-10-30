"""Read-only probe of the Xianyu publish page using the authorized profile.

Never fills the form, uploads, submits, logs in, or reads cookie values.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import json
import os
import pathlib
import re
import socket
import sys
import traceback

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:  # pragma: no cover
    pass

BASE = pathlib.Path(__file__).resolve().parents[1]
RAW = BASE / "raw"
SHOTS = BASE / "shots"
LOGS = BASE / "logs"
for directory in (RAW, SHOTS, LOGS):
    directory.mkdir(parents=True, exist_ok=True)

PROFILE = pathlib.Path(r"D:\桌面\two\tools\platform-login\profile")
CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
PROXY = "127.0.0.1:10808"
HOME = "https://www.goofish.com/"
PUBLISH = os.environ.get("B9_TARGET", "https://www.goofish.com/publish")
PREFIX = os.environ.get("B9_PREFIX", "")
LOG = LOGS / "probe_publish.log"

LOGIN_COOKIE = "unb"
RISK_WORDS = ("安全验证", "滑动", "滑块", "人机验证", "验证码", "异常访问", "登录后", "扫码登录")
CATEGORY_TOKENS = ("选择类目", "选择分类", "类目", "分类", "其他", "文档", "电子", "虚拟", "资料", "办公")
EXCLUDE_TOKENS = ("发布", "提交", "保存", "确认", "立即", "购买", "付款", "私信")


def utc() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def log(message: str, **extra) -> None:
    record = {"utc": utc(), "cwd": str(pathlib.Path.cwd()), "msg": message}
    record.update(extra)
    with LOG.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")
    print(f"[{record['utc']}] {message}", flush=True)


def plain(value):
    if isinstance(value, dict) and "value" in value:
        return plain(value["value"])
    return value


def sanitize_html(text: str) -> str:
    text = re.sub(r"<script\b.*?</script>", " ", text or "", flags=re.S | re.I)
    text = re.sub(r"<style\b.*?</style>", " ", text, flags=re.S | re.I)
    text = re.sub(r"<noscript\b.*?</noscript>", " ", text, flags=re.S | re.I)
    text = re.sub(r'(<input\b[^>]*\bvalue=")[^"]*(")', r"\1[redacted]\2", text, flags=re.I)
    text = re.sub(r'(?i)(token|csrf|session|cookie|unb|_m_h5_tk|tfstk|sgcookie|siv20)([^=<>"\s]*)=([^&"\s<>]+)', r"\1\2=[redacted]", text)
    return text[:250000]


async def cookie_names(tab) -> list[str]:
    names: list[str] = []
    try:
        import nodriver.cdp.network as net
        cookies = await tab.send(net.get_cookies())
        names = sorted({str(c.name) for c in cookies if getattr(c, "name", None)})
    except Exception:
        try:
            raw = plain(await tab.evaluate("document.cookie"))
            names = sorted({part.split("=", 1)[0].strip() for part in str(raw or "").split(";") if "=" in part})
        except Exception:
            names = []
    return names


async def snapshot(tab, name: str, *, save_html: bool = True) -> dict:
    url = plain(await tab.evaluate("location.href"))
    title = plain(await tab.evaluate("document.title"))
    body = plain(await tab.evaluate("document.body ? document.body.innerText : ''"))
    body = str(body or "")
    html = ""
    if save_html:
        try:
            html = str(plain(await tab.evaluate("document.body ? document.body.innerHTML : ''")) or "")
        except Exception:
            html = ""
    (RAW / f"{name}.txt").write_bytes(body.encode("utf-8"))
    if save_html:
        (RAW / f"{name}.html").write_bytes(sanitize_html(html).encode("utf-8"))
    try:
        await tab.save_screenshot(str(SHOTS / f"{name}.png"))
        shot = f"shots/{name}.png"
    except Exception as exc:  # noqa: BLE001
        shot = None
        log(f"{name} screenshot_error={type(exc).__name__}")
    info = {"url": str(url or ""), "title": str(title or ""), "body_len": len(body),
            "body_head": body[:8000], "screenshot": shot, "html": f"raw/{name}.html"}
    (RAW / f"{name}.json").write_bytes(json.dumps(info, ensure_ascii=False, indent=2).encode("utf-8"))
    return info


async def click_candidate(tab, tokens: tuple[str, ...]) -> dict | None:
    token_json = json.dumps(list(tokens), ensure_ascii=False)
    exclude_json = json.dumps(list(EXCLUDE_TOKENS), ensure_ascii=False)
    script = r"""
    (() => {
      const tokens = %s;
      const excludes = %s;
      const nodes = [...document.querySelectorAll('button,a,div,span,li,[role="button"],select,input')];
      for (const el of nodes) {
        const text = ((el.innerText || '') + ' ' + (el.getAttribute('aria-label') || '') + ' ' + (el.getAttribute('placeholder') || '')).trim();
        if (!text || text.length > 200) continue;
        if (excludes.some(x => text.includes(x))) continue;
        if (!tokens.some(x => text.includes(x))) continue;
        const style = window.getComputedStyle(el);
        if (style.display === 'none' || style.visibility === 'hidden' || el.offsetParent === null) continue;
        el.click();
        return {clicked: true, tag: el.tagName, text: text.slice(0, 200)};
      }
      return {clicked: false};
    })()
    """ % (token_json, exclude_json)
    value = plain(await tab.evaluate(script))
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            return json.loads(value)
        except Exception:
            return {"clicked": False, "raw": value[:200]}
    return {"clicked": False}


async def collect_candidates(tab) -> list[dict]:
    token_json = json.dumps(list(CATEGORY_TOKENS), ensure_ascii=False)
    script = r"""
    (() => {
      const tokens = %s;
      const out = []; const seen = new Set();
      for (const el of document.querySelectorAll('button,a,div,span,li,[role="button"],select')) {
        const text = ((el.innerText || '') + ' ' + (el.getAttribute('aria-label') || '')).replace(/\s+/g, ' ').trim();
        if (!text || text.length > 220) continue;
        if (!tokens.some(x => text.includes(x))) continue;
        const key = el.tagName + '|' + text;
        if (seen.has(key)) continue;
        seen.add(key);
        out.push({tag: el.tagName, text: text.slice(0, 220),
                  href: el.getAttribute('href') || null,
                  role: el.getAttribute('role') || null});
        if (out.length >= 120) break;
      }
      return JSON.stringify(out);
    })()
    """ % token_json
    value = plain(await tab.evaluate(script))
    try:
        return json.loads(value) if isinstance(value, str) else (value or [])
    except Exception:
        return []


async def main() -> int:
    try:
        import nodriver as uc
    except Exception:
        log("nodriver import failed", exit=2)
        return 2
    browser = None
    result = {"started_utc": utc(), "steps": [], "profile": str(PROFILE)}
    try:
        try:
            with socket.create_connection(("127.0.0.1", 10808), timeout=0.8):
                proxy_ok = True
        except OSError:
            proxy_ok = False
        result["proxy_available"] = proxy_ok
        browser_args = ["--lang=zh-CN", "--window-size=1440,900", "--disable-notifications",
                        "--no-first-run", "--no-default-browser-check"]
        if proxy_ok:
            browser_args.insert(0, f"--proxy-server=http://{PROXY}")
        browser = await uc.start(
            headless=False,
            browser_executable_path=CHROME,
            user_data_dir=str(PROFILE),
            browser_args=browser_args,
            sandbox=False,
        )
        log("browser started", exit=0, proxy=proxy_ok)
        tab = await browser.get(HOME)
        await asyncio.sleep(6)
        home = await snapshot(tab, PREFIX + "01_home")
        names = await cookie_names(tab)
        login = {"has_unb_name": LOGIN_COOKIE in names, "cookie_names": names,
                 "cookie_count": len(names), "home_url": home["url"],
                 "home_title": home["title"], "home_head": home["body_head"][:1000]}
        result["login"] = login
        if not login["has_unb_name"]:
            result["stopped"] = "not_logged_in"
            log("STOP not logged in (unb name absent)", exit=2, cookie_count=len(names))
            (RAW / (PREFIX + "probe_result.json")).write_bytes(json.dumps(result, ensure_ascii=False, indent=2).encode("utf-8"))
            return 2
        risk_home = [w for w in RISK_WORDS if w in home["body_head"]]
        result["home_risk_words"] = risk_home
        result["home_has_login_button"] = any(
            line.strip() == "登录" for line in home["body_head"].splitlines())
        log("home probed; continuing to publish entry for explicit check",
            exit=0, has_login_button=result["home_has_login_button"], risk=risk_home)

        log("navigating publish", url=PUBLISH)
        tab = await browser.get(PUBLISH)
        await asyncio.sleep(8)
        publish = await snapshot(tab, PREFIX + "02_publish")
        result["publish"] = publish
        risk = [w for w in RISK_WORDS if w in publish["body_head"]]
        result["publish_risk_words"] = risk
        candidates = await collect_candidates(tab)
        result["publish_candidates"] = candidates
        (RAW / (PREFIX + "02_publish_candidates.json")).write_bytes(
            json.dumps(candidates, ensure_ascii=False, indent=2).encode("utf-8"))
        login_page = ("login" in publish["url"].lower()
                      or "扫码登录" in publish["body_head"]
                      or "请登录" in publish["body_head"]
                      or "立即登录" in publish["body_head"]
                      or "登录后可以" in publish["body_head"]
                      or "安全验证" in publish["body_head"]
                      or "滑块" in publish["body_head"]
                      or "人机验证" in publish["body_head"])
        result["publish_is_login_or_verification"] = login_page
        if login_page:
            result["stopped"] = "publish_login_or_verification"
            log("STOP publish login/verification", exit=2, url=publish["url"], risk=risk)
            (RAW / (PREFIX + "probe_result.json")).write_bytes(json.dumps(result, ensure_ascii=False, indent=2).encode("utf-8"))
            return 2

        clicked = await click_candidate(tab, ("选择类目", "选择分类", "类目", "分类"))
        result["category_click"] = clicked
        await asyncio.sleep(3)
        cat = await snapshot(tab, PREFIX + "03_category")
        result["category"] = cat
        cat_candidates = await collect_candidates(tab)
        result["category_candidates"] = cat_candidates
        (RAW / (PREFIX + "03_category_candidates.json")).write_bytes(
            json.dumps(cat_candidates, ensure_ascii=False, indent=2).encode("utf-8"))

        # Open a category branch only if a safe (non-publish) "其他/更多" item exists.
        second = await click_candidate(tab, ("其他", "更多", "电子", "文档", "虚拟", "资料"))
        result["category_branch_click"] = second
        await asyncio.sleep(3)
        req = await snapshot(tab, PREFIX + "04_requirement")
        result["requirement"] = req
        req_candidates = await collect_candidates(tab)
        result["requirement_candidates"] = req_candidates
        (RAW / (PREFIX + "04_requirement_candidates.json")).write_bytes(
            json.dumps(req_candidates, ensure_ascii=False, indent=2).encode("utf-8"))
        result["finished_utc"] = utc()
        result["ok"] = True
        (RAW / (PREFIX + "probe_result.json")).write_bytes(json.dumps(result, ensure_ascii=False, indent=2).encode("utf-8"))
        log("probe finished", exit=0)
        return 0
    except Exception as exc:  # noqa: BLE001
        result["error"] = f"{type(exc).__name__}: {exc}"
        result["traceback_tail"] = traceback.format_exc()[-2000:]
        result["finished_utc"] = utc()
        (RAW / (PREFIX + "probe_result.json")).write_bytes(json.dumps(result, ensure_ascii=False, indent=2).encode("utf-8"))
        log("probe fatal", exit=3, error=result["error"])
        return 3
    finally:
        if browser is not None:
            try:
                browser.stop()
            except Exception:
                pass


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
