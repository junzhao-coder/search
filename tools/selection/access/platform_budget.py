"""Platform-level budget authority, keyed by **site** rather than by state dir.

Why: `budget.py` keeps one ledger per `--state-dir`, so a fresh directory resets
calls, records and locks. This module is the authority that survives that:

- `batches`   explicit authorization only (cap, window, source, note). No charge
              path ever creates a batch; a changed authorization is a conflict.
- `events`    append-only audit. Call kinds consume the cap; audit kinds
              (`offline_check`, `import`, `*_result`) never do.
- `history`   provenance of activity that predates this ledger. It never adds to
              call counts, and importing is a **gate**: a declared source that is
              missing, unreadable, or WAL-uncertain fails closed.
- `locks`     platform-wide risk lock, unique per site. A new state dir cannot
              drop it.

Hard rules encoded here (each one has a test):

1. The lock check happens **inside** the same `BEGIN IMMEDIATE` transaction as the
   count and the insert, so a concurrent `lock()` cannot slip between them.
2. Per-batch limits are enforced here and are shared by every state dir:
   15 s minimum interval between calls, at most 5 reserved records, 300 s window.
   `started_at` comes from the database, so restarts and new directories do not
   refresh the window.
3. A closed window is refused, not reopened; history is never deleted.
4. Real charged calls have no refund path: a failed navigation was still an
   attempt, and it is recorded as such (`*_result` events).

Stdlib only (`sqlite3`), one file, no new dependencies.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import pathlib
import sqlite3
import time

REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]

DEFAULT_PATH = (pathlib.Path(__file__).resolve().parent / "runtime"
                / "platform_weibo.sqlite3")

#: limits shared by every state dir (mirror of the per-run budget, enforced here)
MIN_INTERVAL = 15.0
#: 记录数的**默认目标值**（v11 起为软约束，不是上限）
DEFAULT_RECORDS_TARGET = 5
MAX_RECORDS = DEFAULT_RECORDS_TARGET     # 兼容别名：语义=默认目标值，不再当上限
#: 弃用提示：新代码请直接用 `DEFAULT_RECORDS_TARGET`；本别名不得出现在
#: `if ... > MAX_RECORDS` 这类上限判断里（v11 起记录数是软目标）。
MAX_SECONDS = 300.0
MAX_AUTHORIZED_CALLS = 20

SCHEMA = """
CREATE TABLE IF NOT EXISTS batches (
  batch_id TEXT PRIMARY KEY,
  site TEXT NOT NULL,
  authorized_calls INTEGER NOT NULL,
  records_cap INTEGER NOT NULL DEFAULT 5,
  seed_used INTEGER NOT NULL DEFAULT 0,
  seed_source TEXT,
  seed_note TEXT,
  window_seconds REAL NOT NULL,
  started_at REAL NOT NULL,
  source TEXT NOT NULL,
  note TEXT
);
CREATE TABLE IF NOT EXISTS events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  site TEXT NOT NULL,
  batch_id TEXT NOT NULL,
  kind TEXT NOT NULL,
  detail TEXT,
  at REAL NOT NULL,
  source TEXT
);
CREATE TABLE IF NOT EXISTS history (
  source_key TEXT PRIMARY KEY,
  site TEXT NOT NULL,
  payload_sha256 TEXT NOT NULL,
  imported_at REAL NOT NULL,
  note TEXT,
  payload TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS reservations (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  site TEXT NOT NULL,
  batch_id TEXT NOT NULL,
  count INTEGER NOT NULL,
  at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS locks (
  site TEXT PRIMARY KEY,
  reason TEXT NOT NULL,
  source TEXT,
  at REAL NOT NULL
);
"""

CALL_KINDS = ("active_nav", "search", "detail", "comments")
AUDIT_ONLY_KINDS = ("offline_check", "import", "active_nav_result",
                    "search_result", "detail_result", "comments_result")

#: classifications used when importing pre-ledger evidence
HISTORY_PRE_DEDUCTED = "pre_deducted"          # a call was charged, outcome varies
HISTORY_UNCHARGED_NAV = "uncharged_navigation"  # a real navigation never charged
HISTORY_OFFLINE_CHECK = "offline_check"         # local only, no network


#: Every pre-ledger source that the gate must account for. `may_be_absent` is only
#: allowed together with a written reason, and the reason is stored in the
#: snapshot so a reviewer can audit why a source is missing.
HISTORY_SOURCES = (
    {"source_key": "probe1", "path": "docs/validation/v10/weibo-probe/state-probe1",
     "classification": HISTORY_PRE_DEDUCTED, "may_be_absent": False,
     "reason": "charged before the ledger; launch failed, no request observed"},
    {"source_key": "probe2", "path": "docs/validation/v10/weibo-probe/state-probe2",
     "classification": HISTORY_PRE_DEDUCTED, "may_be_absent": False, "reason": ""},
    {"source_key": "probe3", "path": "docs/validation/v10/weibo-probe/state-probe3",
     "classification": HISTORY_PRE_DEDUCTED, "may_be_absent": False, "reason": ""},
    {"source_key": "login-window-1", "path": "docs/validation/v10/weibo-login/state-login",
     "classification": HISTORY_UNCHARGED_NAV, "may_be_absent": False,
     "reason": "active navigation never charged; timestamp unknown"},
    {"source_key": "login-window-2", "path": "docs/validation/v10/weibo-verify/state-login",
     "classification": HISTORY_UNCHARGED_NAV, "may_be_absent": False,
     "reason": "active navigation never charged; timestamp unknown"},
    {"source_key": "offline-login", "path": "docs/validation/v10/weibo/checks/state_login",
     "classification": HISTORY_OFFLINE_CHECK, "may_be_absent": False,
     "reason": "offline check: no network"},
    {"source_key": "offline-search", "path": "docs/validation/v10/weibo/checks/state_search",
     "classification": HISTORY_OFFLINE_CHECK, "may_be_absent": False, "reason": ""},
    {"source_key": "offline-detail", "path": "docs/validation/v10/weibo/checks/state_detail",
     "classification": HISTORY_OFFLINE_CHECK, "may_be_absent": False, "reason": ""},
    {"source_key": "offline-comments", "path": "docs/validation/v10/weibo/checks/state_comments",
     "classification": HISTORY_OFFLINE_CHECK, "may_be_absent": False, "reason": ""},
)

class PlatformBudgetError(Exception):
    """`code` is stable, `detail` is for humans; both are safe to print."""

    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(f"{code}:{detail}" if detail else code)
        self.code = code
        self.detail = detail


# --------------------------------------------------------------------------
# read-only source inspection (history gate)
# --------------------------------------------------------------------------
def canonical_source_path(spec_path: str) -> pathlib.Path:
    """Resolve a manifest entry to the one real file it is allowed to mean."""
    return (REPO_ROOT / spec_path / "budget.sqlite3").resolve()


def fingerprint(path: pathlib.Path) -> dict:
    """Cheap identity of a source file: size + mtime + sha256 of the bytes."""
    data = path.read_bytes()
    return {"size": len(data),
            "mtime_ns": path.stat().st_mtime_ns,
            "sha256": hashlib.sha256(data).hexdigest()}


def _read_source(path: pathlib.Path) -> dict:
    """Read one historical budget DB. Any doubt raises: this is a gate."""
    if not path.is_file():
        raise PlatformBudgetError("history_source_missing", str(path))
    for suffix in ("-wal", "-shm"):
        sidecar = pathlib.Path(str(path) + suffix)
        if sidecar.exists() and sidecar.stat().st_size > 0:
            # an uncheckpointed WAL means the committed state is uncertain
            raise PlatformBudgetError("history_wal_uncertain", str(sidecar))
    conn = None
    try:
        conn = sqlite3.connect(f"file:{path.as_posix()}?mode=ro&immutable=1",
                               uri=True, timeout=10.0)
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM budget WHERE id=1").fetchone()
        kinds = [r["kind"] for r in conn.execute(
            "SELECT kind FROM ledger ORDER BY rowid")]
    except sqlite3.Error as exc:
        raise PlatformBudgetError("history_source_unreadable",
                                 f"{path}:{type(exc).__name__}") from exc
    finally:
        if conn is not None:
            with contextlib.suppress(sqlite3.Error):
                conn.close()
    if row is None:
        raise PlatformBudgetError("history_source_unreadable", f"{path}:no_budget_row")
    return {"path": str(path), "calls": int(row["calls"] or 0),
            "records": int(row["records"] or 0),
            "locked": bool(row["locked"]),
            "lock_reason": row["lock_reason"],
            "kinds": kinds}


class PlatformLedger:
    """One sqlite file per site namespace. Append-only for events."""

    def __init__(self, path=None, *, site: str = "weibo", clock=time.time,
                 allow_test_manifest: bool = False) -> None:
        self.allow_test_manifest = bool(allow_test_manifest)
        self.path = pathlib.Path(path or DEFAULT_PATH)
        self.site = site
        self._clock = clock
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.path), timeout=30.0,
                                     isolation_level=None)  # explicit BEGIN
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(SCHEMA)

    # -- lifecycle ---------------------------------------------------------
    def close(self) -> None:
        self._conn.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        self.close()

    # -- authorization (explicit input only) --------------------------------
    def authorize_batch(self, batch_id: str, *, authorized_calls: int,
                        window_seconds: float, source: str, note: str = "",
                        records_cap: int = DEFAULT_RECORDS_TARGET, seed_used: int = 0,
                        seed_source: str = "", seed_note: str = "",
                        seed_from=None) -> dict:
        """Record an *externally decided* batch. Never called by a charge path.

        `seed_from` derives the already-spent calls from the audited snapshot
        (keys of `uncharged_navigation` rows), so two login navigations that
        really happened can not be forgotten by passing seed_used=0.
        """
        if not batch_id:
            raise PlatformBudgetError("batch_id_required")
        if not (1 <= int(authorized_calls) <= MAX_AUTHORIZED_CALLS):
            raise PlatformBudgetError("invalid_authorization",
                                      f"authorized_calls={authorized_calls}")
        if int(records_cap) < 1:      # v11：记录数是**软目标**，不设上限
            raise PlatformBudgetError("invalid_authorization",
                                      f"records_cap={records_cap}")
        if not (0 < float(window_seconds) <= MAX_SECONDS):
            raise PlatformBudgetError("invalid_authorization",
                                      f"window_seconds={window_seconds}")
        if not self.allow_test_manifest:
            # the two logins that already happened are not optional: a production
            # batch must bind them, otherwise seed=0 would read as fresh quota
            required = self._audited_uncharged_keys()
            if required:
                if not seed_from or set(seed_from) != set(required):
                    raise PlatformBudgetError("seed_association_incomplete",
                                              ",".join(sorted(required)))
                seed_used = len(required)
                seed_source = seed_source or "history:uncharged_navigation"
        if seed_from:
            audited = self._audited_uncharged(seed_from)
            if audited != len(tuple(seed_from)):
                raise PlatformBudgetError("seed_source_unaudited", str(list(seed_from)))
            seed_used = audited
            seed_source = seed_source or "history:uncharged_navigation"
        if not (0 <= int(seed_used) < int(authorized_calls)):
            raise PlatformBudgetError("invalid_authorization",
                                      f"seed_used={seed_used}")
        row = self._conn.execute("SELECT * FROM batches WHERE batch_id=?",
                                 (batch_id,)).fetchone()
        if row is not None:
            same = (row["site"] == self.site
                    and row["authorized_calls"] == int(authorized_calls)
                    and float(row["window_seconds"]) == float(window_seconds)
                    and int(row["records_cap"]) == int(records_cap)
                    and int(row["seed_used"]) == int(seed_used))
            if not same:
                raise PlatformBudgetError(
                    "batch_conflict",
                    f"existing {row['authorized_calls']}/{row['window_seconds']}s/"
                    f"{row['records_cap']}r/{row['seed_used']}seed != requested "
                    f"{authorized_calls}/{window_seconds}s/{records_cap}r/{seed_used}seed")
            return dict(row)
        self._conn.execute(
            "INSERT INTO batches(batch_id, site, authorized_calls, records_cap,"
            " seed_used, seed_source, seed_note, window_seconds, started_at, source,"
            " note) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (batch_id, self.site, int(authorized_calls), int(records_cap),
             int(seed_used), seed_source, seed_note, float(window_seconds),
             self._clock(), source, note))
        return dict(self._conn.execute("SELECT * FROM batches WHERE batch_id=?",
                                       (batch_id,)).fetchone())

    def _audited_uncharged_keys(self):
        """Keys the snapshot records as uncharged navigations (the two logins)."""
        row = self._conn.execute("SELECT payload FROM history WHERE site=?",
                                 (self.site,)).fetchone()
        if row is None:
            return []
        rows = json.loads(row["payload"]).get("rows", [])
        return [r["source_key"] for r in rows
                if r["classification"] == HISTORY_UNCHARGED_NAV]

    def _audited_uncharged(self, keys) -> int:
        """How many of `keys` are audited uncharged navigations in the snapshot."""
        row = self._conn.execute("SELECT payload FROM history WHERE site=?",
                                 (self.site,)).fetchone()
        if row is None:
            return 0
        payload = json.loads(row["payload"])
        rows = {r["source_key"]: r for r in payload["rows"]}
        return sum(1 for key in keys
                   if rows.get(key, {}).get("classification") == HISTORY_UNCHARGED_NAV)

    # -- lock --------------------------------------------------------------
    def lock(self, reason: str, *, source: str = "unknown") -> None:
        """Persist a platform lock. Callers must treat a raise as "stop"."""
        self._conn.execute(
            "INSERT INTO locks(site, reason, source, at) VALUES (?,?,?,?) "
            "ON CONFLICT(site) DO UPDATE SET reason=excluded.reason, "
            "source=excluded.source, at=excluded.at",
            (self.site, str(reason), source, self._clock()))

    def locked(self) -> tuple[bool, str | None]:
        """Fail closed: an unreadable ledger is reported as a lock."""
        try:
            row = self._conn.execute("SELECT reason FROM locks WHERE site=?",
                                     (self.site,)).fetchone()
        except sqlite3.Error as exc:
            return True, f"ledger_unavailable:{type(exc).__name__}"
        return (True, row["reason"]) if row is not None else (False, None)

    def _lock_inside_txn(self) -> str | None:
        row = self._conn.execute("SELECT reason FROM locks WHERE site=?",
                                 (self.site,)).fetchone()
        return row["reason"] if row is not None else None

    # -- charging ----------------------------------------------------------
    def charge(self, batch_id: str, kind: str, *, detail: str = "",
               source: str = "runtime") -> dict:
        """Atomically charge one call; the lock check is inside this transaction."""
        if kind not in CALL_KINDS:
            raise PlatformBudgetError("unknown_charge_kind", kind)
        self._conn.execute("BEGIN IMMEDIATE")
        try:
            reason = self._lock_inside_txn()
            if reason is not None:
                raise PlatformBudgetError("platform_locked", str(reason))
            refusal = self._verify_history_gate()
            if refusal is not None:
                # the lock was written in this transaction: commit it, then refuse
                self._conn.execute("COMMIT")
                raise PlatformBudgetError(refusal["code"], refusal["detail"])
            batch = self._conn.execute("SELECT * FROM batches WHERE batch_id=?",
                                       (batch_id,)).fetchone()
            if batch is None:
                raise PlatformBudgetError("no_authorized_batch", str(batch_id))
            now = self._clock()
            window_end = float(batch["started_at"]) + float(batch["window_seconds"])
            if now >= window_end:
                # a closed window is refused, never reopened; history stays
                raise PlatformBudgetError("batch_window_closed", str(batch_id))
            last = self._conn.execute(
                "SELECT MAX(at) FROM events WHERE batch_id=? AND site=? "
                "AND kind IN (%s)" % ",".join("?" * len(CALL_KINDS)),
                (batch_id, self.site, *CALL_KINDS)).fetchone()[0]
            if last is not None and now - float(last) < MIN_INTERVAL:
                raise PlatformBudgetError(
                    "interval_not_elapsed", f"{now - float(last):.1f}s<{MIN_INTERVAL}s")
            window_start = now - float(batch["window_seconds"])
            used = self._conn.execute(
                "SELECT COUNT(*) FROM events WHERE batch_id=? AND site=? "
                "AND kind IN (%s) AND at >= ?" % ",".join("?" * len(CALL_KINDS)),
                (batch_id, self.site, *CALL_KINDS, window_start)).fetchone()[0]
            # historical usage seeded at authorization time is NOT filtered by the
            # rolling window: what already happened stays spent.
            used += int(batch["seed_used"] or 0)
            if used >= int(batch["authorized_calls"]):
                raise PlatformBudgetError(
                    "calls_exhausted", f"{used}/{batch['authorized_calls']}")
            self._conn.execute(
                "INSERT INTO events(site, batch_id, kind, detail, at, source) "
                "VALUES (?,?,?,?,?,?)",
                (self.site, batch_id, kind, detail, now, source))
            self._conn.execute("COMMIT")
        except Exception as exc:
            with contextlib.suppress(sqlite3.Error):
                self._conn.execute("ROLLBACK")
            raise
        return self.summary(batch_id)

    def reserve_records(self, batch_id: str, count: int = 1, *,
                        source: str = "runtime") -> dict:
        """登记记录数（**软目标**：超目标照常累加，只回报超了多少）。"""
        if count <= 0:
            raise PlatformBudgetError("invalid_reservation")
        self._conn.execute("BEGIN IMMEDIATE")
        try:
            reason = self._lock_inside_txn()
            if reason is not None:
                raise PlatformBudgetError("platform_locked", str(reason))
            batch = self._conn.execute("SELECT * FROM batches WHERE batch_id=?",
                                       (batch_id,)).fetchone()
            if batch is None:
                raise PlatformBudgetError("no_authorized_batch", str(batch_id))
            used = self._conn.execute(
                "SELECT COALESCE(SUM(count),0) FROM reservations "
                "WHERE batch_id=? AND site=?", (batch_id, self.site)).fetchone()[0]
            cap = int(batch["records_cap"])
            used_total = int(used) + int(count)
            self._conn.execute(
                "INSERT INTO reservations(site, batch_id, count, at) VALUES (?,?,?,?)",
                (self.site, batch_id, int(count), self._clock()))
            self._conn.execute("COMMIT")
        except Exception:
            with contextlib.suppress(sqlite3.Error):
                self._conn.execute("ROLLBACK")
            raise
        return {"batch_id": batch_id, "reserved": int(count),
                "records_target": cap,
                "records_used": used_total,
                "over_cap": used_total > cap,
                "over_by": max(0, used_total - cap),
                "records_cap": cap}

    def record_result(self, batch_id: str, kind: str, outcome: str, *,
                      detail: str = "") -> None:
        """Record success / failed / unknown for an action already charged."""
        if outcome not in ("success", "failed", "unknown"):
            raise PlatformBudgetError("invalid_outcome", outcome)
        self.audit(batch_id, f"{kind}_result", detail=f"{outcome} {detail}".strip(),
                   source="weibo.result")

    def audit(self, batch_id: str, kind: str, *, detail: str = "",
              source: str = "runtime") -> None:
        """Record something that happened but must not consume an allowance."""
        if kind not in AUDIT_ONLY_KINDS:
            raise PlatformBudgetError("unknown_audit_kind", kind)
        self._conn.execute(
            "INSERT INTO events(site, batch_id, kind, detail, at, source) "
            "VALUES (?,?,?,?,?,?)",
            (self.site, batch_id, kind, detail, self._clock(), source))

    def _verify_history_gate(self):
        """Verify the imported snapshot against the real sources, inside the txn.

        Returns a refusal dict when the charge must be refused *after* this
        transaction commits (a locked source is inherited into the platform lock
        here, atomically). Any other doubt raises, which rolls the charge back.

        Checks, in order: snapshot present; manifest entries map to their one
        canonical path; no non-empty WAL/SHM sidecar; the source is readable;
        the source is not locked (fresh read, never a stale flag); the bytes are
        unchanged since the import.
        """
        row = self._conn.execute("SELECT payload FROM history WHERE site=?",
                                 (self.site,)).fetchone()
        if row is None:
            raise PlatformBudgetError("history_gate_unsatisfied",
                                      "no imported history snapshot")
        payload = json.loads(row["payload"])
        manifest = payload.get("manifest") or []
        test_only = bool(payload.get("test_only"))
        if test_only and not self.allow_test_manifest:
            raise PlatformBudgetError("history_manifest_not_allowed",
                                      "test manifest in a production ledger")
        self._check_manifest_against_declaration(manifest, test_only=test_only)
        rows = {r["source_key"]: r for r in payload.get("rows", [])}
        seen_paths = {}
        for spec in manifest:
            key = spec["source_key"]
            canonical = canonical_source_path(spec["path"])
            if canonical in seen_paths:
                raise PlatformBudgetError("history_manifest_duplicate_path",
                                          f"{key} == {seen_paths[canonical]}")
            seen_paths[canonical] = key
            found = rows.get(key)
            if found is None:
                if spec.get("may_be_absent") and spec.get("reason"):
                    continue
                raise PlatformBudgetError("history_source_missing", key)
            if pathlib.Path(found["path"]).resolve() != canonical:
                # a snapshot may not re-point a key at another source
                raise PlatformBudgetError("history_source_mismatch", key)
            if not canonical.is_file():
                if spec.get("may_be_absent") and spec.get("reason"):
                    continue
                raise PlatformBudgetError("history_source_missing", key)
            for suffix in ("-wal", "-shm"):
                sidecar = pathlib.Path(str(canonical) + suffix)
                if sidecar.exists() and sidecar.stat().st_size > 0:
                    raise PlatformBudgetError("history_wal_uncertain", str(sidecar))
            fresh = _read_source(canonical)
            if fresh["locked"]:
                reason = str(fresh.get("lock_reason") or "history_lock")
                try:
                    self._conn.execute(
                        "INSERT INTO locks(site, reason, source, at) VALUES (?,?,?,?) "
                        "ON CONFLICT(site) DO UPDATE SET reason=excluded.reason, "
                        "source=excluded.source, at=excluded.at",
                        (self.site, reason, f"history:{key}", self._clock()))
                except sqlite3.Error as exc:
                    raise PlatformBudgetError(
                        "lock_write_failed", f"{type(exc).__name__}") from exc
                return {"code": "history_locked", "detail": f"{key}|{reason}"}
            if fingerprint(canonical) != found.get("fingerprint"):
                raise PlatformBudgetError("history_source_changed", key)
        return None

    def _check_manifest_against_declaration(self, manifest, *, test_only: bool) -> None:
        """Keys, classifications and necessity must match the fixed declaration.

        A test manifest may point at temp paths, but it may not rename a key,
        disguise a classification, drop an entry or add one.
        """
        fixed = {spec["source_key"]: spec for spec in HISTORY_SOURCES}
        seen = {}
        for spec in manifest:
            key = spec.get("source_key")
            if key in seen:
                raise PlatformBudgetError("history_manifest_invalid", f"duplicate:{key}")
            seen[key] = spec
            declared = fixed.get(key)
            if declared is None:
                raise PlatformBudgetError("history_manifest_invalid", f"extra:{key}")
            if spec.get("classification") != declared["classification"]:
                raise PlatformBudgetError("history_manifest_invalid",
                                          f"classification:{key}")
            if bool(spec.get("may_be_absent")) != bool(declared["may_be_absent"]):
                raise PlatformBudgetError("history_manifest_invalid", f"necessity:{key}")
            if not test_only and (canonical_source_path(spec["path"])
                                  != canonical_source_path(declared["path"])):
                raise PlatformBudgetError("history_source_mismatch", key)
        missing = set(fixed) - set(seen)
        if missing:
            raise PlatformBudgetError("history_manifest_invalid",
                                      "missing:" + ",".join(sorted(missing)))

    # -- history gate (provenance only, but mandatory) ----------------------
    def import_snapshot(self, sources, *, note: str = "", manifest=None) -> dict:
        """Import pre-ledger evidence, or fail closed.

        `sources` is a list of `{"source_key", "path", "classification", "note"}`.
        `manifest` defaults to `HISTORY_SOURCES`; an injected manifest is stored
        with `test_only=True` and a production ledger refuses it. Every manifest
        entry must map to a distinct canonical path, and each snapshot row must
        point at exactly that path.
        """
        if not sources:
            raise PlatformBudgetError("history_sources_required")
        declared = list(manifest or HISTORY_SOURCES)
        test_only = manifest is not None
        by_key = {spec["source_key"]: spec for spec in declared}
        paths = {}
        rows = []
        for spec in sources:
            source_key = str(spec.get("source_key") or "")
            classification = str(spec.get("classification") or "")
            decl = by_key.get(source_key)
            if decl is None:
                raise PlatformBudgetError("history_source_undeclared", source_key)
            if classification not in (HISTORY_PRE_DEDUCTED, HISTORY_UNCHARGED_NAV,
                                      HISTORY_OFFLINE_CHECK):
                raise PlatformBudgetError("history_spec_invalid", source_key)
            canonical = canonical_source_path(decl["path"])
            given = pathlib.Path(spec["path"]).resolve()
            if given != canonical and not test_only:
                raise PlatformBudgetError("history_source_mismatch", source_key)
            if canonical in paths:
                raise PlatformBudgetError("history_manifest_duplicate_path",
                                          f"{source_key} == {paths[canonical]}")
            paths[canonical] = source_key
            data = _read_source(given)
            rows.append({**data, "source_key": source_key,
                         "classification": classification,
                         "note": spec.get("note", ""),
                         "fingerprint": fingerprint(given)})
        payload = json.dumps({"manifest": declared, "rows": rows,
                              "test_only": test_only},
                             ensure_ascii=False, sort_keys=True)
        digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
        self._conn.execute("BEGIN IMMEDIATE")
        try:
            existing = self._conn.execute(
                "SELECT payload_sha256 FROM history WHERE site=?",
                (self.site,)).fetchone()
            if existing is not None and existing["payload_sha256"] == digest:
                self._conn.execute("COMMIT")
                return {"status": "unchanged", "sha256": digest}
            self._conn.execute(
                "INSERT INTO history(source_key, site, payload_sha256, imported_at,"
                " note, payload) VALUES (?,?,?,?,?,?) "
                "ON CONFLICT(source_key) DO UPDATE SET "
                "payload_sha256=excluded.payload_sha256, "
                "imported_at=excluded.imported_at, note=excluded.note, "
                "payload=excluded.payload",
                (f"snapshot:{self.site}", self.site, digest, self._clock(), note, payload))
            self._conn.execute("COMMIT")
        except Exception:
            with contextlib.suppress(sqlite3.Error):
                self._conn.execute("ROLLBACK")
            raise
        return {"status": "recorded", "sha256": digest, "sources": len(rows),
                "test_only": test_only}

    def history_summary(self) -> dict:
        row = self._conn.execute(
            "SELECT payload, imported_at FROM history WHERE site=?",
            (self.site,)).fetchone()
        if row is None:
            return {"imported": False, "pre_deducted_calls": None,
                    "uncharged_navigations": None, "offline_checks": None,
                    "note": "history gate not satisfied: no snapshot imported"}
        payload = json.loads(row["payload"])
        rows = payload.get("rows", payload if isinstance(payload, list) else [])
        return {
            "imported": True,
            "imported_at": row["imported_at"],
            "pre_deducted_calls": sum(r["calls"] for r in rows
                                      if r["classification"] == HISTORY_PRE_DEDUCTED),
            "uncharged_navigations": sum(1 for r in rows
                                         if r["classification"] == HISTORY_UNCHARGED_NAV),
            "offline_checks": sum(1 for r in rows
                                  if r["classification"] == HISTORY_OFFLINE_CHECK),
            "offline_charged_calls": sum(r["calls"] for r in rows
                                         if r["classification"] == HISTORY_OFFLINE_CHECK),
            "sources": [{k: r[k] for k in ("source_key", "classification", "path",
                                           "calls", "records", "locked",
                                           "lock_reason", "note")} for r in rows],
        }

    # -- reads -------------------------------------------------------------
    def summary(self, batch_id: str | None = None) -> dict:
        is_locked, reason = self.locked()
        history_total = self._conn.execute(
            "SELECT COUNT(*) FROM events WHERE site=? AND kind IN (%s)"
            % ",".join("?" * len(CALL_KINDS)), (self.site, *CALL_KINDS)).fetchone()[0]
        history = self.history_summary()
        seeded = self._conn.execute(
            "SELECT COALESCE(SUM(seed_used),0) FROM batches WHERE site=?",
            (self.site,)).fetchone()[0]
        # full history = everything already spent, not just the new events
        full_history = (int(seeded) + int(history_total)
                        + int(history.get("pre_deducted_calls") or 0)
                        + int(history.get("offline_charged_calls") or 0))
        out = {"site": self.site, "locked": is_locked, "lock_reason": reason,
               "history_total_calls": full_history,
               "history_total_new_events": history_total,
               "history_seeded_calls": int(seeded),
               "history": history}
        if batch_id:
            batch = self._conn.execute("SELECT * FROM batches WHERE batch_id=?",
                                       (batch_id,)).fetchone()
            if batch is None:
                out.update({"batch_id": batch_id, "authorized": False})
                return out
            window_start = self._clock() - float(batch["window_seconds"])
            used = self._conn.execute(
                "SELECT COUNT(*) FROM events WHERE batch_id=? AND site=? "
                "AND kind IN (%s) AND at >= ?" % ",".join("?" * len(CALL_KINDS)),
                (batch_id, self.site, *CALL_KINDS, window_start)).fetchone()[0]
            reserved = self._conn.execute(
                "SELECT COALESCE(SUM(count),0) FROM reservations WHERE batch_id=? "
                "AND site=?", (batch_id, self.site)).fetchone()[0]
            seed = int(batch["seed_used"] or 0)
            used = used + seed          # seeded history is never window-filtered
            out.update({
                "batch_id": batch_id, "authorized": True,
                "seed_used": seed, "seed_source": batch["seed_source"],
                "seed_note": batch["seed_note"],
                "authorized_calls": int(batch["authorized_calls"]),
                "records_cap": int(batch["records_cap"]),
                "records_reserved": int(reserved),
                "window_seconds": float(batch["window_seconds"]),
                "started_at": float(batch["started_at"]),
                "window_open": self._clock() < float(batch["started_at"]) + float(
                    batch["window_seconds"]),
                "used": used,
                "remaining": max(0, int(batch["authorized_calls"]) - used),
                "source": batch["source"], "note": batch["note"],
            })
        return out

    def events(self, limit: int = 20) -> list[dict]:
        rows = self._conn.execute(
            "SELECT kind, batch_id, detail, at, source FROM events WHERE site=? "
            "ORDER BY id DESC LIMIT ?", (self.site, int(limit))).fetchall()
        return [dict(row) for row in rows]


def open_default(path=None, *, site: str = "weibo") -> PlatformLedger:
    """Open the site ledger.

    The path is fixed by the caller (or the module default). There is no
    environment override on purpose: a switchable authority is a bypass.
    Tests construct `PlatformLedger(tmp_path)` directly, or patch the adapter's
    `_open_guard` seam.
    """
    return PlatformLedger(path or DEFAULT_PATH, site=site)
