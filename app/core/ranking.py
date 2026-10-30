"""S4-B3 机会排序：只读纯函数（设计 docs/design/S4_RANKING_SPEC.md v2）。

只读保证
--------
本模块只执行 SELECT 并调用既有**只读**函数（``state.recompute``/``effective_gate_status``/
``current_gate_supply``、``matching.match_supplies``、``scenario.compute_scenario``）；
**绝不** INSERT/UPDATE/DELETE、不开事务、不调 ``apply_status``/``set_override``、不建复核，
不写任何表。不接 GET、不新增端点/表/列/依赖/CLI/定时器。

权重
----
``rank-v1`` 为**启发式**权重（**待用户确认**）；同一 ``rank_version`` 内数值冻结，调整必须
升版本（输出携带 ``rank_version``）。分数仅用于同层次序，**不得**当作收益/概率/证据。

分池（设计 §3，严��优先级、命中即止）
------------------------------------
``excluded``（override archived/explore，仅计数）→ ``blocked``（``recompute`` 判 stale 的全部
来源）→ ``recommended``（testable：``complete`` → T1，否则 T2）→ ``observing``（pending 且有需求
信号、有可用货源、无实质缺口）→ ``exploring``（pending 且有需求信号，但无可用货源或存在
``license_unknown``/``format_unknown``）→ ``insufficient``（``demand_signal`` 行数 0 等，仅计数）。
"""

from __future__ import annotations

import datetime as _dt

from .gates import GATES
from .matching import match_supplies
from .scenario import compute_scenario
from .state import SUPPLY_TTL_DAYS, current_gate_supply, effective_gate_status, recompute
from .util import now_utc

RANK_VERSION = "rank-v1"

#: rank-v1 启发式权重（**待用户确认**；同版本内冻结，调整须升版本）。
WEIGHTS = {
    "base": {"T1": 39, "T2": 29, "T3": 15, "T4": 5},
    "complete": 15,
    "net_positive": 10,
    "verified_each": 5,
    "fresh_7d": 8,
    "fresh_30d": 4,
    "supply_stable": 6,
    "minutes_le30": 2,
    "minutes_gt30": 1,
    "material_gap": -2,
}
FRESH_DAYS_7 = 7
FRESH_DAYS_30 = 30
MATERIAL_GAPS = ("license_unknown", "format_unknown", "no_cost_binding_to_g2", "g4_baseline_undefined")
EXPLORING_GAPS = ("license_unknown", "format_unknown")
POOL_ORDER = ("blocked", "recommended", "observing", "exploring")
DEFAULT_SCENARIO_PARAMS = {"variant": "base", "amortize_orders": None, "monthly_orders": None}
BUDGET_NOTE = ("预算只作展示提示，不改变排序与条数（与 PLAN §8 偏差待裁定）；"
               "权重为启发式 rank-v1，待用户确认。")
PENDING_CONFIRMATION = True


def _parse_at(value: str | None):
    if not value:
        return None
    try:
        return _dt.datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=_dt.timezone.utc)
    except (ValueError, TypeError):
        return None


def _require_as_of(as_of) -> _dt.datetime:
    stamp = _parse_at(as_of)
    if stamp is None:
        raise ValueError("as_of 必须是 ISO-8601 UTC 时间（YYYY-MM-DDTHH:MM:SSZ）")
    return stamp


def _head_signal(conn, candidate_id: str):
    """设计 §4.4：demand_signal 头版本行（superseded_by IS NULL），退化规则见设计。"""
    row = conn.execute(
        "SELECT id, version_no, observed_at FROM demand_signal WHERE candidate_id=?"
        " AND superseded_by IS NULL ORDER BY version_no DESC, observed_at DESC, id ASC LIMIT 1",
        (candidate_id,),
    ).fetchone()
    if row is not None:
        return row
    return conn.execute(
        "SELECT id, version_no, observed_at FROM demand_signal WHERE candidate_id=?"
        " ORDER BY version_no DESC, id ASC LIMIT 1",
        (candidate_id,),
    ).fetchone()


def _demand_count(conn, candidate_id: str) -> int:
    return conn.execute("SELECT COUNT(*) AS n FROM demand_signal WHERE candidate_id=?",
                        (candidate_id,)).fetchone()["n"]


def _manual_minutes(conn, candidate_id: str):
    """设计 §4.4：当前 base 口径的人工分钟合计（无行/全 NULL ⇒ 未知）。"""
    row = conn.execute(
        "SELECT SUM(minutes) AS total FROM cost_item WHERE candidate_id=? AND role='manual_labor'"
        " AND basis='per_order' AND variant='base' AND is_active=1 AND minutes IS NOT NULL",
        (candidate_id,),
    ).fetchone()
    return row["total"]


def _verified_count(conn, candidate_id: str) -> int:
    return sum(1 for gate in GATES if effective_gate_status(conn, candidate_id, gate) == "verified")


def _supply_stable(conn, candidate_id: str) -> bool:
    supply_id, status = current_gate_supply(conn, candidate_id)
    if status != "verified" or not supply_id:
        return False
    row = conn.execute("SELECT * FROM supply_offer WHERE id=?", (supply_id,)).fetchone()
    if row is None or row["status"] not in ("candidate", "verified"):
        return False
    if any(row[field] != "yes" for field in ("commercial_allowed", "redistribute_allowed", "resale_allowed")):
        return False
    checked = _parse_at(row["last_checked_at"])
    now = _parse_at(now_utc())
    if checked is not None and now is not None and (now - checked) >= _dt.timedelta(days=SUPPLY_TTL_DAYS):
        return False
    return True


def _freshness_bucket(observed_at: str | None, as_of_dt: _dt.datetime):
    stamp = _parse_at(observed_at)
    if stamp is None:
        return None, 0
    age = as_of_dt - stamp
    if age < _dt.timedelta(0):
        age = _dt.timedelta(0)
    if age <= _dt.timedelta(days=FRESH_DAYS_7):
        return "7d", WEIGHTS["fresh_7d"]
    if age <= _dt.timedelta(days=FRESH_DAYS_30):
        return "30d", WEIGHTS["fresh_30d"]
    return "older", 0


def _score(tier: str, *, complete: bool, net, verified: int, fresh_points: int,
           stable: bool, minutes, material_gap: bool) -> int:
    score = WEIGHTS["base"][tier]
    if complete:
        score += WEIGHTS["complete"]
    if net is not None and net > 0:
        score += WEIGHTS["net_positive"]
    score += WEIGHTS["verified_each"] * verified
    score += fresh_points
    if stable:
        score += WEIGHTS["supply_stable"]
    if minutes is not None:
        score += WEIGHTS["minutes_le30"] if minutes <= 30 else WEIGHTS["minutes_gt30"]
    if material_gap:
        score += WEIGHTS["material_gap"]
    return score


def _judge(conn, candidate: dict, origin: str, as_of_dt: _dt.datetime, scenario_params: dict) -> dict:
    candidate_id = candidate["id"]
    status, reason = recompute(conn, candidate_id)
    demand_count = _demand_count(conn, candidate_id)
    matched = match_supplies(conn, candidate_id)
    signals = _head_signal(conn, candidate_id)
    observed_at = signals["observed_at"] if signals is not None else None
    fresh_bucket, fresh_points = _freshness_bucket(observed_at, as_of_dt)
    verified = _verified_count(conn, candidate_id)
    minutes = _manual_minutes(conn, candidate_id)
    stable = _supply_stable(conn, candidate_id)
    material_gap = any(gap in matched["gaps"] for gap in MATERIAL_GAPS)
    usable_supply = any(item["level"] != "excluded" for item in matched["items"])

    if status in ("archived", "explore"):
        return {"pool": "excluded", "tier": None, "score": None, "reasons": [], "gaps": [],
                "next_action": None, "observed_at": observed_at, "verified": verified,
                "minutes": minutes, "net": None, "complete": False}
    if status == "stale":
        return {"pool": "blocked", "tier": "B", "score": None, "reasons": [f"stale:{reason}"],
                "gaps": [], "next_action": "先处理该门槛/复核后重排", "observed_at": observed_at,
                "verified": verified, "minutes": minutes, "net": None, "complete": False}
    if status == "testable":
        params = dict(DEFAULT_SCENARIO_PARAMS)
        params.update(scenario_params or {})
        scenario = compute_scenario(conn, candidate_id, params["variant"],
                                    amortize_orders=params["amortize_orders"],
                                    monthly_orders=params["monthly_orders"], normalize_periods=False)
        complete = bool(scenario["complete"])
        net = scenario["net_per_order_minor"]
        tier = "T1" if complete else "T2"
        gaps = [f"net 未知：{item}" for item in (scenario.get("unknown_components") or [])]
        if not complete and not gaps:
            gaps = ["net 未知：缺摊销/月销假设（见 scenario_params）"]
        score = _score(tier, complete=complete, net=net, verified=verified, fresh_points=fresh_points,
                       stable=stable, minutes=minutes, material_gap=material_gap)
        reasons = ["四门槛均 verified",
                   f"net={net} 分/单（complete）" if complete else "net 未知（不按 0 计）"]
        if net is not None and net < 0:
            reasons.append("负利润（如实展示，不加正分）")
        if fresh_bucket:
            reasons.append(f"观察时间新鲜度 {fresh_bucket}（相对 as_of）")
        if stable:
            reasons.append("有效 G2 货源稳定")
        if minutes is not None:
            reasons.append(f"人工 {minutes} 分钟")
        return {"pool": "recommended", "tier": tier, "score": score, "reasons": reasons,
                "gaps": gaps, "next_action": "可直接进入人工复核/试单准备",
                "observed_at": observed_at, "verified": verified, "minutes": minutes,
                "net": net, "complete": complete}
    if demand_count == 0:
        return {"pool": "insufficient", "tier": None, "score": None, "reasons": [],
                "gaps": ["无 demand_signal 行"], "next_action": None, "observed_at": observed_at,
                "verified": verified, "minutes": minutes, "net": None, "complete": False}
    exploring = (not usable_supply) or any(gap in matched["gaps"] for gap in EXPLORING_GAPS)
    tier = "T4" if exploring else "T3"
    score = _score(tier, complete=False, net=None, verified=verified, fresh_points=fresh_points,
                   stable=stable, minutes=minutes, material_gap=material_gap)
    gaps = [gap for gap in matched["gaps"] if gap in MATERIAL_GAPS or gap in EXPLORING_GAPS]
    if exploring:
        reasons = ["待验证：弱证据/缺口（D04 单列）"] + ([f"匹配缺口：{gap}" for gap in gaps] or [])
        next_action = "先补许可/版本证据或寻找可用货源后重排"
    else:
        reasons = ["待补证据：四门槛未全部 verified"]
        next_action = "补齐四项门槛证据后重排"
    return {"pool": "exploring" if exploring else "observing", "tier": tier, "score": score,
            "reasons": reasons, "gaps": gaps, "next_action": next_action, "observed_at": observed_at,
            "verified": verified, "minutes": minutes, "net": None, "complete": False}


def _sort_key(item: dict) -> tuple:
    net = item["net"]
    observed = _parse_at(item["observed_at"])
    minutes = item["minutes"]
    return (POOL_ORDER.index(item["pool"]),
            -(item["score"] if item["score"] is not None else 0),
            0 if net is not None else 1, -(net if net is not None else 0),
            0 if observed is not None else 1, -(observed.timestamp() if observed is not None else 0),
            -item["verified"],
            0 if minutes is not None else 1, minutes if minutes is not None else 0,
            item["candidate_id"])


def rank_candidates(conn, *, as_of: str, limit: int = 5, budget_minutes: int = 30,
                    scenario_params: dict | None = None, rank_version: str = RANK_VERSION,
                    include_synthetic: bool = True) -> dict:
    """只读排序（设计 §6）。``as_of`` 必填且写入输出，保证同输入同结果。

    ``include_synthetic``：CONTRACT #19「每日摘要默认只统计 real」的过滤开关——
    ``False`` 只统计 ``candidate.data_origin='real'``；``True`` 时 real+synthetic 都纳入。
    纯函数默认保持 True（既有调用方不变），每日摘要/HTTP 端点默认 real-only。
    """
    as_of_dt = _require_as_of(as_of)
    if rank_version != RANK_VERSION:
        raise ValueError(f"未实现的 rank_version: {rank_version}")
    params = dict(DEFAULT_SCENARIO_PARAMS)
    params.update(scenario_params or {})
    candidates = [dict(row) for row in conn.execute(
        "SELECT id, data_origin FROM candidate ORDER BY id").fetchall()]
    if not include_synthetic:
        candidates = [row for row in candidates if row["data_origin"] == "real"]

    judged, counts = [], {"excluded": 0, "blocked": 0, "recommended": 0, "observing": 0,
                          "exploring": 0, "insufficient": 0}
    for candidate in candidates:
        item = _judge(conn, candidate, candidate["data_origin"], as_of_dt, params)
        counts[item["pool"]] += 1
        item["candidate_id"] = candidate["id"]
        judged.append(item)

    ranked = sorted([item for item in judged if item["pool"] in POOL_ORDER], key=_sort_key)
    recommended_rank, items, omitted = 0, [], []
    for index, item in enumerate(ranked, start=1):
        picked = False
        if item["pool"] == "recommended":
            recommended_rank += 1
            picked = recommended_rank <= limit
            if not picked:
                omitted.append({"rank": index, "candidate_id": item["candidate_id"],
                                "reason": f"超出每日 {limit} 条上限"})
        items.append({"rank": index, "candidate_id": item["candidate_id"], "pool": item["pool"],
                      "tier": item["tier"], "score": item["score"], "reasons": item["reasons"],
                      "gaps": item["gaps"], "next_action": item["next_action"],
                      "daily_pick": picked,
                      "inputs_used": {"observed_at": item["observed_at"],
                                      "verified_gates": item["verified"],
                                      "manual_minutes": item["minutes"],
                                      "net_per_order_minor": item["net"],
                                      "scenario_complete": item["complete"],
                                      "scenario_params": params}})
    return {"rank_version": RANK_VERSION, "as_of": as_of, "scenario_params": params,
            "budget_minutes": budget_minutes, "budget_note": BUDGET_NOTE,
            "pending_confirmation": PENDING_CONFIRMATION,
            "pool_order": list(POOL_ORDER), "pools": counts, "daily_limit": limit,
            "items": items, "omitted": omitted}


__all__ = ["rank_candidates", "RANK_VERSION", "WEIGHTS", "POOL_ORDER", "DEFAULT_SCENARIO_PARAMS",
           "MATERIAL_GAPS", "EXPLORING_GAPS", "PENDING_CONFIRMATION", "BUDGET_NOTE"]
