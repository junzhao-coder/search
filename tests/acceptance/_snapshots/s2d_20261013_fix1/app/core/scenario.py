"""Scenario computation (contract §5.5, S2 scope).

Rules: ``sale_price`` never joins the cost sum; unknown roles/bases stay unknown (I16);
``amortize_orders`` and period normalization are S4 and are not computed here.
"""

from __future__ import annotations

from .errors import AppError
from .gates import selected_supply_id
from .money import apply_rate, labor_minor
from .state import PROCUREMENT_BASES

PER_ORDER_MONEY_ROLES = ("acquisition", "other")
PER_ORDER_RATE_ROLES = ("platform_fee", "payment_fee", "refund_reserve")
RUN_NOTE = "运行支出不计入本情景；摊销与季度/年度归一属 S4"


def _row_value(row) -> int | None:
    """Numeric value of a cost row (money/rate/minutes), or None when the role is unknown."""
    if row is None:
        return None
    if row["value_kind"] == "money":
        return row["money_minor"]
    if row["value_kind"] == "rate":
        return row["rate_bp"]
    if row["value_kind"] == "minutes":
        return row["minutes"]
    return None


def compute_scenario(conn, candidate_id: str, variant: str = "base") -> dict:
    candidate = conn.execute("SELECT * FROM candidate WHERE id=?", (candidate_id,)).fetchone()
    if candidate is None:
        raise AppError("候选不存在", code="not_found", status=404)
    selected = selected_supply_id(conn, candidate_id)
    has_supply = conn.execute(
        "SELECT COUNT(*) AS n FROM supply_offer WHERE candidate_id=? AND status<>'invalid'", (candidate_id,)
    ).fetchone()["n"] > 0
    rows = conn.execute(
        "SELECT * FROM cost_item WHERE candidate_id=? AND is_active=1 AND variant=? ORDER BY created_at",
        (candidate_id, variant),
    ).fetchall()

    def usable(row) -> bool:
        """§5.5-7: costs must belong to the selected supply; with no supply at all, plain rows count."""
        if not has_supply:
            return True
        return selected is not None and row["supply_offer_id"] == selected

    def pick(role: str, basis: str):
        for row in rows:
            if row["role"] == role and row["basis"] == basis:
                return row
        return None

    def matched(role: str, basis: str):
        row = pick(role, basis)
        return row if row is not None and usable(row) else None

    sale_row = pick("sale_price", "per_order")
    sale_price = _row_value(sale_row) if sale_row is not None and sale_row["value_kind"] == "money" else None
    currency = (sale_row["currency"] if sale_row is not None else "CNY")

    per_order: dict[str, int | None] = {}
    per_order["procurement_minor"] = _row_value(matched("procurement", "per_order"))
    for role in PER_ORDER_RATE_ROLES:
        row = matched(role, "per_order")
        bp = _row_value(row)
        if row is not None and bp is not None and row["value_kind"] == "rate":
            per_order[f"{role}_minor"] = apply_rate(sale_price, bp) if sale_price is not None else None
        elif row is not None and row["value_kind"] == "money":
            per_order[f"{role}_minor"] = _row_value(row)
        else:
            per_order[f"{role}_minor"] = None
    for role in PER_ORDER_MONEY_ROLES:
        per_order[f"{role}_minor"] = _row_value(matched(role, "per_order"))
    labor_row = matched("manual_labor", "per_order")
    if labor_row is not None and labor_row["minutes"] is not None and labor_row["hourly_rate_minor"] is not None:
        per_order["manual_labor_minor"] = labor_minor(labor_row["minutes"], labor_row["hourly_rate_minor"])
    else:
        per_order["manual_labor_minor"] = None

    unknown: list[str] = []
    if sale_price is None:
        unknown.append("sale_price")
    for key, value in per_order.items():
        if value is None:
            unknown.append(key.removesuffix("_minor"))
    for basis in PROCUREMENT_BASES:
        row = matched("procurement", basis)
        if row is None or _row_value(row) is None:
            unknown.append(f"procurement.{basis}")

    known_subtotal = sum(value for value in per_order.values() if value is not None)
    per_order_known = all(value is not None for value in per_order.values())
    contribution = (sale_price - known_subtotal) if (sale_price is not None and per_order_known) else None

    one_time_row = matched("procurement", "one_time")
    one_time = _row_value(one_time_row) if one_time_row is not None else None
    recurring_rows = [row for row in rows if row["basis"] == "recurring" and usable(row)]
    recurring_detail = [
        {"role": row["role"], "period": row["period"], "money_minor": row["money_minor"]} for row in recurring_rows
    ]
    # §5.5-4: the monthly total only exists when every recurring row is monthly and known.
    recurring_known = bool(recurring_rows) and all(row["money_minor"] is not None for row in recurring_rows)
    recurring_periods = {row["period"] for row in recurring_rows}
    recurring_total = None
    if recurring_known and recurring_periods == {"monthly"}:
        recurring_total = sum(row["money_minor"] for row in recurring_rows)

    # Completeness is decided on the recurring rows themselves: a NULL aggregate must never be read
    # as "zero", and non-monthly periods are not normalized in S2 (§5.5-2/-4).
    recurring_all_zero = recurring_known and all(row["money_minor"] == 0 for row in recurring_rows)
    positive_recurring = [row for row in recurring_rows if (row["money_minor"] or 0) > 0]

    fixed_cost_gap = None
    if one_time is not None and one_time > 0:
        fixed_cost_gap = one_time
    elif positive_recurring and len(recurring_periods) == 1:
        # 单一周期：缺口即原金额（带周期明细），不做月度归一
        fixed_cost_gap = sum(row["money_minor"] for row in positive_recurring)

    complete = bool(
        contribution is not None
        and not unknown
        and one_time == 0
        and recurring_all_zero
    )
    net = contribution if complete else None

    assumptions: list[str] = []
    for row in rows:
        if not usable(row):
            continue
        note = row["assumption_note"]
        if note:
            assumptions.append(f"{row['role']}.{row['basis']}: {note}")
        elif row["fact_kind"] != "fact":
            assumptions.append(f"{row['role']}.{row['basis']}: {row['fact_kind']}（未填说明，不构成 G3 依据）")

    explanation = [
        f"售价 {sale_price} 分不参与成本求和" if sale_price is not None else "售价未知：sale_price 缺失，贡献值不可计算",
        "未提供的采购 basis 与人工计价视为未知，不按 0 计算",
        RUN_NOTE,
    ]
    platform_row = matched("platform_fee", "per_order")
    if platform_row is not None and platform_row["value_kind"] == "rate" and sale_price is not None:
        explanation.insert(1, f"platform_fee = {platform_row['rate_bp']}bp × {sale_price} 分 = "
                              f"{per_order['platform_fee_minor']} 分（ROUND_HALF_UP）")
    if fixed_cost_gap is not None:
        explanation.append("存在正额一次性/周期成本且未给分摊假设：net 置空，缺口单列")
    if recurring_rows and recurring_periods != {"monthly"}:
        periods = "/".join(sorted(period for period in recurring_periods if period))
        explanation.append(f"存在非月度周期成本（period={periods}）：未归一，recurring_monthly_total_minor 为 null；"
                           f"原周期与金额见 recurring_detail")
    if positive_recurring and len(recurring_periods) > 1:
        explanation.append("周期成本周期不一致：未给出单一 fixed_cost_gap_minor（避免伪月额）；明细见 recurring_detail")

    return {
        "candidate_id": candidate_id,
        "variant": variant,
        "complete": complete,
        "sale_price_minor": sale_price,
        "currency": currency,
        "per_order": per_order,
        "known_subtotal_minor": known_subtotal,
        "contribution_per_order_minor": contribution,
        "net_per_order_minor": net,
        "one_time_total_minor": one_time,
        "fixed_cost_gap_minor": fixed_cost_gap,
        "recurring_monthly_total_minor": recurring_total,
        "recurring_detail": recurring_detail,
        "amortize_orders": None,
        "unknown_components": unknown,
        "assumptions": assumptions,
        "explanation": explanation,
        "selected_supply_id": selected,
        "cost_source_note": "成本仅取选定货源（或本候选无货源时的普通行）与同一 variant；其他货源价格不计入",
    }
