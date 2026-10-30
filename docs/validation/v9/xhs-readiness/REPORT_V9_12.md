# V9-12 报告（已作废）：小红书搜索 A/B 意图词对照

> **本文件结论不成立**：7 次运行合计 17 加载（>8）、两次 risk 后继续 5 次、exit 全 0 不可信、38.9% 为规则假阳性。以 `REPORT_V9_12_REWORK.md` 为准。

> 任务 `task-ad9414765e2ea1eda7a50e3bacffa5e8`（rev2，计划 v9）。2026-10-26 11:33–11:55 UTC+8。
> 用户已明确放行；可见窗口；6 词 × 前 3 条；**7 次页面加载**（首页1 + 6词，≤8）；词间 15s；未登录/扫码/点赞/评论/关注/翻页；未装依赖、未写业务库。

## 1. search

| 项 | 值 |
| --- | --- |
| cmd | `C:\Users\19183\.dsh\tools\x-collect\venv\Scripts\python.exe -X utf8 tools/selection/xhs_probe.py --mode search --per-word 3 --interval 15` |
| cwd | `D:\桌面\two` |
| start_utc / exit | **2026-10-26T03:50:35Z** / **exit=0** |
| 页面加载 | **7**（首页 1 + 六词各 1；≤8） |
| 登录墙/风控 | **未触发**；6 词均 `state=ok` |
| 搜索结果 | 每词 3 条，共 **18** 条；URL 形如 `/search_result?keyword=<词>&type=2`（实际 query 仅记键名/长度） |
| raw | `raw/search_A_1..3_...html`、`search_B_1..3_...html`，逐词脱敏骨架 |

- 前两次直接 URL 尝试出现过脚本 captcha 误报/导航超时；最终采用“首页 + 搜索页 CDP 导航”成功，最终运行 7 加载。误报已修（用 visible text，不把隐藏 DOM/脚本当登录墙）。

## 2. hitrate

| 组 | 词 | demand | promo | noise | 有效 | demand 命中率 |
| --- | --- | --- | --- | --- | --- | --- |
| A | 求推荐 / 有没有 / 怎么做 | **4** | 0 | 5 | 9 | **44.4%** |
| B | 不会用 / 怎么选 / 踩坑 | **3** | 0 | 6 | 9 | **33.3%** |
| 合计 | 6 词 | **7** | 0 | 11 | 18 | **38.9%** |

- 逐词：A 求推荐 1/3、有没有 3/3、怎么做 0/3；B 不会用 3/3、怎么选 0/3、踩坑 0/3。
- triage 为规则判定，不是人工确认；命中率只是本批 18 条观察。

## 3. quotes（demand 原话，≤60 字、无昵称/手机号）

| 查询词 | 原话 |
| --- | --- |
| 求推荐 | 求大神们推荐自用好吃稳定的API |
| 有没有 | 急急急，开学有没有法友？ |
| 有没有 | 500SR电子离合有没有必要上 |

## 4. db

- 隔离库 `tools/selection/runtime/xhs_first.sqlite3`。
- demand 写入上限 6；本批原写出 7，已修正 `_ingest_search(limit=6)` 并删除第 7 条，**最终本批 6 条**；`batch_id=xhs-search-2026-10-26T03:50:35Z`。
- 当前总计：`signals=12`（含前序 6）、`review=12`、`categories=0`、`cards=0`。
- `run_categorize`: signals=6（本批）、review=6、skipped=6、categories=0；`make_cards`: cards=0。
- categories=0 原因：6 条 title/quote 均有值（不是字段不足）；搜索词结果偏生活/社交/泛咨询，未命中现有品类文本规则；6 条样本不足以证明“规则过窄”；不为了出品类改词/挑主题。
- 未写默认 selection 库/业务库。

## 5. conclusion（平台定位）

**小红书：限搜索但样本不足。** 可见搜索可作为小规模需求线索来源（A 44.4%、B 33.3% demand），但仅 6 词/18 条/单页，且 triage 为规则判定、品类 0，不能作为主需求源；首页 feed 不作为需求源。

**是否需登录：否（本次可见搜索无需登录）。** 之前 headless verify 的 `login_required` 不据此判重登；未执行登录/扫码。

已写入 `docs/validation/v9/platform-matrix/MATRIX.md` 的小红书行；本报告结论段即 xhs-readiness 结论。

## 6. tests

| suite | 结果 | 日志 |
| --- | --- | --- |
| selection（基线 90 + search/search_result 6） | **96 tests OK** | `tools/selection/logs/tests_selection_v912.log` exit0 |
| workbench | **218 tests OK** | `tools/selection/logs/workbench_v912.log` exit0 |
| 项目全套（基线 424 + 6） | **430 tests OK** | `tools/selection/logs/project_v912.log` exit0 |

- 新增 search 分组/URL、解析与 triage、登录墙即停、原话/入库、search exit、`/search_result` 结构测试。
- cwd `D:\桌面\two`；UTC 03:50–03:54（本地 11:50–11:54）。

## 7. limits

- 6 词 × 3 条、单页；未验证第二页/翻页/评论/搜索联想/长期稳定性。
- 可见搜索一次；未做第二组独立重复；命中率仅本批 18 条。
- raw 为脱敏 DOM 骨架，不是完整 HTML；query 仅键名/长度。
- stderr 有 nodriver/asyncio ResourceWarning 收尾警告，不影响 exit/stdout。
- triage 是规则版，存在语义误判；未人工复核每条。
