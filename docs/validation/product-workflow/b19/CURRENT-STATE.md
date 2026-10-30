# 独立工作台当前状态（B19 核验快照）

- 快照 UTC：2026-10-24T05:45Z；生产工作台 `/healthz` `app_id=workbench-opportunity/1`。
- 生产单：`wo:20261023-88ef9a66`，status `pending_supply`；readiness **6/7**（唯一阻断：`platform_evidence` 为空）；导出 409。
- 生产工作单库：`tools/workbench/runtime/workflow.sqlite3`，sha `8ae79c58…`；只读 workorder=1、export=0；**candidate 表仍不存在**（首次写懒初始化；B17 临时副本已证明 303 建表，生产未迁移）。
- 生产 `instance/app.db e073f828…`、CONTRACT `826c24cc…` 未变；B19 只写 b19。

## 五阶段

| 阶段 | 当前状态 | 证据索引 |
| --- | --- | --- |
| 1 选品 | 生产自制单 `wo:20261023-88ef9a66`；来源 `self:c3-v1`；规格/交付/状态已保存 | `b12/REPORT.md`、`b12/id_mapping.json`、`b14/INDEPENDENT_VERIFY.md` |
| 2 货源 | 已选 `self:c3-v1`；三项许可 yes；sample_status=verified（注意仅结构自检，非真实打开）；B16 候选/采用、B18 变更传导已实现 | `b16/REPORT.md`、`b19/logs/b18_binding.log`、`b19/binding_probe.json` |
| 3 价值 | 价格 990 分、成本 500 分；B7/B8 定价材料；生产四门槛仍 unverified | `b7/REPORT.md`、`b8/PRICING.md`、`scoring/scores.csv`、`sourcing/opportunity_sourcing_top10.csv` |
| 4 介绍 | copy_status=final、copy_version=c3-v1-copy；版本历史/回滚/导出去重/发布回填已实现（生产无 candidate 表，版本历史为空） | `b11/LISTING.md`、`b12/REPORT.md`、`b13/REPORT.md`、`b15/REPORT.md` |
| 5 上架准备 | readiness 6/7；唯一阻断 platform_evidence 空；GET export 409；未生成上架包 | `b3/REPORT.md`、`b6/INDEPENDENT_VERIFY.md`、`b19/prod_check.json` |

## 闭环（含货源变更失效链路）

| 环节 | 现状 | 证据 |
| --- | --- | --- |
| 导出预览 | GET 只读；未就绪 409 | `b19/prod_check.json`、`b19/binding_probe.json` |
| 导出记录 | POST /export/record；未就绪 409 | b19 probe |
| 去重 | 同 `(revision,copy_version,supply_id,supply_version)` 不增行 | b18/b19 tests |
| 发布回填 | 三档状态/URL/非负销量校验；变更提示 | b13/b15 |
| 版本回滚 | 回滚生成新版本；只回写文案字段 | b13/b15 |
| 货源变更 | **D2 已选许可变化**→许可同步、sample/cost 清空、revision+1、旧 export 失效、GET 409；**D3 停用已选**→selected 清空、许可 unknown、sample/cost 清空、409；**D4 换源**→sample/cost 清空、readiness 不足 7/7、409；控制组未选候选改动 rec 逐字段不变；重检+重填可回 7/7 | `b19/binding_probe.json`、`b18/tests_binding` |

## 已知限制

1. 版本快照只含文案字段（不含成本/门槛/证据）。
2. 回滚只回写文案，不回写证据/货源。
3. 导出去重键含 revision；改证据也会被视为新戳。
4. 生产 `platform_evidence` 为空，readiness 6/7，导出 409。
5. 发布状态仅三档；`published_at` 为自由文本。
6. 样品未真实打开；`verified` 只代表结构自检。
7. `_invalidate_sample_cost` 只清 sample/cost，不清 `platform_evidence`；D4 换源后若只补样品/成本，可能沿用旧平台证据（见 B19 binding probe D4 recovery）。
8. 生产 candidate 表未初始化；首次写可懒建，但部署前候选列表为空。
9. B16 `update_candidate` 不检查 is_active；未知字段忽略而非 400。

## 用户待办 3 项

1. 在 Excel/WPS **实机打开** b7 样品，核对 5 表/公式/下拉/打印区域；确认后更新 sample_ref。
2. 确认闲鱼“学习计划/Excel 模板”类目准入、虚拟商品交付与平台规则，补 `platform_evidence`；补齐后 7/7。
3. 定档价格/售后/退款口径后由用户本人发布；发布后回填状态/URL/销量，不自动发布。

## 结论

- B18 的 D2/D3/D4 修复在隔离库 PASS：已选许可变更/停用/换源均使 sample/cost 清空、导出 409；控制组不变；恢复可回 7/7。
- 生产仍未完成上架：6/7，platform evidence 为空；candidate 表未迁移（懒初始化提醒）；不能把 UI 区块存在当成“已可发布”。
