"""V2EX public read-only adapter (no token, public JSON API only)."""

from __future__ import annotations

import dataclasses
import html
import json
import pathlib
import re
import time
import urllib.error
import urllib.request

from . import models

BASE = "https://www.v2ex.com/api"
UA = "two-selection/1.0"


@dataclasses.dataclass
class FetchResult:
    status: int
    body: bytes
    headers: dict
    url: str
    error: str | None = None
    elapsed_ms: float = 0.0


def default_fetch(url: str, timeout: float = 20.0) -> FetchResult:
    started = time.monotonic()
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read()
            return FetchResult(int(resp.status), body, dict(resp.headers), resp.geturl(),
                               None, round((time.monotonic() - started) * 1000, 1))
    except urllib.error.HTTPError as exc:
        body = exc.read() if exc.fp else b""
        return FetchResult(int(exc.code), body, dict(exc.headers or {}), url,
                           f"http_{exc.code}", round((time.monotonic() - started) * 1000, 1))
    except Exception as exc:  # noqa: BLE001
        return FetchResult(0, b"", {}, url, f"{type(exc).__name__}: {exc}",
                           round((time.monotonic() - started) * 1000, 1))


def _text(value) -> str:
    text = html.unescape(re.sub(r"<[^>]+>", " ", str(value or "")))
    return re.sub(r"\s+", " ", text).strip()


def summary(text: str, limit: int = 200) -> str:
    text = _text(text)
    return text if len(text) <= limit else text[:limit].rstrip() + "…"


def _save_raw(raw_dir: pathlib.Path, batch: str, body: bytes) -> tuple[str, str]:
    raw_dir.mkdir(parents=True, exist_ok=True)
    path = raw_dir / f"v2ex_{batch}.json"
    path.write_bytes(body)
    return str(path), models.sha256_bytes(body)


def parse_topics(payload) -> list[dict]:
    if isinstance(payload, dict):
        payload = payload.get("result") or payload.get("data") or []
    if not isinstance(payload, list):
        raise ValueError("v2ex_payload_not_list")
    out = []
    for row in payload:
        if not isinstance(row, dict):
            continue
        tid = row.get("id")
        title = _text(row.get("title"))
        content = _text(row.get("content") or row.get("content_rendered"))
        if not tid or not title:
            continue
        quote = summary(content or title)
        lang, lang_src = models.lang_of(quote or title)
        out.append({
            "platform": "v2ex", "native_id": str(tid), "parent_native_id": None,
            "url": row.get("url") or f"https://www.v2ex.com/t/{tid}",
            "title": title, "quote": quote, "lang": lang, "lang_source": lang_src,
            "listed_price_minor": None, "effective_price_minor": None,
            "reference_price_minor": None, "wants": None,
            "collected_at": models.utc_now(), "collected_at_scope": "row",
            "origin_kind": "real", "raw_sha256": "",
            "content_hash": models.content_hash(
                platform="v2ex", native_id=str(tid), quote=quote,
                listed_price_minor=None, effective_price_minor=None, wants=None),
            "raw_ref": "", "batch_id": "v2ex",
        })
    return out


def fetch(*, node_name: str = "notion", limit: int = 5, raw_dir=None, fetch=None,
          interval: float = 3.0, sleep=None, clock=None, max_requests: int = 1) -> dict:
    fetch = fetch or default_fetch
    sleep = sleep or time.sleep
    clock = clock or time.monotonic
    raw_dir = pathlib.Path(raw_dir or (pathlib.Path(__file__).resolve().parent / "evidence" / "github-v2ex"))
    url = f"{BASE}/topics/show.json?node_name={node_name}"
    batch = f"topics_{node_name}_{models.utc_now().replace('-', '').replace(':', '')}"
    stats = {"platform": "v2ex", "url": url, "requests": 0, "status": None,
             "bytes": 0, "items": 0, "errors": [], "elapsed_s": 0.0,
             "raw_path": None, "raw_sha256": None, "stop_reason": None,
             "signals": []}
    started = clock()
    if max_requests < 1:
        stats["stop_reason"] = "budget_exhausted"
        return stats
    stats["requests"] += 1
    result = fetch(url)
    stats["status"] = result.status
    stats["bytes"] = len(result.body or b"")
    stats["elapsed_s"] = round(clock() - started, 3)
    if result.status in (403, 429) or (result.status and result.status != 200):
        stats["stop_reason"] = result.error or f"http_{result.status}"
        stats["errors"].append({"status": result.status, "reason": stats["stop_reason"]})
        return stats
    try:
        payload = json.loads(result.body.decode("utf-8")) if result.body else []
    except Exception as exc:  # noqa: BLE001
        stats["stop_reason"] = "invalid_json"
        stats["errors"].append({"status": result.status, "reason": str(exc)})
        return stats
    path, sha = _save_raw(raw_dir, batch, result.body or b"")
    stats["raw_path"], stats["raw_sha256"] = path, sha
    try:
        items = parse_topics(payload)[: max(0, int(limit))]
    except Exception as exc:  # noqa: BLE001
        stats["stop_reason"] = "parse_error"
        stats["errors"].append({"status": result.status, "reason": str(exc)})
        return stats
    for item in items:
        item["raw_sha256"] = sha
        item["raw_ref"] = path
        item["batch_id"] = batch
    stats["items"] = len(items)
    stats["signals"] = items
    if not items:
        stats["stop_reason"] = "empty"
    return stats
