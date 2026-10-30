# S3 受控真实运行证据 · 409 版收口核验

> 被核验对象：`tests/sources/_tmp/real_run_v2/run_20261020_190634_real3/` 下由 B 用当前 **409 行版** `app/sources/real_link.py`（sha256 `46cbd635b5e70cc2d1b6441befde31e25b8203caf28d39b772203c43b8f5802c`）执行的受控真实运行证据（batch_id=`user-authorized-real-3`，2 bvid，budget=3，interval=5s，timeout=120s，隔离 DB）。
> 关联版本：`tests/sources/test_real_link.py` **489 行** sha `680319dec67f1508cfedaa30048d02a4f3467055ac8daebbab13c62484194990`；冻结三文件 `wiring.py` `bafcf397…`、`bilibili_view.py` `b0dc0ced…`、`importer.py` `a11eaf4d…`；业务库 `instance/app.db` `e073f828…`。
> 核验者：独立执行者 A（实现者 B），任务 `task-a667a14c356855d038d101bfb4172246`；核验时点 2026-10-20 19:10–19:12 +08:00。
> 性质：**只读核验 + 独立复算**（严格 UTF-8、audit/batch_result 复算、DB 副本 `mode=ro` 查询、`create_app`+`test_client` 详情回溯、前后哈希）。**未联网、未启动端口、未改任何被验文件/业务库/旧证据**。
> 结论：**409 版受控真实运行证据成立（限本批 2 个 bvid 与既有证据核验范围）**；**不宣称 S3 阶段完成**，未验证项见 §7。

## 0. 运行目录与证据

- 本次核验 run：`tests/acceptance/_tmp/s3_final_verify/run_20261020_191008_finalverify/`
- 关键证据：[01_verify_evidence.json](<../../tests/acceptance/_tmp/s3_final_verify/run_20261020_191008_finalverify/evidence/01_verify_evidence.json>)（17/17 PASS）、[02_verify_detail.json](<../../tests/acceptance/_tmp/s3_final_verify/run_20261020_191008_finalverify/evidence/02_verify_detail.json>)（4/4 PASS）、[00_guard_before.json](<../../tests/acceptance/_tmp/s3_final_verify/run_20261020_191008_finalverify/evidence/00_guard_before.json>) / [03_guard_after.json](<../../tests/acceptance/_tmp/s3_final_verify/run_20261020_191008_finalverify/evidence/03_guard_after.json>)（32 文件前后一致）、[08_evidence_readback.txt](<../../tests/acceptance/_tmp/s3_final_verify/run_20261020_191008_finalverify/evidence/08_evidence_readback.txt>)。
- 日志均 UTF-8 无 BOM，含 `label/cmd/cwd/start_utc/exit/stdout/stderr`；B 的 14 个证据文件只读，核验前后哈希不变。

## 1. run 目录文件清单与严格 UTF-8

| # | 文件 | 说明 |
| --- | --- | --- |
| 1 | `audit.jsonl` | 2 条请求审计（机器生成） |
| 2 | `batch_result.json` | 终态对账（机器生成） |
| 3 | `driver.py` | 驱动脚本（UTF-8 **带 BOM**） |
| 4–5 | `tools_check_path.py`、`tools_readback_check.py` | 辅助自检（UTF-8 **带 BOM**） |
| 6 | `db/real.db` | 隔离运行库，241,664 B，sha `7a4ed405…`，无 `-wal`/`-shm` |
| 7–14 | `evidence/{00_before.txt, 10_result.json, 11_db_readback.json, 12_stdout_failed_attempt1.txt, 12_stdout_run2_summary.txt, 13_audit_snapshot.jsonl, 14_batch_result_snapshot.json, 20_after.txt}` | 证据快照与失败尝试留存 |

- **严格 UTF-8 解码：13 个文本文件全部通过**（0 个 `UnicodeDecodeError`）；其中 `driver.py`、`tools_check_path.py`、`tools_readback_check.py` 含 UTF-8 **BOM**（BOM 仍是合法 UTF-8，已记录、不构成解码失败）。
- 失败尝试 `12_stdout_failed_attempt1.txt` **如实保留**：`ModuleNotFoundError: No module named 'app'`、`exit=1`、时间 19:06:34.742–34.929 +08:00（=11:06:34Z），发生在首次 audit（11:06:45Z）之前；audit 仅 2 行、无失败尝试痕迹 → 该尝试在 import 阶段失败、**未触网**。
- 说明：`12_stdout_run2_summary.txt` 自述"按实际捕获内容重建"，非原始控制台字节流；**主证据以机器生成的 audit/DB/batch_result/10_result 为准**。

## 2. audit.jsonl 复算

| 项 | 实测 |
| --- | --- |
| 行数 | **2** |
| batch_id | 两行均 `user-authorized-real-3` |
| bvid | `BV1us8MzPEmn` → `BV1GJ411x7h7` |
| URL | `https://api.bilibili.com/x/web-interface/view?bvid=BV1us8MzPEmn` / `…?bvid=BV1GJ411x7h7`（**精确匹配**） |
| 时间 | `2026-10-20T11:06:45Z` / `2026-10-20T11:06:50Z`，**间隔 5.0s ≥ 5s** |
| http_status / outcome / error | `200` / `ok` / `null`（两行） |
| attempt / requests_made | `1` / `1,2` |
| 快照一致性 | `evidence/13_audit_snapshot.jsonl` 与 `audit.jsonl` **sha256 相同** |

## 3. batch_result.json 对账

- `status=ok`、`requests=2`、`imported=2`、`target_count=2`、`results=2`、`stopped_reason=null`、`truncated=[]`、`failed_imports=[]`。
- `summary_counts={"attempted":2,"succeeded":2,"failed":0,"unrequested":0}`。
- `target_summary` 两条：`index 0/1`、bvid 对应、`attempts=1`、`attempted=true`、`succeeded=true`、`failed=false`、`unrequested=false`、`error=null`。
- `audit_path` 与真实文件路径**逐字一致**（`…\run_20261020_190634_real3\audit.jsonl`）；`14_batch_result_snapshot.json` 与 `batch_result.json` **sha256 相同**。
- `10_result.json`：imported 2 条、position 0/1、status **201**、`ok=true`、created ids 为 `c_4ca5…/d_4836…/e_9fe2…` 与 `c_ca39…/d_f8f5…/e_b4a6…`，与 DB/详情一致；notes 含 batch_id/requests=2/targets=2。

## 4. 隔离 DB 副本只读核验（`mode=ro`）

- 副本 sha 与源一致 `7a4ed405…4d4bc`、241,664 B；源库无 `-wal`/`-shm`；核验后源 sha 不变。

| 表 | 实测 |
| --- | --- |
| candidate | **2 行，全 `data_origin='real'`**：`c_4ca5d07dde8747f9`、`c_ca391c5859454320` |
| demand_signal | **2 行 real**：identity `n:bilibili:BV1us8MzPEmn` / `n:bilibili:BV1GJ411x7h7`；native_id 对应；`version_no=1`、`superseded_by=NULL`、`source_id=s_bili`、`observed_at_source='import_time'`、`observed_at=2026-10-20T19:06:45+08:00` / `19:06:50+08:00` |
| evidence | **2 行 real**：`e_9fe2666b75a7491f`、`e_b4a68c0b573846c1`，`invalidated_at=NULL`，demand_signal_id 对应 |
| run_record | **2 条**：`status=ok`、`source_id=s_bili`、`items_found=1`、`items_new=1`、`items_dup=0`、notes=`batch=ib_…` |
| import_batch | 2 条 `committed`、`rows_created=1` |
| source | `s_bili.last_success_at=NULL`、`access_mode=manual_import`（未被改写） |
| 其它表 | supply_offer/cost_item/gate_review/review_item 均 **0** |
| readback 交叉 | `11_db_readback.json` 与独立 SQL 查询逐项一致（demand/candidate/run_record/evidence_count） |

## 5. test_client 详情回溯（进程内，无端口、无网络）

- `create_app({"db_path": 副本})` + `app.test_client()`（app 代码为当前 409 版，只读打开副本）：
  - `GET /api/candidates/c_4ca5d07dde8747f9` → **200**，candidate `data_origin=real`、identity `n:bilibili:BV1us8MzPEmn`、demand 1 条（native_id=BV1us8MzPEmn、observed_at=19:06:45+08:00）、evidence `e_9fe2666b75a7491f`；
  - `GET /api/candidates/c_ca391c5859454320` → **200**，identity `n:bilibili:BV1GJ411x7h7`、observed_at=19:06:50+08:00、evidence `e_b4a68c0b573846c1`；
  - `GET /opportunity/<id>` 两个页面 → **200**；副本源文件 sha 前后不变。

## 6. 前后哈希守护

- **32 个文件 before/after 哈希完全一致**（`00_guard_before.json` / `03_guard_after.json`，均 exit=0）：run 目录 14 文件（含 `db/real.db` `7a4ed405…`、`audit.jsonl` `524246af…`、`batch_result.json`）+ live `real_link.py` **409/`46cbd635…`** + test 489/`680319de…` + frozen 三文件 + 业务库 `e073f828…` + real1/diag1/real2 旧证据 + 388/427 对照副本；`wal=False shm=False`。
- 证据自洽：`00_before.txt`/`20_after.txt` 内记录的哈希与本次重算的 live 哈希一致（409/frozen/业务库/real2 DB），BEFORE 与 AFTER 相同。
- 本次核验 15 件证据文本 UTF-8 无 BOM/LF，读回 **exit=0**。

## 7. 无绕过反爬抽查与未验证项

- **audit 仅 2 次请求**（requests_made 最大 2 ≤ budget 3）；driver 参数与自述一致（batch_id/confirmed、budget=3、interval=5.0、timeout=120、2 bvid、隔离 `db/real.db`）；`real_link.py` 抽查无 `Cookie`/`Referer`/`proxies`/伪造 `Mozilla`/`b23.tv`/`import requests` 痕迹；请求 URL 均为公开详情 API、间隔 5s。
- **仍未验证**：仅 2 个 bvid、单批、单端点、单来源，字段稳定性/缺失字段/长尾内容未验证；真实频控/风控（412/-412/-101/验证码/IP 限流）未触发；真实网络中断/DNS/TLS/超时/批次超时/中断恢复未触发；并发/多批次未验证；`observed_at_source` 本批为 `import_time`（driver 未传源观察时间，源时间真实路径未验证）；`BUDGET_EXHAUSTED` 等批次 notes 未入库（仅审计文件），批次注入方案未验证；B 证据中 `12_stdout_run2_summary.txt` 为"重建"摘要（非原始字节流），`driver.py` 等 3 个 py 文件带 BOM（合法 UTF-8，已记录）。
- 本次核验仅只读：**未联网、未启动真实端口、未发起真实请求**；不能独立复核服务器侧响应；真实运行的真实性由 audit/DB/batch_result/10_result 四方一致与哈希守护支撑。

## 8. 结论

- **「409 版受控真实运行证据成立」**（限本批 2 个 bvid 与既有证据核验范围）：status=ok、2 次真实 API 请求均 HTTP 200 且间隔 5s、audit/batch_result/10_result/DB 四方一致（2 real 候选/需求/证据、2 条 ok run_record、identity/observed_at 正确）、详情与页面可回溯、业务库与旧证据未变、无 WAL/SHM、无绕过反爬痕迹。
- **不宣称 S3 阶段完成**：字段稳定性、真实频控/风控、长跑/异常恢复、并发/多批次、源观察时间真实路径等仍未验证（§7）。

## 9. 证据索引

| 证据 | 路径 |
| --- | --- |
| 证据核验（17 项） | [01_verify_evidence.json](<../../tests/acceptance/_tmp/s3_final_verify/run_20261020_191008_finalverify/evidence/01_verify_evidence.json>) |
| 详情回溯（4 项） | [02_verify_detail.json](<../../tests/acceptance/_tmp/s3_final_verify/run_20261020_191008_finalverify/evidence/02_verify_detail.json>) |
| 前后守护（32 文件） | [00_guard_before.json](<../../tests/acceptance/_tmp/s3_final_verify/run_20261020_191008_finalverify/evidence/00_guard_before.json>) / [03_guard_after.json](<../../tests/acceptance/_tmp/s3_final_verify/run_20261020_191008_finalverify/evidence/03_guard_after.json>) |
| 证据文本读回 | [08_evidence_readback.txt](<../../tests/acceptance/_tmp/s3_final_verify/run_20261020_191008_finalverify/evidence/08_evidence_readback.txt>) |
| 核验日志（UTF-8） | [01_verify_evidence.log](<../../tests/acceptance/_tmp/s3_final_verify/run_20261020_191008_finalverify/evidence/01_verify_evidence.log>) / [02_verify_detail.log](<../../tests/acceptance/_tmp/s3_final_verify/run_20261020_191008_finalverify/evidence/02_verify_detail.log>) |
