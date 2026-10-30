# S4 情景增量设计（销量假设 / 一次性摊销 / 季度年度归一月额 / 余分）

> 状态：**设计稿（本批不写实现、不运行应用或测试）**。修订 2：按策划者退回意见修正每单取整路径、真零判定、参数解析分层、估算与门槛边界，并记录本批裁定。
> 依据（已读）：[数据与接口契约 v3](<CONTRACT.md>) §0.3/§0.4/§0.8、§1.5（`cost_item` 字段与约束）、§3.5（G3/G4）、§5.5（情景口径与例 A/B/C）、§9（S4 未决项）；[开发总体计划](<../../DEVELOPMENT_PLAN.md>) §8（S4-B2）与第 92 行 S2 边界；[S2 核心实现记录](<S2_CORE.md>) §3、§6、§10–§11。
> 真实调用路径（已读代码）：`GET /api/candidates/<id>/scenario?variant=base` → `app/api/routes.py::get_scenario`（292–295，页面内部同路径见 482 行）→ `app/core/scenario.py::compute_scenario`（180 行）；成交快照 `app/core/feedback.py:70–71` 以**默认参数**调用同一函数后写入 `predicted_net_per_order_minor`（I4 不可改）。
> 技能：本会话无 `skill` 调用通道（执行者角色不可用），ponytail 以**磁盘读取** SKILL.md（120 行，full）遵循；本批未引入任何依赖、未运行应用或测试。

## 1. 现状（可直接复用的部分）

- `compute_scenario` 已返回：`per_order{procurement/platform_fee/payment_fee/refund_reserve/acquisition/manual_labor/other}`、`known_subtotal_minor`、`contribution_per_order_minor`、`one_time_total_minor`、`fixed_cost_gap_minor`、`recurring_monthly_total_minor`、`recurring_detail[{role,period,money_minor}]`、`amortize_orders`（**恒为 `null`**）、`unknown_components`、`assumptions`、`explanation`、`complete`、`net_per_order_minor`。
- 取整工具（`app/core/money.py`）：`apply_rate(base,bp)=(base*bp+5000)//10000`、`labor_minor(min,hourly)=(min*hourly+30)//60`，均对非负输入 ½ 分向上；派生值可为负（§0.3）。
- 选择规则：成本行须属于**当前有效 G2 所选货源**（本候选完全没有货源时普通行计入）；`sale_price` 不参与成本求和且不按供给过滤（§5.5-7/-8）。`recurring_monthly_total_minor` 目前仅在**全部 recurring 行为 monthly** 时给出，否则 `null`（§5.5-4）。
- 结论：本增量**不新增端点、不加表/列、不加依赖**，只给现 GET 情景增加三个可选 query 参数，并复用 `amortize_orders` 字段承载生效的摊销假设。

## 2. 最小增量请求 / 响应

请求（全部可选，省略即与 S2 逐字段一致）：

| 参数 | 取值（**HTTP query 文本**） | 语义 |
| --- | --- | --- |
| `amortize_orders=N` | 十进制整数文本 `1..1000000` | 一次性成本摊销的**总单数**假设（不是月销量） |
| `monthly_orders=M` | 十进制整数文本 `1..1000000` | **月销量**假设，用于把周期成本折到每单 |
| `normalize_periods` | `1` 或 `0`（缺省 `0`） | 允许把 `quarterly`/`yearly` 纳入归一月额；不提供销量假设时仅做单位换算 |

**解析分层**：HTTP 层只接受“合法十进制整数 query 文本”——去首尾空白后匹配 `^[0-9]+$`，再转为 `int` 交给 core；空文本、`abc`、`0`、负数、`1.5`、超出上限一律 `422 invalid_field`（`details` 指明字段）。core 的 `compute_scenario` 只接受 `int`（且**拒绝 `bool` 与 `float`**，不做“静默取整”），因此 `True`/`20.0` 在 core 直调路径同样非法。

响应增量（其余字段与规则不变）：

| 字段 | 说明 |
| --- | --- |
| `amortize_orders` | 本次生效的摊销总单数；未提供 → `null`（保持 S2） |
| `monthly_orders` | 本次生效的月销量；未提供 → `null` |
| `normalized_periods` | 是否启用周期归一（`true`/`false`） |
| `one_time_per_order_minor` | 一次性成本每单摊销额；无假设或未知 → `null`；`T=0` → `0` |
| `recurring_per_order_minor` | 周期成本每单额；无假设或未知 → `null`；`a=0` → `0` |
| `recurring_monthly_total_minor` | 启用归一后为**归一月额显示值**（见 §3.3）；未启用时保持 S2 语义 |

`net_per_order_minor = contribution − one_time_per_order − recurring_per_order`（两者都已知时），否则 `null`。

## 3. 公式与手算（金额一律整数分；`T`=一次性总额，`a`=周期成本精确年化额，`N`/`M`=上述假设）

### 3.1 逐单部分（沿用 S2，未改）

`contribution = sale_price − (procurement.per_order + platform_fee + payment_fee + acquisition + refund_reserve + manual_labor + other)`

- 费率行：`apply_rate(sale_price,bp) = (sale*bp+5000)//10000`。手算：`33.33 元 → 3333 分`，`500bp → (3333*500+5000)//10000 = 167`。
- 人工：`labor_minor(minutes,hourly) = (minutes*hourly+30)//60`。手算：`15 分 × 3000 → (45000+30)//60 = 750`。
- 例 A（契约 §5.5）：`1000 − (300+50+0+0+0+500+0) = 150`，`complete=true`、`net=150`。
- `sale_price` 永不进入成本求和；成本高于售价时为负：例 C `1000 − 1200 = −200`。

### 3.2 一次性成本摊销（与贡献值分开）

- `one_time_total_minor = T`（来自 `procurement.one_time` 行，**不进入 `contribution`**）。
- `one_time_per_order = round_half_up(T/N) = (2T+N)//(2N)`。
- 契约例 B：`T=10000, N=20 → (20000+20)//40 = 500`；`contribution=450`（逐单采购显式 0）→ `net = 450 − 500 − 0 = −50`。
- 余数例：`T=10001, N=2 → (20002+2)//4 = 5001`（真值 5000.5 → ½ 分向上）；`T=0 → 0`（真零，无需假设）。
- `T` 未知 → `one_time_per_order=null`、`complete=false`、`net=null`；`T>0` 且未给 `N` → 同上且 `fixed_cost_gap_minor=T`。

### 3.3 精确年化额 `a`、归一月额显示 `R` 与余分

- **精确汇总（不取整、不提前归一）**：`a = 12*Σmonthly + 4*Σquarterly + Σyearly`（分）。
  · 归一启用：纳入全部三种周期（要求所有 recurring 行金额已知，否则 `a` 未知）。
  · 归一未启用：`a = 12*Σmonthly`，且**只要存在非月度 recurring 行即视为不可归**（`a` 未知）——与 S2 的 `recurring_monthly_total_minor=null` 一致。
- **显示用月额**：`R = round_half_up(a/12) = (a+6)//12`；精确余分 `r = a − 12R`，`|r| ≤ 6`。
  `|r| ≤ 6` **只是显示误差界**（显示的月额与精确年化值最多差 6 分），**不表示精确守恒**，更不得把 `R` 用于后续计算。
- 手算：`quarterly=10000 → a=40000, R=(40006)//12=3333`；`yearly=12000 → a=12000, R=1000, r=0`（精确）；`quarterly=1 → a=4, R=0, r=4`；`quarterly=3 → a=12, R=1, r=0`。
- 精确值始终是 `a`；`R` 仅用于展示，**任何每单金额都从 `a` 直接计算**。

### 3.4 周期成本的每单额（**直接对 `a` 取整**）

`recurring_per_order = round_half_up(a/(12*M)) = (2a + 12M) // (24M)`（`M` 已给）。

- 手算：`quarterly=10000 (a=40000), M=10 → (80000+120)//240 = 333`（40000/120=333.33）；`yearly=12000 (a=12000), M=4 → (24000+48)//96 = 250`（精确）。
- **反例（不得拿取整后的 `R` 再除 `M`）**：`quarterly=10001 → a=40004, R=(40010)//12=3334`（显示），`M=4`：
  · 错误路径 `round(R/M) = round(3334/4) = 834`；
  · 正确路径 `round(40004/48) = 833`（40004/48 ≈ 833.4167）；
  · `contribution=150, T=0` → `net = 150 − 833 = −683`（不是 −684）。
- 真零与是否需 `M` **按原始行与精确 `a` 判定**：`a=0` 才算真零（无需 `M`）；`a>0` 即使 `R` 显示 0（如 `quarterly=1`）**仍必须有 `M`**，否则 `null`/`complete=false`。
- `a>0` 且未给 `M` → `recurring_per_order=null`、`complete=false`、`net=null`；`fixed_cost_gap_minor` 仍按 §3.5 的 S2 语义（不被改成月额）。
- 负利润照实返回：`contribution=−200, T=10000, N=20 → net = −200 − 500 = −700`。

### 3.5 完整性与缺口（未知 / 真零 / 缺失 / 非法分开）

`complete=true` 必须同时满足：逐单全部已知（`contribution` 可算）、`T` 已知、`a` 已知（至少存在一条 recurring 行且全部金额已知）、`T=0 或 N 已给`、`a=0 或 M 已给`、且 `unknown_components` 为空。

| 情形 | `complete` | `net` | 缺口与说明 |
| --- | --- | --- | --- |
| 逐单已知、`T=0`、`a=0`（原 recurring 行全部显式 0） | `true` | `= contribution` | 真零无需任何销量假设 |
| 逐单已知、`T=0`、`a>0`、`M` 已给 | `true` | `= contribution − recurring_per_order` | 例：`quarterly=1, M=4 → per_order=0 → net=contribution` |
| 逐单已知、`T=0`、`a>0`、`M` 缺失 | `false` | `null` | **`R` 显示 0 也算“需 `M`”**；缺口按 S2（同周期原额） |
| `T>0`、`N` 已给、`a=0` | `true` | `= contribution − one_time_per_order` | 例 B |
| `T>0`、`N` 缺失 | `false` | `null` | `gap=T`；摊销总单数不能当销量 |
| 仅 `N`（无 `M`）且 `a>0` | `false` | `null` | 一次性可算、周期每单额未知；`gap=T` |
| 仅 `M`（归一未启用）且全部 monthly | 可为 `true` | `= contribution − recurring_per_order` | `a=12Σmonthly`；每单额正常 |
| 仅 `M`（归一未启用）但存在非月度行 | `false` | `null` | `a` 未知（不静默忽略季度/年度行） |
| 仅归一（无 `M`）且 `a>0` | `false` | `null` | `R` 可显示、每单额 `null`；`gap` 按 S2（同周期原额；混合 → `null`） |
| 任一 recurring 行金额未知 | `false` | `null` | `a` 未知；不把未知当 0 |
| 参数非法（`0`/负/超限/非整数文本/`bool`/`float`） | — | — | `422 invalid_field`，零写入 |

**缺口 `fixed_cost_gap_minor` 保持 S2 语义（本批裁定，不改为 `R`）**：`T>0 → T`；否则**同一周期**存在正额 recurring → 该周期原金额之和；混合周期正额 → `null`。`explanation` 必须**分别**说明“S2 原金额/原 period 提示”与“本次摊销/归一结果”，避免把两者混为一谈。

## 4. 兼容与版本策略

- **默认路径零变化**：未提供任何新参数时 `amortize_orders=null`、`normalized_periods=false`、`recurring_monthly_total_minor`/`fixed_cost_gap_minor`/`complete`/`net` **逐字段与 S2 完全一致**（既有 57 项边界用例与 S2-20/21 行不作废）。
- 新语义**仅在显式参数下生效**：`normalize_periods=1` 才把 `quarterly`/`yearly` 纳入 `a` 与归一月额显示（契约 §5.5-4 明确“归一规则属 `[S4]`”，本批不改契约文字）。
- 响应只**新增**字段；`amortize_orders` 由“恒 `null`”变为“回显生效假设”（未传仍 `null`）。
- 成交预测快照调用**默认参数**路径，故 S4 参数**不改变**任何历史或新增快照值；`actual_net_per_order_minor`/`actual_complete` 仍为 `NULL`（实际利润属 S5）。

## 5. 不变量与边界（不得退化）

1. `GET` 类接口**零写**：参数只影响计算，`gate_review`/`review_item`/`cost_item` 行数与时间戳不变。
2. 门槛只认**有效已核验的 G2**：本候选唯一非 `invalid` 货源在**没有**有效 G2 时只用于**数值估算**（情景成本匹配），估算**不升级任何门槛**；未核/`failed`/`expired` 的 G2 同样不升级。门槛状态只可能是 `unverified`/`verified`/`failed`/`expired`（`pending` 是**候选**状态，不是门槛状态）。
3. 未知 ≠ 0，0 ≠ 未知；情景给出净值**不能**自动通过 G3/G4，也不能把“情景完整”当作证据。
4. 同值不同来源的成本不得混入：只取选定货源的行（`sale_price` 例外，§5.5-7/-8）；改绑须走真实写接口（§11 已支持同值改绑）。
5. 不新增存储：假设按请求计算，不落库、不进快照；不新增表/列/依赖。

## 6. 下一批代码精确 scope

| 文件 | 改动 |
| --- | --- |
| `app/core/scenario.py` | `compute_scenario(..., *, amortize_orders=None, monthly_orders=None, normalize_periods=False)`；**core 侧校验**：`amortize_orders`/`monthly_orders` 只接受 `int` 且 `1..1000000`（拒绝 `bool`/`float`），`normalize_periods` 只接受 `bool`；新增 `_round_half_up_div(a, d)`；实现 §3.2–§3.5（每单一律由 `a` 直接取整）；`explanation` 增假设说明并区分 S2 原额提示；返回值新增 §2 的 5 个字段 |
| `app/api/routes.py` | 仅 `get_scenario`：解析 query 文本（trim + `^[0-9]+$` + 范围 + `normalize_periods∈{0,1}`），非法 → `422 invalid_field` 且零写入；其余路由不动 |
| `tests/api/test_gates_scenario.py` | 新增 `ScenarioAmortizationTest`（§7 矩阵，含期望值），复用现有 helpers |
| `tests/api/_tmp/s4_scenario_<ID>/` | 运行隔离库与日志（不删旧产物） |
| 文档 | 记录位置由策划者指定（建议 S2_CORE 追加 §12）；**本批未改任何 S2 文档** |

不做：新端点/新表/新列/新依赖、`feedback` 快照路径改动、S5 运行费与预算、实际利润核算、退款实际聚合、S4 排序/匹配大包、界面改动。

## 7. 验收测试矩阵（下一批执行，含期望值）

| # | 输入（API 路径） | 期望 |
| --- | --- | --- |
| 1 | 例 B 形状 + `amortize_orders=20` | `contribution=450`、`one_time_total=10000`、`one_time_per_order=500`、`net=−50`、`complete=true` |
| 2 | 同 #1 不传参数 | `net=null`、`complete=false`、`gap=10000`、`amortize_orders=null`（S2 兼容） |
| 3 | `quarterly=10000` + `normalize_periods=1` | `recurring_monthly_total=3333`、`normalized_periods=true`、细节保留 `period=quarterly`/`10000` |
| 4 | `yearly=12000` + 归一 + `monthly_orders=4` | `a=12000`、`R=1000`、`recurring_per_order=250`、`net=150−250=−100` |
| 5 | **`quarterly=10001` + 归一 + `M=4`** | `a=40004`、`R=3334`（显示）、`recurring_per_order=833`、`net=150−833=−683`（反例：`R/M` 会得 834/−684） |
| 6 | `quarterly=1` + 归一 + `M=4` | `a=4`、`R=0`、`recurring_per_order=0`、`complete=true`、`net=150` |
| 7 | `quarterly=1` + 归一 + **无 `M`** | `complete=false`、`net=null`（`a>0` 需月销量），`gap=1`（S2 同周期原额提示） |
| 8 | 原 recurring 行全部显式 0（`monthly=0` 或 `quarterly=0`）+ 归一 + 无 `M` | `a=0`、真零、`complete=true`、`net=150` |
| 9 | 混合周期 `monthly=100` + `quarterly=10000` + 归一 + `M=4` | `a=41200`、`R=3433`、`recurring_per_order=858`、`net=150−858=−708`；未归一时 `complete=false` |
| 10 | recurring 行金额为 NULL + 归一 | `a` 未知 → `recurring_monthly_total=null`、`complete=false`、`net=null`、`gap=null` |
| 11 | 仅 `N`（无 `M`）且 `a>0` | `one_time_per_order` 有值、`complete=false`、`net=null`、`gap=T` |
| 12 | 仅 `M`（无归一）且全部 monthly | `a=12Σmonthly` → 每单额正常、`complete` 可为真；含非月度行 → `complete=false` |
| 13 | 仅归一（无 `M`）且 `a>0` | `R` 有值、`recurring_per_order=null`、`complete=false`、`net=null`、`gap` 按 S2（同周期原额；混合 → `null`） |
| 14 | 解析/校验：`amortize_orders=` 空、`abc`、`0`、`-1`、`1000001`、`1.5` | 均 `422 invalid_field` 且零写入；`20`、` 20 ` 正常；`normalize_periods=2`/`true` → `422`；core 直传 `True`/`20.0` → 拒绝（不静默取整） |
| 15 | 亏损 `contribution=−200` + `N=20, T=10000` | `net=−700`（负值如实返回） |
| 16 | A/B 两货源、选定 B；以及无有效 G2 但唯一非 invalid 供给 | A 行不计入（`sale_price` 例外）；唯一货源仅作**数值估算**，门槛仍为 `unverified`/`failed`/`expired` 之一（**无 `pending` 门槛状态**） |
| 17 | 两次相同 GET（含参数） | 响应一致、行数/时间戳不变（GET 零写） |
| 18 | 成交后带参数 GET | 历史 `predicted_net_per_order_minor` 不变、`actual_*` 仍 `NULL` |
| 19 | 回归 | `test_gates_scenario`(57)、`test_feedback_draft`(8)、`test_import_api`(27)、core/storage 18 项、隔离 E2E；全量 discover 用镜像跑法避免跨 scope 写 `_tmp` |

## 8. 本批裁定（已定，不再作为待议项）

1. **归一显式启用**：`normalize_periods=1` 才纳入季度/年度；默认路径与 S2 逐字段一致（不改 S2-20/21 行）。
2. **`N`/`M` 上限 1e6**，只接受十进制整数文本（HTTP）/`int`（core），拒绝 `bool`/`float`/`0`/负/超限。
3. **假设不落库**：不写入任何表、不进快照；如需留痕属另一次授权（涉及存储与 S5 预算）。
4. **`fixed_cost_gap_minor` 保持 S2 语义**（`T`／同周期原额／混合 `null`），**不改为月额 `R`**；`explanation` 分别标注“S2 原额提示”与“本次摊销/归一结果”。

## 9. 声明与排除

- 本批**只产出本文档**：未运行应用或测试、未写业务库、未改契约/代码/测试/S2 文档/根台账/快照、未新增依赖、无网络与费用。
- 排除：S5 运行费用台账与预算保护、实际利润核算、退款实际聚合、摘要与付费模型、S4 排序与货源匹配大包、界面实现。
- 未知报价不填 0、费用确认不绕过；本批不声称 S4 已实现或收益已验证。以上裁定如需改动，应走新版计划/新任务授权。

## 10. 实施记录（task-79fcc3d63d74cd9de76839410c67bcef，小批实现）

§1–§9 为设计批（未写实现、未运行应用或测试）；本节的实施批**已实现并实测**，仅记实际成果，不改上文历史。

### 10.1 落点（仅限定范围）

| 文件 | 实际改动 |
| --- | --- |
| `app/core/scenario.py` | 新增 `PERIOD_MONTHS`/`annualized_minor(period, amount)`、`_round_half_up_div(a,d)`、`_assumption_orders(name,value)`（只收 `int`，拒 `bool`/`float`，范围 1..1_000_000）、`_normalize_flag(value)`（只收 `bool`）；`compute_scenario(..., *, amortize_orders=None, monthly_orders=None, normalize_periods=False)`：精确年化 `a`、显示 `R=(a+6)//12`、每单周期 `(2a+12M)//(24M)`、一次性 `(2T+N)//(2N)`；返回值新增 `monthly_orders`/`normalized_periods`/`one_time_per_order_minor`/`recurring_per_order_minor`，`amortize_orders` 由恒 `null` 改为回显假设；`explanation` 增加归一月额、摊销两条说明，并在“已可算”时不再输出 `net 置空` 文案 |
| `app/api/routes.py` | 仅 `get_scenario`：新增 `_orders_query`（trim 后 `^[0-9]+$`、1..1_000_000）与 `_flag_query`（仅 `0`/`1`），非法 → `422 invalid_field`；其余路由未动 |
| `tests/api/test_gates_scenario.py` | 新增 `ScenarioAmortizationTest`（19 项），覆盖 §7 场景 + 解析/core 校验 + GET 零写 + 快照不可变 + 单货源估算不升级门槛 |
| `tests/api/_tmp/s4_scenario_impl/run_20261014_01/` | 本轮隔离库、镜像与日志（未删旧产物） |

### 10.2 与设计的一致性 / 一处偏差

- 一致性：默认路径（无参数）逐字段保持 S2——包括“旧 recurring 原行全部显式 0（含非月度）时 `complete` 可为 true 而 `recurring_monthly_total_minor=null`”，实现按“显式全 0 ⇒ `a=0`（与周期无关）”处理，不使新的“不可归”条件误伤默认成交快照；`a>0` 即使显示 `R=0`（`quarterly=1`）仍必须有 `M`；`fixed_cost_gap_minor` 全程沿用 S2 原额/原周期语义，`explanation` 区分“S2 原额提示”与“本次摊销/归一结果”。
- **偏差（不可达场景）**：设计 §7 第 9 行的“同候选 monthly+quarterly 双活跃 recurring 行”在冻结 schema 下**不可表达**——`cost_item` 对 `(candidate_id, role, basis, variant)` 的活跃行有唯一约束，任何第二条活跃行都会 `IntegrityError`。测试改为：断言该约束确实拒绝第二条活跃行，并直接校验公式（`annualized_minor` 混合 = 41200、`R=3433`、`_round_half_up_div(41200,48)=858`、`net=−708`），不再伪造不可达状态。

### 10.3 实测（隔离库；命令与退出码）

| 步骤 | 命令 | 结果 |
| --- | --- | --- |
| 目标文件 | `python -X utf8 tests\api\test_gates_scenario.py` | `Ran 76 tests … OK`，**exit=0**（57 既有 + 19 新增）→ `05_all_with_s4_tests.txt` |
| 其他回归 | `test_feedback_draft` / `test_import_api` / `test_money` / `test_identity` / `test_migrations` | 8 / 27 / 7 / 7 / 4 项，各自 **exit=0** |
| 隔离 E2E | `& .\instance\_e2e.ps1` | `RESULT PASS` / `E2E_OK`，**exit=0**，`business_db_unchanged=True` → `06_isolated_e2e.txt` |
| 镜像全量 | 复制 `app/`（排除 `sources`）与 `tests/`（排除 `_tmp`/`sources`/`fixtures`）到本轮 run 目录后 `python -X utf8 -m unittest discover -s tests -t .` | `Ran 143 tests … OK`，**exit=0** → `07_mirror_discover.txt`；关键文件 SHA256 与实时源一致（`scenario.py` A8E658A3…、`routes.py` F1DF3BB2…、`test_gates_scenario.py` D76EF682…），镜像 app 34 文件 / tests 137 文件，**不含并行 A 未提交的 sources 范围** |
| 业务库 | `instance/app.db` | 运行前后 SHA256 均 `E073F828CF0F30D6206361BBA3A729826BE096BE3308F5A5DC204406DAE4EB85`（未删除重建） |

确定性断言（节选）：例 B `contribution=450/one_time=10000/N=20 → 500 → net=−50`；`quarterly=10001 + 归一 + M=4 → R=3334（显示）、每单 833、net=−683`；`quarterly=1 + M=4 → complete=true/net=150`，`quarterly=1 无 M → complete=false/net=null/gap=1`；`quarterly=0 或 monthly=0 显式零 → complete=true`（归一开/关均成立）；未知 recurring 行 → 全 `null`；仅 `N`／仅 `M`（无归一）／仅归一（无 `M`）三分支；参数非法（空/`abc`/`0`/`-1`/`1000001`/`1.5`/`normalize_periods∈{2,true}`）→ `422 invalid_field` 且 `gate_review`/`review_item`/`cost_item` 计数不变；core 直调 `True`/`20.0`/`"20"`/`normalize_periods=1` → `AppError`；GET 前后 `gate_review`/`review_item`/`cost_item`/`candidate` 行内容与时间戳一致；成交快照仍走默认路径（`NULL`）且 `actual_*` 保持 `NULL`；唯一货源只作数值估算，`cost` 门槛仍为 `unverified`（无 `pending` 门槛状态）。

### 10.4 未覆盖 / 续接

- 未做：货源匹配与排序、区间/多 variant 对照、权重版本化、S5 运行费与预算、实际利润核算、界面；**S4 阶段不得据此声明通过**。
- 镜像回归**不含**并行 A 的 `app/sources`、`tests/sources`、`tests/fixtures` 未提交写入，故 `143` 项为“S2+B 稳定集合”结果，不是 A+B 联合回归；联合验证待两批稳定后另行安排。
- 单活跃 recurring 行的 schema 约束意味着“多周期并存”不可达；若后续产品需要，需要迁移与设计变更（另立任务）。

### 10.5 返工修订（task-79fcc3d63d74cd9de76839410c67bcef revision 5，含勘误）

**勘误（首轮误判）**：§10.2/§10.4 曾称“同候选多周期 recurring 行不可表达、需要迁移”。**该判断错误**——活跃行唯一索引是 `(candidate_id, role, basis, variant)`，**包含 `role`**，因此 `other` 的 recurring 行与 `procurement` 的 recurring 行可以并存（`costs._spec` 允许 money+other+recurring）。混合周期场景**经现有成本 POST 路径即可构造**，无需迁移、无需新表。已用真实 API 端到端覆盖（见下），本节勘误**不修改** §1–§9 与冻结契约。

| 返工点 | 处理与实测 |
| --- | --- |
| 1. 默认路径 explanation/RUN_NOTE 兼容 | 恢复 `RUN_NOTE` 原文（“…摊销与季度/年度归一属 S4”）；explanation 回到旧实现条件（原额缺口行／非月度未归一行／周期不一致行），仅在 **net 已算**时把缺口行换成“仍为 S2 原额提示，与本次摊销结果分开”，删除自创的“原因见未知项”。新增**冻结 S2 实现对照**测试：测试内嵌原实现（含 `selected_supply_id`/`cost_source_note` 与修边界后的 gap/complete 规则），对 9 种库状态逐字段 `==`（含 `explanation`、`assumptions`、`unknown_components`），并断言“多出的键恰为 4 个 S4 新字段” |
| 2. 显式假设路径的说明精确化 | 分别标注：不可归（非月度且未归一）／缺 `monthly_orders`／缺 `amortize_orders`／真实 unknown（`unknown_components` 非空）；`complete` 时输出“已按假设摊销…”且**不再出现**“net 置空” |
| 3. 混合周期真实 API | 基线 `procurement recurring monthly 100` + 同供给 `other recurring quarterly 10000`（跨 role，活跃行并存）→ `normalize_periods=1&monthly_orders=4`：`R=3433`、`recurring_per_order=858`、`net=−708`、`complete=true`、`recurring_detail` 两行；归一关闭 → 不完整、月额 `null`、`gap=null`（混合周期）；把该行改为金额未知 → 不完整。同 role 第二条活跃行仍被唯一约束拒绝（保留该断言），并**同时断言跨 role 合法** |
| 4. 解析加固 | 三个参数改用 `getlist`：**重复（即使同值）→ `422 invalid_field`**；数字先 `lstrip('0')` 规范化并**先判长度（≤7 位）再 `int()`** → `'9'*5000` 返回 422（不再 500）、`'0'*5000+'20'` 合法解析为 20、`'0'*5000` → 422；core 继续拒 `bool`/`float`/字符串 |
| 5. 未知周期不再猜年额 | `annualized_minor` 未命中返回 `None`（`a` 判未知，`complete=false`/`net=null`）；“全部显式 0 ⇒ a=0”的兼容分支加“周期均在支持集合内”前提；单测覆盖 `weekly → None` |
| 6. GET 零写口径 | 四表（`gate_review`/`review_item`/`cost_item`/`candidate`）`SELECT *` 全量内容（含全部时间戳）前后一致；同一带参 GET 连跑两次响应完全一致 |

**返工实测（全部在 `tests/api/_tmp/s4_scenario_impl/rework_20261014_02/` 的隔离镜像内执行；`cwd=<run>/mirror`，`PYTHONDONTWRITEBYTECODE=1`）**

| 步骤 | 命令 | 真实退出码 / 结果 | 日志 |
| --- | --- | --- | --- |
| 目标文件 | `python -X utf8 tests\api\test_gates_scenario.py` | **exit=0**，`Ran 80 tests … OK`（57 既有 + 23 S4） | `gates_scenario.log`（首跑 `gates_scenario_rerun*.log` 亦保留） |
| 其他目标 | `test_feedback_draft` / `test_import_api` / `test_money` / `test_identity` / `test_migrations` | 8 / 27 / 7 / 7 / 4 项，**均 exit=0** | 同名 `.log` |
| 镜像全量 | `python -X utf8 -m unittest discover -s tests -t .` | **exit=0**，`Ran 147 tests … OK` | `discover.log` |
| 镜像内 E2E | `& .\instance\_e2e.ps1`（复制件，cwd=镜像） | `RESULT PASS` / `E2E_OK`，**exit=0**，`business_db_unchanged=True`；产物落在**镜像内** `…\mirror\tests\api\_tmp\s2_boundaries\e2e_20261014_220454_97e5cf1e\` | `e2e_mirror.log` |

**隔离与范围说明（如实）**：`rework_20261014_02/mirror/` 由稳定源复制而成（`app/` 排除 `sources`；`tests/` 排除 `_tmp`/`sources`/`fixtures`；`requirements.txt`；`instance/_e2e.ps1` 复制未改；`.venv` 为 Junction），`mirror_manifest.txt` 记录纳入/排除项与 9 个关键文件 live/mirror SHA256（全部 `same=True`），`steps.txt` 记录每步命令、cwd、真实 exit 与日志名。本轮执行后**工作区 `tests/api/_tmp` 目录数仍为 3152（未新增越界产物）**，`instance/app.db` SHA256 前后一致（`E073F828…4EB85`，wal/shm 均 MISSING），无残留 `python -m app` 进程。**首轮范围偏差保留并说明**：首轮 `01–07` 日志与 E2E 产物由实时文件直接跑出（E2E 产物落在工作区 `tests/api/_tmp/s2_boundaries`），未删除；自本轮起所有测试（含 E2E）只在镜像内运行，首轮绿日志不作为修后证据。

### 10.6 返工修订 2（task-79fcc3d63d74cd9de76839410c67bcef revision 8）

1. **explanation 按 `assumptions_given` 分流**（`app/core/scenario.py`）：`False`（默认路径）保持 S2 **逐字**——含“存在正额一次性/周期成本且未给分摊假设：net 置空，缺口单列”；`True` 时缺口行只写 `fixed_cost_gap_minor=… 分仍为 S2 原额/原周期提示`，随后**按实际行**列阻塞原因：`存在 recurring 行金额或周期未知（见 recurring_detail）：精确年化额 a 不可计算`／`缺 amortize_orders`／`缺 monthly_orders`，**仅当 `unknown_components` 非空**才追加“存在未知项（见 unknown_components）：net 置空”，`net` 已算时只输出“已按假设摊销…”。判定未知的依据是 **recurring 行自身**（`money_minor is None` 或 `period` 不在支持集合），因为 `unknown_components` 原逻辑只覆盖 procurement 三 basis 与 per_order。
2. **新增测试**（`tests/api/test_gates_scenario.py`）：`test_unknown_recurring_row_reason_is_reported_by_actual_rows`（`one_time=10000` + 经 POST 的 `other recurring quarterly` 金额 NULL + `normalize_periods=1&monthly_orders=4` → `gap=10000`、`net=null`、`complete=false`、`unknown_components==[]`、`recurring_detail` 含 `{"role":"other","period":"quarterly","money_minor":null}`，说明含“金额或周期未知／精确年化额 a 不可计算／缺 amortize_orders”，**不含**“未给分摊假设”“net 置空”；同 shape 默认路径仍逐字含 S2 原文）；`test_unknown_recurring_row_without_gap_still_reports_reason`（`one_time=0` → 无缺口行但**仍出现**该原因行）。
3. **证据文件（新 run 目录）**：`business_db_hash.txt`（工作区 `instance/app.db`/`-wal`/`-shm` 前后 SHA256：`E073F828…4EB85` / MISSING / MISSING，前后一致）、`tmp_dir_count.txt`（`tests/api/_tmp` 条目 **3153 → 3235**，并注明 +82 来自本次 1 次实时文件冒烟运行，镜像运行不落工作区）。
4. **实测（`rework3_20261014_03/mirror/` 内，cwd=镜像，逐条真实 exit 见 `steps.txt`）**：`gates_scenario` **Ran 82 … OK exit=0**（57 既有 + 25 S4）、`feedback_draft` 8／`import_api` 27／`core_money` 7／`core_identity` 7／`storage_migrations` 4 均 **exit=0**、`discover` **Ran 149 … OK exit=0**、镜像内 E2E **`RESULT PASS`/`E2E_OK` exit=0**（产物在镜像内 `…\mirror\tests\api\_tmp\s2_boundaries\e2e_20261014_230955_589392fd\`）；`mirror_manifest.txt` 9 个关键文件 live/mirror SHA256 全部 `same=True`（本轮 `scenario.py F36F2844019C8DEB…`、`routes.py F3EF63D4F1A72200…`、`test_gates_scenario.py C09200EA9737C8D3…`；上一轮为 `CB76B02BFBBA4FAC…` 等，已在上一轮清单中留档）。旧 `01–07` 与 `rework_20261014_02` 全部保留。
