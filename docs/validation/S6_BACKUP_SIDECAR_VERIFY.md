# S6 备份/恢复 · sidecar 修复复验

> 被验对象（修复后 live）：[tools/backup.py](<../../tools/backup.py>)（**243 行**，sha256 `c3b84c1258171a7c65b9d627592fce879d9d770a8524e734fb15e616109ddc83`，与 B 自述 `C3B84C12…` 一致）、[tools/restore.py](<../../tools/restore.py>)（**191 行**，sha256 `c3ccddb3a4bdacfd14d58eb5a8f2b3e05c7411de42f4cc79879754feb7a74dc8`，与 B 自述 `C3CCDDB3…` 一致）、[tests/tools/test_backup_restore.py](<../../tests/tools/test_backup_restore.py>)（**241 行**，sha256 `0c3fbb71…`，与 B 自述 `0C3FBB71…` 一致，14 项测试）。
> 前次验收：[S6_BACKUP_RESTORE_ACCEPTANCE.md](<S6_BACKUP_RESTORE_ACCEPTANCE.md>)（102 行 sha `b1adf907…`，结论"脚本功能成立但不宣称 S6 完成"）；本次为 sidecar 修复后的**快速复验**。
> 关联：冻结三文件 `wiring.py` `bafcf397…`/`bilibili_view.py` `b0dc0ced…`/`importer.py` `a11eaf4d…`、`app/storage/db.py` `ff8a534c…`、`app/core/config.py` `b157b440…`；业务库 `instance/app.db` `e073f828…`。
> 验收者：独立执行者 A（修复者 B），任务 `task-ca267c99f613dd3d34533233c739706e`；验收时点 2026-10-20 20:09–20:12 +08:00。
> 性质：**镜像复跑 + 独立 sidecar 探针 + 前后哈希守护**。未联网、未启动端口、未打开真实业务库（仅哈希/存在性检查）；未改被验文件/业务库/旧证据。
> 结论：**sidecar 修复成立（限本报告断言与 14/308 测试范围）**；**不宣称 S6 完成**。修复内容：只读打开改 `mode=ro&immutable=1`；源库/备份旁检测到 `-wal`/`-shm` 时拒绝（backup→`BackupError`、restore→`RestoreError`），提示人工确认、不自动删除、不静默读可能不完整的 WAL。

## 0. 运行目录与证据

- 唯一 run：`tests/acceptance/_tmp/s6_sidecar_verify_v1/run_20261020_200948_sidecarverify/`
- 关键证据：[02_path_probe.json](<../../tests/acceptance/_tmp/s6_sidecar_verify_v1/run_20261020_200948_sidecarverify/evidence/02_path_probe.json>)、[03_test_backup.log](<../../tests/acceptance/_tmp/s6_sidecar_verify_v1/run_20261020_200948_sidecarverify/evidence/03_test_backup.log>)、[04_discover.log](<../../tests/acceptance/_tmp/s6_sidecar_verify_v1/run_20261020_200948_sidecarverify/evidence/04_discover.log>)、[05_probe_sidecar.json](<../../tests/acceptance/_tmp/s6_sidecar_verify_v1/run_20261020_200948_sidecarverify/evidence/05_probe_sidecar.json>)、[06_guard_after.json](<../../tests/acceptance/_tmp/s6_sidecar_verify_v1/run_20261020_200948_sidecarverify/evidence/06_guard_after.json>)、[08_evidence_readback.txt](<../../tests/acceptance/_tmp/s6_sidecar_verify_v1/run_20261020_200948_sidecarverify/evidence/08_evidence_readback.txt>)。
- 日志：`tools/run_and_log_utf8.py`（`subprocess.run(..., encoding='utf-8')`；含 `label/cmd/cwd/start_utc/exit/stdout/stderr`，UTF-8 无 BOM）。

## 1. 镜像与模块来源

- `build_mirror`：live `app/**`+`tests/**`+`requirements.txt` → **80 件 parity mismatched=0/extra=0**；另补 `tools/` 树 3 件（backup/restore/export_daily）→ **3 件 parity 0**，合计 **83 件**（`01_mirror.log`、`01b_mirror_extra.log` 均 exit=0）。
- 模块来源（cwd=mirror、PYTHONPATH=mirror、PYTHONDONTWRITEBYTECODE=1、venv 3.12.14）：**15/15 checks + 6/6 hash PASS**——`backup`/`restore` 从镜像 `tools/` 加载（`__file__` 在镜像、`ROOT`=mirror、`MIGRATIONS_DIR` 在镜像、`sidecar_files` 助手存在且对干净路径返回 `[]`）；hash 与 live 一致（backup 243/`c3b84c12…`、restore 191/`c3ccddb3…`、test 241/`0c3fbb71…`、export 153/`d71dfb2d…`、__init__ 1、db.py 94/`ff8a534c…`）→ [02_path_probe.json](<../../tests/acceptance/_tmp/s6_sidecar_verify_v1/run_20261020_200948_sidecarverify/evidence/02_path_probe.json>)（**exit=0**）。

## 2. 两轮测试（真实 exit，UTF-8 日志）

| 轮次 | 命令（cwd=mirror） | 结果 |
| --- | --- | --- |
| 备份/恢复单测 | `-m tests.tools.test_backup_restore` | **Ran 14 tests — OK，exit=0**（1.080s，`start_utc=2026-10-20T12:11:24Z`） |
| 完整回归 | `-m unittest discover -s tests -t .` | **Ran 308 tests — OK，exit=0**（47.144s） |

- 与 B 自述 **14/308 一致**；证据：[03_test_backup.log](<../../tests/acceptance/_tmp/s6_sidecar_verify_v1/run_20261020_200948_sidecarverify/evidence/03_test_backup.log>)、[04_discover.log](<../../tests/acceptance/_tmp/s6_sidecar_verify_v1/run_20261020_200948_sidecarverify/evidence/04_discover.log>)。

## 3. 独立 sidecar 探针（19/19 PASS，不复用 B 断言）

证据：[05_probe_sidecar.json](<../../tests/acceptance/_tmp/s6_sidecar_verify_v1/run_20261020_200948_sidecarverify/evidence/05_probe_sidecar.json>)（**exit=0**）；源库为隔离 tmp DB（`create_app`+`b2.seed_full`+`verify_all_gates` 造 2 候选），**未打开真实业务库**。

| # | 检查 | 结果 |
| --- | --- | --- |
| S1 | 造数并 checkpoint 后**清理 seed 残留旁文件**得到干净基线：counts `{candidate:2,demand_signal:2,evidence:6,supply_offer:2,cost_item:20,gate_review:8,review_item:0,schema_migrations:2}`、schema=2、app_max=2；`dbs` 目录 `glob("*-wal")/("*-shm")` 为空 | PASS |
| B1 | 对干净源库备份 → **源库旁、备份文件旁 sidecar 全为空**（`sidecars_after_backup` 四项均为 `[]`）；清单独立重算 **10 项严格一致**（mismatch={}）：sha `9b64c789…`/bytes 241,664/schema/app_max/integrity=ok/fk=[]/8 表计数/3 表行级哈希/kind/tool/db_path/backup_path/source_db；`source_wal_present/source_shm_present=false/false` | PASS |
| B2 | 备份后源库 sha/counts/行级哈希**均不变**（`383df78d…`），源目录无旁文件 | PASS |
| B3 | `verify_manifest` 完好返回 `[]`、篡改 sha 返回问题；校验本身**不产生旁文件** | PASS |
| R1 | 恢复到 `run/restores/ok/app.db`：**恢复目录/副本旁/备份旁 sidecar 全为空**；counts、3 表 row_hashes 与清单一致、integrity=ok/fk=[]、manifest_checked=true；**注意：恢复副本 sha 与清单 sha 本机实测相等（`9b64c789…`），仅记录实测，不当作字节等价承诺** | PASS |
| R2 | 恢复后源备份 sha 与源库 sha 均不变 | PASS |

## 4. 哨兵拒绝矩阵（存在 -wal/-shm 时拒绝，不自动删除）

| 用例 | 结果 |
| --- | --- |
| 源库旁写 0B `<source>.db-wal` → `backup()` | **`BackupError`**，消息含"人工确认…先停止应用"；CLI `backup` **exit=2**；备份目录仅原 `app-*.db`+清单，**无新产物**；哨兵被移出后恢复可正常 |
| 源库旁写 0B `<source>.db-shm` → `backup()` | **`BackupError`**（同提示），备份数仍 1 |
| 备份旁写 0B `<backup>.db-shm` → `restore()` | **`RestoreError`**，消息含"人工确认"；CLI `restore` **exit=2**；**目标未创建**；备份旁无残留（脚本不自动删除哨兵） |
| 清理哨兵后 | 源库/备份目录 sidecar glob 均恢复为空 |

## 5. 回归（守卫 / 损坏 / 高版本 / CLI）

- 守卫：target=业务库路径、instance 子路径（fake root 模拟）、已存在文件均**拒绝且无写入**（已存在文件内容 sha 不变）；真实 `ROOT/instance/app.db`、`instance/sub/app.db` 仅调用守卫函数均拒绝，真实 `instance/` 列表前后不变。
- 损坏备份（覆写前 16 字节）：`RestoreError: 备份无法恢复（DatabaseError: file is not a database）`，CLI **exit=2**，target 未创建，原备份 sha 不变。
- 高版本：实际 DB `schema_migrations=999`（无清单）→ `库版本高于应用支持版本：库=999 应用上限=2（应用层当前不拒绝，恢复层拒绝）`，target 未创建；伪造清单 `schema_version=app_max+5` → 拒绝（清单不一致），target 未创建。
- CLI：backup=0、restore=0、business target=2、existing target=2、overwrite=2；CLI 备份/恢复目录 sidecar glob 均空。
- 非 WAL（`journal_mode=DELETE`）源库：备份/恢复全程源目录、备份目录、恢复目录 sidecar glob 均空，恢复 counts 正确。

## 6. -wal/-shm 结论与前提

- **修复有效**：干净（无旁文件）库上，只读打开不再产生 `-wal`/`-shm`；`verify_manifest`/恢复校验等内部只读访问同样不产生；本探针所有目录 `glob("*-wal")/("*-shm")` 最终均为空（`W1` PASS）。
- **拒绝语义正确**：源库/备份旁存在旁文件时明确拒绝（`BackupError`/`RestoreError`，CLI exit 2），提示"人工确认/先停应用"，**不自动删除、不静默用 immutable 读**，避免把可能不完整/未合并的 WAL 数据当作有效备份。
- **限制/前提**：`immutable=1` 的正确性前提是"无并发写入者"；脚本以"是否存在旁文件"作为是否有写入者的判定，若异常场景下写入者未留下旁文件，仍可能读到旧页（记录为未覆盖风险）；真实业务库未执行导出/恢复（默认备份落点 `instance/backups` 与业务库同目录，若业务库有旁文件会被拒绝，符合设计意图）。

## 7. 前后哈希守护

- **33 个文件 before/after 完全一致**：[00_guard_before.json](<../../tests/acceptance/_tmp/s6_sidecar_verify_v1/run_20261020_200948_sidecarverify/evidence/00_guard_before.json>) / [06_guard_after.json](<../../tests/acceptance/_tmp/s6_sidecar_verify_v1/run_20261020_200948_sidecarverify/evidence/06_guard_after.json>)（exit=0）——backup `c3b84c12…`、restore `c3ccddb3…`、test `0c3fbb71…`、export_daily、tests/tools/*、db.py `ff8a534c…`、config.py `b157b440…`、daily/ranking、frozen 三文件、S6 spec、CONTRACT、业务库 `e073f828…`、real1/diag1/real2/real_run_v2 旧证据；`wal=False shm=False`。
- 13 件核验证据 UTF-8 无 BOM/LF、读回 **exit=0**（[08_evidence_readback.txt](<../../tests/acceptance/_tmp/s6_sidecar_verify_v1/run_20261020_200948_sidecarverify/evidence/08_evidence_readback.txt>)）。

## 8. 结论与未覆盖

- **结论：sidecar 修复成立**——干净库上备份/校验/恢复全程不产生 `-wal/-shm`；存在旁文件时 backup/restore 均明确拒绝且无产物、不自动删除；清单可重算、源库不变、恢复内容校验、守卫/损坏/高版本回归、CLI 与 14/308 真实 exit 均通过。**不宣称 S6 完成**。
- **未覆盖/未执行**：设计 §10 的 **B-04**（恢复后应用启动/health/详情）、**B-05**（真实业务库演练）、**B-07**（真实业务库只读打开不产生 `-shm`——本次仅隔离 tmp 库验证）、**R-01**（断网打桩）、**R-03**（停止/启动）、**R-04**（保留轮转）、真实业务库导出/恢复与切换/回滚、`immutable=1` 的并发写入前提、symlink/junction 守卫、大数据量/权限场景。
- **记录**：前次"恢复副本 sha 恰好相等"仅为实测，**不等于字节等价承诺**（脚本只承诺内容/结构等价）；前次测试文件行数 214 为修复前版本，本次修复后为 241 行/14 项测试。
- 过程：本批一次通过，无我方断言返工；未改被验文件、业务库、旧证据；未联网、未起端口。

## 9. 证据索引

| 证据 | 路径 |
| --- | --- |
| 模块来源/哈希（15+6） | [02_path_probe.json](<../../tests/acceptance/_tmp/s6_sidecar_verify_v1/run_20261020_200948_sidecarverify/evidence/02_path_probe.json>) |
| 单测 14 OK | [03_test_backup.log](<../../tests/acceptance/_tmp/s6_sidecar_verify_v1/run_20261020_200948_sidecarverify/evidence/03_test_backup.log>) |
| 全量 308 OK | [04_discover.log](<../../tests/acceptance/_tmp/s6_sidecar_verify_v1/run_20261020_200948_sidecarverify/evidence/04_discover.log>) |
| 独立 sidecar 探针（19 项） | [05_probe_sidecar.json](<../../tests/acceptance/_tmp/s6_sidecar_verify_v1/run_20261020_200948_sidecarverify/evidence/05_probe_sidecar.json>) |
| 前后守护（33 文件） | [00_guard_before.json](<../../tests/acceptance/_tmp/s6_sidecar_verify_v1/run_20261020_200948_sidecarverify/evidence/00_guard_before.json>) / [06_guard_after.json](<../../tests/acceptance/_tmp/s6_sidecar_verify_v1/run_20261020_200948_sidecarverify/evidence/06_guard_after.json>) |
| 镜像 parity/补齐 tools | [01_mirror.log](<../../tests/acceptance/_tmp/s6_sidecar_verify_v1/run_20261020_200948_sidecarverify/evidence/01_mirror.log>) / [01b_mirror_extra.log](<../../tests/acceptance/_tmp/s6_sidecar_verify_v1/run_20261020_200948_sidecarverify/evidence/01b_mirror_extra.log>) |
| 证据文本读回 | [08_evidence_readback.txt](<../../tests/acceptance/_tmp/s6_sidecar_verify_v1/run_20261020_200948_sidecarverify/evidence/08_evidence_readback.txt>) |
