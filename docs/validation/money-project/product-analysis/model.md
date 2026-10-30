# 产品分析生成规则（可审计，rev2 意图优先）

> 目的：把原始推文标题转成「产品是什么 / 为什么选它 / 有什么风险」。
> **不调用外部模型、不联网、不臆造数字**；文案只由 `scoring/scores.csv` 的字段确定性拼接。

## 1. 先判生意形态（intent），再判载体

| 优先级 | 生意形态 | 命中意图词（不区分大小写） | 目标人群 | 交付形态 |
| --- | --- | --- | --- | --- |
| 1 | 学习或生活规划模板 | class / course / student / school / study / notes / planner / tracker / habit / goal / budget / meal / workout / travel | 学生 | 学习/生活规划模板（可复制的页面或文档） |
| 2 | 求职简历资料 | cv / resume / job / internship / lamaran / apply / interview | 求职者 | 简历·求职排版与投递资料（可编辑文件） |
| 3 | 设计素材 | portfolio / design / psd / figma / ui kit | 设计师 | 设计素材包（PSD / Figma 源文件） |
| 4 | 提示词或数字包 | prompt / pack / bundle / gumroad / checkout / buy / sell | 内容创作者 | 提示词/数字包（文本库、模板包或下载文件） |
| 5 | 教学内容 | teaching / tutorial / guide / how to / import / setup | 教师 | 图文或视频教程（内容型交付） |
| 6 | 未分类 | 以上都不命中 | **人群未明确** | 待确认（需人工打开原始链接判断） |

**载体不是类型**：`notion` 只在 positioning 末尾追加 `；载体为 Notion 模板（可复制到自己的工作区）`，不参与类型判定。
**未分类条目改用「商业形态 + 需求档」区分**（不得同一句）：
- 商业形态：`可售`（`sellability_norm ≥ 0.8`）/ `免费引流`（`≤ 0.2`）/ `无价格信号`（其余，含字段缺失）
- 需求档：`高`（`demand_norm ≥ 0.7`）/ `中`（`0.4 ≤ x < 0.7`）/ `低`（`< 0.4`）/ `需求未评估`（缺失）
- 句式：`<商业形态>（可售性 NN / 无价格信号）的<需求档>需求线索（需求分位 NN%），品类待确认，需人工打开原始链接判断交付形态` + 载体尾巴；句子内嵌真实数值，保证各行不同。

## 2. 选择理由（最多 3 条，按固定优先级，必须挂真实数值）

优先级：`需求分位 > 可售性 > 毛利 > 竞争稀疏 > 综合评分`；仅在字段存在时生成。

- 需求：`需求位于本平台样本第 X% 分位（平台内百分位，原始需求值 N）` ← `demand_norm` / `demand_raw`
- 可售性：`可售性 NN（较强售卖|低信号|不明确）：<sellability_reason 原文>` ← `sellability_norm` / `sellability_reason`
- 毛利：`毛利估算 X%（，区间 A%–B%）（模型假设；价格信号 N 条样本（有效价 min–max））` ← `margin_mid/low/high` + `price_signals`
- 竞争：`竞争稀疏度 X%（平台供给先验 + 同作者惩罚）` ← `competition_norm`
- 评分：`综合评分 0.xxx（加权合计）` ← `total_score`

## 3. 主要风险（逐行差异化，每行 ≤2 条，仅字段支持时出现）

| 严重度 | 触发条件（严格） | 文案 |
| --- | --- | --- |
| 0.0 | `sellability_norm` 缺失/非数值 | 可售性未评估：缺少 `sellability_norm`，无法判断能否交付 |
| 0.1 | `sellability_norm ≤ 0.2` | 可售性仅 NN（低信号）：`sellability_reason` |
| 1.0 | `margin_assumption` 含 `all 20`/`fallback`/`basket proxy`/`全量回退` | 毛利低置信：使用品类回退价（毛利估算 X%），非该机会自身成交价 |
| 1.1 | `margin_high - margin_low > 0.3` | 毛利低置信：区间宽度 X%（A%–B%），估计范围过宽 |
| 2.0 | `competition_norm < 0.5` | 竞争偏密：稀疏度仅 X%（低于 50% 阈值，同质供给多） |
| 3.0 | `missing_metrics` 非空 | 缺失指标：`missing_metrics` |
| 4.0 | 存在毛利区间且 `cost_input` 为空或 `missing` | 成本缺失：无公开成本输入，毛利 X% 为假设区间而非实测 |
| 9.0 | 以上均不成立 | 数据面未见明显风险项；仍需人工核验原始链接真实性与可交付性 |

文案内嵌该行真实数值，因此不同行不会完全相同。**许可待核验不在本生成器中输出**：`scores.csv` 无逐条 `license_verdict`，`sources.csv` 无与 60 条机会连接的键（`scores.source` 为采集描述），属数据缺口，界面不臆造。

## 4. 硬约束

- 不出现「稳赚 / 已验证需求 / 保证销量」；不显示订单、收益、成交量（数据中不存在）。
- 毛利一律标「模型假设」；可售性一律来自 `sellability_norm` 分档。
- 原始标题、作者、时间、链接、评分构成**只在展开的证据区**。
- 关键词搜索同时匹配产品摘要（意图/人群/载体/理由/风险）与原始标题。

## 5. 复算

```powershell
python tools\workbench\gen_profiles.py
```

`profiles.json` 每条含 `evidence_fields[]`，列出该条文案实际用到的 `scores.csv` 列，可逐条对照复核。
