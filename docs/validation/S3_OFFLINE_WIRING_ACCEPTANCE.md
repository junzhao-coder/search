# S3 离线接线与 S4 情景子集 验收证据归档（含证据边界校准）

> 归档人：执行者 C（`session-48004521-daf2-548c-a355-487cc6de6e72`）｜任务：`task-3d4b86d404975f53b272395c15d4e43e`（revision 2，计划 v2）
> 归档观测时点：Flow revision `1639`（派发快照）；文内各批次结论均带各自 runID 时点。本文档**只做证据整理与边界校准**，不重跑任何测试、不修改任何实现/测试/契约/迁移/根台账/旧证据。
> 说明：本文档的"已通过"仅指**该批在该时点、该命令、该退出码下**的结果；未执行/未覆盖项一律标注，不标 PASS，也不由任务状态推断测试结论。

## 1. 输入版本与冻结哈希（本次归档核对）

| 文件 | 冻结 SHA256（权威值） | 本报告核对结果 |
| --- | --- | --- |
| `app/sources/wiring.py` | `bafcf3974cbfb3ed4da99936e5d65d10d6f02c663b6325008255b4eaecc0da05` | 与各批 `01_frozen_hashes.json` 记录一致 |
| `tests/sources/test_wiring_offline.py` | `c66d72ee36f7697c105a87934784a0abb552ae4bdf8c5c60ad7179c4c264da4f` | 同上 |
| `app/core/importer.py` | `a11eaf4d39541ac11459eb1cebb8586f4922838b96714d7f7f3d2e253cff51a1` | 同上 |
| `app/sources/bilibili_view.py` | `b0dc0ced1bc3be3eca85116559d5acae52f7753dca1dcbbac259e573cc73f98e` | 同上 |
| `tests/api/test_import_api.py` | `251fff5fbc734f4b52a7ed092df2702c8aa0027d4daba056058856344b9b3633` | 同上 |

- 各批冻结核对原件：[v1 evidence/01_frozen_and_disputed_hashes.json](<../../tests/acceptance/_tmp/s3_wiring_recheck_v1/run_20261015_222105_wire/evidence/01_frozen_and_disputed_hashes.json>)、[v1 evidence/11_frozen_rework_and_fix_verify.json](<../../tests/acceptance/_tmp/s3_wiring_recheck_v1/run_20261015_222105_wire/evidence/11_frozen_rework_and_fix_verify.json>)、[v2 evidence/01_frozen_hashes.json](<../../tests/acceptance/_tmp/s3_wiring_recheck_v2/run_20261015_230108_v2a/evidence/01_frozen_hashes.json>)、[v3 evidence/11_frozen_rework_and_fix_verify.json](<../../tests/acceptance/_tmp/s3_wiring_recheck_v3/run_20261015_231803_v3/evidence/11_frozen_rework_and_fix_verify.json>)、[v5 evidence/01_frozen_hashes.json](<../../tests/acceptance/_tmp/s3_wiring_recheck_v5/run_20261016_121158_v5b5dc/evidence/01_frozen_hashes.json>)。
- 本报告的**独立哈希复算**记录：[archive 02_hash_recheck.json](<../../tests/acceptance/_tmp/s3_wiring_archive_v1/02_hash_recheck.json>)（本次实际执行，非静态阅读）。

## 2. 逐项证据地图（实现自测 / 独立验证 / 策划 accept 三层分列）

| 项 | 实现或设计侧（自测） | 独立验证（原件路径 + 真实 exit） | 时点 |
| --- | --- | --- | --- |
| 零网络与无新端点 | B 实施记录：[S3_WIRING_SPEC §11](<../design/S3_WIRING_SPEC.md>)（task-665f3cd3） | v1：[06_zero_network.json](<../../tests/acceptance/_tmp/s3_wiring_recheck_v1/run_20261015_222105_wire/evidence/06_zero_network.json>)（4/4，socket 禁用下 import 成功、外呼尝试 0、route_count=23 无 wiring 专用端点）exit=0 | 2026-10-15 22:21 run |
| S4 情景子集不退化 | B/A 实施记录 | v1：[05_s4_method_exit_map.log](<../../tests/acceptance/_tmp/s3_wiring_recheck_v1/run_20261015_222105_wire/evidence/05_s4_method_exit_map.log>)（**6 个方法各 exit=0**，按方法名逐条索引；不额外编造断言结果）＋ [12_full_discover.log](<../../tests/acceptance/_tmp/s3_wiring_recheck_v1/run_20261015_222105_wire/evidence/12_full_discover.log>)（`Ran 217 tests … OK`、`EXIT=0`；同一日志另有 `DeprecationWarning`（`datetime.utcnow`）与 PowerShell `NativeCommandError` 包装 —— **warnings 不等于测试失败，也不称"零警告"**） | 2026-10-15 22:21 run |
| ② 零新增与可判别告警 | 库级规则：`_RECORD_KEYS` 白名单与 stray 判别（[S3_WIRING_SPEC](<../design/S3_WIRING_SPEC.md>)） | **HTTP**：v5 [07_02a_http_clean.json](<../../tests/acceptance/_tmp/s3_wiring_recheck_v5/run_20261016_121158_v5b5dc/evidence/07_02a_http_clean.json>)（7/7，`201`+`created=1`、响应与行结果无丢弃/未知字段告警、`counts.warning=0`、`supply_offer`/`cost_item`/`gate_review` 计数+行哈希前后一致）exit=0；**库级**：v5 [08_02b_build_row_strays.json](<../../tests/acceptance/_tmp/s3_wiring_recheck_v5/run_20261016_121158_v5b5dc/evidence/08_02b_build_row_strays.json>)（5/5，恰一条 `S3_UNKNOWN_FIELDS` 且点名集合恰为越权键）exit=0 | 2026-10-16 12:11 run |
| ③ 两阶段 URL | 设计 §3 字段映射 | v2 [03_two_stage_url.json](<../../tests/acceptance/_tmp/s3_wiring_recheck_v2/run_20261015_230108_v2a/evidence/03_two_stage_url.json>)（16/16）＋ [03b_rejection_isolation.json](<../../tests/acceptance/_tmp/s3_wiring_recheck_v2/run_20261015_230108_v2a/evidence/03b_rejection_isolation.json>)（10/10）均 exit=0 | 2026-10-15 23:01 run |
| ④ 观察时间保真 | 设计 §4.5 内部注入 | v2 [04_observed_at.json](<../../tests/acceptance/_tmp/s3_wiring_recheck_v2/run_20261015_230108_v2a/evidence/04_observed_at.json>)（34/34）exit=0 | 2026-10-15 23:01 run |
| ⑤ 强键与旧证据效力 | 导入管线去重/版本规则（[CONTRACT](<../design/CONTRACT.md>) §4.5/§4.6） | v5 [09_05_http_chain.json](<../../tests/acceptance/_tmp/s3_wiring_recheck_v5/run_20261016_121158_v5b5dc/evidence/09_05_http_chain.json>)（10/10）exit=0 | 2026-10-16 12:11 run |
| ⑥ 事务失败审计 | 设计 §4 事务与审计 | v2 [06_txn_failure_audit.json](<../../tests/acceptance/_tmp/s3_wiring_recheck_v2/run_20261015_230108_v2a/evidence/06_txn_failure_audit.json>)（24/24，含 `sqlite3.IntegrityError` 注入回滚）exit=0；v1 另有 [22_txn_failure_audit.json](<../../tests/acceptance/_tmp/s3_wiring_recheck_v1/run_20261015_222105_wire/evidence/22_txn_failure_audit.json>) 同题记录 | 2026-10-15 23:01 run |
| ⑦ 计数口径 | 设计 §4 | v2 [07_counts.json](<../../tests/acceptance/_tmp/s3_wiring_recheck_v2/run_20261015_230108_v2a/evidence/07_counts.json>)（15/15）exit=0 | 2026-10-15 23:01 run |
| ⑧ 状态不升级 | 设计 §5 | v2 [08_status_no_escalation.json](<../../tests/acceptance/_tmp/s3_wiring_recheck_v2/run_20261015_230108_v2a/evidence/08_status_no_escalation.json>)（11 PASS + 1 UNEXECUTED，verdict=PASS_WITH_UNEXECUTED）exit=0；同候选取真驱动覆盖见 [08b](<../../tests/acceptance/_tmp/s3_wiring_recheck_v2/run_20261015_230108_v2a/evidence/08b_testable_not_downgraded.json>)（14/14）、[08c](<../../tests/acceptance/_tmp/s3_wiring_recheck_v2/run_20261015_230108_v2a/evidence/08c_testable_attach.json>)（18/18） | 2026-10-15 23:01 run |
| ⑩ 镜像内 HTTP E2E 与运行后守护 | `instance/_e2e.ps1`（实现者脚本，镜像内克隆） | v5 [11_10_e2e_mirror_cmd.log](<../../tests/acceptance/_tmp/s3_wiring_recheck_v5/run_20261016_121158_v5b5dc/evidence/11_10_e2e_mirror_cmd.log>)（`RESULT PASS`、exit=0；**两个自启 PID 均已停止**：`server1_stopped pid=119048`、`server2_stopped pid=106084`；其 `business_db_unchanged=True` 比较的是**镜像内** `instance/app.db`＝`MISSING→MISSING`，**不是 live 业务库**）＋ 运行后守护 [10_guard_after.json](<../../tests/acceptance/_tmp/s3_wiring_recheck_v5/run_20261016_121158_v5b5dc/evidence/10_guard_after.json>)（**状态快照，本体无 `checks` 数组**）+ 汇总 [10_guard_after_result.json](<../../tests/acceptance/_tmp/s3_wiring_recheck_v5/run_20261016_121158_v5b5dc/evidence/10_guard_after_result.json>)（唯一的 5/5 断言汇总在这里，不把汇总当作快照内的 5 条断言） | 2026-10-16 12:11 run |
| 加固/前置批次（不冒充 HTTP） | — | v3：[01_v3_mirror_build.log](<../../tests/acceptance/_tmp/s3_wiring_recheck_v3/run_20261015_231803_v3/evidence/01_v3_mirror_build.log>)、[11_frozen_rework_and_fix_verify.json](<../../tests/acceptance/_tmp/s3_wiring_recheck_v3/run_20261015_231803_v3/evidence/11_frozen_rework_and_fix_verify.json>)、[enumeration_reconciliation.py](<../../tests/acceptance/_tmp/s3_wiring_recheck_v3/run_20261015_231803_v3/enumeration_reconciliation.py>)；仅镜像/冻结/守护与起点清单，**不作 HTTP 结论** | 2026-10-15 23:18 run |

- 逐项细节映射（各批自述）：v2 [12_five_item_map.md](<../../tests/acceptance/_tmp/s3_wiring_recheck_v2/run_20261015_230108_v2a/evidence/12_five_item_map.md>)、v5 [12_three_item_map.md](<../../tests/acceptance/_tmp/s3_wiring_recheck_v5/run_20261016_121158_v5b5dc/evidence/12_three_item_map.md>)、v5 [13_exit_map.json](<../../tests/acceptance/_tmp/s3_wiring_recheck_v5/run_20261016_121158_v5b5dc/evidence/13_exit_map.json>)、v1 断点交接 [17_handoff_remaining_items.md](<../../tests/acceptance/_tmp/s3_wiring_recheck_v1/run_20261015_222105_wire/evidence/17_handoff_remaining_items.md>)。
- 任务层状态（**本次归档以 `view=task` 只读核对；状态只作协作事实，不由状态推断测试结论，也不推断容量原因**）：

| 任务（完整 taskId） | 最新已读 revision / status | 结论出处（已验收/未验收） |
| --- | --- | --- |
| B 实施 `task-665f3cd3865b5880602a5e8d759c2d37` | 4 / completed | 策划验收（派发上下文与本文档 §4 时间线） |
| B stray 返工 `task-8f54daee876a13217f26fd017f712fc6` | 4 / completed | 同上；修复实测见 [S3_WIRING_SPEC §11.5](<../design/S3_WIRING_SPEC.md>) 与 fix_v1 日志 |
| B 记录更正 `task-75a2bc58f6e780f28ac20068e7ffc7ab` | 4 / completed | 策划验收 |
| A 离线验证 `task-3d96b6c9be76717be90b6ee6e343ec4f` | 4 / completed | 策划验收（v2 批次为其产出） |
| C HTTP 验证 `task-f9e04d3c49654af5547c2eb7150e5429` | 4 / completed | 策划验收（v5 批次为其产出） |
| D 综合验证 `task-bb9ea780af12a6356670be3d918cbc03` | **19 / paused**（本次实测 `hasSubmission=false`） | **该任务从未 submit**；其 v1 证据是**部分证据**，归档这些原件 ≠ 替该任务 accept |
| D HTTP `task-97b273b2f52e4d1e3117d212707f4a3d` | 7 / paused | 替代分批保留的历史，未验收 |
| A HTTP `task-bd8eb4ebb34b18f5bc51a7eccbcb0926` | 3 / paused | 替代分批保留的历史，未验收 |

## 3. 库级 vs HTTP 分界（显式）

- **HTTP 面**：`POST /api/imports`（`app/api/routes.py` 169–207）只接受 `fmt/body/filename/mode/format_version/client_ref`；**不暴露** `run_source_id` / `internal_observation`，也**不新增** wiring 专用端点。
- 因此 **② 的越权键判别只能走库级 `build_row`**（v5 `08_02b`），**不视为未覆盖**；其有效交叉引用（补 [v5 `08_02b_build_row_strays.json`:47](<../../tests/acceptance/_tmp/s3_wiring_recheck_v5/run_20261016_121158_v5b5dc/evidence/08_02b_build_row_strays.json>) 中 `library_level_cross_refs: []` 为空之处；该字段位于 `08_02b` JSON，**不在** `13_exit_map.json`）：
  1. 真实缺陷与修复记录：[S3_WIRING_SPEC §11.5](<../design/S3_WIRING_SPEC.md>)；
  2. 修复前逐字证据（缺陷复现）：[v1 evidence/09_wiring_strays.log](<../../tests/acceptance/_tmp/s3_wiring_recheck_v1/run_20261015_222105_wire/evidence/09_wiring_strays.log>)；
  3. 修复后逐字对照：[fix_v1 41_warnings_verbatim.log](<../../tests/sources/_tmp/s3_wiring_fix_v1/run_20261015_223500_fixb/41_warnings_verbatim.log>)（`clean_record_keys=21`、`clean_strays=[]`、`clean_warnings=[]`；越权样本 `violation_strays=['gate_cost','procurement_unit_cost','supply_price','supply_url']`、恰 1 条同名告警）。
- **HTTP 侧的零新增结论**（v5 `07_02a`）与**库级判别**（v5 `08_02b`）是两件事，报告与提交均分列，不互相替代。

## 4. 失败 → 修正时间线（真实实现缺陷 与 探针缺陷 必须分列）

1. **真实实现缺陷 A（接线前置，历史归属）**：ABA 版本语义问题，见 [S3_WIRING_SPEC §4.4「已实跑证实的功能 FAIL（接线前置修复）」](<../design/S3_WIRING_SPEC.md>)。
2. **真实实现缺陷 B（stray 误告警，本轮最重要的真缺陷）**：D 在 v1 独立实测发现——真实 `BilibiliViewReader` 干净成功返回 **21 键**，而当时 `_RECORD_KEYS` 仅 **12 键**，strays 恒为 10 键 ⇒ **每次干净成功都会写一条误导性 `S3_UNKNOWN_FIELDS`**；逐字证据 [v1 evidence/09_wiring_strays.log](<../../tests/acceptance/_tmp/s3_wiring_recheck_v1/run_20261015_222105_wire/evidence/09_wiring_strays.log>)，记录见 [S3_WIRING_SPEC §11.5](<../design/S3_WIRING_SPEC.md>)。B 在 `task-8f54daee…` 修复：修复后 [30_wiring_offline.log](<../../tests/sources/_tmp/s3_wiring_fix_v1/run_20261015_223500_fixb/30_wiring_offline.log>) 21 OK、[38_discover.log](<../../tests/sources/_tmp/s3_wiring_fix_v1/run_20261015_223500_fixb/38_discover.log>) `217 OK exit=0`、[41_warnings_verbatim.log](<../../tests/sources/_tmp/s3_wiring_fix_v1/run_20261015_223500_fixb/41_warnings_verbatim.log>) 逐字对照、[39_isolated_e2e_mirror.log](<../../tests/sources/_tmp/s3_wiring_fix_v1/run_20261015_223500_fixb/39_isolated_e2e_mirror.log>) E2E exit=0。
   - **该日志本身是"混合结果"，不得整份单一归因**：`:21–22` 是**真实实现缺陷的两条 FAIL 断言**（干净成功 21 键 vs `_RECORD_KEYS` 12；`observed_at`/`observed_at_source` 被实现消费却按 strays 告警）、`:23` 是判别性 **PASS**（越权记录相对干净**多出** `gate_cost, procurement_unit_cost, supply_price, supply_url` 4 键）、`:24–39` 是**探针自身**的 `sorted()` TypeError 崩溃、`:41` `EXIT=1` 为**上述两者叠加**。
   - 结论口径：**"所有 FAIL 都是探针问题"是错的**；本项是真实实现缺陷，且**不得**被后续 A/C 批次的探针缺陷叙述覆盖。217 回归日志（`Ran 217 tests … OK`／`EXIT=0`）另有 `DeprecationWarning`（`datetime.utcnow`）与 `ResourceWarning`／PowerShell `NativeCommandError` 包装：**warnings 不等于失败，也不称"零警告"**。
3. **探针缺陷（后续批次，与实现无关）**：A v2 自述 [11_attempts_chain.md](<../../tests/acceptance/_tmp/s3_wiring_recheck_v2/run_20261015_230108_v2a/evidence/11_attempts_chain.md>)（③三次/③b/④两次/⑧三次/⑧b两次，全部为探针错误）；C v5 三次 attempt1 失败均留档：[07_02a_http_clean_attempt1_marker_overreach_FAIL.json](<../../tests/acceptance/_tmp/s3_wiring_recheck_v5/run_20261016_121158_v5b5dc/evidence/07_02a_http_clean_attempt1_marker_overreach_FAIL.json>)、[09_05_http_chain_attempt1_expectation_overreach_FAIL.json](<../../tests/acceptance/_tmp/s3_wiring_recheck_v5/run_20261016_121158_v5b5dc/evidence/09_05_http_chain_attempt1_expectation_overreach_FAIL.json>)、[10_guard_after_attempt1_dict_overreach_FAIL.json](<../../tests/acceptance/_tmp/s3_wiring_recheck_v5/run_20261016_121158_v5b5dc/evidence/10_guard_after_attempt1_dict_overreach_FAIL.json>)。旧 FAIL 史一律保留，不改写。

## 5. 守护口径与观测时点（各批不能混算）

| 批 | runID（时点） | 复制/清单口径（包含集说清） | canonical 枚举口径 | 结论边界 |
| --- | --- | --- | --- | --- |
| v1（D） | `run_20261015_222105_wire`（10-15 22:21） | 自述 **live 68 = mirror 68**（= `app` 37 + `tests` 31，见 [v1 断点交接 17](<../../tests/acceptance/_tmp/s3_wiring_recheck_v1/run_20261015_222105_wire/evidence/17_handoff_remaining_items.md>)；该 evidence 目录内**没有**同名 manifest 文件，本报告未再复算） | **只引原件、不重算**：① `7854`／`7854`／差集 `0` 是 [14 号工具](<../../tests/acceptance/_tmp/s3_wiring_recheck_v1/run_20261015_222105_wire/evidence/14_enumeration_reconciliation.md>) **当时自述的全遍历标签（含 junction 目标）**——**不得**把其中的 `nofollow` 标签当作"真实未跟随"的保证；② `64fce7f5dfc26338…` 是其按 `[path,bytes,sha256]` **归一对账的历史值**（**未记 mtime**，[14:14](<../../tests/acceptance/_tmp/s3_wiring_recheck_v1/run_20261015_222105_wire/evidence/14_enumeration_reconciliation.md>)）；③ "排除 `*/mirror/.venv/**` 与嵌套 `*/mirror/tests/**`" 是 [14:28](<../../tests/acceptance/_tmp/s3_wiring_recheck_v1/run_20261015_222105_wire/evidence/14_enumeration_reconciliation.md>) 的**未来建议**，**不证明** `7854` 已应用该排除；④ [16](<../../tests/acceptance/_tmp/s3_wiring_recheck_v1/run_20261015_222105_wire/evidence/16_dual_scope_extension_table.md>) 的 PowerShell `5604` 与 3 个 junction 各 750 差额属**历史归因**，本报告**不给出**任何"过滤后计数" | 冻结/镜像/零网络/S4方法/217 回归/修复复验 3/3；**②③⑤⑩ 未执行** |
| v2（A） | `run_20261015_230108_v2a`（10-15 23:01） | **70 = `app` 37 + `tests` 31 + `instance/_e2e.ps1` + `requirements.txt`**（[05_mirror_manifest.txt](<../../tests/acceptance/_tmp/s3_wiring_recheck_v2/run_20261015_230108_v2a/evidence/05_mirror_manifest.txt>) 逐行可数：L5–41 app、L42 `instance/_e2e.ps1`、L43 `requirements.txt`、L44–74 tests）；`files_copied=70`、`live_side_files=70`、**`mismatches=0`、`set_difference=0`**，清单逐行 `MATCH`（= **same=70 / mismatch=0**） | 前守护 canonical count=**85**、sha256 **`2088180f…`**（[02_guard_before.json](<../../tests/acceptance/_tmp/s3_wiring_recheck_v2/run_20261015_230108_v2a/evidence/02_guard_before.json>)） | ③③b④⑥⑦⑧⑧b⑧c；未跑 ②⑤⑩ |
| v3（D） | `run_20261015_231803_v3`（10-15 23:18） | 镜像+`.venv` 联接、冻结 5/5、parity 68=68（其自身记录） | **未核**：本报告未读其枚举原件，故不引用任何计数 | 仅前置步骤，**不冒充 HTTP** |
| v5（C） | `run_20261016_121158_v5b5dc`（10-16 12:11） | **70 = `app` 37 + `tests` 31 + `requirements.txt` + `instance/_e2e.ps1`**（[05_mirror_manifest.txt](<../../tests/acceptance/_tmp/s3_wiring_recheck_v5/run_20261016_121158_v5b5dc/evidence/05_mirror_manifest.txt>) 逐件 `same=True`，mismatch 0） | 前/后 canonical count=**92**、sha256 **`d0e58f8b…`** | ②⑤⑩；守护前后一致 |
| fix_v1（B 返工） | `run_20261015_223500_fixb`（10-15 22:35） | 清单+逐件核验（其自身记录） | live `tests/api/_tmp` 3236→3236、`s2_boundaries` 清单哈希前后一致（其自身记录；**本报告未复算**） | stray 修复 + 217 OK + E2E exit=0 |

- **计数/哈希纪律**：`85`/`2088180f…` **只归 v2**，`92`/`d0e58f8b…` **只归 v5**，v1 只用自己的 `64fce7f5…`（且其 `7854` 是"follow/nofollow 全遍历口径"，与策划者 PowerShell 口径 `5604` 不同）——**不得跨批借值**；无法确认的口径一律标 **未核**。`68` 与 `70` 的差异来自**包含集**（`70` 另含 `instance/_e2e.ps1` 与 `requirements.txt`），不是"联接/新增文件"的推测。
- **哈希一致的含义**：前后 `sha256` 一致只说明**同一路径内容在两次读数时相同**；它**不等于 mtime 不变**，**也不能证明两次读数之间绝无写入**（本研究未做持续监控）。
- **live 与镜像的守护要分开**：⑩ 的 `business_db_unchanged=True` 只说明**其自身隔离库/镜像侧**未被改写；**live 业务库**的结论必须引用外部守护原件（v5 [02_guard_before.json](<../../tests/acceptance/_tmp/s3_wiring_recheck_v5/run_20261016_121158_v5b5dc/evidence/02_guard_before.json>)/[10_guard_after.json](<../../tests/acceptance/_tmp/s3_wiring_recheck_v5/run_20261016_121158_v5b5dc/evidence/10_guard_after.json>)：`instance/app.db` = `e073f828…4eb85`、无 wal/shm、根四文档哈希一致、端口 5100–5105 残留 0）。

## 6. 证据覆盖边界与缺口（校准，不把已通过断言改成 FAIL）

1. **"公共默认路径逐字段等价"是缺口，不是已证结论**：v2 [04_observed_at.json](<../../tests/acceptance/_tmp/s3_wiring_recheck_v2/run_20261015_230108_v2a/evidence/04_observed_at.json>) 的 `04-11…04-22` 断言是 **HTTP/CSV/JSON 成功状态 + `observed_at`/`observed_at_source` + warning** 检查，**不是修前/修后响应字段的全量差分**。除非另有一个真实旧版本基线对照原件，该项只能作为缺口记录，**不得由 34/34 反推**。
2. **v5 ⑤ 的比较是列投影，不是全字段**：`09_05_http_chain.json` 中 `last_seen_at` 比较只覆盖 `id/version_no/last_seen_at/content_hash/superseded_by` 五列，`changed_index=[0]` 只证明**该投影集合内**仅历史行变化，**不得写成"其余行所有字段均不变"**。
3. **v5 两个模式的覆盖范围**：`atomic-case` 是**单行合法内容变化**（`version_added=1`）；含"合法行 + 非法行"的批次是 **`partial-case`**（`201`、`created=1`、`rejected=1`）。因此**不得**把 v5 atomic-case 叙述为"atomic 混合批次回滚已覆盖"；原子回滚另有已存证据（v2 [06_txn_failure_audit.json](<../../tests/acceptance/_tmp/s3_wiring_recheck_v2/run_20261015_230108_v2a/evidence/06_txn_failure_audit.json>) 的 `sqlite3.IntegrityError` 注入用例）。
4. **"本批无实现缺陷"仅限该批**：v5 [13_exit_map.json](<../../tests/acceptance/_tmp/s3_wiring_recheck_v5/run_20261016_121158_v5b5dc/evidence/13_exit_map.json>) 的 `implementation_defects: []` 只适用于 v5 的 ②⑤⑩；**整体真实缺陷归属见 §4 第 2 条（[S3_WIRING_SPEC §11.5](<../design/S3_WIRING_SPEC.md>)）**，不得据此写成"接线无实现缺陷"。
5. **⑧ 的内联 UNEXECUTED 保留**：v2 `08_status_no_escalation.json` 的 1 项未执行**维持 UNEXECUTED**（不标 PASS）；该断言由 `08b`（14/14）与 `08c`（18/18）真驱动覆盖，但**不改变 ⑧ 自身的 verdict**。
6. **已知偏差（不是"设计如此即无问题"）**：干净成功记录的 `request_url` 等字段**未落业务表**——[S3_WIRING_SPEC](<../design/S3_WIRING_SPEC.md>)（§11 附近，约 :230）记为**明确偏差**；`observed_at`/`observed_at_source` 改走内部 hint（这正是 §4 第 2 条缺陷的成因字段集）。
7. **仍未验证**：B 站限流阈值/字段稳定性/授权与费用；`/api/sources` 的 `last_success_at` 未被驱动；真实浏览器、异机、并发与压力均未测。（`items_new` 不计 `version_added` 属**已定设计口径**——[S3_WIRING_SPEC §4](<../design/S3_WIRING_SPEC.md>) 与 A 批验收均已裁定，**不再列为未验证问题**。）
8. **后续补证建议（另行派发，不在本任务执行）**：**优先** (a) 定位真实修前基线并做"默认公共路径逐字段差分"补证（无法证明同源 → 记"不可比较"，不伪造基线）；(b) ⑤ 补一次全列投影比较（`SELECT *`）以替换现有五列投影。**按需增强（非当前必要验收项）**：(c) 库级 ⇄ HTTP 同输入的判别一致性对照；(d) 文件系统监控（用以获得比"前后哈希"更强的写入结论）。不为获得更强断言而无限扩大测试。

## 7. 仍未满足的阶段条件（不得宣告阶段完成）

- **S3（[计划 §7](<../../DEVELOPMENT_PLAN.md>) 真实需求自动化）**：仍无"读取 → 标准化 → 存储 → 详情回溯"的**真实来源自动链路**证据；本批全部为离线/注入传输与镜像内 E2E，真实渠道接入、限流、授权与费用未验证。**不得称 S3 已完成。**
- **S4（[计划 §8](<../../DEVELOPMENT_PLAN.md>) 货源匹配与收益引擎）**：本批仅覆盖**情景子集**（摊销、未知/真零/缺口、`net=null` 等）与其不退化；**货源匹配（S4-B1）、排序权重（S4-B3）尚未实现**。
- S5/S6/S7 未开始。

## 8. 下一最小切片建议（计划 v2 内，离线、无网络、无新依赖）

**首选（最小前置任务）：定位真实修前基线，做"默认公共路径逐字段差分"补证。**
- 现状：§6 第 1 条已确认现有 `04_observed_at` 断言**不是**修前/修后全字段差分，故"默认公共路径逐字段等价"目前**无证据**。
- 建议任务：在只读前提下定位**可信、可证明同源**的修前基线（旧版本代码或旧快照），若能证明同源则跑一次默认公共路径的逐字段差分并留档；**若无法证明同源，则记录为"不可比较"**，不伪造基线、不把不同源数据当对照。
- 前置：只读既有产物；不新增网络/依赖/服务；不动业务库与既有测试。
- 写入范围（建议）：`docs/validation/` 下一份差分补证记录 + `tests/acceptance/_tmp/<新 scope>/`。
- 验收条件：差分口径（字段集、路径、时点）显式写明；无基线时明确写"不可比较"，不产出伪结论。

**可并行候选：S4-B1 离线匹配设计规范。**
- 现状核查（本次静态阅读 + glob）：`docs/design/` 共 6 份文档（`ACCEPTANCE.md`、`CONTRACT.md`、`S2_CORE.md`、`S2_RUNTIME.md`、`S3_WIRING_SPEC.md`、`S4_SCENARIO_SPEC.md`），其中 [S4_SCENARIO_SPEC.md](<../design/S4_SCENARIO_SPEC.md>) §6/§10.4 明确排除"排序/匹配大包"——**未找到专门面向 S4-B1 的匹配规范**（并非"目录里只有一份文档"）。
- 建议任务：编写 `docs/design/S4_MATCHING_SPEC.md`——需求与货源按**用途 / 内容（版本）/ 交付形式 / 适用条件**的匹配定义、缺口解释、与四项门槛及当前 G2 的关系、"仅名称相似或供应商自称可转售**不**自动升级核验"与"货源失效/许可变化触发复核"两条硬约束、可离线驱动的验收矩阵（含期望值）。
- 前置：S3 接线冻结哈希不变（本报告 §1）；`CONTRACT.md` 只读；不新增端点/表/列/依赖；不引入网络与自动核验。
- 写入范围（建议）：`docs/design/S4_MATCHING_SPEC.md`（单写手；测试矩阵如需另列 `tests/acceptance/_tmp/s4_matching_spec_v1/`）。
- 验收条件（建议）：逐条可对照计划 §8 S4-B1；含上述两条硬约束；给出可离线执行的最小测试清单与期望值；**不宣布 S4 阶段完成**。

**候选（下批再冻结基线；本轮不执行任何新检查）**
- 既有文件 [18_scope_and_hashes.txt](<../../tests/api/_tmp/import_history_fix_v1/run_20261015_212020_704683a1/18_scope_and_hashes.txt>) 的 `:2` 记录该批次 **ABA 修后** `app\core\importer.py` 的 live／mirror 值 `42F1F8FC8A6999C407C77414C8D4A16D2C939B498C3ABFE2A40D9B47287E8946`（`same=True`），其对应镜像文件为 [mirror/app/core/importer.py](<../../tests/api/_tmp/import_history_fix_v1/run_20261015_212020_704683a1/mirror/app/core/importer.py>)（存在）。
- **标注：候选——当前字节 hash／整树同源尚未复核**。该值**早于且不同于**接线批次的冻结值 `a11eaf4d…`，**不得**与之混用；**不得**用 `05_mirror_manifest` 的**初建**旧值替代 18 号修后值。能否作为"修前基线"用于默认公共路径差分，须**下批先冻结基线**再判定（无法证明同源 → 记"不可比较"）。

## 9. 本次归档的文档核验记录（实际执行 vs 静态阅读）

- **上一轮实际执行（对应本报告的"修订前版本"，不覆盖本轮修订后的文本）**：链接存在性检查与 5 个冻结哈希复算曾实际运行，产物见 [01_link_check.json](<../../tests/acceptance/_tmp/s3_wiring_archive_v1/01_link_check.json>)（47/47 存在）、[02_hash_recheck.json](<../../tests/acceptance/_tmp/s3_wiring_archive_v1/02_hash_recheck.json>)（5/5 一致）。这两份产物**只**可作为**上一版报告**的"链接存在／哈希记录"来阅读，**不为新报告或原始 exit 背书**。
- **`00_run.log` 与其可读记录的边界（不得以转录消除缺口）**：原件 [00_run.log](<../../tests/acceptance/_tmp/s3_wiring_archive_v1/00_run.log>) 的**具体编码未做字节核验**——"UTF-16LE"只是基于 PowerShell `Tee-Object` 默认行为的**推测**；[00_run_readable.log](<../../tests/acceptance/_tmp/s3_wiring_archive_v1/00_run_readable.log>) 是**执行者历史自述转录**，**不是 decoded 副本**。因此其中的 `ARCHIVE_EXIT=0` **尚未由策划从原始日志独立核对**，该缺口**不能**由转录消除；本轮以**完整静态核对**限定验收（不再寻找 Shell，也不假造最终哈希）。原件保留不改。
- **本轮修订（revision 5 与 revision 8）未执行任何脚本**：本任务角色当前**不具备 Shell 工具**（如实记录，不自行扩权、不改环境）。因此：新增/改动的链接以**逐条静态核对**（对目标路径 `glob`／`read` 确认存在）方式检查，记录见 [05_static_link_recheck.md](<../../tests/acceptance/_tmp/s3_wiring_archive_v1/05_static_link_recheck.md>)；**全量链接脚本复跑、文本编码解码复检、5 哈希再算、最终报告 sha256 均未执行**，属于本轮的**未执行缺口**。仅"路径存在"**不等于**全内容读回成功。
- **静态阅读**（未执行、仅阅读原件）：v1/v2/v3/v5/fix_v1 的证据 JSON/MD/LOG、[S3_WIRING_SPEC.md](<../design/S3_WIRING_SPEC.md>)、[S4_SCENARIO_SPEC.md](<../design/S4_SCENARIO_SPEC.md>)、[CONTRACT.md](<../design/CONTRACT.md>)、[DEVELOPMENT_PLAN.md](<../../DEVELOPMENT_PLAN.md>)；记录见 [03_static_read_record.md](<../../tests/acceptance/_tmp/s3_wiring_archive_v1/03_static_read_record.md>)、[04_revision_v5_notes.md](<../../tests/acceptance/_tmp/s3_wiring_archive_v1/04_revision_v5_notes.md>)。
- **关于"业务库/端口"**：本报告的档案核验**不新增** live 业务库或端口的实测；§5 与 §6 中出现的 `e073f828…4eb85`／无 wal-shm／端口 5100–5105 残留 0 均**引用既有批次的历史观测**（v1 [14](<../../tests/acceptance/_tmp/s3_wiring_recheck_v1/run_20261015_222105_wire/evidence/14_enumeration_reconciliation.md>)／v5 [02](<../../tests/acceptance/_tmp/s3_wiring_recheck_v5/run_20261016_121158_v5b5dc/evidence/02_guard_before.json>)、[10](<../../tests/acceptance/_tmp/s3_wiring_recheck_v5/run_20261016_121158_v5b5dc/evidence/10_guard_after.json>)），不作为本轮的独立结论。
- **写入监控边界**：`01_link_check.json`／`02_hash_recheck.json` **只是两份哈希/链接产物**，**不能**据此声称本 scope（乃至全仓）"期间绝无写入"；本报告没有文件系统级监控证据。
- 本次**未**执行：任何应用测试、217 回归、HTTP 批次、E2E 重跑；**未**修改 `app/**`、`tests/**` 既有测试、根台账、`PRODUCT.md`、冻结 `CONTRACT.md`、S2 快照、旧 FAIL 史与业务库；**未**改动 v1/v2/v3/v5 证据。

## 10. 声明与限制

- 本文档是**证据归档与边界校准**，不是新的功能测试；"通过"仅对应各批次的命令、退出码与时点，未执行项不标 PASS。
- 各批结论互不继承：不同 runID 的镜像、计数与哈希口径分别列出，**不合并计数、不跨批外推**。
- 任务状态（completed/paused/running）只作协作事实记录，**不用于推断测试覆盖或容量原因**。
- 本报告不宣布 S3 或 S4 阶段完成；下一阶段动作需策划者按计划 v2 另行派发。

## 11. 修订历史（保留每轮审阅与更正）

| 轮次 | 触发 | 本轮实际改动 | 保留 |
| --- | --- | --- | --- |
| 初版（归档任务 revision 2 提交） | 首次归档 | 建本报告与 archive scope（`00_run.log`、`01_link_check.json` 47/47、`02_hash_recheck.json` 5/5、`03_static_read_record.md`） | 首轮执行痕迹与失败史（首轮 `01_link_check` 曾发现 1 处链接路径错误 `../DEVELOPMENT_PLAN.md`） |
| 修订 1（revision 5 提交） | 策划者退回（revision 4，7 点）+ 两条原件抽查细节 | ① §4/§2 写入 v1 `09_wiring_strays.log` **混合结果**与 217 日志 warnings 口径；② §5 逐批重对 canonical 与包含集（85 只归 v2；92 只归 v5；68/70 包含集说清；`same=70/mismatch=0`）；③ §3 空 `cross_refs` 定位改为 v5 `08_02b:47`；④ §2 新增**完整 taskId + revision/status 表**并声明旧综合 D 无 submit；⑤ §6 移除"items_new 未验证"、`request_url` 改为明确偏差、增强项移为按需；⑥ §8 首选改为**修前基线差分补证**、S4-B1 为并行候选、`docs/design` 表述改为"未找到专门匹配规范"；⑦ §9 改写执行记录（无 Shell → 未执行全量复跑/哈希/解码，仅逐条静态核对链接） | 初版证据与首轮执行产物**原样保留**；旧 FAIL／UNEXECUTED／偏差不改写；新增 [00_run_readable.log](<../../tests/acceptance/_tmp/s3_wiring_archive_v1/00_run_readable.log>)、[04_revision_v5_notes.md](<../../tests/acceptance/_tmp/s3_wiring_archive_v1/04_revision_v5_notes.md>)、[05_static_link_recheck.md](<../../tests/acceptance/_tmp/s3_wiring_archive_v1/05_static_link_recheck.md>) |
| 修订 2（revision 8 提交，本轮） | 策划者退回（revision 7，A/B/C 三小处） | A. §5 v1 行改为**三个标签分开**（`7854/7854/差集0`＝14 号工具当时自述的全遍历标签、含 junction，不得把 `nofollow` 当"真实未跟随"保证；`64fce7f5…`＝按 `[path,bytes,sha256]` 归一对账的历史值；"排除镜像子树"＝[14:28](<../../tests/acceptance/_tmp/s3_wiring_recheck_v1/run_20261015_222105_wire/evidence/14_enumeration_reconciliation.md>) 的**未来建议**、不证明 `7854` 已应用；16 的 `5604`／3×750 仅作历史归因，删去"过滤后计数"）。B. §9 与 `00_run_readable.log` 写明：原件编码**未字节核验**（UTF-16LE 系 `Tee-Object` 推测）、可读文件是**自述转录而非 decoded 副本**、`ARCHIVE_EXIT=0` 仍待策划从原始日志独立核对、旧 `01/02` 不为新报告或原始 exit 背书；本轮以完整静态核对限定验收。C. §8 增一行**候选**（`18_scope_and_hashes.txt` 的 ABA 修后 importer `42F1F8FC…E8946` 与其镜像文件为有效链接；标注"当前字节 hash／整树同源尚未复核"，不与接线冻结值混用，下批冻结基线）。 | 上一轮修订内容与全部旧证据**原样保留**；旧 FAIL／UNEXECUTED／偏差不改写；`00_run.log` 原件保留不改 |
