# CONTRACT #19 每日摘要读路径 · 独立验收

> 被验对象（按 CONTRACT #19 收敛后）：
> - [app/api/routes.py](<../../app/api/routes.py>)（**608 行**，sha256 `501aa611…`，`GET /api/summary/daily?date=&include_synthetic=0/1`，删除 `/api/daily`）；
> - [app/core/daily.py](<../../app/core/daily.py>)（**64 行**，sha256 `7916346c…`，`daily_digest(include_synthetic=False)` 默认 real-only）；
> - [app/core/ranking.py](<../../app/core/ranking.py>)（**296 行**，sha256 `1c73caec…`，同名参数默认 `True`，**过滤在 judge/排序之前**）；
> - 测试 [tests/api/test_daily_endpoint.py](<../../tests/api/test_daily_endpoint.py>)（157 行 / 8 项）、[tests/core/test_daily.py](<../../tests/core/test_daily.py>)（174 行 / 5 项，2 行必要适配）。
> 关联：[docs/design/CONTRACT.md](<../design/CONTRACT.md>)（812 行 sha `826c24cc…` 未改）、[README.md](<../../README.md>)（128 行 sha `83c3d403…`，已写 28 路由/24 API + real-only）、[tools/export_daily.py](<../../tools/export_daily.py>)（153 行 sha `d71dfb2d…` 未改）、业务库 `instance/app.db` `e073f828…`。
> 验收者：独立执行者 A（实现者 B），任务 `task-ce7124556103e8f9d0fa7aef63db4461`；验收时点 2026-10-20 21:16–21:21 +08:00。
> 性质：**镜像复跑 + 独立 test_client 探针（隔离 tmp DB，未起端口）+ 前后哈希守护**。未联网、未对业务库发请求；未改被验文件/业务库/旧证据。
> 结论：**CONTRACT #19 每日摘要读路径成立（限本报告断言与 8/5/325 测试范围）**——路径/参数/≤5 对齐 #19、date 矩阵 422、默认 real-only（合成分数更高仍被排除）、`include_synthetic=1` 纳入且与 `daily_digest` 逐字段一致、`/api/daily` 404、路由 24/页面 4、零写入、C 导出 real-only 回归通过。**不宣称 S5 完成**；限制见 §11。

## 0. 运行目录与证据

- 唯一 run：`tests/acceptance/_tmp/summary_daily_verify_v1/run_20261020_211650_summaryverify/`
- 关键证据：[02_path_probe.json](<../../tests/acceptance/_tmp/summary_daily_verify_v1/run_20261020_211650_summaryverify/evidence/02_path_probe.json>)、[03_test_endpoint.log](<../../tests/acceptance/_tmp/summary_daily_verify_v1/run_20261020_211650_summaryverify/evidence/03_test_endpoint.log>)、[04_test_core_daily.log](<../../tests/acceptance/_tmp/summary_daily_verify_v1/run_20261020_211650_summaryverify/evidence/04_test_core_daily.log>)、[05_test_export.log](<../../tests/acceptance/_tmp/summary_daily_verify_v1/run_20261020_211650_summaryverify/evidence/05_test_export.log>)、[06_discover.log](<../../tests/acceptance/_tmp/summary_daily_verify_v1/run_20261020_211650_summaryverify/evidence/06_discover.log>)、[07_probe_summary.json](<../../tests/acceptance/_tmp/summary_daily_verify_v1/run_20261020_211650_summaryverify/evidence/07_probe_summary.json>)、[08_guard_after.json](<../../tests/acceptance/_tmp/summary_daily_verify_v1/run_20261020_211650_summaryverify/evidence/08_guard_after.json>)、[08_evidence_readback.txt](<../../tests/acceptance/_tmp/summary_daily_verify_v1/run_20261020_211650_summaryverify/evidence/08_evidence_readback.txt>)。
- 日志：`tools/run_and_log_utf8.py`（UTF-8 无 BOM，含 `label/cmd/cwd/start_utc/exit/stdout/stderr`）。

## 1. CONTRACT #19 逐条核对

| #19 要求 | 实测 |
| --- | --- |
| 路径 `GET /api/summary/daily` | `url_map` 中存在 `/api/summary/daily`（且 `/api/daily` 已删除） |
| 参数 `date=` | 仅读取 `date`；`date` 严格 `YYYY-MM-DD` 且必须为真实日历日（`datetime.strptime` 校验）；`as_of` 参数不被接受（只传 `as_of` → 422 `date` 缺失） |
| 每日摘要 ≤5 | `daily_limit` 固定 **5**；`include_synthetic=1` 且有 7 条推荐时 `top` 恰为 5、`omitted=2`；`?limit=10` 被忽略（仍 5） |
| #19 表格条目 | CONTRACT 812 行原文未改（`| 19 | GET /api/summary/daily?date= | 每日摘要（≤5） |`）；`/api/daily` 破坏性删除、无别名（用户裁定 A 的直接结果） |
| real-only 条款（L105/§0.5） | 默认 real-only；`include_synthetic=1` 才纳入合成（见 §5） |

## 2. 镜像与模块来源

- `build_mirror`：app/tests+requirements **83 件 parity mismatched=0/extra=0**；补 `tools/` 3 件 parity 0；补 `docs/design/CONTRACT.md`+`README.md` 2 件 parity 0 → **合计 88 件**（01_mirror/01b_mirror_extra/01c_mirror_docs 均 exit=0）。
- 模块来源（cwd=mirror、PYTHONPATH=mirror、PYTHONDONTWRITEBYTECODE=1、venv 3.12.14）：**18/18 checks + 9/9 hash PASS**——`app`/`app.storage.db` 从镜像加载、`APP_VERSION==__version__=="0.1.0"`、schema=2；`daily_digest.include_synthetic` 默认 **False**、`rank_candidates.include_synthetic` 默认 **True**；`ranking.py` 中过滤位置 `if not include_synthetic`（偏移 11118）**早于**判池循环（11380）与排序（11615）——**排序前过滤、非事后截断**；API 规则 **24**（含 summary/daily、不含 /api/daily）、页面 **4**；hash 与 live 一致（routes 608/`501aa611…`、daily 64/`7916346c…`、ranking 296/`1c73caec…`、test_daily 157/`f58874b8…`、core_test_daily 174/`6159e7d5…`、README 128/`83c3d403…`、CONTRACT 812/`826c24cc…`、export 153/`d71dfb2d…`）→ [02_path_probe.json](<../../tests/acceptance/_tmp/summary_daily_verify_v1/run_20261020_211650_summaryverify/evidence/02_path_probe.json>)（**exit=0**）。

## 3. 四轮测试（真实 exit，UTF-8 日志）

| 轮次 | 命令（cwd=mirror） | 结果 |
| --- | --- | --- |
| 端点测试 | `-m tests.api.test_daily_endpoint` | **Ran 8 tests — OK，exit=0**（1.528s，`start_utc=2026-10-20T13:19:58Z`） |
| 纯函数测试 | `-m tests.core.test_daily` | **Ran 5 tests — OK，exit=0**（2.470s） |
| C 导出回归 | `-m tests.tools.test_export_daily` | **Ran 10 tests — OK，exit=0**（3.297s） |
| 完整回归 | `-m unittest discover -s tests -t .` | **Ran 325 tests — OK，exit=0**（48.901s） |

- 与 B 自述 **8/5/325（另 10 导出）一致**；证据：[03_test_endpoint.log](<../../tests/acceptance/_tmp/summary_daily_verify_v1/run_20261020_211650_summaryverify/evidence/03_test_endpoint.log>)、[04_test_core_daily.log](<../../tests/acceptance/_tmp/summary_daily_verify_v1/run_20261020_211650_summaryverify/evidence/04_test_core_daily.log>)、[05_test_export.log](<../../tests/acceptance/_tmp/summary_daily_verify_v1/run_20261020_211650_summaryverify/evidence/05_test_export.log>)、[06_discover.log](<../../tests/acceptance/_tmp/summary_daily_verify_v1/run_20261020_211650_summaryverify/evidence/06_discover.log>)。

## 4. 独立探针（13/13 PASS；混合 real+synthetic，合成分数更高）

证据：[07_probe_summary.json](<../../tests/acceptance/_tmp/summary_daily_verify_v1/run_20261020_211650_summaryverify/evidence/07_probe_summary.json>)（**exit=0**）。隔离 DB：1 个 `real` 候选（真实 CSV 导入 API，T1，score=90）+ 6 个 `synthetic` 候选（T1，score=100）。

| # | 检查 | 结果 |
| --- | --- | --- |
| E1 | 空库 `GET /api/summary/daily?date=2026-10-20` → **200**；键集合与直接 `daily_digest` 一致、逐字段相等；`as_of=2026-10-20T00:00:00Z`、`digest_date=2026-10-20`、`daily_limit=5`、`top=[]`、counts 全 0 | PASS |
| M1 | **默认 real-only**：响应 == `daily_digest(include_synthetic=False)`；`include_synthetic=0` 与缺省相同；**6 个合成候选 id 全部不出现**（尽管其分数 100>90）；`top` 仅真实候选 1 条、`daily_limit=5` | PASS |
| M2 | `include_synthetic=1`：响应 == `daily_digest(include_synthetic=True)`；**含合成候选**（top 5 均为合成，score=100）；真实候选进入 `omitted`（rank 7）；`omitted=2`、`top=5`；合成最高分 100 > 真实 90 | PASS |
| M3 | `include_synthetic` 非法值 `2/yes/01/true/-1/1.0/空` → 均 **422 invalid_field**（details field=include_synthetic） | PASS |
| P1 | date 矩阵：缺失、`2026-10-20T12:00:00Z`、`2026-10-20 12:00:00`、`20261020`、`2026-13-01`、`2026-02-30`、`not-a-date`、`2026-2-3` → **均 422 invalid_field**（details field=date），无 500 | PASS |
| P2 | 仅传 `as_of` → 422（date 必填）；`?date=…&limit=10` → 200 且 `daily_limit` 仍 5（limit 不暴露） | PASS |
| I1 | 同查询（默认与 include=1）连续两次响应**字节一致**（1,489 B） | PASS |
| Z1 | **12 张业务表**请求前后全行快照相同（candidate 7/demand 7/evidence 21/supply 7/cost 70/gate 28/review 0/run 7/import 7/rows 35/draft 0/feedback 0）；DB sha 前后相同（`b5c77bde…`） | PASS |
| Z2 | 全部 **15 张表**行快照与迁移行前后相同 | PASS |
| R1 | `/api/daily?date=…` → **404**；POST `/api/summary/daily` → **405**；API 规则 **24**（含 summary/daily、不含 /api/daily）、页面 **4** | PASS |
| S1 | `daily_digest(...)` 默认 == real-only；`rank_candidates(...)` 默认 **True** 时 real+synthetic 均判池（pools.recommended=7）；#19 仅约束每日摘要 | PASS |
| X1 | C 导出回归：`export_daily.export` 产物 digest == `daily_digest(False)`（top=1、无合成）、CSV 2 行；`tools/export_daily.py` 无 `include_synthetic` 开关（CLI 不暴露） | PASS |
| X2 | README 已含 `GET /api/summary/daily?date=YYYY-MM-DD`、"只统计 `data_origin='real'`"、"28 条路由（24 API + 4 页面）" | PASS |

## 5. 幂等与零写入（补充）

- 同查询连续两次响应字节一致（默认 / include=1 均 PASS）。
- 12 张业务表与全 15 表行快照、DB sha（`b5c77bde…`）在完整参数矩阵请求前后不变；无 `-wal/-shm`。

## 6. C 导出回归与 README

- `-m tests.tools.test_export_daily`：**Ran 10 OK，exit=0**；导出探针（X1）显示 C 导出复用 `daily_digest` 默认值 → real-only，合成候选不出现；README 69 行明确"只统计 `data_origin='real'`；合成数据需 API 侧 `include_synthetic=1`；CLI 不暴露该开关"，与实现一致。
- README 已更新为 28 路由（24 API+4 页面）并列出 summary/daily（B 已改；本次守护确认未再变动）。

## 7. 前后哈希守护

- **39 个文件 before/after 完全一致**：[00_guard_before.json](<../../tests/acceptance/_tmp/summary_daily_verify_v1/run_20261020_211650_summaryverify/evidence/00_guard_before.json>) / [08_guard_after.json](<../../tests/acceptance/_tmp/summary_daily_verify_v1/run_20261020_211650_summaryverify/evidence/08_guard_after.json>)（exit=0）——routes `501aa611…`、daily `7916346c…`、ranking `1c73caec…`、test_daily endpoint `f58874b8…`、core test_daily `6159e7d5…`、b2_helpers、CONTRACT `826c24cc…`、README `83c3d403…`、export_daily `d71dfb2d…`、test_export_daily `58f51a0e…`、tools backup/restore、冻结三文件、业务库 `e073f828…`、real1/diag1/real2/real_run_v2 旧证据；`wal=False shm=False`。
- 20 件核验证据 UTF-8 无 BOM/LF、读回 **exit=0**（[08_evidence_readback.txt](<../../tests/acceptance/_tmp/summary_daily_verify_v1/run_20261020_211650_summaryverify/evidence/08_evidence_readback.txt>)）。

## 8. 结论、限制与未覆盖

- **结论：CONTRACT #19 每日摘要读路径成立**（路径/参数/≤5、date 422 矩阵、默认 real-only 且合成高分仍被排除、`include_synthetic=1` 纳入并与 `daily_digest` 逐字段一致、`/api/daily` 404、路由 24/页面 4、字节幂等、12 表零写入、C 导出 real-only 回归、8/5/10/325 真实 exit=0、业务库/旧证据未变）。**不宣称 S5 完成**。
- 限制/未覆盖：
  1. **date→as_of 时点假设**：`date` 统一映射为 `date+"T00:00:00Z"`（午夜 UTC），无时区/小时粒度；`as_of` 不可传。
  2. **limit 固定 5**：CONTRACT #19 的"≤5"以固定 5 实现，`limit` 查询参数不暴露（传 10 被忽略）。
  3. **`/api/daily` 破坏性删除**：旧路径 404、无兼容别名（用户裁定 A 匹配契约的直接结果）。
  4. **ranking 默认非 real-only**（默认 True，内部兼容）；`daily_digest`/HTTP/C 导出均显式/默认 False；其他调用方若需 real-only 必须自行传 False。
  5. 未对真实业务库发请求（隔离 DB）；未覆盖大数据量/性能/并发/缓存、生产 WSGI/端口；未验证鉴权（本地单用户模型无鉴权）。
  6. 混合库中合成"分数更高"是通过夹具调价（销售价/成本）构造的**机制性验证**，非真实业务评分分布。
  7. 未联网、未起端口；CONTRACT 原文未改（#19 已对齐，无需改动）。

## 9. 证据索引

| 证据 | 路径 |
| --- | --- |
| 模块来源/哈希（18+9） | [02_path_probe.json](<../../tests/acceptance/_tmp/summary_daily_verify_v1/run_20261020_211650_summaryverify/evidence/02_path_probe.json>) |
| 端点测试 8 OK | [03_test_endpoint.log](<../../tests/acceptance/_tmp/summary_daily_verify_v1/run_20261020_211650_summaryverify/evidence/03_test_endpoint.log>) |
| 纯函数测试 5 OK | [04_test_core_daily.log](<../../tests/acceptance/_tmp/summary_daily_verify_v1/run_20261020_211650_summaryverify/evidence/04_test_core_daily.log>) |
| C 导出回归 10 OK | [05_test_export.log](<../../tests/acceptance/_tmp/summary_daily_verify_v1/run_20261020_211650_summaryverify/evidence/05_test_export.log>) |
| 全量 325 OK | [06_discover.log](<../../tests/acceptance/_tmp/summary_daily_verify_v1/run_20261020_211650_summaryverify/evidence/06_discover.log>) |
| 独立探针（13 项：date/real-only/include/幂等/零写入/路由/默认/C导出/README） | [07_probe_summary.json](<../../tests/acceptance/_tmp/summary_daily_verify_v1/run_20261020_211650_summaryverify/evidence/07_probe_summary.json>) |
| 前后守护（39 文件） | [00_guard_before.json](<../../tests/acceptance/_tmp/summary_daily_verify_v1/run_20261020_211650_summaryverify/evidence/00_guard_before.json>) / [08_guard_after.json](<../../tests/acceptance/_tmp/summary_daily_verify_v1/run_20261020_211650_summaryverify/evidence/08_guard_after.json>) |
| 镜像 parity（83+3+2 件） | [01_mirror.log](<../../tests/acceptance/_tmp/summary_daily_verify_v1/run_20261020_211650_summaryverify/evidence/01_mirror.log>) / [01b_mirror_extra.log](<../../tests/acceptance/_tmp/summary_daily_verify_v1/run_20261020_211650_summaryverify/evidence/01b_mirror_extra.log>) / [01c_mirror_docs.log](<../../tests/acceptance/_tmp/summary_daily_verify_v1/run_20261020_211650_summaryverify/evidence/01c_mirror_docs.log>) |
| 证据文本读回 | [08_evidence_readback.txt](<../../tests/acceptance/_tmp/summary_daily_verify_v1/run_20261020_211650_summaryverify/evidence/08_evidence_readback.txt>) |
