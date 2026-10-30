"""V9 selection signal schema constants and canonicalization helpers (stdlib only)."""

from __future__ import annotations

import datetime as dt
import hashlib
import json

SCHEMA_VERSION = 8
ORIGIN_KINDS = ("real", "synthetic", "imported")
COLLECTED_SCOPES = ("row", "batch", "unknown")
LANG_SOURCES = ("source", "heuristic", "unknown")
RUN_STATUSES = ("running", "complete", "partial", "failed", "stopped")
CATEGORY_STATUSES = ("active", "merged", "excluded")
EVENT_KINDS = ("new", "update", "merge", "split", "exclude", "include", "undo")
CARD_STATUSES = ("draft", "confirmed", "rejected", "merged")
FAMILY_NORM = {
    "notion_template": "template",
    "excel_template": "template",
    "prompt_pack": "prompt_pack",
    "design_asset_pack": "asset_pack",
    "pdf_guide": "guide",
}
REVIEW_STATUSES = ("pending", "accepted", "rejected")
ROUND_STATUSES = ("draft", "running", "paused", "partial", "complete", "failed", "cancelled")
ROUND_ITEM_STATES = ("pending", "processing", "done", "failed")
SIGNAL_COLUMNS = (
    "platform", "native_id", "parent_native_id", "url", "title", "quote", "lang",
    "lang_source", "listed_price_minor", "effective_price_minor", "reference_price_minor",
    "wants", "collected_at", "collected_at_scope", "origin_kind", "raw_sha256",
    "content_hash", "raw_ref", "batch_id",
)


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def canonical_json(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def content_hash(*, platform: str, native_id: str, quote: str, listed_price_minor,
                 effective_price_minor, wants) -> str:
    """Stable content version hash; platform+native_id identify, content fields version."""
    payload = {
        "platform": platform, "native_id": str(native_id), "quote": quote,
        "listed_price_minor": listed_price_minor,
        "effective_price_minor": effective_price_minor, "wants": wants,
    }
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def lang_of(text: str) -> tuple[str, str]:
    """Small heuristic only; source has no lang field for Xianyu/Bilibili samples."""
    if any("\u4e00" <= ch <= "\u9fff" for ch in text or ""):
        return "zh", "heuristic"
    if any(("a" <= ch.lower() <= "z") for ch in text or ""):
        return "en", "heuristic"
    return "unknown", "heuristic"


def minor_from_yuan(value: str) -> int:
    """Parse a display price such as '¥ 1', '¥1.09', '¥ 1 .88' into integer cents."""
    import re
    text = str(value or "").strip()
    match = re.search(r"(\d+)(?:\s*\.\s*(\d{1,2}))?", text)
    if not match:
        raise ValueError("price_not_found")
    whole = int(match.group(1))
    frac = (match.group(2) or "00").ljust(2, "0")
    return whole * 100 + int(frac)
