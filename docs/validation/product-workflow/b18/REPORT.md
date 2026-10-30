# B18：货源变更传导修复（D2/D3/D4 + D1 文案）交付报告

- 范围：`tools/workbench/`、`docs/validation/product-workflow/b18/`；未改业务库/CONTRACT/评分与货源 CSR
- 结论：**货源变更不再“改了候选但工作单仍 7/7”**——改已选候选（许可/来源/价格）会同步许可与版本、**作废样品与成本并要求重做**；停用已选候选会清空货源、许可置 unknown 并作废证据；换源同样作废旧证据；未选中候选的修改/停用**完全不影响**工作单；旧导出随 `revision` 变化失效、导出回到 **409**。详情页旧区块已明确标注“来源快照与历史阶段（非当前状态）”。4 套测试全绿；已部署 5015（PID 94372）。

## 1. 修复点（供对照 D2/D3/D4）

| 缺陷 | 触发 | 修复后行为 |
| --- | --- | --- |
| **D2** 改已选候选许可/来源/价格 | `update_candidate` 只写候选 | 若目标是 `selected_supply_id`：同事务同步 `supply_license_*`、`supply_version=updated_at`、`supply_note`；**`sample_status=NULL`、`sample_ref=NULL`、`cost_known='no'`、`cost_minor=NULL`**；`revision+1`；事件 `supply_sync`（记录许可变化与“样品与成本已失效”） |
| **D3** 停用已选候选 | `deactivate` 只置 `is_active=0` | 额外：`selected_supply_id=NULL`、三项许可 `unknown`、样品/成本作废、`revision+1`；事件 `supply_deactivate_selected` |
| **D4** 换源 A→B | `select_candidate` 只覆盖字段 | 换源时**先作废旧样品/成本**再写新源；事件 `supply_replace` 明确“旧样品与成本已失效，需重新自检与重填” |
| **D1** 旧区块与七项并存 | 详情页旧 B1 文案 | 区块标题改为「**来源快照与历史阶段（非当前状态）**· 待核验缺项」，并在页面顶部加提示：**当前是否可上架只看「上架准备检查（服务端判定）」**；证据不删 |

**失效判定的联动**：`readiness()` 仍只读 workorder 字段，因此清空 `sample_*`/`cost_*` 后 `sample`、`cost` 立即转 false；许可改为非 yes 时 `license` 转 false；停用后 `supply` 转 false。旧导出是否失效沿用 `revision` 比对（B13/B15 已有逻辑），故 D2–D4 后 `export_validity.valid=false`、`GET /export` 返回 **409**。

## 2. 测试（隔离库，`tests/test_binding.py`，6 例）

| 用例 | 断言要点 |
| --- | --- |
| `test_d2_license_change_syncs_and_invalidates` | 改 `resale=no` → workorder 同步 `no`；`license/sample/cost` 三项转 false；旧导出 `valid=false`；GET export **409** |
| `test_d3_deactivate_selected_clears_supply` | `selected_supply_id` 为空、许可 `unknown`、`supply` false、导出 **409** |
| `test_d4_replace_requires_new_sample_and_cost` | 换源后 `sample_ref/sample_status/cost_minor` 均空、`cost_known=no`、`sample/cost` false、不得 7/7、导出 **409** |
| `test_control_unselected_candidate_changes_nothing` | 改/停 **B（未选中）** → workorder 逐字段不变、仍 7/7、导出 **200** |
| `test_recovery_after_invalidation` | 作废后重新自检 + 重填成本 → 恢复 7/7 |
| `test_d1_legacy_block_labelled_as_snapshot` | 页面含「来源快照与历史阶段（非当前状态）」与「不代表当前状态」 |

## 3. 测试运行（真实 subprocess，`execution_manifest.json`）

| suite | rc | summary |
| --- | --- | --- |
| `b18_binding` | **0** | `Ran 6 tests — OK` |
| `b16_supply_sample` | **0** | `Ran 11 tests — OK` |
| `workbench_all` | **0** | `Ran 150 tests — OK` |
| `project_full` | **0** | `Ran 334 tests — OK`（47.4s） |

`run_suites.py` 自身 rc=0、`failed=[]`。

## 4. 部署与生产只读核对

- 只停本工具 5015 进程后同端口重启：**PID 94372**。
- 生产单 `wo:20261023-88ef9a66`：详情 **200**，含新标题「来源快照与历史阶段（非当前状态）」与「上架准备检查（服务端判定）」；`GET /export?format=md` 仍 **409**（`platform_evidence` 为空，符合预期，本次未放宽）。
- `/healthz` 仍 `app_id=workbench-opportunity/1`。
- 守卫未变：`instance/app.db e073f828…`、`CONTRACT.md 826c24cc…`、`scores.csv ab0c3546…`、`sources.csv 13679b60…`；未改评分/货源 CSV、未登录/采购/发布。

## 5. 改动摘要（diff）

- `supply.py`：新增 `_invalidate_sample_cost()`、`_sync_selected()`；`update_candidate()` 在目标为已选候选时同事务同步并作废证据（事件 `supply_sync`）；`deactivate()` 对已选候选清空货源/许可并作废证据（`supply_deactivate_selected`）；`select_candidate()` 换源时先作废旧证据，事件说明需重新自检/重填。三者均 `BEGIN IMMEDIATE` + 异常回滚。
- `views_worksheet.py`：`render_detail()` 顶部加“来源快照 ≠ 当前状态”提示；旧「待核验缺项/四门槛」区块标题改为「来源快照与历史阶段（非当前状态）· 待核验缺项」，证据内容未删。
- `tests/test_binding.py`：新增 6 例（上表）。

## 6. 限制与说明

1. 失效是**保守策略**：只要已选候选被修改（哪怕只改备注/价格），样品与成本都会作废，需要重新自检/重填；这是为了避免“旧证据套新货源”。
2. 换源不自动沿用旧 `supply_version`：新版本取候选 `updated_at`。
3. 停用后 `supply_version` 保留最后值（仅作为历史），`selected_supply_id` 置空才是“未选货源”的判定依据。
4. 旧导出失效依赖 `revision` 变化；若绕过应用直接改候选表而不改 workorder，本机制不生效（不在应用保护范围内）。
5. 生产单仍缺 `platform_evidence` → 导出 409 不变；本任务只修传导，不放宽任何门槛。
