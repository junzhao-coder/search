"""Supply writes: #8 append, #9 update (price/clause changes trigger §3.4 downgrades)."""

from __future__ import annotations

import json

from .errors import AppError
from .gates import add_review, append_downgrade, candidate_origin
from .identity import url_norm
from .state import apply_status
from .util import now_utc, slug_id

LICENSE_FIELDS = ("commercial_allowed", "redistribute_allowed", "resale_allowed", "downloadable")
MUTABLE = ("provider_name", "provider_url", "native_id", "origin_type", "format_version", "unit_price_minor",
           "price_basis", "price_valid_until", "license_summary", "license_scope_note", "license_evidence_url",
           "commercial_allowed", "redistribute_allowed", "resale_allowed", "sample_checked", "sample_note",
           "status", "last_checked_at", "check_note")


def _bad(field: str, reason: str) -> AppError:
    return AppError("货源字段不合法", code="invalid_field", status=422, details=[{"field": field, "reason": reason}])


def add_supply(conn, candidate_id: str, payload: dict) -> dict:
    origin = candidate_origin(conn, candidate_id)
    for field in ("provider_name", "provider_url", "sample_checked"):
        if not payload.get(field):
            raise _bad(field, "必填")
    for field in LICENSE_FIELDS[:3]:
        if payload.get(field) not in ("yes", "no", "unknown"):
            raise _bad(field, "必填，取值 yes/no/unknown")
    if payload.get("sample_checked") not in ("none", "partial", "checked"):
        raise _bad("sample_checked", "取值 none/partial/checked")
    if payload["sample_checked"] != "none" and not payload.get("sample_note"):
        raise _bad("sample_note", "非 none 的抽检必须记录范围/结果/未核验部分")
    norm = url_norm(payload["provider_url"])
    version = payload.get("format_version") or ""
    existing = conn.execute(
        "SELECT id FROM supply_offer WHERE data_origin=? AND candidate_id=? AND url_norm=? AND format_version=?",
        (origin, candidate_id, norm, version),
    ).fetchone()
    if existing:
        raise AppError("同一货源（url_norm+format_version）已存在", code="conflict", status=409,
                       details=[{"field": "provider_url", "reason": "命中强键，请改用 PATCH 更新该货源"}])
    supply_id = slug_id("sp")
    now = now_utc()
    conn.execute(
        "INSERT INTO supply_offer(id,candidate_id,provider_name,provider_url,url_norm,native_id,origin_type,"
        "format_version,unit_price_minor,currency,price_basis,price_valid_until,license_summary,license_scope_note,"
        "license_evidence_url,downloadable,commercial_allowed,redistribute_allowed,resale_allowed,sample_checked,"
        "sample_note,status,last_checked_at,check_note,data_origin,created_at,updated_at)"
        " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (supply_id, candidate_id, payload["provider_name"], payload["provider_url"], norm, payload.get("native_id"),
         payload.get("origin_type") or "unknown", version, payload.get("unit_price_minor"), "CNY",
         payload.get("price_basis"), payload.get("price_valid_until"), payload.get("license_summary"),
         payload.get("license_scope_note"), payload.get("license_evidence_url"),
         payload.get("downloadable") or "unknown", payload["commercial_allowed"], payload["redistribute_allowed"],
         payload["resale_allowed"], payload["sample_checked"], payload.get("sample_note"),
         payload.get("status") or "candidate", payload.get("last_checked_at"), payload.get("check_note"),
         origin, now, now),
    )
    apply_status(conn, candidate_id)
    return {"id": supply_id, "candidate_id": candidate_id, "created": True}


def update_supply(conn, supply_id: str, payload: dict) -> dict:
    row = conn.execute("SELECT * FROM supply_offer WHERE id=?", (supply_id,)).fetchone()
    if row is None:
        raise AppError("货源不存在", code="not_found", status=404)
    changes = {k: v for k, v in payload.items() if k in MUTABLE}
    if not changes:
        raise _bad("body", "至少提供一个可改字段")
    for field in LICENSE_FIELDS:
        if field in changes and changes[field] not in ("yes", "no", "unknown"):
            raise _bad(field, "取值 yes/no/unknown")
    if "sample_checked" in changes and changes["sample_checked"] not in ("none", "partial", "checked"):
        raise _bad("sample_checked", "取值 none/partial/checked")
    if "status" in changes and changes["status"] not in ("candidate", "verified", "invalid", "stale"):
        raise _bad("status", "取值 candidate/verified/invalid/stale")
    if "unit_price_minor" in changes:
        price = changes["unit_price_minor"]
        if price is not None and (isinstance(price, bool) or not isinstance(price, int) or price < 0):
            raise _bad("unit_price_minor", "必须是非负整数或 null")
    if changes.get("provider_url"):
        changes["url_norm"] = url_norm(changes["provider_url"])
    effective = {key: (changes.get(key, row[key]) if key in MUTABLE or key == "url_norm" else row[key]) for key in row.keys()}
    if effective["sample_checked"] != "none" and not effective["sample_note"]:
        raise _bad("sample_note", "非 none 的抽检必须记录 sample_note")
    identical = all(row[key] == changes[key] for key in changes)
    if identical:
        return {"id": supply_id, "candidate_id": row["candidate_id"], "changed": False}

    price_changed = "unit_price_minor" in changes and changes["unit_price_minor"] != row["unit_price_minor"]
    version_changed = "format_version" in changes and changes["format_version"] != row["format_version"]
    clause_changed = any(
        key in changes and changes[key] != row[key]
        for key in ("commercial_allowed", "redistribute_allowed", "resale_allowed", "sample_checked", "sample_note",
                    "license_summary", "license_scope_note", "license_evidence_url")
    )
    invalidated = changes.get("status") == "invalid" and row["status"] != "invalid"

    sets = ", ".join(f"{key}=?" for key in changes)
    conn.execute(
        f"UPDATE supply_offer SET {sets}, updated_at=? WHERE id=?",
        list(changes.values()) + [now_utc(), supply_id],
    )
    candidate_id = row["candidate_id"]
    origin = row["data_origin"]
    downgraded = {"cost": False, "supply_distribution": False}
    if price_changed:
        downgraded["cost"] = append_downgrade(conn, candidate_id, "cost", "货源价格变化",
                                             "cost_changed", ref_type="supply_offer", ref_id=supply_id)
    if clause_changed or version_changed:
        downgraded["supply_distribution"] = append_downgrade(
            conn, candidate_id, "supply_distribution", "货源许可/版本/依据变化", "license_changed",
            ref_type="supply_offer", ref_id=supply_id)
    if invalidated:
        add_review(conn, "supply_invalid", "supply_offer", supply_id, "货源标记失效", origin,
                   ref_gate="supply_distribution", blocking=1)
        for gate in ("supply_distribution", "cost"):
            downgraded[gate] = append_downgrade(conn, candidate_id, gate, "货源失效",
                                                "supply_invalid", ref_type="supply_offer", ref_id=supply_id) \
                or downgraded.get(gate, False)
    apply_status(conn, candidate_id)
    return {"id": supply_id, "candidate_id": candidate_id, "changed": True, "fields": sorted(changes),
            "gate_downgraded": json.loads(json.dumps(downgraded))}
