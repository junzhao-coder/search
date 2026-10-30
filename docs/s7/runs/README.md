# runs/ 命名与留证约定

本目录用于每次滚动复盘的实际记录（**当前为空**，尚未产生任何真实经营数据）。

## 命名

```
docs/s7/runs/<YYYY-MM-DD>/          # 复盘日期（本地日期，默认 +08:00）
  operating_log.csv                 # 从 OPERATING_LOG_TEMPLATE.csv 复制后逐行记录（真实事件）
  review-<YYYY-MM-DD>.md            # 本次复盘结论、指标汇总、决策与理由
  evidence/                         # 用户提供的证据截图/导出（不含账号密码/支付凭证全文）
  daily-<date>.json / daily-<date>.csv  # 可选：tools/export_daily.py 的只读摘要副本
```

## 规则

1. **只放真实数据**：合成/示例/估算数据不得放入 runs；如混入须删除并在 `review-*.md` 说明。
2. **append-only**：历史 run 不覆盖、不改写；更正通过新 run 追加并注明原 `log_id`。
3. **证据与数字一一对应**：`operating_log.csv` 每个对外引用数字须能在 `evidence/` 找到对应证据。
4. **不含敏感信息**：不保存账号密码、支付凭证全文、买家个人隐私；截图须脱敏。
5. **复盘结论三选一**：暂未验证盈利 / 本期亏损 / 本期盈利（须附统计区间与样本量）。
6. **不伪造、不预填**：没有发生的事件不写；未确认的行 `user_confirmed=no`，不计入结论。

## 当前状态

- 目录下无 run（无真实经营记录）；模板见上级目录 `OPERATING_LOG_TEMPLATE.md/.csv`，流程见 `ROLLING_REVIEW_PROCESS.md`。
