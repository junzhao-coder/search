"""机会页（仅商品型）与「教程与内容」页（仅内容型）渲染。

- `/opportunities`：只显示**已归类商品型**（25 条），漏斗 `采集60 → 商品25（达线X/弱信号Y） → 教程与内容13（另页） → 已剔除22`。
- `/content`：只显示**内容型三类**（13 条），无货源/无毛利/无可售性，改为“参考价值：可作选题/导购参考，非自营商品”，每人话一句。
- 质量线为**可选开关**（默认关）：`?quality=1` 时只用达线集合，组行标注口径。
"""

from __future__ import annotations

import html

from analysis import build_analysis
from taxonomy import CONTENT_NAMES, FALLBACK_NAME, build_categories, classify
from textindex import build_text_index

PENDING_CATEGORY = "Notion 其它（待人工）"
UNCLASSIFIED_CATEGORY = FALLBACK_NAME

QUALITY_DEMAND = 0.70
QUALITY_SELL = 0.80

# 每个内容类型一句人话解释（非数据结论，明确标注）
CONTENT_PLAIN = {
    "Notion 资源推荐清单": "他人整理的模板合集，可作选题或导购参考（通用判断，非数据结论）",
    "Notion 使用教程/导入设置": "教人导入/设置模板的操作型内容，适合做引流或承接转化（通用判断，非数据结论）",
    "Notion 教学变现": "教人做模板变现的内容，可参考其选题与话术（通用判断，非数据结论）",
}


def _num(value):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number == number and abs(number) != float("inf") else None


def reference_ids(data: dict) -> set[str]:
    return {str(r.get("opportunity_id") or "") for r in (data.get("join") or [])
            if str(r.get("reference_max") or "").strip()}


def meets_quality(row: dict, refs: set[str]) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    demand = _num(row.get("demand_norm"))
    sell = _num(row.get("sellability_norm"))
    if demand is not None and demand >= QUALITY_DEMAND:
        reasons.append(f"需求分位 {demand * 100:.0f}%≥70%")
    if sell is not None and sell >= QUALITY_SELL:
        reasons.append(f"可售性 {round(sell * 100)}≥80")
    if str(row.get("item_id") or "") in refs:
        reasons.append("有参考价")
    return bool(reasons), reasons


def split_rows(rows: list[dict], data: dict) -> dict:
    """拆成 kept（已归类且达线）/ weak（已归类弱信号）/ pending（其它+未归类）。"""
    texts = build_text_index()
    refs = reference_ids(data)
    kept, weak, pending = [], [], []
    for row in rows:
        item_id = str(row.get("item_id") or "")
        entry = texts.get(item_id) or {}
        tax = classify(row, entry.get("text"), entry.get("source") or "")
        record = {"row": row, "tax": tax, "text_source": entry.get("source") or "title"}
        if tax["category"] in (PENDING_CATEGORY, UNCLASSIFIED_CATEGORY):
            record["reason"] = f"未归类到具体用途（{tax['category']}）"
            pending.append(record)
            continue
        ok, why = meets_quality(row, refs)
        record["quality"] = why
        if ok:
            kept.append(record)
        else:
            record["reason"] = "已归类但信号弱（需求<70% 且 可售性<80 且 无参考价）"
            weak.append(record)
    return {"kept": kept, "weak": weak, "pending": pending, "refs": refs}


def _esc(value) -> str:
    return html.escape("" if value is None else str(value), quote=True)


def _chip(text: str, tone: str = "neutral") -> str:
    return f'<span class="chip chip-{tone}">{_esc(text)}</span>'


def _basis(hit: dict) -> str:
    words = " / ".join(hit.get("use_hits") or []) or "—"
    src = hit.get("text_source") or "title"
    secondary = "、".join(hit.get("secondary_tags") or [])
    return f"{words}（{src}）" + (f" ｜ 兼：{secondary}" if secondary else "")


def _member_rows(group: dict, analyses: dict[str, dict]) -> str:
    rows = []
    for item_id in group["members"]:
        hit = (group.get("hit_words") or {}).get(item_id) or {}
        info = analyses.get(item_id) or {}
        why = "".join(f"<li>{_esc(w)}</li>" for w in (info.get("why") or [])) or "<li>—</li>"
        risk = "".join(f"<li>{_esc(x)}</li>" for x in (info.get("risks") or [])) or "<li>—</li>"
        rows.append(
            "<tr>"
            f'<td class="num">{_esc(info.get("_rank") or "")}</td>'
            f'<td class="cell-product"><p class="product-line">{_esc(info.get("positioning") or "—")}</p></td>'
            f'<td class="cell-why"><ul class="why">{why}</ul></td>'
            f'<td class="cell-risk"><ul class="risk">{risk}</ul></td>'
            f'<td class="hits">{_esc(_basis(hit))}</td>'
            "</tr>"
        )
    return ('<table class="inner"><thead><tr><th scope="col">#</th><th scope="col">产品定位</th>'
            '<th scope="col">选择理由</th><th scope="col">主要风险</th><th scope="col">用途判定依据</th>'
            f'</tr></thead><tbody>{"".join(rows)}</tbody></table>')


def _product_five(group: dict) -> str:
    analysis = group.get("analysis") or {}
    parts = [("是什么（具体交付物）", analysis.get("what")),
             ("谁买", analysis.get("who")),
             ("为什么可能卖得动（需求证据 / 可比价格）", analysis.get("demand_evidence")),
             ("竞争与差异化", analysis.get("competition")),
             ("定价、毛利与风险", analysis.get("pricing_risk"))]
    return ('<div class="evidence five-parts"><ol>' + "".join(
        f"<li><strong>{_esc(label)}</strong>：{_esc(text or '需补采集')}</li>" for label, text in parts) + "</ol></div>")


def _analysis_map(records: list[dict], price_stats: dict) -> dict[str, dict]:
    out = {}
    for rec in records:
        info = build_analysis(rec["row"], price_stats)
        info["_rank"] = rec["row"].get("rank")
        out[str(rec["row"].get("item_id") or "")] = info
    return out


def _funnel(total: int, product: int, product_pass: int, product_weak: int,
            content: int, pending: int, only_quality: bool) -> str:
    return (
        '<div class="funnel" role="status">'
        f'<span class="fstep">采集 <strong>{total}</strong></span><span class="farrow">→</span>'
        f'<span class="fstep">商品 <strong>{product}</strong>（达线 {product_pass} / 弱信号 {product_weak}）</span>'
        '<span class="farrow">→</span>'
        f'<span class="fstep"><a href="/content">教程与内容 <strong>{content}</strong>（另页）</a></span>'
        '<span class="farrow">→</span>'
        f'<span class="fstep fstep-warn">已剔除 <strong>{pending}</strong></span>'
        f'<span class="fstep dim">当前口径：{"仅达线" if only_quality else "已归类全部"}</span>'
        '</div>'
    )


def _scope_toggle(state: dict, only_quality: bool, classified: int, kept: int) -> tuple[str, str]:
    base = [f"{k}={v}" for k, v in state.items()
            if k in ("q", "platform", "min_score", "sell", "sort", "dir") and v not in (None, "", "all")]
    on = "/opportunities?" + "&".join(base + ["quality=1"])
    off = "/opportunities?" + ("&".join(base) if base else "")
    toggle = (f'<a class="btn {"btn-primary" if not only_quality else "btn-ghost"}" href="{_esc(off)}">'
              f'已归类全部（{classified}）</a> '
              f'<a class="btn {"btn-primary" if only_quality else "btn-ghost"}" href="{_esc(on)}">'
              f'只看达线（{kept}）</a>')
    note = (f'已归类全部 = {classified} 条（含弱信号）；只看达线 = {kept} 条'
            '（需求分位≥70% 或 可售性≥80 或 有参考价）')
    return toggle, note


def render_grouped(data: dict, args, helpers: dict) -> str:
    """机会页：**只显示商品型**。"""
    esc = helpers["esc"]
    state_chip = helpers["state_chip"]
    table = helpers["table"]
    empty_state = helpers["empty_state"]
    filter_form = helpers["filter_form"]

    import app as wb
    price_stats = data.get("price_stats") or {}
    rows, state = wb.filter_opportunities(data.get("scores") or [], args, price_stats)
    only_quality = str(args.get("quality") or "").lower() in ("1", "true", "on")

    all_rows = data.get("scores") or []
    full = split_rows(all_rows, data)
    classified = full["kept"] + full["weak"]
    products_all = [r for r in classified if r["tax"]["kind"] == "商品"]
    contents_all = [r for r in classified if r["tax"]["kind"] == "内容"]
    products_pass = [r for r in products_all if r in full["kept"]]
    products_weak = [r for r in products_all if r in full["weak"]]

    # 页内筛选后的商品集合
    selected_ids = {str(r.get("item_id") or "") for r in rows}
    scope = [r for r in (full["kept"] if only_quality else classified)
             if r["tax"]["kind"] == "商品" and str(r["row"].get("item_id") or "") in selected_ids]
    product_rows = [r["row"] for r in scope]
    analyses = _analysis_map(scope, price_stats)
    groups = build_categories(product_rows, analyses, price_stats, data.get("sources") or [], build_text_index())

    body_rows = []
    for idx, group in enumerate(groups):
        gid = f"g{idx}"
        secondary = (f'<span class="chip chip-neutral">兼：{_esc("、".join(group.get("secondary_top") or []))}</span>'
                     if group.get("secondary_top") else "")
        sell_mean = f'{group["sellability_mean"] * 100:.0f}' if group.get("sellability_mean") is not None else "—"
        margin_text = (f'{group["margin_range"][0] * 100:.0f}%–{group["margin_range"][1] * 100:.0f}%（假设）'
                       if group.get("margin_range") else "—")
        demand = (f'合计 {group["demand_sum"]:.0f} · 最高分位 {(group["demand_max_norm"] or 0) * 100:.0f}%'
                  if group.get("demand_sum") is not None else "—")
        risks = "".join(f"<li>{_esc(t)}</li>" for t in (group.get("risks_top") or [])) or "<li>—</li>"
        reps = "".join(f'<a href="{_esc(u)}" target="_blank" rel="noopener noreferrer nofollow">{_esc(u[-38:])}</a><br>'
                       for u in (group.get("representative_urls") or [])) or "—"
        src_names = [s.get("name") for s in (group.get("sources") or []) if s.get("name")]
        src_line = (f'<p class="group-src dim">可复用货源（近似匹配）：{_esc("、".join(src_names))}</p>'
                    if src_names else '')
        pick_item = (group.get("members") or [""])[0]
        pick_info = analyses.get(pick_item) or {}
        pick_form = (
            '<form method="post" action="/worksheet/new" class="pick">'
            f'<input type="hidden" name="csrf" value="{_esc(helpers.get("csrf") or "")}">'
            f'<input type="hidden" name="group" value="{_esc(group["group_name"])}">'
            f'<input type="hidden" name="item_id" value="{_esc(pick_item)}">'
            f'<input type="hidden" name="submit_key" value="pick-{_esc(group["group_name"])}-{_esc(pick_item)}">'
            f'<input type="hidden" name="name" value="{_esc(group["group_name"])} 工作单">'
            f'<input type="hidden" name="use_case" value="{_esc(group["group_name"])}">'
            f'<input type="hidden" name="deliverable" value="{_esc(pick_info.get("deliverable") or "待确认")}">'
            f'<input type="hidden" name="target_buyer" value="{_esc(pick_info.get("target_user") or "")}">'
            f'<input type="hidden" name="target_platform" value="xianyu">'
            '<button type="submit" class="btn btn-ghost">选为候选商品</button>'
            '</form>') if pick_item else ""
        body_rows.append(
            f'<tr class="group-row" data-toggle="{gid}">'
            f'<td class="cell-group"><span class="group-name">{_esc(group["group_name"])}</span>'
            f'{state_chip("商品", "ok")}{secondary}'
            f'<p class="group-summary">样本 {group["count"]} 条（口径：{"仅达线" if only_quality else "已归类全部"}）</p>{src_line}{pick_form}</td>'
            f"<td>{esc(demand)}</td>"
            f'<td class="num">{esc(sell_mean)}</td>'
            f'<td class="num margin-cell">{esc(margin_text)}</td>'
            f'<td class="cell-risk"><ul class="risk">{risks}</ul></td>'
            f'<td class="cell-reps">{reps}</td>'
            f'<td class="cell-toggle"><button type="button" class="row-toggle" aria-expanded="false" '
            f'aria-controls="{gid}" data-count="{group["count"]}">展开组内明细（{group["count"]} 条）</button></td>'
            '</tr>'
            f'<tr class="group-detail" id="{gid}" hidden><td colspan="7">'
            f'{_product_five(group)}{_member_rows(group, analyses)}</td></tr>'
        )

    headers = [
        ("商品类型", ""),
        ("需求（合计 · 最高分位）", ""),
        ('<span title="0 = 无售卖信号；100 = 含明确售价与购买入口">可售性均值（0–100）</span>', ""),
        ("毛利区间（模型假设）", ""),
        ("组内高频风险（前 2）", ""),
        ("代表证据", ""),
        ("明细", ""),
    ]
    table_html = (table(headers, body_rows, "按商品类型聚合的机会组") if body_rows
                  else empty_state("没有符合条件的商品型条目", "可调整关键词/平台/最低分，或切换“已归类全部”。"))

    toggle, toggle_note = _scope_toggle(state, only_quality, len(products_all), len(products_pass))
    pending_rows = "".join(
        "<li>" + state_chip(rec["tax"]["category"], "neutral")
        + f' {esc((rec["row"].get("title") or "")[:60])}'
        + f' <span class="dim">— {esc(rec.get("reason"))}</span>'
        + f' · <a href="{esc(rec["row"].get("url"))}" target="_blank" rel="noopener noreferrer nofollow">原链接</a></li>'
        for rec in full["pending"]) or "<li>无</li>"
    weak_rows = "".join(
        "<li>" + state_chip("弱信号", "warn")
        + f' {esc((rec["row"].get("title") or "")[:60])}'
        + f' <span class="dim">— {esc(rec.get("reason"))}</span>'
        + f' · <a href="{esc(rec["row"].get("url"))}" target="_blank" rel="noopener noreferrer nofollow">原链接</a></li>'
        for rec in products_weak) or "<li>无</li>"

    form = filter_form("opportunities", state, ["platform", "min_score", "sell", "sort"], (len(rows), len(all_rows)))
    return f"""
<section class="panel" aria-labelledby="h-opp-group">
  <div class="panel-head"><h2 id="h-opp-group">机会线索（商品型）</h2>
  <p class="hint">默认统计<strong>已归类全部</strong>条目（只剔除未归类）；可切换「只看达线」，达线 = 需求分位≥70% 或 可售性≥80% 或 有参考价。弱信号不并入已剔除，在折叠区单列。内容型（教程/推荐/变现）已移到 <a href="/content">教程与内容</a> 页。</p></div>
  {_funnel(len(all_rows), len(products_all), len(products_pass), len(products_weak), len(contents_all), len(full["pending"]), only_quality)}
  {form}
  <p class="sortbar">统计口径：{toggle}<br><span class="dim">{toggle_note}</span>
    <span class="dim">｜ 剩余 {len(full["pending"])} 条未归类（已剔除，可展开复查）</span></p>
  {table_html}
  <details class="excluded"><summary>已剔除·未归类（{len(full["pending"])} 条：其它 20 + 未归类 2）</summary>
    <ul class="excluded-list">{pending_rows}</ul></details>
  <details class="excluded"><summary>弱信号（{len(products_weak)} 条商品型，未计入“已剔除”；当前口径</summary>
    <ul class="excluded-list">{weak_rows}</ul></details>
  <p class="hint">可售性均值口径：0 = 无售卖信号，100 = 含明确售价与购买入口。</p>
</section>"""


def render_content(data: dict, args, helpers: dict) -> str:
    """教程与内容页：只显示内容型三类；无货源、无毛利、无可售性。"""
    esc = helpers["esc"]
    state_chip = helpers["state_chip"]
    table = helpers["table"]
    empty_state = helpers["empty_state"]

    price_stats = data.get("price_stats") or {}
    all_rows = data.get("scores") or []
    rows, state = __import__("app").filter_opportunities(all_rows, args, price_stats)
    selected_ids = {str(r.get("item_id") or "") for r in rows}
    full = split_rows(all_rows, data)
    content_records = [r for r in (full["kept"] + full["weak"])
                       if r["tax"]["kind"] == "内容" and str(r["row"].get("item_id") or "") in selected_ids]
    analyses = _analysis_map(content_records, price_stats)
    groups = build_categories([r["row"] for r in content_records], analyses, price_stats, [], build_text_index())

    body_rows = []
    for group in groups:
        reps = "".join(f'<a href="{esc(u)}" target="_blank" rel="noopener noreferrer nofollow">{esc(u[-38:])}</a><br>'
                       for u in (group.get("representative_urls") or [])) or "—"
        demand = (f'合计 {group["demand_sum"]:.0f} · 最高分位 {(group["demand_max_norm"] or 0) * 100:.0f}%'
                  if group.get("demand_sum") is not None else "—")
        plain = CONTENT_PLAIN.get(group["group_name"], "内容型素材，可作选题参考（通用判断，非数据结论）")
        body_rows.append(
            "<tr>"
            f'<td class="cell-group"><span class="group-name">{esc(group["group_name"])}</span>'
            f'{state_chip("内容·非商品", "neutral")}'
            f'<p class="group-summary">{esc(plain)}</p></td>'
            f'<td class="num">{esc(group["count"])}</td>'
            f'<td>{esc(demand)}</td>'
            f'<td class="cell-reps">{reps}</td>'
            '<td class="dim">参考价值：可作选题/导购参考，非自营商品</td>'
            "</tr>")

    headers = [("内容类型", ""), ("条数", ""), ("需求（合计 · 最高分位）", ""), ("代表证据（3 条）", ""), ("参考价值", "")]
    table_html = (table(headers, body_rows, "内容型分组") if body_rows
                  else empty_state("没有符合条件的内容型条目", "可调整关键词或平台。"))
    total_content = sum(g["count"] for g in groups)
    return f"""
<section class="panel" aria-labelledby="h-content">
  <div class="panel-head"><h2 id="h-content">教程与内容（非商品）</h2>
  <p class="hint">这里只放内容型：他人整理的模板合集、导入/设置教程、教学变现内容。共 {total_content} 条；
  本页<strong>不显示货源、毛利与可售性</strong>——它们不是自营商品。流量与选题判断若无数值支撑，一律标注“通用建议（非数据结论）”。</p></div>
  {table_html}
  <p class="hint">需求数值来自 <code>scores.csv</code> 的 <code>demand_raw / demand_norm</code>；代表证据为组内评分最高的 3 条原链接。</p>
</section>"""
