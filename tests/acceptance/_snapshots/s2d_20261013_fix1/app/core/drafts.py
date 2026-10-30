"""Drafts (#16 generate / #17 edit): template mode works standalone; no sending path exists."""

from __future__ import annotations

import json
import os

from .errors import AppError
from .gates import candidate_origin
from .money import format_minor
from .state import GATES, effective_gate_status
from .util import now_utc, slug_id

KINDS = ("listing_copy", "reply", "delivery_note")
METHODS = ("template", "model_assisted")
TEMPLATE_VERSION = "v1"


def model_configured() -> bool:
    return bool(os.environ.get("APP_MODEL_NAME"))


def _bad(field: str, reason: str) -> AppError:
    return AppError("草稿字段不合法", code="invalid_field", status=422, details=[{"field": field, "reason": reason}])


def _template_body(conn, candidate, kind: str) -> tuple[str, list[str]]:
    signals = conn.execute(
        "SELECT excerpt, url FROM demand_signal WHERE candidate_id=? AND superseded_by IS NULL", (candidate["id"],)
    ).fetchall()
    supplies = conn.execute(
        "SELECT provider_name, unit_price_minor, license_summary, license_scope_note, resale_allowed"
        " FROM supply_offer WHERE candidate_id=? AND status<>'invalid'", (candidate["id"],)
    ).fetchall()
    costs = conn.execute(
        "SELECT role, value_kind, money_minor, rate_bp, minutes FROM cost_item"
        " WHERE candidate_id=? AND is_active=1 AND role='sale_price'", (candidate["id"],)
    ).fetchall()
    refs = [row["id"] for row in conn.execute(
        "SELECT id FROM evidence WHERE candidate_id=? ORDER BY created_at", (candidate["id"],)
    ).fetchall()]
    gates = {gate: effective_gate_status(conn, candidate["id"], gate) for gate in GATES}
    demand_text = signals[0]["excerpt"] if signals else "【待补：需求原文摘录】"
    price_text = format_minor(costs[0]["money_minor"]) if costs and costs[0]["money_minor"] is not None else "【待补：售价假设】"
    supply_text = supplies[0]["provider_name"] if supplies else "【待补：现成货源】"
    lines = [f"商品标题：{candidate['title']}"]
    if kind == "listing_copy":
        lines += [
            f"需求依据：{demand_text}（未核验内容以占位标记，不写成保证）",
            f"货源：{supply_text}",
            f"售价参考：{price_text}",
            f"交付形式：{candidate['delivery_form'] or '【待补：交付形式】'}",
            "【待核验：平台发布条件】",
        ]
    elif kind == "reply":
        lines += [
            "感谢咨询，可以按您说的用途提供；具体交付时间与格式我确认后回复。",
            f"关联需求：{demand_text}",
            "【待核验：可答范围与售后口径】",
        ]
    else:
        lines += [
            "交付说明：下单后按约定格式发送文件/链接；请在收到后确认可用。",
            f"交付内容来源：{supply_text}",
            "【待核验：许可范围与再分发限制】",
        ]
    if gates["supply_distribution"] != "verified":
        lines.append("【待核验：货源许可与分发条件（G2 未通过）】")
    return "\n".join(lines), refs


def create_draft(conn, candidate_id: str, payload: dict) -> dict:
    kind = payload.get("kind")
    method = payload.get("method") or "template"
    if kind not in KINDS:
        raise _bad("kind", f"允许值：{', '.join(KINDS)}")
    if method not in METHODS:
        raise _bad("method", f"允许值：{', '.join(METHODS)}")
    if method == "model_assisted" and not model_configured():
        raise AppError("未配置模型，无法生成 model_assisted 草稿", code="invalid_state", status=422,
                       details=[{"field": "method", "reason": "未配置模型时应使用 template 模式"}])
    candidate = conn.execute("SELECT * FROM candidate WHERE id=?", (candidate_id,)).fetchone()
    if candidate is None:
        raise AppError("候选不存在", code="not_found", status=404)
    if method == "template":
        body, refs = _template_body(conn, candidate, kind)
        model_name = None
    else:
        body = payload.get("body") or "【模型草稿占位：未配置模型时不可生成】"
        refs = payload.get("evidence_refs") or []
        model_name = os.environ.get("APP_MODEL_NAME")
    draft_id = slug_id("dr")
    now = now_utc()
    conn.execute(
        "INSERT INTO draft(id,candidate_id,kind,method,body,evidence_refs_json,status,model_name,template_version,"
        "data_origin,created_at,updated_at) VALUES (?,?,?,?,?,?,'draft',?,?,?,?,?)",
        (draft_id, candidate_id, kind, method, payload.get("body") or body,
         json.dumps(refs, ensure_ascii=False), model_name, TEMPLATE_VERSION, candidate["data_origin"], now, now),
    )
    return {"id": draft_id, "candidate_id": candidate_id, "kind": kind, "method": method, "status": "draft",
            "template_version": TEMPLATE_VERSION, "evidence_refs": refs, "body": payload.get("body") or body,
            "created_at": now, "no_send_path": True}


def update_draft(conn, draft_id: str, payload: dict) -> dict:
    row = conn.execute("SELECT * FROM draft WHERE id=?", (draft_id,)).fetchone()
    if row is None:
        raise AppError("草稿不存在", code="not_found", status=404)
    unknown = [key for key in payload if key not in ("body", "status")]
    if unknown:
        raise AppError("草稿字段不合法", code="invalid_field", status=422,
                       details=[{"field": key, "reason": "仅 body/status 可改（无发送状态）"} for key in unknown])
    status = payload.get("status", row["status"])
    if status not in ("draft", "final"):
        raise _bad("status", "仅 draft/final（不存在已发送状态）")
    if row["status"] == "final" and status == "draft":
        raise AppError("不允许从 final 退回 draft", code="invalid_state", status=422,
                       details=[{"field": "status", "reason": "定稿后不可退回草稿"}])
    body = payload.get("body", row["body"])
    if body == row["body"] and status == row["status"]:
        return {"id": draft_id, "status": status, "changed": False, "updated_at": row["updated_at"]}
    now = now_utc()
    conn.execute("UPDATE draft SET body=?, status=?, updated_at=? WHERE id=?", (body, status, now, draft_id))
    return {"id": draft_id, "status": status, "changed": True, "updated_at": now}
