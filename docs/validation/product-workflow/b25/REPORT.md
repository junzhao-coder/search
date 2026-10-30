# B25｜复盘 4 个数字：反馈记录表 + 只读脚本（交付报告）

> 执行者：C3（`session-48004521-daf2-548c-a355-487cc6de6e72`）｜任务 `task-cba0d0642b0be5568341dda692339eb3`（计划 v8）
> 口径对齐 [b24/FEEDBACK-CARD.md](../b24/FEEDBACK-CARD.md)（同一张卡、同一套字段与公式）。**未虚构真实经营数据**；CSV 内两行均已标注 synthetic 示例。
> 边界：只写 `docs/validation/product-workflow/b25/`；未改工作台代码与导出语义、未改业务库/CONTRACT/评分与货源 CSV；未登录平台、未采购、未发布。

## 1. 交付物

| 文件 | 说明 |
| --- | --- |
| [feedback-log.csv](feedback-log.csv) | 12 列表头（与 FEEDBACK-CARD 一致）+ **2 行 synthetic 示例**（备注写明"不是真实经营数据"） |
| [review.py](review.py) | 纯标准库只读脚本：算 4 指标 + 一条建议；默认人类可读、`--json` 结构化 |
| [tests/test_review.py](tests/test_review.py) | 6 个单测（正常/零成交/耗时 0/na/非法数字/json 字段） |
| [tests/__init__.py](tests/__init__.py) | 包标记（`unittest discover -s tests -t .` 需要） |
| [run_evidence.py](run_evidence.py) | 证据采集器：跑单测与两次脚本，记录 argv/cwd/UTC/returncode |
| [README.md](README.md) | 三步说明 + 阈值 + 假设 + 出错行为 |
| `tests-run.log` / `run-default.log` / `run-json.log` / `run-manifest.json` | 真实运行日志与清单（含 returncode） |
| 本文件 | 交付报告 |

## 2. CSV 表头与示例行

表头（12 列，与验收一致）：

```
日期,单号,渠道,曝光,询单,成交,退款,实际售价,到手,人工耗时分钟,交付方式,备注
```

两行示例（**虚构**，用于演示"有成交"与"零成交观察期"两种形态）：

| 日期 | 单号 | 渠道 | 曝光 | 询单 | 成交 | 退款 | 实际售价 | 到手 | 人工耗时分钟 | 交付方式 | 备注 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 2026-10-24 | wo:20261023-88ef9a66 | xianyu | na | 6 | 2 | 0 | 19.9 | 35.82 | 180 | 站内文件 | synthetic 示例（虚构数据，仅演示脚本；不是真实经营数据） |
| 2026-10-24 | wo:20261023-88ef9a66 | xianyu | na | 4 | 0 | 0 | 19.9 | 0 | 60 | 站内文件 | synthetic 示例（零成交观察期演示；不是真实经营数据） |

> 与卡片的一处用词差异：卡片写"曝光/浏览"，CSV 列名按验收用 `曝光`，README 已注明对应关系。

## 3. 脚本参数与阈值

| 参数 | 默认 | 作用 |
| --- | --- | --- |
| 位置参数 `csv` | 必填 | 要读的 CSV（只读） |
| `--json` | 关 | 输出结构化结果（指标/建议/假设/合计/错误清单） |
| `--cost` | `0.0` | 采购成本（元/件）；CSV 无此列，故用参数 |
| `--aftersales` | `0.0` | 售后摊销（元/件） |
| `--min-conv` | `20.0` | 转化率阈值（%） |
| `--min-hourly` | `30.0` | 折算时薪阈值（元/小时） |
| `--max-refund` | `20.0` | 退款率阈值（%） |

脚本顶部同名常量（`THRESHOLD_MIN_CONVERSION_PCT` / `THRESHOLD_MIN_HOURLY_CNY` / `THRESHOLD_MAX_REFUND_PCT` / `DEFAULT_COST_PER_UNIT` / `DEFAULT_AFTERSALES_PER_UNIT`）可直接改。

## 4. 四个指标的公式与除零处理

| 指标 | 实现 | 缺失/零值处理 |
| --- | --- | --- |
| 询单转化率 | `成交 ÷ 询单 × 100` | 询单为 0/None → `None`（输出 `na`），不除零 |
| 单件净利 | `(到手合计 ÷ 成交) − 采购 − 售后摊销` | 成交为 0 或到手为 na → `None`；采购/摊销缺省 **0** 并在输出注明假设 |
| 折算时薪 | `单件净利 ÷ (人工耗时分钟 ÷ 60)` | 耗时为 0/na 或净利为 None → `None` |
| 退款率 | `退款 ÷ 成交 × 100` | 成交为 0 → `None`；判"样本不足" |

**样本不足三分支**（按验收）：`成交=0` / `耗时=0` / 四指标全 `na` → 输出 `样本不足，保留观察期`，不崩、不除零。

## 5. 建议分支（四选一 + 样本不足）

| 优先级 | 条件 | 建议 | 依据文本（输出里会打印） |
| --- | --- | --- | --- |
| 0 | 成交=0 / 耗时=0 / 全 na | `样本不足，保留观察期` | 列明成交、耗时与 na 情况，建议至少 7 天 |
| 1 | 单件净利 ≤ 0 | `换品` | 净利 ≤0：先换品/换货源，别降价硬撑 |
| 2 | 退款率 > 阈值(20%) | `修描述` | 先修描述与交付（写清含/不含、交付与售后），别用降价掩盖 |
| 3 | 转化率 < 阈值(20%) 且询单>0 | `修描述` | 买家问了没下单 → 先改详情与价格说明 |
| 4 | 时薪 < 阈值(30) 且净利>0 | `提价` | 提价或标准化交付压耗时 |
| 5 | 都不触发 | `继续` | 维持做法，记下一个观察期 |

> `修描述` 覆盖两类来源（退款高 / 转化低），依据文本不同但标签同属"修描述"，保证**一次只给一条**建议。

## 6. 单测与真实 exit

命令（在 `b25/` 下，`.venv` Python 3.12）：`python -X utf8 -m unittest discover -s tests -t . -v`
结果：**Ran 6 tests … OK，returncode=0**（[tests-run.log](tests-run.log)）。

| 用例 | 覆盖点 |
| --- | --- |
| `test_normal_four_metrics` | 四指标数值（40.0% / 100.0 元 / 20.0 元每小时 / 25.0%）且高退款触发「修描述」 |
| `test_zero_orders_is_insufficient` | 成交=0 → 样本不足，摘要仍打印 |
| `test_zero_minutes_is_insufficient` | 耗时=0 → 时薪 na → 样本不足 |
| `test_na_values_skipped` | 到手 na → 净利/时薪 na，不报错 |
| `test_invalid_number_reports_line_and_field` | 非数字 → 报「第 3 行 / 询单 / 不是数字」，**退码 2**，摘要仍在 |
| `test_json_mode_fields_complete` | `--json` 顶层 7 字段 + 5 个指标键 + 建议 label/reasons + 阈值 |

**脚本两次真实运行**（[run-manifest.json](run-manifest.json)）：
- `review.py feedback-log.csv` → **returncode=0**（[run-default.log](run-default.log)）：合计 询单 10 / 成交 2 / 退款 0 / 到手 35.82 / 耗时 240；四指标 20.0% / 17.91 元 / 4.48 元每小时 / 0.0%；建议【提价】（时薪 4.48 < 30 且净利为正）。
- `review.py feedback-log.csv --json` → **returncode=0**（[run-json.log](run-json.log)）：结构化字段齐全。

清单里每条 run 都记了 `argv` / `cwd`（`…\b25`）/ `start_utc` / `end_utc` / `returncode`。

## 7. README 三步

1. **填表**：按 [b24/FEEDBACK-CARD.md](../b24/FEEDBACK-CARD.md) 的口径填 [feedback-log.csv](feedback-log.csv)（曝光不显示写 `na`；零成交写 `0`；先删掉示例行）。
2. **跑脚本**：`python review.py feedback-log.csv`（要机读加 `--json`）。
3. **看建议**：先看 4 个数字，再看一条建议（`继续`/`提价`/`换品`/`修描述`，或 `样本不足，保留观察期`）；有成本就加 `--cost` / `--aftersales`。

并写明：**阈值可改**（参数或顶部常量）、**建议不等于平台结论、不代表收益/审核结果**。

## 8. 未覆盖 / 需用户确认

1. **采购成本与售后摊销没有数据列**：目前靠参数（缺省 0），示例输出里"单件净利 17.91 元"就是"到手 35.82 ÷ 2 件、成本按 0"的机械结果，**不是真实利润**。用户首次跑时请用 `--cost/--aftersales` 填真实值。
2. **时薪口径**把该行人工耗时当作对应这批成交的总投入；若一行里混了多个 SKU 或含非交付耗时（写文案、上架、拍照），时薪会偏低——本脚本不做工时分摊。
3. **未做多期趋势**：只对单个 CSV 做汇总；跨周对比、环比、图表未实现。
4. **未接工作台**：不读 `workflow.sqlite3`、不改导出语义；单号只是备注性字段，不校验存在性。
5. **平台口径未核**：曝光/询单/成交/退款的定义以平台后台为准，脚本只做算术。
6. 示例 CSV 是 synthetic（备注已注明）；未登录、未采购、未发布，无真实经营数据。
