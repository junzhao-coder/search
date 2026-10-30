# 真实经营记录模板（字段定义 · 手工核算口径）

> 用途：把**用户真实执行**的经营事件（询单/成交/退款/支出/人工时间/备注）按统一字段记录下来，供滚动复盘与手工核算。
> **本文件不含任何数据**；`OPERATING_LOG_TEMPLATE.csv` **只有表头、零数据行**。所有数字必须由用户提供，并附证据路径。
> 系统能力边界（如实）：`feedback` 可记录事件与预测快照；**实际单笔净利（`actual_net_per_order_minor`）目前不可由 API 写入**（服务端保留、S2 只读），因此**实际利润只能手工核算**并写入本表；系统**没有**订单/实际利润报表。

## 1. 记录规则（append-only）

1. **一行一条真实事件**：成交、退款、支出、人工时间、询单、备注各自成行；不得把多个订单合并成一行。
2. **只记真实发生的事**：没有发生的订单/成交/退款不写；估算、情景、模型输出、合成数据一律不得写入本表。
3. **金额用整数分**（`*_minor`，CNY）；元金额输入仅作为搬运来源，换算后填写 `*_minor`。
4. **未知 ≠ 0**：费用/时间未知时留空并在 `note` 说明"未知"；**不得用 0 冒充未知**。
5. **证据可追溯**：每个金额/订单号必须能在 `evidence_path` 指向的截图/导出/订单页找到；证据由用户提供，按 `docs/s7/runs/<YYYY-MM-DD>/evidence/` 存放（不存放账号密码/支付凭证号全文等敏感信息）。
6. **不可改写历史**：错误用"更正行"追加（`note` 注明"更正 log_id=X"），不直接覆盖旧行；复盘以最新有效行为准。

## 2. 字段定义（与 `OPERATING_LOG_TEMPLATE.csv` 列一一对应）

| # | 列名 | 必填 | 说明 |
| --- | --- | --- | --- |
| 1 | `log_id` | 是 | 本记录唯一编号（如 `s7-20261020-001`，人工递增；不复用） |
| 2 | `occurred_at_utc` | 是 | 事件发生时间，UTC ISO（`2026-10-20T09:30:00Z`） |
| 3 | `local_date` | 是 | 本地日期（`YYYY-MM-DD`，默认 +08:00，便于按日复盘） |
| 4 | `candidate_id` | 是 | 对应候选 `candidate.id`（从系统导出/详情页读取；用于与每日摘要对齐） |
| 5 | `platform` | 是 | 发生平台（如 `xianyu`；不得写未发生平台） |
| 6 | `kind` | 是 | `inquiry` / `sale` / `refund` / `expense` / `manual_time` / `note`（与 `feedback.kind` 一致） |
| 7 | `order_ref` | 视类型 | 订单号/交易号（`sale`/`refund` 必填；同一候选的 `sale` 订单号唯一） |
| 8 | `quantity` | 视类型 | 数量（≥1；`sale` 必填） |
| 9 | `unit_price_minor` | 视类型 | 单价（分，≥0；`sale` 必填） |
| 10 | `amount_minor` | 视类型 | 事件金额（分，≥0；`refund`/`expense` 必填；`sale` 可用数量×单价，也可直接填成交总额） |
| 11 | `currency` | 是 | 固定 `CNY`（v1 仅 CNY） |
| 12 | `expense_kind` | `expense` 必填 | `procurement` / `platform` / `acquisition` / `run` / `other`（与 `feedback.expense_kind` 一致） |
| 13 | `expense_basis` | `expense` 必填 | `per_order` / `one_time` / `recurring` |
| 14 | `refund_state` | `refund` 必填 | `pending` / `settled`（与 `feedback.refund_state` 一致） |
| 15 | `related_log_id` | `refund` 必填 | 关联的原 `sale` 行 `log_id`（原订单在本表中的行号） |
| 16 | `actual_minutes` | `manual_time` 必填 | 实际人工时间（整数分钟，0–1440） |
| 17 | `actual_hourly_rate_minor` | 否 | 人工小时费率（分/小时，≥0） |
| 18 | `revenue_minor` | 成交行 | 该订单实际收入（分）＝成交金额（含运费按实际口径，见 §3） |
| 19 | `procurement_cost_minor` | 成交行 | 采购/货源实际成本（分） |
| 20 | `platform_fee_minor` | 成交行 | 平台佣金/服务费（分） |
| 21 | `payment_fee_minor` | 成交行 | 支付手续费（分） |
| 22 | `acquisition_minor` | 成交行 | 获客/推广分摊（分；`one_time` 需在复盘按口径分摊并在 `note` 说明） |
| 23 | `refund_cost_minor` | 成交行 | 退款/售后预提或实际退款（分） |
| 24 | `manual_labor_minor` | 成交行 | 人工成本（分）＝`actual_minutes × rate ÷ 60`（取整按 CONTRACT §0.4） |
| 25 | `other_cost_minor` | 成交行 | 其它实际成本（分；必须在 `note` 说明项目） |
| 26 | `actual_net_per_order_minor` | 成交行 | **手工核算**实际单笔净利（分，可为负）；公式见 §3；系统当前不写入该字段 |
| 27 | `evidence_path` | 是 | 证据相对路径（如 `docs/s7/runs/2026-10-20/evidence/20261020-001-order.png`） |
| 28 | `note` | 否 | 说明/未知项/更正说明/分摊口径；不超过 1000 字 |
| 29 | `user_confirmed` | 是 | 用户确认本行真实且可对外引用：`yes`；未确认填 `no`（复盘不计入） |

## 3. 手工核算口径（仅用于本目录表格，不新增系统计算规则）

对每一笔 `sale`（成交）行：

- `revenue_minor` ＝ 实际成交金额（分）。
- 实际净利（单笔）＝ `revenue_minor`
  − `procurement_cost_minor` − `platform_fee_minor` − `payment_fee_minor`
  − `acquisition_minor`（按已确认口径分摊） − `refund_cost_minor`（实际退款或按用户确认的预提）
  − `manual_labor_minor` − `other_cost_minor`。
- 结果可为负（如实记录亏损）；**不得**为凑正数调整口径。
- `refund`/`expense` 行作为独立事件记录，不重复从成交行扣减；若成交行已含退款成本，需在 `note` 说明"已含，勿重复"。
- 单位利润、每小时收益、售后负担、供应稳定性的**汇总**在复盘流程中计算（见 `ROLLING_REVIEW_PROCESS.md`）；本表只保证原始行可加总。
- 未知费用留空并说明；汇总时按"未知"单独列出，不当作 0（CONTRACT §0.4 未知与已知零）。

## 4. 与系统 `feedback` 接口的对应（可选，非必需）

| 本表字段 | `POST /api/candidates/<id>/feedback` JSON | 备注 |
| --- | --- | --- |
| `kind` | `kind` | 同上枚举 |
| `occurred_at_utc` | `occurred_at` | ISO 时间 |
| `order_ref` | `order_ref` | `sale` 订单号唯一 |
| `quantity`/`unit_price_minor`/`amount_minor` | 同名 | 分 |
| `expense_kind`/`expense_basis` | 同名 | `expense` 必填 |
| `refund_state`/`related_log_id` | `refund_state`/`related_feedback_id` | `refund` 必填 |
| `actual_minutes`/`actual_hourly_rate_minor` | 同名 | `manual_time` 必填 |
| `predicted_net_per_order_minor` | **服务端生成** | 成交时点预测快照，不可由客户端提交 |
| `actual_net_per_order_minor` | **不可提交** | 服务端保留、S2 只读；实际净利请填本表第 26 列 |

- 进入系统的真实记录要求候选本身为 `data_origin='real'`；合成候选产生的 feedback 不得计入真实经营汇总。
- 若选择"只在本 CSV 记录、不留系统 feedback"，属允许方式（本目录不强制写库）；两种方式都要保留证据路径与用户确认。

## 5. 填表前检查清单

- [ ] 每条都是**真实发生**的事件，且 `user_confirmed=yes`。
- [ ] 金额均为整数分、币种 CNY；未知项留空并在 `note` 说明。
- [ ] `sale` 有唯一 `order_ref`；`refund` 有 `related_log_id` 并指向原成交行。
- [ ] `actual_net_per_order_minor` 按 §3 手算，且与各成本分量相加一致。
- [ ] `evidence_path` 可打开、内容与数字一致；未上传敏感凭证。
- [ ] 无任何合成数据、估算或占位数字混入。
