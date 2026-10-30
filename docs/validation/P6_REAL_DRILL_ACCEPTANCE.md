# P6 真实业务库备份/恢复演练 · 独立复核

> 被复核演练（实现者 B）：`tests/acceptance/_tmp/p6_real_drill_v1/run_20261020_212426_p6drill/`
> - 业务库 `instance/app.db`：sha256 `e073f828…`，**241,664 B**，无 `-wal/-shm`；
> - 备份 `instance/backups/app-20261020-132427.db`：sha256 `62982a049d71be288db92546044f477ad575194118eb228181507dabd6f9bee5`，241,664 B；清单 `…db.manifest.json`：sha256 `fe833c8d…`，1,191 B；
> - 工具：[tools/backup.py](<../../tools/backup.py>)（243 行 sha `c3b84c12…`）、[tools/restore.py](<../../tools/restore.py>)（191 行 sha `c3ccddb3…`）；代码 routes `501aa611…`/daily `7916346c…`/ranking `1c73caec…`、CONTRACT `826c24cc…`、迁移 `9b049373…`/`34d70a1d…`、README `83c3d403…`。
> 复核者：独立执行者 A（实现者 B），任务 `task-24c89878842b63efba5a908e596c7fb5`；复核时点 2026-10-20 21:28–21:33 +08:00。
> 复核 run：`tests/acceptance/_tmp/p6_real_drill_verify_v1/run_20261020_212855_p6verify/`
> 性质：**只读复核**——业务库仅做文件哈希与 `mode=ro&immutable=1` 读取（无 SQL 写、无侧车产生），备份复制到自有 run 目录后恢复；**未联网、未起端口、未改实现/业务库/备份/旧证据**。
> 结论：**演练工具链在真实业务库文件上成立**（备份/清单/恢复/五项校验/三个 test_client 端点/哈希守护均可复算），但**业务库只含 synthetic 示例数据，故不证明 real 数据恢复**；**不宣称 S6 完成**。

## 0. 本次复核证据

- [02_probe_p6.json](<../../tests/acceptance/_tmp/p6_real_drill_verify_v1/run_20261020_212855_p6verify/evidence/02_probe_p6.json>)（8/8 PASS，exit=0）
- [01_b_evidence.json](<../../tests/acceptance/_tmp/p6_real_drill_verify_v1/run_20261020_212855_p6verify/evidence/01_b_evidence.json>)（B 证据 UTF-8/取值核验，exit=0）
- [00_guard_before.json](<../../tests/acceptance/_tmp/p6_real_drill_verify_v1/run_20261020_212855_p6verify/evidence/00_guard_before.json>) / [03_guard_after.json](<../../tests/acceptance/_tmp/p6_real_drill_verify_v1/run_20261020_212855_p6verify/evidence/03_guard_after.json>)（38 文件，exit=0）
- [08_evidence_readback.txt](<../../tests/acceptance/_tmp/p6_real_drill_verify_v1/run_20261020_212855_p6verify/evidence/08_evidence_readback.txt>)（13 件 UTF-8 无 BOM/LF，exit=0）
- 日志：[02_probe_p6.log](<../../tests/acceptance/_tmp/p6_real_drill_verify_v1/run_20261020_212855_p6verify/evidence/02_probe_p6.log>)（含 `cwd/start_utc/exit`）。

## 1. 业务库 BEFORE/AFTER

| 项 | BEFORE（本次复核开始） | AFTER（复核算毕） |
| --- | --- | --- |
| sha256 | `e073f828cf0f30d6206361bba3a729826be096be3308f5a5dc204406dae4eb85` | **相同** |
| bytes | 241,664 | 241,664 |
| `-wal` / `-shm` | 无 / 无 | 无 / 无 |
| integrity / fk / schema | `ok` / `[]` / 2 | 通过只读复核，内容未变 |
| 8 表计数 | candidate1 / demand1 / evidence2 / supply1 / cost10 / gate0 / review0 / schema_migrations2 | **相同**（行级哈希亦相同） |
| `instance/backups/` 列表 | `app-20261020-132427.db`、`….db.manifest.json` | **相同**（无新增/无侧车） |

- 结论：业务库在 B 演练与本次复核前后**字节级不变、无侧车、备份目录未被污染**。

## 2. synthetic-only 事实（只读查询）

| 表 | 全部行的 `data_origin` |
| --- | --- |
| candidate | `synthetic`（仅 `c_094bed6f319b4de0`，identity_key=`u:xianyu:https://example.com/demand/1001`） |
| demand_signal | `synthetic`（`d_db3e48477c574613`，observed_at=`2026-06-01T08:00:00Z`） |
| supply_offer | `synthetic`（`sp_fabe11fa5220476e`） |
| evidence | `synthetic`（2 行，observed_at 均 `2026-06-01T08:00:00Z`） |

- **业务库只含 synthetic 示例数据**（`real` 行 0 条）；B 演练的 detail 投影亦记录 `candidate.data_origin='synthetic'`、`identity_key=u:xianyu:…`、`observed_at=2026-06-01`（其 `30_test_client` 中 `detail_data_origin:null` 是 GET 投影未含该字段所致，非数据为 real）。
- **因此：工具链可在真实业务库文件上运行，但不能证明"real 数据"的备份/恢复；本结论不改变业务库现状。**

## 3. 备份与清单独立重算

- 备份文件 `app-20261020-132427.db`：sha `62982a04…`、241,664 B；清单 sha `fe833c8d…`、1,191 B；备份旁无 `-wal/-shm`；`instance/backups` 恰含这 2 个文件。
- 独立重算清单（只读打开备份）与清单 JSON **逐字段一致**（mismatch={}）：sha256/bytes/schema=2/app_max=2/integrity=ok/fk=[]/**8 表计数**/**3 表行级哈希**（candidate `019ac59f…`、demand `f12dfd85…`、supply `2644a7dc…`）/source_db/backup_path/source_wal_present=false/source_shm_present=false。
- `backup.verify_manifest()` 返回 **problems=[]**；备份的 8 表计数与 3 表行级哈希 **等于业务库**（同一数据的只读快照）。

## 4. 恢复到自有隔离目录 + 五项校验

- 目标 `run/restore/app.db`（不存在，独占创建）；`restore.restore()` 返回 `manifest_checked=true`；源备份与清单 sha 前后**不变**。
- 独立五项校验（对恢复副本只读复算）：
  1. `integrity_check` = **ok**；
  2. `foreign_key_check` = **[]**；
  3. **8 表计数**逐表与清单相等（candidate1/demand1/evidence2/supply1/cost10/gate0/review0/schema_migrations2）；
  4. `schema_version` = **2**（= app_max=2）；
  5. **3 表行级哈希**与清单相等（`019ac59f…`/`f12dfd85…`/`2644a7dc…`）。
- 记录：恢复副本 sha 本机实测与备份 sha 相等（`62982a04…`，241,664 B），但按 S6 口径**只承诺内容/结构等价**，字节相等仅作实测记录。

## 5. create_app + test_client 三端点（恢复副本）

`create_app({"db_path": 恢复副本})` + `test_client`（进程内，**未起真实端口**）：

| 端点 | 结果 |
| --- | --- |
| `GET /api/health` | **200**，四键 `ok/version/schema_version/time`，version=`0.1.0`、schema=2 |
| `GET /api/candidates/c_094bed6f319b4de0` | **200**，返回 candidate 的 id 一致（投影含 data_origin/identity_key 等字段） |
| `GET /api/summary/daily?date=2026-10-20` | **200**，kind=`daily_digest`、as_of=`2026-10-20T00:00:00Z`；默认 real-only 下 counts 全 0/top=0（因为副本只有 synthetic 数据，属预期） |

- 恢复副本在 HTTP 读取后旁无 `-wal/-shm`（本次实测）。

## 6. 代码/契约/迁移与前后哈希守护

- 独立核对（live）：routes 608/`501aa611…`、daily 64/`7916346c…`、ranking 296/`1c73caec…`、CONTRACT 812/`826c24cc…`、README 128/`83c3d403…`、迁移 0001 `9b049373…`/0002 `34d70a1d…`、backup 243/`c3b84c12…`、restore 191/`c3ccddb3…`——**全部与预期一致，未变**。
- **38 个文件 before/after 完全一致**（含业务库、备份+清单、上述代码/契约/迁移/README、tests/tools、冻结三文件、real1/diag1/real2/real_run_v2 旧证据）；`wal=False shm=False`；备份目录列表前后一致。

## 7. 证据可读性与真实 exit

- 本次复核日志含 `label/cwd/start_utc/exit`（如 `02_probe_p6.log`：`cwd=…run_20261020_212855_p6verify`、`start_utc=2026-10-20T13:30:54+00:00`、`exit=0`）；13 件证据 UTF-8 无 BOM/LF、读回 exit=0。
- B 演练证据：17 个文本文件**严格 UTF-8 可解码、无解码错误**、JSON 取值与本复核一致（`values_ok=true`）；记录格式缺口：4 个 `.py` 带 UTF-8 BOM、JSON 为 CRLF、`50_stdout.txt` 只有汇总 JSON + `exit=0` **无显式 cmd/cwd/UTC 行**（如实记录，非本次复核阻断项）。

## 8. 结论与限制

- **结论：演练工具链在真实业务库文件上成立**——备份+清单可在真实库（只读）上生成/重算、恢复副本五项校验通过、恢复副本上三个端点 200、业务库/备份/代码/契约/迁移哈希前后未变、证据可读。
- **不证明 real 数据恢复**：业务库只含 synthetic 示例数据（real 行 0），故不能外推"real 数据可恢复/业务真实数据安全"。
- **未覆盖/未执行**：真实切换/回滚（停止应用→替换库→再启动的运维流程）、真实端口启动（仅 test_client）、保留轮转、加密、并发/多进程、异地备份、恢复后人工验收；B-04/B-05 等 §10 项中的真实业务库操作未执行。**不宣称 S6 完成**。
- 记录：B 的 `detail_data_origin:null` 源于 GET 投影字段缺失（非数据为 real）；B `30_test_client` 中 `copy_run_records=2` 与本次业务库 read-only 未改一致。

## 9. 证据索引

| 证据 | 路径 |
| --- | --- |
| 独立复核探针（8 项） | [02_probe_p6.json](<../../tests/acceptance/_tmp/p6_real_drill_verify_v1/run_20261020_212855_p6verify/evidence/02_probe_p6.json>) |
| B 证据 UTF-8/取值核验 | [01_b_evidence.json](<../../tests/acceptance/_tmp/p6_real_drill_verify_v1/run_20261020_212855_p6verify/evidence/01_b_evidence.json>) |
| 前后守护（38 文件） | [00_guard_before.json](<../../tests/acceptance/_tmp/p6_real_drill_verify_v1/run_20261020_212855_p6verify/evidence/00_guard_before.json>) / [03_guard_after.json](<../../tests/acceptance/_tmp/p6_real_drill_verify_v1/run_20261020_212855_p6verify/evidence/03_guard_after.json>) |
| 复核证据读回 | [08_evidence_readback.txt](<../../tests/acceptance/_tmp/p6_real_drill_verify_v1/run_20261020_212855_p6verify/evidence/08_evidence_readback.txt>) |
| B 演练原始证据 | [B run dir](<../../tests/acceptance/_tmp/p6_real_drill_v1/run_20261020_212426_p6drill>)（`10_manifest_snapshot.json`/`13_five_checks.json`/`30_test_client_readback.json`/`40_summary.json`） |
