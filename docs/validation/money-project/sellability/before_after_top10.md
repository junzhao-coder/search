# Top10 前后对比（六维 → 七维含可售性）

- 旧：`scores_before.csv`（六维，Top1 0.800 @booorenjiiy）。
- 新：`scores_with_sellability.csv`（七维，Top1 0.763534 @aeshoui）。
- 新旧分数不可直接比大小（权重缩放 + 新维）；**看排名与可售性理由**。

## 新 Top10

| 新# | 旧# | 分数 | 可售性 | 作者/机会 | 可售性理由 |
| --- | --- | --- | --- | --- | --- |
| 1 | 7 | 0.763534 | 0.85 | @aeshoui · notion template for your class … selling it for 5 ph | 含明确售价 |
| 2 | 1 | 0.755000 | 0.50 | @booorenjiiy · notion template thread | 无价格/购买/赠送信号，中性 |
| 3 | 2 | 0.746207 | 0.50 | @mareidaily · CARA MENCARI … TEMPLATE NOTION | 中性 |
| 4 | 3 | 0.728621 | 0.50 | @worksfess · template notion lamaran kerja | 中性 |
| 5 | 4 | 0.721000 | 0.50 | 心愉自寂 · Notion模板怎么导入？ | 中性 |
| 6 | 6 | 0.719828 | 0.50 | @opteemisty · notion template reveal | 中性 |
| 7 | 8 | 0.707579 | 0.50 | Estela也是蛋挞 · Notion教程/拷贝模板 | 中性 |
| 8 | 9 | 0.702241 | 0.50 | @IAmPascio · Search Planner for ChatGPT | 中性 |
| 9 | 10 | 0.694158 | 0.50 | 177_bilibili · 177 Notion 教程 | 中性 |
| 10 | **23** | 0.690604 | 0.95 | @JamesEbringer · Sell it for $14/$21/$28 on Gumroad | 含售价+购买入口 |

## 跌出/下降

| 条目 | 旧# → 新# | 旧分 → 新分 | 可售性 | 原因 |
| --- | --- | --- | --- | --- |
| @heyeaslo “FREE Notion template for students … I’ll send it” | **5 → 15** | 0.759310 → 0.660414 | **0.10** | 纯 free 赠送，无售价/购买入口；高互动被可售性降权 |
| @bibabercerita “FREE NOTION TEMPLATE: BOOK TRACKER” | 11 → 22 | 0.727586 → 0.633448 | **0.10** | 纯 free 赠送 |
| @aeshoui “selling it for 5 ph” | 7 → **1** | 0.748276 → 0.763534 | **0.85** | 明确售价，升到榜首 |
| @JamesEbringer “Sell it for $14 ... Gumroad” | 23 → **10** | 0.644828 → 0.690604 | **0.95** | 明确售价 + 购买入口，进入 Top10 |
| @booorenjiiy 中性 thread | 1 → 2 | 0.800000 → 0.755000 | 0.50 | 无价格信号；被有售价机会超过 |

## 结论

- 至少 1 条纯免费帖显著下降：**@heyeaslo 5→15**；同类的 @bibabercerita 11→22。
- 含售价/购买入口的 @aeshoui、@JamesEbringer 上升，说明新维度不是单纯“降权所有 X 帖”，而是区分“可成交”与“纯需求/赠送”。
- 旧 Top10 仅 @heyeaslo 跌出；新 Top10 引入 @JamesEbringer（旧 23）。
- Top10 内 6 条中性（0.50），说明可售性只修正“明确可售/明确免费”两端；中性内容仍靠原六维排序。
