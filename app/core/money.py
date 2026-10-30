"""Money/rate/minute rules (contract §0.3): integer minor units, no floats."""

from __future__ import annotations

import decimal
import re

YUAN_RE = re.compile(r"^\d{1,9}(\.\d{1,2})?$")

# `*_minor` equivalence whitelist (contract §4.2): each alias maps to its yuan column.
MONEY_MINOR_ALIASES = {
    "sale_price_minor": "sale_price",
    "supply_price_minor": "supply_price",
    "acquisition_cost_minor": "acquisition_cost",
    "procurement_unit_cost_minor": "procurement_unit_cost",
    "procurement_cost_minor": "procurement_cost",
    "procurement_recurring_cost_minor": "procurement_recurring_cost",
    "other_cost_minor": "other_cost",
    "manual_hourly_rate_minor": "manual_hourly_rate",
}

# Columns whose text form is a decimal amount in yuan (≤2 decimals).
MONEY_YUAN_COLUMNS = (
    "sale_price",
    "supply_price",
    "acquisition_cost",
    "procurement_unit_cost",
    "procurement_cost",
    "procurement_recurring_cost",
    "other_cost",
    "manual_hourly_rate",
)

BP_COLUMNS = ("platform_fee_bp", "payment_fee_bp", "refund_rate_bp")


def yuan_to_minor(text: str) -> int:
    """Decimal yuan string -> integer minor units. Raises ValueError on any other shape."""
    if not isinstance(text, str) or not YUAN_RE.match(text.strip()):
        raise ValueError("金额必须是十进制元字符串（最多 2 位小数）")
    return int((decimal.Decimal(text.strip()) * 100).to_integral_value(rounding=decimal.ROUND_HALF_UP))


def minor_int(value) -> int:
    """Whitelisted ``*_minor`` input: non-negative integer, bool rejected."""
    if isinstance(value, bool):
        raise ValueError("布尔值不是合法金额")
    if isinstance(value, int):
        if value < 0:
            raise ValueError("输入金额必须非负")
        return value
    if isinstance(value, str) and re.match(r"^\d+$", value.strip()):
        return int(value.strip())
    raise ValueError("_minor 列必须是非负整数")


def apply_rate(base_minor: int, bp: int) -> int:
    """ROUND_HALF_UP integer arithmetic: ``(base_minor * bp + 5000) // 10000``."""
    if base_minor < 0 or bp < 0:
        raise ValueError("费率金额仅对非负输入取整")
    return (base_minor * bp + 5000) // 10000


def labor_minor(minutes: int, hourly_rate_minor: int) -> int:
    """``(minutes * hourly_rate_minor + 30) // 60`` (½ 分向上)."""
    if minutes < 0 or hourly_rate_minor < 0:
        raise ValueError("人工金额仅对非负输入取整")
    return (minutes * hourly_rate_minor + 30) // 60


def format_minor(value) -> str:
    """Display convention: unknown -> 未知, known zero -> ¥0.00 (contract §0.4)."""
    if value is None:
        return "未知"
    return f"¥{value / 100:.2f}"
