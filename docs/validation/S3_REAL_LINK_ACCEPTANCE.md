# S3 受控 real 链路 · 独立复核验收（非实现者复核）

> 复核对象：`app/sources/real_link.py`（**272 行**，sha256 `9dd45d468a6ec98f23e9ee9d7c33544b5bb312acf4f0f9c0e7f08567028a033c`，与 B 自称 `9DD45D46…` 一致）与 `tests/sources/test_real_link.py`（**192 行**，sha256 `90af4a87aedb1d76bd11e28febf6143ce1438abad68d4f06036826e39c7741ae`，与 B 自称 `90AF4A87…` 一致）。
> 复核者：独立执行者 A（实现者 B），任务 `task-9e8ace84deb144cf26dc5465895bf481`；复核时点 2026-10-20 15:42–15:48 +08:00。
> 性质：**镜像复跑 + 离线探针 + 既有真实证据只读核验**。**全程未发起任何网络请求**、未启动服务、未改文件、未写业务库。
> 结论：**通过（限定于「受控真实链路 2 个 bvid 样本」）**——镜像内单测 10/10、全量 263/263 均 `OK exit=0`；离线探针 **15/15**、真实证据只读核验 **16/16** 全过；冻结三文件与业务库前后哈希一致、WAL/SHM 不存在。**字段稳定性、频控/风控、长跑与异常恢复、源观察时间真实路径等未验证；不宣称 S3 阶段完成**。

## 0. 运行目录与证据

- 唯一 run：`tests/acceptance/_tmp/s3_real_verify_v1/run_20261020_154246_realverify/`
- 证据：[00_guard_before.json](<../../tests/acceptance/_tmp/s3_real_verify_v1/run_20261020_154246_realverify/evidence/00_guard_before.json>)、[01_mirror.json](<../../tests/acceptance/_tmp/s3_real_verify_v1/run_20261020_154246_realverify/evidence/01_mirror.json>)、[02_path_probe.json](<../../tests/acceptance/_tmp/s3_real_verify_v1/run_20261020_154246_realverify/evidence/02_path_probe.json>)、[03_test_real_link_cmd.log](<../../tests/acceptance/_tmp/s3_real_verify_v1/run_20261020_154246_realverify/evidence/03_test_real_link_cmd.log>)、[04_discover_cmd.log](<../../tests/acceptance/_tmp/s3_real_verify_v1/run_20261020_154246_realverify/evidence/04_discover_cmd.log>)、[03_probe_real_link.json](<../../tests/acceptance/_tmp/s3_real_verify_v1/run_20261020_154246_realverify/evidence/03_probe_real_link.json>)、[04_probe_real_evidence.json](<../../tests/acceptance/_tmp/s3_real_verify_v1/run_20261020_154246_realverify/evidence/04_probe_real_evidence.json>)、[07_guard_after.json](<../../tests/acceptance/_tmp/s3_real_verify_v1/run_20261020_154246_realverify/evidence/07_guard_after.json>)、[08_evidence_readback.txt](<../../tests/acceptance/_tmp/s3_real_verify_v1/run_20261020_154246_realverify/evidence/08_evidence_readback.txt>)

## 1. 镜像与模块来源实证

- 镜像：复制 live `app/**`+`tests/**`+`requirements.txt` → `<run>/mirror/`（排除 `__pycache__`/`_tmp`/`_snapshots`/`.venv`/reparse；**77 件**、逐件 parity **mismatched=0 / extra=0**）→ [01_mirror.json](<../../tests/acceptance/_tmp/s3_real_verify_v1/run_20261020_154246_realverify/evidence/01_mirror.json>)（**exit=0**）。
- 模块/DB 来源（cwd=mirror、PYTHONPATH=mirror、PYTHONDONTWRITEBYTECODE=1、live venv python 3.12.14）：**12/12 PASS**——`app`/`app.sources.real_link`/`app.sources.bilibili_view`/`app.sources.wiring`/`app.core.importer`/`tests.sources.test_real_link`/`config.ROOT` 全在镜像内，fresh DB 在 run 内，sys.path 无 live/旧镜像路径 → [02_path_probe.json](<../../tests/acceptance/_tmp/s3_real_verify_v1/run_20261020_154246_realverify/evidence/02_path_probe.json>)（**exit=0**）。

## 2. 两轮测试（真实 exit）

| 轮次 | 命令（cwd=mirror） | 结果 | 对照 B 宣称 |
| --- | --- | --- | --- |
| real_link 单测 | `-m tests.sources.test_real_link` | **Ran 10 tests — OK，exit=0** | 10 ✓ |
| 完整回归 | `-m unittest discover -s tests -t .` | **Ran 263 tests — OK，exit=0** | 263 ✓ |

证据：[03_test_real_link_cmd.log](<../../tests/acceptance/_tmp/s3_real_verify_v1/run_20261020_154246_realverify/evidence/03_test_real_link_cmd.log>)、[04_discover_cmd.log](<../../tests/acceptance/_tmp/s3_real_verify_v1/run_20261020_154246_realverify/evidence/04_discover_cmd.log>)。

## 3. 离线探针（fixture transport，不联网；15/15 PASS）

证据：[03_probe_real_link.json](<../../tests/acceptance/_tmp/s3_real_verify_v1/run_20261020_154246_realverify/evidence/03_probe_real_link.json>)（**exit=0**）。探针独立编写（未复用 B 断言），仅复用 fixture 与 `create_app` 隔离 DB 造数。

| # | 检查 | 结果 |
| --- | --- | --- |
| U1 | 未授权（None / 空对象 / 空批次号 / confirmed=False）→ `AppError` 422，**transport 调用 0 次**，不创建 audit.jsonl | PASS |
| P1 | 参数越界（budget 0/21、interval 4.9、timeout 0/601、空目标）→ 422 且 **0 次请求** | PASS |
| B1 | budget=1、2 目标 → 仅 1 次请求；返回值 notes 含 `BUDGET_EXHAUSTED`、`stopped_reason=BUDGET_EXHAUSTED`、status=failed；audit 1 行 `requests_made=1` | PASS |
| R1 | 首次 timeout→重试成功：**2 次 transport，审计 attempt=[1,2]、requests_made=[1,2]**，退避 2.0s（间隔 5.0s 亦记录）、最终 status=ok | PASS |
| R2 | 预算=1 且超时：1 次请求后不重试，`BUDGET_EXHAUSTED` 停止（重试受预算约束） | PASS |
| T1 | transport 抛异常：status=partial（results 含 failed 记录）、audit 2 行 `transport 异常：RuntimeError: boom`（failed 属可重试类→重试 1 次）、run_record **failed** 且 error_summary 原文、业务表 0 新增 | PASS |
| N1 | `normalize_response`：JSON dict→payload；**gzip JSON→payload**；HTML→`html_shell`；非 dict JSON→`html_shell`；空 body→`html_shell`（content_type 被忽略，仅按内容判） | PASS |
| A1/A2 | `api_url` 精确为 `https://api.bilibili.com/x/web-interface/view?bvid=…`；从网页 URL/API URL 提取 bvid；`real_transport` 经 patch 的 urlopen 捕获：**请求目标为 API URL**，headers `User-Agent=local-selection-tool/1.0 (+offline research)`、`Accept=application/json`、`Accept-Encoding=identity` | PASS |
| S1/S2 | 静态扫描：无 `Cookie`/`Referer`/`proxies`/`proxy=`/`b23.tv`/`Mozilla`/`import requests`/`httpx`/`aiohttp`/`random`；**无 `UPDATE source`**（不写 last_success_at）；`MAX_BUDGET=20`、`MIN_INTERVAL_SECONDS=5.0`、`RETRY_WAIT_SECONDS=2.0`、`attempts >= 2`、可重试集合 `{timeout, failed}`、不重试集合 `{rate_limited, blocked_login}` | PASS |
| I1–I4 | 隔离 DB 导入：2 个 bvid → candidate/demand/evidence 各 2 行且 `data_origin='real'`、identity `n:bilibili:<bvid>`、version 1、superseded NULL、evidence 2、run_record 2 条 status=ok（items_new=1/条）；`source.last_success_at` 保持 NULL；audit 字段（ts Z、batch_id、url==api_url(bvid)、attempt、requests_made、outcome=ok、http_status=200）齐全 | PASS |

## 4. 既有真实运行证据只读核验（16/16 PASS；**未发起新网络请求**）

- 证据来源（既有，只读）：`tests/sources/_tmp/real_diag_v1/run_20261020_real2/`；`real.db` 复制到 `<run>/dbs/real_evidence_copy.db` 后以 **`mode=ro` URI 只读**打开（源文件 sha256 前后一致）。
- 证据：[04_probe_real_evidence.json](<../../tests/acceptance/_tmp/s3_real_verify_v1/run_20261020_154246_realverify/evidence/04_probe_real_evidence.json>)（**exit=0**）。

| 核验点 | 实测 |
| --- | --- |
| 隔离 DB | sha256 `088ef810…64e587`、241,664 B、无 `-wal`/`-shm`（与 B 证据一致） |
| candidate | **2 行，全 `data_origin='real'`**：`c_ae26738619e94336`（n:bilibili:BV1us8MzPEmn）、`c_4ba6d786e30840be`（n:bilibili:BV1GJ411x7h7） |
| demand_signal | **2 行，real**；native_id=BV1us8MzPEmn / BV1GJ411x7h7；version_no=1、superseded_by=NULL、source_id=s_bili |
| observed_at | `2026-10-20T15:38:31+08:00` / `2026-10-20T15:38:36+08:00`；**`observed_at_source='import_time'`**——driver 未传 observed_at，适配器按设计 §5 回退到调用时刻并标注，**未冒充源观察时间** |
| evidence | **2 行 real**：`e_18e2ccbf59174696`、`e_6aea262ba08d4435`；invalidated_at 均 NULL |
| run_record | **2 条**（每条成功导入各 1 条）：status=ok、source_id=s_bili、run_type=import、items_found=1/items_new=1/items_dup=0、notes=`batch=ib_…`；**无批次级 run_record**（批次 notes 走审计文件，见 §6） |
| import_batch / row_result | 2 条 committed（`real:BV1us8MzPEmn.json`/`real:BV1GJ411x7h7.json`，rows_created=1）；import_row_result **6 条 created** |
| source / 其它表 | `s_bili.last_success_at=NULL`、access_mode 仍 `manual_import`；supply_offer/cost_item/gate_review/review_item **均 0** |
| audit.jsonl | **2 行**：ts `2026-10-20T07:38:31Z`/`07:38:36Z`（**间隔 5.0s ≥ 5s**）；URL 均为 `https://api.bilibili.com/x/web-interface/view?bvid=…`；outcome=ok、http_status=200、attempt=1、requests_made=[1,2]、batch_id=`user-authorized-real-2`、error=null；与 `12_audit_snapshot.jsonl` **哈希一致** |
| stdout | status=ok、requests=2、targets 2、results=2、imported 2×**201**，6 个 created ids 与 DB 逐一对应 |
| driver / 时间窗 | budget=3、interval=5.0、timeout=120.0、授权 confirmed=True；meta `exit=0`，运行窗 15:38:30.567→15:38:36.572+08:00 完整包含两条 audit 时间 |
| 根因证据（首轮失败） | diag1：网页 URL 返回 **gzip HTML**（`content_type=text/html`、bytes=47664、`json_ok=false`、body 以 `0x1f 0x8b` 开头）——与「修复=改用详情 API + 归一化」的叙述一致 |

## 5. 冻结与业务库守护

| 项 | 运行前 | 运行后 |
| --- | --- | --- |
| 冻结 `wiring.py` | `bafcf397…0da05` | **一致** |
| 冻结 `bilibili_view.py` | `b0dc0ced…3f98e` | **一致** |
| 冻结 `importer.py` | `a11eaf4d…f51a1` | **一致** |
| 被验 `real_link.py` / `test_real_link.py` | `9dd45d46…a033c` / `90af4a87…741ae` | **一致** |
| 业务库 `instance/app.db` | `e073f828…eb85` | **一致**；`-wal`/`-shm` 均不存在 |
| 真实证据文件（real.db/audit/stdout/meta/driver/diag） | 8 个哈希 | **逐一一致**（含源 real.db sha `088ef810…`） |

证据：[00_guard_before.json](<../../tests/acceptance/_tmp/s3_real_verify_v1/run_20261020_154246_realverify/evidence/00_guard_before.json>) / [07_guard_after.json](<../../tests/acceptance/_tmp/s3_real_verify_v1/run_20261020_154246_realverify/evidence/07_guard_after.json>)（5 类共 15 文件全等，`wal=False shm=False`）；证据文本 20 件 UTF-8 无 BOM/LF、读回 **exit=0**。

## 6. 实现与设计差异 / 需记录点

1. **`BUDGET_EXHAUSTED` 的落点**：实现只写返回值 `notes`（以及调用方 stdout）并即时停止；**未持久化到 `run_record`**（批次级无 run_record，成功导入的 run_record.notes 固定 `batch=ib_…`）。设计 §3/§11-1 允许“批次审计文件、不入库”的通道，但验收时不能把“notes=BUDGET_EXHAUSTED”当作 DB 内可查事实——本次探针以返回值 + audit 断言行数/请求数确认。
2. **transport 异常时的状态语义**：返回 status=`partial`（results 含 failed 记录），同时 `wiring.record_failure` 写 `run_record(status='failed')`；“不得吞、不得当成功”成立，但 status 字段值需按代码实际（partial + failed run）记录。
3. **真实批次 `observed_at_source=import_time`**：driver 未显式传源观察时间，适配器按设计 §5 回退并标注；`observed_at_source='source'` 的真实路径本次**未验证**（仅离线 fixture 覆盖）。
4. **审计通道**：请求 URL/状态/outcome 写入 `run_dir/audit.jsonl`（不入库）；`run_record` 不新增 URL 列，符合设计 §7 边界。
5. **重试等待叠加**：timeout 重试实际等待 = `RETRY_WAIT_SECONDS(2s)` + 下一轮 `interval_seconds(5s)`（离线探针记录 sleeps=[2.0,5.0]）；未超过设计“一次重试”语义，但与“仅等 2 秒”的字面理解不同。
6. **诚实 UA/合规静态面**：`_USER_AGENT=local-selection-tool/1.0 (+offline research)`，无 cookie/referer/代理/伪造 UA/搜索接口；`_REAL_ROW_KEEP` 常量当前未被使用（代码整洁项，不影响行为）。
7. **证据文件编码事实**：既有 `10_stdout.txt` 带 UTF-8 BOM、`02_probe_stdout.txt` 为 UTF-16 LE（BOM）；读取时需 `utf-8-sig`/`utf-16`。不影响内容，但交付/复现时需注意。

## 7. 未验证项（不得当作已成立）

1. **样本规模**：仅 **2 个 bvid**、单批次、单端点（B 站详情 API）、单来源；字段稳定性/缺失字段/异常内容/长尾视频未验证。
2. **频控与风控**：真实仅 2 次请求（间隔 5s）；**412/-412、-101 登录、验证码、IP 限流、短时高频**均未在真实环境触发（仅离线分类测试）；未验证服务端频控阈值。
3. **长跑与异常恢复**：网络中断/DNS/TLS 失败、真实 timeout、批次超时 `TIMEOUT_STOP`、中断后续跑均未真实触发。
4. **源观察时间真实路径**：`observed_at_source='source'` 未验证（driver 未传）；`published_at` 与 `observed_at` 的区分仅在离线/设计层。
5. **批次级审计入库**：BUDGET_EXHAUSTED/stops 未入 `run_record`；notes 注入方案（入库）未实现验证。
6. **真实数据质量与 ABA**：内容变化/旧版本重见/去重版本链在真实数据上未验证（离线既有覆盖）。
7. **合规外部前置**：robots/条款检查、`source` 状态变更（保持 manual_import）、费用/配额台账均未接入。
8. **本轮未联网**（任务禁止）：无法独立复核服务器侧响应；真实性由既有 audit/DB/stdout 三方一致性与证据哈希支撑。

## 8. 结论

- **镜像/测试**：77 件 parity 0；`test_real_link` **10/10 OK exit=0**、完整 `discover` **263/263 OK exit=0**（与 B 宣称 10/263 一致）。
- **离线机制**：15/15 通过（授权 0 请求、预算耗尽、重试计入预算、transport 异常→失败 run、归一化三态、API URL/bvid、审计字段、无绕过静态面、导入 real 行）。
- **真实证据（既有）**：16/16 通过（2 real 候选/需求/证据、identity、observed_at/import_time、2 条 ok run_record、audit 2 条 5s 间隔与 API URL、stdout 201 ids 对应、diag 根因 gzip HTML）。
- **守护**：冻结三文件 + 业务库前后哈希一致、WAL/SHM 不存在、真实证据文件未被修改。
- **限定结论**：**“受控真实链路 2 个 bvid 样本成立”**（真实 API 200、授权/预算/间隔/审计机制与代码一致、落库 real 行与导入路径完整）；**字段稳定性、频控/风控、长跑/异常恢复、源观察时间真实路径等未验证（§7）**。**不宣称 S3 阶段完成或 “real 链路全面接通”**。

## 9. 证据索引与过程修正

| 证据 | 路径 |
| --- | --- |
| 前后守护（15 文件） | [00_guard_before.json](<../../tests/acceptance/_tmp/s3_real_verify_v1/run_20261020_154246_realverify/evidence/00_guard_before.json>) / [07_guard_after.json](<../../tests/acceptance/_tmp/s3_real_verify_v1/run_20261020_154246_realverify/evidence/07_guard_after.json>) |
| 镜像 parity | [01_mirror.json](<../../tests/acceptance/_tmp/s3_real_verify_v1/run_20261020_154246_realverify/evidence/01_mirror.json>) |
| 模块/DB 来源 | [02_path_probe.json](<../../tests/acceptance/_tmp/s3_real_verify_v1/run_20261020_154246_realverify/evidence/02_path_probe.json>) |
| 单测/全量日志 | [03_test_real_link_cmd.log](<../../tests/acceptance/_tmp/s3_real_verify_v1/run_20261020_154246_realverify/evidence/03_test_real_link_cmd.log>) / [04_discover_cmd.log](<../../tests/acceptance/_tmp/s3_real_verify_v1/run_20261020_154246_realverify/evidence/04_discover_cmd.log>) |
| 离线探针（15 断言） | [03_probe_real_link.json](<../../tests/acceptance/_tmp/s3_real_verify_v1/run_20261020_154246_realverify/evidence/03_probe_real_link.json>) |
| 真实证据核验（16 断言） | [04_probe_real_evidence.json](<../../tests/acceptance/_tmp/s3_real_verify_v1/run_20261020_154246_realverify/evidence/04_probe_real_evidence.json>) |
| 证据文本读回 | [08_evidence_readback.txt](<../../tests/acceptance/_tmp/s3_real_verify_v1/run_20261020_154246_realverify/evidence/08_evidence_readback.txt>) |

- **过程修正史（如实保留）**：我方探针首轮有 5 处口径/实现问题，均已保留失败件并修正重跑：① transport 异常状态实为 `partial`（非 failed）；② `observed_at` 为 `+08:00` 格式（非 Z）；③ 同一 fixture 内容换 bvid 会命中 `suspect_review`（改为按 bvid 生成不同内容）；④ 探针 run 目录复用导致 audit 追加（改为每用例清理）；⑤ 既有证据 `10_stdout.txt` 带 UTF-8 BOM、`02_probe_stdout.txt` 为 UTF-16 LE、meta 中 7 位小数秒（Python 3.10 不接受）——均为读取口径，不影响被验实现。失败件见 `*_attempt1_*.{json,log}`。
- 本轮**未发起网络请求、未启动服务、未改任何文件**（guard 前后 15 文件哈希全等、业务库不变、证据文件未改）；结论仅限本复核与上述哈希；**不宣称 S3 阶段完成**。
