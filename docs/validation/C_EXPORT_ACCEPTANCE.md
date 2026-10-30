# C 每日摘要文件导出 · 独立验收

> 被验对象：[tools/export_daily.py](<../../tools/export_daily.py>)（**153 行**，sha256 `d71dfb2d2767e8e755ec7822c11e15520b380fc71b679bcb096a7d9cea08b93c`，与 B 自述 `D71DFB2D…` 一致）、[tests/tools/test_export_daily.py](<../../tests/tools/test_export_daily.py>)（**188 行**，sha256 `58f51a0e119884cc89fd877c7dce544651e17a3976b26d6c77fe6a29c68e6d1e`，与 B 自述 `58F51A0E…` 一致）、`tests/tools/__init__.py`（1 行，sha `65cf5571…`）。
> 关联只读依赖：[app/core/daily.py](<../../app/core/daily.py>)（59 行 sha `6b3dcfde…`）、[app/core/ranking.py](<../../app/core/ranking.py>)（288 行 sha `17cd66c4…`）；冻结三文件 `wiring.py` `bafcf397…`、`bilibili_view.py` `b0dc0ced…`、`importer.py` `a11eaf4d…`；业务库 `instance/app.db` `e073f828…`。
> 验收者：独立执行者 A（实现者 B），任务 `task-79c098801f1de3c53564f7cac6c65571`；验收时点 2026-10-20 19:33–19:42 +08:00。
> 性质：**镜像复跑 + 独立导出探针 + 只读/零写入核验 + 前后哈希守护**。未联网、未启动端口、未改被验文件/业务库/旧证据。
> 结论：**导出脚本功能成立（限本报告断言与 10/294 测试范围）**；**不宣称 S5 完成**。记录项：JSON/CSV 原始字节为 CRLF（Windows 文本模式/csv 默认），按行归一化后与 `json.dumps` 一致（语义一致、非缺陷）；未覆盖项见 §7。

## 0. 运行目录与证据

- 唯一 run：`tests/acceptance/_tmp/c_export_verify_v1/run_20261020_193346_exportverify/`
- 关键证据：[02_path_probe.json](<../../tests/acceptance/_tmp/c_export_verify_v1/run_20261020_193346_exportverify/evidence/02_path_probe.json>)、[03_test_export.log](<../../tests/acceptance/_tmp/c_export_verify_v1/run_20261020_193346_exportverify/evidence/03_test_export.log>)、[04_discover.log](<../../tests/acceptance/_tmp/c_export_verify_v1/run_20261020_193346_exportverify/evidence/04_discover.log>)、[05_probe_export.json](<../../tests/acceptance/_tmp/c_export_verify_v1/run_20261020_193346_exportverify/evidence/05_probe_export.json>)、[06_guard_after.json](<../../tests/acceptance/_tmp/c_export_verify_v1/run_20261020_193346_exportverify/evidence/06_guard_after.json>)、[08_evidence_readback.txt](<../../tests/acceptance/_tmp/c_export_verify_v1/run_20261020_193346_exportverify/evidence/08_evidence_readback.txt>)。
- 日志：`tools/run_and_log_utf8.py`（`subprocess.run(..., encoding='utf-8')`；含 `label/cmd/cwd/start_utc/exit/stdout/stderr`，UTF-8 无 BOM）。

## 1. 镜像与模块来源

- `build_mirror`：复制 live `app/**`+`tests/**`+`requirements.txt` → `<run>/mirror/`（排除缓存/`_tmp`/`_snapshots`/`.venv`）→ **79 件，逐件 parity mismatched=0/extra=0**；另补 `tools/` 树（build_mirror 不复制仓库根 `tools/`）→ **1 件 parity 0**，合计 **80 件**（[01_mirror.log](<../../tests/acceptance/_tmp/c_export_verify_v1/run_20261020_193346_exportverify/evidence/01b_mirror_extra.log>)）。
- 模块来源（cwd=mirror、PYTHONPATH=mirror、PYTHONDONTWRITEBYTECODE=1、live venv 3.12.14）：**12/12 checks + 5/5 hash PASS**——`app`/`app.core.daily`/`app.core.ranking` 从镜像加载；工具以 importlib 从**镜像 `tools/export_daily.py`** 加载（`tool.__file__` 在镜像内、`tool.ROOT`=mirror、其 `daily_digest` 来自镜像模块）；镜像内 **export 153 行/`d71dfb2d…`、test 188 行/`58f51a0e…`、__init__ 1 行、daily 59 行/`6b3dcfde…`、ranking 288 行/`17cd66c4…`** 与 live 一致 → [02_path_probe.json](<../../tests/acceptance/_tmp/c_export_verify_v1/run_20261020_193346_exportverify/evidence/02_path_probe.json>)（**exit=0**）。

## 2. 两轮测试（真实 exit，UTF-8 日志）

| 轮次 | 命令（cwd=mirror） | 结果 |
| --- | --- | --- |
| 导出单测 | `-m tests.tools.test_export_daily` | **Ran 10 tests — OK，exit=0**（3.037s，`start_utc=2026-10-20T11:38:45Z`） |
| 完整回归 | `-m unittest discover -s tests -t .` | **Ran 294 tests — OK，exit=0**（45.874s） |

- 与 B 自述 **10/294 一致**（注：B 原文“10 项测试与完整 discover 294 为自述待复跑”，本次独立复跑确认）。证据：[03_test_export.log](<../../tests/acceptance/_tmp/c_export_verify_v1/run_20261020_193346_exportverify/evidence/03_test_export.log>)、[04_discover.log](<../../tests/acceptance/_tmp/c_export_verify_v1/run_20261020_193346_exportverify/evidence/04_discover.log>)。

## 3. 独立导出探针（17/17 PASS；不复用 B 断言）

证据：[05_probe_export.json](<../../tests/acceptance/_tmp/c_export_verify_v1/run_20261020_193346_exportverify/evidence/05_probe_export.json>)（**exit=0**）。隔离 DB 由 `b2_helpers` 造数：6 个 T1 推荐 + blocked（supply invalid）+ observing（pending）+ exploring（commercial unknown）+ insufficient（无需求 raw 行）+ excluded（override explore）。

| # | 检查 | 结果 |
| --- | --- | --- |
| D1 | `export()` 返回 digest 与直接 `daily_digest(as_of, limit=5)` **逐字段相等**；JSON 解析等于 digest；JSON 字节按行归一化后等于 `json.dumps(digest, ensure_ascii=False, indent=1)` | PASS（**原始字节为 CRLF**：`write_text` 文本模式在 Windows 将 LF 写为 CRLF，归一化后一致——记录项） |
| D2 | JSON/CSV 均严格 UTF-8、**无 BOM** | PASS |
| D3 | CSV 表头=`pool,rank,candidate_id,tier,score,daily_pick,next_action,reasons,gaps`；**8 行**（top5+blocked1+observing1+exploring1）；行序/关键列逐值正确（`None`→空串、`reasons`/`gaps` 为 JSON 字符串） | PASS（CSV 使用 csv 默认 **CRLF**） |
| D4 | 池计数：top=5、blocked=1、observing=1、exploring=1、omitted=1、insufficient=1、excluded=1 | PASS |
| L1 | `limit=2`：`daily_limit=2`、top=2，CSV 行数=2+1+1+1=5，digest 与直接 `daily_digest(limit=2)` 相等 | PASS |
| P1 | 同 as-of 两次导出：JSON sha `cc4c72e9…` 两次相同、CSV sha `8122b8ec…` 两次相同 | PASS |
| E1 | 空库：counts 全 0、四池空、CSV 仅表头 1 行、digest 与直接调用相等 | PASS |

## 4. out-dir 守卫与参数矩阵

- **out-dir 守卫**（`resolve()+normcase`，先于写文件）：absolute / relative / case 变体（均指向 fake instance 模拟）→ `ExportError`，**目录/文件均未创建**；`write_digest_files` 直接调用亦拒绝（防御性复检）；对**真实** `ROOT/instance`、`instance/sub`、`instance/sub/deep` 直接调用 `_reject_out_dir` 均拒绝；真实 `instance/` 列表未变（仍只有 `app.db` 与既有运行记录）。
- **symlink/junction**：本机创建 **junction** 指向 fake instance 成功，`export(out_dir=junction/out)` **被拒绝且无产物**；未把链接指向真实 instance（避免风险，如实记录）。
- **CLI**：缺 `--as-of` → **SystemExit 2**；非法 as-of → **2**；输入库不存在 → **2**；out-dir 指向 instance（fake 模拟）→ **2**；正常调用 → **0** 且 JSON/CSV 落盘。
- 证据：probe 中 `G1/G2/C1/G3` 四项均 PASS。

## 5. 只读与全表零写入

- `mode=ro` 连接下主动写操作全部失败：`INSERT` / `PRAGMA user_version=7` / `CREATE TABLE` 均 `sqlite3.OperationalError: attempt to write a readonly database`。
- 导出前后**全表快照**（15 张表：candidate/cost_item/demand_signal/draft/evidence/feedback/gate_review/idempotency_key/import_batch/import_row_result/review_item/run_record/schema_migrations/source/supply_offer）逐行相等（`changed=[]`）。
- 输入 DB sha `a25a3bd0…` 前后一致；导出后无 `-wal`/`-shm`；digest 与直接 `daily_digest` 一致（工具未重算、未改排序）。

## 6. 前后哈希守护

- **26 个文件 before/after 哈希完全一致**：`tools/export_daily.py` `d71dfb2d…`、`tests/tools/test_export_daily.py` `58f51a0e…`、`tests/tools/__init__.py` `65cf5571…`、`app/core/daily.py` `6b3dcfde…`、`app/core/ranking.py` `17cd66c4…`、frozen 三文件、业务库 `e073f828…`、real1/diag1/real2/real_run_v2 旧真实证据；`wal=False shm=False`（[00_guard_before.json](<../../tests/acceptance/_tmp/c_export_verify_v1/run_20261020_193346_exportverify/evidence/00_guard_before.json>) / [06_guard_after.json](<../../tests/acceptance/_tmp/c_export_verify_v1/run_20261020_193346_exportverify/evidence/06_guard_after.json>)）。
- 23 件核验证据 UTF-8 无 BOM/LF、读回 **exit=0**（[08_evidence_readback.txt](<../../tests/acceptance/_tmp/c_export_verify_v1/run_20261020_193346_exportverify/evidence/08_evidence_readback.txt>)）。

## 7. 结论、记录项与未覆盖

- **结论：脚本功能成立**——只读复用 `daily_digest`（不重算/不改排序）、JSON/CSV 与摘要逐字段一致、四池/omitted/insufficient/excluded 计数正确、limit 截断、同 as-of 字节幂等、空库空摘要、out-dir instance 守卫（含 relative/case/junction）、`--as-of` 必填/非法与缺库均 exit 2、mode=ro 写失败与全表零写入、UTF-8 无 BOM、10/294 测试真实 exit=0、业务库/冻结/旧证据哈希未变。**不宣称 S5 完成**（S5 定时触发/提醒/真实工作流未实现）。
- **记录项（非缺陷）**：JSON 用 `write_text` 文本模式、CSV 用 csv 默认行终止符，Windows 下原始字节为 CRLF；与 `json.dumps(...).encode()` 的 LF 在**字节级**不同，按行归一化后完全一致（语义一致）。若未来要求字节级可复现，可在实现中显式 `newline="\n"`（建议，不影响本验收）。
- **未覆盖**：大数据量/性能与并发；CSV 转义极端样本（引号/换行/逗号字段——当前 CSV 不含 excerpt，`reasons/next_action` 常态化覆盖）；时区仅接受 `Z` 秒精度并取日期前 10 字符（未覆盖其他时区/夏令时）；真实业务库 `instance/app.db` 的只读导出未实际执行（按任务纪律只用隔离 DB；业务库哈希未变）；symlink/junction 只验证指向 fake instance 的语义，未把链接指向真实业务目录；CLI 运行期失败路径（exit 1）未触发；网络盘/权限/只读文件系统未覆盖；S5 定时/提醒/工作流未实现。
- **过程修正（如实保留）**：首轮镜像缺 `tools/` 树（`build_mirror` 仅含 app/tests/requirements）→ 补 `mirror_extra` 1 件 parity；探针首轮 4 处我方断言问题（JSON CRLF 字节比较、CSV `None`→空串、insufficient 原始 INSERT 未 commit、CLI 守卫缺 `_INSTANCE_DIR` patch 且 fake 目录残留）已保留失败件并修正重跑。未改被验文件、业务库与旧证据。

## 8. 证据索引

| 证据 | 路径 |
| --- | --- |
| 模块来源/哈希 | [02_path_probe.json](<../../tests/acceptance/_tmp/c_export_verify_v1/run_20261020_193346_exportverify/evidence/02_path_probe.json>) |
| 单测 10 OK | [03_test_export.log](<../../tests/acceptance/_tmp/c_export_verify_v1/run_20261020_193346_exportverify/evidence/03_test_export.log>) |
| 全量 294 OK | [04_discover.log](<../../tests/acceptance/_tmp/c_export_verify_v1/run_20261020_193346_exportverify/evidence/04_discover.log>) |
| 独立导出探针（17 项） | [05_probe_export.json](<../../tests/acceptance/_tmp/c_export_verify_v1/run_20261020_193346_exportverify/evidence/05_probe_export.json>) |
| 前后守护（26 文件） | [00_guard_before.json](<../../tests/acceptance/_tmp/c_export_verify_v1/run_20261020_193346_exportverify/evidence/00_guard_before.json>) / [06_guard_after.json](<../../tests/acceptance/_tmp/c_export_verify_v1/run_20261020_193346_exportverify/evidence/06_guard_after.json>) |
| 镜像 parity/补齐 tools | [01_mirror.log](<../../tests/acceptance/_tmp/c_export_verify_v1/run_20261020_193346_exportverify/evidence/01_mirror.log>) / [01b_mirror_extra.log](<../../tests/acceptance/_tmp/c_export_verify_v1/run_20261020_193346_exportverify/evidence/01b_mirror_extra.log>) |
| 证据文本读回 | [08_evidence_readback.txt](<../../tests/acceptance/_tmp/c_export_verify_v1/run_20261020_193346_exportverify/evidence/08_evidence_readback.txt>) |
