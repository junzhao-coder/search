# S7 经营验证准备（模板 / 滚动复盘 / 当前结论）

> **状态：准备批（仅文档）。当前结论：暂未验证盈利。**
> 本目录只提供**真实经营记录模板、滚动复盘流程与当前结论**；不伪造数据、不自动发布/联系/采购/付款、不采集外部数据、不改代码/契约/迁移/业务库、未联网。
> 说明：`docs/design/` 下**不存在 S7 设计文档**，`CONTRACT.md` 也**无 S7 专章**；本目录为准备批**自拟**的操作材料，不是契约、不是验收证据、不代表 S7 已开始或已完成。
> 准备时点：2026-10-20（如实记录；此后新增事实须由用户提供）。

## 文件索引

| 文件 | 用途 |
| --- | --- |
| [OPERATING_LOG_TEMPLATE.md](OPERATING_LOG_TEMPLATE.md) | 真实经营记录字段定义、与系统 `feedback` 接口的对应关系、手工核算口径 |
| [OPERATING_LOG_TEMPLATE.csv](OPERATING_LOG_TEMPLATE.csv) | CSV 模板（**仅表头、零数据行**；不预填任何内容） |
| [ROLLING_REVIEW_PROCESS.md](ROLLING_REVIEW_PROCESS.md) | 滚动复盘流程（记录→导出→手工核算→复盘→决策→留证） |
| [CURRENT_STATUS.md](CURRENT_STATUS.md) | 当前结论与依据、阻塞、下一步（**暂未验证盈利**） |
| [runs/README.md](runs/README.md) | 每次复盘 run 目录的命名与留证约定（当前为空目录） |

## 硬边界（与 README / CONTRACT / DEVELOPMENT_PLAN §11 一致）

- **不做经营动作的自动化**：不自动发布、不自动联系买家/卖家、不自动采购、不自动付款；所有对外经营动作由用户逐项确认并执行。开发计划/本目录**不是经营动作许可**。
- **不伪造数据**：没有真实成交就写"无/未验证"；不得用合成数据、示例数据、估算或模型输出冒充真实经营结果；不得预填成交金额、订单号、利润。
- **不承诺未实现能力**：定时触发、提醒、实际利润自动核算、经营报表、告警、自动对账、发布/消息/采购/付款接口目前**均未实现**（见下表），本目录不把它们写成已有能力。
- **不把预测当成交**：系统里的情景/排序/摘要是**估算与展示**；`feedback.predicted_net_per_order_minor` 只是成交时点的预测快照，不等于实际利润。
- **真实/合成可区分**：业务库当前只有 synthetic 示例数据（见 `CURRENT_STATUS.md`）；真实数据须经用户提供并标记 `data_origin='real'`；本目录的任何汇总不得混入 synthetic 记录。

## 已实现 / 未实现（截至文档时点，均如实标注）

| 能力 | 状态 | 说明 |
| --- | --- | --- |
| 每日摘要只读导出（`tools/export_daily.py`） | **已实现** | 只读复用 `daily_digest`，JSON/CSV 落盘；**默认只统计 real**（`data_origin='real'`），合成数据不计入 |
| 每日摘要 HTTP 读路径（`GET /api/summary/daily?date=`） | **已实现** | CONTRACT #19；默认 real-only，`include_synthetic=1` 才纳入合成；≤5 条 |
| 经营反馈事件记录（`POST /api/candidates/<id>/feedback`、`PATCH /api/feedback/<id>`） | **已实现** | `kind`：inquiry/sale/refund/expense/manual_time/note；可记录订单号、金额、退款状态、人工时间等；金额单位**分（`_minor`）** |
| **实际利润核算/报表**（`actual_net_per_order_minor` 写入与汇总） | **未实现** | 该字段为服务端保留、S2 只读（NULL）；无实际利润报表/对账；手工核算见模板 |
| 定时触发 / 提醒 | **未实现** | 需用户手动执行导出与复盘 |
| 自动发布 / 联系 / 采购 / 付款 | **未实现（且按边界不做）** | 人工执行并逐项确认 |
| 经营数据备份/恢复 | **已实现（脚本）** | `tools/backup.py` / `tools/restore.py`；未实现 CONTRACT §6 端点 |

## 单位与时间口径（与 CONTRACT 一致）

- 金额一律**整数分**（`*_minor`），货币 v1 仅 **CNY**；非 `_minor` 的金额输入为十进制元字符串（最多 2 位小数）。
- 时间存 UTC（`...Z`）；展示可换算本地时区（`APP_TZ_OFFSET_HOURS`，默认 +8）。
- 汇总公式与取整规则以 `CONTRACT.md` §0.4 为准；本目录只做**手工记录与核算说明**，不新增计算口径。

## 使用顺序

1. 用户确认试验范围：预算上限、观察窗口、止损条件（**当前均待用户裁定**，本目录不预设数值）。
2. 用户逐项选择合格商品，逐次确认发布/发送/采购/付款；执行后按 `OPERATING_LOG_TEMPLATE.md` 记录（CSV 一行一条真实事件 + 证据路径）。
3. 按 [ROLLING_REVIEW_PROCESS.md](ROLLING_REVIEW_PROCESS.md) 导出摘要、手工核算、更新 [CURRENT_STATUS.md](CURRENT_STATUS.md)。
4. 达到用户确认的评估条件后，由策划者另行提出 S7 评估；本目录不自行宣布盈利或 S7 完成。
