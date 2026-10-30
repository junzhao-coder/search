# V9-2 实现报告：规则版品类台账 + 方向卡 + 复核队列

> 任务：`task-bab4c261d53b877fb2be2479acbea17f`（revision 2，计划 v9）；范围仅 `tools/selection/`、`docs/validation/v9/impl/`、`tests/test_selection_categories.py`、`tests/test_selection_rounds.py`。
> 工作区 `D:\桌面\two`；实现/测试时间 2026-10-25 19:08–19:12 UTC+8（11:08–11:12Z）。仅标准库；无 LLM/embedding/向量库/依赖/UI。

## 1. schema（v2 追加，旧 signals/runs 语义不变）

| 表 | 字段 | 代码 |
| --- | --- | --- |
| `categories` | id, identity_key UNIQUE, audience, task, deliverable_family, locale, canonical_label, status(active/merged/excluded), merged_into, created_at | `db.py` SCHEMA_SQL |
| `category_alias` | id, category_id, alias_norm, created_at, source；`UNIQUE(category_id, alias_norm)` | 同上 |
| `discovery_event` | id, category_id, kind(new/update/merge/split/exclude/include/undo), signal_id, before_json, after_json, at, undo_of | 同上 |
| `direction_card` | id, category_id UNIQUE, audience, task, deliverable, evidence_ids_json, gaps_json, status(draft/confirmed/rejected), created_at | 同上 |
| `review_queue` | id, signal_id, reason, candidate_category_id, status(pending/accepted/rejected), created_at | 同上 |

- 迁移：`models.SCHEMA_VERSION=2`；`init_db` 幂等插入 v1/v2 两条 `schema_migrations`；旧 `signals/runs` 不变。
- 事件不硬删：merge 保留 source 行 `status=merged`/`merged_into`；exclude/include/undo 只追加事件。

## 2. identity / alias / review

- `identity_key = sha256(canonical_json({audience,task,deliverable_family,locale}))`，**不含 platform/title/format/carrier**；`categories.identity_key UNIQUE`。
- 规则推断：`AUDIENCE_RULES/TASK_RULES/FAMILY_RULES` 关键词表；推断不出写 `unknown`；`locale` 由 CJK/拉丁启发式；见 `categories.py:14-45`。
- 合并条件：**exact identity_key** 或 `category_alias.alias_norm` 命中；否则：
- **alias 限制**：当前 `category_alias` 只支持人工插入；没有自动学习/自动同义归并。相似但未合并的信号只进 `review_queue`，不自动生成生效 alias；如未来做“建议别名”，必须标注建议、不自动生效。
  - **严格可证**：`task` 与 `deliverable_family` 同时已知，且 `audience` 或 `locale` 至少一个已知 → **new category**；任一为 `unknown` 的组合（如 student/design_assets/unknown）→ **review_queue**，不建品类；
  - 字段不足/字符串相似 → `review_queue`，用 `difflib.SequenceMatcher` 只给候选，不自动合并；`categories.py:72-116`。
- 平台/标题/格式变化：identity_key 不含这些字段 → 同 key update；旧品类新证据 → `discovery_event(update)`，不新建。
- 排除可恢复：`exclude` 置 excluded，`include`/`undo` 恢复 active；merge/split 均写事件，`undo` 依 `before_json` 反向。

## 3. events（merge/split/exclude/include/undo）

- `merge(source→target)`：source `status=merged`、`merged_into=target`；事件保留 before/after；evidence/alias/card 关联迁到 target，不硬删 source。`categories.py:147-166`。
- `undo(merge)`：source 恢复 active、merged_into 清空；事件/别名/卡迁回 source；追加 `undo` 事件。`categories.py:169-196`。
- `split(category, signal_ids)`：新建子品类，选中信号事件迁到子品类，追加 split 事件；`undo` 只写反向事件，不删除历史。
- `exclude/include`：状态切换 + 事件；`undo` 依 before_json 恢复。`categories.py:199-235`。

## 4. direction_card

- 每个 active category 生成 1 张 draft 卡；`evidence_ids_json` 引用 signal id；`gaps_json` 显式列：
  - 全无价格→`price_unknown`；
  - 全无 wants→`wants_unknown`；
  - 只有闲鱼、无第二平台/评论→`comments_or_second_platform_unknown`；
  - 不编造价格/成交/评论数字。`categories.py:119-144`。
- 代表原话保留在 signal.quote；卡本身不复制全文，避免摘要冒充原文。

## 5. CLI（JSON 单行）

新增 `categorize` / `cards` / `ledger`：

```powershell
.\.venv\Scripts\python.exe -X utf8 -m tools.selection.cli --db <db> categorize
.\.venv\Scripts\python.exe -X utf8 -m tools.selection.cli --db <db> cards
.\.venv\Scripts\python.exe -X utf8 -m tools.selection.cli --db <db> ledger
```

- `categorize` 输出 `signals/new/update/review/categories/cards`；失败异常→2（沿用现有 CLI 退出码）。
- `split` 当前只迁移选中信号的事件并追加 split 事件；`undo(split)` 只写反向事件，不自动重建旧归属——这是本版最小语义，已在测试中验证“不硬删/可追加 undo”。
- `cards`/`ledger` 只读输出。

## 6. 两轮 synthetic 计数对照

`tests/test_selection_rounds.py`（tempfile DB）两轮共 14 条，覆盖：完全重复、跨平台同需求、同义改写（alias 单测）、同大类不同任务、旧品类新证据、排除后更新、新 family、unknown→review。

| 轮次 | 输入 | 预期 new | 预期 update | 预期 review | 预期 active 品类 | 实际 |
| --- | --- | --- | --- | --- | --- | --- |
| 第一轮 | 6 | 3 | 2（含完全重复/跨平台） | 1 | 3 | 3/2/1/3 |
| 第二轮 | 8 | 3（client_management、exam_countdown、designer resume） | 4（excel 更新、排除后更新、bilibili 更新、notion 更新） | 1 | 7 | 3/4/1/7 |
| 合计 | 14 | 6 | 6 | 2 | 7 | 6/6/2/7 |

> 说明：完全重复 signal #2 不写 discovery_event，因此事件数=13（非 14）；测试按“非重复信号均有事件”断言。

## 7. 真实 23 条

- 隔离合并库：`docs/validation/v9/impl/runtime/merged23.sqlite3`（从 bilibili 3 + xianyu 20 只读复制，未写源库）。
- 真实命令/exit（返工后严格门槛，`--explain`）：
  - `categorize`：`logs/real23_categorize_strict.log` **exit 0**；`{"signals":23,"new":6,"update":16,"review":1,"categories":6,"cards":6}`。
  - `cards`：`logs/real23_cards_strict.log` **exit 0**；6 张卡。`logs/real23_ledger_strict.log` exit 0。
- 结果：**23 条信号 → 6 个 active 品类、6 张 draft 卡、1 review、6 new + 16 update**；唯一 review 为 signal 14（student/design_assets/unknown，family 未知）。
- 品类（label）：student/study_planning/notion_template；designer/prompt_generation/prompt_pack；designer/resume_portfolio/design_asset_pack；designer/design_assets/design_asset_pack；student/prompt_generation/prompt_pack；creator/prompt_generation/prompt_pack。原 `student/design_assets/unknown` 已按严格门槛进入 review，不再建品类。
- gaps：卡 1 `price_unknown/wants_unknown`；其余卡 `comments_or_second_platform_unknown`（闲鱼样本无评论；B站 3 条全并入 notion 卡）。
- **样本极小，不代表市场需求**；wants 是兴趣代理，价格是展示价，不是成交。

## 8. 推断明细（--explain）

真实 23 条 `categorize --explain` 逐条输出 `signal_id/hits/fields/outcome/category_id`；完整 JSON 见 `logs/real23_categorize_strict.log`。摘要：

| 信号 | 四字段 | 落点 | 主要命中（节选） |
| --- | --- | --- | --- |
| 1–3 | student/study_planning/notion_template/zh | new + update×2 | 学习、notion、学习笔记模板、template |
| 4–5 | designer/prompt_generation/prompt_pack/zh | new + update | 设计、提示词、AI绘画、出图 |
| 6,8,10,15,17 | designer/resume_portfolio/design_asset_pack/zh | new + update | 简历、作品集、PSD、排版 |
| 7,9,12,13,19–23 | designer/design_assets/design_asset_pack/zh | new + update | 设计素材、矢量、logo、图标、PSD |
| 11 | student/prompt_generation/prompt_pack/zh | new | 学习、提示词、pdf/教程 |
| 14 | student/design_assets/**unknown**/zh | **review** | 模板/内容；family 无命中 |
| 16,18 | creator/prompt_generation/prompt_pack/zh | new + update | 视频、创作者、提示词、生图 |

- 噪声/误判风险：`designer` 词表会命中“平面/设计/PSD”等泛词；`task` 的 `design_assets:模板` 与 `resume_portfolio` 有重叠；因此 6 个品类里仍可能有过宽合并（例如 6/8/10/15/17 都落 resume_portfolio）。本报告不把这些词表结果当作市场需求结论。
- `alias` 只做人工精确匹配，不自动学习；相似候选只进 review。

## 9. tests / guards / limits

- 新增 `tests/test_selection_categories.py`（6 tests：identity/alias/review/merge/undo/exclude/include/cards/split/undo）与 `tests/test_selection_rounds.py`（1 test：两轮计数）。
- 全量 selection 测试：`logs/tests_selection_all.log` exit **0**，**Ran 25 tests ... OK**（18 旧 + 7 新），cwd `D:\桌面\two`，UTC 11:15:33Z。
- 未改 `app/`、`tools/workbench/`、既有 CSV/业务库/CONTRACT；未接 UI、未接 LLM/embedding、未加依赖。
- 未验证：第三平台、LLM 语义归并、imported 进业务核心、UI；真实样本仅 23 条，品类数不代表市场。
