"""Gate verification write path (contract §3.5) + same-transaction downgrade (§3.4).

``verified_by='user'`` for API writes; only ``system_rule`` rows are created by downgrades.
"""

from __future__ import annotations

import datetime as _dt

from .errors import AppError
from .state import GATES, apply_status, base_unknown_components, current_gate_supply
from .util import now_utc, slug_id

GATE_TTL_DAYS = {"demand": 90, "supply_distribution": 30, "cost": 30, "platform_policy": 180}
CLAUSE_EVIDENCE_TYPES = ("supply_distribution",)


def candidate_origin(conn, candidate_id: str) -> str:
    row = conn.execute("SELECT data_origin FROM candidate WHERE id=?", (candidate_id,)).fetchone()
    if row is None:
        raise AppError("候选不存在", code="not_found", status=404)
    return row["data_origin"]


def add_review(conn, kind, ref_type, ref_id, reason, origin, *, ref_gate=None, ref_id_b=None, blocking=0) -> None:
    """Pending-unique review item (contract §1.9); duplicates are silently ignored."""
    if kind == "dup_suspect" and ref_id_b:
        ref_id, ref_id_b = sorted([ref_id, ref_id_b])
    conn.execute(
        "INSERT INTO review_item(id,kind,ref_type,ref_id,ref_gate,ref_id_b,reason,status,blocking,created_at,data_origin)"
        " VALUES (?,?,?,?,?,?,?,'open',?,?,?) ON CONFLICT DO NOTHING",
        (slug_id("rv"), kind, ref_type, ref_id, ref_gate, ref_id_b, reason, blocking, now_utc(), origin),
    )


def append_downgrade(conn, candidate_id: str, gate: str, reason: str, review_kind: str, *,
                     ref_type: str = "candidate", ref_id: str | None = None, blocking: int = 1) -> bool:
    """§3.4: append ``seq=max+1``/``expired``/``system_rule`` only when the current row is verified."""
    current = conn.execute(
        "SELECT * FROM gate_review WHERE candidate_id=? AND gate=? ORDER BY seq DESC LIMIT 1",
        (candidate_id, gate),
    ).fetchone()
    if current is None or current["status"] != "verified":
        return False
    next_seq = conn.execute(
        "SELECT COALESCE(MAX(seq),0)+1 AS n FROM gate_review WHERE candidate_id=? AND gate=?",
        (candidate_id, gate),
    ).fetchone()["n"]
    conn.execute(
        "INSERT INTO gate_review(id,candidate_id,gate,seq,status,evidence_id,supply_offer_id,applies_to_platform,"
        "applies_to_version,verified_by,verified_at,expires_at,note,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (slug_id("g"), candidate_id, gate, next_seq, "expired", current["evidence_id"], current["supply_offer_id"],
         current["applies_to_platform"], current["applies_to_version"], "system_rule", now_utc(), None, reason, now_utc()),
    )
    add_review(conn, review_kind, ref_type, ref_id or candidate_id, reason,
               candidate_origin(conn, candidate_id), ref_gate=gate, blocking=blocking)
    return True


def downgrade_cost_gate_if_verified(conn, candidate_id: str, reason: str) -> bool:
    return append_downgrade(conn, candidate_id, "cost", reason, "cost_changed")


def gate_expires_at(conn, gate: str, evidence_id: str | None, verified_at: str) -> str:
    """§3.2: min(evidence.expires_at ∪ verified_at + gate TTL), NULL ignored."""
    stamp = _dt.datetime.strptime(verified_at, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=_dt.timezone.utc)
    values = [(stamp + _dt.timedelta(days=GATE_TTL_DAYS[gate])).strftime("%Y-%m-%dT%H:%M:%SZ")]
    if evidence_id:
        row = conn.execute("SELECT expires_at FROM evidence WHERE id=?", (evidence_id,)).fetchone()
        if row is not None and row["expires_at"]:
            values.append(row["expires_at"])
    return min(values)


def selected_supply_id(conn, candidate_id: str) -> str | None:
    """Cost-matching reference for scenario costing (§5.5-7).

    Uses the *current* G2 selection only while it is still effectively verified (newest row +
    validity, not history); otherwise a single active supply is a purely numeric estimate that
    never lets a gate pass.
    """
    supply, status = current_gate_supply(conn, candidate_id)
    if status == "verified" and supply:
        return supply
    rows = conn.execute(
        "SELECT id FROM supply_offer WHERE candidate_id=? AND status<>'invalid'", (candidate_id,)
    ).fetchall()
    return rows[0]["id"] if len(rows) == 1 else None


# ------------------------------------------------------------------ admission (§3.5)

def _evidence_row(conn, evidence_id, candidate_id, details, field="evidence_id"):
    if not evidence_id:
        details.append({"field": field, "reason": "verified 状态必须引用证据"})
        return None
    row = conn.execute("SELECT * FROM evidence WHERE id=?", (evidence_id,)).fetchone()
    if row is None:
        details.append({"field": field, "reason": "证据不存在"})
        return None
    if row["candidate_id"] != candidate_id:
        details.append({"field": field, "reason": "证据不属于本候选"})
        return None
    if row["invalidated_at"]:
        details.append({"field": field, "reason": "证据已失效（invalidated_at 非空），不能支撑 verified"})
    if row["expires_at"] and row["expires_at"] <= now_utc():
        details.append({"field": field, "reason": f"证据已过期（expires_at={row['expires_at']}）"})
    return row


def _gate_reference_supply(conn, candidate_id: str, payload: dict, gate: str, details) -> str | None:
    """§3.5: G3/G4 follow the *current* G2 selection; a payload supply may not override it.

    Requiring a currently verified G2 keeps the single-supply estimate (§5.5-7 fallback) from
    upgrading any gate.
    """
    g2_supply, g2_status = current_gate_supply(conn, candidate_id)
    claimed = payload.get("supply_offer_id")
    if claimed:
        row = conn.execute("SELECT id, candidate_id FROM supply_offer WHERE id=?", (claimed,)).fetchone()
        if row is None or row["candidate_id"] != candidate_id:
            details.append({"field": "supply_offer_id", "reason": f"{gate}: 货源不属于本候选"})
            claimed = None
    if g2_status != "verified" or not g2_supply:
        details.append({
            "field": "supply_offer_id",
            "reason": f"{gate}: 需要当前已核验的 G2 货源作为基准（当前 supply_distribution={g2_status}）；"
                      f"单一货源估算仅供情景计价，不升级门槛",
        })
        return None
    if claimed and claimed != g2_supply:
        details.append({
            "field": "supply_offer_id",
            "reason": f"{gate}: 传入货源与当前 G2 已核验选择不一致；G3/G4 遵从当前 G2 选择",
        })
    return g2_supply


def _check_demand(conn, candidate_id, payload, details) -> None:
    evidence = _evidence_row(conn, payload.get("evidence_id"), candidate_id, details)
    if evidence is None:
        return
    if evidence["evidence_type"] != "demand":
        details.append({"field": "evidence_id", "reason": "G1: 证据类型必须为 demand"})
    if not (evidence["source_url"] and evidence["excerpt"] and evidence["observed_at"]):
        details.append({"field": "evidence_id", "reason": "G1: 证据需要 source_url/excerpt/observed_at"})
    signal_id = evidence["demand_signal_id"]
    if not signal_id:
        details.append({"field": "evidence_id", "reason": "G1: 需求证据必须由本候选的需求信号派生"})
        return
    signal = conn.execute("SELECT * FROM demand_signal WHERE id=?", (signal_id,)).fetchone()
    if signal is None or signal["candidate_id"] != candidate_id:
        details.append({"field": "evidence_id", "reason": "G1: 需求信号不属于本候选"})
        return
    if signal["signal_kind"] == "seller_promo":
        details.append({"field": "signal_kind", "reason": "G1: 卖家宣传不构成需求资格"})


def _check_supply(conn, candidate_id, payload, details) -> None:
    supply_id = payload.get("supply_offer_id")
    if not supply_id:
        details.append({"field": "supply_offer_id", "reason": "G2: 必须指定本次核验的货源"})
        return
    supply = conn.execute("SELECT * FROM supply_offer WHERE id=?", (supply_id,)).fetchone()
    if supply is None or supply["candidate_id"] != candidate_id:
        details.append({"field": "supply_offer_id", "reason": "G2: 货源不属于本候选"})
        return
    if supply["status"] == "invalid":
        details.append({"field": "supply_offer_id", "reason": "G2: 货源已标记失效"})
    for field in ("commercial_allowed", "redistribute_allowed", "resale_allowed"):
        if supply[field] != "yes":
            details.append({
                "field": field,
                "reason": f"G2: {field}='{supply[field]}'，本用途不允许（no/unknown 均不自动通过）；"
                          f"如认为本用途不适用，请补 license_scope_note 与条款摘录，门槛保持待复核",
            })
    if supply["sample_checked"] == "none":
        details.append({"field": "sample_checked", "reason": "G2: 抽样验货为 none"})
    elif not supply["sample_note"]:
        details.append({"field": "sample_note", "reason": "G2: 非 none 的抽检必须记录范围/结果/未核验部分"})
    clause_id = payload.get("evidence_id") or supply["license_evidence_id"]
    if not clause_id:
        details.append({"field": "evidence_id", "reason": "G2: 需要条款证据（license_evidence_id 或本次 evidence_id）"})
    else:
        clause = _evidence_row(conn, clause_id, candidate_id, details)
        if clause is not None and clause["evidence_type"] not in CLAUSE_EVIDENCE_TYPES:
            details.append({"field": "evidence_id", "reason": "G2: 条款证据类型应为 supply_distribution"})


def _check_cost(conn, candidate_id, payload, details) -> None:
    unknown = base_unknown_components(conn, candidate_id)
    for item in unknown:
        details.append({"field": item, "reason": f"G3: {item} 未知；未提供的成本不按 0 计算"})
    rows = conn.execute(
        "SELECT * FROM cost_item WHERE candidate_id=? AND is_active=1 AND variant='base'", (candidate_id,)
    ).fetchall()
    for row in rows:
        has_value = any(row[k] is not None for k in ("money_minor", "rate_bp", "minutes"))
        if not has_value:
            continue
        basis_ok = (row["fact_kind"] == "fact" and row["source_evidence_id"]) or row["assumption_note"]
        if not basis_ok:
            details.append({
                "field": f"{row['role']}.{row['basis']}",
                "reason": "G3: 该行既无 fact+依据，也无明确假设说明（assumption_note）",
            })
    selected = _gate_reference_supply(conn, candidate_id, payload, "G3", details)
    if selected:
        for row in rows:
            if row["role"] != "procurement":
                continue
            if row["supply_offer_id"] != selected:
                details.append({
                    "field": f"procurement.{row['basis']}",
                    "reason": "G3: 采购成本未绑定 G2 所选货源（未绑定或指向其他货源不计入本次核验）",
                })


def _check_platform(conn, candidate_id, payload, details) -> None:
    evidence = _evidence_row(conn, payload.get("evidence_id"), candidate_id, details)
    if evidence is not None and evidence["evidence_type"] != "platform_policy":
        details.append({"field": "evidence_id", "reason": "G4: 证据类型必须为 platform_policy"})
    platform = payload.get("applies_to_platform")
    if not platform:
        details.append({"field": "applies_to_platform", "reason": "G4: 必填（首版固定 xianyu）"})
    elif platform != "xianyu":
        details.append({"field": "applies_to_platform", "reason": "G4: 首版仅 xianyu"})
    version = payload.get("applies_to_version")
    if not version:
        details.append({"field": "applies_to_version", "reason": "G4: 必填，须与所选货源 format_version 一致或为 *"})
        return
    selected = _gate_reference_supply(conn, candidate_id, payload, "G4", details)
    if version != "*" and selected:
        supply = conn.execute("SELECT format_version FROM supply_offer WHERE id=?", (selected,)).fetchone()
        if supply is not None and version != supply["format_version"]:
            details.append({
                "field": "applies_to_version",
                "reason": f"G4: 版本 {version} 与所选货源 format_version={supply['format_version']!r} 不一致",
            })


ADMISSION = {
    "demand": _check_demand,
    "supply_distribution": _check_supply,
    "cost": _check_cost,
    "platform_policy": _check_platform,
}


def _resolve_context(conn, candidate_id: str, gate: str, payload: dict) -> dict:
    """Effective evidence/supply actually used for admission, TTL, persistence and the response.

    §3.5-G2: when ``evidence_id`` is omitted the supply's ``license_evidence_id`` is the clause
    evidence, and that default must be stored on the row (not only used during admission).
    """
    resolved = dict(payload)
    if gate == "supply_distribution":
        supply_id = payload.get("supply_offer_id")
        if supply_id:
            supply = conn.execute(
                "SELECT id, candidate_id, license_evidence_id FROM supply_offer WHERE id=?", (supply_id,)
            ).fetchone()
            if supply is not None and supply["candidate_id"] == candidate_id:
                resolved["evidence_id"] = payload.get("evidence_id") or supply["license_evidence_id"]
    return resolved


def record_gate(conn, candidate_id: str, gate: str, payload: dict) -> dict:
    """#11: record one gate verification; returns the new row plus the re-derived candidate status."""
    if gate not in GATES:
        raise AppError("门槛名不合法", code="invalid_field", status=422,
                       details=[{"field": "gate", "reason": f"允许值：{', '.join(GATES)}"}])
    status = payload.get("status")
    if status not in ("unverified", "verified", "failed", "expired"):
        raise AppError("status 不合法", code="invalid_field", status=422,
                       details=[{"field": "status", "reason": "允许值：unverified/verified/failed/expired"}])
    candidate_origin(conn, candidate_id)
    resolved = _resolve_context(conn, candidate_id, gate, payload) if status == "verified" else dict(payload)
    details: list[dict] = []
    if status == "verified":
        ADMISSION[gate](conn, candidate_id, resolved, details)
    if details:
        raise AppError("门槛准入不满足", code="invalid_state", status=422, details=details)
    verified_at = now_utc()
    expires_at = gate_expires_at(conn, gate, resolved.get("evidence_id"), verified_at) if status == "verified" else None
    seq = conn.execute(
        "SELECT COALESCE(MAX(seq),0)+1 AS n FROM gate_review WHERE candidate_id=? AND gate=?", (candidate_id, gate)
    ).fetchone()["n"]
    gate_id = slug_id("g")
    conn.execute(
        "INSERT INTO gate_review(id,candidate_id,gate,seq,status,evidence_id,supply_offer_id,applies_to_platform,"
        "applies_to_version,verified_by,verified_at,expires_at,note,created_at) VALUES (?,?,?,?,?,?,?,?,?,'user',?,?,?,?)",
        (gate_id, candidate_id, gate, seq, status, resolved.get("evidence_id"), resolved.get("supply_offer_id"),
         resolved.get("applies_to_platform"), resolved.get("applies_to_version"), verified_at, expires_at,
         resolved.get("note"), verified_at),
    )
    candidate_status, reason = apply_status(conn, candidate_id)
    return {
        "id": gate_id,
        "candidate_id": candidate_id,
        "gate": gate,
        "seq": seq,
        "status": status,
        "evidence_id": resolved.get("evidence_id"),
        "supply_offer_id": resolved.get("supply_offer_id"),
        "verified_by": "user",
        "verified_at": verified_at,
        "expires_at": expires_at,
        "candidate_status": candidate_status,
        "candidate_status_reason": reason,
    }
