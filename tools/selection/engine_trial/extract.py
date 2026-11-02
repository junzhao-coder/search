"""One page-level extractor shared by both engines.

The JS only reads what is visible in the rendered page.  Every field carries a
`source` selector and a `missing` list; a missing value stays `None` (never 0
or an API fallback).  Native IDs are accepted only when they are digit strings,
so an absent ID is reported as unidentified instead of being synthesised.
"""

from __future__ import annotations

import hashlib
import json

FIELDS = ("native_id", "text", "author", "published_at", "likes")

EXTRACT_JS = r"""
(() => {
  const norm = (t) => String(t || '').replace(/\s+/g, ' ').trim();
  const visible = (el) => {
    if (!el || !el.getClientRects || el.getClientRects().length === 0) return false;
    const style = getComputedStyle(el);
    return style.display !== 'none' && style.visibility !== 'hidden';
  };
  const textOf = (el) => el ? (norm(el.innerText || el.textContent || '') || null) : null;
  const numOf = (el) => {
    if (!el) return null;
    const attr = el.getAttribute('data-likes');
    const raw = attr !== null ? attr : (el.innerText || el.textContent || '');
    const match = String(raw).replace(/\s/g, '').match(/\d+/);
    return match ? parseInt(match[0], 10) : null;
  };
  const firstOwn = (root, selector) => Array.from(root.querySelectorAll(selector))
    .find((el) => !el.closest('.pb-lzl-item'));
  const firstInLzl = (root, selector) => Array.from(root.querySelectorAll(selector))
    .find((el) => el.closest('.pb-lzl-item') === root);

  const threadRoot = document.querySelector('.image-text') || document.body;
  const tidAttr = threadRoot.getAttribute('data-tid') || '';
  const tidUrl = (location.pathname.match(/\/p\/(\d+)/) || [])[1] || '';
  const tid = (tidAttr || tidUrl || '').trim() || null;
  const bodyEl = document.querySelector('span.pb-text-wrapper[tid][order-id="0"]')
    || firstOwn(threadRoot, 'span.pb-text-wrapper');
  const titleEl = firstOwn(threadRoot, 'span.pb-title');
  const authorEl = firstOwn(threadRoot, 'a.head-name');
  const timeEl = firstOwn(threadRoot, 'span.post-num');
  const likeEl = firstOwn(threadRoot, '[data-likes], .pb-agree-num');
  const titleFallback = norm(document.title).replace(/_百度贴吧.*$/, '') || null;

  const thread = {
    native_id: tid,
    title: textOf(titleEl) || titleFallback,
    text: textOf(bodyEl),
    author: textOf(authorEl),
    published_at: textOf(timeEl),
    likes: numOf(likeEl),
    sources: {
      native_id: tid ? 'data-tid|url:/p/<tid>' : null,
      title: titleEl ? 'span.pb-title' : (titleFallback ? 'document.title' : null),
      text: bodyEl ? 'span.pb-text-wrapper[tid][order-id="0"]' : null,
      author: authorEl ? 'a.head-name' : null,
      published_at: timeEl ? 'span.post-num' : null,
      likes: likeEl ? '[data-likes]|.pb-agree-num' : null
    }
  };

  const comment = (root, kind, parent) => {
    const pick = (selector) => kind === 'lzl'
      ? firstInLzl(root, selector) : firstOwn(root, selector);
    const body = pick('span.pb-text-wrapper');
    const name = pick('a.head-name');
    const time = pick('div.comment-desc-left > span');
    const like = pick('[data-likes], .pb-agree-num');
    const id = (root.getAttribute('data-id') || '').trim() || null;
    return {
      native_id: id, kind: kind, parent_id: parent, root_comment_id: tid,
      url: location.href,
      text: textOf(body), author: textOf(name), published_at: textOf(time),
      likes: numOf(like),
      sources: {
        native_id: id ? 'div[data-id]' : null,
        text: body ? 'span.pb-text-wrapper' : null,
        author: name ? 'a.head-name' : null,
        published_at: time ? 'div.comment-desc-left > span' : null,
        likes: like ? '[data-likes]|.pb-agree-num' : null
      }
    };
  };

  const comments = [];
  document.querySelectorAll('.pb-comment-item[data-id]').forEach((item) => {
    if (!visible(item)) return;
    const cid = (item.getAttribute('data-id') || '').trim() || null;
    comments.push(comment(item, 'comment', tid));
    item.querySelectorAll('.pb-lzl-item[data-id]').forEach((lzl) => {
      if (!visible(lzl)) return;
      comments.push(comment(lzl, 'lzl', cid));
    });
  });

  const tabEl = document.querySelector('[id^="tab-全部回复"]');
  const declaredMatch = tabEl ? (tabEl.innerText || '').match(/\((\d+)\)/) : null;

  return JSON.stringify({
    url: location.href,
    title: document.title,
    ready: document.readyState,
    thread: thread,
    comments: comments,
    declared_comments: declaredMatch ? parseInt(declaredMatch[1], 10) : null,
    events: window.__events || [],
    scroll: {
      y: Math.round(window.scrollY),
      height: Math.round(document.documentElement.scrollHeight
                        || document.body.scrollHeight || 0)
    }
  });
})()
"""


def _as_int(value):
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        digits = "".join(ch for ch in value if ch.isdigit())
        return int(digits) if digits else None
    return None


def _as_text(value):
    if value is None:
        return None
    text = " ".join(str(value).split())
    return text or None


def _native_id(value):
    text = str(value or "").strip()
    return text if text.isdigit() and len(text) >= 6 else None


def _scroll(raw) -> dict:
    raw = raw if isinstance(raw, dict) else {}
    return {"y": _as_int(raw.get("y")) or 0,
            "height": _as_int(raw.get("height")) or 0}


def _comment(raw: dict) -> dict:
    kind = "lzl" if raw.get("kind") == "lzl" else "comment"
    record = {
        "native_id": _native_id(raw.get("native_id")),
        "kind": kind,
        "parent_id": str(raw.get("parent_id") or "").strip() or None,
        "root_comment_id": str(raw.get("root_comment_id") or "").strip() or None,
        "url": raw.get("url"),
        "text": _as_text(raw.get("text")),
        "author": _as_text(raw.get("author")),
        "published_at": _as_text(raw.get("published_at")),
        "likes": _as_int(raw.get("likes")),
        "sources": raw.get("sources") if isinstance(raw.get("sources"), dict) else {},
    }
    record["missing"] = [field for field in FIELDS if record.get(field) is None]
    return record


def normalize(payload) -> dict:
    """Raw extractor JSON -> one state with thread, de-duplicated records, IDs."""
    if isinstance(payload, str):
        payload = json.loads(payload or "{}")
    if not isinstance(payload, dict):
        payload = {}
    raw_thread = payload.get("thread") if isinstance(payload.get("thread"), dict) else {}
    thread = {
        "native_id": _native_id(raw_thread.get("native_id")),
        "title": _as_text(raw_thread.get("title")),
        "text": _as_text(raw_thread.get("text")),
        "author": _as_text(raw_thread.get("author")),
        "published_at": _as_text(raw_thread.get("published_at")),
        "likes": _as_int(raw_thread.get("likes")),
        "sources": raw_thread.get("sources") if isinstance(raw_thread.get("sources"), dict) else {},
    }
    thread["missing"] = [field for field in FIELDS if thread.get(field) is None]

    records: dict[str, dict] = {}
    unidentified = 0
    for raw in payload.get("comments") or []:
        if not isinstance(raw, dict):
            continue
        record = _comment(raw)
        key = record["native_id"] or (
            "unidentified:" + hashlib.sha1(
                (record.get("text") or "").encode("utf-8")).hexdigest()[:12])
        record["key"] = key
        if record["native_id"] is None:
            unidentified += 1
        records.setdefault(key, record)

    return {
        "url": payload.get("url"),
        "title": payload.get("title"),
        "ready": payload.get("ready"),
        "thread": thread,
        "records": records,
        "events": payload.get("events") if isinstance(payload.get("events"), list) else [],
        "scroll": _scroll(payload.get("scroll")),
        "declared": _as_int(payload.get("declared_comments")),
        "unidentified": unidentified,
    }


def ids_of(state: dict) -> list[str]:
    """Thread ID plus every identifiable comment / lzl ID, sorted and unique."""
    ids = []
    thread_id = (state.get("thread") or {}).get("native_id")
    if thread_id:
        ids.append(str(thread_id))
    for record in (state.get("records") or {}).values():
        if record.get("native_id"):
            ids.append(str(record["native_id"]))
    return sorted(set(ids))


def field_summary(records) -> dict:
    """Per-field presence and selector sources for the collected records."""
    out = {"count": 0, "comment": 0, "lzl": 0, "likes_known": 0,
           "times_known": 0, "missing": {}, "sources": {}}
    for record in records:
        out["count"] += 1
        out[record["kind"]] = out.get(record["kind"], 0) + 1
        for field in record.get("missing") or []:
            out["missing"].setdefault(field, []).append(record["key"])
        for field, source in (record.get("sources") or {}).items():
            if source:
                out["sources"].setdefault(field, {})
                out["sources"][field][source] = out["sources"][field].get(source, 0) + 1
        if record.get("likes") is not None:
            out["likes_known"] += 1
        if record.get("published_at") is not None:
            out["times_known"] += 1
    return out


def compare_ids(left: dict, right: dict) -> dict:
    """Compare two ID sets without pretending equal means complete."""
    left_ids = {str(item) for item in (left.get("ids") or [])}
    right_ids = {str(item) for item in (right.get("ids") or [])}
    return {
        "left_count": len(left_ids),
        "right_count": len(right_ids),
        "common_count": len(left_ids & right_ids),
        "left_only": sorted(left_ids - right_ids),
        "right_only": sorted(right_ids - left_ids),
        "common": sorted(left_ids & right_ids),
    }
