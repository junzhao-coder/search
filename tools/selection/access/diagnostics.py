"""Whitelisted diagnostics for the browser transports.

The contract is the whitelist below and nothing else. Page text, scripts,
inline state, account nicknames, user ids, tokens, cookies and hidden form
values never enter a diagnostic record: an href is reduced to a *shape* (and
query **key names** are counted, never their values), so a diagnostic can be
printed or stored without leaking anything from the account.

Shapes are per site (`SITES`): adding a platform means adding one entry here,
not another diagnostics module.
"""

from __future__ import annotations

import collections
import re
import urllib.parse

SHAPE_OTHER_SAME_ORIGIN = "other_same_origin"
SHAPE_OTHER_CROSS_ORIGIN = "other_cross_origin"
SHAPE_RELATIVE_OTHER = "relative_other"
SHAPE_NON_HTTP = "non_http"
GENERIC_SHAPES = (SHAPE_OTHER_SAME_ORIGIN, SHAPE_OTHER_CROSS_ORIGIN,
                  SHAPE_RELATIVE_OTHER, SHAPE_NON_HTTP)

#: per site: which shapes count as content, the path patterns, the hosts that
#: count as "same origin" for the histogram. Patterns are ordered: first wins.
SITES = {
    "zhihu": {
        "content": ("answer", "question", "article", "video"),
        "patterns": (
            ("answer", re.compile(r"/question/\d+/answer/\d+/?$")),
            ("question", re.compile(r"/question/\d+/?$")),
            ("article", re.compile(r"/p/\d+/?$")),
            ("video", re.compile(r"/zvideo/\d+/?$")),
        ),
        "hosts": ("zhihu.com",),
    },
    "weibo": {
        "content": ("detail", "status", "post"),
        "patterns": (
            ("detail", re.compile(r"/detail/\d+/?$")),
            ("status", re.compile(r"/status/\d+/?$")),
            ("post", re.compile(r"/\d{6,}/[A-Za-z0-9]{6,12}/?$")),
            ("profile", re.compile(r"(?:/u/|/profile/)?\d{6,}/?$")),
        ),
        "hosts": ("weibo.cn", "weibo.com"),
    },
    "douyin": {
        "content": ("video",),
        "patterns": (
            ("video", re.compile(r"/video/\d{6,}/?$")),
            ("profile", re.compile(r"/(?:user|share/user)/[\w.-]+/?$")),
        ),
        "hosts": ("douyin.com",),
    },
}

#: Zhihu content shapes, kept as module constants for existing callers.
CONTENT_SHAPES = SITES["zhihu"]["content"]
_CONTENT_PATTERNS = SITES["zhihu"]["patterns"]

#: the only keys a diagnostic record may contain
ALLOWED_KEYS = (
    "requested_url", "final_url", "final_url_known", "ready_state", "phase", "elapsed_ms",
    "html_bytes", "anchors_total", "anchors_recognized", "anchors_rejected", "href_shapes",
    "query_key_counts", "state", "parse_state", "web_state", "risk", "probe",
    "selectors_assumed", "error",
    "probe_level", "probe_elapsed_ms", "render_wait_ms", "render_wait_exhausted",
    "dom_anchor_count",
)

#: the page selectors each site waits on have NOT been confirmed against a real
#: page yet, so every diagnostic says so explicitly.
ASSUMED_BY_SITE = {
    "zhihu": (
        "result_container (assumed)",
        "candidate_links=/question/<id>(/answer/<id>)?, /p/<id>, /zvideo/<id> (assumed)",
        "empty_markers text (assumed)",
        "wall_markers text (assumed)",
    ),
    "douyin": (
        "result_container [data-e2e*=search-result] (assumed)",
        "candidate_links=/video/<id> (assumed)",
        "empty_markers text (assumed)",
        "wall_markers text (assumed)",
    ),
    "weibo": (
        "result_container (assumed)",
        "candidate_links=/detail/<id>, /status/<id>, /<uid>/<bid> (assumed)",
        "empty_markers text (assumed)",
        "wall_markers text (assumed)",
    ),
}

ASSUMED_SELECTORS = ASSUMED_BY_SITE["zhihu"]


def assumed_selectors(site: str = "zhihu") -> tuple:
    return ASSUMED_BY_SITE.get(site, ASSUMED_SELECTORS)


def _site(site: str) -> dict:
    return SITES.get(site, SITES["zhihu"])


def classify_href(href: str, site: str = "zhihu") -> str:
    """One href -> one shape. The URL itself is never returned."""
    text = str(href or "").strip()
    if not text:
        return SHAPE_RELATIVE_OTHER
    if text.startswith(("#", "javascript:", "mailto:", "tel:")):
        return SHAPE_NON_HTTP
    parts = urllib.parse.urlsplit(text)
    if parts.scheme and parts.scheme not in ("http", "https"):
        return SHAPE_NON_HTTP
    spec = _site(site)
    path = parts.path or ""
    for shape, pattern in spec["patterns"]:
        if pattern.search(path):
            return shape
    if not parts.scheme and not parts.netloc:
        return SHAPE_RELATIVE_OTHER
    host = (parts.hostname or "").lower()
    for suffix in spec["hosts"]:
        if host == suffix or host.endswith("." + suffix):
            return SHAPE_OTHER_SAME_ORIGIN
    return SHAPE_OTHER_CROSS_ORIGIN


def count_href_shapes(hrefs, site: str = "zhihu") -> dict:
    """Shape histogram plus the recognised/rejected totals the parser needs."""
    spec = _site(site)
    keys = tuple(shape for shape, _pattern in spec["patterns"]) + GENERIC_SHAPES
    shapes: collections.Counter = collections.Counter()
    recognized = rejected = 0
    for href in hrefs or []:
        shape = classify_href(href, site)
        shapes[shape] += 1
        if shape in spec["content"]:
            recognized += 1
        else:
            rejected += 1
    histogram = {name: shapes.get(name, 0) for name in keys}
    return {"shapes": histogram, "recognized": recognized, "rejected": rejected,
            "total": sum(histogram.values())}


def query_key_counts(hrefs, limit: int = 10) -> dict:
    """Count query **key names** only (never values)."""
    counts: collections.Counter = collections.Counter()
    for href in hrefs or []:
        text = str(href or "")
        if "?" not in text:
            continue
        for key, _value in urllib.parse.parse_qsl(text.split("?", 1)[1].split("#", 1)[0],
                                                  keep_blank_values=False):
            counts[key] += 1
    return dict(counts.most_common(limit))


def sanitize(diag: dict | None) -> dict:
    """Drop everything outside the whitelist. Called on the way out, always."""
    out: dict = {}
    for key in ALLOWED_KEYS:
        if key in (diag or {}):
            value = diag[key]
            if isinstance(value, (str, int, float, bool)) or value is None:
                out[key] = value
            elif isinstance(value, dict):
                out[key] = {str(k): v for k, v in value.items()
                            if isinstance(v, (str, int, float, bool)) or v is None}
            elif isinstance(value, (list, tuple)):
                out[key] = [str(v) for v in value][:16]
    return out
