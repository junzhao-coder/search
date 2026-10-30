# 本地选品/库存小工具（Flask + SQLite，离线运行）

> 定位：**本地、单人、离线**运行的选品与货源评估辅助工具。它把候选商品的需求、货源与许可、成本、平台发布条件四项证据与利润情景、匹配、排序、每日摘要聚合起来，供人工复核与决策。
> 边界（不做）：不自动发布/联系/采购/付款；不自动抓取平台数据；受控真实网络仅在用户逐批授权下使用（当前仅完成 2 bvid 受控样本，见"能力现状"与"已知差距"）；不提供云端托管、多用户与远程访问；模型/热度/互动量不作为证据。

## 版本与依赖

- Python **3.12.14**（`.venv` 内已有环境；不要用系统 Python 直接跑）。
- `requirements.txt`：仅 `flask==3.1.3`（其余为 Python 标准库；SQLite 由标准库提供，本机 sqlite3 **3.53.1**）。
- 离线安装（依赖已备时可跳过；联网安装需自行确认）：

```powershell
# 首次准备（如 .venv 不存在）
python -m venv .venv
& .\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

## 环境变量（共 6 个，均有默认值）

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `APP_HOST` | `127.0.0.1` | 仅本机监听 |
| `APP_PORT` | `5000` | HTTP 端口 |
| `APP_DB_PATH` | `instance/app.db` | SQLite 路径（**测试/演练请务必指向隔离副本**） |
| `APP_TZ_OFFSET_HOURS` | `8` | 展示用本地时区 |
| `APP_MAX_BODY_BYTES` | `5242880`（5 MiB） | 请求体上限 |
| `APP_MAX_ROWS` | `5000` | 单批导入行数上限 |

> 不存在 `SECRET_KEY`；本应用无登录/鉴权，请勿暴露到公网。

## 启动 / 健康检查 / 停止

```powershell
# 启动（默认 http://127.0.0.1:5000，threaded=True，无 reloader）
& .\.venv\Scripts\python.exe -m app

# 健康检查（实际字段：ok / version / schema_version / time）
Invoke-RestMethod http://127.0.0.1:5000/api/health

# 停止：结束对应 python 进程并确认端口释放
Get-NetTCPConnection -LocalPort 5000 -State Listen -ErrorAction SilentlyContinue
Stop-Process -Id <PID>
```

- 端口占用时可用 `$env:APP_PORT='5001'` 另起并记录。
- `GET /api/health` 返回 `{"ok":true,"version":"0.1.0","schema_version":<int>,"time":"<UTC>"}`（契约 #24：版本与 schema）；
  `version` 来自 `app/__init__.py` 的 `APP_VERSION`（当前占位 **0.1.0**），`schema_version` = `MAX(schema_migrations.version)`。
- 启动会校验库版本：库内 schema 版本 **高于** 代码支持版本（`MIGRATIONS_DIR` 最大版本）时**拒绝启动**并报 `SchemaVersionError`（契约 L767）。

## 测试

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
& .\.venv\Scripts\python.exe -X utf8 -m unittest discover -s tests -t .
```

- 全部测试使用 `tests/` 下的隔离临时库（`tests/**/_tmp/`），不写业务库。
- 期望：全绿并以真实退出码为准（当前基线 **317 项**）。

## C 导出（每日摘要 → JSON/CSV）

```powershell
# 只读复用 daily_digest；--as-of 必填（ISO-8601 UTC 秒精度）；--out-dir 不得位于 instance/ 下
& .\.venv\Scripts\python.exe tools\export_daily.py --db <隔离副本.db> ``
    --as-of 2026-10-20T12:00:00Z --limit 5 --out-dir reports
```

- 产物：`reports/daily-<digest_date>.json`（= `daily_digest` 原样）与 `.csv`（覆盖 top/blocked/observing/exploring 四池）。
- 数据范围：复用 `daily_digest` 的**默认真实优先口径——只统计 `data_origin='real'`**（合成数据需在 API 侧用 `include_synthetic=1` 显式纳入；本 CLI 不暴露该开关，当前产物默认为 real-only）。
- 限制：`--as-of` 必填、非法格式 exit 2；`--db` 默认 `instance/app.db` 仅只读打开；`--out-dir` 指向 `instance/` 时拒绝；
  CSV 原始字节为 Windows 文本模式（CRLF），按行归一化后与 JSON 语义一致；**不宣称 S5 完成**（定时触发/提醒/工作流仍属 S5，未实现）。

## 备份 / 恢复（S6 脚本，形态 b）

```powershell
# 备份：只读源库 + sqlite3.Connection.backup()；默认落点 instance/backups/app-<UTC>.db，同名绝不覆盖
& .\.venv\Scripts\python.exe tools\backup.py --db <隔离副本.db> --out-dir <隔离备份目录>
# 恢复：仅生成新的隔离副本（目标必须不存在），拒绝覆盖业务库/instance 目录；校验清单/行级哈希/版本
& .\.venv\Scripts\python.exe tools\restore.py --backup <备份.db> --target restore\<run>\app.db
```

- 清单：`<backup>.db.manifest.json`（sha256/字节/integrity/外键/8 表计数/3 张关键表行级哈希/schema 版本/源库 wal-shm 存在性）。
- 限制：**不实现 CONTRACT §6 端点**（形态偏差）；只读打开用 `mode=ro&immutable=1`，检测到旁侧 `-wal`/`-shm` 时**拒绝并提示人工确认**（不自动删除）；
  恢复为**内容/结构等价**校验（非字节级）；未执行 B-04/B-05/B-07/R-01/R-03/R-04 与真实切换/回滚；脚本不探测运行中进程（单写者/quiesce 前提由操作者保证）；**不宣称 S6 完成**。

## 数据隔离（重要）

- **业务库** `instance/app.db` 只由应用写，**禁止**测试、脚本、演练指向它。
- 备份/恢复演练一律在隔离副本（`restore/<run>/app.db`）进行；恢复前先对现库做切换前备份。
- 冻结快照 `tests/acceptance/_snapshots/`（含 `*.manifest.sha256`）为历史证据，**只读**、不得用于恢复运行数据。
- 测试产物位于 `tests/**/_tmp/`，不进入版本控制（见 `.gitignore`）。
- `.gitignore` 对 `tests/acceptance/_snapshots/**` 与 `tests/fixtures/**` 设有**否定例外**；且测试临时目录只按**顶层显式清单**忽略（`tests/api/_tmp/`、`tests/core/_tmp/`、`tests/sources/_tmp/`、`tests/storage/_tmp/`、`tests/ui/_tmp/`、`tests/acceptance/_tmp/`），**不使用**递归模式——因为 `tests/acceptance/_snapshots/**` 内部带有嵌套的 `tests/*/_tmp/`，其中共 **92 个 `.db` 证据文件必须保留**（递归模式会先排除父目录导致否定例外失效）。

## 能力现状

| 能力 | 状态 |
| --- | --- |
| CSV/JSON 导入（校验/去重/版本/证据派生）、候选/证据/货源/成本写入、四项门槛、状态派生 | **已实现并验收** |
| S4 情景（贡献值/摊销/归一/`complete`/`net`，未知≠0） | **已实现并由测试覆盖（无独立验收报告）** |
| S4-B1 货源匹配（只读 `matching.match_supplies`）、S4-B3 排序（只读 `ranking.rank_candidates`）、S5 每日摘要聚合（只读 `daily.daily_digest`） | **已实现并验收（纯函数）** |
| 每日摘要 **HTTP 读路径**：`GET /api/summary/daily?date=YYYY-MM-DD`（CONTRACT #19；默认 **只统计 real**，`include_synthetic=1` 才纳入合成；≤5 条） | **已接入并验收** |
| 上述匹配/排序的 **HTTP 读路径** | **未接入**（方案见 `docs/design/S4_S5_READ_PATH_PROPOSAL.md`，待用户裁定） |
| S3 真实数据源链路（受控 real 模式） | **脚本/模块已实现并验收**（`app/sources/real_link.py`，**409 版**）；已完成用户**逐批授权**的 **2 bvid 真实运行**（隔离 DB、生成 `real` 行与 `ok` run_record，详情回溯经独立核验）。**限制**：仅 2 bvid 单批样本；真实频控/**412**/长跑/并发/断点未验证；`observed_at_source=import_time`（本批 runner 未传源时间）；常规自动化调度/每日触发未实现。依据：`docs/validation/S3_REAL_RUN_FINAL_VERIFY.md`、`S3_REAL_LINK_HARDENING_VERIFY2.md`；**不宣称 S3 阶段全部完成** |
| 健康检查与版本 | **已实现并验收**：`GET /api/health` 返回 `ok/version/schema_version/time` 四键；库版本高于代码支持版本时**拒绝启动**（契约 #24 / L767） |
| 界面：**4 条页面路由只读展示**（`/`、`/opportunity/<id>`、`/import`、`/ops`） | **页面路由已实现（只读展示）**；全站共 **28 条路由**（24 API + 4 页面） |
| C 导出脚本：`tools/export_daily.py`（只读复用 `daily.daily_digest` → `reports/daily-<date>.json/.csv`，支持 `--as-of/--limit/--out-dir`，拒绝 instance 输出目录） | **已实现并验收**（不宣称 S5 完成） |
| S6 备份/恢复脚本（形态 b）：`tools/backup.py` / `tools/restore.py`（sqlite backup API、清单/行级哈希、不覆盖、恢复仅隔离副本） | **已实现并验收**（**脚本形态**；CONTRACT §6 端点 `POST /api/maintenance/backup` 仍未实现，不宣称 S6 完成） |
| 每日定时触发、提醒、交互式前端 | 未实现 |

## 已知差距（如实记录，非承诺）

1. **无备份端点**：CONTRACT §6 规定的 `POST /api/maintenance/backup` **尚未实现**（现有 23 条 API 路由中无该端点）；当前备份/恢复以 `tools/backup.py` / `tools/restore.py` 的**脚本形态 b** 实现（与契约端点描述存在形态偏差，已在 `docs/design/S6_DELIVERY_SPEC.md` §2 记录）。
2. **排序/匹配/摘要未接 HTTP**；排序权重为启发式 `rank-v1`，**待用户确认**；`budget_minutes` 语义与 PLAN §8 存在偏差待裁定。
3. **无独立运行手册**（本 README 即运行说明）、**无 `.git` 仓库**（`.gitignore` 为交付预置）。
4. 设计/验收文档：`docs/design/`、`docs/validation/`（含 `C_EXPORT_ACCEPTANCE.md`、`S6_BACKUP_RESTORE_ACCEPTANCE.md`、`S6_BACKUP_SIDECAR_VERIFY.md`、`CONTRACT_GAP_ACCEPTANCE.md` 等）；S6 备份/恢复**脚本已实现并验收**，但恢复后应用启动（B-04）、真实业务库演练（B-05/B-07）、断网打桩（R-01）、保留轮转（R-04）与真实切换/回滚**未执行**（见 `docs/design/S6_DELIVERY_SPEC.md` §10 与验收报告限制段）。

## 目录速览

```
app/            应用（api 路由、core 领域逻辑、storage 迁移与连接）
tests/          单元/集成测试（api、core、sources、storage、acceptance 快照与临时证据）
docs/design/    契约与各阶段设计（CONTRACT.md、S2/S3/S4/S5/S6 等）
docs/validation/ 独立验收/评审报告
instance/       运行数据（app.db 及既有运行记录；不入版本控制）
tools/          离线脚本（export_daily.py 导出、backup.py/restore.py 备份恢复；只读/隔离）
reports/        C 导出的每日摘要产物（不入版本控制；默认路径）
requirements.txt 依赖（仅 flask==3.1.3）
```
