"""Cost item writes: #26 append and #10 supersede, both with the §3.4 in-transaction downgrade."""

from __future__ import annotations

from .errors import AppError
from .gates import append_downgrade, candidate_origin
from .state import apply_status
from .util import now_utc, slug_id

ROLES = ("sale_price", "procurement", "platform_fee", "payment_fee", "acquisition", "refund_reserve",
         "manual_labor", "other")
BASES = ("per_order", "one_time", "recurring")
PERIODS = ("monthly", "quarterly", "yearly")


def _bad(field: str, reason: str) -> AppError:
    return AppError("成本项字段不合法", code="invalid_field", status=422, details=[{"field": field, "reason": reason}])


def _spec(payload: dict) -> dict:
    role = payload.get("role")
    basis = payload.get("basis")
    if role not in ROLES:
        raise _bad("role", f"允许值：{', '.join(ROLES)}")
    if basis not in BASES:
        raise _bad("basis", f"允许值：{', '.join(BASES)}")
    value_kind = payload.get("value_kind")
    money, rate, minutes = payload.get("money_minor"), payload.get("rate_bp"), payload.get("minutes")
    hourly = payload.get("hourly_rate_minor")
    provided = [name for name, value in (("money_minor", money), ("rate_bp", rate), ("minutes", minutes))
                if value is not None]
    if len(provided) > 1:
        raise _bad("value_kind", "money_minor/rate_bp/minutes 至多一个非空")
    if value_kind is None:
        if provided:
            raise _bad("value_kind", "提供值列时必须声明 value_kind")
    else:
        if value_kind not in ("money", "rate", "minutes"):
            raise _bad("value_kind", "允许值：money/rate/minutes 或省略（未知）")
        expected = {"money": "money_minor", "rate": "rate_bp", "minutes": "minutes"}[value_kind]
        if provided != [expected]:
            raise _bad("value_kind", f"value_kind={value_kind} 必须且只能提供 {expected}")
    if value_kind == "rate" and basis != "per_order":
        raise _bad("basis", "rate 仅允许 basis=per_order")
    if value_kind == "minutes" and role != "manual_labor":
        raise _bad("role", "minutes 仅允许 role=manual_labor")
    if hourly is not None and role != "manual_labor":
        raise _bad("hourly_rate_minor", "仅 manual_labor 可填费率")
    for name, value, limit in (("money_minor", money, None), ("rate_bp", rate, 10000), ("minutes", minutes, 1440),
                               ("hourly_rate_minor", hourly, None)):
        if value is None:
            continue
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise _bad(name, "必须是非负整数")
        if limit is not None and value > limit:
            raise _bad(name, f"必须 ≤ {limit}")
    period = payload.get("period")
    if basis == "recurring":
        if period not in PERIODS:
            raise _bad("period", f"recurring 必须提供 period（{', '.join(PERIODS)}）")
    elif period is not None:
        raise _bad("period", "period 仅 recurring 可填")
    fact_kind = payload.get("fact_kind") or "assumption"
    if fact_kind not in ("fact", "estimate", "assumption"):
        raise _bad("fact_kind", "允许值：fact/estimate/assumption")
    return {
        "role": role,
        "basis": basis,
        "value_kind": value_kind,
        "money_minor": money,
        "rate_bp": rate,
        "minutes": minutes,
        "hourly_rate_minor": hourly,
        "period": period,
        "variant": payload.get("variant") or "base",
        "currency": payload.get("currency") or "CNY",
        "fact_kind": fact_kind,
        "assumption_note": payload.get("assumption_note"),
        "supply_offer_id": payload.get("supply_offer_id"),
        "source_evidence_id": payload.get("source_evidence_id"),
    }


def _insert(conn, candidate_id, spec, supersedes_id=None) -> str:
    cost_id = slug_id("ci")
    now = now_utc()
    conn.execute(
        "INSERT INTO cost_item(id,candidate_id,supply_offer_id,role,basis,value_kind,money_minor,rate_bp,minutes,"
        "hourly_rate_minor,period,variant,currency,fact_kind,source_evidence_id,assumption_note,is_active,"
        "supersedes_id,data_origin,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,1,?,?,?)",
        (cost_id, candidate_id, spec["supply_offer_id"], spec["role"], spec["basis"], spec["value_kind"],
         spec["money_minor"], spec["rate_bp"], spec["minutes"], spec["hourly_rate_minor"], spec["period"],
         spec["variant"], spec["currency"], spec["fact_kind"], spec["source_evidence_id"], spec["assumption_note"],
         supersedes_id, candidate_origin(conn, candidate_id), now),
    )
    return cost_id


def _active_row(conn, candidate_id, role, basis, variant):
    return conn.execute(
        "SELECT * FROM cost_item WHERE candidate_id=? AND role=? AND basis=? AND variant=? AND is_active=1",
        (candidate_id, role, basis, variant),
    ).fetchone()


def _same(row, spec) -> bool:
    return bool(
        row
        and row["value_kind"] == spec["value_kind"]
        and row["money_minor"] == spec["money_minor"]
        and row["rate_bp"] == spec["rate_bp"]
        and row["minutes"] == spec["minutes"]
        and row["hourly_rate_minor"] == spec["hourly_rate_minor"]
        and (row["period"] or None) == (spec["period"] or None)
        and (row["assumption_note"] or None) == (spec["assumption_note"] or None)
    )


def _touch_candidate(conn, candidate_id, *, recheck_cost_gate: bool, reason: str) -> bool:
    downgraded = False
    if recheck_cost_gate:
        downgraded = append_downgrade(conn, candidate_id, "cost", reason, "cost_changed")
    apply_status(conn, candidate_id)
    return downgraded


def add_cost_item(conn, candidate_id: str, payload: dict) -> dict:
    candidate_origin(conn, candidate_id)
    spec = _spec(payload)
    active = _active_row(conn, candidate_id, spec["role"], spec["basis"], spec["variant"])
    if _same(active, spec):
        return {"id": active["id"], "created": False, "candidate_id": candidate_id}
    if active is not None:
        conn.execute("UPDATE cost_item SET is_active=0 WHERE id=?", (active["id"],))
    cost_id = _insert(conn, candidate_id, spec, active["id"] if active else None)
    downgraded = _touch_candidate(conn, candidate_id, recheck_cost_gate=spec["variant"] == "base",
                                  reason="成本项新增/取代导致成本门槛失效")
    return {"id": cost_id, "created": True, "candidate_id": candidate_id, "superseded_id": active["id"] if active else None,
            "gate_downgraded": downgraded}


def supersede_cost_item(conn, cost_id: str, payload: dict) -> dict:
    row = conn.execute("SELECT * FROM cost_item WHERE id=?", (cost_id,)).fetchone()
    if row is None:
        raise AppError("成本项不存在", code="not_found", status=404)
    merged = dict(payload)
    merged.setdefault("role", row["role"])
    merged.setdefault("basis", row["basis"])
    merged.setdefault("variant", row["variant"])
    merged.setdefault("currency", row["currency"])
    # Context fields are inherited unless the caller states otherwise, so a plain value correction
    # does not silently drop the supply link that G3/scenario matching relies on.
    merged.setdefault("supply_offer_id", row["supply_offer_id"])
    merged.setdefault("source_evidence_id", row["source_evidence_id"])
    spec = _spec(merged)
    if (spec["role"], spec["basis"], spec["variant"]) != (row["role"], row["basis"], row["variant"]):
        raise _bad("role", "取代必须保持同 role/basis/variant（改为新增另一项）")
    if not row["is_active"]:
        raise AppError("该成本项已被取代", code="invalid_state", status=422,
                       details=[{"field": "is_active", "reason": "只能取代当前活跃项"}])
    if _same(row, spec):
        return {"id": row["id"], "created": False, "candidate_id": row["candidate_id"]}
    conn.execute("UPDATE cost_item SET is_active=0 WHERE id=?", (row["id"],))
    new_id = _insert(conn, row["candidate_id"], spec, row["id"])
    downgraded = _touch_candidate(conn, row["candidate_id"], recheck_cost_gate=spec["variant"] == "base",
                                  reason="成本项取代导致成本门槛失效")
    return {"id": new_id, "created": True, "superseded_id": row["id"], "candidate_id": row["candidate_id"],
            "gate_downgraded": downgraded}
