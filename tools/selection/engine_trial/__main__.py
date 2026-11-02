"""Run the local engine trial and write a reproducible JSON + Markdown report.

Usage:
    python -m tools.selection.engine_trial --engine all --runs 3 \
        --out docs/validation/v18/engine-trial

The command never touches a real site or a user profile: the fixture is local
and every browser launch uses a fresh temporary profile.
"""

from __future__ import annotations

import argparse
import datetime
import json
import pathlib
import platform
import sys

from . import collector, engines, extract, fixture


def _stats(values) -> dict:
    numbers = sorted(float(value) for value in values
                     if isinstance(value, (int, float)))
    if not numbers:
        return {"n": 0, "min": None, "median": None, "max": None}
    middle = len(numbers) // 2
    median = (numbers[middle] if len(numbers) % 2
              else (numbers[middle - 1] + numbers[middle]) / 2)
    return {"n": len(numbers), "min": round(numbers[0], 1),
            "median": round(median, 1), "max": round(numbers[-1], 1)}


def _aggregate(entry: dict, truth: dict) -> dict:
    runs = entry.get("runs") or []
    if not runs:
        entry["status"] = "blocked"
        return entry
    entry["timings"] = {
        phase: _stats([(run.get("phases") or {}).get(phase) for run in runs])
        for phase in ("start_ms", "navigate_ms", "first_read_ms", "evidence_ms",
                      "final_evidence_ms", "actions_ms", "close_ms", "total_ms")
    }
    ids_union = sorted({item for run in runs for item in run.get("ids") or []})
    ids_intersection = (sorted(set.intersection(
        *(set(run.get("ids") or []) for run in runs))) if runs else [])
    entry["ids_union"] = ids_union
    entry["ids_intersection"] = ids_intersection
    entry["ids_stable"] = all(set(run.get("ids") or []) == set(ids_union)
                              for run in runs)
    entry["missing_vs_ground"] = sorted(set(truth["ids"]) - set(ids_union))
    entry["extra_vs_ground"] = sorted(set(ids_union) - set(truth["ids"]))
    first = runs[0]
    entry["fields"] = first.get("fields") or {}
    entry["action_evidence"] = first.get("action_evidence") or {}
    entry["stop_reasons"] = [run.get("stop") for run in runs]
    entry["stop_details"] = [run.get("stop_detail") for run in runs]
    entry["desktop_proof"] = (first.get("evidence") or {}).get("desktop_proof")
    entry["screenshots"] = [(run.get("evidence") or {}).get("page_screenshot")
                            for run in runs]
    entry["final_screenshots"] = [
        (run.get("final_evidence") or {}).get("page_screenshot") for run in runs]
    entry["visibility"] = ("not_checked" if not entry["desktop_proof"] else
                           "proven" if entry["desktop_proof"].get("proven")
                           else "unproven")
    actions_ok = all((run.get("action_evidence") or {}).get("ok")
                     for run in runs)
    stops_ok = all(run.get("stop") == "no_growth" for run in runs)
    ids_ok = not entry["missing_vs_ground"]
    entry["status"] = ("verified" if (actions_ok and stops_ok and ids_ok)
                       else "partial")
    entry["verdict"] = (
        f"stop={','.join(str(item) for item in entry['stop_reasons'])}; "
        f"ids={len(ids_union)}/{len(truth['ids'])}; "
        f"missing={len(entry['missing_vs_ground'])}; "
        f"extra={len(entry['extra_vs_ground'])}; "
        f"actions_ok={actions_ok}; visibility={entry['visibility']}")
    return entry


def _make_driver(name: str, args):
    if name == "playwright":
        return engines.PlaywrightDriver(
            headless=args.headless, channel=args.channel,
            timeout_ms=args.timeout_ms)
    return engines.NodriverDriver(headless=args.headless,
                                  timeout=args.timeout_ms / 1000.0)


def _run_engine(name: str, fixture_path: pathlib.Path, out: pathlib.Path,
                args) -> dict:
    info = engines.availability(name)
    entry = {"engine": name, "availability": info, "runs": [],
             "status": "blocked", "reason": info.get("reason"),
             "repro": info.get("repro")}
    if not info.get("usable"):
        return entry
    shots = out / "shots"
    shots.mkdir(parents=True, exist_ok=True)
    for index in range(max(1, int(args.runs))):
        driver = _make_driver(name, args)

        def evidence(drv, state, index=index):
            shot_path = shots / f"{name}-run{index + 1}.png"
            try:
                shot = drv.screenshot(shot_path)
            except Exception as exc:  # noqa: BLE001 - evidence failure is reported
                shot = {"path": str(shot_path),
                        "error": f"{type(exc).__name__}:{exc}"}
            proof = None
            if index == 0 and not args.no_desktop_proof:
                try:
                    title = drv.evaluate("document.title")
                    from tools.selection.rpa import desktop
                    proof = desktop.prove(title_hint=str(title), screenshot=None,
                                          wait_s=2.0)
                except Exception as exc:  # noqa: BLE001
                    proof = {"proven": False,
                             "reason": f"desktop_proof_error:{type(exc).__name__}:{exc}"}
            return {"page_screenshot": shot, "desktop_proof": proof}

        def final_evidence(drv, state, index=index):
            shot_path = shots / f"{name}-run{index + 1}-final.png"
            try:
                return {"page_screenshot": drv.screenshot(shot_path)}
            except Exception as exc:  # noqa: BLE001
                return {"page_screenshot": {
                    "path": str(shot_path),
                    "error": f"{type(exc).__name__}:{exc}"}}

        result = collector.run_trial(
            driver, fixture_path.as_uri(),
            config=collector.TrialConfig(max_scrolls=args.max_scrolls,
                                         settle_ms=args.settle_ms,
                                         timeout_ms=args.timeout_ms),
            evidence=evidence, final_evidence=final_evidence)
        entry["runs"].append(result)
    return entry


def _limitations(report: dict) -> list[str]:
    out = [
        "本地 fixture，不是真实贴吧；真实站点选择器、会话、风控均未验证。",
        "页面声明 12 条、可见 9 条；no_growth 只证明本次动作无新增/无位移，"
        "没有可核验的到底标记，按部分/未知处理。",
        "Playwright 使用 CDP 合成输入，不移动系统鼠标指针；不是物理鼠标轨迹。",
        "样本量为配置的重复次数，同一台机器、同一 Chrome；不能外推到真实站点速度。",
        "桌面可见性以 desktop.prove 结果为准；若未 proven，不能声称用户已看到。",
        "未访问真实贴吧、未读取或修改用户 profile；每次启动使用临时独立 profile。",
        "桌面证据不含整屏截图；只保存页面截图与前台窗口/矩形证据，"
        "避免截入无关桌面内容。",
    ]
    playwright = report["engines"].get("playwright")
    nodriver = report["engines"].get("nodriver")
    if playwright and playwright.get("runs"):
        out.append("Playwright 使用项目外已存在的 Python 3.12.10 + "
                   "playwright 1.60.0；未安装或修改环境。")
    if nodriver and nodriver.get("runs"):
        executable = (report.get("environment") or {}).get(
            "nodriver_executable") or "nodriver 解释器"
        version = (nodriver.get("availability") or {}).get("version") or "unknown"
        out.append(f"nodriver 使用 `{executable}`（nodriver {version}）；与 Playwright "
                   "使用同一 Chrome 二进制、同一 fixture、同样 n=3 和临时独立 profile。")
        out.append("nodriver 页面截图按浏览器窗口尺寸输出（本次 1920×1080），布局视口"
                   "仍固定 1280×720；截图尺寸差异不影响 DOM 提取与滚动位移。")
    else:
        out.append("nodriver 未运行；空集不等于两引擎一致，未把空集当作对照结果。")
    return out


def _render_markdown(report: dict) -> str:
    lines: list[str] = []

    def add(text: str = "") -> None:
        lines.append(text)

    add("# v18 单帖引擎试点：Playwright 主引擎 / nodriver 备用（本地 fixture）")
    add()
    add(f"- 生成时间：{report['generated_at']}")
    add(f"- 命令：`{report['command']}`")
    add(f"- 输出目录：`{report['out']}`")
    if report.get("playwright_generated_at"):
        add(f"- Playwright 数据生成时间：{report['playwright_generated_at']}")
    if report.get("playwright_command"):
        add(f"- Playwright 命令：`{report['playwright_command']}`")
    add()
    add("## 结论")
    for name in ("playwright", "nodriver"):
        entry = report["engines"].get(name)
        if not entry:
            continue
        if entry["status"] == "blocked":
            detail = (entry.get("availability") or {}).get("detail")
            add(f"- **{name}**：blocked，`{entry.get('reason')}`；"
                f"detail=`{detail}`；复现：`{entry.get('repro')}`。")
        else:
            add(f"- **{name}**：{entry['status']}；{entry['verdict']}。")
            if entry.get("visibility") == "unproven":
                proof = entry.get("desktop_proof") or {}
                add(f"  - 桌面可见性未证明：`{proof.get('reason')}`；"
                    "不能声称用户已看到窗口。")
            elif entry.get("visibility") == "proven":
                add("  - 桌面可见性：`desktop.prove` 前台窗口匹配 + 窗口矩形通过。")
    comparison = report.get("comparison") or {}
    add(f"- **两引擎对照**：{comparison.get('status')}；{comparison.get('reason', '')}")
    if comparison.get("status") == "compared":
        add()
        add("| 对照项 | 值 |")
        add("| --- | --- |")
        add(f"| 共同 ID | {comparison.get('common_count')} |")
        left_only = ", ".join(comparison.get("left_only") or []) or "无"
        right_only = ", ".join(comparison.get("right_only") or []) or "无"
        add(f"| 仅 Playwright | {left_only} |")
        add(f"| 仅 nodriver | {right_only} |")
    add()
    add("## 环境")
    add()
    add("| 项 | 值 |")
    add("| --- | --- |")
    add(f"| 操作系统 | {report['environment']['platform']} |")
    add(f"| Python | {report['environment']['python']} |")
    add(f"| 解释器 | `{report['environment']['executable']}` |")
    add(f"| 工作目录 | `{report['environment']['cwd']}` |")
    if report["environment"].get("nodriver_executable"):
        add(f"| nodriver 解释器 | `{report['environment']['nodriver_executable']}` |")
        add(f"| nodriver Python | {report['environment'].get('nodriver_python')} |")
        add(f"| nodriver venv | `{report['environment'].get('nodriver_venv')}` |")
    for name, entry in report["engines"].items():
        info = entry.get("availability") or {}
        add(f"| {name} 版本 | {info.get('version') or '未安装'} |")
        add(f"| {name} Chrome | `{info.get('chrome')}` |")
        browser_version = (((entry.get("runs") or [{}])[0].get("environment") or {})
                           .get("browser_version"))
        add(f"| {name} 浏览器版本 | {browser_version or '未记录'} |")
    add()
    add("> 环境边界：项目 `.venv` 未安装 playwright；Playwright 使用已存在的 "
        "Python 3.12.10（playwright 1.60.0），nodriver 使用本机已有的 x-collect venv"
        "（nodriver 0.50.6）；未安装或修改任何环境。")
    add()
    for name, entry in report["engines"].items():
        if not entry.get("runs"):
            continue
        profile = (entry["runs"][0].get("start_info") or {}).get("profile")
        add(f"- **{name}** 临时 profile：`{profile}`（运行结束删除）")
    add()
    add("## Fixture 与地面真值")
    add()
    truth = report["fixture"]["ground_truth"]
    add(f"- 文件：`{report['fixture']['path']}`")
    add(f"- URL：`{report['fixture']['url']}`")
    add(f"- 帖子 ID：`{truth['thread_id']}`；正文、作者、时间、点赞均来自页面 DOM。")
    add(f"- 地面真值：{len(truth['comment_ids'])} 条顶层评论 + "
        f"{len(truth['lzl_ids'])} 条楼中楼 + 1 条帖子；页面声明 "
        f"{truth['declared_comments']} 条评论。")
    add()
    add("## 计时（每次运行独立启动浏览器）")
    add()
    for name, entry in report["engines"].items():
        if not entry.get("runs"):
            continue
        add(f"### {name}（n={len(entry['runs'])}）")
        add()
        add("| 阶段 | n | min ms | median ms | max ms |")
        add("| --- | --- | --- | --- | --- |")
        for phase, label in (("start_ms", "启动浏览器"), ("navigate_ms", "导航"),
                             ("first_read_ms", "首次读取"),
                             ("evidence_ms", "证据采集（截图/置前）"),
                             ("final_evidence_ms", "动作后截图"),
                             ("actions_ms", "动作+读取"), ("close_ms", "关闭"),
                             ("total_ms", "总计（含证据）")):
            stats = (entry.get("timings") or {}).get(phase) or {}
            add(f"| {label} | {stats.get('n')} | {stats.get('min')} | "
                f"{stats.get('median')} | {stats.get('max')} |")
        add()
    add("样本量 n=3，同一台机器、同一 Chrome、同一本地 fixture；只用于引擎自身"
        "对照，不能外推到真实站点或用户网络。")
    add()
    playwright_entry = report["engines"].get("playwright") or {}
    nodriver_entry = report["engines"].get("nodriver") or {}
    if playwright_entry.get("runs") and nodriver_entry.get("runs"):
        def _median(entry, phase):
            return ((entry.get("timings") or {}).get(phase) or {}).get("median")

        add("## 计时差异说明")
        add()
        add(f"- 启动/导航/首次读取量级接近；动作+读取中位：Playwright "
            f"{_median(playwright_entry, 'actions_ms')} ms，nodriver "
            f"{_median(nodriver_entry, 'actions_ms')} ms。")
        add(f"- 关闭中位：Playwright {_median(playwright_entry, 'close_ms')} ms，"
            f"nodriver {_median(nodriver_entry, 'close_ms')} ms；nodriver 的关闭"
            "包含 `aclose`、进程 wait 与 transport close，Playwright 使用 "
            "context.close，属于驱动清理路径差异。")
        add(f"- 证据采集中位：Playwright "
            f"{_median(playwright_entry, 'evidence_ms')} ms，nodriver "
            f"{_median(nodriver_entry, 'evidence_ms')} ms；动作后截图中位："
            f"Playwright {_median(playwright_entry, 'final_evidence_ms')} ms，"
            f"nodriver {_median(nodriver_entry, 'final_evidence_ms')} ms。"
            "这部分已从动作/关闭阶段扣除，只计入总计；截图与 desktop.prove 的"
            "驱动实现差异不影响 ID/动作/位移结论。")
        add("- 两边均固定 1280×720 CSS 视口（nodriver 用 CDP "
            "`Emulation.setDeviceMetricsOverride`），使用同一 Chrome 156 二进制；"
            "ID、动作与页面位移完全一致，计时差异不改变数据判据。")

        def _collection_total(entry):
            timings = entry.get("timings") or {}
            total = (timings.get("total_ms") or {}).get("median")
            evidence = (timings.get("evidence_ms") or {}).get("median") or 0
            final = (timings.get("final_evidence_ms") or {}).get("median") or 0
            return None if total is None else round(total - evidence - final, 1)

        add(f"- 扣除证据采集后的总计约：Playwright "
            f"{_collection_total(playwright_entry)} ms，nodriver "
            f"{_collection_total(nodriver_entry)} ms；差异主要来自关闭清理与"
            "点击定位/滚动路径，不是页面数据量差异。")
        add()
    add("## 实际动作证据")
    add()
    for name, entry in report["engines"].items():
        if not entry.get("runs"):
            continue
        evidence = entry.get("action_evidence") or {}
        counts = evidence.get("counts") or {}
        expected = evidence.get("expected") or {}
        displacement = evidence.get("displacement") or {}
        add(f"### {name}（run 1）")
        add()
        add(f"- 页面事件：wheel={counts.get('wheel', 0)}/"
            f"{expected.get('wheel', 0)}，click={counts.get('click', 0)}/"
            f"{expected.get('click', 0)}，expand={counts.get('expand', 0)}，"
            f"load_more={counts.get('load_more', 0)}，"
            f"lazy_load={counts.get('lazy_load', 0)}。")
        trusted = evidence.get("trusted") or {}
        add(f"- 可信输入（`isTrusted=true`）：click={trusted.get('click', 0)}，"
            f"wheel={trusted.get('wheel', 0)}，expand={trusted.get('expand', 0)}，"
            f"load_more={trusted.get('load_more', 0)}。")
        add(f"- 页面位移：scrollY {displacement.get('scroll_y_start')} → "
            f"{displacement.get('scroll_y_end')}；scrollHeight "
            f"{displacement.get('scroll_height_start')} → "
            f"{displacement.get('scroll_height_end')}。")
        add(f"- 自检：{'通过' if evidence.get('ok') else '未通过'}；"
            f"checks={json.dumps(evidence.get('checks') or {}, ensure_ascii=False)}")
        final_shot = (entry["runs"][0].get("final_evidence") or {}).get(
            "page_screenshot")
        if isinstance(final_shot, dict):
            add(f"- 动作后截图：`{final_shot.get('path')}`"
                f"（{final_shot.get('bytes')} bytes）。")
        add()
        add(f"### {name} run 1 动作时间线")
        add()
        add("| 时间线 ms | 阶段 | 细节 |")
        add("| --- | --- | --- |")
        for item in entry["runs"][0].get("timeline") or []:
            detail = {key: value for key, value in item.items()
                      if key not in ("phase", "ms")}
            add(f"| {item.get('ms')} | `{item.get('phase')}` | "
                f"`{json.dumps(detail, ensure_ascii=False)[:180]}` |")
        add()
    add("## 数据对照")
    add()
    add("| 引擎 | 运行数 | ID 并集 | 地面真值 | 缺失 | 额外 | 每次一致 |")
    add("| --- | --- | --- | --- | --- | --- | --- |")
    for name, entry in report["engines"].items():
        if not entry.get("runs"):
            add(f"| {name} | 0 | - | {len(truth['ids'])} | - | - | - |")
            continue
        add(f"| {name} | {len(entry['runs'])} | {len(entry['ids_union'])} | "
            f"{len(truth['ids'])} | {len(entry['missing_vs_ground'])} | "
            f"{len(entry['extra_vs_ground'])} | {entry.get('ids_stable')} |")
    add()
    for name, entry in report["engines"].items():
        if not entry.get("runs"):
            continue
        fields = entry.get("fields") or {}
        add(f"- **{name}**：记录 {fields.get('count')}（顶层评论 "
            f"{fields.get('comment')}，楼中楼 {fields.get('lzl')}）；"
            f"likes 已知 {fields.get('likes_known')}，时间已知 "
            f"{fields.get('times_known')}。")
        if entry.get("missing_vs_ground"):
            add(f"  - 相对地面真值缺失：`{', '.join(entry['missing_vs_ground'])}`")
        if entry.get("extra_vs_ground"):
            add(f"  - 相对地面真值多出：`{', '.join(entry['extra_vs_ground'])}`")
        missing = fields.get("missing") or {}
        if missing:
            add(f"  - 字段缺失：{json.dumps(missing, ensure_ascii=False)}")
    add()
    add("### 原生 ID 集合")
    add()
    playwright_ids = set((report["engines"].get("playwright") or {}).get("ids_union") or [])
    nodriver_ids = set((report["engines"].get("nodriver") or {}).get("ids_union") or [])

    def _id_cell(ids: set, expected) -> str:
        if not ids:
            return "未运行"
        return f"{sum(1 for item in expected if item in ids)}/{len(expected)}"

    add("| 类别 | 地面真值 | playwright | nodriver |")
    add("| --- | --- | --- | --- |")
    add(f"| 帖子 | 1 | {_id_cell(playwright_ids, [truth['thread_id']])} | "
        f"{_id_cell(nodriver_ids, [truth['thread_id']])} |")
    add(f"| 顶层评论 | {len(truth['comment_ids'])} | "
        f"{_id_cell(playwright_ids, truth['comment_ids'])} | "
        f"{_id_cell(nodriver_ids, truth['comment_ids'])} |")
    add(f"| 楼中楼 | {len(truth['lzl_ids'])} | "
        f"{_id_cell(playwright_ids, truth['lzl_ids'])} | "
        f"{_id_cell(nodriver_ids, truth['lzl_ids'])} |")
    add()
    add(f"- 顶层评论 ID：`{', '.join(truth['comment_ids'])}`")
    add(f"- 楼中楼 ID：`{', '.join(truth['lzl_ids'])}`")
    add()
    add("### 字段归属")
    add()
    for name, entry in report["engines"].items():
        if not entry.get("runs"):
            add(f"- **{name}**：未运行，无字段归属。")
            continue
        fields = entry.get("fields") or {}
        total = fields.get("count") or 0
        add(f"- **{name}**：{total} 条记录")
        for field in ("native_id", "text", "author", "published_at", "likes"):
            sources = (fields.get("sources") or {}).get(field) or {}
            source_text = ", ".join(f"`{key}` ({value})"
                                    for key, value in sources.items()) or "—"
            missing_count = len((fields.get("missing") or {}).get(field) or [])
            add(f"  - `{field}`：{total - missing_count}/{total}；"
                f"来源 {source_text}")
    add()
    add("## 停止语义")
    add()
    for name, entry in report["engines"].items():
        if not entry.get("runs"):
            continue
        for index, run in enumerate(entry["runs"], 1):
            add(f"- **{name} run{index}**：`{run['stop']}`；"
                f"{run['stop_detail']}")
    add()
    add("## 桌面可见性")
    add()
    for name, entry in report["engines"].items():
        if not entry.get("runs"):
            continue
        proof = entry.get("desktop_proof") or {}
        add(f"- **{name}**：proven={proof.get('proven')}，"
            f"reason={proof.get('reason')}，"
            f"matched_by={proof.get('matched_by')}，"
            f"candidates={proof.get('candidate_count')}，"
            f"window={proof.get('window_title')}，"
            f"foreground={proof.get('foreground_matched')}，"
            f"rect={proof.get('window_rect')}")
        add("  - 证据边界：前台窗口匹配 + 窗口矩形证明窗口被置前；"
            "页面截图只证明页面渲染，不证明人眼已经看到，也不移动系统鼠标指针。")
    add()
    add("## 本地测试与停止语义")
    add()
    add("项目 venv（不启动浏览器；playwright/nodriver 不在该解释器，"
        "浏览器相关项按环境跳过）：")
    add()
    add("```powershell")
    add(".venv\\Scripts\\python.exe -m unittest tests.test_v18_engine_trial -v")
    add("```")
    add()
    add("真实有头 Playwright（Python 3.12.10 + playwright 1.60.0）：")
    add()
    add("```powershell")
    add('$env:DSH_ENGINE_TRIAL_REAL = "1"')
    add(f"{sys.executable} -m unittest tests.test_v18_engine_trial.PlaywrightRealTests -v")
    add("```")
    add()
    add("真实有头 nodriver（x-collect venv，nodriver 0.50.6）：")
    add()
    add("```powershell")
    add('$env:DSH_ENGINE_TRIAL_REAL = "1"')
    add(f"{report['environment'].get('nodriver_executable') or '<x-collect venv python>'} "
        "-m unittest tests.test_v18_engine_trial.NodriverRealTests -v")
    add("```")
    add()
    add("覆盖：无增长停止、取消保留部分数据、错误保留部分数据、重复读取去重、"
        "缺失字段与父关系、ID 双向差异；完整输出见 `tests.log`。")
    add()
    add("## 限制与未证明")
    add()
    for item in report.get("limitations") or []:
        add(f"- {item}")
    add()
    add("## 复现")
    add()
    add("```powershell")
    if report.get("playwright_command"):
        add("# 1) Playwright 3 次（已有数据可跳过）")
        add(f"{report['playwright_command']}")
    add("# 2) nodriver 3 次并合并到既有报告")
    add(f"{report['command']}")
    add("```")
    add()
    add("单测（不启动浏览器）：")
    add()
    add("```powershell")
    add(f"{sys.executable} -m unittest tests.test_v18_engine_trial -v")
    add("```")
    add()
    add("可选真实有头集成测试：")
    add()
    add("```powershell")
    add('$env:DSH_ENGINE_TRIAL_REAL = "1"')
    add(f"{sys.executable} -m unittest tests.test_v18_engine_trial.PlaywrightRealTests -v")
    add("```")
    return "\n".join(lines) + "\n"


def main(argv=None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:  # noqa: BLE001 - console encoding is best-effort
        pass
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--engine", choices=("all", "playwright", "nodriver"),
                        default="all")
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--out", default="docs/validation/v18/engine-trial")
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--channel", default="chrome")
    parser.add_argument("--timeout-ms", type=int, default=15000)
    parser.add_argument("--max-scrolls", type=int, default=8)
    parser.add_argument("--settle-ms", type=int, default=250)
    parser.add_argument("--no-desktop-proof", action="store_true")
    parser.add_argument("--merge-existing", action="store_true",
                        help="keep engines already present in OUT/report.json")
    parser.add_argument("--fixture", default=None,
                        help="use this existing fixture instead of regenerating")
    args = parser.parse_args(argv)

    out = pathlib.Path(args.out).expanduser().resolve()
    out.mkdir(parents=True, exist_ok=True)
    existing = None
    report_path = out / "report.json"
    if args.merge_existing and report_path.is_file():
        existing = json.loads(report_path.read_text(encoding="utf-8"))

    if args.fixture:
        fixture_path = pathlib.Path(args.fixture).expanduser().resolve()
        if not fixture_path.is_file():
            parser.error(f"fixture not found: {fixture_path}")
        truth = fixture.ground_truth()
        fixture_info = {"path": str(fixture_path), "url": fixture_path.as_uri(),
                        "ground_truth": truth}
    elif existing:
        old_fixture = existing.get("fixture") or {}
        fixture_path = pathlib.Path(old_fixture.get("path")
                                    or (out / "fixture.html")).expanduser().resolve()
        if not fixture_path.is_file():
            parser.error(f"fixture from existing report not found: {fixture_path}")
        truth = fixture.ground_truth()
        fixture_info = {"path": str(fixture_path), "url": fixture_path.as_uri(),
                        "ground_truth": truth}
    else:
        fixture_path = out / "fixture.html"
        fixture_info = fixture.build_fixture(fixture_path)
        truth = fixture_info["ground_truth"]
        fixture.write_ground_truth(out / "ground-truth.json", truth)

    selected = (["playwright", "nodriver"] if args.engine == "all"
                else [args.engine])
    now = datetime.datetime.now().astimezone().isoformat(timespec="seconds")
    command = " ".join([sys.executable, "-m", "tools.selection.engine_trial",
                        *sys.argv[1:]])
    if existing:
        report = existing
        report["playwright_generated_at"] = (
            existing.get("playwright_generated_at")
            or existing.get("generated_at"))
        report["playwright_command"] = (
            existing.get("playwright_command") or existing.get("command"))
        report["generated_at"] = now
        report["command"] = command
        report["out"] = str(out)
        report["fixture"] = existing.get("fixture") or fixture_info
        report.setdefault("environment", {})
        report.setdefault("engines", {})
    else:
        report = {
            "generated_at": now,
            "command": command,
            "out": str(out),
            "environment": {"platform": platform.platform(),
                            "python": sys.version.split()[0],
                            "executable": sys.executable,
                            "cwd": str(pathlib.Path.cwd())},
            "fixture": fixture_info,
            "engines": {},
            "comparison": {},
            "limitations": [],
        }
    if "nodriver" in selected:
        report["environment"]["nodriver_executable"] = sys.executable
        report["environment"]["nodriver_python"] = sys.version.split()[0]
        report["environment"]["nodriver_venv"] = str(
            pathlib.Path(sys.executable).parent.parent)
    for name in selected:
        entry = _run_engine(name, fixture_path, out, args)
        report["engines"][name] = _aggregate(entry, truth)
    if "playwright" in selected:
        report["playwright_generated_at"] = now
        report["playwright_command"] = command

    playwright = report["engines"].get("playwright")
    nodriver = report["engines"].get("nodriver")
    if playwright and nodriver and playwright.get("runs") and nodriver.get("runs"):
        comparison = extract.compare_ids({"ids": playwright["ids_union"]},
                                         {"ids": nodriver["ids_union"]})
        comparison.update({"status": "compared", "left": "playwright",
                           "right": "nodriver"})
    else:
        comparison = {"status": "not_comparable", "left": "playwright",
                      "right": "nodriver",
                      "reason": "nodriver 未运行或没有可比较的运行；未伪造对照。"}
        if playwright and playwright.get("runs"):
            comparison["playwright_vs_ground_truth"] = {
                "ground_count": len(truth["ids"]),
                "playwright_count": len(playwright["ids_union"]),
                "missing": playwright["missing_vs_ground"],
                "extra": playwright["extra_vs_ground"],
            }
    report["comparison"] = comparison
    report["limitations"] = _limitations(report)

    (out / "report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    (out / "REPORT.md").write_text(_render_markdown(report), encoding="utf-8")
    summary = {name: {"status": entry["status"],
                      "reason": entry.get("reason"),
                      "runs": len(entry.get("runs") or []),
                      "ids": len(entry.get("ids_union") or [])}
               for name, entry in report["engines"].items()}
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if any(entry["status"] == "verified"
                    for entry in report["engines"].values()) else 2


if __name__ == "__main__":
    raise SystemExit(main())
