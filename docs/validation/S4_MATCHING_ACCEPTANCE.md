# S4-B1 匹配实现 · 独立验证验收（非实现者复跑）

> 验证对象：`app/core/matching.py`（**258 行**，sha256 `5cd186c8d8402cb3a0fa41ed62212f991aff6b86de152fcc688fc3ebba5dcade`，11937 bytes）与 `tests/core/test_matching.py`（**286 行**，sha256 `ab088d2b456883edee52a74fb958b71e7302cd1964d6a9a8dd025245a71b84b7`，18655 bytes）。
> 设计依据：[S4_MATCHING_SPEC.md](<../design/S4_MATCHING_SPEC.md>) v2（**149 行**，sha256 `27e90bd5…f372df`）；评审：[S4_MATCHING_REVIEW.md](<S4_MATCHING_REVIEW.md>)(159 行，sha256 `1e69427e…cda04b`)。
> 验证者：独立执行者 A（实现者为 B），任务 `task-47491625a449b62a33a2388bc2a2a78c`；验证时点 2026-10-20 13:29–13:35 +08:00。
> 性质：**隔离镜像复跑 + 独立探针**。未修改 `app/**`、`tests/**`、契约、迁移、台账与业务库；**未联网、未启动服务**（无 socket/HTTP server）；`GET` 结果均来自镜像内 `test_client`，未用任何"猜结果"。
> 结论：**通过（仅限本实现与设计矩阵范围）**——匹配测试 14/14、全量套件 231/231 均 `OK exit=0`；独立探针 20/20 全过（只读零写入、H1/H2、G2/G4、M-13、`is_selected_by_g2`、结构/等级）；业务库哈希前后一致、WAL/SHM 不存在；**不宣称 S4 阶段完成**。

## 1. 运行目录与镜像

- 唯一 run：`tests/acceptance/_tmp/s4_matching_verify_v1/run_20261020_132906_matchverify/`
- 镜像：`<run>/mirror/`（复制 live `app/**` + `tests/**` + `requirements.txt`；排除 `__pycache__`/`_tmp`/`_snapshots`/`.venv`/`.pytest_cache`/`.mypy_cache` 与任何 reparse 目录；无 `.pyc`）
- 证据：[01_mirror.json](<../../tests/acceptance/_tmp/s4_matching_verify_v1/run_20261020_132906_matchverify/evidence/01_mirror.json>)、[01_mirror_cmd.log](<../../tests/acceptance/_tmp/s4_matching_verify_v1/run_20261020_132906_matchverify/evidence/01_mirror_cmd.log>)（**exit=0**）

| 项 | 结果 |
| --- | --- |
| 复制文件 | **71**（app+tests+requirements） |
| 剪枝目录 | 16（`__pycache__`/`_tmp`/`_snapshots` 等；逐项列于 01_mirror.json） |
| reparse/junction 跳过 | **0**；遍历异常 **0** |
| 逐件 parity | **mismatched=0 / extra=0**（每件 bytes+sha256 与 live 源一致） |
| 关键哈希 | matching `5cd186c8…`、test_matching `ab088d2b…`、routes `f3ef63d4…`（routes 与评审时点同哈希 → GET 路径未被改动） |

## 2. 模块与 DB 来源实证（不加载 live/旧镜像）

- 证据：[02_path_probe.json](<../../tests/acceptance/_tmp/s4_matching_verify_v1/run_20261020_132906_matchverify/evidence/02_path_probe.json>)、[02_path_probe_cmd.log](<../../tests/acceptance/_tmp/s4_matching_verify_v1/run_20261020_132906_matchverify/evidence/02_path_probe_cmd.log>)（**exit=0，checks=10/10**）
- 运行方式：`cwd=<run>/mirror`、`PYTHONPATH=<run>/mirror`、`PYTHONDONTWRITEBYTECODE=1`、venv python 3.12。
- 逐项：`cwd_is_mirror` ✓、`mirror_in_sys_path` ✓、`app_file_in_mirror` ✓、`matching_file_in_mirror` ✓、`importer_file_in_mirror` ✓、`test_file_in_mirror` ✓、`config_root_in_mirror` ✓、`db_path_in_run` ✓（fresh DB 在 `<run>/dbs/`）、`cfg_db_matches` ✓、`live_root_not_imported` ✓（sys.path 无 `s3_public_compat*`/`s3_wiring_recheck*`）。

## 3. 两轮测试（真实 exit）

| 轮次 | 命令（cwd=mirror） | 结果 | 证据 |
| --- | --- | --- | --- |
| 匹配单测 | `-m tests.core.test_matching` | **Ran 14 tests in 2.525s — OK**，**exit=0** | [03_matching_tests_cmd.log](<../../tests/acceptance/_tmp/s4_matching_verify_v1/run_20261020_132906_matchverify/evidence/03_matching_tests_cmd.log>) |
| 完整回归 | `-m unittest discover -s tests -t .` | **Ran 231 tests in 35.182s — OK**，**exit=0** | [04_discover_cmd.log](<../../tests/acceptance/_tmp/s4_matching_verify_v1/run_20261020_132906_matchverify/evidence/04_discover_cmd.log>) |

- 与 B 宣称对照：B 称 **14/231** → **实测 14/231，数字一致**；B 称行数 **240/273** → 实测 **258/286**（与策划实读 258/286 一致），以本报告 §5 哈希为准。
- 测试期间仅在镜像内写临时 DB（`mirror/tests/api/_tmp/`），未写 live `instance/app.db`（§6）。

## 4. 静态扫描与独立探针（20/20）

- 证据：[05_probe.json](<../../tests/acceptance/_tmp/s4_matching_verify_v1/run_20261020_132906_matchverify/evidence/05_probe.json>)、[05_probe_cmd.log](<../../tests/acceptance/_tmp/s4_matching_verify_v1/run_20261020_132906_matchverify/evidence/05_probe_cmd.log>)（**exit=0，checks=20 passed=20 failed=0**）
- 探针由本执行者独立编写（未复用 B 的测试断言），仅复用既有 `tests/api/b2_helpers` 造数。

| # | 检查 | 结果 |
| --- | --- | --- |
| A1 | `matching.py` AST 扫描：无 INSERT/UPDATE/DELETE/REPLACE/CREATE/DROP/ALTER/BEGIN/COMMIT/`.commit()` | PASS（write_calls=[]） |
| A2 | `app/api/routes.py` 无 `matching`/`match_supplies` 引用 | PASS（routes_refs=[]） |
| B1 | 连续两次 `match_supplies` 结果完全相同 | PASS |
| B2 | **全表**快照（candidate/demand_signal/evidence/supply_offer/cost_item/gate_review/review_item/import_batch/import_row_result/run_record/idempotency_key/schema_migrations/source/draft/feedback）两次调用前后逐值一致 | PASS（changed=[]） |
| B3 | 候选详情响应键未变、无 matching 键 | PASS（12 个既有键） |
| C1 | H1：`license_summary` 含"可转售"且 `commercial_allowed='unknown'` → `reasons=[self_claim_only]` | PASS |
| C2 | H1：同关键词但三项许可均 `yes` → **不**产出 `self_claim_only` | PASS（reasons=[]） |
| C3 | H1：无关键词、`provider_name` 与标题几乎一致 → 不产出 `self_claim_only`，也**不产出** `name_only_similarity`（不做相似度） | PASS |
| D1 | `status='invalid'` → `level='excluded'`、`reasons=[supply_invalid]` | PASS |
| D2 | `last_checked_at` 早于 30 天 → `level='excluded'`、`reasons=[supply_ttl_expired]` | PASS |
| E1 | M-13 前置：G2+G4 verified 后新增第二货源并核验新 G2 → 成功（200） | PASS |
| E2 | M-13：旧 G4 读时 `expired`；首货源 `gate_refs` 含 `platform_policy: expired`（另含 `cost: expired`，均为既有机制） | PASS |
| E3 | M-13：首货源 `reasons` **不含** `license_changed`/`supply_invalid`/`supply_ttl_expired`/`cost_changed`（实测 reasons=[]） | PASS |
| E4 | M-13：匹配前后全表快照一致（零写入） | PASS |
| F1 | G2 未核验 → `is_current_g2_valid=false` 且所有 `is_selected_by_g2=false` | PASS |
| F2 | G2 已核验 → 仅该货源 `is_selected_by_g2=true`，另一货源 false；`current_g2_supply_id` 指向已核验者 | PASS |
| G1 | 顶层键 = {candidate_id, current_g2_supply_id, is_current_g2_valid, items, gaps, display_note}（设计 §3） | PASS |
| G2 | item 键/{dims 四维} 与设计 §3 一致 | PASS |
| G3 | 全部 level ∈ 设计 LEVELS，且 **`adaptable` 不可达**（用途恒 hint_only ⇒ needs_review） | PASS |
| G4 | `display_note` 与设计固定文案逐字一致 | PASS |

**实现观察（不影响 PASS，仅记录）**：`match_supplies` 内 `_gate_rows` 被调用两次（`gate_states` 与 `baseline_version` 各一次）；纯 SELECT、无写入，属性能冗余而非缺陷。

## 5. 行数与哈希更正（以实测为准）

| 文件 | 实测行数 | 实测 sha256 | 对照 |
| --- | --- | --- | --- |
| `app/core/matching.py` | **258** | `5cd186c8d8402cb3a0fa41ed62212f991aff6b86de152fcc688fc3ebba5dcade` | B 宣称 240 → **不实**；策划实读 258 ✓ |
| `tests/core/test_matching.py` | **286** | `ab088d2b456883edee52a74fb958b71e7302cd1964d6a9a8dd025245a71b84b7` | B 宣称 273 → **不实**；策划实读 286 ✓ |
| `app/api/routes.py` | 561 | `f3ef63d4f1a722003826a1c8d8ea917826a538b4493b667758df7955a1a07630` | 与评审时点同哈希（GET 未改） |
| `docs/design/S4_MATCHING_SPEC.md` | 149 | `27e90bd50c946b00a7cbcaffb829516f1fc9afd5a05828d45b658564d0f372df` | 设计 v2 |
| `docs/validation/S4_MATCHING_REVIEW.md` | 159 | `1e69427e4e3b8c09c6acd3951b89412995d6bbe2b203b263930a9afad2cda04b` | 评审稿 |

## 6. 前后守护（业务库与 live 树）

| 项 | 运行前 | 运行后 |
| --- | --- | --- |
| `instance/app.db` sha256 | `e073f828cf0f30d6206361bba3a729826be096be3308f5a5dc204406dae4eb85` | **相同** |
| `instance/app.db-wal` / `-shm` | 不存在 | **不存在** |
| live `app/**`、`tests/**` | — | 未改（镜像逐件 parity=0；本任务只写了 `<run>/` 与 `docs/validation/S4_MATCHING_ACCEPTANCE.md`） |

- 证据文本：14 件证据文件 UTF-8 无 BOM、仅 LF、读回 **exit=0**（[06_evidence_check_cmd.log](<../../tests/acceptance/_tmp/s4_matching_verify_v1/run_20261020_132906_matchverify/evidence/06_evidence_check_cmd.log>)、[08_evidence_readback.txt](<../../tests/acceptance/_tmp/s4_matching_verify_v1/run_20261020_132906_matchverify/evidence/08_evidence_readback.txt>)）。

## 7. 验证过程修正史（如实保留，均未触 live）

1. **attempt1**：我自写的 `build_mirror.py`/`probe_matching.py` 含 Python 3.10 不允许的 f-string 反斜杠表达式 → 语法错误、镜像未生成；失败日志保留为 `*_attempt1_nodir.log`。
2. **attempt2**：镜像已正确复制，但我的清单相对路径漏 `app/`/`tests/` 前缀（parity 70 误报、extra 70），且 path probe 断言 `sys.path[0]==mirror`（实际脚本目录在前）过严 → 构建工具 exit=1、path probe 9/10，但同批匹配测试与全量回归已在正确镜像上 `OK`（日志保留为 `*_attempt2_manifest.log`）。
3. **attempt3（最终）**：删除本 run 内的部分镜像（已验证路径仅在 run 下）后从源头重建；修正清单前缀与 sys.path 断言 → 镜像 parity 全 0、path probe 10/10、两轮测试与新探针全过。

失败与修正全部发生在 `<run>/tools/` 与 `<run>/evidence/`；未修改 `app/**`、`tests/**`、契约、迁移、台账与业务库。

## 8. 未执行 / 未覆盖（不标 PASS）

- **未联网、未启动服务**：全部测试与探针在镜像内以 `test_client`/直接函数调用执行；无 socket/HTTP server、无真实渠道。
- **matching 未接入任何 API 路由**（设计 §3 的"纯函数"形态）：未测 HTTP 级匹配端点（现无该端点）；`GET /api/candidates/{id}` 仅证明未含匹配字段。
- **未测**：并发/多连接、大候选集性能、`_reason_from_note` 对更多自由文本的穷举、跨 data_origin 组合、S4-B3 排序/权重、S5/S6、真实网络证据、行级覆盖率（未跑 coverage）。
- 独立探针复用既有 `tests/api/b2_helpers` 造数（未用 B 的断言）；M-13 只覆盖"换 G2 后旧 G4 失效"的一种场景。
- 结论仅限本实现（上述哈希）与本矩阵；**不宣称 S4 阶段完成**。

## 9. 证据索引

| 证据 | 路径 |
| --- | --- |
| 镜像清单/parity | [01_mirror.json](<../../tests/acceptance/_tmp/s4_matching_verify_v1/run_20261020_132906_matchverify/evidence/01_mirror.json>) |
| 模块/DB 来源实证 | [02_path_probe.json](<../../tests/acceptance/_tmp/s4_matching_verify_v1/run_20261020_132906_matchverify/evidence/02_path_probe.json>) |
| 单测日志 | [03_matching_tests_cmd.log](<../../tests/acceptance/_tmp/s4_matching_verify_v1/run_20261020_132906_matchverify/evidence/03_matching_tests_cmd.log>) |
| 全量回归日志 | [04_discover_cmd.log](<../../tests/acceptance/_tmp/s4_matching_verify_v1/run_20261020_132906_matchverify/evidence/04_discover_cmd.log>) |
| 独立探针结果 | [05_probe.json](<../../tests/acceptance/_tmp/s4_matching_verify_v1/run_20261020_132906_matchverify/evidence/05_probe.json>) |
| 证据文本读回 | [08_evidence_readback.txt](<../../tests/acceptance/_tmp/s4_matching_verify_v1/run_20261020_132906_matchverify/evidence/08_evidence_readback.txt>) |
