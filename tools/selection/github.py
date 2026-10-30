"""GitHub public read-only adapter (no token; caller must respect 60/h)."""

from __future__ import annotations

import dataclasses
import json
import pathlib
import re
import time
import urllib.error
import urllib.parse
import urllib.request

from . import models

BASE = "https://api.github.com"
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
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/vnd.github+json"})
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
    return re.sub(r"\s+", " ", str(value or "")).strip()


def summary(text: str, limit: int = 200) -> str:
    text = _text(text)
    return text if len(text) <= limit else text[:limit].rstrip() + "…"


def _repo(item: dict) -> str:
    repo = item.get("repository_url") or ""
    m = re.search(r"/repos/([^/]+/[^/]+)$", repo)
    if m:
        return m.group(1)
    url = item.get("html_url") or ""
    m = re.search(r"github\.com/([^/]+/[^/]+)/(?:issues|pull)/", url)
    return m.group(1) if m else ""


def _save_raw(raw_dir: pathlib.Path, batch: str, body: bytes) -> tuple[str, str]:
    raw_dir.mkdir(parents=True, exist_ok=True)
    path = raw_dir / f"github_{batch}.json"
    path.write_bytes(body)
    return str(path), models.sha256_bytes(body)


def parse_issues(payload, limit: int = 5) -> list[dict]:
    if not isinstance(payload, dict) or not isinstance(payload.get("items"), list):
        raise ValueError("github_payload_missing_items")
    out = []
    for row in payload["items"][: max(0, int(limit))]:
        if not isinstance(row, dict):
            continue
        number = row.get("number")
        title = _text(row.get("title"))
        body = _text(row.get("body"))
        repo = _repo(row)
        if not number or not title:
            continue
        native = f"{repo}#{number}" if repo else str(number)
        quote = summary(body or title)
        lang, lang_src = models.lang_of(quote or title)
        out.append({
            "platform": "github", "native_id": native, "parent_native_id": None,
            "url": row.get("html_url") or f"https://github.com/{repo}/issues/{number}",
            "title": title, "quote": quote, "lang": lang, "lang_source": lang_src,
            "listed_price_minor": None, "effective_price_minor": None,
            "reference_price_minor": None, "wants": None,
            "collected_at": models.utc_now(), "collected_at_scope": "row",
            "origin_kind": "real", "raw_sha256": "",
            "content_hash": models.content_hash(
                platform="github", native_id=native, quote=quote,
                listed_price_minor=None, effective_price_minor=None, wants=None),
            "raw_ref": "", "batch_id": "github",
        })
    return out


def fetch(*, query: str = "notion template", limit: int = 3, raw_dir=None, fetch=None,
          interval: float = 3.0, sleep=None, clock=None, max_requests: int = 1) -> dict:
    fetch = fetch or default_fetch
    sleep = sleep or time.sleep
    clock = clock or time.monotonic
    raw_dir = pathlib.Path(raw_dir or (pathlib.Path(__file__).resolve().parent / "evidence" / "github-v2ex"))
    q = urllib.parse.quote(f"{query} type:issue")
    url = f"{BASE}/search/issues?q={q}&per_page={max(1, min(int(limit), 10))}"
    batch = f"issues_{models.utc_now().replace('-', '').replace(':', '')}"
    stats = {"platform": "github", "url": url, "requests": 0, "status": None,
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
        payload = json.loads(result.body.decode("utf-8")) if result.body else {}
    except Exception as exc:  # noqa: BLE001
        stats["stop_reason"] = "invalid_json"
        stats["errors"].append({"status": result.status, "reason": str(exc)})
        return stats
    path, sha = _save_raw(raw_dir, batch, result.body or b"")
    stats["raw_path"], stats["raw_sha256"] = path, sha
    try:
        items = parse_issues(payload, limit=limit)
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
