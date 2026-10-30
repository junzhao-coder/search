# S5 每日摘要聚合 · 独立验证验收（非实现者复跑）

> 验证对象：`app/core/daily.py`（**59 行**，sha256 `6b3dcfdea5bec811364c14b065fda2f13ebf9a4851c3342c17218c03ff6c6c31`）与 `tests/core/test_daily.py`（**170 行**，sha256 `e5ca9b2eb48aea9b4f85261cef640a686d95d99d5af2b0849fdbb3290ca756f4`）。
> 上游（未改）：`app/core/ranking.py`（**288 行**，sha256 `17cd66c4b401aa4329c91eabf311438d7c667b85f0841fa8ff96d5198e8cc396`）；设计依据 [S4_RANKING_SPEC.md](<../design/S4_RANKING_SPEC.md>) v2 §6/§8（206 行）。
> 验证者：独立执行者 A（实现者为 B），任务 `task-da88bc5142ef4b8f82d3e06d72d98eb6`；验证时点 2026-10-20 14:14–14:17 +08:00。
> 性质：**隔离镜像复跑 + 独立探针**。未修改 `app/**`、`tests/**`、契约、迁移、台账与业务库；**未联网、未启动服务**（无 socket/HTTP server）。
> 结论：**通过（仅限本实现与聚合范围）**——每日摘要单测 5/5、全量套件 253/253 均 `OK exit=0`；独立探针 **21/21** 全过；业务库哈希前后一致、WAL/SHM 不存在。**不宣称 S5 完成**；未覆盖项见 §7。

## 1. 运行目录与镜像

- 唯一 run：`tests/acceptance/_tmp/s5_daily_verify_v1/run_20261020_141437_dailyverify/`
- 镜像：`<run>/mirror/`（复制 live `app/**`+`tests/**`+`requirements.txt`；排除 `__pycache__`/`_tmp`/`_snapshots`/`.venv`/`.pytest_cache`/`.mypy_cache` 与 reparse 目录；无 `.pyc`）
- 证据：[01_mirror.json](<../../tests/acceptance/_tmp/s5_daily_verify_v1/run_20261020_141437_dailyverify/evidence/01_mirror.json>)、[01_mirror_cmd.log](<../../tests/acceptance/_tmp/s5_daily_verify_v1/run_20261020_141437_dailyverify/evidence/01_mirror_cmd.log>)（**exit=0**）

| 项 | 结果 |
| --- | --- |
| 复制文件 | **75**（app+tests+requirements） |
| 剪枝目录 | 16；reparse/junction 跳过 **0**；遍历异常 **0** |
| 逐件 parity | **mismatched=0 / extra=0**（bytes+sha256 与 live 源一致） |
| 关键哈希 | daily `6b3dcfde…`、test_daily `e5ca9b2e…`、ranking `17cd66c4…`（上游未改）、routes `f3ef63d4…`（未改） |

## 2. 模块与 DB 来源实证

- 证据：[02_path_probe.json](<../../tests/acceptance/_tmp/s5_daily_verify_v1/run_20261020_141437_dailyverify/evidence/02_path_probe.json>)、[02_path_probe_cmd.log](<../../tests/acceptance/_tmp/s5_daily_verify_v1/run_20261020_141437_dailyverify/evidence/02_path_probe_cmd.log>)（**exit=0，checks=11/11**）
- 运行方式：`cwd=<run>/mirror`、`PYTHONPATH=<run>/mirror`、`PYTHONDONTWRITEBYTECODE=1`、venv python 3.12。
- 逐项：cwd 是镜像、mirror 在 sys.path、`app`/`app.core.daily`/`app.core.ranking`/`app.core.matching`/`tests.core.test_daily`/`config.ROOT` 全在镜像内、fresh DB 在 run 内且 cfg 一致、sys.path 无 live/旧镜像路径。

## 3. 两轮测试（真实 exit）

| 轮次 | 命令（cwd=mirror） | 结果 | 证据 |
| --- | --- | --- | --- |
| 摘要单测 | `-m tests.core.test_daily` | **Ran 5 tests in 2.449s — OK**，**exit=0** | [03_daily_tests_cmd.log](<../../tests/acceptance/_tmp/s5_daily_verify_v1/run_20261020_141437_dailyverify/evidence/03_daily_tests_cmd.log>) |
| 完整回归 | `-m unittest discover -s tests -t .` | **Ran 253 tests in 41.911s — OK**，**exit=0** | [04_discover_cmd.log](<../../tests/acceptance/_tmp/s5_daily_verify_v1/run_20261020_141437_dailyverify/evidence/04_discover_cmd.log>) |

- 与 B 宣称对照：B 称 **5/253** → **实测 5/253 一致**；B 称行数 **56/164** → 实测 **59/170**（行数不实；sha256 `6B3DCFDE…`/`E5CA9B2E…` 与实测一致，见 §5）。

## 4. 静态扫描与独立探针（21/21）

- 证据：[05_probe.json](<../../tests/acceptance/_tmp/s5_daily_verify_v1/run_20261020_141437_dailyverify/evidence/05_probe.json>)、[05_probe_cmd.log](<../../tests/acceptance/_tmp/s5_daily_verify_v1/run_20261020_141437_dailyverify/evidence/05_probe_cmd.log>)（**exit=0，checks=21 passed=21 failed=0**）
- 探针由本执行者独立编写（未复用 B 的测试断言），仅复用既有 `tests/api/b2_helpers` 造数。

| # | 检查 | 结果 |
| --- | --- | --- |
| A1 | `daily.py` AST 扫描：无 INSERT/UPDATE/DELETE/REPLACE/CREATE/DROP/ALTER/BEGIN/COMMIT/`.commit()`（该模块仅调用 `ranking.rank_candidates`） | PASS（write_calls=[]） |
| A2 | `app/api/routes.py` 无 `daily`/`daily_digest` 引用 | PASS（routes_refs=[]） |
| A3 | `routes.py` sha256 = `f3ef63d4…`（与上游验证时点一致，GET 未改） | PASS |
| A4 | `ranking.py` sha256 = `17cd66c4…`（上游未改） | PASS |
| A5 | 候选详情响应键与验证前一致（12 个既有键） | PASS |
| B1 | digest `top` 的 candidate_id 序列 == ranking 中 `pool=recommended 且 daily_pick` 的序列 | PASS（5 条，逐项相同） |
| B2 | digest `top` 的 `rank` 序列 == ranking 对应项（实测 `[2,3,4,5,6]`，因 blocked 占 rank 1） | PASS |
| B3 | 仅推荐池进 top（5 条 ⊆ 6 推荐；blocked/observing/exploring/excluded 均不在 top） | PASS |
| B4 | blocked 独立列出且与 ranking blocked 一致；`ranking.items[0].pool == "blocked"`（置顶）；`reasons[0]` 以 `stale:` 开头、`next_action` 非空 | PASS |
| B5 | `pools`/`omitted` 与 ranking 原样透传一致（omitted=1，rank 7） | PASS |
| B6 | observing/exploring 列表与 ranking 对应池一致 | PASS |
| B7 | counts 一致：top=5/blocked=1/observing=1/exploring=1/omitted=1/insufficient=1/excluded=1 | PASS |
| B8 | 元数据：kind=`daily_digest`、as_of、digest_date=`2026-10-20`、rank_version、daily_limit=5、source=`ranking.rank_candidates`、pending_confirmation、display_note 含"不凑数/不是收益"、scenario_params/budget_minutes 透传 | PASS |
| C1 | limit=20（>推荐数）：top=3、omitted=[]、推荐项 `daily_pick` 全真 | PASS |
| C2 | limit=1：top=1、omitted=2 且与 ranking `omitted` 一致、推荐项仅 1 个 `daily_pick` | PASS |
| C3 | limit=0（实现未报错）：top=[]、3 个推荐项全部进 `omitted`（rank 1..3、reason"超出每日 0 条上限"）、无 `daily_pick` | PASS（记录实际行为） |
| D1 | 空库：top/blocked/observing/exploring/omitted 均空，`pools` 六项全 0，`counts.top=0` | PASS |
| E1 | `as_of` 缺省 → `TypeError: missing 1 required keyword-only argument` | PASS |
| E2 | 非法 `as_of` → `ValueError`（与 ranking 同一校验） | PASS |
| E3 | 同 `as_of` 连调两次逐字段一致 | PASS |
| F1 | **全表**（candidate/demand_signal/evidence/supply_offer/cost_item/gate_review/review_item/import_batch/import_row_result/run_record/idempotency_key/draft/feedback/source/schema_migrations）两次 digest 前后逐值一致 | PASS（changed=[]） |

## 5. 行数与哈希更正（以实测为准）

| 文件 | 实测行数 | 实测 sha256 | 对照 |
| --- | --- | --- | --- |
| `app/core/daily.py` | **59** | `6b3dcfdea5bec811364c14b065fda2f13ebf9a4851c3342c17218c03ff6c6c31` | B 称 56 行 → **行数不实**；sha 与 B 的 `6B3DCFDE…` 一致；策划实读 59 ✓ |
| `tests/core/test_daily.py` | **170** | `e5ca9b2eb48aea9b4f85261cef640a686d95d99d5af2b0849fdbb3290ca756f4` | B 称 164 行 → **行数不实**；sha 与 B 的 `E5CA9B2E…` 一致；策划实读 170 ✓ |
| `app/core/ranking.py`（上游） | 288 | `17cd66c4b401aa4329c91eabf311438d7c667b85f0841fa8ff96d5198e8cc396` | 未改 ✓ |
| `app/api/routes.py` | 561 | `f3ef63d4f1a722003826a1c8d8ea917826a538b4493b667758df7955a1a07630` | 未改 ✓ |

## 6. 前后守护

| 项 | 运行前 | 运行后 |
| --- | --- | --- |
| `instance/app.db` sha256 | `e073f828cf0f30d6206361bba3a729826be096be3308f5a5dc204406dae4eb85` | **相同** |
| `instance/app.db-wal` / `-shm` | 不存在 | **不存在** |
| live `app/**`、`tests/**` | — | 未改（镜像 parity=0；本任务只写 `<run>/` 与 `docs/validation/S5_DAILY_ACCEPTANCE.md`） |

- 证据文本：8 件证据文件 UTF-8 无 BOM、仅 LF、读回 **exit=0**（[06_evidence_check_cmd.log](<../../tests/acceptance/_tmp/s5_daily_verify_v1/run_20261020_141437_dailyverify/evidence/06_evidence_check_cmd.log>)、[08_evidence_readback.txt](<../../tests/acceptance/_tmp/s5_daily_verify_v1/run_20261020_141437_dailyverify/evidence/08_evidence_readback.txt>)）。
- 本轮探针**一次通过**，无失败 attempt 需要留档（与 S4-B1/S4-B3 验证不同）。

## 7. 实现边界与未覆盖（不标 PASS）

- **纯聚合、未接线**：`daily_digest` 只调用 `ranking.rank_candidates` 并重组输出；**不接 GET、不新增端点、不持久化**（模块 docstring 明确"每日一次与提醒属 S5 流水线，未实现"）。未测 HTTP 级摘要端点（现无）。
- **每日流水线/提醒/幂等触发**：未实现、未测（S5 范围外，本批不涉及）。
- **继承上游边界**：`as_of` 必填；`_supply_stable` 用真实 now 判 30 天 TTL（跨边界非严格确定，见 S4-B3 验收 E1）；ranking 的 `origin` 未用（摘要**不按 data_origin 过滤**，real+synthetic 一并聚合；若每日摘要默认只统计 real（CONTRACT §0.5），需调用方/后续批处理）。
- **参数边界**：`daily_digest` 不暴露 `rank_version`（固定走 ranking 默认 `rank-v1`）；`limit` 未做取值校验（实测 limit=0 不报错：top 空、全部推荐进 omitted；**负数 limit 未测**）；`budget_minutes` 仅透传（与 ranking 一致，不改变排序/条数）。
- **未测**：并发/大候选集性能、`digest_date` 时区/闰日等边界、摘要持久化与历史对比、提醒通道、界面、真实网络、覆盖率（未跑 coverage）、S5 运行费用与预算保护。
- 独立探针复用既有 `b2_helpers` 造数（未复用 B 断言）；21 项探针不是全参数空间穷举。结论仅限本实现（上述哈希）与聚合矩阵；**不宣称 S5 完成**。

## 8. 证据索引

| 证据 | 路径 |
| --- | --- |
| 镜像清单/parity | [01_mirror.json](<../../tests/acceptance/_tmp/s5_daily_verify_v1/run_20261020_141437_dailyverify/evidence/01_mirror.json>) |
| 模块/DB 来源实证 | [02_path_probe.json](<../../tests/acceptance/_tmp/s5_daily_verify_v1/run_20261020_141437_dailyverify/evidence/02_path_probe.json>) |
| 单测日志 | [03_daily_tests_cmd.log](<../../tests/acceptance/_tmp/s5_daily_verify_v1/run_20261020_141437_dailyverify/evidence/03_daily_tests_cmd.log>) |
| 全量回归日志 | [04_discover_cmd.log](<../../tests/acceptance/_tmp/s5_daily_verify_v1/run_20261020_141437_dailyverify/evidence/04_discover_cmd.log>) |
| 独立探针结果 | [05_probe.json](<../../tests/acceptance/_tmp/s5_daily_verify_v1/run_20261020_141437_dailyverify/evidence/05_probe.json>) |
| 证据文本读回 | [08_evidence_readback.txt](<../../tests/acceptance/_tmp/s5_daily_verify_v1/run_20261020_141437_dailyverify/evidence/08_evidence_readback.txt>) |
