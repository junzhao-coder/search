"""Evidence writes: #6 append, #7 invalidate (invalidating downgrades referencing gates)."""

from __future__ import annotations

from .errors import AppError
from .gates import add_review, append_downgrade, candidate_origin
from .state import GATES, apply_status
from .util import now_utc, slug_id

TYPES = ("demand", "supply_distribution", "cost", "platform_policy", "validity", "other")
FACT_KINDS = ("fact", "estimate", "assumption")


def add_evidence(conn, candidate_id: str, payload: dict) -> dict:
    origin = candidate_origin(conn, candidate_id)
    evidence_type = payload.get("evidence_type")
    if evidence_type not in TYPES:
        raise AppError("evidence_type 不合法", code="invalid_field", status=422,
                       details=[{"field": "evidence_type", "reason": f"允许值：{', '.join(TYPES)}"}])
    for field in ("source_url", "excerpt"):
        if not payload.get(field):
            raise AppError("证据字段不完整", code="invalid_field", status=422,
                           details=[{"field": field, "reason": "必填（无摘录不创建证据行）"}])
    fact_kind = payload.get("fact_kind") or "fact"
    if fact_kind not in FACT_KINDS:
        raise AppError("fact_kind 不合法", code="invalid_field", status=422,
                       details=[{"field": "fact_kind", "reason": "允许值：fact/estimate/assumption"}])
    signal_id = payload.get("demand_signal_id")
    if evidence_type == "demand" and not signal_id:
        # Deterministic auto-link so G1 is satisfiable in one call (documented in S2_CORE §差异).
        row = conn.execute(
            "SELECT id FROM demand_signal WHERE candidate_id=? AND superseded_by IS NULL"
            " ORDER BY version_no DESC LIMIT 1",
            (candidate_id,),
        ).fetchone()
        signal_id = row["id"] if row else None
    if signal_id:
        signal = conn.execute("SELECT candidate_id FROM demand_signal WHERE id=?", (signal_id,)).fetchone()
        if signal is None or signal["candidate_id"] != candidate_id:
            raise AppError("需求信号不属于本候选", code="invalid_field", status=422,
                           details=[{"field": "demand_signal_id", "reason": "必须属于本候选"}])
        if evidence_type != "demand":
            raise AppError("需求信号仅用于 demand 证据", code="invalid_field", status=422,
                           details=[{"field": "demand_signal_id", "reason": "其他类型留空"}])
        exists = conn.execute("SELECT id FROM evidence WHERE demand_signal_id=?", (signal_id,)).fetchone()
        if exists:
            raise AppError("该需求信号已有派生证据", code="conflict", status=409,
                           details=[{"field": "demand_signal_id", "reason": "1:1 唯一"}])
    evidence_id = slug_id("e")
    observed_at = payload.get("observed_at") or now_utc()
    conn.execute(
        "INSERT INTO evidence(id,candidate_id,evidence_type,demand_signal_id,source_id,source_url,native_id,excerpt,"
        "fact_kind,observed_at,expires_at,data_origin,import_batch_id,created_at)"
        " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,NULL,?)",
        (evidence_id, candidate_id, evidence_type, signal_id, payload.get("source_id"), payload["source_url"],
         payload.get("native_id"), payload["excerpt"], fact_kind, observed_at, payload.get("expires_at"), origin,
         now_utc()),
    )
    return {"id": evidence_id, "candidate_id": candidate_id, "evidence_type": evidence_type,
            "demand_signal_id": signal_id, "fact_kind": fact_kind, "observed_at": observed_at}


def invalidate_evidence(conn, evidence_id: str, reason: str | None) -> dict:
    row = conn.execute("SELECT * FROM evidence WHERE id=?", (evidence_id,)).fetchone()
    if row is None:
        raise AppError("证据不存在", code="not_found", status=404)
    if not reason:
        raise AppError("缺少 invalid_reason", code="invalid_field", status=422,
                       details=[{"field": "invalid_reason", "reason": "必填"}])
    if row["invalidated_at"]:
        return {"id": evidence_id, "candidate_id": row["candidate_id"], "changed": False,
                "invalidated_at": row["invalidated_at"]}
    stamp = now_utc()
    conn.execute("UPDATE evidence SET invalidated_at=?, invalid_reason=? WHERE id=?", (stamp, reason, evidence_id))
    candidate_id = row["candidate_id"]
    downgraded = []
    for gate in GATES:
        if append_downgrade(conn, candidate_id, gate, f"引用证据失效（{reason}）", "evidence_expired",
                            ref_type="evidence", ref_id=evidence_id):
            downgraded.append(gate)
    add_review(conn, "evidence_expired", "evidence", evidence_id, f"证据失效（{reason}）", row["data_origin"],
               ref_gate=None, blocking=1)
    # A supply that pointed at this clause evidence keeps the link but loses the verified basis.
    if row["evidence_type"] == "supply_distribution":
        supply = conn.execute("SELECT id FROM supply_offer WHERE license_evidence_id=?", (evidence_id,)).fetchone()
        if supply:
            add_review(conn, "license_changed", "supply_offer", supply["id"], "条款证据失效", row["data_origin"],
                       ref_gate="supply_distribution", blocking=1)
    apply_status(conn, candidate_id)
    return {"id": evidence_id, "candidate_id": candidate_id, "changed": True, "invalidated_at": stamp,
            "gate_downgraded": downgraded}
