# S6 备份/恢复脚本 · 独立验收

> 被验对象：[tools/backup.py](<../../tools/backup.py>)（**230 行**，sha256 `9dba7f4093d2badee4dfa03dd3fa7788fa1bb4f46cc2c5a57aba86b495d56f02`，与 B 自述 `9DBA7F40…` 一致）、[tools/restore.py](<../../tools/restore.py>)（**185 行**，sha256 `f26b460f7a8446a8cf7b8e16ef90cd07e4a0f1902bb9eb5f6365aa332a51b6da`，与 B 自述 `F26B460F…` 一致）、[tests/tools/test_backup_restore.py](<../../tests/tools/test_backup_restore.py>)（**214 行**，sha256 `4d1b6948…`——B 自述 **204 行**，sha 一致但**行数不实**，以实测 214 为准）。
> 关联依赖：[app/storage/db.py](<../../app/storage/db.py>)（94 行 sha `ff8a534c…`）、[app/core/config.py](<../../app/core/config.py>)（25 行 sha `b157b440…`）、冻结三文件 `wiring.py` `bafcf397…`/`bilibili_view.py` `b0dc0ced…`/`importer.py` `a11eaf4d…`；业务库 `instance/app.db` `e073f828…`；设计 [S6_DELIVERY_SPEC.md](<../design/S6_DELIVERY_SPEC.md>) v2 159 行 sha `e0bde4a7…`。
> 验收者：独立执行者 A（实现者 B），任务 `task-7fb92c7a05ca4444c784903c07da2446`；验收时点 2026-10-20 19:56–20:03 +08:00。
> 性质：**镜像复跑 + 独立备份/恢复探针（隔离 DB）+ 前后哈希守护**。**未联网、未启动端口、未打开真实业务库做任何写操作（也未做 SQL 读）**；未改被验文件/业务库/旧证据。
> 结论：**脚本功能成立（限本报告断言与 12/306 测试范围；对应设计 §10 的 B-01/B-02/B-03/B-06/R-02 离线子集）**；**不宣称 S6 完成**。记录项：WAL 库的只读打开会在源/备份/恢复副本旁生成**空 `-wal`(0B)+`-shm`(32KB)**（与设计 B-07"只读打开不产生 `-shm`"预期不符；本次未打开真实业务库，故业务库未受影响）；恢复为**内容等价**校验（本机实测 sha 恰好一致，但脚本只承诺内容/结构等价）。

## 0. 运行目录与证据

- 唯一 run：`tests/acceptance/_tmp/s6_backup_verify_v1/run_20261020_195656_backupverify/`
- 关键证据：[02_path_probe.json](<../../tests/acceptance/_tmp/s6_backup_verify_v1/run_20261020_195656_backupverify/evidence/02_path_probe.json>)、[03_test_backup.log](<../../tests/acceptance/_tmp/s6_backup_verify_v1/run_20261020_195656_backupverify/evidence/03_test_backup.log>)、[04_discover.log](<../../tests/acceptance/_tmp/s6_backup_verify_v1/run_20261020_195656_backupverify/evidence/04_discover.log>)、[05_probe_backup.json](<../../tests/acceptance/_tmp/s6_backup_verify_v1/run_20261020_195656_backupverify/evidence/05_probe_backup.json>)、[06_guard_after.json](<../../tests/acceptance/_tmp/s6_backup_verify_v1/run_20261020_195656_backupverify/evidence/06_guard_after.json>)、[08_evidence_readback.txt](<../../tests/acceptance/_tmp/s6_backup_verify_v1/run_20261020_195656_backupverify/evidence/08_evidence_readback.txt>)。
- 日志格式：`tools/run_and_log_utf8.py`（`subprocess.run(..., encoding='utf-8')`；含 `label/cmd/cwd/start_utc/exit/stdout/stderr`，UTF-8 无 BOM）。

## 1. 镜像与模块来源

- `build_mirror`：复制 live `app/**`+`tests/**`+`requirements.txt` → **80 件，逐件 parity mismatched=0/extra=0**；另补仓库根 `tools/` 树（build_mirror 不复制）→ `backup.py`/`restore.py`/`export_daily.py` **3 件 parity 0**，合计 **83 件**（[01_mirror.log](<../../tests/acceptance/_tmp/s6_backup_verify_v1/run_20261020_195656_backupverify/evidence/01_mirror.log>)、[01b_mirror_extra.log](<../../tests/acceptance/_tmp/s6_backup_verify_v1/run_20261020_195656_backupverify/evidence/01b_mirror_extra.log>)）。
- 模块来源（cwd=mirror、PYTHONPATH=mirror、PYTHONDONTWRITEBYTECODE=1、venv 3.12.14）：**14/14 checks + 6/6 hash PASS**——`backup`/`restore` 从镜像 `tools/` 加载（`__file__` 在镜像、`ROOT`=mirror、`MIGRATIONS_DIR` 在镜像）、`app.storage.db`/`config.ROOT` 来自镜像、hash 与 live 一致（backup 230/`9dba7f40…`、restore 185/`f26b460f…`、test **214**/`4d1b6948…`、export 153/`d71dfb2d…`、__init__ 1/`65cf5571…`、db.py 94/`ff8a534c…`）→ [02_path_probe.json](<../../tests/acceptance/_tmp/s6_backup_verify_v1/run_20261020_195656_backupverify/evidence/02_path_probe.json>)（**exit=0**）。

## 2. 两轮测试（真实 exit，UTF-8 日志）

| 轮次 | 命令（cwd=mirror） | 结果 |
| --- | --- | --- |
| 备份/恢复单测 | `-m tests.tools.test_backup_restore` | **Ran 12 tests — OK，exit=0**（1.031s，`start_utc=2026-10-20T12:00:06Z`） |
| 完整回归 | `-m unittest discover -s tests -t .` | **Ran 306 tests — OK，exit=0**（46.184s） |

- 与 B 自述 **12/306 一致**；证据：[03_test_backup.log](<../../tests/acceptance/_tmp/s6_backup_verify_v1/run_20261020_195656_backupverify/evidence/03_test_backup.log>)、[04_discover.log](<../../tests/acceptance/_tmp/s6_backup_verify_v1/run_20261020_195656_backupverify/evidence/04_discover.log>)。

## 3. 独立备份探针（17/17 PASS；不复用 B 断言）

证据：[05_probe_backup.json](<../../tests/acceptance/_tmp/s6_backup_verify_v1/run_20261020_195656_backupverify/evidence/05_probe_backup.json>)（**exit=0**）。源库为隔离 tmp DB（`create_app` + `b2.seed_full`+`verify_all_gates` 造 2 候选），**未打开真实业务库**。

| # | 检查 | 结果 |
| --- | --- | --- |
| S1 | 源库造数并 checkpoint：counts `{candidate:2,demand_signal:2,evidence:6,supply_offer:2,cost_item:20,gate_review:8,review_item:0,schema_migrations:2}`、schema=2、app_max=2；seed/checkpoint 后无 `-wal/-shm` | PASS |
| B1 | 备份产物 `app-20261020-200000.db`（241,664 B，sha `1a61b2ab…`）+ 同名 `.db.manifest.json`；**独立重算清单 10 项严格一致**（sha256/bytes/schema_version/app_max=2/integrity=ok/fk=[]/8 表计数/3 表行级哈希/kind/tool/db_path/backup_path/source_db/duration≥0） | PASS |
| B1b | 清单 `source_wal_present/source_shm_present` 与现场一致（备份时只读打开源库已生成空 sidecar，见 §8） | PASS |
| B2 | 备份后源库 sha、8 表计数、3 表行级哈希**均不变**（`a701aef6…`；只产生空 sidecar，见 §8） | PASS |
| B3 | `verify_manifest` 对完好备份返回 `[]`；伪造 sha256 清单返回 `["sha256 不一致"]`（篡改可检出） | PASS |
| B4 | 同名 `stamp` 第二次备份 → `BackupError`（拒绝覆盖），原备份/清单 sha 不变，`app-*.db` 仍 1 份 | PASS |

## 4. 恢复探针（内容等价与源备份保护）

| 检查 | 结果 |
| --- | --- |
| 恢复到 `run/restores/ok/app.db`（目标不存在、独占创建） | **成功**；`manifest_checked=true`、schema=2、counts 与清单一致、3 表 row_hashes 与清单一致、副本 integrity=ok、fk=[] |
| 恢复副本 sha 与清单 sha | **本机实测相等**（`1a61b2ab…`）；脚本仅承诺内容/结构等价（sqlite backup 不保证字节级），此处记录为"实测恰好一致" |
| 源备份文件 | 恢复前后 sha **不变**（未被修改） |
| 恢复后副本旁 | 生成空 `-wal`(0B)+`-shm`(32KB)（见 §8，记录项） |

## 5. 守卫矩阵（写文件前拒绝）

| 用例 | 结果 |
| --- | --- |
| target = 业务库路径（`business_db` 等值） | **拒绝**（`拒绝覆盖业务库`），未创建文件 |
| target = `ROOT/instance/sub/...`（fake root 模拟 instance 前缀） | **拒绝**（`拒绝在业务库目录（instance/）内…`），未创建目录 |
| target = 已存在文件 | **拒绝**（`目标已存在，拒绝覆盖`），原内容 sha 不变 |
| 真实 `ROOT/instance/app.db` 与 `instance/sub/app.db`（仅调用守卫函数，不写） | 均**拒绝**；真实 `instance/` 列表前后不变 |
| symlink/junction | 本次未单独构造（守卫用 realpath+normcase，junction 场景属未覆盖，见 §9） |

## 6. 高版本与损坏备份

| 用例 | 结果 |
| --- | --- |
| 伪造清单 `schema_version=app_max+5` | **拒绝**：`恢复副本校验失败：schema_version 与备份清单不一致`；target 未创建 |
| 实际高版本 DB（`schema_migrations` 插入 999、无清单） | **拒绝**：`库版本高于应用支持版本：库=999 应用上限=2（应用层当前不拒绝，恢复层拒绝）`；target 未创建 |
| 损坏备份（覆写前 16 字节 SQLite 头） | **拒绝**：`RestoreError: 备份无法恢复（DatabaseError: file is not a database）`；CLI **exit=2**；target 未创建；原备份 sha 不变 |

## 7. CLI 与参数

- `backup.main` → 0 并落盘；`restore.main` → 0 并生成副本；`restore` 指向业务库 → **2**；指向已存在目标 → **2**；`backup` 同名 → **2**（均与脚本约定一致）。

## 8. `-wal`/`-shm` 副作用记录（重要，含与 B-07 预期的差异）

- 实测：**WAL 模式的 SQLite 库被 `mode=ro` 只读打开时，会在库旁生成空 `-wal`（0 字节）与 `-shm`（32,768 字节）**。出现位置：
  - 源库旁（`backup` 打开源库只读后）；
  - 备份文件旁（`build_manifest` 以只读打开备份目标）；
  - 恢复副本旁、CLI 备份/恢复目录、高版本副本旁（同类只读访问）。
- 影响：**不改变数据**（源库/备份/副本的 sha 与内容校验均一致；`glob("app-*.db")` 不受影响），但会在备份目录/恢复目录/源库目录留下旁文件；若把这些目录作为交付或轮转对象，需要预期/清理。
- **与设计 B-07（"只读打开不产生 `-shm`"）不符**：本次在**隔离 tmp 库**上实测会产生空 `-wal/-shm`；因任务纪律**未打开真实业务库**，业务库未受影响，但若将来对 `instance/app.db` 执行 backup.py，应预期同现象（或改用 `mode=ro&immutable=1` 规避；本验收的独立复算即用 immutable，未产生副作用）。→ 作为**记录项/风险**保留，不判定脚本功能失败；B-07 仍属未执行/未覆盖项。
- 清单已记录 `source_wal_present/source_shm_present` 且在本次现场为 `true/true`，与观察一致。

## 9. 前后哈希守护与结论

- **33 个文件 before/after 完全一致**：[00_guard_before.json](<../../tests/acceptance/_tmp/s6_backup_verify_v1/run_20261020_195656_backupverify/evidence/00_guard_before.json>) / [06_guard_after.json](<../../tests/acceptance/_tmp/s6_backup_verify_v1/run_20261020_195656_backupverify/evidence/06_guard_after.json>)（均 exit=0）——`tools/backup.py` `9dba7f40…`、`restore.py` `f26b460f…`、test `4d1b6948…`、`export_daily.py`、`tests/tools/*`、`db.py` `ff8a534c…`、`config.py` `b157b440…`、daily/ranking、frozen 三文件、S6 spec、CONTRACT、业务库 `e073f828…`、real1/diag1/real2/real_run_v2 旧证据；`wal=False shm=False`。
- 17 件核验证据 UTF-8 无 BOM/LF、读回 **exit=0**（[08_evidence_readback.txt](<../../tests/acceptance/_tmp/s6_backup_verify_v1/run_20261020_195656_backupverify/evidence/08_evidence_readback.txt>)）。
- **结论：脚本功能成立**（隔离 tmp DB 上备份→清单可重算→同名校验→损坏拒绝→恢复内容校验→守卫→高版本拒绝→CLI 均通过；12/306 真实 exit=0；未打开真实业务库、未联网、未起端口）。
- **未执行/未覆盖**：设计 §10 的 **B-04**（恢复后应用启动/health/详情）、**B-05**（真实业务库演练零写入——本次仅隔离与哈希守护，未对真实业务库做演练）、**B-07**（"只读打开不产生 `-shm`"——实测相反，见 §8）、**R-01**（断网打桩证明）、**R-03**（停止/启动）、**R-04**（保留轮转）、真实业务库切换/回滚、symlink/junction 守卫、大数据量/并发、Windows 权限/只读文件系统。
- **过程修正（如实保留）**：首轮探针 4 项 FAIL 源于我方对"只读打开会产生空 `-wal/-shm`"的误判（以及清单 `source_*` 时间点），改用 `mode=ro&immutable=1` 做独立复算并记录副作用后 17/17；并清理上轮产物。未改被验文件、业务库、旧证据。
- **不宣称 S6 完成**。

## 10. 证据索引

| 证据 | 路径 |
| --- | --- |
| 模块来源/哈希（14+6） | [02_path_probe.json](<../../tests/acceptance/_tmp/s6_backup_verify_v1/run_20261020_195656_backupverify/evidence/02_path_probe.json>) |
| 单测 12 OK | [03_test_backup.log](<../../tests/acceptance/_tmp/s6_backup_verify_v1/run_20261020_195656_backupverify/evidence/03_test_backup.log>) |
| 全量 306 OK | [04_discover.log](<../../tests/acceptance/_tmp/s6_backup_verify_v1/run_20261020_195656_backupverify/evidence/04_discover.log>) |
| 独立备份/恢复探针（17 项，含 sidecar 记录） | [05_probe_backup.json](<../../tests/acceptance/_tmp/s6_backup_verify_v1/run_20261020_195656_backupverify/evidence/05_probe_backup.json>) |
| 前后守护（33 文件） | [00_guard_before.json](<../../tests/acceptance/_tmp/s6_backup_verify_v1/run_20261020_195656_backupverify/evidence/00_guard_before.json>) / [06_guard_after.json](<../../tests/acceptance/_tmp/s6_backup_verify_v1/run_20261020_195656_backupverify/evidence/06_guard_after.json>) |
| 镜像 parity/补齐 tools | [01_mirror.log](<../../tests/acceptance/_tmp/s6_backup_verify_v1/run_20261020_195656_backupverify/evidence/01_mirror.log>) / [01b_mirror_extra.log](<../../tests/acceptance/_tmp/s6_backup_verify_v1/run_20261020_195656_backupverify/evidence/01b_mirror_extra.log>) |
| 证据文本读回 | [08_evidence_readback.txt](<../../tests/acceptance/_tmp/s6_backup_verify_v1/run_20261020_195656_backupverify/evidence/08_evidence_readback.txt>) |
