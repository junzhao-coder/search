"""V9-4 `/leads` read-only page + controlled round actions (no state machine copy)."""

from __future__ import annotations

import html
import json
import os
import pathlib
import sqlite3

ROOT = pathlib.Path(__file__).resolve().parents[2]


def esc(value) -> str:
    return html.escape("" if value is None else str(value), quote=True)


def selection_db() -> pathlib.Path:
    return pathlib.Path(os.environ.get("V9_SELECTION_DB") or
                        (ROOT / "tools" / "selection" / "runtime" / "selection.sqlite3"))


def _read(conn, sql: str, args=()):
    try:
        return conn.execute(sql, args).fetchall()
    except sqlite3.Error:
        return []


def load_lead_data(db_path: pathlib.Path | None = None) -> dict:
    """Read-only snapshot; missing DB/schema -> empty state, never raises to GET."""
    path = pathlib.Path(db_path or selection_db())
    out = {"path": str(path), "exists": path.exists(), "signals": 0, "by_origin": {},
           "by_platform": {}, "categories": [], "cards": [], "reviews": [], "rounds": [],
           "imported_count": 0, "triage": {}, "triage_rows": []}
    if not path.exists():
        return out
    try:
        conn = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True, timeout=5)
        conn.row_factory = sqlite3.Row
    except sqlite3.Error:
        return out
    try:
        table = {r[0] for r in _read(conn, "SELECT name FROM sqlite_master WHERE type='table'")}
        if "signals" not in table:
            return out
        out["signals"] = conn.execute("SELECT COUNT(*) FROM signals").fetchone()[0]
        out["imported_count"] = conn.execute(
            "SELECT COUNT(*) FROM signals WHERE origin_kind='imported'").fetchone()[0]
        if "signal_triage" in table:
            out["triage"] = {r[0]: r[1] for r in _read(
                conn, "SELECT signal_id,label FROM signal_triage")}
            if "signals" in table:
                out["triage_rows"] = [dict(r) for r in _read(
                    conn, "SELECT t.signal_id, t.label, t.manual_override, t.native_id_source, "
                          "t.demand_hits_json, t.promo_hits_json, s.platform, s.native_id, "
                          "substr(s.title,1,40) AS title FROM signal_triage t "
                          "JOIN signals s ON s.id=t.signal_id ORDER BY t.signal_id DESC LIMIT 20")]
        out["by_origin"] = {r[0]: r[1] for r in _read(
            conn, "SELECT origin_kind,COUNT(*) FROM signals GROUP BY origin_kind ORDER BY origin_kind")}
        out["by_platform"] = {r[0]: r[1] for r in _read(
            conn, "SELECT platform,COUNT(*) FROM signals GROUP BY platform ORDER BY platform")}
        if "categories" in table:
            out["categories"] = [dict(r) for r in _read(
                conn, "SELECT c.*, (SELECT COUNT(DISTINCT signal_id) FROM discovery_event e "
                      "WHERE e.category_id=c.id AND e.signal_id IS NOT NULL) AS evidence_count, "
                      "(SELECT MAX(at) FROM discovery_event e WHERE e.category_id=c.id) AS last_event_at "
                      "FROM categories c ORDER BY c.id")]
        if "direction_card" in table:
            out["cards"] = [dict(r) for r in _read(
                conn, "SELECT * FROM direction_card ORDER BY id")]
        if "review_queue" in table:
            out["reviews"] = [dict(r) for r in _read(
                conn, "SELECT * FROM review_queue WHERE status='pending' ORDER BY id LIMIT 10")]
            out["review_total"] = conn.execute(
                "SELECT COUNT(*) FROM review_queue WHERE status='pending'").fetchone()[0]
        if "rounds" in table:
            out["rounds"] = [dict(r) for r in _read(
                conn, "SELECT r.*, (SELECT COUNT(*) FROM round_item i WHERE i.round_id=r.id AND i.state='done') AS done_items "
                      "FROM rounds r ORDER BY r.id DESC LIMIT 20")]
    except sqlite3.Error:
        return out
    finally:
        conn.close()
    return out


def _table(headers, rows, empty="暂无数据", allow_html=False) -> str:
    if not rows:
        return f'<div class="empty"><p class="empty-title">{esc(empty)}</p></div>'
    th = "".join(f"<th scope=\"col\">{esc(h)}</th>" for h in headers)
    def _cell(v):
        return v if allow_html else esc(v)
    body = "".join("<tr>" + "".join(f"<td>{_cell(v)}</td>" for v in row) + "</tr>" for row in rows)
    return f'<div class="table-wrap"><table><thead><tr>{th}</tr></thead><tbody>{body}</tbody></table></div>'


def render_leads(data: dict, *, csrf: str, msg: str = "", err: str = "") -> str:
    dist = " · ".join(f"{k}={v}" for k, v in (data.get("by_origin") or {}).items()) or "—"
    platforms = " · ".join(f"{k}={v}" for k, v in (data.get("by_platform") or {}).items()) or "—"
    cats = []
    for c in data.get("categories") or []:
        cats.append((c.get("id"), c.get("canonical_label"), c.get("status"),
                     c.get("evidence_count"), c.get("last_event_at") or "—"))
    cards = []
    for c in data.get("cards") or []:
        try:
            gaps = "、".join(json.loads(c.get("gaps_json") or "[]"))
        except Exception:
            gaps = c.get("gaps_json") or ""
        cards.append((c.get("id"), c.get("category_id"), c.get("deliverable"),
                      c.get("evidence_ids_json"), gaps, c.get("status")))
    reviews = [(r.get("id"), r.get("signal_id"), r.get("reason"), r.get("candidate_category_id"),
                r.get("created_at")) for r in data.get("reviews") or []]
    rounds = []
    for r in data.get("rounds") or []:
        try:
            budget = json.loads(r.get("budget_json") or "{}")
        except Exception:
            budget = {}
        try:
            cursor = json.loads(r.get("cursor_json") or "{}")
        except Exception:
            cursor = {}
        try:
            requests_used = json.loads(r.get("stats_json") or "{}").get("requests_used", 0)
        except Exception:
            requests_used = 0
        rounds.append((r.get("id"), r.get("status"), cursor.get("last_item_key") or "—",
                       requests_used, budget.get("max_requests"), r.get("started_at"),
                       f'{r.get("done_items", 0)} done'))
    flash = ""
    if msg:
        flash = f'<div class="notice notice-ok" role="status">{esc(msg)}</div>'
    if err:
        flash += f'<div class="notice notice-warn" role="alert">{esc(err)}</div>'
    return f"""
<section class="panel">
  <div class="panel-head"><h2>需求线索 / 轮次（只读）</h2>
    <p class="hint">规则推断，不是市场结论；样本极小。只读展示不触发采集。</p></div>
  <p class="hint">selection 库：<code>{esc(data.get("path"))}</code>
    {"（库不存在，显示空态）" if not data.get("exists") else ""}</p>
  <p class="meta-line">signals <strong>{esc(data.get("signals", 0))}</strong> · origin {esc(dist)} · platform {esc(platforms)}
    · pending review <strong>{esc(data.get("review_total", 0))}</strong>
    · 人工导入 <strong>{esc(data.get("imported_count", 0))}</strong>（人工导入≠自动采集，分开计数）</p>
  {flash}
</section>
<section class="panel">
  <div class="panel-head"><h2>开一轮 B 站采集</h2>
    <p class="hint">每次只推进一轮（budget ≤5、interval ≥3s）；遇 412/验证码即停。需 bvid 或 aid 二选一。</p></div>
  <form method="post" action="/leads/round" class="form-grid">
    <input type="hidden" name="csrf" value="{esc(csrf)}">
    <label>BVID <input name="bvid" placeholder="BV..."></label>
    <label>或 AID <input name="aid" type="number" min="1" placeholder="540769243"></label>
    <label>budget <input name="budget" type="number" min="1" max="5" value="3"></label>
    <label>interval <input name="interval" type="number" min="3" step="1" value="3"></label>
    <label>idempotency key <input name="idempotency_key" placeholder="留空自动生成"></label>
    <div class="filter-actions"><button class="btn btn-primary" type="submit">开轮并推进一次</button></div>
  </form>
</section>
<section class="panel">
  <div class="panel-head"><h2>人工贴一条</h2>
    <p class="hint">url 或 text 至少一项必填；native_id 优先从 url 解析，解析不出用 content_hash 前 16 位（derived）。</p></div>
  <form method="post" action="/leads/manual" class="form-grid">
    <input type="hidden" name="csrf" value="{esc(csrf)}">
    <label>platform
      <select name="platform">
        <option value="xiaohongshu">xiaohongshu</option>
        <option value="douyin">douyin</option>
        <option value="weibo">weibo</option>
        <option value="zhihu">zhihu</option>
        <option value="tieba">tieba</option>
        <option value="other">other</option>
      </select>
    </label>
    <label>url <input name="url" placeholder="https://..."></label>
    <label>title <input name="title" placeholder="可选标题"></label>
    <label>text <input name="text" placeholder="或粘贴文本"></label>
    <div class="filter-actions"><button class="btn btn-primary" type="submit">入库并分流</button></div>
  </form>
</section>
<section class="panel"><div class="panel-head"><h2>品类台账</h2></div>
  {_table(["id", "label", "status", "证据数", "最近事件"], cats)}
</section>
<section class="panel"><div class="panel-head"><h2>方向卡</h2></div>
  {_table(["id", "category", "deliverable", "evidence_ids", "gaps", "status"], cards)}
</section>
<section class="panel"><div class="panel-head"><h2>人工分流（前 20）</h2>
    <p class="hint">label 可改判（只作标注，不影响品类/判重）；显示命中词。</p></div>
  {_table(["signal", "platform", "native_id", "label", "override", "命中(demand)", "命中(promo)", "改判"],
          [(f'{esc(r.get("signal_id"))} {esc(r.get("title") or "")}',
            esc(r.get("platform")), esc(r.get("native_id")), esc(r.get("label")),
            esc(r.get("manual_override") or "—"),
            esc(r.get("demand_hits_json") or "[]"), esc(r.get("promo_hits_json") or "[]"),
            _triage_actions(r.get("signal_id"), csrf)) for r in data.get("triage_rows") or []],
          empty="暂无分流记录", allow_html=True)}
</section>
<section class="panel"><div class="panel-head"><h2>待复核（前 10）</h2></div>
  {_table(["id", "signal", "reason", "candidate", "created_at"], reviews)}
</section>
<section class="panel"><div class="panel-head"><h2>轮次</h2></div>
  {_table(["id", "status", "cursor", "requests_used", "budget", "started_at", "items"], rounds)}
  {"".join(_round_actions(r.get("id"), r.get("status"), csrf) for r in data.get("rounds") or [])}
</section>"""


def _round_actions(round_id, status, csrf) -> str:
    if round_id is None:
        return ""
    actions = []
    if status in ("running", "partial"):
        actions.append("pause")
    if status in ("paused", "partial"):
        actions.append("resume")
    if status != "cancelled":
        actions.append("cancel")
    buttons = "".join(
        f'<form method="post" action="/leads/round/{esc(round_id)}/{a}" class="inline-form">'
        f'<input type="hidden" name="csrf" value="{esc(csrf)}">'
        f'<button class="btn btn-ghost" type="submit">{a}</button></form>'
        for a in actions)
    return f'<p class="hint">round {esc(round_id)}：{buttons}</p>'


def _triage_actions(signal_id, csrf) -> str:
    if signal_id is None:
        return ""
    buttons = "".join(
        f'<form method="post" action="/leads/triage/{esc(signal_id)}" class="inline-form">'
        f'<input type="hidden" name="csrf" value="{esc(csrf)}">'
        f'<input type="hidden" name="label" value="{lab}">'
        f'<button class="btn btn-ghost" type="submit">{lab}</button></form>'
        for lab in ("demand", "promo", "noise"))
    return buttons