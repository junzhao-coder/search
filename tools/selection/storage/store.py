"""最小隔离持久化：帖子/评论、可核实原生 ID、未知值语义、续跑与停止状态。

v18 单帖阶段只做这一件事：

* 身份 = ``(platform, kind, native_id)``：平台或类型不同就是不同内容；
* 没有原生 ID 的内容**不伪造 ID**，作为观察保留（``native_id NULL`` +
  ``needs_recheck=1``），不按文本启发式合并，避免把两条不同评论合成一条；
* 未知值一律 ``NULL``：``likes=NULL`` 是没读到，``0`` 是确实为 0；
* 每次 ``save()`` 是一个事务：中断只回滚这一批，已提交记录不受影响；续跑用
  同一个 ``run_id`` 再写一遍即可，原生 ID 相同不会重复；
* 停止/覆盖状态写在 ``runs`` 里：``complete`` 只有在 ``end_signal`` 时才允许为真。

库的身份是**应用标识 + schema 版本**（``PRAGMA application_id`` /
``PRAGMA user_version``）：非空、不是本模块可验证 schema 的库在改
``journal_mode`` / 建表之前一律拒绝；旧版（v1）库只有在 schema 逐列核对通过后
才做原地迁移。只写调用方显式传入的文件，不读也不改既有业务库、账本或历史导出。
标准库实现。
"""

from __future__ import annotations

import json
import pathlib
import re
import sqlite3
import time
import uuid
from dataclasses import dataclass, field

POST = "post"
COMMENT = "comment"
KINDS = (POST, COMMENT)

#: 终止词表与 ``access.collector`` / tieba 对齐；新增原因先登记再使用。
STOP_END = "end_signal"          # 可验证的结束信号：唯一允许 complete=True 的原因
STOP_CANCELLED = "cancelled"     # 用户取消：检查点保留，可续跑
STOP_PAUSED = "paused"           # 暂停超时：可续跑
STOP_RISK = "risk"               # 平台风险信号：即停
STOP_BATCH = "batch_expired"     # 批次窗口到期：检查点，不是完成
STOP_PENDING = "pending"         # 证据不足/未结束：可续跑
STOP_ERROR = "error"             # 传输或解析异常：已落盘记录保留
STOP_RECORDS = "records"         # 拿到记录后的正常停：不等于取全
STOP_NO_MORE = "no_more_evidence"  # 连续无新增/无位移：部分/未知

STOP_REASONS = frozenset({STOP_END, STOP_CANCELLED, STOP_PAUSED, STOP_RISK,
                          STOP_BATCH, STOP_PENDING, STOP_ERROR, STOP_RECORDS,
                          STOP_NO_MORE})

#: 发布时间精度；``unknown`` = 能读到原文但无法归一化。
PRECISIONS = ("second", "minute", "hour", "day", "relative", "unknown")

#: 本模块的持久应用标识（"V18\\0"）；**不随 schema 版本变化**。
APPLICATION_ID = 0x56313800
SCHEMA_VERSION = 3

RUNS_DDL = """CREATE TABLE IF NOT EXISTS runs (
  run_id TEXT PRIMARY KEY,
  platform TEXT NOT NULL,
  target_native_id TEXT,
  started_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  stop_reason TEXT,
  complete INTEGER NOT NULL DEFAULT 0 CHECK (complete IN (0, 1)),
  declared_count INTEGER,
  note TEXT,
  resumes INTEGER NOT NULL DEFAULT 0
)"""

RUN_STOPS_DDL = """CREATE TABLE IF NOT EXISTS run_stops (
  stop_id INTEGER PRIMARY KEY AUTOINCREMENT,
  run_id TEXT NOT NULL REFERENCES runs(run_id),
  stop_reason TEXT NOT NULL,
  complete INTEGER NOT NULL CHECK (complete IN (0, 1)),
  at TEXT NOT NULL,
  note TEXT
)"""

ITEMS_DDL = """CREATE TABLE IF NOT EXISTS items (
  item_id INTEGER PRIMARY KEY AUTOINCREMENT,
  platform TEXT NOT NULL,
  kind TEXT NOT NULL CHECK (kind IN ('post', 'comment')),
  native_id TEXT,
  id_verified INTEGER NOT NULL CHECK (id_verified IN (0, 1)),
  parent_native_id TEXT,
  parent_kind TEXT CHECK (parent_kind IS NULL OR parent_kind IN ('post', 'comment')),
  post_native_id TEXT,
  url TEXT,
  title TEXT,
  text TEXT,
  text_truncated INTEGER CHECK (text_truncated IS NULL OR text_truncated IN (0, 1)),
  author TEXT,
  likes INTEGER,
  comments_count INTEGER,
  published_at_raw TEXT,
  published_at TEXT,
  published_at_precision TEXT,
  collected_at TEXT NOT NULL,
  last_seen_at TEXT NOT NULL,
  first_run_id TEXT REFERENCES runs(run_id),
  last_run_id TEXT REFERENCES runs(run_id),
  needs_recheck INTEGER NOT NULL DEFAULT 0 CHECK (needs_recheck IN (0, 1)),
  source TEXT,
  evidence_json TEXT,
  not_applicable_json TEXT,
  parent_known INTEGER CHECK (parent_known IS NULL OR parent_known IN (0, 1)),
  recheck_explicit INTEGER NOT NULL DEFAULT 0 CHECK (recheck_explicit IN (0, 1)),
  CHECK (id_verified = (native_id IS NOT NULL)),
  CHECK (kind <> 'comment' OR post_native_id IS NOT NULL),
  CHECK (kind <> 'comment' OR parent_known IS NOT NULL),
  CHECK (kind <> 'post' OR parent_known IS NULL),
  CHECK (parent_known IS NOT 1 OR (parent_native_id IS NOT NULL
         AND parent_kind IN ('post', 'comment'))),
  CHECK (parent_known IS NOT 0 OR (parent_native_id IS NULL AND parent_kind IS NULL))
)"""

INDEX_DDL = (
    "CREATE UNIQUE INDEX IF NOT EXISTS ux_items_identity"
    " ON items(platform, kind, native_id) WHERE native_id IS NOT NULL",
    "CREATE INDEX IF NOT EXISTS ix_items_thread ON items(platform, post_native_id)",
    "CREATE INDEX IF NOT EXISTS ix_items_parent ON items(platform, parent_native_id)",
    "CREATE INDEX IF NOT EXISTS ix_run_stops_run ON run_stops(run_id)",
)

SCHEMA_STATEMENTS = (RUNS_DDL, RUN_STOPS_DDL, ITEMS_DDL) + INDEX_DDL

# --- 可验证 schema：列顺序/类型/非空/默认值/PK 与具名索引 -------------------
V1_RUNS = (
    ("run_id", "TEXT", 0, None, 1),
    ("platform", "TEXT", 1, None, 0),
    ("target_native_id", "TEXT", 0, None, 0),
    ("started_at", "TEXT", 1, None, 0),
    ("updated_at", "TEXT", 1, None, 0),
    ("stop_reason", "TEXT", 0, None, 0),
    ("complete", "INTEGER", 1, "0", 0),
    ("declared_count", "INTEGER", 0, None, 0),
    ("note", "TEXT", 0, None, 0),
)
V2_RUNS = V1_RUNS + (("resumes", "INTEGER", 1, "0", 0),)

V1_ITEMS = (
    ("item_id", "INTEGER", 0, None, 1),
    ("platform", "TEXT", 1, None, 0),
    ("kind", "TEXT", 1, None, 0),
    ("native_id", "TEXT", 0, None, 0),
    ("id_verified", "INTEGER", 1, None, 0),
    ("parent_native_id", "TEXT", 0, None, 0),
    ("parent_kind", "TEXT", 0, None, 0),
    ("post_native_id", "TEXT", 0, None, 0),
    ("url", "TEXT", 0, None, 0),
    ("title", "TEXT", 0, None, 0),
    ("text", "TEXT", 0, None, 0),
    ("text_truncated", "INTEGER", 0, None, 0),
    ("author", "TEXT", 0, None, 0),
    ("likes", "INTEGER", 0, None, 0),
    ("comments_count", "INTEGER", 0, None, 0),
    ("published_at_raw", "TEXT", 0, None, 0),
    ("published_at", "TEXT", 0, None, 0),
    ("published_at_precision", "TEXT", 0, None, 0),
    ("collected_at", "TEXT", 1, None, 0),
    ("last_seen_at", "TEXT", 1, None, 0),
    ("first_run_id", "TEXT", 0, None, 0),
    ("last_run_id", "TEXT", 0, None, 0),
    ("needs_recheck", "INTEGER", 1, "0", 0),
    ("source", "TEXT", 0, None, 0),
    ("evidence_json", "TEXT", 0, None, 0),
    ("not_applicable_json", "TEXT", 0, None, 0),
)
V2_ITEMS = V1_ITEMS + (("parent_known", "INTEGER", 0, None, 0),)
V3_ITEMS = V2_ITEMS + (("recheck_explicit", "INTEGER", 1, "0", 0),)

V2_RUN_STOPS = (
    ("stop_id", "INTEGER", 0, None, 1),
    ("run_id", "TEXT", 1, None, 0),
    ("stop_reason", "TEXT", 1, None, 0),
    ("complete", "INTEGER", 1, None, 0),
    ("at", "TEXT", 1, None, 0),
    ("note", "TEXT", 0, None, 0),
)

V1_INDEXES = {
    "ux_items_identity": ("items", ("platform", "kind", "native_id"), 1, 1),
    "ix_items_thread": ("items", ("platform", "post_native_id"), 0, 0),
    "ix_items_parent": ("items", ("platform", "parent_native_id"), 0, 0),
}
V2_INDEXES = dict(V1_INDEXES,
                  ix_run_stops_run=("run_stops", ("run_id",), 0, 0))


def utc_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _required_text(value, name: str) -> str:
    text = str(value if value is not None else "").strip()
    if not text:
        raise ValueError("%s_required" % name)
    if any(ch.isspace() for ch in text):
        raise ValueError("%s_invalid" % name)
    return text


def _optional_id(value, name: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("%s_must_be_str" % name)
    if not value or value != value.strip() or any(ch.isspace() for ch in value):
        raise ValueError("%s_invalid" % name)
    return value


@dataclass(frozen=True)
class Item:
    """一条帖子或评论。字段为 None = 未知；绝不用 0/空串冒充未知。

    父级是**三态**，没有"缺省就是顶层"这回事：

    * ``parent_known=True`` 且没给 ``parent_native_id``：已知顶层（父 = 帖子）；
    * ``parent_known=True`` 且给了 ``parent_native_id``：已知楼中楼父 ID；
    * ``parent_known=False``：父评论未知——保留 ``post_native_id``，父级留空并
      标 ``needs_recheck``；不会当成帖子的直接子评论。

    ``parent_known=None`` 时只按证据推断：给了父 ID 视为已知，没给视为未知。
    """

    platform: str
    kind: str
    native_id: str | None = None
    post_native_id: str | None = None
    parent_native_id: str | None = None
    parent_kind: str | None = None
    parent_known: bool | None = None
    url: str | None = None
    title: str | None = None
    text: str | None = None
    text_truncated: bool | None = None
    author: str | None = None
    likes: int | None = None
    comments_count: int | None = None
    published_at_raw: str | None = None
    published_at: str | None = None
    published_at_precision: str | None = None
    collected_at: str = field(default_factory=utc_now)
    source: str | None = None
    evidence: dict | None = None
    not_applicable: tuple = ()
    #: 用户显式要求复核；与"仅因父级未知/无 ID 自动触发"分开记账。
    recheck: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "platform", _required_text(self.platform, "platform"))
        if self.kind not in KINDS:
            raise ValueError("kind_invalid")
        object.__setattr__(self, "native_id", _optional_id(self.native_id, "native_id"))
        if self.kind == POST:
            if self.parent_native_id is not None or self.parent_kind is not None \
                    or self.parent_known is not None:
                raise ValueError("post_has_parent")
            post = (_optional_id(self.post_native_id, "post_native_id")
                    if self.post_native_id is not None else self.native_id)
            if post != self.native_id:
                raise ValueError("post_attribution_mismatch")
            object.__setattr__(self, "post_native_id", post)
        else:
            post = _optional_id(self.post_native_id, "post_native_id")
            if post is None:
                raise ValueError("comment_requires_post_native_id")
            parent = _optional_id(self.parent_native_id, "parent_native_id")
            known = self.parent_known
            if known is None:
                known = parent is not None      # 只按证据推断，缺省不是顶层
            if known:
                if parent is None:
                    parent, parent_kind = post, POST
                else:
                    parent_kind = self.parent_kind or (
                        POST if parent == post else COMMENT)
                    if parent_kind not in KINDS:
                        raise ValueError("parent_kind_invalid")
                    if (parent_kind == POST) != (parent == post):
                        raise ValueError("parent_kind_mismatch")
            else:
                if parent is not None or self.parent_kind is not None:
                    raise ValueError("unknown_parent_with_parent")
                parent_kind = None
            object.__setattr__(self, "post_native_id", post)
            object.__setattr__(self, "parent_native_id", parent)
            object.__setattr__(self, "parent_kind", parent_kind)
            object.__setattr__(self, "parent_known", bool(known))
        for name in ("likes", "comments_count"):
            value = getattr(self, name)
            if value is None:
                continue
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError("%s_invalid" % name)
        if self.text_truncated is not None and not isinstance(self.text_truncated, bool):
            raise ValueError("text_truncated_invalid")
        if self.text_truncated is not None and self.text is None:
            raise ValueError("text_truncated_requires_text")
        if not isinstance(self.recheck, bool):
            raise ValueError("recheck_invalid")
        if (self.published_at_precision is not None
                and self.published_at_precision not in PRECISIONS):
            raise ValueError("published_at_precision_invalid")
        if self.published_at_precision is not None and self.published_at is None:
            # 精度描述的是规范化时间；没有规范时间就不带精度，避免三字段错配。
            raise ValueError("published_at_precision_without_normalized")
        if not str(self.collected_at or "").strip():
            raise ValueError("collected_at_required")
        if self.evidence is not None and not isinstance(self.evidence, dict):
            raise ValueError("evidence_invalid")
        na = tuple(self.not_applicable or ())
        if any(not isinstance(entry, str) or not entry for entry in na):
            raise ValueError("not_applicable_invalid")
        object.__setattr__(self, "not_applicable", na)

    @property
    def needs_recheck(self) -> bool:
        """显式复核要求，或身份不完整（无原生 ID / 评论父级未知）。"""
        if self.recheck:
            return True
        if self.native_id is None:
            return True
        return self.kind == COMMENT and not self.parent_known


class Storage:
    """隔离的 SQLite 存储；一个实例一个连接，调用方负责 close/with。"""

    def __init__(self, path, *, clock=None) -> None:
        self.path = pathlib.Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._clock = clock or utc_now
        self._conn = sqlite3.connect(str(self.path), timeout=30.0)
        self._conn.row_factory = sqlite3.Row
        try:
            action = self._plan()
            self._conn.execute("PRAGMA journal_mode=WAL")
            if action == "create":
                _create_schema(self._conn)
            elif action == "migrate_v1":
                _migrate_v1(self._conn)
            elif action == "migrate_v2":
                _migrate_v2(self._conn)
            elif action == "stamp":
                _stamp_identity(self._conn)
            self._conn.execute("PRAGMA foreign_keys=ON")
        except BaseException:
            self._conn.close()
            raise

    def _plan(self) -> str:
        """在任何写操作（journal_mode/DDL）之前判断这是不是本模块的库。"""
        conn = self._conn
        try:
            app_id = int(conn.execute("PRAGMA application_id").fetchone()[0])
            version = int(conn.execute("PRAGMA user_version").fetchone()[0])
            objects = frozenset(
                (row[0], row[1]) for row in conn.execute(
                    "SELECT type, name FROM sqlite_master"
                    " WHERE name NOT LIKE 'sqlite_%'"))
        except sqlite3.DatabaseError as exc:
            raise RuntimeError("not_a_v18_store") from exc
        if app_id not in (0, APPLICATION_ID):
            raise RuntimeError("not_a_v18_store")
        if not objects:
            if version != 0:
                raise RuntimeError("schema_version_mismatch:%s" % version)
            return "create"
        is_v3 = _matches_v3(conn, objects)
        is_v2 = False if is_v3 else _matches_v2(conn, objects)
        is_v1 = False if (is_v3 or is_v2) else _matches_v1(conn, objects)
        if not (is_v3 or is_v2 or is_v1):
            # 陌生 schema：即使 user_version=1、表名相同也不接管。
            if app_id == APPLICATION_ID:
                raise RuntimeError("schema_mismatch")
            raise RuntimeError("not_a_v18_store")
        if version > SCHEMA_VERSION:
            raise RuntimeError("schema_version_mismatch:%s" % version)
        if is_v3:
            if app_id == APPLICATION_ID and version == SCHEMA_VERSION:
                return "open"
            return "stamp"
        if is_v2:
            return "migrate_v2"
        return "migrate_v1"

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> "Storage":
        return self

    def __exit__(self, *exc_info) -> None:
        self.close()

    # ------------------------------------------------------------- runs
    def begin_run(self, platform: str, *, run_id: str | None = None,
                  target_native_id: str | None = None,
                  started_at: str | None = None) -> str:
        """开始或续跑一次采集；续跑清掉"已完成"，旧停止原因留在 run_stops。"""
        platform = _required_text(platform, "platform")
        run_id = run_id or "%s-%s" % (platform, uuid.uuid4().hex[:12])
        target = _optional_id(target_native_id, "target_native_id")
        now = started_at or self._clock()
        row = self._conn.execute("SELECT * FROM runs WHERE run_id=?",
                                 (run_id,)).fetchone()
        if row is None:
            with self._conn:
                self._conn.execute(
                    "INSERT INTO runs(run_id, platform, target_native_id, started_at,"
                    " updated_at) VALUES (?,?,?,?,?)",
                    (run_id, platform, target, now, now))
            return run_id
        if row["platform"] != platform:
            raise ValueError("run_platform_mismatch")
        if target and row["target_native_id"] and row["target_native_id"] != target:
            raise ValueError("run_target_mismatch")
        resumed = 1 if row["stop_reason"] is not None else 0
        with self._conn:
            self._conn.execute(
                "UPDATE runs SET target_native_id=COALESCE(target_native_id, ?),"
                " stop_reason=NULL, complete=0, resumes=resumes+?, updated_at=?"
                " WHERE run_id=?", (target, resumed, now, run_id))
        return run_id

    def finish_run(self, run_id: str, *, stop_reason: str, complete: bool = False,
                   declared_count: int | None = None, note: str = "") -> dict:
        """登记停止原因；``complete=True`` 只允许配 ``end_signal``。"""
        self._run_row(run_id)
        if stop_reason not in STOP_REASONS:
            raise ValueError("stop_reason_invalid:%s" % stop_reason)
        if complete and stop_reason != STOP_END:
            raise ValueError("complete_requires_end_signal")
        if declared_count is not None:
            if isinstance(declared_count, bool) or not isinstance(declared_count, int) \
                    or declared_count < 0:
                raise ValueError("declared_count_invalid")
        now = self._clock()
        with self._conn:
            self._conn.execute(
                "INSERT INTO run_stops(run_id, stop_reason, complete, at, note)"
                " VALUES (?,?,?,?,?)",
                (run_id, stop_reason, int(bool(complete)), now, note))
            self._conn.execute(
                "UPDATE runs SET stop_reason=?, complete=?,"
                " declared_count=COALESCE(?, declared_count),"
                " note=COALESCE(NULLIF(?, ''), note), updated_at=? WHERE run_id=?",
                (stop_reason, int(bool(complete)), declared_count, note, now, run_id))
        return self.run_summary(run_id)

    def run_summary(self, run_id: str) -> dict:
        run = self._run_row(run_id)
        first_seen = int(self._conn.execute(
            "SELECT COUNT(*) FROM items WHERE first_run_id=?", (run_id,)).fetchone()[0])
        target = run["target_native_id"]
        thread_items = None
        if target:
            thread_items = int(self._conn.execute(
                "SELECT COUNT(*) FROM items WHERE platform=? AND post_native_id=?",
                (run["platform"], target)).fetchone()[0])
        history = []
        for row in self._conn.execute(
                "SELECT stop_reason, complete, at, note FROM run_stops"
                " WHERE run_id=? ORDER BY stop_id", (run_id,)):
            history.append({"stop_reason": row["stop_reason"],
                            "complete": bool(row["complete"]),
                            "at": row["at"], "note": row["note"]})
        return {"run_id": run_id, "platform": run["platform"],
                "target_native_id": target, "started_at": run["started_at"],
                "updated_at": run["updated_at"], "stop_reason": run["stop_reason"],
                "complete": bool(run["complete"]),
                "pending": run["stop_reason"] is None,
                "resumes": int(run["resumes"]),
                "previous_stop_reason": (history[-1]["stop_reason"]
                                         if history else None),
                "stop_history": history,
                "declared_count": run["declared_count"], "note": run["note"],
                "items_first_seen": first_seen, "thread_items": thread_items}

    def runs(self, limit: int = 20) -> list:
        rows = self._conn.execute(
            "SELECT * FROM runs ORDER BY started_at DESC, run_id DESC LIMIT ?",
            (int(limit),)).fetchall()
        return [{**dict(row), "complete": bool(row["complete"])} for row in rows]

    # ------------------------------------------------------------- writes
    def save(self, items, *, run_id: str | None = None) -> dict:
        """一个事务写入一批；原生 ID 相同合并，无 ID 逐条保留为观察。"""
        batch = list(items)
        for item in batch:
            if not isinstance(item, Item):
                raise TypeError("item_required")
        target = None
        if run_id is not None:
            run = self._run_row(run_id)
            for item in batch:
                if item.platform != run["platform"]:
                    raise ValueError("platform_mismatch")
            target = run["target_native_id"]
            if target is None:
                # 目标未知时从本批证据补上；一批里出现两个帖子就是冲突。
                candidates = {item.post_native_id for item in batch
                              if item.post_native_id is not None}
                if len(candidates) > 1:
                    raise ValueError("run_target_conflict")
                target = next(iter(candidates), None)
            for item in batch:
                if target is not None and item.post_native_id != target:
                    raise ValueError("run_target_mismatch:%s" % item.native_id)
        inserted = updated = no_id = 0
        ids: list = []
        with self._conn:
            if run_id is not None:
                if run["target_native_id"] is None and target is not None:
                    self._conn.execute(
                        "UPDATE runs SET target_native_id=? WHERE run_id=?",
                        (target, run_id))
                self._conn.execute("UPDATE runs SET updated_at=? WHERE run_id=?",
                                   (self._clock(), run_id))
            for item in batch:
                if item.native_id is None:
                    ids.append(self._insert(item, run_id))
                    inserted += 1
                    no_id += 1
                    continue
                row = self._conn.execute(
                    "SELECT * FROM items WHERE platform=? AND kind=? AND native_id=?",
                    (item.platform, item.kind, item.native_id)).fetchone()
                if row is None:
                    ids.append(self._insert(item, run_id))
                    inserted += 1
                    continue
                old = _decode(dict(row))
                self._check_conflicts(old, item)
                changes = self._merge(old, item, run_id)
                assignments = ", ".join("%s=?" % key for key in changes)
                self._conn.execute(
                    "UPDATE items SET %s WHERE item_id=?" % assignments,
                    (*changes.values(), row["item_id"]))
                ids.append(int(row["item_id"]))
                updated += 1
        return {"inserted": inserted, "updated": updated,
                "without_native_id": no_id, "item_ids": ids}

    def _insert(self, item: Item, run_id: str | None) -> int:
        values = {
            "platform": item.platform, "kind": item.kind,
            "native_id": item.native_id, "id_verified": int(item.native_id is not None),
            "parent_native_id": item.parent_native_id, "parent_kind": item.parent_kind,
            "parent_known": (None if item.kind == POST
                             else int(bool(item.parent_known))),
            "post_native_id": item.post_native_id, "url": item.url,
            "title": item.title, "text": item.text,
            "text_truncated": (None if item.text_truncated is None
                               else int(item.text_truncated)),
            "author": item.author, "likes": item.likes,
            "comments_count": item.comments_count,
            "published_at_raw": item.published_at_raw,
            "published_at": item.published_at,
            "published_at_precision": item.published_at_precision,
            "collected_at": item.collected_at, "last_seen_at": item.collected_at,
            "first_run_id": run_id, "last_run_id": run_id,
            "needs_recheck": int(item.needs_recheck),
            "recheck_explicit": int(bool(item.recheck)),
            "source": item.source,
            "evidence_json": (json.dumps(item.evidence, ensure_ascii=False, sort_keys=True)
                              if item.evidence else None),
            "not_applicable_json": (json.dumps(list(item.not_applicable), ensure_ascii=False)
                                    if item.not_applicable else None),
        }
        columns = ", ".join(values)
        marks = ", ".join("?" for _ in values)
        cursor = self._conn.execute(
            "INSERT INTO items (%s) VALUES (%s)" % (columns, marks),
            tuple(values.values()))
        return int(cursor.lastrowid)

    @staticmethod
    def _check_conflicts(old: dict, item: Item) -> None:
        """同一原生 ID 的所属帖子/父级不允许被静默改写。"""
        old_post = old.get("post_native_id")
        if old_post and item.post_native_id and old_post != item.post_native_id:
            raise ValueError("post_conflict:%s" % item.native_id)
        if item.kind == COMMENT and old.get("parent_known") and item.parent_known:
            if (old.get("parent_native_id"), old.get("parent_kind")) != (
                    item.parent_native_id, item.parent_kind):
                raise ValueError("parent_conflict:%s" % item.native_id)

    @staticmethod
    def _merge(old: dict, item: Item, run_id: str | None) -> dict:
        """后写覆盖先写的**已知**值；未知值不会抹掉已知值。"""
        changes: dict = {}
        for name in ("url", "title", "author", "likes", "comments_count", "source"):
            value = getattr(item, name)
            if value is not None:
                changes[name] = value
        changes.update(Storage._merge_time(old, item))
        changes.update(Storage._merge_text(old, item))
        parent_known = old.get("parent_known")
        if item.kind == COMMENT and item.parent_known:
            # 从未知升级到有证据的已知父级；已知的不允许被改成另一个父级
            # （冲突已在 _check_conflicts 里拒绝）。
            changes["parent_native_id"] = item.parent_native_id
            changes["parent_kind"] = item.parent_kind
            changes["parent_known"] = 1
            parent_known = True
        evidence = dict(old.get("evidence") or {})
        new_evidence = {key: value for key, value in (item.evidence or {}).items()
                        if value}
        adopted = set()
        for field, column in (("url", "url"), ("title", "title"),
                              ("author", "author"), ("likes", "likes"),
                              ("comments", "comments_count")):
            if column in changes and changes[column] != old.get(column):
                adopted.add(field)
        if "text" in changes and changes["text"] != old.get("text"):
            adopted.add("text")
        if any(changes.get(name) != old.get(name)
               for name in ("published_at_raw", "published_at",
                            "published_at_precision")
               if name in changes):
            adopted.add("published_at")
        if item.kind == COMMENT and item.parent_known and (
                old.get("parent_native_id"), old.get("parent_kind")) != (
                item.parent_native_id, item.parent_kind):
            adopted.add("parent_id")
        # 证据随实际采纳的值走：被拒绝的新值不能改来源；采纳但没给证据时，
        # 不能沿用属于旧值的来源（宁可为空，也不串换）。
        for field in adopted:
            tag = new_evidence.get(field)
            if tag:
                evidence[field] = tag
            else:
                evidence.pop(field, None)
        for field, tag in new_evidence.items():
            if field not in adopted and not evidence.get(field):
                evidence[field] = tag
        if evidence:
            changes["evidence_json"] = json.dumps(evidence, ensure_ascii=False,
                                                  sort_keys=True)
        elif old.get("evidence"):
            changes["evidence_json"] = None
        na = tuple(item.not_applicable) or tuple(old.get("not_applicable") or ())
        if na:
            changes["not_applicable_json"] = json.dumps(list(na), ensure_ascii=False)
        # 显式复核要求与"身份不完整"的自动复核分开：父级升级只清自动原因。
        explicit = bool(old.get("recheck_explicit")) or bool(item.recheck)
        auto = item.native_id is None or (
            item.kind == COMMENT and not parent_known)
        changes["recheck_explicit"] = int(explicit)
        changes["needs_recheck"] = int(explicit or auto)
        changes["last_seen_at"] = item.collected_at
        if run_id:
            changes["last_run_id"] = run_id
        return changes

    @staticmethod
    def _merge_time(old: dict, item: Item) -> dict:
        """原文/规范化/精度是一组：新原文不会和旧的规范时间拼在一起。"""
        new_raw = item.published_at_raw
        new_norm = item.published_at
        new_prec = item.published_at_precision
        old_raw = old.get("published_at_raw")
        old_norm = old.get("published_at")
        old_prec = old.get("published_at_precision")
        if new_norm is not None:
            same = old_norm == new_norm
            return {"published_at_raw": (new_raw if new_raw is not None
                                         else (old_raw if same else None)),
                    "published_at": new_norm,
                    "published_at_precision": (new_prec if new_prec is not None
                                               else (old_prec if same else None))}
        if new_raw is not None and new_raw != old_raw:
            # 新原文、没有规范化时间：旧的规范时间与精度不再可信，一起清空。
            return {"published_at_raw": new_raw, "published_at": None,
                    "published_at_precision": None}
        return {}

    @staticmethod
    def _merge_text(old: dict, item: Item) -> dict:
        """截断三态：旧无正文时新正文一律保留；已知完整不被截断摘要覆盖。"""
        if item.text is None:
            return {}
        old_text = old.get("text")
        old_flag = old.get("text_truncated")
        new_flag = item.text_truncated
        if old_text is None or old_text == "":
            # 旧记录没有正文：哪怕是截断摘要也是唯一可得的正文，必须保留。
            return {"text": item.text,
                    "text_truncated": None if new_flag is None else int(new_flag)}
        if old_text == item.text:
            # 同一文本：完整性可以从"未知"升级为已知截断/完整，但不把已知完整降级。
            if new_flag is None or new_flag == old_flag:
                return {}
            if old_flag is False and new_flag is True:
                return {}
            return {"text_truncated": int(new_flag)}
        if new_flag is True and old_flag is not True:
            return {}                        # 新采样明确截断，旧文本不是已知截断
        return {"text": item.text,
                "text_truncated": None if new_flag is None else int(new_flag)}

    # -------------------------------------------------------------- reads
    def items(self, *, platform: str | None = None, kind: str | None = None) -> list:
        sql, args = "SELECT * FROM items", []
        where = []
        if platform:
            where.append("platform=?")
            args.append(platform)
        if kind:
            if kind not in KINDS:
                raise ValueError("kind_invalid")
            where.append("kind=?")
            args.append(kind)
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY item_id"
        return [_decode(dict(row)) for row in self._conn.execute(sql, args)]

    def get(self, platform: str, kind: str, native_id: str) -> dict | None:
        row = self._conn.execute(
            "SELECT * FROM items WHERE platform=? AND kind=? AND native_id=?",
            (platform, kind, native_id)).fetchone()
        return _decode(dict(row)) if row is not None else None

    def thread(self, platform: str, post_native_id: str) -> list:
        rows = self._conn.execute(
            "SELECT * FROM items WHERE platform=? AND post_native_id=? ORDER BY item_id",
            (platform, post_native_id)).fetchall()
        return [_decode(dict(row)) for row in rows]

    def children(self, platform: str, parent_native_id: str, *,
                 parent_kind: str | None = None) -> list:
        sql = "SELECT * FROM items WHERE platform=? AND parent_native_id=?"
        args = [platform, parent_native_id]
        if parent_kind:
            sql += " AND parent_kind=?"
            args.append(parent_kind)
        sql += " ORDER BY item_id"
        return [_decode(dict(row)) for row in self._conn.execute(sql, args)]

    def counts(self) -> dict:
        def one(sql: str) -> int:
            return int(self._conn.execute(sql).fetchone()[0])

        return {"items": one("SELECT COUNT(*) FROM items"),
                "posts": one("SELECT COUNT(*) FROM items WHERE kind='post'"),
                "comments": one("SELECT COUNT(*) FROM items WHERE kind='comment'"),
                "without_native_id": one(
                    "SELECT COUNT(*) FROM items WHERE native_id IS NULL"),
                "needs_recheck": one(
                    "SELECT COUNT(*) FROM items WHERE needs_recheck=1"),
                "runs": one("SELECT COUNT(*) FROM runs")}

    # ------------------------------------------------------------ internal
    def _run_row(self, run_id: str) -> sqlite3.Row:
        row = self._conn.execute("SELECT * FROM runs WHERE run_id=?",
                                 (str(run_id),)).fetchone()
        if row is None:
            raise ValueError("run_not_found:%s" % run_id)
        return row


# --- schema 识别 / 创建 / 迁移 ---------------------------------------------
def _table_columns(conn, table: str) -> tuple:
    return tuple((row[1], (row[2] or "").upper(), int(row[3]), row[4], int(row[5]))
                 for row in conn.execute("PRAGMA table_info(%s)" % table))


def _index_matches(conn, name: str, spec: tuple) -> bool:
    table, columns, unique, partial = spec
    rows = [row for row in conn.execute("PRAGMA index_list(%s)" % table)
            if row[1] == name]
    if len(rows) != 1:
        return False
    row = rows[0]
    if int(row[2]) != unique or int(row[4]) != partial:
        return False
    actual = tuple(item[2] for item in conn.execute("PRAGMA index_info(%s)" % name))
    if actual != columns:
        return False
    if partial:
        stored = conn.execute("SELECT sql FROM sqlite_master"
                              " WHERE type='index' AND name=?", (name,)).fetchone()
        if not stored or "where native_id is not null" not in (
                re.sub(r"\s+", " ", stored[0] or "").lower()):
            return False
    return True


def _expected_objects(tables, indexes) -> frozenset:
    return frozenset([("table", name) for name in tables]
                     + [("index", name) for name in indexes])


def _matches_v1(conn, objects: frozenset) -> bool:
    return (objects == _expected_objects(("runs", "items"), V1_INDEXES)
            and _table_columns(conn, "runs") == V1_RUNS
            and _table_columns(conn, "items") == V1_ITEMS
            and all(_index_matches(conn, name, spec)
                    for name, spec in V1_INDEXES.items()))


def _matches_v2(conn, objects: frozenset) -> bool:
    return (objects == _expected_objects(("runs", "run_stops", "items"), V2_INDEXES)
            and _table_columns(conn, "runs") == V2_RUNS
            and _table_columns(conn, "items") == V2_ITEMS
            and _table_columns(conn, "run_stops") == V2_RUN_STOPS
            and all(_index_matches(conn, name, spec)
                    for name, spec in V2_INDEXES.items()))


def _matches_v3(conn, objects: frozenset) -> bool:
    return (objects == _expected_objects(("runs", "run_stops", "items"), V2_INDEXES)
            and _table_columns(conn, "runs") == V2_RUNS
            and _table_columns(conn, "items") == V3_ITEMS
            and _table_columns(conn, "run_stops") == V2_RUN_STOPS
            and all(_index_matches(conn, name, spec)
                    for name, spec in V2_INDEXES.items()))


def _create_schema(conn) -> None:
    """DDL 在 SQLite 里是事务性的：中断只会留下空库，不会留下半套表。"""
    conn.execute("BEGIN IMMEDIATE")
    try:
        for statement in SCHEMA_STATEMENTS:
            conn.execute(statement)
        conn.execute("PRAGMA application_id=%d" % APPLICATION_ID)
        conn.execute("PRAGMA user_version=%d" % SCHEMA_VERSION)
        conn.commit()
    except BaseException:
        conn.rollback()
        raise


def _stamp_identity(conn) -> None:
    """schema 已可验证、只缺应用标识/版本：只补 header，不碰表。"""
    conn.execute("BEGIN IMMEDIATE")
    try:
        conn.execute("PRAGMA application_id=%d" % APPLICATION_ID)
        conn.execute("PRAGMA user_version=%d" % SCHEMA_VERSION)
        conn.commit()
    except BaseException:
        conn.rollback()
        raise


def _migrate_v1(conn) -> None:
    """v1 -> v3：补父级三态、停止历史与显式复核标记。"""
    conn.execute("BEGIN IMMEDIATE")
    try:
        conn.execute("ALTER TABLE items ADD COLUMN parent_known INTEGER"
                     " CHECK (parent_known IS NULL OR parent_known IN (0, 1))")
        conn.execute("UPDATE items SET parent_known = 1 WHERE kind = 'comment'")
        conn.execute("ALTER TABLE runs ADD COLUMN resumes INTEGER NOT NULL DEFAULT 0")
        conn.execute(RUN_STOPS_DDL)
        conn.execute("CREATE INDEX IF NOT EXISTS ix_run_stops_run ON run_stops(run_id)")
        # 旧库只留了最后一次停止状态：迁移时把它补成历史的第一条。
        conn.execute(
            "INSERT INTO run_stops(run_id, stop_reason, complete, at, note)"
            " SELECT run_id, stop_reason, complete, updated_at, note FROM runs"
            " WHERE stop_reason IS NOT NULL")
        _add_recheck_column(conn)
        _verify_v3(conn)
        conn.execute("PRAGMA application_id=%d" % APPLICATION_ID)
        conn.execute("PRAGMA user_version=%d" % SCHEMA_VERSION)
        conn.commit()
    except BaseException:
        conn.rollback()
        raise


def _migrate_v2(conn) -> None:
    """v2 -> v3：把自动 needs_recheck 与用户显式复核分开。"""
    conn.execute("BEGIN IMMEDIATE")
    try:
        _add_recheck_column(conn)
        _verify_v3(conn)
        conn.execute("PRAGMA application_id=%d" % APPLICATION_ID)
        conn.execute("PRAGMA user_version=%d" % SCHEMA_VERSION)
        conn.commit()
    except BaseException:
        conn.rollback()
        raise


def _add_recheck_column(conn) -> None:
    conn.execute("ALTER TABLE items ADD COLUMN recheck_explicit INTEGER NOT NULL"
                 " DEFAULT 0 CHECK (recheck_explicit IN (0, 1))")
    # 旧行没有"显式"概念：只有无法由身份/父级解释的 1 才视为显式复核。
    conn.execute(
        "UPDATE items SET recheck_explicit = CASE"
        " WHEN needs_recheck = 1 AND native_id IS NOT NULL"
        "  AND (kind <> 'comment' OR parent_known = 1) THEN 1 ELSE 0 END")
    conn.execute(
        "UPDATE items SET needs_recheck = CASE"
        " WHEN recheck_explicit = 1 OR native_id IS NULL"
        "  OR (kind = 'comment' AND parent_known = 0) THEN 1 ELSE 0 END")


def _verify_v3(conn) -> None:
    objects = frozenset(
        (row[0], row[1]) for row in conn.execute(
            "SELECT type, name FROM sqlite_master"
            " WHERE name NOT LIKE 'sqlite_%'"))
    if not _matches_v3(conn, objects):
        raise RuntimeError("migration_failed")


def _decode(row: dict) -> dict:
    """DB 行 -> 便于阅读/导出的 dict：JSON 列解码，0/1 还原为 bool。"""
    row["id_verified"] = bool(row["id_verified"])
    row["needs_recheck"] = bool(row["needs_recheck"])
    row["recheck_explicit"] = bool(row["recheck_explicit"])
    if row["text_truncated"] is not None:
        row["text_truncated"] = bool(row["text_truncated"])
    if row["parent_known"] is not None:
        row["parent_known"] = bool(row["parent_known"])
    evidence = row.pop("evidence_json", None)
    row["evidence"] = json.loads(evidence) if evidence else {}
    na = row.pop("not_applicable_json", None)
    row["not_applicable"] = tuple(json.loads(na)) if na else ()
    return row
