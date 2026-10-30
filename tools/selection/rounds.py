"""Round/round_item state machine for bounded selection rounds (stdlib only)."""

from __future__ import annotations

import json
import uuid

from . import db, models

ALLOWED = {
    ("draft", "running"), ("running", "paused"), ("running", "complete"),
    ("running", "partial"), ("running", "failed"), ("paused", "running"),
    ("partial", "running"),
}
TERMINAL = {"complete", "failed", "cancelled"}


def _now():
    return models.utc_now()


def transition(conn, round_id: int, new_status: str, *, reason: str | None = None) -> dict:
    """Single state-transition function; illegal transitions raise ValueError."""
    row = conn.execute("SELECT * FROM rounds WHERE id=?", (round_id,)).fetchone()
    if row is None:
        raise ValueError("round_not_found")
    old = row["status"]
    if new_status == "cancelled":
        allowed = old != "cancelled"
    else:
        allowed = (old, new_status) in ALLOWED
    if not allowed:
        raise ValueError(f"illegal_transition:{old}->{new_status}")
    ended = _now() if new_status in TERMINAL else row["ended_at"]
    conn.execute("UPDATE rounds SET status=?,ended_at=? WHERE id=?", (new_status, ended, round_id))
    if new_status == "cancelled":
        conn.execute("UPDATE round_item SET state='failed',last_error=?,updated_at=? "
                     "WHERE round_id=? AND state IN ('pending','processing')",
                     ("cancelled", _now(), round_id))
    conn.commit()
    return {"round_id": round_id, "from": old, "to": new_status, "reason": reason}


def start(conn, *, kind: str, platform: str, budget: dict, idempotency_key: str) -> dict:
    if not idempotency_key:
        raise ValueError("idempotency_key_required")
    existing = conn.execute("SELECT * FROM rounds WHERE idempotency_key=?", (idempotency_key,)).fetchone()
    if existing:
        try:
            old_budget = json.loads(existing["budget_json"] or "{}")
        except Exception:
            old_budget = {}
        if old_budget != budget:
            raise ValueError("idempotency_conflict")
        return {**dict(existing), "reused": True}
    cur = conn.execute(
        "INSERT INTO rounds(kind,platform,status,budget_json,idempotency_key,started_at,error_count) "
        "VALUES (?,?,'draft',?,?,?,0)",
        (kind, platform, json.dumps(budget, ensure_ascii=False), idempotency_key, _now()))
    conn.commit()
    row = conn.execute("SELECT * FROM rounds WHERE id=?", (cur.lastrowid,)).fetchone()
    return {**dict(row), "reused": False}


def add_item(conn, round_id: int, item_key: str) -> dict:
    row = conn.execute("SELECT * FROM round_item WHERE round_id=? AND item_key=?",
                       (round_id, item_key)).fetchone()
    if row:
        return dict(row)
    conn.execute(
        "INSERT INTO round_item(round_id,item_key,state,attempts,updated_at) VALUES (?,?,'pending',0,?)",
        (round_id, item_key, _now()))
    conn.commit()
    return dict(conn.execute("SELECT * FROM round_item WHERE round_id=? AND item_key=?",
                             (round_id, item_key)).fetchone())


def mark_item(conn, round_id: int, item_key: str, state: str, *, error: str | None = None) -> dict:
    if state not in models.ROUND_ITEM_STATES:
        raise ValueError("invalid_item_state")
    row = conn.execute("SELECT * FROM round_item WHERE round_id=? AND item_key=?",
                       (round_id, item_key)).fetchone()
    if row is None:
        raise ValueError("item_not_found")
    conn.execute(
        "UPDATE round_item SET state=?,attempts=attempts+1,last_error=?,updated_at=? "
        "WHERE round_id=? AND item_key=?",
        (state, error, _now(), round_id, item_key))
    if state == "failed":
        conn.execute("UPDATE rounds SET error_count=error_count+1 WHERE id=?", (round_id,))
    conn.commit()
    return dict(conn.execute("SELECT * FROM round_item WHERE round_id=? AND item_key=?",
                             (round_id, item_key)).fetchone())


def pause(conn, round_id: int, *, cursor: dict | None = None) -> dict:
    """Validate first, transition once, then update cursor only when it is non-empty."""
    row = conn.execute("SELECT status,cursor_json FROM rounds WHERE id=?", (round_id,)).fetchone()
    if row is None:
        raise ValueError("round_not_found")
    if row["status"] not in ("running", "partial"):
        raise ValueError(f"illegal_transition:{row['status']}->paused")
    out = transition(conn, round_id, "paused", reason="user_pause")
    if cursor:
        conn.execute("UPDATE rounds SET cursor_json=? WHERE id=?",
                     (json.dumps(cursor, ensure_ascii=False), round_id))
        conn.commit()
    return out


def resume(conn, round_id: int) -> dict:
    """Mark a crashed processing item as failed/interrupted before resuming."""
    row = conn.execute("SELECT status FROM rounds WHERE id=?", (round_id,)).fetchone()
    if row is None:
        raise ValueError("round_not_found")
    if row["status"] not in ("paused", "partial"):
        raise ValueError(f"illegal_transition:{row['status']}->running")
    conn.execute(
        "UPDATE round_item SET state='failed',last_error='interrupted',attempts=attempts+1,updated_at=? "
        "WHERE round_id=? AND state='processing'", (_now(), round_id))
    conn.commit()
    out = transition(conn, round_id, "running", reason="resume")
    out["interrupted_items"] = conn.execute(
        "SELECT COUNT(*) FROM round_item WHERE round_id=? AND last_error='interrupted'",
        (round_id,)).fetchone()[0]
    return out


def cancel(conn, round_id: int) -> dict:
    return transition(conn, round_id, "cancelled", reason="user_cancel")


def status(conn, round_id: int) -> dict:
    row = conn.execute("SELECT * FROM rounds WHERE id=?", (round_id,)).fetchone()
    if row is None:
        raise ValueError("round_not_found")
    items = [dict(r) for r in conn.execute(
        "SELECT item_key,state,attempts,last_error,updated_at FROM round_item "
        "WHERE round_id=? ORDER BY id", (round_id,))]
    return {**dict(row), "items": items}


def used_requests(conn, round_id: int) -> int:
    row = conn.execute("SELECT stats_json FROM rounds WHERE id=?", (round_id,)).fetchone()
    if row and row["stats_json"]:
        try:
            return int(json.loads(row["stats_json"]).get("requests_used", 0))
        except Exception:
            return 0
    return 0


def update_stats(conn, round_id: int, stats: dict) -> None:
    conn.execute("UPDATE rounds SET stats_json=? WHERE id=?",
                 (json.dumps(stats, ensure_ascii=False), round_id))
    conn.commit()
