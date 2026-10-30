"""Xiaohongshu read-only skeleton: fixture-driven parsing, risk stop, profile doctor.

Zero network in tests; structure assumptions must be corrected on first real collect.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import pathlib
import re
import sqlite3
import urllib.parse
import time
from html.parser import HTMLParser

from . import models

BASE = "https://www.xiaohongshu.com"
UA = "two-selection/1.0"

RISK_MARKERS = {
    "text": ("请完成安全验证", "验证码", "登录后查看", "请登录", "访问异常", "操作频繁",
             "rate limit", "captcha", "verify", "登录墙", "风控"),
    "dom": ('[data-testid*="captcha" i]', 'iframe[src*="captcha" i]',
            '[class*="captcha" i]', '[class*="login-mask" i]', '[class*="login-wall" i]',
            '[id*="captcha" i]'),
}


class RiskStop(Exception):
    """Raised when a page matches risk markers; callers must stop, never retry."""


def _stop_for(reason: str) -> dict:
    """Immediate stop payload; no retry, no collection."""
    return {"ok": False, "stop": True, "stop_reason": reason, "retry": False}


def search_url(keyword: str) -> str:
    return f"{BASE}/search_result?keyword={urllib.parse.quote_plus(keyword)}"


def _text(value) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _summary(text: str, limit: int = 200) -> str:
    text = _text(text)
    return text if len(text) <= limit else text[:limit].rstrip() + "…"


LOGIN_MARKERS = ("登录后查看", "请登录", "登录墙")
ERROR_MARKERS = ("你访问的页面不见了", "页面不见了", "笔记不存在", "404")


class _Meta(HTMLParser):
    def __init__(self):
        super().__init__()
        self.meta = {}
        self.title = ""
        self._in_title = False

    def handle_starttag(self, tag, attrs):
        a = {k: (v or "") for k, v in attrs}
        if tag == "meta":
            key = (a.get("property") or a.get("name") or "").lower()
            if key and "content" in a:
                self.meta[key] = a["content"]
        elif tag == "title":
            self._in_title = True

    def handle_data(self, data):
        if self._in_title:
            self.title += data

    def handle_endtag(self, tag):
        if tag == "title":
            self._in_title = False


class _Likes(HTMLParser):
    """Capture the first count inside a like-wrapper; ignore other counters."""
    def __init__(self):
        super().__init__()
        self.depth = 0
        self.like_depth = None
        self.target_depth = None
        self.text = ""

    def handle_starttag(self, tag, attrs):
        self.depth += 1
        a = {k: (v or "") for k, v in attrs}
        cls = (a.get("class") or "").lower()
        if self.like_depth is None and "like-wrapper" in cls:
            self.like_depth = self.depth
        if self.like_depth is not None and self.target_depth is None and "count" in cls:
            self.target_depth = self.depth

    def handle_data(self, data):
        if self.target_depth is not None and not self.text.strip():
            self.text += data

    def handle_endtag(self, tag):
        if self.target_depth == self.depth:
            self.target_depth = None
        if self.like_depth == self.depth:
            self.like_depth = None
        self.depth = max(0, self.depth - 1)


def parse_note_fields(html: str, url: str) -> dict:
    """Parse a note detail page; error/login pages are explicit, never complete."""
    p = _Meta()
    try:
        p.feed(html or "")
    except Exception:  # noqa: BLE001
        pass
    title = _text(p.meta.get("og:title") or p.meta.get("twitter:title") or p.title)
    title = re.sub(r"\s*[-|]\s*小红书.*$", "", title)
    desc = _text(p.meta.get("og:description") or p.meta.get("description"))
    author = _text(p.meta.get("og:article:author") or p.meta.get("author"))
    if not author:
        m = re.search(r'"nickname"\s*:\s*"([^"]{1,80})"', html or "")
        author = _text(m.group(1)) if m else ""
    likes = ""
    likes_path = "unavailable"
    lp = _Likes()
    try:
        lp.feed(html or "")
    except Exception:  # noqa: BLE001
        pass
    if lp.text.strip():
        likes = _text(lp.text)
        likes_path = "like-wrapper.count / engage-bar.count"
    else:
        m = re.search(r"([0-9]+(?:\.[0-9]+)?[万wW]?)\s*(?:赞|点赞)", _text(html))
        if m:
            likes = m.group(1)
            likes_path = "text:number+赞"
    native_id = ""
    m = re.search(r"/explore/([0-9A-Za-z]+)", url or "")
    if m:
        native_id = m.group(1)
    publish_time = ""
    publish_path = "unavailable"
    for key in ("article:published_time", "og:article:published_time", "datepublished"):
        val = _text(p.meta.get(key))
        if val:
            publish_time, publish_path = val, f"meta[{key}]"
            break
    if not publish_time:
        m = re.search(r'<time[^>]+datetime=["\']([^"\']+)', html or "", re.I)
        if m:
            publish_time, publish_path = _text(m.group(1)), "time[datetime]"

    comment_entry_present = bool(re.search(r'class=["\'][^"\']*comment|id=["\'][^"\']*comment|评论', html or "", re.I))
    error_page = any(m in (title + " " + desc) for m in ERROR_MARKERS)
    login_required = any(m in (title + " " + desc) for m in LOGIN_MARKERS)
    expected = ["native_id", "title", "desc", "author_redacted", "author_hash",
                "likes", "publish_time", "comment_entry_present"]
    values = {"native_id": native_id, "title": title, "desc": desc,
              "author_redacted": bool(author), "author_hash": bool(author),
              "likes": likes, "publish_time": publish_time,
              "comment_entry_present": comment_entry_present}
    found = [k for k in expected if values[k]]
    complete = bool(native_id and (title or desc) and not error_page and not login_required)
    return {"native_id": native_id, "title": title, "desc": desc, "author": author,
            "author_hash": hashlib.sha256(author.encode("utf-8")).hexdigest()[:12] if author else "",
            "author_redacted": bool(author), "likes": likes, "publish_time": publish_time,
            "likes_path": likes_path, "publish_time_path": publish_path,
            "comment_entry_present": comment_entry_present, "expected": expected, "found": found,
            "missing": [k for k in expected if k not in found],
            "error_page": error_page, "login_required": login_required, "complete": complete}


def classify_note(fields: dict) -> str:
    if fields.get("risk"):
        return "risk"
    if fields.get("error_page"):
        return "error_page"
    if fields.get("login_required"):
        return "login_required"
    if fields.get("complete"):
        return "note"
    return "incomplete"


def parse_results(html: str, *, limit: int = 10, risk_text: str | None = None,
                  risk_dom: bool = True) -> dict:
    """Parse XHS results; risk markers can be checked on visible text only."""
    text = _text(risk_text if risk_text is not None else html)
    for marker in RISK_MARKERS["text"]:
        if marker.lower() in text.lower():
            return _stop_for(f"risk_marker:{marker}")
    if risk_dom:
        try:
            from html.parser import HTMLParser as _HP

            class _Dom(_HP):
                def __init__(self):
                    super().__init__()
                    self.hit = None

                def handle_starttag(self, tag, attrs):
                    if self.hit:
                        return
                    a = {k: (v or "") for k, v in attrs}
                    hay = " ".join((a.get("class") or "", a.get("id") or "",
                                    a.get("data-testid") or "", a.get("src") or "")).lower()
                    if "captcha" in hay or "login-mask" in hay or "login-wall" in hay:
                        self.hit = True
            d = _Dom(); d.feed(html)
            if d.hit:
                return _stop_for("risk_marker:dom")
        except Exception as exc:  # noqa: BLE001
            return _stop_for(f"parse_error:{type(exc).__name__}")
    cards = []
    try:
        from html.parser import HTMLParser

        class _Real(HTMLParser):
            """Real XHS feed: section.note-item > a.title/span, a.author .name, span.count."""
            def __init__(self):
                super().__init__()
                self.cards = []
                self.cur = None
                self.mode = None
                self.buf = ""

            def handle_starttag(self, tag, attrs):
                a = {k: (v or "") for k, v in attrs}
                cls = (a.get("class") or "").lower()
                if tag == "section" and "note-item" in cls:
                    self.cur = {"note_id": None, "url": "", "title": "", "text": "",
                                "author": "", "likes": ""}
                    self.mode = None
                if self.cur is None:
                    return
                if tag == "a" and any(x in (a.get("href") or "") for x in ("/explore/", "/search_result/")):
                    href = a["href"]
                    if not self.cur["note_id"]:
                        marker = "/explore/" if "/explore/" in href else "/search_result/"
                        self.cur["note_id"] = href.split(marker)[-1].split("?")[0].split("#")[0]
                        self.cur["url"] = ("https://www.xiaohongshu.com" + href) if href.startswith("/") else href
                    if "title" in cls:
                        self.mode, self.buf = "title", ""
                elif tag == "a" and "author" in cls:
                    self.mode, self.buf = "author", ""
                elif tag == "span" and "name" in cls:
                    self.mode, self.buf = "author_name", ""
                elif tag == "span" and "count" in cls:
                    self.mode, self.buf = "likes", ""

            def handle_data(self, data):
                if self.cur is not None and self.mode:
                    self.buf += data

            def handle_endtag(self, tag):
                if self.cur is None:
                    return
                if tag == "span" and self.mode in ("author_name", "likes"):
                    if self.mode == "author_name":
                        self.cur["author"] = _text(self.buf)
                    else:
                        self.cur["likes"] = _text(self.buf)
                    self.mode = None
                elif tag == "a" and self.mode == "title":
                    self.cur["title"] = _text(self.buf)
                    self.mode = None
                elif tag == "a" and self.mode == "author":
                    if not self.cur["author"]:
                        self.cur["author"] = _text(self.buf)
                    self.mode = None
                elif tag == "section":
                    if self.cur.get("note_id") and self.cur.get("title"):
                        self.cards.append(self.cur)
                    self.cur = None
                    self.mode = None

        parser = _Real()
        parser.feed(html)
        cards = parser.cards
    except Exception as exc:  # noqa: BLE001
        return _stop_for(f"parse_error:{type(exc).__name__}")
    if not cards:
        try:
            from html.parser import HTMLParser

            class _Old(HTMLParser):
                def __init__(self):
                    super().__init__()
                    self.cards = []
                    self.cur = None
                    self.counts = 0

                def handle_starttag(self, tag, attrs):
                    d = dict(attrs)
                    if tag == "a" and any(d.get("href", "").startswith(x) for x in ("/explore/", "/search_result/")):
                        marker = "/explore/" if d["href"].startswith("/explore/") else "/search_result/"
                        self.cur = {"url": BASE + d["href"],
                                    "note_id": d["href"].split(marker)[-1].split("?")[0],
                                    "title": "", "text": ""}
                    elif self.cur is not None and tag in ("h3", "p"):
                        self.counts += 1

                def handle_data(self, data):
                    if self.cur is not None and self.counts == 1:
                        self.cur["title"] = _text(self.cur["title"] + data)
                    elif self.cur is not None and self.counts >= 2:
                        self.cur["text"] = _text(self.cur["text"] + data)

                def handle_endtag(self, tag):
                    if tag == "a" and self.cur is not None:
                        if self.cur.get("note_id") and self.cur.get("title"):
                            self.cards.append(self.cur)
                        self.cur = None
                        self.counts = 0

            old = _Old()
            old.feed(html)
            cards = old.cards
        except Exception as exc:  # noqa: BLE001
            return _stop_for(f"parse_error:{type(exc).__name__}")
    signals = []
    for card in cards[: max(0, int(limit))]:
        quote = _summary(card.get("text") or card.get("title") or "")
        lang, lang_src = models.lang_of(quote or card.get("title") or "")
        author = card.get("author") or ""
        signals.append({
            "platform": "xiaohongshu", "native_id": card["note_id"],
            "parent_native_id": None, "url": card["url"],
            "title": card["title"], "quote": quote, "lang": lang, "lang_source": lang_src,
            "author_hash": models.sha256_bytes(author.encode("utf-8"))[:12] if author else "",
            "likes": card.get("likes") or "",
            "listed_price_minor": None, "effective_price_minor": None,
            "reference_price_minor": None, "wants": None,
            "collected_at": models.utc_now(), "collected_at_scope": "row",
            "origin_kind": "real", "raw_sha256": models.sha256_bytes(html.encode("utf-8")),
            "content_hash": models.content_hash(
                platform="xiaohongshu", native_id=card["note_id"], quote=quote,
                listed_price_minor=None, effective_price_minor=None, wants=None),
            "raw_ref": "fixture", "batch_id": "xhs-fixture",
        })
    return {"ok": True, "stop": False, "signals": signals, "count": len(signals)}


def parse_replies(payload: str | dict, *, limit: int = 20) -> dict:
    """Parse constructed note JSON (comments); fixture-only until first real sample."""
    data = payload if isinstance(payload, dict) else json.loads(payload)
    comments = data.get("comments") or []
    out = []
    for c in comments[: max(0, int(limit))]:
        text = _text(c.get("content") or "")
        if not text or not c.get("id"):
            continue
        quote = _summary(text)
        lang, lang_src = models.lang_of(quote)
        out.append({
            "platform": "xiaohongshu", "native_id": str(c["id"]), "parent_native_id": c.get("parent_id"),
            "url": data.get("note_url") or "", "title": _text(data.get("title") or ""),
            "quote": quote, "lang": lang, "lang_source": lang_src,
            "listed_price_minor": None, "effective_price_minor": None,
            "reference_price_minor": None, "wants": None,
            "collected_at": models.utc_now(), "collected_at_scope": "row",
            "origin_kind": "real", "raw_sha256": models.sha256_bytes(
                json.dumps(data, ensure_ascii=False).encode("utf-8")),
            "content_hash": models.content_hash(
                platform="xiaohongshu", native_id=str(c["id"]), quote=quote,
                listed_price_minor=None, effective_price_minor=None, wants=None),
            "raw_ref": "fixture", "batch_id": "xhs-fixture",
        })
    return {"ok": True, "signals": out, "count": len(out)}


def check_profile(profile_dir: str | pathlib.Path) -> dict:
    """Read-only profile check; NEVER launches a browser or reads cookie values."""
    path = pathlib.Path(profile_dir)
    out = {"path": str(path), "exists": path.exists(), "cookies": {}, "state": "waiting_user"}
    cookies_path = path / "Default" / "Network" / "Cookies"
    out["cookies"]["db_exists"] = cookies_path.exists()
    if not cookies_path.exists():
        return out
    try:
        conn = sqlite3.connect(f"file:{cookies_path.as_posix()}?mode=ro", uri=True)
        try:
            rows = conn.execute(
                "SELECT name FROM cookies WHERE host_key LIKE '%xiaohongshu.com%'").fetchall()
        finally:
            conn.close()
        names = {r[0] for r in rows}
    except sqlite3.Error:
        out["cookies"] = {"db_exists": True, "error": True}
        return out
    # names only; booleans never values
    for name in ("web_session", "a1", "webId", "customerClientId"):
        out["cookies"][name] = name in names
    logged = bool(out["cookies"].get("web_session"))
    out["state"] = "ready" if logged else "waiting_user"
    return out


def doctor(profile_dir: str | pathlib.Path) -> tuple[int, dict]:
    """Exit contract: 0 ready; non-zero waiting_user (等待用户登录). Never launches."""
    info = check_profile(profile_dir)
    if info["state"] == "ready":
        return 0, info
    print("等待用户登录", flush=True)
    return 2, info
