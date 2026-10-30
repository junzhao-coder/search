"""机会聚合：把逐条机会按“品类（优先）/载体（兜底）”合并成组（纯标准库、确定性）。

`group_key`：
  - 已判品类：`type:<product_type>`，组名 = 品类名
  - 未分类且 carrier 含 Notion：`carrier:notion`，组名「Notion 模板（品类待定）」
  - 未分类且无 carrier：`carrier:unknown`，组名「载体未明确（品类待定）」

组内统计只用真实列（可复算）：count / demand_sum / demand_max_norm / sellability_mean /
margin_range / risks_top(2) / representative_urls(3) / sources(1–2，标“近似匹配”)。
"""

from __future__ import annotations

from collections import Counter

UNCLASSIFIED = "未分类"
CARRIER_LABEL = {"carrier:notion": "Notion 模板（品类待定）", "carrier:unknown": "载体未明确（品类待定）"}


def _num(value):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number == number and abs(number) != float("inf") else None


def group_key_of(row: dict, analysis: dict) -> tuple[str, str]:
    product_type = (analysis or {}).get("product_type") or UNCLASSIFIED
    if product_type != UNCLASSIFIED:
        return f"type:{product_type}", product_type
    carrier = ((analysis or {}).get("carrier") or "").lower()
    if "notion" in carrier:
        return "carrier:notion", CARRIER_LABEL["carrier:notion"]
    return "carrier:unknown", CARRIER_LABEL["carrier:unknown"]


def _source_matches(group_name: str, sources: list[dict], limit: int = 2) -> list[dict]:
    """货源按 group_name 与 sources.type/name 的关键词重叠度匹配，标注“近似匹配”。"""
    tokens = [t for t in (group_name.replace("（", " ").replace("）", " ").split()) if len(t) >= 2]
    scored = []
    for src in sources:
        haystack = f"{src.get('type') or ''} {src.get('name') or ''}"
        overlap = sum(1 for token in tokens if token and token in haystack)
        if overlap:
            scored.append((overlap, _num(src.get("stars")) or 0, src))
    scored.sort(key=lambda item: (-item[0], -item[1]))
    return [{"name": src.get("name"), "type": src.get("type"),
             "license_verdict": src.get("license_verdict"), "license_spdx": src.get("license_spdx"),
             "evidence_url": src.get("evidence_url"), "match": "近似匹配"}
            for _o, _s, src in scored[:limit]]


def build_groups(rows: list[dict], analyses: dict[str, dict], sources: list[dict] | None = None) -> list[dict]:
    """rows 为已筛选后的机会行；analyses 以 item_id 索引。返回按组内最高 total_score 降序的组列表。"""
    buckets: dict[str, dict] = {}
    for row in rows:
        item_id = str(row.get("item_id") or "")
        info = analyses.get(item_id) or {}
        key, name = group_key_of(row, info)
        bucket = buckets.setdefault(key, {"group_key": key, "group_name": name, "members": [], "rows": []})
        bucket["members"].append(item_id)
        bucket["rows"].append((row, info))

    groups: list[dict] = []
    for key, bucket in buckets.items():
        members = bucket["rows"]
        demand_values = [v for v in (_num(r.get("demand_norm")) for r, _ in members) if v is not None]
        demand_raws = [v for v in (_num(r.get("demand_raw")) for r, _ in members) if v is not None]
        sell_values = [v for v in (_num(r.get("sellability_norm")) for r, _ in members) if v is not None]
        lows = [v for v in (_num(r.get("margin_low")) for r, _ in members) if v is not None]
        highs = [v for v in (_num(r.get("margin_high")) for r, _ in members) if v is not None]
        scores = [v for v in (_num(r.get("total_score")) for r, _ in members) if v is not None]
        risk_counter: Counter[str] = Counter()
        for _row, info in members:
            for risk in info.get("risks") or []:
                risk_counter[risk] += 1
        risks_top = [text for text, _n in risk_counter.most_common(2)]
        ranked = sorted(members, key=lambda pair: -(_num(pair[0].get("total_score")) or 0.0))
        representatives = [{"item_id": r.get("item_id"), "title": (r.get("title") or "")[:120],
                            "url": r.get("url"), "total_score": _num(r.get("total_score"))}
                           for r, _i in ranked[:3]]
        groups.append({
            "group_key": key,
            "group_name": bucket["group_name"],
            "members": bucket["members"],
            "count": len(members),
            "demand_sum": round(sum(demand_raws), 3) if demand_raws else None,
            "demand_max_norm": round(max(demand_values), 4) if demand_values else None,
            "sellability_mean": round(sum(sell_values) / len(sell_values), 4) if sell_values else None,
            "margin_range": [round(min(lows), 4), round(max(highs), 4)] if lows and highs else None,
            "risks_top": risks_top,
            "representative_urls": [item["url"] for item in representatives],
            "representatives": representatives,
            "max_total_score": round(max(scores), 4) if scores else None,
            "sources": _source_matches(bucket["group_name"], sources or []),
            "risk_variants": len({tuple(info.get("risks") or []) for _r, info in members}),
        })

    groups.sort(key=lambda g: (-(g["max_total_score"] or 0.0), -(g["count"] or 0), g["group_key"]))
    return groups
