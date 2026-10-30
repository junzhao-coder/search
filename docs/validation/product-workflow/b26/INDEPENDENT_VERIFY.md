# B26 独立核验：B21–B25 一致性与真实性

> 任务：`task-2b723b8f31e275a05007fcb9e4eb35a0`（v8 独立核验；只写 b26）。
> 结论：**PASS（一致性/真实性/测试/哈希）**；2 个**文档/状态 WARN**（`/copy` 链接/已售为发布后条件显示；B24 反馈表建议路径写 b24，实际 b25）。p1–p4 均未达成，不得标为完成。

## 1. verify-consistency（逐项）

| # | 检查 | 结果 | 证据/说明 |
| --- | --- | --- | --- |
| ① | 三栏导航仅选品/选源/起草介绍；根入口进选品 | **PASS** | `/` 302 `/pick`；`/pick` 200、`/source?wo=…` 200、`/copy?wo=…` 200；三页 `nav[aria-label=主导航]` 均只有三项，旧 8 个标签不在 nav；HTML `logs/{pick,source,copy}.html` |
| ② | `/pick` “继续已有工作单”与 wo 链接 | **PASS** | `继续已有工作单` 存在；`/source?wo=`、`/copy?wo=`、`wo:20261023-88ef9a66` 均存在（`page_probe.json`） |
| ③ | B23 清单 5 点 + 三选一 + 停止条件 | **PASS** | `PLATFORM-CHECKLIST.md` 5 个 `### ①…⑤`；`PLATFORM-DECISION.md` A/B/C 三选一，3 个“停止条件”（`doc_check.json`） |
| ④ | B24 发布卡 8 步、反馈卡 12 字段、/copy 指引 | **PASS（带 W-DOC）** | `PUBLISH-CARD.md` 8 个“第 1–8 步”；`FEEDBACK-CARD.md` 12 个字段名；`/copy` 含 `platform_evidence`、`发布回填`、`PUBLISH-CARD.md`/`FEEDBACK-CARD.md`、不代发提示。W-DOC：生产未发布时 `/copy` 只显示“未发布”，链接/已售需有 `workorder_publish` 才渲染 |
| ⑤ | B25 反馈表 12 列、synthetic、review.py 可运行 | **PASS** | CSV 12 列、2 行，备注均含 `synthetic`；`review.py` 默认/`--json` 均 exit=0（`review_default.log`/`review_output.json`）；B25 6 单测 exit=0 |

- 导航实际截图/HTML 显示：`/pick` 无 wo 时“选源/起草介绍”是 disabled span，带 wo 后为链接；仍只有三项，符合 B21。
- B24 REPORT 说 `/copy` “显示状态、链接与已售数”；实际 `views_wizard.py:294-296` 是 `if publish` 才显示链接/已售，生产单未发布所以只显示“未发布”。这是**状态条件**，不是伪造；W-DOC 已记录。

## 2. verify-truth（真实运行与独立复算）

### 2.1 review.py 默认与 JSON

命令（cwd `docs/validation/product-workflow/b25`）：

- `python -X utf8 review.py feedback-log.csv` → exit 0；输出：询单 10 / 成交 2 / 退款 0 / 到手 35.82 / 耗时 240；四指标 **20.0% / 17.91 元 / 4.48 元/小时 / 0.0%**；建议 **【提价】**。
- `python -X utf8 review.py feedback-log.csv --json` → exit 0；结构化字段齐全（`review_output.json`）。

### 2.2 独立复算（不调用 review.py）

| 指标 | 独立公式/值 | 脚本值 | 一致 |
| --- | --- | --- | --- |
| 询单转化率 | 2 ÷ 10 × 100 = **20.0** | 20.0 | 是 |
| 单件到手 | 35.82 ÷ 2 = **17.91** | 17.91 | 是 |
| 单件净利 | 17.91 − 0 − 0 = **17.91** | 17.91 | 是 |
| 折算时薪 | 17.91 ÷ (240 ÷ 60) = **4.48** | 4.48 | 是 |
| 退款率 | 0 ÷ 2 × 100 = **0.0** | 0.0 | 是 |

`recompute.json`：`all_match=true`；建议 `提价`（时薪 4.48 < 30 且净利 >0）。CSV 两行均 `synthetic`，不是真实经营数据。

### 2.3 夸大/保证性表述

`page_probe.json` 搜索 `保证|包过|必过|稳赚|过审|收益`，命中 6 处，均为：

- “没有‘包过/稳赚/官方’这类词”（禁止词提示）；
- “不代表一定过审”“不等于平台结论，也不代表收益”“建议 ≠ 平台结论，≠ 收益保证，≠ 审核结果”；
- “保证一次只给一条建议”（实现约束，不是收益承诺）。

**未发现“保证过审/保证收益”的承诺性表述**。B24/B25 均明确平台审核由平台决定、脚本不给结论背书。

## 3. tests

| suite | cwd | UTC | exit | Ran/OK |
| --- | --- | --- | --- | --- |
| b25 review 单测 | `docs/validation/product-workflow/b25` | 12:43:44–12:43:45 | 0 | 6 / OK |
| workbench_all | `tools/workbench` | 12:44:30–12:45:02 | 0 | **213** / OK |
| project_full | 仓库根 | 12:45:02–12:46:22 | 0 | **334** / OK |

- 日志：`logs/{b25_tests,workbench_all,project_full}.log`，均含 argv/cwd/UTC/returncode。
- B21/B22/B23/B24 的既有测试/证据保留在各自目录；本轮按要求只复跑工作台全套与原项目全套，另跑 B25 六例。

## 4. hashes / isolation

- `guard_compare.json`：10 个文件与 B14 基线 **10/10 same**：
  - `instance/app.db e073f828…`、`CONTRACT 826c24cc…`、`scoring/scores.csv ab0c3546…`、`sourcing/{sources,price_signals}.csv`、wiring/bilibili_view/importer、migrations 2 文件；wal/shm=false。
- 生产工作单库 `workorder 8ae79c58…`；B26 只读，无 POST。
- `b26/tmp` 空；只写 b26；未改工作单数据/业务库/契约。

## 5. stage-close 要点

- **B21–B25 已完成**：三栏导航、`/pick` 继续区块、B23 清单/决策模板、B24 两张卡、B25 反馈表/复盘脚本（详见 `STAGE-CLOSE.md` 第一表）。
- **p1–p4 均未达成**：真实类目/资质未核、未手动发布/回填、无真实反馈、复盘仅 synthetic 机械结果。
- 用户待办 4 项：**看类目并登记结论 → 手动发布并回填 → 记录真实反馈 → 跑复盘得结论**；未完成前不得标 p1–p4 达成。
- 生产仍 6/7（`platform_evidence` 空）、导出 409、未发布。

## 6. WARN / 限制

1. **W-DOC `/copy` 链接/已售**：生产单未发布，页面只显示“未发布”；`views_wizard.py:294-296` 在 `publish` 存在时才显示链接/已售。B24 REPORT 的“显示链接与已售”应理解为发布后。
2. **W-DOC 反馈表路径**：`FEEDBACK-CARD.md` 建议 `b24/feedback-log.csv`；实际交付在 `b25/feedback-log.csv`（`doc_check.json`），属路径文档小不一致。
3. **synthetic**：B25 两行均虚构；单件净利 17.91 是参数 0 的机械结果，不是真实利润。
4. **样品自检结构限制**：PDF 仅头、xlsx 仅结构计数；`verified` 不等于全面验货/授权/可渲染。
5. **未做**：平台登录/发布/采购、真实经营数据、多期趋势、恶意宏、并发；B25 采购/摊销需用户参数。
6. `/copy` 的 `platform_evidence` 是证据入口，不代表平台批准；生产 6/7 是设计阻断。

## 7. 证据

- [page_probe.json](page_probe.json)、`logs/{pick,source,copy}.html`
- [doc_check.json](doc_check.json)
- [review_output.json](review_output.json)、[recompute.json](recompute.json)
- [review_default.log](logs/review_default.log)、[review_json.log](logs/review_json.log)
- [b25_tests.log](logs/b25_tests.log)、[workbench_all.log](logs/workbench_all.log)、[project_full.log](logs/project_full.log)
- [guard_compare.json](guard_compare.json)
- [STAGE-CLOSE.md](STAGE-CLOSE.md)
