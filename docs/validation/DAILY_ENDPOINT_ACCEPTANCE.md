# GET /api/daily 端点 · 独立验收

> 被验对象：[app/api/routes.py](<../../app/api/routes.py>)（**603 行**，sha256 `e10354bb8248a0649e1e1e37c3ad41e2030a258cebdf349ae344b3459ed4fad7`，新增 `@bp.get("/daily")`/`_daily_args`/`get_daily`）、[tests/api/test_daily_endpoint.py](<../../tests/api/test_daily_endpoint.py>)（**133 行**，sha256 `1763a02e…`，8 项）。
> 关联未改：[app/core/daily.py](<../../app/core/daily.py>)（59 行 sha `6b3dcfde…`）、[app/core/ranking.py](<../../app/core/ranking.py>)（288 行 sha `17cd66c4…`）、[app/core/errors.py](<../../app/core/errors.py>)（34 行 sha `b5ce9076…`）、[docs/design/CONTRACT.md](<../design/CONTRACT.md>)（812 行 sha `826c24cc…`）、[README.md](<../../README.md>)（126 行 sha `61c6600d…`）、业务库 `instance/app.db` `e073f828…`。
> 验收者：独立执行者 A（实现者 B），任务 `task-5a69054ee10a5442023d08bc69e7d15b`；验收时点 2026-10-20 20:53–20:56 +08:00。
> 性质：**镜像复跑 + 独立 test_client 探针（隔离 tmp DB，未起端口）+ 前后哈希守护**。未联网、未对业务库发请求；未改被验文件/业务库/旧证据。
> 结论：**`GET /api/daily` 端点功能成立（限本报告断言与 8/325 测试范围）**——结构/字段与 `daily.daily_digest` 完全一致、参数矩阵 422/200/405 正确、空库 200、同 as_of 字节幂等、12 张业务表零写入、既有端点/路由计数（API 24 + 页面 4）未破、业务库与旧证据哈希未变。**不宣称 S5 完成**；README/CONTRACT 文字待同步项见 §9。

## 0. 运行目录与证据

- 唯一 run：`tests/acceptance/_tmp/daily_endpoint_verify_v1/run_20261020_205308_dailyverify/`
- 关键证据：[02_path_probe.json](<../../tests/acceptance/_tmp/daily_endpoint_verify_v1/run_20261020_205308_dailyverify/evidence/02_path_probe.json>)、[03_test_daily.log](<../../tests/acceptance/_tmp/daily_endpoint_verify_v1/run_20261020_205308_dailyverify/evidence/03_test_daily.log>)、[04_discover.log](<../../tests/acceptance/_tmp/daily_endpoint_verify_v1/run_20261020_205308_dailyverify/evidence/04_discover.log>)、[05_probe_daily.json](<../../tests/acceptance/_tmp/daily_endpoint_verify_v1/run_20261020_205308_dailyverify/evidence/05_probe_daily.json>)、[06_guard_after.json](<../../tests/acceptance/_tmp/daily_endpoint_verify_v1/run_20261020_205308_dailyverify/evidence/06_guard_after.json>)、[08_evidence_readback.txt](<../../tests/acceptance/_tmp/daily_endpoint_verify_v1/run_20261020_205308_dailyverify/evidence/08_evidence_readback.txt>)。
- 日志：`tools/run_and_log_utf8.py`（UTF-8 无 BOM，含 `label/cmd/cwd/start_utc/exit/stdout/stderr`）。

## 1. 镜像与模块来源

- `build_mirror`：live `app/**`+`tests/**`+`requirements.txt` → **83 件 parity mismatched=0/extra=0**；另补 `tools/` 3 件 parity 0、`docs/design/CONTRACT.md`+`README.md` 2 件 parity 0 → **合计 88 件**（`01_mirror.log`/`01b_mirror_extra.log`/`01c_mirror_docs.log` 均 exit=0）。
- 模块来源（cwd=mirror、PYTHONPATH=mirror、PYTHONDONTWRITEBYTECODE=1、venv 3.12.14）：**13/13 checks + 8/8 hash PASS**——`app`/`app.storage.db` 从镜像加载、`config.ROOT` 在镜像、`APP_VERSION==__version__=="0.1.0"`、`schema_version==app_schema_version()==2`、`/api/daily` 在 `url_map` 中、**API 规则 24 / 页面规则 4**；hash 与 live 一致（routes 603/`e10354bb…`、test_daily 133/`1763a02e…`、daily 59/`6b3dcfde…`、ranking 288/`17cd66c4…`、errors 34/`b5ce9076…`、api/__init__ 5、CONTRACT 812/`826c24cc…`、README 126/`61c6600d…`）→ [02_path_probe.json](<../../tests/acceptance/_tmp/daily_endpoint_verify_v1/run_20261020_205308_dailyverify/evidence/02_path_probe.json>)（**exit=0**）。

## 2. 两轮测试（真实 exit，UTF-8 日志）

| 轮次 | 命令（cwd=mirror） | 结果 |
| --- | --- | --- |
| daily 端点测试 | `-m tests.api.test_daily_endpoint` | **Ran 8 tests — OK，exit=0**（0.607s，`start_utc=2026-10-20T12:54:53Z`） |
| 完整回归 | `-m unittest discover -s tests -t .` | **Ran 325 tests — OK，exit=0**（48.322s） |

- 与 B 自述 **8/325 一致**；证据：[03_test_daily.log](<../../tests/acceptance/_tmp/daily_endpoint_verify_v1/run_20261020_205308_dailyverify/evidence/03_test_daily.log>)、[04_discover.log](<../../tests/acceptance/_tmp/daily_endpoint_verify_v1/run_20261020_205308_dailyverify/evidence/04_discover.log>)。

## 3. 独立探针（12/12 PASS，不复用 B 断言）

证据：[05_probe_daily.json](<../../tests/acceptance/_tmp/daily_endpoint_verify_v1/run_20261020_205308_dailyverify/evidence/05_probe_daily.json>)（**exit=0**）；隔离 tmp DB + `create_app` + `test_client`。

| # | 检查 | 结果 |
| --- | --- | --- |
| E1 | 空库 `GET /api/daily?as_of=2026-10-20T12:00:00Z` → **200**；键集合与直接 `daily_digest` 返回**完全一致**；响应体与直接返回值**逐字段相等**；`kind=daily_digest`、`as_of` 透传、`digest_date=2026-10-20`、`daily_limit=5`、`top=[]`、counts 全 0、`source=ranking.rank_candidates`、`application/json` | PASS |
| D1 | 造数（6 推荐+blocked+观察+探索+insufficient+excluded，candidate 11 行）后 `limit=5` → **200**、响应 == 直接 `daily_digest` 逐字段相等；counts 精确 `top=5/blocked=1/observing=1/exploring=1/omitted=1/insufficient=1/excluded=1`，top 长度 5、daily_limit 5 | PASS |
| Z1 | **12 张业务表**（candidate/demand_signal/evidence/supply_offer/cost_item/gate_review/review_item/run_record/import_batch/import_row_result/draft/feedback）请求前后全行快照相同、DB sha 前后相同（`4cb97fc9…`） | PASS |
| Z2 | 全部 **15 张表**（含 idempotency_key/source/schema_migrations）行快照与迁移行前后相同 | PASS |
| Z3 | 参数矩阵全部请求后再次核验：15 表快照与 DB sha 仍不变 | PASS |

## 4. 参数矩阵（422 / 200 / 405，无 500）

- **as_of 非法 → 均 422 `invalid_field`、details 含 `field=as_of`**：缺失、`2026-10-20`、`2026-10-20T12:00:00`（无 Z）、`2026-10-20T12:00:00+08:00`、`2026-02-30T00:00:00Z`（日历非法）、`2026-13-01T00:00:00Z`（月份非法）、`not-a-date`（共 7 例）。
- **limit 非法 → 均 422 `invalid_field`、details 含 `field=limit`**：`0`、`21`、`-1`、`abc`、`3.5`、`+5`、空值、多值首个非法（`limit=21&limit=1`）（共 8 例）。
- **合法 limit → 200 且 `daily_limit` 回显**：`1`、`5`、`20`；缺省时 `daily_limit=5`。
- **方法约束**：`POST /api/daily` → **405**（错误体 code=`invalid_state`）。
- 全部错误路径均非 5xx；错误响应 JSON 含 `error.code`/`error.details`。

## 5. 幂等与只读

- 同 `as_of`/`limit=3` 连续两次响应 **字节完全一致**（4,229 B）；默认参数连续两次响应亦字节一致（I1 PASS）。
- 零写入结论见 Z1–Z3：12 张业务表 + 全 15 表行快照不变、DB sha `4cb97fc9…` 前后一致、无 `-wal/-shm`。

## 6. 兼容性与路由计数

- `/api/health` → 200，四键 `ok/version/schema_version/time`，`version=0.1.0`、`schema_version=2`；`/api/candidates`、`/api/sources` 均 200（C1 PASS）。
- `url_map`：**API 规则 24**（23+`/api/daily`）、**页面规则 4**（`/`、`/opportunity/<id>`、`/import`、`/ops`）；`/api/daily` 已注册，未破坏既有路由（C2 PASS，规则清单见证据）。

## 7. `GET /api/daily` 与 `daily_digest` 的边界（核对实现而非重算）

- 端点仅 `get_db()` + 参数校验 + `daily_digest(get_db(), as_of, limit)`，无写库、无缓存、无额外排序/截断；`daily_digest` 只调用 `ranking.rank_candidates`（纯只读）。
- `budget_minutes`（默认 30）与 `scenario_params`（默认 None）未暴露为 query 参数，端点固定使用函数默认值（记录，非缺陷）。

## 8. 前后哈希守护

- **38 个文件 before/after 完全一致**：[00_guard_before.json](<../../tests/acceptance/_tmp/daily_endpoint_verify_v1/run_20261020_205308_dailyverify/evidence/00_guard_before.json>) / [06_guard_after.json](<../../tests/acceptance/_tmp/daily_endpoint_verify_v1/run_20261020_205308_dailyverify/evidence/06_guard_after.json>)（exit=0）——routes `e10354bb…`、test_daily `1763a02e…`、daily/ranking/errors、app/__init__/db.py、b2_helpers、CONTRACT `826c24cc…`、README `61c6600d…`、tools 三脚本、tests/tools 三文件、冻结三文件、业务库 `e073f828…`、real1/diag1/real2/real_run_v2 旧证据；`wal=False shm=False`。
- 14 件核验证据 UTF-8 无 BOM/LF、读回 **exit=0**（[08_evidence_readback.txt](<../../tests/acceptance/_tmp/daily_endpoint_verify_v1/run_20261020_205308_dailyverify/evidence/08_evidence_readback.txt>)）。

## 9. 待同步文字（如实记录，不在本次修改）

- **README 过期**：仍写"全站共 **27 条路由（23 API + 4 页面）**"且未列 `GET /api/daily`（实际为 **28 条（24 API + 4 页面）**）。
- **CONTRACT 接口文档不一致**：CONTRACT 表 #19 写 `GET /api/summary/daily?date=`（每日摘要 `[S5]`），实际端点为实现确认的 `GET /api/daily?as_of=`；需评审后同步（本次未改契约/README）。
- 结论仅针对实现与行为；文字同步属文档工作项。

## 10. 结论与未覆盖

- **结论：`GET /api/daily` 端点功能成立**（只读、结构/字段与 `daily_digest` 一致、参数矩阵 422/200/405 正确、空库 200、字节幂等、12 表零写入、既有端点与路由计数未破、业务库/旧证据未变）。**不宣称 S5 完成**。
- 未覆盖：README/CONTRACT 文字待同步（§9）；未对真实业务库发请求（隔离 DB）；未覆盖大数据量/性能/并发/缓存；未验证生产 WSGI/端口部署与跨进程行为；`budget_minutes`/`scenario_params` 未暴露；错误体其余字段（details reason 文案）未逐字断言；未联网、未起端口。
- 过程：本批一次通过，无我方断言返工；未改被验文件、业务库、旧证据。

## 11. 证据索引

| 证据 | 路径 |
| --- | --- |
| 模块来源/哈希（13+8） | [02_path_probe.json](<../../tests/acceptance/_tmp/daily_endpoint_verify_v1/run_20261020_205308_dailyverify/evidence/02_path_probe.json>) |
| daily 端点测试 8 OK | [03_test_daily.log](<../../tests/acceptance/_tmp/daily_endpoint_verify_v1/run_20261020_205308_dailyverify/evidence/03_test_daily.log>) |
| 全量 325 OK | [04_discover.log](<../../tests/acceptance/_tmp/daily_endpoint_verify_v1/run_20261020_205308_dailyverify/evidence/04_discover.log>) |
| 独立探针（12 项） | [05_probe_daily.json](<../../tests/acceptance/_tmp/daily_endpoint_verify_v1/run_20261020_205308_dailyverify/evidence/05_probe_daily.json>) |
| 前后守护（38 文件） | [00_guard_before.json](<../../tests/acceptance/_tmp/daily_endpoint_verify_v1/run_20261020_205308_dailyverify/evidence/00_guard_before.json>) / [06_guard_after.json](<../../tests/acceptance/_tmp/daily_endpoint_verify_v1/run_20261020_205308_dailyverify/evidence/06_guard_after.json>) |
| 镜像 parity（83+3+2 件） | [01_mirror.log](<../../tests/acceptance/_tmp/daily_endpoint_verify_v1/run_20261020_205308_dailyverify/evidence/01_mirror.log>) / [01b_mirror_extra.log](<../../tests/acceptance/_tmp/daily_endpoint_verify_v1/run_20261020_205308_dailyverify/evidence/01b_mirror_extra.log>) / [01c_mirror_docs.log](<../../tests/acceptance/_tmp/daily_endpoint_verify_v1/run_20261020_205308_dailyverify/evidence/01c_mirror_docs.log>) |
| 证据文本读回 | [08_evidence_readback.txt](<../../tests/acceptance/_tmp/daily_endpoint_verify_v1/run_20261020_205308_dailyverify/evidence/08_evidence_readback.txt>) |
