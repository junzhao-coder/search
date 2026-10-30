# V9 工具清单与平台状态（进度梳理）

> 任务 `task-0acc32d7c2751dae6f23c8eb28f2d255`（V9-14）。2026-10-26 22:16–22:25 UTC+8。
> **零执行**：本文件只做文档同步——未运行任何脚本/测试、未发网络请求、未开浏览器、未写业务库/CSV/CONTRACT、未装依赖。
> 事实来源：`tools/selection/*`（只读）、`docs/validation/v9/{platform-matrix/MATRIX.md, account-safety/ACCOUNT-SAFETY.md, xhs-migration/MIGRATION.md, xhs-readiness/*}`、隔离库 `tools/selection/runtime/xhs_first.sqlite3`。
> 本文件不宣称任何平台“已接入可用”；所有“实测”均标注次数/时间/限制。

## 1. 采集 / 入口清单

| 入口 | 路径 | 运行方式（解释器） | 依赖 | 当前状态 | 证据 |
| --- | --- | --- | --- | --- | --- |
| selection CLI | `tools/selection/cli.py` | `python -m tools.selection.cli --db <db> run bilibili --bvid BV... --budget 3`；子命令 `run/import/stats/categorize/cards/ledger/round` | stdlib（argparse/sqlite3/urllib） | 可用（本地）；默认 DB `tools/selection/runtime/selection.sqlite3` | `tools/selection/cli.py:13-14,21-72` |
| B站适配器 | `tools/selection/bilibili.py` | 经 CLI `run bilibili`，或模块函数 `collect_round(...)` | stdlib；公开 web API | **可读，但仅第一页**；评论必须 `sort=2`（`bilibili.py:171-172,322`）；子回复仅入口 1 条 | V9-1b/3/7a 报告与 raw |
| V2EX 适配器 | `tools/selection/v2ex.py` | 模块 `fetch(node_name="notion", limit=5, raw_dir=...)`；无 CLI 子命令 | stdlib（urllib/json）；UA `two-selection/1.0`；无 token | 实测：**2 次请求 200**、47,035B、5 条 | `docs/validation/v9/…/REPORT_V9_8A.md`；`evidence/github-v2ex/request_log.json` |
| GitHub 适配器 | `tools/selection/github.py` | 模块 `fetch(query=..., limit=3, raw_dir=...)`；无 CLI 子命令 | stdlib；公开 REST；无 token | 实测：**1 次请求 200**、16,135B、3 条 | 同上 |
| 新源入链 | `tools/selection/new_sources.py` | `ingest(signals, db_path)` → upsert + categorize + cards | 依赖 db/models/categories/triage | 可用（隔离库） | `new_sources.py:11-28` |
| 闲鱼导入 | `tools/selection/xianyu.py` | `python -m tools.selection.cli --db <db> import xianyu --path <jsonl>` | stdlib；读用户导出 JSONL | 仅导入 **20 条**；卖家文案，价格仅参考 | `xianyu.py:91`；`tools/platform-login/data/xianyu_items.jsonl` |
| 人工贴一条 | `tools/selection/manual.py` + `/leads/manual` | Web 表单（`tools/workbench`），或 `manual.add(conn, platform, url/text/title)` | Flask 工作台；stdlib 解析 | 可用（本地）；native_id 优先 URL 正则，否则 content_hash 前 16 位 | `manual.py`；`REPORT_V9_8B.md` |
| triage 规则 | `tools/selection/triage.py` | `triage.classify(text)`；`store/backfill/refresh` | stdlib | 规则版 `triage-v1`；词表 `求/问/求助/有没有/想要/推荐/怎么做/不会` 与 `出/售/接单/…`；**已知假阳性** | `triage.py:8-32`；`REPORT_V9_12_REWORK.md` |
| 小红书骨架 | `tools/selection/xiaohongshu.py` | 模块：`search_url/parse_results/parse_note_fields/classify_note/check_profile` | stdlib（HTMLParser/sqlite3） | 解析与 doctor 可用；**需求能力未验证** | `REPORT_V9_9/10/11/12_REWORK.md` |
| 小红书可见探针 | `tools/selection/xhs_probe.py` | `python tools/selection/xhs_probe.py --mode home|note|batch|search`（需可见 Chrome + 专用 profile） | stdlib + **nodriver（仅 x-collect venv 有）** | 工具存在；**已封存，不再请求**；search exit 已修为 stopped→5/6、records 空→6 | `xhs_probe.py::exit_code`；`REPORT_V9_12_REWORK.md` |
| 迁移采集器（另一会话） | `tools/selection/vendor_xhs/xhs_collect.py` | `C:\Users\19183\.dsh\tools\x-collect\venv\Scripts\python.exe tools\selection\vendor_xhs\xhs_collect.py --profile "D:\桌面\破甲\profiles\xhs_main" --db "D:\桌面\破甲\crawler\xhs_data.db" <cmd>` | stdlib + `websockets.sync.client`（仅 x-collect venv 有） | **已迁移、未测试、未接本项目流程**（39,281B，SHA `bbab14db…df09`，与源一致） | `docs/validation/v9/xhs-migration/MIGRATION.md` |
| 工作台 `/leads` | `tools/workbench/app.py`、`views_leads.py` | `python tools/workbench/app.py`（本地 Flask） | Flask（已装） | 可用（本地只读+人工导入+改判） | `REPORT_V9_8B.md` |
| 隔离库（小红书） | `tools/selection/runtime/xhs_first.sqlite3` | sqlite3 | — | `signals=12`、`review=12`、`categories=0`、`cards=0` | 本轮只读计数 |

## 2. 平台状态表

| 平台 | 实测等级 | 当前结论 | 限制 / 备注 |
| --- | --- | --- | --- |
| **B站** | **实测（V9-1b/3/7a）** | 公开 web API 可读视频/评论第一页 | **仅第一页**；评论必须 `sort=2`（缺 sort 会假阴性）；第 2 页 `pn=2` 为空；子回复仅入口 1 条；无登录/cookie 实测；高频/并发未测 |
| **V2EX** | **实测（V9-8a）** | 公开 API 可读 node 话题 | 2 次请求 200、47,035B、5 条；未验证翻页/限速/403/429 真实路径 |
| **GitHub** | **实测（V9-8a）** | 公开 REST search 可读 issue | 1 次请求 200、16,135B、3 条；未验证 60/h 耗尽、翻页 |
| **X（Twitter）** | **实测-只读小样本（V9-6）** | x-collect 专用 profile，doctor exit0，search 5 条 | 仅 5 条；handle `@Johnsmathjyjp` 与旧 `@xluchuan` 不一致，**归属待用户确认**；不等于全站可采 |
| **小红书** | **测量不合格 / 需求能力未验证** | 可见搜索/点击详情技术上可打开，但 V9-12 超限（17 loads > 8）+ 两次 risk 后继续 + triage 假阳性，**结论作废** | **已封存，不再请求**；`headless verify` 曾 `login_required` 属无头误判，不能据此重登；违规记录见 `ACCOUNT-SAFETY.md` §3.4.1；建议冷却 ≥24h 或换号（用户决定）；迁移代码 `vendor_xhs` **未测试** |
| **闲鱼** | **样本观察（20 条导入）** | 仅用户导出 20 条，价格/想要可作参考 | 卖家文案，非真实成交；`price` 多为 ¥1、`wants` 是兴趣代理；平台入口/实时未验证；无评论字段 |
| **贴吧** | **实测-失败（V9-1c-A）** | 公开 GET 返回 **403 百度安全验证** | 1/5 请求即停；未取得 tid/分页；需用户浏览器/登录或导入 |
| **微博** | **实测-登录墙（A 任务）** | `m.weibo.cn` 被重定向访客墙 | 首请求即停；正文/评论/翻页未验证；需登录态 |
| **知乎** | **未接** | 仅入口模板 | 预期需登录；无本项目 raw |
| **抖音** | **未接** | 仅入口模板 | 预期需登录/cookie/风控；无本项目 raw |
| （附）淘宝/天猫、京东、拼多多 | 未接 | 仅入口模板 | 需登录/风控；自动采集未批准 |

## 3. 已知坑与运行前置条件

1. **`vendor_xhs` 默认路径错位（必须显式传参）**
   脚本 `ROOT` 由文件位置推导，迁移后默认 `--profile`/`--db` 指向 `tools/selection/{profiles,crawler}`（不存在）。
   所有命令必须写成（顶层参数在子命令前）：
   ```powershell
   C:\Users\19183\.dsh\tools\x-collect\venv\Scripts\python.exe `
     tools\selection\vendor_xhs\xhs_collect.py `
     --profile "D:\桌面\破甲\profiles\xhs_main" `
     --db "D:\桌面\破甲\crawler\xhs_data.db" check
   ```
   **没有 `fill` 子命令**（源文件头部 docstring 过时）；真实子命令只有 `login/check/explore/note/user/search/stats`。
2. **`websockets` 只在 x-collect venv**
   系统 `Python312` 无 `websockets`；`C:\Users\19183\.dsh\tools\xhs-collect\venv` 不存在。必须用 `C:\Users\19183\.dsh\tools\x-collect\venv\Scripts\python.exe`。
3. **小红书 300012 与 risk 记录**
   源会话记录“推荐流 50 条 + 300012 限制”属**另一会话**，本项目未复核；本项目 V9-12 出现 `risk_marker:captcha`/`dom` 后仍继续 5 次，属违规（`ACCOUNT-SAFETY.md` §3.4.1）。当前会话状态未知，**不要直接重跑**。
4. **`headless verify` 误判**
   小红书 headless `verify` 曾返回 `login_required`，而可见窗口 `online=valid`（25 条 explore 链接）；不能据 headless 结果判定会话失效或要求用户重登。
5. **小红书直开 URL 缺 token**
   `https://www.xiaohongshu.com/explore/<id>` 直开会“页面不见了”；必须从首页点击卡片（带 `xsec_token`/referer），或保留点击后的完整 URL。query 只记键名/长度，不落 token。
6. **triage 是规则版、有假阳性**
   `有没有/不会用` 等字面匹配会把泛问/找同伴算 demand；V9-12 规则 38.9% → 人工复核 11.1%（选品口径 5.6%）。不要把规则命中当需求结论。
7. **`selection` 默认 DB 与隔离库不同**
   CLI 默认 `tools/selection/runtime/selection.sqlite3`；小红书用 `runtime/xhs_first.sqlite3`；小红书迁移器用原 `D:\桌面\破甲\crawler\xhs_data.db`。三者不要混用。
8. **零执行声明**
   本文件撰写期间未运行任何脚本/测试、未发请求、未开浏览器；文中命令为“可复制执行”的用法说明，不代表已在本项目验证。

## 4. 本项目未验证项（明确）

- `vendor_xhs/xhs_collect.py` 的**可运行性、CLI 行为、登录态、300012 限流表现**（用户要求只迁移不测试）。
- 小红书**需求能力**（V9-12 测量不合格）；小红书**登录要求**（最后一次可见搜索未触发登录墙，但整体不合格）。
- 小红书**翻页/评论/搜索联想/长期稳定性**；`likes/publish_time` 真实字段（V9-11 批内值不可信）。
- B站第 2 页/楼中楼全量；V2EX/GitHub 翻页与限速边界；X 全站与 handle 归属；闲鱼实时入口；贴吧/微博/知乎/抖音/淘宝/京东/拼多多 均未接。
- 工作台 `/leads` 的浏览器实机截图与多用户并发未验证。
