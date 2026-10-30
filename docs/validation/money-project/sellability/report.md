# B8 可售性维度交付摘要

> 任务：`task-80850b7537e8e664b3347b369f7ccdd5`（计划 v6 B8，用户方案 A）。
> 评分/规则/测试已收口；按用户最新优先级，前端（`/dash/opportunities` 可售性列）由独立 UI 任务 C 接力，本任务未启动服务、未截图、未改 UI 逻辑。

## 权重

| 指标 | 旧 | 新 |
| --- | --- | --- |
| 需求 | 0.30 | 0.255 |
| 竞争 | 0.20 | 0.170 |
| 毛利 | 0.20 | 0.170 |
| 履约 | 0.10 | 0.085 |
| 合规 | 0.10 | 0.085 |
| 可复制 | 0.10 | 0.085 |
| 可售性 | — | 0.150 |
| 合计 | 1.00 | 1.00 |

原六维等比 ×0.85；公式不变。详见 [model_diff.md](model_diff.md) 与 `scoring/model.md`。

## 规则

- 高 0.80–1.00：售价（¥/$/价格/售价/selling for/sold for）、购买入口（链接/扫码/私信购买/下单/buy/checkout）、商品化词（合集/素材包/模板包/教程包）。
- 低 0.00–0.20：`free`（排除 free shipping）、giveaway/giving away、免费/领取/抽奖/赠送/求推荐/有没有/推荐一下；`送` 只在“免费送/送出/送模板/送资料”等短语命中。
- 中性 0.40–0.60。
- 免费与售价/购买冲突：有购买入口→0.90（冲突说明）；无购买入口→0.10（冲突说明）。
- 闲鱼价格/`platform=xianyu` → 0.55，reason 写明“闲鱼标价为引流价”。
- 误伤：`free shipping`/`freedom` 不命中；`发送` 不命中“送”。

## 结果

- 60 行重算；Top1 `@aeshoui` 0.763534（可售性 0.85，含 selling for 5 ph）。
- 纯免费 @heyeaslo：rank **5→15**，0.759310→0.660414（可售性 0.10）。
- @bibabercerita 免费帖：11→22，0.727586→0.633448。
- @JamesEbringer 售价+购买入口：23→10，0.644828→0.690604（0.95）。
- 至少 1 条纯免费帖显著下降（实际 2 条）；Top10 具体见 [before_after_top10.md](before_after_top10.md)。

## 字段快照（供 UI C）

`scoring/scores.csv` 60 行 / 39 列；新增：

- `sellability_raw`
- `sellability_norm`
- `sellability_weighted`
- `sellability_reason`

sha256：`ab0c3546c3e9e46ffe726aa036aecce7e535c38fd54f3423c4e4b4bb03967cd1`

UI 直接消费，不重算。交接说明：[shots/UI_HANDOFF.md](shots/UI_HANDOFF.md)。

## 测试

- 完整套件：**334/334，exit=0**，50.906s（[test.log](test.log)）。
- 新增可售性单测：**5/5，exit=0**（[scoring_test.log](scoring_test.log)）。
- `test_scoring.py` 缺失需求覆盖率更新为 **0.745**（1−0.255），不是删断言。
- 旧 `tests/dash/test_routes.py` 的 0.800：改用隔离 `DASH_DATA_ROOT` fixture（合成 0.800，不写死生产榜首、不改真实 scores）。

## 限制

1. 规则是启发式，不是购买意向实测；“有价格”不等于成交。
2. 免费/售价冲突仅按购买入口判定，可能误判私信购买等隐式入口。
3. 闲鱼 ¥1 仅为引流价，0.55 只是“有价格但不可信”的中间分。
4. 60 条样本非概率抽样；Top10 排名对权重敏感。
5. UI 列未在本任务实现/截图，已交接 C；未启动服务，未改 app/dash/templates/dash 非必要内容。
6. 未重新采集、未发布互动、未改业务库/契约/迁移。
