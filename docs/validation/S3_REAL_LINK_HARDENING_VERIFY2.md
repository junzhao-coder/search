# S3 real 失败路径加固 · 复验（409 版最小修复，同矩阵重跑）

> 复验对象：`app/sources/real_link.py`（**409 行**，sha256 `46cbd635b5e70cc2d1b6441befde31e25b8203caf28d39b772203c43b8f5802c`，与 B 宣称 `46CBD635…` 一致）与 `tests/sources/test_real_link.py`（**489 行**，sha256 `680319dec67f1508cfedaa30048d02a4f3467055ac8daebbab13c62484194990`，与 B 宣称 `680319DE…` 一致）。
> 对照版本：上一轮被复核并判「需修订」的 **427 行版**（sha `1bf597706f7995a7473d3da4bca535fdda53ce4cc7a3868b56fe9b1892af55ab`，取自 v1 复核 run 的镜像）与更早 **388 行修前副本**（sha `8fbe34376b7f9e8e874cede03f8f90abc7eca4bc12155af3bad7db66a2e55470`，`before_20261020_160909_rev8`）。
> 冻结三文件（未改）：`wiring.py` `bafcf397…`、`bilibili_view.py` `b0dc0ced…`、`importer.py` `a11eaf4d…`；业务库 `instance/app.db` `e073f828…`。
> 复验者：独立执行者 A（实现者 B），任务 `task-7bbd50cf7589cb9dd66d80f3cd194c10`；复验时点 2026-10-20 19:00–19:03 +08:00。
> 性质：**隔离镜像 + 同一 18 项差分矩阵（+2 项分支补充）指向 409 复跑 + B 证据核对**。**未联网、未启动端口、未改任何被验文件/业务库/旧证据**。
> 结论：**加固可放行（限本报告断言范围；仍不宣称 S3 阶段完成）**——A1/A2/B1/B2 四项由 FAIL 转 PASS，原放行项零回归（20/20 PASS）；`-m tests.sources.test_real_link` **31/31 OK exit=0**、完整 discover **284/284 OK exit=0**；44 文件前后哈希一致。

## 0. 运行目录与证据

- 唯一 run：`tests/acceptance/_tmp/s3_hardening_verify_v2/run_20261020_190032_hardverify2/`
- 日志：`tools/run_and_log_utf8.py`（`subprocess.run(..., encoding='utf-8')`；每条含 `label/cmd/cwd/start_utc/exit/stdout/stderr`，UTF-8 无 BOM）。
- 关键证据：[02_path_probe.json](<../../tests/acceptance/_tmp/s3_hardening_verify_v2/run_20261020_190032_hardverify2/evidence/02_path_probe.json>)、[04_test_real_link.log](<../../tests/acceptance/_tmp/s3_hardening_verify_v2/run_20261020_190032_hardverify2/evidence/04_test_real_link.log>)、[05_discover.log](<../../tests/acceptance/_tmp/s3_hardening_verify_v2/run_20261020_190032_hardverify2/evidence/05_discover.log>)、[06_probe_diff.json](<../../tests/acceptance/_tmp/s3_hardening_verify_v2/run_20261020_190032_hardverify2/evidence/06_probe_diff.json>)、[07_probe_b_evidence.json](<../../tests/acceptance/_tmp/s3_hardening_verify_v2/run_20261020_190032_hardverify2/evidence/07_probe_b_evidence.json>)、[08_guard_after.json](<../../tests/acceptance/_tmp/s3_hardening_verify_v2/run_20261020_190032_hardverify2/evidence/08_guard_after.json>)、[08_evidence_readback.txt](<../../tests/acceptance/_tmp/s3_hardening_verify_v2/run_20261020_190032_hardverify2/evidence/08_evidence_readback.txt>)。

## 1. 镜像与来源实证

- 镜像：live `app/**`+`tests/**`+`requirements.txt` → `<run>/mirror/`（排除缓存/`_tmp`/`_snapshots`/`.venv`/reparse；**77 件**、逐件 parity **mismatched=0 / extra=0**）→ [01_mirror.json](<../../tests/acceptance/_tmp/s3_hardening_verify_v2/run_20261020_190032_hardverify2/evidence/01_mirror.json>)（**exit=0**）。
- 模块来源（cwd=mirror、PYTHONPATH=mirror、PYTHONDONTWRITEBYTECODE=1、live venv python 3.12.14）：**12/12 checks + 2/2 hash PASS**——`app.sources.real_link`/`bilibili_view`/`wiring`/`app.core.importer`/`tests.sources.test_real_link` 全从镜像加载；镜像内 **real_link 409 行/`46cbd635…`、test 489 行/`680319de…`** 与 live 一致 → [02_path_probe.json](<../../tests/acceptance/_tmp/s3_hardening_verify_v2/run_20261020_190032_hardverify2/evidence/02_path_probe.json>)（**exit=0**）。
- 对照 427 版从 v1 复核 run 镜像复制入本次镜像为 `app.sources.real_link_ref427`：**427 行/`1bf59770…`** 校验通过（[03_copy_ref427.log](<../../tests/acceptance/_tmp/s3_hardening_verify_v2/run_20261020_190032_hardverify2/evidence/03_copy_ref427.log>)，**exit=0**）。

## 2. 同矩阵复跑：409（current）vs 427（ref）；18 项 + 2 项分支补充

- 探针：[06_probe_diff.json](<../../tests/acceptance/_tmp/s3_hardening_verify_v2/run_20261020_190032_hardverify2/evidence/06_probe_diff.json>)（**exit=0**，20 项断言，`current`=409、`ref`=427；FakeTransport/隔离 sqlite DB/仅离线）。
- 汇总：**当前 409 = 20/20 PASS**；427 = 16/20；**修前 427 的 4 项 FAIL 全部转 PASS**；**`released_regressions=[]`（原放行项零回归）、`no_regression_on_previously_passing=true`**。

| # | 断言 | 409（current） | 427（对照） | 关键证据 |
| --- | --- | --- | --- | --- |
| A1 | 同 bvid×3，outcomes=[ok, rate_limited, ok] → 逐 index 归属 | **PASS** `[T,F],[F,T],[T,F]` | FAIL `[T,F],[T,F],[F,T]` | 同 v1 最小输入；位置回填 |
| A1n | A1 数值不变量 | PASS | PASS | attempted+unrequested=3、succeeded+failed=3、succeeded=imported=2 |
| A2 | 同 bvid×2，第 1 次导入返回 422、第 2 次成功 → 逐 index 归属 | **PASS** `[F,T],[T,F]` | FAIL `[T,F],[F,T]` | patch handle_import 第 1 次→422 |
| A2n | A2 数值不变量 | PASS | PASS | succeeded=1=imported |
| B1 | 非成功码分支 `record_failure` 自身抛 sqlite3：调用次数/冒泡/run_record | **PASS**：**calls=1**、`OperationalError` 冒泡、run_record **0 行**、原因保留"导入返回非成功码 status=422" | FAIL：calls=2、异常被吞并改写 run_record | 单 target + handle_import→422 + record_failure 第 1 次抛 |
| B2 | 同上、record_failure 每次都抛：单次尝试/冒泡 | **PASS** calls=1、冒泡 | FAIL calls=2 | 同上 always-raise |
| B3 | 分支补充：transport 失败分支（outcome=rate_limited）下 record_failure 抛 sqlite3 | **PASS** calls=1、冒泡、0 行 | PASS | 新增覆盖（两版本来就正确） |
| B4 | 分支补充：映射异常分支（`_build_real_row` 抛 AppError）下 record_failure 抛 sqlite3 | **PASS** calls=1、冒泡、0 行 | PASS | 新增覆盖 |
| C1 | transport 失败 → status≠ok、failed run | PASS | PASS | — |
| C2 | 映射失败 → status≠ok、failed run | PASS | PASS | — |
| C3 | 导入非成功码 → status≠ok、failed run | PASS | PASS | — |
| C4 | handle_import 抛 sqlite3 → 落 failed 不冒泡 | PASS | PASS | — |
| D1 | budget=1、4 唯一目标 → unrequested 3、无伪造 failed run、indices [0..3] | PASS | PASS | — |
| D2 | 间隔等待跨 deadline → 第 2 目标 unrequested、无伪造 failed run | PASS | PASS | — |
| E1 | remaining=0.2 → timeout≤remaining | PASS（0.2） | PASS | — |
| E2 | remaining=0.0006 → 无 0.001 下限 | PASS（0.0006） | PASS | — |
| E2b | 精确 0.0005 → 不超剩余 | PASS（不调用；浮点 0.000499999999988<阈值，安全侧） | PASS | — |
| E3 | remaining=0.0004 < 阈值 → 不调用 transport | PASS（calls=0） | PASS | — |
| G | 非法 cfg → 422 且 0 请求 | PASS | PASS | — |
| H | `_audit` 写失败 → 冒泡、不递归记 run | PASS | PASS | — |

- 四项由 FAIL→PASS：**A1 索引归属、A2 索引归属、B1 record_failure 二次调用、B2 单次尝试**（`fixed_current_pass_pre_fail` 列表）。原放行项（C1–C4、D1/D2、E1/E2/E2b/E3、A1n/A2n、G、H）**全部保持 PASS，无回归**。

## 3. 代码差异核验（427 → 409，最小修复）

逐行对比 409 与 v1 镜像中的 427（行数 427→409，净 −18 行）：改动集中在**导入/对账循环**——`results` 携带 `position`（`real_link.py:321-322`）；导入循环按 position 直接回填 `target_summary`（`:336-380`）；`record_failure` 被**移出导入 try、在失败分支单次调用**（`:376-380`），导入异常仅在 try 内转成 `error_text`（`:348-368`）；**删除**了按 bvid 的 `imported_q`/`err_by_bvid` FIFO 对账段（旧 427 的 `defaultdict(deque)` 整段移除）。授权/预算/transport/审计/状态判定等其余逻辑与 427 一致（未发现无关改动）。

## 4. 测试与 B 证据核对

| 项 | 结果 |
| --- | --- |
| `-m tests.sources.test_real_link` | **Ran 31 tests — OK，exit=0**（`04_test_real_link.log`，`start_utc=2026-10-20T11:02:08Z`，cwd=mirror） |
| 完整 discover | **Ran 284 tests — OK，exit=0**（`05_discover.log`，44.017s） |
| B minfix1 证据（8/8 PASS） | `10_module_tests_v.txt`、`11_discover.txt` 现均为 **UTF-8 可读**（v1 时 hard3 `11_discover.txt` 非 UTF-8 的问题已消除）；含 "Ran 31 tests/OK"、"Ran 284 tests"、`module_exit=0`/`discover_exit=0`；`01_hashes.txt` 的 409/489/388 哈希与实测一致；四个新测试（A1/A2/B1/B2）均出现在 verbose 日志 |

## 5. 前后哈希守护

- **44 个文件 before/after 完全一致**：live real_link 409/`46cbd635…`、test 489/`680319de…`、frozen 三文件（`bafcf397…`/`b0dc0ced…`/`a11eaf4d…`）、388 修前副本（`8fbe3437…`）、427 对照副本（`1bf59770…`）、real1/diag1/real2 证据、B minfix1 证据、业务库 `e073f828…`；`wal=False shm=False` → [00_guard_before.json](<../../tests/acceptance/_tmp/s3_hardening_verify_v2/run_20261020_190032_hardverify2/evidence/00_guard_before.json>) / [08_guard_after.json](<../../tests/acceptance/_tmp/s3_hardening_verify_v2/run_20261020_190032_hardverify2/evidence/08_guard_after.json>)（均 **exit=0**）。
- 证据 16 件文本 UTF-8 无 BOM/LF、读回 **exit=0**（[08_evidence_readback.txt](<../../tests/acceptance/_tmp/s3_hardening_verify_v2/run_20261020_190032_hardverify2/evidence/08_evidence_readback.txt>)）。

## 6. 过程说明与未验证项

- **无失败重跑**：本次探针首次运行即通过（20/20）；仅在本地语法检查时遇到系统 Python 3.10 对 f-string 反斜杠的限制（探针实际以 venv 3.12 运行，不影响结果）。
- **未验证**：未联网/未启动真实端口/未发起真实请求；差分场景为合成 FakeTransport 与隔离 DB；未覆盖真实时钟下的截断、真实 412/-412/登录/超时、并发/多批次；427/388 对照来自已存副本（哈希可核）而非 VCS 历史；B 的 minfix1 日志为 B 自产（现 UTF-8 可读且与本次独立复跑一致，但非 A 独立执行）；精确 0.0005 浮点边界维持"安全侧不调用"（未作为缺陷）。
- **不宣称 S3 阶段完成**；真实网络批次仍需单独授权与证据。

## 7. 结论

- **加固可放行（限本报告断言范围）**：A1/A2/B1/B2 四项按同一最小输入复验已由 FAIL 转 PASS（A1 `[T,F],[F,T],[T,F]`、A2 `[F,T],[T,F]`；B1/B2 `record_failure` **单次调用并冒泡**、run_record 不增）；原放行项（C1–C4、D1/D2、E1/E2/E2b/E3、A1n/A2n、G、H）**零回归**；31/31 与 284/284 测试 `OK exit=0`；44 文件哈希前后一致、业务库与旧证据未动、无 WAL/SHM。
- **不宣称 S3 阶段完成**；建议保留后续真实网络批次（单独授权）与现有 real1/diag1/real2 证据不变。

## 8. 证据索引

| 证据 | 路径 |
| --- | --- |
| 前后守护（44 文件） | [00_guard_before.json](<../../tests/acceptance/_tmp/s3_hardening_verify_v2/run_20261020_190032_hardverify2/evidence/00_guard_before.json>) / [08_guard_after.json](<../../tests/acceptance/_tmp/s3_hardening_verify_v2/run_20261020_190032_hardverify2/evidence/08_guard_after.json>) |
| 镜像 parity | [01_mirror.json](<../../tests/acceptance/_tmp/s3_hardening_verify_v2/run_20261020_190032_hardverify2/evidence/01_mirror.json>) |
| 409/489 来源与哈希 | [02_path_probe.json](<../../tests/acceptance/_tmp/s3_hardening_verify_v2/run_20261020_190032_hardverify2/evidence/02_path_probe.json>) |
| 427 对照副本复制 | [03_copy_ref427.log](<../../tests/acceptance/_tmp/s3_hardening_verify_v2/run_20261020_190032_hardverify2/evidence/03_copy_ref427.log>) |
| 单测 31 OK | [04_test_real_link.log](<../../tests/acceptance/_tmp/s3_hardening_verify_v2/run_20261020_190032_hardverify2/evidence/04_test_real_link.log>) |
| 全量 284 OK | [05_discover.log](<../../tests/acceptance/_tmp/s3_hardening_verify_v2/run_20261020_190032_hardverify2/evidence/05_discover.log>) |
| 20 项差分矩阵 | [06_probe_diff.json](<../../tests/acceptance/_tmp/s3_hardening_verify_v2/run_20261020_190032_hardverify2/evidence/06_probe_diff.json>) |
| B 证据核对 | [07_probe_b_evidence.json](<../../tests/acceptance/_tmp/s3_hardening_verify_v2/run_20261020_190032_hardverify2/evidence/07_probe_b_evidence.json>) |
| 证据文本读回 | [08_evidence_readback.txt](<../../tests/acceptance/_tmp/s3_hardening_verify_v2/run_20261020_190032_hardverify2/evidence/08_evidence_readback.txt>) |
