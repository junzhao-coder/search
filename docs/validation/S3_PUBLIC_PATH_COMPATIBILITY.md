# S3 公共路径兼容性补证 第 1 批（修订 1）：资格 + 矩阵

- 任务：`task-6342b3e021dc225c5b6f31481b8a7e1a`（revision 5）　执行者：`session-01ba487c-f808-55a7-a1f7-5f436ee12811`（原A）
- 运行目录：[run_20261016_133627_compat1](<../../tests/acceptance/_tmp/s3_public_compat_v1/run_20261016_133627_compat1>)
- 本批**只做资格与矩阵**：**未运行应用测试、未启动服务、未做 HTTP/E2E/217 回归、未做差分执行**，因此**不给出任何兼容性结论**。
- 修订说明：本轮按退回意见**一次性**修订；旧 20 号证据与两个旧工具**原样保留**，新增 **21/22** 号原件，不覆盖历史。

## 1. 工具通道资格（真实执行证据）

| 能力 | 结论 | 真实依据（可打开） |
| --- | --- | --- |
| 命令/进程通道 | **可用** | 本批真实执行：21 号复算与包含集脚本 [21_contain_set_manifest_cmd.log](<../../tests/acceptance/_tmp/s3_public_compat_v1/run_20261016_133627_compat1/evidence/21_contain_set_manifest_cmd.log>) **exit=0**；版本命令 [21_toolchain_versions_venv_cmd.log](<../../tests/acceptance/_tmp/s3_public_compat_v1/run_20261016_133627_compat1/evidence/21_toolchain_versions_venv_cmd.log>) 与 [21_toolchain_versions_system_cmd.log](<../../tests/acceptance/_tmp/s3_public_compat_v1/run_20261016_133627_compat1/evidence/21_toolchain_versions_system_cmd.log>) 均 **exit=0** |
| Python 版本（实读日志） | 仓库 venv **3.12.14**；系统 **3.10.9** | 上述两份版本日志逐字：`python 3.12.14` / `python 3.10.9`，`platform Windows-…26200` |
| Flask / sqlite（实读日志） | Flask **3.1.3**、Werkzeug **3.1.9**、sqlite3 **3.53.1** | `21_toolchain_versions_venv_cmd.log` 逐行输出 |
| SHA256 | **本批真复算** | 21 号脚本对 live 五件重算并 PASS（见 §3）；候选 importer 亦真复算（§2） |
| 子进程与证据编码 | 可用 | `run_and_log.py` 捕获 `cmd/cwd/time/stdout/stderr/exit`；21/22 号文本均 **UTF-8 无 BOM、LF**，脚本自检 `text_problems=[]` |
| 技能通道 | **无 tool 通道；本批未加载** | 本会话工具集未暴露 `skill` 工具（工具目录虽公告技能清单，但调用面不存在）；历史批次曾以**磁盘读取** SKILL.md 遵循 ponytail；本批只写文档/矩阵，未加载任何技能 |
| 本批**不**做 | — | 不跑 `tests/**`、不启 loopback 服务、不做真实 HTTP、不做差分、不写旧树/历史 scope、不新增依赖或费用 |

**失败史更正（撤回此前表述）**：
- 第 1 轮 GBK 编码失败：首轮输出被写入同一 20 号日志，随后成功轮**覆盖**了它，本 run 内**没有独立原件**。因此本报告**撤回**"exit1 原件已留档"，改为如实记录：**"执行者自述首次失败（GBK 控制台编码），原始输出未留存"**；不做事后转录冒充原始日志。
- venv 版本命令首次尝试：因相对路径解析失败（`FileNotFoundError`，异常在记录器内抛出）**未生成日志**，亦属"执行者自述失败、无原件"；随后用**绝对路径**重试成功（日志 exit=0）。
- 此后纪律：每次运行使用**唯一 label/path**；旧 20 号 JSON/log 与两个旧工具原件不覆盖，修改工具另存 v2 命名（本轮即 `compat_evidence_v2.py`）。

## 2. 修前候选出处与当前 hash（真复算，合格）

- 出处（逐字）：`tests/api/_tmp/import_history_fix_v1/run_20261015_212020_704683a1/18_scope_and_hashes.txt:2` → `AFTER app\core\importer.py live=42F1F8FC…E8946 mirror=42F1F8FC…E8946 same=True`。
- 本批真复算候选 `…/mirror/app/core/importer.py` = `42F1F8FC8A6999C407C77414C8D4A16D2C939B498C3ABFE2A40D9B47287E8946` → **一致（合格）**；未触发停止、未重建旧文件（20 号证据见 [20_compat_hashes.json](<../../tests/acceptance/_tmp/s3_public_compat_v1/run_20261016_133627_compat1/evidence/20_compat_hashes.json>)）。
- 取值口径（防混用）：`05_mirror_manifest.txt:8` 为**初建修前** `C2BF667B…`（仅历史）；`:15` 才是**修后** `42F1F8FC…`；`:18` 是夹具文件 hash；`:19` 说明镜像纳入 A 已验收 scope（`app/sources`、`tests/sources`、`tests/fixtures`），其增减**不算业务差异**。

## 3. 基线（**收窄为 hash/包含集资格**，不外推语义等价）

**通路口径**：应用集 = `app/**`（含 `app/storage/migrations/*.sql`）+ `requirements.txt`；测试/夹具集单列。遍历实现（本轮修正）：`os.scandir` 显式递归，**按精确目录名剪枝**（`__pycache__`/`_tmp`/`_snapshots`/`.venv`/`.pytest_cache`/`.mypy_cache`），**逐项检查 `st_file_attributes & FILE_ATTRIBUTE_REPARSE_POINT`** 并跳过 reparse/junction，`scandir` 异常**记录不吞**。

实测（[21_contain_set_manifest.json](<../../tests/acceptance/_tmp/s3_public_compat_v1/run_20261016_133627_compat1/evidence/21_contain_set_manifest.json>)）：
- 文件数：应用集候选 **37** / live **38**；测试集候选 **29** / live **31**。
- 剪枝：live **4** 个目录被剪枝、候选 0；**reparse/junction 命中 0**（两侧均为 `[]`）；遍历异常 **0**。
- 差异：应用集**缺失 0**、**新增 `app/sources/wiring.py`**、**内容变化仅 `app/core/importer.py`**（候选 `42F1F8FC…` → live `A11EAF4D…`）；测试集新增 2 件（`tests/sources/test_wiring_offline.py`、`tests/acceptance/fixtures/contract_4_7_positive.csv`）、内容变化 0。
- 冻结件（live）**再次真复算 5/5 PASS**：`wiring bafcf397…`、`importer a11eaf4d…`、`adapter b0dc0ced…`、`test_import_api 251fff5f…`、`test_wiring_offline c66d72ee…`。
- 逐件清单：(path, bytes, sha256) 两侧全量在 21 号 JSON 的 `manifests` 中，供运行前复制校验。

**结论收窄（按退回意见）**：token 只说明 token 出现——`internal_observation`/`run_source_id`/`_INTERNAL_OBSERVATION_KEYS`/`observed_at_hint` 在候选 importer **全部 false**、在 live **全部 true**，`wiring.py` 候选无/live 有；这**不能**推出"恰由内部参数解释了全部改动"。可逐 hunk 复核的原始证据是 stdlib `difflib` 生成的 [21_importer_unified_diff.txt](<../../tests/acceptance/_tmp/s3_public_compat_v1/run_20261016_133627_compat1/evidence/21_importer_unified_diff.txt>)（**106 行，+63/−5**）；本报告不对其语义作判定，交由策划逐 hunk 读。异常差异不静默接受：21 号脚本对遍历异常、reparse 命中、文本编码问题均以显式字段报告并在异常时非零退出。

## 4. 最小差分矩阵（设计稿，**本批不执行**）

### 4.1 列口径（"全列"的唯一定义）

- **全列 = `PRAGMA table_info(<table>)` 导出的全部列 / `SELECT *`**，不做任何选列裁剪。
- 必须覆盖：`import_batch`、`import_row_result`、`run_record`；以及本矩阵 case 实际涉及的 `candidate`、`demand_signal`、`evidence`、`supply_offer`、`cost_item`、`gate_review`、复核项（`review_item`）、幂等行（`idempotency_key`）。
- 其余表：断言**零写入**（前后行数相等且无新增主键）。
- 响应侧保留**完整键集**与嵌套行结果（`batch_id/status/format/mode/rows_total/counts{created,duplicate_skipped,version_added,suspect_review,rejected,warning}/rows[]`，其中每行保留 `row_no/action/records/skipped/warnings/errors` 原样），**不为可比而删 warning/错误/字段**。

### 4.2 路径表（HTTP 处理栈模拟不可缺席）

| 路径 | 说明 |
| --- | --- |
| `core-CSV` | `app.core.importer.handle_import(fmt="csv", mode=…)`，进程内调用 |
| `core-JSON` | `handle_import(fmt="json", mode=…)`，进程内调用 |
| `tc-CSV` | Flask `test_client().post("/api/imports?format=csv&mode=…")` —— **HTTP 处理栈模拟，不是 loopback 真实 HTTP** |
| `tc-JSON` | 同上，`format=json` |

### 4.3 case → 路径 → 字段集 → 期望

| # | case | core-CSV | core-JSON | tc-CSV | tc-JSON | 期望（字段集见 4.1） |
| --- | --- | --- | --- | --- | --- | --- |
| C1 | 成功且带 `observed_at` | 执行 | 执行 | 执行 | 执行 | 201/`committed`；`observed_at_source='source'` 且值等于输入；`counts.created=1`；无 warning；`supply_offer/cost_item/gate_review` 行数不变 |
| C2 | 成功且不带 `observed_at` | 执行 | 执行 | 执行 | 执行 | 201/`committed`；`observed_at_source='import_time'`（DB 侧时间，双跑需归一）；其余同 C1 |
| C3 | 非法：`synthetic` + 真实 bili URL | 执行 | 执行 | 执行 | 执行 | 422 + `status='rejected'`；**仅非法行**有 `import_row_result(action='rejected', reason_code='V4', reason_detail='synthetic 行的 URL 必须为空或示例域')`；业务表零行 |
| C4 | 非法：title **301 字** | 执行 | 执行 | 执行 | 执行 | 行级拒绝、**不截断**；公共规则依据 **CONTRACT §4.2 V2**（`title` 去空白后非空且 ≤300 字符，见 `CONTRACT.md:84/428/472`）；实现路径 `validate_row` → `importer.py:228 _check_len(get("title"), "title", 300, errors)`，`_check_len`（`:214–217`）写入 **`V12`**"长度超过 300 字符" ⇒ **实测 reason_code 预期为 `V12`，与契约 V2 的对应关系列为待确认口径（不改实现、不判缺陷）** |
| C5 | 重复（同 body 重放） | 执行 | 执行 | 执行 | 执行 | 201/`committed`；`duplicate_skipped=1`；候选/需求/证据行数不变；仅命中行 `last_seen_at` 刷新 |
| C6 | A→B→A（同身份、内容变化） | 执行 | 执行 | 执行 | 执行 | 首次 A：`created`；B：`version_added=1`、v1 `superseded_by`=v2；再次 A：`duplicate_skipped=1`、**不新增行/版本**、仅旧行 `last_seen_at` 刷新、`evidence` 与 `invalidated_at/invalid_reason` 不变；`gate_review` 零新增 |
| C7 | `atomic` 合法+非法混合 | 执行 | 执行 | 执行 | 执行 | **业务全不落行**；`payload.status='rejected'`；`rows_total=2`；`counts.rejected` = **实际错误行数（=1）**；**只有非法行**有 `import_row_result` 条目与 `payload.rows` 条目（合法行**无** reason/result）；`import_batch.error_summary` 记"N 行校验失败（atomic 未写入业务数据）"（依据 `importer.py:967–991`） |
| C8 | `partial` 合法+非法混合 | 执行 | 执行 | 执行 | 执行 | 合法行落库、非法行只留原因；**`payload.status` 与 `import_batch.status = 'partial_committed'`**、**`run_record.status = 'partial'`**（依据 `importer.py:932/943`）；`counts.created=1`、`counts.rejected=1`、`rows_total=2`；仅错误行有 reason |
| C9 | **带 supply + cost 的完整导入正例** | 执行 | 执行 | 执行 | 执行 | 使用既有完整导入样例（`title,data_origin,demand_source,demand_url,demand_excerpt,demand_kind,supply_*` 全列）：201/`committed`；`candidate`、`demand_signal`、`evidence`、`supply_offer` 按样例产生；`cost_item` 按既有 V17 规则产生（不因本补证另立规则）；`gate_review` 等其余表零新增 |
| C10 | **warning 正例**（无需求组行提供 `observed_at`，契约 V23） | 执行 | 执行 | 执行 | 执行 | 201；`counts.warning=1`；`import_row_result(action='warning', reason_code='V23')`；业务行按该行内容落库；不改门槛/证据效力 |

> 说明：C9/C10 采用**既有完整导入样例**（不新造框架、不加依赖）；若执行批取不到合适样例，该项按"未执行"如实标注，**不得**以需求单样例宣称所有公共输入等价。

### 4.4 归一规则（**执行前须冻结**，本批只列规则）

1. **进程内固定 clock/ID，不改源文件**。仅 patch `util` 本体不足：各消费模块在 import 时已绑定别名（绑定表见 [22_matrix_grounding.txt](<../../tests/acceptance/_tmp/s3_public_compat_v1/run_20261016_133627_compat1/evidence/22_matrix_grounding.txt>)），**必须逐模块 patch 其模块属性**：
   - `now_utc`：`importer`、`db`、`state`、`gates`、`evidence`、`costs`、`supplies`、`reviews`、`idempotency`、`wiring`、`routes`、`candidates`、`drafts`、`feedback`
   - `today_local`：`importer`、`reviews`、`wiring`
   - `slug_id`：`importer`、`gates`、`evidence`、`costs`、`supplies`、`reviews`、`idempotency`、`wiring`、`drafts`、`feedback`
   - **每步 clock 推进**：两侧共用同一脚本化时钟（例如第 k 步 = `BASE + k*60s`），并记录每步实际时间戳；ID 用 `(prefix, 序号)` 确定性生成器（保留 `c_/d_/e_/ib_/rr_/r_/ik_/g_/sp_/ci_` 前缀），如仍残留随机源则同样逐模块 patch 并记录位置。
2. **若改用 ID 映射**：保存**每表 old/new 主键**，并校验 FK、响应体、`notes` 内 ID 引用的**一一对应**；**不得整列删除**。
3. **业务时间语义不得归一掉**：`observed_at`、`observed_at_source`、`last_seen_at` 的刷新事实、`status_updated_at` 等一律逐值比较。
4. **非业务时间白名单（精确字段名，不写"等"）**：仅 `run_record.started_at`、`run_record.finished_at`、`import_batch.created_at`、`import_batch.finished_at` 四项可按脚本化时钟归一；**除此之外所有时间列必须逐值相等**。
5. **绝不归一掉**：`identity_key`、`content_hash`、`status`/`status_reason`、计数、warning（code+reason）、rejected/失败 reason（code+detail）。
6. 原始结果保留（原文 + 归一后副本并存）；差分不等即**如实 FAIL**，不改被测实现、不放宽断言；禁止用宽泛正则抹平时间戳。
7. **环境版本必须实读日志**：执行批每轮附 `python -V`、`flask.__version__`、`sqlite3.sqlite_version` 的真实输出（本批已给出可用版本实例：venv python 3.12.14 / Flask 3.1.3 / sqlite3 3.53.1），不从 `allowCommands` 或历史推断。

### 4.5 能否启动执行批

前置：① 你明确授权"可运行应用测试/HTTP 栈"的批次（本批禁止）；② 冻结上述归一规则与 patch 落点；③ 新建唯一 run 目录；④ 依赖仅标准库 + 既有 Flask/sqlite，不新增。满足后按 4.3 逐 case 执行并给真实 exit。

## 5. 未执行 / 未核 / 限制（不标 PASS）

- 本批**未**执行差分、**未**启动服务、**未**运行 `tests/**`、**未**做 HTTP/E2E/217 回归 → **无兼容性结论**。
- 21 号 diff 为**原始 unified diff**（供逐 hunk 读），本报告**未**对其作"已解释"判定；token 事实仅作 token 存在性记录。
- C4 的 `V12`（实现码）与契约 `V2`（规则）对应关系列为**待确认口径**；本批不改实现、不判缺陷。
- C9/C10 若执行批取不到合适既有样例，须标"未执行"，不得以单一样例外推。
- 失败史如上：GBK 首轮与 venv 首次尝试均**无原件留存**，已撤回"原件已留档"表述。
- 本批只新增本报告、21/22 号证据与 `tools/compat_evidence_v2.py`；未写 v1/v2/v3/v5 与历史归档，未改旧树/业务库/台账/契约，未导入被核对树（无 pycache 产生）。

## 6. 第 2 批实跑记录（双镜像逐字段差分，2026-10-19）

运行目录：[run_20261019_222804_compat2](<../../tests/acceptance/_tmp/s3_public_compat_v1/run_20261019_222804_compat2>)　冻结采用确定性依赖，无事后时间删列/无 ID 映射。

### 6.1 两侧镜像与资格核对

| 侧 | 来源 | 文件 | 关键哈希（真复算） | 结果 |
| --- | --- | --- | --- | --- |
| before（修前） | `tests/api/_tmp/import_history_fix_v1/run_20261015_212020_704683a1/mirror` | 37 | importer `42F1F8FC…E8946` | PASS |
| after（接线后） | 当前 live `app/**` + `requirements.txt` | 38 | importer `a11eaf4d…`、wiring `bafcf397…` | PASS |

- 复制后**逐件 parity**：两侧 missing=0 / mismatched=0；与资格 manifest 对照 only_expected=0 / only_actual=0 / changed=0。
- 遍历：显式目录名剪枝（before 0、after 4 目录）、**reparse/junction 命中 0**、异常 0。
- 证据：[01_dual_mirrors.json](<../../tests/acceptance/_tmp/s3_public_compat_v1/run_20261019_222804_compat2/evidence/01_dual_mirrors.json>)、[01_dual_mirrors_cmd.log](<../../tests/acceptance/_tmp/s3_public_compat_v1/run_20261019_222804_compat2/evidence/01_dual_mirrors_cmd.log>)（**exit=0**）。

### 6.2 归一策略（执行前冻结）

[inputs/normalization_policy.json](<../../tests/acceptance/_tmp/s3_public_compat_v1/run_20261019_222804_compat2/inputs/normalization_policy.json>) 先落盘：clock `BASE=2026-06-01T00:00:00Z`、**每操作推进 60s**；`slug_id(prefix) -> prefix_<16 hex>` 按 **prefix 计数**；patch 点逐模块（含 `importer/db/state/gates/evidence/costs/supplies/reviews/idempotency/wiring/routes/...` 的已绑定别名，`today_local` 固定 `2026-06-01`）；非业务时间白名单仅 `run_record.started_at/finished_at`、`import_batch.created_at/finished_at`；**不使用 ID 映射**；`observed_at/source`、`last_seen` 刷新、`status_updated_at`、身份键、content_hash、计数、warning/reason 一律不裁。

### 6.3 执行结果（40 对 = C1–C10 × 4 路径）

| 批次 | 对数 | 结果 | 真实 exit | 日志 |
| --- | --- | --- | --- | --- |
| C1–C4 | 16 | **16 PASS**，两侧断言全过 | **0** | [10_c1_4_cmd.log](<../../tests/acceptance/_tmp/s3_public_compat_v1/run_20261019_222804_compat2/evidence/10_c1_4_cmd.log>) |
| C5–C8 | 16 | **16 PASS** | **0** | [11_c5_10_cmd.log](<../../tests/acceptance/_tmp/s3_public_compat_v1/run_20261019_222804_compat2/evidence/11_c5_10_cmd.log>) |
| C9–C10（修正探针后重跑） | 8 | **8 PASS** | **0** | [13_c9_10_retry_cmd.log](<../../tests/acceptance/_tmp/s3_public_compat_v1/run_20261019_222804_compat2/evidence/13_c9_10_retry_cmd.log>) |
| 合计 | **40** | **40 PASS / 0 FAIL / 0 UNEXECUTED**，**total_diffs=0** | — | [40_summary_all.md](<../../tests/acceptance/_tmp/s3_public_compat_v1/run_20261019_222804_compat2/evidence/40_summary_all.md>) |

- 每对均有：原始输入（`inputs/cases.json`、`inputs/c9_sample.csv`）、两侧每步响应与**每步全列 DB 快照**（`results/<label>/<side>_<case>_<path>.json`，含全部表 `columns`+`rows` 与 `PRAGMA foreign_key_check`）、差分记录（`diffs/<label>/<case>_<path>.json`）、每侧命令日志（`evidence/runs/<label>/...`，含 cmd/cwd/time/stdout/stderr/真实 exit）。
- 关键语义两侧实测：C7 `rows_total=2`、`counts.rejected=1`、仅 `row_no=2` 有 rejected 记录、业务表零行；C8 `payload.status` 与 `import_batch.status = partial_committed`、`run_record.status = partial`；C4 两侧实测拒绝码均为 `V12`（契约 `V2` 规则的对应问题仍按既存口径另列，**不据此声明契约全过**）。

### 6.4 探针修正史（原件保留，未覆盖）

1. C9 的 CSV 两路首轮 `exit=2`：`raw_file` 误按镜像根解析（`FileNotFoundError`）→ 改为相对 spec 上级目录；两侧同因，非实现差异。
2. C10 期望写错：实际 `counts.warning=0` 但存在 `V23` warning 行（两侧一致）→ 断言改为"V23 行恰 1 条 + `counts.warning=0` + `import_batch=committed`"，并在证据中记录该观察。
3. `run_all` 输出路径加 label 级目录，避免重跑覆盖旧结果；两个工具（`verify_mirrors_after`、`frozen_live`、`guard_delta`）的 Python 3.10 f-string 反斜杠语法错误 → 修复，失败日志另存 `*_attempt*.log`。

### 6.5 运行后守护

| 项 | 结果 | 证据 |
| --- | --- | --- |
| 两侧镜像复算 | missing=0 / mismatched=0 / extra=0（**exit=0**） | [31_mirrors_after_cmd.log](<../../tests/acceptance/_tmp/s3_public_compat_v1/run_20261019_222804_compat2/evidence/31_mirrors_after_cmd.log>) |
| 业务库 | `e073f828…4eb85` match=True，**wal/shm 不存在** | [32_guard_after_cmd.log](<../../tests/acceptance/_tmp/s3_public_compat_v1/run_20261019_222804_compat2/evidence/32_guard_after_cmd.log>) |
| 四文档 | 与资格批次记录一致（PRODUCT `1639891d…`、PLAN `0a50d317…`、PROGRESS `1df8c16c…`、CONTRACT `826c24cc…`） | 同上 |
| live 枚举 canonical | count=87 sha256 `4bc5a95f…`；相对基线**恰 2 个具名新增**：`docs/validation/S3_OFFLINE_WIRING_ACCEPTANCE.md`、`docs/validation/S3_PUBLIC_PATH_COMPATIBILITY.md`，**无未解释漂移** | [33_guard_delta_cmd.log](<../../tests/acceptance/_tmp/s3_public_compat_v1/run_20261019_222804_compat2/evidence/33_guard_delta_cmd.log>) |
| 冻结 live 五件 | 5/5 PASS（**exit=0**） | [30_frozen_live_cmd.log](<../../tests/acceptance/_tmp/s3_public_compat_v1/run_20261019_222804_compat2/evidence/30_frozen_live_cmd.log>) |
| 证据文本 | 125 件，UTF-8 无 BOM/LF，读回 **exit=0** | [35_evidence_check_cmd.log](<../../tests/acceptance/_tmp/s3_public_compat_v1/run_20261019_222804_compat2/evidence/35_evidence_check_cmd.log>) |

### 6.6 结论与不外推

- 在**本矩阵覆盖范围内**（C1–C10 × core-CSV / core-JSON / tc-CSV / tc-JSON，默认参数省略 `run_source_id`/`internal_observation`，同一字节输入、确定性 clock/ID）**修前与接线后逐字段等价**：40/40 对、total_diffs=0、两侧断言全过。
- `tc-*` 为 **Flask test_client 的 HTTP 处理栈模拟**，**不是** loopback 真实 HTTP；本批**未起任何服务/端口**。
- **不外推**：不声明所有公共输入等价、不声明 S3/S4 阶段完成；`V12`（实现码）与契约 `V2` 的对应问题仍是既存口径。
- 未改任何业务实现；仅在本 scope 新增工具/证据与本节记录；旧 20/21/22 号原件与历史失败均未覆盖。

## 7. 受控重跑（第 2 批修订，2026-10-19）

运行目录：[run_20261019_224713_compat3](<../../tests/acceptance/_tmp/s3_public_compat_v1/run_20261019_224713_compat3>)。compat2 全体原件未动；工具全部另存 v2 命名；本节为修订结论，**§6 保留为首轮历史，且不作为"保护通过"依据**。

### 7.1 对首轮 §6 的纠错

1. `11_c5_10_cmd.log` 的**整体真实 exit=1**（24 对：18 PASS / 4 FAIL / 2 UNEXECUTED）；§6.3 曾误列为 0。C5–C8 每对子进程 exit=0 只属**逐对**信息。
2. 首轮 `32_guard_after_cmd.log` **整体 exit=1 且缺 baseline**（compat1 无 `02_guard_before.json` → FileNotFound），故首轮**保护未通过**，属方法缺陷；§6 的相关表述撤回。
3. 是**三个**工具（`verify_mirrors_after` / `frozen_live` / `guard_delta`），不是两个。
4. §6 索引中的 `<label>` 是模板；首轮真实文件在 `results/<side>_<case>_<path>.json`、`diffs/<case>_<path>.json`（C1–C8）与 `diffs/c9_10_retry/`（C9/C10）；**最终真实路径索引见 §7.5**。
5. C10 的 `counts.warning=0` 但存在 `V23` warning 行，是**两侧一致的既存观察**；首轮修改预期不等于"原语义预期全部通过"。
6. 本节的兼容性结论与契约结论**分列**：只声明本矩阵默认路径等价，不声明契约 V2/V12 口径已解决。

### 7.2 本次运行前/后保护（新鲜同口径，非旧常量）

- **运行前**：业务库实际 `sha256=e073f828cf0f30d6206361bba3a729826be096be3308f5a5dc204406dae4eb85`，WAL/SHM 均不存在；四保护文档 hash 逐一记录；被核域（`app/**`+`tests/**`+`docs/**`+根 `*.md`，剪枝 `_tmp`/缓存/junction，**并排除本任务允许变更的报告文件**）共 **86 件**、逐件 `(path,bytes,sha256)`、域 digest `19396ef6…`；报告文件单独记录 `6a40ee42…`。[01_protection_pre.json](<../../tests/acceptance/_tmp/s3_public_compat_v1/run_20261019_224713_compat3/evidence/01_protection_pre.json>) / [01_protection_pre_cmd.log](<../../tests/acceptance/_tmp/s3_public_compat_v1/run_20261019_224713_compat3/evidence/01_protection_pre_cmd.log>)（**exit=0**）。
- **运行后**：同口径重拍并**逐文件比对**：missing=0 / added=0 / content_changed=0，业务库与四文档不变、两侧源与镜像逐件不变 → `protection_verdict=PASS`。[20_protection_post.json](<../../tests/acceptance/_tmp/s3_public_compat_v1/run_20261019_224713_compat3/evidence/20_protection_post.json>) / [20_protection_post_cmd.log](<../../tests/acceptance/_tmp/s3_public_compat_v1/run_20261019_224713_compat3/evidence/20_protection_post_cmd.log>)（**exit=0**）。
- **源侧资格（跑前再核）**：before/after 与资格 manifest 逐件一致（only_expected=0 / only_actual=0 / changed=0）；候选 importer `42F1F8FC…E8946`、live importer `a11eaf4d…`、wiring `bafcf397…` 真复算 PASS → [02_mirrors_v2_cmd.log](<../../tests/acceptance/_tmp/s3_public_compat_v1/run_20261019_224713_compat3/evidence/02_mirrors_v2_cmd.log>)（**exit=0**）。

### 7.3 harness v2 收紧清单（已落实）

policy 常量核验（BASE/步长/hex 长度）；**create_app 之前**断言 `db_path` 在新 run 内且 fresh；`app/importer/config_ROOT` 用 resolve 的**祖孙关系**判定（非字符串子串）；patch 仅作用于**已存在**函数，仅 before 侧缺 `app.sources.wiring` 豁免、其它 import 异常**记录并失败**；记录实际 patch 表；每 case 建 schema 后、首操作前存 `initial_snapshot`；每步全列快照且**每侧 FK 必须为空**（违反即 exit 2）；request body 字节落 `inputs/bodies/<sha>.bin` 并记 `body_sha`，tc 另记 `raw_response_sha256`。

### 7.4 结果（40/40）

- 36 对在 `run40` 批次；C6 的 4 对在 `c6_retry`（首轮 C6 的 2 类失败均为**我方断言口径错误**：`row_nonnull` 用空 `where` 命中两行证据只失效其一；`review_item` 是失效操作的合法派生副作用未列入 `except`。修正后 C6 两侧各 20/20 通过，首轮原件保留于 `run40` 批次）。
- 汇总：**40/40 PASS，0 FAIL，0 UNEXECUTED，total_diffs=0，FK 问题 0**；负对照 run40 **2/2**、c6_retry **2/2**（纯内存改 `counts.created` 或 `observed_at` 后 `diff_tree` 均命中对应路径）。
- 关键断言（两侧各自）：C2 缺省时间值 = **本步固定 clock** 且 `observed_at_source='import_time'`；C5 命中 demand 行仅 `last_seen_at` 变为 step1 clock；C6 失效后 `invalidated_at` 非空且 `invalid_reason` 为输入原文、证据行 step3→4 **逐值不变**、v1 仅 `last_seen_at`→step4 clock、v2 **整行不变**、`review_item`/`gate_review` 在重放中无新增；C7 业务五表零行且仅 `row_no=2` rejected(V4)；C8 `partial_committed`/`partial`；C9 `cost_item=10`（样例 9 个成本列 + `manual_minutes`）；C10 恰 1 条 V23 warning 行且 `counts.warning=0`（既存观察）。
- 真实 exit：`10_run40_cmd.log` **exit=1**（36/40，C6 首轮口径失败，**属实保留**）、`11_c6_retry_cmd.log` **exit=0**、`30_summary_final_cmd.log` **exit=0**、`31_evidence_check_cmd.log` **exit=0**（105 件证据 UTF-8 无 BOM/LF）。

### 7.5 最终 40 对索引（真实文件）

每对的 before/after 结果、两侧日志、diff 的**真实路径**见 [40_summary_final.md](<../../tests/acceptance/_tmp/s3_public_compat_v1/run_20261019_224713_compat3/evidence/40_summary_final.md>)；机器可读版 [40_summary_final.json](<../../tests/acceptance/_tmp/s3_public_compat_v1/run_20261019_224713_compat3/evidence/40_summary_final.json>)（含 `result_before/result_after/log_before/log_after/diff_file` 字段）。

### 7.6 结论与限制

- 仅本矩阵（C1–C10 × 4 路径、默认省略 `run_source_id`/`internal_observation`、同一字节输入 + 确定性 clock/ID）内**逐字段等价**；不外推其它输入、参数组合或阶段完成。
- `tc-*` 为 **Flask test_client 处理栈模拟**，本批**未起任何服务/端口**。
- 契约结论分列：`V12` 为实现码、`V2` 为契约规则，二者对应仍属**既存口径**，本批不判缺陷、不据此声明契约全过。
- 首轮 §6 的错误已按 §7.1 纠正；§6 不作为保护通过依据。首轮 C6 的失败属于探针口径问题（非实现差异，两侧 `diffs=0`）。

### 7.7 最终离线补核（只读审计，2026-10-19）

- **性质**：本节**不是新功能实跑**；主要 40 对已在前述批次实跑，这里只**只读复核现存结果**——未启动 app/HTTP、未创建或修改 DB、未重跑任何 case。
- **输入**：[40_summary_final.json](<../../tests/acceptance/_tmp/s3_public_compat_v1/run_20261019_224713_compat3/evidence/40_summary_final.json>)（40 对真实路径索引；C6 取 `c6_retry`）。审计工具 [final_audit_v1.py](<../../tests/acceptance/_tmp/s3_public_compat_v1/run_20261019_224713_compat3/tools/final_audit_v1.py>)，输出 [50_final_audit.json](<../../tests/acceptance/_tmp/s3_public_compat_v1/run_20261019_224713_compat3/evidence/50_final_audit.json>) 与 [50_final_audit_cmd.log](<../../tests/acceptance/_tmp/s3_public_compat_v1/run_20261019_224713_compat3/evidence/50_final_audit_cmd.log>)，**exit=0**，`checks=75 passed=75 failed=0 verdict=PASS readback_ok=True`。
- **A 结构复核（40/40 PASS）**：独立（不复用 runner 的）比较每对 `initial_snapshot` 与全部 `steps` 完整结构 → `structure_diff_count=0`；每侧 `initial` 与**每一步** `fk_check` 恒空；元数据归属：`app_file/importer_file/config.ROOT` 分别落在 `<run>/before`、`<run>/after` 镜像内，**DB 按设计位于 `<run>/dbs`（不在镜像内）**且文件名含侧别；索引中的 `result_before/result_after/log_before/log_after/diff_file` **均真实存在**；两侧结果文件 sha256 已逐对记录。
- **B 严格行级断言（32/32 PASS）**：C5 每侧按 `native_id` 精确选**唯一** demand 行 → `changed_keys` **恰为 `{last_seen_at}`** 且新值**等于 step1.clock**；C6 每侧 v1 同样恰变 `last_seen_at` 且值 = **step4.clock**、v2 **整行不变**；用 `steps[3].evidence_id` **精确定位**失效目标 → 该行 `invalidated_at` 非 NULL、`invalid_reason` 与输入原文**逐字一致**、step3→step4 **全部 evidence 行逐值相等**。
- **C 纯内存负对照（3/3 PASS）**：把 C5 的 `last_seen_at` 恢复旧值 → 刷新检查**检出失败**；把 C6 目标 `invalidated_at` 置 NULL → 目标检查**检出失败**；选真实存在的 `demand_signal.observed_at` 列改其值 → 精确命中路径 `db.demand_signal.rows[0].observed_at`。早先的 candidate 额外键负对照仅作历史保留，**不再称其验证了真实 DB 列值突变**。
- **审计首轮勘误（保留原件）**：attempt1 曾把"DB 必须在镜像内"当作路径判据，导致 40 项 A 全判失败；根因是**审计规则写错**（DB 设计上在 `<run>/dbs`），不是结果差异；修正后 75/75 通过，原始结果未改动。失败件保留为 `50_final_audit_attempt1_db_rule.json` / `50_final_audit_attempt1_db_rule_cmd.log`。
- **证据数量勘误**：应为 **109 件**（以 `31_evidence_check_cmd.log` 为准）；早先记录的 105 为历史值，**保留不抹除**。
- **存档边界（如实）**：HTTP 原始 **JSON payload 完整保留**（`steps[].payload`）；**raw HTTP body 仅记录 sha（`raw_response_sha256`），没有独立字节文件**，不回填所谓原始 body。
- **结论分列**：C10 的 `counts.warning=0` 与 V23 行并存仍是**两侧一致既存观察**；契约 `V12`（实现码）与 `V2`（规则）的对应仍属**既存口径**——二者与本节"有限 case 默认路径等价"的兼容性结论分列，本补核不改变任何一方。



