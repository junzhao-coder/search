# 商品分类法：载体 × 具体用途（可审计）

> 目标：把“Notion 模板 / 教学内容 / 提示词包”这类笼统说法，换成**具体商品类型**（如「Notion 求职投递追踪表」）。
> 纯关键词规则、确定性、可复算；**不调用模型、不编造价格或销量**。

## 1. 载体（先判）

| 载体 | 关键词 |
| --- | --- |
| Notion | notion |
| PPT | ppt / powerpoint / 幻灯片 / 演示文稿 |
| 服务 | 代充 / 代下 / 代购 / 充值 / download service / top up |
| 素材 | psd / figma / ui kit / 素材 / 插画 / icon / design pack |
| 文档 | doc / docx / pdf / 文档 / 表格 / excel / spreadsheet / 简历文档 |
| 其他 | 以上都不命中 |

## 2. 用途（后判，按优先级）

| 用途 | 关键词 |
| --- | --- |
| 求职 | job / apply / interview / lamaran / cv / resume / 求职 / 简历 / 面试 / 投递 |
| 学习 | study / class / lecture / notes / student / school / 学习 / 课堂 / 笔记 |
| 内容创作 | content / creator / edit / social / 选题 / 内容 / 创作 / 社媒 |
| 生活 | budget / meal / workout / habit / goal / travel / planner / tracker / 预算 / 健身 / 旅行 / 习惯 / 计划 / 记账 |
| 设计 | design / portfolio / ui / 设计 / 作品集 |
| 赠送引流 | giveaway / free / 赠送 / 免费 / 福利 |
| 未判定 | 以上都不命中 |

## 3. 商品类型名（载体 × 用途）

| 载体 | 用途 | 商品类型 |
| --- | --- | --- |
| Notion | 求职 | Notion 求职投递追踪表 |
| Notion | 学习 | Notion 学习笔记模板 |
| Notion | 内容创作 | Notion 内容创作选题库 |
| Notion | 生活 | Notion 生活计划（预算/健身/旅行） |
| Notion | 设计 | Notion 设计作品集模板 |
| Notion | 赠送引流 | Notion 赠送引流模板 |
| PPT | 设计 / 求职 / 学习 | PPT 模板（作品集）/（汇报/述职）/（课件） |
| 文档 | 求职 | 简历文档模板 |
| 服务 | 未判定 | 资料代充/代下服务 |
| 素材 | 设计 | 设计素材包 |
| — | 兜底 | Notion 其它（待人工）/ PPT 模板（用途待定）/ 文档模板（用途待定）/ 未归类（待人工） |

**禁止**用“学习或生活规划模板 / 教学内容 / 提示词或数字包”这类笼统词作为组名。

## 4. 每类固定五段分析（组级，全部由真实列推导）

1. **是什么（具体交付物）**：载体 × 用途 组合出的商品类型。
2. **谁买**：取组内评分最高成员的目标人群（`profiles.json.target_user`）。
3. **为什么可能卖得动**：组内条数、`demand_raw` 合计、`demand_norm` 最高分位、`sellability_norm` 均值；**无可比成交价时写明「仅内容信号、无售卖证据」**；有价格信号时注明样本数为 `price_signals`，且**不是该类型自身成交价**。
4. **竞争与差异化**：该类型占全部机会的比例、组内可售（≥0.8）条数；**无竞品计数数据时写「需补采集平台在售数量」**。
5. **定价、毛利与风险**：`margin_low..high` 并集区间（标「模型假设」）、组内高频风险前 2；**无真实成交/订单时写「定价需补采集」**。

## 5. 质量线与默认统计口径（页面默认视图）

- **只统计已归类条目**：`商品型具体品类` + `内容型具体类别`。
- 从默认统计与组表中**剔除**：`Notion 其它（待人工）`、`未归类（待人工）`，以及**信号弱**条目。
- **质量线（可配置，当前取值）**：已归类 且（`demand_norm ≥ 0.70` **或** `sellability_norm ≥ 0.80` **或** 有参考价）。
  - 边界含等号：`0.70` 视为达线，`0.699` 不达线；`0.80` 达线，`0.79` 不达线。
  - 「有参考价」= `opportunity_sourcing_top10.csv` 中该机会的 `reference_max` 非空。
  - 未达线者标为「信号弱」，**不计入组级统计**（条数/需求合计/可售性均值/毛利区间），但在「查看已剔除条目」折叠区保留原链接可复查。
- **漏斗**：采集 60 → 已归类 N（商品 a / 内容 b；其中达线 x · 弱信号 y）→ 已剔除 M（其它 m + 未归类 n），且 `N + M = 60`。
- 组行标注「样本 N 条（已剔除无关/弱信号）」，确保被剔除条目不参与均值。

## 6. 守恒与兜底

- 分类守恒：各具体类型条数之和 + 待人工 = 总条数（脚本输出 `conservation` 字段，测试断言）。
- 只有 Notion 载体但无用途词 → 「Notion 其它（待人工）」，并记录原因。
- 既无载体也无用途词 → 「未归类（待人工）」，原因同时写入 `categories.json.unclassified_reason`。

## 7. 复算

```powershell
python tools\workbench\gen_profiles.py     # 生成 profiles.json / groups.json / product-taxonomy/{categories.json,model.md}
```
每条成员保留 `hit_words`（载体命中词 / 用途命中词），即“用途判定依据”。
