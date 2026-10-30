"""B20：三步向导视图（选品 → 找货源 → 写介绍），与旧页面共用同一套 CSS 与数据。"""

from __future__ import annotations

import html
from urllib.parse import urlencode

import readiness as rd
import workflow as wf

STEPS = (("pick", "/pick", "选品"), ("source", "/source", "找货源"), ("copy", "/copy", "写文案"))


def esc(value) -> str:
    return html.escape("" if value is None else str(value), quote=True)


def wizard_bar(current: str, wo: str = "", *, pick_args: str = "") -> str:
    """三步向导条：当前步高亮；已完成步可点（需要 wo 时带上参数）。"""
    order = [s[0] for s in STEPS]
    idx = order.index(current) if current in order else 0
    parts = []
    for key, href, label in STEPS:
        pos = order.index(key)
        if key == current:
            parts.append(f'<span class="wiz-step wiz-current" aria-current="step">{esc(label)}</span>')
        elif pos < idx and wo:
            parts.append(f'<a class="wiz-step" href="{href}?wo={esc(wo)}">{esc(label)}</a>')
        elif key == "pick":
            parts.append(f'<a class="wiz-step" href="{href}{pick_args}">{esc(label)}</a>')
        else:
            parts.append(f'<span class="wiz-step wiz-todo">{esc(label)}</span>')
    return f'<nav class="wizard" aria-label="三步向导">{"<span class=\"wiz-sep\">→</span>".join(parts)}</nav>'


def render_continue(workorders: list[dict]) -> str:
    """“继续已有工作单”：只读列表 + 跳转，不自动选中、不自动建单。"""
    rows = ""
    for item in workorders:
        wo = item.get("workorder_id") or ""
        rows += (
            "<tr>"
            f'<td class="cell-title"><a href="/source?wo={esc(wo)}">{esc(item.get("name") or "（未命名）")}</a>'
            f'<p class="dim small mono">{esc(wo)}</p></td>'
            f'<td>{esc(item.get("status_label") or item.get("status") or "—")}</td>'
            f'<td class="num">{esc(item.get("ready_ok"))}/{esc(item.get("ready_total"))}</td>'
            f'<td class="mono dim">{esc(item.get("updated_at") or "—")}</td>'
            f'<td><a class="btn btn-ghost" href="/source?wo={esc(wo)}">继续找货源</a> '
            f'<a class="btn btn-ghost" href="/copy?wo={esc(wo)}">继续写文案</a></td>'
            "</tr>")
    if rows:
        body = (f'<div class="table-wrap"><table><caption class="sr-only">已有工作单</caption>'
                '<thead><tr><th scope="col">名称 / 单号</th><th scope="col">状态</th>'
                '<th scope="col">就绪进度</th><th scope="col">更新时间</th><th scope="col">继续</th></tr></thead>'
                f'<tbody>{rows}</tbody></table></div>')
    else:
        body = ('<div class="empty"><p class="empty-title">还没有工作单，先在上面选一个商品</p>'
                '<p class="dim">选好后这里会出现“继续找货源 / 继续写文案”的入口。</p></div>')
    return f"""
<section class="panel" aria-labelledby="h-continue">
  <div class="panel-head"><h2 id="h-continue">继续已有工作单（{len(workorders)}）</h2>
  <p class="hint">最近更新的前 10 条；点名称或按钮继续，不会自动选中或自动建单。</p></div>
  {body}
</section>"""


def render_need_wo(current: str, workorders: list[dict]) -> str:
    """没有当前工作单时的引导页（200）：两条路径 + 最近 10 条快捷入口。不自动选中/建单。"""
    rows = ""
    for item in workorders:
        wo = item.get("workorder_id") or ""
        rows += (
            "<tr>"
            f'<td class="cell-title">{esc(item.get("name") or "（未命名）")}'
            f'<p class="dim small mono">{esc(wo)}</p></td>'
            f'<td class="num">{esc(item.get("ready_ok"))}/{esc(item.get("ready_total"))}</td>'
            f'<td class="mono dim">{esc(item.get("updated_at") or "—")}</td>'
            f'<td><a class="btn btn-ghost" href="/source?wo={esc(wo)}">继续找货源</a> '
            f'<a class="btn btn-ghost" href="/copy?wo={esc(wo)}">继续写文案</a></td>'
            "</tr>")
    table = (
        f'<div class="table-wrap"><table><caption class="sr-only">最近的工作单</caption>'
        '<thead><tr><th scope="col">名称 / 单号</th><th scope="col">就绪</th>'
        '<th scope="col">更新时间</th><th scope="col">继续</th></tr></thead>'
        f'<tbody>{rows}</tbody></table></div>') if rows else (
        '<p class="hint dim">还没有任何工作单——先从第 1 步选一个商品，这里就会出现快捷入口。</p>')
    title = "找货源" if current == "source" else "写文案"
    return f"""
{wizard_bar(current)}
<section class="panel" aria-labelledby="h-need-wo">
  <div class="panel-head"><h2 id="h-need-wo">{esc(title)}</h2>
  <p class="notice notice-warn" role="status">还没有选中商品。请先选品，或从下面的最近工作单继续。</p></div>
  <p class="sortbar"><a class="btn btn-primary" href="/pick">① 去选品（选一个商品）</a>
  <a class="btn btn-ghost" href="/worksheet/new">新建自制商品</a></p>
  <h3>从最近工作单继续</h3>
  {table}
</section>"""


def render_pick(groups: list[dict], args, csrf: str, *, meta: dict | None = None, error: str = "",
                workorders: list[dict] | None = None) -> str:
    query = {k: v for k, v in (args or {}).items() if k in ("q", "platform", "view", "quality") and v}
    pick_args = ("?" + urlencode(query)) if query else ""
    meta = meta or {}
    rows = []
    for g in groups:
        name = g.get("category") or g.get("name") or "（未命名）"
        members = g.get("members") or []
        first = members[0] if members else ""
        pending = bool(g.get("pending"))
        if pending or not g.get("selectable", True):
            action = '<span class="dim">需先人工确认品类（不会建单）</span>'
        else:
            action = (
                f'<form method="post" action="/worksheet/new" class="inline-form">'
                f'<input type="hidden" name="csrf" value="{esc(csrf)}">'
                f'<input type="hidden" name="group" value="{esc(name)}">'
                f'<input type="hidden" name="item_id" value="{esc(first)}">'
                f'<input type="hidden" name="submit_key" value="pick-{esc(name)}-{esc(first)}">'
                f'<input type="hidden" name="name" value="{esc(name)}">'
                f'<input type="hidden" name="use_case" value="{esc(name)}">'
                f'<input type="hidden" name="deliverable" value="{esc(name)} 交付物">'
                f'<input type="hidden" name="target_platform" value="xianyu">'
                f'<button type="submit" class="btn btn-primary">选这个</button></form>')
        sell = g.get("sellability_avg")
        sell_n = g.get("sellability_n") or 0
        if isinstance(sell, (int, float)):
            if sell_n >= 1:
                sell_html = f'{sell:.2f}（n={sell_n}）'
                sell_title = f'组内 sellability_norm 均值，n={sell_n} 条样本（与条数同量级）'
            else:                                  # 防御：有值但 n=0 时不显示 n
                sell_html = f'{sell:.2f}（组均值）'
                sell_title = "组级 sellability_mean（未记录样本数）"
        else:
            sell_html = "未评估"
            sell_title = "该组没有可售性字段，未做评估"
        comp = g.get("competition_avg")
        comp_n = g.get("competition_n") or 0
        if isinstance(comp, (int, float)):
            comp_html = f'{comp:.2f}（n={comp_n}）'
            comp_title = f'组内 competition_norm 均值，n={comp_n} 条；1=竞争者最少'
        else:
            comp_html = "未评估"
            comp_title = "该组没有 competition_norm 字段，未做评估"
        links = "".join(f'<a href="{esc(u)}" target="_blank" rel="noopener noreferrer nofollow">链接{i + 1}</a> '
                        for i, u in enumerate((g.get("representative_urls") or [])[:2])) or "—"
        rows.append(
            "<tr>"
            f'<td class="cell-title">{esc(name)}{" <span class=\"chip chip-warn\">待人工确认</span>" if pending else ""}'
            f'<p class="dim small">{esc(g.get("note") or "")}</p></td>'
            f'<td class="num">{esc(g.get("count") or len(members))}</td>'
            f'<td class="num">{float(g.get("max_total_score") or 0):.2f}</td>'
            f'<td class="num" title="{esc(sell_title)}">{esc(sell_html)}</td>'
            f'<td class="num" title="{esc(comp_title)}">{esc(comp_html)}</td>'
            f'<td class="dim">{links}</td>'
            f"<td>{action}</td>"
            "</tr>")
    body = "".join(rows) or ('<tr><td colspan="7"><div class="empty"><p class="empty-title">没有可选的商品类型</p>'
                             '<p class="dim">换个关键词或平台筛选试试；若你要卖的是自己做的，请用'
                             ' <a href="/worksheet/new">新建自制商品</a>。</p></div></td></tr>')
    err = f'<div class="notice notice-warn" role="alert">{esc(error)}</div>' if error else ""
    caption = (f'数据快照：{esc(meta.get("snapshot") or "未知")} · 样本量：商品型 {meta.get("groups", len(groups))} 组 / '
               f'共 {meta.get("members", 0)} 条 · 可售性：优先组级 sellability_mean，缺则组内 sellability_norm 均值'
               f'（两位小数，括号内为样本数） · 竞争稀疏：组内 competition_norm 均值（0–1，1=竞争者最少；'
               f'不是平台竞品数量）')
    return f"""
{wizard_bar("pick", pick_args=pick_args)}
{err}
{render_continue(workorders or [])}
<section class="panel" aria-labelledby="h-pick">
  <div class="panel-head"><h2 id="h-pick">① 选品：有需求的商品类型</h2>
  <p class="hint">只列<strong>商品型且非待人工</strong>的类别。每行显示条数、需求分位（最高评分）、可售性均值、竞争稀疏。
  点「选这个」会用该类型代表条目建立工作单，然后进入第②步找货源。</p></div>
  <form method="get" action="/pick" class="filters">
    <label class="field"><span>关键词</span><input type="search" name="q" value="{esc((args or {}).get('q') or '')}" placeholder="如 笔记 / 简历 / 作品集"></label>
    <label class="field"><span>平台</span><select name="platform">
      <option value="">全部</option>
      {''.join(f'<option value="{esc(p)}"{" selected" if (args or {}).get("platform") == p else ""}>{esc(p)}</option>'
               for p in ("x", "xiaohongshu", "bilibili"))}
    </select></label>
    <div class="filter-actions"><button type="submit" class="btn">筛选</button>
      <a class="btn btn-ghost" href="/pick">重置</a></div>
  </form>
  <p class="hint dim" aria-label="数据口径说明">{caption}</p>
  <div class="table-wrap"><table><caption class="sr-only">可选的商品类型</caption>
    <thead><tr><th scope="col">商品类型</th><th scope="col">条数</th><th scope="col">需求分位</th>
    <th scope="col" title="组内 sellability_norm 均值；无值显示未评估">可售性</th>
    <th scope="col" title="1=竞争者最少（组内 competition_norm 均值，不是平台竞品数量）">竞争稀疏</th>
    <th scope="col">代表链接</th><th scope="col">操作</th></tr></thead>
    <tbody>{body}</tbody></table></div>
  <p class="hint dim">内容型（教程 / 资源推荐清单 / 教学变现）不在本页，请到 <a href="/content">教程与内容</a> 页查看；
  自制商品走 <a href="/worksheet/new">新建自制商品</a>。</p>
</section>"""


def render_source(record: dict, candidates: list[dict], ready: dict, csrf: str, *,
                  last_export: dict | None = None, error: str = "") -> str:
    wo = record["workorder_id"]
    selected = record.get("selected_supply_id")
    rows = ""
    for c in candidates:
        is_sel = selected == c["id"]
        rows += (
            "<tr>"
            f'<td class="mono">{esc(c["id"])}</td>'
            f'<td>{esc(c["provider"])}<p class="dim small">{esc(c.get("source_url") or "—")}</p></td>'
            f'<td>{esc(c["kind"])}</td>'
            f'<td>{esc(c["commercial"])}/{esc(c["redistribute"])}/{esc(c["resale"])}</td>'
            f'<td>{esc(c.get("license_note") or "—")}</td>'
            f'<td>{"<span class=\"chip chip-ok\">已采用</span>" if is_sel else ""}</td>'
            '<td>'
            f'<form method="post" action="/worksheet/{esc(wo)}/supply/select" class="inline-form">'
            f'<input type="hidden" name="csrf" value="{esc(csrf)}">'
            f'<input type="hidden" name="revision" value="{record["revision"]}">'
            f'<input type="hidden" name="candidate_id" value="{esc(c["id"])}">'
            '<button type="submit" class="btn btn-ghost">采用</button></form>'
            f'<form method="post" action="/worksheet/{esc(wo)}/supply/candidates/{esc(c["id"])}/deactivate" class="inline-form">'
            f'<input type="hidden" name="csrf" value="{esc(csrf)}"><input type="hidden" name="confirm" value="1">'
            '<button type="submit" class="btn btn-ghost" onclick="return confirm(\'确认停用该候选？\')">停用</button>'
            '</form></td></tr>')
    body = rows or ('<tr><td colspan="7"><div class="empty"><p class="dim">还没有候选：新增一条或粘贴 JSON 导入。</p>'
                    '</div></td></tr>')
    confirm_disabled = "" if selected else " disabled aria-disabled=\"true\""
    confirm_note = ("" if selected else
                    '<p class="hint dim">未采用任何货源前不能确定上架商品（服务端同样校验）。</p>')
    err = f'<div class="notice notice-warn" role="alert">{esc(error)}</div>' if error else ""
    return f"""
{wizard_bar("source", wo)}
{err}
<section class="panel" aria-labelledby="h-src">
  <div class="panel-head"><h2 id="h-src">② 找货源：确定最终上架商品</h2>
  <p class="hint">当前商品：<strong>{esc(record["name"])}</strong> · 用途 {esc(record["use_case"])}
  · 交付物 {esc(record["deliverable"])} · 平台 {esc(record["target_platform"])} · revision {record["revision"]}</p></div>
  <p class="sortbar">样品状态：<span class="chip {'chip-ok' if record.get('sample_status') == 'verified' else 'chip-warn'}">
  {esc(record.get("sample_status") or "未核验")}</span> <span class="dim">{esc(record.get("sample_ref") or "—")}</span></p>
  <div class="table-wrap"><table><caption class="sr-only">货源候选</caption>
    <thead><tr><th scope="col">候选</th><th scope="col">提供方/链接</th><th scope="col">类型</th>
    <th scope="col">许可</th><th scope="col">许可说明</th><th scope="col">状态</th><th scope="col">操作</th></tr></thead>
    <tbody>{body}</tbody></table></div>
  <h3>新增候选</h3>
  <form method="post" action="/worksheet/{esc(wo)}/supply/candidates" class="filters form-grid">
    <input type="hidden" name="csrf" value="{esc(csrf)}">
    <label class="field"><span>提供方</span><input type="text" name="provider" required placeholder="自制 / 某素材站"></label>
    <label class="field"><span>来源链接</span><input type="text" name="source_url" placeholder="https:// 或 self:…"></label>
    <label class="field"><span>类型</span><select name="kind"><option>同款</option><option selected>替代</option><option>不匹配</option></select></label>
    <label class="field"><span>可商用</span><select name="commercial"><option value="unknown">不明</option><option value="yes">允许</option><option value="no">禁止</option></select></label>
    <label class="field"><span>可再分发</span><select name="redistribute"><option value="unknown">不明</option><option value="yes">允许</option><option value="no">禁止</option></select></label>
    <label class="field"><span>可转售</span><select name="resale"><option value="unknown">不明</option><option value="yes">允许</option><option value="no">禁止</option></select></label>
    <label class="field span2"><span>许可说明</span><input type="text" name="license_note" placeholder="条款摘要或链接"></label>
    <div class="filter-actions"><button type="submit" class="btn">新增候选</button></div>
  </form>
  <h3>样品自检（本地文件）</h3>
  <form method="post" action="/worksheet/{esc(wo)}/sample/check" class="filters form-grid">
    <input type="hidden" name="csrf" value="{esc(csrf)}">
    <input type="hidden" name="revision" value="{record["revision"]}">
    <label class="field span2"><span>文件路径（docs/ 或 tools/ 下）</span>
      <input type="text" name="path" required placeholder="docs/validation/product-workflow/b7/sample-study-planner-v1.xlsx"></label>
    <div class="filter-actions"><button type="submit" class="btn">执行自检</button></div>
  </form>
  <form method="post" action="/worksheet/{esc(wo)}/source/confirm" class="filters">
    <input type="hidden" name="csrf" value="{esc(csrf)}">
    <input type="hidden" name="revision" value="{record["revision"]}">
    <div class="filter-actions"><button type="submit" class="btn btn-primary"{confirm_disabled}>确定上架商品 → 下一步</button>
    <a class="btn btn-ghost" href="/pick">← 返回选品</a></div>
  </form>
  {confirm_note}
</section>"""


def render_copy(record: dict, ready: dict, export_info: dict, csrf: str, versions: list[dict],
                publish: dict | None = None) -> str:
    wo = record["workorder_id"]
    checks = "".join(
        f'<li>{"✅" if c["ok"] else "⛔"} {esc(c["label"])}'
        f'{"" if c["ok"] else "：" + esc(c["blocker"])}</li>' for c in ready["checks"])
    if ready["overall_ready"]:
        export_html = (f'<a class="btn btn-primary" href="/worksheet/{esc(wo)}/export?format=md">导出 Markdown</a> '
                       f'<a class="btn btn-ghost" href="/worksheet/{esc(wo)}/export?format=json">导出 JSON</a> '
                       f'<form method="post" action="/worksheet/{esc(wo)}/export/record" class="inline-form">'
                       f'<input type="hidden" name="csrf" value="{esc(csrf)}"><input type="hidden" name="format" value="md">'
                       '<button type="submit" class="btn btn-ghost">记录本次导出</button></form>')
    else:
        export_html = ('<button type="button" class="btn" disabled aria-disabled="true">导出（未就绪）</button>'
                       '<p class="hint dim">未就绪原因见左侧检查表；补齐后按钮可用。</p>')
    hist = "".join(f'<li class="dim">v{v["version_no"]} · {esc(v["created_at"])} · {esc(v["created_by"])}</li>'
                   for v in versions[:5]) or '<li class="dim">尚无版本</li>'
    faq_rows = record.get("faq_json") or ""
    return f"""
{wizard_bar("copy", wo)}
<section class="panel" aria-labelledby="h-copy3">
  <div class="panel-head"><h2 id="h-copy3">③ 起草商品介绍</h2>
  <p class="hint">保存会走既有证据接口（CSRF + revision），并生成不可变文案版本；未就绪不提供导出。
  当前 revision {record["revision"]}。</p></div>
  <div class="grid2">
    <form method="post" action="/worksheet/{esc(wo)}/copy/save" class="filters form-grid">
      <input type="hidden" name="csrf" value="{esc(csrf)}">
      <input type="hidden" name="revision" value="{record["revision"]}">
      <label class="field span2"><span>标题（名称）</span><input type="text" name="name" value="{esc(record["name"])}" required></label>
      <label class="field span2"><span>卖点（每行一条）</span><textarea name="selling_points" rows="5">{esc(record.get("selling_points") or "")}</textarea></label>
      <label class="field"><span>价格（分）</span><input type="number" name="price_minor" value="{esc(record.get("price_minor") or "")}"></label>
      <label class="field"><span>文案版本</span><input type="text" name="copy_version" value="{esc(record.get("copy_version") or "")}" placeholder="copy-v1"></label>
      <label class="field"><span>文案状态</span><select name="copy_status">
        <option value="draft"{" selected" if (record.get("copy_status") or "draft") == "draft" else ""}>草稿</option>
        <option value="final"{" selected" if record.get("copy_status") == "final" else ""}>定稿</option></select></label>
      <label class="field span2"><span>包含内容</span><textarea name="includes" rows="3">{esc(record.get("includes") or "")}</textarea></label>
      <label class="field span2"><span>不包含内容</span><textarea name="excludes" rows="3">{esc(record.get("excludes") or "")}</textarea></label>
      <label class="field span2"><span>目标平台条件证据</span>
        <input type="text" name="platform_evidence" value="{esc(record.get("platform_evidence") or "")}"
               placeholder="条款链接或截图编号，例如 20261024-01-类目页截图"></label>
      <p class="hint dim span2">请填<strong>条款链接或截图编号</strong>；未核对前请保持为空，导出会被阻止。
      填了只代表“有证据”，<strong>不代表平台已批准</strong>。核对方法与结论登记见本地文件
      <span class="mono">docs/validation/product-workflow/b23/PLATFORM-CHECKLIST.md</span> 与
      <span class="mono">PLATFORM-DECISION.md</span>。</p>
      <label class="field span2"><span>交付说明</span><textarea name="delivery_note" rows="2">{esc(record.get("delivery_note") or "")}</textarea></label>
      <label class="field span2"><span>售后说明</span><textarea name="aftersales_note" rows="2">{esc(record.get("aftersales_note") or "")}</textarea></label>
      <label class="field span2"><span>FAQ（JSON 数组）</span><textarea name="faq_json" rows="3">{esc(faq_rows)}</textarea></label>
      <div class="filter-actions"><button type="submit" class="btn btn-primary">保存并生成版本</button>
        <a class="btn btn-ghost" href="/source?wo={esc(wo)}">← 返回找货源</a></div>
      <p class="hint dim">改标题（名称）会额外产生一个版本号（一次保存可能 +2 revision）；只改文案字段则 +1。</p>
    </form>
    <div>
      <h3>七项就绪</h3><ul class="stages">{checks}</ul>
      <p class="hint">{'已就绪（服务端判定）' if ready["overall_ready"] else '未就绪：共 %d 项阻断' % len(ready["blockers"])}</p>
      <h3>导出</h3><p class="sortbar">{export_html}</p>
      <p class="dim">{esc(export_info.get("reason") or "尚未导出")}</p>
      <h3>发布回填</h3>
      <p class="sortbar">当前状态：<span class="chip {'chip-ok' if (publish or {}).get('status') == '已发布' else 'chip-warn'}">
      {esc((publish or {}).get("status") or "未发布")}</span>
      {f'<span class="dim">· {esc(publish.get("published_url"))} · 已售 {publish.get("sold_count")}</span>' if publish else ''}</p>
      <p class="hint dim">发布与回填步骤见本地文件 <span class="mono">docs/validation/product-workflow/b24/PUBLISH-CARD.md</span>
      与 <span class="mono">FEEDBACK-CARD.md</span>；填表入口在
      <a href="/worksheet/{esc(wo)}#h-pub">该单详情页的「发布回填」</a>。系统不代发、不登录、不改平台设置。</p>
      <h3>文案版本（最近 5 条）</h3><ul class="gaps">{hist}</ul>
    </div>
  </div>
</section>"""
