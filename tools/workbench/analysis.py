"""机会列表的产品分析生成器（纯标准库、确定性、可复算）。

口径（rev2）：
1) **先判生意形态（intent），再判载体**：`notion` 不进产品类型，只作为“载体”出现在 positioning 末尾。
2) `target_user` 只能由意图词推出（求职者/学生/教师/设计师/独立开发者/内容创作者），推不出写「人群未明确」。
3) 风险**逐行差异化**、只在字段支持时出现，每行最多 2 条：
   - 可售性低：仅 `sellability_norm <= 0.2`；未评估：仅字段缺失
   - 毛利低置信：仅「margin_assumption 含 all 20 / fallback / basket proxy / 全量回退」或「区间宽度 > 0.3」
   - 竞争偏密：仅 `competition_norm < 0.5`
   - 缺失指标：仅 `missing_metrics` 非空
   - 成本缺失：仅在存在毛利区间（即影响毛利）时列出
   许可风险不在此处生成：`scores.csv` 无逐条 license_verdict，`sources.csv` 亦无连接键，故不臆造。
"""

from __future__ import annotations

# (生意形态, 关键词, 目标人群, 交付形态) —— 顺序即优先级（先意图、后载体）
INTENT_RULES: tuple[tuple[str, tuple[str, ...], str, str], ...] = (
    ("学习或生活规划模板",
     ("class", "course", "student", "school", "study", "notes", "planner", "tracker", "habit",
      "goal", "budget", "meal", "workout", "travel", "学习", "课堂", "笔记", "计划", "习惯", "预算", "旅行"),
     "学生", "学习/生活规划模板（可复制的页面或文档）"),
    ("求职简历资料",
     ("cv", "resume", "job", "internship", "lamaran", "apply", "interview", "求职", "简历", "面试"),
     "求职者", "简历/求职排版与投递资料（可编辑文件）"),
    ("设计素材",
     ("portfolio", "design", "psd", "figma", "ui kit", "作品集", "设计", "素材", "插画", "icon"),
     "设计师", "设计素材包（PSD / Figma 等源文件）"),
    ("提示词或数字包",
     ("prompt", "pack", "bundle", "gumroad", "checkout", "buy", "sell", "提示词", "指令", "合集包"),
     "内容创作者", "提示词/数字包（文本库、模板包或下载文件）"),
    ("教学内容",
     ("teaching", "tutorial", "guide", "how to", "import", "setup", "教程", "讲解", "课程", "导入", "设置"),
     "教师", "图文或视频教程（内容型交付）"),
)

INTENT_META = {name: (target, deliverable) for name, _kw, target, deliverable in INTENT_RULES}
INTENT_META["未分类"] = ("人群未明确", "待确认（需人工打开原始链接判断交付形态）")

# 兼容旧调用名（gen_profiles / 测试可能引用）
TYPE_RULES = INTENT_RULES
TYPE_META = INTENT_META

CARRIER_WORDS = {"notion": "Notion 模板（可复制到自己的工作区）"}
FALLBACK_HINTS = ("all 20", "fallback", "basket proxy", "全量回退")
MARGIN_WIDTH_LIMIT = 0.3
COMPETITION_LIMIT = 0.5


def infer_product_type(row: dict) -> tuple[str, list[str]]:
    """返回 (生意形态, 命中的意图词)。notion 不参与类型判定。"""
    title = str(row.get("title") or "").lower()
    for name, keywords, _target, _deliver in INTENT_RULES:
        hit = [k for k in keywords if k in title]
        if hit:
            return name, hit
    return "未分类", []


def _num(row: dict, key: str):
    value = row.get(key)
    if value is None or str(value).strip() == "":
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number == number and abs(number) != float("inf") else None


def _pct(value) -> str:
    return f"{value * 100:.0f}%"


def _carrier_note(row: dict) -> str:
    title = str(row.get("title") or "").lower()
    for word, label in CARRIER_WORDS.items():
        if word in title:
            return f"；载体为 {label}"
    return ""


def build_analysis(row: dict, price_stats: dict | None = None) -> dict:
    """确定性生成一条机会的产品分析；同一输入必然同一输出。"""
    intent, intent_hits = infer_product_type(row)
    target_user, deliverable = INTENT_META[intent]
    evidence: list[str] = list(intent_hits)
    carrier = _carrier_note(row)
    if carrier:
        evidence.append("title:notion(carrier)")

    demand = _num(row, "demand_norm")
    competition = _num(row, "competition_norm")
    margin_mid = _num(row, "margin_mid")
    margin_low, margin_high = _num(row, "margin_low"), _num(row, "margin_high")
    sell_norm = _num(row, "sellability_norm")
    total = _num(row, "total_score")
    raw_count = _num(row, "demand_raw")
    sell_reason = str(row.get("sellability_reason") or "").strip()
    cost_input = str(row.get("cost_input") or "").strip()
    missing = str(row.get("missing_metrics") or "").strip()
    assumption = str(row.get("margin_assumption") or "").lower()

    sell_bucket = ("较强售卖" if (sell_norm is not None and sell_norm >= 0.8)
                   else "低信号" if (sell_norm is not None and sell_norm <= 0.2)
                   else "不明确" if sell_norm is not None else "未评估")

    # ---------- 选择理由（≤3，挂真实数值）----------
    candidates: list[tuple[int, str, list[str]]] = []
    if demand is not None:
        extra = f"，原始需求值 {raw_count:g}" if raw_count is not None else ""
        candidates.append((0, f"需求位于本平台样本第 {_pct(demand)} 分位（平台内百分位{extra}）",
                           ["demand_norm", "demand_raw"]))
    if sell_norm is not None:
        candidates.append((1, f"可售性 {round(100 * sell_norm)}（{sell_bucket}）"
                              + (f"：{sell_reason}" if sell_reason else ""),
                           ["sellability_norm", "sellability_reason"]))
    if margin_mid is not None:
        band = (f"，区间 {_pct(margin_low)}–{_pct(margin_high)}"
                if margin_low is not None and margin_high is not None else "")
        price_note = ""
        if price_stats and price_stats.get("count"):
            price_note = (f"；价格信号 {price_stats['count']} 条样本"
                          f"（有效价 {price_stats.get('effective_min')}–{price_stats.get('effective_max')}）")
        candidates.append((2, f"毛利估算 {_pct(margin_mid)}{band}（模型假设{price_note}）",
                           ["margin_mid", "margin_low", "margin_high"]))
    if competition is not None:
        candidates.append((3, f"竞争稀疏度 {_pct(competition)}（平台供给先验 + 同作者惩罚）",
                           ["competition_norm"]))
    if total is not None:
        candidates.append((4, f"综合评分 {total:.3f}（加权合计）", ["total_score"]))
    candidates.sort(key=lambda item: item[0])
    why = [text for _p, text, _f in candidates[:3]]
    for _p, _t, fields in candidates[:3]:
        evidence.extend(fields)

    # ---------- 风险（逐行差异化，≤2 条，仅字段支持时）----------
    risks: list[tuple[float, str, list[str]]] = []
    if sell_norm is None:
        risks.append((0.0, "可售性未评估：缺少 sellability_norm，无法判断能否交付", ["sellability_norm"]))
    elif sell_norm <= 0.2:
        risks.append((0.1, f"可售性仅 {round(100 * sell_norm)}（低信号）"
                           + (f"：{sell_reason}" if sell_reason else ""),
                      ["sellability_norm", "sellability_reason"]))
    if margin_mid is not None:
        fallback = any(hint in assumption for hint in FALLBACK_HINTS)
        width = (margin_high - margin_low) if (margin_high is not None and margin_low is not None) else None
        if fallback:
            risks.append((1.0, f"毛利低置信：使用品类回退价（毛利估算 {_pct(margin_mid)}），非该机会自身成交价",
                          ["margin_assumption", "margin_mid"]))
        elif width is not None and width > MARGIN_WIDTH_LIMIT:
            risks.append((1.1, f"毛利低置信：区间宽度 {_pct(width)}（{_pct(margin_low)}–{_pct(margin_high)}），估计范围过宽",
                          ["margin_low", "margin_high"]))
    if competition is not None and competition < COMPETITION_LIMIT:
        risks.append((2.0, f"竞争偏密：稀疏度仅 {_pct(competition)}（低于 {_pct(COMPETITION_LIMIT)} 阈值，同质供给多）",
                      ["competition_norm"]))
    if missing:
        risks.append((3.0, f"缺失指标：{missing}", ["missing_metrics"]))
    if margin_mid is not None and (cost_input.lower() == "missing" or not cost_input):
        risks.append((4.0, f"成本缺失：无公开成本输入，毛利 {_pct(margin_mid)} 为假设区间而非实测",
                      ["cost_input", "margin_mid"]))
    if not risks:
        platform = str(row.get("platform") or "未知平台")
        risks.append((9.0, f"数据面未见明显风险项；仍需人工核验 {platform} 原始链接的真实性与可交付性",
                      ["platform", "url"]))
    risks.sort(key=lambda item: item[0])
    risk_texts = [text for _p, text, _f in risks[:2]]
    for _p, _t, fields in risks[:2]:
        evidence.extend(fields)

    # ---------- 商业形态 + 需求档（未分类条目据此区分，写入 profile 便于审计）----------
    if sell_norm is None:
        commercial, commercial_note = "无价格信号", "无价格信号"
    elif sell_norm >= 0.8:
        commercial, commercial_note = "可售", f"可售性 {round(100 * sell_norm)}"
    elif sell_norm <= 0.2:
        commercial, commercial_note = "免费引流", f"可售性 {round(100 * sell_norm)}"
    else:
        commercial, commercial_note = "无价格信号", f"可售性 {round(100 * sell_norm)}（未达可售）"

    if demand is None:
        tier, tier_note = "需求未评估", "需求分位缺失"
    elif demand >= 0.7:
        tier, tier_note = "高", f"需求分位 {_pct(demand)}"
    elif demand >= 0.4:
        tier, tier_note = "中", f"需求分位 {_pct(demand)}"
    else:
        tier, tier_note = "低", f"需求分位 {_pct(demand)}"

    if intent == "未分类":
        positioning = (f"{commercial}（{commercial_note}）的{tier}需求线索（{tier_note}），"
                       f"品类待确认，需人工打开原始链接判断交付形态{carrier}")
        evidence.extend(["sellability_norm", "demand_norm"])
    else:
        positioning = f"{intent}，面向{target_user}，交付形态为{deliverable}{carrier}"

    return {
        "product_type": intent,
        "target_user": target_user,
        "deliverable": deliverable,
        "positioning": positioning,
        "carrier": carrier.lstrip("；"),
        "commercial_form": commercial,
        "demand_tier": tier,
        "why": why,
        "risks": risk_texts,
        "sellability_bucket": sell_bucket,
        "evidence_fields": sorted(set(evidence)),
    }


def search_blob(row: dict, analysis: dict) -> str:
    """关键词搜索用：产品摘要 + 原始标题 + 平台（不改变筛选语义）。"""
    parts = [str(row.get("title") or ""), str(row.get("platform") or ""), str(row.get("author") or ""),
             str(row.get("item_id") or ""), str(row.get("url") or ""),
             analysis["product_type"], analysis["target_user"], analysis["deliverable"],
             analysis.get("carrier", ""), " ".join(analysis["why"]), " ".join(analysis["risks"])]
    return " ".join(parts).lower()
