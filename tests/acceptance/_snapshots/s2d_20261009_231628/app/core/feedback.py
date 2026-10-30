"""Business feedback events (#18 create) and the #27 update whitelist.

I4: ``predicted_*`` is a server-generated snapshot, immutable afterwards;
``actual_net_per_order_minor``/``actual_complete`` stay NULL in S2 (read-only).
"""

from __future__ import annotations

from .errors import AppError
from .gates import candidate_origin
from .scenario import compute_scenario
from .util import now_utc, slug_id

KINDS = ("inquiry", "sale", "refund", "expense", "manual_time", "note")
SERVER_FIELDS = ("predicted_net_per_order_minor", "predicted_snapshot_at", "actual_net_per_order_minor",
                 "actual_complete")
MUTABLE_FIELDS = ("refund_state", "note", "actual_minutes", "actual_hourly_rate_minor")
EXPENSE_KINDS = ("procurement", "platform", "acquisition", "run", "other")
EXPENSE_BASES = ("per_order", "one_time", "recurring")


def _bad(field: str, reason: str) -> AppError:
    return AppError("反馈字段不合法", code="invalid_field", status=422, details=[{"field": field, "reason": reason}])


def _int_or_none(payload: dict, name: str, *, minimum: int = 0, maximum: int | None = None):
    value = payload.get(name)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise _bad(name, f"必须是 ≥ {minimum} 的整数")
    if maximum is not None and value > maximum:
        raise _bad(name, f"必须 ≤ {maximum}")
    return value


def create_feedback(conn, candidate_id: str, payload: dict) -> dict:
    origin = candidate_origin(conn, candidate_id)
    for field in SERVER_FIELDS:
        if field in payload:
            raise _bad(field, "服务端生成或 S2 只读字段，客户端不得提交")
    kind = payload.get("kind")
    if kind not in KINDS:
        raise _bad("kind", f"允许值：{', '.join(KINDS)}")
    occurred_at = payload.get("occurred_at") or now_utc()
    quantity = _int_or_none(payload, "quantity", minimum=1)
    unit_price = _int_or_none(payload, "unit_price_minor")
    amount = _int_or_none(payload, "amount_minor")
    order_ref = payload.get("order_ref")
    note = payload.get("note")
    related_id = payload.get("related_feedback_id")
    refund_state = payload.get("refund_state")
    expense_kind = payload.get("expense_kind")
    expense_basis = payload.get("expense_basis")
    minutes = _int_or_none(payload, "actual_minutes", maximum=1440)
    hourly = _int_or_none(payload, "actual_hourly_rate_minor")
    predicted = None

    if kind == "sale":
        if amount is None and not (quantity is not None and unit_price is not None):
            raise _bad("amount_minor", "成交必须提供 amount_minor 或（quantity + unit_price_minor）")
        if order_ref:
            exists = conn.execute(
                "SELECT id FROM feedback WHERE candidate_id=? AND kind='sale' AND order_ref=?",
                (candidate_id, order_ref),
            ).fetchone()
            if exists:
                raise AppError("该订单号已记录成交", code="conflict", status=409,
                               details=[{"field": "order_ref", "reason": "同候选同 order_ref 唯一"}])
        scenario = compute_scenario(conn, candidate_id)
        predicted = scenario["net_per_order_minor"]  # snapshot; incomplete scenario -> NULL (never inferred as 0)
    elif kind == "refund":
        if not refund_state or refund_state not in ("pending", "settled"):
            raise _bad("refund_state", "退款必须提供 pending/settled")
        if not related_id:
            raise _bad("related_feedback_id", "退款必须关联同候选同 origin 的成交")
        sale = conn.execute("SELECT * FROM feedback WHERE id=?", (related_id,)).fetchone()
        if sale is None or sale["kind"] != "sale":
            raise _bad("related_feedback_id", "关联记录不存在或不是成交")
        if sale["candidate_id"] != candidate_id or sale["data_origin"] != origin:
            raise _bad("related_feedback_id", "必须指向同候选同 data_origin 的成交")
        if order_ref and sale["order_ref"] and order_ref != sale["order_ref"]:
            raise _bad("order_ref", "与关联成交的 order_ref 不一致")
        order_ref = order_ref or sale["order_ref"]
        if amount is None:
            raise _bad("amount_minor", "退款必须提供金额")
    elif kind == "expense":
        if expense_kind not in EXPENSE_KINDS:
            raise _bad("expense_kind", f"必填，允许值：{', '.join(EXPENSE_KINDS)}")
        if expense_basis is not None and expense_basis not in EXPENSE_BASES:
            raise _bad("expense_basis", f"允许值：{', '.join(EXPENSE_BASES)}")
        if amount is None:
            raise _bad("amount_minor", "支出必须提供金额")
    elif kind == "manual_time":
        if minutes is None:
            raise _bad("actual_minutes", "manual_time 必须提供 actual_minutes（0..1440）")
    else:  # inquiry / note
        if payload.get("refund_state") is not None or minutes is not None or hourly is not None:
            raise _bad("kind", "该事件类型不接受退款状态或人工时间字段")

    if kind != "manual_time" and (minutes is not None or hourly is not None):
        raise _bad("actual_minutes", "人工时间字段仅 kind='manual_time' 可写")
    if kind != "refund" and refund_state is not None:
        raise _bad("refund_state", "仅 kind='refund' 可写")

    feedback_id = slug_id("fb")
    now = now_utc()
    conn.execute(
        "INSERT INTO feedback(id,candidate_id,kind,order_ref,related_feedback_id,occurred_at,quantity,"
        "unit_price_minor,amount_minor,currency,expense_kind,expense_basis,refund_state,"
        "predicted_net_per_order_minor,predicted_snapshot_at,actual_minutes,actual_hourly_rate_minor,note,"
        "data_origin,created_at) VALUES (?,?,?,?,?,?,?,?,?,'CNY',?,?,?,?,?,?,?,?,?,?)",
        (feedback_id, candidate_id, kind, order_ref, related_id, occurred_at, quantity, unit_price, amount,
         expense_kind, expense_basis, refund_state, predicted, now if kind == "sale" else None, minutes, hourly,
         note, origin, now),
    )
    return {"id": feedback_id, "candidate_id": candidate_id, "kind": kind, "occurred_at": occurred_at,
            "order_ref": order_ref, "amount_minor": amount, "refund_state": refund_state,
            "actual_minutes": minutes, "actual_hourly_rate_minor": hourly,
            "predicted_net_per_order_minor": predicted, "predicted_snapshot_at": now if kind == "sale" else None,
            "actual_net_per_order_minor": None, "actual_complete": None, "created_at": now}


def update_feedback(conn, feedback_id: str, payload: dict) -> dict:
    row = conn.execute("SELECT * FROM feedback WHERE id=?", (feedback_id,)).fetchone()
    if row is None:
        raise AppError("反馈不存在", code="not_found", status=404)
    for field in SERVER_FIELDS:
        if field in payload:
            raise AppError("禁止改写预测/实际核算字段", code="invalid_field", status=422,
                           details=[{"field": field, "reason": "写入后不可改（I4）：预测快照与 S2 只读实际字段"}])
    unknown = [key for key in payload if key not in MUTABLE_FIELDS]
    if unknown:
        raise AppError("字段不在更新白名单", code="invalid_field", status=422,
                       details=[{"field": key, "reason": f"白名单：{', '.join(MUTABLE_FIELDS)}"} for key in unknown])
    if not payload:
        raise _bad("body", "至少提供一个白名单字段")
    if "refund_state" in payload:
        if row["kind"] != "refund":
            raise _bad("refund_state", "仅 kind='refund' 可改")
        if payload["refund_state"] not in ("pending", "settled"):
            raise _bad("refund_state", "允许值：pending/settled")
    if "actual_minutes" in payload or "actual_hourly_rate_minor" in payload:
        if row["kind"] != "manual_time":
            raise _bad("actual_minutes", "人工时间字段仅 kind='manual_time' 可改")
    changes = {}
    for key in MUTABLE_FIELDS:
        if key not in payload:
            continue
        value = payload[key]
        if key == "actual_minutes":
            value = _int_or_none(payload, key, maximum=1440)
            if value is None:
                raise _bad(key, "manual_time 必须提供 actual_minutes")
        elif key == "actual_hourly_rate_minor":
            value = _int_or_none(payload, key)
        changes[key] = value
    identical = all((row[key] or None) == (changes[key] if changes[key] is not None else None) for key in changes) \
        and all(row[key] == changes[key] for key in changes if changes[key] is not None)
    if identical:
        return {"id": feedback_id, "changed": False}
    sets = ", ".join(f"{key}=?" for key in changes)
    conn.execute(f"UPDATE feedback SET {sets} WHERE id=?", list(changes.values()) + [feedback_id])
    return {"id": feedback_id, "changed": True, "updated_fields": sorted(changes)}
