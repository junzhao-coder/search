"""Weibo adapter — same six commands as the Zhihu one, same shared base.

Nothing here re-implements transport, budget, records or diagnostics: this
module only supplies what is genuinely Weibo-specific —

- the site profile (link shapes, container selectors, wall/empty wording) that
  the shared `transport.AuthenticatedBrowserTransport` drives,
- URL rules and three parsers (search HTML, detail HTML, comments JSON),
- login markers, so the shared poll loop knows what "signed in" looks like.

**Every Weibo selector and endpoint below is an assumption.** No Weibo page has
been observed by this project: the entire batch is offline, so
`diagnostics.ASSUMED_BY_SITE["weibo"]` marks the unknowns and every parser says
`html:*` / `json:*` about where a value came from, never "verified".

Orchestration helpers (`_charge`, `_finish`, `_risk_or_error`,
`_merge_diagnostics`) are imported from the Zhihu adapter on purpose: the risk
policy (a wall locks the batch, 403/429 locks, timeouts do not) must be one
implementation, not two that drift.
"""

from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import json
import pathlib
import re
import sys
import time
import urllib.parse

from . import budget as budget_mod
from . import codes
from . import diagnostics as diag_mod
from . import platform_budget as platform_mod
from . import records as rec
from . import transport as transport_mod
from .zhihu import (_charge, _finish, _merge_diagnostics, _risk_or_error,
                    export as export_records)

BASE = "https://m.weibo.cn"

#: 桌面搜索入口（服务端直出结果卡片）；`search_url()` 默认用它。
DESKTOP_SEARCH = "https://s.weibo.com/weibo"
ALLOWED_HOST = "weibo.cn"
LOGIN_URL = "https://passport.weibo.com/sso/signin"
#: explicit "is this profile still signed in?" entry: the business home
#: only. No fallback to the passport page, no reopen.
SESSION_CHECK_URL = "https://weibo.com/"
DEFAULT_PROFILE = pathlib.Path.home() / ".dsh" / "tools" / "weibo-collect" / "profile"

#: Mobile UA. Assumption (documented in RESEARCH.md): m.weibo.cn tends to serve
#: server-rendered cards to a mobile UA and a JS shell to a desktop UA. This is
#: a *launch switch* on the browser, so the very first request carries it.
MOBILE_UA = ("Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 "
             "(KHTML, like Gecko) Chrome/124.0.0.0 Mobile Safari/537.36")

#: cookie NAMES we look for; values are never read, exported or logged.
COOKIE_NAMES = ("SUB", "SUBP", "SUHB", "SCL", "SSOLoginState", "_T_WM", "XSRF-TOKEN")

#: content paths a Weibo listing actually links to (assumed).
WEIBO_LINK_RE = re.compile(
    r"/(?:detail/\d+|status/\d+|\d{6,}/[A-Za-z0-9]{6,12})/?$")

#: wall wording. Deliberately **without** a bare "验证码": sign-in pages show
#: "获取验证码" as normal copy, and treating that as a wall is the exact
#: false-positive class that closed the Zhihu login window after 4 seconds.
#: Same rule applies to `SITE.wall_markers` below: only real wall wording, never
#: the sign-in page's own "获取验证码 / 短信验证码" copy.
RISK_MARKERS = ("安全验证", "captcha", "访问异常", "操作频繁", "访问过于频繁",
                "请求过于频繁", "系统繁忙", "系统检测到", "账号异常", "访问受限",
                "登录后查看", "请先登录")
LOGIN_WALL_MARKERS = ("访问异常", "操作频繁", "访问过于频繁", "请求过于频繁",
                      "系统繁忙", "账号异常", "访问受限", "安全验证", "captcha")

#: observed page state for the shared transport: four link shapes plus wording.
SITE = transport_mod.SiteProfile(
    "weibo",
    shape_rules=(
        ("detail", r"/\/detail\/\d+\/?$/.test(href)"),
        ("status", r"/\/status\/\d+\/?$/.test(href)"),
        ("post", r"/^\/\d{6,}\/[A-Za-z0-9]{6,12}\/?$/.test(href)"),
        ("profile", r"/^\/(?:u\/)?\d{6,}\/?$/.test(href)"),
    ),
    recognized_keys=("detail", "status", "post"),
    result_selectors='[class*="card"],[class*="feed"],[class*="m-panel"]',
    list_selectors='[class*="list"],[class*="item"],[id*="app"]',
    wall_markers=("安全验证", "访问异常", "操作频繁", "访问过于频繁",
                  "请求过于频繁", "系统繁忙", "账号异常", "访问受限",
                  "登录后查看", "请先登录"),
    empty_markers=("没有找到", "暂无内容", "未找到相关", "暂无搜索结果", "没有更多"),
    user_agent=MOBILE_UA,
)

#: Page-visible **signals** only: this script collects facts, it does not decide.
#: The decision lives in `classify_signed_in()` so it can be unit-tested as a
#: pure predicate (and the same JS is executed against a DOM stub in the tests).
#: Selectors are **assumed** -- no real logged-in page has been observed.
SIGNED_IN_JS = r"""
(() => {
  const host = (location.hostname || '').toLowerCase();
  const path = location.pathname || '';
  const text = (document.body && document.body.innerText) || '';
  const has = (sel) => { try { return document.querySelector(sel) !== null; } catch (e) { return false; } };
  const count = (sel) => { try { return document.querySelectorAll(sel).length; } catch (e) { return 0; } };
  const userLinkCount = count('a[href*="/u/"]');
  const out = {
    host: host,
    path: path,
    text: text.slice(0, 4000),
    hasLogout: has('a[href*="/logout"]'),
    hasSettings: has('a[href*="/setting"]') || has('a[href*="/account/"]'),
    hasCompose: has('a[href*="/compose"]') || has('[class*="publish"]') || has('[class*="compose"]'),
    avatarCount: count('img[src*="avatar"],[class*="avatar"],[class*="Avatar"]'),
    userLinkCount: userLinkCount
  };
  // 退出入口常在折叠菜单里、且不一定是 /logout 形态；发微博按钮同理。
  // 这些键**只在为真时**出现，保持"空白页只吐 8 个键"的既有契约。
  const signout = has('a[href*="/signout"]') || has('[class*="logout"]')
    || has('[class*="signout"]') || text.includes('退出');
  const ownProfile = count('header a[href^="/u/"]') > 0 || userLinkCount > 0;
  const composeBtn = has('a[href*="/compose"]') || has('[class*="publish"]')
    || has('[class*="compose"]') || /发微博|发布/.test(text);
  const marks = {signout: text.includes('退出'), profile: text.includes('我的主页')};
  if (signout) out.hasSignout = true;
  if (ownProfile) out.hasOwnProfileLink = true;
  if (composeBtn) out.hasComposeBtn = true;
  if (marks.signout || marks.profile) out.textMarks = marks;
  return JSON.stringify(out);
})()
"""

#: 兼容旧调用方：`STRONG_SIGNALS` 仍只列最老的强信号；
#: 完整判定规则见 `signed_in_evidence()`（hasLogout / hasSignout /
#: hasComposeBtn+userLinkCount / 正文命中「退出」「我的主页」）。
STRONG_SIGNALS = ("hasLogout",)

#: pages that can never prove a session, whatever they render
_EXCLUDED_HOST = re.compile(r"(^|\.)(passport|login|signin)\.")
_EXCLUDED_PATH = re.compile(r"/(signin|login|sso)\b")


def _weibo_business_host(host: str) -> bool:
    host = (host or "").lower()
    if not host or _EXCLUDED_HOST.search(host):
        return False
    return host == "weibo.com" or host.endswith(".weibo.com")


def signed_in_evidence(signals) -> str | None:
    """命中的判定规则名；未命中返回 None。供报告写清"凭什么判登录"。"""
    if isinstance(signals, str):
        try:
            signals = json.loads(signals)
        except (json.JSONDecodeError, TypeError):
            return None
    if not isinstance(signals, dict):
        return None
    if not _weibo_business_host(str(signals.get("host") or "")):
        return None
    if _EXCLUDED_PATH.search(str(signals.get("path") or "")):
        return None
    if signals.get("hasLogout"):
        return "hasLogout"
    if signals.get("hasSignout"):
        return "hasSignout"
    if signals.get("hasComposeBtn") and int(signals.get("userLinkCount") or 0) > 0:
        return "composeBtn+userLink"
    marks = signals.get("textMarks") or {}
    if isinstance(marks, dict):
        if marks.get("signout"):
            return "text:退出"
        if marks.get("profile"):
            return "text:我的主页"
    text = str(signals.get("text") or "")
    if "退出" in text:
        return "text:退出"
    if "我的主页" in text:
        return "text:我的主页"
    return None


def classify_signed_in(signals) -> str:
    """`ok` on any documented strong signal; everything weaker is `unknown`.

    Deliberately NOT sufficient: public avatars, generic `/u/` links, a lone
    "消息", and generic `/account/` or `/setting` entries (a logged-out page can
    carry all of them). The host/path gate keeps passport/login pages and
    non-Weibo tabs out even if they happen to render a control. Selectors are
    **assumed** -- no real logged-in page has been observed.
    """
    if isinstance(signals, str):
        try:
            signals = json.loads(signals)
        except (json.JSONDecodeError, TypeError):
            return "unknown"
    if not isinstance(signals, dict):
        return "unknown"
    return "ok" if signed_in_evidence(signals) else "unknown"


def signed_in_verdict(signals) -> bool:
    """Boolean view of `classify_signed_in` for the shared poll loop."""
    return classify_signed_in(signals) == "ok"


EXIT_OK = codes.EXIT_OK
EXIT_EMPTY = codes.EXIT_EMPTY
EXIT_UNSUPPORTED = codes.EXIT_UNSUPPORTED
EXIT_RISK = codes.EXIT_RISK
EXIT_BUDGET = codes.EXIT_BUDGET
EXIT_TRANSPORT = codes.EXIT_TRANSPORT
EXIT_INPUT = codes.EXIT_INPUT
EXIT_EXPORT = codes.EXIT_EXPORT
EXIT_PARTIAL = codes.EXIT_PARTIAL
EXIT_LOGIN_TIMEOUT = codes.EXIT_LOGIN_TIMEOUT
EXIT_LOGIN_POLL_LIMIT = codes.EXIT_LOGIN_POLL_LIMIT
EXIT_LOGIN_UNKNOWN = codes.EXIT_LOGIN_UNKNOWN


# --------------------------------------------------------------------------
# URLs
# --------------------------------------------------------------------------
def allowed_url(url) -> bool:
    parts = urllib.parse.urlsplit(str(url or "").strip())
    host = (parts.hostname or "").lower()
    if parts.scheme not in ("http", "https"):
        return False
    return host == ALLOWED_HOST or host.endswith("." + ALLOWED_HOST)


def require_url(url) -> str:
    if not allowed_url(url):
        raise ValueError("url_not_allowed")
    return rec.sanitize_url(url) or ""


def search_url(keyword: str, *, surface: str = "desktop") -> str:
    """搜索入口：**默认桌面版** `s.weibo.com`（服务端直出结果卡片），移动版保留为可选。

    差异（2026-10-30 实测）：
    - `surface="desktop"`：`https://s.weibo.com/weibo?q=<kw>&typeall=1&suball=1`，
      结果是服务端渲染的 `div.card-wrap` 结构，适合用 HTML 直接数结构；
    - `surface="mobile"`：`https://m.weibo.cn/search?containerid=...`，实测导航后
      `containerid` 会被丢掉、页面只剩壳（text_len≈6、cards_in=0），**不推荐**再用于采集。
    """
    if surface == "mobile":
        container = f"100103type=1&q={keyword}"
        return f"{BASE}/search?containerid={urllib.parse.quote(container, safe='')}"
    query = urllib.parse.quote(keyword, safe="")
    return f"{DESKTOP_SEARCH}?q={query}&typeall=1&suball=1"


def comments_url(mid: str) -> str:
    """Comments endpoint (assumed): hotflow JSON for one status id."""
    return f"{BASE}/comments/hotflow?id={mid}&mid={mid}&max_id_type=0"


def url_identity(url: str) -> dict:
    """(type, native_id, parent_id) from a Weibo URL; nothing guessed."""
    path = urllib.parse.urlsplit(str(url or "")).path
    out = {"type": None, "native_id": None, "parent_id": None, "evidence": None}
    match = re.search(r"/(?:detail|status)/(\d+)", path)
    if match:
        return {"type": "status", "native_id": match.group(1), "parent_id": None,
                "evidence": "url:/detail|status/<id>"}
    match = re.search(r"^/(\d{6,})/([A-Za-z0-9]{6,12})/?$", path)
    if match:
        return {"type": "status", "native_id": match.group(2), "parent_id": match.group(1),
                "evidence": "url:/<uid>/<bid>"}
    match = re.search(r"^/(?:u/)?(\d{6,})/?$", path)
    if match:
        return {"type": "profile", "native_id": match.group(1), "parent_id": None,
                "evidence": "url:/<uid>"}
    return out


# --------------------------------------------------------------------------
# risk scans
# --------------------------------------------------------------------------
def detect_risk(text: str, status=None) -> str | None:
    """Marker scan over a plain string. HTTP 403/429/432 is risk by itself."""
    if status in (403, 429, 432):
        return f"http_{status}"
    lowered = " ".join(str(text or "").split()).lower()
    for marker in RISK_MARKERS:
        if marker.lower() in lowered:
            return f"text:{marker}"
    return None


def detect_login_wall(text: str) -> str | None:
    """Login-page wall scan: normal sign-in copy is not a wall."""
    lowered = " ".join(str(text or "").split()).lower()
    for marker in LOGIN_WALL_MARKERS:
        if marker.lower() in lowered:
            return f"text:{marker}"
    return None


# --------------------------------------------------------------------------
# doctor / login
# --------------------------------------------------------------------------
def doctor(profile=DEFAULT_PROFILE) -> dict:
    """Read-only: profile dir + cookie NAMES only. Never launches a browser."""
    from .zhihu import _open_readonly  # shared read-only sqlite opener

    profile = pathlib.Path(profile)
    cookies = profile / "Default" / "Network" / "Cookies"
    out = {"site": "weibo", "profile": str(profile), "profile_exists": profile.is_dir(),
           "cookie_db_exists": cookies.is_file(), "cookie_names": {},
           "online": "unverified", "network": "none",
           "note": "cookie names only; presence is not proof of a valid session"}
    if not out["cookie_db_exists"]:
        return out
    conn = _open_readonly(cookies)
    if conn is None:
        out["error"] = "cookie_db_open_failed"
        return out
    try:
        rows = conn.execute(
            "SELECT DISTINCT name FROM cookies WHERE host_key LIKE '%weibo%'").fetchall()
    except Exception as exc:  # noqa: BLE001 - a locked/old cookie db is not a crash
        out["error"] = f"cookie_db_read_failed:{type(exc).__name__}"
        return out
    finally:
        conn.close()
    names = {rec.collapse(row[0]) for row in rows if row and row[0]}
    out["cookie_names"] = {name: (name in names) for name in COOKIE_NAMES}
    out["cookie_count"] = len(names)
    return out


def login(profile=DEFAULT_PROFILE, *, budget, clock=None, timeout: float = 300.0,
          headless: bool = False, browser=None, check_session: bool = False,
          platform=None, batch_id: str | None = None) -> dict:
    """Open a visible window for the user to sign in. Never fills credentials.

    Reuses `browser.wait_for_login` (poll quota, five states, risk lock) — only
    the signed-in markers and the wall wording are Weibo's.
    """
    from . import browser as browser_mod  # local import: nodriver is optional

    clock = clock or time.time
    # opening a window always navigates: it is metered, no exceptions. Tests must
    # inject an isolated ledger; there is no unmetered switch on this API.
    denial = _platform_charge(platform, batch_id, "active_nav",
                              "check_session" if check_session else "login",
                              metered=True)
    if denial:
        return {"status": "denied", "exit": EXIT_BUDGET, "stop": denial,
                "polls": 0, "signed_in": False}
    try:
        if browser is None:
            info = browser_mod.available()
            if not info["usable"]:
                payload = {"status": "unavailable", "exit": EXIT_TRANSPORT,
                           "error": "browser_unavailable", "detail": info,
                           "profile": str(profile), "polls": 0, "signed_in": False}
            else:
                payload = _login_with_real_browser(
                    profile, budget=budget, clock=clock, timeout=timeout,
                    headless=headless, info=info, check_session=check_session)
        else:
            payload = asyncio.run(browser_mod.wait_for_login(
                browser, profile=profile, budget=budget, clock=clock, timeout=timeout,
                signed_in_js=SIGNED_IN_JS, wall_markers=LOGIN_WALL_MARKERS,
                signed_in_verdict=signed_in_verdict, risk_wins=True))
    except Exception as exc:  # noqa: BLE001 - a charged call must still be settled
        payload = {"status": "unknown", "exit": EXIT_TRANSPORT, "polls": 0,
                   "signed_in": False,
                   "stop": f"login_exception:{type(exc).__name__}"}
    return _login_settle(platform, batch_id, payload)


def _login_settle(platform, batch_id, payload: dict) -> dict:
    """Persist the login risk to the platform lock, then record the outcome."""
    if payload.get("status") == "risk":
        try:
            _platform_lock(platform, payload.get("risk_reason") or "login_risk",
                           "weibo.login")
        except Exception:  # noqa: BLE001 - an unpersisted lock must stop the run
            return {**payload, "status": "risk", "exit": EXIT_BUDGET,
                    "stop": "platform:lock_write_failed"}
    failure = _platform_result(platform, batch_id, "active_nav",
                               int(payload.get("exit", 0)))
    if failure:
        # the navigation already happened and could not be recorded: never report
        # it as a signed-in success. Keep the original risk evidence in the payload.
        return {**payload, "status": "unknown", "signed_in": False,
                "exit": EXIT_BUDGET, "ok": False, "result_persisted": False,
                "record_error": failure, "stop": failure}
    return payload


def _login_with_real_browser(profile, *, budget, clock, timeout: float,
                             headless: bool, info: dict,
                             check_session: bool = False) -> dict:
    """Real nodriver window. Never executed in this offline batch."""
    import nodriver as uc

    from . import browser as browser_mod

    clock = clock or time.time
    # `uc.start` needs an absolute user_data_dir: a relative one launches and then
    # fails with "Failed to connect to browser" (verified on the Weibo probe).
    profile = pathlib.Path(profile).expanduser().resolve()
    pathlib.Path(profile).mkdir(parents=True, exist_ok=True)

    async def _run() -> dict:
        browser = await uc.start(headless=headless, user_data_dir=str(profile),
                                 browser_executable_path=info["chrome"])
        try:
            await browser.get(SESSION_CHECK_URL if check_session else LOGIN_URL)
            return await browser_mod.wait_for_login(
                browser, profile=profile, budget=budget, clock=clock, timeout=timeout,
                signed_in_js=SIGNED_IN_JS, wall_markers=LOGIN_WALL_MARKERS,
                signed_in_verdict=signed_in_verdict, risk_wins=True)
        finally:
            try:
                browser.stop()
            except Exception:  # noqa: BLE001
                pass

    return asyncio.run(_run())


# --------------------------------------------------------------------------
# parsers (all Weibo assumptions are named here)
# --------------------------------------------------------------------------
def parse_search_html(html: str, *, collected_at: str, limit: int = 5) -> dict:
    """Search listing -> status stubs. `html:links` only when links matched."""
    if not (html or "").strip():
        return {"records": [], "stop": "empty", "structure": "html:empty",
                "web_state": "empty_document", "anchors_total": 0,
                "anchors_recognized": 0, "anchors_rejected": 0}
    parser = rec.Links(WEIBO_LINK_RE)
    try:
        parser.feed(html or "")
        parser.close()
    except Exception:  # noqa: BLE001 - malformed markup is not a crash
        return {"records": [], "stop": "parse_error", "structure": "html:unknown",
                "web_state": "parse_error", "anchors_total": parser.total,
                "anchors_recognized": len(parser.items),
                "anchors_rejected": parser.rejected}
    if not parser.items:
        return {"records": [], "stop": "unknown", "structure": "html:unknown",
                "web_state": "no_recognized_anchors" if parser.total else "no_anchors",
                "anchors_total": parser.total, "anchors_recognized": 0,
                "anchors_rejected": parser.rejected}
    out: list[dict] = []
    seen: set[str] = set()
    for item in parser.items:
        href = urllib.parse.urljoin(BASE, item["href"])
        if not allowed_url(href):
            continue
        ident = url_identity(href)
        if not ident["native_id"] or ident["native_id"] in seen:
            continue
        seen.add(ident["native_id"])
        values = {"native_id": ident["native_id"], "type": ident["type"],
                  "parent_id": ident["parent_id"], "url": href,
                  "title": item.get("text") or None, "text": None,
                  "published_at": None, "voteup": None, "comments": None, "likes": None}
        paths = {"native_id": ident["evidence"], "type": ident["evidence"],
                 "parent_id": ident["evidence"], "url": "html:a[href]",
                 "title": "html:a[text]"}
        out.append(rec.make_record(values=values, evidence=_evidence(values, paths),
                                   collected_at=collected_at, source="weibo:search:status"))
        if len(out) >= max(1, int(limit)):
            break
    return {"records": out, "stop": "records" if out else "empty",
            "structure": "html:links", "web_state": "result",
            "anchors_total": parser.total, "anchors_recognized": len(parser.items),
            "anchors_rejected": parser.rejected}


def parse_detail_html(html: str, url: str, *, collected_at: str) -> dict:
    """Detail page -> one status record. Wall/unknown pages never become records."""
    text = str(html or "")
    if not text.strip():
        return {"record": None, "stop": "empty", "structure": "html:empty"}
    reason = detect_risk(rec.strip_tags(text)[:20000], None)
    if reason and not rec.collapse(rec.meta_tags(text)["meta"].get("og:description")):
        # a wall page has no description meta; a normal post that merely talks
        # about captchas does, so the meta is what keeps this from misfiring
        return {"record": None, "stop": f"risk:{reason}", "structure": "html:wall"}
    ident = url_identity(url)
    meta = rec.meta_tags(text)["meta"]
    body = rec.strip_tags(text)
    title = rec.collapse(meta.get("og:title") or "")
    description = rec.collapse(meta.get("og:description") or "")
    values = {"native_id": ident["native_id"], "type": "status",
              "parent_id": ident["parent_id"], "url": url,
              "title": title or None, "text": description or body[:2000] or None,
              "published_at": None, "voteup": None, "comments": None, "likes": None}
    if not values["native_id"] or not (values["title"] or values["text"]):
        return {"record": None, "stop": "unknown", "structure": "html:unknown"}
    paths = {"native_id": ident["evidence"] or "derived:url",
             "type": "constant:status", "parent_id": ident["evidence"] or "derived:url",
             "url": "input:url",
             "title": "html:meta[og:title]" if title else None,
             "text": "html:meta[og:description]" if description else "html:body:text"}
    record = rec.make_record(values=values, evidence=_evidence(values, paths),
                             collected_at=collected_at, source="weibo:detail:status")
    return {"record": record, "stop": None, "structure": "html:meta+body"}


def parse_comments_json(payload, *, content_id: str, collected_at: str,
                        limit: int = 5) -> dict:
    """hotflow JSON -> comment records, `parent_id` = the status they belong to."""
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except json.JSONDecodeError:
            return {"records": [], "stop": "unsupported", "structure": "json:invalid"}
    if not isinstance(payload, dict):
        return {"records": [], "stop": "unsupported", "structure": "json:not_object"}
    items = payload.get("data")
    if isinstance(items, dict):
        items = items.get("data") or items.get("comments")
    if not isinstance(items, list):
        return {"records": [], "stop": "unsupported", "structure": "json:no_data",
                "is_end": None}
    out: list[dict] = []
    unknown = 0
    for item in items:
        if not isinstance(item, dict):
            unknown += 1
            continue
        native_id = item.get("id") or item.get("idstr")
        text = rec.strip_tags(str(item.get("text") or ""))
        if native_id is None or not text:
            unknown += 1
            continue
        values = {"native_id": str(native_id), "type": "comment",
                  "parent_id": content_id, "url": f"{BASE}/detail/{content_id}",
                  "title": None, "text": text[:2000],
                  "published_at": rec.collapse(str(item.get("created_at") or "")) or None,
                  "voteup": None, "comments": None,
                  "likes": item.get("like_count") if isinstance(item.get("like_count"), int) else None}
        paths = {"native_id": "json:data[].id", "type": "constant:comment",
                 "parent_id": "input:url", "url": "derived:status.id",
                 "text": "json:data[].text",
                 "published_at": "json:data[].created_at" if values["published_at"] else None,
                 "likes": "json:data[].like_count" if values["likes"] is not None else None}
        out.append(rec.make_record(values=values, evidence=_evidence(values, paths),
                                   collected_at=collected_at, source="weibo:comment:hotflow"))
        if len(out) >= max(1, int(limit)):
            break
    stop = "records" if out else "empty"
    if unknown and out:
        stop = "unknown_objects"
    return {"records": out, "stop": stop, "structure": "json:hotflow",
            "is_end": payload.get("ok") == 1 and not payload.get("data", {}).get("max_id")
            if isinstance(payload.get("data"), dict) else None,
            "next_offset": (payload.get("data") or {}).get("max_id")
            if isinstance(payload.get("data"), dict) else None,
            "unknown_objects": unknown}


def _evidence(values: dict, paths: dict) -> dict:
    """Evidence only where the value actually exists."""
    return {field: (paths.get(field) if values.get(field) is not None else None)
            for field in rec.FIELDS}


# --------------------------------------------------------------------------
# commands (charge the budget before every active call)
# --------------------------------------------------------------------------
def _records_result(kind: str):
    """Wrap a run_* so its outcome is recorded after the charge, on every path."""
    def decorate(fn):
        def wrapper(*args, **kwargs):
            platform = kwargs.get("platform")
            batch_id = kwargs.get("batch_id")
            try:
                payload = fn(*args, **kwargs)
            except Exception as exc:  # noqa: BLE001 - the call may already be charged
                failure = _platform_result(platform, batch_id, kind, EXIT_TRANSPORT)
                out = {"command": kind, "ok": False, "exit": EXIT_TRANSPORT,
                       "records": [], "result_persisted": failure is None,
                       "stop": f"adapter_exception:{type(exc).__name__}"}
                if failure:
                    out["persist_error"] = failure
                return out
            failure = _platform_result(platform, batch_id, kind,
                                       int(payload.get("exit", 0)))
            if failure:
                # an unrecorded charged call must not look like a success
                return {**payload, "ok": False, "exit": EXIT_BUDGET, "records": [],
                        "stop": failure, "result_persisted": False}
            return payload
        wrapper.__name__ = fn.__name__
        wrapper.__doc__ = fn.__doc__
        return wrapper
    return decorate


@_records_result("search")
def run_search(keyword: str, *, batch, transport, collected_at: str,
               limit: int = 5, platform=None, batch_id: str | None = None) -> dict:
    url = search_url(keyword)
    safe_url = redact_detail(url)          # no keyword, no query, no token
    err = _charge(batch, "search", redact_detail(url))
    if err:
        return _finish("search", exit_code=EXIT_BUDGET, batch=batch, records_out=[],
                       keyword=None, stop=f"budget:{err.code}", url=safe_url)
    denial = _platform_charge(platform, batch_id, "search", redact_detail(url),
                              metered=_is_metered_transport(transport))
    if denial:
        return _finish("search", exit_code=EXIT_BUDGET, batch=batch, records_out=[],
                       keyword=None, stop=denial, url=safe_url)
    result = transport.fetch(url)
    reason, locks = _risk_or_error(result)
    if locks:
        batch.lock(reason, source="search")
        try:
            _platform_lock(platform, reason, "weibo.search")
        except Exception:  # noqa: BLE001 - an unpersisted lock must stop the run
            return _finish("search", exit_code=EXIT_BUDGET, batch=batch,
                           records_out=[], keyword=None,
                           stop="platform:lock_write_failed", url=safe_url)
        return _finish("search", exit_code=EXIT_RISK, batch=batch, records_out=[],
                       keyword=None, stop=reason, url=safe_url,
                       diagnostics=_merge_diagnostics(result, {}))
    if reason:
        batch.note("transport_error", reason)
        return _finish("search", exit_code=EXIT_TRANSPORT, batch=batch, records_out=[],
                       keyword=None, stop=reason, url=safe_url,
                       diagnostics=_merge_diagnostics(result, {}))
    parsed = parse_search_html(result.get("text") or "", collected_at=collected_at,
                              limit=limit)
    diagnostics = _merge_diagnostics(result, parsed)
    found = parsed["records"]
    exit_code = EXIT_OK
    if parsed.get("stop") in ("unsupported", "unknown"):
        exit_code = EXIT_UNSUPPORTED
    elif parsed.get("stop") == "empty" or not found:
        exit_code = EXIT_EMPTY
    elif parsed.get("stop") == "unknown_objects":
        exit_code = EXIT_PARTIAL
    if not found and diagnostics.get("state") in ("unknown", "loading") and (
            result.get("diagnostics") or result.get("probe")):
        exit_code = EXIT_TRANSPORT
        parsed = {**parsed, "stop": "readiness_timeout"}
    reserve_info = {}
    if found:
        denial = _platform_reserve(platform, batch_id, len(found))
        if denial:
            return _finish("search", exit_code=EXIT_BUDGET, batch=batch,
                           records_out=[], keyword=None, stop=denial, url=safe_url,
                           diagnostics=_merge_diagnostics(result, parsed))
        err = budget_mod_error(lambda: batch.reserve_records(len(found)))
        if err:
            return _finish("search", exit_code=EXIT_BUDGET, batch=batch, records_out=[],
                           keyword=None, stop=f"budget:{err.code}", url=safe_url,
                           parsed_structure=parsed["structure"], diagnostics=diagnostics)
        reserve_info = _reserve_fields(batch, len(found))
    batch.note("search_result", json.dumps({"count": len(found), "exit": exit_code}))
    out = _finish("search", exit_code=exit_code, batch=batch, records_out=found,
                  keyword=None, stop=parsed.get("stop"), url=safe_url,
                  parsed_structure=parsed["structure"], diagnostics=diagnostics)
    out.update(reserve_info)
    return out


@_records_result("detail")
def run_detail(url: str, *, batch, transport, collected_at: str,
               platform=None, batch_id: str | None = None) -> dict:
    try:
        target = require_url(url)
    except ValueError:
        return _finish("detail", exit_code=EXIT_INPUT, batch=batch, records_out=[],
                       stop="url_not_allowed", url=None)
    if url_identity(target)["type"] != "status":
        return _finish("detail", exit_code=EXIT_INPUT, batch=batch, records_out=[],
                       stop="unsupported_content_url", url=redact_detail(target))
    err = _charge(batch, "detail", redact_detail(target))
    if err:
        return _finish("detail", exit_code=EXIT_BUDGET, batch=batch, records_out=[],
                       stop=f"budget:{err.code}", url=redact_detail(target))
    denial = _platform_charge(platform, batch_id, "detail", redact_detail(target),
                              metered=_is_metered_transport(transport))
    if denial:
        return _finish("detail", exit_code=EXIT_BUDGET, batch=batch, records_out=[],
                       stop=denial, url=redact_detail(target))
    result = transport.fetch(target)
    reason, locks = _risk_or_error(result)
    if locks:
        batch.lock(reason, source="detail")
        try:
            _platform_lock(platform, reason, "weibo.detail")
        except Exception:  # noqa: BLE001
            return _finish("detail", exit_code=EXIT_BUDGET, batch=batch,
                           records_out=[], stop="platform:lock_write_failed",
                           url=redact_detail(target))
        return _finish("detail", exit_code=EXIT_RISK, batch=batch, records_out=[],
                       stop=reason, url=redact_detail(target),
                       diagnostics=_merge_diagnostics(result, {}))
    if reason:
        batch.note("transport_error", reason)
        return _finish("detail", exit_code=EXIT_TRANSPORT, batch=batch, records_out=[],
                       stop=reason, url=redact_detail(target))
    parsed = parse_detail_html(result.get("text") or "", target, collected_at=collected_at)
    record = parsed.get("record")
    stop = parsed.get("stop")
    if stop:
        if stop.startswith("risk:"):
            batch.lock(stop, source="detail")
            try:
                _platform_lock(platform, stop, "weibo.detail")
            except Exception:  # noqa: BLE001 - an unpersisted lock must stop the run
                return _finish("detail", exit_code=EXIT_BUDGET, batch=batch,
                               records_out=[], stop="platform:lock_write_failed",
                               url=redact_detail(target))
            return _finish("detail", exit_code=EXIT_RISK, batch=batch, records_out=[],
                           stop=stop, url=redact_detail(target),
                           diagnostics=_merge_diagnostics(result, parsed))
        exit_code = EXIT_EMPTY if stop == "empty" else EXIT_UNSUPPORTED
        return _finish("detail", exit_code=exit_code, batch=batch, records_out=[],
                       stop=stop, url=redact_detail(target),
                       diagnostics=_merge_diagnostics(result, parsed))
    denial = _platform_reserve(platform, batch_id, 1)
    if denial:
        return _finish("detail", exit_code=EXIT_BUDGET, batch=batch, records_out=[],
                       stop=denial, url=redact_detail(target),
                       diagnostics=_merge_diagnostics(result, parsed))
    err = budget_mod_error(lambda: batch.reserve_records(1))
    if err:
        return _finish("detail", exit_code=EXIT_BUDGET, batch=batch, records_out=[],
                       stop=f"budget:{err.code}", url=redact_detail(target))
    batch.note("detail_result", json.dumps({"native_id": record["native_id"]}))
    return _finish("detail", exit_code=EXIT_OK, batch=batch, records_out=[record],
                   stop=None, url=redact_detail(target), parsed_structure=parsed["structure"],
                   diagnostics=_merge_diagnostics(result, parsed))


@_records_result("comments")
def run_comments(url: str, *, batch, transport, collected_at: str,
                 limit: int = 5, platform=None, batch_id: str | None = None) -> dict:
    try:
        target = require_url(url)
    except ValueError:
        return _finish("comments", exit_code=EXIT_INPUT, batch=batch, records_out=[],
                       stop="url_not_allowed", url=None)
    ident = url_identity(target)
    if ident["type"] != "status" or not ident["native_id"]:
        return _finish("comments", exit_code=EXIT_INPUT, batch=batch, records_out=[],
                       stop="unsupported_content_url", url=redact_detail(target))
    api = comments_url(ident["native_id"])
    err = _charge(batch, "comments", redact_detail(api))
    if err:
        return _finish("comments", exit_code=EXIT_BUDGET, batch=batch, records_out=[],
                       stop=f"budget:{err.code}", url=redact_detail(target))
    denial = _platform_charge(platform, batch_id, "comments", redact_detail(api),
                              metered=_is_metered_transport(transport))
    if denial:
        return _finish("comments", exit_code=EXIT_BUDGET, batch=batch, records_out=[],
                       stop=denial, url=redact_detail(target))
    result = transport.fetch(api)
    reason, locks = _risk_or_error(result)
    if locks:
        batch.lock(reason, source="comments")
        try:
            _platform_lock(platform, reason, "weibo.comments")
        except Exception:  # noqa: BLE001
            return _finish("comments", exit_code=EXIT_BUDGET, batch=batch,
                           records_out=[], stop="platform:lock_write_failed",
                           url=redact_detail(target))
        return _finish("comments", exit_code=EXIT_RISK, batch=batch, records_out=[],
                       stop=reason, url=redact_detail(target), api=redact_detail(api),
                       diagnostics=_merge_diagnostics(result, {}))
    if reason:
        batch.note("transport_error", reason)
        return _finish("comments", exit_code=EXIT_TRANSPORT, batch=batch, records_out=[],
                       stop=reason, url=redact_detail(target), api=redact_detail(api))
    parsed = parse_comments_json(result.get("json") if result.get("json") is not None
                                 else (result.get("text") or ""),
                                 content_id=ident["native_id"],
                                 collected_at=collected_at, limit=limit)
    found = parsed["records"]
    if parsed.get("stop") == "unsupported":
        return _finish("comments", exit_code=EXIT_UNSUPPORTED, batch=batch, records_out=[],
                       stop="unsupported", url=redact_detail(target), api=redact_detail(api),
                       diagnostics=_merge_diagnostics(result, parsed))
    if not found:
        return _finish("comments", exit_code=EXIT_EMPTY, batch=batch, records_out=[],
                       stop="empty", url=redact_detail(target), api=redact_detail(api),
                       parsed_structure=parsed["structure"],
                       diagnostics=_merge_diagnostics(result, parsed))
    denial = _platform_reserve(platform, batch_id, len(found))
    if denial:
        return _finish("comments", exit_code=EXIT_BUDGET, batch=batch, records_out=[],
                       stop=denial, url=redact_detail(target), api=redact_detail(api),
                       diagnostics=_merge_diagnostics(result, parsed))
    err = budget_mod_error(lambda: batch.reserve_records(len(found)))
    if err:
        return _finish("comments", exit_code=EXIT_BUDGET, batch=batch, records_out=[],
                       stop=f"budget:{err.code}", url=redact_detail(target))
    batch.note("comments_result", json.dumps({"count": len(found)}))
    exit_code = EXIT_PARTIAL if parsed.get("stop") == "unknown_objects" else EXIT_OK
    return _finish("comments", exit_code=exit_code, batch=batch, records_out=found,
                   stop=parsed.get("stop"), url=redact_detail(target), api=redact_detail(api),
                   parsed_structure=parsed["structure"], is_end=parsed.get("is_end"),
                   next_offset=parsed.get("next_offset"),
                   unknown_objects=parsed.get("unknown_objects"),
                   diagnostics=_merge_diagnostics(result, parsed))


def _is_metered_transport(transport) -> bool:
    """Only a transport that provably refuses the network is exempt.

    Capability, not class identity: `offline = True` is set by RefusedTransport
    (no socket, ever). Everything else must present a platform ledger.
    """
    return type(transport) is not transport_mod.RefusedTransport


def _open_guard():
    """Adapter seam: the CLI opens the fixed-path ledger; tests patch this."""
    return platform_mod.open_default()


def platform_budget_error():
    """The exception type to catch, resolved lazily to avoid a hard import cycle."""
    return platform_mod.PlatformBudgetError


def redact_detail(url: str) -> str:
    """Persistent logs keep scheme://host/path only: no query, no fragment.

    Search keywords and tokens live in the query string, so dropping the whole
    query (not just a few keys) is the only safe rule.
    """
    parts = urllib.parse.urlsplit(str(url or ""))
    if not parts.scheme or not parts.netloc:
        return ""
    return f"{parts.scheme}://{parts.netloc}{parts.path}"


def _platform_charge(platform, batch_id, kind: str, detail: str, *, metered: bool):
    """Charge before the action, or refuse.

    `metered=True` means the caller is about to touch the real site (a real
    browser transport, or a login window). Such a call without a guard is a
    bypass attempt and is refused; only explicitly unmetered callers (offline /
    fake transports used by tests) may run without a ledger.
    """
    if platform is None:
        return "platform:guard_required" if metered else None
    try:
        platform.charge(batch_id or "", kind, detail=redact_detail(detail),
                        source=f"weibo.{kind}")
    except platform_mod.PlatformBudgetError as exc:
        return f"platform:{exc.code}"
    return None


def _reserve_fields(batch, count: int) -> dict:
    """记录数软目标的四字段（与 CLI 输出同源：都取自 batch.snapshot()）。"""
    snap = batch.snapshot()
    target = int(snap.get("records_max") or snap.get("records_target") or 0)
    used = int(snap.get("records") or 0)
    return {"records_target": target, "records_used": used,
            "over_cap": used > target, "over_by": max(0, used - target)}


def _platform_reserve(platform, batch_id, count: int):
    """Atomically reserve record quota before any record is emitted.

    Returns a stop reason when the platform cap (5, shared by every state dir)
    would be exceeded, so the caller emits nothing rather than over-reporting.
    """
    if platform is None:
        return "platform:guard_required"
    if count <= 0:
        return None
    try:
        platform.reserve_records(batch_id or "", count, source="weibo.records")
    except platform_mod.PlatformBudgetError as exc:
        return f"platform:{exc.code}"
    except Exception as exc:  # noqa: BLE001 - an unverifiable quota must stop output
        return f"platform:reserve_failed:{type(exc).__name__}"
    return None


def _platform_lock(platform, reason: str, source: str) -> None:
    """Persist a risk lock; a write failure propagates so the caller can stop."""
    if platform is None:
        return
    platform.lock(reason, source=source)


def _platform_result(platform, batch_id, kind: str, exit_code: int):
    """Record success/failed/unknown after a charged action. Never refunds.

    Returns a stop reason when the write fails: an unrecorded charged call must
    surface, not pass silently as a success.
    """
    if platform is None:
        return "platform:guard_required"
    outcome = ("success" if exit_code == EXIT_OK
               else "unknown" if exit_code in (EXIT_PARTIAL, EXIT_TRANSPORT)
               else "failed")
    try:
        platform.record_result(batch_id or "", kind, outcome)
    except Exception as exc:  # noqa: BLE001 - never re-run the call itself
        return f"platform:result_write_failed:{type(exc).__name__}"
    return None


def budget_mod_error(fn):
    """Run a budget step; a refusal comes back as the error, never as I/O."""
    try:
        fn()
        return None
    except budget_mod.BudgetError as exc:
        return exc


# --------------------------------------------------------------------------
# export (local only, same whitelist as the Zhihu adapter)
# --------------------------------------------------------------------------
def export(input_path, output_path=None, *, fmt: str = "jsonl",
           collected_at: str | None = None) -> dict:
    """One exporter for every adapter: Zhihu's whitelist and report shape.

    This used to be a near-copy of `zhihu.export` with drifted report fields
    (`dropped_keys` list vs counts, `unsupported` int vs id list). Two platforms
    reporting the same export differently is a silent cross-platform bug, so the
    Weibo side now delegates to the accepted Zhihu implementation unchanged.
    """
    return export_records(input_path, output_path, fmt=fmt, collected_at=collected_at)


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="weibo", description="Weibo access (offline by default)")
    parser.add_argument("--state-dir", required=True)
    parser.add_argument("--profile", default=str(DEFAULT_PROFILE))
    parser.add_argument("--batch-id")
    parser.add_argument("--mode", choices=("offline", "public-http", "authenticated-browser"),
                        default="offline")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("doctor", help="local read-only profile/cookie-NAME report (no network)")

    login_p = sub.add_parser("login", help="open a visible window for the user to sign in")
    login_p.add_argument("--timeout", type=float, default=300.0)
    login_p.add_argument("--headless", action="store_true")
    login_p.add_argument("--check-session", action="store_true",
                         help="only navigate https://weibo.com/ and judge the session "
                              "(no passport fallback, no reopen)")

    for name in ("search", "detail", "comments"):
        command = sub.add_parser(name)
        command.add_argument("--limit", type=int, default=5)
        command.add_argument("--diagnostics-dir")
        command.add_argument("--timeout", type=float, default=60.0)
        command.add_argument("--visible", action="store_true")
        command.add_argument("--user-agent", default=None,
                             help="override the site User-Agent (default: the mobile UA)")
    sub.choices["search"].add_argument("keyword")
    sub.choices["detail"].add_argument("url")
    sub.choices["comments"].add_argument("url")

    export_p = sub.add_parser("export", help="normalize local records into an export")
    export_p.add_argument("--input", required=True)
    export_p.add_argument("--output")
    export_p.add_argument("--format", choices=("jsonl", "json"), default="jsonl")

    budget_p = sub.add_parser("budget", help="show the persisted budget snapshot")
    budget_p.add_argument("--ledger", type=int, default=0)
    return parser


def _emit(payload) -> None:
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str))


def _platform_gate(args, guard) -> dict | None:
    """Deny before any network unless this batch is explicitly authorized.

    The platform ledger is site-scoped and path-fixed, so a different
    `--state-dir` cannot reset the count or the lock. Returning a payload here
    means "no transport may be built".
    """
    is_locked, reason = guard.locked()
    if is_locked:
        return {"command": args.command, "ok": False, "exit": EXIT_BUDGET,
                "stop": f"platform:locked:{reason}"}
    if getattr(args, "mode", "offline") == "offline" and args.command != "login":
        return None                      # refused transport: no network anyway
    batch_id = getattr(args, "batch_id", None)
    if not batch_id:
        return {"command": args.command, "ok": False, "exit": EXIT_BUDGET,
                "stop": "platform:batch_id_required"}
    summary = guard.summary(batch_id)
    if not summary.get("authorized"):
        return {"command": args.command, "ok": False, "exit": EXIT_BUDGET,
                "stop": "platform:no_authorized_batch", "platform": summary}
    return None


def _make_transport(args):
    if getattr(args, "mode", "offline") == "authenticated-browser":
        site = SITE
        override = getattr(args, "user_agent", None)
        if override:
            site = SITE.with_user_agent(override)
        return transport_mod.AuthenticatedBrowserTransport(
            args.profile, headless=not getattr(args, "visible", False),
            timeout=getattr(args, "timeout", None) or 60.0,
            allowed_host_suffix=ALLOWED_HOST, site=site)
    if getattr(args, "mode", "offline") == "public-http":
        return transport_mod.PublicHttpTransport()
    return transport_mod.RefusedTransport()


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    state_dir = pathlib.Path(args.state_dir)

    if args.command == "doctor":
        _emit({"command": "doctor", "ok": True, "exit": EXIT_OK, **doctor(args.profile)})
        return EXIT_OK

    if args.command == "export":
        payload = export(args.input, args.output, fmt=args.format)
        _emit({"command": "export", "ok": payload["ok"], "exit": payload["exit"],
               "count": payload["count"], "output": payload.get("output"),
               "dropped_keys": payload.get("dropped_keys"),
               "url_query_stripped": payload.get("url_query_stripped"),
               "evidence_rejected": payload.get("evidence_rejected"),
               "unsupported": payload.get("unsupported"),
               "error": payload.get("error")})
        return int(payload["exit"])

    if args.command == "budget":
        snapshot = budget_mod.peek(state_dir)
        payload = {"command": "budget", "ok": snapshot is not None, "exit": EXIT_OK,
                   "budget": snapshot}
        if args.ledger and snapshot:
            payload["ledger"] = budget_mod.read_ledger(state_dir, args.ledger)
        _emit(payload)
        return EXIT_OK

    try:
        batch = budget_mod.open_budget(state_dir, batch_id=args.batch_id)
    except budget_mod.BudgetError as exc:
        _emit({"command": args.command, "ok": False, "exit": EXIT_BUDGET,
               "stop": f"budget:{exc.code}", "detail": exc.detail,
               "budget": budget_mod.peek(state_dir)})
        return EXIT_BUDGET

    guard = None
    if args.command in ("login", "search", "detail", "comments"):
        guard = _open_guard()
        denial = _platform_gate(args, guard)
        if denial is not None:
            guard.close()
            batch.close()
            _emit(denial)
            return EXIT_BUDGET

    if args.command == "login":
        try:
            payload = login(args.profile, budget=batch, timeout=args.timeout,
                            headless=args.headless,
                            check_session=getattr(args, "check_session", False),
                            platform=guard, batch_id=args.batch_id)
        finally:
            batch.close()
        _emit({"command": "login", **payload})
        return int(payload.get("exit", EXIT_TRANSPORT))

    transport = None
    try:
        collected_at = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        transport = _make_transport(args)
        if args.command == "search":
            payload = run_search(args.keyword, batch=batch, transport=transport,
                                 collected_at=collected_at, limit=args.limit,
                                 platform=guard, batch_id=args.batch_id)
        elif args.command == "detail":
            payload = run_detail(args.url, batch=batch, transport=transport,
                                 collected_at=collected_at,
                                 platform=guard, batch_id=args.batch_id)
        elif args.command == "comments":
            payload = run_comments(args.url, batch=batch, transport=transport,
                                   collected_at=collected_at, limit=args.limit,
                                   platform=guard, batch_id=args.batch_id)
        else:  # pragma: no cover - argparse rejects anything else
            raise SystemExit(64)
    finally:
        try:
            if transport is not None and hasattr(transport, "close"):
                transport.close()
        finally:
            if guard is not None:
                guard.close()
            batch.close()

    diag_dir = getattr(args, "diagnostics_dir", None)
    if diag_dir:
        _write_diagnostics(diag_dir, payload)
    _emit(payload)
    return int(payload.get("exit", EXIT_TRANSPORT))


def _write_diagnostics(directory, payload: dict) -> None:
    """Redacted skeleton only: whitelist + shapes; never page text or ids."""
    diag = diag_mod.sanitize(payload.get("diagnostics") or {})
    diag.setdefault("parse_state", payload.get("stop") or "unknown")
    target = pathlib.Path(directory)
    target.mkdir(parents=True, exist_ok=True)
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    name = f"{payload.get('command', 'run')}-{stamp}.json"
    (target / name).write_text(json.dumps(diag, ensure_ascii=False, indent=1,
                                          sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
