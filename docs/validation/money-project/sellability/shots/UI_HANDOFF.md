# UI 交接：可售性列（不在本任务截图）

按用户最新优先级，前端 `/dash/opportunities` 由独立 UI 任务（session-c1428bc7）接手；本任务**不启动服务、不截图、不改 app/dash/templates/dash/tests/dash 的 UI 逻辑**。

UI 侧可直接消费已冻结的 `scoring/scores.csv`：

- 新增列：`sellability_raw`、`sellability_norm`、`sellability_weighted`、`sellability_reason`
- 页面建议：在机会表加“可售性”列，显示 `sellability_norm`（两位小数）+ `sellability_reason`（短文本/hover）；不要在前端重算规则。
- 数据快照 sha256：`ab0c3546c3e9e46ffe726aa036aecce7e535c38fd54f3423c4e4b4bb03967cd1`
- 行数：60；Top1 `@aeshoui` 0.763534；纯免费 @heyeaslo 1→15（旧→新）。

旧测试已用隔离 fixture 解耦：
`tests/dash/_fixtures/opportunities_data/.../scores.csv`（合成 0.800，不写死生产榜首）。
