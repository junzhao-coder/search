# S4-B3 排序实现 · 独立验证验收（非实现者复跑）

> 验证对象：`app/core/ranking.py`（**288 行**，sha256 `17cd66c4b401aa4329c91eabf311438d7c667b85f0841fa8ff96d5198e8cc396`）与 `tests/core/test_ranking.py`（**264 行**，sha256 `8e2f29e09aa8f78629b28fad4e82135bccf91cc2cc5eef0df81c4e3bd9803997`）。
> 设计依据：[S4_RANKING_SPEC.md](<../design/S4_RANKING_SPEC.md>) v2（**206 行**，sha256 `b43da4ac…1b10`）。
> 验证者：独立执行者 A（实现者为 B），任务 `task-3b0847864175330f55b80f78105935eb`；验证时点 2026-10-20 14:01–14:05 +08:00。
> 性质：**隔离镜像复跑 + 独立探针**。未修改 `app/**`、`tests/**`、契约、迁移、台账与业务库；**未联网、未启动服务**（无 socket/HTTP server）。
> 结论：**通过（仅限本实现与设计矩阵范围）**——排序单测 17/17、全量套件 248/248 均 `OK exit=0`；独立探针 **21/21** 全过；业务库哈希前后一致、WAL/SHM 不存在。**不宣称 S4 完成或排序可用**；实现与设计的差异及确定性边界见 §5。

## 1. 运行目录与镜像

- 唯一 run：`tests/acceptance/_tmp/s4_ranking_verify_v1/run_20261020_140101_rankverify/`
- 镜像：`<run>/mirror/`（复制 live `app/**`+`tests/**`+`requirements.txt`；排除 `__pycache__`/`_tmp`/`_snapshots`/`.venv`/`.pytest_cache`/`.mypy_cache` 与 reparse 目录；无 `.pyc`）
- 证据：[01_mirror.json](<../../tests/acceptance/_tmp/s4_ranking_verify_v1/run_20261020_140101_rankverify/evidence/01_mirror.json>)、[01_mirror_cmd.log](<../../tests/acceptance/_tmp/s4_ranking_verify_v1/run_20261020_140101_rankverify/evidence/01_mirror_cmd.log>)（**exit=0**）

| 项 | 结果 |
| --- | --- |
| 复制文件 | **73**（app+tests+requirements） |
| 剪枝目录 | 16；reparse/junction 跳过 **0**；遍历异常 **0** |
| 逐件 parity | **mismatched=0 / extra=0**（bytes+sha256 与 live 源一致） |
| 关键哈希 | ranking `17cd66c4…`、test_ranking `8e2f29e0…`、routes `f3ef63d4…`（与 S4-B1 验证时点同哈希 → GET 未改） |

## 2. 模块与 DB 来源实证

- 证据：[02_path_probe.json](<../../tests/acceptance/_tmp/s4_ranking_verify_v1/run_20261020_140101_rankverify/evidence/02_path_probe.json>)、[02_path_probe_cmd.log](<../../tests/acceptance/_tmp/s4_ranking_verify_v1/run_20261020_140101_rankverify/evidence/02_path_probe_cmd.log>)（**exit=0，checks=12/12**）
- 运行方式：`cwd=<run>/mirror`、`PYTHONPATH=<run>/mirror`、`PYTHONDONTWRITEBYTECODE=1`、venv python 3.12。
- 逐项：cwd 是镜像、mirror 在 sys.path、`app`/`app.core.ranking`/`app.core.matching`/`app.core.scenario`/`app.core.importer`/`tests.core.test_ranking`/`config.ROOT` 全在镜像内、fresh DB 在 run 内且 cfg 一致、sys.path 无 live/旧镜像路径。

## 3. 两轮测试（真实 exit）

| 轮次 | 命令（cwd=mirror） | 结果 | 证据 |
| --- | --- | --- | --- |
| 排序单测 | `-m tests.core.test_ranking` | **Ran 17 tests in 4.460s — OK**，**exit=0** | [03_ranking_tests_cmd.log](<../../tests/acceptance/_tmp/s4_ranking_verify_v1/run_20261020_140101_rankverify/evidence/03_ranking_tests_cmd.log>) |
| 完整回归 | `-m unittest discover -s tests -t .` | **Ran 248 tests in 40.175s — OK**，**exit=0** | [04_discover_cmd.log](<../../tests/acceptance/_tmp/s4_ranking_verify_v1/run_20261020_140101_rankverify/evidence/04_discover_cmd.log>) |

- 与 B 宣称对照：B 称 **17/248** → **实测 17/248 一致**；B 称行数 **280/254** → 实测 **288/264**（**行数不实**；B 给出的两个 sha256 `17CD66C4…`/`8E2F29E0…` 与实测一致，见 §6 更正表）。
- `04_discover_cmd.log` 含 `ResourceWarning`（非失败；`Ran 248 … OK`）。

## 4. 静态扫描与独立探针（21/21）

- 证据：[05_probe.json](<../../tests/acceptance/_tmp/s4_ranking_verify_v1/run_20261020_140101_rankverify/evidence/05_probe.json>)、[05_probe_cmd.log](<../../tests/acceptance/_tmp/s4_ranking_verify_v1/run_20261020_140101_rankverify/evidence/05_probe_cmd.log>)（**exit=0，checks=21 passed=21 failed=0**）
- 探针由本执行者独立编写（未复用 B 的测试断言），仅复用既有 `tests/api/b2_helpers` 造数。

| # | 检查 | 结果 |
| --- | --- | --- |
| A1 | `ranking.py` AST 扫描：无 INSERT/UPDATE/DELETE/REPLACE/CREATE/DROP/ALTER/BEGIN/COMMIT/`.commit()` | PASS（write_calls=[]） |
| A2 | `app/api/routes.py` 无 `ranking`/`rank_candidates` 引用 | PASS（routes_refs=[]） |
| A3 | `routes.py` sha256 与验证前一致（`f3ef63d4…`） | PASS |
| A4 | `_judge` 的 `origin` 参数**未被使用**（AST 名称扫描） | PASS（记录：无 data_origin 过滤） |
| A5 | 候选详情响应键与验证前一致（12 个既有键） | PASS |
| B1 | 连续两次 `rank_candidates` 结果完全相同 | PASS |
| B2 | **全表**（candidate/demand_signal/evidence/supply_offer/cost_item/gate_review/review_item/import_batch/import_row_result/run_record/idempotency_key/draft/feedback/source/schema_migrations）两次调用前后逐值一致 | PASS（changed=[]） |
| C1 | 分池计数：excluded=1 / blocked=1 / recommended=2 / observing=1 / exploring=1 / insufficient=1 | PASS |
| C2 | 各例 pool/tier：blocked=B、T1/T2 均 recommended、observing=T3、exploring=T4 | PASS |
| C3 | 全局 rank 连续 1..5，且 `items[0].pool == "blocked"`（置顶） | PASS |
| C4 | `daily_pick` 仅推荐池为真，观察/探索/blocked 均 false | PASS |
| D1 | `as_of` 缺省 → `TypeError: missing 1 required keyword-only argument`（必填） | PASS |
| D2 | 非法 `as_of`（"2026-13-99"）→ `ValueError`（格式校验） | PASS |
| D3 | 同 `as_of` 连续两次调用逐字段一致 | PASS |
| D4 | 不同 `as_of` 仅新鲜度变化：6 天→100 分、15 天→96 分（差 4），其余字段一致 | PASS |
| E1 | **真实 now 的 TTL 边界**：`last_checked_at=2026-09-20T03:00:00Z`（相对 `as_of` 仅 29d21h）→ 因 `_supply_stable` 用真实 now 判 30 天，本次已≥30d ⇒ G2 读时 expired ⇒ recompute stale ⇒ **落 blocked 池**（非 strict 确定） | PASS（记录） |
| F1 | `limit=5` 且 6 个推荐候选：5 个 `daily_pick`、第 6 在 `omitted` 且全局 `rank=6` | PASS |
| G1 | R-01 分数按设计权重复算：39+15+10+5×4+8+6+2 = **100**（actual 100） | PASS |
| H1 | 权重常量与设计 §4.3 一致（T1=39/T2=29/T3=15/T4=5 等，material_gap=-2），`rank_version="rank-v1"` | PASS |
| H2 | 输出字段：rank_version/as_of/scenario_params/budget_minutes/budget_note/pending_confirmation/pool_order/pools/daily_limit/items/omitted | PASS |
| H3 | item 字段：rank/candidate_id/pool/tier/score/reasons/gaps/next_action/daily_pick/inputs_used | PASS |

## 5. 实现差异与确定性边界（实测记录，不掩盖）

1. **`as_of` 必填**：实现 `rank_candidates(conn, *, as_of, …)` 无默认值（缺省 `TypeError`、非法 `ValueError`）；设计 §2 L29 写"入口默认 `now_utc()` 注入"，而 §6 签名 `as_of` 无默认——**设计内部不一致**，实现选择了更严格的可复现口径。记录为实现差异（不判缺陷）。
2. **`_supply_stable` 用真实 now 判 30 天 supply TTL**（`ranking.py:119-121`）：固定 `as_of` 不能保证跨 TTL 边界完全确定；探针 E1 已构造"按 as_of 仅 29d21h、按真实 now 已≥30d"的候选，结果由 recommended 变 blocked。**不得宣称"固定 as_of 即完全确定"**。
3. **`origin` 参数传入后未使用**：`_judge(... origin ...)` 无 data_origin 过滤，排序包含 real+synthetic 全部候选。若未来每日摘要默认只统计 `real`（CONTRACT §0.5），需调用方过滤或加参数（当前设计未要求，记录为边界）。
4. **`pool_order` 输出值**：实现输出池名 `["blocked","recommended","observing","exploring"]`（与设计 §4.2 的 pool_order 列一致）；设计 §6 示例字面写 `["blocked","T1","T2","T3","T4"]`（tier 名）——**设计示例与实现字面不同**，行为无影响，记录为文档内部不一致。
5. 其余口径与设计 v2 一致：情景参数缺省 `{variant:'base', amortize_orders:null, monthly_orders:null}` 并写入 `inputs_used`；`complete=true→T1`、`false→T2`；观察时间取**头版本行**、人工分钟取 `manual_labor/per_order/base/active` 合计；−2 仅当实质缺口（不含 `dims_text_only`/`scope_text_only`）；blocked 覆盖全部 `recompute` stale 来源（含手工 G1 failed、无 blocking 复核）。

## 6. 行数与哈希更正（以实测为准）

| 文件 | 实测行数 | 实测 sha256 | 对照 |
| --- | --- | --- | --- |
| `app/core/ranking.py` | **288** | `17cd66c4b401aa4329c91eabf311438d7c667b85f0841fa8ff96d5198e8cc396` | B 称 280 行 → **行数不实**；sha 与 B 的 `17CD66C4…` 一致；策划实读 288 ✓ |
| `tests/core/test_ranking.py` | **264** | `8e2f29e09aa8f78629b28fad4e82135bccf91cc2cc5eef0df81c4e3bd9803997` | B 称 254 行 → **行数不实**；sha 与 B 的 `8E2F29E0…` 一致 |
| `docs/design/S4_RANKING_SPEC.md` | 206 | `b43da4aca577e239e3a92594023480ba3346b229762a57c4d8eb41f0c2ea1b10` | 设计 v2 |
| `app/api/routes.py` | 561 | `f3ef63d4f1a722003826a1c8d8ea917826a538b4493b667758df7955a1a07630` | 与 S4-B1 验证时点同哈希（GET 未改） |

## 7. 前后守护

| 项 | 运行前 | 运行后 |
| --- | --- | --- |
| `instance/app.db` sha256 | `e073f828cf0f30d6206361bba3a729826be096be3308f5a5dc204406dae4eb85` | **相同** |
| `instance/app.db-wal` / `-shm` | 不存在 | **不存在** |
| live `app/**`、`tests/**` | — | 未改（镜像 parity=0；本任务只写 `<run>/` 与 `docs/validation/S4_RANKING_ACCEPTANCE.md`） |

- 证据文本：10 件证据文件 UTF-8 无 BOM、仅 LF、读回 **exit=0**（[06_evidence_check_cmd.log](<../../tests/acceptance/_tmp/s4_ranking_verify_v1/run_20261020_140101_rankverify/evidence/06_evidence_check_cmd.log>)、[08_evidence_readback.txt](<../../tests/acceptance/_tmp/s4_ranking_verify_v1/run_20261020_140101_rankverify/evidence/08_evidence_readback.txt>)）。

## 8. 验证过程修正史（如实保留，均未触 live）

1. **attempt1**：探针 E1 断言写错——我预期"跨 TTL 边界仅少 +6 分"（score 94），实际真实 now 已使 G2 读时 expired ⇒ `recompute` 判 stale ⇒ 候选落 **blocked** 池（score=null）。首次结果保留为 `05_probe_attempt1_pool.json` / `05_probe_cmd_attempt1_pool.log`。
2. **attempt2（最终）**：把 E1 改为断言 `pool=blocked` 且 `reasons` 以 `stale:` 开头，重跑后 **21/21 PASS**。
修正仅发生在 `<run>/tools/` 与 `<run>/evidence/`；未修改 `app/**`、`tests/**`、契约、迁移、台账与业务库。

## 9. 未执行 / 未覆盖（不标 PASS）

- **未联网、未启动服务**：全部在镜像内以直接函数调用/`test_client` 执行，无 socket/HTTP server、无真实渠道。
- **排序未接入任何读路径/流水线**：未测 HTTP 级排序端点（现无该端点）、无 S5 每日流水线与提醒、无界面呈现。
- **确定性边界**：`as_of` 固定可复现，但 `_supply_stable` 用真实 now 判 TTL，跨 30 天边界时结果可能变化（探针 E1 已记录）；未宣称完全确定。
- **未测**：并发/大候选集性能、跨 data_origin 组合（实现不过滤 origin）、R-14 权重升级（属实现批）、覆盖率（未跑 coverage）、真实运行证据。
- 独立探针复用既有 `b2_helpers` 造数（未用 B 的断言）；共 21 项探针，不是全参数空间穷举。
- 结论仅限本实现（上述哈希）与本矩阵；**不宣称 S4 阶段完成**。

## 10. 证据索引

| 证据 | 路径 |
| --- | --- |
| 镜像清单/parity | [01_mirror.json](<../../tests/acceptance/_tmp/s4_ranking_verify_v1/run_20261020_140101_rankverify/evidence/01_mirror.json>) |
| 模块/DB 来源实证 | [02_path_probe.json](<../../tests/acceptance/_tmp/s4_ranking_verify_v1/run_20261020_140101_rankverify/evidence/02_path_probe.json>) |
| 单测日志 | [03_ranking_tests_cmd.log](<../../tests/acceptance/_tmp/s4_ranking_verify_v1/run_20261020_140101_rankverify/evidence/03_ranking_tests_cmd.log>) |
| 全量回归日志 | [04_discover_cmd.log](<../../tests/acceptance/_tmp/s4_ranking_verify_v1/run_20261020_140101_rankverify/evidence/04_discover_cmd.log>) |
| 独立探针结果 | [05_probe.json](<../../tests/acceptance/_tmp/s4_ranking_verify_v1/run_20261020_140101_rankverify/evidence/05_probe.json>) |
| 证据文本读回 | [08_evidence_readback.txt](<../../tests/acceptance/_tmp/s4_ranking_verify_v1/run_20261020_140101_rankverify/evidence/08_evidence_readback.txt>) |
