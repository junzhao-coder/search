# 毛利由价格信号驱动 + 联动表可观测性（返工版）

> 任务：`task-8dfd3329210aa7621744685567e139c5`（计划 v6 B7，返工 rev5）。
> 结论：**¥1 引流标价已排除**，`price_low/price_high` 改用 `reference` 中位数（无参考价则 `effective_high`）；10 行中 **8 行 margin_low > 0**，形成 **3 组**区间；fallback 行保留 ±0.15 且 low；置信度收紧；334 测试 exit=0。

## 1. 返工后的算法

### 价格锚点（排除 ¥1）

- `¥1` 类标价视为**引流价/缺失**：不进入 `price_low`，不再用 `effective_low` 作下限。
- 有参考价：`anchor = median(reference_price)`。
- 无参考价：`anchor = effective_high`（该品类或全量篮子的有效价上限，显式标注为估计）。
- 全量回退/样本<3：全量篮子 + `low−0.15 / high+0.15`（clip 0–1），置信度固定 **low**。
- `reference_max`（699）只作展示，不作锚点，避免极值放大。

### 毛利与归一化

```
margin_low  = clamp((anchor - cost_high) / anchor, 0, 1)
margin_high = clamp((anchor - cost_low)  / anchor, 0, 1)
margin_mid  = (margin_low + margin_high) / 2
```

- 成本假设：**¥0.5–3/单** 人民币数字交付边际成本（不含退款/支付/流量/客服/人工；未按汇率硬换算）。
- 归一化：直接使用 0–1 的毛利率比值，不把绝对毛利金额除以 cap；`mid` 是区间中点。与既有评分 0–1 口径一致。
- 旧 `model.md` 的 `$9–49 / $0.5–3` 仅在**完全没有可用价格信号**时作为 fallback；本批 10 行均有价格信号，因此不参与。

### 置信度规则（收紧）

| 条件 | confidence |
| --- | --- |
| 全量回退 | low（即使 n=20、有参考价） |
| n<5 | 最高只能到 medium |
| n≥5 且有 reference | 允许 high |
| n≥5 无 reference | medium |
| 无价格信号 | low |

本批分布：**high 1 / medium 0 / low 9**。design n=17 有参考价 → high；7 条 fallback → low；prompt n=3 无参考价 → low。

## 2. margin_low 分布与 10 行对比

- `margin_low > 0`：**8/10**。
- `margin_low = 0`：2/10，均为 prompt 品类（n=3、无参考价，anchor=¥1.00；成本上限 ¥3 覆盖价格，属保守结果）。
- 区间不再全部从 0 起：fallback `0.547–1.000`；design `0.697–0.949`；只有 prompt `0.000–0.500`。

| # | 机会 | 口径/样本 | 旧 low–high (mid) | 新 low–high (mid) | basis | conf |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | X @booorenjiiy | fallback/20 | 0.700–0.950 (0.825) | **0.547–1.000 (0.773)** | all20_reference_median_widened | low |
| 2 | X @mareidaily | category/3 | 0.700–0.950 (0.825) | **0.000–0.500 (0.250)** | category_effective_high | low |
| 3 | X @worksfess | category/17 | 0.700–0.950 (0.825) | **0.697–0.949 (0.823)** | category_reference_median | high |
| 4 | B站 Notion 导入 | fallback/20 | 0.450–0.800 (0.625) | **0.547–1.000 (0.773)** | all20_reference_median_widened | low |
| 5 | X @heyeaslo | fallback/20 | 0.700–0.950 (0.825) | **0.547–1.000 (0.773)** | all20_reference_median_widened | low |
| 6 | X @opteemisty | fallback/20 | 0.700–0.950 (0.825) | **0.547–1.000 (0.773)** | all20_reference_median_widened | low |
| 7 | X @aeshoui | fallback/20 | 0.700–0.950 (0.825) | **0.547–1.000 (0.773)** | all20_reference_median_widened | low |
| 8 | B站 小白教程 | fallback/20 | 0.450–0.800 (0.625) | **0.547–1.000 (0.773)** | all20_reference_median_widened | low |
| 9 | X @IAmPascio | category/3 | 0.700–0.950 (0.825) | **0.000–0.500 (0.250)** | category_effective_high | low |
| 10 | B站 177 教程 | fallback/20 | 0.450–0.800 (0.625) | **0.547–1.000 (0.773)** | all20_reference_median_widened | low |

> 旧值说明：B6 报告称旧 10 行全 0.7/0.95；本批实际 `before_join.csv` 为 X 行 0.7/0.95、B站行 0.45/0.8。两者共同点是没有价格传导；evidence 以实际文件为准。

## 3. 排除 ¥1 的证据

- 每个新行的 `margin_note` 均以 **“已排除 ¥1 引流标价”** 开头；`assumptions` 亦写明 `¥1 listings excluded as traffic bait.`
- 价格锚点取自 `reference median`（9.90）或 `effective_high`（1.00），不是 `effective_low`。
- 证据：
  - [margin_table.csv](margin_table.csv)：29 列，含 `margin_note`/`assumptions`。
  - [before_after.csv](before_after.csv)：10 行 old/new 区间。
  - [logs/join_run.log](logs/join_run.log)：stdout 逐行 `old -> new`。

## 4. UI

`/dash/sources` 联动表：

- 价格口径列改为可读文案并带样本量：**“全量回退（20 条）” / “品类过滤（3 条）”**。
- 除以样本量列后，表为 10 列；固定列宽 + 横向滚动，无异常挤压。
- 依据列显示“品类参考价中位 / 品类有效价上限 / 全量参考价+放宽”，hover 显示 `margin_basis` 与 `margin_note`。
- 置信度列显示“低/中/高”，hover 显示原始 low/medium/high。
- 表下说明：**“¥1 为引流价，已排除，不作为价格下限；毛利按参考价中位数（无参考价则品类有效价上限）与成本 ¥0.5–3/单估算；全量回退额外放宽 ±0.15，置信度 low。”**

截图：

- before：[shots/sources_before.png](shots/sources_before.png)
- after：[shots/sources_after.png](shots/sources_after.png)
- HTML 差异：[screenshots.diff](screenshots.diff)

## 5. 测试

- 命令：`.\.venv\Scripts\python.exe -m unittest discover -s tests -v`
- **exit=0**
- `Ran 334 tests in 49.512s` → **OK**
- `tests/dash/test_routes.py` 已补充 `已排除`、`全量回退（20 条）` 等断言；测试数仍 334。
- 证据：[logs/test.log](logs/test.log)

## 6. 偏差方向与不可比

- **高价值可能低估**：design 仅有 3 条参考价，¥699 极值被排除；若机会本身可卖到 699，锚点 9.9 的上限 0.949 会低估。
- **低价值可能抬高**：7 条 Notion 用全量 20 条篮子的参考中位数 9.9，跨品类混合；±0.15 进一步放宽，不是 Notion 专属价格，mid 0.773 对低价值教程可能偏高。
- **prompt 保守**：n=3、无参考价，锚点仅 ¥1，成本上限 ¥3 覆盖价格 → low 0，置信度 low。
- **不可比**：¥1 是引流价；effective 是品类篮子代理而非机会自身成交价；reference 是划线价不是成交价；wants 是兴趣代理；X/B站内容平台与闲鱼交易平台不可直接比价。
- 新毛利只用于相对排序/情景，不是实际利润；旧 0.7–0.95 不应再被当作“利润事实”。

## 7. 限制

1. 成本 ¥0.5–3 是数字交付边际成本假设，不是完整成本。
2. 参考价仅 3 条（design）；699 不作锚点；高价值可能低估。
3. 7 条 Notion fallback 为跨品类篮子，low 置信度，可能高估低价值教程。
4. prompt n=3、无参考价，low/margin_low=0 是保守结果，不是“无利润”。
5. 未新增依赖、未改既有 API/业务库/契约/迁移；未重新采集。
6. 截图 1440×6000 全页；未做移动端逐页回归。
