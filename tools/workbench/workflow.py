"""商品工作单（B1）：独立 SQLite 持久化 + 服务端校验 + 待核验缺项。

设计要点
- 库与密钥都放在 `tools/workbench/runtime/`（可用环境变量覆盖，便于测试用临时库）；
  **绝不打开/写 `instance/app.db`**，也不 import 原业务 app 工厂。
- 初始四门槛 `demand/supply_distribution/cost/platform_policy` 一律 `unverified`，
  `selected_supply_id` 为 NULL，状态为 `pending_supply`（待补/待货源）。
- 只接受规格字段白名单；客户端伪造 `status=ready/verified`、门槛、选定货源、快照
  一律拒绝并保持原记录。
- 幂等：`submit_key` 唯一；同键同内容返回原单，同键不同内容 409 冲突。
- 版本：`revision` 乐观锁；不匹配 409，不改原记录。
"""

from __future__ import annotations

import hashlib
import json
import os
import pathlib
import re
import sqlite3
import time
import uuid

import csv

WORKBENCH_DIR = pathlib.Path(__file__).resolve().parent
ROOT = WORKBENCH_DIR.parents[1]
RUNTIME = WORKBENCH_DIR / "runtime"

SCORES = ROOT / "docs" / "validation" / "money-project" / "scoring" / "scores.csv"
TOP10 = ROOT / "docs" / "validation" / "money-project" / "sourcing" / "opportunity_sourcing_top10.csv"

DB_PATH = pathlib.Path(os.environ.get("WORKBENCH_WORKFLOW_DB") or (RUNTIME / "workflow.sqlite3"))
SECRET_PATH = pathlib.Path(os.environ.get("WORKBENCH_SECRET_FILE") or (RUNTIME / "secret_key"))

EDITABLE_FIELDS = ("name", "use_case", "target_buyer", "deliverable", "fmt", "language", "version",
                   "includes", "excludes", "target_platform", "status")
FIELD_LIMITS = {"name": 80, "use_case": 120, "target_buyer": 80, "deliverable": 120, "fmt": 40,
                "language": 20, "version": 20, "includes": 600, "excludes": 600, "target_platform": 20,
                "status": 32}
REQUIRED_FIELDS = ("name", "use_case", "deliverable", "target_platform")
ALLOWED_PLATFORMS = {"xianyu"}
ALLOWED_STATUS = {"pending_supply", "in_review"}
STATUS_LABEL = {"pending_supply": "待补/待货源", "in_review": "核验中（人工）"}
GATES = ("demand", "supply_distribution", "cost", "platform_policy")
# 客户端一旦提交这些字段（非空）即视为越级/伪造
FORBIDDEN_FIELDS = ("gates", "gate_demand", "gate_supply_distribution", "gate_cost", "gate_platform_policy",
                    "selected_supply_id", "snapshot", "source_snapshot", "ready", "verified", "is_ready",
                    "workorder_id", "revision", "submit_key")
STAGES = (("select", "选产品"), ("supply", "查找货源"), ("inspect", "验货"),
          ("copy", "文案与素材"), ("review", "人工复核"), ("listing", "上架包"))


class Reject(Exception):
    """业务拒绝（4xx）：带有稳定 code 与中文说明。"""

    def __init__(self, code: str, message: str, status: int = 400):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status


def db_path() -> pathlib.Path:
    return pathlib.Path(os.environ.get("WORKBENCH_WORKFLOW_DB") or (RUNTIME / "workflow.sqlite3"))


def secret_key() -> bytes:
    """持久化密钥（重启不丢），文件不进版本库、不在日志/HTML 打印。"""
    path = pathlib.Path(os.environ.get("WORKBENCH_SECRET_FILE") or (RUNTIME / "secret_key"))
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        return path.read_bytes()
    value = uuid.uuid4().hex.encode()
    path.write_bytes(value)
    try:
        path.chmod(0o600)
    except OSError:
        pass
    return value


def connect() -> sqlite3.Connection:
    path = db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def connect_ro() -> sqlite3.Connection | None:
    """只读连接：库不存在时返回 None，**不创建文件**（GET 零写）。"""
    path = db_path()
    if not path.exists():
        return None
    try:
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        return conn
    except sqlite3.Error:
        return None


def init_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS workorder (
          workorder_id TEXT PRIMARY KEY,
          submit_key TEXT UNIQUE NOT NULL,
          payload_hash TEXT NOT NULL,
          source_group TEXT NOT NULL,
          source_item_id TEXT NOT NULL,
          source_url TEXT,
          source_platform TEXT,
          snapshot_json TEXT NOT NULL,
          name TEXT NOT NULL,
          use_case TEXT NOT NULL,
          target_buyer TEXT,
          deliverable TEXT NOT NULL,
          fmt TEXT,
          language TEXT,
          version TEXT,
          includes TEXT,
          excludes TEXT,
          target_platform TEXT NOT NULL,
          status TEXT NOT NULL,
          gate_demand TEXT NOT NULL DEFAULT 'unverified',
          gate_supply_distribution TEXT NOT NULL DEFAULT 'unverified',
          gate_cost TEXT NOT NULL DEFAULT 'unverified',
          gate_platform_policy TEXT NOT NULL DEFAULT 'unverified',
          selected_supply_id TEXT,
          revision INTEGER NOT NULL DEFAULT 1,
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS workorder_event (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          workorder_id TEXT NOT NULL,
          action TEXT NOT NULL,
          detail TEXT,
          at TEXT NOT NULL
        );
        """
    )
    _ensure_columns(conn)
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS workorder_export (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          workorder_id TEXT NOT NULL,
          format TEXT NOT NULL,
          revision INTEGER NOT NULL,
          copy_version TEXT,
          supply_id TEXT,
          supply_version TEXT,
          stamp_hash TEXT NOT NULL,
          content_sha256 TEXT NOT NULL,
          created_utc TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS workorder_copy_version (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          workorder_id TEXT NOT NULL,
          version_no INTEGER NOT NULL,
          snapshot_json TEXT NOT NULL,
          content_hash TEXT NOT NULL,
          created_at TEXT NOT NULL,
          created_by TEXT NOT NULL,
          UNIQUE (workorder_id, version_no)
        );
        CREATE TABLE IF NOT EXISTS workorder_publish (
          workorder_id TEXT PRIMARY KEY,
          status TEXT NOT NULL,
          published_url TEXT,
          published_at TEXT,
          platform_note TEXT,
          sold_count INTEGER NOT NULL DEFAULT 0,
          publish_version INTEGER NOT NULL DEFAULT 0,
          updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS workorder_supply_candidate (
          id TEXT PRIMARY KEY,
          workorder_id TEXT NOT NULL,
          provider TEXT NOT NULL,
          source_url TEXT,
          kind TEXT NOT NULL DEFAULT '替代',
          commercial TEXT NOT NULL DEFAULT 'unknown',
          redistribute TEXT NOT NULL DEFAULT 'unknown',
          resale TEXT NOT NULL DEFAULT 'unknown',
          license_note TEXT,
          price_minor INTEGER,
          currency TEXT DEFAULT 'CNY',
          sample_status TEXT,
          note TEXT,
          conclusion TEXT,
          is_active INTEGER NOT NULL DEFAULT 1,
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL
        );
        """
    )
    _ensure_columns(conn)
    _ensure_export_columns(conn)
    conn.commit()


def _ensure_export_columns(conn: sqlite3.Connection) -> None:
    """workorder_export 增量列（IF NOT EXISTS 语义）+ dedupe_key 唯一约束。"""
    existing = {row[1] for row in conn.execute("PRAGMA table_info(workorder_export)").fetchall()}
    if "dedupe_key" not in existing:
        conn.execute('ALTER TABLE workorder_export ADD COLUMN "dedupe_key" TEXT')
    if "publish_version" not in existing:
        conn.execute('ALTER TABLE workorder_export ADD COLUMN "publish_version" INTEGER')
    pub_cols = {row[1] for row in conn.execute("PRAGMA table_info(workorder_publish)").fetchall()}
    if "publish_version" not in pub_cols:
        conn.execute('ALTER TABLE workorder_publish ADD COLUMN "publish_version" INTEGER NOT NULL DEFAULT 0')
    _ensure_export_unique(conn)


def _ensure_export_unique(conn: sqlite3.Connection) -> None:
    """dedupe_key 唯一索引：先回填旧行、处理历史重复（保留最新，其余置 NULL），再建唯一索引。

    SQLite 唯一索引允许多个 NULL，因此旧行被置 NULL 后不会互相冲突，也不会被去重查询命中。
    """
    # 1) 回填 dedupe_key（仅限为空的行）
    rows = conn.execute("""SELECT id, revision, copy_version, supply_id, supply_version FROM workorder_export
                           WHERE dedupe_key IS NULL""").fetchall()
    for row in rows:
        key = f'{row["revision"] or 0}|{row["copy_version"] or ""}|{row["supply_id"] or ""}|{row["supply_version"] or ""}'
        conn.execute("UPDATE workorder_export SET dedupe_key=? WHERE id=?", (key, row["id"]))
    # 2) 历史重复：保留最大 id，其余置 NULL（保留行本身，不删数据）
    dups = conn.execute("""SELECT workorder_id, dedupe_key, MAX(id) AS keep_id, COUNT(*) AS n
                           FROM workorder_export WHERE dedupe_key IS NOT NULL
                           GROUP BY workorder_id, dedupe_key HAVING n > 1""").fetchall()
    for dup in dups:
        conn.execute("""UPDATE workorder_export SET dedupe_key=NULL
                        WHERE workorder_id=? AND dedupe_key=? AND id<>?""",
                     (dup["workorder_id"], dup["dedupe_key"], dup["keep_id"]))
    # 3) 唯一索引（IF NOT EXISTS，可重复执行）
    conn.execute("DROP INDEX IF EXISTS idx_export_dedupe")          # 旧的非唯一索引
    conn.execute("""CREATE UNIQUE INDEX IF NOT EXISTS idx_export_dedupe_unique
                    ON workorder_export (workorder_id, dedupe_key)""")
    conn.commit()


# B3 追加字段（只 ALTER，不动既有数据）
B3_COLUMNS = (
    ("supply_license_commercial", "TEXT"), ("supply_license_redistribute", "TEXT"),
    ("supply_license_resell", "TEXT"), ("supply_version", "TEXT"),
    ("sample_status", "TEXT"), ("sample_ref", "TEXT"),
    ("cost_minor", "INTEGER"), ("cost_known", "TEXT"),
    ("platform_evidence", "TEXT"), ("copy_status", "TEXT"), ("copy_version", "TEXT"),
    ("selling_points", "TEXT"), ("price_minor", "INTEGER"),
    ("delivery_note", "TEXT"), ("aftersales_note", "TEXT"), ("faq_json", "TEXT"),
    ("supply_note", "TEXT"),
)


def _ensure_columns(conn: sqlite3.Connection) -> None:
    existing = {row[1] for row in conn.execute("PRAGMA table_info(workorder)").fetchall()}
    for name, sql_type in B3_COLUMNS:
        if name not in existing:
            conn.execute(f'ALTER TABLE workorder ADD COLUMN "{name}" {sql_type}')


# ---------------------------------------------------------------- 只读来源
def _read_csv(path: pathlib.Path) -> list[dict]:
    with path.open(encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def load_sources() -> tuple[dict[str, dict], set[str]]:
    """读取来源清单；测试可用 `WORKBENCH_SOURCE_FIXTURE=<scores.csv>,<top10.csv>` 指向临时合成数据。"""
    fixture = os.environ.get("WORKBENCH_SOURCE_FIXTURE")
    if fixture:
        parts = [p.strip() for p in fixture.split(",") if p.strip()]
        if len(parts) != 2:
            raise RuntimeError("WORKBENCH_SOURCE_FIXTURE 需要 <scores.csv>,<top10.csv> 两个路径")
        scores_path, top10_path = pathlib.Path(parts[0]), pathlib.Path(parts[1])
    else:
        scores_path, top10_path = SCORES, TOP10
    rows = {str(r.get("item_id")): r for r in _read_csv(scores_path)}
    refs = {str(r.get("opportunity_id")) for r in _read_csv(top10_path)
            if str(r.get("reference_max") or "").strip()}
    return rows, refs


def _num(value):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number == number and abs(number) != float("inf") else None


def classify_group(row: dict) -> tuple[str, str]:
    """返回 (kind, category)；kind ∈ {商品, 内容, 未归类}。"""
    from taxonomy import classify
    from textindex import build_text_index
    entry = (build_text_index().get(str(row.get("item_id"))) or {})
    tax = classify(row, entry.get("text"), entry.get("source") or "")
    return tax["kind"], tax["category"]


def validate_source(group: str, item_id: str) -> tuple[dict, str, str]:
    """校验来源必须是“已归类商品型且非待人工”，且 group 与之一致。"""
    from taxonomy import FALLBACK_NAME
    rows, _refs = load_sources()
    row = rows.get(item_id or "")
    if row is None:
        raise Reject("source_not_found", "来源条目不存在：请从机会页“选为候选商品”进入")
    kind, category = classify_group(row)
    if kind != "商品":
        raise Reject("source_not_product", f"该条目不是已归类商品型（当前：{category}），"
                                           "教程/内容与未归类条目不能创建商品工作单")
    if category in ("Notion 其它（待人工）", FALLBACK_NAME):
        raise Reject("source_unclassified", f"该条目未归类到具体商品类型（{category}），"
                                            "请先人工确认品类后再建立工作单")
    if group and group != category:
        raise Reject("source_group_mismatch", f"来源分组不匹配（提交 {group} / 实际 {category}）")
    return row, kind, category


def snapshot_of(row: dict, category: str) -> dict:
    keys = ("item_id", "platform", "title", "url", "author", "published_at", "total_score",
            "demand_raw", "demand_norm", "sellability_norm", "sellability_reason",
            "margin_low", "margin_high", "margin_mid", "margin_assumption",
            "cost_input", "cost_note", "missing_metrics", "source", "raw_ref", "rank")
    snap = {k: row.get(k) for k in keys}
    snap["category"] = category
    return snap


def derive_gaps(snapshot: dict, refs: set[str]) -> list[str]:
    """待核验缺项（只由快照字段推导，不臆造）。"""
    gaps: list[str] = ["四门槛均未核验：demand / supply_distribution / cost / platform_policy", "未选定货源（selected_supply_id 为空）"]
    if str(snapshot.get("item_id")) not in refs:
        gaps.append("无可比参考价（未出现在机会-货源联动表）")
    sell = _num(snapshot.get("sellability_norm"))
    if sell is None:
        gaps.append("可售性未评估（缺少 sellability_norm）")
    elif sell < 0.8:
        gaps.append(f"可售性 {round(sell * 100)} 未达 80（需人工确认是否有明确售价与购买入口）")
    assumption = str(snapshot.get("margin_assumption") or "").lower()
    if any(k in assumption for k in ("all 20", "fallback", "basket proxy", "全量回退")):
        gaps.append("毛利为品类回退价，非该商品自身成交价")
    if str(snapshot.get("cost_input") or "").strip().lower() in ("", "missing"):
        gaps.append("无公开成本输入，毛利为假设区间")
    if str(snapshot.get("missing_metrics") or "").strip():
        gaps.append(f"缺失指标：{snapshot.get('missing_metrics')}")
    gaps.extend(["未验货（B2 待实现）", "未准备文案与素材（B3 待实现）",
                 "未人工复核（B4 待实现）", "未生成上架包（B5 待实现）"])
    return gaps


def stages_state(record: dict) -> list[dict]:
    done = {"select": True}
    return [{"key": key, "label": label,
             "state": "done" if done.get(key) else "pending",
             "note": "已完成（规格已保存）" if done.get(key) else "待后续实现"}
            for key, label in STAGES]


# ---------------------------------------------------------------- 校验与写
def _as_text(value) -> str:
    return "" if value is None else str(value).strip()


def normalize_fields(payload: dict) -> dict:
    """只允许规格字段；出现越级/伪造字段直接拒绝。"""
    rejected = [k for k in FORBIDDEN_FIELDS if k in payload and _as_text(payload.get(k)) != ""]
    if rejected:
        raise Reject("forbidden_field",
                     f"不允许提交以下字段：{', '.join(sorted(rejected))}"
                     "（门槛/选定货源/快照/就绪状态只能由服务端与后续阶段设置）", 403)
    unknown = [k for k in payload if k not in EDITABLE_FIELDS]
    if unknown:
        raise Reject("unknown_field", f"未知字段：{', '.join(sorted(unknown))}")

    data = {k: _as_text(payload.get(k)) for k in EDITABLE_FIELDS if k in payload}
    for key, limit in FIELD_LIMITS.items():
        if key in data and len(data[key]) > limit:
            raise Reject("field_too_long", f"{key} 超过 {limit} 字（当前 {len(data[key])}）")
    for key in REQUIRED_FIELDS:
        if not data.get(key):
            raise Reject("field_required", f"{key} 为必填")
    if "target_platform" in data and data["target_platform"] not in ALLOWED_PLATFORMS:
        raise Reject("platform_invalid", "目标平台只能是 xianyu（本批仅支持闲鱼）")
    if "status" in data and data["status"] not in ALLOWED_STATUS:
        raise Reject("status_forbidden",
                     f"状态只能是 {sorted(ALLOWED_STATUS)}；ready/verified 属于后续阶段，本批不接受", 403)
    return data


def _payload_hash(group: str, item_id: str, data: dict) -> str:
    blob = json.dumps({"group": group, "item_id": item_id, "data": data}, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(blob.encode()).hexdigest()


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def row_to_record(row: sqlite3.Row) -> dict:
    record = dict(row)
    record["snapshot"] = json.loads(record["snapshot_json"])
    record["status_label"] = STATUS_LABEL.get(record["status"], record["status"])
    return record


def get(conn: sqlite3.Connection, workorder_id: str) -> dict | None:
    if not db_path().exists():
        return None
    try:
        cur = conn.execute("SELECT * FROM workorder WHERE workorder_id = ?", (workorder_id,))
    except sqlite3.OperationalError:
        return None
    row = cur.fetchone()
    return row_to_record(row) if row else None


def list_all(conn: sqlite3.Connection) -> list[dict]:
    """只读列表：库或表不存在时返回空，不建表（GET 零写）。"""
    if not db_path().exists():
        return []
    try:
        rows = conn.execute("SELECT * FROM workorder ORDER BY created_at DESC").fetchall()
    except sqlite3.OperationalError:
        return []
    return [row_to_record(r) for r in rows]


def create(conn: sqlite3.Connection, *, group: str = "", item_id: str = "", payload: dict,
           submit_key: str, self_made: bool = False) -> tuple[dict, bool]:
    """返回 (record, created)。幂等：同键同内容→原单；同键不同内容→409。

    `self_made=True` 时跳过采集目录校验（自制商品），`item_id` 必须以 `self:` 开头，
    snapshot 记为 {"self_made": true, "note": "自制商品，无采集来源"}。
    """
    init_schema(conn)
    submit_key = _as_text(submit_key)
    if not submit_key or len(submit_key) > 80:
        raise Reject("submit_key_invalid", "缺少提交键（防止双击重复建单）")
    data = normalize_fields(payload)

    if self_made:
        raw_item = _as_text(item_id)
        if raw_item and not raw_item.startswith("self:"):
            raise Reject("source_invalid", "自制商品的来源标识必须以 self: 开头")
        slug = re.sub(r"[^0-9a-zA-Z\u4e00-\u9fff]+", "-", data["name"]).strip("-")[:40] or "item"
        item_id = raw_item or f"self:{slug}"
        category = "自制商品"
        row = {"url": f"self://{item_id}", "platform": "self", "title": data["name"]}
        snapshot = {"self_made": True, "note": "自制商品，无采集来源", "item_id": item_id,
                    "title": data["name"], "category": category}
    else:
        row, _kind, category = validate_source(group, item_id)
        snapshot = snapshot_of(row, category)
    payload_hash = _payload_hash(category, item_id, data)

    existing = conn.execute("SELECT * FROM workorder WHERE submit_key = ?", (submit_key,)).fetchone()
    if existing:
        if existing["payload_hash"] == payload_hash:
            return row_to_record(existing), False
        raise Reject("idempotency_conflict", "相同提交键但内容不同，已拒绝以避免覆盖原工作单", 409)

    now = _now()
    workorder_id = f"wo:{time.strftime('%Y%m%d', time.gmtime())}-{uuid.uuid4().hex[:8]}"
    if not re.fullmatch(r"wo:\d{8}-[0-9a-f]{8}", workorder_id):   # 单号格式自检
        raise Reject("workorder_id_invalid", "内部错误：生成的单号不符合 wo:yyyymmdd-8hex", 500)
    try:
        conn.execute(
            """INSERT INTO workorder (workorder_id, submit_key, payload_hash, source_group, source_item_id,
                 source_url, source_platform, snapshot_json, name, use_case, target_buyer, deliverable, fmt,
                 language, version, includes, excludes, target_platform, status, selected_supply_id,
                 revision, created_at, updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,NULL,1,?,?)""",
            (workorder_id, submit_key, payload_hash, category, item_id, row.get("url"), row.get("platform"),
             json.dumps(snapshot, ensure_ascii=False), data["name"], data["use_case"], data.get("target_buyer", ""),
             data["deliverable"], data.get("fmt", ""), data.get("language", ""), data.get("version", ""),
             data.get("includes", ""), data.get("excludes", ""), data["target_platform"],
             data.get("status", "pending_supply"), now, now))
        conn.execute("INSERT INTO workorder_event (workorder_id, action, detail, at) VALUES (?,?,?,?)",
                     (workorder_id, "create", f"category={category} self_made={self_made}", now))
        conn.commit()
    except sqlite3.IntegrityError:
        conn.rollback()
        raise Reject("idempotency_conflict", "提交键冲突（并发重复提交），已拒绝", 409)
    record = get(conn, workorder_id)
    assert record is not None
    return record, True


def update(conn: sqlite3.Connection, workorder_id: str, *, revision, payload: dict) -> dict:
    """原子更新：UPDATE 必须恰好命中 1 行；0 行则回滚并 409，且不追加成功审计。"""
    init_schema(conn)
    raw_revision = str(revision).strip() if revision is not None else ""
    if not re.fullmatch(r"[0-9]+", raw_revision or ""):
        raise Reject("revision_invalid", f"revision 必须是 ASCII 正整数（收到 {revision!r}）")
    revision_int = int(raw_revision)
    if revision_int < 1:
        raise Reject("revision_invalid", f"revision 必须 ≥ 1（收到 {revision_int}）")
    record = get(conn, workorder_id)
    if record is None:
        raise Reject("not_found", "工作单不存在", 404)
    if revision_int != int(record["revision"]):
        raise Reject("revision_conflict",
                     f"版本冲突：当前 revision={record['revision']}，提交 {revision_int}；请刷新后重试", 409)
    data = normalize_fields({**{k: record[k] for k in ("name", "use_case", "target_buyer", "deliverable",
                                                        "fmt", "language", "version", "includes", "excludes",
                                                        "target_platform", "status")}, **payload})
    now = _now()
    try:
        conn.execute("BEGIN IMMEDIATE")
        cur = conn.execute(
            """UPDATE workorder SET name=?, use_case=?, target_buyer=?, deliverable=?, fmt=?, language=?, version=?,
                 includes=?, excludes=?, target_platform=?, status=?, revision=revision+1, updated_at=?
               WHERE workorder_id=? AND revision=?""",
            (data["name"], data["use_case"], data.get("target_buyer", ""), data["deliverable"], data.get("fmt", ""),
             data.get("language", ""), data.get("version", ""), data.get("includes", ""), data.get("excludes", ""),
             data["target_platform"], data.get("status", record["status"]), now, workorder_id, revision_int))
        if cur.rowcount != 1:
            conn.rollback()
            raise Reject("revision_conflict",
                         "版本冲突：提交后记录已被其它请求修改（UPDATE 命中 0 行），本次未写入", 409)
        conn.execute("INSERT INTO workorder_event (workorder_id, action, detail, at) VALUES (?,?,?,?)",
                     (workorder_id, "update", f"revision {revision_int} -> {revision_int + 1}", now))
        conn.commit()
    except Reject:
        raise
    except sqlite3.Error as exc:
        conn.rollback()
        raise Reject("update_failed", f"更新失败已回滚：{type(exc).__name__}", 409)
    updated = get(conn, workorder_id)
    assert updated is not None
    return updated


def counts(conn: sqlite3.Connection) -> dict:
    return {"workorders": len(list_all(conn))}
