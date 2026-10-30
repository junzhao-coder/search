"""Bilibili known-object completion (S3-A1a).

Scope: one adapter, offline by construction. The transport is injected; this
module never imports an HTTP client and performs no network I/O. Storage
wiring, run records and version columns are a later batch.
"""

from __future__ import annotations

import datetime as _dt
import json
import re
import urllib.parse
from typing import Callable

from app.core.identity import content_hash, demand_identity_key, url_norm

SOURCE_NAME = "bilibili"
API_URL = "https://api.bilibili.com/x/web-interface/view?bvid={bvid}"
CANONICAL_URL = "https://www.bilibili.com/video/{bvid}/"
EXCERPT_MAX = 4000

_BVID_RE = re.compile(r"^BV[0-9A-Za-z]{10}$")
_VIDEO_PATH_RE = re.compile(r"^/video/(BV[0-9A-Za-z]{10})/?$")
_AT_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(Z|[+-]\d{2}:\d{2})$")
_TRUSTED_HOSTS = {"bilibili.com", "www.bilibili.com", "m.bilibili.com"}
_CST = _dt.timezone(_dt.timedelta(hours=8))

MIN_PUBDATE = 1230768000  # 2009-01-01T00:00:00Z
MAX_PUBDATE = 4102444800  # 2100-01-01T00:00:00Z


def resolve_target(value: object) -> tuple[str, str]:
    """Return ``(bvid, original_url)``; ``("", "")`` when the input is unusable.

    Trust boundary (separate from ``url_norm``, which only normalises): the
    scheme must be http/https, userinfo of any kind is rejected (including an
    empty ``@``), ports must be the scheme default, the hostname must be an
    explicitly listed bilibili host and the path must be an exact
    ``/video/<bvid>`` shape. Short links (b23.tv) are **not** followed and
    arbitrary hosts are never used as a network target.
    """
    raw = str(value or "").strip()
    if _BVID_RE.match(raw):
        return raw, ""
    try:
        parts = urllib.parse.urlsplit(raw)
        hostname = (parts.hostname or "").lower()
        port = parts.port
    except ValueError:  # malformed IPv6 literal, bad port, unusable netloc
        return "", ""
    if parts.scheme not in ("http", "https"):
        return "", ""
    if "@" in parts.netloc:  # userinfo present, even when empty
        return "", ""
    if port is not None and port != (443 if parts.scheme == "https" else 80):
        return "", ""
    if hostname not in _TRUSTED_HOSTS:
        return "", ""
    match = _VIDEO_PATH_RE.match(parts.path)
    if not match:
        return "", ""
    return match.group(1), raw


def classify_failure(
    http_status: int | None,
    app_code: int | None,
    app_message: str | None,
    error: str | None,
) -> tuple[str, str]:
    """Map one raw failure to ``(outcome_enum, raw_reason)``.

    Outcome values are the frozen ``search_coverage.outcome`` enum members.
    Login is decided only by explicit markers (handled before this function);
    a plain 401/403 is **not** treated as login. The reason keeps the raw
    status/app code/message verbatim: no rate-limit threshold is inferred and
    HTTP 429 is never claimed.
    """
    reason = _raw_reason(http_status, app_code, app_message, error)
    if error == "timeout":
        return "timeout", reason
    if app_code == -412 or http_status == 412:
        return "rate_limited", reason
    if app_code == -101:
        return "blocked_login", reason
    return "failed", reason


def _raw_reason(http_status, app_code, app_message, error) -> str:
    parts = []
    if http_status is not None:
        parts.append(f"http={http_status}")
    if app_code is not None:
        parts.append(f"app_code={app_code}")
    if app_message:
        parts.append(f"message={app_message}")
    if error:
        parts.append(f"error={error}")
    return "; ".join(parts) if parts else "unknown_failure"


def _bad_code(value) -> bool:
    """``bool`` is a subclass of ``int``; both `True` and `False` are invalid codes."""
    return isinstance(value, bool) or not isinstance(value, int)


def _iso_utc8(epoch_seconds) -> str | None:
    if epoch_seconds is None:
        return None
    return _dt.datetime.fromtimestamp(int(epoch_seconds), _CST).isoformat(timespec="seconds")


def _valid_at(value: str) -> bool:
    """ISO-8601, second precision, timezone required, real calendar date."""
    if not _AT_RE.match(value):
        return False
    text = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        _dt.datetime.fromisoformat(text)
    except ValueError:
        return False
    return True


def _observation(observed_at, clock: Callable[[], float]) -> tuple[str, str, str | None]:
    """Caller time must be valid to earn ``source``; otherwise call time is used."""
    if isinstance(observed_at, str) and _valid_at(observed_at):
        return observed_at, "source", None
    if observed_at:
        return _iso_utc8(clock()), "import_time", str(observed_at)
    return _iso_utc8(clock()), "import_time", None


def _login_marker(result: dict) -> str | None:
    """Explicit login evidence only: transport flag, or a ``login`` path *segment*.

    Segment equality (not substring) keeps normal pages such as
    ``/video/BV.../login-tips`` or ``/loginx`` out of ``blocked_login``.
    """
    if result.get("login_redirect") is True:
        return "login_redirect"
    final_url = result.get("final_url")
    if isinstance(final_url, str) and final_url:
        try:
            path = urllib.parse.urlsplit(final_url).path
        except ValueError:
            return None
        if any(segment == "login" for segment in path.strip("/").split("/")):
            return f"final_url_login={final_url}"
    return None


def _failure(bvid, status, code, outcome, reason) -> dict:
    return {
        "outcome": outcome,
        "failure_reason": reason,
        "bvid": bvid,
        "native_id": bvid,
        "source_name": SOURCE_NAME,
        "http_status": status,
        "app_code": code,
    }


def _excerpt_from(desc, title: str, unknown: list) -> str:
    if isinstance(desc, str):
        text = desc.strip()
        if text:
            return text[:EXCERPT_MAX]  # explicit truncation rule; wording untouched
    elif desc is not None:
        unknown.append("desc_malformed")
    return title[:EXCERPT_MAX]  # fallback is truncated too (contract: excerpt ≤4000)


def _author_from(owner, unknown: list) -> str | None:
    if isinstance(owner, dict):
        name = owner.get("name")
        if isinstance(name, str) and name.strip():
            return name.strip()
        unknown.append("owner_name_missing")
        return None
    if owner is not None:
        unknown.append("owner_malformed")
    return None


def _published_from(value, unknown: list) -> str | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        unknown.append("pubdate_malformed")
        return None
    if not (MIN_PUBDATE <= value <= MAX_PUBDATE):
        unknown.append("pubdate_out_of_range")
        return None
    return _iso_utc8(value)


def _engagement_from(stat, unknown: list) -> str:
    if isinstance(stat, dict):
        return json.dumps(stat, ensure_ascii=False, sort_keys=True)
    if stat is not None:
        unknown.append("stat_malformed")
    return "{}"


def _parse_view_response(bvid: str, result: dict) -> dict:
    """Decide outcome. Explicit login/type errors are checked before success."""
    status = result.get("http_status")
    error = result.get("error")
    payload = result.get("payload")
    code = result.get("app_code")
    message = result.get("app_message")

    marker = _login_marker(result)
    if marker:
        return _failure(bvid, status, code, "blocked_login", _raw_reason(status, code, marker, None))

    payload_code = payload.get("code") if isinstance(payload, dict) else None
    if isinstance(payload, dict) and message is None:
        message = payload.get("message")
    bad_code = None
    if code is not None and _bad_code(code):
        bad_code = code
    elif payload_code is not None and _bad_code(payload_code):
        bad_code = payload_code
    if bad_code is not None:
        return _failure(bvid, status, None, "failed", _raw_reason(status, bad_code, None, "unexpected_response"))
    if code is None:
        code = payload_code

    if error:
        outcome, reason = classify_failure(status, code, message, error)
        return _failure(bvid, status, code, outcome, reason)
    if code == -412 or status == 412 or code == -101:
        outcome, reason = classify_failure(status, code, message, None)
        return _failure(bvid, status, code, outcome, reason)
    if status != 200 or code != 0 or not isinstance(payload, dict) or not isinstance(payload.get("data"), dict):
        return _failure(bvid, status, code, "failed", _raw_reason(status, code, message, "unexpected_response"))

    data = payload["data"]
    returned = data.get("bvid")
    if not isinstance(returned, str) or returned != bvid:
        return _failure(bvid, status, code, "failed", _raw_reason(status, code, "bvid_mismatch", None))
    title_raw = data.get("title")
    if not isinstance(title_raw, str) or not title_raw.strip():
        return _failure(bvid, status, code, "failed", _raw_reason(status, code, "missing_title", None))

    title = title_raw.strip()
    unknown: list = []
    excerpt = _excerpt_from(data.get("desc"), title, unknown)
    return {
        "outcome": "ok",
        "bvid": bvid,
        "native_id": bvid,
        "source_name": SOURCE_NAME,
        "title": title,
        "excerpt": excerpt,
        "signal_kind": "other",
        "published_at": _published_from(data.get("pubdate"), unknown),
        "original_author": _author_from(data.get("owner"), unknown),
        "engagement_json": _engagement_from(data.get("stat"), unknown),
        "content_hash": content_hash(excerpt, title),
        "http_status": status,
        "app_code": code,
        "unknown_fields": unknown,
    }


def _render_ok(base: dict, original_url: str) -> dict:
    """Rebuild URL-derived fields from the *current* input (content may be cached)."""
    url = original_url or CANONICAL_URL.format(bvid=base["bvid"])
    norm = url_norm(url)
    identity_key, identity_source = demand_identity_key(SOURCE_NAME, base["bvid"], norm)
    out = dict(base)
    out["url"] = url
    out["url_norm"] = norm
    out["identity_key"] = identity_key
    out["identity_source"] = identity_source
    out["unknown_fields"] = list(base.get("unknown_fields") or [])  # never share the cached list
    return out


def _finalize(record: dict, observed_at, clock: Callable[[], float], request_url: str | None = None) -> dict:
    out = dict(record)
    if request_url is not None:
        out["request_url"] = request_url
    stamp, source, rejected = _observation(observed_at, clock)
    out["observed_at"] = stamp
    out["observed_at_source"] = source
    if rejected is not None:
        out["observed_at_rejected"] = rejected
    return out


class BilibiliViewReader:
    """One known object in, one normalised demand record out. No retries.

    ``transport(url)`` must return a dict with ``http_status``, ``app_code``,
    ``app_message``, ``error`` and ``payload`` keys (plus optional
    ``login_redirect`` / ``final_url``). Only the object's *content* is cached
    (24h by default); URL-derived output is rebuilt per call from the current
    input. Failures are never cached and never retried.
    """

    def __init__(self, transport: Callable[[str], dict], *, clock: Callable[[], float] | None = None,
                 ttl_seconds: float = 86400, maxsize: int = 256):
        self._transport = transport
        self._clock = clock or (lambda: _dt.datetime.now(_dt.timezone.utc).timestamp())
        self._ttl = ttl_seconds
        self._maxsize = maxsize
        # ponytail: process-local dict cache, swap for a persistent store if cross-process TTL matters
        self._cache: dict[str, tuple[float, dict]] = {}

    def complete(self, value: object, *, observed_at: str | None = None) -> dict:
        bvid, original_url = resolve_target(value)
        if not bvid:
            record = _failure(None, None, None, "failed", "invalid_target: 仅接受合法 bvid 或 bilibili.com /video/ 链接")
            return _finalize(record, observed_at, self._clock)
        request_url = API_URL.format(bvid=bvid)
        now = float(self._clock())
        hit = self._cache.get(bvid)
        if hit is not None and now < hit[0]:
            base = dict(hit[1])
        else:
            parsed = _parse_view_response(bvid, self._transport(request_url))
            if parsed["outcome"] != "ok":
                return _finalize(parsed, observed_at, self._clock, request_url)
            self._cache[bvid] = (now + self._ttl, parsed)
            if len(self._cache) > self._maxsize:
                self._cache.pop(next(iter(self._cache)))
            base = dict(parsed)
        return _finalize(_render_ok(base, original_url), observed_at, self._clock, request_url)
