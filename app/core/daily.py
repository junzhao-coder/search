"""S5 每日摘要聚合：只读（复用 ``ranking.rank_candidates``，设计见 S4_RANKING_SPEC v2 §6/§8）。

只做聚合，**不重算、不重排、不另设截断**：``top`` 取推荐池中 ``daily_pick=True`` 的条目（保持
ranking 的相对次序），``blocked``/``observing``/``exploring`` 独立列出，``omitted``/``pools``
原样透传。本模块只读：仅调用 ``ranking.rank_candidates``（其内部只 SELECT），不写库、不接 GET、
不新增端点/表/列/依赖/CLI/定时器；摘要不持久化（每日一次与提醒属 S5 流水线，未实现）。
"""

from __future__ import annotations

from .ranking import rank_candidates

DIGEST_KIND = "daily_digest"
DISPLAY_NOTE = ("每日摘要仅供人工查看：重点机会最多 5 条（不足按实展示、不凑数）；"
                "排序分是启发式展示次序，不是收益、概率或证据。")
_ITEM_KEYS = ("rank", "candidate_id", "pool", "tier", "score", "reasons", "gaps",
              "next_action", "daily_pick", "inputs_used")


def _item(entry: dict) -> dict:
    return {key: entry[key] for key in _ITEM_KEYS if key in entry}


def daily_digest(conn, *, as_of: str, limit: int = 5, budget_minutes: int = 30,
                 scenario_params: dict | None = None, include_synthetic: bool = False) -> dict:
    """只读每日摘要；``as_of`` 必填并透传，保证同输入同结果。

    ``include_synthetic``：**默认 False = 只统计 real**（CONTRACT #19 与“每日摘要默认只统计
    real；include_synthetic=1 才纳入合成数据”）；True 时 real+synthetic 都纳入。
    """
    ranked = rank_candidates(conn, as_of=as_of, limit=limit, budget_minutes=budget_minutes,
                             scenario_params=scenario_params,
                             include_synthetic=include_synthetic)
    items = ranked["items"]
    top = [_item(entry) for entry in items if entry["pool"] == "recommended" and entry.get("daily_pick")]
    blocked = [_item(entry) for entry in items if entry["pool"] == "blocked"]
    observing = [_item(entry) for entry in items if entry["pool"] == "observing"]
    exploring = [_item(entry) for entry in items if entry["pool"] == "exploring"]
    return {
        "kind": DIGEST_KIND,
        "as_of": ranked["as_of"],
        "digest_date": ranked["as_of"][:10],
        "rank_version": ranked["rank_version"],
        "daily_limit": limit,
        "scenario_params": ranked["scenario_params"],
        "budget_minutes": budget_minutes,
        "pools": ranked["pools"],
        "top": top,
        "blocked": blocked,
        "observing": observing,
        "exploring": exploring,
        "omitted": ranked["omitted"],
        "counts": {"top": len(top), "blocked": len(blocked), "observing": len(observing),
                   "exploring": len(exploring), "omitted": len(ranked["omitted"]),
                   "insufficient": ranked["pools"]["insufficient"],
                   "excluded": ranked["pools"]["excluded"]},
        "pending_confirmation": ranked["pending_confirmation"],
        "budget_note": ranked["budget_note"],
        "display_note": DISPLAY_NOTE,
        "source": "ranking.rank_candidates",
    }


__all__ = ["daily_digest", "DIGEST_KIND", "DISPLAY_NOTE"]
