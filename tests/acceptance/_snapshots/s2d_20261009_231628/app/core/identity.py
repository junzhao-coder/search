"""Identity, fingerprints and URL normalization (contract §4.5)."""

from __future__ import annotations

import hashlib
import urllib.parse

# Only these parameter names are removed as tracking noise (no open-ended "etc.").
TRACKING_EXACT = {"fbclid", "spm", "from", "referer"}
TRACKING_PREFIXES = ("utm_", "share_")


def normalize(text: str) -> str:
    """Strip, collapse whitespace, full-width -> half-width, ASCII lowercased."""
    if text is None:
        return ""
    out = []
    for ch in str(text):
        code = ord(ch)
        if 0xFF01 <= code <= 0xFF5E:  # full-width ASCII variants
            out.append(chr(code - 0xFEE0))
        elif code == 0x3000:  # ideographic space
            out.append(" ")
        else:
            out.append(ch)
    collapsed = " ".join("".join(out).split())
    return _ascii_lower(collapsed)


def _ascii_lower(text: str) -> str:
    return "".join(ch.lower() if "A" <= ch <= "Z" else ch for ch in text)


def _sha16(payload: str) -> str:
    """sha256 truncated to the first 16 bytes (32 hex chars)."""
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:32]


def title_norm_hash(title: str) -> str:
    return _sha16(normalize(title))


def content_hash(excerpt: str, title: str) -> str:
    """Fingerprint used only for version detection / cross-object suspicion (never identity)."""
    return _sha16(normalize(excerpt) + "\n" + normalize(title))


def url_norm(url: str) -> str:
    """Fixed normalization rules; path case is preserved, tracking params are dropped by name."""
    if url is None:
        return ""
    raw = str(url).strip()
    if not raw:
        return ""
    parts = urllib.parse.urlsplit(raw)
    scheme = (parts.scheme or "").lower()
    host = (parts.hostname or "").lower()
    port = parts.port
    if (scheme == "http" and port == 80) or (scheme == "https" and port == 443):
        port = None
    netloc = host if port is None else f"{host}:{port}"
    kept = []
    for key, value in urllib.parse.parse_qsl(parts.query, keep_blank_values=True):
        lowered = key.lower()
        if lowered in TRACKING_EXACT or any(lowered.startswith(p) for p in TRACKING_PREFIXES):
            continue
        kept.append((key, value))
    kept.sort(key=lambda kv: kv[0])
    query = urllib.parse.urlencode(kept)
    return urllib.parse.urlunsplit((scheme, netloc, parts.path, query, ""))


def demand_identity_key(source_id: str, native_id: str | None, norm_url: str) -> tuple[str, str]:
    """Return (identity_key, identity_source) for a demand signal."""
    if native_id:
        return f"n:{source_id}:{native_id}", "demand_native_id"
    return f"u:{source_id}:{norm_url}", "demand_url"


def candidate_identity_key(demand_key: str | None, title_hash: str) -> tuple[str, str]:
    """Candidate identity: reuse the demand identity, else the title fingerprint."""
    if demand_key:
        return demand_key, ("demand_native_id" if demand_key.startswith("n:") else "demand_url")
    return f"t:{title_hash}", "title"
