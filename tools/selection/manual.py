"""Manual paste-one import (V9-8b): stable native_id, triage link, no auto-collection."""

from __future__ import annotations

import re
import urllib.parse

from . import db, models, triage

PLATFORMS = ("xiaohongshu", "douyin", "weibo", "zhihu", "tieba", "other")

URL_RULES = {
    "xiaohongshu": re.compile(r"/explore/(\w+)|[?&]note_id=(\w+)"),
    "douyin": re.compile(r"/video/(\d+)"),
    "weibo": re.compile(r"/status/(\w+)"),
    "zhihu": re.compile(r"/question/(\d+)|/p/(\w+)"),
    "tieba": re.compile(r"/p/(\d+)"),
}


def parse_native_id(platform: str, url: str | None) -> tuple[str, str] | None:
    """Return (native_id, source) from a platform URL, or None."""
    url = urllib.parse.unquote(str(url or "").strip())
    if not url:
        return None
    rule = URL_RULES.get(platform)
    if rule is None:
        return None
    m = rule.search(url)
    if not m:
        return None
    value = next((g for g in m.groups() if g), None)
    return (value, "url") if value else None


def build_signal(platform: str, *, url: str | None = None, text: str | None = None,
                 title: str | None = None) -> dict:
    platform = str(platform or "").strip().lower()
    if platform not in PLATFORMS:
        raise ValueError("unsupported_platform")
    url = str(url or "").strip()
    text = str(text or "").strip()
    title = str(title or "").strip()
    if not url and not text:
        raise ValueError("url_or_text_required")
    if len(url) > 2048 or len(text) > 20000:
        raise ValueError("field_too_long")
    parsed = parse_native_id(platform, url)
    if parsed:
        native_id, source = parsed
    else:
        native_id, source = None, "derived"
    quote = (text or "")[:200]
    lang, lang_src = models.lang_of(text or title or url)
    content_hash = models.content_hash(
        platform=platform, native_id=native_id or "derived", quote=quote,
        listed_price_minor=None, effective_price_minor=None, wants=None)
    if native_id is None:
        native_id = content_hash[:16]
    return {
        "platform": platform, "native_id": native_id, "parent_native_id": None,
        "url": url or None, "title": title or None, "quote": quote,
        "lang": lang, "lang_source": lang_src,
        "listed_price_minor": None, "effective_price_minor": None,
        "reference_price_minor": None, "wants": None,
        "collected_at": models.utc_now(), "collected_at_scope": "batch",
        "origin_kind": "imported", "raw_sha256": "", "raw_ref": "",
        "batch_id": "manual", "content_hash": content_hash,
    }


def add(conn, platform: str, *, url: str | None = None, text: str | None = None,
        title: str | None = None) -> dict:
    sig = build_signal(platform, url=url, text=text, title=title)
    outcome, sid = db.upsert_signal(conn, sig)
    source = parse_native_id(sig["platform"], sig["url"] or "")
    native_source = source[1] if source else "derived"
    triage.store(conn, int(sid),
                 (sig["title"] or "") + " " + (sig["quote"] or ""),
                 native_id_source=native_source,
                 note=f"manual paste; native_id_source={native_source}")
    return {"outcome": outcome, "signal_id": int(sid), "native_id": sig["native_id"],
            "native_id_source": native_source, "content_hash": sig["content_hash"]}
