# S2 核心实现记录（S2-B2）

> 任务：`task-82bf9fe8e1b233d133b1b9c2b0a62318`（S2-B2，执行者 session-2e7e3159-0ac8-53a2-a3ae-0c589fafdb87）。
> 依据：[数据与接口契约 v3](<CONTRACT.md>)（Flow 已验收冻结）；基线为已验收的 S2-B1（`task-829baf5647ea6a6f87a0ec5729abd80a`）。
> 记录时间：2026-10-09（UTC+8）。只写实际执行过的事实；未运行项明确标为未执行。
> B1 的运行证据在 [S2 运行与验证记录](<S2_RUNTIME.md>)（本轮未改动该文件）。

## 1. 结论摘要

- 本轮把 S2 核心闭环补齐：**四门槛写入口（§3.5 准入）**、**§3.4 同事务降级（成本/货源/证据入口 + recompute 物化）**、**§5.5 情景口径**、**草稿（template 独立可用）**、**经营反馈与事件更新白名单**、**复核队列处理**、**人工分池**，并新增迁移 0002（`draft`/`feedback`）。
- 状态派生两处修正已落地：所选货源 `last_checked_at` 超 30 天 → `expired`；阻断复核查询覆盖本候选子记录（供货/成本/证据/需求信号）。
- 实测：`python -m unittest discover -s tests -t .` → **78 项 OK，exit=0**；按文件 7/7/4/27/25/8 各自 exit=0；真实 HTTP 端到端（端口 5081–5084，独立临时库）`E2E_OK`，覆盖“导入 → 补证/成本 → 四门槛 → 情景 → 草稿 → 反馈 → 降级 → 重核 → 重启查询”。
- 未实现（属后续阶段）：来源自动采集与覆盖、货源匹配与排序权重、每日摘要与定时流水线、备份/部署/回归、界面（C）、以及 S4/S5 的摊销与实际利润核算。

## 2. 实现摘要（模块 ↔ 契约）

| 模块 | 覆盖契约 | 说明 |
| --- | --- | --- |
| `app/core/gates.py` | §3.2 TTL、§3.5 G1–G4、§3.4 降级 | 门槛核验写入口、`seq=max+1`、`expires_at=min(证据.expires_at ∪ verified_at+TTL)`、准入反证 422 details、`verified_by='user'`；系统降级行 `verified_by='system_rule'` 且只降级当前 `verified` 行 |
| `app/core/costs.py` | #26/#10、§3.4 | 追加/取代成本项；同 `(role,basis,variant)` 活跃项自动 `is_active=0`；同值提交不新增行；取代时继承 `supply_offer_id`/`source_evidence_id`（避免静默丢链） |
| `app/core/supplies.py` | #8/#9、§3.4 | 追加货源（强键命中 → 409）；更新货源：价格变化 → `cost_changed` + cost 门槛降级；许可/版本/依据变化 → `license_changed` + supply 门槛降级；`status='invalid'` → `supply_invalid` + 两门槛降级 |
| `app/core/evidence.py` | #6/#7、§3.4 | 追加证据（无摘录不建档；`demand` 类型自动关联最新未取代需求信号）；失效 → 引用该证据的已核验门槛降级 + `evidence_expired` 复核项 |
| `app/core/scenario.py` | §5.5 | per_order 已知才给 `contribution`；固定/周期为 0 且关键费用齐备才 `complete/net`；正额一次性或周期 → `net=null` + `fixed_cost_gap`；`unknown_components`/`assumptions`/`explanation` 显式；`sale_price` 不参与成本求和 |
| `app/core/drafts.py` | #16/#17 | template 模式独立可用（未核验内容用显式占位）；`model_assisted` 未配置模型 → 422；状态仅 `draft/final`；无发送路径 |
| `app/core/feedback.py` | #18/#27、§5.4 kind 表 | sale 快照由服务端生成（`net`，不完整时 NULL）；refund 必须关联同候选同 origin 的 sale 且 `order_ref` 相符；manual_time 可录入/更正人工字段；`predicted_*`/`actual_net`/`actual_complete` 客户端提交一律 422 |
| `app/core/reviews.py` | #14/#15/#21 | 复核队列、处理（不恢复已失效核验）、`recompute` 物化降级（幂等，重复运行不追加） |
| `app/core/candidates.py` | #12 | 人工分池（非 `none` 必须给原因） |
| `app/core/idempotency.py` | §0.7/§1.15/I15 | 统一幂等：同 `(scope,client_ref)` + 同载荷 → 重放并标 `deduplicated`；异载荷 → 409；记录与业务同事务 |
| `app/core/state.py` | §3.3 | 两处修正：货源 30 天 TTL → `expired`；阻断复核查询覆盖子记录 |
| `app/storage/migrations/0002_draft_feedback.sql` | §1.7/§1.8 | 新增 `draft`、`feedback` 两表与索引（含 sale 订单号唯一部分索引、kind 相关 CHECK）；0001 未被改动 |
| `app/api/routes.py` | #5–#18、#21、#26、#27 | 全部端点接线；统一事务包装（业务 + 幂等记录同事务）；`GET /api/health` 仅返回 `ok/schema_version/time` |

端点覆盖（契约 §5.3）：#1–#12、#14–#18、#20、#21、#23、#24、#26、#27 已实现；#13 合并、#19 每日摘要、#22 流水线、#25 备份属后续阶段/任务，保持 404 或未实现；页面路由 `/`、`/opportunity/<id>`、`/import`、`/ops` 维持 501 占位。

## 3. 关键规则实现细节

- **门槛准入（§3.5）**：`verified` 时才做准入检查，失败返回 `422 invalid_state` 且 `details` 逐字段给出缺口：G1 证据类型/来源/卖家宣传、G2 三项许可 + 抽检 + 条款证据（`no/unknown` 时提示例外路径：补 `license_scope_note` 与摘录、门槛保持待复核）、G3 未知角色 + 每行依据（`fact+source_evidence_id` 或 `assumption_note`）+ 采购行须绑定 G2 所选货源、G4 平台/版本匹配。
- **有效期（§3.2）**：`expires_at = min(证据.expires_at, verified_at + 门槛 TTL)`，TTL 为 demand 90 / supply 30 / cost 30 / platform 180 天；`min` 忽略 NULL。
- **降级（§3.4）**：所有降级入口共用 `append_downgrade`——仅当该门槛当前行 `status='verified'` 时追加 `seq=max+1`/`expired`/`system_rule`，并写幂等复核项（`status='open'` 未决唯一）；当前行已是 `expired` 或相同语义值重放时不追加。`recompute` 用同一函数物化，`GET` 保持零副作用（测试断言读前后行数一致）。
- **情景（§5.5）**：`contribution = sale_price − Σper_order(已知)`，仅当全部 per_order 角色已知；`complete` 还需固定/周期成本为 0 且无未知项；正额一次性/周期给 `fixed_cost_gap_minor`；`amortize_orders` 固定为 null（S4）；周期非 monthly 时不输出伪月额。
- **反馈（§1.8/§5.4）**：sale 写入 `predicted_net_per_order_minor`（情景 `net`，不完整则 NULL）与 `predicted_snapshot_at`；此后任何路径拒改（PATCH 白名单外/预测字段 → 422）；`actual_net_per_order_minor`/`actual_complete` 保持 NULL。
- **幂等（§0.7）**：`payload_hash = sha256(scope + 规范化 JSON)`；导入沿用文件内容哈希；被拒批次不写幂等记录，因此改正后可用同一 `client_ref` 重试（实测）。

## 4. 实测证据（本轮实际运行）

命令（`.venv\Scripts\python.exe` 全路径调用，`PYTHONUTF8=1`）：

| 命令 | 结果 | 退出码 |
| --- | --- | --- |
| `python -X utf8 -m unittest discover -s tests -t .` | `Ran 78 tests … OK` | 0 |
| `python -X utf8 tests\core\test_money.py` | 7 项 OK | 0 |
| `python -X utf8 tests\core\test_identity.py` | 7 项 OK | 0 |
| `python -X utf8 tests\storage\test_migrations.py` | 4 项 OK（schema v2） | 0 |
| `python -X utf8 tests\api\test_import_api.py` | 27 项 OK | 0 |
| `python -X utf8 tests\api\test_gates_scenario.py` | 25 项 OK | 0 |
| `python -X utf8 tests\api\test_feedback_draft.py` | 8 项 OK | 0 |
| `python -X utf8 tests\api\b2_e2e.py http://127.0.0.1:508x`（真实 HTTP，重启前后各一次） | `E2E_OK`（详见下） | 0 |

真实 HTTP 端到端决定性输出（脚本 `tests/api/b2_e2e.py`，独立临时库 `tests/api/_tmp/b2e2e/app.db`；`netstat` 确认 `TCP 127.0.0.1:508x … LISTENING`）：

- `GET /api/health` → 200，键集合 `["ok","schema_version","time"]`，`schema_version=2`（按策划者 steer 已去掉 `stage` 与绝对 `db_path`）。
- `POST /api/imports`（正例行）→ 201；四个门槛依次核验：demand/supply/cost/platform 均 200，`seq=1`，`expires_at` 分别为 +90/+30/+30/+180 天；末次返回 `candidate_status="testable"`。
- 反证：`platform_policy` 用 `applies_to_version="v9"`（与所选货源 v1 不符）→ **422**，`details` 含 `applies_to_version`。
- 情景：修正前 `complete=true`、`known_subtotal=850`、`contribution=150`、`net=150`、`unknown_components=[]`；平台费率更正为 600bp 后 `known_subtotal=860`、`contribution=140`（证明 `sale_price` 不参与成本求和、费率按 bp 重算）。
- 降级：`POST /api/cost-items/{id}/supersede` → 200 且 `gate_downgraded=true`；随后 `cost` 门槛为 `expired`、候选 `stale`、存在未决 `cost_changed` 复核项；重新核验 `cost`（`seq=3`）后处理复核项 → `derived_status=testable`。
- 草稿：template 201，`template_version=v1`，正文含显式占位；反馈：sale 201，`predicted_net_per_order_minor=140`，改写尝试（PATCH 预测字段）→ **422 invalid_field**；重启后再查：`gates` 全 `verified`、`derived_status=testable`、drafts/feedback 仍在。

## 5. 验收矩阵映射（本轮实际执行的行）

| 矩阵行 | 对应实测 |
| --- | --- |
| S2-14 六例反证 | `test_supply_gate_rejects_licence_and_sample_gaps`（resale=no、commercial=no、sample=none）、`test_cost_gate_rejects_unknown_roles_and_ungrounded_rows`（payment_fee NULL、无 manual_labor）、`test_platform_gate_version_must_match_selected_supply`（其他平台与其他版本） |
| S2-15 / S2-18 / S2-21 | `test_expiry_by_evidence_expires_and_resequences`（过期 → 只读零副作用 → recompute 物化 → `seq+2` 重核）、`test_same_second_supersede_downgrades_cost_gate`（dismiss 不恢复） |
| S2-16 | `test_supply_ttl_degrades_supply_and_cost_gates`（30 天 TTL → 两门槛降级 + `supply_invalid`） |
| S2-17 | `test_four_gates_make_candidate_testable_with_ttls`、`FullChainTest.test_end_to_end_chain_and_restart` |
| S2-19 / S2-20 / S2-21 | `test_loss_snapshot_and_negative_derived_value`（−750 快照可存）、`test_contribution_800_case`、`test_buyout_nulls_net_and_reports_gap` |
| S2-24 | `DraftTest.test_template_draft_works_without_a_model`（含 `status=final`、退回 422、`/send` 404） |
| S2-25 / S2-26 | `FeedbackTest` 四个用例（快照冻结、退款规则、人工时间、白名单与 422 明细） |
| S2-27 | `test_gate_write_idempotency_and_override`、`test_rejected_import_leaves_no_idempotency_record`、`test_idempotency_survives_restart`（B1） |
| S2-28 八步 | `test_same_second_supersede_downgrades_cost_gate`（①②③④⑤）、`test_import_price_change_downgrades_without_new_cost_row`（⑥）、`test_validate_mode_never_materializes_downgrade`（⑦）、`test_atomic_rollback_undoes_downgrade`（⑧） |
| S2-30 | `FullChainTest.test_end_to_end_chain_and_restart` + `b2_e2e.py` 真实 HTTP 全链 |
| S2-03 / S2-12 / S2-13 | `test_example_scenario_190_and_g3_needs_grounding`（38 列正例 → 190/complete、10 条成本项、G3 因无说明 422）、`test_unknown_components_never_inferred_as_zero`、`test_four_candidate_groups_stay_pending`（B1） |
| S2-22 | `test_no_purchase_or_payment_endpoints`（采购/付款端点 404） |

## 6. 与契约文本的差异与实现层解释

1. **身份命名空间用已登记来源名**（`n:xianyu:1001`、`u:xianyu:<url_norm>`），与 §4.7 示例与矩阵 S2-05 一致；§4.5 已按策划者要求加括注说明，数据库仍保留 `source.id` 外键。
2. **`fact_kind='assumption'` 且无 `assumption_note` 的成本行允许入库**：§4.3 明示该行“视为假设未说明、不构成 G3 依据”，因此该要求实现为**门槛准入规则**而非 DB CHECK；G3 会逐行给出 422 缺口。
3. **`import_batch.status` 无 `running`**：批次行在同一事务内先写占位值、提交前改写为最终状态。
4. **批次 counts 与记录级动作是两个层级**：`import_batch.rows_*` 是**行级聚合计数**，而“需求侧 `duplicate_skipped`”是 **`import_row_result` 的记录级动作**（同一行可既有 `created` 记录又有 `duplicate_skipped` 子记录，V17）。断言必须按层级选择，不能互相替代。
5. **情景的成本匹配范围（§5.5-7 的实现）**：本候选**无有效货源**时，普通成本行参与计算（否则 §5.5 例 A/B 无法成立）；存在货源时只接受绑定到**选定货源**的行，指向其他货源或未绑定的行不计入（未绑定即视为未匹配）。
6. **选定货源的回退**：优先取**当前**（`seq` 最大且仍有效）的 `supply_distribution` 核验所指向货源；若该行已 `expired`/`failed`（含证据失效、货源超 30 天 TTL），则不再冒充当前选择；此时若本候选恰有唯一有效货源，`selected_supply_id` 仍返回它作为**纯情景计价估算**（`has_supply` 时成本行需绑定该货源），但**G3/G4 核验一律要求当前存在已核验的 G2**，估算不升级门槛（task-639aeee9 收紧，见 §9）。
7. **`cost_item.supply_offer_id` 的写入范围比契约文字更宽**：当前实现中费率行与人工行同样写入该字段（正例 10/10 行全部关联），比契约“采购/单价类行建议填写”的文字更宽；属可接受的实现（计算与 G3 仍按契约只对采购行要求绑定），**不要据此写“仅采购类才有该字段”的断言**。
8. **`demand` 证据自动关联**：`POST /evidences` 未显式给 `demand_signal_id` 时，自动关联本候选最新未取代的需求信号（1:1 唯一），使 G1 可在一次调用内满足；其他类型证据不受影响。
9. **取代成本项继承上下文**：`supersede` 未显式提供时继承旧行的 `role/basis/variant/currency/supply_offer_id/source_evidence_id`，避免“只改一个数值”就把货源绑定丢掉（该行为在实测中暴露出必要性：继承前情景会因失去绑定而变成未知）。
10. **契约 §5.5 例 B 已裁定并补正文字**：原问题（例 A 逐单输入给出 `contribution = 150`，例 B 却写“同上但一次采购 10000 → 450”，与“一次性成本不进入逐单贡献值”的规则冲突）由策划者裁定为**文字表述问题**——例 B 的原意是“采购改为一次性 10000（不再有逐单采购）”，此时逐单成本仅平台 50 与人工 500，`contribution = 1000 − 550 = 450`，与摊销示例 `450 − 500 = −50`（10000 ÷ 20 单）自洽。契约 §5.5 例 B 已按此原意补正（见 CONTRACT §5.5 例 B）；**实现按规则计算，无代码变更**。原问题记录出处：本清单上一版本条目与提交流水中的“§5.5 例 B 数值待裁定”。
11. **页面路由保持 501 占位**：模板由 C 交付，当前不构成可用界面。

## 7. 未覆盖与限制

- 未实现：`POST /api/candidates/{id}/merge`（#13）、每日摘要（#19）、手动流水线（#22）、备份（#25）、来源自动采集与 `search_coverage`、货源匹配与排序权重、S5 运行费用台账与预算保护、S5 实际利润核算、浏览器界面。
- 未做的验证：浏览器渲染与键盘可用性、异机访问（无第二台主机，按约定留空）、并发与压力、故障注入、备份恢复流程、真实渠道数据核验。
- 环境事实：仅 `.venv` 内 Flask 3.1.3（唯一新增依赖）；服务默认 `127.0.0.1:5000`，本轮 E2E 用 `APP_PORT=5081–5084` 避开占用；时区以固定 +08:00 实现（Windows 无系统 tzdata）。
- 数据事实：全部测试与 E2E 使用示例域合成数据与独立临时库；业务库未迁移、未被测试写入。

## 8. 复跑指引

```powershell
$env:PYTHONUTF8='1'
$py = ".\.venv\Scripts\python.exe"

# 全量（含 discover，对应 T-07）
& $py -X utf8 -m unittest discover -s tests -t .

# 真实 HTTP 端到端（隔离库/端口，不触碰 instance\app.db）
& .\instance\_e2e.ps1                        # 默认 5091；占用或路径越界即报错退出
& $py -X utf8 tests\api\test_gates_scenario.py
```

## 9. 边界修正（task-639aeee9a8f8365c4b4e06c0dfcc4cc7）

策划者静态追踪的三处疑点全部复现并修复；先写测试、在隔离库跑失败基线，再改代码。

### 9.1 根因与修复

| 编号 | 根因（修复前行为） | 修复 | 定点 |
| --- | --- | --- | --- |
| A | `scenario.py` 的 `complete` 用 `recurring_total in (0, None)` 判定，而 `recurring_total` 只在“全部 recurring 行为 monthly”时才计算 → **quarterly/yearly 正额周期成本被当成 0**，候选被误判 `complete=true`、`net` 给出虚假净收益 | 完整性改为独立检查**原始周期行**：仅当存在 recurring 行且每行 `money_minor == 0`（显式已知 0）才 `complete`；月额字段仍仅在全部行 monthly 时给出；`fixed_cost_gap_minor` 在单一周期时等于原金额、周期不一致时为 `null`，并补说明（非月度不归一、不给伪月额） | `app/core/scenario.py` §5.5-2/-4 |
| B | `_check_supply` 准入时用 `supply.license_evidence_id` 兜底条款证据，但 `record_gate` 只落 `payload.evidence_id` → **默认关联丢失**：核验行 `evidence_id=NULL`、TTL 不取证据有效期，事后 `invalidate` 该证据也无法触发降级 | 新增 `_resolve_context`：先解析实际核验证据/货源，再**同源**用于准入、TTL min、落库与响应（响应也回传 `evidence_id`/`supply_offer_id`）；`_evidence_row` 增加“已失效/已过期证据不得支撑 verified”检查 | `app/core/gates.py` §3.2/§3.5 |
| C | `_check_cost`/`_check_platform` 用 `payload.supply_offer_id or selected_supply_id(...)` 作基准，且 `selected_supply_id` 只搜历史 `verified` 行 → **G3/G4 可被 payload 改写成另一货源**，历史 verified 也会在更晚的 expired/failed 之后继续充当“当前选择” | 新增 `state.current_gate_supply`（取 `seq` 最大行并按有效性判定）；`_gate_reference_supply` 统一 G3/G4 基准：**必须当前 G2 有效已核验**，传入货源与当前 G2 不一致或不属于本候选 → `422`；`selected_supply_id` 改为“当前有效 G2 → 否则唯一有效货源（仅情景估算）” | `app/core/{gates,state,scenario}.py` §3.3/§3.5/§5.5-7 |

### 9.2 实测（隔离库；命令与退出码）

| 步骤 | 命令 | 结果 |
| --- | --- | --- |
| 失败基线（修前） | `python -X utf8 tests\api\test_gates_scenario.py -v` | `Ran 41 tests … FAILED (failures=11, errors=2)`，**exit=1**；日志 `tests\api\_tmp\s2_boundaries\evidence\baseline_test_gates_scenario.txt` |
| 修后单文件 | 同上 | `Ran 41 tests … OK`，**exit=0**；日志 `…\evidence\after_fix_test_gates_scenario.txt` |
| 全量回归 | `python -X utf8 -m unittest discover -s tests -t .` | `Ran 107 tests … OK`，**exit=0**；日志 `…\evidence\full_suite_after_fix.txt` |
| 隔离端到端 | `& .\instance\_e2e.ps1` | `RESULT PASS`、`E2E_OK`，**exit=0**，`business_db_unchanged=True`；日志 `…\<run>\http_e2e.txt` |
| 边界守卫 | `& .\instance\_e2e.ps1 -WorkRoot "instance"` / `-Port <占用>` | 均被拒绝并给出明确原因（退出非零），业务库哈希不变 |

最小输入与期望/实际（修前 → 修后）：
- `quarterly=10000`（逐单全已知、`one_time=0`）：期望 `complete=false`/`net=NULL`/月额 NULL → 修前 `complete=true`、`net=150`（误判），修后 `complete=false`、`net=NULL`、`fixed_cost_gap=10000` 且 `recurring_detail` 保留原周期与金额。
- `quarterly=0` 与 `yearly=0`：期望可完整 → 修后 `complete=true`、`net=150`，月额字段仍为 `null`（非全 monthly）。
- G2 省略 `evidence_id` + 条款证据 5 天后到期：期望核验行 `evidence_id=<条款证据>`、`expires_at=<5 天后>` → 修前落库为 `NULL`/30 天，修后与期望一致；随后 `invalidate` 该证据 → 核验行同事务降级为 `expired`、读取不写入、`recompute` 幂等（`downgraded=0`）。
- G2 已选 A 后传 B（同候选）/ 传跨候选货源 / 无有效 G2：期望 `422` → 修前分别返回 200/422(原因错)、200，修后三次均 `422` 且 `details` 给出 `supply_offer_id` 原因。
- 历史 verified 被更晚失效覆盖：期望不冒充当前选择 → 修前按旧 verified 继续匹配，修后 `selected_supply_id=None`（两个有效货源）且 G3 拒绝。

失败写原子回滚：准入失败时 `gate_review`/`review_item`/`candidate.status` 计数与内容均不变（`test_failed_gate_write_leaves_no_partial_row`）。

### 9.3 边界脚本（D）

`instance/_e2e.ps1` 改为隔离运行：每次在 `tests\api\_tmp\s2_boundaries\e2e_<时间戳>_<GUID8>\` 写入独立 `app.db`/`input.csv`/`http_e2e.txt`；`APP_DB_PATH`/`APP_PORT` 只对子进程生效并在 `finally` 恢复；只停止自己启动的 PID；任何 HTTP 状态或计数不符均以非零退出（`$ErrorActionPreference='Stop'` + 显式断言）；`instance\http_e2e.txt` 为历史捕获，脚本不再改写；运行前后对比 `instance\app.db`（及 wal/shm）SHA256 并在日志中记录。

路径守卫（返工轮收紧，消除前缀同命中）：
- 统一为**一个判断函数** `Resolve-IsolatedPath`：先 `GetFullPath` 规范化（`..` 在规范化阶段即被解析），再只接受**隔离根自身**或**隔离根 + 目录分隔符**下的子路径——比较时把分隔符计入，`tests\api\_tmp\s2_boundaries_extra` 这类同级前缀不再通过；WorkRoot、run 目录、run 数据库三处共用同一判断。指向 `instance/` 的路径一律拒绝。全部检查在**任何目录/文件创建之前**执行。
- run 目录唯一化：id 为 `e2e_<秒级时间戳>_<GUID 前 8 位>`，且用 `New-Item -ItemType Directory`（**不带 `-Force`**）独占创建，避免同秒复用旧库。

守卫与唯一性实测（子进程退出码，日志 `tests/api/_tmp/s2_boundaries/evidence/guards_rework.txt`）：

| 输入 | 结果 |
| --- | --- |
| `-WorkRoot "tests\api\_tmp\s2_boundaries_extra"`（相似前缀） | **exit=1**，报“must be the isolation root itself or a path under it”，且运行后该目录仍不存在 |
| `-WorkRoot "tests\api\_tmp\s2_boundaries\..\s2_boundaries_extra"`（`..` 越界） | **exit=1**，同上，未创建任何目录 |
| `-WorkRoot "instance"` | **exit=1**，拒绝指向业务库目录 |
| 默认 WorkRoot（隔离根自身） | `RESULT PASS`、**exit=0**，目录 `e2e_20261009_230547_0fc454e2` |
| `-WorkRoot "tests\api\_tmp\s2_boundaries\sub"`（root+分隔符子路径） | `RESULT PASS`、**exit=0**，目录 `e2e_20261009_230602_56db1242` |

两次运行目录名不同（`dirs_differ=True`），证明独立库/日志不复用；三次越界调用后 `tests\api\_tmp\s2_boundaries_extra`、`..._ext`、`instance\s2_boundaries` 均不存在，`instance\app.db` SHA256 前后一致（`E073F828CF0F30D6206361BBA3A729826BE096BE3308F5A5DC204406DAE4EB85`，wal/shm 均 MISSING），无残留 `python -m app` 进程。
