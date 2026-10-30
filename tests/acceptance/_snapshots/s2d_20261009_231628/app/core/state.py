"""Status derivation (contract §3.3/§3.4): one function shared by reads and writes."""

from __future__ import annotations

import datetime as _dt

from ..core.util import now_utc

GATES = ("demand", "supply_distribution", "cost", "platform_policy")
REQUIRED_MONEY_ROLES = ("sale_price", "platform_fee", "payment_fee", "acquisition", "refund_reserve", "other")
PROCUREMENT_BASES = ("per_order", "one_time", "recurring")
SUPPLY_TTL_DAYS = 30


def _parse_at(value: str | None):
    if not value:
        return None
    try:
        return _dt.datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=_dt.timezone.utc)
    except (ValueError, TypeError):
        return None


def _older_than_days(value: str | None, days: int) -> bool:
    stamp = _parse_at(value)
    if stamp is None:
        return False
    return (_dt.datetime.now(_dt.timezone.utc) - stamp) >= _dt.timedelta(days=days)


def _current_gate_row(conn, candidate_id: str, gate: str):
    return conn.execute(
        "SELECT * FROM gate_review WHERE candidate_id=? AND gate=? ORDER BY seq DESC LIMIT 1",
        (candidate_id, gate),
    ).fetchone()


def _evidence_invalid(conn, evidence_id: str | None) -> bool:
    if not evidence_id:
        return False
    row = conn.execute("SELECT invalidated_at FROM evidence WHERE id=?", (evidence_id,)).fetchone()
    return bool(row and row["invalidated_at"])


def _supply_invalid(conn, supply_offer_id: str | None) -> bool:
    """Invalid or not re-checked within the 30-day supply TTL (contract §3.3 rule 1)."""
    if not supply_offer_id:
        return False
    row = conn.execute(
        "SELECT status, last_checked_at FROM supply_offer WHERE id=?", (supply_offer_id,)
    ).fetchone()
    if row is None:
        return False
    if row["status"] == "invalid":
        return True
    return _older_than_days(row["last_checked_at"], SUPPLY_TTL_DAYS)


def _blocking_reviews(conn, candidate_id: str) -> int:
    """Open blocking review items on the candidate itself or on any of its sub-records."""
    return conn.execute(
        "SELECT COUNT(*) AS n FROM review_item r WHERE r.status='open' AND r.blocking=1 AND ("
        " (r.ref_type='candidate' AND r.ref_id=?)"
        " OR (r.ref_type='demand_signal' AND r.ref_id IN (SELECT id FROM demand_signal WHERE candidate_id=?))"
        " OR (r.ref_type='evidence' AND r.ref_id IN (SELECT id FROM evidence WHERE candidate_id=?))"
        " OR (r.ref_type='supply_offer' AND r.ref_id IN (SELECT id FROM supply_offer WHERE candidate_id=?))"
        " OR (r.ref_type='cost_item' AND r.ref_id IN (SELECT id FROM cost_item WHERE candidate_id=?))"
        ")",
        (candidate_id, candidate_id, candidate_id, candidate_id, candidate_id),
    ).fetchone()["n"]


def base_unknown_components(conn, candidate_id: str, variant: str = "base") -> list[str]:
    """Unknown required cost roles/bases for one scenario variant (never treats missing as 0)."""
    rows = conn.execute(
        "SELECT role, basis, value_kind, money_minor, rate_bp, minutes, hourly_rate_minor "
        "FROM cost_item WHERE candidate_id=? AND is_active=1 AND variant=?",
        (candidate_id, variant),
    ).fetchall()
    known_roles: set[str] = set()
    known_bases: set[str] = set()
    labor_rate_known = False
    for row in rows:
        role, basis = row["role"], row["basis"]
        has_value = any(row[k] is not None for k in ("money_minor", "rate_bp", "minutes"))
        if role == "manual_labor":
            if row["minutes"] is not None and row["hourly_rate_minor"] is not None:
                known_roles.add(role)
            continue
        if has_value:
            known_roles.add(role)
            if role == "procurement":
                known_bases.add(basis)
    unknown: list[str] = []
    for role in REQUIRED_MONEY_ROLES:
        if role not in known_roles:
            unknown.append(role)
    for basis in PROCUREMENT_BASES:
        if basis not in known_bases:
            unknown.append(f"procurement.{basis}")
    if "manual_labor" not in known_roles:
        unknown.append("manual_labor")
    return unknown


def current_gate_supply(conn, candidate_id: str) -> tuple[str | None, str]:
    """Newest G2 row's supply plus its *effective* status (validity, not history).

    An older verified row must not stand in for the current selection once a newer
    expired/failed row exists (§3.3/§3.5).
    """
    row = _current_gate_row(conn, candidate_id, "supply_distribution")
    if row is None:
        return None, "unverified"
    return row["supply_offer_id"], effective_gate_status(conn, candidate_id, "supply_distribution")


def effective_gate_status(conn, candidate_id: str, gate: str) -> str:
    """Unverified when no review exists; otherwise the newest row, degraded when still invalid."""
    row = _current_gate_row(conn, candidate_id, gate)
    if row is None:
        return "unverified"
    status = row["status"]
    if status == "verified":
        if _evidence_invalid(conn, row["evidence_id"]) or _supply_invalid(conn, row["supply_offer_id"]):
            return "expired"
        if gate == "cost":
            unknown = base_unknown_components(conn, candidate_id)
            if unknown:
                return "expired"
        expires_at = row["expires_at"]
        if expires_at and expires_at <= now_utc():
            return "expired"
    return status


def recompute(conn, candidate_id: str) -> tuple[str, str]:
    """Return (status, reason) for a candidate; never writes."""
    cand = conn.execute(
        "SELECT manual_override FROM candidate WHERE id=?", (candidate_id,)
    ).fetchone()
    if cand is None:
        raise KeyError(candidate_id)
    override = cand["manual_override"]
    if override == "archived":
        return "archived", "override:archived"
    if override == "explore":
        return "explore", "override:explore"
    blocking = _blocking_reviews(conn, candidate_id)
    statuses = {gate: effective_gate_status(conn, candidate_id, gate) for gate in GATES}
    if blocking or any(s in ("expired", "failed") for s in statuses.values()):
        trigger = next((g for g, s in statuses.items() if s in ("expired", "failed")), "review_item")
        return "stale", f"stale:{trigger}"
    if all(s == "verified" for s in statuses.values()):
        return "testable", "derived:testable|gates_ok"
    return "pending", "derived:pending|gates_incomplete"


def apply_status(conn, candidate_id: str) -> tuple[str, str]:
    """Recompute and persist status (allowed write points per invariant I1)."""
    status, reason = recompute(conn, candidate_id)
    conn.execute(
        "UPDATE candidate SET status=?, status_reason=?, status_updated_at=? WHERE id=?",
        (status, reason, now_utc(), candidate_id),
    )
    return status, reason
