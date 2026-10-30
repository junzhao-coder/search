"""Review queue (#14 list, #15 resolve) and the #21 recompute materializer.

Resolving or dismissing a review item never restores an invalidated verification (I1/§3.3).
"""

from __future__ import annotations

from .errors import AppError
from .gates import append_downgrade
from .state import (GATES, _current_gate_row, _evidence_invalid, _follows_current_g2, _older_than_days,
                    apply_status, base_unknown_components, current_gate_supply)
from .util import now_utc, slug_id, today_local

RESOLVE_STATES = ("resolved_merged", "resolved_distinct", "resolved_recheck", "dismissed")
REF_TABLES = {
    "candidate": ("candidate", "id", "id"),
    "demand_signal": ("demand_signal", "id", "candidate_id"),
    "evidence": ("evidence", "id", "candidate_id"),
    "supply_offer": ("supply_offer", "id", "candidate_id"),
    "cost_item": ("cost_item", "id", "candidate_id"),
}


def candidate_of_ref(conn, ref_type: str, ref_id: str) -> str | None:
    table, key, owner = REF_TABLES[ref_type]
    if ref_type == "candidate":
        row = conn.execute("SELECT id FROM candidate WHERE id=?", (ref_id,)).fetchone()
        return row["id"] if row else None
    row = conn.execute(f"SELECT {owner} AS owner FROM {table} WHERE {key}=?", (ref_id,)).fetchone()
    return row["owner"] if row else None


def list_reviews(conn, status: str = "open", limit: int = 100) -> list[dict]:
    rows = conn.execute(
        "SELECT * FROM review_item WHERE (? = 'all' OR status=?) ORDER BY created_at DESC LIMIT ?",
        (status, status, limit),
    ).fetchall()
    return [dict(row) for row in rows]


def resolve_review(conn, review_id: str, payload: dict) -> dict:
    row = conn.execute("SELECT * FROM review_item WHERE id=?", (review_id,)).fetchone()
    if row is None:
        raise AppError("复核项不存在", code="not_found", status=404)
    status = payload.get("status")
    if status not in RESOLVE_STATES:
        raise AppError("复核状态不合法", code="invalid_field", status=422,
                       details=[{"field": "status", "reason": f"允许值：{', '.join(RESOLVE_STATES)}"}])
    if row["status"] != "open":
        if row["status"] == status and (row["note"] or None) == (payload.get("note") or None):
            return {"id": review_id, "status": status, "changed": False, "candidate_status": None}
        raise AppError("复核项已处理", code="invalid_state", status=422,
                       details=[{"field": "status", "reason": f"当前状态 {row['status']}"}])
    note = payload.get("note") or row["note"]
    conn.execute("UPDATE review_item SET status=?, resolved_at=?, note=? WHERE id=?",
                 (status, now_utc(), note, review_id))
    candidate_id = candidate_of_ref(conn, row["ref_type"], row["ref_id"])
    candidate_status = None
    if candidate_id:
        # Only re-derives; a dismissed review never restores a failed/expired gate row.
        candidate_status, _ = apply_status(conn, candidate_id)
    return {"id": review_id, "status": status, "changed": True, "candidate_id": candidate_id,
            "candidate_status": candidate_status}


def _degrade_reason(conn, candidate_id: str, gate: str) -> tuple[str, str] | None:
    """Return (review_kind, reason) when a currently verified gate must be degraded."""
    row = _current_gate_row(conn, candidate_id, gate)
    if row is None or row["status"] != "verified":
        return None
    if _evidence_invalid(conn, row["evidence_id"]):
        return "evidence_expired", "引用证据已失效"
    supply_id = row["supply_offer_id"]
    if supply_id:
        supply = conn.execute("SELECT status, last_checked_at FROM supply_offer WHERE id=?", (supply_id,)).fetchone()
        if supply is not None:
            if supply["status"] == "invalid":
                return "supply_invalid", "所选货源标记失效"
            if _older_than_days(supply["last_checked_at"], 30):
                return "supply_invalid", "所选货源超过 30 天未复核（TTL）"
    if gate == "cost":
        # 与 state.effective_gate_status 同一口径：完整性只看当前有效成本集
        supply, _ = current_gate_supply(conn, candidate_id)
        unknown = base_unknown_components(conn, candidate_id, supply_id=supply)
        if unknown:
            return "cost_changed", f"成本角色未知：{', '.join(unknown)}"
    if gate in ("cost", "platform_policy") and not _follows_current_g2(conn, candidate_id, row):
        # 复用 §3.5 的当前 G2（含版本）一致性规则：GET 报 expired 的情形必须同样被物化
        reason = "与当前有效 G2 所选货源/版本不一致"
        return ("cost_changed", reason) if gate == "cost" else ("license_changed", reason)
    if row["expires_at"] and row["expires_at"] <= now_utc():
        return "gate_expired", "核验有效期已过"
    return None


def recompute(conn, cfg: dict, candidate_id: str | None = None) -> dict:
    """#21: materialize degradations deterministically; repeated runs do not append twice."""
    if candidate_id:
        candidates = [candidate_id]
    else:
        candidates = [row["id"] for row in conn.execute("SELECT id FROM candidate").fetchall()]
    downgraded = 0
    review_items = 0
    for cid in candidates:
        for gate in GATES:
            outcome = _degrade_reason(conn, cid, gate)
            if outcome is None:
                continue
            review_kind, reason = outcome
            before = conn.execute(
                "SELECT COUNT(*) AS n FROM review_item WHERE status='open' AND ref_gate=?", (gate,)
            ).fetchone()["n"]
            if append_downgrade(conn, cid, gate, f"recompute: {reason}", review_kind):
                downgraded += 1
                after = conn.execute(
                    "SELECT COUNT(*) AS n FROM review_item WHERE status='open' AND ref_gate=?", (gate,)
                ).fetchone()["n"]
                review_items += max(after - before, 0)
        apply_status(conn, cid)
    run_id = slug_id("r")
    conn.execute(
        "INSERT INTO run_record(id,run_type,trigger,logical_date,source_id,status,started_at,finished_at,"
        "items_found,items_new,items_dup,notes) VALUES (?,'recompute','manual',?,NULL,?,?,?,?,?,0,?)",
        (run_id, today_local(cfg["tz_offset_hours"]), "ok" if downgraded == 0 else "partial", now_utc(), now_utc(),
         len(candidates), downgraded, f"materialized_downgrades={downgraded} review_items={review_items}"),
    )
    return {"run_id": run_id, "candidates": len(candidates), "downgraded": downgraded,
            "review_items_created": review_items}
