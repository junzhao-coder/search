# S2-D 整链路独立验收报告

> **本文件为同一份持续维护的报告**：以下"§0 当前结论（新快照 fix1）"为最新覆盖层；其后的 §1–§10 保留为历史分层记录（旧快照 `s2d_20261009_231628` 时代的观察与失败留档），两者**按快照与日期区分**，不得互相冒充。

## §0 当前结论（新快照 `s2d_20261013_fix1`）

**状态：D 侧独立核验已完成并可复跑；验收结论待策划者判定，本报告不预写 accept。**

- 冻结对象：快照 `s2d_20261013_fix1`（55 文件），**树哈希 `3a0d32836d548982be2b0a9f17d5f7c53824182ebb2a4e28f942620910e0dee6`**，清单 `s2d_20261013_fix1.manifest.sha256` = **`e1578b05650f5d2418267d8947dac61a15e5c5ee036924b83cc33ea77f73d1bc`**，来源探针 `…\_snapshots\s2d_20261013_fix1\app\__init__.py`（`PYTHONDONTWRITEBYTECODE=1`）。旧快照（`s2d_20261009_231628`，树 `1808beb518a38e7699a61eae39ebc3425d34db997bfc107fbac76475f3d369ea`、清单 `2c8b76b80bd20a7ca68f4de39da4ea743b326b779b7ae6c332bc94e83807e783`）仅作历史与对照。完整 64 位哈希与原件编码转换记录见 `tests/acceptance/_tmp/attempts/attempt_20261013_223040_w4s3/final_evidence_hashes.json`。

**本轮六组独立证据（可复跑；均只停自启 PID、只用隔离库；下列链接均可从本报告直接打开）**

| 组 | 命令（工作区根、`PYTHONUTF8=1`、`.venv\Scripts\python.exe -X utf8`） | 结果 / 退出码 | 证据（相对本报告的 Markdown 链接） |
| --- | --- | --- | --- |
| 新树完整链 | `$env:S2D_SNAPSHOT_ID='s2d_20261013_fix1'; tests\acceptance\run_s2_acceptance.py` | **47/47 PASS，exit=0，0 INFO** | 脚本 [run_s2_acceptance.py](<../../tests/acceptance/run_s2_acceptance.py>)；日志 [fix1_chain_utf8.txt](<../../tests/acceptance/_tmp/fix1_chain_utf8.txt>)（原件 UTF-16 sha256 `23935956e3fd98c35f18d1118bf02c90fb09ca80847ba51298babd21cb8d7333`）；清单 [s2d_20261013_fix1.manifest.sha256](<../../tests/acceptance/_snapshots/s2d_20261013_fix1.manifest.sha256>)；[final_evidence_hashes.json](<../../tests/acceptance/_tmp/attempts/attempt_20261013_223040_w4s3/final_evidence_hashes.json>) |
| legacy NULL | `tests\acceptance\run_legacy_null_case.py` | **8/8 PASS，exit=0** | 脚本 [run_legacy_null_case.py](<../../tests/acceptance/run_legacy_null_case.py>)；结果 [legacy_cases.json](<../../tests/acceptance/_tmp/attempts/legacy_20261013_220452_vi1e/legacy_cases.json>)；[legacy_review_rows.json](<../../tests/acceptance/_tmp/attempts/legacy_20261013_220452_vi1e/legacy_review_rows.json>) |
| 版本/`*`/failed | `tests\acceptance\run_version_cases.py` | **8/8 PASS，exit=0** | 脚本 [run_version_cases.py](<../../tests/acceptance/run_version_cases.py>)；结果 [version_cases.json](<../../tests/acceptance/_tmp/attempts/version_20261013_224557_c9l8/version_cases.json>)；[version_materialized_c1.json](<../../tests/acceptance/_tmp/attempts/version_20261013_224557_c9l8/version_materialized_c1.json>)、[version_materialized_c3.json](<../../tests/acceptance/_tmp/attempts/version_20261013_224557_c9l8/version_materialized_c3.json>) |
| 业务边界（三档/全量改绑/重放/短 TTL） | `tests\acceptance\run_boundary_cases.py` | **10/10 PASS，exit=0** | 脚本 [run_boundary_cases.py](<../../tests/acceptance/run_boundary_cases.py>)；结果 [boundary_cases.json](<../../tests/acceptance/_tmp/attempts/boundary_20261013_215030_yj9t/boundary_cases.json>)；[boundary_supersedes_exact.json](<../../tests/acceptance/_tmp/attempts/boundary_20261013_215030_yj9t/boundary_supersedes_exact.json>)（覆盖：三档采购部分转 B 其余 A → G3 422 且缺口含 `platform_fee`/`manual_labor` 等 6 项；全部活跃行改绑按实际待改 7 行增长且每组唯一活跃绑 B、非 B 活跃=0；重放无增殖；用户 API 重核+队列处理 → testable；省略 `evidence_id` 短 TTL 精确 min） |
| 三入口 CLI | `tests\acceptance\run_guard_negatives.py` | **18/18 PASS** | 脚本 [run_guard_negatives.py](<../../tests/acceptance/run_guard_negatives.py>)；结果 [guard_cases.json](<../../tests/acceptance/_tmp/attempts/guard_20261013_202340_zft9/guard_cases.json>)（含 MIRROR-HASH 真 digest 比较 + 篡改自证、独占 bind 端口探测） |
| 新树 A→B 切换探针 | `$env:S2D_SNAPSHOT_ID='s2d_20261013_fix1'; tests\acceptance\run_s2_attempt.py` | **23/23 PASS** | 脚本 [run_s2_attempt.py](<../../tests/acceptance/run_s2_attempt.py>)；结果 [attempt_log.txt](<../../tests/acceptance/_tmp/attempts/attempt_20261013_194043_ga1q/attempt_log.txt>) |

要点：完整链覆盖导入/去重（新打印只比五个业务表）/版本/跨渠道与起点隔离/atomic 422 零写/GBK 400/validate 零写/幂等 201·200·409/四门槛反例与 `testable`/情景 190·800·−200·未知·一次性·周期/草稿与无发送端点/反馈预测快照·退款关联·结算幂等·`manual_time`/降级 GET 零写+recompute 幂等+`dismiss` 不恢复/页面 P1–P4·404·转义·未知0·分页分池/restart 一致；`SELF-COVERAGE` 36 个必测 ID 全覆盖、0 INFO；退款 JS 桥接为真实 HTTP **201**、金额 **990 保留**、关联字段经适配。

**退款落库与关联（只读复现，未改库、未重复交易）**：`tests/acceptance/_tmp/attempts/attempt_20261013_223040_w4s3/final_evidence_hashes.json` 记录新增行 `fb_c2e11031fcc64e19`：`candidate=c_ca60bbefdcd74bb1`、`data_origin=synthetic`、`order_ref=D-ORDER-1`、`related_feedback_id=fb_6ccf2c2f4ded4e9b`、`amount_minor=990`、`refund_state=pending`、`actual_minutes/actual_hourly_rate_minor/actual_net_per_order_minor/actual_complete` 全 NULL；成交行 `fb_6ccf2c2f4ded4e9b` `predicted_net_per_order_minor=190`、`actual_*` NULL（预测快照不可改）。JS captured payload 键 `[kind, amount_minor, related_feedback_id, refund_state]`，桥接保留 `amount_minor`、仅替换关联 ID/`order_ref`/`refund_state`（**非原样字节提交**）。

**本轮更正（保留历史原文，不删除）**

- **默认省略 `evidence_id` 的短 TTL**：`None+30d` 分支**已实测**（历史 §10 中"None 分支未测"的表述**作废**，原文保留）；**本轮新增的是「SQL 关联夹具」补测**——用 SQL 仅把新货源的 `license_evidence_id` 绑定到一条 **`expires_at` 非 None（+2 日）** 的证据（脚本内明标 `MARKER: SQL 夹具（仅时间/关联，不改业务值）`），实测核验行 `expires_at` **精确等于该证据有效期（`min(证据, verified_at+30d)`）**；该夹具**仅用于时间分支验证，不用于改绑/恢复**。
- **45 项的成因**：历史 §10 曾记为"合理分支差异"，**更正为：桥接检查（`UI-JS-refund-realHTTP`）曾被放进 Node 失败分支导致漏检，故 45/45 并不代表资金路径通过**；该错误日志与失败 JSON 原件保留（`guard_20261013_200527_7qms` 等），修后为 47/47（补回漏检 ID + 新增 `SELF-COVERAGE`）。
- **跨候选 supersedes 解释**：早期 `boundary_supersedes_rows.json` 混入另一候选 `c_b3294a4642bc4fd9`/货源 `sp_addf634174d94a03`（跨候选测试原始行），其"no-op"结论**作废**；已按目标候选 `c_f749b0c979ee4f7b`/货源 B `sp_4cfe646b936c40ca` 重新只读取证 `boundary_20261013_215030_yj9t/boundary_supersedes_exact.json`：10 条父子边角色/口径/值/周期完全一致、父货源 A → 子货源 B（旧误 JSON 保留并附作废说明）。
- **legacy 复核行归属**：实测 `legacy_review_rows.json` 两行 `blocking=1`、`ref_gate` 分别为 `cost`（kind `cost_changed`，status `resolved_recheck`）与 `platform_policy`（kind `license_changed`，status `dismissed`），`ref_type=candidate`、`ref_id=c_6001aa640ef447ea`；并含 `system_rule` 降级行 `cost/platform_policy, expired, seq=2`。

**必要矩阵（S2 关键项：实现者自测 vs 本轮 D 独立结果 vs 未测）**

| S2 关键项 | 实现者自测（B/C 声明） | 本轮 D 独立结果 + 证据 | 未测 |
| --- | --- | --- | --- |
| 导入/去重/版本/起点隔离/atomic/编码/validate/幂等 | B 执行**全量镜像回归（含各模块）**共 124 项；其中 **57 项为 `gates_scenario` 子集**（两者均未由 D 复核其代码） | `S2-03/04/05/06/08/09/10/27/29` 均 PASS（[attempt_20261013_223040_w4s3](<../../tests/acceptance/_tmp/attempts/attempt_20261013_223040_w4s3/acceptance_log.txt>)） | 真实渠道数据 |
| 四门槛准入与反例 | B 自测含 G1–G4 反例 | G1 卖家宣传 422、G2 三反例 422、G3 无依据 422 与补说明通过、G4 版本 422/`*` 200、G3/G4 异货源·跨候选 422、`testable` 达成 | 平台规则真实抓取 |
| 货源切换后核验归属（原 P1） | B 修复后自测通过 | 新树 `B-no-impersonation` **PASS**（切 B 后 `derived=stale`、cost/platform expired）；legacy NULL case 8/8 | 多货源并发切换压测 |
| 情景数值/未知口径/周期 | B 自测含 190/800/负值/一次性/周期 | `S2-03/12/19/20/21` 均 PASS | 真实成交分布 |
| 草稿/反馈/预测快照 | B/C 自测 | `S2-24/22/25` PASS；退款 990 真实 HTTP 201 且 `actual_*` NULL | 真实付款渠道 |
| 界面（HTTP/HTML/Node 模拟） | C 侧既有证据：HTTP/HTML 页面检查 + **Node 15 用例模拟**（不编独立总数；其代码未由 D 复核） | 独立结果：P1–P4·404·转义·未知0·分页分池 PASS；Node 镜像 [ui_behavior.mjs](<../../tests/ui/ui_behavior.mjs>) 运行结果 `15 passed / 0 failed`（见 [fix1_chain_utf8.txt](<../../tests/acceptance/_tmp/fix1_chain_utf8.txt>)） | **真实浏览器**（无工具）：点击/键盘/焦点/剪贴板/截图 |
| 重启一致性/零写/复核 | B 自测 | `S2-32`、GET 零写、recompute 幂等、resolve/dismiss 不回生 均 PASS | 异机、并发、备份/恢复 |

**未覆盖与限制（不补造）**

1. 无浏览器工具：界面结论来自真实 HTTP + 服务端渲染 HTML + **Node 模拟 DOM**，**≠ 真实浏览器**。
2. 未测：异机访问、并发/压力、备份与恢复、真实渠道数据；未实现端点（merge／每日摘要／流水线／备份）与后续阶段能力（采集/排序/预算/实际利润核算）不给通过结论。
3. **旧 run 无 before 全量哈希**：`_tmp/s2d_20261009_231628/*` 只能给本次 after 值与"时间戳未变"的历史基线说明，未事后补造 before。
4. 旧快照目录实际含 148 个文件：其中早期误在快照内生成的 `_tmp` 副产物**不在 55 条清单内**（清单校验按 `_tmp` 排除规则仍一致），已在保护哈希 JSON 标注。
5. **纯数字 TTL 未测**：本轮未做"把最新 gate 的 `expiresAt` 置为过去"的自库时间夹具小 case；单货号数字估算不作为准入门槛证据。
6. 结论仅对应上文所列快照与哈希；实时树若再变需重新冻结复核。旧快照 P1 属**历史观察**，新树结论仅由本轮新树证据支撑。


> 任务：`task-4631f618b16f77f7c849e1764a123a3c`（revision 2，计划 v2）；执行者 `session-c1428bc7-460b-511e-aaea-719314ba8cbc`（D 独立质量槽位）。
> 依赖（均已由策划者验收）：B 边界回归 `task-639aeee9a8f8365c4b4e06c0dfcc4cc7`、C 界面 `task-fcc9b07e7a52315315ff2874b45f0143`。
> 方式：**在固定快照上从干净库实际运行**。独立库 `tests/acceptance/_tmp/<run>/app.db`、独立端口 `5095`、解释器 `.venv\Scripts\python.exe`（Python 3.12.14 / SQLite 3.53.1 / Flask 3.1.3）；只读应用代码；未写 `instance/`、未改 `app/**`、`tests/core|storage|api|ui`、`docs/design`、根台账。
> 交付：本报告 + [freeze_snapshot.py](<../../tests/acceptance/freeze_snapshot.py>)（快照冻结/哈希校验）+ [run_s2_acceptance.py](<../../tests/acceptance/run_s2_acceptance.py>)（46 项独立检查，可复跑）。

## 1. 结论摘要

- **历史观察（当时检查范围）**：在冻结快照 + 干净隔离库上，原 46 项检查全部通过（exit=0，日志不变）。该结论**只覆盖当时那批检查项**——导入/去重/版本/隔离/原子/validate/幂等、四门槛准入与反例、情景数值、草稿、反馈快照、失效降级、页面 200/404 与转义、重启一致性；**当时“未发现 P0/P1/P2 阻断项”亦仅指该范围**。
- **当前结论（rev9/rev12 补证后）**：已证 **P1 阻断**——货源切换后旧 G3/G4 冒充当前核验，候选仍为 `testable`（§10，实测两轮复现）；**S2 未收口**，须待该 P1 修复或经策划者明确接受。3 条 P3 观察与“未覆盖清单”见 §6、§8。
- 关键边界单独验证：G1 卖家宣传 422、G2 三反例（`resale=no`／许可 `unknown`／未抽检）422、G3 无依据 422 且补说明后通过、G4 版本不符 422、G3 传非当前 G2 货源 422、`unknown ≠ 0`、一次性正额 `net=NULL`+缺口、月度/季度/年度正额与 0 的不同判定。
- 实现者自测（B+C）在快照内实测 `Ran 108 tests … OK`（exit=0），**仅作对照，不作为本验收依据**（§5）。
- **浏览器证据分级**：本会话无浏览器工具，界面结论来自真实 HTTP + 服务端渲染 HTML + Node 模拟 DOM（C 的 `ui_behavior.mjs`，在快照内实跑 exit=0）+ JS 捕获载荷经真实 HTTP 落库 201；**未做真实浏览器 DOM/点击/键盘/截图/剪贴板**（§5）。
- **S2 收口判断（供策划者决定）**：本快照已支持 S2 声明的最小闭环，“本地闭环可用”的结论有实测支撑；未实现项（merge/摘要/流水线/备份）与浏览器项按计划留待后续阶段（§7）。**但 rev9 补证发现“货源切换后旧 G3/G4 仍冒充当前核验”的阻断项（§10），在该项解决或明确接受前，不建议 S2 收口。**

## 2. 冻结、隔离与来源证据

| 项 | 值 |
| --- | --- |
| run_id | `s2d_20261009_231628` |
| 快照目录 | `tests/acceptance/_snapshots/s2d_20261009_231628/`（55 个文件） |
| 逐文件清单 | `tests/acceptance/_snapshots/s2d_20261009_231628.manifest.sha256`（另存 `_tmp/<run>/snapshot_manifest.sha256`） |
| **树哈希** | 实时树复制前 `84f4a47c…d5ae` = 复制后 `84f4a47c…d5ae` = 快照 `84f4a47c…d5ae` = **验收后再次实测的实时树**（55 文件一致；说明期间 B/C 未再写入、我也未改树） |
| `app.__file__` | `…\_snapshots\s2d_20261009_231628\app\__init__.py`（探针 `python -c "import app;print(app.__file__)"`，cwd=快照，`PYTHONPATH` 置空，exit=0）→ **实际导入来自快照** |
| 关键文件哈希 | `app/api/routes.py 9744a4dc…`、`app/core/scenario.py 60633b48…`、`app/core/gates.py 6d733607…`、`app/static/ui.js acd8cbbf…`、`app/templates/home.html dbc1d4d6…` |
| 业务库 | `instance/app.db` SHA256 = `e073f828…4eb85`（与 B 边界回归记录的运行前后值一致，**未被本任务写入**）；未创建 wal/shm |
| 端口/进程 | 仅监听 `127.0.0.1:5095`；结束时端口残留监听 = `none`；只停止自己拉起的 PID |
| 产物 | `_tmp/<run>/{acceptance_log.txt,snapshot_summary.json,snapshot_manifest.sha256,app.db,server.log}` |

## 3. 独立检查结果（46 项，全部 PASS）

| 组 | 检查（id → 决定性输出） |
| --- | --- |
| 基础 | `S2-01-health` `{"ok":true,"schema_version":2,"time":…}`（键集合恰为三键，`stage`/`db_path` 已移除）；`S2-01-netstat` `127.0.0.1:5095`；`S2-01-schema` migrations `[1,2]`、15 表；`S2-01-seeds` 4 来源 × `manual_import`；`UI-empty0` 空库 `total=0, items=[]` |
| 导入 | `S2-03-csv38` 201、`created=1`、五表 `1/1/2/1/10`；`S2-03-json-alias` 201、`sale_price_minor=1990` 落库；`S2-04-reimport` 201、`duplicate_skipped=1`、五表不变；`S2-06-version` `version_added=1`、`superseded=1`；`S2-05-crosschannel` `n:xianyu:1001`+`n:bilibili:1001` 两候选；`S2-08-origin-isolation` real/synthetic 同键=2 候选；`S2-09-atomic` 422、业务零写、批次+1、行级 `V22`；`S2-10-gbk` 400 `encoding_error` 零写；`S2-29-validate` 200 `saved=false` 且业务/批次/运行/幂等零写；`S2-27-idempotency` 201→200(`deduplicated`)→409(`conflict`) |
| 四门槛 | `S2-13-initial-pending` 四门槛 `unverified`+`pending`；`S2-14-g1-counterexample` 卖家宣传→422（`signal_kind`）；`S2-14-g2-counterexamples` `resale=no`／`commercial=unknown`／`sample_checked=none` 三次 422；`S2-B-G2默认关联` 省略 `evidence_id` → 200 且核验行回填条款证据、`verified_by=user`；`S2-17-testable` G1/G2/G3/G4 顺序通过（G3 先 422 后补说明通过）→ `derived=testable`；`S2-B-异货源G3G4` 传非当前 G2 货源→422 |
| 情景 | `S2-03-scenario190`（改动前）`contribution=190, net=190, complete=true, unknown=[]`；`S2-20-scenario800` 逐单采购 200 → `contribution=800, net=800`；`S2-19-negative` 逐单成本 1200 → `contribution=-200`；`S2-12-unknown-not-zero` 缺支付费 → `contribution=null` 且 `unknown_components` 列出（不按 0）；`S2-21-onetime-gap` 一次性 2000 → `net=null, gap=2000`；`S2-21-recurring` 月度正→`null`、月度 0→有净值、季度正→`null` 且月额 `null`、季度 0/年度 0→有净值、年度正→`null` |
| 草稿/反馈/边界 | `S2-24-draft` template 201（正文含 `【待…】/未核验` 占位）、`model_assisted` 422、`PATCH` 定稿 200、`/send` 404；`S2-22-no-purchase` `/api/payments`、`/api/purchase` 404；`S2-25-feedback` sale 201（`predicted` 快照）、裸退款 422、关联退款 201、结算幂等 200/200、改预测 422 `invalid_field`、`manual_time` 201 与更正 200、`actual_net/actual_complete` 保持 NULL |
| 降级/重启 | `S2-15-downgrade` 连续 GET 零写、失效→`demand=expired`+`stale`、`recompute` 幂等、`dismiss` 后仍 `stale`；`S2-32-restart` 重启后计数一致、状态与预测快照一致 |
| UI（HTTP/HTML） | `UI-P1/P2/P3/P4` `/`、`/opportunity/<id>`、`/import`、`/ops` 均 200；`UI-404` 不存在候选 404；`UI-escape` 服务端渲染页无原样 `<script>`/`<img`、含 `&lt;script&gt;`；`UI-unknown0` 详情页区分“未知/0”；`UI-sources` “人工导入”三态；`UI-paging-pool` 分页 `page=2&page_size=2` 与 `status=stale` 过滤；`UI-JS-node-harness` Node 模拟 DOM exit=0 |
| JS 载荷落库 | `UI-JS-refund-realHTTP`：Node 捕获 `{"kind":"refund","amount_minor":990,"related_feedback_id":"fb_1","refund_state":"settled"}` → 绑定真实成交后经 **真实 HTTP** `POST /api/candidates/{id}/feedback` → **201** |

命令与退出码：`freeze_snapshot.py` exit=0；`run_s2_acceptance.py` exit=0（46/46，日志 `_tmp/<run>/acceptance_log.txt`）；快照内 `python -X utf8 -m unittest discover -s tests -t .` exit=0；快照内 `node tests/ui/ui_behavior.mjs` exit=0。

## 4. 与实现者自测分列

| 来源 | 结果 | 定位 |
| --- | --- | --- |
| D 独立检查（本报告） | **46/46 PASS**（冻结快照、独立库、独立端口、独立脚本） | 验收依据 |
| B+C 自测（快照内复跑） | `Ran 108 tests … OK` exit=0（含 B2 41 项边界、C 界面用例） | **仅作对照**，不作为通过依据 |
| B 的 `instance/_e2e.ps1` | 未由本任务复跑（属实现者证据），其运行目录/守卫证据已由策划者在 §9 记录 | 参考 |

## 5. 证据分级（HTTP/HTML/Node 模拟 vs 真实浏览器）

- **真实执行**：HTTP 请求/响应（urllib，含状态码与 JSON）、SQLite 直查、服务端渲染 HTML 文本、`.venv` 解释器、快照内进程生命周期。
- **Node 模拟 DOM**：C 的 `tests/ui/ui_behavior.mjs` 在 `vm` + 最小 DOM + fetch 模拟下运行 `app/static/ui.js`（快照内实跑 exit=0），覆盖：空态可见/撤销（`pool-empty`、`feedback-empty`↔表格 0→1）、三态来源渲染、分页复位、预览“未保存不得显示通过”（`import-saved-note` 保持 hidden）、错误态撤 loading、多实例互不干扰、捕获 refund/sale 载荷到 `tests/ui/_tmp/feedback_payloads.json`。
- **未做（本会话无浏览器工具，如实声明）**：真实浏览器 DOM、点击/键盘/焦点/剪贴板、常用窗口尺寸、截图；异机访问（无第二台主机）；并发与压力；备份/恢复流程。
- 因此：**“界面可用”只按 HTTP+HTML+Node 模拟结论成立**，`S2-34`/`S6-06` 所需的浏览器级检查仍为缺口（缺工具，按约定留空，不记为通过）。

## 6. 发现（按严重度）

**P0/P1/P2：无。** 未发现阻断 S2 收口的问题。以下为 P3 观察（不阻断，供 B/C 酌情处理）：

- **P3-1 成本取代的两条路径必须分列（已按前后行快照实测）**：
  - `recurring` 行**缺 `period`** 的取代 → **422 且零写**：`app/core/costs.py` 的 `_spec` 校验（155 行）在 `UPDATE is_active=0`（163 行）之前，实测前后 `cost_item` 行完全一致（21 项批次中 `ASSERT-recurring-422-zerowrite` PASS，details 指向 `period`）。
  - `per_order` 行**只改 `assumption_note`** → **200 且旧行停用、新行值列 NULL**：实测 `is_active` 0→1 切换、新行 `value_kind/money_minor` 均为 NULL（值从此变未知），故随后情景 `contribution=null`（`ASSERT-per_order-note-only` PASS）。这是“只改说明必须重发数值”的真实语义，不是 422。
- **P3-2 首页候选区为 JS 渲染**：候选标题不在服务端 HTML（`/` 仅 3.2 KB 含空态占位），转义保证由 `textContent` 渲染路径承担；服务端渲染的机会页已实测转义正确。建议在界面验收清单中固定“转义断言应打服务端渲染页或 DOM 断言”，避免误判。
- **P3-3 历史证据文件已由 B 重生成（原“仍乱码”表述作废）**：`instance/http_e2e.txt` 现为 **REGENERATED** 版本（首行 `2026-10-09T19:52:55`，2–4 行标注采集端已按 UTF-8 解码并引本报告 P2-4 作为诊断来源），实测 sha256 `6140a4c6538ff7c7bf6d1094384ed1d976899a82e7a65c3135b310de6f7db9a6`、9100 B、mtime `2026-10-09 19:53:08`、不含 `æ` 模式且含正确中文；两文件各自哈希为 —— `instance/http_e2e.txt 6140a4c6…`、`instance/app.db e073f828cf0f30d6206361bba3a729826be096be3308f5a5dc204406dae4eb85`（241664 B）。本报告早前版本把 app.db 的哈希误标为该证据文件，已更正；旧观测保留为历史。

## 7. 未覆盖与阶段缺口（不假报完成）

- 未实现端点（计划内，属后续阶段）：`#13 merge`、`#19 每日摘要`、`#22 流水线`、`#25 备份` → 保持 404/未实现；来源自动采集与 `search_coverage`、货源匹配与排序权重、S5 运行费用台账与预算保护、S5 实际利润核算均未实现，本报告未对其给出通过结论。
- 未执行检查：`S2-34`（浏览器空态/分页的可视化与键盘）、`S6-06`、异机访问、并发/压力、备份恢复、真实渠道数据、真实浏览器交互。
- 数据性质：全部为示例域合成数据（`data_origin=synthetic`，另有 1 条 `.invalid` 域的 real 隔离样例）；**不代表任何真实市场需求或盈利**。

## 8. 复跑指引

```powershell
Set-Location 'D:\桌面\two'
$env:PYTHONUTF8='1'; $env:PYTHONIOENCODING='utf-8'
$py = '.\.venv\Scripts\python.exe'
# 1) 冻结快照（新 run_id；校验实时树 = 快照树）
& $py -X utf8 tests\acceptance\freeze_snapshot.py
# 2) 独立整链路验收（读取 _tmp\current_run_id.txt；端口 5095；不触碰 instance\）
& $py -X utf8 tests\acceptance\run_s2_acceptance.py; "exit=$LASTEXITCODE"
# 3) 对照：快照内实现者自测与 Node 行为用例
Push-Location (Get-Content tests\acceptance\_tmp\current_run_id.txt | ForEach-Object { "tests\acceptance\_snapshots\$_" })
& 'D:\桌面\two\.venv\Scripts\python.exe' -X utf8 -m unittest discover -s tests -t .
node tests\ui\ui_behavior.mjs
Pop-Location
```

## 9. 限制

1. 结论对应固定快照 `s2d_20261009_231628`（树哈希 `84f4a47c…`）；验收后实时树与该哈希一致，但若后续 B/C 再写入，需重新冻结复核。
2. 无浏览器工具：界面结论的边界已在 §5 声明；不得据本报告宣称真实浏览器交互已验证。
3. 我的 46 项检查是**独立实现**（自建夹具取自快照内契约 §4.7、独立断言），与 B/C 自测代码无共享；但输入的“正例”仍源自契约样例，不代表真实业务数据。
4. 未能覆盖 `supersede` 全字段语义的组合空间、并发/幂等竞争、超长/超限请求等压力场景。
5. 提交仅进入待验收；S2 是否收口与是否要求 B/C 处理 §6 三项观察，由策划者决定。

## 10. rev9 补证批次：A→B 货源切换（2026-10-12）

- 脚本：[run_s2_attempt.py](<../../tests/acceptance/run_s2_attempt.py>)；attempt 目录 `tests/acceptance/_tmp/attempts/attempt_20261012_223504_227s/`（日志 `attempt_log.txt`、`server.log`），**与原 46 项日志、原 55 文件快照分开留档**（快照清单复校 55 条不符=0；`app.__file__` 来自快照；端口 5096 仅本机；只停自启 PID）。
- 本批 **22 项：21 PASS / 1 FAIL（阻断）**。

**阻断 · B-no-impersonation**（expected：当前 G2=B 时 derived≠testable 且不沿用 A 的 G3/G4）
- 实际：`G2(B)=200`、DB 当前 G2 行 `seq=2, supply_offer_id=B`（断言通过）、短 TTL 断言通过（`expires_at=2026-10-14T14:35:06Z` = 证据有效期）；但 GET 详情 **`derived_status` 仍为 `testable`**、四门槛全 `verified`，而 `cost`/`platform_policy` 核验行仍是 `seq=1, status=verified, supply_offer_id=null` —— **B 的成本/平台条件从未核验，A 的旧核验继续充当“当前核验”**（= 原 P1，**属旧快照 `s2d_20261009_231628` 的历史观察**；新快照 `s2d_20261013_fix1` 上该项已不复现，见 §0 与 [attempt_20261013_194043_ga1q/attempt_log.txt](<../../tests/acceptance/_tmp/attempts/attempt_20261013_194043_ga1q/attempt_log.txt>) 的 23/23）。
- 最小复现：导入 38 列正例 → A 四门槛 verified（断言 `testable`+`contribution=190`）→ `POST /evidences`（`supply_distribution`，`expires_at=+2d`）→ `POST /supplies`（B：`format_version=v2`、三项许可 `yes`、`sample_checked=partial`）→ `POST /gates/supply_distribution {supply_offer_id:B, evidence_id:B条款}` → 200 → `GET /api/candidates/{id}` 得 `derived=testable`。
- 静态根因：`app/core/state.py` 118–134 `effective_gate_status` 仅校验自身证据/货源、成本未知与过期，**不把 `cost`/`platform_policy` 行与“当前 G2 选定货源”比对**；`app/core/gates.py` 291–294 `record_gate` 对这两类门槛**未落 `supply_offer_id`**（DB 证据为 `null`），使一致性比对也无字段可用。
- 影响：资金/证据边界——选定货源切换后，未核验的成本/平台条件仍显示为可测试；若进入推荐，会把 A 的条件当作 B 的。
- 建议方向（未代改应用）：G3/G4 行持久化当时依据的 `supply_offer_id`，并在 `effective_gate_status`/`recompute` 增加“依据货源 ≠ 当前 G2 选定货源 → 按 `expired` 处理并物化复核项”，与既有失效降级共用同一路径。

**本批其余断言（均 PASS，expected 已写明）**：A 四门槛→`testable` 且 `contribution=190`；`G3` 无说明 422（details 指向 `sale_price.per_order`）与 `per_order` 仅改说明 200（旧行停用、新行值 NULL）分列；`recurring` 缺 `period` 取代 422 且前后行一致（零写）；`G4` 版本不符 422；G2 省略 `evidence_id` 的默认同源关联与短 TTL 精确值（**更正：`None+30d` 分支已实测，非"未测"**；见 §0「本轮更正」）；`G3` 用旧 A → 422、`G4` 用旧 A 版本 → 422、`G3` 用跨候选货源 → 422；B 条款失效后 supply=expired 且当前行仍指向 B（不回退旧 A）；两次 GET 前后全部计数与 `gate_review`/`review_item` 时间戳一致（零写）。

**批次状态（第二批已完成，2026-10-12 23:17，attempt_20261012_231739_87ln）**：修正探针后 23 项 **22 PASS / 1 FAIL**，唯一 FAIL 即上面的 P1 阻断（`B-no-impersonation`：切换成功为前提——`ASSERT-G2-switch-A2B` 200 且当前行=B、`ASSERT-G2-TTL-equals-evidence` 精确相等——但 `derived=testable` 依旧，`cost`/`platform_policy` 行仍 `supply_offer_id=null`）。
- **真实 CLI 守卫（不再伪断言）**：非法 ID 三类（绝对路径/`a/b`/`..`）均 `exit=1` 且输出“非法 RUN_ID”、哨兵工作区仍为空；重复 ID 首次 `exit=0`、重复 `exit=1` 且既有快照哈希未变（`84f4a47c…`）；占用端口 `exit=1` 并提示“被占用”；哨兵证明固定快照树哈希、清单哈希与 `instance/app.db` 前后不变。
- **正/反路独立断言**：`ASSERT-G2-omitted-evidence-TTL` 200 且默认关联条款证据、`expires_at` **精确等于** `min(证据有效期, verified_at+30d)=2026-11-11T15:17:42Z`（该证据 `expires_at=None`，故取 +30d 分支，精确相等）；`ASSERT-G3-foreign`/`ASSERT-G4-foreign`（显式传 `supply_offer_id` 的异货源）与 `ASSERT-G3-cross-candidate` 均 422，且断言带“切换成功”前置，不满足前置即为 FAIL；`ASSERT-G2-no-fallback` 失效后 `expired` 且当前行仍=B；`ASSERT-GET-zero-write` 两窗口全表计数与时间戳一致；`ASSERT-recurring-422-zerowrite`（422 且前后行一致）与 `ASSERT-per_order-note-only`（200、旧行停用、新行值 NULL）分列。
- **镜像卫生**：Node 与对照副产物只在 `_tmp` 哈希一致镜像内生成（`MIRROR-HASH` 逐字节一致，`NODE-MIRROR-HARNESS` 镜像内 `exit=0`，快照内不产副产物）；probe/server 均带 `PYTHONDONTWRITEBYTECODE=1`；快照 ID 显式固定（不按目录序择新）；清单/端口校验在创建产物之前，端口被占用不杀他人进程。
- **探针缺陷留档（不归因应用）**：`attempt_20261012_223207` 的 GET 计数窗口包住了写入（错误窗口，已在后续批次改为只包 GET）；`223504` 四项 guard 受 `else True` 伪断言影响**不计证据**；`231544` 因 `POST /supplies` 不落 `license_evidence_id`（`app/core/supplies.py` INSERT 未含该列）导致“切换”实际未发生，该轮 `B-no-impersonation`/`G3/G4-foreign`/`no-fallback` **不计证据**，已在 `231739` 用显式证据路径重做。
- **第四批（rev18，仅工具与修复）**：①**修 runner 分支回归**——退款桥接检查移出 Node 失败分支、改在**成功路径**执行：镜像内 `node ui_behavior.mjs` 成功后才解析载荷，`captured` 非空即适配关联 ID/order_ref/refund_state（`amount_minor`=990 保留，非原样字节）并真实 `POST` 断言 **201**；缺 Node／镜像不一致／artifact 不存在／未取到载荷四种情况一律 `FAIL`（不再 `None`/INFO、不跳过）；②**新增 `SELF-COVERAGE`**：36 个必测 ID（含 `UI-JS-node-harness`、`UI-JS-refund-realHTTP`、`S2-15-downgrade`、`S2-32-restart` 与各反例）必须全部登记且 **INFO 计数为 0**，漏检即 FAIL；③`S2-15-downgrade` 补入 `st_rc1/st_rc2/st_res == 200` 真断言（此前 recompute/dismiss 状态码只在打印里）。实测：`python -X utf8 tests\acceptance\run_s2_acceptance.py` → **exit=0、47/47 PASS / 0 FAIL / 0 INFO**（attempt_20261013_192351_ko7x）；其中 `UI-JS-refund-realHTTP` 201（金额 990 保留、关联字段适配）、镜像 Node harness `15 passed / 0 failed`、`SELF-COVERAGE 缺失=none INFO=none`；原 run 目录 `_tmp/s2d_20261009_231628` 最大时间戳仍为 2026/10/9 23:22:34（未被改写）。项数由 45 升至 47，正是因为此前漏检的桥接 ID 与新增的自证检查现在都实际登记。
- **守卫硬化（同一批，代码已落）**：`preflight` 拒绝**重复清单条目**（不再 dict 静默覆盖）、清单非空、绝对/`..` 越界条目；**逐文件 `resolve()` 后必须仍在 snapshot 内**且为文件；`snapshot_root()`／`pointer_path()` 解析后（含既有链接）必须落在固定批准根（`tests/acceptance`）与隔离区（`_tmp`）之内，env 覆盖不得扩根。**对三个真实入口的 CLI 负例证据（非法 ID/指针、重复目录、占端口、损坏/空/重复清单、越界根/pointer，仅 `_tmp` 同源码镜像 + 哨兵前后树/库/log 哈希）尚未在本批执行**，列为待办。`run_s2_acceptance.py` 与 `freeze_snapshot.py` 共用 [_guard.py](<../../tests/acceptance/_guard.py>) 同一守卫——`safe_id` 用**规范化返回值**拼接、批准根固定 `tests/acceptance`（`S2D_SNAPSHOT_ROOT`/`S2D_POINTER` 覆盖只允许 `_tmp` 之下，否则拒绝）、解析后（含既有链接）核对 `parent==批准根`、目录独占创建；顺序固定为「显式 snapshot ID → 清单完整性（非空／无绝对与越界路径／条目集合与快照实际文件一致／逐文件哈希）→ 来源在快照内 → 端口空闲 → 独占新 attempt + 干净库」，**已删除原 DB/wal/shm unlink 与旧日志覆盖**。实测命令 `python -X utf8 tests\acceptance\run_s2_acceptance.py` → **exit=0、45/45 PASS**（attempt_20261013_190642_2clr；项数比首跑少 1 项，系**桥接检查被放进 Node 失败分支导致漏检**（**更正：原记"检查条件分支差异"不成立**；见 §0「本轮更正」），补回漏检 ID 并新增 `SELF-COVERAGE` 后为 47/47，缺失/跳过一律记 FAIL 不静默通过）；来源探针=`快照内 app/__init__.py`（`PYTHONDONTWRITEBYTECODE=1`）；Node 与对照产物只落 `_tmp` 哈希一致镜像；打印与断言只比五个业务表；**原 run 目录 `_tmp/s2d_20261009_231628` 五个文件时间戳与内容未变**（未删库、未覆盖旧日志）。
