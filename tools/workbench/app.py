"""本地机会工作台（独立 Flask UI，只读数据、零业务库写入）。

设计要点：
- 不 import `app` 包（避免触发 create_app/ensure_schema 写 instance/app.db）；
  以文件路径方式加载 `app/dash/data.py` 的纯数据函数 load_dashboard_data。
- 仅绑定 127.0.0.1；无 CDN/外部静态资源；SSR + 原生 JS 渐进增强。
- 五个页面：/（总览）、/opportunities（机会）、/sources（货源）、/collect（采集来源）、/daily（每日快照）。
- 筛选/排序/计数/清空全部走真实查询参数并在服务端生效。
"""

from __future__ import annotations

import html
import importlib.util
import os
import json
import pathlib
import sys
import urllib.parse

import hmac
import secrets

from flask import Flask, Response, redirect, request, session

from analysis import build_analysis, search_blob
from groups import build_groups
from taxonomy import build_categories, classify, summarize_conservation
from textindex import build_text_index
import views_worksheet as vws
import views_wizard as vwiz
import views_leads as vleads
import workflow as wf
import readiness as rd
import samplecheck as sc
import supply as sup
import taxonomy

WORKBENCH_DIR = pathlib.Path(__file__).resolve().parent
ROOT = WORKBENCH_DIR.parents[1]
DATA_PY = ROOT / "app" / "dash" / "data.py"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from tools.selection import bilibili as sel_bili  # noqa: E402
from tools.selection import categories as sel_categories  # noqa: E402
from tools.selection import manual as sel_manual  # noqa: E402
from tools.selection import triage as sel_triage  # noqa: E402
from tools.selection import db as sel_db  # noqa: E402
from tools.selection import rounds as sel_rounds  # noqa: E402

NAV = [("pick", "/pick", "选品"), ("source", "/source", "找货源"), ("copy", "/copy", "写文案")]

PLATFORM_LABEL = {"x": "X", "bilibili": "B 站", "github": "GitHub", "xianyu": "闲鱼", "xiaohongshu": "小红书"}
SORTS = {
    "opportunities": {"score": "total_score", "demand": "demand_raw", "margin": "margin_mid", "rank": "rank"},
    "sources": {"stars": "stars", "risk": "after_sales_risk", "name": "name"},
}


def _load_data_module():
    spec = importlib.util.spec_from_file_location("dash_data_readonly", DATA_PY)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"无法加载数据模块：{DATA_PY}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # 只执行纯 stdlib 解析逻辑，不触碰数据库
    return module


DATA = _load_data_module()
load_dashboard_data = DATA.load_dashboard_data


# ---------------------------------------------------------------- 工具函数
def esc(value) -> str:
    return html.escape("" if value is None else str(value), quote=True)


def num(value, default=0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def fmt_score(value) -> str:
    return f"{num(value):.3f}"


def fmt_pct(value) -> str:
    return f"{num(value) * 100:.1f}%"


def fmt_price(value) -> str:
    if value in (None, ""):
        return "—"
    try:
        return f"¥{float(value):.2f}"
    except (TypeError, ValueError):
        return "—"


def fmt_raw_price(value) -> str:
    """原始标价展示：能安全解析就规范成 ¥数值，否则**原样**输出（不吞成 —）。"""
    if value is None or str(value).strip() == "":
        return "—"
    text = str(value).strip()
    cleaned = (text.replace("¥", "").replace("￥", "").replace(",", "")
                   .replace("，", "").replace("\u3000", "").replace(" ", ""))
    try:
        return f"¥{float(cleaned):.2f}"
    except (TypeError, ValueError):
        return esc(text)


def fmt_margin(row: dict) -> str:
    """毛利是 0–1 的估算比例：显示百分比与区间，绝不加货币符号；缺失显示 —。"""
    mid = row.get("margin_mid")
    if mid in (None, ""):
        return "—"
    low, high = row.get("margin_low"), row.get("margin_high")
    if low in (None, "") or high in (None, ""):
        return f"{num(mid) * 100:.1f}%（估算）"
    return f"{num(mid) * 100:.1f}%（{num(low) * 100:.0f}%–{num(high) * 100:.0f}%，估算）"


SELL_BUCKETS = ("较强售卖", "低信号", "不明确", "未评估")


def sellability(row: dict) -> tuple[str, int | None, str]:
    """**只读** scores.csv 的 `sellability_norm`（0..1），不参与也不发明评分。

    分类（仅按该列阈值）：
      v >= 0.8 → 较强售卖；v <= 0.2 → 低信号；其余 → 不明确；缺失/非有限数值 → 未评估。
    展示分 = round(100*v)；理由取 `sellability_reason` 原文（缺列时才写"缺少真实可售性字段"）。
    """
    raw = row.get("sellability_norm")
    text = "" if raw is None else str(raw).strip()
    try:
        value = float(text)
    except (TypeError, ValueError):
        value = float("nan")
    reason = str(row.get("sellability_reason") or "").strip()
    if text == "" or value != value or value in (float("inf"), float("-inf")):
        return "未评估", None, reason or "缺少真实可售性字段"
    score = round(100 * value)
    if value >= 0.8:
        bucket = "较强售卖"
    elif value <= 0.2:
        bucket = "低信号"
    else:
        bucket = "不明确"
    return bucket, score, reason or "（无理由字段）"


def fmt_size(size) -> str:
    size = int(num(size))
    if size >= 1024 * 1024:
        return f"{size / 1024 / 1024:.1f} MB"
    if size >= 1024:
        return f"{size / 1024:.1f} KB"
    return f"{size} B"


def clean_text(text, limit: int = 160) -> str:
    """仅在展示层清理空白与控制字符，不改原始文件。"""
    raw = "" if text is None else str(text)
    cleaned = "".join(ch if (ch.isprintable() or ch in " \t") else " " for ch in raw)
    cleaned = " ".join(cleaned.split())
    return cleaned if len(cleaned) <= limit else cleaned[: limit - 1] + "…"


def state_chip(text: str, tone: str = "neutral") -> str:
    return f'<span class="chip chip-{tone}">{esc(text)}</span>'


def qs(**params) -> str:
    clean = {k: v for k, v in params.items() if v not in (None, "", "all")}
    return ("?" + urllib.parse.urlencode(clean)) if clean else ""


def sort_link(page: str, key: str, label: str, current: dict) -> str:
    """同列表头再次点击时 desc↔asc 翻转；保留其余全部筛选条件。"""
    active = current.get("sort") == key
    cur_dir = current.get("dir") or "desc"
    new_dir = "asc" if (active and cur_dir == "desc") else "desc"
    params = {k: v for k, v in current.items() if k not in ("sort", "dir")}
    params.update({"sort": key, "dir": new_dir})
    arrow = (" ↑" if cur_dir == "asc" else " ↓") if active else ""
    cls = ' class="sorted"' if active else ""
    next_label = "升序" if new_dir == "asc" else "降序"
    return (f'<a{cls} href="{esc(qs(**params))}" '
            f'aria-label="按{esc(label)}{esc(next_label)}排序">{esc(label)}{arrow}</a>')


# ---------------------------------------------------------------- 数据与筛选
def get_data() -> dict:
    from flask import current_app
    root = current_app.config.get("DATA_ROOT") or ROOT
    return load_dashboard_data(root)


def filter_opportunities(rows: list[dict], args, price_stats: dict | None = None) -> tuple[list[dict], dict]:
    kw = (args.get("q") or "").strip().lower()
    platform = args.get("platform") or "all"
    min_score = args.get("min_score") or ""
    sell = args.get("sell") or "all"
    sort = args.get("sort") or "score"
    direction = args.get("dir") or "desc"
    result = []
    for row in rows:
        if platform != "all" and (row.get("platform") or "") != platform:
            continue
        if min_score:
            if num(row.get("total_score")) < num(min_score):
                continue
        if sell != "all" and sellability(row)[0] != sell:
            continue
        if kw:
            # 关键词同时匹配“产品摘要（类型/目标用户/理由/风险）”与原始标题
            if kw not in search_blob(row, build_analysis(row, price_stats)):
                continue
        result.append(row)
    column = SORTS["opportunities"].get(sort, "total_score")
    reverse = direction != "asc"
    result.sort(key=lambda r: (num(r.get(column)) if column != "rank" else num(r.get(column), 1e9)), reverse=reverse)
    state = {"q": kw, "platform": platform, "min_score": min_score, "sell": sell, "sort": sort, "dir": direction}
    return result, state


def filter_sources(rows: list[dict], args) -> tuple[list[dict], dict]:
    kw = (args.get("q") or "").strip().lower()
    license_filter = args.get("license") or "all"
    sort = args.get("sort") or "stars"
    direction = args.get("dir") or "desc"
    result = []
    for row in rows:
        verdict = row.get("license_verdict") or "未知"
        if license_filter == "待核验":
            if verdict in ("可商用", "需授权"):
                continue
        elif license_filter != "all" and verdict != license_filter:
            continue
        if kw:
            haystack = " ".join(str(row.get(k) or "") for k in ("name", "type", "repo_or_url", "license_spdx", "license_reason")).lower()
            if kw not in haystack:
                continue
        result.append(row)
    column = SORTS["sources"].get(sort, "stars")
    if column == "after_sales_risk":
        weight = {"低": 0, "中": 1, "高": 2}
        result.sort(key=lambda r: weight.get(r.get("after_sales_risk") or "", -1), reverse=direction != "asc")
    elif column == "name":
        result.sort(key=lambda r: r.get("name") or "", reverse=direction != "asc")
    else:
        result.sort(key=lambda r: num(r.get(column)), reverse=direction != "asc")
    return result, {"q": kw, "license": license_filter, "sort": sort, "dir": direction}


def filter_items(rows: list[dict], args) -> tuple[list[dict], dict]:
    kw = (args.get("q") or "").strip().lower()
    result = [r for r in rows if not kw or kw in " ".join(str(v) for v in r.values()).lower()]
    return result, {"q": kw}


# ---------------------------------------------------------------- 版式
def _recent_workorders(limit: int = 10) -> list[dict]:
    """“继续已有工作单”：只读连接读取，库不存在/异常时返回空列表（GET 零写、不 500）。"""
    conn = wf.connect_ro()
    if conn is None:
        return []
    try:
        records = wf.list_all(conn)
    except Exception:  # noqa: BLE001 只读失败不应影响选品页渲染
        return []
    finally:
        conn.close()
    records.sort(key=lambda r: str(r.get("updated_at") or ""), reverse=True)
    out = []
    for record in records[:limit]:
        state = rd.readiness(record)
        ok = sum(1 for c in state["checks"] if c["ok"])
        out.append({**record, "ready_ok": ok, "ready_total": len(state["checks"])})
    return out


def _current_wo() -> str:
    """当前工作单：取路径里的 workorder_id 或查询/表单里的 wo；不引入额外状态。"""
    view_args = request.view_args or {}
    return str(view_args.get("workorder_id") or request.args.get("wo") or request.form.get("wo") or "").strip()


def layout(page: str, data: dict, body: str, subtitle: str = "", flash: str = "") -> str:
    wo = _current_wo()
    items = []
    for key, href, label in NAV:
        if key == "pick":
            target = href + (f"?wo={wo}" if wo else "")
        else:
            target = f"{href}?wo={wo}" if wo else href
        items.append((key, target, label))
    nav_items = "".join(
        f'<li><a href="{esc(href)}"{" aria-current=\"page\"" if key == page else ""}>'
        f'<span class="nav-label">{esc(label)}</span></a></li>'
        for key, href, label in items
    )
    counts = data.get("counts", {})
    warnings = data.get("warnings") or []
    warn_html = ""
    if warnings:
        warn_html = (
            '<div class="notice notice-warn" role="status">'
            f'<strong>数据提示</strong><ul>' + "".join(f"<li>{esc(w)}</li>" for w in warnings) + "</ul></div>"
        )
    fresh = data.get("generated_at") or "暂无数据"
    freshness = state_chip(f"数据快照 {fresh}", "neutral") if fresh != "暂无数据" else state_chip("数据缺失", "warn")
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(subtitle or '机会工作台')} · 本地机会工作台</title>
<link rel="stylesheet" href="/static/app.css">
</head>
<body>
<a class="skip" href="#main">跳到主要内容</a>
<div class="shell">
  <aside class="sidebar" id="sidebar">
    <div class="brand"><span class="dot" aria-hidden="true"></span><span>机会工作台</span></div>
    <nav aria-label="主导航"><ul>{nav_items}</ul></nav>
    <div class="side-meta">
      <p class="meta-line">机会 {counts.get('scores', 0)} · 货源 {counts.get('sources', 0)}</p>
      <p class="meta-line">价格信号 {counts.get('prices', 0)} · 联动 {counts.get('join', 0)}</p>
      <p class="meta-line dim">只读本地文件 · 无业务库写入</p>
    </div>
  </aside>
  <div class="main-col">
    <header class="topbar">
      <button class="nav-toggle" type="button" aria-expanded="false" aria-controls="sidebar">目录</button>
      <div class="topbar-text">
        <h1>{esc(subtitle or '总览')}</h1>
        <div class="topbar-meta">{freshness}<span class="sep">·</span><span class="dim">只读快照，非实时在线</span></div>
      </div>
    </header>
    <main id="main" tabindex="-1">
      {warn_html}
      {flash}
      {body}
    </main>
    <footer class="foot">
      <p>本地只读工作台 · 数据来自 docs/validation/money-project 与 tools/platform-login；毛利为低置信估算，需人工价格核验。</p>
    </footer>
  </div>
</div>
<script src="/static/app.js" defer></script>
</body>
</html>"""


def stat_line(items: list[tuple[str, str, str]]) -> str:
    cells = "".join(
        f'<div class="stat"><span class="stat-label">{esc(label)}</span>'
        f'<span class="stat-value">{esc(value)}</span><span class="stat-note">{esc(note)}</span></div>'
        for label, value, note in items
    )
    return f'<div class="stat-strip">{cells}</div>'


def filter_form(page: str, state: dict, fields: list[str], counts: tuple[int, int], extra: str = "") -> str:
    total = counts[1]
    shown = counts[0]
    q_val = esc(state.get("q") or "")
    parts = [
        f'<form class="filters" method="get" action="{esc("/" + page if page != "index" else "/")}" role="search">',
        f'<label class="field"><span>关键词</span><input type="search" name="q" value="{q_val}" '
        f'placeholder="标题 / 作者 / 编号" autocomplete="off"></label>',
    ]
    if "platform" in fields:
        options = "".join(
            f'<option value="{esc(v)}"{" selected" if state.get("platform") == v else ""}>{esc(label)}</option>'
            for v, label in [("all", "全部平台")] + [(k, PLATFORM_LABEL.get(k, k)) for k in ("x", "bilibili", "github")]
        )
        parts.append(f'<label class="field"><span>平台</span><select name="platform">{options}</select></label>')
    if "license" in fields:
        options = "".join(
            f'<option value="{esc(v)}"{" selected" if state.get("license") == v else ""}>{esc(label)}</option>'
            for v, label in [("all", "全部许可"), ("可商用", "可商用"), ("需授权", "需授权"), ("待核验", "待核验（禁止/不明/未知）")]
        )
        parts.append(f'<label class="field"><span>许可</span><select name="license">{options}</select></label>')
    if "sell" in fields:
        options = "".join(
            f'<option value="{esc(v)}"{" selected" if state.get("sell") == v else ""}>{esc(label)}</option>'
            for v, label in [("all", "全部可售性"), ("较强售卖", "较强售卖"), ("低信号", "低信号（需求/赠送）"),
                             ("不明确", "不明确"), ("未评估", "未评估")]
        )
        parts.append(f'<label class="field"><span>可售性</span><select name="sell">{options}</select></label>')
    if "min_score" in fields:
        parts.append(
            '<label class="field"><span>最低分</span>'
            f'<input type="number" name="min_score" step="0.05" min="0" max="1" value="{esc(state.get("min_score") or "")}" '
            'placeholder="如 0.7"></label>'
        )
    if "sort" in fields:
        parts.append(
            f'<input type="hidden" name="sort" value="{esc(state.get("sort") or "")}">'
            f'<input type="hidden" name="dir" value="{esc(state.get("dir") or "")}">'
        )
    parts.append('<div class="filter-actions"><button type="submit" class="btn btn-primary">筛选</button>')
    parts.append(f'<a class="btn btn-ghost" href="{esc("/" + page)}">清空条件</a>')
    parts.append(f'<span class="filter-count" role="status">筛后 <strong>{shown}</strong> / 共 {total}</span></div>')
    parts.append("</form>")
    if extra:
        parts.append(extra)
    return "".join(parts)


def table(headers: list[tuple[str, str]], rows: list[str], caption: str) -> str:
    head = "".join(f"<th scope=\"col\">{h}</th>" for h, _ in headers)
    return (
        f'<div class="table-wrap"><table><caption class="sr-only">{esc(caption)}</caption>'
        f"<thead><tr>{head}</tr></thead><tbody>{''.join(rows)}</tbody></table></div>"
    )


def empty_state(title: str, hint: str) -> str:
    return f'<div class="empty" role="status"><p class="empty-title">{esc(title)}</p><p class="dim">{esc(hint)}</p></div>'


# ---------------------------------------------------------------- 页面
def page_index(data: dict) -> str:
    scores = data.get("scores") or []
    join = data.get("join") or []
    sources = data.get("sources") or []
    prices = data.get("prices") or []
    top = scores[0] if scores else None
    stats = stat_line([
        ("机会线索", str(len(scores)), "已评分"),
        ("货源候选", str(len(sources)), f"可商用 {data.get('license_verdicts', {}).get('可商用', 0)}"),
        ("价格信号", str(len(prices)), "闲鱼样本"),
        ("联动行", str(len(join)), "品类聚合口径"),
    ])
    lead = ""
    if top:
        lead_bucket, lead_score, _ = sellability(top)
        lead_sell = f"{lead_bucket} {lead_score}" if lead_score is not None else lead_bucket
        lead = f"""
<section class="panel" aria-labelledby="h-lead">
  <h2 id="h-lead">当前最值得先核验的一条</h2>
  <div class="lead">
    <div class="lead-main">
      <p class="lead-title">{esc(clean_text(top.get('title'), 120))}</p>
      <p class="lead-meta">{state_chip(PLATFORM_LABEL.get(top.get('platform'), top.get('platform') or '未知'))}
        {state_chip('评分 ' + fmt_score(top.get('total_score')), 'accent')}
        {state_chip('毛利估算，待价格核验', 'warn')}</p>
      <p class="dim">下一步：核对是否存在同款可售商品 → 打开证据链接 → 记录人工核验结论。</p>
    </div>
    <div class="lead-side">
      <dl class="kv">
        <dt>需求分位</dt><dd>{fmt_pct(top.get('demand_norm'))}</dd>
        <dt>竞争稀疏</dt><dd>{fmt_pct(top.get('competition_norm'))}</dd>
        <dt>可售性</dt><dd>{esc(lead_sell)}</dd>
      </dl>
      <a class="btn btn-primary" href="/opportunities?q=&sort=score&dir=desc">查看全部机会</a>
    </div>
  </div>
</section>"""
    join_rows = "".join(
        "<tr>"
        f"<td>{esc(r.get('rank'))}</td>"
        f"<td>{esc(PLATFORM_LABEL.get(r.get('platform'), r.get('platform')))}</td>"
        f"<td class=\"cell-title\">{esc(clean_text(r.get('title'), 70))}</td>"
        f"<td>{esc(r.get('price_category'))}</td>"
        f"<td>{state_chip(r.get('price_scope') or '未知', 'neutral')}</td>"
        f"<td>{esc(r.get('price_signal_count'))}</td>"
        f"<td>{fmt_price(r.get('effective_low'))} – {fmt_price(r.get('effective_high'))}</td>"
        f"<td>{esc(r.get('wants_sum'))}</td>"
        "</tr>"
        for r in join[:5]
    )
    join_table = table(
        [("排名", ""), ("平台", ""), ("机会标题", ""), ("品类", ""), ("价格口径", ""), ("信号数", ""), ("有效区间", ""), ("想要合计", "")],
        list(join_rows), "机会与货源联动前五行",
    ) if join_rows else empty_state("暂无联动数据", "opportunity_sourcing_top10.csv 缺失或为空。")
    return lead + stats + f"""
<section class="panel" aria-labelledby="h-join">
  <div class="panel-head">
    <h2 id="h-join">机会—货源联动</h2>
    <a class="link" href="/sources">查看货源与价格明细</a>
  </div>
  <p class="hint">价格口径说明：<code>all_20_fallback</code> = 无同品类货源时用全部 20 条闲鱼信号作篮子代理；<code>category_filtered</code> = 按品类过滤。想要数不是销量，划线价不是成交价。</p>
  {join_table}
</section>"""


def page_opportunities_items(data: dict, args) -> str:
    price_stats = data.get("price_stats") or {}
    rows, state = filter_opportunities(data.get("scores") or [], args, price_stats)
    body_rows = []
    for row in rows:
        info = build_analysis(row, price_stats)
        breakdown = (
            f"需求 {fmt_score(row.get('demand_weighted'))} · 竞争 {fmt_score(row.get('competition_weighted'))} · "
            f"毛利 {fmt_score(row.get('margin_weighted'))} · 履约 {fmt_score(row.get('fulfillment_weighted'))} · "
            f"合规 {fmt_score(row.get('compliance_weighted'))} · 可复制 {fmt_score(row.get('replicability_weighted'))} · "
            f"可售性 {fmt_score(row.get('sellability_weighted'))}"
        )
        evidence = (
            '<div class="evidence">'
            f'<p><span class="dim">原始标题</span> {esc(clean_text(row.get("title"), 220) or "—")}</p>'
            f'<p><span class="dim">作者 / 时间</span> {esc(row.get("author") or "—")} · {esc(row.get("published_at") or "—")}</p>'
            f'<p><span class="dim">原始链接</span> <a href="{esc(row.get("url"))}" rel="noopener noreferrer nofollow" target="_blank">{esc(clean_text(row.get("url"), 80))}</a></p>'
            f'<p><span class="dim">评分构成</span> {esc(breakdown)}</p>'
            f'<p><span class="dim">毛利假设</span> {esc(clean_text(row.get("margin_assumption"), 180) or "—")}</p>'
            f'<p><span class="dim">成本输入</span> {esc(row.get("cost_input") or "缺失")} · <span class="dim">说明</span> {esc(clean_text(row.get("cost_note"), 120) or "—")}</p>'
            f'<p><span class="dim">生成依据字段</span> {esc("、".join(info["evidence_fields"]))}</p>'
            f'<p><span class="dim">原始引用</span> {esc(row.get("raw_ref") or "—")} · <span class="dim">来源</span> {esc(row.get("source") or "—")}</p>'
            '</div>'
        )
        bucket, sscore, sreason = sellability(row)
        sell_tone = {"较强售卖": "ok", "低信号": "warn"}.get(bucket, "neutral")
        sell_chip = (state_chip(f"{bucket} {sscore}" if sscore is not None else bucket, sell_tone)
                     + f'<span class="dim sell-reason">{esc(sreason)}</span>')
        why_items = "".join(f"<li>{esc(w)}</li>" for w in info["why"]) or "<li>暂无可支撑的选择理由（相关字段缺失）</li>"
        risk_items = "".join(f"<li>{esc(r)}</li>" for r in info["risks"]) or "<li>—</li>"
        product_cell = (
            '<div class="product">'
            f'<span class="product-type">{esc(info["product_type"])}</span>'
            f'<p class="product-line">{esc(info["positioning"])}</p>'
            f'<details class="product-details"><summary>原始证据</summary>{evidence}</details>'
            '</div>'
        )
        body_rows.append(
            "<tr>"
            f'<td class="num">{esc(row.get("rank"))}</td>'
            f'<td class="cell-product">{product_cell}</td>'
            f'<td class="cell-why"><ul class="why">{why_items}</ul></td>'
            f'<td class="cell-risk"><ul class="risk">{risk_items}</ul></td>'
            f'<td class="num strong">{fmt_score(row.get("total_score"))}</td>'
            f"<td>{sell_chip}</td>"
            "</tr>"
        )
    sortbar = " · ".join([
        sort_link("opportunities", "score", "评分", state),
        sort_link("opportunities", "demand", "需求分位", state),
        sort_link("opportunities", "margin", "毛利", state),
        sort_link("opportunities", "rank", "排名", state),
    ])
    headers = [
        ("排名", ""),
        ("产品定位（是什么 / 给谁用 / 交付形态）", ""),
        ("选择理由（挂真实指标）", ""),
        ("主要风险（来自实际字段）", ""),
        ("评分", ""),
        ("可售性", ""),
    ]
    table_html = table(headers, body_rows, "机会产品分析列表") if body_rows else empty_state("没有符合条件的机会", "试试放宽关键词或最低分，或点“清空条件”。")
    form = filter_form("opportunities", state, ["platform", "min_score", "sell", "sort"], (len(rows), len(data.get("scores") or []))) + (
        f'<p class="sortbar">视图：<a href="{esc(qs(**{**state, "view": "grouped"}))}">按品类</a> · <strong>按条目</strong></p>')
    return f"""
<section class="panel" aria-labelledby="h-opp">
  <div class="panel-head"><h2 id="h-opp">机会线索（产品分析视图）</h2>
  <p class="hint">共 {len(data.get('scores') or [])} 条；每条给「产品定位 / 选择理由 / 主要风险」，原始标题与链接收在“原始证据”里。文案由 scores.csv 字段确定性生成，不调用模型、不臆造数字。</p></div>
  {form}
  <p class="sortbar">排序：{sortbar}</p>
  {table_html}
  <p class="hint">毛利为低置信估算（模型假设，非成交数据），以百分比区间显示、不折合货币；货币符号只用于真实标价。
  可售性<strong>只读</strong> <code>sellability_norm</code>（0–1），展示为 <code>100×该值</code>，理由取 <code>sellability_reason</code> 原文：
  <strong>较强售卖</strong>＝≥0.8；<strong>低信号</strong>＝≤0.2；其余为<strong>不明确</strong>；字段缺失或非数值才显示<strong>未评估</strong>。本界面不另造评分，也不承诺收益。</p>
</section>"""


def page_opportunities(data: dict, args, csrf: str = "") -> str:
    """默认按品类聚合（已归类 + 质量线）；`view=items` 逐条；`view=legacy_grouped` 回退旧实现。"""
    if (args.get("view") or "grouped") == "items":
        return page_opportunities_items(data, args)
    if (args.get("view") or "grouped") == "grouped":
        from views_grouped import render_grouped
        return render_grouped(data, args, {
            "esc": esc, "state_chip": state_chip, "table": table, "empty_state": empty_state,
            "filter_form": filter_form, "fmt_score": fmt_score, "clean_text": clean_text, "csrf": csrf,
        })
    # view=legacy_grouped：保留上一版分组实现，便于对比回退（默认不走这里）

    price_stats = data.get("price_stats") or {}
    rows, state = filter_opportunities(data.get("scores") or [], args, price_stats)
    analyses = {str(r.get("item_id") or ""): build_analysis(r, price_stats) for r in rows}
    groups = build_categories(rows, analyses, price_stats, data.get("sources") or [], build_text_index())
    group_sort = args.get("group_sort") or "score"
    if group_sort == "count":
        groups.sort(key=lambda g: (-(g["count"] or 0), -(g["max_total_score"] or 0.0)))

    row_index = {str(r.get("item_id") or ""): r for r in rows}
    body_rows = []
    for group in groups:
        members_html = []
        for item_id in group["members"]:
            row = row_index.get(item_id) or {}
            info = analyses.get(item_id) or {}
            why = "".join(f"<li>{esc(w)}</li>" for w in (info.get("why") or [])) or "<li>—</li>"
            risk = "".join(f"<li>{esc(x)}</li>" for x in (info.get("risks") or [])) or "<li>—</li>"
            hit = (group.get("hit_words") or {}).get(item_id) or {}
            words = " / ".join(hit.get("use_hits") or []) or "—"
            src = hit.get("text_source") or "title"
            hits = f"{words}（{src}）"
            if hit.get("secondary_tags"):
                hits += " ｜ 兼：" + "、".join(hit["secondary_tags"])
            members_html.append(
                "<tr>"
                f'<td class="num">{esc(row.get("rank"))}</td>'
                f'<td class="cell-product"><p class="product-line">{esc(info.get("positioning") or "—")}</p></td>'
                f'<td class="cell-why"><ul class="why">{why}</ul></td>'
                f'<td class="cell-risk"><ul class="risk">{risk}</ul></td>'
                f'<td class="num strong">{fmt_score(row.get("total_score"))}</td>'
                f'<td class="dim hits">{esc(hits)}</td>'
                "</tr>"
            )
        member_table = (
            '<table class="inner"><thead><tr><th scope="col">排名</th><th scope="col">产品定位</th>'
            '<th scope="col">选择理由</th><th scope="col">主要风险</th><th scope="col">评分</th>'
            '<th scope="col">用途判定依据</th></tr></thead>'
            f'<tbody>{"".join(members_html)}</tbody></table>'
        )
        reps = "".join(
            f'<a href="{esc(url)}" target="_blank" rel="noopener noreferrer nofollow">{esc(clean_text(url, 40))}</a><br>'
            for url in (group.get("representative_urls") or [])
        ) or "—"
        srcs = "".join(
            f'{esc(src.get("name"))}<span class="dim">（{esc(src.get("type") or "")}'
            f'·{esc(src.get("license_verdict") or "未知")}·{esc(src.get("match") or "近似匹配")}）</span><br>'
            for src in (group.get("sources") or [])
        ) or "—"
        risks_html = "".join(f"<li>{esc(text)}</li>" for text in (group.get("risks_top") or [])) or "<li>—</li>"
        if group.get("margin_range"):
            low, high = group["margin_range"]
            margin = f"{low * 100:.0f}%–{high * 100:.0f}%（假设）"
        else:
            margin = "—"
        sell_mean = (f'{group["sellability_mean"] * 100:.0f}' if group.get("sellability_mean") is not None else "—")
        demand = (f'合计 {group["demand_sum"]:.0f} · 最高分位 {(group["demand_max_norm"] or 0) * 100:.0f}%'
                  if group.get("demand_sum") is not None else "—")
        analysis = group.get("analysis") or {}
        five_parts = [("是什么（具体交付物）", analysis.get("what")),
                      ("谁买", analysis.get("who")),
                      ("为什么可能卖得动（需求证据 / 可比价格）", analysis.get("demand_evidence")),
                      ("竞争与差异化", analysis.get("competition")),
                      ("定价、毛利与风险", analysis.get("pricing_risk"))]
        analysis_html = ('<div class="evidence five-parts"><ol>' + "".join(
            f"<li><strong>{esc(label)}</strong>：{esc(text or '需补采集')}</li>" for label, text in five_parts
        ) + "</ol></div>")
        reason_html = (f'<p class="hint">未归类原因：{esc(group.get("unclassified_reason"))}</p>'
                       if group.get("unclassified_reason") else "")
        secondary_chip = (f'<span class="chip chip-neutral">兼：{esc("、".join(group.get("secondary_top") or []))}</span>'
                          if group.get("secondary_top") else "")
        body_rows.append(
            '<tr class="group-row">'
            f'<td class="cell-group"><span class="group-name">{esc(group["group_name"])}</span>'
            f'<span class="chip chip-neutral">{group["count"]} 条 · 占 {group.get("share", 0) * 100:.0f}%</span>'
            f'{secondary_chip}'
            f'<p class="group-summary">{esc(analysis.get("what") or "")}'
            f' · {esc((analysis.get("demand_evidence") or "")[:90])}</p></td>'
            f"<td>{esc(demand)}</td>"
            f'<td>{state_chip("商品" if group.get("kind") == "商品" else "内容·非商品", "ok" if group.get("kind") == "商品" else "neutral")}</td>'
            f'<td class="num">{esc(sell_mean if group.get("kind") == "商品" else "—")}</td>'
            f'<td class="num margin-cell">{esc(margin if group.get("kind") == "商品" else "—（内容型不适用）")}</td>'
            f'<td class="cell-risk"><ul class="risk">{risks_html}</ul></td>'
            f'<td class="cell-reps">{reps}</td>'
            f'<td class="cell-src">{srcs}</td>'
            "</tr>"
            f'<tr class="group-detail"><td colspan="7"><details>'
            f'<summary>展开组内明细与五段分析（{group["count"]} 条）</summary>'
            f'{reason_html}{analysis_html}{member_table}</details></td></tr>'
        )

    headers = [
        ("品类 / 载体组", ""),
        ("需求（合计 · 最高分位）", ""),
        ("类型", ""),
        ("可售性均值", ""),
        ("毛利区间（模型假设）", ""),
        ("组内高频风险（前 2）", ""),
        ("代表证据（3 条）", ""),
        ("可复用货源（近似匹配）", ""),
    ]
    table_html = (table(headers, body_rows, "按品类聚合的机会组") if body_rows
                  else empty_state("没有符合条件的机会", "试试放宽关键词或最低分，或点“清空条件”。"))
    shown = len(rows)
    form = filter_form("opportunities", state, ["platform", "min_score", "sell", "sort"], (shown, len(data.get("scores") or [])))
    toggle = (
        f'<p class="sortbar">视图：<strong>按品类</strong> · '
        f'<a href="{esc(qs(**{**state, "view": "items"}))}">按条目</a>'
        f' ｜ 组排序：<a href="{esc(qs(**{**state, "group_sort": "score"}))}">按最高评分</a> · '
        f'<a href="{esc(qs(**{**state, "group_sort": "count"}))}">按条数</a></p>'
    )
    product_count = sum(g.get("count", 0) for g in groups if g.get("kind") == "商品")
    content_count = sum(g.get("count", 0) for g in groups if g.get("kind") == "内容")
    remaining = sum(g.get("count", 0) for g in groups if g.get("category") == "Notion 其它（待人工）")
    remaining_note = (f'<strong>剩余 {remaining} 条需补采集/人工判断</strong>（逐条缺词见 '
                      f'<code>categories.json.other_missing</code>）。' if remaining else "")
    return f"""
<section class="panel" aria-labelledby="h-opp-group">
  <div class="panel-head"><h2 id="h-opp-group">机会线索（载体 × 用途）</h2>
  <p class="hint">共 {len(data.get('scores') or [])} 条原始机会，合并为 {len(groups)} 组：<strong>可售商品 {product_count} 条</strong> · <strong>内容型 {content_count} 条（不计入可售）</strong>。
  内容型（教程/推荐/变现教学）不估算毛利，第五段改为「流量价值 · 引流去向 · 相邻可带货商品」。同类型合并一行，可展开组内明细与五段分析。{remaining_note}</p></div>
  {form}
  {toggle}
  {table_html}
  <p class="hint">统计口径：条数、<code>demand_raw</code> 合计、<code>demand_norm</code> 最高分位、<code>sellability_norm</code> 均值、
  <code>margin_low..margin_high</code> 并集区间（模型假设）、组内高频风险前 2；代表证据取组内评分最高 3 条链接；
  货源来自 <code>sources.csv</code> 的 <code>type/name</code> 关键词匹配，标“近似匹配”，<strong>不代表已获授权</strong>。</p>
</section>"""


def page_sources(data: dict, args) -> str:
    rows, state = filter_sources(data.get("sources") or [], args)
    body_rows = []
    for row in rows:
        tone = {"可商用": "ok", "需授权": "warn"}.get(row.get("license_verdict") or "", "neutral")
        evidence = (
            '<div class="evidence">'
            f'<p><span class="dim">许可理由</span> {esc(clean_text(row.get("license_reason"), 160) or "—")}</p>'
            f'<p><span class="dim">关键句</span> {esc(clean_text(row.get("license_key_sentence"), 160) or "—")}</p>'
            f'<p><span class="dim">证据</span> <a href="{esc(row.get("evidence_url"))}" rel="noopener noreferrer nofollow" target="_blank">{esc(clean_text(row.get("evidence_url"), 80))}</a></p>'
            f'<p><span class="dim">成本/投入/交付</span> {esc(row.get("cost") or "—")} · {esc(row.get("effort") or "—")} · {esc(row.get("delivery") or "—")}</p>'
            f'<p><span class="dim">核验时间</span> {esc(row.get("checked_at") or "—")} · <span class="dim">来源</span> {esc(row.get("license_source") or "—")}</p>'
            '</div>'
        )
        body_rows.append(
            "<tr>"
            f'<td class="cell-title"><details><summary>{esc(clean_text(row.get("name"), 60))}</summary>{evidence}</details></td>'
            f'<td>{esc(row.get("type"))}</td>'
            f'<td>{state_chip(row.get("license_verdict") or "未知", tone)}<span class="dim mono">{esc(row.get("license_spdx") or "—")}</span></td>'
            f'<td class="num">{esc(row.get("stars") or "—")}</td>'
            f'<td>{esc(row.get("differentiation"))}</td>'
            f'<td>{esc(row.get("after_sales_risk") or "—")}</td>'
            "</tr>"
        )
    headers = [
        ("货源", ""),
        ("类型", ""),
        (sort_link("sources", "name", "许可/仓库", state), ""),
        (sort_link("sources", "stars", "Stars", state), ""),
        ("差异化", ""),
        (sort_link("sources", "risk", "售后风险", state), ""),
    ]
    table_html = table(headers, body_rows, "货源与许可列表") if body_rows else empty_state("没有符合条件的货源", "试试清空关键词或许可筛选。")
    form = filter_form("sources", state, ["license", "sort"], (len(rows), len(data.get("sources") or [])))

    price_rows = "".join(
        "<tr>"
        f'<td class="cell-title">{esc(clean_text(r.get("title_snippet"), 60))}</td>'
        f'<td class="num">{fmt_raw_price(r.get("listed_price"))}</td>'
        f'<td class="num">{fmt_raw_price(r.get("effective_price"))}</td>'
        f'<td class="num">{esc(r.get("wants") or "—")}</td>'
        f'<td>{esc(r.get("province") or "—")}</td>'
        f'<td>{state_chip(r.get("parse_status") or "未知", "neutral")}</td>'
        "</tr>"
        for r in (data.get("prices") or [])[:20]
    )
    join_rows = "".join(
        "<tr>"
        f'<td class="num">{esc(r.get("rank"))}</td>'
        f'<td class="cell-title">{esc(clean_text(r.get("title"), 60))}</td>'
        f'<td>{esc(PLATFORM_LABEL.get(r.get("platform"), r.get("platform")))}</td>'
        f'<td>{esc(r.get("price_category"))}</td>'
        f'<td>{state_chip(r.get("price_scope") or "未知", "neutral")}</td>'
        f'<td class="num">{esc(r.get("price_signal_count"))}</td>'
        f'<td class="num">{fmt_price(r.get("effective_low"))} – {fmt_price(r.get("effective_high"))}</td>'
        f'<td class="num">{fmt_price(r.get("reference_max"))}</td>'
        f'<td>{esc(clean_text(r.get("match_quality"), 40))}</td>'
        "</tr>"
        for r in (data.get("join") or [])
    )
    stats = data.get("price_stats", {})
    return f"""
<section class="panel" aria-labelledby="h-src">
  <div class="panel-head"><h2 id="h-src">货源与许可</h2><p class="hint">“可商用”需保留声明，不等于附带素材可转售；点击名称展开许可理由与证据。</p></div>
  {form}
  {table_html}
</section>
<section class="panel" aria-labelledby="h-price">
  <div class="panel-head"><h2 id="h-price">价格信号（闲鱼样本 {stats.get('count', 0)} 条）</h2>
  <p class="hint">有效价区间 {fmt_price(stats.get('effective_min'))} – {fmt_price(stats.get('effective_max'))}；想要合计 {esc(stats.get('wants_sum', 0))}（兴趣代理，不是销量）。</p></div>
  {table([("标题截取", ""), ("标价", ""), ("有效价", ""), ("想要", ""), ("地区", ""), ("解析状态", "")], [price_rows] if price_rows else [], "价格信号列表") if price_rows else empty_state("暂无价格信号", "price_signals.csv 缺失或为空。")}
</section>
<section class="panel" aria-labelledby="h-join2">
  <div class="panel-head"><h2 id="h-join2">机会—货源联动（{len(data.get('join') or [])} 行）</h2><p class="hint">口径不一：机会 id 为 x:/bili:，价格信号为闲鱼数字 id，二者按品类聚合而非逐条连接。</p></div>
  {table([("排名", ""), ("机会", ""), ("平台", ""), ("品类", ""), ("价格口径", ""), ("信号数", ""), ("有效区间", ""), ("参考上限", ""), ("匹配质量", "")], [join_rows] if join_rows else [], "机会货源联动列表") if join_rows else empty_state("暂无联动数据", "opportunity_sourcing_top10.csv 缺失或为空。")}
</section>"""


def page_collect(data: dict, args) -> str:
    datasets = data.get("datasets") or {}
    rows = []
    for key, entry in datasets.items():
        tone = "ok" if entry.get("exists") and not entry.get("error") else "warn"
        state_text = "可用" if entry.get("exists") and not entry.get("error") else (entry.get("error") or "缺失")
        rows.append(
            "<tr>"
            f'<td class="mono">{esc(key)}</td>'
            f'<td class="mono dim">{esc(entry.get("path"))}</td>'
            f'<td>{state_chip(state_text, tone)}</td>'
            f'<td class="num">{esc(entry.get("count", 0))}</td>'
            f'<td class="num">{esc(entry.get("bad_lines", 0))}</td>'
            f'<td class="num">{fmt_size(entry.get("size", 0))}</td>'
            f'<td class="mono dim">{esc(entry.get("mtime"))}</td>'
            "</tr>"
        )
    platform = args.get("platform") or "all"
    kw_state = {"q": (args.get("q") or "").strip().lower()}
    xianyu, _ = filter_items(data.get("xianyu") or [], args)
    xhs, _ = filter_items(data.get("xiaohongshu") or [], args)
    if platform == "xianyu":
        xhs = []
    elif platform == "xiaohongshu":
        xianyu = []
    item_rows = []
    for label, items in (("闲鱼", xianyu), ("小红书", xhs)):
        for item in items[:20]:
            item_rows.append(
                "<tr>"
                f"<td>{esc(label)}</td>"
                f'<td class="cell-title"><a href="{esc(item.get("href"))}" rel="noopener noreferrer nofollow" target="_blank">{esc(clean_text(item.get("title"), 80))}</a></td>'
                f'<td class="num">{fmt_raw_price(item.get("price"))}</td>'
                "</tr>"
            )
    form = (
        '<form class="filters" method="get" action="/collect" role="search">'
        f'<label class="field"><span>关键词</span><input type="search" name="q" value="{esc(args.get("q") or "")}" placeholder="标题 / 文本"></label>'
        '<label class="field"><span>平台</span><select name="platform">'
        + "".join(
            f'<option value="{v}"{" selected" if platform == v else ""}>{label}</option>'
            for v, label in [("all", "全部"), ("xianyu", "闲鱼"), ("xiaohongshu", "小红书")]
        )
        + '</select></label>'
        '<div class="filter-actions"><button type="submit" class="btn btn-primary">筛选</button>'
        '<a class="btn btn-ghost" href="/collect">清空条件</a>'
        f'<span class="filter-count" role="status">筛后 <strong>{len(xianyu) + len(xhs)}</strong> 条</span></div></form>'
    )
    warnings = data.get("warnings") or []
    return f"""
<section class="panel" aria-labelledby="h-files">
  <div class="panel-head"><h2 id="h-files">数据文件状态</h2><p class="hint">刷新只重读本地产物，不会启动采集；时间为文件修改时间（UTC）。</p></div>
  {table([("数据集", ""), ("路径", ""), ("状态", ""), ("行数", ""), ("坏行", ""), ("体积", ""), ("更新时间", "")], rows, "数据集状态")}
  <p class="hint">告警 {len(warnings)} 条{('：' + esc('；'.join(warnings[:3]))) if warnings else '（无）'}。来源不虚标实时：本页仅显示文件快照。</p>
</section>
<section class="panel" aria-labelledby="h-items">
  <div class="panel-head"><h2 id="h-items">平台样本（闲鱼 / 小红书）</h2><p class="hint">已登录采集的只读样本，最多各展示 20 条；“想要/点赞”不代表成交。</p></div>
  {form}
  {table([("平台", ""), ("标题", ""), ("标价", "")], item_rows, "平台样本列表") if item_rows else empty_state("没有匹配的样本", "调整关键词或平台，或清空条件。")}
</section>"""


def page_daily(data: dict, args=None) -> str:
    counts = data.get("counts", {})
    verdicts = data.get("license_verdicts", {})
    stats = data.get("price_stats", {})
    verdict_rows = "".join(
        f"<tr><td>{esc(k)}</td><td class=\"num\">{esc(v)}</td></tr>" for k, v in sorted(verdicts.items())
    )
    dist: dict[str, int] = {}
    for _row in (data.get("scores") or []):
        _b, _s, _r = sellability(_row)
        dist[_b] = dist.get(_b, 0) + 1
    sell_line = "、".join(f"{k} {v}" for k, v in dist.items()) or "—"
    snapshot = stat_line([
        ("评分行", str(counts.get("scores", 0)), "scoring/scores.csv"),
        ("货源行", str(counts.get("sources", 0)), "sourcing/sources.csv"),
        ("价格信号", str(counts.get("prices", 0)), "sourcing/price_signals.csv"),
        ("联动行", str(counts.get("join", 0)), "opportunity_sourcing_top10.csv"),
    ])
    return snapshot + f"""
<section class="panel" aria-labelledby="h-batch">
  <div class="panel-head"><h2 id="h-batch">批次快照</h2><p class="hint">按当前文件产物汇总，不是经营日报；毛利为估算，不显示订单/收益。</p></div>
  <dl class="kv kv-wide">
    <dt>数据快照时间</dt><dd class="mono">{esc(data.get('generated_at') or '暂无数据')}</dd>
    <dt>机会线索</dt><dd>{esc(counts.get('scores', 0))} 条（已评分）</dd>
    <dt>可售性分布</dt><dd>{esc(sell_line)} <span class="dim">（只读 sellability_norm；缺失才未评估）</span></dd>
    <dt>许可分布</dt><dd>{esc('、'.join(f'{k} {v}' for k, v in sorted(verdicts.items())) or '—')}</dd>
    <dt>有效价格区间</dt><dd>{fmt_price(stats.get('effective_min'))} – {fmt_price(stats.get('effective_max'))}（{stats.get('count', 0)} 条样本）</dd>
    <dt>想要合计</dt><dd>{esc(stats.get('wants_sum', 0))} <span class="dim">兴趣代理，不是销量</span></dd>
  </dl>
</section>
<section class="panel" aria-labelledby="h-verdict">
  <div class="panel-head"><h2 id="h-verdict">许可分布明细</h2></div>
  {table([("许可结论", ""), ("数量", "")], [verdict_rows] if verdict_rows else [], "许可分布") if verdict_rows else empty_state("暂无许可数据", "sources.csv 缺失或为空。")}
</section>"""


# ---------------------------------------------------------------- 应用
def create_app(root: str | pathlib.Path | None = None) -> Flask:
    app = Flask(__name__, static_folder=str(WORKBENCH_DIR / "static"), static_url_path="/static")
    app.config["JSON_AS_ASCII"] = False
    app.config["DATA_ROOT"] = str(root) if root else None
    app.secret_key = wf.secret_key()

    def render(page: str, subtitle: str, body_builder) -> Response:
        data = get_data()
        body = body_builder(data)
        return Response(layout(page, data, body, subtitle), mimetype="text/html; charset=utf-8")

    # ---------- 本地写保护：CSRF + 同源 ----------
    def csrf_token() -> str:
        token = session.get("csrf")
        if not token:
            token = secrets.token_urlsafe(24)
            session["csrf"] = token
        return token

    def require_local_write() -> None:
        token = str(request.form.get("csrf") or request.headers.get("X-CSRF-Token") or "")
        expected = str(session.get("csrf") or "")
        try:
            token_b, expected_b = token.encode("utf-8"), expected.encode("utf-8")
        except UnicodeEncodeError:
            raise wf.Reject("csrf_invalid", "CSRF 校验失败：token 编码非法", 403)
        if not expected_b or not token_b or not hmac.compare_digest(token_b, expected_b):
            raise wf.Reject("csrf_invalid", "CSRF 校验失败：请从工作台页面内的表单提交", 403)
        origin = request.headers.get("Origin") or request.headers.get("Referer")
        if origin is not None:
            from urllib.parse import urlparse
            src = urlparse(origin)
            host = urlparse(request.host_url)
            if (src.scheme, src.netloc) != (host.scheme, host.netloc):
                raise wf.Reject("origin_rejected",
                                f"跨站/跨协议或畸形来源被拒绝（origin={origin[:60]!r}，本站={host.scheme}://{host.netloc}）",
                                403)

    @app.errorhandler(wf.Reject)
    def _on_reject(exc: wf.Reject):
        data = get_data()
        body = (f'<section class="panel"><div class="notice notice-warn" role="alert">'
                f'<strong>{esc(exc.code)}</strong>：{esc(exc.message)}</div>'
                f'<p class="hint"><a href="/worksheet">← 返回工作单</a> · <a href="/opportunities">去机会页选品</a></p>'
                f'</section>')
        return Response(layout("worksheet", data, body, "操作被拒绝"), status=exc.status,
                        mimetype="text/html; charset=utf-8")

    def worksheet_gaps(record: dict) -> list[str]:
        _rows, refs = wf.load_sources()
        return wf.derive_gaps(record["snapshot"], refs)

    @app.get("/")
    def index():
        return redirect("/pick", code=302)

    @app.get("/opportunities")
    def opportunities():
        return render("opportunities", "机会线索",
                      lambda d: page_opportunities(d, request.args, csrf_token()))

    @app.get("/content")
    def content():
        from views_grouped import render_content
        return render("content", "教程与内容", lambda d: render_content(d, request.args, {
            "esc": esc, "state_chip": state_chip, "table": table, "empty_state": empty_state,
        }))

    # ---------- 商品工作单（B1） ----------
    # ---------------- B20 三步向导 ----------------
    @app.get("/pick")
    def wizard_pick():
        data = get_data()
        args = {k: request.args.get(k) for k in ("q", "platform", "view", "quality") if request.args.get(k)}
        price_stats = data.get("price_stats") or {}
        rows, _state = filter_opportunities(data.get("scores") or [], args, price_stats)
        analyses = {str(r.get("item_id") or ""): build_analysis(r, price_stats) for r in rows}
        groups = build_categories(rows, analyses, price_stats, data.get("sources") or [], build_text_index())
        pending_names = {taxonomy.FALLBACK_NAME, "Notion 其它（待人工）"}
        content_names = set(taxonomy.CONTENT_NAMES)
        row_index = {str(r.get("item_id") or ""): r for r in rows}
        listed_groups, hidden_content = [], 0
        total_members = 0
        for g in groups:
            name = g.get("category") or ""
            if name in content_names:
                hidden_content += 1
                continue
            members = g.get("members") or []
            sell_vals = []
            for m in members:
                try:
                    sell_vals.append(float(row_index.get(m, {}).get("sellability_norm")))
                except (TypeError, ValueError):
                    continue
            sell_group = g.get("sellability_mean")
            if sell_group is not None:                 # 组级均值：n 用组内成员数（与左侧条数同量级）
                g["sellability_avg"] = round(float(sell_group), 4)
                g["sellability_n"] = len(members)
            elif sell_vals:                            # 回退：组内均值，n=确实带该字段的成员数
                g["sellability_avg"] = round(sum(sell_vals) / len(sell_vals), 4)
                g["sellability_n"] = len(sell_vals)
            else:
                g["sellability_avg"] = None
                g["sellability_n"] = 0
            comp_vals = []
            for m in members:
                try:
                    comp_vals.append(float(row_index.get(m, {}).get("competition_norm")))
                except (TypeError, ValueError):
                    continue
            g["competition_avg"] = round(sum(comp_vals) / len(comp_vals), 4) if comp_vals else None
            g["competition_n"] = len(comp_vals)
            g["pending"] = name in pending_names
            g["selectable"] = not g["pending"]
            listed_groups.append(g)
            total_members += len(members)
        listed_groups.sort(key=lambda g: (-(g.get("max_total_score") or 0.0), -(g.get("count") or 0)))
        meta = {"snapshot": data.get("generated_at") or "未知",
                "groups": len(listed_groups), "members": total_members,
                "hidden_content_groups": hidden_content}
        error = ""
        if request.args.get("err") == "invalid":
            error = "参数无效：请从本页点「选这个」进入。"
        body = vwiz.render_pick(listed_groups, args, csrf_token(), meta=meta, error=error,
                                workorders=_recent_workorders())
        body = ('<p class="hint"><a href="/leads">查看需求线索与轮次 →</a></p>' + body)
        return render("pick", "选品", lambda _d: body)

    def _wizard_record(wo: str):
        conn = wf.connect_ro()
        try:
            return wf.get(conn, wo) if conn is not None else None
        finally:
            if conn is not None:
                conn.close()

    @app.get("/source")
    def wizard_source():
        wo = str(request.args.get("wo") or "").strip()
        if not wo:
            body = vwiz.render_need_wo("source", _recent_workorders())
            return render("source", "找货源", lambda _d: body)
        record = _wizard_record(wo)
        if record is None:
            raise wf.Reject("not_found", "工作单不存在", 404)
        conn = wf.connect_ro()
        try:
            candidates = sup.list_candidates(conn, wo) if conn is not None else []
            last = rd.last_export(conn, wo) if conn is not None else None
        finally:
            if conn is not None:
                conn.close()
        ready = rd.readiness(record)
        error = "请先采用一条货源" if request.args.get("err") == "no_supply" else ""
        body = vwiz.render_source(record, candidates, ready, csrf_token(), last_export=last, error=error)
        return render("source", "找货源", lambda _d: body)

    @app.post("/worksheet/<workorder_id>/source/confirm")
    def wizard_source_confirm(workorder_id: str):
        require_local_write()
        conn = wf.connect()
        try:
            record = wf.get(conn, workorder_id)
        finally:
            conn.close()
        if record is None:
            raise wf.Reject("not_found", "工作单不存在", 404)
        if not record.get("selected_supply_id"):
            return redirect(f"/source?wo={workorder_id}&err=no_supply", code=303)
        return redirect(f"/copy?wo={workorder_id}", code=303)

    @app.get("/copy")
    def wizard_copy():
        wo = str(request.args.get("wo") or "").strip()
        if not wo:
            body = vwiz.render_need_wo("copy", _recent_workorders())
            return render("copy", "写文案", lambda _d: body)
        record = _wizard_record(wo)
        if record is None:
            raise wf.Reject("not_found", "工作单不存在", 404)
        conn = wf.connect_ro()
        try:
            last = rd.last_export(conn, wo) if conn is not None else None
            versions = rd.list_copy_versions(conn, wo) if conn is not None else []
            publish = rd.publish_info(conn, wo) if conn is not None else None
        finally:
            if conn is not None:
                conn.close()
        ready = rd.readiness(record)
        body = vwiz.render_copy(record, ready, rd.export_validity(record, last), csrf_token(), versions,
                                publish=publish)
        return render("copy", "写文案", lambda _d: body)

    @app.post("/worksheet/<workorder_id>/copy/save")
    def wizard_copy_save(workorder_id: str):
        require_local_write()
        payload = {k: v for k, v in request.form.items() if k not in ("csrf", "revision")}
        new_name = str(payload.pop("name", "") or "").strip()
        revision = request.form.get("revision")
        conn = wf.connect()
        try:
            try:
                record = wf.get(conn, workorder_id)
                if record is None:
                    raise wf.Reject("not_found", "工作单不存在", 404)
                if new_name and new_name != record["name"]:
                    wf.update(conn, workorder_id, revision=revision, payload={"name": new_name})
                    revision = str(wf.get(conn, workorder_id)["revision"])
                if payload:
                    rd.save_evidence(conn, workorder_id, revision=revision, payload=payload)
            except wf.Reject as exc:
                if exc.status != 409:
                    raise
                record = wf.get(conn, workorder_id)
                body = vwiz.render_copy(record, rd.readiness(record), {"valid": False, "reason": exc.message},
                                        csrf_token(), rd.list_copy_versions(conn, workorder_id))
                return Response(layout("copy", get_data(), body, "保存失败"), status=409,
                                mimetype="text/html; charset=utf-8")
        finally:
            conn.close()
        return redirect(f"/copy?wo={workorder_id}", code=303)

    @app.get("/worksheet")
    def worksheet_list():
        conn = wf.connect_ro()
        try:
            records = wf.list_all(conn) if conn is not None else []
        finally:
            if conn is not None:
                conn.close()
        body = vws.render_list(records, worksheet_gaps, csrf_token())
        return render("worksheet", "商品工作单", lambda _d: body)

    @app.get("/worksheet/<workorder_id>")
    def worksheet_detail(workorder_id: str):
        conn = wf.connect_ro()
        try:
            record = wf.get(conn, workorder_id) if conn is not None else None
        finally:
            if conn is not None:
                conn.close()
        if record is None:
            raise wf.Reject("not_found", "工作单不存在", 404)
        conn = wf.connect_ro()
        try:
            last = rd.last_export(conn, workorder_id) if conn is not None else None
            versions = rd.list_copy_versions(conn, workorder_id) if conn is not None else []
            candidates = sup.list_candidates(conn, workorder_id) if conn is not None else []
            publish = rd.publish_info(conn, workorder_id) if conn is not None else None
        finally:
            if conn is not None:
                conn.close()
        ready = rd.readiness(record)
        export_info = rd.export_validity(record, last)
        changed = rd.publish_changed(publish, last)
        body = (vws.render_detail(record, worksheet_gaps(record), wf.stages_state(record), csrf_token())
                + vws.render_supply(record, candidates, csrf_token())
                + vws.render_sample(record, csrf_token())
                + vws.render_readiness(record, ready, export_info, csrf_token())
                + vws.render_copy_history(record, versions, csrf_token())
                + vws.render_publish(record, publish, changed, csrf_token()))
        return render("worksheet", record["name"], lambda _d: body)

    @app.get("/worksheet/<workorder_id>/edit")
    def worksheet_edit(workorder_id: str):
        conn = wf.connect_ro()
        try:
            record = wf.get(conn, workorder_id) if conn is not None else None
        finally:
            if conn is not None:
                conn.close()
        if record is None:
            raise wf.Reject("not_found", "工作单不存在", 404)
        body = vws.render_edit(record, csrf_token())
        return render("worksheet", "编辑规格", lambda _d: body)

    @app.get("/worksheet/new")
    def worksheet_new():
        body = vws.render_new(csrf_token())
        return render("worksheet", "新建自制商品", lambda _d: body)

    @app.post("/worksheet/new")
    def worksheet_create():
        require_local_write()
        self_made = str(request.form.get("self_made") or "") == "1"
        payload = {k: v for k, v in request.form.items()
                   if k not in ("csrf", "revision", "submit_key", "group", "item_id", "self_made")}
        submit_key = str(request.form.get("submit_key") or "").strip()
        if not submit_key:
            raise wf.Reject("submit_key_invalid", "缺少提交键（请从页面表单提交）")
        conn = wf.connect()
        try:
            record, created = wf.create(conn, group=str(request.form.get("group") or ""),
                                        item_id=str(request.form.get("item_id") or ""),
                                        payload=payload, submit_key=submit_key, self_made=self_made)
        finally:
            conn.close()
        return redirect(f"/worksheet/{record['workorder_id']}" + ("" if created else "?deduplicated=1"), code=303)

    @app.post("/worksheet/<workorder_id>/edit")
    def worksheet_update(workorder_id: str):
        require_local_write()
        payload = {k: v for k, v in request.form.items() if k not in ("csrf", "revision")}
        conn = wf.connect()
        try:
            try:
                wf.update(conn, workorder_id, revision=request.form.get("revision"),
                          payload=payload)
            except wf.Reject as exc:
                if exc.status != 409:
                    raise
                record = wf.get(conn, workorder_id)
                body = vws.render_edit(record, csrf_token(), error=exc.message) if record else exc.message
                data = get_data()
                return Response(layout("worksheet", data, body, "编辑失败"), status=409,
                                mimetype="text/html; charset=utf-8")
        finally:
            conn.close()
        return redirect(f"/worksheet/{workorder_id}", code=303)

    @app.post("/worksheet/<workorder_id>/evidence")
    def worksheet_evidence(workorder_id: str):
        require_local_write()
        payload = {k: v for k, v in request.form.items() if k not in ("csrf", "revision")}
        conn = wf.connect()
        try:
            try:
                rd.save_evidence(conn, workorder_id, revision=request.form.get("revision"), payload=payload)
            except wf.Reject as exc:
                if exc.status != 409:
                    raise
                record = wf.get(conn, workorder_id)
                body = vws.render_edit(record, csrf_token(), error=exc.message) if record else exc.message
                data = get_data()
                return Response(layout("worksheet", data, body, "保存失败"), status=409,
                                mimetype="text/html; charset=utf-8")
        finally:
            conn.close()
        return redirect(f"/worksheet/{workorder_id}", code=303)

    @app.post("/worksheet/<workorder_id>/copy/rollback")
    def worksheet_copy_rollback(workorder_id: str):
        require_local_write()
        conn = wf.connect()
        try:
            rd.rollback_copy(conn, workorder_id, version_no=request.form.get("version_no"),
                             revision=request.form.get("revision"))
        finally:
            conn.close()
        return redirect(f"/worksheet/{workorder_id}", code=303)

    @app.post("/worksheet/<workorder_id>/publish")
    def worksheet_publish(workorder_id: str):
        require_local_write()
        payload = {k: v for k, v in request.form.items() if k not in ("csrf", "revision")}
        conn = wf.connect()
        try:
            rd.save_publish(conn, workorder_id, payload)
        finally:
            conn.close()
        return redirect(f"/worksheet/{workorder_id}", code=303)

    @app.post("/worksheet/<workorder_id>/supply/candidates")
    def supply_candidate_add(workorder_id: str):
        require_local_write()
        payload = {k: v for k, v in request.form.items() if k not in ("csrf", "revision")}
        conn = wf.connect()
        try:
            sup.add(conn, workorder_id, payload)
        finally:
            conn.close()
        return redirect(f"/worksheet/{workorder_id}#h-supply", code=303)

    @app.post("/worksheet/<workorder_id>/supply/candidates/<candidate_id>")
    def supply_candidate_update(workorder_id: str, candidate_id: str):
        require_local_write()
        payload = {k: v for k, v in request.form.items() if k not in ("csrf", "revision")}
        conn = wf.connect()
        try:
            sup.update_candidate(conn, workorder_id, candidate_id, payload)
        finally:
            conn.close()
        return redirect(f"/worksheet/{workorder_id}#h-supply", code=303)

    @app.post("/worksheet/<workorder_id>/supply/candidates/<candidate_id>/deactivate")
    def supply_candidate_deactivate(workorder_id: str, candidate_id: str):
        require_local_write()
        conn = wf.connect()
        try:
            sup.deactivate(conn, workorder_id, candidate_id, confirm=request.form.get("confirm"))
        finally:
            conn.close()
        return redirect(f"/worksheet/{workorder_id}#h-supply", code=303)

    @app.post("/worksheet/<workorder_id>/supply/import")
    def supply_import(workorder_id: str):
        require_local_write()
        conn = wf.connect()
        try:
            result = sup.import_json(conn, workorder_id, str(request.form.get("payload") or ""))
        finally:
            conn.close()
        data = get_data()
        body = (f'<section class="panel"><h2>导入结果</h2><p>导入 {result["imported"]} / 共 {result["total"]} 条；'
                f'跳过/忽略 {len(result["skipped"])} 项。</p>'
                f'<pre class="mono dim">{esc(json.dumps(result["skipped"], ensure_ascii=False, indent=1))}</pre>'
                f'<p><a href="/worksheet/{esc(workorder_id)}">← 返回工作单</a></p></section>')
        return Response(layout("worksheet", data, body, "导入结果"), mimetype="text/html; charset=utf-8")

    @app.post("/worksheet/<workorder_id>/supply/select")
    def supply_select(workorder_id: str):
        require_local_write()
        conn = wf.connect()
        try:
            sup.select_candidate(conn, workorder_id, str(request.form.get("candidate_id") or ""),
                                 revision=request.form.get("revision"))
        finally:
            conn.close()
        return redirect(f"/worksheet/{workorder_id}#h-supply", code=303)

    @app.post("/worksheet/<workorder_id>/sample/check")
    def sample_check(workorder_id: str):
        require_local_write()
        conn = wf.connect()
        try:
            outcome = sc.check_and_apply(conn, workorder_id, path_text=str(request.form.get("path") or ""),
                                         revision=request.form.get("revision"))
        finally:
            conn.close()
        if outcome["applied"]:
            return redirect(f"/worksheet/{workorder_id}#h-sample", code=303)
        result = outcome["result"]
        data = get_data()
        checks = "".join(f'<li>{esc(c["item"])}：{"通过" if c["ok"] else "未通过"}（{esc(c["detail"])}）</li>'
                         for c in result.get("checks") or [])
        body = (f'<section class="panel"><h2>样品自检未通过</h2>'
                f'<p class="notice notice-warn" role="alert">{esc(result.get("error") or "检查项未通过")}</p>'
                f'<ul class="gaps">{checks}</ul>'
                f'<p class="hint dim">状态保持原样（sample_status 未改）。修正后重试。</p>'
                f'<p><a href="/worksheet/{esc(workorder_id)}">← 返回工作单</a></p></section>')
        return Response(layout("worksheet", data, body, "样品自检未通过"), status=400,
                        mimetype="text/html; charset=utf-8")

    @app.get("/worksheet/<workorder_id>/export")
    def worksheet_export(workorder_id: str):
        """GET 只生成内容，**不写库**（D1 修复）：导出记录由 POST /export/record 产生。"""
        fmt = (request.args.get("format") or "md").lower()
        if fmt not in ("md", "json"):
            raise wf.Reject("format_invalid", "format 只能是 md 或 json", 400)
        conn = wf.connect_ro()
        try:
            record = wf.get(conn, workorder_id) if conn is not None else None
            if record is None:
                raise wf.Reject("not_found", "工作单不存在", 404)
            ready = rd.readiness(record)
            if not ready["overall_ready"]:
                blockers = "".join(f"<li>{esc(b)}</li>" for b in ready["blockers"])
                body = (f'<section class="panel"><h2>导出被阻止（未就绪）</h2>'
                        f'<p class="hint">以下检查项未通过，导出未生成：</p><ul class="gaps">{blockers}</ul>'
                        f'<p><a href="/worksheet/{esc(workorder_id)}">← 返回工作单</a></p></section>')
                data = get_data()
                return Response(layout("worksheet", data, body, "导出被阻止"), status=409,
                                mimetype="text/html; charset=utf-8")
            payload = rd.build_export(record)
            stamp = payload["version_stamp"]
        finally:
            if conn is not None:
                conn.close()
        return _export_response(payload, fmt, stamp, recorded=False)

    @app.post("/worksheet/<workorder_id>/export/record")
    def worksheet_export_record(workorder_id: str):
        """显式记录本次导出（CSRF+同源+就绪检查）；写入 1 行 workorder_export。"""
        require_local_write()
        fmt = (request.form.get("format") or "md").lower()
        if fmt not in ("md", "json"):
            raise wf.Reject("format_invalid", "format 只能是 md 或 json", 400)
        conn = wf.connect()
        try:
            record = wf.get(conn, workorder_id)
            if record is None:
                raise wf.Reject("not_found", "工作单不存在", 404)
            ready = rd.readiness(record)
            if not ready["overall_ready"]:
                raise wf.Reject("export_not_ready", "未就绪，不能记录导出：" + "；".join(ready["blockers"]), 409)
            payload = rd.build_export(record)
            info = rd.record_export(conn, record, payload, fmt)
        finally:
            conn.close()
        return _export_response(payload, fmt, info["stamp"], recorded=True,
                                deduplicated=bool(info.get("deduplicated")))

    @app.get("/sources")
    def sources():
        return render("sources", "货源与价格", lambda d: page_sources(d, request.args))

    @app.get("/collect")
    def collect():
        return render("collect", "采集来源", lambda d: page_collect(d, request.args))

    @app.get("/daily")
    def daily():
        return render("daily", "每日快照", page_daily)

    # ---------- V9-4 线索与轮次（只读 + 受控写） ----------
    def _leads_flash(msg: str = "", err: str = ""):
        return redirect(f"/leads?msg={urllib.parse.quote(msg)}&err={urllib.parse.quote(err)}", code=303)

    @app.get("/leads")
    def leads_page():
        data = get_data()
        lead_data = vleads.load_lead_data()
        body = vleads.render_leads(lead_data, csrf=csrf_token(),
                                   msg=request.args.get("msg", ""), err=request.args.get("err", ""))
        return render("pick", "需求线索", lambda _d: body)

    @app.post("/leads/round")
    def leads_round_start():
        require_local_write()
        aid_raw = str(request.form.get("aid") or "").strip()
        bvid = str(request.form.get("bvid") or "").strip()
        aid = int(aid_raw) if aid_raw.isdigit() else None
        if not aid and not bvid:
            return _leads_flash(err="bvid 或 aid 二选一必填")
        try:
            budget = int(request.form.get("budget") or 3)
            interval = float(request.form.get("interval") or 3)
        except ValueError:
            return _leads_flash(err="budget/interval 必须是数字")
        budget = max(1, min(5, budget))
        interval = max(3.0, interval)
        key = str(request.form.get("idempotency_key") or "").strip() or             f"leads-{int(__import__('time').time())}-{os.urandom(3).hex()}"
        path = vleads.selection_db()
        conn = sel_db.init_db(path)
        try:
            target_budget = {"max_requests": budget, "interval": interval,
                             "aid": aid, "bvid": bvid or None}
            started = sel_rounds.start(conn, kind="bilibili", platform="bilibili",
                                       budget=target_budget, idempotency_key=key)
            if started["status"] == "draft":
                sel_rounds.transition(conn, started["id"], "running")
            out = sel_bili.collect_round(db_path=path, round_id=started["id"],
                                         raw_dir=ROOT / "docs" / "validation" / "v9" / "impl" / "raw" / "leads",
                                         aid=aid, bvid=bvid or None, budget=budget, interval=interval)
            cat = sel_categories.run_categorize(conn)
            cards = sel_categories.make_cards(conn)
            return _leads_flash(msg=f'round {started["id"]} {out.get("status")} '
                                    f'requests={out.get("requests_used", "?")} '
                                    f'new={cat.get("new", 0)} update={cat.get("update", 0)} '
                                    f'review={cat.get("review", 0)} categories={cat.get("categories", 0)} '
                                    f'cards={cards.get("cards", 0)}')
        except Exception as exc:  # noqa: BLE001 - UI returns 303 with readable error
            return _leads_flash(err=f"{type(exc).__name__}: {exc}")
        finally:
            conn.close()

    @app.post("/leads/round/<int:round_id>/<action>")
    def leads_round_action(round_id: int, action: str):
        require_local_write()
        path = vleads.selection_db()
        conn = sel_db.init_db(path)
        try:
            if action == "pause":
                sel_rounds.pause(conn, round_id)
            elif action == "resume":
                sel_rounds.resume(conn, round_id)
                st = sel_rounds.status(conn, round_id)
                try:
                    bj = json.loads(st.get("budget_json") or "{}")
                except Exception:
                    bj = {}
                out = sel_bili.collect_round(
                    db_path=path, round_id=round_id,
                    raw_dir=ROOT / "docs" / "validation" / "v9" / "impl" / "raw" / "leads",
                    aid=bj.get("aid"), bvid=bj.get("bvid"),
                    budget=int(bj.get("max_requests", 3)),
                    interval=float(bj.get("interval", 3)))
                msg = (f'round {round_id} resume {out.get("status")} '
                       f'requests={out.get("requests_used", "?")}')
                return _leads_flash(msg=msg)
            elif action == "cancel":
                sel_rounds.cancel(conn, round_id)
            else:
                return _leads_flash(err="未知操作")
            return _leads_flash(msg=f"round {round_id} {action} 成功")
        except Exception as exc:  # noqa: BLE001
            return _leads_flash(err=f"{type(exc).__name__}: {exc}")
        finally:
            conn.close()

    @app.post("/leads/manual")
    def leads_manual_add():
        require_local_write()
        platform = str(request.form.get("platform") or "").strip().lower()
        url = str(request.form.get("url") or "").strip()
        text = str(request.form.get("text") or "").strip()
        title = str(request.form.get("title") or "").strip()
        if not url and not text:
            return _leads_flash(err="url 与 text 至少一项必填")
        path = vleads.selection_db()
        conn = sel_db.init_db(path)
        try:
            out = sel_manual.add(conn, platform, url=url or None, text=text or None,
                                 title=title or None)
            tri = conn.execute("SELECT label FROM signal_triage WHERE signal_id=?",
                               (out["signal_id"],)).fetchone()
            conn2 = sel_db.init_db(path)
            try:
                cat = sel_categories.run_categorize(conn2)
                cards = sel_categories.make_cards(conn2)
            finally:
                conn2.close()
            return _leads_flash(msg=f"manual {out['outcome']} signal={out['signal_id']} "
                                    f"native_id={out['native_id']} ({out['native_id_source']}) "
                                    f"triage={tri['label'] if tri else '?'} "
                                    f"categories={cat.get('categories', 0)} cards={cards.get('cards', 0)}")
        except Exception as exc:  # noqa: BLE001
            return _leads_flash(err=f"{type(exc).__name__}: {exc}")
        finally:
            conn.close()

    @app.post("/leads/triage/<int:signal_id>")
    def leads_triage_override(signal_id: int):
        require_local_write()
        label = str(request.form.get("label") or "").strip().lower()
        if label not in ("demand", "promo", "noise"):
            return _leads_flash(err="label 必须是 demand/promo/noise")
        path = vleads.selection_db()
        conn = sel_db.init_db(path)
        try:
            out = sel_triage.set_override(conn, signal_id, label)
            return _leads_flash(msg=f"triage signal {signal_id} -> {out['label']} (override)")
        except Exception as exc:  # noqa: BLE001
            return _leads_flash(err=f"{type(exc).__name__}: {exc}")
        finally:
            conn.close()

    @app.get("/healthz")
    def healthz():
        data = get_data()
        return {"app_id": "workbench-opportunity/1", "status": "ok", "root": data.get("root"),
                "generated_at": data.get("generated_at"), "counts": data.get("counts"),
                "workflow": {"db": str(wf.db_path()), "workorders": _workorder_count()}}

    return app


def _export_response(payload: dict, fmt: str, stamp: dict, *, recorded: bool, deduplicated: bool = False) -> Response:
    """统一生成导出响应；`recorded` 仅表示是否由 POST 记录（GET 一律 false）。"""
    workorder_id = stamp["workorder_id"]
    if fmt == "json":
        text = json.dumps(payload, ensure_ascii=False, indent=1)
        mime = "application/json; charset=utf-8"
        filename = f'{workorder_id.replace(":", "-")}-r{stamp["revision"]}.json'
    else:
        text = rd.to_markdown(payload)
        mime = "text/markdown; charset=utf-8"
        filename = f'{workorder_id.replace(":", "-")}-r{stamp["revision"]}.md'
    resp = Response(text, mimetype=mime)
    resp.headers["Content-Disposition"] = f'attachment; filename="{filename}"'
    resp.headers["X-WB-Revision"] = str(stamp["revision"])
    resp.headers["X-WB-Stamp"] = stamp["stamp_hash"][:16]
    resp.headers["X-WB-Copy-Version"] = stamp["copy_version"] or ""
    resp.headers["X-WB-Supply"] = f'{stamp["supply_id"] or ""}@{stamp["supply_version"] or ""}'
    resp.headers["X-WB-Recorded"] = "true" if recorded else "false"
    resp.headers["X-WB-Deduplicated"] = "true" if deduplicated else "false"
    return resp


def _workorder_count():
    """只读计数：库不存在时返回 0，不做任何写入。"""
    import sqlite3
    path = wf.db_path()
    if not path.exists():
        return 0
    try:
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        try:
            return int(conn.execute("SELECT COUNT(*) FROM workorder").fetchone()[0])
        finally:
            conn.close()
    except sqlite3.Error:
        return None


if __name__ == "__main__":  # pragma: no cover
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 5015
    create_app().run(host="127.0.0.1", port=port, debug=False)
