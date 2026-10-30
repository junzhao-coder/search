# 独立工作台当前状态（B14 核验快照）

- 快照 UTC：2026-10-23T15:10Z；生产工作台 `/healthz app_id=workbench-opportunity/1`。
- 生产工作单库：`tools/workbench/runtime/workflow.sqlite3`，sha256 `d9349c03…`。
- 生产工作单：`wo:20261023-88ef9a66`（B12 归一后），status `pending_supply`；1 单、export 0；**copy_version / publish 两张 B13 表在生产库中尚不存在**（只读查询确认）。
- 生产 `instance/app.db` `e073f828…`、CONTRACT `826c24cc…` 未变；本次 B14 只写 `b14/`。

## 五阶段现状

| 阶段 | 现状 | 证据文件路径 |
| --- | --- | --- |
| 1 选品 | 生产单 `wo:20261023-88ef9a66` 为自制学习计划 Excel；来源 `self:c3-v1`，规格/交付已保存；status `pending_supply` | `docs/validation/product-workflow/b1/REPORT.md`；`b12/REPORT.md`；`b12/id_mapping.json` |
| 2 货源 | 选定 `self:c3-v1`；许可三档均 `yes`；样品状态 `verified`，但 sample_ref 明示是“selfcheck 17/17（非真实 Excel 打开）”；外部候选表另存 | `b2/candidates.json`、`b2/REPORT.md`；`b7/REPORT.md`；`b12/REPORT.md` |
| 3 价值 | 价格 `price_minor=990`、成本 `cost_minor=500`；B7 样例/定价材料存在；生产四门槛仍未核验 | `b7/REPORT.md`、`b8/PRICING.md`、`scoring/scores.csv`、`sourcing/opportunity_sourcing_top10.csv` |
| 4 介绍 | 文案 `copy_status=final`、`copy_version=c3-v1-copy`；卖点/FAQ/交付说明已保存；生产无 copy_version 历史表 | `b11/LISTING.md`、`b12/REPORT.md`、`b13/REPORT.md` |
| 5 上架准备 | readiness **6/7**；唯一阻断：`platform_evidence` 为空（xianyu 平台条件缺证）；导出 409，未生成上架包 | `b3/REPORT.md`、`b6/INDEPENDENT_VERIFY.md`、`b14/INDEPENDENT_VERIFY.md` |

## 闭环现状

| 环节 | 现状 | 证据 |
| --- | --- | --- |
| 导出 | GET 预览不写；未就绪 409；就绪后生成 md/json 附件 | `b14/probe.json`、`b3/REPORT.md` |
| 记录 | POST `/export/record` 写 1 行 | `b14/probe.json` |
| 去重 | 同 `(revision, copy_version, supply_id, supply_version)` 第二次 `deduplicated=true`，行数 1→1 | `b14/probe.json`、`b13/REPORT.md` |
| 发布回填 | 非法状态/协议/负销量 400；合法保存 publish_version+1 | `b14/probe.json`、`b13/REPORT.md` |
| 版本回滚 | 回滚到 v1 生成 v3；supply/license/sample/cost/platform 五组不变；快照仅文案字段 | `b14/probe.json`、`b13/REPORT.md` |
| 生产实际 | 未执行导出/记录/发布；生产库缺 B13 两表 | `b14/production_state.json` |

## 7 项已知限制

1. **版本快照只含文案字段**：`name/selling_points/includes/excludes/fmt/language/version/price_minor/delivery_note/aftersales_note/faq_json`；不含成本/门槛/证据字段（`b13/REPORT.md`）。
2. **回滚不回写证据**：只回写文案字段；supply/license/sample/cost/platform 保持当前值，需另行核验（B14 实测五组不变）。
3. **去重键含 revision**：只改成本/证据（revision 变化）也会被视为新导出戳；不是内容级去重（`readiness.py:303-322`）。
4. **平台条件未核**：生产 `platform_evidence` 为空，ready 6/7，导出 409；`demo://` 走查不能代表闲鱼真实类目/资质。
5. **发布状态仅三档**：`未发布/已发布/已下架`；不支持自定义状态（`readiness.py:372`）。
6. **发布时间自由文本**：`published_at` 只截断 32 字符，未做 ISO/时区强校验（`readiness.py:406`）。
7. **样品未真实打开**：生产 sample_ref 为 selfcheck 结构/公式自检，“非真实 Excel 打开”；需在 Excel/WPS 实机打开确认。

## 用户待办 3 项

1. **实机打开样品**：在 Excel/WPS 打开 `.xlsx`，核对 5 表/50 公式/下拉/打印区域；确认后可更新 sample_ref（需用户自己确认，不由系统代签）。
2. **确认闲鱼类目资质**：确认“学习计划/Excel 模板”类目准入、虚拟商品交付与平台规则，补 `platform_evidence`；补齐后 ready 7/7。
3. **定档并发布**：确认最终价格/售后/退款口径后，由用户本人在闲鱼发布；系统只导出人工上架包，不自动发布/联系/收款。

## 结论

- 代码层/隔离库：B12 自制建单与证据录入、B13 版本/回滚/去重/发布回填 **PASS**。
- 生产状态：**尚未完成 B13 数据层初始化**（copy_version/publish 表不存在）；因此生产单暂时没有版本历史/发布回填记录，不能宣称生产闭环已完成。
- 上架准备：6/7，唯一硬阻断是平台条件证据；在用户完成 3 项待办前不应向外发布。
