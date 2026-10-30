"""Candidate-level manual override (#12)."""

from __future__ import annotations

from .errors import AppError
from .gates import candidate_origin
from .state import apply_status
from .util import now_utc

OVERRIDES = ("none", "explore", "archived")


def set_override(conn, candidate_id: str, payload: dict) -> dict:
    candidate_origin(conn, candidate_id)
    override = payload.get("manual_override")
    if override not in OVERRIDES:
        raise AppError("manual_override 不合法", code="invalid_field", status=422,
                       details=[{"field": "manual_override", "reason": f"允许值：{', '.join(OVERRIDES)}"}])
    reason = payload.get("override_reason")
    if override != "none" and not reason:
        raise AppError("缺少 override_reason", code="invalid_field", status=422,
                       details=[{"field": "override_reason", "reason": "非 none 的人工分池必须写明原因"}])
    now = now_utc()
    conn.execute(
        "UPDATE candidate SET manual_override=?, override_reason=?, override_at=? WHERE id=?",
        (override, reason, now if override != "none" else None, candidate_id),
    )
    status, status_reason = apply_status(conn, candidate_id)
    return {"candidate_id": candidate_id, "manual_override": override, "override_reason": reason,
            "candidate_status": status, "candidate_status_reason": status_reason}
