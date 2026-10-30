"""商品工作单页面：列表 / 详情 / 编辑表单（服务端渲染，无前端框架）。"""

from __future__ import annotations

import html

import readiness as rd
import workflow as wf

STAGE_CLASS = {"done": "ok", "pending": "neutral"}


def esc(value) -> str:
    return html.escape("" if value is None else str(value), quote=True)


def _field(label: str, name: str, value: str = "", *, required: bool = False, placeholder: str = "",
           textarea: bool = False, hint: str = "") -> str:
    req = ' required aria-required="true"' if required else ""
    hint_html = f'<span class="dim field-hint">{esc(hint)}</span>' if hint else ""
    if textarea:
        control = (f'<textarea name="{name}" rows="3" id="f-{name}"{req} placeholder="{esc(placeholder)}">'
                   f'{esc(value)}</textarea>')
    else:
        control = (f'<input type="text" name="{name}" id="f-{name}" value="{esc(value)}"{req} '
                   f'placeholder="{esc(placeholder)}">')
    return f'<label class="field span2"><span>{esc(label)}{" *" if required else ""}</span>{control}{hint_html}</label>'


def render_new(csrf: str, submit_key: str = "") -> str:
    """自制商品建单表单（不需要采集来源）。"""
    import secrets
    key = submit_key or f"self-{secrets.token_hex(8)}"
    return f"""
<section class="panel" aria-labelledby="h-new">
  <div class="panel-head"><h2 id="h-new">新建自制商品</h2>
  <p class="hint">自制商品（自己做的模板/文档/提示词包等）不需要采集来源；建单后到详情页逐项录入证据。
  单号自动生成 <span class="mono">wo:yyyymmdd-8hex</span>；重复提交同一表单不会重复建单。</p></div>
  <form method="post" action="/worksheet/new" class="filters form-grid">
    <input type="hidden" name="csrf" value="{esc(csrf)}">
    <input type="hidden" name="self_made" value="1">
    <input type="hidden" name="submit_key" value="{esc(key)}">
    {_field("计划商品名", "name", "", required=True, hint="1–80 字，例如：学习计划 Excel 模板")}
    {_field("具体用途", "use_case", "", required=True, hint="例如：学习计划 / 考试倒计时")}
    {_field("拟交付物", "deliverable", "", required=True, hint="例如：Excel .xlsx 单文件（5 表 / 50 公式）")}
    {_field("目标买家", "target_buyer", "", hint="可选，例如：学生 / 备考人群")}
    {_field("格式", "fmt", "", hint="可选，例如：xlsx / md / pdf")}
    {_field("语言", "language", "", hint="可选，例如：中文")}
    {_field("版本", "version", "", hint="可选，例如：v1")}
    {_field("来源标识", "item_id", "", hint="可选，留空自动生成 self:<名称>")}
    {_field("包含内容", "includes", "", textarea=True)}
    {_field("不包含内容", "excludes", "", textarea=True)}
    <label class="field"><span>目标平台</span>
      <select name="target_platform"><option value="xianyu" selected>闲鱼（xianyu）</option></select>
      <span class="dim field-hint">本批仅支持闲鱼</span></label>
    <div class="filter-actions">
      <button type="submit" class="btn btn-primary">建立工作单</button>
      <a class="btn btn-ghost" href="/worksheet">取消</a>
    </div>
  </form>
  <p class="hint dim">建单只填规格；七项证据（货源/许可/样品/成本/平台/文案）到详情页录入，未就绪时导出一律 409。</p>
</section>"""


KIND_OPTIONS = [("同款", "同款"), ("替代", "替代"), ("不匹配", "不匹配")]
LICENSE_OPTIONS = [("unknown", "未记录/不明"), ("yes", "允许"), ("no", "禁止")]


def render_supply(record: dict, candidates: list[dict], csrf: str) -> str:
    rows = ""
    for c in candidates:
        selected = record.get("selected_supply_id") == c["id"]
        badge = '<span class="chip chip-ok">已采用</span>' if selected else ""
        price = f'¥{c["price_minor"] / 100:.2f}' if c.get("price_minor") else "—"
        rows += (
            "<tr>"
            f'<td class="mono">{esc(c["id"])}</td>'
            f'<td>{esc(c["provider"])}<p class="dim small">{esc(c.get("source_url") or "—")}</p></td>'
            f'<td>{esc(c["kind"])}</td>'
            f'<td>{esc(c["commercial"])}/{esc(c["redistribute"])}/{esc(c["resale"])}</td>'
            f'<td class="num">{esc(price)}</td>'
            f'<td>{esc(c.get("conclusion") or c.get("sample_status") or "—")} {badge}</td>'
            '<td>'
            f'<form method="post" action="/worksheet/{esc(record["workorder_id"])}/supply/select" class="inline-form">'
            f'<input type="hidden" name="csrf" value="{esc(csrf)}">'
            f'<input type="hidden" name="revision" value="{record["revision"]}">'
            f'<input type="hidden" name="candidate_id" value="{esc(c["id"])}">'
            '<button type="submit" class="btn btn-ghost">采用为选定货源</button></form>'
            f'<form method="post" action="/worksheet/{esc(record["workorder_id"])}/supply/candidates/{esc(c["id"])}/deactivate" class="inline-form">'
            f'<input type="hidden" name="csrf" value="{esc(csrf)}">'
            '<input type="hidden" name="confirm" value="1">'
            '<button type="submit" class="btn btn-ghost" onclick="return confirm(\'确认停用该候选？（软删除，可保留历史）\')">停用</button>'
            '</form></td></tr>')
    body = rows or ('<tr><td colspan="7"><div class="empty"><p class="dim">还没有货源候选。'
                    '新增一条，或粘贴 b2 格式的 JSON 数组导入。</p></div></td></tr>')
    return f"""
<section class="panel" aria-labelledby="h-supply">
  <div class="panel-head"><h2 id="h-supply">货源候选（{len(candidates)}）</h2>
  <p class="hint">候选只是记录；点「采用为选定货源」才会写入工作单的货源与许可字段（需 revision，替换会记事件）。
  停用为软删除（is_active=0），不会删历史。</p></div>
  <div class="table-wrap"><table><caption class="sr-only">货源候选</caption>
    <thead><tr><th scope="col">候选</th><th scope="col">提供方/链接</th><th scope="col">类型</th>
    <th scope="col">许可（商/分发/转售）</th><th scope="col">价格</th><th scope="col">结论</th>
    <th scope="col">操作</th></tr></thead><tbody>{body}</tbody></table></div>
  <h3>新增候选</h3>
  <form method="post" action="/worksheet/{esc(record["workorder_id"])}/supply/candidates" class="filters form-grid">
    <input type="hidden" name="csrf" value="{esc(csrf)}">
    {_field("提供方 / 来源", "provider", "", required=True, hint="例如：自制 / 某素材站")}
    {_field("来源链接", "source_url", "", hint="http(s):// 或 self:…")}
    <label class="field"><span>类型</span><select name="kind">{"".join(f'<option value="{v}">{t}</option>' for v, t in KIND_OPTIONS)}</select></label>
    <label class="field"><span>可商用</span><select name="commercial">{"".join(f'<option value="{v}">{t}</option>' for v, t in LICENSE_OPTIONS)}</select></label>
    <label class="field"><span>可再分发</span><select name="redistribute">{"".join(f'<option value="{v}">{t}</option>' for v, t in LICENSE_OPTIONS)}</select></label>
    <label class="field"><span>可转售</span><select name="resale">{"".join(f'<option value="{v}">{t}</option>' for v, t in LICENSE_OPTIONS)}</select></label>
    {_field("许可说明", "license_note", "", hint="条款摘要或链接")}
    {_field("价格（分）", "price_minor", "", hint="选填，整数分")}
    {_field("备注", "note", "", textarea=True)}
    <div class="filter-actions"><button type="submit" class="btn btn-ghost">新增候选</button></div>
  </form>
  <h3>粘贴 JSON 导入（数组）</h3>
  <form method="post" action="/worksheet/{esc(record["workorder_id"])}/supply/import" class="filters form-grid">
    <input type="hidden" name="csrf" value="{esc(csrf)}">
    {_field("JSON 数组", "payload", "", textarea=True, hint="字段同 b2/candidates.json；未知字段忽略并报告")}
    <div class="filter-actions"><button type="submit" class="btn btn-ghost">导入</button></div>
  </form>
</section>"""


def render_sample(record: dict, csrf: str) -> str:
    status = record.get("sample_status") or "（未核验）"
    return f"""
<section class="panel" aria-labelledby="h-sample">
  <div class="panel-head"><h2 id="h-sample">样品自检（本地文件）</h2>
  <p class="hint">只读检查工作区内 <span class="mono">docs/</span> 或 <span class="mono">tools/</span> 下的
  .xlsx/.pptx/.md/.csv/.pdf（≤20MB）。xlsx 会读表数/非空单元格/公式数，并检查无外部链接、无 vbaProject；
  <strong>绝不执行宏或脚本</strong>。通过后写入 sample_status=verified 与 sample_ref。</p></div>
  <p class="sortbar">当前样品状态：<span class="chip {'chip-ok' if record.get("sample_status") == "verified" else 'chip-warn'}">{esc(status)}</span>
  <span class="dim">{esc(record.get("sample_ref") or "—")}</span></p>
  <form method="post" action="/worksheet/{esc(record["workorder_id"])}/sample/check" class="filters form-grid">
    <input type="hidden" name="csrf" value="{esc(csrf)}">
    <input type="hidden" name="revision" value="{record["revision"]}">
    {_field("文件路径（工作区内）", "path", "", required=True,
            hint="例如：docs/validation/product-workflow/b7/sample-study-planner-v1.xlsx")}
    <div class="filter-actions"><button type="submit" class="btn btn-primary">执行自检</button></div>
  </form>
</section>"""


def render_copy_history(record: dict, versions: list[dict], csrf: str) -> str:
    rows = "".join(
        "<tr>"
        f'<td class="mono">v{v["version_no"]}</td>'
        f'<td class="mono dim">{esc(v["created_at"])}</td>'
        f'<td>{esc(v["created_by"])}</td>'
        f'<td class="dim">{esc((v["summary"] or "—")[:40])} · sha {esc(v["content_hash"][:10])}</td>'
        '<td><form method="post" action="/worksheet/' + esc(record["workorder_id"]) + '/copy/rollback" class="inline-form">'
        f'<input type="hidden" name="csrf" value="{esc(csrf)}">'
        f'<input type="hidden" name="revision" value="{record["revision"]}">'
        f'<input type="hidden" name="version_no" value="{v["version_no"]}">'
        '<button type="submit" class="btn btn-ghost">回滚到此版本</button></form></td>'
        "</tr>" for v in versions)
    body = rows or ('<tr><td colspan="5"><div class="empty"><p class="dim">还没有文案版本；'
                    '保存证据（文案字段）后会自动生成不可变版本。</p></div></td></tr>')
    return f"""
<section class="panel" aria-labelledby="h-copy">
  <div class="panel-head"><h2 id="h-copy">文案版本历史（{len(versions)}）</h2>
  <p class="hint">保存文案字段时自动生成不可变版本；**同一内容重复保存不新增**。回滚会用旧快照生成**新版本**，历史不删除。</p></div>
  <div class="table-wrap"><table><caption class="sr-only">文案版本历史</caption>
    <thead><tr><th scope="col">版本</th><th scope="col">时间</th><th scope="col">来源</th>
    <th scope="col">摘要</th><th scope="col">操作</th></tr></thead><tbody>{body}</tbody></table></div>
</section>"""


def render_publish(record: dict, publish: dict | None, changed: dict, csrf: str) -> str:
    status = (publish or {}).get("status") or "未发布"
    options = "".join(f'<option value="{v}"{" selected" if status == v else ""}>{v}</option>'
                      for v in ("未发布", "已发布", "已下架"))
    banner = ""
    if changed.get("changed"):
        banner = (
            f'<div class="notice notice-warn" role="status">{esc(changed["reason"])}'
            f'<form method="post" action="/worksheet/{esc(record["workorder_id"])}/export/record" class="inline-form">'
            f'<input type="hidden" name="csrf" value="{esc(csrf)}">'
            '<input type="hidden" name="format" value="md">'
            '<button type="submit" class="btn btn-ghost">重新记录本次导出</button></form></div>')
    info = ""
    if publish:
        info = (f'<p class="sortbar">当前状态：<span class="chip chip-ok">{esc(publish["status"])}</span> · '
                f'链接：{esc(publish.get("published_url") or "—")} · 发布时间：{esc(publish.get("published_at") or "—")} · '
                f'已售 {publish.get("sold_count")} · 更新 {esc(publish["updated_at"])}</p>')
    return f"""
<section class="panel" aria-labelledby="h-pub">
  <div class="panel-head"><h2 id="h-pub">发布回填</h2>
  <p class="hint">上架动作由你手动完成，这里只记录结果；状态/链接变更后若已有导出记录，会提示重新核验与导出。</p></div>
  {banner}{info}
  <form method="post" action="/worksheet/{esc(record["workorder_id"])}/publish" class="filters form-grid">
    <input type="hidden" name="csrf" value="{esc(csrf)}">
    <label class="field"><span>发布状态</span><select name="status">{options}</select></label>
    {_input("发布链接（http/https）", "published_url", (publish or {}).get("published_url") or "")}
    {_input("发布时间（文本，可留空）", "published_at", (publish or {}).get("published_at") or "")}
    {_input("已售数量", "sold_count", (publish or {}).get("sold_count") or 0, kind="number")}
    {_field("平台备注", "platform_note", (publish or {}).get("platform_note") or "", textarea=True)}
    <div class="filter-actions"><button type="submit" class="btn btn-ghost">保存发布信息</button></div>
  </form>
</section>"""


def render_list(records: list[dict], gaps_of, csrf: str) -> str:
    rows = []
    for rec in records:
        gaps = gaps_of(rec)
        rows.append(
            "<tr>"
            f'<td class="mono">{esc(rec["workorder_id"])}</td>'
            f'<td class="cell-title"><a href="/worksheet/{esc(rec["workorder_id"])}">{esc(rec["name"])}</a>'
            f'<p class="dim small">来源：{esc(rec["source_group"])} · {esc(rec["source_item_id"])}</p></td>'
            f'<td>{esc(rec["status_label"])}</td>'
            f'<td class="num">{len(gaps)}</td>'
            f'<td class="mono dim">{esc(rec["updated_at"])}</td>'
            f'<td><a class="btn btn-ghost" href="/worksheet/{esc(rec["workorder_id"])}/edit">编辑</a></td>'
            "</tr>")
    body = ("".join(rows) if rows else
            '<tr><td colspan="6"><div class="empty"><p class="empty-title">还没有工作单</p>'
            '<p class="dim">到 <a href="/opportunities">机会线索</a> 的商品组点「选为候选商品」即可建立。</p></div></td></tr>')
    return f"""
<section class="panel" aria-labelledby="h-ws">
  <div class="panel-head"><h2 id="h-ws">商品工作单</h2>
  <p class="hint">这里只做「选品 + 规格」：初始四门槛全部<strong>未核验</strong>，状态为<strong>待补/待货源</strong>；
  货源、验货、文案素材、人工复核、上架包均为<strong>后续阶段（B2–B5）待实现</strong>，本页不会把候选标成“上架就绪”。</p></div>
  <div class="table-wrap"><table>
    <caption class="sr-only">工作单列表</caption>
    <thead><tr><th scope="col">工作单</th><th scope="col">名称 / 来源</th><th scope="col">状态</th>
    <th scope="col">待核验缺项</th><th scope="col">更新时间</th><th scope="col">操作</th></tr></thead>
    <tbody>{body}</tbody></table></div>
  <p class="hint dim">共 {len(records)} 单；建单入口：<a href="/worksheet/new">新建自制商品</a>（自制），或到 <a href="/opportunities">机会线索</a> 的商品组选候选。</p>
</section>"""


def render_detail(record: dict, gaps: list[str], stages: list[dict], csrf: str) -> str:
    snap = record["snapshot"]
    spec_rows = [
        ("计划商品名", record["name"]), ("具体用途", record["use_case"]), ("目标买家", record["target_buyer"]),
        ("拟交付物", record["deliverable"]), ("格式", record["fmt"]), ("语言", record["language"]),
        ("版本", record["version"]), ("包含内容", record["includes"]), ("不包含内容", record["excludes"]),
        ("目标平台", record["target_platform"]),
    ]
    spec_html = "".join(f"<dt>{esc(k)}</dt><dd>{esc(v) or '—'}</dd>" for k, v in spec_rows)
    gates = "".join(
        f'<li>{esc(g)}：<strong>未核验</strong>（本批无自动通过路径）</li>'
        for g in wf.GATES)
    gaps_html = "".join(f"<li>{esc(g)}</li>" for g in gaps)
    stages_html = "".join(
        f'<li class="stage stage-{esc(s["state"])}"><span class="chip chip-{STAGE_CLASS.get(s["state"], "neutral")}">'
        f'{esc(s["label"])}</span> <span class="dim">{esc(s["note"])}</span></li>' for s in stages)
    return f"""
<section class="panel" aria-labelledby="h-detail">
  <div class="panel-head"><h2 id="h-detail">{esc(record["name"])}</h2>
  <p class="hint mono">{esc(record["workorder_id"])} · revision {record["revision"]} · 状态 {esc(record["status_label"])}</p></div>
  <p class="notice notice-warn" role="note">以下区块是<strong>来源快照与历史阶段说明</strong>，
  不代表当前状态。当前是否可上架只看下方「上架准备检查（服务端判定）」——那里的七项才由证据字段实时推导。</p>
  <p class="sortbar"><a class="btn btn-ghost" href="/worksheet">← 返回列表</a>
    <a class="btn" href="/worksheet/{esc(record["workorder_id"])}/edit">编辑规格</a></p>
  <div class="grid2">
    <div><h3>计划规格</h3><dl class="kv kv-wide">{spec_html}</dl>
      <p class="hint dim">规格为计划项，不代表已验货事实。</p></div>
    <div><h3>来源证据（选择时快照，不可编辑）</h3>
      <dl class="kv kv-wide">
        <dt>来源分组</dt><dd>{esc(record["source_group"])}</dd>
        <dt>来源条目</dt><dd class="mono">{esc(record["source_item_id"])}</dd>
        <dt>平台</dt><dd>{esc(record["source_platform"])}</dd>
        <dt>原始标题</dt><dd>{esc(snap.get("title"))}</dd>
        <dt>原链接</dt><dd><a href="{esc(record["source_url"])}" target="_blank" rel="noopener noreferrer nofollow">{esc(record["source_url"])}</a></dd>
        <dt>需求分位 / 可售性</dt><dd>{esc(snap.get("demand_norm"))} / {esc(snap.get("sellability_norm"))}</dd>
        <dt>可售性理由</dt><dd>{esc(snap.get("sellability_reason")) or "—"}</dd>
        <dt>毛利区间</dt><dd>{esc(snap.get("margin_low"))}–{esc(snap.get("margin_high"))}（模型假设）</dd>
        <dt>成本输入</dt><dd>{esc(snap.get("cost_input")) or "缺失"}</dd>
      </dl></div>
  </div>
</section>
<section class="panel" aria-labelledby="h-gaps">
  <div class="panel-head"><h2 id="h-gaps">来源快照与历史阶段（非当前状态）· 待核验缺项（{len(gaps)}）</h2>
  <p class="hint">本区块保留建单时的来源快照与阶段说明，仅作历史参考；<strong>当前就绪状态以上方服务端检查为准</strong>。
  缺项由来源字段推导，不能手动勾掉。</p></div>
  <ul class="gaps">{gaps_html}</ul>
  <h3>四门槛</h3><ul class="risk">{gates}</ul>
</section>
<section class="panel" aria-labelledby="h-flow">
  <div class="panel-head"><h2 id="h-flow">流程进度</h2><p class="hint">只有“选产品”在本批可操作，其余阶段待后续实现。</p></div>
  <ol class="stages">{stages_html}</ol>
</section>"""


def _input(label: str, name: str, value="", *, kind: str = "text", placeholder: str = "", hint: str = "") -> str:
    v = "" if value is None else value
    hint_html = f'<span class="dim field-hint">{esc(hint)}</span>' if hint else ""
    return (f'<label class="field"><span>{esc(label)}</span>'
            f'<input type="{kind}" name="{name}" value="{esc(v)}" placeholder="{esc(placeholder)}">{hint_html}</label>')


def _select(label: str, name: str, options: list[tuple[str, str]], current: str, hint: str = "") -> str:
    opts = "".join(f'<option value="{esc(v)}"{" selected" if str(current or "") == v else ""}>{esc(t)}</option>'
                   for v, t in options)
    hint_html = f'<span class="dim field-hint">{esc(hint)}</span>' if hint else ""
    return (f'<label class="field"><span>{esc(label)}</span><select name="{name}">{opts}</select>{hint_html}</label>')


def render_readiness(record: dict, ready: dict, export_info: dict, csrf: str) -> str:
    rows = []
    for check in ready["checks"]:
        tone = "ok" if check["ok"] else "warn"
        state = "通过" if check["ok"] else "未通过"
        rows.append(
            "<tr>"
            f'<td>{esc(check["label"])}</td>'
            f'<td><span class="chip chip-{tone}">{state}</span></td>'
            f'<td class="dim">{esc(check["blocker"]) or "—"}</td>'
            "</tr>")
    overall = ("已就绪（服务端判定）" if ready["overall_ready"] else "未就绪")
    blockers = "".join(f"<li>{esc(b)}</li>" for b in ready["blockers"]) or "<li>无</li>"
    if ready["overall_ready"]:
        export_buttons = (
            f'<a class="btn btn-primary" href="/worksheet/{esc(record["workorder_id"])}/export?format=md">'
            '导出 Markdown（买家可见）</a> '
            f'<a class="btn btn-ghost" href="/worksheet/{esc(record["workorder_id"])}/export?format=json">'
            '导出 JSON</a> '
            f'<form method="post" action="/worksheet/{esc(record["workorder_id"])}/export/record" class="inline-form">'
            f'<input type="hidden" name="csrf" value="{esc(csrf)}">'
            '<label class="field"><span>记录格式</span><select name="format">'
            '<option value="md">Markdown</option><option value="json">JSON</option></select></label>'
            '<button type="submit" class="btn btn-ghost">记录本次导出</button>'
            '</form>')
    else:
        export_buttons = (
            '<button type="button" class="btn" disabled aria-disabled="true" '
            'title="存在未通过的检查项，导出已禁用">导出 Markdown（未就绪）</button> '
            '<button type="button" class="btn" disabled aria-disabled="true">导出 JSON（未就绪）</button>')
    export_state = ""
    if export_info.get("has_export"):
        tone = "ok" if export_info["valid"] else "warn"
        export_state = (
            f'<p class="sortbar">上次导出：<span class="chip chip-{tone}">'
            f'{"有效" if export_info["valid"] else "已失效"}</span> '
            f'<span class="dim">{esc(export_info.get("created_utc"))} · {esc(export_info.get("format"))}'
            f' · sha {esc((export_info.get("content_sha256") or "")[:12])} · {esc(export_info.get("reason"))}</span></p>')
    else:
        export_state = '<p class="sortbar dim">尚未导出过。</p>'

    lic = {k: (record.get(k) or "unknown") for k in rd.LICENSE_KEYS}
    lic_opts = [("unknown", "未记录/不明"), ("yes", "允许"), ("no", "禁止")]
    sample_opts = [("", "未核验"), ("pending", "核验中"), ("verified", "已核对")]
    copy_opts = [("draft", "草稿"), ("final", "定稿")]
    return f"""
<section class="panel" aria-labelledby="h-ready">
  <div class="panel-head"><h2 id="h-ready">上架准备检查（服务端判定）</h2>
  <p class="hint">{esc(overall)}：共 {len(ready["checks"])} 项，未通过 {len(ready["blockers"])} 项。就绪与否只看证据字段，不提供“标记完成”的入口。</p></div>
  <div class="table-wrap"><table><caption class="sr-only">上架准备检查</caption>
    <thead><tr><th scope="col">检查项</th><th scope="col">结果</th><th scope="col">缺项/原因</th></tr></thead>
    <tbody>{''.join(rows)}</tbody></table></div>
  <p class="sortbar"><strong>阻断项</strong></p><ul class="gaps">{blockers}</ul>
  <p class="sortbar">{export_buttons}</p>
  <p class="hint dim">GET 导出仅生成内容、<strong>不写库</strong>；点「记录本次导出」才会写入导出记录（版本戳入库，供失效比对）。</p>
  {export_state}
  <p class="hint dim">导出只含买家可见字段：标题、卖点、内容清单、格式/兼容、价格规格、交付与售后、FAQ；
  不含采购成本、利润、打分、货源内部备注与内部路径。</p>
</section>
<section class="panel" aria-labelledby="h-evidence">
  <div class="panel-head"><h2 id="h-evidence">录入证据（填写后仍需服务端检查）</h2>
  <p class="hint">这些是证据字段，不是“就绪开关”：许可三档需明确允许、样品需已核对、成本与平台条件需有据、文案需定稿。</p>
  <p class="hint dim">文案字段（卖点/价格/交付/售后/FAQ）与<strong>文案版本</strong>请在
  <a href="/copy?wo={esc(record["workorder_id"])}">「起草介绍」页</a>编辑；<strong>本页保存不生成文案版本</strong>。</p></div>
  <form method="post" action="/worksheet/{esc(record["workorder_id"])}/evidence" class="filters form-grid">
    <input type="hidden" name="csrf" value="{esc(csrf)}">
    <input type="hidden" name="revision" value="{record["revision"]}">
    {_input("货源 ID", "selected_supply_id", record.get("selected_supply_id"), hint="B2 选定的货源标识")}
    {_input("货源版本", "supply_version", record.get("supply_version"))}
    {_select("许可·可商用", "supply_license_commercial", lic_opts, lic["supply_license_commercial"])}
    {_select("许可·可再分发", "supply_license_redistribute", lic_opts, lic["supply_license_redistribute"])}
    {_select("许可·可转售", "supply_license_resell", lic_opts, lic["supply_license_resell"])}
    {_select("样品/交付入口", "sample_status", sample_opts, record.get("sample_status") or "")}
    {_input("样品核验证据（URL/编号）", "sample_ref", record.get("sample_ref"))}
    {_input("成本（分）", "cost_minor", record.get("cost_minor"), kind="number", hint="整数，单位分")}
    {_select("成本是否已知", "cost_known", [("", "否"), ("yes", "是")], record.get("cost_known") or "")}
    {_input("目标平台条件证据", "platform_evidence", record.get("platform_evidence"), hint="条款 URL 或截图编号")}
    {_select("文案状态", "copy_status", copy_opts, record.get("copy_status") or "draft")}
    {_input("文案版本", "copy_version", record.get("copy_version"), hint="如 v1")}
    {_input("建议售价（分）", "price_minor", record.get("price_minor"), kind="number")}
    {_input("交付说明", "delivery_note", record.get("delivery_note"))}
    {_input("售后说明", "aftersales_note", record.get("aftersales_note"))}
    {_field("卖点（每行一条）", "selling_points", record.get("selling_points") or "", textarea=True)}
    {_field("FAQ（JSON 数组：{\"q\":\"…\",\"a\":\"…\"}）", "faq_json", record.get("faq_json") or "", textarea=True)}
    <div class="filter-actions"><button type="submit" class="btn btn-primary">保存证据（revision {record["revision"]}）</button></div>
  </form>
</section>"""


def render_edit(record: dict, csrf: str, error: str = "") -> str:
    err_html = f'<div class="notice notice-warn" role="alert">{esc(error)}</div>' if error else ""
    status_options = "".join(
        f'<option value="{esc(k)}"{" selected" if record["status"] == k else ""}>{esc(v)}</option>'
        for k, v in wf.STATUS_LABEL.items())
    return f"""
<section class="panel" aria-labelledby="h-edit">
  <div class="panel-head"><h2 id="h-edit">编辑规格</h2>
  <p class="hint mono">{esc(record["workorder_id"])} · 当前 revision {record["revision"]}</p></div>
  {err_html}
  <form method="post" action="/worksheet/{esc(record["workorder_id"])}/edit" class="filters form-grid">
    <input type="hidden" name="csrf" value="{esc(csrf)}">
    <input type="hidden" name="revision" value="{record["revision"]}">
    {_field("计划商品名", "name", record["name"], required=True, hint="1–80 字")}
    {_field("具体用途", "use_case", record["use_case"], required=True, hint="如：求职投递追踪")}
    {_field("目标买家", "target_buyer", record["target_buyer"])}
    {_field("拟交付物", "deliverable", record["deliverable"], required=True, hint="如：Notion 页面模板（可复制）")}
    {_field("格式", "fmt", record["fmt"], hint="如：Notion / PSD / PDF")}
    {_field("语言", "language", record["language"])}
    {_field("版本", "version", record["version"])}
    {_field("包含内容", "includes", record["includes"], textarea=True)}
    {_field("不包含内容", "excludes", record["excludes"], textarea=True)}
    <label class="field"><span>目标平台</span>
      <select name="target_platform"><option value="xianyu" selected>闲鱼（xianyu）</option></select>
      <span class="dim field-hint">本批仅支持闲鱼</span></label>
    <label class="field"><span>状态</span>
      <select name="status">{status_options}</select>
      <span class="dim field-hint">只有“待补/待货源”“核验中”；ready/verified 由后续阶段接入</span></label>
    <div class="filter-actions">
      <button type="submit" class="btn btn-primary">保存（revision {record["revision"]}）</button>
      <a class="btn btn-ghost" href="/worksheet/{esc(record["workorder_id"])}">取消</a>
    </div>
  </form>
  <p class="hint dim">保存会做服务端校验：必填/长度/平台/状态；旧 revision 提交会 409 冲突且不改原记录。</p>
</section>"""
