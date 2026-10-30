"""S4-B1 离线货源匹配：只读判断（设计 docs/design/S4_MATCHING_SPEC.md v2）。

契约要点
--------
* **只读**：本模块只执行 SELECT，绝不 INSERT/UPDATE/DELETE、不开事务、不建复核、不改门槛或
  候选状态；``match_supplies`` 可被 GET 类读取路径或调用方直接使用（设计 §3/§4）。
* **H1（硬约束）**：仅名称相似**不做**任何相似度计算（不产出 ``name_only_similarity``）；
  "供应商自称可转售"只做**固定关键词表子串命中**（见 ``SELF_CLAIM_KEYWORDS``，实现批冻结，
  不改语义），且仅当 ``resale_allowed`` 或 ``commercial_allowed`` 不为 ``yes`` 时产出
  ``self_claim_only``。命中**绝不**升级许可字段或门槛。
* **H2（硬约束）**：货源失效 / 许可或价格变化 / 供应商 TTL / 门槛到期均**只读反映**既有状态
  （``gate_review.note`` 文本映射为 reason），不新增 review kind、不写库（设计 §5.2）。
* 用途维在当前模型下恒为 ``hint_only``（无受控词表），因此非排除项最高只能到
  ``needs_review``；``adaptable`` 保留给未来受控词表落地后使用（设计 §2/§5.1）。

返回结构（设计 §3）::

    {"candidate_id", "current_g2_supply_id", "is_current_g2_valid",
     "items": [{"supply_offer_id", "level", "is_selected_by_g2", "dims", "reasons",
                "gaps", "gate_refs"}],
     "gaps": [...], "display_note": DISPLAY_NOTE}
"""

from __future__ import annotations

import datetime as _dt

from .gates import selected_supply_id
from .state import GATES, SUPPLY_TTL_DAYS, current_gate_supply, effective_gate_status
from .util import now_utc

#: H1 固定关键词表（子串命中即"供应商自称可转售"；不做相似度/模糊匹配）。
SELF_CLAIM_KEYWORDS = ("可转售", "可商用", "可二次分发", "可转授权", "授权齐全")

DISPLAY_NOTE = "匹配结果仅供挑选与复核，不构成门槛核验或证据。"

LEVELS = ("adaptable", "needs_review", "not_applicable", "excluded")
DIMS = ("用途", "内容版本", "交付形式", "适用条件")
GAPS = ("no_supply_rows", "license_unknown", "scope_text_only", "format_unknown",
        "no_cost_binding_to_g2", "g2_not_verified", "dims_text_only", "g4_baseline_undefined")
_LICENSE_FIELDS = ("commercial_allowed", "redistribute_allowed", "resale_allowed")


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


def _self_claim(row) -> bool:
    """H1: fixed keyword substring hit AND a license value is not ``yes``."""
    text = " ".join(filter(None, (row["license_summary"], row["license_scope_note"], row["check_note"])))
    if not any(keyword in text for keyword in SELF_CLAIM_KEYWORDS):
        return False
    return row["resale_allowed"] != "yes" or row["commercial_allowed"] != "yes"


def _gate_rows(conn, candidate_id: str) -> dict[str, object]:
    """Latest gate_review row per gate (read-only)."""
    rows = {}
    for gate in GATES:
        rows[gate] = conn.execute(
            "SELECT gate, seq, status, supply_offer_id, applies_to_version, expires_at, note"
            " FROM gate_review WHERE candidate_id=? AND gate=? ORDER BY seq DESC LIMIT 1",
            (candidate_id, gate),
        ).fetchone()
    return rows


def _reason_from_note(note: str | None) -> str | None:
    """Map an existing degradation note to a design reason code (H2; read-only reflection)."""
    if not note:
        return None
    if "G2 所选货源/版本变更" in note:
        # gates._downgrade_selectors_for_new_g2 的物化原因：换货源/版本不符 ≠ 许可变化；
        # 设计 §5.2 未为它定义 reason，故不标（gate_refs 已显示 expired），不得冒充 license_changed。
        return None
    if "TTL" in note:
        return "supply_ttl_expired"
    if "失效" in note:
        return "supply_invalid"
    if "有效期" in note:
        return "gate_expired"
    if "价格" in note or "成本" in note:
        return "cost_changed"
    if "许可" in note or "版本" in note or "依据" in note or "不一致" in note:
        return "license_changed"
    return None


def _baseline_version(conn, gate_rows: dict, g2_supply: str | None, selected: str | None) -> str | None:
    """G4 comparison basis: G4 row's applies_to_version, else current G2/fallback supply version."""
    g4 = gate_rows.get("platform_policy")
    if g4 is not None and g4["applies_to_version"]:
        return g4["applies_to_version"]
    for supply_id in (g2_supply, selected):
        if supply_id:
            row = conn.execute("SELECT format_version FROM supply_offer WHERE id=?", (supply_id,)).fetchone()
            if row is not None:
                return row["format_version"]
    return None


def _effective_reason(row, supply_row) -> str | None:
    """H2 read-only reflection: why a gate row is (effectively) expired, mirroring §3.3/§3.4 order.

    Only **substantiated** causes yield a reason. The remaining cause for a verified row is
    "no longer follows the current valid G2" (supply switch / version mismatch), which the design
    (§5.2) defines no reason for — return ``None`` rather than mislabel it as a license change
    (``gate_refs`` already reports ``expired``).
    """
    if row["status"] != "verified":
        return _reason_from_note(row["note"])
    if supply_row is not None and (
        supply_row["status"] == "invalid" or _older_than_days(supply_row["last_checked_at"], SUPPLY_TTL_DAYS)
    ):
        return "supply_invalid" if supply_row["status"] == "invalid" else "supply_ttl_expired"
    if row["expires_at"] and row["expires_at"] <= now_utc():
        return "gate_expired"
    return None


def _judge_supply(conn, candidate_id: str, row, *, baseline_version: str | None, is_valid_g2: bool,
                  g2_supply: str | None, gate_states: dict) -> dict:
    supply_id = row["id"]
    dims: dict[str, str] = {}
    reasons: list[str] = []
    gaps: list[str] = []
    excluded = row["status"] == "invalid" or _older_than_days(row["last_checked_at"], SUPPLY_TTL_DAYS)

    if excluded:
        reasons.append("supply_invalid" if row["status"] == "invalid" else "supply_ttl_expired")
        dims = {dim: "excluded" for dim in DIMS}
    else:
        dims["用途"] = "hint_only"                       # 无受控词表：恒人工阅读
        gaps.append("dims_text_only")

        if not baseline_version or not row["format_version"]:
            dims["内容版本"] = "gap"
            gaps.append("format_unknown")
        elif baseline_version == "*" or row["format_version"] == baseline_version:
            dims["内容版本"] = "ok"
        else:
            dims["内容版本"] = "not_applicable"           # 明确不一致（设计 M-10）
            gaps.append("format_unknown")

        if row["downloadable"] == "yes":
            dims["交付形式"] = "ok"
        elif row["downloadable"] == "no":
            dims["交付形式"] = "not_applicable"
        else:
            dims["交付形式"] = "gap"

        licenses = [row[field] for field in _LICENSE_FIELDS]
        if "no" in licenses:
            dims["适用条件"] = "not_applicable"
        elif "unknown" in licenses:
            dims["适用条件"] = "gap"
            gaps.append("license_unknown")
        elif row["sample_checked"] == "none" or not row["sample_note"]:
            dims["适用条件"] = "gap"                     # 未抽检/无抽检记录：不足以判定
        elif row["price_valid_until"] and row["price_valid_until"] < now_utc():
            dims["适用条件"] = "gap"                     # 价格有效期已过：时效信息不可用
        else:
            dims["适用条件"] = "ok"

        if _self_claim(row):
            reasons.append("self_claim_only")

    # H2: reflect existing degraded gate rows that point at *this* supply (never create).
    for gate, (gate_row, effective) in gate_states.items():
        if gate_row is None or gate_row["supply_offer_id"] != supply_id or effective != "expired":
            continue
        reason = _effective_reason(gate_row, row)
        if reason and reason not in reasons:
            reasons.append(reason)

    if excluded:
        level = "excluded"
    elif "not_applicable" in dims.values():
        level = "not_applicable"
    else:
        # 用途恒 hint_only ⇒ 当前模型不可达 adaptable（设计 §2/§5.1：不得因文本相似升级）
        level = "needs_review"

    refs = [{"gate": gate, "seq": gate_row["seq"], "status": effective}
            for gate, (gate_row, effective) in gate_states.items()
            if gate_row is not None and gate_row["supply_offer_id"] == supply_id]
    return {"supply_offer_id": supply_id, "level": level,
            # 仅"当前**有效** G2 所选货源"为真；无有效 G2 时唯一非 invalid 货源只是数值 fallback，
            # 不算 G2 选择（设计 §3/§4.2），也不代表任何核验升级。
            "is_selected_by_g2": bool(is_valid_g2 and g2_supply) and supply_id == g2_supply,
            "dims": dims, "reasons": reasons, "gaps": gaps, "gate_refs": refs}


def match_supplies(conn, candidate_id: str) -> dict:
    """Read-only matching result for one candidate (design §3). Raises ``KeyError`` if unknown."""
    candidate = conn.execute("SELECT id, data_origin FROM candidate WHERE id=?", (candidate_id,)).fetchone()
    if candidate is None:
        raise KeyError(candidate_id)
    origin = candidate["data_origin"]

    g2_supply, g2_status = current_gate_supply(conn, candidate_id)
    is_valid_g2 = bool(g2_supply) and g2_status == "verified"
    selected = selected_supply_id(conn, candidate_id)
    gate_states = {gate: (row, effective_gate_status(conn, candidate_id, gate))
                   for gate, row in _gate_rows(conn, candidate_id).items()}
    baseline_version = _baseline_version(conn, _gate_rows(conn, candidate_id), g2_supply, selected)

    supplies = conn.execute(
        "SELECT * FROM supply_offer WHERE candidate_id=? AND data_origin=? ORDER BY created_at, id",
        (candidate_id, origin),
    ).fetchall()
    items = [_judge_supply(conn, candidate_id, row, baseline_version=baseline_version,
                           is_valid_g2=is_valid_g2, g2_supply=g2_supply, gate_states=gate_states)
             for row in supplies]

    gaps: list[str] = []
    if not supplies:
        gaps.append("no_supply_rows")
    if not is_valid_g2:
        gaps.append("g2_not_verified")
    if baseline_version is None:
        gaps.append("g4_baseline_undefined")
    g4 = gate_states["platform_policy"][0]
    if supplies and (g4 is None or not g4["applies_to_version"]):
        gaps.append("scope_text_only")                    # 平台/版本仅存在于门槛行自由文本
    for item in items:
        for gap in item["gaps"]:
            if gap not in gaps:
                gaps.append(gap)
    if is_valid_g2:
        bound = conn.execute(
            "SELECT COUNT(*) AS n FROM cost_item WHERE candidate_id=? AND supply_offer_id=? AND is_active=1",
            (candidate_id, g2_supply),
        ).fetchone()["n"]
        if not bound:
            gaps.append("no_cost_binding_to_g2")

    return {"candidate_id": candidate_id,
            "current_g2_supply_id": g2_supply,
            "is_current_g2_valid": is_valid_g2,
            "items": items,
            "gaps": gaps,
            "display_note": DISPLAY_NOTE}


__all__ = ["match_supplies", "SELF_CLAIM_KEYWORDS", "DISPLAY_NOTE", "LEVELS", "DIMS", "GAPS"]
