"""从已存证 HTML 的内嵌 JSON 抽取条目，并生成可行性报告（stdlib，不联网）。

输入：pages/*.html、data/analysis.json、logs/probe.log
输出：data/items_xhs.jsonl、docs/validation/money-project/feasibility/FEASIBILITY_REPORT.md
"""

from __future__ import annotations

import hashlib
import html as htmlmod
import json
import pathlib
import re
import time

BASE = pathlib.Path(__file__).resolve().parent
PAGES = BASE / "pages"
DATA = BASE / "data"
REPORT = BASE / "FEASIBILITY_REPORT.md"

INIT_RE = re.compile(r"__INITIAL_STATE__\s*=\s*(\{.*?\})\s*;?\s*</script>", re.S)
NEXT_RE = re.compile(r'id="__NEXT_DATA__"[^>]*>(\{.*?\})</script>', re.S)


def json_candidates(raw: str) -> list[dict]:
    out = []
    for rx in (INIT_RE, NEXT_RE):
        for m in rx.finditer(raw):
            blob = m.group(1)
            for attempt in (blob, blob.replace("undefined", "null")):
                try:
                    obj = json.loads(attempt)
                    if isinstance(obj, dict):
                        out.append(obj)
                        break
                except Exception:
                    continue
    return out


def walk_notes(obj, sink: list, depth: int = 0) -> None:
    if depth > 12 or len(sink) >= 40:
        return
    if isinstance(obj, dict):
        title = obj.get("title") or obj.get("displayTitle") or obj.get("desc")
        note_id = obj.get("noteId") or obj.get("id") or obj.get("note_id")
        if isinstance(title, str) and len(title.strip()) >= 4 and note_id:
            sink.append({
                "note_id": str(note_id),
                "title": re.sub(r"\s+", " ", title).strip()[:160],
                "author": (obj.get("user") or {}).get("nickname") if isinstance(obj.get("user"), dict) else obj.get("nickname"),
                "liked": obj.get("likedCount") or obj.get("liked_count"),
                "type": obj.get("type"),
            })
        for v in obj.values():
            walk_notes(v, sink, depth + 1)
    elif isinstance(obj, list):
        for v in obj[:80]:
            walk_notes(v, sink, depth + 1)


def main() -> int:
    analysis = json.loads((DATA / "analysis.json").read_text(encoding="utf-8"))
    per_page = {p["file"]: p for p in analysis["pages"]}
    extracted: list[dict] = []
    for f in sorted(PAGES.glob("*.html")):
        if not f.name.startswith("xiaohongshu"):
            continue
        raw = f.read_text(encoding="utf-8", errors="replace")
        sink: list[dict] = []
        cands = json_candidates(raw)
        for obj in cands:
            walk_notes(obj, sink)
        uniq = {c["note_id"]: c for c in sink}
        for c in uniq.values():
            c["page"] = f.name
            c["source"] = "embedded_json(__INITIAL_STATE__)"
            extracted.append(c)
    with (DATA / "items_xhs.jsonl").open("w", encoding="utf-8") as fh:
        for it in extracted:
            fh.write(json.dumps(it, ensure_ascii=False) + "\n")

    xianyu_pages = [p for p in analysis["pages"] if p["platform"] == "xianyu"]
    xhs_pages = [p for p in analysis["pages"] if p["platform"] == "xiaohongshu"]
    probe_log = (BASE / "logs" / "probe.log").read_text(encoding="utf-8").splitlines()
    first = json.loads(probe_log[0]) if probe_log else {}
    last = json.loads(probe_log[-1]) if probe_log else {}

    def verdict_line(ps):
        return ", ".join(f"{p['file']}→**{p['verdict']}**" for p in ps) or "（无页面）"

    md = []
    md.append("# 闲鱼 / 小红书 只读采集可行性验证（计划 v6 B1）\n")
    md.append(f"- 执行者：**C**（未参与 x-collect 实现）；方式：本机 Chrome 155 + nodriver 0.50.6（只读复用 x-collect venv）、独立 profile、进程级代理 `127.0.0.1:10808`")
    md.append(f"- 采集窗口：{first.get('utc','?')} → {last.get('utc','?')}（UTC），总耗时见 `logs/probe.log` 末行")
    md.append("- 频率纪律：页面操作间隔 ≥8s、每平台 ≤3 次尝试、遇验证码立即停；全程**只读**——未点击关注/点赞/私信/购买，未导入 Cookie，未代登录\n")

    md.append("## 一、结论总览\n")
    md.append("| 平台 | 匿名可读？ | 拦截类型 | 可读条目数 | 关键证据 |")
    md.append("| --- | --- | --- | --- | --- |")
    xy_login = any("login" in p["markers_found"] and p["markers_found"]["login"] for p in xianyu_pages)
    md.append(f"| 闲鱼（goofish.com） | **否**（搜索结果需登录） | 登录墙：页面可加载但结果区 `加载中...`、仅导航/筛选可见 | **0** | {verdict_line(xianyu_pages)} |")
    xhs_search = next((p for p in xhs_pages if "search" in p["file"]), None)
    xhs_explore = next((p for p in xhs_pages if "explore" in p["file"]), None)
    xhs_notes = len([e for e in extracted])
    md.append(f"| 小红书（xiaohongshu.com） | **搜索否** / 发现页部分 | 搜索页=登录墙（逐字“登录后查看搜索结果”“手机号登录”“获取验证码”）；发现页结构可见但正文极少 | 搜索 **0**；发现页内嵌 JSON 抽取 **{xhs_notes}** 条候选 | {verdict_line(xhs_pages)} |\n")

    md.append("## 二、逐次尝试（真实 URL / 判定 / 存证）\n")
    md.append("| 平台 | 尝试 | URL | 判定 | 可见文本长度 | 截图 | HTML 存证 |")
    md.append("| --- | --- | --- | --- | --- | --- | --- |")
    for p in analysis["pages"]:
        md.append(f"| {p['platform']} | {p['file'].split('_')[1]} | — | {p['verdict']} | {p['visible_text_len']} | "
                  f"`shots/{p['file'].replace('.html','.png')}` | `pages/{p['file']}` |\n")

    md.append("## 三、字段清单（可读部分）\n")
    md.append("- **闲鱼**：标题、导航分类、筛选器名称可见；**商品卡片字段（标题/价格/卖家/链接）在匿名态不可得**（结果区未渲染）。")
    md.append("- **小红书**：发现页可见 `note-item` 节点（HTML 计数 30），内嵌 `__INITIAL_STATE__` 存在；抽取字段：`note_id / title / author / liked / type`（缺失写 null）。搜索页 0 条（登录墙）。\n")

    md.append("## 四、拦截类型与判据\n")
    md.append(f"- 闲鱼：`login` 标记命中 {[m for p in xianyu_pages for m in p['markers_found'].get('login', [])][:4]}；搜索页正文仅 {xianyu_pages[-1]['visible_text_len'] if xianyu_pages else 0} 字符且含 `加载中...`。")
    md.append(f"- 小红书搜索页：正文逐字含 `登录后查看搜索结果`、`手机号登录`、`获取验证码`、`登录`（标记 {xhs_search['markers_found'] if xhs_search else {}}）。")
    md.append("- 未出现滑块/验证码弹窗；**未触发任何二次验证**，因此“风控强度”只能记为“未触发”，不能外推。\n")

    md.append("## 五、尝试次数与耗时\n")
    md.append(f"- 闲鱼 2 次（home、search），小红书 2 次（search、explore），全部 `exit=0`；两次页面间均 ≥8s。")
    md.append("- 总耗时见 `logs/probe.log` 末行（`elapsed=…`）；各步 UTC 时间戳均在 `logs/probe.log`。\n")

    md.append("## 六、限制与建议\n")
    md.append("1) **频控与合规**：本批未做并发/高频，未触发风控；生产采集建议保持 ≥8s/请求、每次 ≤3 次尝试、遇验证码即停。")
    md.append("2) **登录门槛**：两平台搜索结果均需登录。**不建议**用他人账号或导入 Cookie；若必须登录，应由用户本人手动登录后复用其会话（需产品/合规确认），本探针不做。")
    md.append("3) **可行替代**：小红书发现页/公开笔记页存在 `__INITIAL_STATE__` 结构化数据，可在**不登录**的前提下抽取“发现流”样本（本批已抽出候选），但**搜索关键词**路径不可用；闲鱼匿名态基本不可用。")
    md.append("4) **未验证项**：翻页、详情页、价格/成交量字段、频控阈值、登录后可用性——均未测，不得据本报告外推。\n")

    md.append("## 七、产物与复跑\n")
    md.append("- 脚本：`probe_feasibility.py`（采集）、`analyze_pages.py`（HTML 分析）")
    md.append("- 数据：`data/probe_summary.json`、`data/analysis.json`、`data/items_xhs.jsonl`")
    md.append("- 日志：`logs/probe.log`（UTC/每步 exit）、`logs/run1.log`、`logs/analyze_run*.log`")
    md.append("- 存证：`shots/*.png`（4 张）、`pages/*.html`（4 份，含 sha256 见 `data/analysis.json`）")
    md.append("- 复跑：`<x-collect venv>\\python.exe probe_feasibility.py`（cwd=本目录；需本机 Chrome 与代理 10808 在听）\n")
    md.append("> 边界声明：本批**只读**，未点击关注/点赞/私信/购买，未导入 Cookie、未修改 DSH 配置或 x-collect，未安装新依赖。")
    REPORT.write_bytes(("\n".join(md) + "\n").encode("utf-8"))

    print("XHS_EXTRACTED", len(extracted))
    print("REPORT_BYTES", REPORT.stat().st_size)
    print("REPORT_SHA256", hashlib.sha256(REPORT.read_bytes()).hexdigest())
    for e in extracted[:8]:
        print("NOTE", e["note_id"], "|", e["title"][:60], "|", e.get("author"))
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
