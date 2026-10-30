# 契约差距补实现 · 独立验收（health #24 + 库版本启动守卫）

> 被验对象（修复后 live）：
> - [app/__init__.py](<../../app/__init__.py>)（**85 行**，sha256 `0017d43b…`，`__version__`/`APP_VERSION=0.1.0`）；
> - [app/api/routes.py](<../../app/api/routes.py>)（**563 行**，sha256 `58ab29e5…`，`/api/health` 四键）；
> - [app/storage/db.py](<../../app/storage/db.py>)（**110 行**，sha256 `af43f9ba…`，`SchemaVersionError`/`app_schema_version()`/启动前比较）；
> - 新增测试 [tests/api/test_health_version.py](<../../tests/api/test_health_version.py>)（45 行 / 3 项）、[tests/storage/test_schema_version_guard.py](<../../tests/storage/test_schema_version_guard.py>)（103 行 / 6 项）、[tests/ui/test_pages.py](<../../tests/ui/test_pages.py>)（237 行，**仅 1 行断言对齐 3→4 键**）。
> 关联未改：[docs/design/CONTRACT.md](<../design/CONTRACT.md>)（812 行 sha `826c24cc…`，§6 L763–769 与 #24）、迁移 `0001_init.sql` sha `9b049373…`、`0002_draft_feedback.sql` sha `34d70a1d…`、冻结三文件、业务库 `instance/app.db` `e073f828…`。
> 验收者：独立执行者 A（实现者 B），任务 `task-2c46d815fb342d6527e6da104b6606f4`；验收时点 2026-10-20 20:27–20:31 +08:00。
> 性质：**镜像复跑 + 独立探针（create_app/test_client，隔离 tmp DB）+ 前后哈希守护**。未联网、未启动端口、未对业务库执行 create_app；未改被验文件/业务库/旧证据。
> 结论：**两处契约差距修复成立**——①`/api/health` 恰为 `ok/version/schema_version/time` 四键且版本链正确；②库 schema 版本高于代码支持版本时**启动拒绝**（`SchemaVersionError`）且库不被改动；③低版本补齐/同版本幂等/空库启动正常；④14 项新测试（3+6）与完整 **317** discover 真实 exit=0；⑤tests/ui 仅 1 行必要对齐；⑥CONTRACT/迁移/业务库/旧证据哈希未变。**不宣称 S6 完成**；README 已知差距文字过期、版本号 `0.1.0` 为占位、拒绝为异常语义等未覆盖项见 §8。

## 0. 运行目录与证据

- 唯一 run：`tests/acceptance/_tmp/contract_gap_verify_v1/run_20261020_202701_contractgap/`
- 关键证据：[02_path_probe.json](<../../tests/acceptance/_tmp/contract_gap_verify_v1/run_20261020_202701_contractgap/evidence/02_path_probe.json>)、[03_health_version.log](<../../tests/acceptance/_tmp/contract_gap_verify_v1/run_20261020_202701_contractgap/evidence/03_health_version.log>)、[04_schema_guard.log](<../../tests/acceptance/_tmp/contract_gap_verify_v1/run_20261020_202701_contractgap/evidence/04_schema_guard.log>)、[05_discover.log](<../../tests/acceptance/_tmp/contract_gap_verify_v1/run_20261020_202701_contractgap/evidence/05_discover.log>)、[06_probe.json](<../../tests/acceptance/_tmp/contract_gap_verify_v1/run_20261020_202701_contractgap/evidence/06_probe.json>)、[07_ui_diff.json](<../../tests/acceptance/_tmp/contract_gap_verify_v1/run_20261020_202701_contractgap/evidence/07_ui_diff.json>)、[08_guard_after.json](<../../tests/acceptance/_tmp/contract_gap_verify_v1/run_20261020_202701_contractgap/evidence/08_guard_after.json>)、[08_evidence_readback.txt](<../../tests/acceptance/_tmp/contract_gap_verify_v1/run_20261020_202701_contractgap/evidence/08_evidence_readback.txt>)。
- 日志：`tools/run_and_log_utf8.py`（`subprocess.run(..., encoding='utf-8')`；含 `label/cmd/cwd/start_utc/exit/stdout/stderr`，UTF-8 无 BOM）。

## 1. 镜像与模块来源

- `build_mirror`：live `app/**`+`tests/**`+`requirements.txt` → **82 件 parity mismatched=0/extra=0**；另补 `tools/` 3 件（backup/restore/export_daily）parity 0；再补 `docs/design/CONTRACT.md` 与 `README.md` 2 件 parity 0 → **合计 87 件**（`01_mirror.log`/`01b_mirror_extra.log`/`01c_mirror_docs.log` 均 exit=0）。
- 模块来源（cwd=mirror、PYTHONPATH=mirror、PYTHONDONTWRITEBYTECODE=1、venv 3.12.14）：**12/12 checks + 9/9 hash PASS**——`app`/`app.storage.db` 从镜像加载，`MIGRATIONS_DIR`/`config.ROOT` 在镜像，`APP_VERSION == __version__ == "0.1.0"`，`create_app` 正常且 `schema_version == app_schema_version() == 2`；hash 与 live 一致（`app/__init__.py` 85/`0017d43b…`、routes 563/`58ab29e5…`、db.py 110/`af43f9ba…`、health test 45/`9fb57801…`、schema guard 103/`8039df36…`、test_pages 237/`d7f026f8…`、CONTRACT 812/`826c24cc…`、迁移两文件）→ [02_path_probe.json](<../../tests/acceptance/_tmp/contract_gap_verify_v1/run_20261020_202701_contractgap/evidence/02_path_probe.json>)（**exit=0**）。

## 2. 三轮测试（真实 exit，UTF-8 日志）

| 轮次 | 命令（cwd=mirror） | 结果 |
| --- | --- | --- |
| health 测试 | `-m tests.api.test_health_version` | **Ran 3 tests — OK，exit=0**（0.122s，`start_utc=2026-10-20T12:28:46Z`） |
| 版本守卫测试 | `-m tests.storage.test_schema_version_guard` | **Ran 6 tests — OK，exit=0**（0.238s） |
| 完整回归 | `-m unittest discover -s tests -t .` | **Ran 317 tests — OK，exit=0**（47.021s） |

- 与 B 自述 **3+6 / 317** 一致；证据：[03_health_version.log](<../../tests/acceptance/_tmp/contract_gap_verify_v1/run_20261020_202701_contractgap/evidence/03_health_version.log>)、[04_schema_guard.log](<../../tests/acceptance/_tmp/contract_gap_verify_v1/run_20261020_202701_contractgap/evidence/04_schema_guard.log>)、[05_discover.log](<../../tests/acceptance/_tmp/contract_gap_verify_v1/run_20261020_202701_contractgap/evidence/05_discover.log>)。

## 3. 独立 health 探针（13/13 PASS，不复用 B 断言）

证据：[06_probe.json](<../../tests/acceptance/_tmp/contract_gap_verify_v1/run_20261020_202701_contractgap/evidence/06_probe.json>)（**exit=0**）。隔离 tmp DB + `create_app` + `test_client`，未起端口。

- `GET /api/health` → **200**，实测 JSON：`{"ok": true, "schema_version": 2, "time": "2026-10-20T12:30:15Z", "version": "0.1.0"}`；键集合**恰为** `ok/schema_version/time/version`（`sorted == ["ok","schema_version","time","version"]`）。
- `version == app.APP_VERSION == app.__version__ == "0.1.0"`；`schema_version` 为 **int 2**（非 bool）且等于 `db.schema_version(db)==db.app_schema_version()==2`。
- `time` 严格匹配 `^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$`，可解析为 UTC，与本机当前 UTC 偏差 **0.08s**；响应体**不含** run 路径/绝对路径/`secret`；`Content-Type: application/json`。
- 同一探针在 fresh/low/empty/idem 四种库状态上均返回四键健康响应（见 §5）。

## 4. 高版本库启动拒绝（独立构造）

- 用 `create_app` 建库（schema=2）→ 插入 `schema_migrations(version=99)` → 再 `create_app` 同一库：抛 **`SchemaVersionError`**，消息为 `库版本高于代码支持版本：库=99 代码支持=2；拒绝启动，请使用匹配版本的应用或迁移脚本；MIGRATIONS_DIR=…`；直接调用 `db.ensure_schema()` 亦抛同类型异常。
- **拒绝前后库未变**：库文件 sha 前后相同（`5421785b…`）；`schema_migrations` 仍为 `[1, 2, 99]`；15 张表全表行快照前后相同；业务表计数 `candidate/demand_signal/evidence/run_record = 0/0/0/0` 不变；未追加任何迁移。
- 记录：拒绝以 Python 异常（`SchemaVersionError`，RuntimeError 子类）表达，发生在 Flask app 创建前，符合 CONTRACT L767"拒绝启动"的语义；**未**演示真实进程退出码/运维提示（见 §8 未覆盖）。

## 5. 低版本 / 幂等 / 空库

| 用例 | 结果 |
| --- | --- |
| 低版本库（`schema_migrations` 仅 version 1） | `create_app` **成功**；迁移补到 `[1, 2]`；`schema_version=2`；health 200 四键、schema_version=2 |
| 同版本幂等（连续两次 `create_app`） | 两次迁移行均 `[1, 2]`，无重复、无新增；schema=2 |
| 空库（不存在的路径） | `create_app` 正常建库并迁移 `[1, 2]`；schema=2；health 200 四键 |
| 记录 | 低版本用例仅验证**追加迁移**语义（模拟库仅建 `schema_migrations`，未重建 0001 业务表）；不足以证明任意缺表库可完整修复（如实标 limitation） |

## 6. tests/ui 变更最小（与修复前镜像快照逐字节对比）

- 修复前快照（20:09 镜像）：`tests/ui/test_pages.py` sha `522c6103…`（10,929 B）；修复后：sha `d7f026f8…`（11,177 B）。
- **仅 `test_pages.py` 变化**，`test_ui_behavior.py` / `ui_behavior.mjs` / `__init__.py` **逐字节相同**；无新增/删除文件。
- Unified diff **恰好 1 行替换**（`@@ -229,7 +229,7 @@`）：`sorted(health.keys()) == ["ok","schema_version","time"]` → `["ok","schema_version","time","version"]`；无行为改动。证据：[07_ui_diff.json](<../../tests/acceptance/_tmp/contract_gap_verify_v1/run_20261020_202701_contractgap/evidence/07_ui_diff.json>) / [07_ui_diff.txt](<../../tests/acceptance/_tmp/contract_gap_verify_v1/run_20261020_202701_contractgap/evidence/07_ui_diff.txt>)（exit=0）。

## 7. 静态核对、CONTRACT 与哈希守护

- 静态：`app/__init__.py` 含 `__version__ = "0.1.0"`/`APP_VERSION = __version__`；`db.py` 含 `class SchemaVersionError` 与 `if current > supported`；`routes.py` health 段含 `ok/version/schema_version/time` 四键并从 `.. import APP_VERSION`；CONTRACT 含"库版本高于代码支持版本时拒绝启动"与 `| 24 | GET /api/health | 版本与 schema |`（812 行原文未改）。
- **43 个文件 before/after 哈希完全一致**：[00_guard_before.json](<../../tests/acceptance/_tmp/contract_gap_verify_v1/run_20261020_202701_contractgap/evidence/00_guard_before.json>) / [08_guard_after.json](<../../tests/acceptance/_tmp/contract_gap_verify_v1/run_20261020_202701_contractgap/evidence/08_guard_after.json>)（exit=0）——被验三文件、新增测试、tests/ui、CONTRACT、迁移两文件、冻结三文件、tools 三脚本、tests/tools 三文件、README、业务库 `e073f828…`、real1/diag1/real2/real_run_v2 旧证据；`wal=False shm=False`。
- 27 件核验证据 UTF-8 无 BOM/LF、读回 **exit=0**（[08_evidence_readback.txt](<../../tests/acceptance/_tmp/contract_gap_verify_v1/run_20261020_202701_contractgap/evidence/08_evidence_readback.txt>)）。

## 8. 结论与未覆盖

- **结论：两处契约差距修复成立**（health 四键+版本正确；高版本库启动拒绝且库不变；低版本补齐/同版本幂等/空库正常；3+6+317 真实 exit=0；tests/ui 仅 1 行必要对齐；CONTRACT/迁移/业务库/旧证据未变）。**不宣称 S6 完成**。
- 未覆盖/记录：
  1. **README 已知差距文字过期**：#2"health 无版本字段"、#3"不拒绝高版本库"仍保留修复前描述，与当前实现不符（文档未更新，如实记录；非实现缺陷）。
  2. 版本号 `0.1.0` 为**占位**（未与发行/契约版本策略对齐）。
  3. 高版本拒绝为**异常语义**（`create_app` 抛 `SchemaVersionError`），未演示真实进程退出码/独立健康检查；异常消息含 `MIGRATIONS_DIR` 绝对路径（仅内部错误信息，不在 health 响应中）。
  4. 低版本用例只验证追加迁移，未验证"缺表库"完整重建；并发启动/迁移竞争未覆盖。
  5. 未对真实业务库执行 `create_app`/启动（仅隔离 tmp DB；业务库哈希未变）；未起端口、未联网。
  6. 无 `.git` 仓库，tests/ui diff 采用修复前镜像快照对比（快照 sha 已记录）而非提交级 diff。
- 过程修正（如实保留）：镜像最初未含 `docs/` → 补 `mirror_docs` 2 件 parity；`ui_diff` 曾因路径 `_tmp` 分片误排除全部文件与相对旧路径失败，修正后 1 行 diff 通过；探针一处 detail 表达式修正。失败件保留为 `*_attempt1_missing_docs.*` / `*_attempt3_exclusionbug.*` / `06_probe_attempt2_detailbug.*`；未改被验文件、业务库、旧证据。

## 9. 证据索引

| 证据 | 路径 |
| --- | --- |
| 模块来源/哈希（12+9） | [02_path_probe.json](<../../tests/acceptance/_tmp/contract_gap_verify_v1/run_20261020_202701_contractgap/evidence/02_path_probe.json>) |
| health 测试 3 OK | [03_health_version.log](<../../tests/acceptance/_tmp/contract_gap_verify_v1/run_20261020_202701_contractgap/evidence/03_health_version.log>) |
| 版本守卫 6 OK | [04_schema_guard.log](<../../tests/acceptance/_tmp/contract_gap_verify_v1/run_20261020_202701_contractgap/evidence/04_schema_guard.log>) |
| 全量 317 OK | [05_discover.log](<../../tests/acceptance/_tmp/contract_gap_verify_v1/run_20261020_202701_contractgap/evidence/05_discover.log>) |
| 独立探针（13 项：health/守卫/低版本/幂等/空库） | [06_probe.json](<../../tests/acceptance/_tmp/contract_gap_verify_v1/run_20261020_202701_contractgap/evidence/06_probe.json>) |
| tests/ui 1 行 diff | [07_ui_diff.json](<../../tests/acceptance/_tmp/contract_gap_verify_v1/run_20261020_202701_contractgap/evidence/07_ui_diff.json>) / [07_ui_diff.txt](<../../tests/acceptance/_tmp/contract_gap_verify_v1/run_20261020_202701_contractgap/evidence/07_ui_diff.txt>) |
| 前后守护（43 文件） | [00_guard_before.json](<../../tests/acceptance/_tmp/contract_gap_verify_v1/run_20261020_202701_contractgap/evidence/00_guard_before.json>) / [08_guard_after.json](<../../tests/acceptance/_tmp/contract_gap_verify_v1/run_20261020_202701_contractgap/evidence/08_guard_after.json>) |
| 镜像 parity（82+3+2 件） | [01_mirror.log](<../../tests/acceptance/_tmp/contract_gap_verify_v1/run_20261020_202701_contractgap/evidence/01_mirror.log>) / [01b_mirror_extra.log](<../../tests/acceptance/_tmp/contract_gap_verify_v1/run_20261020_202701_contractgap/evidence/01b_mirror_extra.log>) / [01c_mirror_docs.log](<../../tests/acceptance/_tmp/contract_gap_verify_v1/run_20261020_202701_contractgap/evidence/01c_mirror_docs.log>) |
| 证据文本读回 | [08_evidence_readback.txt](<../../tests/acceptance/_tmp/contract_gap_verify_v1/run_20261020_202701_contractgap/evidence/08_evidence_readback.txt>) |
