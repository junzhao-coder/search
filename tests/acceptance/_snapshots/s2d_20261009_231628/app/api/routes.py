"""HTTP routes (contract §5.3): imports, candidates, gates, scenario, drafts, feedback, reviews, runs.

Page routes are reserved stubs for the four planned pages (C owns templates):
``/``, ``/opportunity/<id>``, ``/import``, ``/ops`` answer 501 until templates are delivered.
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager

from flask import Blueprint, current_app, jsonify, render_template, request

from ..core import candidates as candidates_core
from ..core import costs, drafts, supplies
from ..core import evidence as evidence_core
from ..core import feedback as feedback_core
from ..core.errors import AppError
from ..core.gates import record_gate
from ..core.idempotency import client_ref_of, remember, replay
from ..core.importer import handle_import
from ..core.reviews import list_reviews, recompute, resolve_review
from ..core.scenario import compute_scenario
from ..core.state import GATES, effective_gate_status, recompute as derive_status
from ..core.util import now_utc
from ..storage.db import get_db, schema_version

bp = Blueprint("api", __name__, url_prefix="/api")
pages = Blueprint("pages", __name__)


def _cfg() -> dict:
    return current_app.config["APP_CFG"]


@contextmanager
def _tx(conn):
    """One business transaction per write request (idempotency record included)."""
    conn.execute("BEGIN")
    try:
        yield
    except sqlite3.IntegrityError as err:
        conn.execute("ROLLBACK")
        raise AppError(f"数据完整性约束拒绝：{err}", code="invalid_state", status=422) from err
    except Exception:
        conn.execute("ROLLBACK")
        raise
    conn.execute("COMMIT")


def _body() -> dict:
    payload = request.get_json(silent=True)
    if payload is None:
        payload = {}
    if not isinstance(payload, dict):
        raise AppError("请求体必须是 JSON 对象", code="invalid_field", status=422)
    return payload


def _write(conn, scope: str, perform, *, success: int = 200, body: dict | None = None):
    payload = _body() if body is None else body
    client_ref = client_ref_of(request.args, request.headers)
    stored, _ = replay(conn, scope, client_ref, payload)
    if stored is not None:
        stored = dict(stored)
        stored["deduplicated"] = True
        return jsonify(stored), 200
    with _tx(conn):
        result = perform()
        remember(conn, scope, client_ref, payload, result, result.get("id") or result.get("candidate_id"))
    return jsonify(result), success


# ------------------------------------------------------------------ health / sources / runs

@bp.get("/health")
def health():
    # Contract #24: version + schema status only (no stage label, no absolute paths).
    cfg = _cfg()
    return jsonify({
        "ok": True,
        "schema_version": schema_version(cfg["db_path"]),
        "time": now_utc(),
    })


@bp.get("/sources")
def list_sources():
    rows = get_db().execute(
        "SELECT id,name,channel,access_mode,access_verified,fields_available,rate_limit_note,cost_note,terms_note,"
        "last_success_at,last_error_at,last_error,enabled FROM source ORDER BY id"
    ).fetchall()
    return jsonify({"items": [dict(r) for r in rows]})


@bp.get("/runs")
def list_runs():
    db = get_db()
    try:
        limit = min(max(int(request.args.get("limit", 20)), 1), 200)
    except ValueError:
        raise AppError("limit 必须是整数", code="validation_failed")
    rows = db.execute(
        "SELECT id,run_type,trigger,logical_date,source_id,status,started_at,finished_at,items_found,items_new,"
        "items_dup,error_summary,notes FROM run_record ORDER BY started_at DESC LIMIT ?", (limit,)
    ).fetchall()
    return jsonify({"items": [dict(r) for r in rows]})


@bp.post("/runs/recompute")
def run_recompute():
    db = get_db()
    payload = _body()
    candidate_id = payload.get("candidate_id")
    with _tx(db):
        result = recompute(db, _cfg(), candidate_id)
    return jsonify(result), 200


# ------------------------------------------------------------------ imports

@bp.post("/imports")
def create_import():
    cfg = _cfg()
    db = get_db()
    mode = request.args.get("mode", "atomic")
    try:
        format_version = int(request.args.get("format_version", request.headers.get("X-Format-Version", 1)))
    except ValueError:
        raise AppError("format_version 必须是整数", code="unsupported_format")
    client_ref = client_ref_of(request.args, request.headers)
    fmt = request.args.get("format")
    filename = None
    if request.mimetype and request.mimetype.startswith("multipart/form-data"):
        upload = request.files.get("file")
        if upload is None:
            raise AppError("multipart 请求必须包含 file 字段", code="validation_failed")
        filename = upload.filename
        body = upload.read()
        if not fmt:
            fmt = "csv" if (filename or "").lower().endswith(".csv") else "json"
    else:
        body = request.get_data()
        if not fmt:
            if request.mimetype in ("text/csv", "application/csv", "text/plain"):
                fmt = "csv"
            elif request.is_json:
                fmt = "json"
    if not fmt:
        raise AppError("无法判定 format，请显式传入 ?format=csv|json", code="unsupported_format")
    if not body:
        raise AppError("请求体为空", code="validation_failed")
    payload, status, deduplicated = handle_import(
        db, cfg, fmt=fmt, body=body, filename=filename, mode=mode,
        format_version=format_version, client_ref=client_ref,
    )
    if deduplicated:
        payload = dict(payload)
        payload["deduplicated"] = True
    return jsonify(payload), status


@bp.get("/imports/<batch_id>")
def get_import(batch_id: str):
    db = get_db()
    batch = db.execute("SELECT * FROM import_batch WHERE id=?", (batch_id,)).fetchone()
    if batch is None:
        raise AppError("批次不存在", code="not_found", status=404)
    results = db.execute(
        "SELECT row_no, action, record_type, record_id, reason_code, reason_detail FROM import_row_result"
        " WHERE batch_id=? ORDER BY row_no, id", (batch_id,)
    ).fetchall()
    return jsonify({"batch": dict(batch), "row_results": [dict(r) for r in results]})


# ------------------------------------------------------------------ candidates

POOL_ORDER = {"testable": 0, "explore": 1, "pending": 2, "stale": 3, "archived": 4}


@bp.get("/candidates")
def list_candidates():
    db = get_db()
    try:
        page = max(int(request.args.get("page", 1)), 1)
        page_size = min(max(int(request.args.get("page_size", 50)), 1), 100)
    except ValueError:
        raise AppError("page/page_size 必须是整数", code="validation_failed")
    filters, params = [], []
    for column in ("status", "data_origin"):
        value = request.args.get(column)
        if value:
            filters.append(f"{column}=?")
            params.append(value)
    keyword = request.args.get("q")
    if keyword:
        filters.append("title LIKE ?")
        params.append(f"%{keyword}%")
    where = f" WHERE {' AND '.join(filters)}" if filters else ""
    total = db.execute(f"SELECT COUNT(*) AS n FROM candidate{where}", params).fetchone()["n"]
    sort = request.args.get("sort", "default")
    if sort == "updated_desc":
        order = "updated_at DESC, id"
    elif sort == "created_desc":
        order = "created_at DESC, id"
    else:
        order = (
            "CASE status WHEN 'testable' THEN 0 WHEN 'explore' THEN 1 WHEN 'pending' THEN 2"
            " WHEN 'stale' THEN 3 ELSE 4 END, updated_at DESC, id"
        )
    rows = db.execute(
        f"SELECT id,title,status,status_reason,data_origin,category,identity_key,created_at,updated_at"
        f" FROM candidate{where} ORDER BY {order} LIMIT ? OFFSET ?",
        params + [page_size, (page - 1) * page_size],
    ).fetchall()
    return jsonify({"items": [dict(r) for r in rows], "total": total, "page": page, "page_size": page_size})


@bp.get("/candidates/<candidate_id>")
def get_candidate(candidate_id: str):
    db = get_db()
    candidate = db.execute("SELECT * FROM candidate WHERE id=?", (candidate_id,)).fetchone()
    if candidate is None:
        raise AppError("候选不存在", code="not_found", status=404)
    signals = db.execute(
        "SELECT id,native_id,url,excerpt,signal_kind,published_at,published_date,observed_at,observed_at_source,"
        "content_hash,version_no,superseded_by,data_origin FROM demand_signal WHERE candidate_id=? ORDER BY version_no DESC",
        (candidate_id,),
    ).fetchall()
    evidences = db.execute(
        "SELECT id,evidence_type,source_url,excerpt,fact_kind,observed_at,expires_at,invalidated_at,invalid_reason"
        " FROM evidence WHERE candidate_id=? ORDER BY created_at DESC", (candidate_id,)
    ).fetchall()
    supplies_rows = db.execute(
        "SELECT id,provider_name,provider_url,origin_type,format_version,unit_price_minor,currency,price_basis,"
        "commercial_allowed,redistribute_allowed,resale_allowed,sample_checked,sample_note,status,"
        "license_evidence_url,license_evidence_id,last_checked_at FROM supply_offer WHERE candidate_id=?",
        (candidate_id,),
    ).fetchall()
    costs_rows = db.execute(
        "SELECT id,role,basis,value_kind,money_minor,rate_bp,minutes,hourly_rate_minor,period,variant,currency,"
        "fact_kind,assumption_note,is_active,supply_offer_id FROM cost_item WHERE candidate_id=? ORDER BY created_at",
        (candidate_id,),
    ).fetchall()
    gate_rows = {}
    for gate in GATES:
        row = db.execute(
            "SELECT id,seq,status,evidence_id,supply_offer_id,applies_to_platform,applies_to_version,verified_by,"
            "verified_at,expires_at,note FROM gate_review WHERE candidate_id=? AND gate=? ORDER BY seq DESC LIMIT 1",
            (candidate_id, gate),
        ).fetchone()
        if row is not None:
            gate_rows[gate] = dict(row)
    reviews = db.execute(
        "SELECT id,kind,ref_type,ref_id,ref_gate,ref_id_b,reason,status,blocking,created_at FROM review_item"
        " WHERE (ref_type='candidate' AND ref_id=?) OR ref_id IN (SELECT id FROM demand_signal WHERE candidate_id=?)"
        " OR ref_id IN (SELECT id FROM evidence WHERE candidate_id=?)"
        " OR ref_id IN (SELECT id FROM supply_offer WHERE candidate_id=?)"
        " OR ref_id IN (SELECT id FROM cost_item WHERE candidate_id=?)"
        " ORDER BY created_at DESC",
        (candidate_id, candidate_id, candidate_id, candidate_id, candidate_id),
    ).fetchall()
    drafts_rows = db.execute(
        "SELECT id,kind,method,status,template_version,model_name,created_at,updated_at FROM draft"
        " WHERE candidate_id=? ORDER BY created_at DESC", (candidate_id,)
    ).fetchall()
    feedback_rows = db.execute("SELECT * FROM feedback WHERE candidate_id=? ORDER BY occurred_at DESC",
                               (candidate_id,)).fetchall()
    status, status_reason = derive_status(db, candidate_id)
    return jsonify({
        "candidate": dict(candidate),
        "derived_status": status,
        "derived_status_reason": status_reason,
        "gates": {gate: effective_gate_status(db, candidate_id, gate) for gate in GATES},
        "gate_reviews": gate_rows,
        "demand_signals": [dict(r) for r in signals],
        "evidences": [dict(r) for r in evidences],
        "supplies": [dict(r) for r in supplies_rows],
        "cost_items": [dict(r) for r in costs_rows],
        "review_items": [dict(r) for r in reviews],
        "drafts": [dict(r) for r in drafts_rows],
        "feedback": [dict(r) for r in feedback_rows],
    })


@bp.post("/candidates/<candidate_id>/override")
def post_override(candidate_id: str):
    db = get_db()
    return _write(db, "override", lambda: candidates_core.set_override(db, candidate_id, _body()))


@bp.get("/candidates/<candidate_id>/scenario")
def get_scenario(candidate_id: str):
    variant = request.args.get("variant", "base")
    return jsonify(compute_scenario(get_db(), candidate_id, variant))


# ------------------------------------------------------------------ gates

@bp.post("/candidates/<candidate_id>/gates/<gate>")
def post_gate(candidate_id: str, gate: str):
    db = get_db()
    return _write(db, "gate", lambda: record_gate(db, candidate_id, gate, _body()))


# ------------------------------------------------------------------ evidence

@bp.post("/candidates/<candidate_id>/evidences")
def post_evidence(candidate_id: str):
    db = get_db()
    return _write(db, "evidence", lambda: evidence_core.add_evidence(db, candidate_id, _body()), success=201)


@bp.post("/evidences/<evidence_id>/invalidate")
def post_invalidate(evidence_id: str):
    db = get_db()
    return _write(db, "evidence", lambda: evidence_core.invalidate_evidence(db, evidence_id, _body().get("invalid_reason")))


# ------------------------------------------------------------------ supplies

@bp.post("/candidates/<candidate_id>/supplies")
def post_supply(candidate_id: str):
    db = get_db()
    return _write(db, "supply", lambda: supplies.add_supply(db, candidate_id, _body()), success=201)


@bp.patch("/supplies/<supply_id>")
def patch_supply(supply_id: str):
    db = get_db()
    return _write(db, "supply", lambda: supplies.update_supply(db, supply_id, _body()))


# ------------------------------------------------------------------ costs

@bp.post("/candidates/<candidate_id>/cost-items")
def post_cost_item(candidate_id: str):
    db = get_db()
    return _write(db, "cost_item", lambda: costs.add_cost_item(db, candidate_id, _body()), success=201)


@bp.post("/cost-items/<cost_id>/supersede")
def post_supersede(cost_id: str):
    db = get_db()
    return _write(db, "cost_item", lambda: costs.supersede_cost_item(db, cost_id, _body()))


# ------------------------------------------------------------------ drafts

@bp.post("/candidates/<candidate_id>/drafts")
def post_draft(candidate_id: str):
    db = get_db()
    return _write(db, "draft", lambda: drafts.create_draft(db, candidate_id, _body()), success=201)


@bp.patch("/drafts/<draft_id>")
def patch_draft(draft_id: str):
    db = get_db()
    return _write(db, "draft", lambda: drafts.update_draft(db, draft_id, _body()))


# ------------------------------------------------------------------ feedback

@bp.post("/candidates/<candidate_id>/feedback")
def post_feedback(candidate_id: str):
    db = get_db()
    return _write(db, "feedback", lambda: feedback_core.create_feedback(db, candidate_id, _body()), success=201)


@bp.patch("/feedback/<feedback_id>")
def patch_feedback(feedback_id: str):
    db = get_db()
    return _write(db, "feedback", lambda: feedback_core.update_feedback(db, feedback_id, _body()))


# ------------------------------------------------------------------ reviews

@bp.get("/review-items")
def get_review_items():
    status = request.args.get("status", "open")
    try:
        limit = min(max(int(request.args.get("limit", 100)), 1), 500)
    except ValueError:
        raise AppError("limit 必须是整数", code="validation_failed")
    return jsonify({"items": list_reviews(get_db(), status, limit)})


@bp.post("/review-items/<review_id>/resolve")
def post_resolve_review(review_id: str):
    db = get_db()
    return _write(db, "review_item", lambda: resolve_review(db, review_id, _body()))


# ------------------------------------------------------------------ pages (S2-C minimal local UI)

GATE_LABELS = {
    "demand": "需求",
    "supply_distribution": "货源及分发条件",
    "cost": "成本",
    "platform_policy": "对应平台发布条件",
}
GATE_STATUS_LABELS = {
    "verified": "已核验",
    "unverified": "未核验",
    "pending": "待处理",
    "expired": "已过期",
    "failed": "未通过",
}
GATE_HINTS = {
    "demand": "缺少可复查的需求证据：来源链接／原文摘录／观察时间",
    "supply_distribution": "缺少选定货源或分发条件证据（许可原文、抽检范围）",
    "cost": "关键费用未知或缺依据：未知不按 0 处理",
    "platform_policy": "缺少对应平台的发布条件证据（平台／版本适用）",
}
POOL_LABELS = {
    "testable": "可测试池",
    "explore": "探索池（弱证据高潜力）",
    "pending": "待核验",
    "stale": "已失效",
    "archived": "已归档",
}
ORIGIN_LABELS = {"real": "真实市场数据", "synthetic": "合成测试数据"}


def _api_json(path: str, query: dict | None = None) -> tuple[int, dict]:
    """Read the frozen JSON API in-process: pages never query the database directly."""
    resp = current_app.test_client().get(path, query_string=query or {})
    payload = resp.get_json(silent=True)
    return resp.status_code, (payload if isinstance(payload, dict) else {})


def _money(value) -> str:
    """Unknown stays unknown; an explicit zero is shown as ¥0.00."""
    if value is None:
        return "未知"
    return f"¥{value / 100:.2f}"


def _tri_state(value) -> str:
    """yes/no/unknown come from the contract as strings; both must not read as truthy."""
    if value is True or value == "yes":
        return "是"
    if value is False or value == "no":
        return "否"
    if value in (None, "", "unknown"):
        return "未知"
    return str(value)


def _render(template: str, nav: str, **context):
    base = {
        "nav": nav,
        "money": _money,
        "tri_state": _tri_state,
        "pool_labels": POOL_LABELS,
        "origin_labels": ORIGIN_LABELS,
        "gate_labels": GATE_LABELS,
        "gate_status_labels": GATE_STATUS_LABELS,
        "gate_hints": GATE_HINTS,
    }
    base.update(context)
    return render_template(template, **base)


def _detail_failure(status: int, payload: dict) -> str:
    error = payload.get("error") if isinstance(payload.get("error"), dict) else {}
    return error.get("message") or f"接口返回 HTTP {status}"


@pages.get("/")
def page_home():
    return _render("home.html", "home")


@pages.get("/opportunity/<candidate_id>")
def page_opportunity(candidate_id: str):
    status, detail = _api_json(f"/api/candidates/{candidate_id}")
    if status != 200:
        message = _detail_failure(status, detail)
        code = 404 if status == 404 else 502
        return _render("not_found.html", "home", candidate_id=candidate_id, message=message), code
    scenario_status, scenario = _api_json(f"/api/candidates/{candidate_id}/scenario", {"variant": "base"})
    if scenario_status != 200:
        return _render(
            "opportunity.html", "home", detail=detail, scenario={},
            scenario_error=_detail_failure(scenario_status, scenario),
        )
    return _render("opportunity.html", "home", detail=detail, scenario=scenario, scenario_error=None)


@pages.get("/import")
def page_import():
    status, sources = _api_json("/api/sources")
    return _render(
        "import_page.html", "import",
        sources=sources.get("items", []) if status == 200 else [],
        sources_error=None if status == 200 else _detail_failure(status, sources),
    )


@pages.get("/ops")
def page_ops():
    status, runs = _api_json("/api/runs", {"limit": 50})
    return _render(
        "ops.html", "ops",
        runs=runs.get("items", []) if status == 200 else [],
        runs_error=None if status == 200 else _detail_failure(status, runs),
    )
