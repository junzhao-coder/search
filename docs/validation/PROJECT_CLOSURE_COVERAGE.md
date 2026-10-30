# 项目收口判据覆盖核验（p1/p2/p3/p8/p9）

> 目的：项目完成候选被拒，因 p1/p2/p3/p8/p9 在计划 v3 下缺少小目标证据覆盖；本批由独立执行者 A **只读**核验既有证据是否仍完好、未被改动/伪造，逐项给出「判据 → 文件/哈希 → 结论 → 缺口」。
> 范围：`docs/validation/PROJECT_CLOSURE_COVERAGE.md` + run 证据；**未改被核验文件/代码/契约/业务库/备份/旧证据，未联网、未起端口**。
> 复核 run：`tests/acceptance/_tmp/project_closure_v1/run_20261020_214906_closure/`（`evidence/{01_hashes,10_p1,11_p2,12_p3,20_p8,21_p9,30_report_checks}`）
> 方法：sha256 只读文件哈希（103 文件 before/after 全等，`wal=False shm=False`）；S2 快照清单逐条校验；S3 real 证据只读复算（audit/batch_result/隔离 DB `mode=ro&immutable=1`）；app/ AST 静态扫描（导入/调用/标识符/路由，字符串与注释单列为文档）；验收报告抽样；Flow `view=plan` 读取计划确认信息。

## 0. 总表

| 判据 | 结论 | 关键证据 | 缺口/说明 |
| --- | --- | --- | --- |
| **p1** 计划 v3 已确认 + CONTRACT 未改回 | ✅ | 计划 v3 `confirmedAt=1792495145757`；CONTRACT 812 行 sha `826c24cc…` 未变 | 无 |
| **p2** S0/S1/S2 基线 + 合成最小闭环证据与历史一致 | ✅（⚠️ 1 项历史口径） | S2_ACCEPTANCE 174 行 sha `be43bb02…`；新快照 `s2d_20261013_fix1` 55/55 文件哈希全对、清单 `e1578b05…`、树哈希 `3a0d3283…` 与报告一致；旧快照清单 `2c8b76b8…` 55/55 文件全对 | 旧快照报告树哈希 `1808beb5…` 无法由现有清单复算（复算 `84f4a47c…`）；旧快照目录含 131 个清单外 `__pycache__/_tmp` 副产物——**历史口径不一致，记录为缺口**，不影响新快照/文件完整性 |
| **p3** 真实来源自动链路有独立运行证据（2 bvid） | ✅ | real_link 409 行 sha `46cbd635…`；S3_REAL_RUN_FINAL_VERIFY 98 行 `cfd56e35…`；real3 14 文件；batch ok/2/2、audit 2 行均 200/ok/间隔 5.0s、DB sha `7a4ed405…`、2 real 候选/需求/证据、2 条 ok run_record(items_new=1)、2 committed import_batch | 仅 2 bvid 单批；真实频控/长跑/并发未验证、observed_at_source=import_time（报告已如实记录） |
| **p8** D01–D11 边界（不自动发布/联系/采购/付款；无付费新增；证据纪律） | ✅ | 31 个 app py AST 扫描：0 forbidden imports、0 automation calls、0 禁止路由、0 interaction 标识符、0 dangerous calls；28 路由=24 API+4 页面，无 publish/contact/purchase/payment 端点；requirements 仅 `flask==3.1.3`；app 内 URL 仅 bilibili 受控 API + `example.org` 合成样例；80 处 token 仅出现在字符串/注释（如"无发送"说明） | D02（100 元/月）为文档约束、无代码强制；无支出/付费记录（S3 2 bvid 免费 API）；"模型/互动量不作证据"由代码不含互动字段评分 + 报告声明支持，非运行时强制 |
| **p9** 证据纪律（真实 exit、UTF-8 命令行/时间、限制/UNEXECUTED、不超证据宣告） | ✅（⚠️ 1 处格式） | 抽样 5 份报告 hash/行数全对，均含 exit、UTC/时间、限制段、不宣称；S7 CURRENT_STATUS 明确"暂未验证盈利/0 条真实记录/未发布未联系未采购未付款"，模板 CSV 仅表头 | S3_REAL_RUN_FINAL_VERIFY 未内嵌 `cwd=`（引用日志路径而非内联记录）——格式缺口记录；`docs/validation` 中 UNEXECUTED 2 处、未覆盖/未执行/未验证 23 处、不宣称 16 处，均保留 |

## 1. p1：计划 v3 与 CONTRACT

- Flow `view=plan`：`version=3`、`confirmedAt=1792495145757`（2026-10-20 计划确认）；计划正文为「开发计划 v3（重建推进链路，延续 v2 已确认范围）」，范围/纪律与本次核验一致。
- CONTRACT：`docs/design/CONTRACT.md` **812 行**、sha256 `826c24cc6c99551178875bed617e085231bd23998b6a049f396116e1e70fb4f9`，与冻结值一致（未改回）。
- 结论：**p1 ✅**。

## 2. p2：S0/S1/S2 既有验收证据

- 文档链：[ACCEPTANCE.md](<../design/ACCEPTANCE.md>)、[S2_CORE.md](<../design/S2_CORE.md>)、[S2_RUNTIME.md](<../design/S2_RUNTIME.md>)、[S1_REVIEW.md](S1_REVIEW.md)、[S1_REVIEW_REVISED.md](S1_REVIEW_REVISED.md)、[S2_ACCEPTANCE.md](S2_ACCEPTANCE.md)、[S2_B1_REVIEW.md](S2_B1_REVIEW.md) 均存在且哈希已记录（见 `01_hashes/before.json`）。
- S2 验收报告：[S2_ACCEPTANCE.md](S2_ACCEPTANCE.md) **174 行**、sha `be43bb0298e42f63983441eeb363671b2d549c012934814b0f1d27605630eb7f`（与预期一致）；覆盖导入→去重→证据→四项门槛→情景→草稿→反馈链路。
- 冻结快照：
  - 新快照 `s2d_20261013_fix1`：清单 55 条**逐条 sha 校验 55/55 通过**、0 mismatch/0 missing；清单文件 sha `e1578b05…` 与报告一致；树哈希复算 `3a0d3283…` **与报告一致**；目录 55 文件=清单（无额外文件）。
  - 旧快照 `s2d_20261009_231628`：清单 55 条**逐条校验 55/55 通过**、0 mismatch；清单文件 sha `2c8b76b8…` 与报告一致；**树哈希复算 `84f4a47c…` ≠ 报告 `1808beb5…`**（旧目录实含 186 文件，131 个清单外 `__pycache__/_tmp` 副产物，属历史口径/副产物问题）。
- 冻结代码/迁移哈希（importer `a11eaf4d…`、wiring `bafcf397…`、bilibili_view `b0dc0ced…`、迁移 0001/0002）均与既有记录一致。
- 结论：**p2 ✅（新快照/报告/冻结文件完好；旧快照树哈希为历史口径缺口 ⚠️）**，不影响 S2 最小闭环证据成立，但**旧树哈希值不应再作为规范基准**。

## 3. p3：S3 受控 real 运行证据

- 代码：[real_link.py](<../../app/sources/real_link.py>) **409 行**、sha `46cbd635b5e70cc2d1b6441befde31e25b8203caf28d39b772203c43b8f5802c`（冻结版）。
- 报告哈希：S3_REAL_RUN_FINAL_VERIFY.md 98 行 `cfd56e35…`、S3_REAL_LINK_HARDENING_VERIFY2.md 92 行 `d8c06c8f…`、S3_REAL_LINK_HARDENING_VERIFY.md 135 行 `effdb24d…`、S3_REAL_LINK_ACCEPTANCE.md 119 行 `56d73670…`——均与预期一致。
- 运行证据（`tests/sources/_tmp/real_run_v2/run_20261020_190634_real3/`，**14 文件**）：`batch_result` status=ok、requests=2、imported=2、batch_id=`user-authorized-real-3`、目标 `BV1us8MzPEmn`/`BV1GJ411x7h7`；audit 2 行均 `http_status=200/outcome=ok`、间隔 **5.0s**；隔离 DB sha `7a4ed4056874071a2c23d35a259e5bc7a201c77b8bbdeb0ecb57f0a70224d4bc`，`candidate/demand_signal/evidence` 各 2 行且 `data_origin='real'`，`run_record` 2 条 ok（items_new=1）、`import_batch` 2 条 committed；`10_result` 的 2 个 candidate id 与 DB 一致。
- 结论：**p3 ✅**（2 bvid 单批证据可回溯、未改动）；缺口：真实频控/412/长跑/并发/断点/字段稳定性未验证，`observed_at_source=import_time`（报告已记录，不宣称 S3 阶段全部完成）。

## 4. p8：D01–D11 代码边界扫描

- 扫描 31 个 `app/**/*.py`（AST）：**0** 禁止导入（requests/httpx/aiohttp/smtplib/websocket/selenium/subprocess/stripe/paypal 等）、**0** 自动化调用（publish/contact/purchase/pay/send 等）、**0** 禁止路由、**0** 危险调用（eval/exec/os.system/popen）、**0** ranking/scenario/daily 互动标识符（like/view_count/play/fans…）。
- 网络导入：`urllib.parse`（identity/bilibili_view，仅解析）与 `socket/urllib.request/urllib.error`（**仅 real_link.py**）；app 内 URL 仅 `api.bilibili.com` 受控详情 API 与 `example.org` 合成样例域。
- 路由：共 **28**（24 API + 4 页面），逐条扫描无发布/联系/采购/付款/下单/发送端点；草稿仅 `draft/final` 状态、无发送动作。
- 依赖：`requirements.txt` 仅 `flask==3.1.3`（无付费 SDK/新依赖）；80 处自动化相关 token **仅出现在字符串/注释**（如"无发送端点""平台政策"等说明文本，非调用）。
- 结论：**p8 ✅（代码层）**；D01–D11 对照 CONTRACT §8（L788–802）无代码违规。缺口：D02 月度 100 元为文档级约束、无代码/账单强制；无真实支出记录（S3 2 bvid 使用免费公开 API）；"模型输出/互动量不作成交/净收益证据"由代码不含互动评分与报告声明支持，**无运行时强制**。

## 5. p9：近期报告与证据纪律抽样

- 抽样 5 份报告（hash/行数均匹配）：S3_REAL_RUN_FINAL_VERIFY（98 行 `cfd56e35…`）、S6_BACKUP_RESTORE_ACCEPTANCE（102 行 `b1adf907…`）、SUMMARY_DAILY_ACCEPTANCE（104 行 `6ade26c1…`）、P6_REAL_DRILL_ACCEPTANCE（99 行 `ffaa848e…`）、C_EXPORT_ACCEPTANCE（78 行 `387c1886…`）。
- 内容检查：5/5 含真实 exit 码、UTC/时间、限制/未覆盖段、"不宣称/仅"措辞；4/5 内嵌 `cwd=`（S3_REAL_RUN_FINAL_VERIFY 引用日志路径而未内联，记录格式缺口）。
- 全 `docs/validation`：UNEXECUTED 2 处、未覆盖/未执行/未验证 23 处、不宣称 16 处（未执行项保留，未改写）；[S7 CURRENT_STATUS.md](<../s7/CURRENT_STATUS.md>) 明确"暂未验证盈利 / 真实经营记录 0 条 / 未发布未联系未采购未付款"，[OPERATING_LOG_TEMPLATE.csv](<../s7/OPERATING_LOG_TEMPLATE.csv>) 仅表头。
- 结论：**p9 ✅（⚠️ S3 报告 cwd 内嵌格式缺口）**。

## 6. 前后哈希与不修改声明

- **103 个文件 before/after sha256 完全一致**（含 CONTRACT、app 全部 py、docs/validation 全部、docs/design、S2 快照清单、S3 运行证据、S7 文档、requirements、业务库 `instance/app.db` `e073f828…`、备份+清单）；`wal=False shm=False`；业务库/备份目录未变。
- 本次复核**未修改**任何被核验文件、代码、契约、业务库、备份、旧证据；仅新增本报告与 `tests/acceptance/_tmp/project_closure_v1/` 证据目录；未联网、未起端口。
- 证据 UTF-8 无 BOM/LF（21 文件读回 exit=0）；各步骤日志含 `label/cwd/start_utc/exit`。

## 7. 结论与真实缺口

- **p1 ✅ / p2 ✅（旧快照树哈希 ⚠️）/ p3 ✅（限 2 bvid 单批）/ p8 ✅（代码+文档，D02 无强制）/ p9 ✅（S3 报告 cwd 格式 ⚠️）**；五项的既有证据在本次只读核验下**未被改动、可复算**。
- 已知缺口（与计划/既有报告一致，不因本报告消失）：
  1. 业务库仅 synthetic 示例数据（P6 复核 `e073f828…`，real 0 行），**不能作为真实经营/真实数据恢复证据**；
  2. S5 定时触发/提醒/真实工作流未实现（UNEXECUTED 保留）；
  3. 真实切换/回滚、真实端口启动未执行（仅 test_client/隔离副本）；
  4. S7 无真实经营记录，结论仅"暂未验证盈利"；
  5. S3 仅 2 bvid 单批样本（频控/长跑/并发/断点/字段稳定性未验证、observed_at_source=import_time）；
  6. 旧 S2 快照树哈希与现有清单不一致（历史口径），旧快照目录含 131 个清单外副产物；
  7. S3_REAL_RUN_FINAL_VERIFY 未内嵌 cwd（引用日志路径）。
- **本报告不宣称项目全部完成**；仅证明 p1/p2/p3/p8/p9 的既有证据仍可追溯、未被改写，并列出上述真实缺口供策划者裁定。

## 8. 证据索引

| 证据 | 路径 |
| --- | --- |
| 前后哈希（103 文件 before/after） | [before.json](<../../tests/acceptance/_tmp/project_closure_v1/run_20261020_214906_closure/evidence/01_hashes/before.json>) / [after.json](<../../tests/acceptance/_tmp/project_closure_v1/run_20261020_214906_closure/evidence/01_hashes/after.json>) |
| p1 计划/CONTRACT | [plan_and_contract.json](<../../tests/acceptance/_tmp/project_closure_v1/run_20261020_214906_closure/evidence/10_p1/plan_and_contract.json>) |
| p2 快照清单逐条校验 | [snapshot_manifests.json](<../../tests/acceptance/_tmp/project_closure_v1/run_20261020_214906_closure/evidence/11_p2/snapshot_manifests.json>) |
| p3 real 证据复算 | [real_evidence.json](<../../tests/acceptance/_tmp/project_closure_v1/run_20261020_214906_closure/evidence/12_p3/real_evidence.json>) |
| p8 AST 代码扫描 | [code_scan.json](<../../tests/acceptance/_tmp/project_closure_v1/run_20261020_214906_closure/evidence/20_p8/code_scan.json>) |
| p9 报告抽样 | [report_checks.json](<../../tests/acceptance/_tmp/project_closure_v1/run_20261020_214906_closure/evidence/21_p9/report_checks.json>) |
| 汇总 | [closure_summary.json](<../../tests/acceptance/_tmp/project_closure_v1/run_20261020_214906_closure/evidence/30_report_checks/closure_summary.json>) |
| 证据读回 | [08_evidence_readback.txt](<../../tests/acceptance/_tmp/project_closure_v1/run_20261020_214906_closure/evidence/08_evidence_readback.txt>) |
