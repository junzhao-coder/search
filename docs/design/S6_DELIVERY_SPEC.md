# S6 交付设计：备份/恢复、隔离、可复现与回滚（设计稿：未实现、未执行、未联网）

> 状态：**设计稿 / 未实现**。本文不实现任何脚本/端点、不改 `app/**`、`tests/**`、迁移、契约、台账与业务库；不联网、不加依赖；**不宣称 S6 完成、交付可用或已符合契约**。
> **本版为修订 v2**：按独立评审 [S6_DELIVERY_REVIEW.md](../validation/S6_DELIVERY_REVIEW.md)（158 行，结论「需修订」，6 项阻断）的 F-01…F-16 与 M-01…M-09 逐条修订；F→修改位置见 §12，修订史见 §13。评审行号对应 v1（113 行），本文行号以本文件为准。
> 依据（只读已阅）：`docs/design/CONTRACT.md` **§6 存储/迁移/备份（L763–769）**——§6 规定备份由 `POST /api/maintenance/backup` 生成 `instance/backups/app-YYYYMMDD-HHMMSS.db`、恢复为"停应用后替换库文件"、单写者假设（L768）、"库版本更高须拒绝启动"（L767）· `app/api/routes.py`（**实测 561 行 / 23 条路由，无 maintenance/backup**）· `app/api/routes.py:123–131` health 实际返回 `{"ok":true,"schema_version":…,"time":…}`（**无版本字段**）· `app/storage/db.py`（每连接 `journal_mode=WAL`/`foreign_keys=ON`/`busy_timeout=5000`；`ensure_schema:38–64`；`schema_version:69–75` 读 **`MAX(schema_migrations.version)`**）· `app/core/config.py`（实测 env：`APP_HOST/APP_PORT/APP_DB_PATH/APP_TZ_OFFSET_HOURS/APP_MAX_BODY_BYTES/APP_MAX_ROWS` **六个，无 SECRET_KEY**）· `app/__main__.py`（默认 127.0.0.1:5000、threaded=True、无必需 env）· `requirements.txt`（仅 `flask==3.1.3`）· `tests/api/b2_helpers.py`（`tests/api/_tmp/` 下 `mkdtemp`）· `tests/acceptance/_snapshots/`（`s2d_20261009_231628/`、`s2d_20261013_fix1/` 及两份 `*.manifest.sha256`）· 既有 S3/S4/S5 验证批镜像实践 · `DEVELOPMENT_PLAN.md`、`PRODUCT.md`（真实数据与测试隔离、本地交付）。
> 实测环境：Python **3.12.14**、Flask **3.1.3**、sqlite3 **3.53.1**；**仓库根无 README/运行说明，也无 `.gitignore`**；业务库基线 `E073F828CF0F30D6206361BBA3A729826BE096BE3308F5A5DC204406DAE4EB85`，WAL/SHM 当前不存在。
> 技能：本会话**未暴露 `skill` 工具**，如实标注未加载。

## 1. 目标与不可越界边界

- **目标**：给出备份/恢复校验与演练、快照保留、真实/测试隔离、运行/测试/部署可复现、失败回滚、交付清单与离线验收矩阵的**设计**。
- **不做**：不实现脚本/端点、不执行备份/恢复、不联网、不加依赖、不改代码/路由/契约/迁移/台账/业务库；不把演练写成已执行证据。
- **硬纪律**：`instance/app.db` 只由应用写；备份/恢复练习一律在**副本或隔离目录**进行，不得留下业务库 `-wal`/`-shm`。
- **契约-实现先存差距（如实记录，不静默处理）**：①CONTRACT §6 规定的 `POST /api/maintenance/backup` **不存在**（routes.py 23 条路由中无 maintenance）；②CONTRACT L767"库版本更高须拒绝启动"**应用未实现**（`ensure_schema` 只升序应用迁移，不比较上限）；③CONTRACT #24 "health 返回版本与 schema" **实现仅返回 `ok/schema_version/time`，无版本字段**。以上差距均需实现批或裁定处理，本设计**不宣称已符合契约**。

## 2. 备份设计（与 CONTRACT §6 对齐 + 形态待裁定）

- **一致性前提（F-02）**：以 CONTRACT L768 的**单写者假设**为基础，默认流程为 **quiesce → 备份**：先停止应用（确认无 `python -m app` 进程、端口释放），使源库无并发写，再执行备份；`-wal`/`-shm` 在停应用后被 SQLite 正常合并/移除，备份前记录其存在性。**不使用**"只读打开 WAL 库"这类不可执行定义（只读打开 WAL 需要 `-shm` 可写，且复用 `db.connect()` 会再执行 `journal_mode=WAL`）。
- **落点与命名（F-01）**：按 CONTRACT §6 为 **`instance/backups/app-YYYYMMDD-HHMMSS.db`**（契约原文）；**v1 稿的 `backups/` 与"不放在 instance 下"作废**。备份根目录与 `.gitignore` 缺失问题见 §9-1/§9-2。
- **实现形态（两个选项，须用户裁定，不得静默择一）**：
  - **(a) 实现批新增 `POST /api/maintenance/backup`**（与契约一致，但属**公共接口变更**，需用户批准；端点内部仍用标准库 `sqlite3.Connection.backup()` 生成契约路径文件）；
  - **(b) 脚本实现**：由脚本写契约路径与命名，但**形态与契约的端点描述不一致**——须在裁定中明示该偏差。
- **方式**：停应用后，用标准库 `sqlite3.Connection.backup(target)`（源库以普通连接打开并显式关闭）或"停服务后复制 `app.db`（此时 WAL 已合并）"；两条路径均需在副本上验证。
- **每次备份记录**：备份文件 sha256/字节数、`PRAGMA integrity_check`（`ok`）、`PRAGMA foreign_key_check`（空）、关键表计数（`candidate`/`demand_signal`/`evidence`/`supply_offer`/`cost_item`/`gate_review`/`review_item`/`schema_migrations`）、`schema_version`、**3 张关键表行级哈希（F-06）**：`candidate`/`demand_signal`/`supply_offer` 按 `id` 升序，逐行 `sha256(json(行))` 再整体 `sha256` 拼接 → 作为 §3 抽样校验的**期望值来源**；备份耗时；"源库最后写入时间"（F-14）：**停应用后**取关键表 `MAX(updated_at)`（或 `MAX(observed_at)`，视表而定）；**不采用**"WAL 活跃时主文件 sha256"作为内容哈希（改为对备份文件取 sha256），并注明该时间仅为启发式（无统一字段）。
- **失败与磁盘不足**：写前检查目标盘可用空间 ≥ 备份预计大小 × 2；失败/中断删除半成品并明确报错；同名冲突即失败，**不覆盖已有备份**。

## 3. 恢复设计（隔离副本 + 守卫 + 人工切换）

1. **路径守卫（F-05）**：目标路径必须通过 `os.path.realpath` + `os.path.normcase` 规范化后**既不等于**业务库 `instance/app.db`、**也不在其下**；目标**必须不存在**（新建/独占创建，不可覆盖）；**符号链接/junction**（realpath 跟随）与相对路径、大小写变体均须覆盖；**硬链接无法用路径检测** → 以业务库前后哈希 + 目标写保护作为兜底。
2. **隔离副本校验**：复制备份到 `restore/<run>/app.db`，在副本上依次：`integrity_check`（`ok`）→ `foreign_key_check`（空）→ 表计数与备份记录一致 → `schema_version` 与备份记录一致（来源=`MAX(schema_migrations.version)`）→ 3 张关键表行级哈希与备份记录**逐一相等**。
3. **人工切换**：校验通过 → **先停应用** → 对现业务库做"切换前备份"（同样走 §2，含记录）→ 记录现库 sha256 → 替换库文件（同目录原子改名优先）→ 启动 → `GET /api/health` 200（断言实际字段 `ok/schema_version/time`）→ `GET /api/candidates/{known_id}` 200 → 旧库副本按 §4 保留。
4. **known id 来源**：只读从**备份副本**查询（`SELECT id FROM candidate LIMIT 1`），不写业务库。
5. **回滚**：health/详情/校验任一失败 → 立即用"切换前备份"回滚 → 回滚后重跑 health 与详情校验 → 记录原始错误文本与回滚结果；不据错误文本推断数据正确。
6. **演练**：全流程在副本与隔离目录完成，报告写明"演练=副本上执行，业务库未改"；演练中若在副本目录产生 `-wal`/`-shm` **如实记录并保留在隔离目录**，不复制回业务库。

## 4. 保留与轮转（与冻结快照区分）

| 类型 | 位置 | 作用 | 保留 |
| --- | --- | --- | --- |
| **运行备份**（本设计新增） | `instance/backups/`（契约） | 运行数据灾难恢复 | 建议最近 **7 份**或 **14 天**（先到者，待裁定）；只读；删除前先校验新备份可用 |
| **S2 冻结快照** | `tests/acceptance/_snapshots/s2d_20261009_231628`、`s2d_20261013_fix1`，及两份 `*.manifest.sha256` | 历史证据/验收基线 | **永久只读**；不得用于恢复运行数据 |
| **测试/镜像产物** | `tests/**/_tmp/<run>/…` | 单批证据 | 按批次保留；不与运行备份混放 |

- 运行备份与冻结快照**互不替代**；冻结快照的 `*.manifest.sha256` 仅作快照完整性参照。
- 仓库根**无 `.gitignore`**（F-12）：若备份落在仓库内（契约路径 `instance/backups/`）须确认 `instance/` 的交付/版本控制排除策略，避免污染工作区；见 §9-2。

## 5. 真实/测试隔离（硬约束）

- **业务库**：`instance/app.db` 只由应用写；当前基线 `E073F828…4EB85`，WAL/SHM 不存在——交付前必须复验（哈希 + 附加文件存在性）；**禁止任何测试/演练/脚本以它为目标**（§3 守卫 + 前后哈希）。
- **测试用库**：隔离 tmp（`tests/api/_tmp/` 或 `_tmp/<run>/`）。
- **镜像实践（F-07，与既有验证批一致）**：复制 live 的 `app/`、`tests/`（排除 `__pycache__`/`_tmp`/`_snapshots`）、`requirements.txt`、`instance/_e2e.ps1` 到 `_tmp/<run>/mirror`；**不创建镜像内独立 venv**，而用 **live `.venv\Scripts\python.exe` 绝对路径** + `cwd=mirror` + `PYTHONPATH=mirror` 运行；记录真实 cwd 与 `app.__file__`/DB 绝对路径。
- **零写入证据**：前后业务库 + WAL/SHM 哈希、全表全行快照（含时间戳）、无残留进程/端口检查、cwd/DB 路径实证。

## 6. 运行/测试/部署可复现

- **解释器与依赖**：`.venv\Scripts\python.exe` 绝对路径（Python 3.12.14）；依赖仅 `flask==3.1.3`（sqlite3 标准库 3.53.1）；离线（依赖已装，不联网安装）。
- **环境变量（F-13，实测六个）**：`APP_HOST`（默认 127.0.0.1）、`APP_PORT`（默认 5000）、`APP_DB_PATH`、`APP_TZ_OFFSET_HOURS`、`APP_MAX_BODY_BYTES`、`APP_MAX_ROWS`；**无 `SECRET_KEY`**（v1 举例错误，已改正）；配置加载经 `create_app(overrides)` + `app/core/config.py::load_config`。
- **启动/停止/健康检查（明文命令，F-11）**：
  - 启动：`$env:APP_DB_PATH='<隔离库>'; $env:APP_PORT='<备用端口>'; & .\.venv\Scripts\python.exe -m app`（默认 `127.0.0.1:5000`、`threaded=True`、无 reloader）；后台启动须记录 PID；
  - 健康：`Invoke-RestMethod http://127.0.0.1:<端口>/api/health` → `{"ok":true,"schema_version":N,"time":"…"}`（**实际字段**；契约 #24 的"版本"字段缺失 = 先存差距，B-04 按实际字段断言）；
  - 端口避让：启动前检查端口占用（`Get-NetTCPConnection -LocalPort <端口>`），被占用即换端口并记录；
  - 停止：结束对应 PID → 确认端口释放 → 核验无残留 `python -m app`。
- **测试**：`& .\.venv\Scripts\python.exe -X utf8 -m unittest discover -s tests -t .`（`PYTHONDONTWRITEBYTECODE=1`）；记录真实 exit 与计数。
- **schema 版本（F-04）**：`schema_version` = `MAX(schema_migrations.version)`（`db.py:69–75`）；"应用支持版本"在恢复工具/脚本层取 `MIGRATIONS_DIR` 中迁移文件名最大版本前缀；**应用本身当前不拒绝"库版本更高"**（`ensure_schema` 不比较上限，与 CONTRACT L767 存在差距）→ R-02 的"明确报错"由**恢复层**实现并在交付说明中标注该差距。

## 7. 失败模式与回滚

| 失败 | 检测 | 处理 | 回滚 |
| --- | --- | --- | --- |
| 备份中进程被杀/断电 | 半成品、缺记录 | 删除半成品、重做 | 无（源库未改） |
| 磁盘不足 | 写前空间检查/写失败 | 中止、清理 | 无 |
| 备份损坏 | 副本 integrity/foreign_key/计数/行哈希 | 标记不可用、保留现场 | 用上一份可用备份 |
| **备份期间并发写（F-08）** | 备份前后源库 hash/计数不一致 | 立即作废该备份，按 §2 quiesce 重做 | 无 |
| **只读打开 WAL 遗留 `-shm`（F-08）** | 业务库旁出现 `app.db-shm` | 不得再以只读方式打开业务库；由应用正常关闭合并 | 记录并人工确认 |
| 权限/只读文件系统 | 写报错 | 中止并报告 | 无 |
| **符号链接/junction 误指向（F-08）** | realpath+normcase 守卫 | 拒绝、退出码非 0 | 无（未写） |
| **硬链接误写（F-08）** | 无法路径检测 → 业务库前后哈希 | 立即回滚（用切换前备份）并记录 | 切换前备份 |
| 恢复校验失败 | 副本校验项不通过 | 停止切换、保留副本 | 继续用现库（未切换） |
| **恢复中途磁盘不足/中断（F-08）** | 写失败/副本不完整 | 作废副本、清理隔离目录 | 现库未动 |
| **并发备份（F-08）** | 同名/目录锁/独占创建失败 | 后者失败退出 | 无 |
| 切换后 health 失败 | health 非 200/详情异常 | 立即回滚 | 切换前备份 |
| **恢复后副本目录残留 `-wal`/`-shm`（F-08）** | 隔离目录文件清单 | 记录并保留于隔离目录，提醒勿复制回 | 现库未动 |
| 版本/schema 不符 | 恢复层比较 `MIGRATIONS_DIR` 最大版本 | 拒绝恢复（应用层不报错，需脚本层判） | 无 |

## 8. 本地交付检查清单（草案）

- [ ] `.venv` 可执行且 `python -V`=3.12.14；`requirements.txt` 依赖已装（离线）。
- [ ] `app/`、`tests/`、迁移 SQL 完整；`schema_migrations`/`schema_version` 可读。
- [ ] **README/运行说明待补**（当前缺失）：启动/测试/health/停止、配置项、备份恢复命令。
- [ ] **`.gitignore` 待补**并且 `instance/backups/` 处置已定（F-12，见 §9-2）。
- [ ] 业务库基线 `E073F828…4EB85`、WAL/SHM 不存在；`integrity_check=ok`、`foreign_key_check` 空（只读或经备份副本核验）。
- [ ] 最近一份备份的校验记录（含 3 表行级哈希）存在；备份路径符合契约 `instance/backups/`。
- [ ] 隔离纪律：无测试/演练指向业务库的证据（cwd/DB 路径 + 前后哈希）。
- [ ] 离线 `discover` 全绿（记录 exit/计数）；health 200（按实际字段）。
- [ ] 回滚包：切换前备份 + 哈希 + 步骤。
- [ ] `instance/` 既有非库文件（`env_checks.txt`/`http_e2e.txt`/`test_run.txt`/`_e2e.csv`/`_e2e.ps1`）的交付处置已说明（F-15）：默认**随交付保留、只读、不入版本控制**，具体见 §9。

## 9. 待用户/策划者裁定

1. **备份实现形态（F-01）**：(a) 实现批新增 `POST /api/maintenance/backup`（公共接口变更，需批准）或 (b) 脚本写契约路径但形态偏差——**未裁定前不实施**。
2. 备份目录与 `.gitignore`（F-12）：契约路径 `instance/backups/` 是否纳入交付/是否忽略；备份根目录是否允许仓库外。
3. 保留策略数值（默认最近 7 份或 14 天）。
4. 定时备份（本设计不含定时器；如需属 S6 实现批）。
5. README/运行说明编写与位置（交付必需）。
6. 恢复演练频率与记录存放位置。
7. 备份加密/压缩（不引入新依赖；加密需另行授权）。
8. 切换批准流程（谁批准、如何留痕）。
9. **CONTRACT §6/#24/L767 三处契约-实现差距的处置**（端点、health 版本字段、库版本上限）：由实现批补齐还是修订契约，须裁定。

## 10. 可离线执行的最小验收矩阵（设计；本批**未执行**）

> 全部在隔离副本/隔离目录进行，`instance/app.db` 只读或哈希检查；命令以 live `.venv` 绝对路径书写；未执行项不得写成证据。

| # | case | 命令/步骤（草案） | 期望证据 |
| --- | --- | --- | --- |
| B-01 | 备份后校验 | 停应用 → `sqlite3.connect(src).backup(dst)` 至 `instance/backups/app-<ts>.db` → 在 dst 上 integrity/foreign_key/计数/行哈希 | `ok`/空/与记录一致；dst sha256+字节；记录"停应用后"时点 |
| B-02 | 恢复副本并校验 | 复制备份→`restore/<run>/app.db`（目标不存在、独占创建）→ 5 项校验（含 3 表行级哈希） | 全部通过；业务库哈希前后不变 |
| B-03 | 损坏备份被拒绝 | **确定性破坏（F-10）**：覆写备份文件前 16 字节 SQLite 头魔数（`SQLite format 3\0`）→ 以 `sqlite3.connect` 打开并 `PRAGMA integrity_check` | 抛 `sqlite3.DatabaseError`（"file is not a database"）或 integrity≠ok → **拒绝恢复**、退出码非 0 |
| B-04 | 恢复后应用可启动 | `APP_DB_PATH=<restore>/app.db`、`APP_PORT=<备用>`、后台启动记录 PID → health → 已知候选详情（known id 从副本只读查得） | health 200 且含 `ok/schema_version/time`；详情 200；停止后端口释放 |
| B-05 | 演练不写业务库 | 全程前后记录业务库+WAL/SHM 哈希 | `E073F828…4EB85` 不变；WAL/SHM 仍不存在 |
| B-06 | 守卫拒绝误指向 | 目标=`instance/app.db`、相对路径、大小写变体、symlink/junction、目标已存在 | 全部拒绝、退出码非 0；业务库哈希不变；硬链接用例→业务库前后哈希兜底 |
| B-07 | 只读打开不产生 `-shm`（F-16） | 对业务库做一次纯哈希/存在性检查前后对比 | `-shm`/`-wal` 均未出现（本设计不打开业务库做 SQL 查询） |
| R-01 | 全新环境离线跑测试（F-09） | 已装依赖 + `PYTHONDONTWRITEBYTECODE=1` 跑 discover；**无网络证明**：以 `socket.socket.connect`/`getaddrinfo` 打桩抛 `RuntimeError` 跑同一套件并记录 exit | 两次均 exit=0/计数一致；`app/sources/*` 无网络客户端导入 |
| R-02 | 版本不符明确报错 | 构造 `schema_version` 高于 `MIGRATIONS_DIR` 最大版本的备份副本 → 恢复工具比较 | 恢复层明确报错"库版本高于应用支持版本"并拒绝；**注明应用层当前不拒绝（契约 L767 差距）** |
| R-03 | 停止/启动可复现 | 指定 `APP_DB_PATH`/`APP_PORT` → 启动（记录 PID）→ health → 停止 → 端口检查 → 再启动 → health | 两次 health 200；端口释放；无残留进程 |
| R-04 | 保留轮转不误删 | 造 8 份备份、保留 7 份；设只读（`attrib +R`/`icacls`） | 最旧列待删且删除前校验新备份可用；冻结快照与 `*.manifest.sha256` 不受影响 |

## 11. 未实现 / 未执行 / 未覆盖

- **未实现**：备份/恢复脚本或端点、校验工具、README、`.gitignore`、保留轮转、定时任务、加密/压缩、表行级哈希记录工具。
- **未执行**：§10 的 B-01…B-07、R-01…R-04 全部未运行（未备份、未恢复、未启动应用）。
- **未覆盖**：远程/云备份、异地容灾、多实例并发、CI、界面操作手册；SQLite `backup()` 与并发写的重启语义、只读 WAL 打开对 `-shm` 的具体要求属实现批须实测确认项。
- **声明**：全文设计稿/未实现/未联网；不改代码/路由/契约/迁移/台账/业务库；**不宣称 S6 完成或交付可用**；需独立执行者评审（g3）后按 §9 裁定另立实现批。

## 12. F→修改位置映射表（本轮修订）

| 编号 | 问题（评审） | 修改位置 | 修订要点（前 → 后） |
| --- | --- | --- | --- |
| F-01 | 备份落点/形态与 CONTRACT §6 冲突 | §1 差距、§2、§4、§8、§9-1 | `backups/` → **`instance/backups/app-YYYYMMDD-HHMMSS.db`**；写明端点 `POST /api/maintenance/backup` **契约有、实现无**；给 (a) 新增端点（须批准）/(b) 脚本（形态偏差）两选项，不静默择一 |
| F-02 | 一致性前提未定义、"只读打开 WAL"不可执行、切换前备份顺序 | §2 前提、§3.3、§7 | 默认 **quiesce→备份**（单写者假设 + 停应用）；删除"只读/短连接"表述；定义 `-wal`/`-shm` 处理；切换前备份移到**停应用之后** |
| F-03 | health 响应描述不实 | §1 差距、§6、B-04 | 实际字段 `ok/schema_version/time`（无版本）；契约 #24 缺口如实记录；B-04 按实际字段断言 |
| F-04 | schema_version 来源未写、R-02 不可执行 | §2 记录、§6、R-02 | 来源=`MAX(schema_migrations.version)`；R-02 由**恢复层**比较 `MIGRATIONS_DIR` 最大版本；注明应用层不拒绝高版本（L767 差距） |
| F-05 | 恢复守卫不足 | §3.1、B-06 | realpath+normcase、目标不存在/独占创建、symlink/junction/相对路径/大小写用例；硬链接→业务库前后哈希兜底 |
| F-06 | 抽样行哈希无期望值 | §2 记录、§3.2、B-02 | 备份时记录 3 张关键表按 `id` 排序的逐行 sha256 + 拼接 sha256，作为恢复校验期望值 |
| F-07 | 镜像独立 venv 不符实践 | §5 镜像段 | 改为 **live `.venv` 绝对路径 + `cwd=mirror` + `PYTHONPATH=mirror`**，不建镜像内 venv |
| F-08 | 失败表遗漏 7 类 | §7 | 补并发写/`-shm` 残留/权限只读/符链 junction/硬链接/恢复中断/并发备份/副本 WAL-SHM 残留 |
| F-09 | R-01 无网络无证明方法 | R-01 | 补 socket 打桩抛错跑 discover 的可核验方法（或明确降级） |
| F-10 | B-03 损坏构造不确定 | B-03 | 写死"覆写前 16 字节头魔数"→ 接受 `sqlite3.DatabaseError`/integrity≠ok 为检出 |
| F-11 | B-04/B-06/R-03 缺命令细节 | B-04/B-06/R-03、§6 | 补 `APP_DB_PATH`/`APP_PORT`、后台 PID、端口占用检查、known id 只读来源 |
| F-12 | 备份目录污染/无 `.gitignore` | §4、§8、§9-2 | 列为待裁定/实现项；交付清单增加 `.gitignore` 与备份目录处置 |
| F-13 | 环境变量清单不符 | §6 | 改为实测 6 个 `APP_*`（无 `SECRET_KEY`） |
| F-14 | "源库最后写入时间"取法未定义 | §2 | 定义"停应用后取关键表 `MAX(updated_at)`"、反面排除主文件 sha256；注明启发式局限 |
| F-15 | 未列 freeze manifest/`instance/` 非库文件 | §4、§8 | 补 `*.manifest.sha256`；交付清单说明 `instance/` 既有非库文件处置 |
| F-16 | §9 缺契约冲突项、缺 `-shm` 用例 | §9-9、B-07 | 补契约-实现差距裁定项与"只读打开不产生 `-shm`"用例 |

## 13. 修订史

- v1（revision 2）：初版（备份/恢复/保留/隔离/可复现/失败/清单/B、R 矩阵）。
- v2（本版，task-4974f39a22fb460843d3374787327f23）：按 `S6_DELIVERY_REVIEW.md`（F-01…F-16/M-01…M-09）修订：备份落点与形态对齐 CONTRACT §6 并记录契约-实现先存差距（端点/health 版本/库版本上限）、一致性前提改为 quiesce、health 实际字段、schema 版本来源与恢复层判定、恢复守卫强化、行级哈希期望值、镜像纪律、失败表补 8 类、R-01 无网络证明、B-03 确定性破坏、B-04/B-06/R-03 命令细节、环境变量清单、源库末次写入定义、manifest 与非库文件处置、新增 B-07 与 §12 映射表、§13 修订史。
