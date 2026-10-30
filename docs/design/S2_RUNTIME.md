# S2 运行与验证记录（S2-B1）

> 任务：`task-829baf5647ea6a6f87a0ec5729abd80a`（S2-B1，执行者 session-2e7e3159-0ac8-53a2-a3ae-0c589fafdb87）。
> 依据：[数据与接口契约 v3](<CONTRACT.md>)（Flow 已验收冻结）与[验收矩阵](<ACCEPTANCE.md>)。
> 记录时间：2026-10-09（本地 UTC+8）。本文件只写实际执行过的事实；未运行的项目明确标为未执行。
> 证据文件（均在 `instance/`，属本任务授权范围）：`env_checks.txt`、`test_run.txt`、`http_e2e.txt`、`_e2e.ps1`（可复跑脚本）。

## 1. 结论摘要

- 本地运行环境实际可用：Python 3.12.14、SQLite 3.53.1、Flask 3.1.3（唯一新增直接依赖，已锁定）。
- 已实现并可运行：最小 Flask 入口（仅绑定 `127.0.0.1:5000`）、SQLite 版本化迁移与种子、CSV/JSON 导入（`validate`/`atomic`/`partial`）、身份与去重（§4.5）、幂等回执（§0.7/§1.15）、候选列表/详情与证据回溯、来源与运行记录查询。
- 已实际通过：45 项 stdlib unittest（4 个命令，exit=0）+ 一次真实 HTTP 端到端（导入 → 详情 → 重导 → 重启 → 查询）。
- 未实现（后续任务）：四门槛写入口与门槛降级物化、情景与利润计算、草稿、经营反馈、来源自动采集、排序权重、备份/部署。相关矩阵行保持「未执行」。
- 本任务授权写入范围只含 `docs/design/S2_RUNTIME.md`（`ACCEPTANCE.md`/`CONTRACT.md` 不在范围，Flow 已拒绝写入），因此**矩阵行状态填写的对照表放在本文件 §7**，需授权后落盘。

## 2. 环境与依赖核验（T-01…T-11）

命令原文与完整输出见 `instance/env_checks.txt`。摘要如下。

| 行 | 命令 | 结果 | 退出码 |
| --- | --- | --- | --- |
| T-01 | `& <内置>\python.exe -V` | `Python 3.12.14` | 0 |
| T-02 | `python -m venv .venv`；检查 `Scripts\python.exe`、`pyvenv.cfg` | 均存在 | 0 |
| T-03 | `pip --version`；`pip download flask -d .venv/cache` | `pip 25.0.1`；缓存落 7 个 wheel（flask/jinja2/werkzeug/click/itsdangerous/blinker/markupsafe） | 0 |
| T-04 | `pip install flask`；`pip show flask`；写 `requirements.txt` | `Flask 3.1.3`；`flask==3.1.3` | 0 |
| T-05 | `python -c "import sqlite3;print(sqlite3.sqlite_version)"` | `3.53.1`（部分唯一索引与 COALESCE 表达式索引在本库可用并已使用） | 0 |
| T-06 | `python -m app`；`GET /api/health`；`netstat -ano` | 200 `{"ok":true,"schema_version":1}`；`TCP 127.0.0.1:5000 LISTENING` | 0 |
| T-07 | `python -m unittest discover -s tests` | **失败**：`ImportError: Start directory is not importable: 'tests'`（缺 `tests/__init__.py`，该文件不在本任务授权写入范围，Flow 拒绝写入）→ 改为按文件运行，见 §4 | 1（discover）/ 0（按文件 4/4） |
| T-08 | `flow_state` + 实测命令工具 | 执行者 `allowCommands=true`；`pwsh` 实测返回 `Python 3.12.14` | — |
| T-09 | 首启与 `instance/`、`instance/app.db` | 目录与库文件生成；测试全部走 `APP_DB_PATH` 临时库 | 0 |
| T-10 | 启动前 5000 检查；`APP_HOST`/`APP_PORT` 配置 | 启动前 5000 空闲；服务绑定 5000；端口与 DSH GUI 19387 不同 | 0 |
| T-11 | `requirements.txt` + `app/` 导入清单 + `pip freeze` | `app/` 内第三方导入只有 `flask`；freeze 7 项均为 Flask 传递依赖 | 0 |

安装环境（`pip freeze`）：`blinker==1.9.0, click==8.5.0, Flask==3.1.3, itsdangerous==2.2.0, Jinja2==3.1.6, MarkupSafe==3.0.4, Werkzeug==3.1.9`。

## 3. 数据库与迁移

- 默认业务库：`instance/app.db`（`APP_DB_PATH` 可覆盖）；WAL 模式、`foreign_keys=ON`、`busy_timeout=5000`。
- 迁移：`app/storage/migrations/0001_init.sql`，由 `app/storage/db.py` 按 `schema_migrations` 版本号顺序应用；重复执行是空操作（`ensure_schema` 两次调用返回同一版本 1）。
- 表（本轮范围）：`source`、`candidate`、`demand_signal`、`evidence`、`supply_offer`、`cost_item`、`gate_review`、`review_item`、`import_batch`、`import_row_result`、`run_record`、`idempotency_key`、`schema_migrations`。**未创建** `draft`、`feedback`、`search_coverage`、`expense`（属 B2/S3/S5，不预建）。
- 约束按契约 §2.2 原生实现：身份唯一键均含 `data_origin`；`cost_item` 活跃唯一部分索引；`gate_review(candidate_id, gate, seq)` 唯一；`review_item` 未决唯一（含 `COALESCE(ref_gate,'')`、`COALESCE(ref_id_b,'')`）；`run_record` 每日幂等部分索引；`idempotency_key UNIQUE(scope, client_ref)`。
- CHECK 覆盖：输入金额 `>= 0`；`*_bp ∈ 0..10000`；`minutes/actual_minutes ∈ 0..1440`；`cost_item` 值列非空个数 ∈ {0,1} 且与 `value_kind` 一致；`rate ⇒ per_order`；`minutes ⇒ manual_labor`；`hourly_rate_minor ⇒ manual_labor`；`sale_price ⇒ (value_kind IS NULL OR value_kind='money')`；`recurring ⇒ period 非空`；`sample_checked<>'none' ⇒ sample_note 非空`。
- 种子：`manual_import`、`xianyu`、`xiaohongshu`、`bilibili` 四行来源，`access_mode='manual_import'`、`access_verified='yes'`（**不代表任何平台自动读取可用**）。

## 4. 测试证据（实际运行，45 项）

命令与逐条输出见 `instance/test_run.txt`。

| 命令（`.venv\Scripts\python.exe` 绝对路径调用，`PYTHONUTF8=1`） | 用例数 | 结果 | 退出码 |
| --- | --- | --- | --- |
| `python -X utf8 tests\core\test_money.py -v` | 7 | OK | 0 |
| `python -X utf8 tests\core\test_identity.py -v` | 7 | OK | 0 |
| `python -X utf8 tests\storage\test_migrations.py -v` | 4 | OK | 0 |
| `python -X utf8 tests\api\test_import_api.py -v` | 27 | OK | 0 |

覆盖要点：金额解析与取整（`9.90×500bp=50`、`33.33×500bp=167`、`15 分×3000 分/时=750`）、bool/负号/多位小数拒绝；归一化与 `url_norm`（去跟踪参数、排序、去默认端口/片段）；身份键命名空间与跨渠道隔离；迁移幂等与种子；CHECK 反例；正例 CSV/JSON 导入计数；重导不增殖；内容变化 `version_added`；不同 URL 同文 `dup_suspect`；跨渠道同 `native_id` 两候选；同需求新增成本子记录；`real`/`synthetic` 隔离；GBK 拒绝；URL-only 货源不造摘录；无需求组 `observed_at` warning；采购三档 basis 相互独立；原子拒绝与逐行原因；`validate` 零写入；幂等重放/409/重启后重放；404 契约；列表顺序可复现；页面路由 501。

测试隔离：每个用例用 `tests/<area>/_tmp/` 下的独立临时目录（`tempfile.mkdtemp`），不触碰 `instance/app.db`。

## 5. HTTP 端到端证据（实际运行）

脚本 `instance/_e2e.ps1`，原始输出 `instance/http_e2e.txt`。

1. 清空业务库后 `python -m app` 启动，`GET /api/health` → `200 {"ok":true,"schema_version":1,"stage":"S2-B1"}`。
2. `netstat`：`TCP 127.0.0.1:5000 … LISTENING`（仅本机地址，无 `0.0.0.0`）。
3. `POST /api/imports?format=csv&mode=atomic`（§4.7 38 列正例）→ `201`，`counts.created=1`，返回真实实体 ID：1 `candidate`、1 `demand_signal`、2 `evidence`（需求 + 条款）、1 `supply_offer`、10 `cost_item`。
4. `GET /api/candidates` → `200`，`total=1`，身份键 `u:xianyu:https://example.com/demand/1001`，`status=pending`。
5. `GET /api/candidates/{id}` → `200`：四门槛全 `unverified`，`derived_status=pending`，`status_reason=derived:pending|gates_incomplete`；成本项 10 条（`money_minor=990`、`rate_bp=500`、`minutes=15`+`hourly_rate_minor=3000`，`period` 仅 recurring 采购行有值）；货源 `unit_price_minor=0`（已知免费）、`resale_allowed=yes`、`license_evidence_id` 指向条款证据。
6. 同文件再次导入 → `201`，`counts.duplicate_skipped=1`、`created=0`；业务表计数不变，仅新增批次与运行记录。
7. 停止服务并重启 → 列表仍 `total=1`、`GET /api/runs` 返回 2 条运行记录（每次导入一条，`source_id` 为 NULL）。
8. `GET /` → `501`（页面占位，模板未交付）。
9. 库内最终计数：`candidate 1 / demand_signal 1 / evidence 2 / supply_offer 1 / cost_item 10 / import_batch 2 / run_record 2 / idempotency_key 0`（未使用 `client_ref`）。

## 6. 实现摘要

- `app/__init__.py`：`create_app`（配置、请求体大小上限、蓝图、统一错误体）；`app/__main__.py`：`python -m app` 启动，`debug=False`、`use_reloader=False`，仅本机。
- `app/core/`：`config.py`（环境变量配置，`APP_HOST/APP_PORT/APP_DB_PATH/APP_TZ_OFFSET_HOURS`）、`money.py`（整数分、½ 分向上取整）、`identity.py`（归一化、指纹、`url_norm`、身份键）、`state.py`（`effective_gate_status` 四条判定 + `recompute`）、`importer.py`（V1–V27 校验、CSV/JSON 解析、身份/版本/子记录去重、事务策略、幂等）、`errors.py`、`util.py`。
- `app/storage/`：`db.py`（连接、迁移、种子）、`migrations/0001_init.sql`。
- `app/api/routes.py`：`GET /api/health`、`POST /api/imports`、`GET /api/imports/{id}`、`GET /api/candidates`、`GET /api/candidates/{id}`、`GET /api/sources`、`GET /api/runs`；页面占位 `/`、`/opportunity/<id>`、`/import`、`/ops`（`501`）。
- 事务策略：`atomic` 任一行校验失败 → 业务数据零写入、批次记 `rejected` 且逐行原因可查；`partial` 跳过失败行并记 `partial_committed`；`validate` 只解析校验、不写任何记录。导入的幂等记录与业务写入同事务；`client_ref` 同载荷重放返回原批次并标 `deduplicated`，异载荷 `409`。
- 未实现端点（契约 §5.3 其余项）保持 404，不做占位声明。

## 7. 验收矩阵结果对照（S2-B1 时点快照）

> **本表为 S2-B1 时点记录；权威状态见 [ACCEPTANCE.md](<ACCEPTANCE.md>)（S2-B2 已按实测落盘）。** S2-03/12/13 在 B1 时点应为“部分通过”（情景与 #11 门槛端点属 B2），S2-11/S2-31 以 ACCEPTANCE 实测为准（B1 时点由 B2 实测补齐，见 ACCEPTANCE 对应行）。

本任务授权写入范围只含 `docs/design/S2_RUNTIME.md`；当时对 `ACCEPTANCE.md` 的写入被 Flow 拒绝（超出授权文件范围），故先在此登记；B2 任务获权后已按实测落盘。

| 行 | 本轮状态 | 依据 |
| --- | --- | --- |
| T-01–T-06, T-08–T-11 | 通过 | §2 表（命令、输出、退出码） |
| T-07 | 部分通过 | 按文件运行 45 项全绿；`discover -s tests` 需 `tests/__init__.py`（范围外） |
| S2-01, S2-02 | 通过 | 迁移幂等 + 重启持久（§4、§5） |
| S2-03 | 部分通过（B1 时点：存储层/只读派生已证；情景与 #11 门槛端点由 B2 完成，见 ACCEPTANCE） | 正例 38 列/10 成本项/`cost_supply_url`→`supply_offer_id` 已证；情景数值与 G3 准入在 B1 无端点可证 |
| S2-04, S2-05, S2-06, S2-07 | 通过 | 重导不增殖、跨渠道两候选、版本与 `dup_suspect`、`t:` 复用与子记录独立判定 |
| S2-08 | 部分通过 | `real`/`synthetic` 隔离已测；`POST /merge` 属后续任务 |
| S2-09, S2-10, S2-11 | 通过 | 原子拒绝与逐行规则号（含 V16 行级拒绝）、GBK `encoding_error`、V10/V23 与 URL-only 货源 |
| S2-12 | 部分通过（B1 时点：存储层/只读派生已证；情景与 #11 门槛端点由 B2 完成，见 ACCEPTANCE） | 未知/已知 0/单 basis 已知三情形；B1 无情景端点 |
| S2-13 | 部分通过（B1 时点：存储层/只读派生已证；情景与 #11 门槛端点由 B2 完成，见 ACCEPTANCE） | 4 组候选均 `pending`/`unverified`；门槛核验端点属 B2 |
| S2-19, S2-22, S2-23, S2-27 | 部分通过 | 取整/负金额拒绝、0 vs NULL 落库、顺序可复现、导入幂等（含重启）；其余属 B2/S4/C |
| S2-29, S2-31, S2-32 | 通过 | `validate` 零写入、错误码覆盖、仅本机监听（异机留空） |
| S2-14–S2-18, S2-20, S2-21, S2-24, S2-25, S2-26, S2-28, S2-30, S2-33, S2-34 | 未执行 | 四门槛写入口、情景、草稿、反馈、页面属 B2/C/D |
| S3-01, S3-03–S3-06, S4-01–S4-07, S5-01–S5-08, S6-01–S6-06 | 未执行 | 对应阶段未开始（S3-02 仅种子行可查，给 部分通过 更准确） |

## 8. 与契约文本的差异（实现层解释，供策划者核对）

1. **身份键命名空间用来源名**：实现产出 `n:xianyu:1001`、`u:xianyu:<url_norm>`，与 §4.7 示例和矩阵 S2-05 一致；§4.5 文字写作 `<source_id>`（内部为 `s_xianyu`）。数据库仍保留 `source.id` 外键。若需与文字严格一致，须改契约示例与矩阵行，二者只能取一。
2. **`assumption` 无说明可入库**：§4.3 明示导入成本项默认 `fact_kind='assumption'` 且说明为空时「视为假设未说明、不构成 G3 依据」，故该要求实现为门槛准入规则；§1.5「`estimate`/`assumption` 必须填 `assumption_note`」未落成 DB CHECK，否则导入正例无法落库。
3. **批次状态无 `running`**：`import_batch.status` 枚举按契约仅 `committed/rejected/partial_committed/validated`，批次行在同一事务内先写占位值、提交前改写最终值，避免出现枚举外状态。
4. **页面路由为 501 占位**：`/`、`/opportunity/<id>`、`/import`、`/ops` 已保留但**不构成可用界面**，模板由 C 交付后实现。

## 9. 未覆盖与限制

- 四门槛写入口、门槛同事务降级物化（§3.4）、情景与利润计算、草稿、经营反馈、来源采集、排序权重、备份/部署均未实现，亦未运行相应矩阵行。
- `python -m unittest discover -s tests` 未通过（缺 `tests/__init__.py`，范围外）；如需该形式，请授权该单文件或调整 T-07 命令。
- `instance/http_e2e.txt` 曾被 D 判定为**采集端编码产物**（PowerShell 5.1 把服务端 UTF-8 响应字节按 cp1252/latin-1 解码后再以 UTF-8 写入；存储与接口字节均正确，反解证明见 [S2_B1_REVIEW.md](../validation/S2_B1_REVIEW.md) §4-P2-4）。收尾任务已把 `instance/_e2e.ps1` 的采集改为 **Python urllib 读取并显式 UTF-8 解码**（并设置 `[Console]::OutputEncoding`/`$OutputEncoding`），复跑重生成该文件：命令 `& .\instance\_e2e.ps1`，**exit=0**；复查结果——文件以 UTF-8 解码无异常、`U+FFFD` 计数 0、cp1252 残留标记计数 0，且含抽查串“示例-周会纪要模板包”。
- **历史（已修正）**：B1 版 `instance/_e2e.ps1` 含 `Remove-Item instance\app.db*`，只适合一次性证据复现，不应作为通用复跑方案。收尾任务（`task-639aeee9a8f8365c4b4e06c0dfcc4cc7`）已把它改为**隔离运行**：每次在 `tests\api\_tmp\s2_boundaries\e2e_<时间戳>_<GUID8>\` 下新建独立 `app.db`/`input.csv`/`http_e2e.txt`，注入 `APP_DB_PATH`/`APP_PORT` 并在 `finally` 恢复，只停止自己启动的 PID，任何 HTTP 状态/计数不符即以非零退出；运行前后对比 `instance\app.db`（及 wal/shm）SHA256。路径守卫由**同一函数**处理（`GetFullPath` 规范化后只接受隔离根自身或“根+目录分隔符”子路径，指向 `instance/` 一律拒绝，且在任何目录/文件创建之前判定），run 目录用 GUID 后缀 + 不带 `-Force` 的独占创建。实测：默认与子目录各跑一次 → 均 `RESULT PASS`、**exit=0**，目录分别为 `e2e_20261009_230547_0fc454e2` 与 `e2e_20261009_230602_56db1242`（不同，证明不复用旧库）；越界输入 `s2_boundaries_extra`、`s2_boundaries\..\s2_boundaries_extra`、`instance` 三次均 **exit=1** 且未创建任何越界目录；全程 `business_db_unchanged=True`（`E073F828CF0F30D6206361BBA3A729826BE096BE3308F5A5DC204406DAE4EB85`，wal/shm 均 MISSING），无残留进程。证据日志：`tests/api/_tmp/s2_boundaries/evidence/guards_rework.txt`。`instance\http_e2e.txt` 作为历史捕获保留、不再由脚本改写。
- 未做浏览器渲染检查（无 UI）、未做异机访问验证（无第二台主机，按约定留空）、未做真实渠道数据核验。
- 未启用任何付费或外部服务；未发起外部网络请求；未自动抓取任何链接。
- 测试与端到端只使用示例域合成数据；`instance/app.db` 保留一次合成 E2E 样本（B1 时代写入，收尾任务起脚本不再触碰业务库；如需回到干净库由用户自行删除）。

## 10. 复跑指引

```powershell
$env:PYTHONUTF8='1'
$py = ".\.venv\Scripts\python.exe"

# 1) 全量回归（含 discover；当前实测 107 项 OK / exit=0，数量随 C/D 槽位新增用例变化）
& $py -X utf8 -m unittest discover -s tests -t .

# 2) 环境核验（追加写入 instance\env_checks.txt）
& $py -V; & $py -m pip show flask; & $py -c "import sqlite3;print(sqlite3.sqlite_version)"

# 3) HTTP 端到端（隔离运行：独立临时库/输入/日志，不触碰 instance\app.db）
& .\instance\_e2e.ps1                       # 默认端口 5091；占用或路径越界会直接报错退出
& .\instance\_e2e.ps1 -Port 5093 -WorkRoot "tests\api\_tmp\s2_boundaries"
```

端到端产物落在 `tests\api\_tmp\s2_boundaries\e2e_<时间戳>\`（`app.db`、`input.csv`、`http_e2e.txt`），脚本退出码 0 表示全部状态/计数断言通过；日志内含 `business_db_unchanged=True` 与 `instance\app.db` 的前后 SHA256，用来证明业务库未被改动。
