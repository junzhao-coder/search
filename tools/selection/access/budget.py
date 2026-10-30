"""Durable call budget, shared by every process and keyed by the state dir.

One state dir == one budget. There is deliberately **no** flag that starts a
fresh budget or bypasses a lock: the only way to get more calls is for the
planner to hand over a new state dir. An explicit `--batch-id` is a *label*
inside that state dir, not an escape hatch — it is recorded, it becomes the
current label, and it inherits every counter and lock already accumulated.

Two independent counters live in the same row:

- `calls` — active navigations / API reads (3 max, >=15s apart, 300s window);
- `polls` — login-state polling (10 max). Login must never eat the data
  budget: 300s at 3s/poll would otherwise burn 100 calls before the first
  real read. Polls are recorded in the same ledger but counted separately.

Rules encoded here (v10 Zhihu batch, learned from the XHS overrun):

- every active navigation / API call is charged BEFORE it is sent;
- a failed call is never refunded;
- if the charge cannot be written, the caller must not send anything;
- login wall / captcha / 403 / 429 / risk locks the budget permanently, and a
  locked budget fails for any later process, any batch label, any default run.
"""

from __future__ import annotations

import json
import pathlib
import sqlite3
import time
import uuid

MAX_CALLS = 3
DEFAULT_RECORDS_TARGET = 5
MAX_RECORDS = DEFAULT_RECORDS_TARGET  # 兼容别名：默认目标值，不是上限（v11）
#: Poll quota guards the ledger, not the wall clock. It must cover a full login
#: window (300s) at the default 3s poll: ceil(300/3)=100, plus margin. A fixed
#: 10 closed the window after ~30s and made scanning impossible.
MAX_POLLS = 120
MIN_INTERVAL = 15.0
MAX_SECONDS = 300.0


def polls_for_window(timeout: float, poll: float) -> int:
    """Poll quota that covers `timeout` at `poll` seconds, with margin."""
    poll = max(float(poll), 0.1)
    return max(MAX_POLLS, int(-(-float(timeout) // poll)) + 5)

SCHEMA = """
CREATE TABLE IF NOT EXISTS budget (
  id INTEGER PRIMARY KEY CHECK (id = 1),
  state_dir TEXT NOT NULL,
  batch_id TEXT NOT NULL,
  created_at REAL NOT NULL,
  started_at REAL NOT NULL,
  calls INTEGER NOT NULL DEFAULT 0,
  records INTEGER NOT NULL DEFAULT 0,
  polls INTEGER NOT NULL DEFAULT 0,
  last_call_at REAL,
  locked INTEGER NOT NULL DEFAULT 0,
  lock_reason TEXT,
  lock_source TEXT
);
CREATE TABLE IF NOT EXISTS ledger (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  at REAL NOT NULL,
  kind TEXT NOT NULL,
  detail TEXT
);
CREATE TABLE IF NOT EXISTS batches (
  batch_id TEXT PRIMARY KEY,
  first_seen_at REAL NOT NULL
);
"""


class BudgetError(Exception):
    """Raised before any network call; `code` is stable for tests and logs."""

    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(f"{code}:{detail}" if detail else code)
        self.code = code
        self.detail = detail


def db_path(state_dir) -> pathlib.Path:
    return pathlib.Path(state_dir) / "budget.sqlite3"


def _connect(path: pathlib.Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path), timeout=5.0, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout=5000")
    return conn


def _rollback(conn) -> None:
    """End any open transaction. Connection.rollback() is a no-op when idle and
    does not need write permission, so it also works on a broken write path."""
    try:
        conn.rollback()
    except sqlite3.Error:
        pass


class Budget:
    """The single budget of one state dir. `batch_id` is only a label."""

    def __init__(self, conn, *, state_dir: str, batch_id: str, clock=time.time,
                 max_calls: int = MAX_CALLS, max_records: int = DEFAULT_RECORDS_TARGET,
                 max_polls: int = MAX_POLLS, min_interval: float = MIN_INTERVAL,
                 max_seconds: float = MAX_SECONDS):
        self._conn = conn
        self.state_dir = state_dir
        self.batch_id = batch_id
        self._clock = clock
        self.max_calls = max_calls
        self.max_records = max_records
        self.max_polls = max_polls
        self.min_interval = min_interval
        self.max_seconds = max_seconds

    # -- reads -------------------------------------------------------------
    def row(self) -> sqlite3.Row:
        got = self._conn.execute("SELECT * FROM budget WHERE id=1").fetchone()
        if got is None:
            raise BudgetError("budget_missing", self.state_dir)
        return got

    def snapshot(self) -> dict:
        r = self.row()
        now = self._clock()
        return {
            "state_dir": r["state_dir"], "batch_id": self.batch_id,
            "calls": r["calls"], "calls_max": self.max_calls,
            "records": r["records"], "records_max": self.max_records,
            "polls": r["polls"], "polls_max": self.max_polls,
            "elapsed_s": round(now - r["started_at"], 3), "seconds_max": self.max_seconds,
            "last_call_at": r["last_call_at"], "locked": bool(r["locked"]),
            "lock_reason": r["lock_reason"], "lock_source": r["lock_source"],
        }

    # -- writes ------------------------------------------------------------
    def _begin(self) -> None:
        try:
            self._conn.execute("BEGIN IMMEDIATE")
        except sqlite3.Error as exc:
            raise BudgetError("budget_write_failed", str(exc))

    def charge(self, kind: str, detail: str = "") -> dict:
        """Reserve one active call. Never returns when the reservation failed."""
        now = self._clock()
        self._begin()
        try:
            r = self._conn.execute("SELECT * FROM budget WHERE id=1").fetchone()
            if r is None:
                raise BudgetError("budget_missing", self.state_dir)
            if r["locked"]:
                raise BudgetError("batch_locked", r["lock_reason"] or "")
            if r["calls"] >= self.max_calls:
                raise BudgetError("calls_exhausted", f"{r['calls']}/{self.max_calls}")
            if now - r["started_at"] > self.max_seconds:
                raise BudgetError("time_exhausted", f"{now - r['started_at']:.0f}s")
            if r["last_call_at"] is not None and now - r["last_call_at"] < self.min_interval:
                raise BudgetError("interval_not_elapsed",
                                  f"{self.min_interval - (now - r['last_call_at']):.1f}s left")
            self._conn.execute(
                "UPDATE budget SET calls=calls+1, last_call_at=? WHERE id=1", (now,))
            self._conn.execute(
                "INSERT INTO ledger(at, kind, detail) VALUES (?,?,?)",
                (now, "charge", json.dumps({"kind": kind, "detail": detail,
                                            "batch_id": self.batch_id},
                                           ensure_ascii=False)))
            self._conn.execute("COMMIT")
        except BudgetError:
            _rollback(self._conn)
            raise
        except sqlite3.Error as exc:
            _rollback(self._conn)
            raise BudgetError("budget_write_failed", str(exc))
        return self.snapshot()

    def charge_poll(self, detail: str = "") -> dict:
        """Reserve one login-state poll. Separate quota; still blocked by a lock.

        No interval and no batch-window check: the login window has its own
        deadline, and polling it must not consume (or be throttled by) the
        active-call budget.
        """
        now = self._clock()
        self._begin()
        try:
            r = self._conn.execute("SELECT * FROM budget WHERE id=1").fetchone()
            if r is None:
                raise BudgetError("budget_missing", self.state_dir)
            if r["locked"]:
                raise BudgetError("batch_locked", r["lock_reason"] or "")
            if r["polls"] >= self.max_polls:
                raise BudgetError("polls_exhausted", f"{r['polls']}/{self.max_polls}")
            self._conn.execute("UPDATE budget SET polls=polls+1 WHERE id=1")
            self._conn.execute(
                "INSERT INTO ledger(at, kind, detail) VALUES (?,?,?)",
                (now, "poll", json.dumps({"detail": detail, "batch_id": self.batch_id},
                                         ensure_ascii=False)))
            self._conn.execute("COMMIT")
        except BudgetError:
            _rollback(self._conn)
            raise
        except sqlite3.Error as exc:
            _rollback(self._conn)
            raise BudgetError("budget_write_failed", str(exc))
        return self.snapshot()

    def reserve_records(self, count: int) -> dict:
        if count < 0:
            raise BudgetError("bad_record_count", str(count))
        now = self._clock()
        self._begin()
        try:
            r = self._conn.execute("SELECT * FROM budget WHERE id=1").fetchone()
            if r is None:
                raise BudgetError("budget_missing", self.state_dir)
            if r["locked"]:
                raise BudgetError("batch_locked", r["lock_reason"] or "")
            # v11：记录数是**软目标**——超目标照常累加，只回报超了多少
            self._conn.execute("UPDATE budget SET records=records+? WHERE id=1", (count,))
            self._conn.execute(
                "INSERT INTO ledger(at, kind, detail) VALUES (?,?,?)",
                (now, "records", json.dumps({"count": count, "batch_id": self.batch_id})))
            self._conn.execute("COMMIT")
            used_total = int(r["records"]) + int(count)
        except BudgetError:
            _rollback(self._conn)
            raise
        except sqlite3.Error as exc:
            _rollback(self._conn)
            raise BudgetError("budget_write_failed", str(exc))
        target = int(self.max_records)
        out = self.snapshot()
        out.update({"records_target": target, "records_used": used_total,
                    "over_cap": used_total > target,
                    "over_by": max(0, used_total - target)})
        return out

    def note(self, kind: str, detail: str = "") -> None:
        """Outcome/evidence line; failure here never hides the primary result."""
        try:
            self._conn.execute("INSERT INTO ledger(at, kind, detail) VALUES (?,?,?)",
                               (self._clock(), kind, detail))
        except sqlite3.Error:
            pass

    def lock(self, reason: str, source: str = "unknown") -> None:
        """Permanent for this state dir; any later process reads it from disk."""
        now = self._clock()
        self._begin()
        try:
            self._conn.execute(
                "UPDATE budget SET locked=1, lock_reason=?, lock_source=? WHERE id=1",
                (reason, source))
            self._conn.execute(
                "INSERT INTO ledger(at, kind, detail) VALUES (?,?,?)",
                (now, "lock", json.dumps({"reason": reason, "source": source,
                                          "batch_id": self.batch_id},
                                         ensure_ascii=False)))
            self._conn.execute("COMMIT")
        except sqlite3.Error as exc:
            _rollback(self._conn)
            raise BudgetError("budget_write_failed", str(exc))

    def close(self) -> None:
        try:
            self._conn.close()
        except sqlite3.Error:
            pass


def open_budget(state_dir, *, batch_id: str | None = None, clock=time.time,
                **limits) -> Budget:
    """Open the one budget of this state dir.

    A locked budget refuses here, before any caller can build a transport. A
    `batch_id` only labels this run: it is recorded and becomes the current
    label, but the counters, the window and the lock all stay state-dir wide.
    """
    directory = pathlib.Path(state_dir)
    try:
        directory.mkdir(parents=True, exist_ok=True)
        conn = _connect(db_path(directory))
        conn.executescript(SCHEMA)
    except (sqlite3.Error, OSError) as exc:
        raise BudgetError("budget_write_failed", str(exc))

    now = clock()
    resolved = directory.resolve()
    try:
        row = conn.execute("SELECT * FROM budget WHERE id=1").fetchone()
        if row is None:
            # the ledger is shared by every adapter, so the auto label is neutral
            label = batch_id or f"batch-{uuid.uuid4().hex[:12]}"
            conn.execute(
                "INSERT INTO budget(id, state_dir, batch_id, created_at, started_at) "
                "VALUES (1,?,?,?,?)", (str(resolved), label, now, now))
            conn.execute("INSERT OR IGNORE INTO batches(batch_id, first_seen_at) "
                         "VALUES (?,?)", (label, now))
            row = conn.execute("SELECT * FROM budget WHERE id=1").fetchone()
        elif row["locked"]:
            conn.close()
            raise BudgetError("batch_locked", row["lock_reason"] or "")
        elif batch_id and batch_id != row["batch_id"]:
            # a different label is NOT a new budget: register it, keep counting
            conn.execute("UPDATE budget SET batch_id=? WHERE id=1", (batch_id,))
            conn.execute("INSERT OR IGNORE INTO batches(batch_id, first_seen_at) "
                         "VALUES (?,?)", (batch_id, now))
            conn.execute("INSERT INTO ledger(at, kind, detail) VALUES (?,?,?)",
                         (now, "relabel", json.dumps({"from": row["batch_id"],
                                                      "to": batch_id},
                                                     ensure_ascii=False)))
            row = conn.execute("SELECT * FROM budget WHERE id=1").fetchone()
    except BudgetError:
        conn.close()
        raise
    except sqlite3.Error as exc:
        conn.close()
        raise BudgetError("budget_write_failed", str(exc))

    return Budget(conn, state_dir=str(resolved), batch_id=row["batch_id"],
                  clock=clock, **limits)


def read_ledger(state_dir, limit: int = 20) -> list[dict]:
    path = db_path(state_dir)
    if not path.exists():
        return []
    conn = _connect(path)
    try:
        rows = conn.execute(
            "SELECT at, kind, detail FROM ledger ORDER BY id DESC LIMIT ?",
            (limit,)).fetchall()
        return [dict(r) for r in rows]
    except sqlite3.Error:
        return []
    finally:
        conn.close()


def peek(state_dir) -> dict | None:
    """Read the budget without enforcing the lock, so a lock stays inspectable."""
    path = db_path(state_dir)
    if not path.exists():
        return None
    conn = _connect(path)
    try:
        row = conn.execute("SELECT * FROM budget WHERE id=1").fetchone()
        if row is None:
            return None
        return {"state_dir": row["state_dir"], "batch_id": row["batch_id"],
                "calls": row["calls"], "calls_max": MAX_CALLS,
                "records": row["records"], "records_max": MAX_RECORDS,
                "polls": row["polls"], "polls_max": MAX_POLLS,
                "started_at": row["started_at"], "last_call_at": row["last_call_at"],
                "seconds_max": MAX_SECONDS, "locked": bool(row["locked"]),
                "lock_reason": row["lock_reason"], "lock_source": row["lock_source"]}
    except sqlite3.Error:
        return None
    finally:
        conn.close()
