"""商品分类法：载体 × 具体用途（纯标准库、确定性、可复算）。

两类产物：
- **商品型（kind=商品）**：载体 × 用途 → 具体商品类型（如「Notion 求职投递追踪表」）
- **内容型（kind=内容，非商品）**：教程/推荐/变现教学 → 不计入可售商品；五段分析改口径
  （流量价值 / 引流去向 / 相邻可带货商品），不估算毛利。

用途判定**全文优先**（`full_text` 非空时用「标题+全文」）；载体以标题为主。
"""

from __future__ import annotations

from collections import Counter

CARRIERS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Notion", ("notion",)),
    ("PPT", ("ppt", "powerpoint", "幻灯片", "演示文稿")),
    ("服务", ("代充", "代下", "代购", "充值", "download service", "top up")),
    ("素材", ("psd", "figma", "ui kit", "素材", "插画", "icon", "design pack")),
    ("文档", ("doc", "docx", "pdf", "文档", "表格", "excel", "spreadsheet", "简历文档")),
)

USES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("求职", ("job", "apply", "interview", "lamaran", "hiring", "resume", "cv",
              "求职", "简历", "面试", "投递")),
    ("学习", ("class", "student", "study", "lecture", "notes", "exam", "school",
              "学习", "课堂", "笔记", "考试", "学校")),
    ("内容创作", ("content", "creator", "post", "edit", "social", "newsletter",
                  "内容", "创作", "选题", "编辑", "社交")),
    ("生活", ("budget", "finance", "expense", "meal", "workout", "habit", "goal", "travel",
              "预算", "理财", "记账", "健身", "习惯", "目标", "旅行", "计划")),
    ("设计", ("design", "portfolio", "ui", "moodboard", "设计", "作品集")),
    ("赠送引流", ("giveaway", "free", "赠送", "免费", "福利")),
)

# 强用途词：命中即优先判商品类（即使同时含 best/list/推荐 等泛词）
STRONG_USE_RULES: tuple[tuple[str, tuple[str, ...], str], ...] = (
    ("Notion 设计作品集模板",
     ("portfolio", "design", "ui kit", "moodboard", "作品集", "设计"), "设计"),
)

# 内容型（非商品）——泛词（best/list/推荐 等）只在无强用途词时生效
CONTENT_RULES: tuple[tuple[str, tuple[str, ...], str], ...] = (
    ("Notion 使用教程/导入设置",
     ("import", "setup", "how to", "copy", "导入", "拷贝", "设置", "模板怎么用", "怎么导入", "如何导入"),
     "教程"),
    ("Notion 资源推荐清单",
     ("rekomendasi", "cara mencari", "best", "list", "合集", "推荐", "盘点"), "推荐"),
    ("Notion 教学变现",
     ("create a template", "sell it for", "monetize", "turn into product", "教人做模板", "变现"),
     "变现教学"),
)

NAME_TABLE = {
    ("Notion", "求职"): "Notion 求职投递追踪表",
    ("Notion", "学习"): "Notion 学习笔记模板",
    ("Notion", "内容创作"): "Notion 内容创作选题库",
    ("Notion", "生活"): "Notion 生活计划（预算/健身/旅行）",
    ("Notion", "设计"): "Notion 设计作品集模板",
    ("Notion", "赠送引流"): "Notion 赠送引流模板",
    ("PPT", "设计"): "PPT 模板（作品集）",
    ("PPT", "求职"): "PPT 模板（汇报/述职）",
    ("PPT", "学习"): "PPT 模板（课件）",
    ("文档", "求职"): "简历文档模板",
    ("服务", "未判定"): "资料代充/代下服务",
    ("素材", "设计"): "设计素材包",
}

FALLBACK_NAME = "未归类（待人工）"
CONTENT_NAMES = {name for name, _w, _f in CONTENT_RULES}


def _hit(text: str, words: tuple[str, ...]) -> list[str]:
    return [w for w in words if w in text]


def classify(row: dict, full_text: str | None = None, text_source: str = "") -> dict:
    """返回 carrier / kind / use / category / 命中词 / 未归类原因。"""
    title = str(row.get("title") or "").lower()
    body = str(full_text or "").lower()
    use_haystack = f"{title} {body}".strip() if body else title
    carrier_haystack = title if title else body

    carrier, carrier_hits = "其他", []
    for name, words in CARRIERS:
        hits = _hit(carrier_haystack, words)
        if hits:
            carrier, carrier_hits = name, hits
            break
    if carrier == "其他" and body:
        for name, words in CARRIERS:
            hits = _hit(body, words)
            if hits:
                carrier, carrier_hits = name, hits
                break

    secondary: list[str] = []
    if carrier == "Notion":
        # 1) 强用途词优先（portfolio/design/ui kit/moodboard/作品集/设计）
        for name, words, use_name in STRONG_USE_RULES:
            hits = _hit(use_haystack, words)
            if hits:
                for cname, cwords, _flavour in CONTENT_RULES:
                    if _hit(use_haystack, cwords):
                        secondary.append(cname)
                return {"carrier": carrier, "kind": "商品", "use_case": use_name, "category": name,
                        "carrier_hits": carrier_hits, "use_hits": hits, "secondary_tags": secondary,
                        "text_source": (text_source or ("full_text" if body else "title")),
                        "unclassified_reason": ""}
        # 2) 内容型（泛词）
        for name, words, flavour in CONTENT_RULES:
            hits = _hit(use_haystack, words)
            if hits:
                for cname, cwords, _flavour in CONTENT_RULES:
                    if cname != name and _hit(use_haystack, cwords):
                        secondary.append(cname)
                return {"carrier": carrier, "kind": "内容", "use_case": flavour, "category": name,
                        "carrier_hits": carrier_hits, "use_hits": hits, "secondary_tags": secondary,
                        "text_source": (text_source or ("full_text" if body else "title")),
                        "unclassified_reason": ""}

    use, use_hits = "未判定", []
    for name, words in USES:
        hits = _hit(use_haystack, words)
        if hits:
            use, use_hits = name, hits
            break

    composed = NAME_TABLE.get((carrier, use))
    if composed:
        name, reason = composed, ""
    elif carrier == "Notion":
        name, reason = "Notion 其它（待人工）", "标题与全文均无商品用途词，也未命中内容型词（import/推荐/变现 等）"
    elif carrier == "PPT":
        name, reason = "PPT 模板（用途待定）", "命中 PPT 载体，但未命中具体用途词"
    elif carrier == "素材":
        name, reason = ("设计素材包（用途待定）" if use != "设计" else "设计素材包"), "素材载体未命中具体用途词"
    elif carrier == "服务":
        name, reason = "资料代充/代下服务", ""
    elif carrier == "文档":
        name, reason = "文档模板（用途待定）", "文档载体未命中具体用途词"
    else:
        name, reason = FALLBACK_NAME, "既未命中载体，也未命中用途词"
    return {"carrier": carrier, "kind": ("内容" if name in CONTENT_NAMES else "商品"),
            "use_case": use, "category": name, "carrier_hits": carrier_hits, "use_hits": use_hits,
            "secondary_tags": secondary,
            "text_source": (text_source or ("full_text" if body else "title")),
            "unclassified_reason": reason}


def _num(value):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number == number and abs(number) != float("inf") else None


def build_categories(rows: list[dict], analyses: dict[str, dict], price_stats: dict | None = None,
                     sources: list[dict] | None = None, texts: dict[str, dict] | None = None) -> list[dict]:
    """按商品/内容类型聚合；内容型五段分析改口径（不估毛利）。"""
    buckets: dict[str, dict] = {}
    for row in rows:
        item_id = str(row.get("item_id") or "")
        entry = (texts or {}).get(item_id) or {}
        tax = classify(row, entry.get("text"), entry.get("source") or "")
        bucket = buckets.setdefault(tax["category"], {
            "category": tax["category"], "carrier": tax["carrier"], "kind": tax["kind"],
            "use_case": tax["use_case"], "reason": tax["unclassified_reason"],
            "members": [], "rows": [], "hits": {}})
        bucket["members"].append(item_id)
        bucket["rows"].append(row)
        bucket["hits"][item_id] = {"carrier_hits": tax["carrier_hits"], "use_hits": tax["use_hits"],
                                   "text_source": tax["text_source"],
                                   "secondary_tags": tax.get("secondary_tags") or []}

    total = len(rows) or 1
    out: list[dict] = []
    for category, bucket in buckets.items():
        members = bucket["rows"]
        demand_values = [v for v in (_num(r.get("demand_norm")) for r in members) if v is not None]
        demand_raws = [v for v in (_num(r.get("demand_raw")) for r in members) if v is not None]
        sell_values = [v for v in (_num(r.get("sellability_norm")) for r in members) if v is not None]
        lows = [v for v in (_num(r.get("margin_low")) for r in members) if v is not None]
        highs = [v for v in (_num(r.get("margin_high")) for r in members) if v is not None]
        scores = [v for v in (_num(r.get("total_score")) for r in members) if v is not None]
        risk_counter: Counter[str] = Counter()
        for r in members:
            for risk in (analyses.get(str(r.get("item_id") or "")) or {}).get("risks") or []:
                risk_counter[risk] += 1
        ranked = sorted(members, key=lambda r: -(_num(r.get("total_score")) or 0.0))
        sellers = [r for r in members if (_num(r.get("sellability_norm")) or 0) >= 0.8]
        count = len(members)
        share = count / total
        margin = ([round(min(lows), 4), round(max(highs), 4)] if lows and highs else None)
        price_count = (price_stats or {}).get("count") or 0
        kind = bucket["kind"]
        demand_sum = sum(demand_raws) if demand_raws else 0
        demand_max = max(demand_values) * 100 if demand_values else 0

        analysis = {
            "what": f"{category}（载体 {bucket['carrier']} × {'内容主题' if kind == '内容' else '用途'} {bucket['use_case']}）",
            "who": (analyses.get(str(ranked[0].get("item_id") or "")) or {}).get("target_user") or "人群未明确",
            "demand_evidence": (
                f"组内 {count} 条内容信号：需求合计 {demand_sum:.0f}、最高分位 {demand_max:.0f}%；"
                + (f"可售性均值 {(sum(sell_values) / len(sell_values) * 100):.0f}" if sell_values else "可售性：无数据")
                + ("；无可比成交价，仅内容信号、无售卖证据" if price_count == 0 else
                   f"；参考价来自 price_signals {price_count} 条样本（{price_stats.get('effective_min')}–{price_stats.get('effective_max')}），非该类型自身成交价")
            ),
            "competition": (
                f"本组占全部机会 {share * 100:.0f}%（{count}/{total}）；"
                + (f"可售（≥0.8）条目 {len(sellers)} 条" if sellers else "组内暂无可售条目")
                + "；无竞品计数数据，需补采集平台在售数量"
            ),
        }
        if kind == "内容":
            analysis["pricing_risk"] = (
                f"内容型（非商品），不估算毛利；流量价值：组内 {count} 条、需求合计 {demand_sum:.0f}、"
                f"最高分位 {demand_max:.0f}%；引流去向：站内主页 / 合集 / 私信关键词；"
                "可带货的相邻商品：同主题的 Notion 模板、PPT 模板或资料包（需人工挑选，数据中未标注）"
            )
            analysis["kind_note"] = "内容型（非商品），不计入可售商品口径"
        else:
            analysis["pricing_risk"] = (
                (f"毛利区间 {margin[0] * 100:.0f}%–{margin[1] * 100:.0f}%（模型假设）" if margin else "毛利区间缺失")
                + f"；组内高频风险：{'、'.join(t for t, _ in risk_counter.most_common(2)) or '暂无'}"
                + "；无真实成交与订单数据，定价需补采集"
            )
            analysis["kind_note"] = "商品型"

        sources_matched = [s for s in (sources or [])
                           if any(tok and tok in f"{s.get('type') or ''}{s.get('name') or ''}"
                                  for tok in [bucket["carrier"], bucket["use_case"]])][:2]
        out.append({
            "group_key": f"cat:{category}", "group_name": category, "category": category,
            "kind": kind, "carrier": bucket["carrier"], "use_case": bucket["use_case"],
            "unclassified_reason": bucket["reason"], "members": bucket["members"], "count": count,
            "share": round(share, 4),
            "demand_sum": round(demand_sum, 3) if demand_raws else None,
            "demand_max_norm": round(max(demand_values), 4) if demand_values else None,
            "sellability_mean": round(sum(sell_values) / len(sell_values), 4) if sell_values else None,
            "margin_range": margin, "risks_top": [t for t, _n in risk_counter.most_common(2)],
            "representative_urls": [r.get("url") for r in ranked[:3]],
            "max_total_score": round(max(scores), 4) if scores else None,
            "hit_words": bucket["hits"], "analysis": analysis,
            "secondary_top": [t for t, _n in Counter(
                tag for h in bucket["hits"].values() for tag in (h.get("secondary_tags") or [])
            ).most_common(2)],
            "sources": [{"name": s.get("name"), "type": s.get("type"),
                         "license_verdict": s.get("license_verdict"), "match": "近似匹配"}
                        for s in sources_matched],
        })
    out.sort(key=lambda g: (g["kind"] != "商品", -(g["max_total_score"] or 0.0), -(g["count"] or 0)))
    return out


def summarize_conservation(categories: list[dict], total: int) -> dict:
    pending = sum(c["count"] for c in categories if c["category"] in (FALLBACK_NAME, "Notion 其它（待人工）"))
    classified = sum(c["count"] for c in categories) - pending
    product = sum(c["count"] for c in categories if c["kind"] == "商品")
    content = sum(c["count"] for c in categories if c["kind"] == "内容")
    return {"total": total, "classified": classified, "pending": pending,
            "product": product, "content": content,
            "checked": classified + pending == total and product + content == total}
