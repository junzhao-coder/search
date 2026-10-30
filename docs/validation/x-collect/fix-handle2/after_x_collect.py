#!/usr/bin/env python
"""x-collect minimal CLI: doctor (session check) + login (visible one-shot helper).

Read-only with respect to X: never posts/likes/follows/messages, never reads or logs
cookies/tokens/passwords. Uses nodriver with the dedicated profile only.
"""

from __future__ import annotations

import argparse
import asyncio
import datetime
import json
import os
import pathlib
import random
import sys
import time
from urllib.parse import quote, urlparse

import nodriver as uc

ROOT = pathlib.Path(__file__).resolve().parents[1]
PROFILE = ROOT / "profile"
LOGS = ROOT / "logs"
DATA = ROOT / "data"
ERRORS = DATA / "errors"
SEEN = DATA / "seen.jsonl"
CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
HOME_URL = "https://x.com/home"
LOGIN_URL = "https://x.com/login"
NOT_IMPLEMENTED = 4
SESSION_EXPIRED = 2
ERROR = 3
PARSE_EMPTY = 4
MAX_LIMIT = 60
MAX_SECONDS = 900

HANDLE_JS = r"""
(() => {
  const b = document.querySelector('[data-testid="SideNav_AccountSwitcher_Button"]');
  if (b) {
    const t = (b.innerText || '') + ' ' + (b.getAttribute('aria-label') || '');
    const m = t.match(/@([A-Za-z0-9_]{1,20})/);
    if (m) return m[1];
  }
  return null;
})()
"""

SETTINGS_URL = "https://x.com/settings/account"
SETTINGS_HANDLE_JS = r"""
(() => {
  const input = document.querySelector('input[name="username"]');
  if (input && input.value) return input.value.replace(/^@/, '');
  return null;
})()
"""

CLICK_SWITCHER_JS = r"""
(() => {
  const b = document.querySelector('[data-testid="SideNav_AccountSwitcher_Button"]');
  if (!b) return false;
  b.click();
  return true;
})()
"""

MENU_HANDLE_JS = r"""
(() => {
  const logout = document.querySelector('[data-testid="AccountSwitcher_Logout_Button"]');
  if (logout) {
    const t = (logout.innerText || '') + ' ' + (logout.getAttribute('aria-label') || '');
    const m = t.match(/@([A-Za-z0-9_]{1,20})/);
    if (m) return m[1];
  }
  const menu = document.querySelector('[role="menu"]');
  if (menu) {
    const m = (menu.innerText || '').match(/@([A-Za-z0-9_]{1,20})/);
    if (m) return m[1];
  }
  return null;
})()
"""

EXPIRED_JS = r"""
(() => {
  const text = document.body ? document.body.innerText : '';
  return text.includes('Sign in to X') || text.includes('登录 X') ||
         text.includes('Sign in') || text.includes('Log in');
})()
"""

EXTRACT_JS = r"""
(() => {
  const num = (s) => {
    if (!s) return null;
    const t = String(s).replace(/,/g, '').trim();
    const m = t.match(/([\d.]+)\s*([KMB万亿]?)/i);
    if (!m) return null;
    const n = parseFloat(m[1]);
    const u = (m[2] || '').toLowerCase();
    const mult = u === 'k' ? 1e3 : u === 'm' ? 1e6 : u === 'b' ? 1e9 : u === '万' ? 1e4 : u === '亿' ? 1e8 : 1;
    return Math.round(n * mult);
  };
  const out = [];
  for (const a of document.querySelectorAll('article[data-testid="tweet"]')) {
    const link = a.querySelector('a[href*="/status/"]');
    if (!link) continue;
    const href = link.getAttribute('href') || '';
    const m = href.match(/^\/([A-Za-z0-9_]{1,20})\/status\/(\d+)/);
    if (!m) continue;
    const handle = m[1], id = m[2];
    const textEl = a.querySelector('[data-testid="tweetText"]');
    const text = textEl ? (textEl.innerText || '') : '';
    const timeEl = a.querySelector('time');
    const created_at = timeEl ? timeEl.getAttribute('datetime') : null;
    let author_name = null;
    const un = a.querySelector('[data-testid="User-Name"]');
    if (un) {
      const nameEl = un.querySelector('div[dir="ltr"] span') || un.querySelector('span');
      author_name = nameEl ? (nameEl.innerText || null) : null;
    }
    let replies = null, retweets = null, likes = null, views = null;
    const rt = a.querySelector('[data-testid="reply"]');
    if (rt) replies = num(rt.getAttribute('aria-label') || rt.innerText);
    const rw = a.querySelector('[data-testid="retweet"]');
    if (rw) retweets = num(rw.getAttribute('aria-label') || rw.innerText);
    const lk = a.querySelector('[data-testid="like"]');
    if (lk) likes = num(lk.getAttribute('aria-label') || lk.innerText);
    const va = a.querySelector('[aria-label*="views" i], [aria-label*="查看" i]');
    if (va) views = num(va.getAttribute('aria-label'));
    const media = [];
    for (const el of a.querySelectorAll('[data-testid="tweetPhoto"] img, video')) {
      const src = el.currentSrc || el.src;
      if (src) media.push(src);
    }
    const lang = a.getAttribute('lang') || (textEl ? textEl.getAttribute('lang') : null);
    out.push({tweet_id: id, author_handle: handle, text: text, author_name: author_name,
              created_at: created_at, lang: lang, replies: replies, retweets: retweets,
              likes: likes, views: views, media_urls: media,
              url: 'https://x.com/' + handle + '/status/' + id});
  }
  return out;
})()
"""

RISK_JS = r"""
(() => {
  const t = document.body ? document.body.innerText : '';
  return /Something went wrong|Rate limit|rate limit|Verify you are human|captcha|Challenge|尝试过多|出错了/i.test(t);
})()
"""

BODY_JS = "(() => document.body ? document.body.innerText.slice(0, 2000) : '')()"


def _decode_cdp(value):
    """Decode nodriver/CDP RemoteObject-shaped values into plain Python."""
    if isinstance(value, list):
        return [_decode_cdp(v) for v in value]
    if isinstance(value, dict):
        if "type" in value:
            kind = value.get("type")
            if kind in ("null", "undefined"):
                return None
            if "value" not in value:
                return None
            raw = value.get("value")
            if kind == "object" and isinstance(raw, list):
                return {k: _decode_cdp(v) for k, v in raw}
            if kind == "array" and isinstance(raw, list):
                return [_decode_cdp(v) for v in raw]
            return _decode_cdp(raw)
        return {k: _decode_cdp(v) for k, v in value.items()}
    return value




def utc() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def system_proxy() -> str | None:
    """Read the per-user WinINET proxy (process-level use only; never written back)."""
    try:
        import winreg

        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Internet Settings",
        ) as key:
            enabled, _ = winreg.QueryValueEx(key, "ProxyEnable")
            server, _ = winreg.QueryValueEx(key, "ProxyServer")
        if enabled and server:
            server = server.split(";")[0].strip()
            if "=" in server:
                server = server.split("=", 1)[1]
            return server
    except Exception:  # noqa: BLE001
        return None
    return None


class RunLog:
    def __init__(self, command: str):
        LOGS.mkdir(parents=True, exist_ok=True)
        self.path = LOGS / f"{command}-{utc().replace(':', '')}.log"
        self.lines: list[str] = []

    def write(self, message: str) -> None:
        line = f"{utc()} {message}"
        self.lines.append(line)
        print(line, flush=True)

    def close(self, exit_code: int) -> None:
        self.lines.append(f"{utc()} EXIT={exit_code}")
        self.path.write_text("\n".join(self.lines) + "\n", encoding="utf-8", newline="\n")
        print(f"LOG={self.path} EXIT={exit_code}", flush=True)


async def _graceful_close(browser, log: RunLog) -> None:
    """Ask Chrome to close via CDP so cookies/profile are flushed before process exit."""
    try:
        import nodriver.cdp as cdp

        await browser.send(cdp.browser.close())
        log.write("BROWSER_CLOSE_SENT")
        await asyncio.sleep(6)
    except Exception as exc:  # noqa: BLE001
        log.write(f"BROWSER_CLOSE_ERROR={type(exc).__name__}")
    try:
        browser.stop()
    except Exception as exc:  # noqa: BLE001
        log.write(f"BROWSER_STOP_ERROR={type(exc).__name__}")


async def _start(headless: bool, log: RunLog):
    args = ["--disable-blink-features=AutomationControlled"]
    proxy = system_proxy()
    if proxy:
        args.append(f"--proxy-server=http://{proxy}")
        log.write(f"PROXY=system process-level ({proxy})")
    else:
        log.write("PROXY=none (direct)")
    return await uc.start(
        user_data_dir=str(PROFILE),
        browser_executable_path=CHROME,
        headless=headless,
        browser_args=args,
        no_sandbox=True,
    )


async def _snapshot(tab, log: RunLog, stage: str):
    href = await tab.evaluate("location.href")
    title = await tab.evaluate("document.title")
    bodylen = await tab.evaluate("document.body ? document.body.innerText.length : -1")
    content = await tab.get_content()
    log.write(f"{stage} href={href} title={title!r} bodylen={bodylen} html_len={len(content)}")
    return str(href or ""), str(title or ""), str(content or "")


async def _handle(tab, *, settings_fallback: bool = False, log: RunLog | None = None) -> str | None:
    value = _decode_cdp(await tab.evaluate(HANDLE_JS))
    if isinstance(value, str) and value:
        return value
    try:
        clicked = _decode_cdp(await tab.evaluate(CLICK_SWITCHER_JS))
        if log and clicked:
            log.write("HANDLE_SWITCHER_CLICKED")
        await asyncio.sleep(2)
        value = _decode_cdp(await tab.evaluate(MENU_HANDLE_JS))
        if isinstance(value, str) and value:
            return value
        try:
            await tab.evaluate("(() => { document.body.click(); return true; })()")
        except Exception:  # noqa: BLE001
            pass
    except Exception as exc:  # noqa: BLE001
        if log:
            log.write(f"HANDLE_MENU_ERROR={type(exc).__name__}")
    if not settings_fallback:
        return None
    try:
        await tab.get(SETTINGS_URL)
    except Exception as exc:  # noqa: BLE001
        if log:
            log.write(f"SETTINGS_NAV_ERROR={type(exc).__name__}")
        return None
    for _ in range(6):
        await asyncio.sleep(2)
        try:
            value = _decode_cdp(await tab.evaluate(SETTINGS_HANDLE_JS))
        except Exception as exc:  # noqa: BLE001
            if log:
                log.write(f"SETTINGS_EVAL_ERROR={type(exc).__name__}")
            value = None
        if isinstance(value, str) and value:
            return value.lstrip("@")
    if log:
        log.write("SETTINGS_HANDLE_UNKNOWN")
    return None


def _expired(href: str, title: str, html: str, body_text_flag: bool | None = None) -> bool:
    low = href.lower()
    if "/login" in low or "/i/flow/login" in low or "jf/onboarding" in low or "mode=login" in low:
        return True
    if body_text_flag:
        return True
    return False


async def _doctor_once(headed: bool, log: RunLog) -> int:
    log.write(f"START doctor headed={headed} profile={PROFILE}")
    browser = await _start(headless=not headed, log=log)
    try:
        tab = await browser.get(HOME_URL)
        href = ""
        title = ""
        html = ""
        for _ in range(6):
            await asyncio.sleep(3)
            try:
                href, title, html = await _snapshot(tab, log, "DOCTOR")
            except Exception as exc:  # noqa: BLE001
                log.write(f"SNAPSHOT_ERROR={type(exc).__name__}")
                continue
            if html and len(html) > 1000:
                break
        flag = None
        try:
            flag = await tab.evaluate(EXPIRED_JS)
        except Exception:  # noqa: BLE001
            pass
        if _expired(href, title, html, bool(flag)):
            log.write("SESSION_EXPIRED (redirected to login)")
            return SESSION_EXPIRED
        handle = None
        for _ in range(3):
            try:
                handle = await _handle(tab, settings_fallback=True, log=log)
            except Exception as exc:  # noqa: BLE001
                log.write(f"HANDLE_EVAL_ERROR={type(exc).__name__}")
            if handle:
                break
            await asyncio.sleep(2)
        if not handle:
            log.write("HANDLE_UNKNOWN (account switcher and settings/account both unavailable)")
            return 0
        log.write(f"LOGGED_IN handle=@{handle} utc={utc()}")
        return 0
    finally:
        try:
            browser.stop()
        except Exception as exc:  # noqa: BLE001
            log.write(f"BROWSER_STOP_ERROR={type(exc).__name__}")


def _cookie_auth() -> dict:
    """Read cookie metadata only (names/counts), never values."""
    import sqlite3

    path = PROFILE / "Default" / "Network" / "Cookies"
    info = {"path": str(path), "exists": path.exists(), "auth_token": False, "ct0": False,
            "x_rows": 0}
    if not path.exists():
        return info
    try:
        conn = sqlite3.connect(f"file:{path.as_posix()}?mode=ro&immutable=1", uri=True)
        try:
            rows = conn.execute(
                "SELECT name FROM cookies WHERE host_key LIKE '%x.com%'").fetchall()
            names = {r[0] for r in rows}
            info["x_rows"] = len(rows)
            info["auth_token"] = "auth_token" in names
            info["ct0"] = "ct0" in names
        finally:
            conn.close()
    except Exception as exc:  # noqa: BLE001
        info["error"] = repr(exc)
    return info


async def doctor_async(headed: bool, log: RunLog) -> int:
    meta = _cookie_auth()
    log.write(f"COOKIE_CHECK exists={meta['exists']} x_rows={meta['x_rows']} "
              f"auth_token={meta['auth_token']} ct0={meta['ct0']}")
    if not (meta["auth_token"] and meta["ct0"]):
        log.write("SESSION_EXPIRED (no auth cookies in profile; browser not launched)")
        return SESSION_EXPIRED
    code = await _doctor_once(headed, log)
    if code == ERROR and not headed:
        log.write("HEADLESS_BLOCKED_OR_UNKNOWN -> retry headed once")
        code = await _doctor_once(True, log)
    return code


async def login_async(timeout: int, log: RunLog) -> int:
    log.write(f"START login profile={PROFILE} timeout={timeout}s")
    browser = await _start(headless=False, log=log)
    ok = False
    try:
        tab = await browser.get(LOGIN_URL)
        log.write("WAITING_FOR_USER_LOGIN 窗口已打开，请用户本人登录小号（执行者不读取输入）")
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            await asyncio.sleep(3)
            try:
                href = str(await tab.evaluate("location.href") or "")
            except Exception:  # noqa: BLE001
                href = ""
            path = urlparse(href).path
            meta = _cookie_auth()
            if meta["auth_token"] and meta["ct0"]:
                log.write(f"LOGIN_DETECTED auth cookies present url={href} x_rows={meta['x_rows']}")
                ok = True
                break
            if path == "/home" or path.startswith("/home/"):
                log.write(f"HOME_WITHOUT_AUTH_COOKIES url={href} x_rows={meta['x_rows']} (仍等待)")
            try:
                handle = await _handle(tab)
            except Exception:  # noqa: BLE001
                handle = None
            if handle:
                log.write(f"LOGIN_DETECTED_DOM handle=@{handle} url={href}")
                ok = True
                break
        if not ok:
            log.write("LOGIN_TIMEOUT (未检测到 /home；窗口已关闭，可重跑 login)")
            return ERROR
        log.write("WAIT_FOR_COOKIE_FLUSH 8s")
        await asyncio.sleep(8)
    finally:
        await _graceful_close(browser, log)
    if not ok:
        return ERROR
    await asyncio.sleep(2)
    meta = _cookie_auth()
    log.write(f"POST_CLOSE_COOKIE_CHECK x_rows={meta['x_rows']} "
              f"auth_token={meta['auth_token']} ct0={meta['ct0']}")
    if not (meta["auth_token"] and meta["ct0"]):
        log.write("AUTH_COOKIE_MISSING after graceful close")
        return SESSION_EXPIRED
    return await doctor_async(headed=False, log=log)


def _load_seen() -> set[str]:
    ids: set[str] = set()
    if not SEEN.exists():
        return ids
    for line in SEEN.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
            tid = str(row.get("tweet_id") or "")
            if tid:
                ids.add(tid)
        except Exception:  # noqa: BLE001
            continue
    return ids


def _append_jsonl(path: pathlib.Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def _save_error(kind: str, url: str, title: str, body: str, log: RunLog) -> str:
    ERRORS.mkdir(parents=True, exist_ok=True)
    path = ERRORS / f"{kind}-{utc().replace(':', '')}.txt"
    text = (f"utc={utc()}\nkind={kind}\nurl={url}\ntitle={title}\n"
            f"body_excerpt={body[:2000]}\n")
    path.write_text(text, encoding="utf-8", newline="\n")
    log.write(f"ERROR_FRAGMENT={path}")
    return str(path)


def _item(raw: dict, keyword: str | None, kind: str) -> dict:
    return {
        "tweet_id": str(raw.get("tweet_id")),
        "url": raw.get("url"),
        "text": (raw.get("text") or "").strip(),
        "author_handle": raw.get("author_handle"),
        "author_name": raw.get("author_name"),
        "created_at": raw.get("created_at"),
        "lang": raw.get("lang"),
        "replies": raw.get("replies"),
        "retweets": raw.get("retweets"),
        "likes": raw.get("likes"),
        "views": raw.get("views"),
        "media_urls": raw.get("media_urls") or [],
        "discovered_by_keyword": keyword if kind == "search" else f"{kind}:{keyword or ''}",
        "fetched_at": utc(),
    }


async def _wait_for_articles(tab, kind: str, target: str | None, log: RunLog,
                             timeout: float = 20.0) -> None:
    deadline = time.monotonic() + timeout
    last = 0
    while time.monotonic() < deadline:
        try:
            raw = _decode_cdp(await tab.evaluate(EXTRACT_JS)) or []
        except Exception:  # noqa: BLE001
            raw = []
        last = len(raw) if isinstance(raw, list) else 0
        if kind == "tweet" and target:
            ids = {str(r.get("tweet_id")) for r in raw if isinstance(r, dict)}
            if target in ids:
                log.write(f"WAIT_ARTICLES target_ready visible={last}")
                return
        elif last:
            log.write(f"WAIT_ARTICLES ready visible={last}")
            return
        await asyncio.sleep(1)
    log.write(f"WAIT_ARTICLES timeout visible={last}")


async def _check_state(tab, kind: str, log: RunLog) -> int | None:
    try:
        href = str(_decode_cdp(await tab.evaluate("location.href")) or "")
        title = str(_decode_cdp(await tab.evaluate("document.title")) or "")
    except Exception:  # noqa: BLE001
        return None
    low = href.lower()
    if "/login" in low or "/i/flow/login" in low or "jf/onboarding" in low or "mode=login" in low:
        log.write(f"SESSION_EXPIRED href={href}")
        return SESSION_EXPIRED
    try:
        risk = bool(_decode_cdp(await tab.evaluate(RISK_JS)))
    except Exception:  # noqa: BLE001
        risk = False
    if risk:
        try:
            body = str(_decode_cdp(await tab.evaluate(BODY_JS)) or "")
        except Exception:  # noqa: BLE001
            body = ""
        _save_error(kind, href, title, body, log)
        log.write(f"RISK_CONTROL href={href} title={title!r}")
        return ERROR
    return None


async def _collect_async(kind: str, url: str, limit: int, keyword: str | None,
                         with_replies: bool, interval_min: int, interval_max: int,
                         log: RunLog) -> int:
    meta = _cookie_auth()
    log.write(f"COOKIE_CHECK x_rows={meta['x_rows']} auth_token={meta['auth_token']} ct0={meta['ct0']}")
    if not (meta["auth_token"] and meta["ct0"]):
        log.write("SESSION_EXPIRED (no auth cookies in profile; browser not launched)")
        return SESSION_EXPIRED
    DATA.mkdir(parents=True, exist_ok=True)
    seen = _load_seen()
    batch_ids: set[str] = set()
    items: list[dict] = []
    duplicates = 0
    stop = "LIMIT"
    risk_partial = False
    login_partial = False
    started = time.monotonic()
    started_utc = utc()
    log.write(f"START collect kind={kind} url={url} limit={limit} interval={interval_min}-{interval_max}s")
    browser = await _start(headless=True, log=log)
    try:
        tab = await browser.get(url)
        await asyncio.sleep(4)
        state = await _check_state(tab, kind, log)
        if state is not None:
            return state
        await _wait_for_articles(tab, kind, keyword if kind == "tweet" else None, log)
        rounds = 0
        no_new = 0
        while len(items) < limit:
            if time.monotonic() - started > MAX_SECONDS:
                stop = "TIMEOUT"
                break
            try:
                raw = _decode_cdp(await tab.evaluate(EXTRACT_JS)) or []
            except Exception as exc:  # noqa: BLE001
                log.write(f"EXTRACT_ERROR={type(exc).__name__}")
                raw = []
            before_filter = len(raw) if isinstance(raw, list) else 0
            if kind == "tweet" and not with_replies:
                raw = [r for r in raw if isinstance(r, dict)
                       and str(r.get("tweet_id") or "") == str(keyword)]
            added = 0
            for r in raw if isinstance(raw, list) else []:
                if len(items) >= limit:
                    break
                if not isinstance(r, dict):
                    continue
                tid = str(r.get("tweet_id") or "")
                if not tid:
                    continue
                if tid in batch_ids or tid in seen:
                    duplicates += 1
                    continue
                batch_ids.add(tid)
                items.append(_item(r, keyword, kind))
                added += 1
            log.write(f"ROUND={rounds} visible={before_filter} "
                      f"kept={len(raw) if isinstance(raw, list) else 0} "
                      f"added={added} total={len(items)} duplicates={duplicates}")
            if len(items) >= limit:
                stop = "LIMIT"
                break
            if kind == "tweet" and not with_replies:
                stop = "SINGLE"
                break
            rounds += 1
            try:
                await tab.evaluate(f"window.scrollBy(0, {random.randint(800, 1200)})")
            except Exception:  # noqa: BLE001
                pass
            await asyncio.sleep(random.uniform(interval_min, interval_max))
            state = await _check_state(tab, kind, log)
            if state is not None:
                if state == SESSION_EXPIRED:
                    stop = "SESSION_EXPIRED_PARTIAL"
                    login_partial = True
                elif items:
                    stop = "RISK_CONTROL_PARTIAL"
                    risk_partial = True
                else:
                    return state
                break
            if added == 0:
                no_new += 1
            else:
                no_new = 0
            if no_new >= 3:
                stop = "END"
                break
        elapsed = round(time.monotonic() - started, 1)
        out = DATA / f"{kind}-{utc().replace(':', '')}.jsonl"
        if items:
            _append_jsonl(out, items)
            _append_jsonl(SEEN, [{"tweet_id": i["tweet_id"], "first_seen_utc": i["fetched_at"],
                                  "url": i["url"]} for i in items])
        nonempty = sum(1 for i in items if i["text"])
        stats = {
            "command": kind, "url": url, "keyword": keyword,
            "started_utc": started_utc, "finished_utc": utc(), "elapsed_s": elapsed,
            "requested_limit": limit, "collected": len(items),
            "duplicates": duplicates, "seen_total": len(seen) + len(items),
            "nonempty_text": nonempty,
            "nonempty_text_ratio": round(nonempty / len(items), 3) if items else 0.0,
            "stop_reason": stop, "jsonl": str(out) if items else None,
            "exit": 0 if items else (ERROR if stop == "TIMEOUT" else PARSE_EMPTY),
        }
        (DATA / "last_run_stats.json").write_text(
            json.dumps(stats, ensure_ascii=False, indent=1), encoding="utf-8", newline="\n")
        log.write("STATS=" + json.dumps(stats, ensure_ascii=False))
        if not items:
            log.write("PARSE_EMPTY (page normal but no tweet article parsed)")
            return ERROR if stop == "TIMEOUT" else PARSE_EMPTY
        if login_partial:
            return SESSION_EXPIRED
        return ERROR if risk_partial else 0
    finally:
        await _graceful_close(browser, log)


def main() -> int:
    parser = argparse.ArgumentParser(prog="x-collect")
    sub = parser.add_subparsers(dest="command", required=True)
    d = sub.add_parser("doctor", help="check X session in the dedicated profile")
    d.add_argument("--headed", action="store_true", help="run Chrome headed instead of headless")
    d.add_argument("--timeout", type=int, default=90)
    lg = sub.add_parser("login", help="open a visible Chrome for the user to log in once")
    lg.add_argument("--timeout", type=int, default=1200, help="max seconds to wait (<=1200)")
    s = sub.add_parser("search", help="collect public tweets from x.com search (read-only)")
    s.add_argument("--keyword", required=True)
    s.add_argument("--limit", type=int, default=20)
    s.add_argument("--interval-min", type=int, default=8)
    s.add_argument("--interval-max", type=int, default=12)
    u = sub.add_parser("user", help="collect recent public tweets from a profile (read-only)")
    u.add_argument("--handle", required=True)
    u.add_argument("--limit", type=int, default=20)
    u.add_argument("--interval-min", type=int, default=8)
    u.add_argument("--interval-max", type=int, default=12)
    t = sub.add_parser("tweet", help="collect one public tweet (optional first-level replies)")
    t.add_argument("--url", required=True)
    t.add_argument("--with-replies", action="store_true")
    t.add_argument("--limit", type=int, default=20)
    t.add_argument("--interval-min", type=int, default=8)
    t.add_argument("--interval-max", type=int, default=12)
    args = parser.parse_args()

    log = RunLog(args.command)
    log.write(f"CMD={' '.join(sys.argv)} CWD={os.getcwd()} UTC={utc()}")
    try:
        if args.command == "doctor":
            code = asyncio.run(asyncio.wait_for(doctor_async(args.headed, log), timeout=args.timeout))
        elif args.command == "login":
            timeout = min(max(args.timeout, 30), 1200)
            code = asyncio.run(asyncio.wait_for(login_async(timeout, log), timeout=timeout + 120))
        elif args.command in ("search", "user", "tweet"):
            limit = min(max(args.limit, 1), MAX_LIMIT)
            imin = max(args.interval_min, 8)
            imax = max(args.interval_max, imin, 12)
            if args.command == "search":
                keyword = args.keyword.strip()
                if not keyword:
                    log.write("INVALID keyword")
                    code = 4
                else:
                    url = f"https://x.com/search?q={quote(keyword)}&f=live"
                    code = asyncio.run(asyncio.wait_for(
                        _collect_async("search", url, limit, keyword, False, imin, imax, log),
                        timeout=MAX_SECONDS + 180))
            elif args.command == "user":
                handle = args.handle.strip().lstrip("@")
                if not handle or not handle.replace("_", "").isalnum():
                    log.write("INVALID handle")
                    code = 4
                else:
                    url = f"https://x.com/{handle}"
                    code = asyncio.run(asyncio.wait_for(
                        _collect_async("user", url, limit, handle, False, imin, imax, log),
                        timeout=MAX_SECONDS + 180))
            else:
                url = args.url.strip()
                if not (url.startswith("https://x.com/") or url.startswith("https://twitter.com/")):
                    log.write("INVALID url (must be x.com/twitter.com status URL)")
                    code = 4
                else:
                    tweet_id = url.rstrip("/").split("/")[-1]
                    tweet_limit = limit if args.with_replies else 1
                    code = asyncio.run(asyncio.wait_for(
                        _collect_async("tweet", url, tweet_limit, tweet_id, args.with_replies,
                                       imin, imax, log),
                        timeout=MAX_SECONDS + 180))
        else:
            log.write("NOT_IMPLEMENTED")
            code = NOT_IMPLEMENTED
    except asyncio.TimeoutError:
        log.write("TIMEOUT")
        code = ERROR
    except Exception as exc:  # noqa: BLE001
        log.write(f"ERROR {type(exc).__name__}: {exc}")
        code = ERROR
    log.close(code)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
