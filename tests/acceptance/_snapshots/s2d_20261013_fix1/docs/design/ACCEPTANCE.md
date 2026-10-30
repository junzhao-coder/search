# 技术与验收矩阵（S1-B v3）

> 状态：测试设计 + **实际执行结果**（S2-B1/S2-B2，2026-10-09）。已执行行按事实填 `通过`/`部分通过`，未跑的行保持 `未执行`，**未预填通过**；实现记录见 [S2 核心实现记录](<S2_CORE.md>)，B1 运行证据见 [S2 运行与验证记录](<S2_RUNTIME.md>)（本轮未改动该文件）。
> 用途：S2–S6 的可复现检查清单。执行者逐行执行并填写「状态」列，D 独立复现，策划者验收。
> 对应契约：[数据与接口契约 v3](<CONTRACT.md>)（Flow 已验收冻结，作为 S2 实现依据）。文中 `§n`、`V n`、`I n`、`G n`、`D-nn` 分别指契约章节、校验规则、不变量、门槛准入与 D 的审阅用例编号。
> 旁证：[来源可行性报告](<../research/FEASIBILITY.md>)（Flow 已验收）、[开发总体计划](<../../DEVELOPMENT_PLAN.md>) 附录 A（P1–P4）、[S1 独立审阅](<../validation/S1_REVIEW.md>) 与 [修后复核](<../validation/S1_REVIEW_REVISED.md>)（Flow 已验收）。
> 合成声明：测试输入一律使用示例域合成数据（`data_origin=synthetic`）；真实脱敏样本另库、另批次。

## 1. 执行与证据约定

- 每行记录：执行者、时间、命令或 HTTP 请求、原始输出（含状态码）、数据库路径、关键表前后行数。
- 测试库隔离：`APP_DB_PATH` 指向独立临时文件；破坏性检查只在副本或测试库进行。
- 「状态」列取值：`未执行` / `通过` / `部分通过` / `失败` / `阻塞` / `留空（缺工具）`；异机与浏览器类检查缺工具时据实留空，不记为通过。
- 行数断言统一用 `SELECT COUNT(*)`：`candidate`、`demand_signal`、`evidence`、`supply_offer`、`cost_item`。
- 金额断言一律比较整数分，不得出现浮点字面量。
- 执行环境（实测）：内置 Python 3.12.14 + 工作区 `.venv`；SQLite 3.53.1；Flask 3.1.3（唯一新增直接依赖）；服务默认 `127.0.0.1:5000`，端到端检查用 `APP_PORT=5081–5084` 避开占用；时区以固定 +08:00 实现。

## 2. 技术基线核验清单

已知事实（设计输入）：环境清单工具返回内置 Python/Node/pnpm 路径与该 Python 包清单（未含 Flask/werkzeug——只说明不属于该捆绑运行时，**不能推断安装或捆绑状态**）；`flow_state` 早期各角色 `allowCommands=false`，S2 阶段实测执行者 `allowCommands=true` 且会话具备命令工具（`pwsh` 实测可用）。下表按实际运行结果填写。

| ID | 检查 | 操作 | 预期 | 证据要求 | 状态 |
| --- | --- | --- | --- | --- | --- |
| T-01 | 宿主 Python | `python -V`（内置解释器与 `.venv` 解释器） | 可执行；记录实际版本 | 命令原文与输出 | 通过（3.12.14；`instance/env_checks.txt` T-01） |
| T-02 | 虚拟环境 | `.venv` 创建并检查 `pyvenv.cfg` | 创建成功 | 命令与输出 | 通过（`python -m venv .venv` exit=0） |
| T-03 | pip 与包源 | `pip --version`；`pip download flask -d .venv/cache` | 可达或记录离线条件；缓存写入已授权路径 | 命令与输出；`.venv/cache` 内容 | 通过（pip 25.0.1；download exit=0，缓存 7 个 wheel） |
| T-04 | Flask 安装与锁定 | `pip install flask`；`pip show flask`；写 `requirements.txt` | 成功；版本锁定；不裸 `pip` 改宿主 | `pip show` 原文；依赖文件 | 通过（Flask 3.1.3；`flask==3.1.3`） |
| T-05 | sqlite3 | `import sqlite3; print(sqlite3.sqlite_version)` | 可用；记录版本（确认表达式索引/部分索引可用） | 命令与输出 | 通过（3.53.1；部分唯一索引与 COALESCE 表达式索引已使用） |
| T-06 | 启动与绑定 | 启动应用；`GET /api/health`；`netstat -ano` | 200；schema 一致；仅监听 `127.0.0.1` | 响应 JSON；netstat 输出 | 通过（health 200 / `schema_version=2`；`TCP 127.0.0.1:5000` 与 5081–5084 LISTENING） |
| T-07 | 测试入口 | `.venv\Scripts\python -m unittest discover -s tests -t .` | 可运行（标准库，不引入 pytest） | 命令与完整输出 | 通过（S2-B2 补 `tests/__init__.py` 后实测 `Ran 78 tests … OK`，exit=0） |
| T-08 | 权限与工具 | 读 `flow_state` 确认 `allowCommands`；确认会话具备命令执行工具 | 两者同时具备才可执行其余项 | `flow_state` 观察值；工具清单 | 通过（执行者 `allowCommands=true`；`pwsh` 实测输出 `Python 3.12.14`） |
| T-09 | 数据目录 | 首启创建 `instance/` 与 `instance/app.db`；`APP_DB_PATH` 覆盖生效 | 可写；覆盖生效 | 目录清单；库文件路径 | 通过（`instance/app.db` 生成；测试与 E2E 全部走临时库覆盖） |
| T-10 | 端口 | 检查 5000 占用；`APP_PORT` 可配 | 冲突可视且可配置避开 | netstat 输出与配置值 | 通过（启动前 5000 空闲；`APP_PORT=5081–5084` 实测可用） |
| T-11 | 依赖边界 | 检查 `requirements.txt` 与 `app/` 导入 | 仅 Flask 为新增直接依赖 | 文件内容与导入清单 | 通过（`app/` 内第三方导入仅 flask；`pip freeze` 7 项均为 Flask 传递依赖） |
| T-12 | 备份与恢复（S6 执行） | 见 S6-02 | — | — | 未执行（阶段归 S6） |

## 3. 矩阵 A：S2 本地最小闭环

| ID | 阶段 | 前置/输入 | 操作 | 预期 | 证据要求 | 状态 |
| --- | --- | --- | --- | --- | --- | --- |
| S2-01 | S2 | 空测试库；`APP_DB_PATH` 指向新文件 | 首启 → `health` → 再启；写一次无来源 `import` | 建表到 schema v2（0001+0002）；两次启动幂等；`run_record.source_id` 为 NULL 且 FK 有效 | 启动输出；`schema_migrations`；`run_record`（D-07） | 通过（`tests/storage/test_migrations.py`；迁移两次调用返回同一版本） |
| S2-02 | S2 | 已导入 1 条候选 | 停止并重启后读列表与详情 | 数据保留，字段不变 | 前后响应 JSON | 通过（`test_restart_keeps_data`；B2 E2E 重启后仍 `testable`） |
| S2-03 | S2 | §4.7 CSV 正例（**38 列**）与 JSON 正例 | 各导入一次，逐字段核对；再读情景与门槛 | 别名映射准确；`_minor` 白名单键正常解析；派生需求证据 1 条；条款链接与证据落位；**成本项 10 条**；`cost_supply_url` 解析为 `supply_offer_id`；**情景 `contribution=190`、`complete=true`**；**G3 因 assumption 无说明 → 422**；返回真实实体 ID | 批次行结果；各实体计数与字段值（D-01） | 通过（B1 证存储层与只读派生；B2 `test_example_scenario_190_and_g3_needs_grounding` 实测 190/complete 与 G3 422） |
| S2-04 | S2 | 合成行：无 `demand_native_id`、固定 URL | 原样导入两次 | 一候选、一信号、一证据；第二次全部 `duplicate_skipped`；业务表计数不变 | 批次结果；前后计数（D-02/R2） | 通过（`test_reimport_same_file_does_not_proliferate`） |
| S2-05 | S2 | 两个渠道分别导入 `native_id=1001`（xianyu / bilibili） | 分别导入并读列表 | **两个独立候选**（`n:xianyu:1001` 与 `n:bilibili:1001`），不以复核项代替隔离 | 两条详情；候选计数（R2/P2-2） | 通过（`test_cross_channel_same_native_id_stays_two_candidates`） |
| S2-06 | S2 | 同上记录；另造不同 URL 同文行 | ① 改 `demand_excerpt` 重导；② 导入不同 URL 同文行 | ① `version_added`，旧行 `superseded_by` 指向新行；② `dup_suspect` 复核项，不自动合并 | 批次结果；两行字段；复核项（D-02） | 通过（`test_content_change_adds_version`、`test_same_content_different_url_creates_suspect_review`） |
| S2-07 | S2 | ① 无需求组且无原生 ID 的候选；② 同需求行再次导入但新增费用列 | 各重导一次 | ① 候选按 `t:<title_norm_hash>` 复用不增殖；② 需求侧 `duplicate_skipped`，**新增成本项照常落库**（V17），不整行跳过 | 候选计数；成本项计数（D-03/R2） | 通过（`test_title_only_row_reuses_candidate`；`test_same_demand_with_new_cost_row_keeps_sub_records` 按 **`import_row_result` 记录级**核对 `duplicate_skipped/demand_signal`） |
| S2-08 | S2 | `real` 与 `synthetic` 同来源、同 `native_id`、同内容 | 分别导入；再尝试跨 origin 合并 | 两条独立记录与统计；合并 `422` 说明跨界禁止 | 两组详情；422 响应（D-04/I14） | 部分通过（隔离已测：`test_real_and_synthetic_are_isolated`；`POST /merge` 属后续任务，未执行） |
| S2-09 | S2 | 造行：`title` 空、金额 `12.345`、双表示不一致、负金额、行宽不一致、重复表头、`recurring` 缺 `period` | `mode=atomic` 导入 | 整批 `rejected`；业务表 0 行；逐行返回 V2/V5/V21/V22/V25/V26/**V16** | 响应 JSON（含行号与规则号）（P2-1） | 通过（`test_negative_rows_are_rejected_atomically_with_reasons`、`test_recurring_without_period_is_row_rejected`） |
| S2-10 | S2 | GBK 编码文件 | 导入 | 整批拒绝 `encoding_error`；无业务行 | 响应 JSON | 通过（`test_non_utf8_body_is_rejected`：400 `encoding_error`，业务表 0 行） |
| S2-11 | S2 | ① 只填 `demand_url` 缺摘录；② 货源组缺许可位；③ 货源只有 `supply_evidence_url`；④ 无需求组行提供 `observed_at` | 分别导入 | ①②行级拒绝（V10）；③导入成功且只保留 `license_evidence_url`、**不创建证据行**；④`warning`（V23） | 响应 JSON；货源详情 | 通过（四情形实测：负例样本 V10 两例 + `test_url_only_supply_keeps_gap_and_observed_at_warning`） |
| S2-12 | S2 | 行 A 成本列全空；行 B 各角色显式全 0；行 C 仅 `procurement_unit_cost=0` | 导入后读成本项与情景 | A：无成本行（未知）；B：已知 0 落库并计入；C：其余 basis 与 `other` 分别列入未知；门槛 `unverified`、候选 `pending` | 响应与库内字段值（D-05/I16） | 通过（B2 `test_unknown_components_never_inferred_as_zero`、`test_procurement_bases_are_independent`、B1 `test_unknown_cost_and_explicit_zero_are_distinct`） |
| S2-13 | S2 | 4 组候选，各缺 1 项门槛 | 逐组读详情 | 4 组均 `pending`；`status_reason` 指向缺失门槛；未核验门槛为 `unverified` | 4 次详情响应 | 通过（B1 `test_four_candidate_groups_stay_pending`；B2 门槛端点实测 `pending` → `testable` 的迁移） |
| S2-14 | S2 | 6 例反证：`resale_allowed='no'`；`commercial_allowed='no'` 且 `resale_allowed='yes'`；`sample_checked='none'`；`payment_fee` 为 NULL；平台证据属其他平台/版本；无 `manual_labor` 行 | 各自提交 `status=verified` | 六次均 `422 invalid_state`，`details` 列出具体缺口 | 6 次响应（D-08/R4） | 通过（`test_supply_gate_rejects_licence_and_sample_gaps`、`test_cost_gate_rejects_unknown_roles_and_ungrounded_rows`、`test_platform_gate_version_must_match_selected_supply` 含其他平台与其他版本；边界修正后补充 `test_cost_gate_cannot_be_switched_to_another_supply`、`test_cross_candidate_supply_is_rejected`、`test_g3_requires_a_currently_verified_g2`、`test_platform_version_follows_the_current_g2` 与 `test_invalidated_evidence_cannot_produce_verified`、`test_expired_evidence_cannot_produce_verified`） |
| S2-15 | S2 | 门槛已 `verified` 且其证据随后被 `invalidate` | 多次 GET → `recompute` → `resolve/dismissed` → 再读详情 | 多次 GET 不新增记录、不改时间戳；`dismissed` 不恢复 `verified`；候选保持 `stale` | 复核项计数与时间戳（I1/§3.3） | 通过（`test_expiry_by_evidence_expires_and_resequences` 的零副作用断言、`test_blocking_review_on_subrecord_makes_candidate_stale`、`test_same_second_supersede_downgrades_cost_gate` 的 dismiss 分支；`test_g2_default_clause_evidence_is_persisted_and_used_for_ttl` 实测失效即同事务降级 + 读取零写入 + `recompute` 幂等） |
| S2-16 | S2 | 货源 `last_checked_at` 超出 30 天 | 读数详情 → `recompute` | `supply_distribution` 为 `expired`；`supply_invalid` 复核项；候选 `stale`；引用该货源的 `cost` 门槛同样降级 | 详情；复核项（§3.3/§3.4） | 通过（`test_supply_ttl_degrades_supply_and_cost_gates`） |
| S2-17 | S2 | 满足 §3.5 的候选 | 依次核验 4 项门槛 | 第 4 项后 `testable`；门槛各含证据/货源/平台字段与有效期 | 门槛响应序列（§3.5） | 通过（`test_four_gates_make_candidate_testable_with_ttls`：四门槛 TTL 90/30/30/180 天；E2E 同结论） |
| S2-18 | S2 | 已 `testable` 的候选 | 门槛过期 → 读详情 → `recompute`；同一秒内合法重核一次 | 读取时 `expired`；复核项物化；候选 `stale`；重核 `seq=max+1` 成功 | 前后详情；`seq` 序列（R1） | 通过（`test_expiry_by_evidence_expires_and_resequences`：证据有效期 → `expires_at=min(证据, TTL)`；把核验行 `expires_at` 推过期 → 读取 `expired` 且零写入 → 物化 → `seq 1→2→3`） |
| S2-19 | S2 | ① 售价 33.33 + 500bp；② 售价 10.00、逐单成本 12.00；③ 输入负金额行 | 读情景/记录成交；导入 ③ | ① 167 分；② `contribution=−200` 且 `predicted_net_per_order_minor=−200` 可保存；③ 拒绝（V22） | 情景/反馈 JSON；拒绝响应（D-06/R1） | 通过（`test_rate_rounding_half_up`、`test_loss_snapshot_and_negative_derived_value`、`test_negative_rows_are_rejected_atomically_with_reasons` 的 V22） |
| S2-20 | S2 | 售价 10.00；`procurement_unit_cost=2.00`；其余逐单费用、人工、一次性/周期采购与 `other` 均显式 0 | 读情景 | `contribution=800` 分且 `net=800`；一次性/周期性成本不混入逐单 | 情景 JSON（D-09/R5） | 通过（`test_contribution_800_case`；边界修正补测周期维度：`test_monthly_positive_sets_monthly_total_and_gap`、`test_non_monthly_explicit_zero_is_complete`、`test_monthly_explicit_zero_is_complete_with_zero_total`、`test_quarterly_positive_keeps_contribution_but_not_complete`、`test_yearly_positive_is_not_complete`、`test_missing_recurring_row_stays_unknown`） |
| S2-21 | S2 | 售价 10.00；一次性买断 20.00（无销量假设）；逐单与周期费用已知 | 读情景 | `contribution` 返回；`net=null`、`complete=false`、`fixed_cost_gap_minor=2000`；`amortize_orders` 归 S4 | 情景 JSON（R5/§5.5） | 通过（`test_buyout_nulls_net_and_reports_gap`：one_time 10000 → 缺口 10000、net=null；非月度正额周期同样 `net=null` 且不给伪月额，见 `test_quarterly_positive_keeps_contribution_but_not_complete`；摊销仍属 S4-07） |
| S2-22 | S2 | 同一候选下免费（0）、付费（>0）、未知（NULL）货源 | 读详情与路由表 | 三者分别显示；未知不显示为 0；无采购/付款端点（404） | 详情 JSON；404 响应 | 部分通过（API 层 0 与 NULL 可区分、`test_no_purchase_or_payment_endpoints` 404 已测；**界面展示文案属 C**） |
| S2-23 | S2 | 固定输入集合 | 同参数连续读取两次 | 顺序完全一致；每项含非空解释字段 | 两次响应 diff | 部分通过（`test_list_order_is_stable_and_repeatable` 顺序一致；**排序解释字段属 S4**） |
| S2-24 | S2 | 未配置任何模型 | 生成 `method=template` 草稿；检查外发路径 | 生成成功；未核验内容有显式占位；状态仅 `draft`/`final`；无发送/发布端点（404） | 草稿 JSON；404 | 通过（`DraftTest.test_template_draft_works_without_a_model`、`test_model_assisted_requires_a_configured_model`） |
| S2-25 | S2 | 已 `testable` 候选；两笔成交；退款；人工时间 | 记成交 → 退款（`pending`）→ `PATCH` 结算 → 重复结算 → 更正人工分钟数 | `predicted_*` 始终不变；退款归属唯一；`pending`→`settled` 幂等；人工分钟/费率可录入与更正（同值不新增行）；`actual_net`/`actual_complete` 保持 NULL | 反馈 JSON（D-11/R6） | 通过（`test_sale_snapshot_is_generated_and_frozen`、`test_refund_requires_matching_sale`、`test_manual_time_record_and_correction`） |
| S2-26 | S2 | 7 例反例（退款关联、`order_ref` 不符、`quantity=0`、提交预测/实际字段、白名单外字段、非 manual_time 传人工字段、非 refund 传退款状态） | 分别请求 | 全部 `422`，`details` 指明字段 | 7 次响应（§5.4） | 通过（`test_refund_requires_matching_sale`、`test_manual_time_record_and_correction`、`test_expense_inquiry_and_server_field_rejections`） |
| S2-27 | S2 | 同 `client_ref` 的门槛/导入请求；改载荷再提交；制造批次失败 | 重放；重启后重放；改载荷；失败后重试 | 重放返回原记录且 `deduplicated=true`；重启后仍重放；改载荷 `409`；失败批次不写幂等记录（可同 `client_ref` 重试）；失效重复不增殖 | 响应与 `idempotency_key`/`review_item` 行（D-10/R7/P2-3） | 通过（`test_gate_write_idempotency_and_override`、`test_idempotency_survives_restart`（B1）、`test_rejected_import_leaves_no_idempotency_record`、`test_supply_ttl_and_recompute_are_idempotent`） |
| S2-28 | S2 | 成本项写入口与门槛降级（八步） | ① 补首个支付费；② `supersede` 修正；③ 同一秒内连续取代（其他成本项仍活跃）；④ `dismiss` 后读详情；⑤ 新增 `verified` 核验；⑥ 导入路径仅改货源价格/依据；⑦ 同一改动走 `validate`；⑧ `atomic` 批次含失败行 | ① 首次追加成功；② 活跃项唯一、旧行 `is_active=0`；③④ 同事务追加 `seq=max+1`/`expired`/`system_rule` + 幂等 `cost_changed`（同秒生效、`dismiss` 后仍 `stale`）；⑤ 仅新增 `verified` 才恢复 `testable`；⑥ 未新增成本行也降级；⑦ 不产生降级/复核项；⑧ 随批次回滚 | 门槛 `seq`；复核项计数；详情（§3.3/§3.4） | 通过（`test_same_second_supersede_downgrades_cost_gate`①②③④⑤、`test_import_price_change_downgrades_without_new_cost_row`⑥、`test_validate_mode_never_materializes_downgrade`⑦、`test_atomic_rollback_undoes_downgrade`⑧） |
| S2-29 | S2 | 合法正例与含错行的文件 | `POST /api/imports?mode=validate` | `200` 且 `saved=false`；行级结果；不写业务/批次/运行/幂等记录；随后正式导入正常执行 | 响应 JSON；各表计数（P2-4/§5.4） | 通过（`test_validate_mode_writes_nothing`；B2 追加 `test_validate_mode_never_materializes_downgrade`） |
| S2-30 | S2 | 单行正例（端到端） | 导入 → 补证据/成本 → 四门槛 → 模板草稿 → 反馈 → 重启 → 查询 | 证据缺口先挡池；补齐后 `testable`；草稿有占位且无发送；事件与快照、幂等记录持久 | 全链路响应与库计数（D-12/P3-5） | 通过（`FullChainTest.test_end_to_end_chain_and_restart` + 真实 HTTP `b2_e2e.py` → `E2E_OK`，重启后 `testable`） |
| S2-31 | S2 | 无效路径、未知 ID、非法枚举、白名单外字段、超大请求 | 分别请求 | `400`/`404`/`409`/`422` 各至少 1 例；错误体含 `code`/`message`/`details` | 响应状态码与 JSON | 通过（400：空体/未知格式/GBK；404：候选/批次/草稿/反馈/采购路径；409：幂等异载荷、重复 `order_ref`、货源强键；422：准入与字段类） |
| S2-32 | S2 | 服务已启动 | `netstat` 确认监听；本机请求 `health`；异机访问 | 仅监听 `127.0.0.1`；本机 200；异机不可达（缺异机环境时留空） | netstat；本机响应；异机留空说明 | 通过（`TCP 127.0.0.1:5000`/5081–5084 LISTENING，无 0.0.0.0；本机 200；**异机环境缺失，留空**） |
| S2-33 | S2 | `title`/`excerpt` 含 `<script>` 的合成行 | 导入后打开详情页与接口 | 页面以文本显示、无脚本执行；接口为 JSON 文本 | DOM 断言或文本快照 | 未执行（页面属 C；接口返回 JSON 文本已可观察，未做 DOM 断言） |
| S2-34 | S2 | 空库／失败态／待核验与过期候选 | 打开 P1–P4 页面 | 空数据、加载、失败、待核验、已过期可区分 | 截图或 DOM 断言 | 未执行（页面与浏览器工具属 C/D；四个页面路由当前为 501 占位） |

## 4. 矩阵 B：S3 需求自动化与 S4 货源/收益

| ID | 阶段 | 前置/输入 | 操作 | 预期 | 证据要求 | 状态 |
| --- | --- | --- | --- | --- | --- | --- |
| S3-01 | S3 | A 结论：本轮未核实到发现型自动入口 | 实现一个已核实适配后触发 | 读取 → 标准化 → 存储 → 详情可回溯；留 `run_record` | 运行记录、计数、详情 | 未执行（依赖 S3 实施，未开始） |
| S3-02 | S3 | 三渠道种子来源行（`manual_import`） | 读 `/api/sources` | 显示"人工导入"；`access_mode` 不得为 `auto_read` | 响应 JSON（§1.10） | 部分通过（API 实测 4 行种子全部 `manual_import`；**界面展示属 C**） |
| S3-03 | S3 | 制造来源失败 | 触发采集 | 运行标 `failed/partial`；历史证据不变 | 运行记录；前后计数 | 未执行（无采集路径） |
| S3-04 | S3 | 配置重试上限 | 连续触发失败来源 | 达上限后停止 | 运行记录序列 | 未执行 |
| S3-05 | S3 | 来源字段变化/缺字段 | 触发采集 | 运行 `partial`；生成复核项 | 运行记录；复核项 | 未执行 |
| S3-06 | S3 | 有覆盖记录的检索 | 读覆盖与三种缺失 | 三种缺失分别显示；不推断全市场 | 覆盖 JSON | 未执行（`search_coverage` 归 S3） |
| S4-01 | S4 | 需求与多个货源 | 读匹配结果 | 每项含匹配依据与缺口 | 响应 JSON（R5） | 未执行（匹配引擎未开始） |
| S4-02 | S4 | 货源许可由 `yes` 改为 `no` | 更新货源 | `license_changed` 复核项；候选转 `stale` | 复核项；状态序列 | 未执行（S4 阶段行；降级机制已由 B2 实现，尚未按该行验收） |
| S4-03 | S4 | 证据不足但潜力较高的候选 | 人工置 `explore` | 进入探索池；不出现在摘要重点位 | 列表与摘要响应 | 未执行（分池写入已实现，摘要属 S5） |
| S4-04 | S4 | 供给缺口记录；A 的 `license_reviewed` 标签样例 | 读自制建议与该货源状态 | 研究标签**不升级** `supply_offer.status`，也不使门槛通过 | 响应 JSON（§3.5/§9） | 部分通过（导入不读取研究标签、`status` 恒为 `candidate`；自制建议属 S4） |
| S4-05 | S4 | 同候选 `variant=low/base/high` | 读三个情景 | 三情景独立返回、互不覆盖 | 三次情景 JSON | 未执行（`variant` 已入库并按 variant 计算，多情景验收属 S4） |
| S4-06 | S4 | 免费且适用与付费货源 | 读排序/推荐 | 免费且适用排前；付费不自动采购 | 排序响应；采购路径 404 | 未执行（排序属 S4；采购路径 404 已由 S2-22 覆盖） |
| S4-07 | S4 | 买断/订阅/季度成本 | 补假设后读情景 | 摊销与周期归一按 S4 规则；缺假设时 `net=null` | 情景 JSON（R5/§5.5/§9） | 未执行（归一与摊销属 S4） |

## 5. 矩阵 C：S5 日常工作流与 S6 验收

| ID | 阶段 | 前置/输入 | 操作 | 预期 | 证据要求 | 状态 |
| --- | --- | --- | --- | --- | --- | --- |
| S5-01 | S5 | 0 / 3 / 8 条合格候选 | `GET /api/summary/daily` | 0/3/5 条 + "更多见完整候选池" | 三次响应 | 未执行（端点属 S5） |
| S5-02 | S5 | 同一 `logical_date` | 二次触发 `pipeline` | 第二次 `skipped_duplicate` | 两次运行记录 | 未执行（S5；`run_record` 每日幂等索引已建） |
| S5-03 | S5 | 同一时刻并发两次触发 | 同时请求 | 第二次被拒或跳过 | 两次响应；表计数 | 未执行（S5） |
| S5-04 | S5 | 月累计 + 预留接近上限 | 触发新增计费调用 | 接近上限时拒绝或降级 | 运行记录与降级证据 | 未执行（S5） |
| S5-05 | S5 | 未获确认的计费服务配置 | 触发流水线 | 保持停用、不产生费用 | 配置与运行记录 | 未执行（S5；本轮未启用任何计费服务） |
| S5-06 | S5 | 实际成本全 0 的成交与全退 | 结算后读实际核算 | 实际利润 0（非 −500）；预测快照不变 | 反馈/核算值（D-11/R6） | 未执行（实际核算属 S5-06；`actual_*` 在 S2 保持 NULL 已由 S2-25 覆盖） |
| S5-07 | S5 | 设备休眠/离线期间 | 恢复后读运行状态 | 如实显示停跑/补跑 | 运行记录；界面状态 | 未执行（S5） |
| S5-08 | S5 | 已有预测与历史反馈 | 记录成交与退款后读摘要 | 历史 `predicted_*` 不被改写 | 前后响应 | 未执行（S5；快照不可改已由 S2-25 覆盖） |
| S6-01 | S6 | 干净环境 | 重跑矩阵 A/B/C | 结果可复现；真实与合成分开 | 回归报告 | 未执行（S6） |
| S6-02 | S6 | 有数据的测试库与备份文件 | 备份 → `integrity_check` → 替换 → 回滚 | 备份生成于 `instance/backups/`；恢复后一致 | 路径、integrity 输出、计数 | 未执行（S6；端点未实现） |
| S6-03 | S6 | 超长/超大/重定向/内网目标 URL | 触发抓取路径 | 超时、大小、重定向上限生效 | 抓取日志与限制参数 | 未执行（依赖 S3 抓取路径） |
| S6-04 | S6 | 含敏感字段的请求 | 检查日志 | 日志不含凭据或敏感原文 | 日志样本 | 未执行（S6） |
| S6-05 | S6 | 一次真实选品操作 | 记录人工耗时 | 与每日 30–60 分钟目标对照 | 计时记录 | 未执行（S6） |
| S6-06 | S6 | 常用窗口尺寸与纯键盘操作 | 走完整路径 | 证据可读；空态/失败态清晰；键盘可达 | 截图或 DOM 断言 | 未执行（C/D） |

## 6. 覆盖缺口与未决项

- A 报告（321 行/索引 665 行/12 条）已验收：本轮未核实到发现型自动入口；B站详情接口与 Met API 为 S3 候选；研究标签不作为门槛依据（§3.5、S4-04）。
- D 的 D-01–D-12 已映射进 S2-01…S2-30；D 报告自身为静态复核，不代表任何用例通过。
- 未冻结到 S2 的项：S5 运行费用台账与预算保护字段、S5 实际利润核算（S5-06 已标注前置）、S4-07 的周期归一与余分处理、排序权重版本化。
- 界面信息架构按 C 附录 A（P1–P4）；四个页面路由当前为 501 占位，S2-33、S2-34、S6-06 依赖界面或浏览器工具，保持未执行。
- v1 仅 CNY；多币种不在本矩阵范围。
- **最权威的运行结论与命令原文**见 [S2 核心实现记录](<S2_CORE.md>) §4 与 B1 的 [运行记录](<S2_RUNTIME.md>)；矩阵状态只按已实际执行并留证据的项填写，**未跑部分一律未执行**。
- 各行的「通过」仅覆盖该行列出的断言；界面展示、异机、并发、备份与 S3–S6 能力不在本轮范围，不构成渠道或经营验证结论。
