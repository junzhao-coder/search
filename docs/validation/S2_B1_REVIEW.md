# S2-B1 独立执行复核报告（D 角色）

> 任务：`task-a91929c70f461e73bed28efcfd8810df`（revision 2，计划 v2）；执行者 `session-c1428bc7-460b-511e-aaea-719314ba8cbc`（D 独立质量槽位）。
> 被复核对象：S2-B1（`task-829baf5647ea6a6f87a0ec5729abd80a`，策划者已静态验收）与 [S2_RUNTIME.md](<../design/S2_RUNTIME.md>) §7 状态表。
> 复核方式：**在隔离环境实际运行**。独立库 `tests/acceptance/_tmp/b1_check.db`、独立端口 `5051`、解释器 `.venv\Scripts\python.exe`（Python 3.12.14 / SQLite 3.53.1 / Flask 3.1.3）；只读使用 `app/**`，未写 `instance/`、未改 `app/**`、`tests/core|storage|api`、`docs/design`。
> 交付物：本报告 + [run_b1_checks.py](<../../tests/acceptance/run_b1_checks.py>)（可复跑，27 项断言）+ 夹具 `tests/acceptance/fixtures/contract_4_7_positive.csv`（由已冻结契约 §4.7 抽取）+ 日志 `tests/acceptance/_tmp/b1_check_log.txt`。
> **并发声明**：B2（`task-82bf9fe8e1b233d133b1b9c2b0a62318`）在本复核期间同步改写 `app/**`。本报告所有结论对应运行瞬间的代码树；每次运行前后均记录哈希并在运行内校验一致性（见 §5）。

## 1. 结论摘要

- **未发现可归因于 B1 交付的缺陷**：27 项断言中 **24 项复现成功**，1 项只记录现状（discover），2 项失败**全部**由并发 B2 造成（B1 的 `schema_version=1` 已变为 `2`）。
- B1 声明的核心闭环**逐条复现成功**：§4.7 38 列正例导入计数 1/1/2/1/10、身份 `u:xianyu:…` 与 `n:<渠道>:1001`、同键重导不增殖、改摘录 `version_added`+`superseded_by`、异 URL 同文 `dup_suspect`、`mode=validate` 零写入、`atomic` 坏行零业务写入且批次与行级原因保留、GBK→`400 encoding_error`、`client_ref` 同载荷重放/异载荷 409/重启后仍重放、重启数据保留、四门槛 `unverified`+`pending`、`run_record.source_id` 为 NULL。
- **§7 存在 3 处越界“通过”**：`S2-03`（情景 `contribution=190`/`complete=true`）、`S2-12`（读情景）、`S2-13`（逐组尝试核验门槛）在 B1 时点不可证，属 B2 范围；`S2-11` 的四情形与 `S2-31` 的错误码本轮未覆盖。建议在 B2 落盘矩阵时按“部分通过/未执行”填写（B2 任务已含该要求）。
- **一处证据文件可读性问题**：`instance/http_e2e.txt` 的中文为**采集端编码错误产物**，并非存储或接口问题（§4-P2-4 给出反解证明）。
- **一处流程问题**：B2 在 D 开始复核前已覆盖 `app/core/importer.py` 等文件，B1 交付版本**已无法按字节复现**；建议后续把 D 复核安排在任何写任务之前，或先冻结只读快照（§4-P2-1）。

## 2. 复核环境与隔离

| 项 | 值 |
| --- | --- |
| 解释器 | `.venv\Scripts\python.exe` → Python 3.12.14；SQLite 3.53.1；Flask 3.1.3 |
| 环境变量 | `APP_DB_PATH=tests/acceptance/_tmp/b1_check.db`、`APP_PORT=5051`、`APP_HOST=127.0.0.1`、`PYTHONUTF8=1` |
| 隔离 | 未触碰 `instance/app.db`（业务库仍在 B 处）；未占用 B 的 5000；每次运行前删除并重建独立库 |
| 夹具 | 直接从 [CONTRACT.md §4.7](<../design/CONTRACT.md>) 抽取正例（38 列，实测表头 38 列、数据行 38 字段、单行） |
| 观测手段 | HTTP（urllib，无代理）+ `sqlite3` 只读查询 + `netstat` + 子进程退出码；不导入应用模块 |
| 运行次数 | 4 次（前 2 次为脚本自身判定缺陷修复，第 3 次补 §7-S2-07 断言，第 4 次为最终结果，见 §5） |

## 3. 逐项复现结果

判定口径：**复现成功**＝与 B1 声明一致且由本轮观测支持；**失败**＝与声明不一致；**无法复现**＝因并发/前置变化不能按原值核验；**未覆盖**＝本轮未测。

| 步骤（派发编号） | 复跑命令 / 请求（最终运行） | 决定性输出 | 判定 |
| --- | --- | --- | --- |
| 1 哈希记录 | 脚本 STEP1/STEP17；`Get-FileHash tests/acceptance/_tmp/app_hashes_repro_start.txt` | 起始与结束各 36 个文件哈希；**运行期间变化 0 个** | 复现成功 |
| 2 健康检查 | `GET /api/health` | `200 {"ok":true,"schema_version":2,"stage":"S2-B2"}` | **无法复现（B1 原值 `schema_version=1`；B2 已应用 0002）** |
| 2 监听地址 | `netstat -ano \| findstr :5051` | `TCP 127.0.0.1:5051 … LISTENING`（本地地址列仅 127.0.0.1） | 复现成功 |
| 3 迁移与表 | `sqlite3 b1_check.db "SELECT * FROM schema_migrations"` | `[1 0001_init.sql, 2 0002_draft_feedback.sql]`，共 **15** 表 | 失败（15 表＝B1 的 13 表 + B2 的 `draft`/`feedback`） |
| 3 B1 表子集 | 同上 | B1 声称的 13 张表**全部存在**，缺失 0，新增 `draft`/`feedback` | 复现成功（子集性质） |
| 3 来源种子 | `SELECT name,access_mode FROM source` | 4 行 `manual_import/xianyu/xiaohongshu/bilibili`，`access_mode='manual_import'` | 复现成功 |
| 4 正例导入 | `POST /api/imports?format=csv&mode=atomic`（§4.7） | `201`，`created=1`；五表 `candidate 1 / demand_signal 1 / evidence 2 / supply_offer 1 / cost_item 10` | 复现成功 |
| 4 身份键 | `GET /api/candidates` | `total=1`，`identity_key=u:xianyu:https://example.com/demand/1001` | 复现成功 |
| 4 成本形状 | `SELECT role,basis,minutes,hourly_rate_minor,supply_offer_id FROM cost_item` | 10 条，角色含 `sale_price/platform_fee/payment_fee/acquisition/refund_reserve/procurement/manual_labor/other`；`manual_labor: minutes=15, hourly_rate_minor=3000`；`cost_supply_url→supply_offer_id` 关联 10/10 | 复现成功 |
| 4 门槛与派生 | `GET /api/candidates/{id}` | 四门槛均 `unverified`；`derived_status=pending`；`reason=derived:pending\|gates_incomplete` | 复现成功 |
| 运行记录 | `SELECT COUNT(*) FROM run_record WHERE source_id IS NULL` | `1`（无 `''` 悬空外键） | 复现成功 |
| 5 同文件重导 | 再次 `POST`（同字节） | `201`，`duplicate_skipped=1, created=0`；五表计数不变 | 复现成功 |
| 5 改摘录重导 | 改 `demand_excerpt` 后 `POST` | `counts.version_added=1`；`demand_signal` 两行，旧行 `superseded_by` 指向新行 | 复现成功 |
| 6 validate | `POST …&mode=validate` | `200 {"mode":"validate","saved":false}`；五表 + `import_batch`/`run_record`/`idempotency_key` **前后完全一致** | 复现成功 |
| 7 atomic 坏行 | 同表头 1 好行 + 1 坏行（`sale_price=-9.90`） | `422 status=rejected`；业务表不变；`import_batch +1`；行级原因 `V22` | 复现成功 |
| 8 GBK | 以 GBK 字节 `POST format=csv` | `400 {"code":"encoding_error"}`；业务表与批次/运行零写入 | 复现成功 |
| 9 跨渠道同 ID | 两文件 `demand_native_id=1001`（xianyu / bilibili） | `201/201`；候选身份 `n:xianyu:1001`、`n:bilibili:1001` | 复现成功 |
| 9 异 URL 同文 | 两条同文不同 `demand_url` | `suspect_review=1`；`review_item(kind=dup_suspect, blocking=0, status=open)` | 复现成功 |
| §7-S2-07 补充 | 无需求组行重导；同需求行仅增 `payment_fee_bp` | 候选 `identity_key=t:2dcdd1ca…` 复用不增殖；后者批次逐记录为 `('duplicate_skipped','demand_signal')` + `('created','cost_item')`，该候选成本项 `sale_price,payment_fee` | 复现成功 |
| 10 幂等 | 同 `client_ref` 同载荷两次；异载荷一次 | `201` → `200 deduplicated=true`（同一 `batch_id`）；异载荷 `409 conflict` | 复现成功 |
| 11 重启 | `terminate` → 重启 → 读列表 | 重启后 `health 200`、五表计数与重启前一致、`total=8` | 复现成功 |
| 10 重启后重放 | 重启后再次同键同载荷 | `200 deduplicated=true`（幂等记录已持久化） | 复现成功 |
| 12 依赖边界 | `requirements.txt`；`app/**` 导入扫描 | 有效依赖仅 `flask==3.1.3`；第三方导入集合 `{flask}` | 复现成功 |
| 13 编码核验 | 库内查询 + `GET` 原始字节 + `instance/http_e2e.txt` 反解 | 见 §4-P2-4 | 复现成功（结论：存储与接口正确，证据文件为采集端乱码） |
| 14 T-07 | `python -m unittest discover -s tests` | B1 交付瞬间（19:37:3x）：`exit=5 / NO TESTS RAN`，`tests/__init__.py` 不存在；B2 于 19:37:39 补齐后：`exit=0 / Ran 64 tests / OK` | 只记录现状（B1 记录为 `ImportError`，文本与本次不同，结论一致） |
| 补充：B1 用例 | 逐文件运行 B1 交付的 4 个测试文件 | `test_money 7 OK`、`test_identity 7 OK`、`test_migrations 4 OK`、`test_import_api 27 OK`，各自 `exit=0`（合计 45，与 §4 声明一致） | 复现成功 |
| 15 结论行 | — | 27 项：**PASS 24 / MANUAL 1 / FAIL 2**；脚本 `exit=1` 由 2 项 FAIL 触发 | — |

## 4. 发现（按严重度）

**未见可归因于 B1 的 P0/P1 缺陷。** 以下为 P2/P3。

### P2-1 · B1 交付版本已不可按字节复现（并发写入早于独立复核）

- 事实：B2 在本复核开始前已改写 `app/core/importer.py`（mtime 19:36:36，本轮首次运行 19:36:41）、`app/api/routes.py`（19:37:06），并新增 `candidates/drafts/feedback/reviews/scenario.py`（19:35–19:36）。B1 交付时的 `importer.py`（`DEED68E5…`）与 `routes.py`（`1BC6AC83…`）在本轮任何一次运行中都不再同时存在。
- 影响：本轮验证的是**当前树行为与 B1 声明一致**，不能宣称“B1 二进制/源码版本本身被独立复现”。核心导入链路恰是 B2 改过的文件，因此该差异不可忽略。
- 最小修法（流程，不需改代码）：对需要独立复现的实现任务，D 复核应排在其后任一写任务之前，或由 B 先产出只读快照（如 `tests/acceptance/_snapshot/`），复核以快照为对象。若接受现状，则应在 S2_B1_REVIEW 与台账中明确“B1 以自身证据 + D 行为级复现共同支持”。

### P2-2 · `S2_RUNTIME §7` 三处“通过”超出 B1 可证范围

| 行 | §7 声明 | 本轮结论 |
| --- | --- | --- |
| [S2-03](<../design/S2_RUNTIME.md>) | 通过 | 存储层全部复现成功；但该行期望含 `情景 contribution=190、complete=true`，属 B2（B2 现已实现 `/scenario`，本轮观测 `200`），B1 时点不可证 → 应为“部分通过” |
| S2-12 | 通过 | 期望“导入后读情景”（A/B/C 三行成本情形）；B1 无情景端点 → 应为“部分通过（读情景属 B2）” |
| S2-13 | 通过 | 期望“逐组尝试核验其余门槛”需 `POST /candidates/{id}/gates/{gate}`（B2）；B1 只能证“未核验→`unverified`/`pending`”这一半 → 应为“部分通过” |
| S2-11 | 通过 | 四情形（①②V10、③URL-only 不造证据、④`observed_at` warning）本轮只覆盖存储形状，未逐项复现；§7 依据的是 B1 自测 → 建议保持“通过”但注明依据来源为 B1 用例 |

- 最小修法：B2 落盘 `ACCEPTANCE.md` 时把 S2-03/12/13 标“部分通过”并注明 B2 部分；`S2_RUNTIME §7` 同步（该文件属 B 范围，我不代改）。

### P2-3 · `/api/health` 的 `stage` 为硬编码，复核期间出现滞后

- 事实：19:36:41 观测 `schema_version=2` 但 `stage="S2-B1"`；19:37:27 起为 `stage="S2-B2"`。即阶段标签与实际 schema 版本无绑定，落盘任务换阶段时会短暂自相矛盾（或长期滞后）。
- 最小修法：`stage` 由 `schema_migrations` 最新版本或单一常量派生，或直接移除该字段；顺带 `model_configured` 一类状态同样只保留真实已接入事实。

### P2-4 · `instance/http_e2e.txt` 的中文为采集端编码产物（非存储/接口问题）

- 反解证明（本轮实测）：文件中的 `"category":"æ¨¡æ\x9d¿"` 经 `latin-1 → utf-8` 得 `模板`；`"title":"ç¤ºä¾\x8b-å\x91¨ä¼\x9açºªè¦\x81æ¨¡æ\x9d¿å\x8c\x85"` 得 `示例-周会纪要模板包`。文件本身是合法 UTF-8（`utf-8-sig` 解码成功，0 个 `?`、0 个 U+FFFD），即“先把服务端 UTF-8 字节按 Windows-1252/Latin-1 解码，再按 UTF-8 写出”。
- 对照证据：库内 `candidate.title` 与 `demand_signal.excerpt` 与契约样例完全一致；本轮抓取的**原始 HTTP 字节**含正确 UTF-8 `示例-周会纪要模板包`（`tests/acceptance/_tmp/b1_check_http_raw.json`）。
- 结论：**存储层与 HTTP 层无编码缺陷**；`http_e2e.txt` 作为审计证据会误导（若只读该文件会以为存储乱码）。
- 最小修法：`instance/_e2e.ps1` 采集端显式指定 UTF-8（如 `[Console]::OutputEncoding=[Text.Encoding]::UTF8`、`Get-Content -Encoding utf8`、或改用 Python 采集），并在文件头注明采集编码。属 B 范围，我不代改。

### P3（低风险/记录类）

- **P3-1** `/api/health` 返回绝对路径 `db_path`；本机单用户应用风险低，但截图/外发会带出用户目录，建议评估是否保留。
- **P3-2** 批次行级 `counts` 与 `import_row_result` 记录级动作层级不同：S2-07 的第二批 `counts={"created":1}`，而逐记录含 `('duplicate_skipped','demand_signal')`。矩阵 S2-07 的“需求侧 `duplicate_skipped`”应在**记录级**核对，建议在 §7/矩阵注明层级，避免后续复核误判。
- **P3-3** T-07 证据文本不一致：B1 记录 `ImportError: Start directory is not importable`，本轮在同一缺失状态下得到 `exit=5 / NO TESTS RAN`；两者都表示 discover 不可用，但原文不同，建议保留双方原文而不改写成同一句。B2 已补 `tests/__init__.py`，当前 `discover` 可运行（`Ran 64 tests / OK`，含 B2 新增 19 项）。
- **P3-4** `cost_item.supply_offer_id` 关联 10/10（含费率与人工行），而契约对该字段的表述是“采购/单价类成本**建议**填写”。行为比文字更宽，属可接受实现，但建议契约或 §8 差异清单补一句，避免后续按“仅采购类”写断言。

## 5. 哈希与并发说明（可复核）

- 起始快照（B1 之后、本轮运行之前）：`tests/acceptance/_tmp/app_hashes_start.txt`，例：`app/core/importer.py DEED68E5…`、`app/api/routes.py 1BC6AC83…`、`app/core/state.py 01BCCFAC…`、`requirements.txt 0AF19A0F…`。
- 最终运行（第 4 次，起始 19:39:2x）：`app_hashes_repro_start.txt` / `app_hashes_repro_end.txt`，**运行期间变化 0 个**（运行内自洽）；关键项：`importer.py C2BF667B…`、`routes.py 98C01EF5…`、`state.py 01BCCFAC…`、`storage/db.py FF8A534C…`、`migrations/0001_init.sql 9B049373…`、`migrations/0002_draft_feedback.sql 34D70A1D…`、`requirements.txt 0AF19A0F…`。
- 期间漂移（第 2 次运行检出 1 个，B2 在写 `tests/api/test_gates_scenario.py`；第 1、3、4 次运行期间 0 个）。文档侧：`docs/design/{ACCEPTANCE,CONTRACT,S2_RUNTIME}.md` 在本轮全程未变（哈希 `68c3840f…`、`d6724fd2…`、`5309b6ca…`）。
- 结论：§3 的 FAIL 两项（`schema_version`、表数）与 §7 的 S2-03/12/13 判断均为**时间点差异**，不是 B1 的运行时错误。

## 6. 复跑指引

```powershell
Set-Location 'D:\桌面\two'
$env:PYTHONUTF8='1'; $env:PYTHONIOENCODING='utf-8'
# 独立复核（独立库 + 端口 5051；每次运行会重建 tests/acceptance/_tmp/b1_check.db）
& .\.venv\Scripts\python.exe -X utf8 tests\acceptance\run_b1_checks.py; "exit=$LASTEXITCODE"
# 逐项日志与原始字节
Get-Content tests\acceptance\_tmp\b1_check_log.txt -Encoding utf8
# B1 声明的 45 项用例（逐文件）
foreach ($f in 'tests\core\test_money.py','tests\core\test_identity.py','tests\storage\test_migrations.py','tests\api\test_import_api.py') { & .\.venv\Scripts\python.exe -X utf8 $f; "exit=$LASTEXITCODE ($f)" }
# discover（B2 补齐 __init__.py 后可用）
& .\.venv\Scripts\python.exe -m unittest discover -s tests
```

退出码对照：最终运行 `exit=1`（由 §3 两项并发型 FAIL 触发）；B1 四个测试文件 `exit=0`；`discover` 当前 `exit=0`。

## 7. 限制与未覆盖

1. **不可按字节复现 B1**（P2-1）；本报告是“当前树行为 + B1 声明一致性”复核，不等于对 B1 交付快照的完整核验。
2. 未覆盖：`POST /api/candidates/{id}/merge` 的跨界 422、`real/synthetic` 同键隔离的完整往返、`S2-11` 四情形逐项、`S2-31` 错误码矩阵（本轮仅覆盖 `400/404/409/422` 各一部分）、`S2-23` 顺序复现（B1 有自测）等；这些或属 B2 范围，或未列入本次派发步骤。
3. 未做：浏览器/界面（无 UI，页面仍 501）、异机访问（无第二台主机）、并发与压力、备份恢复、真实渠道数据；均未声明通过。
4. 端口 5000 未验证（避免与 B 冲突），仅验证 5051 上的 `127.0.0.1` 绑定。
5. 本轮未写 `instance/`、未改 `app/**`、`tests/core|storage|api`、`docs/design`；新增文件仅 `tests/acceptance/run_b1_checks.py`、`tests/acceptance/fixtures/contract_4_7_positive.csv`、`tests/acceptance/_tmp/*`（库、日志、哈希、原始 HTTP 字节）与本报告。
6. 技能：本任务匹配 `ponytail`；执行者角色无 `skill` 加载工具，按已知磁盘路径读取 `SKILL.md`（120 行，full）并遵循（最小脚本、stdlib/urllib/sqlite3、不引依赖、不改被测量对象）。无下级代理。
7. 提交仅进入待验收；是否要求 B 修复 P2-2/P2-3/P2-4 与是否重排复核顺序，由策划者决定。
