# tests/dash 评分数值解耦与评分产物只读核对（计划 v6）

> 任务：`task-0093effe570db1ba5d3cb7ed85bd5584`（revision 2，计划 v6）；执行者 session-01ba487c…。
> 范围：`tests/dash`、`docs/validation/money-project/scoring-closeout`；其它路径只读。未改 scoring/scorer.py、model.md、scores.csv、sources.csv、业务库/CONTRACT/迁移/冻结文件。
> 采样：2026-10-22 11:38–11:40 UTC（19:38–19:40 UTC+8）；证据 UTF-8 无 BOM，命令/cwd/UTC/真实 exit 见 `logs/`。
> **结论：测试已改为 tempfile 隔离 root（自造 scores.csv + sources.csv），全量 `Ran 334 tests / OK / exit=0`；七维产物只读核对通过，唯一记录项是 model.md 3.5 只显式写“旧六维 0.85”、未字面写 sellability 0.15（数学等价，不构成实现矛盾）。**

## 0. 状态表

| 类别 | 结论 | 要点 |
| --- | --- | --- |
| fix | **PASS** | 仅改 `tests/dash/test_routes.py` 的 `test_opportunities_shows_model_rows_and_links`：临时 root + 自造 scores/sources，断言派生分数/链接；未动其它断言 |
| test | **PASS** | 全量 `Ran 334 tests / OK / exit=0`（APP_DB_PATH 临时库）；日志 `logs/full_suite_utf8.log` |
| consistency | **PASS（1 个文档提示）** | 权重合计 1.0；scores 60 行 sellability_norm 0.1–0.95；rank 1..60 与 total_score 降序一致；model 3.5 与实现一致 |
| limits | 见 §4 | model 未字面写 0.15；测试 fixture 为最小合成样本；未重跑真实评分；全量有既存 ResourceWarning |

## 1. fix：只解耦评分数值断言

- 修改文件：`tests/dash/test_routes.py`（当前 163 行、7,397 B、sha256 `cd925fcb…`；修改前 121 行、5,250 B、sha256 `e269f021…`，备份 `before_test_routes.py`）。
- 改动仅 `test_opportunities_shows_model_rows_and_links`：
  - 在 `self.tmp` 下创建隔离 `data_root`，写入 `<root>/docs/validation/money-project/scoring/scores.csv` 与 `<root>/docs/validation/money-project/sourcing/sources.csv`（最小列集，符合 `app/dash/data.py` 读取逻辑）。
  - scores.csv 固定合成值 `total_score=0.812`、`url=https://example.test/isolated-opportunity`、标题 `isolated fixture opportunity`；sources.csv 固定 `fixture-src`/`https://example.test/source`。
  - `create_app({"db_path": <tmp>/fixture.db, "DASH_DATA_ROOT": <tmp>})` 后：
    - `/dash/opportunities` 断言页面含 `机会榜`、合成标题、**由合成 CSV 派生并格式化后的 `0.812`**、合成链接；
    - `/dash/sources` 断言含 `fixture-src` 与合成 source 链接（验证 sources.csv fixture 可用）。
  - **不再引用** `tests/dash/_fixtures/opportunities_data`，也不再从真实 `scores.csv` 取榜首；没有硬编码 `0.800`，也没有把真实值 `0.763534` 写进断言。
- 其它已有断言（数据来源、文件更新时间、机会榜标题、许可三档、价格口径、缺文件降级、坏 JSONL、health）保留；新测试仍 9/9 通过。
- 真实 CSV 未复制/未重生成；static `_fixtures/opportunities_data` 仅留作历史文件，当前测试路径不使用。
- Diff：`diff.patch`（76 行 unified diff，仅 `tests/dash/test_routes.py`）。

## 2. test：完整套件

命令（cwd=`D:\桌面\two`；`APP_DB_PATH` 指向临时库）：

```powershell
$env:APP_DB_PATH = "$env:TEMP\dash_full_95ab417c...db"
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

- 日志 `logs/full_suite_utf8.log`：`start_utc=2026-10-22T11:38:53+00:00`、**exit=0**、`Ran 334 tests in 51.089s`、`OK`。
- 目标文件单独复跑：`tests.dash.test_routes` **9/9 OK**（改后）。
- 说明：修改前本工作树的全量也已是 `Ran 334 / OK`（当时的静态 fixture 已不再断言 `0.800`）；本次改动重点是把静态 fixture 换为任务要求的 tempfile 隔离 root + scores/sources 双文件，避免再次依赖真实数据，同时保持全绿。
- 全量日志含既存 `ResourceWarning: unclosed file ...app/static/*`（不影响 OK/exit=0）；未改相关静态资源。

## 3. consistency：七维产物只读核对

脚本 `tools/consistency_check.py`（stdlib ast/csv/json/math；只读），输出 `consistency.json`；日志 `logs/consistency_check.log`，exit=0。

| 检查 | 结果 |
| --- | --- |
| `WEIGHTS` 权重合计 | **1.0**（`0.255+0.17+0.17+0.085+0.085+0.085+0.15`） |
| 旧六维合计 / sellability | 旧六维 **0.85**、sellability **0.15** |
| model.md §3.5 | 存在（82–96 行），含可售性/sellability 与“旧六维按 0.85 缩放”；与实现一致 |
| scores.csv 行数 | **60** |
| sellability 列 | `sellability_raw/norm/weighted/reason` 均存在 |
| `sellability_norm` 范围 | min 0.1 / max 0.95，全部在 `[0,1]`；越界 0 行 |
| `sellability_weighted` | 60 行均与 `0.15*norm` 一致（容差 1e-5） |
| rank / total_score | rank 1..60 连续；按 rank 升序 total_score **无逆序**；并列 item_id 顺序无问题 |
| 结果 | `ok=true`；**唯一提示**：model.md §3.5 未字面写“0.15”，只写“旧六维 0.85”；0.15 为数学上隐含，不是实现矛盾，未改文档 |

- 源文件当前 sha（只读）：scores.csv `ab0c3546…`（37,342 B）、sources.csv `13679b60…`（5,488 B）、scorer.py `4e105acf…`（21,338 B）、model.md `76375313…`（7,951 B）。
- 测试前后产品 hash 对比：`hashes.json`（测试前）与 `product_hashes_after.json`（测试后）**4/4 相同**；未重生成/复制真实 CSV，未修改 scorer/model。

## 4. limits

1. model.md §3.5 只显式写“旧六维按 0.85 缩放”，没有字面写 sellability 0.15；本次按数学等价判为一致并记录文档提示，未改文档。
2. 测试 fixture 是最小合成样本，仅验证页面渲染/读取路径，不覆盖真实 60 条评分的分布；真实 CSV 未重算、未改动。
3. 全量套件有既存 `ResourceWarning`（静态资源未关闭）；不影响 `Ran 334 / OK / exit 0`，未在本次范围修复。
4. 未运行 workbench UI 任务（`task-77c67de0`，另一范围）；未跑真实采集/评分重生成；未改业务库/CONTRACT/迁移/冻结文件。
5. 未改 scoring/scorer.py、model.md、scores.csv、sources.csv 或 tools/workbench/start_workbench.cmd。

## 5. 证据索引

| 证据 | 路径 |
| --- | --- |
| 全量测试真实 exit | [full_suite_utf8.log](logs/full_suite_utf8.log) |
| 改动 diff | [diff.patch](diff.patch) |
| 修改前测试副本 | [before_test_routes.py](before_test_routes.py) |
| 一致性结果 | [consistency.json](consistency.json)（日志 [consistency_check.log](logs/consistency_check.log)） |
| 测试前后产品 hash | [hashes.json](hashes.json) / [product_hashes_after.json](product_hashes_after.json) |
| 校验脚本 | [consistency_check.py](tools/consistency_check.py) |
