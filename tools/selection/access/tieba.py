"""百度贴吧离线入口（第六个平台之一）：doctor / login / search / detail / comments / export。

设计原则（照搬抖音/微博的打法）：
- **权威账本按站点隔离**：复用 `platform_budget.PlatformLedger(site="tieba")`，
  换 state dir 不能重置额度；预扣在真实动作之前。
- **默认不触网**：`doctor` 只读本地 profile 与 cookie **名称**；`login` 只由显式命令启动，
  且在没有真实登录样本前一律 `unknown`；`comments` 端点未知 → **预扣前显式 unsupported**。
- **记录走白名单**：`records.make_record` + `not_applicable`（帖子没有 root_comment_id）。
- **风险锁优先**：命中 `RISK_MARKERS` 就持久锁，后续调用直接拒。
"""

from __future__ import annotations

import pathlib
import re
import sqlite3

from . import codes
from . import records as rec
from . import platform_budget as pb

SITE_NAME = "tieba"
#: 仓库根目录：profile **不得**落在它下面（登录态绝不入仓库）
REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
#: 与微博/知乎同构：默认 profile 放在仓库外
DEFAULT_PROFILE = pathlib.Path.home() / ".dsh" / "tools" / "tieba-collect" / "profile"
ALLOWED_HOST = "tieba.baidu.com"

SEARCH_URL = "https://tieba.baidu.com/f?kw={keyword}"
THREAD_URL = "https://tieba.baidu.com/p/{tid}"

THREAD_RE = re.compile(r"/p/(\d{5,})")
RISK_MARKERS = ("安全验证", "验证码", "访问异常", "操作频繁", "访问过于频繁",
                "请完成验证", "百度安全验证")
EMPTY_MARKERS = ("没有找到", "暂无内容", "未找到相关", "该吧尚未", "没有更多")

CALL_KINDS = ("active_nav", "search", "detail", "comments")
MIN_INTERVAL = 15.0
DEFAULT_RECORDS_TARGET = 5
MAX_RECORDS = DEFAULT_RECORDS_TARGET  # 兼容别名：默认目标值，不是上限
#: 弃用提示：新代码请直接用 `DEFAULT_RECORDS_TARGET`；本别名仅保留给旧调用方，
#: 不得用于 `if used > MAX_RECORDS` 这类上限判断（v11 起记录数是软目标）。
MAX_SECONDS = 300.0

LEDGER_PATH = (pathlib.Path(__file__).resolve().parent / "runtime"
               / "platform_tieba.sqlite3")

COOKIE_NAMES = ("BDUSS", "STOKEN", "BAIDUID", "PTOKEN", "SAID")


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


class TiebaBudgetError(Exception):
    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(f"{code}:{detail}" if detail else code)
        self.code = code
        self.detail = detail


class TiebaLedger:
    """贴吧站点账本：预扣先行、跨实例累计、风险锁持久（换 state dir 不能重置）。"""

    site = SITE_NAME

    def __init__(self, path=None, *, clock=None) -> None:
        import sqlite3
        import time

        self.path = pathlib.Path(path or LEDGER_PATH)
        self._clock = clock or time.time
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.path), timeout=30.0, isolation_level=None)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(LEDGER_SCHEMA)

    # -- lifecycle
    def close(self) -> None:
        self._conn.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        self.close()

    # -- authorize
    def authorize_batch(self, batch_id: str, *, authorized_calls: int,
                        window_seconds: float = MAX_SECONDS, source: str = "unknown",
                        note: str = "", records_cap: int = DEFAULT_RECORDS_TARGET) -> dict:
        if not batch_id:
            raise TiebaBudgetError("batch_id_required")
        if not (1 <= int(authorized_calls) <= 20):
            raise TiebaBudgetError("invalid_authorization", str(authorized_calls))
        if int(records_cap) < 1:      # v11：记录数软目标，不设上限
            raise TiebaBudgetError("invalid_authorization", f"records_cap={records_cap}")
        if not (0 < float(window_seconds) <= MAX_SECONDS):
            raise TiebaBudgetError("invalid_authorization", f"window={window_seconds}")
        row = self._conn.execute("SELECT * FROM batches WHERE batch_id=?",
                                 (batch_id,)).fetchone()
        if row is not None:
            same = (row["authorized_calls"] == int(authorized_calls)
                    and float(row["window_seconds"]) == float(window_seconds)
                    and int(row["records_cap"]) == int(records_cap))
            if not same:
                raise TiebaBudgetError("batch_conflict", str(batch_id))
            return dict(row)
        self._conn.execute(
            "INSERT INTO batches(batch_id, site, authorized_calls, records_cap,"
            " window_seconds, started_at, source, note) VALUES (?,?,?,?,?,?,?,?)",
            (batch_id, self.site, int(authorized_calls), int(records_cap),
             float(window_seconds), self._clock(), source, note))
        return dict(self._conn.execute("SELECT * FROM batches WHERE batch_id=?",
                                       (batch_id,)).fetchone())

    # -- lock
    def lock(self, reason: str, *, source: str = "unknown") -> None:
        self._conn.execute("INSERT OR REPLACE INTO locks(site, reason, source, at)"
                           " VALUES (?,?,?,?)", (self.site, str(reason), source,
                                                 self._clock()))

    def locked(self):
        row = self._conn.execute("SELECT reason FROM locks WHERE site=?",
                                 (self.site,)).fetchone()
        return (True, row["reason"]) if row else (False, None)

    # -- charge / reserve
    def _used(self, batch_id: str) -> int:
        calls = self._conn.execute("SELECT COUNT(*) FROM events WHERE batch_id=?"
                                   " AND kind IN ('active_nav','search','detail','comments')",
                                   (batch_id,)).fetchone()[0]
        reserved = self._conn.execute(
            "SELECT COALESCE(SUM(count),0) FROM reservations WHERE batch_id=?",
            (batch_id,)).fetchone()[0]
        return int(calls) + int(reserved)

    def charge(self, batch_id: str, kind: str, *, detail: str = "",
               source: str = "tieba") -> dict:
        if kind not in CALL_KINDS:
            raise TiebaBudgetError("invalid_kind", kind)
        locked, reason = self.locked()
        if locked:
            raise TiebaBudgetError("site_locked", reason or "")
        row = self._conn.execute("SELECT * FROM batches WHERE batch_id=?",
                                 (batch_id,)).fetchone()
        if row is None:
            raise TiebaBudgetError("batch_not_found", batch_id)
        now = self._clock()
        started = float(row["started_at"])
        if now - started > float(row["window_seconds"]):
            raise TiebaBudgetError("window_closed", batch_id)
        last = self._conn.execute("SELECT MAX(at) FROM events WHERE batch_id=?",
                                  (batch_id,)).fetchone()[0]
        if last is not None and (now - float(last)) < MIN_INTERVAL:
            raise TiebaBudgetError("interval_not_elapsed", f"{MIN_INTERVAL}s")
        used = self._used(batch_id)
        if used + 1 > int(row["authorized_calls"]):
            raise TiebaBudgetError("quota_exceeded", f"{used}+1>{row['authorized_calls']}")
        self._conn.execute(
            "INSERT INTO events(site, batch_id, kind, detail, at, source)"
            " VALUES (?,?,?,?,?,?)",
            (self.site, batch_id, kind, detail, now, source))
        return {"batch_id": batch_id, "kind": kind, "used": used + 1,
                "remaining": int(row["authorized_calls"]) - used - 1}

    def reserve_records(self, batch_id: str, count: int = 1, *,
                        source: str = "tieba:records") -> dict:
        row = self._conn.execute("SELECT * FROM batches WHERE batch_id=?",
                                 (batch_id,)).fetchone()
        if row is None:
            raise TiebaBudgetError("batch_not_found", batch_id)
        reserved = self._conn.execute(
            "SELECT COALESCE(SUM(count),0) FROM reservations WHERE batch_id=?",
            (batch_id,)).fetchone()[0]
        self._conn.execute("INSERT INTO reservations(site, batch_id, count, at)"
                           " VALUES (?,?,?,?)", (self.site, batch_id, int(count),
                                                 self._clock()))
        total = int(reserved) + int(count)
        target = int(row["records_cap"])
        return {"reserved": int(count), "records_target": target,
                "records_used": total, "over_cap": total > target,
                "over_by": max(0, total - target), "total": total}

    # -- reporting
    def summary(self, batch_id: str | None = None) -> dict:
        if batch_id is None:
            batch_id = self._conn.execute(
                "SELECT batch_id FROM batches ORDER BY started_at DESC LIMIT 1"
            ).fetchone()
            batch_id = batch_id[0] if batch_id else None
        row = self._conn.execute("SELECT * FROM batches WHERE batch_id=?",
                                 (batch_id,)).fetchone()
        if row is None:
            return {"batch_id": None, "authorized_calls": 0, "used": 0,
                    "remaining": 0, "locked": self.locked()[0]}
        used = self._used(batch_id)
        reserved_total = self._conn.execute(
            "SELECT COALESCE(SUM(count),0) FROM reservations WHERE batch_id=?",
            (batch_id,)).fetchone()[0]
        return {"batch_id": batch_id, "authorized_calls": int(row["authorized_calls"]),
                "records_cap": int(row["records_cap"]),
                "records_target": int(row["records_cap"]),
                "records_used": int(reserved_total),
                "over_cap": int(reserved_total) > int(row["records_cap"]),
                "over_by": max(0, int(reserved_total) - int(row["records_cap"])),
                "used": used,
                "remaining": max(0, int(row["authorized_calls"]) - used),
                "window_seconds": float(row["window_seconds"]),
                "locked": self.locked()[0]}

    def events(self, limit: int = 20) -> list[dict]:
        rows = self._conn.execute(
            "SELECT kind, detail, at, source, batch_id FROM events"
            " ORDER BY id DESC LIMIT ?", (int(limit),)).fetchall()
        return [dict(row) for row in rows]


def open_ledger(path=None, *, clock=None) -> TiebaLedger:
    """贴吧专用权威账本（站点隔离，跨进程累计）。"""
    return TiebaLedger(path, clock=clock)


def allowed_url(url) -> bool:
    from urllib.parse import urlsplit

    parts = urlsplit(str(url or ""))
    return parts.scheme in ("http", "https") and (parts.hostname or "").lower() in (
        ALLOWED_HOST, "www.tieba.baidu.com")


def thread_id(url: str) -> str | None:
    match = THREAD_RE.search(str(url or ""))
    return match.group(1) if match else None


def redact_url(url: str) -> str:
    """诊断里去掉查询串（保留 host/path，供复盘不泄露关键词）。"""
    from urllib.parse import urlsplit, urlunsplit

    parts = urlsplit(str(url or ""))
    return urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))


def risk_reason(*, text: str = "", http_status=None) -> str | None:
    if http_status in (403, 429):
        return f"http_{http_status}"
    for marker in RISK_MARKERS:
        if marker and marker in (text or ""):
            return f"text:{marker}"
    return None


# --- doctor / login -------------------------------------------------------

def profile_in_repo(profile) -> bool:
    """True 表示 profile 路径解析后落在仓库内。"""
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
    """本地只读：profile 是否存在、cookie **名称**布尔、浏览器是否可用。不触网。"""
    profile = pathlib.Path(profile)
    cookie_db = profile / "Default" / "Network" / "Cookies"
    names = {name: False for name in COOKIE_NAMES}
    count = 0
    if cookie_db.is_file():
        try:
            con = sqlite3.connect(cookie_db.as_uri() + "?mode=ro&immutable=1", uri=True,
                                  timeout=5.0)
            try:
                rows = con.execute("SELECT name FROM cookies WHERE host_key LIKE '%baidu%'"
                                   ).fetchall()
            finally:
                con.close()
            count = len(rows)
            for (name,) in rows:
                if name in names:
                    names[name] = True
        except sqlite3.Error:
            pass
    chrome = None
    for candidate in ("chrome", "google-chrome", "chrome.exe"):
        path = pathlib.Path(candidate)
        if path.is_file():
            chrome = str(path)
            break
    in_repo = profile_in_repo(profile)
    out = {
        "site": SITE_NAME,
        "profile": str(profile),
        "profile_in_repo": in_repo,
        "repo_root": str(REPO_ROOT),
        "profile_exists": profile.is_dir(),
        "cookie_db_exists": cookie_db.is_file(),
        "cookie_count": count,
        "cookie_names": names,
        "browser": chrome,
        "browser_found": chrome is not None,
        "network": "none",
        "online": "unverified",
        "note": "只读 cookie 名称，不读值；没有任何在线判定",
    }
    if in_repo:
        out["warning"] = ("profile_inside_repo：登录态会写进仓库，禁止使用；"
                          "请改用 DEFAULT_PROFILE 或仓库外的 --profile")
    return out


def login(profile=DEFAULT_PROFILE, *, budget=None, clock=None, timeout: float = 300.0) -> dict:
    """登录窗口只能由显式命令启动；**没有真实样本前一律 unknown**。

    离线批次里连窗口都不开：`budget=None` → 直接返回 unsupported_offline。
    """
    if profile_in_repo(profile):
        return {"site": SITE_NAME, "status": "rejected", "verdict": "rejected",
                "stop": "profile_inside_repo", "profile": str(profile),
                "note": "profile 在仓库内：拒绝登录，未启动窗口、未扣费",
                "network": "none"}
    if budget is None:
        return {"site": SITE_NAME, "status": "unknown", "verdict": "unknown",
                "stop": "unsupported_offline",
                "note": "登录窗口需显式命令与真实浏览器；离线批次不启动",
                "profile": str(pathlib.Path(profile)), "network": "none"}
    raise NotImplementedError("tieba.login_window")


# --- 解析 -----------------------------------------------------------------

def parse_search_html(html: str, *, collected_at: str,
                      limit: int = DEFAULT_RECORDS_TARGET) -> dict:
    """贴吧搜索/吧页 HTML -> 记录（只认 /p/<tid> 链接；不猜）。"""
    text = str(html or "")
    total = len(re.findall(r"/p/\d{5,}", text))
    seen: list[str] = []
    for match in THREAD_RE.finditer(text):
        tid = match.group(1)
        if tid not in seen:
            seen.append(tid)
    out: list[dict] = []
    for tid in seen[:limit]:
        url = THREAD_URL.format(tid=tid)
        out.append(rec.make_record(
            values={"native_id": tid, "type": "thread", "parent_id": None,
                    "url": url, "title": None, "text": None,
                    "published_at": None, "voteup": None, "comments": None,
                    "likes": None, "reposts": None, "author": None,
                    "root_comment_id": None},
            evidence={"native_id": "html:a[href*=/p/]", "type": "constant:thread",
                      "url": "html:a[href*=/p/]"},
            collected_at=collected_at, source="tieba:search",
            not_applicable=("root_comment_id", "parent_id", "voteup", "reposts")))
    stop = "records" if out else ("empty" if total == 0 else "unsupported")
    return {"records": out, "stop": stop, "structure": "html:links",
            "anchors_total": total, "anchors_recognized": len(seen),
            "anchors_rejected": max(0, total - len(seen))}


TITLE_RE = re.compile(r"<title>(.*?)</title>", re.S | re.I)


def parse_thread_html(html: str, url: str, *, collected_at: str) -> dict:
    """帖子详情页 -> 一条记录（标题来自 `<title>`）；拿不到就 unsupported。"""
    text = str(html or "")
    tid = thread_id(url)
    if not allowed_url(url) or not tid:
        return {"record": None, "stop": "unsupported_content_url"}
    if not text.strip():
        return {"record": None, "stop": "empty", "structure": "html:empty"}
    title_match = TITLE_RE.search(text)
    title = (title_match.group(1).strip() if title_match else "") or None
    if title is None:
        return {"record": None, "stop": "unsupported", "structure": "html:unknown"}
    record = rec.make_record(
        values={"native_id": tid, "type": "thread", "parent_id": None,
                "url": THREAD_URL.format(tid=tid), "title": title, "text": None,
                "published_at": None, "voteup": None, "comments": None,
                "likes": None, "reposts": None, "author": None,
                "root_comment_id": None},
        evidence={"native_id": "url:/p/<tid>", "type": "constant:thread",
                  "url": "input:thread_url", "title": "html:title"},
        collected_at=collected_at, source="tieba:detail",
        not_applicable=("root_comment_id", "parent_id", "voteup", "reposts"))
    return {"record": record, "stop": None, "structure": "html:title"}


def comments(*_, **__) -> dict:
    """贴吧评论端点**尚未侦察**：显式 unsupported，且必须在预扣之前返回。"""
    return {"site": SITE_NAME, "status": "unsupported", "stop": "unsupported_endpoint",
            "records": [], "charged": False,
            "note": "评论端点未侦察；不预扣、不返回空成功"}


# --- 导出 -----------------------------------------------------------------

def export(input_path, output_path=None, *, fmt: str = "jsonl") -> dict:
    """白名单导出：只保留 `records.EXPORT_FIELDS`，不认识的键丢弃并计数。"""
    import json

    src = pathlib.Path(input_path)
    out = pathlib.Path(output_path) if output_path else src.with_suffix(".export." + fmt)
    rows: list[dict] = []
    dropped: set[str] = set()
    for line in src.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if not isinstance(row, dict):
            continue
        kept = {}
        for key, value in row.items():
            if key in rec.EXPORT_FIELDS:
                kept[key] = value
            else:
                dropped.add(key)
        rows.append(kept)
    rec.write_records(rows, out, fmt=fmt)
    return {"ok": True, "site": SITE_NAME, "count": len(rows), "path": str(out),
            "dropped_keys": sorted(dropped), "format": fmt}


EXIT_OK = codes.EXIT_OK
