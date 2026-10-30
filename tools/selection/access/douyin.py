"""Douyin adapter: the minimum that really runs, with honest capability labels.

What this module can do **offline** (verified by `tests/test_access_douyin.py`):

- `doctor`      profile / browser availability, cookie **names** only, no network
- `search`      HTML parse of `/video/<id>` links (offline transport by default)
- `detail`      one video page -> one record (og/meta/title), else unsupported
- `export`      the shared whitelist exporter
- `login`       visible window for the user, always reported as `unknown` because
                no real signed-in page has ever been observed for this adapter

What it deliberately does **not** claim:

- `comments` / replies / pagination: there is no verified endpoint, so the entry
  exists and returns a non-zero `unsupported` — never an empty success and never
  a guessed cursor.
- Any signed-in state: selectors here are **assumed**; login reports `unknown`
  even when a logout-looking node appears.
- Real network reachability: the real path needs an explicitly authorized batch
  in the Douyin ledger; otherwise it is refused before any transport is built.

Budget: Douyin has its **own** fixed ledger (`runtime/douyin_platform.sqlite3`),
keyed by site, so a new `--state-dir`, a restart, or a different process cannot
reset the counter or drop a risk lock. The Weibo history gate is *not* reused.

Stdlib only; no new dependencies.
"""

from __future__ import annotations

import asyncio
import contextlib
import datetime as dt
import json
import pathlib
import re
import sqlite3
import sys
import time
import urllib.parse

from . import browser as browser_mod
from . import budget as budget_mod
from . import codes
from . import diagnostics as diag_mod
from . import records as rec
from . import transport as transport_mod
from .zhihu import (_charge, _finish, _merge_diagnostics, _risk_or_error,
                    detect_risk)

SITE_NAME = "douyin"
#: 仓库根目录：profile **不得**落在它下面（登录态绝不入仓库）
REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
#: 与微博/知乎同构：默认 profile 放在仓库外，持久保存且不进 git
DEFAULT_PROFILE = pathlib.Path.home() / ".dsh" / "tools" / "douyin-collect" / "profile"
ALLOWED_HOST = "douyin.com"

SEARCH_URL = "https://www.douyin.com/search/{keyword}"
#: what we persist and print: a fixed path, never the keyword
SEARCH_PAGE = "https://www.douyin.com/search"
DETAIL_URL = "https://www.douyin.com/video/{vid}"
#: logged-out visitors get the QR login modal right on the home page
LOGIN_URL = "https://www.douyin.com/"
#: the only success evidence this adapter accepts for a real login (names only)
SESSION_COOKIE_NAMES = ("sessionid", "sid_tt")
#: how often the login window re-reads the cookie **names**
POLL_SECONDS = 3.0

#: content paths a Douyin listing links to (**assumed**: no real page observed)
DOUYIN_LINK_RE = re.compile(r"/video/(\d{6,})/?$")

#: wall wording: real wall copy only, never a bare "验证码"
RISK_MARKERS = ("安全验证", "captcha", "访问异常", "操作频繁", "访问过于频繁",
                "请求过于频繁", "系统繁忙", "账号异常", "访问受限",
                "登录后查看", "请先登录")
EMPTY_MARKERS = ("没有找到", "暂无内容", "未找到相关", "暂无搜索结果", "没有更多")

SITE = transport_mod.SiteProfile(
    SITE_NAME,
    shape_rules=(("video", r"/\/video\/\d{6,}\/?$/.test(href)"),),
    recognized_keys=("video",),
    result_selectors='[data-e2e*="search-result"],[class*="search-result"]',
    list_selectors='[data-e2e*="feed"],[class*="feed"],[id*="root"]',
    wall_markers=RISK_MARKERS,
    empty_markers=EMPTY_MARKERS,
)

#: Signals only; the verdict lives in Python so it can be unit-tested.
#: Selectors are **assumed** and never treated as proof of a session.
SIGNED_IN_JS = r"""
(() => {
  const host = (location.hostname || '').toLowerCase();
  const path = location.pathname || '';
  const text = (document.body && document.body.innerText) || '';
  const has = (sel) => { try { return document.querySelector(sel) !== null; } catch (e) { return false; } };
  return JSON.stringify({
    host: host,
    path: path,
    text: text.slice(0, 2000),
    hasLogout: has('a[href*="/logout"]') || has('[data-e2e*="logout"]'),
    hasAvatar: has('img[src*="avatar"],[class*="avatar"]'),
    hasUpload: has('[data-e2e*="upload"]')
  });
})()
"""

STRONG_SIGNALS = ("hasLogout",)


def classify_signed_in(signals) -> str:
    """`unknown` unless a logout control exists on the Douyin business host.

    Even then this adapter reports the login as `unknown`: the selector has never
    been observed on a real signed-in page.
    """
    if isinstance(signals, str):
        try:
            signals = json.loads(signals)
        except (TypeError, json.JSONDecodeError):
            return "unknown"
    if not isinstance(signals, dict):
        return "unknown"
    host = str(signals.get("host") or "").lower()
    if not (host == "douyin.com" or host.endswith(".douyin.com")):
        return "unknown"
    if re.search(r"/(signin|login|passport)\b", str(signals.get("path") or "")):
        return "unknown"
    return "unknown" if not any(bool(signals.get(k)) for k in STRONG_SIGNALS) else "unknown"


def signed_in_verdict(signals) -> bool:
    """Never true: no verified signed-in page exists for this adapter."""
    classify_signed_in(signals)
    return False


# --------------------------------------------------------------------------
# Douyin-only ledger (fixed path, no history gate)
# --------------------------------------------------------------------------
LEDGER_PATH = (pathlib.Path(__file__).resolve().parent / "runtime"
               / "douyin_platform.sqlite3")
MIN_INTERVAL = 15.0
DEFAULT_RECORDS_TARGET = 5
MAX_RECORDS = DEFAULT_RECORDS_TARGET  # 兼容别名：默认目标值，不是上限
#: 弃用提示：新代码请直接用 `DEFAULT_RECORDS_TARGET`；本别名仅保留给旧调用方，
#: 不得用于 `if used > MAX_RECORDS` 这类上限判断（v11 起记录数是软目标）。
MAX_SECONDS = 300.0

LEDGER_SCHEMA = """
CREATE TABLE IF NOT EXISTS batches (
  batch_id TEXT PRIMARY KEY, site TEXT NOT NULL, authorized_calls INTEGER NOT NULL,
  records_cap INTEGER NOT NULL DEFAULT 5, window_seconds REAL NOT NULL,
  started_at REAL NOT NULL, source TEXT NOT NULL, note TEXT);
CREATE TABLE IF NOT EXISTS events (
  id INTEGER PRIMARY KEY AUTOINCREMENT, site TEXT NOT NULL, batch_id TEXT NOT NULL,
  kind TEXT NOT NULL, detail TEXT, at REAL NOT NULL, source TEXT);
CREATE TABLE IF NOT EXISTS reservations (
  id INTEGER PRIMARY KEY AUTOINCREMENT, site TEXT NOT NULL, batch_id TEXT NOT NULL,
  count INTEGER NOT NULL, at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS locks (
  site TEXT PRIMARY KEY, reason TEXT NOT NULL, source TEXT, at REAL NOT NULL);
"""

CALL_KINDS = ("active_nav", "search", "detail", "comments")
AUDIT_KINDS = ("offline_check", "search_result", "detail_result",
               "comments_result", "active_nav_result")


class DouyinBudgetError(Exception):
    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(f"{code}:{detail}" if detail else code)
        self.code = code
        self.detail = detail


class DouyinLedger:
    """Site-scoped authority for Douyin; a new state dir cannot reset it."""

    def __init__(self, path=None, *, clock=time.time) -> None:
        self.path = pathlib.Path(path or LEDGER_PATH)
        self.site = SITE_NAME
        self._clock = clock
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.path), timeout=30.0,
                                     isolation_level=None)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(LEDGER_SCHEMA)

    def close(self) -> None:
        self._conn.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        self.close()

    def authorize_batch(self, batch_id: str, *, authorized_calls: int,
                        window_seconds: float, source: str, note: str = "",
                        records_cap: int = DEFAULT_RECORDS_TARGET) -> dict:
        if not batch_id:
            raise DouyinBudgetError("batch_id_required")
        if not (1 <= int(authorized_calls) <= 20):
            raise DouyinBudgetError("invalid_authorization", str(authorized_calls))
        if int(records_cap) < 1:      # v11：记录数软目标，不设上限
            raise DouyinBudgetError("invalid_authorization", f"records_cap={records_cap}")
        if not (0 < float(window_seconds) <= MAX_SECONDS):
            raise DouyinBudgetError("invalid_authorization", f"window={window_seconds}")
        row = self._conn.execute("SELECT * FROM batches WHERE batch_id=?",
                                 (batch_id,)).fetchone()
        if row is not None:
            same = (row["authorized_calls"] == int(authorized_calls)
                    and float(row["window_seconds"]) == float(window_seconds)
                    and int(row["records_cap"]) == int(records_cap))
            if not same:
                raise DouyinBudgetError("batch_conflict", str(batch_id))
            return dict(row)
        self._conn.execute(
            "INSERT INTO batches(batch_id, site, authorized_calls, records_cap,"
            " window_seconds, started_at, source, note) VALUES (?,?,?,?,?,?,?,?)",
            (batch_id, self.site, int(authorized_calls), int(records_cap),
             float(window_seconds), self._clock(), source, note))
        return dict(self._conn.execute("SELECT * FROM batches WHERE batch_id=?",
                                       (batch_id,)).fetchone())

    def lock(self, reason: str, *, source: str = "unknown") -> None:
        self._conn.execute(
            "INSERT INTO locks(site, reason, source, at) VALUES (?,?,?,?) "
            "ON CONFLICT(site) DO UPDATE SET reason=excluded.reason, "
            "source=excluded.source, at=excluded.at",
            (self.site, str(reason), source, self._clock()))

    def locked(self):
        try:
            row = self._conn.execute("SELECT reason FROM locks WHERE site=?",
                                     (self.site,)).fetchone()
        except sqlite3.Error as exc:
            return True, f"ledger_unavailable:{type(exc).__name__}"
        return (True, row["reason"]) if row is not None else (False, None)

    def charge(self, batch_id: str, kind: str, *, detail: str = "",
               source: str = "runtime") -> dict:
        if kind not in CALL_KINDS:
            raise DouyinBudgetError("unknown_charge_kind", kind)
        self._conn.execute("BEGIN IMMEDIATE")
        try:
            row = self._conn.execute("SELECT reason FROM locks WHERE site=?",
                                     (self.site,)).fetchone()
            if row is not None:
                raise DouyinBudgetError("platform_locked", str(row["reason"]))
            batch = self._conn.execute("SELECT * FROM batches WHERE batch_id=?",
                                       (batch_id,)).fetchone()
            if batch is None:
                raise DouyinBudgetError("no_authorized_batch", str(batch_id))
            now = self._clock()
            if now >= float(batch["started_at"]) + float(batch["window_seconds"]):
                raise DouyinBudgetError("batch_window_closed", str(batch_id))
            last = self._conn.execute(
                "SELECT MAX(at) FROM events WHERE batch_id=? AND site=? AND kind IN"
                " (%s)" % ",".join("?" * len(CALL_KINDS)),
                (batch_id, self.site, *CALL_KINDS)).fetchone()[0]
            if last is not None and now - float(last) < MIN_INTERVAL:
                raise DouyinBudgetError("interval_not_elapsed", f"{now - float(last):.1f}s")
            used = self._conn.execute(
                "SELECT COUNT(*) FROM events WHERE batch_id=? AND site=? AND kind IN"
                " (%s)" % ",".join("?" * len(CALL_KINDS)),
                (batch_id, self.site, *CALL_KINDS)).fetchone()[0]
            if used >= int(batch["authorized_calls"]):
                raise DouyinBudgetError("calls_exhausted",
                                        f"{used}/{batch['authorized_calls']}")
            self._conn.execute(
                "INSERT INTO events(site, batch_id, kind, detail, at, source)"
                " VALUES (?,?,?,?,?,?)",
                (self.site, batch_id, kind, detail, now, source))
            self._conn.execute("COMMIT")
        except Exception:
            with contextlib.suppress(sqlite3.Error):
                self._conn.execute("ROLLBACK")
            raise
        return self.summary(batch_id)

    def reserve_records(self, batch_id: str, count: int = 1) -> dict:
        if count <= 0:
            raise DouyinBudgetError("invalid_reservation")
        self._conn.execute("BEGIN IMMEDIATE")
        try:
            batch = self._conn.execute("SELECT * FROM batches WHERE batch_id=?",
                                       (batch_id,)).fetchone()
            if batch is None:
                raise DouyinBudgetError("no_authorized_batch", str(batch_id))
            used = self._conn.execute(
                "SELECT COALESCE(SUM(count),0) FROM reservations WHERE batch_id=?"
                " AND site=?", (batch_id, self.site)).fetchone()[0]
            cap = int(batch["records_cap"])
            self._conn.execute(
                "INSERT INTO reservations(site, batch_id, count, at) VALUES (?,?,?,?)",
                (self.site, batch_id, int(count), self._clock()))
            self._conn.execute("COMMIT")
        except Exception:
            with contextlib.suppress(sqlite3.Error):
                self._conn.execute("ROLLBACK")
            raise
        total = int(used) + int(count)
        return {"records_target": cap, "records_used": total,
                "over_cap": total > cap, "over_by": max(0, total - cap),
                "records_cap": cap}

    def record_result(self, batch_id: str, kind: str, outcome: str) -> None:
        self._conn.execute(
            "INSERT INTO events(site, batch_id, kind, detail, at, source)"
            " VALUES (?,?,?,?,?,?)",
            (self.site, batch_id, f"{kind}_result", outcome, self._clock(),
             "douyin.result"))

    def summary(self, batch_id: str | None = None) -> dict:
        locked, reason = self.locked()
        out = {"site": self.site, "locked": locked, "lock_reason": reason}
        if batch_id:
            batch = self._conn.execute("SELECT * FROM batches WHERE batch_id=?",
                                       (batch_id,)).fetchone()
            if batch is None:
                return {**out, "batch_id": batch_id, "authorized": False}
            used = self._conn.execute(
                "SELECT COUNT(*) FROM events WHERE batch_id=? AND site=? AND kind IN"
                " (%s)" % ",".join("?" * len(CALL_KINDS)),
                (batch_id, self.site, *CALL_KINDS)).fetchone()[0]
            reserved = self._conn.execute(
                "SELECT COALESCE(SUM(count),0) FROM reservations WHERE batch_id=?"
                " AND site=?", (batch_id, self.site)).fetchone()[0]
            out.update({"batch_id": batch_id, "authorized": True,
                        "authorized_calls": int(batch["authorized_calls"]),
                        "used": used,
                        "remaining": max(0, int(batch["authorized_calls"]) - used),
                        "records_cap": int(batch["records_cap"]),
                        "records_target": int(batch["records_cap"]),
                        "records_reserved": int(reserved),
                        "records_used": int(reserved),
                        "over_cap": int(reserved) > int(batch["records_cap"]),
                        "over_by": max(0, int(reserved) - int(batch["records_cap"])),
                        "window_open": self._clock() < float(batch["started_at"])
                        + float(batch["window_seconds"])})
        return out

    def events(self, limit: int = 20) -> list[dict]:
        rows = self._conn.execute(
            "SELECT kind, batch_id, detail, at, source FROM events WHERE site=?"
            " ORDER BY id DESC LIMIT ?", (self.site, int(limit))).fetchall()
        return [dict(r) for r in rows]


def open_ledger(path=None) -> DouyinLedger:
    return DouyinLedger(path)


# --------------------------------------------------------------------------
# URLs / parsing
# --------------------------------------------------------------------------
def allowed_url(url) -> bool:
    parts = urllib.parse.urlsplit(str(url or "").strip())
    host = (parts.hostname or "").lower()
    return (parts.scheme in ("http", "https")
            and (host == ALLOWED_HOST or host.endswith("." + ALLOWED_HOST)))


def search_url(keyword: str) -> str:
    return SEARCH_URL.format(keyword=urllib.parse.quote(str(keyword or "").strip()))


def video_id(url: str) -> str | None:
    match = DOUYIN_LINK_RE.search(urllib.parse.urlsplit(str(url or "")).path)
    return match.group(1) if match else None


def redact_detail(url: str) -> str:
    parts = urllib.parse.urlsplit(str(url or ""))
    if not parts.scheme or not parts.netloc:
        return ""
    return f"{parts.scheme}://{parts.netloc}{parts.path}"


def parse_search_html(html: str, *, collected_at: str, limit: int = 5) -> dict:
    """Search page -> status records, deduplicated by video id.

    `title` comes from the anchor text only; a generic label such as "全文"
    is **not** treated as the video body.
    """
    text = str(html or "")
    if not text.strip():
        return {"records": [], "stop": "empty", "structure": "html:empty",
                "anchors_total": 0, "anchors_recognized": 0, "anchors_rejected": 0}
    seen, out = set(), []
    total = recognized = 0
    for match in re.finditer(r'<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', text,
                             flags=re.S | re.I):
        href, label = match.group(1), rec.strip_tags(match.group(2))
        total += 1
        absolute = urllib.parse.urljoin("https://www.douyin.com/", href)
        if not allowed_url(absolute):      # off-host links never become records
            continue
        vid = video_id(absolute)
        if not vid or vid in seen:
            continue
        recognized += 1
        seen.add(vid)
        title = rec.collapse(label)
        record = rec.make_record(
            values={"native_id": vid, "type": "video",
                    "url": f"https://www.douyin.com/video/{vid}",
                    "title": title if title and title != "全文" else None},
            evidence={"native_id": "url:/video/<id>", "type": "url:/video/<id>",
                      "url": "html:a[href]", "title": "html:a[text]"},
            collected_at=collected_at, source="douyin:search:video")
        out.append(record)
        if len(out) >= max(1, int(limit)):
            break
    stop = "records" if out else ("empty" if total else "unsupported")
    return {"records": out, "stop": stop, "structure": "html:links",
            "anchors_total": total, "anchors_recognized": recognized,
            "anchors_rejected": max(0, total - recognized)}


def parse_detail_html(html: str, url: str, *, collected_at: str) -> dict:
    """Video page -> one record from meta/title; unknown otherwise."""
    text = str(html or "")
    vid = video_id(url)
    if not vid:
        return {"record": None, "stop": "unsupported_content_url"}
    if not text.strip():
        return {"record": None, "stop": "empty", "structure": "html:empty"}
    meta = rec.meta_tags(text)["meta"]
    title_tag = re.search(r"<title[^>]*>(.*?)</title>", text, flags=re.S | re.I)
    head = rec.collapse(meta.get("og:title") or (title_tag.group(1) if title_tag else ""))
    desc = rec.collapse(meta.get("og:description") or "")
    body = rec.strip_tags(text)[:20000]
    # meta-only pages carry their text in attributes, so scan head + desc + body
    lowered = rec.collapse(" ".join([head, desc, body])).lower()
    hit = next((m for m in RISK_MARKERS if m.lower() in lowered), None)
    reason = f"text:{hit}" if hit else None
    if reason:
        if hit.lower() in rec.collapse(head).lower():
            return {"record": None, "stop": f"risk:{reason}", "structure": "html:wall"}
        if hit.lower() not in rec.collapse(desc).lower():
            return {"record": None, "stop": f"risk:{reason}", "structure": "html:wall"}
        # the wording only appears inside og:description: a post *about* captchas
        # looks exactly like this, so we neither lock nor claim success.
        return {"record": None, "stop": "risk_ambiguous",
                "structure": "meta:description-only"}
    title = rec.collapse(meta.get("og:title") or "")
    desc = rec.collapse(meta.get("og:description") or "")
    if not title and not desc:
        return {"record": None, "stop": "unsupported", "structure": "html:unknown"}
    record = rec.make_record(
        values={"native_id": vid, "type": "video",
                "url": f"https://www.douyin.com/video/{vid}",
                "title": title or None, "text": desc or None},
        evidence={"native_id": "url:/video/<id>", "type": "url:/video/<id>",
                  "url": "input:video_id", "title": "meta:og:title",
                  "text": "meta:og:description"},
        collected_at=collected_at, source="douyin:detail:video")
    return {"record": record, "stop": None, "structure": "meta:video"}


# --------------------------------------------------------------------------
# commands
# --------------------------------------------------------------------------
def profile_in_repo(profile) -> bool:
    """True 表示 profile 路径解析后落在仓库内——登录态会随仓库走，必须拒绝。"""
    try:
        resolved = pathlib.Path(profile).expanduser().resolve()
    except (OSError, RuntimeError):
        return False
    try:
        resolved.relative_to(REPO_ROOT)
    except ValueError:
        return False
    return True


def doctor(profile=DEFAULT_PROFILE) -> dict:
    """Offline only: profile presence, cookie **names**, browser availability."""
    profile = pathlib.Path(profile)
    cookies = profile / "Default" / "Network" / "Cookies"
    in_repo = profile_in_repo(profile)
    out = {"site": SITE_NAME, "profile": str(profile),
           "profile_exists": profile.is_dir(),
           "cookie_db_exists": cookies.is_file(), "cookie_names": {},
           "profile_in_repo": in_repo, "repo_root": str(REPO_ROOT),
           "online": "unverified", "network": "none",
           "note": "cookie names only; no real Douyin page has been observed"}
    if in_repo:
        out["warning"] = ("profile_inside_repo：登录态会写进仓库，禁止使用；"
                          "请改用 DEFAULT_PROFILE 或仓库外的 --profile")
    if cookies.is_file():
        try:
            conn = sqlite3.connect(f"file:{cookies.as_posix()}?mode=ro", uri=True)
            names = {row[0] for row in conn.execute(
                "SELECT DISTINCT name FROM cookies WHERE host_key LIKE '%douyin%'")}
            conn.close()
            out["cookie_names"] = {name: (name in names)
                                   for name in ("sessionid", "sid_tt", "uid_tt")}
        except sqlite3.Error as exc:
            out["error"] = f"cookie_db_read_failed:{type(exc).__name__}"
    try:
        info = browser_mod.available()
        out["browser"] = {"usable": bool(info.get("usable"))}
    except Exception as exc:  # noqa: BLE001 - doctor never crashes on a missing browser
        out["browser"] = {"usable": False, "error": type(exc).__name__}
    return out


def _session_cookie_seen(profile) -> bool:
    """True when a Douyin **session cookie name** exists in the profile DB.

    Names only: the value is never selected, so it can never be printed or kept.
    A locked DB (Chrome still writing) is "not yet", not an error.
    """
    db = pathlib.Path(profile) / "Default" / "Network" / "Cookies"
    if not db.is_file():
        return False
    try:
        conn = sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True, timeout=1.0)
    except sqlite3.Error:
        return False
    try:
        rows = conn.execute(
            "SELECT DISTINCT name FROM cookies WHERE host_key LIKE '%douyin%'").fetchall()
    except sqlite3.Error:
        return False
    finally:
        conn.close()
    return bool({row[0] for row in rows if row[0]} & set(SESSION_COOKIE_NAMES))


def _login_with_real_browser(profile, *, timeout: float, headless: bool, info: dict,
                             clock) -> dict:
    """Visible nodriver window; success == a Douyin session cookie name appears."""
    import nodriver as uc

    profile = pathlib.Path(profile).expanduser().resolve()
    pathlib.Path(profile).mkdir(parents=True, exist_ok=True)

    async def _run() -> dict:
        browser = await uc.start(headless=headless, user_data_dir=str(profile),
                                 browser_executable_path=info["chrome"])
        started = clock()
        polls = 0
        try:
            await browser.get(LOGIN_URL)
            # Chrome keeps cookies in memory and flushes the DB on shutdown, so an
            # in-window SQLite read can stay empty even after a successful scan.
            # The verdict is therefore taken AFTER the window closes.
            while clock() - started < timeout:
                if _session_cookie_seen(profile):
                    break
                polls += 1
                await asyncio.sleep(POLL_SECONDS)
        finally:
            try:
                browser.stop()
            except Exception:  # noqa: BLE001 - a dead window must not hide the verdict
                pass
        seen = _session_cookie_seen(profile)   # post-close flush is the real evidence
        return {"status": "ok" if seen else "timeout",
                "exit": codes.EXIT_OK if seen else codes.EXIT_LOGIN_TIMEOUT,
                "signed_in": seen, "session_cookie": seen,
                "session_cookie_names": list(SESSION_COOKIE_NAMES),
                "polls": polls, "elapsed_s": round(clock() - started, 3),
                "final_url": LOGIN_URL, "charged": False,
                "verdict_source": "cookie_names_after_close",
                "note": "cookie names only; no value was read or printed"}

    return asyncio.run(_run())


def login(profile=DEFAULT_PROFILE, *, budget, clock=None, timeout: float = 300.0,
          headless: bool = False, browser=None, ledger=None,
          batch_id: str | None = None, open_window: bool = False) -> dict:
    """Open a visible window for the user to sign in. Never fills credentials.

    Default stays the offline answer (`unsupported`, nothing charged) so existing
    callers/tests keep their behaviour; `open_window=True` is what the CLI uses.
    """
    if profile_in_repo(profile):
        return {"status": "rejected", "exit": codes.EXIT_UNSUPPORTED,
                "stop": "profile_inside_repo", "signed_in": False, "polls": 0,
                "profile": str(profile),
                "note": "profile 在仓库内：拒绝登录，未启动窗口、未扣费"}
    if browser is None and not open_window:
        return {"status": "unsupported", "exit": codes.EXIT_UNSUPPORTED,
                "stop": "login_not_supported:no_visible_window_implemented",
                "signed_in": False, "polls": 0,
                "note": "no visible login window requested; nothing was charged"}

    clock = clock or time.time
    if browser is None:
        info = browser_mod.available()
        if not info["usable"]:
            return {"status": "unavailable", "exit": codes.EXIT_TRANSPORT,
                    "error": "browser_unavailable", "detail": info, "polls": 0,
                    "signed_in": False, "profile": str(profile), "charged": False}
        return _login_with_real_browser(profile, timeout=timeout, headless=headless,
                                        info=info, clock=clock)
    # Injected browser (tests): reuse the shared poll loop; the Douyin key
    # selector has never been observed on a real page, so its verdict stays
    # `unknown` and the exit code is non-zero — never a fake success.
    return asyncio.run(browser_mod.wait_for_login(
        browser, profile=profile, budget=budget, clock=clock, timeout=timeout,
        signed_in_js=SIGNED_IN_JS, wall_markers=RISK_MARKERS,
        signed_in_verdict=lambda raw: classify_signed_in(raw) == "ok"))


def _scrub(value, keyword: str):
    """Remove the keyword (raw and percent-encoded) from anything we persist/print."""
    if not keyword:
        return value
    forms = {keyword, urllib.parse.quote(keyword), urllib.parse.quote(keyword, safe="")}
    if isinstance(value, str):
        for form in sorted(forms, key=len, reverse=True):
            if form:
                value = value.replace(form, "[redacted]")
        return value
    if isinstance(value, list):
        return [_scrub(v, keyword) for v in value]
    if isinstance(value, dict):
        return {k: _scrub(v, keyword) for k, v in value.items()}
    return value


def _settle(ledger, batch_id, kind: str, exit_code: int, payload: dict) -> dict:
    """Record the outcome; a failed write is a failure, never a silent success."""
    if ledger is None:
        return payload
    outcome = ("success" if exit_code == codes.EXIT_OK
               else "unknown" if exit_code in (codes.EXIT_PARTIAL, codes.EXIT_TRANSPORT)
               else "failed")
    try:
        ledger.record_result(batch_id or "", kind, outcome)
    except Exception as exc:  # noqa: BLE001 - the call already happened
        return {**payload, "ok": False, "exit": codes.EXIT_BUDGET, "records": [],
                "stop": f"platform:result_write_failed:{type(exc).__name__}",
                "result_persisted": False}
    return payload


def run_search(keyword: str, *, batch, transport, collected_at: str,
               limit: int = 5, ledger=None, batch_id: str | None = None) -> dict:
    url = search_url(keyword)
    safe_url = SEARCH_PAGE                 # fixed path: no keyword, no encoding
    err = _charge(batch, "search", safe_url)
    if err:
        return _finish("search", exit_code=codes.EXIT_BUDGET, batch=batch,
                       records_out=[], keyword=None, stop=f"budget:{err.code}",
                       url=safe_url)
    if ledger is not None:
        try:
            ledger.charge(batch_id or "", "search", detail="search",
                          source="douyin.search")
        except DouyinBudgetError as exc:
            return _finish("search", exit_code=codes.EXIT_BUDGET, batch=batch,
                           records_out=[], keyword=None,
                           stop=f"platform:{exc.code}", url=safe_url)
    try:
        result = transport.fetch(url)
    except Exception as exc:  # noqa: BLE001 - a charged call must still settle
        payload = _finish("search", exit_code=codes.EXIT_TRANSPORT, batch=batch,
                          records_out=[], keyword=None,
                          stop=f"adapter_exception:{type(exc).__name__}", url=safe_url)
        return _settle(ledger, batch_id, "search", codes.EXIT_TRANSPORT,
                       _scrub(payload, keyword))
    reason, locks = _risk_or_error(result)
    if locks:
        clean_reason = _scrub(str(reason), keyword)
        try:
            batch.lock(clean_reason, source="search")
            if ledger is not None:
                ledger.lock(clean_reason, source="douyin.search")
        except Exception as exc:  # noqa: BLE001 - an unpersisted lock must stop
            return _finish("search", exit_code=codes.EXIT_BUDGET, batch=batch,
                           records_out=[], keyword=None,
                           stop=f"platform:lock_write_failed:{type(exc).__name__}",
                           url=safe_url)
        payload = _finish("search", exit_code=codes.EXIT_RISK, batch=batch,
                          records_out=[], keyword=None, stop=clean_reason, url=safe_url,
                          diagnostics=_merge_diagnostics(result, {}))
        return _settle(ledger, batch_id, "search", codes.EXIT_RISK,
                       _scrub(payload, keyword))
    if reason:
        clean_reason = _scrub(str(reason), keyword)
        batch.note("transport_error", clean_reason)      # never persist the keyword
        payload = _finish("search", exit_code=codes.EXIT_TRANSPORT, batch=batch,
                          records_out=[], keyword=None, stop=clean_reason, url=safe_url,
                          diagnostics=_merge_diagnostics(result, {}))
        return _settle(ledger, batch_id, "search", codes.EXIT_TRANSPORT,
                       _scrub(payload, keyword))
    parsed = parse_search_html(result.get("text") or "", collected_at=collected_at,
                               limit=limit)
    found = parsed["records"]
    exit_code = codes.EXIT_OK
    if parsed["stop"] == "unsupported" or not found:
        exit_code = codes.EXIT_EMPTY if parsed["stop"] == "empty" else codes.EXIT_UNSUPPORTED
    if found:
        if ledger is not None:
            try:
                ledger.reserve_records(batch_id or "", len(found))
            except DouyinBudgetError as exc:
                return _finish("search", exit_code=codes.EXIT_BUDGET, batch=batch,
                               records_out=[], keyword=None,
                               stop=f"platform:{exc.code}", url=safe_url)
        err = budget_mod_error(lambda: batch.reserve_records(len(found)))
        if err:
            return _finish("search", exit_code=codes.EXIT_BUDGET, batch=batch,
                           records_out=[], keyword=None, stop=f"budget:{err.code}",
                           url=safe_url)
    payload = _finish("search", exit_code=exit_code, batch=batch, records_out=found,
                   keyword=None, stop=parsed["stop"], url=safe_url,
                   anchors_total=parsed["anchors_total"],
                   anchors_recognized=parsed["anchors_recognized"],
                   anchors_rejected=parsed["anchors_rejected"],
                   diagnostics=_merge_diagnostics(result, parsed))
    return _settle(ledger, batch_id, "search", exit_code, _scrub(payload, keyword))


def run_detail(url: str, *, batch, transport, collected_at: str,
               ledger=None, batch_id: str | None = None) -> dict:
    target = redact_detail(url)
    if not allowed_url(url) or not video_id(url):
        return _finish("detail", exit_code=codes.EXIT_INPUT, batch=batch,
                       records_out=[], stop="unsupported_content_url", url=target)
    err = _charge(batch, "detail", target)
    if err:
        return _finish("detail", exit_code=codes.EXIT_BUDGET, batch=batch,
                       records_out=[], stop=f"budget:{err.code}", url=target)
    if ledger is not None:
        try:
            ledger.charge(batch_id or "", "detail", detail=target,
                          source="douyin.detail")
        except DouyinBudgetError as exc:
            return _finish("detail", exit_code=codes.EXIT_BUDGET, batch=batch,
                           records_out=[], stop=f"platform:{exc.code}", url=target)
    try:
        result = transport.fetch(url)
    except Exception as exc:  # noqa: BLE001 - a charged call must still settle
        payload = _finish("detail", exit_code=codes.EXIT_TRANSPORT, batch=batch,
                          records_out=[],
                          stop=f"adapter_exception:{type(exc).__name__}", url=target)
        return _settle(ledger, batch_id, "detail", codes.EXIT_TRANSPORT, payload)
    reason, locks = _risk_or_error(result)
    if locks:
        try:
            batch.lock(reason, source="detail")
            if ledger is not None:
                ledger.lock(reason, source="douyin.detail")
        except Exception as exc:  # noqa: BLE001
            return _finish("detail", exit_code=codes.EXIT_BUDGET, batch=batch,
                           records_out=[],
                           stop=f"platform:lock_write_failed:{type(exc).__name__}",
                           url=target)
        payload = _finish("detail", exit_code=codes.EXIT_RISK, batch=batch,
                          records_out=[], stop=reason, url=target)
        return _settle(ledger, batch_id, "detail", codes.EXIT_RISK, payload)
    if reason:
        payload = _finish("detail", exit_code=codes.EXIT_TRANSPORT, batch=batch,
                          records_out=[], stop=reason, url=target)
        return _settle(ledger, batch_id, "detail", codes.EXIT_TRANSPORT, payload)
    parsed = parse_detail_html(result.get("text") or "", url,
                               collected_at=collected_at)
    stop = parsed.get("stop")
    if stop:
        if str(stop).startswith("risk:"):
            try:
                batch.lock(stop, source="detail")
                if ledger is not None:
                    ledger.lock(stop, source="douyin.detail")
            except Exception as exc:  # noqa: BLE001 - parse risk must persist
                return _finish("detail", exit_code=codes.EXIT_BUDGET, batch=batch,
                               records_out=[],
                               stop=f"platform:lock_write_failed:{type(exc).__name__}",
                               url=target)
            payload = _finish("detail", exit_code=codes.EXIT_RISK, batch=batch,
                              records_out=[], stop=stop, url=target)
            return _settle(ledger, batch_id, "detail", codes.EXIT_RISK, payload)
        code = codes.EXIT_EMPTY if stop == "empty" else codes.EXIT_UNSUPPORTED
        payload = _finish("detail", exit_code=code, batch=batch, records_out=[],
                          stop=stop, url=target)
        return _settle(ledger, batch_id, "detail", code, payload)
    err = budget_mod_error(lambda: batch.reserve_records(1))
    if err:
        return _finish("detail", exit_code=codes.EXIT_BUDGET, batch=batch,
                       records_out=[], stop=f"budget:{err.code}", url=target)
    if ledger is not None:
        try:
            ledger.reserve_records(batch_id or "", 1)
        except DouyinBudgetError as exc:
            return _finish("detail", exit_code=codes.EXIT_BUDGET, batch=batch,
                           records_out=[], stop=f"platform:{exc.code}", url=target)
    payload = _finish("detail", exit_code=codes.EXIT_OK, batch=batch,
                      records_out=[parsed["record"]], stop=None, url=target,
                      parsed_structure=parsed["structure"])
    return _settle(ledger, batch_id, "detail", codes.EXIT_OK, payload)


def run_comments(url: str, *, batch, transport=None, collected_at: str = "",
                 limit: int = 5, ledger=None, batch_id: str | None = None) -> dict:
    """No verified endpoint: the entry exists and refuses, never guesses."""
    target = redact_detail(url)
    return _finish("comments", exit_code=codes.EXIT_UNSUPPORTED, batch=batch,
                   records_out=[], stop="comments_not_supported:no_verified_endpoint",
                   url=target)


def export(input_path, output_path=None, *, fmt: str = "jsonl",
           collected_at: str | None = None) -> dict:
    from .zhihu import export as zhihu_export
    return zhihu_export(input_path, output_path, fmt=fmt, collected_at=collected_at)


def budget_mod_error(fn):
    try:
        fn()
        return None
    except budget_mod.BudgetError as exc:
        return exc


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------
def build_parser():
    import argparse

    parser = argparse.ArgumentParser(prog="douyin")
    parser.add_argument("--state-dir", required=True)
    parser.add_argument("--profile", default=DEFAULT_PROFILE)
    parser.add_argument("--batch-id", default=None)
    parser.add_argument("--mode", default="offline",
                        choices=("offline", "public-http", "authenticated-browser"))
    parser.add_argument("--diagnostics-dir", default=None)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("doctor")
    login_p = sub.add_parser("login")
    login_p.add_argument("--timeout", type=float, default=300.0)
    login_p.add_argument("--headless", action="store_true")
    login_p.add_argument("--window", action="store_true",
                         help="open the visible login window (opt-in; default is the offline answer)")
    search_p = sub.add_parser("search")
    search_p.add_argument("keyword")
    search_p.add_argument("--limit", type=int, default=5)
    search_p.add_argument("--visible", action="store_true")
    search_p.add_argument("--timeout", type=float, default=60.0)
    detail_p = sub.add_parser("detail")
    detail_p.add_argument("url")
    detail_p.add_argument("--visible", action="store_true")
    detail_p.add_argument("--timeout", type=float, default=60.0)
    comments_p = sub.add_parser("comments")
    comments_p.add_argument("url")
    comments_p.add_argument("--limit", type=int, default=5)
    export_p = sub.add_parser("export")
    export_p.add_argument("input")
    export_p.add_argument("--output", default=None)
    export_p.add_argument("--format", default="jsonl")
    sub.add_parser("budget")
    return parser


def _emit(payload) -> None:
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))


def _make_transport(args):
    if getattr(args, "mode", "offline") == "authenticated-browser":
        return transport_mod.AuthenticatedBrowserTransport(
            args.profile, headless=not getattr(args, "visible", False),
            timeout=getattr(args, "timeout", None) or 60.0,
            allowed_host_suffix=ALLOWED_HOST, site=SITE)
    if getattr(args, "mode", "offline") == "public-http":
        return transport_mod.PublicHttpTransport()
    return transport_mod.RefusedTransport()


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    state_dir = pathlib.Path(args.state_dir)

    if args.command == "doctor":
        _emit({"command": "doctor", "ok": True, "exit": codes.EXIT_OK, **doctor(args.profile)})
        return codes.EXIT_OK
    if args.command == "export":
        payload = export(args.input, args.output, fmt=args.format)
        _emit({"command": "export", **payload})
        return int(payload.get("exit", codes.EXIT_EXPORT))

    try:
        batch = budget_mod.open_budget(state_dir, batch_id=args.batch_id)
    except budget_mod.BudgetError as exc:
        _emit({"command": args.command, "ok": False, "exit": codes.EXIT_BUDGET,
               "stop": f"budget:{exc.code}", "detail": exc.detail})
        return codes.EXIT_BUDGET

    if args.command == "login":
        payload = login(args.profile, budget=batch, timeout=args.timeout,
                        headless=args.headless, open_window=args.window)
        _emit({"command": "login", **payload})
        batch.close()
        return int(payload.get("exit", codes.EXIT_UNSUPPORTED))

    ledger = None
    try:
        if args.command in ("search", "detail", "comments"):
            ledger = open_ledger()
            locked, reason = ledger.locked()
            if locked:
                _emit({"command": args.command, "ok": False,
                       "exit": codes.EXIT_BUDGET,
                       "stop": f"platform:locked:{reason}"})
                return codes.EXIT_BUDGET
            if getattr(args, "mode", "offline") != "offline" or args.command == "login":
                if not args.batch_id:
                    _emit({"command": args.command, "ok": False,
                           "exit": codes.EXIT_BUDGET,
                           "stop": "platform:batch_id_required"})
                    return codes.EXIT_BUDGET
                if not ledger.summary(args.batch_id).get("authorized"):
                    _emit({"command": args.command, "ok": False,
                           "exit": codes.EXIT_BUDGET,
                           "stop": "platform:no_authorized_batch"})
                    return codes.EXIT_BUDGET

        if args.command == "comments":
            payload = run_comments(args.url, batch=batch, collected_at="",
                                   limit=args.limit, ledger=ledger,
                                   batch_id=args.batch_id)
            _emit({"command": "comments", **payload})
            return int(payload.get("exit", codes.EXIT_UNSUPPORTED))

        transport = _make_transport(args)
        collected_at = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        try:
            if args.command == "search":
                payload = run_search(args.keyword, batch=batch, transport=transport,
                                     collected_at=collected_at, limit=args.limit,
                                     ledger=ledger, batch_id=args.batch_id)
            elif args.command == "detail":
                payload = run_detail(args.url, batch=batch, transport=transport,
                                     collected_at=collected_at, ledger=ledger,
                                     batch_id=args.batch_id)
            else:
                _emit({"command": args.command, "ok": False,
                       "exit": codes.EXIT_INPUT, "stop": "unknown_command"})
                return codes.EXIT_INPUT
        finally:
            if hasattr(transport, "close"):
                transport.close()
        _emit({"command": args.command, **payload})
        return int(payload.get("exit", codes.EXIT_TRANSPORT))
    finally:
        if ledger is not None:
            ledger.close()
        batch.close()


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
