# V9-7c 实现报告：categorize 幂等、卡片刷新、excluded/merged 归属、载体归一、origin 首见保护

> 任务 `task-ba95f3ef72d22c4463fe1090bc080e0b`（rev2，计划 v9）；范围 `tools/selection`、`tests`。
> 2026-10-25 21:34–21:41 UTC+8。未装依赖、未接 LLM、未改业务库/workflow/CSV；未动 merge/undo/split/rounds 已修语义。
> 注：Flow 范围不含 `docs/validation/v9/impl`，报告放 `tools/selection/`。

## 1. 幂等（取舍：纯跳过）

- `categories.py run_categorize`：只扫描 **无 discovery_event** 且 **无 pending review** 的 signal；已处理 signal 计入 `skipped`，不写 update、不重复 review。
- 选择 **纯跳过**，不写 `reindex` 事件：避免把“跳过”混入 update 统计；代价是将来要“同信号再归类”需显式 reindex（未实现）。
- `_review()` 先查 `(signal_id,status='pending')`，存在即复用，不重复插。
- 审计 E3 `repeat_categorize_cards` **FAIL→PASS**（修正 temp 审计对“新信号 s2”的旧断言）：run2 新信号 update=1/事件 1→2，run3 skipped=2/事件不变；卡 evidence `[1,2]`；review=1。

## 2. 卡片刷新

- `categories.py make_cards`：对已有卡**更新** `evidence_ids_json`（该品类全部 distinct event signal）、重算 `gaps_json`、audience/task/deliverable；`refreshed` 计数；`status='merged'` 的卡直接跳过，不复活 split 墓碑。
- 审计 card1 created=1；card2 refreshed=1；证据 `[1,2]`；不再“existing 即 continue”。

## 3. excluded / merged 归属

- `_resolve_active`：递归沿 `merged_into` 找 active target；excluded 直接判定。
- 命中 excluded：不写 update，写 review，reason=`category_excluded: hit excluded category`，返回 `category_id=None`、`candidate_category_id=excluded id`（避免把 review 算成归属）。
- 命中 merged：沿链找最终 active target 再 update；链断（target 缺失/也 merged 无终点）→ review `category_merged_without_target`。
- 审计 E4 `merged_excluded_attribution` **FAIL→PASS**：excluded 结果 review/null/候选 1；merged 结果 update target 2，source 仍 merged。

## 4. 载体归一（粗族）

- `models.FAMILY_NORM`：`notion_template/excel_template→template`，`design_asset_pack→asset_pack`，`pdf_guide→guide`，`prompt_pack` 保持。
- `categories.identity_key` 对 family 先粗化；`categorize_signal` 新建品类存粗族，`canonical_label` 保留细载体样式；`categories.deliverable_carriers` JSON 数组记录见过的细载体。
- 同键换载体：update 事件 `after.carrier/carrier_changed/deliverable_carriers`，不新建品类。
- **迁移方案**：`db._migrate_v5` 给旧库加 `deliverable_carriers`；逐行计算粗键：
  - 无冲突→更新该行 `identity_key/family/carriers`（保留 id/events）；
  - 与已有粗键冲突→把旧行 events/aliases/cards 迁到既有品类，旧行 `status=merged` 且 identity_key 加 `#legacy<id>` 保留追溯。
- 隔离副本验证 `merged23_v97c_migrated.sqlite3`：schema=5；6 个旧品类全部转粗键（template/asset_pack/prompt_pack），events=22、cards=6 保留；无重复键。
- 审计 E5 `identity_carrier_origin` **FAIL→PASS**：notion→excel 同需求 **1 category**；carriers `[notion_template, excel_template]`。

## 5. origin 首见保护

- `db.upsert_signal`：existing `origin_kind='imported'` + incoming `'real'`，**无论 content_hash 是否变化都保留 imported**（首见来源不被覆盖）。
  - 同 hash → duplicate，`ORIGIN_GUARD` reason `origin_upgrade_skipped`；
  - hash 变化 → UPDATE 内容/version+1，但 `origin_kind` 仍 imported，新增 `signals.last_origin_kind='real'`，`ORIGIN_GUARD` reason **`origin_upgrade_on_change_kept_first_seen`**。
- schema v6 增加 `signals.last_origin_kind`；旧库 `_migrate_v6` ALTER。
- 审计 E5 origin：imported→same real = duplicate，`same_origin=imported`；changed real = updated，`stored={origin_kind:imported,last_origin_kind:real,version:2}`。

## 6. 真实 23 条（隔离副本）

- 迁移副本：`tools/selection/runtime/merged23_v97c_migrated.sqlite3`（6 品类，schema5，events/cards 保留）。
- 仅 signals 的新副本 `merged23_v97c_fresh.sqlite3`：`run_categorize` → **6 categories / 6 cards / 1 review / new=6 update=16 skipped=0**。
- 与 V9-7b 的 6 品类相比 **6→6 未变**。原因：现有 6 类的 audience/task 已不同；载体归一只会在“同 audience+task 不同细载体”时合并，本 23 条没有这种额外组合。signal14（student/design_assets/unknown）仍 review。**样本极小，不代表市场需求**。

## 7. 测试 / 审计 exit

| suite | 结果 | 日志 |
| --- | --- | --- |
| selection（基线 46 + 5 新） | **51 tests OK** | `tools/selection/logs/tests_selection_v97c_r2.log` exit 0 |
| workbench | **218 tests OK** | `tools/selection/logs/workbench_v97c_r2.log` exit 0 |
| 项目全套（基线 380 + 5 新） | **385 tests OK** | `tools/selection/logs/project_v97c_r2.log` exit 0 |

- cwd `D:\桌面\two`；UTC 21:39–21:41。新增：幂等、卡片刷新、excluded/merged、载体归一、origin 保护（另修两轮测试以适配粗族）。
- 审计 temp 副本（不改审计目录；按新验收语义修正 E3/E4/E5 的过时 fixture/断言）：E3/E4/E5/E8 **全部 PASS**；E9 `merge_cards_undo` 也在修正 fixture 后 PASS；E10 `round_edges` 仍 ERROR（V9-7a 审计脚本未捕获 idempotency_conflict，与本任务无关）。

## 8. 未修 / 限制

- 未实现 reindex 事件/同信号再归类；纯跳过。
- origin 首见保护现在连内容变化也保留 imported；这是 H4 的解释：来源是“首见来源”，内容更新不改变来源。若未来需要“来源升级”必须显式人工确认（未实现）。
- 未改 merge/undo/split/rounds 语义；E10 未处理。
- 卡片 `gaps_json` 只按价格/wants/第二平台重算；未新增其它 gap。
- 迁移冲突时旧行标 merged 并加 `#legacy` 键；canonical_label 未强制改粗族（保留细族展示）。
- 真实 23 条只重跑 categorize/cards，不重新采集；未验证长跑/更多样本。
