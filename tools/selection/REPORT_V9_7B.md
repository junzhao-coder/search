# V9-7b 实现报告：merge 原子/卡片冲突、undo 精确还原、split undo、坏行不整批失败

> 任务 `task-4a45996ce927d1041e232b7d1f409dd1`（rev2，计划 v9）；范围 `tools/selection`、`tests`。
> 2026-10-25 21:25–21:29 UTC+8。未装依赖、未接 LLM、未写 `instance/app.db`/`workflow.sqlite3`/业务 CSV；未改 identity_key 组成/判重/rounds 语义。
> 注：Flow 范围不含 `docs/validation/v9/impl`，报告放 `tools/selection/`。

## 1. merge 原子 + 卡片冲突规则

- **事务边界**：`categories.py:224-274`，`BEGIN IMMEDIATE`；source 状态、事件、别名、卡片、merge 事件在同一事务；异常 `rollback()`，不会 UNIQUE 后留半合并。
- **卡片冲突规则（取舍）**：target 已有卡时，**保留 target 卡**（不改其 evidence/status），source 卡置 `status='merged'`、`merged_into=target`，不硬删；target 无卡时才把 source 卡迁给 target。理由：避免 UNIQUE 冲突，同时保留 source 追溯；undo 可恢复。
- **schema v4**：`direction_card` 增加 `merged_into`，status CHECK 增加 `merged`；`discovery_event` 增加 `origin_category_id`。旧库 `_migrate_v4` 重建 card 表并复制原列，保留既有数据；`SCHEMA_VERSION=4`。
- 事件迁移按 `source_event_ids` 显式列表更新，并写 `origin_category_id=source`；别名按 `source_alias_ids`；卡片按 `source_cards`。

## 2. undo(merge) 精确还原

- `categories.py:277-336`：只按 before 中 source 自己的 event/alias/card ID 迁回；不按 `category_id=target` 批量迁移，避免把 target 原有事件/卡带走。
- 恢复 source `status`/`merged_into`，source 卡恢复原 status/category。
- 审计 E9：`undo_before_target_events=1`、`after_merge_target_events=2`（merge 后 target 暂时持有 source 事件）、`after_undo.target_events=1`（undo 后恢复）；target 原有事件未被搬走；source 卡恢复；审计 `merge_cards_undo` **PASS**。
- 新增测试 `test_merge_dual_cards_atomic_and_undo_target_counts` 固定双卡场景。

## 3. split undo 恢复归属

- `categories.py:339-397`：split 记录 `moved_events`（event_id、signal_id、from category）、`source_card_evidence`、`new_category_id`；更新 source 卡 evidence 去除被移动 signal；为子品类建 draft 卡（若有移动信号）。
- undo(split) `categories.py:299-326`：按 `moved_events.event_id` 把事件迁回 `from`；恢复 source 卡 evidence；子卡移除被移动 signal 并置 `status='merged'`/`merged_into=source`；不再只追加 undo 事件。
- 审计 E6 `split_undo` **PASS**：split 后 source 卡 `[2]`、signal1 事件在 new category 2；undo 后 source 卡恢复 `[1,2]`、事件回 category 1。
- 新增测试 `test_split_undo_restores_evidence_and_events`。

## 4. 坏 JSON 单行继续

- `xianyu.py:71-88`：`_read_rows` 逐行 `yield (line_no, raw_bytes, row_or_exception)`；`json.loads` 异常作为行对象返回，不传出外层。
- `xianyu.py:101-147`：`isinstance(row, Exception)` 时计 `bad_rows`/errors，继续下一行；成功行计 `ok_rows`；`max_rows`/`max_errors` 仍生效；status 为 `partial`（有错误未停止）或 `stopped`（预算/错误上限）。
- 审计 E7 `import_bad_json_budget` **PASS**：坏 JSON 不抛异常、`bad_run status=partial`、`bad_signals=2`；max_rows 仍 `stopped/rows_exceeded`。
- 新增测试：坏行+2 好行→rows=3/ok=2/bad=1/errors=1/new=2/partial；2 坏行 max_errors=1→stopped/errors_exceeded/bad_rows=1。

## 5. 测试 / 审计（真实 exit）

| suite | 结果 | 日志 |
| --- | --- | --- |
| selection（基线 42 + 新增 4） | **46 tests OK** | `tools/selection/logs/tests_selection_v97b.log` exit 0 |
| workbench | **218 tests OK** | `tools/selection/logs/workbench_v97b.log` exit 0 |
| 项目全套（基线 376 + 新增 4） | **380 tests OK** | `tools/selection/logs/project_v97b.log` exit 0 |

- cwd `D:\桌面\two`；UTC 21:27–21:29。新增测试：categories 2（双卡 merge/undo、split undo evidence）、xianyu 2（坏行继续、max_errors）。
- 审计 temp 副本（不改 `docs/validation/v9/integration-audit/`）：
  - E9 `merge_cards_undo` FAIL→**PASS**
  - E6 `split_undo` FAIL→**PASS**
  - E7 `import_bad_json_budget` FAIL→**PASS**
  - 其余 3 项（repeat_categorize_cards、merged_excluded_attribution、identity_carrier_origin）仍 FAIL，属下一批；E10 `round_edges` 因 V9-7a 审计脚本自身未捕获冲突而 ERROR，与本任务无关。

## 6. 未修 / 限制

- 未修：判重幂等/卡片刷新、excluded/merged 归属、carrier/origin（第三批）；rounds 语义未动。
- schema v4 改变了 `direction_card.status` CHECK（新增 merged）和两列；旧库自动迁移，但迁移会重建 `direction_card` 表（数据复制，非业务库）。
- 卡片冲突选择“target 保留 + source tombstone”；未合并 source 卡 evidence 到 target（避免编造/污染），需要时可由人工/后续刷新处理。
- split 子卡为 draft、gaps 空；未刷新子卡 gaps；source 卡 gaps 不重算。
- 未跑真实 X/闲鱼导入；全 temp DB/桩。
