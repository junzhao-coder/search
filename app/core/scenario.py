"""Scenario computation (contract §5.5 + S4 increment, see docs/design/S4_SCENARIO_SPEC.md).

Rules: ``sale_price`` never joins the cost sum; unknown roles/bases stay unknown (I16).
S4 increment (opt-in only): ``amortize_orders`` (one-time amortization), ``monthly_orders``
(monthly sales volume) and ``normalize_periods`` (quarterly/yearly → monthly). Without them the
response is field-for-field the S2 one; ``fixed_cost_gap_minor`` always keeps the S2 amount/period
semantics and never becomes a monthly figure.
"""

from __future__ import annotations

from .errors import AppError
from .gates import selected_supply_id
from .money import apply_rate, labor_minor
from .state import PROCUREMENT_BASES

PER_ORDER_MONEY_ROLES = ("acquisition", "other")
PER_ORDER_RATE_ROLES = ("platform_fee", "payment_fee", "refund_reserve")
RUN_NOTE = "运行支出不计入本情景；摊销与季度/年度归一属 S4"
MAX_ASSUMPTION = 1_000_000
PERIOD_MONTHS = {"monthly": 12, "quarterly": 4, "yearly": 1}


def annualized_minor(period: str, amount_minor: int) -> int | None:
    """One recurring row in annual minor units (12/4/1), or ``None`` when the period is unknown.

    An unsupported period is never guessed as yearly: the caller treats ``None`` as "a unknown".
    """
    months = PERIOD_MONTHS.get(period)
    return None if months is None else amount_minor * months


def _round_half_up_div(numerator: int, denominator: int) -> int:
    """ROUND_HALF_UP integer division (non-negative numerator, positive denominator)."""
    return (2 * numerator + denominator) // (2 * denominator)


def _bad_field(field: str, reason: str) -> AppError:
    return AppError("情景参数不合法", code="invalid_field", status=422, details=[{"field": field, "reason": reason}])


def _assumption_orders(name: str, value) -> int | None:
    """Core-level guard: ints only (no bool/float/str), 1..MAX_ASSUMPTION, ``None`` = not given."""
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise _bad_field(name, f"必须是 1..{MAX_ASSUMPTION} 的整数（不接受 bool/float/字符串）")
    if not 1 <= value <= MAX_ASSUMPTION:
        raise _bad_field(name, f"必须在 1..{MAX_ASSUMPTION} 之间")
    return value


def _normalize_flag(value) -> bool:
    if not isinstance(value, bool):
        raise _bad_field("normalize_periods", "只接受布尔值（HTTP query 取 0/1）")
    return value



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


def compute_scenario(conn, candidate_id: str, variant: str = "base", *, amortize_orders=None,
                     monthly_orders=None, normalize_periods=False) -> dict:
    amortize_orders = _assumption_orders("amortize_orders", amortize_orders)
    monthly_orders = _assumption_orders("monthly_orders", monthly_orders)
    normalize_periods = _normalize_flag(normalize_periods)
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
    # §3.3 exact annualized amount a = 12*Σmonthly + 4*Σquarterly + Σyearly (never pre-rounded).
    # Normalization is opt-in: with the flag off a non-monthly row makes the total unavailable (S2).
    recurring_known = bool(recurring_rows) and all(row["money_minor"] is not None for row in recurring_rows)
    recurring_periods = {row["period"] for row in recurring_rows}
    yearly_equivalent = None
    if recurring_known:
        supported = recurring_periods <= set(PERIOD_MONTHS)
        if normalize_periods:
            parts = [annualized_minor(row["period"], row["money_minor"]) for row in recurring_rows]
            yearly_equivalent = None if any(part is None for part in parts) else sum(parts)
        elif recurring_periods == {"monthly"}:
            yearly_equivalent = 12 * sum(row["money_minor"] for row in recurring_rows)
        elif supported and all(row["money_minor"] == 0 for row in recurring_rows):
            yearly_equivalent = 0          # 全部显式 0：与周期无关的真零（保持 S2 可完整）
    monthly_display = (yearly_equivalent + 6) // 12 if yearly_equivalent is not None else None
    recurring_total = None
    if normalize_periods:
        recurring_total = monthly_display                      # S4: displayed normalized monthly amount
    elif recurring_known and recurring_periods == {"monthly"}:
        recurring_total = sum(row["money_minor"] for row in recurring_rows)   # S2 semantics

    recurring_all_zero = recurring_known and all(row["money_minor"] == 0 for row in recurring_rows)
    positive_recurring = [row for row in recurring_rows if (row["money_minor"] or 0) > 0]

    # §3.2/§3.4: per-order shares; the recurring one always divides the exact ``a`` (never the
    # displayed ``R``), and a positive ``a`` needs ``monthly_orders`` even when ``R`` shows 0.
    one_time_per_order = None
    if one_time == 0:
        one_time_per_order = 0
    elif one_time is not None and one_time > 0 and amortize_orders is not None:
        one_time_per_order = _round_half_up_div(one_time, amortize_orders)
    recurring_per_order = None
    if yearly_equivalent == 0:
        recurring_per_order = 0
    elif yearly_equivalent is not None and yearly_equivalent > 0 and monthly_orders is not None:
        recurring_per_order = _round_half_up_div(yearly_equivalent, 12 * monthly_orders)

    # S2 semantics kept: gap is the original one-time amount or the single-period recurring amount.
    fixed_cost_gap = None
    if one_time is not None and one_time > 0:
        fixed_cost_gap = one_time
    elif positive_recurring and len(recurring_periods) == 1:
        fixed_cost_gap = sum(row["money_minor"] for row in positive_recurring)

    assumptions_known = bool(
        one_time is not None
        and yearly_equivalent is not None
        and (one_time == 0 or amortize_orders is not None)
        and (yearly_equivalent == 0 or monthly_orders is not None)
    )
    complete = bool(contribution is not None and not unknown and assumptions_known)
    net = (contribution - (one_time_per_order or 0) - (recurring_per_order or 0)) if complete else None

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
    # --- explanation: 默认路径与 S2 逐项一致；显式给出假设时才按“实际行”列出阻塞原因 ---
    assumptions_given = bool(amortize_orders is not None or monthly_orders is not None or normalize_periods)
    # unknown_components 只覆盖 procurement 三 basis 与 per_order，故 recurring 行的未知要按行本身判定。
    unknown_recurring_rows = [row for row in recurring_rows
                              if row["money_minor"] is None or row["period"] not in PERIOD_MONTHS]
    if fixed_cost_gap is not None:
        if assumptions_given:
            explanation.append(f"fixed_cost_gap_minor={fixed_cost_gap} 分仍为 S2 原额/原周期提示")
        else:
            explanation.append("存在正额一次性/周期成本且未给分摊假设：net 置空，缺口单列")
    if recurring_rows and recurring_periods != {"monthly"} and not normalize_periods:
        periods = "/".join(sorted(period for period in recurring_periods if period))
        explanation.append(f"存在非月度周期成本（period={periods}）：未归一，recurring_monthly_total_minor 为 null；"
                           f"原周期与金额见 recurring_detail")
    if positive_recurring and len(recurring_periods) > 1 and not normalize_periods:
        explanation.append("周期成本周期不一致：未给出单一 fixed_cost_gap_minor（避免伪月额）；明细见 recurring_detail")
    if assumptions_given:
        if normalize_periods and yearly_equivalent is not None:
            remainder = yearly_equivalent - 12 * monthly_display
            explanation.append(f"已按 12/4/1 归一月额：精确年化额 a={yearly_equivalent} 分 → 显示月额 "
                               f"{monthly_display} 分（余分 r={remainder}，|r|≤6 仅为显示误差界；每单金额由 a 直接计算）")
        if net is None:
            if unknown_recurring_rows:
                explanation.append("存在 recurring 行金额或周期未知（见 recurring_detail）："
                                   "精确年化额 a 不可计算")
            if one_time is not None and one_time > 0 and amortize_orders is None:
                explanation.append("缺 amortize_orders：一次性成本每单摊销额未知")
            if yearly_equivalent is not None and yearly_equivalent > 0 and monthly_orders is None:
                explanation.append("缺 monthly_orders：周期成本每单额未知")
            if unknown:
                explanation.append("存在未知项（见 unknown_components）：net 置空")
        else:
            explanation.append(f"已按假设摊销：one_time_per_order={one_time_per_order} 分、"
                               f"recurring_per_order={recurring_per_order} 分 → net={net} 分")

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
        "amortize_orders": amortize_orders,
        "monthly_orders": monthly_orders,
        "normalized_periods": normalize_periods,
        "one_time_per_order_minor": one_time_per_order,
        "recurring_per_order_minor": recurring_per_order,
        "unknown_components": unknown,
        "assumptions": assumptions,
        "explanation": explanation,
        "selected_supply_id": selected,
        "cost_source_note": "成本仅取选定货源（或本候选无货源时的普通行）与同一 variant；其他货源价格不计入",
    }
