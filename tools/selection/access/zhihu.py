"""Zhihu read-only adapter: URL/domain rules, structure parsers, doctor, export.

Nothing here opens a network connection by itself. `run_*` functions take a
transport, charge the durable budget first, and hand the fetched text to a
parser. No browser, no login, no real request happens in this batch.

Structure sources are recorded in docs/validation/v10/zhihu/RESEARCH.md:
search_v3 / comment_v5 field names are copied from MediaCrawler's Zhihu client
(source observation, not a live Zhihu response); the HTML link fallback is a
deliberate assumption that must be corrected on the first real page.
"""

from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import json
import pathlib
import re
import sqlite3
import sys
import time
import urllib.parse
from html.parser import HTMLParser

from . import budget as budget_mod
from . import codes
from . import diagnostics as diag_mod
from . import records as rec
from . import transport as transport_mod

BASE = "https://www.zhihu.com"
ALLOWED_HOST = "zhihu.com"
DEFAULT_PROFILE = pathlib.Path(r"C:\Users\19183\.dsh\tools\zhihu-collect\profile")
REPO = pathlib.Path(__file__).resolve().parents[3]
DEFAULT_STATE = REPO / "tools" / "selection" / "access" / "runtime"
COOKIE_NAMES = ("z_c0", "d_c0", "_xsrf", "__zse_ck", "q_c1", "SESSIONID")

#: Phrases that stop a batch. A bare "登录" nav link is deliberately absent:
#: every page has one, and treating it as a wall is the XHS mistake repeated.
RISK_MARKERS = ("安全验证", "验证码", "captcha", "unhuman", "访问异常", "操作频繁",
                "请求过于频繁", "系统检测到", "请登录后查看", "登录后查看",
                "请先登录", "请登录知乎")

#: Login page only: real walls, not normal sign-in copy. The sign-in page
#: legitimately shows "获取验证码 / 短信验证码", so a bare "验证码" must never
#: close the window the user is supposed to scan (same false-positive class as
#: the XHS risk bug). "captcha" stays only as a DOM-ish marker.
LOGIN_WALL_MARKERS = ("安全验证", "访问异常", "操作频繁", "请求过于频繁",
                      "unhuman", "系统检测到", "captcha")

#: Transport prefix for a real wall observed in the DOM (`browser:risk:text:验证码`).
#: Same lock semantics as 403/429: the batch is durably blocked, not just
#: exited non-zero. Plan P5: 风控即停、非零退出、不自动重试.
RISK_ERROR_PREFIX = "browser:risk:"

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
# small helpers
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


def search_url(keyword: str) -> str:
    return f"{BASE}/search?type=content&q={urllib.parse.quote_plus(keyword)}"


def as_int(value):
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    text = str(value).replace(",", "").replace("，", "").strip()
    match = re.match(r"^(-?\d+(?:\.\d+)?)\s*([万wWkK]?)$", text)
    if not match:
        return None
    number = float(match.group(1))
    suffix = match.group(2).lower()
    if suffix in ("万", "w"):
        number *= 10000
    elif suffix == "k":
        number *= 1000
    return int(number)


def unix_to_iso(value):
    try:
        stamp = int(value)
    except (TypeError, ValueError):
        return None
    if stamp <= 0:
        return None
    try:
        return dt.datetime.fromtimestamp(stamp, dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    except (OverflowError, OSError, ValueError):
        return None


def detect_login_wall(text: str) -> str | None:
    """Risk scan for the **login page only**.

    Deliberately narrower than `detect_risk`: the sign-in page's own copy
    ("获取验证码", "短信验证码") must not be treated as a wall, otherwise the
    window closes before the user can scan. Real walls (安全验证/访问异常/
    操作频繁/captcha) still stop the flow.
    """
    lowered = rec.collapse(text).lower()
    for marker in LOGIN_WALL_MARKERS:
        if marker.lower() in lowered:
            return f"text:{marker}"
    return None


def detect_risk(text: str, status=None) -> str | None:
    """Marker scan over a plain string. HTTP 403/429 is risk by itself."""
    if status in (403, 429):
        return f"http_{status}"
    lowered = rec.collapse(text).lower()
    for marker in RISK_MARKERS:
        if marker.lower() in lowered:
            return f"text:{marker}"
    return None


def html_risk(html: str) -> str | None:
    """Risk decision for an HTML page: does it look like a wall, not like content?

    Primary signal is *rendered content*, not keywords: a wall/captcha page has
    no real `og:description`, a normal answer page always has one. So a page
    that carries a description is never treated as a wall — otherwise a Zhihu
    question whose title is literally "知乎老是弹验证码怎么办" would lock the
    batch, which is the XHS false-positive pattern in a new place. Only pages
    without a description fall through to the title/body marker scan.
    """
    tags = rec.meta_tags(html or "")
    meta = tags["meta"]
    if rec.collapse(meta.get("og:description") or meta.get("description")):
        return None
    headline = f"{tags['title']} {meta.get('og:title', '')}"
    return detect_risk(headline) or detect_risk(rec.strip_tags(str(html or ""))[:20000])


def url_identity(url: str) -> dict:
    """(type, native_id, parent_id) from a Zhihu URL; nothing guessed."""
    path = urllib.parse.urlsplit(str(url or "")).path
    out = {"type": None, "native_id": None, "parent_id": None, "evidence": None}
    m = re.search(r"/question/(\d+)/answer/(\d+)", path)
    if m:
        return {"type": "answer", "native_id": m.group(2), "parent_id": m.group(1),
                "evidence": "url:/question/<qid>/answer/<aid>"}
    m = re.search(r"/p/(\d+)", path)
    if m:
        return {"type": "article", "native_id": m.group(1), "parent_id": None,
                "evidence": "url:/p/<id>"}
    m = re.search(r"/zvideo/(\d+)", path)
    if m:
        return {"type": "zvideo", "native_id": m.group(1), "parent_id": None,
                "evidence": "url:/zvideo/<id>"}
    m = re.search(r"/question/(\d+)", path)
    if m:
        return {"type": "question", "native_id": m.group(1), "parent_id": None,
                "evidence": "url:/question/<qid>"}
    return out


def _evidence(values: dict, paths: dict) -> dict:
    return {field: (paths.get(field) if values.get(field) is not None else None)
            for field in rec.FIELDS}


# --------------------------------------------------------------------------
# parsers
# --------------------------------------------------------------------------
def _content_values(obj: dict) -> tuple[dict, dict, str | None]:
    """One search/detail object -> (values, evidence paths, kind|None)."""
    kind = rec.collapse(obj.get("type")).lower()
    question = obj.get("question") if isinstance(obj.get("question"), dict) else {}
    if kind == "answer" or (not kind and question.get("id")):
        aid = rec.collapse(obj.get("id"))
        qid = rec.collapse(question.get("id"))
        values = {
            "native_id": aid or None, "type": "answer", "parent_id": qid or None,
            "url": f"{BASE}/question/{qid}/answer/{aid}" if aid and qid else None,
            "title": rec.collapse(question.get("name") or question.get("title")) or None,
            "text": rec.strip_tags(obj.get("content") or obj.get("excerpt")) or None,
            "published_at": unix_to_iso(obj.get("created_time") or obj.get("created")),
            "voteup": as_int(obj.get("voteup_count")),
            "comments": as_int(obj.get("comment_count")),
            "likes": None,
        }
        paths = {"native_id": "json:object.id", "type": "json:object.type",
                 "parent_id": "json:object.question.id",
                 "url": "derived:question.id+answer.id",
                 "title": "json:object.question.name",
                 "text": "json:object.content",
                 "published_at": "json:object.created_time",
                 "voteup": "json:object.voteup_count",
                 "comments": "json:object.comment_count"}
        return values, paths, "answer"
    if kind == "article" or (not kind and obj.get("title") and obj.get("content")):
        aid = rec.collapse(obj.get("id"))
        values = {
            "native_id": aid or None, "type": "article", "parent_id": None,
            "url": f"{BASE}/p/{aid}" if aid else None,
            "title": rec.collapse(obj.get("title")) or None,
            "text": rec.strip_tags(obj.get("content")) or None,
            "published_at": unix_to_iso(obj.get("created") or obj.get("created_time")),
            "voteup": as_int(obj.get("voteup_count")),
            "comments": as_int(obj.get("comment_count")),
            "likes": None,
        }
        paths = {"native_id": "json:object.id", "type": "json:object.type",
                 "url": "derived:article.id", "title": "json:object.title",
                 "text": "json:object.content",
                 "published_at": "json:object.created",
                 "voteup": "json:object.voteup_count",
                 "comments": "json:object.comment_count"}
        return values, paths, "article"
    if kind == "zvideo":
        vid = rec.collapse(obj.get("id"))
        values = {
            "native_id": vid or None, "type": "zvideo", "parent_id": None,
            "url": f"{BASE}/zvideo/{vid}" if vid else None,
            "title": rec.collapse(obj.get("title")) or None,
            "text": None,
            "published_at": unix_to_iso(obj.get("created") or obj.get("created_time")),
            "voteup": as_int(obj.get("voteup_count")),
            "comments": as_int(obj.get("comment_count")),
            "likes": None,
        }
        paths = {"native_id": "json:object.id", "type": "json:object.type",
                 "url": "derived:zvideo.id", "title": "json:object.title",
                 "published_at": "json:object.created",
                 "voteup": "json:object.voteup_count",
                 "comments": "json:object.comment_count"}
        return values, paths, "zvideo"
    return {}, {}, None


#: the shared anchor parser, with Zhihu''s content-path pattern as its default
_Links = rec.Links


def parse_search_html(html: str, *, collected_at: str, limit: int = 5) -> dict:
    """HTML fallback.

    The **web state** (what the page showed) and the **parse state** (what the
    fallback could read) are reported separately: an empty document or a page
    whose anchors do not match the assumed content paths is *not* evidence that
    the content is readable, so it never claims `html:links`.
    """
    if not (html or "").strip():
        return {"records": [], "stop": "empty", "structure": "html:empty",
                "web_state": "empty_document", "anchors_total": 0,
                "anchors_recognized": 0, "anchors_rejected": 0}
    parser = _Links()
    try:
        parser.feed(html or "")
        parser.close()
    except Exception:  # noqa: BLE001 - malformed markup is not a crash
        return {"records": [], "stop": "parse_error", "structure": "html:unknown",
                "web_state": "parse_error", "anchors_total": parser.total,
                "anchors_recognized": len(parser.items), "anchors_rejected": parser.rejected}
    if not parser.items:
        # anchors exist but none matched the assumed content paths: the real
        # reason is unknown, and saying "empty" would hide that.
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
                                   collected_at=collected_at,
                                   source="zhihu:html:links"))
        if len(out) >= limit:
            break
    return {"records": out, "stop": None if out else "empty", "structure": "html:links",
            "web_state": "anchors_recognized", "anchors_total": parser.total,
            "anchors_recognized": len(parser.items), "anchors_rejected": parser.rejected}


def parse_search(payload, *, collected_at: str, limit: int = 5) -> dict:
    """search_v3 JSON (dict) or page HTML (str). Unknown shapes never invent fields."""
    if isinstance(payload, str):
        return parse_search_html(payload, collected_at=collected_at, limit=limit)
    if not isinstance(payload, dict):
        return {"records": [], "stop": "unsupported", "structure": "unknown"}
    data = payload.get("data")
    if not isinstance(data, list):
        return {"records": [], "stop": "unsupported", "structure": "json:unknown"}
    out: list[dict] = []
    unknown = 0
    for item in data:
        if not isinstance(item, dict):
            unknown += 1
            continue
        obj = item.get("object") if isinstance(item.get("object"), dict) else item
        values, paths, kind = _content_values(obj)
        if kind is None or not values.get("native_id") or not (values.get("title")
                                                               or values.get("text")):
            unknown += 1
            continue
        out.append(rec.make_record(values=values, evidence=_evidence(values, paths),
                                   collected_at=collected_at,
                                   source=f"zhihu:search_v3:{kind}"))
        if len(out) >= limit:
            break
    stop = None
    if not out:
        stop = "unsupported" if unknown else "empty"
    elif unknown:
        stop = "unknown_objects"  # usable records kept, but not a clean success
    return {"records": out, "stop": stop, "structure": "json:search_v3",
            "unknown_objects": unknown,
            "is_end": bool((payload.get("paging") or {}).get("is_end"))}


def parse_detail(html: str, url: str, *, collected_at: str) -> dict:
    ident = url_identity(url)
    tags = rec.meta_tags(html or "")
    meta = tags["meta"]
    title = rec.collapse(meta.get("og:title") or tags["title"])
    title = re.sub(r"\s*[-|]\s*知乎\s*$", "", title) or None
    description = rec.collapse(meta.get("og:description") or meta.get("description")) or None
    # a wall/captcha page has no real description; a normal page does, so the
    # body scan inside html_risk only fires when there is nothing else to go on
    reason = html_risk(html or "")
    if reason:
        return {"record": None, "stop": reason, "structure": "html:meta"}
    published, published_path = None, None
    for key in ("article:published_time", "og:article:published_time", "datepublished"):
        if meta.get(key):
            published, published_path = rec.collapse(meta[key]), f"meta:{key}"
            break
    if not published:
        match = re.search(r'<meta[^>]+itemprop=["\']dateCreated["\'][^>]+content=["\']([^"\']+)',
                          html or "", re.I)
        if match:
            published, published_path = rec.collapse(match.group(1)), "meta:itemprop=dateCreated"
    voteup = None
    comments = None
    body_text = rec.strip_tags(html or "")[:20000]
    match = re.search(r"([0-9][0-9,\.]*\s*[万wWkK]?)\s*赞同", body_text)
    if match:
        voteup = as_int(match.group(1).replace(" ", ""))
    match = re.search(r"([0-9][0-9,\.]*\s*[万wWkK]?)\s*条评论", body_text)
    if match:
        comments = as_int(match.group(1).replace(" ", ""))
    if not ident["native_id"] or not (title or description):
        return {"record": None, "stop": "unsupported", "structure": "html:meta"}
    values = {"native_id": ident["native_id"], "type": ident["type"],
              "parent_id": ident["parent_id"], "url": url,
              "title": title, "text": description, "published_at": published,
              "voteup": voteup, "comments": comments, "likes": None}
    paths = {"native_id": ident["evidence"], "type": ident["evidence"],
             "parent_id": ident["evidence"], "url": "input:url",
             "title": "meta:og:title" if meta.get("og:title") else "html:title",
             "text": "heuristic:meta og:description (may be truncated)",
             "published_at": published_path,
             "voteup": "heuristic:visible text '赞同'",
             "comments": "heuristic:visible text '条评论'"}
    record = rec.make_record(values=values, evidence=_evidence(values, paths),
                             collected_at=collected_at, source=f"zhihu:detail:{ident['type']}")
    return {"record": record, "stop": None, "structure": "html:meta"}


def parse_comments(payload, *, content_id: str, collected_at: str,
                   parent_id: str | None = None, limit: int = 5) -> dict:
    """comment_v5 root/child payload -> comment records with real parent ids."""
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except json.JSONDecodeError:
            return {"records": [], "stop": "unsupported", "structure": "json:unknown"}
    if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
        return {"records": [], "stop": "unsupported", "structure": "json:comment_v5"}
    out: list[dict] = []
    unknown = 0
    for item in payload["data"]:
        if not isinstance(item, dict):
            unknown += 1
            continue
        cid = rec.collapse(item.get("id"))
        text = rec.strip_tags(item.get("content"))
        if not cid or not text:
            unknown += 1
            continue
        values = {"native_id": cid, "type": "comment",
                  "parent_id": parent_id or content_id, "url": None,
                  "title": None, "text": text,
                  "published_at": unix_to_iso(item.get("created_time") or item.get("created")),
                  "voteup": None,
                  "likes": as_int(item.get("vote_count")),
                  "comments": as_int(item.get("child_comment_count"))}
        paths = {"native_id": "json:data[].id", "type": "constant:comment",
                 "parent_id": "input:parent_id" if parent_id else "input:content_id",
                 "text": "json:data[].content",
                 "published_at": "json:data[].created_time",
                 "likes": "json:data[].vote_count",
                 "comments": "json:data[].child_comment_count"}
        out.append(rec.make_record(values=values, evidence=_evidence(values, paths),
                                   collected_at=collected_at, source="zhihu:comment_v5"))
        if len(out) >= limit:
            break
    paging = payload.get("paging") or {}
    stop = None
    if not out:
        stop = "unsupported" if unknown else "empty"
    elif unknown:
        stop = "unknown_objects"  # usable records kept, but not a clean success
    return {"records": out, "stop": stop, "structure": "json:comment_v5",
            "unknown_objects": unknown, "is_end": bool(paging.get("is_end")),
            "next_offset": paging.get("next")}


# --------------------------------------------------------------------------
# doctor / login (local only; login is implemented but not run in this batch)
# --------------------------------------------------------------------------
def doctor(profile=DEFAULT_PROFILE) -> dict:
    """Read-only: profile dir + cookie NAMES only. Never launches a browser."""
    profile = pathlib.Path(profile)
    cookies = profile / "Default" / "Network" / "Cookies"
    out = {"profile": str(profile), "profile_exists": profile.is_dir(),
           "cookie_db_exists": cookies.is_file(), "cookie_names": {}, "online": "unverified",
           "network": "none", "note": "cookie names only; presence is not proof of a valid session"}
    if not out["cookie_db_exists"]:
        return out
    conn = _open_readonly(cookies)
    if conn is None:
        out["error"] = "cookie_db_open_failed"
        return out
    try:
        rows = conn.execute(
            "SELECT DISTINCT name FROM cookies WHERE host_key LIKE '%zhihu.com%'").fetchall()
    except sqlite3.Error as exc:
        out["error"] = f"cookie_db_read_failed:{type(exc).__name__}"
        return out
    finally:
        conn.close()
    names = {rec.collapse(row[0]) for row in rows if row and row[0]}
    out["cookie_names"] = {name: (name in names) for name in COOKIE_NAMES}
    out["cookie_count"] = len(names)
    return out


def _open_readonly(path: pathlib.Path):
    """Open an existing sqlite file read-only. Never creates, never migrates."""
    try:
        uri = pathlib.Path(path).resolve().as_uri()
    except (ValueError, OSError):
        return None
    for suffix in ("?mode=ro&immutable=1", "?mode=ro"):
        try:
            return sqlite3.connect(uri + suffix, uri=True, timeout=3.0)
        except sqlite3.Error:
            continue
    return None


def _z_c0_seen(profile) -> bool:
    """True when a `z_c0` cookie **name** exists in the profile DB (names only)."""
    db = pathlib.Path(profile) / "Default" / "Network" / "Cookies"
    if not db.is_file():
        return False
    conn = _open_readonly(db)
    if conn is None:
        return False
    try:
        rows = conn.execute(
            "SELECT DISTINCT name FROM cookies WHERE host_key LIKE '%zhihu.com%'").fetchall()
    except sqlite3.Error:
        return False
    finally:
        conn.close()
    return "z_c0" in {row[0] for row in rows if row[0]}


def _with_session_cookie(profile, payload: dict) -> dict:
    """`z_c0` decides the verdict; page markers alone are not a login.

    - page looked signed in but no z_c0 -> `unknown` (non-zero), never success;
    - z_c0 appeared during the window even if the page was slow -> `ok`.
    """
    seen = _z_c0_seen(profile)
    out = {**payload, "session_cookie": seen, "session_cookie_name": "z_c0",
           "charged": False}
    status = payload.get("status")
    if status == "ok" and not seen:
        out.update({"status": "unknown", "exit": EXIT_LOGIN_UNKNOWN,
                    "signed_in": False, "stop": "page_signed_in_but_z_c0_false"})
    elif seen and status in ("timeout", "poll_limit", "unknown"):
        out.update({"status": "ok", "exit": EXIT_OK, "signed_in": True,
                    "stop": "session_cookie_seen"})
    return out


def login(profile=DEFAULT_PROFILE, *, budget, clock=None, timeout: float = 300.0,
          headless: bool = False, browser=None) -> dict:
    """Open a visible window for the user to sign in. Never fills credentials.

    Returns one of ok / timeout / poll_limit / unknown / risk / locked /
    budget_error, each with its own non-zero exit code except `ok`. Cookie
    names never decide this; only page-visible session evidence does.
    """
    from . import browser as browser_mod  # local import: nodriver is optional

    clock = clock or time.time
    if browser is None:
        info = browser_mod.available()
        if not info["usable"]:
            return {"status": "unavailable", "exit": EXIT_TRANSPORT,
                    "error": "browser_unavailable", "detail": info,
                    "profile": str(profile)}
        return _with_session_cookie(profile, _login_with_real_browser(
            profile, budget=budget, clock=clock, timeout=timeout,
            headless=headless, info=info))
    # A fake browser may implement evaluate as a coroutine (matching nodriver);
    # run the async poll loop on a private loop so `login()` stays sync for CLI.
    return asyncio.run(browser_mod.wait_for_login(
        browser, profile=profile, budget=budget, clock=clock, timeout=timeout))


def _login_with_real_browser(profile, *, budget, clock, timeout: float,
                             headless: bool, info: dict) -> dict:
    """Visible nodriver window; the verdict is `z_c0` after the window closes.

    Page markers are not used here: on an already-partially-cookied profile they
    fired within seconds while `z_c0` stayed false (2026-10-30 run), which would
    end the wait before the user could scan.
    """
    import asyncio
    import time

    import nodriver as uc
    from . import records as rec

    clock = clock or time.time
    # `uc.start` needs an absolute user_data_dir: a relative one launches and then
    # fails with "Failed to connect to browser" (verified on the Weibo probe).
    profile = pathlib.Path(profile).expanduser().resolve()
    pathlib.Path(profile).mkdir(parents=True, exist_ok=True)

    async def _run() -> dict:
        browser = await uc.start(headless=headless, user_data_dir=str(profile),
                                 browser_executable_path=info["chrome"])
        started = clock()
        polls = 0
        last_url = f"{BASE}/signin"
        try:
            await browser.get(f"{BASE}/signin")
            while clock() - started < timeout:
                if _z_c0_seen(profile):
                    break
                polls += 1
                await asyncio.sleep(3.0)
        finally:
            try:
                browser.stop()
            except Exception:  # noqa: BLE001 - a dead window must not hide the verdict
                pass
        seen = _z_c0_seen(profile)          # post-close flush is the real evidence
        return {"status": "ok" if seen else "timeout",
                "exit": EXIT_OK if seen else EXIT_LOGIN_TIMEOUT,
                "signed_in": seen, "session_cookie": seen,
                "session_cookie_name": "z_c0", "polls": polls,
                "elapsed_s": round(clock() - started, 3),
                "final_url": rec.sanitize_url(last_url),
                "verdict_source": "cookie_names_after_close"}

    return asyncio.run(_run())


# --------------------------------------------------------------------------
# commands (charge the budget before every active call)
# --------------------------------------------------------------------------
def _finish(command: str, *, exit_code: int, batch, records_out: list, **extra) -> dict:
    payload = {"command": command, "ok": exit_code == EXIT_OK, "exit": exit_code,
               "records": records_out, "count": len(records_out),
               "batch": batch.snapshot() if batch is not None else None}
    payload.update(extra)
    return payload


def _attempt(fn):
    """Run a budget step; a refusal becomes (None, BudgetError), never I/O."""
    try:
        return fn(), None
    except budget_mod.BudgetError as exc:
        return None, exc


def _charge(batch, kind: str, detail: str):
    return _attempt(lambda: batch.charge(kind, detail))[1]


def _risk_or_error(result: dict) -> tuple[str | None, bool]:
    """(stop reason, locks_batch). Only risk pages, 403/429 and offsite locks."""
    error = result.get("error")
    if error:
        text = str(error)
        if text.startswith("offsite_redirect:"):
            # a page that walked us off the target domain is treated as a wall:
            # we no longer know what we are reading, and continuing is how a
            # collector ends up scraping an unvalidated host.
            return text, True
        if text.startswith(RISK_ERROR_PREFIX):
            # the transport already saw a real wall (验证码/安全验证/访问异常/
            # 操作频繁…). A non-zero exit alone is not enough: plan P5 wants the
            # batch durably locked, exactly like 403/429, or the next keyword
            # in the same run walks straight into the same captcha.
            return text, True
        return text, False  # offline refusal / timeout: never a risk signal
    status = result.get("status")
    if status in (403, 429):
        return f"http_{status}", True
    if isinstance(status, int) and status >= 400:
        return f"http_{status}", False  # 404/5xx is a transport outcome, not a risk page
    payload = result.get("json")
    if isinstance(payload, dict):
        # JSON body: an `error` field is the platform's own signal. Scanning the
        # content text here would lock the batch for a question that merely
        # *discusses* captchas, so it is deliberately not done.
        return ("api_error", True) if payload.get("error") else (None, False)
    text = str(result.get("text") or "")[:200_000]
    if "<html" in text.lower() or "<meta" in text.lower() or "<body" in text.lower():
        reason = html_risk(text)  # headline-first, body only when there is no meta
    else:
        reason = detect_risk(text)
    return (reason, True) if reason else (None, False)


def _merge_diagnostics(result: dict, parsed: dict) -> dict:
    """Transport diagnostics + parse counters -> one whitelisted record."""
    diag = dict(result.get("diagnostics") or {})
    diag["parse_state"] = parsed.get("stop") or ("records" if parsed.get("records") else "empty")
    if parsed.get("web_state"):
        diag["web_state"] = parsed["web_state"]
    diag["state"] = diag.get("state") or parsed.get("web_state") or "unknown"
    for key in ("anchors_total", "anchors_recognized", "anchors_rejected"):
        # the transport observed the live DOM, so its counters win over the
        # counters re-derived from the saved HTML
        if key not in diag and key in parsed:
            diag[key] = parsed[key]
    return diag_mod.sanitize(diag)


def run_search(keyword: str, *, batch, transport, collected_at: str,
               limit: int = 5) -> dict:
    url = search_url(keyword)
    safe_url = rec.sanitize_url(url)
    err = _charge(batch, "search", url)
    if err:
        return _finish("search", exit_code=EXIT_BUDGET, batch=batch, records_out=[],
                       keyword=keyword, stop=f"budget:{err.code}", url=safe_url)
    result = transport.fetch(url)
    reason, locks = _risk_or_error(result)
    if locks:
        batch.lock(reason, source="search")
        return _finish("search", exit_code=EXIT_RISK, batch=batch, records_out=[],
                       keyword=keyword, stop=reason, url=safe_url,
                       diagnostics=_merge_diagnostics(result, {}))
    if reason:
        batch.note("transport_error", reason)
        return _finish("search", exit_code=EXIT_TRANSPORT, batch=batch, records_out=[],
                       keyword=keyword, stop=reason, url=safe_url,
                       diagnostics=_merge_diagnostics(result, {}))
    parsed = parse_search(result.get("json") if result.get("json") is not None
                          else (result.get("text") or ""),
                          collected_at=collected_at, limit=limit)
    diagnostics = _merge_diagnostics(result, parsed)
    found = parsed["records"]
    exit_code = EXIT_OK
    if parsed.get("stop") == "unsupported":
        exit_code = EXIT_UNSUPPORTED
    elif parsed.get("stop") == "unknown":
        # the page was read but its shape is unknown: not an "empty but done"
        exit_code = EXIT_UNSUPPORTED
    elif parsed.get("stop") == "empty" or not found:
        exit_code = EXIT_EMPTY
    elif parsed.get("stop") == "unknown_objects":
        exit_code = EXIT_PARTIAL  # some objects were unusable: not a clean success
    if not found and diagnostics.get("state") in ("unknown", "loading") and (
            result.get("diagnostics") or result.get("probe")):
        # a page that never became readable must not be reported as an empty
        # *completed* search (only when the transport actually observed a page)
        exit_code = EXIT_TRANSPORT
        parsed = {**parsed, "stop": "readiness_timeout"}
    if found:
        err = _attempt(lambda: batch.reserve_records(len(found)))[1]
        if err:
            return _finish("search", exit_code=EXIT_BUDGET, batch=batch, records_out=[],
                           keyword=keyword, stop=f"budget:{err.code}", url=safe_url,
                           parsed_structure=parsed["structure"], diagnostics=diagnostics)
    batch.note("search_result", json.dumps({"count": len(found), "exit": exit_code}))
    return _finish("search", exit_code=exit_code, batch=batch, records_out=found,
                   keyword=keyword, stop=parsed.get("stop"), url=safe_url,
                   parsed_structure=parsed["structure"], is_end=parsed.get("is_end"),
                   diagnostics=diagnostics)


def run_detail(url: str, *, batch, transport, collected_at: str) -> dict:
    try:
        target = require_url(url)
    except ValueError:
        return _finish("detail", exit_code=EXIT_INPUT, batch=batch, records_out=[],
                       stop="url_not_allowed", url=None)
    err = _charge(batch, "detail", target)
    if err:
        return _finish("detail", exit_code=EXIT_BUDGET, batch=batch, records_out=[],
                       stop=f"budget:{err.code}", url=target)
    result = transport.fetch(target)
    reason, locks = _risk_or_error(result)
    if locks:
        batch.lock(reason, source="detail")
        return _finish("detail", exit_code=EXIT_RISK, batch=batch, records_out=[],
                       stop=reason, url=target)
    if reason:
        batch.note("transport_error", reason)
        return _finish("detail", exit_code=EXIT_TRANSPORT, batch=batch, records_out=[],
                       stop=reason, url=target)
    parsed = parse_detail(result.get("text") or "", target, collected_at=collected_at)
    record = parsed.get("record")
    if parsed.get("stop"):
        if parsed["stop"] == "unsupported":
            return _finish("detail", exit_code=EXIT_UNSUPPORTED, batch=batch,
                           records_out=[], stop="unsupported", url=target)
        # a wall/risk page the transport layer could not see (e.g. no meta at all)
        batch.lock(parsed["stop"], source="detail")
        return _finish("detail", exit_code=EXIT_RISK, batch=batch, records_out=[],
                       stop=parsed["stop"], url=target)
    err = _attempt(lambda: batch.reserve_records(1))[1]
    if err:
        return _finish("detail", exit_code=EXIT_BUDGET, batch=batch, records_out=[],
                       stop=f"budget:{err.code}", url=target)
    batch.note("detail_result", json.dumps({"native_id": record["native_id"]}))
    return _finish("detail", exit_code=EXIT_OK, batch=batch, records_out=[record],
                   stop=None, url=target, parsed_structure=parsed["structure"])


def comments_url(record_url: str, content_type: str, content_id: str) -> str:
    return f"{BASE}/api/v4/comment_v5/{content_type}s/{content_id}/root_comment"


def run_comments(url: str, *, batch, transport, collected_at: str,
                 limit: int = 5) -> dict:
    try:
        target = require_url(url)
    except ValueError:
        return _finish("comments", exit_code=EXIT_INPUT, batch=batch, records_out=[],
                       stop="url_not_allowed", url=None)
    ident = url_identity(target)
    if ident["type"] not in ("answer", "article", "zvideo") or not ident["native_id"]:
        return _finish("comments", exit_code=EXIT_INPUT, batch=batch, records_out=[],
                       stop="unsupported_content_url", url=target)
    api = comments_url(target, ident["type"], ident["native_id"])
    err = _charge(batch, "comments", api)
    if err:
        return _finish("comments", exit_code=EXIT_BUDGET, batch=batch, records_out=[],
                       stop=f"budget:{err.code}", url=target)
    result = transport.fetch(api)
    reason, locks = _risk_or_error(result)
    if locks:
        batch.lock(reason, source="comments")
        return _finish("comments", exit_code=EXIT_RISK, batch=batch, records_out=[],
                       stop=reason, url=target)
    if reason:
        batch.note("transport_error", reason)
        return _finish("comments", exit_code=EXIT_TRANSPORT, batch=batch, records_out=[],
                       stop=reason, url=target)
    parsed = parse_comments(result.get("json") if result.get("json") is not None
                            else (result.get("text") or ""),
                            content_id=ident["native_id"], collected_at=collected_at,
                            limit=limit)
    found = parsed["records"]
    if parsed.get("stop") == "unsupported":
        return _finish("comments", exit_code=EXIT_UNSUPPORTED, batch=batch, records_out=[],
                       stop="unsupported", url=target, api=api)
    if not found:
        return _finish("comments", exit_code=EXIT_EMPTY, batch=batch, records_out=[],
                       stop="empty", url=target, api=api, is_end=parsed.get("is_end"))
    err = _attempt(lambda: batch.reserve_records(len(found)))[1]
    if err:
        return _finish("comments", exit_code=EXIT_BUDGET, batch=batch, records_out=[],
                       stop=f"budget:{err.code}", url=target, api=api)
    batch.note("comments_result", json.dumps({"count": len(found)}))
    exit_code = EXIT_PARTIAL if parsed.get("stop") == "unknown_objects" else EXIT_OK
    return _finish("comments", exit_code=exit_code, batch=batch, records_out=found,
                   stop=parsed.get("stop"), url=target, api=api,
                   parsed_structure=parsed["structure"],
                   is_end=parsed.get("is_end"), next_offset=parsed.get("next_offset"),
                   unknown_objects=parsed.get("unknown_objects"))


# --------------------------------------------------------------------------
# export
# --------------------------------------------------------------------------
def export(input_path, output_path=None, *, fmt: str = "jsonl",
           collected_at: str | None = None) -> dict:
    """Local records -> whitelisted export.

    `normalize_record` never copies the input, so unknown/nested credential or
    nickname fields cannot survive; here we only count what was thrown away so
    the drop is visible instead of silent.
    """
    try:
        raw = rec.read_records(input_path)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return {"ok": False, "exit": EXIT_EXPORT, "error": f"read_failed:{type(exc).__name__}",
                "count": 0, "records": []}
    cleaned = []
    dropped_keys: dict[str, int] = {}
    stripped_query = 0
    rejected_evidence = 0
    for item in raw:
        extra = sorted(set(item) - set(rec.EXPORT_FIELDS))
        for key in extra:
            dropped_keys[key] = dropped_keys.get(key, 0) + 1
        before = item.get("url")
        record = rec.normalize_record(item, collected_at=collected_at)
        if before and record.get("url") != before:
            stripped_query += 1
        if record.get("evidence_rejected"):
            rejected_evidence += 1
        cleaned.append(record)
    written = None
    if output_path:
        try:
            written = rec.write_records(cleaned, output_path, fmt=fmt)
        except OSError as exc:
            return {"ok": False, "exit": EXIT_EXPORT, "error": f"write_failed:{type(exc).__name__}",
                    "count": 0, "records": []}
    return {"ok": True, "exit": EXIT_OK, "count": len(cleaned), "records": cleaned,
            "output": written, "dropped_keys": dropped_keys,
            "url_query_stripped": stripped_query,
            "evidence_rejected": rejected_evidence,
            "unsupported": [r.get("native_id") for r in cleaned if not r.get("supported")]}


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------
class _OneShot:
    """Serve one offline response; never opens a socket."""

    mode = "offline"

    def __init__(self, text: str, parsed) -> None:
        self.text = text
        self.parsed = parsed
        self.urls: list[str] = []

    def fetch(self, url: str) -> dict:
        self.urls.append(url)
        return {"status": 200, "text": self.text, "json": self.parsed,
                "url": url, "final_url": url, "redirect": None, "error": None}


def _offline(path: str, *, as_json: bool) -> _OneShot:
    target = pathlib.Path(path)
    if not target.is_file():
        raise SystemExit(f"input not found: {path}")
    text = target.read_text(encoding="utf-8")
    parsed = None
    if as_json:
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            parsed = None
    return _OneShot(text, parsed)


MODES = ("offline", "public-http", "authenticated-browser")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m tools.selection.access.zhihu",
        description="Zhihu read-only access with a durable state-dir budget")
    parser.add_argument("--state-dir", default=str(DEFAULT_STATE),
                        help="runtime dir holding the budget; one dir == one budget")
    parser.add_argument("--profile", default=str(DEFAULT_PROFILE),
                        help="dedicated Chrome profile dir (never committed)")
    parser.add_argument("--batch-id", default=None,
                        help="label for this run; does NOT reset counters or locks")
    parser.add_argument("--mode", choices=MODES, default="offline",
                        help="offline (default) | public-http | authenticated-browser")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("doctor", help="local-only profile/cookie-name check")

    login = sub.add_parser("login", help="visible window for the user to sign in")
    login.add_argument("--timeout", type=float, default=300.0)
    login.add_argument("--headless", action="store_true")

    search = sub.add_parser("search", help="one search call")
    search.add_argument("keyword")
    search.add_argument("--limit", type=int, default=5)
    search.add_argument("--input", help="offline JSON/HTML response instead of a call")

    detail = sub.add_parser("detail", help="one detail page call")
    detail.add_argument("url")
    detail.add_argument("--input", help="offline HTML file instead of a call")

    comments = sub.add_parser("comments", help="one root-comment call")
    comments.add_argument("url")
    comments.add_argument("--limit", type=int, default=5)
    comments.add_argument("--input", help="offline JSON file instead of a call")

    export_p = sub.add_parser("export", help="normalize local records into an export")
    export_p.add_argument("--input", required=True)
    export_p.add_argument("--output")
    export_p.add_argument("--format", choices=("jsonl", "json"), default="jsonl")

    for name in ("search", "detail", "comments"):
        sub.choices[name].add_argument(
            "--diagnostics-dir",
            help="optional dir for a minimal, redacted diagnostic skeleton (no page text)")
        sub.choices[name].add_argument(
            "--timeout", type=float, default=60.0,
            help="total budget for one browser navigation in seconds (default 60)")
        sub.choices[name].add_argument(
            "--visible", action="store_true",
            help="open a visible browser window instead of headless (opt-in; default headless)")

    budget_p = sub.add_parser("budget", help="show the persisted budget snapshot")
    budget_p.add_argument("--ledger", type=int, default=0, help="also print N ledger rows")
    return parser


def _emit(payload) -> None:
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str))


def _make_transport(args):
    """Build the transport for this mode. Offline never opens a socket."""
    if getattr(args, "input", None):
        return _offline(args.input, as_json=args.command in ("search", "comments"))
    if args.mode == "public-http":
        return transport_mod.PublicHttpTransport()
    if args.mode == "authenticated-browser":
        return transport_mod.AuthenticatedBrowserTransport(
            args.profile, headless=not getattr(args, "visible", False),
            timeout=getattr(args, "timeout", None) or 60.0)
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
               "unsupported": payload.get("unsupported"), "error": payload.get("error")})
        return int(payload["exit"])

    if args.command == "budget":
        # inspectable even when locked, otherwise a lock hides its own cause
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

    if args.command == "login":
        try:
            payload = login(args.profile, budget=batch, timeout=args.timeout,
                            headless=args.headless)
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
                                 collected_at=collected_at, limit=args.limit)
        elif args.command == "detail":
            payload = run_detail(args.url, batch=batch, transport=transport,
                                 collected_at=collected_at)
        elif args.command == "comments":
            payload = run_comments(args.url, batch=batch, transport=transport,
                                   collected_at=collected_at, limit=args.limit)
        else:  # pragma: no cover - argparse rejects anything else
            raise SystemExit(64)
    except SystemExit as exc:  # `--input` missing: keep the message, exit 8
        payload = {"command": args.command, "ok": False, "exit": EXIT_INPUT,
                   "stop": "input_not_found", "detail": str(exc)}
        _emit(payload)
        return EXIT_INPUT
    finally:
        batch.close()
        close = getattr(transport, "close", None)
        if callable(close):
            close()

    _emit(payload)
    _write_diagnostics(args, payload)
    return int(payload["exit"])


def _write_diagnostics(args, payload: dict) -> None:
    """Optional, opt-in diagnostic skeleton. Never the page, never the text."""
    target = getattr(args, "diagnostics_dir", None)
    if not target:
        return
    diag = diag_mod.sanitize(payload.get("diagnostics") or {})
    try:
        folder = pathlib.Path(target)
        folder.mkdir(parents=True, exist_ok=True)
        name = f"{payload.get('command', 'run')}-{dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.json"
        (folder / name).write_text(json.dumps(diag, ensure_ascii=False, indent=1), encoding="utf-8")
    except OSError:
        pass  # diagnostics are best-effort; they never change the exit code


if __name__ == "__main__":
    sys.exit(main())
