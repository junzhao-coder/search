# S3 real 失败路径加固 · 独立复核（427 版 vs 已存 388 修前副本）

> 复核对象：`app/sources/real_link.py`（**427 行**，sha256 `1bf597706f7995a7473d3da4bca535fdda53ce4cc7a3868b56fe9b1892af55ab`，与 B 宣称 `1BF59770…` 一致）与 `tests/sources/test_real_link.py`（**423 行**，sha256 `0ede6cca12c4b96950a6e340cc1a51ab78542113e4b47c52f3c70bf3d9fbb908`）。
> 修前副本：`tests/sources/_tmp/real_hardening_v1/before_20261020_160909_rev8/real_link.py`（**388 行**，sha256 `8fbe34376b7f9e8e874cede03f8f90abc7eca4bc12155af3bad7db66a2e55470`，与 `01_hashes.txt` 记录一致；同目录 `test_real_link.py` 313 行 sha `6f60c7de…`）。
> 冻结三文件（未改）：`wiring.py` `bafcf397…`、`bilibili_view.py` `b0dc0ced…`、`importer.py` `a11eaf4d…`；业务库 `instance/app.db` `e073f828…`。
> 复核者：独立执行者 A（实现者 B），任务 `task-e003bd06d975dc9dca85cc8d7700912d`；复核时点 2026-10-20 18:46–18:53 +08:00。
> 性质：**隔离镜像 + 离线差分探针 + 真实 DB 副本只读回溯**。**未联网、未启动真实端口、未改 `app/**`/`tests/**`/被验文件/业务库**。
> 结论：**需修订（不建议以当前 427 版放行 S3 real 失败路径加固）**。确认修好 5 项（C4/E2/E2b/E3/A2-numeric），但 **3 项相对修前 388 回归**（A1 索引归属、B1/B2 `record_failure` 二次调用）与 **1 项两版仍错**（A2 索引归属）；详见 §3/§4。**不宣称 S3 完成**。

## 0. 运行目录与证据

- 唯一 run：`tests/acceptance/_tmp/s3_real_hardening_verify_v1/run_20261020_184650_hardverify/`
- 日志格式（`tools/run_and_log_utf8.py`）：`label/cmd/cwd/start_utc/exit/stdout/stderr`，Python `subprocess.run(..., encoding='utf-8')`，日志文件 **UTF-8 无 BOM**；每条命令的真实 exit 见日志，文件名见 §9。
- 关键证据：[02_path_probe.json](<../../tests/acceptance/_tmp/s3_real_hardening_verify_v1/run_20261020_184650_hardverify/evidence/02_path_probe.json>)、[04_test_real_link.log](<../../tests/acceptance/_tmp/s3_real_hardening_verify_v1/run_20261020_184650_hardverify/evidence/04_test_real_link.log>)、[05_discover.log](<../../tests/acceptance/_tmp/s3_real_hardening_verify_v1/run_20261020_184650_hardverify/evidence/05_discover.log>)、[06_probe_diff.json](<../../tests/acceptance/_tmp/s3_real_hardening_verify_v1/run_20261020_184650_hardverify/evidence/06_probe_diff.json>)、[07_probe_detail.json](<../../tests/acceptance/_tmp/s3_real_hardening_verify_v1/run_20261020_184650_hardverify/evidence/07_probe_detail.json>)、[08_guard_after.json](<../../tests/acceptance/_tmp/s3_real_hardening_verify_v1/run_20261020_184650_hardverify/evidence/08_guard_after.json>)、[08_evidence_readback.txt](<../../tests/acceptance/_tmp/s3_real_hardening_verify_v1/run_20261020_184650_hardverify/evidence/08_evidence_readback.txt>)。

## 1. 镜像与模块来源实证

- 镜像：live `app/**`+`tests/**`+`requirements.txt` → `<run>/mirror/`（排除 `__pycache__`/`_tmp`/`_snapshots`/`.venv`/reparse；**77 件**、逐件 parity **mismatched=0 / extra=0**）→ [01_mirror.json](<../../tests/acceptance/_tmp/s3_real_hardening_verify_v1/run_20261020_184650_hardverify/evidence/01_mirror.json>)（**exit=0**）。
- 模块来源（cwd=mirror、PYTHONPATH=mirror、PYTHONDONTWRITEBYTECODE=1、live venv python 3.12.14）：**12/12 checks + 2/2 hash 校验 PASS**——`app.sources.real_link`/`bilibili_view`/`wiring`/`app.core.importer`/`tests.sources.test_real_link` 全在镜像内；镜像内 real_link 427 行/`1bf59770…`、test 423 行/`0ede6cca…` 与 live 一致 → [02_path_probe.json](<../../tests/acceptance/_tmp/s3_real_hardening_verify_v1/run_20261020_184650_hardverify/evidence/02_path_probe.json>)（**exit=0**）。
- 修前副本复制进镜像为 `app/sources/real_link_prefix.py`，复制后校验 **388 行/`8fbe3437…`**（[03_copy_pre388.log](<../../tests/acceptance/_tmp/s3_real_hardening_verify_v1/run_20261020_184650_hardverify/evidence/03_copy_pre388.log>)，**exit=0**）。

## 2. 两轮测试（真实 exit，UTF-8 可读日志）

| 轮次 | 命令（cwd=mirror） | 结果 | 对照 B 宣称 |
| --- | --- | --- | --- |
| real_link 单测 | `-m tests.sources.test_real_link` | **Ran 27 tests — OK，exit=0**（`start_utc=2026-10-20T10:49:32Z`） | 27 ✓ |
| 完整回归 | `-m unittest discover -s tests -t .` | **Ran 280 tests — OK，exit=0**（42.605s） | 280 ✓ |

- B 的 hard3 证据：`10_module_tests.txt` 为 UTF-8 可读（`Ran 27 tests … OK`）；**`11_discover.txt` 不是 UTF-8**（严格解码在 byte 13 失败：`invalid continuation byte`）→ B 的 "282/280" 结论**无法由该文件独立核对**；本次独立复跑得到 **27/280 且 exit=0**（与 `01_hashes.txt` 内记录的 280 一致）。上下文所称 B 宣称 **27/280** 与实测一致。

## 3. 当前 427 版 vs 修前 388 版：同组独立断言矩阵（18 项）

- 探针：[06_probe_diff.json](<../../tests/acceptance/_tmp/s3_real_hardening_verify_v1/run_20261020_184650_hardverify/evidence/06_probe_diff.json>)（**exit=0**）；FakeTransport 可控 outcome + 隔离 sqlite DB；同一断言函数分别对 `current`（427）与 `pre`（388）执行。
- 汇总：当前 **14/18 PASS**、修前 **12/18 PASS**；**修前 FAIL / 当前 PASS 5 项**；**修前 PASS / 当前 FAIL（回归）3 项**；**两版均 FAIL 1 项**；两者均 PASS 9 项。

| # | 断言 | 当前 427 | 修前 388 | 最小复现输入 |
| --- | --- | --- | --- | --- |
| A1 | 同 bvid×3，中间 fetch 失败（ok/rate_limited/ok）→ 每 index 归属 | **FAIL**（`[T,F],[T,F],[F,T]`，应 `[T,F],[F,T],[T,F]`） | PASS（`[T,F],[F,T],[T,F]`） | bvids=[BV,BV,BV]；outcomes=[ok,rate_limited,ok]；budget=3 |
| A1n | A1 的数值不变量 | PASS | PASS | — |
| A2 | 同 bvid×2，两次 fetch 成功、第 1 次导入返回 422、第 2 次成功 → 每 index 归属 | **FAIL**（`[T,F],[F,T]`，应 `[F,T],[T,F]`） | **FAIL**（`[T,T]`，无导入对账） | bvids=[BV,BV]；handle_import 第 1 次→422、第 2 次真实导入 |
| A2n | A2 的数值不变量 | PASS（succeeded=1=imported） | **FAIL**（succeeded=2≠imported=1） | — |
| B1 | 非成功码分支 `record_failure` 自身抛 `sqlite3.OperationalError`：调用次数/是否冒泡 | **FAIL**（调用 **2** 次；第 2 次成功 → 异常被吞、返回 failed；run_record 原因被改成"导入SQL异常"） | PASS（调用 1 次，异常冒泡，无 run_record） | 单 target；handle_import→(422)；record_failure 第 1 次抛 sqlite3 |
| B2 | 同上但 `record_failure` 每次都抛：不递归/单次尝试 | **FAIL**（2 次调用后冒泡） | PASS（1 次调用后冒泡） | 同上，record_failure 每次抛 |
| C1 | transport 失败 → 不报 ok、有 failed run | PASS | PASS | 单 target；outcome=rate_limited |
| C2 | 映射失败（`_build_real_row` 抛 AppError）→ 不报 ok | PASS | PASS | patch `_build_real_row` |
| C3 | `handle_import` 返回 422 → 不报 ok | PASS | PASS | patch 返回 `({"rows":[]},422,None)` |
| C4 | `handle_import` 抛 `sqlite3.OperationalError` → 落 failed 不冒泡 | **PASS**（落 failed run + failed_imports） | **FAIL**（异常穿透） | patch 抛 sqlite3 |
| D1 | budget=1、4 个唯一目标 → 未请求全 unrequested、无伪造 failed run | PASS | PASS | budget=1；4 unique targets |
| D2 | 5s 间隔等待跨越 deadline → 未执行位置 unrequested、无伪造 failed run | PASS | PASS | 2 targets；clock 在 5.0s sleep 时 +700s |
| E1 | remaining=0.2 → 默认 transport timeout≤remaining | PASS（0.2） | PASS（0.2） | timeout_seconds=0.2；默认 transport |
| E2 | remaining=0.0006 → **无 0.001 下限** | **PASS**（timeout=0.0006） | **FAIL**（0.001 > remaining） | timeout_seconds=0.0006 |
| E2b | 精确 remaining=0.0005 → 不超过剩余 | **PASS**（不调用；浮点 remaining=0.000499999999988 < 阈值，安全侧） | **FAIL**（调用 0.001 > remaining） | timeout_seconds=0.0005 |
| E3 | remaining=0.0004 < 阈值 → **不调用 transport** | **PASS**（calls=0，落 failed） | **FAIL**（calls=1，timeout 0.001） | timeout_seconds=0.0004 |
| G | 非法 cfg → 422 且 0 请求 | PASS | PASS | cfg={"tz_offset_hours":99,…} |
| H | `_audit` 写失败 → 异常冒泡、不递归记 run | PASS | PASS | patch `_audit`→OSError |

## 4. 定向结论（a）–（f）

### (a) 同 bvid 多位置的 target_summary index 归属 —— **仍复现（A1 为回归、A2 两版均错）**
- A1（先失败后成功）：当前得到 index0 succeeded、**index1 succeeded（错，实际该位置 fetch=rate_limited）**、index2 failed（错，实际成功）；修前 388 为 `[T,F],[F,T],[T,F]`（正确）。
- A2（首个导入失败、第二个成功）：当前 index0 succeeded（错，其导入被 422 拒绝）、index1 failed（错，实际成功）；修前 `[T,T]` 也不对（无导入对账）。
- 根因（当前 427）：`real_link.py:390-408` 用 `imported_q[bvid]` **按 bvid 的 FIFO 队列**在 `target_summary` 顺序上消费，未携带"该导入来自哪个输入位置"；因此同 bvid 的失败位置会消费后来位置的成功导入。最小复现见 §3 A1/A2。
- 影响：`target_summary`/`summary_counts` 的逐目标语义错配（数值不变量恰好看不出，见 (f)）。

### (b) 非成功码分支 `record_failure` 自身抛 `sqlite3.Error`：是否二次记账/冒泡 —— **仍复现（B1/B2 均为回归）**
- 代码结构：`real_link.py:357-362` 非成功码分支在 `try` 内调用 `wiring.record_failure`，其抛出的 `sqlite3.Error` 被 `:372` 的 `except sqlite3.Error` 捕获 → 追加"导入SQL异常"并**再调用一次** `record_failure`。
- 实测 B1：`record_failure` 第 1 次抛 → 第 2 次成功 ⇒ **调用 2 次、异常未冒泡、run_record 1 条且 error_summary 被改写为"导入SQL异常"**（原始"导入返回非成功码"丢失）；B2（每次都抛）：**调用 2 次后冒泡**（不递归，但多一次尝试）。
- 修前 388：**调用 1 次、异常直接冒泡、无 run_record**（符合"审计写入失败必须冒泡、不吞、不递归"的设计口径）。→ 当前版在此路径相对修前**退化**。

### (c) `handle_import` 422 / 非成功码 / 真实 transport 失败是否均落 failed 不报 ok —— **修好**
- C1/C2/C3 当前与修前均 PASS（status≠ok、failed_imports 有记录、failed run 存在）；**C4（handle_import 抛 sqlite3.OperationalError）当前 PASS**（落 failed、failed_imports=导入SQL异常、failed run 1 条），修前 388 **异常穿透** → C4 为修复项。

### (d) 预算/超时截断后未请求位置与伪造 failed run —— **修好/通过**
- D1（budget=1、4 目标）：requests=1；`target_summary` 4 条且 indices `[0,1,2,3]`（当前；修前无 index 字段）；未请求 3 个全 `unrequested=true`；**无伪造 failed run**（run_record 仅 1 条 ok）；不变量成立。
- D2（间隔等待跨 deadline）：requests=1、stopped=BATCH_TIMEOUT、第 2 目标 unrequested、无伪造 failed run；两版均 PASS。

### (e) 默认 transport `timeout≤remaining` 与阈值 —— **修好（E2/E2b/E3）**
- E1 remaining=0.2：两版均传 0.2（下限 0.001 不影响该值）。
- E2 remaining=0.0006：当前传 0.0006（无下限）；修前传 **0.001 > remaining**（违反 timeout≤remaining）。
- E2b remaining=0.0005：当前**不调用**（浮点 `(deadline-clock)=0.000499999999988 < 0.0005` 阈值，属安全侧）；修前调用 0.001（超剩余）。
- E3 remaining=0.0004：当前 **calls=0**（wrapper 先 raise，落 failed、不触达 transport）；修前 calls=1（0.001）。→ 阈值处理已加固；精确 0.0005 的浮点边界建议在实现侧用 epsilon/`<=` 明确，但当前不超时是安全的。

### (f) 对账不变量 —— **数值不变量成立但不足以发现索引错配**
- `attempted+unrequested=target_count`、`succeeded+failed=attempted`、`succeeded=imported` 在 C1–C4/D1/D2/A1/A2 的当前结果中均成立（A2 修前 `succeeded=2≠imported=1` 为 FAIL）。
- 但 A1/A2 的**逐 index 归属**错误时数值不变量仍全部成立 → 仅靠数值不变量**不能**证明对账正确；需断言每 position 的 fetch/import 结果归属（本次 A1/A2 断言即为该缺口证据）。

## 5. 真实 DB 副本详情回溯（只读、test_client 进程内、无网络）

- 副本：`real2/db/real.db` → `<run>/dbs/real_detail_copy.db`（复制后 sha 与源一致 `088ef810…`）；`create_app({"db_path": 副本})` + `app.test_client()`。证据：[07_probe_detail.json](<../../tests/acceptance/_tmp/s3_real_hardening_verify_v1/run_20261020_184650_hardverify/evidence/07_probe_detail.json>)（**4/4 PASS，exit=0**）。
- `GET /api/candidates/c_ae26738619e94336` → **200**，candidate `data_origin=real`、`identity_key=n:bilibili:BV1us8MzPEmn`、demand 1 条（native_id=BV1us8MzPEmn、observed_at=2026-10-20T15:38:31+08:00）、evidence 1 条；`GET /api/candidates/c_4ba6d786e30840be` → 200，`n:bilibili:BV1GJ411x7h7`、observed_at=15:38:36+08:00；`GET /opportunity/<id>` 页面路由 **200**；源 `real.db` 读取前后 sha 不变。

## 6. 冻结 / 业务库 / 证据守护

- 38 个文件的 before/after 哈希字典**完全一致**（frozen 三文件、live real_link 427/`1bf59770…`、test 423/`0ede6cca…`、修前副本 388/`8fbe3437…` 与 313 行 test、hard1/2/3 证据、real1/diag1/real2 证据、业务库 `e073f828…`）；`wal=False shm=False`。
- 证据：[00_guard_before.json](<../../tests/acceptance/_tmp/s3_real_hardening_verify_v1/run_20261020_184650_hardverify/evidence/00_guard_before.json>) / [08_guard_after.json](<../../tests/acceptance/_tmp/s3_real_hardening_verify_v1/run_20261020_184650_hardverify/evidence/08_guard_after.json>)；24 件证据文本 UTF-8 无 BOM/LF，读回 **exit=0**（[08_evidence_readback.txt](<../../tests/acceptance/_tmp/s3_real_hardening_verify_v1/run_20261020_184650_hardverify/evidence/08_evidence_readback.txt>)）。

## 7. 过程修正史（如实保留，均未触 live）

1. **attempt1**：路径探针把"脚本目录"误判为 live 路径（`sys.path[0]=<run>/tools`）；差分探针用 `read_text` 后哈希（换行归一化）导致 `1bf59770…` 断言失败；详情探针要求 evidence 行含 `data_origin`（GET 详情投影不含该键）。失败件保留 `*_attempt1_probe_bug.*`。
2. **attempt2**：差分探针的 `target_count` 不在返回 dict（改用 `len(targets)`）、G 断言措辞、E2 用 0.0005 触发浮点边界（改为 0.0006 验"无下限"并单列 E2b 精确 0.0005 行为）。失败件保留 `06_probe_diff_attempt2_assertbug.*`。
3. 所有修正仅发生在 `<run>/tools/` 与 `<run>/evidence/`；未修改 `app/**`、`tests/**`、被验文件与业务库（§6 哈希可证）。

## 8. 未验证 / 限制（不写成已成立）

- **未联网、未启动真实端口、未发起真实请求**；真实链路证据仍为既有 real1/diag1/real2，只读回溯，不能独立复核服务器侧。
- 差分探针场景为**合成 FakeTransport/隔离 DB**；未覆盖真实时钟下的截断、并发/多批次、真实 412/-412/登录/超时行为。
- 修前 388 副本仅能按已存副本与 `01_hashes.txt` 核对，无法证明更早版本历史（不补造更早快照）。
- B 的 hard3 `11_discover.txt` 非 UTF-8，其 280/282 结论不能由该文件复现（本次独立复跑为 280）；B 的 hard3 demo 未覆盖 (a) 中间失败 duplicate 与 (b) record_failure 自身 sqlite3.Error 两点。
- 精确 0.0005 边界的浮点行为已记录（安全侧不调用），是否用 epsilon/`<=` 属实现批取舍，未作为缺陷判定。
- 本会话函数清单中**没有 `skill` 工具**，如实标注未加载。

## 9. 结论与最小修复建议

**可放行范围**（当前 427 已通过）：C1/C2/C3/C4（导入/传输失败不报 ok、SQLite 导入异常落 failed）、D1/D2（截断未请求/无伪造 failed run）、E1/E2/E2b/E3（timeout≤remaining、无 0.001 下限、低于阈值不调用）、G（cfg 先校验）、H（审计写失败冒泡不递归）、A1 数值不变量。
**已证实修好**（相对修前 388 FAIL→PASS）：C4、E2、E2b、E3、A2 数值不变量。
**仍复现**：A1 索引归属错配、A2 索引归属错配（两版均错）；**回归**：B1/B2（`record_failure` 二次调用/吞错）与 A1（修前正确、当前错）——共 3 项回归。
**最终结论：需修订（不建议以当前 427 版放行 S3 real 失败路径加固）**；最小修复建议：
1. **对账改为按输入位置**：把 position/index 随请求结果传入导入阶段，用 `(position → fetch outcome, import outcome)` 直接回填 `target_summary`，不要用 `imported_q[bvid]` 的按 bvid FIFO 队列（`real_link.py:390-408`）。
2. **把 `record_failure` 调用移出导入 `try`**（或只捕获 `handle_import` 自身的异常），使"失败审计写入失败"按设计**单次冒泡、不重试/不吞**（`real_link.py:357-378`，尤其 `:360-362` 与 `:372` 的组合）。
3. 补两条回归测试：同 bvid 中间失败后的 index 归属；`record_failure` 自身抛 `sqlite3.Error` 时的调用次数与冒泡语义。
**不宣称 S3 阶段完成**；上述修复后应按本报告的 A1/A2/B1/B2 断言重验。

## 10. 证据索引

| 证据 | 路径 |
| --- | --- |
| 前后守护（38 文件） | [00_guard_before.json](<../../tests/acceptance/_tmp/s3_real_hardening_verify_v1/run_20261020_184650_hardverify/evidence/00_guard_before.json>) / [08_guard_after.json](<../../tests/acceptance/_tmp/s3_real_hardening_verify_v1/run_20261020_184650_hardverify/evidence/08_guard_after.json>) |
| 镜像 parity | [01_mirror.json](<../../tests/acceptance/_tmp/s3_real_hardening_verify_v1/run_20261020_184650_hardverify/evidence/01_mirror.json>) |
| 模块来源/哈希 | [02_path_probe.json](<../../tests/acceptance/_tmp/s3_real_hardening_verify_v1/run_20261020_184650_hardverify/evidence/02_path_probe.json>) |
| 修前副本复制 | [03_copy_pre388.log](<../../tests/acceptance/_tmp/s3_real_hardening_verify_v1/run_20261020_184650_hardverify/evidence/03_copy_pre388.log>) |
| 单测 27 OK | [04_test_real_link.log](<../../tests/acceptance/_tmp/s3_real_hardening_verify_v1/run_20261020_184650_hardverify/evidence/04_test_real_link.log>) |
| 全量 280 OK | [05_discover.log](<../../tests/acceptance/_tmp/s3_real_hardening_verify_v1/run_20261020_184650_hardverify/evidence/05_discover.log>) |
| 差分断言矩阵（18 项） | [06_probe_diff.json](<../../tests/acceptance/_tmp/s3_real_hardening_verify_v1/run_20261020_184650_hardverify/evidence/06_probe_diff.json>) |
| 真实 DB 副本详情回溯 | [07_probe_detail.json](<../../tests/acceptance/_tmp/s3_real_hardening_verify_v1/run_20261020_184650_hardverify/evidence/07_probe_detail.json>) |
| 证据文本读回 | [08_evidence_readback.txt](<../../tests/acceptance/_tmp/s3_real_hardening_verify_v1/run_20261020_184650_hardverify/evidence/08_evidence_readback.txt>) |
