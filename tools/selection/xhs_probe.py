"""Visible single-page XHS probe (V9-9).

One visible window, one homepage request, optional one note request only when
the homepage is `valid` and exposes an /explore/ link. Saves sanitized DOM
skeletons only (no text nodes, user paths redacted). No login, no scrolling,
no pagination. Run with the x-collect venv for nodriver:

    <x-collect venv>/python tools/selection/xhs_probe.py
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import pathlib
import re
import urllib.parse
import sys
from html.parser import HTMLParser

REPO = pathlib.Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from tools.selection import categories, db, models, triage, xiaohongshu  # noqa: E402
from tools.selection.xiaohongshu import classify_note, parse_note_fields  # noqa: E402

HOME = "https://www.xiaohongshu.com"
PROFILE = pathlib.Path(r"C:\Users\19183\.dsh\tools\xhs-collect\profile")
CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
RAW_DIR = REPO / "docs" / "validation" / "v9" / "xhs-readiness" / "raw"
ISO_DB = REPO / "tools" / "selection" / "runtime" / "xhs_first.sqlite3"
DEFAULT_SEED = RAW_DIR / "probe_20261026T023927Z.html"
LOGIN_MARKERS = xiaohongshu.LOGIN_MARKERS
SEARCH_GROUPS = {
    "A": ("求推荐", "有没有", "怎么做"),
    "B": ("不会用", "怎么选", "踩坑"),
}


def _text(value) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _summary(text: str, limit: int = 200) -> str:
    text = _text(text)
    return text if len(text) <= limit else text[:limit].rstrip() + "…"


def classify_online(visible_text: str, links: list[str]) -> tuple[str, list[str]]:
    """Return (valid|login_required|risk|unknown, rationale)."""
    text = _text(visible_text).lower()
    markers = xiaohongshu.RISK_MARKERS["text"]
    risk_hits = [m for m in markers if m not in LOGIN_MARKERS and m.lower() in text]
    login_hits = [m for m in LOGIN_MARKERS if m.lower() in text]
    if risk_hits:
        return "risk", [f"risk_marker:{m}" for m in risk_hits]
    if login_hits:
        return "login_required", [f"login_marker:{m}" for m in login_hits]
    if links:
        return "valid", [f"explore_links:{len(links)}"]
    return "unknown", ["no_explore_links"]


def _redact_href(href: str) -> str:
    href = str(href or "").strip()
    if not href:
        return ""
    path = href.split("#", 1)[0].split("?", 1)[0]
    if "/explore/" in path:
        return path if path.startswith("/") else "/" + path.split("/", 3)[-1]
    if "/user/profile/" in path:
        return "/user/profile/[redacted]"
    if path.startswith("http"):
        return "[external]"
    return path[:120]


def sanitize_skeleton(html: str) -> str:
    """DOM skeleton: tags + safe attributes only, no text nodes/nicknames."""
    keep = ("class", "id", "data-testid", "href")

    class _S(HTMLParser):
        def __init__(self):
            super().__init__(convert_charrefs=False)
            self.out = []

        def handle_starttag(self, tag, attrs):
            parts = []
            for k, v in attrs:
                if k not in keep:
                    continue
                if k == "href":
                    parts.append(f'{k}="{_redact_href(v)}"')
                else:
                    parts.append(f'{k}="{_text(v)[:120]}"')
            self.out.append("<" + tag + (" " + " ".join(parts) if parts else "") + ">")

        def handle_startendtag(self, tag, attrs):
            self.handle_starttag(tag, attrs)

        def handle_endtag(self, tag):
            self.out.append(f"</{tag}>")

        def handle_data(self, data):
            return  # never save text nodes

    p = _S()
    p.feed(html or "")
    p.close()
    return "\n".join(p.out)


def extract_explore_links(html: str) -> list[str]:
    out = []
    for m in re.finditer(r'href=["\']([^"\']*/explore/[^"\']+)["\']', html or "", re.I):
        href = m.group(1)
        url = href if href.startswith("http") else HOME.rstrip("/") + "/" + href.lstrip("/")
        url = url.split("?", 1)[0].split("#", 1)[0]
        if url not in out:
            out.append(url)
    return out


def _save(text: str, name: str) -> tuple[str, str]:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    path = RAW_DIR / name
    data = text.encode("utf-8")
    path.write_bytes(data)  # no Windows newline translation; sha matches the file
    return str(path), hashlib.sha256(data).hexdigest()


def _ingest(fields: dict, url: str, raw_sha: str, batch_id: str) -> dict:
    if fields.get("error_page"):
        return {"written": 0, "reason": "error_page"}
    if fields.get("login_required"):
        return {"written": 0, "reason": "login_required"}
    if not fields.get("complete") or not fields.get("native_id") or not (fields.get("title") or fields.get("desc")):
        return {"written": 0, "reason": "incomplete_note"}
    conn = db.init_db(ISO_DB)
    try:
        quote = _summary(fields.get("desc") or fields.get("title") or "")
        lang, lang_src = models.lang_of(fields.get("title") or quote)
        sig = {
            "platform": "xiaohongshu", "native_id": fields["native_id"],
            "parent_native_id": None, "url": url, "title": fields.get("title") or "",
            "quote": quote, "lang": lang, "lang_source": lang_src,
            "listed_price_minor": None, "effective_price_minor": None,
            "reference_price_minor": None, "wants": None,
            "collected_at": models.utc_now(), "collected_at_scope": "row",
            "origin_kind": "real", "raw_sha256": raw_sha, "raw_ref": "",
            "batch_id": batch_id,
            "content_hash": models.content_hash(
                platform="xiaohongshu", native_id=fields["native_id"], quote=quote,
                listed_price_minor=None, effective_price_minor=None, wants=None),
        }
        outcome, sid = db.upsert_signal(conn, sig)
        count = conn.execute("SELECT COUNT(*) FROM signals").fetchone()[0]
        return {"written": 1 if outcome in ("new", "update") else 0, "outcome": outcome,
                "signal_id": int(sid), "signals": count}
    finally:
        conn.close()


def run_outputs(db_path=ISO_DB) -> dict:
    conn = db.init_db(db_path)
    try:
        cat = categories.run_categorize(conn)
        cards = categories.make_cards(conn)
        review = conn.execute("SELECT COUNT(*) FROM review_queue").fetchone()[0]
        return {"categorize": cat, "cards": cards, "review": review}
    finally:
        conn.close()


def query_meta(url: str) -> dict:
    """Return query key -> value length only; never retain token plaintext."""
    q = urllib.parse.parse_qs(urllib.parse.urlparse(url or "").query)
    return {k: len(v[0]) if v else 0 for k, v in sorted(q.items())}


async def probe_note_async(seed_html: pathlib.Path = DEFAULT_SEED, max_tries: int = 3,
                           interval: float = 15.0) -> dict:
    """Click the first live feed card (no direct URL get); max 2 page loads."""
    import nodriver as uc

    started = models.utc_now()
    result = {"mode": "note-click", "started_utc": started, "requests": 0,
              "page_loads": 0, "attempts": [], "note": None, "db": None,
              "categorize": None, "hypotheses": None}
    browser = await uc.start(headless=False, user_data_dir=str(PROFILE),
                             browser_executable_path=CHROME)
    try:
        tab = await browser.get(HOME)
        result["requests"] += 1
        result["page_loads"] += 1
        await asyncio.sleep(8)
        hrefs = await tab.evaluate(
            "Array.from(document.querySelectorAll('section.note-item a.title, "
            "section.note-item a.cover')).map(a => a.href)")
        def _js_value(v):
            return v.get("value") if isinstance(v, dict) and "value" in v else v
        result["home_hrefs"] = [{"path": urllib.parse.urlparse(str(_js_value(h))).path,
                                 "query": query_meta(str(_js_value(h)))} for h in (hrefs or [])[:3]]
        await asyncio.sleep(interval)
        element = None
        try:
            element = await tab.select("section.note-item a.title", timeout=8)
        except Exception:  # noqa: BLE001
            element = await tab.select("section.note-item a.cover", timeout=8)
        await element.click()
        await asyncio.sleep(8)
        note_url = str(await tab.evaluate("location.href") or "")
        result["requests"] += 1
        result["page_loads"] += 1
        visible = str(await tab.evaluate("document.body ? document.body.innerText : ''") or "")
        html = await tab.get_content()
        fields = parse_note_fields(html, note_url)
        page, why = classify_online(visible, [])
        if page == "login_required":
            fields["login_required"] = True
        if page == "risk":
            fields["risk"] = True
        verdict = classify_note(fields)
        skeleton = sanitize_skeleton(html)
        path, sha = _save(skeleton, f"note_click_{started.replace(':', '').replace('-', '')}.html")
        out_fields = {k: v for k, v in fields.items() if k != "author"}
        attempt = {"index": 1, "url": urllib.parse.urlparse(note_url).path,
                   "query": query_meta(note_url), "verdict": verdict, "rationale": why,
                   "raw": {"path": path, "sha256": sha,
                           "bytes": len(skeleton.encode("utf-8"))},
                   "fields": out_fields}
        result["attempts"].append(attempt)
        if verdict == "note":
            result["note"] = {"url": urllib.parse.urlparse(note_url).path,
                              **out_fields, "raw_sha256": sha}
            batch_id = f"first-real-{started}"
            result["db"] = _ingest(fields, note_url, sha, batch_id)
            if result["db"].get("written"):
                result["categorize"] = run_outputs()
        elif verdict == "error_page":
            result["hypotheses"] = {
                "click_url_query_keys": sorted(query_meta(note_url)),
                "click_url_token_lengths": query_meta(note_url),
                "home_hrefs_have_query": any(x["query"] for x in result["home_hrefs"]),
                "login_required": bool(fields.get("login_required")),
                "conclusion": "click still error; no extra request; decide query reattach vs login wall next",
            }
        result["completed"] = True
        return result
    finally:
        try:
            browser.stop()
        except Exception:  # noqa: BLE001
            pass


def batch_should_stop(verdict: str) -> bool:
    return verdict in ("login_required", "risk")


def batch_limit(max_notes: int, max_loads: int) -> int:
    """Homepage + N clicks + (N-1) backs must fit max_loads."""
    return max(0, min(int(max_notes), int(max_loads) // 2))


async def probe_batch_async(max_notes: int = 8, max_loads: int = 10,
                            interval: float = 15.0) -> dict:
    import nodriver as uc

    started = models.utc_now()
    limit = batch_limit(max_notes, max_loads)
    batch_id = f"first-batch-{started}"
    result = {"mode": "batch", "started_utc": started, "batch_id": batch_id,
              "max_notes": max_notes, "max_loads": max_loads, "limit": limit,
              "page_loads": 0, "requests": 0, "attempts": [], "db": None,
              "categorize": None, "completed": False}
    browser = await uc.start(headless=False, user_data_dir=str(PROFILE),
                             browser_executable_path=CHROME)
    try:
        tab = await browser.get(HOME)
        result["page_loads"] += 1
        result["requests"] += 1
        await asyncio.sleep(8)
        for idx in range(limit):
            if idx > 0:
                await asyncio.sleep(interval)
                await tab.back()
                result["page_loads"] += 1
                result["requests"] += 1
                await asyncio.sleep(3)
            elements = await tab.select_all("section.note-item a.title", timeout=8)
            if len(elements) <= idx:
                result["attempts"].append({"index": idx + 1, "verdict": "no_card"})
                break
            await elements[idx].click()
            result["page_loads"] += 1
            result["requests"] += 1
            await asyncio.sleep(5)
            note_url = str(await tab.evaluate("location.href") or "")
            visible = str(await tab.evaluate("document.body ? document.body.innerText : ''") or "")
            html = await tab.get_content()
            fields = parse_note_fields(html, note_url)
            page, why = classify_online(visible, [])
            if page == "login_required":
                fields["login_required"] = True
            if page == "risk":
                fields["risk"] = True
            verdict = classify_note(fields)
            skeleton = sanitize_skeleton(html)
            path, sha = _save(skeleton, f"batch_{idx + 1}_{started.replace(':', '').replace('-', '')}.html")
            out_fields = {k: v for k, v in fields.items() if k != "author"}
            attempt = {"index": idx + 1, "url": urllib.parse.urlparse(note_url).path,
                       "query": query_meta(note_url), "verdict": verdict, "rationale": why,
                       "raw": {"path": path, "sha256": sha,
                               "bytes": len(skeleton.encode("utf-8"))},
                       "fields": out_fields}
            result["attempts"].append(attempt)
            if verdict == "note":
                dbout = _ingest(fields, note_url, sha, batch_id)
                result.setdefault("db_notes", []).append({"index": idx + 1, **dbout})
            if batch_should_stop(verdict):
                result["stopped"] = f"{verdict} at card {idx + 1}"
                break
        if result.get("db_notes"):
            result["categorize"] = run_outputs()
        result["completed"] = True
        return result
    finally:
        try:
            browser.stop()
        except Exception:  # noqa: BLE001
            pass


def search_words(group: str) -> tuple[str, ...]:
    return SEARCH_GROUPS[group]


def search_url(keyword: str) -> str:
    return xiaohongshu.search_url(keyword)


def _quote60(text: str) -> str:
    text = re.sub(r"1[3-9]\d{9}", "[phone]", str(text or ""))
    text = re.sub(r"@[\w\u4e00-\u9fff-]{1,30}", "[user]", text)
    text = _text(text)
    return text if len(text) <= 60 else text[:60].rstrip() + "…"


def parse_search_page(html: str, keyword: str, *, limit: int = 3,
                      visible_text: str | None = None) -> dict:
    res = xiaohongshu.parse_results(html, limit=limit, risk_text=visible_text, risk_dom=False)
    if not res.get("ok"):
        return {"ok": False, "keyword": keyword, "stop": res.get("stop_reason"),
                "records": []}
    records = []
    for s in res.get("signals") or []:
        text = f"{s.get('title') or ''} {s.get('quote') or ''}"
        records.append({
            "keyword": keyword, "native_id": s.get("native_id"), "url": s.get("url"),
            "title": s.get("title") or "", "quote": _quote60(s.get("quote") or ""),
            "triage": triage.classify(text), "signal": s,
        })
    return {"ok": True, "keyword": keyword, "stop": None, "records": records}


def search_page_state(visible_text: str, records: list[dict]) -> str:
    page, _ = classify_online(visible_text, [r.get("url") for r in records if r.get("url")])
    if page in ("login_required", "risk"):
        return page
    return "ok"


def triage_summary(records: list[dict]) -> dict:
    counts = {"demand": 0, "promo": 0, "noise": 0}
    for r in records:
        counts[r.get("triage", "noise")] = counts.get(r.get("triage", "noise"), 0) + 1
    valid = len(records)
    return {"counts": counts, "valid": valid,
            "demand_rate": (counts["demand"] / valid) if valid else 0.0}


def group_summary(records: list[dict]) -> dict:
    by_group = {"A": [], "B": []}
    for r in records:
        group = r.get("group")
        if group in by_group:
            by_group[group].append(r)
    return {g: triage_summary(rs) for g, rs in by_group.items()}


def quote_evidence(records: list[dict], limit: int = 3) -> list[dict]:
    out = []
    for r in records:
        if r.get("triage") == "demand":
            out.append({"keyword": r.get("keyword"), "quote": _quote60(r.get("quote") or r.get("title") or "")})
            if len(out) >= limit:
                return out
    if not out:
        for r in records:
            if r.get("triage") in ("promo", "noise"):
                out.append({"keyword": r.get("keyword"), "triage": r.get("triage"),
                            "quote": _quote60(r.get("quote") or r.get("title") or "")})
                if len(out) >= limit:
                    break
    return out


def _ingest_search(records: list[dict], batch_id: str, limit: int = 6) -> dict:
    written = 0
    conn = db.init_db(ISO_DB)
    try:
        for r in records:
            if written >= limit:
                break
            if r.get("triage") != "demand":
                continue
            s = dict(r.get("signal") or {})
            if not s.get("native_id") or not (s.get("title") or s.get("quote")):
                continue
            s.update({"origin_kind": "real", "batch_id": batch_id,
                      "collected_at": models.utc_now(), "collected_at_scope": "row"})
            outcome, sid = db.upsert_signal(conn, s)
            written += 1 if outcome in ("new", "update") else 0
        return {"written": written}
    finally:
        conn.close()


async def probe_search_async(group: str | None = None, per_word: int = 3,
                             interval: float = 15.0) -> dict:
    import nodriver as uc

    started = models.utc_now()
    groups = [group] if group in SEARCH_GROUPS else ["A", "B"]
    batch_id = f"xhs-search-{started}"
    result = {"mode": "search", "started_utc": started, "batch_id": batch_id,
              "groups": groups, "per_word": per_word, "page_loads": 0,
              "records": [], "words": [], "raw": [], "stopped": None, "completed": False,
              "db": None, "summaries": None, "quotes": None}
    try:
        browser = await asyncio.wait_for(
            uc.start(headless=False, user_data_dir=str(PROFILE),
                     browser_executable_path=CHROME), timeout=30)
    except Exception as exc:  # noqa: BLE001
        result["stopped"] = f"browser_start_timeout:{type(exc).__name__}"
        result["completed"] = True
        return result
    try:
        tab = await asyncio.wait_for(browser.get(HOME), timeout=20)
        result["page_loads"] += 1
        await asyncio.sleep(8)
        for g in groups:
            for idx, word in enumerate(SEARCH_GROUPS[g]):
                if result["page_loads"] >= 8:
                    result["stopped"] = "max_page_loads"
                    break
                if result["page_loads"] > 1:
                    await asyncio.sleep(interval)
                try:
                    from nodriver import cdp
                    await asyncio.wait_for(
                        tab.send(cdp.page.navigate(search_url(word))), timeout=20)
                    result["page_loads"] += 1
                    await asyncio.sleep(6)
                    visible = str(await asyncio.wait_for(
                        tab.evaluate("document.body ? document.body.innerText : ''"), timeout=10) or "")
                    html = await asyncio.wait_for(tab.get_content(), timeout=10)
                    page_url = str(await asyncio.wait_for(tab.evaluate("location.href"), timeout=5) or "")
                except Exception as exc:  # noqa: BLE001
                    result["stopped"] = f"search_nav_timeout:{type(exc).__name__}"
                    break
                skeleton = sanitize_skeleton(html)
                raw_path, raw_sha = _save(
                    skeleton, f"search_{g}_{idx + 1}_{started.replace(':', '').replace('-', '')}.html")
                result["raw"].append({"group": g, "keyword": word, "path": raw_path,
                                      "sha256": raw_sha,
                                      "bytes": len(skeleton.encode("utf-8"))})
                parsed = parse_search_page(html, word, limit=per_word, visible_text=visible)
                if not parsed["ok"]:
                    result["stopped"] = parsed.get("stop") or "parse_stop"
                    break
                state = search_page_state(visible, parsed["records"])
                for r in parsed["records"]:
                    r["group"] = g
                result["words"].append({"group": g, "keyword": word,
                                        "url": urllib.parse.urlparse(page_url).path,
                                        "query": query_meta(page_url),
                                        "count": len(parsed["records"]), "state": state})
                result["records"].extend(parsed["records"])
                if state in ("login_required", "risk"):
                    result["stopped"] = state
                    break
            if result["stopped"]:
                break
        result["summaries"] = group_summary(result["records"])
        result["quotes"] = quote_evidence(result["records"])
        if result["records"]:
            result["db"] = _ingest_search(result["records"], batch_id, limit=6)
            if result["db"].get("written"):
                result["categorize"] = run_outputs()
        result["completed"] = True
        return result
    finally:
        try:
            browser.stop()
        except Exception:  # noqa: BLE001
            pass


async def probe_async(wait: float = 8.0, interval: float = 15.0) -> dict:
    import nodriver as uc

    started = models.utc_now()
    browser = await uc.start(headless=False, user_data_dir=str(PROFILE),
                             browser_executable_path=CHROME)
    result = {"started_utc": started, "requests": 0, "online": "unknown",
              "rationale": [], "raw": [], "note": None, "db": None}
    try:
        tab = await browser.get(HOME)
        result["requests"] += 1
        await asyncio.sleep(wait)
        visible = str(await tab.evaluate("document.body ? document.body.innerText : ''") or "")
        html = await tab.get_content()
        links = extract_explore_links(html)
        verdict, why = classify_online(visible, links)
        result.update({"online": verdict, "rationale": why, "links": links[:3],
                       "login_wall": verdict == "login_required", "risk": verdict == "risk"})
        skeleton = sanitize_skeleton(html)
        path, sha = _save(skeleton, f"probe_{started.replace(':', '').replace('-', '')}.html")
        result["raw"].append({"path": path, "sha256": sha, "bytes": len(skeleton.encode("utf-8")),
                              "kind": "home_skeleton"})
        if verdict != "valid" or not links:
            return result
        await asyncio.sleep(interval)
        note_url = links[0]
        note_tab = await browser.get(note_url)
        result["requests"] += 1
        await asyncio.sleep(4)
        note_html = await note_tab.get_content()
        fields = parse_note_fields(note_html, note_url)
        note_skeleton = sanitize_skeleton(note_html)
        npath, nsha = _save(note_skeleton, f"probe_note_{started.replace(':', '').replace('-', '')}.html")
        result["raw"].append({"path": npath, "sha256": nsha,
                              "bytes": len(note_skeleton.encode("utf-8")), "kind": "note_skeleton"})
        output_fields = {k: v for k, v in fields.items() if k != "author"}
        output_fields["author_redacted"] = True
        result["note"] = {"url": note_url, **output_fields, "raw_sha256": nsha}
        batch_id = f"first-real-{started}"
        result["db"] = _ingest(fields, note_url, nsha, batch_id)
        return result
    finally:
        try:
            browser.stop()
        except Exception:  # noqa: BLE001
            pass


def exit_code(result: dict) -> int:
    if result.get("mode") == "search":
        stopped = str(result.get("stopped") or "")
        if stopped:
            low = stopped.lower()
            return 5 if ("risk" in low or "captcha" in low or "dom" in low) else 6
        if not result.get("records"):
            return 6
        return 0 if result.get("completed") else 6
    if str(result.get("mode", "")).startswith("note") or result.get("mode") == "batch":
        return 0 if result.get("completed") else 6
    return {"valid": 0, "login_required": 4, "risk": 5}.get(result.get("online"), 6)


def main() -> int:
    parser = argparse.ArgumentParser(description="visible XHS single-page probe")
    parser.add_argument("--mode", choices=("home", "note", "batch", "search"), default="home")
    parser.add_argument("--seed-html", default=str(DEFAULT_SEED))
    parser.add_argument("--max-tries", type=int, default=3)
    parser.add_argument("--max-notes", type=int, default=8)
    parser.add_argument("--max-loads", type=int, default=10)
    parser.add_argument("--group", choices=("A", "B"), default=None)
    parser.add_argument("--per-word", type=int, default=3)
    parser.add_argument("--wait", type=float, default=8.0)
    parser.add_argument("--interval", type=float, default=15.0)
    args = parser.parse_args()
    try:
        if args.mode == "note":
            result = asyncio.run(probe_note_async(pathlib.Path(args.seed_html),
                                                 max_tries=args.max_tries,
                                                 interval=args.interval))
        elif args.mode == "search":
            result = asyncio.run(probe_search_async(group=args.group,
                                                    per_word=args.per_word,
                                                    interval=args.interval))
        elif args.mode == "batch":
            result = asyncio.run(probe_batch_async(max_notes=args.max_notes,
                                                   max_loads=args.max_loads,
                                                   interval=args.interval))
        else:
            result = asyncio.run(probe_async(wait=args.wait, interval=args.interval))
    except Exception as exc:  # noqa: BLE001
        print(json.dumps({"online": "unknown", "error": type(exc).__name__}, ensure_ascii=False))
        return 6
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return exit_code(result)


if __name__ == "__main__":
    sys.exit(main())
