"""Bilibili public first-page comment collector (bounded, read-only)."""

from __future__ import annotations

import dataclasses
import json
import pathlib
import re
import time
import urllib.error
import urllib.request

from . import db, models

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
VIEW_URL = "https://api.bilibili.com/x/web-interface/view"
REPLY_URL = "https://api.bilibili.com/x/v2/reply"
SUBREPLY_URL = "https://api.bilibili.com/x/v2/reply/reply"
MAX_BYTES = 1024 * 1024


@dataclasses.dataclass
class FetchResult:
    status: int
    body: bytes = b""
    headers: dict = dataclasses.field(default_factory=dict)
    final_url: str = ""
    elapsed_ms: float = 0.0
    error: str | None = None


def default_fetch(url: str, timeout: float = 20.0) -> FetchResult:
    """Public GET only: no Cookie header, no login, no proxy jar."""
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    req = urllib.request.Request(url, headers={
        "User-Agent": UA, "Accept": "application/json",
        "Accept-Language": "zh-CN,zh;q=0.9", "Accept-Encoding": "identity",
        "Referer": "https://www.bilibili.com/",
    }, method="GET")
    started = time.monotonic()
    try:
        with opener.open(req, timeout=timeout) as resp:
            body = resp.read(MAX_BYTES + 1)[:MAX_BYTES]
            return FetchResult(int(resp.status), body, dict(resp.headers), resp.geturl(),
                               round((time.monotonic() - started) * 1000, 1))
    except urllib.error.HTTPError as exc:
        try:
            body = exc.read(MAX_BYTES + 1)[:MAX_BYTES]
        except Exception:
            body = b""
        return FetchResult(int(exc.code), body, dict(exc.headers or {}), exc.geturl() or url,
                           round((time.monotonic() - started) * 1000, 1), f"HTTPError {exc.code}")
    except Exception as exc:  # noqa: BLE001
        return FetchResult(0, b"", {}, url, round((time.monotonic() - started) * 1000, 1),
                           f"{type(exc).__name__}: {exc}")


def sanitize(value, path: str = ""):
    """Drop nicknames/avatars/profile links; keep ids, rpid/parent/root and text."""
    if isinstance(value, dict):
        out = {}
        for key, item in value.items():
            lowered = str(key).lower()
            if lowered in {"uname", "handle", "avatar", "avatar_item", "face", "sign", "sex",
                           "profile_url", "screen_name", "official_verify", "pendant", "nameplate",
                           "vip", "fans_detail", "tribee", "user_sailing", "is_contractor",
                           "contract_desc", "level_info", "rank", "face_nft_new",
                           "is_senior_member", "senior"}:
                out[key] = "u***" if lowered in {"uname", "handle", "screen_name"} else None
                continue
            if lowered == "name" and any(p in path for p in ("owner", "member", "user")):
                out[key] = "u***"
                continue
            if lowered in {"url", "uri", "href"} and isinstance(item, str) and any(
                    host in item for host in ("space.bilibili.com", "weibo.com/u/", "/profile")):
                out[key] = None
                continue
            out[key] = sanitize(item, f"{path}.{key}" if path else str(key))
        return out
    if isinstance(value, list):
        return [sanitize(item, path) for item in value]
    if isinstance(value, str):
        return re.sub(r"@[A-Za-z0-9_\-\u4e00-\u9fff]{2,}", "@u***", value)
    return value


def _save_raw(raw_dir: pathlib.Path, batch_id: str, kind: str, payload) -> tuple[str, str]:
    raw_dir.mkdir(parents=True, exist_ok=True)
    path = raw_dir / f"bilibili_{kind}_{batch_id}.json"
    data = json.dumps(sanitize(payload), ensure_ascii=False, indent=2).encode("utf-8")
    path.write_bytes(data)
    return str(path), models.sha256_bytes(data)


def _stop_for(status: int, data, error: str | None) -> str | None:
    if error:
        return error
    if status != 200:
        return f"http_{status}"
    if not isinstance(data, dict):
        return "invalid_json"
    code = data.get("code")
    if code in (-412, -352):
        return f"json_code_{code}"
    if code != 0:
        return f"json_code_{code}"
    return None


def collect(*, db_path: str | pathlib.Path, raw_dir: str | pathlib.Path, aid: int | None = None,
            bvid: str | None = None, budget: int = 5, interval: float = 3.0,
            include_subreply: bool = False, origin_kind: str = "real",
            fetch=None) -> dict:
    if origin_kind not in models.ORIGIN_KINDS:
        raise ValueError("invalid origin_kind")
    if not aid and not bvid:
        raise ValueError("aid_or_bvid_required")
    if budget < 1:
        raise ValueError("budget_must_be_positive")
    fetch = fetch or default_fetch
    raw_dir = pathlib.Path(raw_dir)
    conn = db.init_db(db_path)
    run_id, batch = db.start_run(
        conn, kind="bilibili", platform="bilibili",
        budget={"max_requests": budget, "interval_seconds": interval, "max_pages": 1},
        raw_dir=raw_dir)
    stats = {"requests": 0, "comments": 0, "new": 0, "updated": 0, "duplicate": 0,
             "errors": [], "stop_reason": None, "raw_files": []}
    last_at = 0.0

    def request(url: str):
        nonlocal last_at
        if stats["requests"] >= budget:
            stats["stop_reason"] = "budget_exhausted"
            return None
        wait = interval - (time.monotonic() - last_at)
        if last_at and wait > 0:
            time.sleep(wait)
        result = fetch(url)
        last_at = time.monotonic()
        stats["requests"] += 1
        try:
            data = json.loads(result.body.decode("utf-8")) if result.body else None
        except Exception:
            data = None
        reason = _stop_for(result.status, data, result.error)
        if reason:
            stats["stop_reason"] = reason
            stats["errors"].append({"url": url, "status": result.status, "reason": reason})
            return None
        return data

    try:
        view_url = f"{VIEW_URL}?aid={int(aid)}" if aid else f"{VIEW_URL}?bvid={bvid}"
        view = request(view_url)
        if view is None:
            db.finish_run(conn, run_id, status="failed", stop_reason=stats["stop_reason"], stats=stats)
            return {**stats, "status": "failed", "batch_id": batch, "run_id": run_id}
        view_path, view_sha = _save_raw(raw_dir, batch, "view", view)
        stats["raw_files"].append({"kind": "view", "path": view_path, "sha256": view_sha})
        vdata = view.get("data") or {}
        actual_aid = vdata.get("aid") or aid
        actual_bvid = vdata.get("bvid") or bvid
        title = vdata.get("title")
        if not actual_aid:
            stats["stop_reason"] = "aid_missing"
            db.finish_run(conn, run_id, status="failed", stop_reason="aid_missing", stats=stats)
            return {**stats, "status": "failed", "batch_id": batch, "run_id": run_id}

        # Mandatory sort=2; only page 1 is allowed by this adapter.
        reply_url = f"{REPLY_URL}?type=1&oid={int(actual_aid)}&pn=1&ps=5&sort=2"
        reply = request(reply_url)
        if reply is None:
            status = "partial" if stats["stop_reason"] == "budget_exhausted" else "failed"
            db.finish_run(conn, run_id, status=status, stop_reason=stats["stop_reason"], stats=stats)
            return {**stats, "status": status, "batch_id": batch, "run_id": run_id}
        reply_path, reply_sha = _save_raw(raw_dir, batch, "reply_p1", reply)
        stats["raw_files"].append({"kind": "reply_p1", "path": reply_path, "sha256": reply_sha})
        replies = (reply.get("data") or {}).get("replies") or []
        root_id = None
        for reply_item in replies:
            if not isinstance(reply_item, dict):
                continue
            rpid = reply_item.get("rpid")
            content = reply_item.get("content") or {}
            quote = str(content.get("message") or "").strip()
            if not rpid or not quote:
                continue
            if root_id is None:
                root_id = rpid
            parent = reply_item.get("parent")
            signal = {
                "platform": "bilibili", "native_id": str(rpid),
                "parent_native_id": str(parent) if parent not in (None, 0, "0") else None,
                "url": f"https://www.bilibili.com/video/{actual_bvid}#reply{rpid}" if actual_bvid else None,
                "title": title, "quote": quote,
                "lang": models.lang_of(quote)[0], "lang_source": "heuristic",
                "listed_price_minor": None, "effective_price_minor": None,
                "reference_price_minor": None, "wants": None,
                "collected_at": models.utc_now(), "collected_at_scope": "row",
                "origin_kind": origin_kind, "raw_sha256": reply_sha,
                "raw_ref": reply_path, "batch_id": batch,
            }
            signal["content_hash"] = models.content_hash(
                platform="bilibili", native_id=signal["native_id"], quote=quote,
                listed_price_minor=None, effective_price_minor=None, wants=None)
            outcome, _ = db.upsert_signal(conn, signal)
            stats[outcome] += 1
            stats["comments"] += 1

        if include_subreply and root_id:
            sub_url = f"{SUBREPLY_URL}?type=1&oid={int(actual_aid)}&root={root_id}&pn=1&ps=2"
            sub = request(sub_url)
            if sub is not None:
                sub_path, sub_sha = _save_raw(raw_dir, batch, f"subreply_{root_id}", sub)
                stats["raw_files"].append({"kind": f"subreply_{root_id}", "path": sub_path, "sha256": sub_sha})
                for item in (sub.get("data") or {}).get("replies") or []:
                    if not isinstance(item, dict):
                        continue
                    rpid = item.get("rpid")
                    quote = str((item.get("content") or {}).get("message") or "").strip()
                    if not rpid or not quote:
                        continue
                    signal = {
                        "platform": "bilibili", "native_id": str(rpid),
                        "parent_native_id": str(root_id),
                        "url": f"https://www.bilibili.com/video/{actual_bvid}#reply{rpid}" if actual_bvid else None,
                        "title": title, "quote": quote,
                        "lang": models.lang_of(quote)[0], "lang_source": "heuristic",
                        "listed_price_minor": None, "effective_price_minor": None,
                        "reference_price_minor": None, "wants": None,
                        "collected_at": models.utc_now(), "collected_at_scope": "row",
                        "origin_kind": origin_kind, "raw_sha256": sub_sha,
                        "raw_ref": sub_path, "batch_id": batch,
                    }
                    signal["content_hash"] = models.content_hash(
                        platform="bilibili", native_id=signal["native_id"], quote=quote,
                        listed_price_minor=None, effective_price_minor=None, wants=None)
                    outcome, _ = db.upsert_signal(conn, signal)
                    stats[outcome] += 1
                    stats["comments"] += 1

        status = ("partial" if stats["stop_reason"] == "budget_exhausted"
                  else "failed" if stats["stop_reason"] else "complete")
        db.finish_run(conn, run_id, status=status, stop_reason=stats["stop_reason"], stats=stats)
        return {**stats, "status": status, "batch_id": batch, "run_id": run_id}
    except Exception as exc:  # noqa: BLE001
        stats["errors"].append({"reason": f"{type(exc).__name__}: {exc}"})
        db.finish_run(conn, run_id, status="failed", stop_reason=stats.get("stop_reason") or str(exc),
                      stats=stats)
        return {**stats, "status": "failed", "batch_id": batch, "run_id": run_id}
    finally:
        conn.close()

def collect_round(*, db_path, round_id: int, raw_dir, aid: int | None = None,
                  bvid: str | None = None, budget: int = 3, interval: float = 3.0,
                  fetch=None, pause_after_items: int | None = None,
                  sleep=None, clock=None) -> dict:
    """Item-level Bilibili round: view + reply are two items; resume skips done items."""
    from . import rounds as rounds_mod
    fetch = fetch or default_fetch
    sleep = sleep or time.sleep
    clock = clock or time.monotonic
    raw_dir = pathlib.Path(raw_dir)
    conn = db.init_db(db_path)
    try:
        state = rounds_mod.status(conn, round_id)
        if state["status"] not in ("running", "paused", "partial"):
            raise ValueError(f"round_not_running:{state['status']}")
        if state["status"] in ("paused", "partial"):
            rounds_mod.resume(conn, round_id)
            state = rounds_mod.status(conn, round_id)
        budget_json = json.loads(state["budget_json"] or "{}")
        max_requests = int(budget_json.get("max_requests", budget))
        interval = float(budget_json.get("interval", interval))
        stats = json.loads(state["stats_json"] or "{}")
        requests_used = int(stats.get("requests_used", 0))
        stats.setdefault("errors", [])
        items = {i["item_key"]: i for i in state["items"]}
        for key in ("bilibili:view", "bilibili:reply"):
            if key not in items:
                rounds_mod.add_item(conn, round_id, key)
        items = {i["item_key"]: i for i in rounds_mod.status(conn, round_id)["items"]}
        last_item = stats.get("last_item_key")
        order = ["bilibili:view", "bilibili:reply"]
        processed = 0
        last_at = None
        for key in order:
            item = items.get(key)
            if item and item["state"] == "done":
                continue
            cur_status = rounds_mod.status(conn, round_id)["status"]
            if cur_status == "cancelled":
                return {**stats, "status": "cancelled", "stop_reason": "cancelled",
                        "requests_used": requests_used, "round_id": round_id}
            if cur_status == "paused":
                return {**stats, "status": "paused", "stop_reason": "user_pause",
                        "requests_used": requests_used, "round_id": round_id}
            if pause_after_items is not None and processed >= pause_after_items:
                rounds_mod.pause(conn, round_id, cursor=stats.get("cursor") or None)
                return {**stats, "status": "paused", "stop_reason": "user_pause",
                        "requests_used": requests_used, "round_id": round_id}
            if requests_used >= max_requests:
                stats["stop_reason"] = "budget_exhausted"
                cursor = stats.get("cursor") or {"last_item_key": stats.get("last_item_key")}
                if cursor.get("last_item_key"):
                    conn.execute("UPDATE rounds SET cursor_json=? WHERE id=?",
                                 (json.dumps(cursor, ensure_ascii=False), round_id))
                    conn.commit()
                rounds_mod.update_stats(conn, round_id, stats)
                rounds_mod.transition(conn, round_id, "partial")
                return {**stats, "status": "partial", "requests_used": requests_used,
                        "cursor": cursor,
                        "stop_reason": "budget_exhausted"}
            # perform exactly one item request
            if key.endswith("view"):
                url = f"{VIEW_URL}?aid={int(aid)}" if aid else f"{VIEW_URL}?bvid={bvid}"
            else:
                view_stats = stats.get("view") or {}
                actual_aid = view_stats.get("aid") or aid
                url = f"{REPLY_URL}?type=1&oid={int(actual_aid)}&pn=1&ps=5&sort=2"
            if last_at is not None and interval > 0:
                wait = interval - (clock() - last_at)
                if wait > 0:
                    sleep(wait)
            rounds_mod.mark_item(conn, round_id, key, "processing")
            result = fetch(url)
            last_at = clock()
            requests_used += 1
            stats["requests_used"] = requests_used
            try:
                data = json.loads(result.body.decode("utf-8")) if result.body else None
            except Exception:
                data = None
            reason = _stop_for(result.status, data, result.error)
            if reason:
                stats["stop_reason"] = reason
                stats["errors"].append({"url": url, "status": result.status, "reason": reason})
                rounds_mod.mark_item(conn, round_id, key, "failed", error=reason)
                rounds_mod.update_stats(conn, round_id, stats)
                rounds_mod.transition(conn, round_id, "failed")
                return {**stats, "status": "failed", "requests_used": requests_used}
            if key.endswith("view"):
                vdata = (data.get("data") or {})
                stats["view"] = {"aid": vdata.get("aid") or aid, "bvid": vdata.get("bvid") or bvid,
                                 "title": vdata.get("title")}
                path, sha = _save_raw(raw_dir, str(state["id"]), "view", data)
                stats.setdefault("raw_files", []).append({"kind": "view", "path": path, "sha256": sha})
            else:
                path, sha = _save_raw(raw_dir, str(state["id"]), "reply_p1", data)
                stats.setdefault("raw_files", []).append({"kind": "reply_p1", "path": path, "sha256": sha})
                vdata = (data.get("data") or {})
                for r in vdata.get("replies") or []:
                    if not isinstance(r, dict):
                        continue
                    rpid = r.get("rpid")
                    quote = str((r.get("content") or {}).get("message") or "").strip()
                    if not rpid or not quote:
                        continue
                    sig = {
                        "platform": "bilibili", "native_id": str(rpid), "parent_native_id": None,
                        "url": f"https://www.bilibili.com/video/{stats['view'].get('bvid')}#reply{rpid}",
                        "title": stats["view"].get("title"), "quote": quote,
                        "lang": models.lang_of(quote)[0], "lang_source": "heuristic",
                        "listed_price_minor": None, "effective_price_minor": None,
                        "reference_price_minor": None, "wants": None,
                        "collected_at": models.utc_now(), "collected_at_scope": "row",
                        "origin_kind": "real", "raw_sha256": sha, "raw_ref": path,
                        "batch_id": f"round:{round_id}",
                    }
                    sig["content_hash"] = models.content_hash(
                        platform="bilibili", native_id=sig["native_id"], quote=quote,
                        listed_price_minor=None, effective_price_minor=None, wants=None)
                    db.upsert_signal(conn, sig)
            rounds_mod.mark_item(conn, round_id, key, "done")
            stats["cursor"] = {"last_item_key": key}
            stats["last_item_key"] = key
            rounds_mod.update_stats(conn, round_id, stats)
            processed += 1
            if pause_after_items is not None and processed >= pause_after_items:
                rounds_mod.pause(conn, round_id, cursor=stats["cursor"])
                return {**stats, "status": "paused", "stop_reason": "user_pause",
                        "requests_used": requests_used, "round_id": round_id}
        cur_status = rounds_mod.status(conn, round_id)["status"]
        if cur_status == "cancelled":
            return {**stats, "status": "cancelled", "stop_reason": "cancelled",
                    "requests_used": requests_used, "round_id": round_id}
        if cur_status == "paused":
            return {**stats, "status": "paused", "stop_reason": "user_pause",
                    "requests_used": requests_used, "round_id": round_id}
        rounds_mod.update_stats(conn, round_id, stats)
        rounds_mod.transition(conn, round_id, "complete")
        return {**stats, "status": "complete", "requests_used": requests_used, "round_id": round_id}
    finally:
        conn.close()
