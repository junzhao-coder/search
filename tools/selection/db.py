"""Independent V9 selection SQLite store (no business/workbench DB access)."""

from __future__ import annotations

import json
import pathlib
import sqlite3
import uuid

from . import models

ROOT = pathlib.Path(__file__).resolve().parents[2]
DEFAULT_DB = ROOT / "tools" / "selection" / "runtime" / "selection.sqlite3"
ORIGIN_GUARD = {"count": 0, "last": None}

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS schema_migrations (
  version INTEGER PRIMARY KEY,
  name TEXT NOT NULL,
  applied_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS signals (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  platform TEXT NOT NULL,
  native_id TEXT NOT NULL,
  parent_native_id TEXT,
  url TEXT,
  title TEXT,
  quote TEXT NOT NULL,
  lang TEXT NOT NULL,
  lang_source TEXT NOT NULL CHECK (lang_source IN ('source','heuristic','unknown')),
  listed_price_minor INTEGER,
  effective_price_minor INTEGER,
  reference_price_minor INTEGER,
  wants INTEGER,
  collected_at TEXT NOT NULL,
  collected_at_scope TEXT NOT NULL CHECK (collected_at_scope IN ('row','batch','unknown')),
  origin_kind TEXT NOT NULL CHECK (origin_kind IN ('real','synthetic','imported')),
  last_origin_kind TEXT,
  raw_sha256 TEXT NOT NULL,
  content_hash TEXT NOT NULL,
  raw_ref TEXT NOT NULL,
  batch_id TEXT NOT NULL,
  version INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  UNIQUE (platform, native_id)
);
CREATE INDEX IF NOT EXISTS ix_signals_platform ON signals(platform);
CREATE INDEX IF NOT EXISTS ix_signals_origin ON signals(origin_kind);
CREATE INDEX IF NOT EXISTS ix_signals_batch ON signals(batch_id);
CREATE TABLE IF NOT EXISTS runs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  batch_id TEXT NOT NULL UNIQUE,
  kind TEXT NOT NULL,
  platform TEXT,
  status TEXT NOT NULL CHECK (status IN ('running','complete','partial','failed','stopped')),
  stop_reason TEXT,
  budget_json TEXT,
  stats_json TEXT,
  started_at TEXT NOT NULL,
  ended_at TEXT,
  raw_dir TEXT
);
CREATE TABLE IF NOT EXISTS categories (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  identity_key TEXT NOT NULL UNIQUE,
  audience TEXT NOT NULL,
  task TEXT NOT NULL,
  deliverable_family TEXT NOT NULL,
  locale TEXT NOT NULL,
  canonical_label TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('active','merged','excluded')),
  merged_into INTEGER REFERENCES categories(id),
  deliverable_carriers TEXT NOT NULL DEFAULT '[]',
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS category_alias (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  category_id INTEGER NOT NULL REFERENCES categories(id),
  alias_norm TEXT NOT NULL,
  created_at TEXT NOT NULL,
  source TEXT NOT NULL,
  UNIQUE (category_id, alias_norm)
);
CREATE TABLE IF NOT EXISTS discovery_event (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  category_id INTEGER REFERENCES categories(id),
  kind TEXT NOT NULL CHECK (kind IN ('new','update','merge','split','exclude','include','undo')),
  signal_id INTEGER REFERENCES signals(id),
  before_json TEXT,
  after_json TEXT,
  at TEXT NOT NULL,
  undo_of INTEGER REFERENCES discovery_event(id),
  origin_category_id INTEGER REFERENCES categories(id)
);
CREATE TABLE IF NOT EXISTS direction_card (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  category_id INTEGER NOT NULL UNIQUE REFERENCES categories(id),
  audience TEXT,
  task TEXT,
  deliverable TEXT,
  evidence_ids_json TEXT NOT NULL,
  gaps_json TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('draft','confirmed','rejected','merged')),
  merged_into INTEGER REFERENCES categories(id),
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS review_queue (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  signal_id INTEGER NOT NULL REFERENCES signals(id),
  reason TEXT NOT NULL,
  candidate_category_id INTEGER REFERENCES categories(id),
  status TEXT NOT NULL CHECK (status IN ('pending','accepted','rejected')),
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_categories_status ON categories(status);
CREATE INDEX IF NOT EXISTS ix_alias_norm ON category_alias(alias_norm);
CREATE INDEX IF NOT EXISTS ix_events_category ON discovery_event(category_id);
CREATE INDEX IF NOT EXISTS ix_events_signal ON discovery_event(signal_id);
CREATE INDEX IF NOT EXISTS ix_reviews_status ON review_queue(status);
CREATE TABLE IF NOT EXISTS signal_triage (
  signal_id INTEGER PRIMARY KEY REFERENCES signals(id),
  label TEXT NOT NULL CHECK (label IN ('demand','promo','noise')),
  demand_hits_json TEXT NOT NULL,
  promo_hits_json TEXT NOT NULL,
  rule_version TEXT NOT NULL,
  at TEXT NOT NULL,
  manual_override TEXT,
  native_id_source TEXT,
  note TEXT
);
CREATE TABLE IF NOT EXISTS rounds (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  kind TEXT NOT NULL,
  platform TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('draft','running','paused','partial','complete','failed','cancelled')),
  budget_json TEXT NOT NULL,
  cursor_json TEXT,
  idempotency_key TEXT NOT NULL UNIQUE,
  started_at TEXT NOT NULL,
  ended_at TEXT,
  error_count INTEGER NOT NULL DEFAULT 0,
  stats_json TEXT
);
CREATE TABLE IF NOT EXISTS round_item (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  round_id INTEGER NOT NULL REFERENCES rounds(id),
  item_key TEXT NOT NULL,
  state TEXT NOT NULL CHECK (state IN ('pending','processing','done','failed')),
  attempts INTEGER NOT NULL DEFAULT 0,
  last_error TEXT,
  updated_at TEXT NOT NULL,
  UNIQUE (round_id, item_key)
);
CREATE INDEX IF NOT EXISTS ix_round_items_round ON round_item(round_id, state);
"""


def connect(db_path: str | pathlib.Path) -> sqlite3.Connection:
    path = pathlib.Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), isolation_level=None, timeout=10.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=10000")
    return conn


def _migrate_v4(conn: sqlite3.Connection) -> None:
    """Add event origin + card merged fields; rebuild old card CHECK constraint."""
    cols = {r[1] for r in conn.execute("PRAGMA table_info(discovery_event)")}
    if "origin_category_id" not in cols:
        conn.execute("ALTER TABLE discovery_event ADD COLUMN origin_category_id INTEGER")
    sql_row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='direction_card'").fetchone()
    sql = (sql_row[0] or "") if sql_row else ""
    if "merged_into" not in sql or "'merged'" not in sql:
        conn.execute("ALTER TABLE direction_card RENAME TO direction_card_v3")
        conn.execute("""CREATE TABLE direction_card (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  category_id INTEGER NOT NULL UNIQUE REFERENCES categories(id),
  audience TEXT,
  task TEXT,
  deliverable TEXT,
  evidence_ids_json TEXT NOT NULL,
  gaps_json TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('draft','confirmed','rejected','merged')),
  merged_into INTEGER REFERENCES categories(id),
  created_at TEXT NOT NULL
)""")
        old_cols = {r[1] for r in conn.execute("PRAGMA table_info(direction_card_v3)")}
        carry = [c for c in ("id","category_id","audience","task","deliverable",
                             "evidence_ids_json","gaps_json","status","created_at") if c in old_cols]
        conn.execute(f"INSERT INTO direction_card({','.join(carry)}) SELECT {','.join(carry)} FROM direction_card_v3")
        conn.execute("DROP TABLE direction_card_v3")
    conn.commit()


def _identity(fields: dict) -> str:
    payload = {k: str(fields.get(k) or "unknown") for k in
               ("audience", "task", "deliverable_family", "locale")}
    return models.canonical_json(payload)


def _key(fields: dict) -> str:
    import hashlib
    return hashlib.sha256(_identity(fields).encode("utf-8")).hexdigest()


def _migrate_v5(conn: sqlite3.Connection) -> None:
    """Coarse deliverable family in identity keys; preserve events/aliases/cards."""
    cols = {r[1] for r in conn.execute("PRAGMA table_info(categories)")}
    if "deliverable_carriers" not in cols:
        conn.execute("ALTER TABLE categories ADD COLUMN deliverable_carriers TEXT NOT NULL DEFAULT '[]'")
    rows = [dict(r) for r in conn.execute("SELECT * FROM categories ORDER BY id")]
    for row in rows:
        fine = row.get("deliverable_family") or "unknown"
        coarse = models.FAMILY_NORM.get(fine, fine)
        fields = {"audience": row["audience"], "task": row["task"],
                  "deliverable_family": coarse, "locale": row["locale"]}
        new_key = _key(fields)
        try:
            carriers = json.loads(row.get("deliverable_carriers") or "[]")
        except Exception:
            carriers = []
        if fine not in carriers:
            carriers.append(fine)
        if row["identity_key"] == new_key:
            conn.execute("UPDATE categories SET deliverable_family=?,deliverable_carriers=? WHERE id=?",
                         (coarse, json.dumps(carriers, ensure_ascii=False), row["id"]))
            continue
        target = conn.execute("SELECT * FROM categories WHERE identity_key=? AND id<>?",
                              (new_key, row["id"])).fetchone()
        if target:
            # merge this legacy key into the existing coarse-key category
            conn.execute("UPDATE discovery_event SET category_id=? WHERE category_id=?",
                         (target["id"], row["id"]))
            conn.execute("UPDATE category_alias SET category_id=? WHERE category_id=?",
                         (target["id"], row["id"]))
            conn.execute("UPDATE direction_card SET category_id=? WHERE category_id=?",
                         (target["id"], row["id"]))
            conn.execute("UPDATE categories SET status='merged',merged_into=?,identity_key=?,deliverable_carriers=? WHERE id=?",
                         (target["id"], row["identity_key"] + f"#legacy{row['id']}",
                          json.dumps(carriers, ensure_ascii=False), row["id"]))
            try:
                tc = json.loads(target["deliverable_carriers"] or "[]")
            except Exception:
                tc = []
            for c in carriers:
                if c not in tc:
                    tc.append(c)
            conn.execute("UPDATE categories SET deliverable_carriers=? WHERE id=?",
                         (json.dumps(tc, ensure_ascii=False), target["id"]))
        else:
            conn.execute("UPDATE categories SET identity_key=?,deliverable_family=?,deliverable_carriers=? WHERE id=?",
                         (new_key, coarse, json.dumps(carriers, ensure_ascii=False), row["id"]))
    conn.commit()


def _migrate_v6(conn: sqlite3.Connection) -> None:
    cols = {r[1] for r in conn.execute("PRAGMA table_info(signals)")}
    if "last_origin_kind" not in cols:
        conn.execute("ALTER TABLE signals ADD COLUMN last_origin_kind TEXT")
    conn.commit()


def _migrate_v8(conn: sqlite3.Connection) -> None:
    cols = {r[1] for r in conn.execute("PRAGMA table_info(signal_triage)")}
    for col in ("manual_override", "native_id_source", "note"):
        if cols and col not in cols:
            conn.execute(f"ALTER TABLE signal_triage ADD COLUMN {col} TEXT")
    conn.commit()


def init_db(db_path: str | pathlib.Path) -> sqlite3.Connection:
    conn = connect(db_path)
    conn.executescript(SCHEMA_SQL)
    _migrate_v4(conn)
    _migrate_v5(conn)
    _migrate_v6(conn)
    _migrate_v8(conn)
    for version, name in ((1, "v9_selection_signals_runs"),
                          (2, "v9_categories_cards_reviews"),
                          (3, "v9_rounds_round_items"),
                          (4, "v9_merge_cards_undo"),
                          (5, "v9_family_carriers"),
                          (6, "v9_origin_first_seen"),
                          (7, "v9_signal_triage"),
                          (8, "v9_manual_triage")):
        conn.execute(
            "INSERT OR IGNORE INTO schema_migrations(version,name,applied_at) VALUES (?,?,?)",
            (version, name, models.utc_now()),
        )
    conn.commit()
    return conn


def _row(conn: sqlite3.Connection, platform: str, native_id: str):
    return conn.execute(
        "SELECT * FROM signals WHERE platform=? AND native_id=?", (platform, str(native_id))
    ).fetchone()


def upsert_signal(conn: sqlite3.Connection, signal: dict) -> tuple[str, int]:
    """Return ('new'|'updated'|'duplicate', signal id); identity=(platform,native_id)."""
    for key in models.SIGNAL_COLUMNS:
        if key not in signal:
            raise ValueError(f"missing signal field: {key}")
    existing = _row(conn, signal["platform"], signal["native_id"])
    now = models.utc_now()
    if existing is None:
        cur = conn.execute(
            "INSERT INTO signals(" + ",".join(models.SIGNAL_COLUMNS) +
            ",version,created_at,updated_at) VALUES (" +
            ",".join("?" for _ in models.SIGNAL_COLUMNS) + ",1,?,?)",
            [signal[k] for k in models.SIGNAL_COLUMNS] + [now, now],
        )
        conn.commit()
        return "new", int(cur.lastrowid)
    if existing["content_hash"] == signal["content_hash"]:
        if existing["origin_kind"] == "imported" and signal["origin_kind"] == "real":
            ORIGIN_GUARD["count"] += 1
            ORIGIN_GUARD["last"] = {
                "platform": signal["platform"], "native_id": signal["native_id"],
                "kept_origin": "imported", "incoming_origin": "real",
                "reason": "origin_upgrade_skipped", "at": now,
            }
        return "duplicate", int(existing["id"])
    keep_first_seen = (existing["origin_kind"] == "imported"
                       and signal["origin_kind"] == "real")
    stored_origin = "imported" if keep_first_seen else signal["origin_kind"]
    last_origin = signal["origin_kind"] if keep_first_seen else existing["last_origin_kind"] \
        if "last_origin_kind" in existing.keys() else None
    if keep_first_seen:
        ORIGIN_GUARD["count"] += 1
        ORIGIN_GUARD["last"] = {
            "platform": signal["platform"], "native_id": signal["native_id"],
            "kept_origin": "imported", "incoming_origin": "real",
            "reason": "origin_upgrade_on_change_kept_first_seen", "at": now,
        }
    conn.execute(
        "UPDATE signals SET parent_native_id=?,url=?,title=?,quote=?,lang=?,lang_source=?,"
        "listed_price_minor=?,effective_price_minor=?,reference_price_minor=?,wants=?,"
        "collected_at=?,collected_at_scope=?,origin_kind=?,last_origin_kind=?,raw_sha256=?,content_hash=?,raw_ref=?,batch_id=?,"
        "version=version+1,updated_at=? WHERE id=?",
        [signal[k] for k in ("parent_native_id", "url", "title", "quote", "lang", "lang_source",
                             "listed_price_minor", "effective_price_minor", "reference_price_minor",
                             "wants", "collected_at", "collected_at_scope")] +
        [stored_origin, last_origin, signal["raw_sha256"], signal["content_hash"],
         signal["raw_ref"], signal["batch_id"], now, existing["id"]],
    )
    conn.commit()
    return "updated", int(existing["id"])


def start_run(conn: sqlite3.Connection, *, kind: str, platform: str | None, budget: dict,
              raw_dir: str | pathlib.Path | None) -> tuple[int, str]:
    batch_id = f"{kind}-{models.utc_now().replace('-', '').replace(':', '')}-{uuid.uuid4().hex[:6]}"
    cur = conn.execute(
        "INSERT INTO runs(batch_id,kind,platform,status,budget_json,started_at,raw_dir) "
        "VALUES (?,?,?,?,?,?,?)",
        (batch_id, kind, platform, "running", json.dumps(budget, ensure_ascii=False),
         models.utc_now(), str(raw_dir) if raw_dir else None),
    )
    conn.commit()
    return int(cur.lastrowid), batch_id


def finish_run(conn: sqlite3.Connection, run_id: int, *, status: str, stop_reason: str | None,
               stats: dict) -> None:
    if status not in models.RUN_STATUSES:
        raise ValueError(f"invalid run status: {status}")
    conn.execute(
        "UPDATE runs SET status=?,stop_reason=?,stats_json=?,ended_at=? WHERE id=?",
        (status, stop_reason, json.dumps(stats, ensure_ascii=False), models.utc_now(), run_id),
    )
    conn.commit()


def stats(conn: sqlite3.Connection) -> dict:
    total = conn.execute("SELECT COUNT(*) AS n FROM signals").fetchone()["n"]
    by_platform = {r["platform"]: r["n"] for r in conn.execute(
        "SELECT platform,COUNT(*) AS n FROM signals GROUP BY platform ORDER BY platform")}
    by_origin = {r["origin_kind"]: r["n"] for r in conn.execute(
        "SELECT origin_kind,COUNT(*) AS n FROM signals GROUP BY origin_kind ORDER BY origin_kind")}
    runs = [dict(r) for r in conn.execute(
        "SELECT batch_id,kind,platform,status,stop_reason,started_at,ended_at,stats_json "
        "FROM runs ORDER BY id DESC LIMIT 20")]
    return {"signals": total, "by_platform": by_platform, "by_origin": by_origin, "runs": runs}
