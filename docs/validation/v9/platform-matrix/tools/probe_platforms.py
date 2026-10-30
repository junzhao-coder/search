"""Bounded read-only probes for Bilibili and Weibo (V9-1a-A).

Constraints:
- Bilibili <= 10 requests, Weibo <= 5 requests, >=3s between requests.
- Public GET only; no cookies, no login, no writes/likes/follows/messages.
- Stop a platform immediately on HTTP 412/403/429, JSON -412/-352,
  verification/login-wall markers.
- Raw responses are truncated at 200 KiB, sanitized (no nicknames/profile links/
  @mentions), and hashed. No app imports or business/workorder DB access.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import pathlib
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

BASE = pathlib.Path(__file__).resolve().parents[1]
RAW = BASE / "raw"
LOGS = BASE / "logs"
for directory in (RAW, LOGS):
    directory.mkdir(parents=True, exist_ok=True)

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
MAX_BYTES = 200 * 1024
INTERVAL_SECONDS = 3.2
BILI_OID = 540769243
BILI_LIMIT = 10
WEIBO_LIMIT = 5
LOGIN_WORDS = ("sina visitor system", "passport.weibo", "请先登录", "登录后查看",
               "安全验证", "验证码", "访问过于频繁", "人机验证")
BILI_RISK = ("-412", "-352", "风控", "安全验证", "captcha", "验证码")


def utc() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sanitize_text(text: str) -> str:
    text = re.sub(r"@[A-Za-z0-9_\-\u4e00-\u9fff]{2,}", "@u***", text or "")
    return text


def sanitize(obj, path: str = "") -> object:
    """Redact names/profile links/avatars; keep ids, text and counts."""
    if isinstance(obj, dict):
        out = {}
        for key, value in obj.items():
            name = str(key)
            lowered = name.lower()
            if lowered in {"uname", "screen_name", "profile_url", "avatar", "avatar_hd",
                           "face", "nickname", "user_name", "verify_info"}:
                out[name] = "u***" if lowered in {"uname", "screen_name", "nickname", "user_name"} else None
                continue
            if lowered == "name" and any(part in path for part in ("owner", "member", "user")):
                out[name] = "u***"
                continue
            if lowered in {"url", "uri", "href"} and isinstance(value, str):
                if any(host in value for host in ("space.bilibili.com", "weibo.com/u/", "/profile")):
                    out[name] = None
                    continue
            out[name] = sanitize(value, f"{path}.{name}" if path else name)
        return out
    if isinstance(obj, list):
        return [sanitize(item, path) for item in obj]
    if isinstance(obj, str):
        return sanitize_text(obj)
    return obj


def parse_body(body: bytes, content_type: str):
    if "json" in (content_type or "").lower():
        text = body.decode("utf-8", "replace")
        try:
            return json.loads(text), text
        except json.JSONDecodeError:
            return None, text
    return None, body.decode("utf-8", "replace")


def load_json(name: str):
    p = RAW / name
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


class Prober:
    def __init__(self) -> None:
        self.requests = []
        self.last_at = 0.0
        self.counts = {"bilibili": 0, "weibo": 0}
        self.stopped = {"bilibili": None, "weibo": None}
        self.manifest = []
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def wait(self) -> None:
        wait = INTERVAL_SECONDS - (time.monotonic() - self.last_at)
        if wait > 0:
            time.sleep(wait)

    def fetch(self, platform: str, name: str, url: str, *, accept: str = "application/json"):
        limit = BILI_LIMIT if platform == "bilibili" else WEIBO_LIMIT
        if self.stopped[platform]:
            return {"skipped": f"platform stopped: {self.stopped[platform]}"}
        if self.counts[platform] >= limit:
            self.stopped[platform] = f"request cap {limit} reached"
            return {"skipped": self.stopped[platform]}
        self.wait()
        started = time.monotonic()
        request = urllib.request.Request(url, headers={
            "User-Agent": UA,
            "Accept": accept,
            "Accept-Language": "zh-CN,zh;q=0.9",
            "Accept-Encoding": "identity",
            "Referer": "https://www.bilibili.com/" if platform == "bilibili" else "https://m.weibo.cn/",
        }, method="GET")
        status, headers, body, final_url, error = None, {}, b"", url, None
        try:
            with self.opener.open(request, timeout=20) as response:
                status = int(response.status)
                headers = dict(response.headers)
                final_url = response.geturl()
                body = response.read(MAX_BYTES + 1)
        except urllib.error.HTTPError as exc:
            status = int(exc.code)
            headers = dict(exc.headers or {})
            final_url = exc.geturl() or url
            try:
                body = exc.read(MAX_BYTES + 1)
            except Exception:
                body = b""
            error = f"HTTPError {exc.code}"
        except Exception as exc:  # noqa: BLE001
            error = f"{type(exc).__name__}: {exc}"
        elapsed_ms = round((time.monotonic() - started) * 1000, 1)
        self.last_at = time.monotonic()
        self.counts[platform] += 1
        truncated = len(body) > MAX_BYTES
        body = body[:MAX_BYTES]
        content_type = headers.get("Content-Type", "")
        parsed, text = parse_body(body, content_type)
        safe_obj = sanitize(parsed) if parsed is not None else None
        safe_text = sanitize_text(text)
        raw_name = f"{name}.json" if parsed is not None else f"{name}.html"
        raw_bytes = (json.dumps(safe_obj, ensure_ascii=False, indent=2)
                     if safe_obj is not None else safe_text).encode("utf-8")
        (RAW / raw_name).write_bytes(raw_bytes)
        record = {
            "platform": platform, "name": name, "utc": utc(), "url": url, "final_url": final_url,
            "status": status, "content_type": content_type, "bytes_received": len(body),
            "truncated": truncated, "elapsed_ms": elapsed_ms, "error": error,
            "json_code": safe_obj.get("code") if isinstance(safe_obj, dict) else None,
            "raw_file": f"raw/{raw_name}", "raw_bytes": len(raw_bytes),
            "raw_sha256": sha256_bytes(raw_bytes), "sanitized": True,
            "cookie_header_sent": False, "request_count_platform": self.counts[platform],
        }
        # risk detection on sanitized text/JSON; do not retry
        lower = (safe_text or "").lower()
        risk = None
        if platform == "bilibili":
            if status in (403, 412, 429):
                risk = f"HTTP {status}"
            elif isinstance(safe_obj, dict) and safe_obj.get("code") in (-412, -352):
                risk = f"JSON code {safe_obj.get('code')}"
            elif any(token in lower for token in BILI_RISK):
                risk = "body risk/verification marker"
        else:
            if status in (403, 412, 429):
                risk = f"HTTP {status}"
            elif any(token in lower for token in LOGIN_WORDS):
                risk = "login/verification wall marker"
            elif "passport.weibo.com" in (final_url or "").lower():
                risk = "redirected to passport"
        if risk:
            record["risk"] = risk
            self.stopped[platform] = risk
        record["risk"] = risk
        record["stop"] = self.stopped[platform]
        self.requests.append(record)
        self.manifest.append({k: record[k] for k in ("raw_file", "raw_bytes", "raw_sha256", "truncated")})
        with (LOGS / "requests.jsonl").open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
        print(json.dumps({k: record[k] for k in ("platform", "name", "status", "bytes_received",
                                                 "elapsed_ms", "json_code", "risk", "stop")},
                         ensure_ascii=False), flush=True)
        return {"record": record, "parsed": safe_obj, "text": safe_text, "headers": headers}

    def run_bilibili(self) -> None:
        view = self.fetch("bilibili", "bili_view",
                          f"https://api.bilibili.com/x/web-interface/view?aid={BILI_OID}",
                          accept="application/json")
        if self.stopped["bilibili"] or "skipped" in view:
            return
        pages = []
        for pn in (1, 2, 3):
            if self.stopped["bilibili"]:
                break
            out = self.fetch("bilibili", f"bili_reply_p{pn}",
                             f"https://api.bilibili.com/x/v2/reply?type=1&oid={BILI_OID}&pn={pn}&ps=5",
                             accept="application/json")
            if "skipped" in out:
                break
            pages.append(out)
            data = out.get("parsed") or {}
            replies = ((data.get("data") or {}).get("replies") or []) if isinstance(data, dict) else []
            if not replies and pn > 1:
                break
            if pn == 2:
                page = ((data.get("data") or {}).get("page") or {}) if isinstance(data, dict) else {}
                if page.get("count") is not None and page.get("count") <= 10:
                    break
        root = None
        for out in pages:
            data = out.get("parsed") or {}
            for reply in ((data.get("data") or {}).get("replies") or []):
                if isinstance(reply, dict) and reply.get("rpid"):
                    root = reply.get("rpid")
                    break
            if root:
                break
        if root and not self.stopped["bilibili"]:
            self.fetch("bilibili", f"bili_subreply_{root}",
                       f"https://api.bilibili.com/x/v2/reply/reply?type=1&oid={BILI_OID}&root={root}&pn=1&ps=5",
                       accept="application/json")

    def run_weibo(self) -> None:
        first = self.fetch("weibo", "weibo_feed_p1",
                           "https://m.weibo.cn/api/container/getIndex?containerid=102803&page=1",
                           accept="application/json")
        if self.stopped["weibo"] or "skipped" in first:
            return
        second = self.fetch("weibo", "weibo_feed_p2",
                            "https://m.weibo.cn/api/container/getIndex?containerid=102803&page=2",
                            accept="application/json")
        if self.stopped["weibo"] or "skipped" in second:
            return
        self.fetch("weibo", "weibo_search",
                   "https://s.weibo.com/weibo?q=" + urllib.parse.quote("学习计划"),
                   accept="text/html,application/xhtml+xml")

    def write_manifest(self) -> None:
        payload = {
            "generated_utc": utc(),
            "constraints": {"bilibili_limit": BILI_LIMIT, "weibo_limit": WEIBO_LIMIT,
                            "interval_seconds": INTERVAL_SECONDS, "max_bytes": MAX_BYTES,
                            "method": "public GET; no cookie/login; no retries",
                            "sanitized": True},
            "counts": self.counts,
            "stopped": self.stopped,
            "files": self.manifest,
        }
        (BASE / "sha_manifest.json").write_bytes(
            json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8"))


def main() -> int:
    prober = Prober()
    try:
        prober.run_bilibili()
        prober.run_weibo()
    finally:
        prober.write_manifest()
    (BASE / "raw" / "probe_result.json").write_bytes(
        json.dumps({"generated_utc": utc(), "requests": prober.requests,
                    "counts": prober.counts, "stopped": prober.stopped},
                   ensure_ascii=False, indent=2).encode("utf-8"))
    print(json.dumps({"counts": prober.counts, "stopped": prober.stopped}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
