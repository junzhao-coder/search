# V9-8a 实现报告：V2EX/GitHub 公开只读适配器 + 需求/营销分流 + 入信号库出卡

> 任务 `task-602b87f7d5ae8365cb4b107495864e5e`（rev4，计划 v9）；范围 `tools/selection`、`tests`。
> 2026-10-25 21:48–21:57 UTC+8。未登录、未装依赖、未加代理、未写业务库/workflow/CSV；未动 merge/undo/split/判重/NAV。

## 1. V2EX（真实只读）

- 模块 `tools/selection/v2ex.py`：公开 `/api/topics/show.json?node_name=notion`；UA `two-selection/1.0`；无 token；分页不请求。
- 真实请求（总 2 次，≤3；间隔 >3s）：
  - 第 1 次 13:49:49Z：raw `v2ex_topics_notion_20261025T134939Z.json` 47,035B、5 条、sha `b2c683c68deb…`；工具调用在捕获返回前被中断，**status 未记录**（raw 可解析，未伪造为 200）。
  - 第 2 次 13:55:49Z：**status 200**、47,035B、5 条、11.125s、同 sha；raw `v2ex_topics_notion_20261025T135538Z.json`。
- 解析：`native_id` topic id、`url`、`title`、`quote` 正文去 HTML + 截断 200 字；`lang` heuristic；`origin_kind='real'`；raw_sha256/content_hash 用 models。
- 缺字段/坏 JSON：`parse_topics` 跳缺 id/title 行；`fetch` 返回 `invalid_json/parse_error`，不抛。

## 2. GitHub（真实只读）

- 模块 `tools/selection/github.py`：公开 `/search/issues?q=...type:issue&per_page=3`；UA 同上；无 token；只 search，不 clone/下载。
- 真实请求 1 次（≤3）：13:55:18Z，**200**、16,135B、3 条、9.907s，raw `github_issues_20261025T135508Z.json` sha `6d85730d6cb8…`。
- 解析：`native_id` 用 `owner/repo#number`（避免跨仓库 issue 号冲突）、`url`、`title`、`quote` body 截断 200；缺 items/异常 → `github_payload_missing_items`/invalid_json。
- 总真实请求 **3**（V2EX 2 + GitHub 1）≤10；无 403/429。

请求日志：`tools/selection/evidence/github-v2ex/request_log.json`（URL/status/bytes/items/elapsed/UTC/raw/sha；V2EX 第一次 status 如实 null）。

## 3. 需求/营销分流（规则版，只分流）

- `tools/selection/triage.py`：`classify(text)->demand|promo|noise`；词表按验收（求/问/求助/有没有/想要/推荐/怎么做/不会；出/售/接单/代做/推广/优惠/私我/加v/自营），并加营销强词（自动发货/秒发/拍下/网盘/标价/发货/素材/合集/源文件/价格）。
- **营销优先**：任一拍到营销词即 promo，避免“想要/问”把商品文案算 demand。
- 统计（最终规则）：
  - 23 条（B站 3 + 闲鱼 20）：**promo 19 / demand 2 / noise 2**；
  - X 5 条：**noise 5**（英文，不在中文词表）；
  - 新 8 条（V2EX5+GitHub3）：**demand 3 / noise 4 / promo 1**。
- 混淆样例（如实列）：
  - V2EX `<edu.kg notion 笔记还能登录吗>` 因“出”字判 promo（误报）；
  - B站评论含“不会/问”判 demand，但它们是评论口吻，不是明确需求（偏宽）；
  - GitHub 3 条英文 issue 全 noise；X 5 条英文全 noise（词表只覆盖中文）。
- 规则版、只作分流，不作为需求结论；不影响 identity_key/判重。
- **持久化位置**：独立表 `signal_triage(signal_id PK, label, demand_hits_json, promo_hits_json, rule_version, at)`（schema v7），不改 `signals` 字段；`triage.store()` 与 `triage.backfill()` 供适配器/人工导入复用。新 8 条已回填 8 行（demand3/promo1/noise4，rule_version=`triage-v1`）；`xianyu.import_file` 也已复用同一函数。

## 4. 串链路（隔离库）

- `tools/selection/new_sources.py`：`ingest(signals, db)` → upsert → `run_categorize` → `make_cards`。
- 隔离库 `tools/selection/runtime/github_v2ex.sqlite3`：schema v7、8 new（v2ex5/github3）、0 errors；`signal_triage` 8 行；`categorize`: new=5/update=3/review=0/categories=5；cards=5。
- `views_leads.load_lead_data`：`signals=8`、`by_platform={github:3,v2ex:5}`、categories=5、cards=5；`/leads` 会显示两平台。

## 5. 测试 / 真实 exit

| suite | 结果 | 日志 |
| --- | --- | --- |
| selection（基线 51 + 4 新） | **55 tests OK** | `tools/selection/logs/tests_selection_v98a.log` exit 0 |
| workbench | **218 tests OK** | `tools/selection/logs/workbench_v98a.log` exit 0 |
| 项目全套（基线 385 + 4 新） | **389 tests OK** | `tools/selection/logs/project_v98a.log` exit 0 |

- 新增 `tests/test_selection_sources.py` 4 项：V2EX 解析/缺字段/坏 JSON、GitHub 解析/429 停、triage 三类、端到端桩 ingest→categorize→cards。
- cwd `D:\桌面\two`；UTC 21:56–21:58。

## 6. 未验证 / 限制

- 只各 1–2 次请求，未验证翻页、限速边界、GitHub 60/h 耗尽、403/429 真实路径（仅桩）。
- 未验证 X/小红书等登录源；triage 仅中文词表，英文/中英混合会噪声化；规则版有误判（见 §3）。
- quote 只是摘要，不能当全文/证据原文；`raw` 中可能含公开用户名，未做账号隐私清洗。
- 未接 CLI/UI；新源通过模块 ingest 入隔离库，未并入默认 selection 库。
- 未验证真实数据的需求质量；8 条样本极小。
