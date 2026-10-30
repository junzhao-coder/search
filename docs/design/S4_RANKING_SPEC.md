# S4-B3 机会排序设计（设计稿：未实现、未联网、未接入）

> 状态：**设计稿 / 未实现**。本文不新增表/列/迁移/端点/CLI/定时器/依赖，不改 `app/**`、`tests/**`、契约、台账与业务库；不改门槛、匹配（S4-B1）、情景（S4-B2）与状态派生语义。**排序是只读的展示次序**：不写库、不产生证据、不改变金额。
> 边界声明：**不宣称 S4 完成、不宣称排序可用**；权重为**启发式 `rank-v1`**，不声称由经营数据训练（PLAN §8 S4-B3）。真实渠道未接通（PRODUCT D07）。
> **本版为修订 v2**：按独立评审 [S4_RANKING_REVIEW.md](../validation/S4_RANKING_REVIEW.md)（196 行，结论「需修订」，8 项阻断）的 F-01…F-18 与 M-01…M-10 逐条修订；F→修改位置见 §11，修订史见 §12。评审行号对应 v1（152 行），本文行号以本文件为准。
> 依据（只读已阅）：[S4_MATCHING_SPEC.md](<S4_MATCHING_SPEC.md>) v2（149 行）· `app/core/matching.py`（258 行，只读；用途恒 `hint_only`、非排除项 `needs_review`）· [S4_SCENARIO_SPEC.md](<S4_SCENARIO_SPEC.md>) · `app/core/scenario.py`（`:194–201` `complete` 还需 `assumptions_known`；`:257–281` 返回键）· `app/core/state.py`（`effective_gate_status:158–178`、`current_gate_supply:123–132`、`recompute:181–210`、`_supply_invalid/SUPPLY_TTL_DAYS:12/45–56`）· `app/core/candidates.py`（override 枚举 `:10`）· `app/core/reviews.py`（`_degrade_reason:66–93`）· `app/storage/migrations/0001_init.sql`（`demand_signal.observed_at NOT NULL :81`、`demand_signal` 版本 `:87–89`、`cost_item` `:164–172`、`supply_offer` `:142–149`、`review_item.blocking :229`）· [CONTRACT.md](<CONTRACT.md>) §0.4/§3.3/§5.5 · `DEVELOPMENT_PLAN.md:123` §8 S4-B3 · `PRODUCT.md` D04/D08/D09/D07。
> 技能：本会话**未暴露 `skill` 工具**，如实标注未加载；无新依赖、无费用。

## 1. 目标与不做什么

- **目标**：对"已可测试（`testable`）"与"待核验"候选给出**确定性、可解释、可复算**的展示次序，服务"每日一次、最多 5 条重点机会"（D09）与"人工预算内先看什么"（PLAN §8 S4-B3）。
- **不做**：不自动核验、不改门槛/状态/金额、不写库、不生成证据、不用模型/互动量/热度、不把未知当 0、不把排序分当收益或概率、不新增接口/表/列、不做发现型检索。

## 2. 排序输入与数据来源（现有可判定性）

| 输入 | 现有来源（只读） | 可判定性 |
| --- | --- | --- |
| 候选状态/派生 | `state.recompute(conn, cid)` → `(status, reason)`；`status ∈ {testable, pending, stale, archived, explore}` | **可判定** |
| 四门槛有效状态 | `state.effective_gate_status` ∈ {`unverified`,`verified`,`failed`,`expired`} | **可判定** |
| 当前有效 G2 货源 | `state.current_gate_supply`（最新 `seq` 货源 + 有效状态） | **可判定** |
| 情景完整性与净值 | `scenario`：`complete`、`net_per_order_minor`、`contribution_per_order_minor`、`unknown_components` | **可判定**（`net` 非 None 当且仅当 `complete=True`） |
| **排序调用情景的参数口径** | 由调用方传入 `scenario_params={variant, amortize_orders, monthly_orders}`，写入输出；缺省 `{variant:'base', amortize_orders:null, monthly_orders:null}`（**不带摊销/月销假设**） | **可判定**（口径固定，见 §4.1） |
| 观察时间新鲜度 | `demand_signal` **头版本行**（`superseded_by IS NULL` 中 `version_no DESC, observed_at DESC, id ASC` 取 1；`observed_at` 为 `NOT NULL` 且导入时经 ISO-8601 校验） | **可判定**（见 §4.4 取行规则） |
| 匹配结论 | `matching.match_supplies` 的 `items[].level/dims/gaps/is_selected_by_g2`、`gaps`、`current_g2_supply_id` | **可判定**（用途恒 `hint_only`；非排除项恒 `needs_review` 且恒含 `dims_text_only`） |
| 供应稳定性 | 有效 G2 verified + G2 货源 `status ∈ {candidate, verified}`（**`stale`/`invalid` 不计**）+ 三许可均 `yes` + `last_checked_at` 未超 30 天 | **部分可判定**（无历史稳定性序列） |
| 交付/售后负担 | 唯一代理：`cost_item` 当前 G2 的 `manual_labor`（见 §4.4 取行）；无结构化交付/售后字段 | **缺口**（不虚构） |
| 阻塞复核 | `review_item` `blocking=1 AND status='open'`（含 `recompute` 的 blocking 判定） | **可判定** |
| 人工预算 | 调用方参数 `budget_minutes`（默认 30） | **外部参数**（不改变排序，见 §9） |
| 时间基准 | 调用方参数 `as_of`（ISO-8601 带时区；入口默认 `now_utc()` 注入） | **外部参数**（写入输出，保证确定性） |

## 3. 分池（严格优先级，命中即止；只影响展示位置，不写库）

按下列顺序判定，**每个候选恰落一池**，无循环、无重叠：

| 序 | 池 | 判定条件（命中即止） |
| --- | --- | --- |
| 1 | **排除** | `manual_override ∈ {archived, explore}`（`candidates.py:10`；explore 不进推荐、archived 不参与）→ 计数单列，不进 `items` |
| 2 | **需处理（blocked）** | `recompute().status == 'stale'`（**全部 stale 来源**：任一门槛 `failed`/`expired`、阻塞复核、G4 版本不一致、手工写入 failed/expired 门槛行等，`state.py:193–197`）→ **置顶**，`reasons` 直接引用 `recompute` 的 `reason`（如 `stale:demand`），`next_action`="先处理该门槛/复核后重排" |
| 3 | **推荐** | `status == 'testable'`（四门槛 verified 且无 blocking，`state.py:198–199`） |
| 4 | **观察** | `status == 'pending'` 且 `demand_signal` 行数 ≥ 1 且 匹配存在可用货源（`items` 中至少一个 `level != 'excluded'`）且 匹配 `gaps` **不含** `license_unknown`/`format_unknown` |
| 5 | **探索** | `status == 'pending'` 且 `demand_signal` 行数 ≥ 1 且（**无可用货源**，或 `gaps` 含 `license_unknown`/`format_unknown`）→ 弱证据高潜力单列（D04） |
| 6 | **数据不足** | `demand_signal` 行数为 **0**（无可解释需求行）或状态不在上述枚举 → 计数单列，不参与排序 |

> 观察/探索的互斥由"探索条件"的**可判定缺口集合** `{license_unknown, format_unknown}` + "无可用货源"给出；`dims_text_only`/`scope_text_only` 恒真，**不作为**探索判据（避免把全部 pending 推入探索池）。R-04/R-05 与之对齐。

## 4. 分层权重与并列规则（版本 `rank-v1`，启发式、确定性）

**先分层（`pool_order` + `tier`），层内按整数分 `score`，同分按并列键。** 相同输入 + 相同 `as_of` + 相同 `scenario_params` 必须得到相同顺序。

### 4.1 情景口径（F-01/M-01）

- 排序**固定**以 §2 的 `scenario_params` 调用情景；缺省为 `{variant:'base', amortize_orders:null, monthly_orders:null}`（即**不带摊销/月销假设**）。
- `complete=True` 需同时满足：成本集完整 **且** `assumptions_known`（`scenario.py:194–201`：一次性成本 >0 须 `amortize_orders`；周期成本 >0 须 `monthly_orders`）。G3 verified 只要求成本集完整 ⇒ **有正一次性/周期成本的 testable 候选在缺省参数下 `complete=false`**。
- 因此 **T2 可达、且 T1 可能为空**（全库候选都需假设时）——如实展示，不凑数、不推定。
- 调用方若传入 `amortize_orders`/`monthly_orders`，须**写入输出** `inputs_used.scenario_params`，使排序可复算（同参数同结果）。

### 4.2 分层（`tier`，第一排序键，不跨层比较）

| pool_order | pool | tier | 条件 |
| --- | --- | --- | --- |
| 0 | blocked | `B` | `recompute` 判为 `stale`（不计算 score，`score=null`） |
| 1 | recommended | `T1` | `testable` 且 `complete=True`（`net` 已知） |
| 2 | recommended | `T2` | `testable` 且 `complete=False`（缺假设/未知项；`net=None`） |
| 3 | observing | `T3` | 观察池 |
| 4 | exploring | `T4` | 探索池 |

> `rank` 在 `items` 中按 `(pool_order, tier 内次序)` **全局连续编号**（blocked 从 1 起，其后 T1…T4 依次接续）；`omitted` 只记录推荐池超出 `limit` 的项及其**全局 rank 值**。

### 4.3 层内加权分（整数；**分域 0–100，非百分比**）

| 计分项 | 取值 | 依据 |
| --- | --- | --- |
| 基础分 | T1=**39** / T2=**29** / T3=15 / T4=5 | 层级差异（blocked 无 score） |
| `complete`（`net` 已知） | +15 | `scenario.py:200–201` |
| `net > 0` | +10（`=0` 不加、`<0` 仅标注负利润） | 同上 |
| 四门槛 verified 数 | +5 × n（n≤4，最大 20） | `effective_gate_status` |
| 观察时间新鲜（相对 `as_of`） | ≤7 天 +8；≤30 天 +4；更旧 +0 | §4.4 取行 |
| 供应稳定 | +6 | §2 口径（与 `effective_gate_status` 同源） |
| 人工分钟 | ≤30 分钟 +2；>30 分钟 +1；未知 +0 | §4.4 取行 |
| **实质匹配缺口** | −2（仅当 `gaps` 含 `license_unknown`/`format_unknown`/`no_cost_binding_to_g2`/`g4_baseline_undefined` **且** 不含仅恒真项） | `dims_text_only`/`scope_text_only` **不计**（恒真、无区分度） |

**最大分 = 39+15+10+20+8+6+2 = 100**；出现 −2 时为 98（v1 误写"满分 100"而实际 101，已按 F-07 修正权重使自洽）。T2 理论最大 = 29+0+0+20+8+6+2 = 65（无 `complete`/正 net 加分）。分数仅用于同层次序，**不得**当收益/概率/证据。

### 4.4 取行规则（F-05/F-13，必须写死）

- **观察时间**：`demand_signal` 头版本行——`WHERE candidate_id=? AND superseded_by IS NULL ORDER BY version_no DESC, observed_at DESC, id ASC LIMIT 1`；若无 `superseded_by IS NULL` 的行（历史异常），退化为 `ORDER BY version_no DESC, id ASC LIMIT 1`；`observed_at` 为 `NOT NULL` 且导入时经 ISO-8601 校验（`importer._check_at`），**正常数据不会为空**；仅在人工直改等防御性情形缺失时，该候选按"无观察时间"处理（新鲜 +0、并列键末位），**不伪造时间**。
- **人工分钟**：`SELECT SUM(minutes) FROM cost_item WHERE candidate_id=? AND role='manual_labor' AND basis='per_order' AND variant='base' AND is_active=1 AND minutes IS NOT NULL`（与情景 `base`/当前口径一致）；无行或全 NULL ⇒ **未知**（+0、并列末位），**不当 0**。
- **新鲜度**：`age = max(0, as_of − observed_at)`；≤7 天/≤30 天分桶。**同 `as_of` 同数据必得同分**。

### 4.5 并列与稳定次序（唯一全序）

同分依次比较：1) `net_per_order_minor` 降序（`None` 恒在已知之后，不参与数值比较）；2) `observed_at` 降序（缺失最后）；3) verified 数降序；4) 人工分钟升序（未知最后）；5) `candidate_id` 升序（唯一终键）。

## 5. 排除 / 降级口径（禁止把未知当 0）

- **未知 ≠ 0**：`net` 未知（`complete=false`）只落 T2，不参与正负比较、不填 0。
- **负利润**：`net<0` 仍展示并标"负利润"，不加正分。
- **非 `testable`**：不进推荐池（D08）；`pending` 只进观察/探索池，**不得**显示为已验证机会。
- **匹配 `excluded` 货源**：不删除候选；**有效 G2 货源失效**时 `recompute` 判 `stale` → 落 blocked 池（既有 blocking 复核 `supply_invalid` 会使其 stale，`supplies.py:117–119`）。
- **H1 提示**（名称相似/供应商自称可转售）：只作提示，不加分、不改分数与核验。
- **数据不足**：`demand_signal` 行数 0 → 计数单列，不进任何排序池。

## 6. 可解释输出结构（只读、不落库）

纯函数（实现批提供，本设计**不实现**）：
`rank_candidates(conn, *, as_of, limit=5, budget_minutes=30, scenario_params=None, rank_version="rank-v1") -> dict`

```
{"rank_version":"rank-v1","as_of":"2026-10-20T00:00:00Z",
 "scenario_params":{"variant":"base","amortize_orders":null,"monthly_orders":null},
 "budget_minutes":30,"budget_note":"预算只作展示提示，不改变排序与条数（与 PLAN §8 偏差待裁定）",
 "pool_order":["blocked","T1","T2","T3","T4"],
 "pools":{"excluded":n,"blocked":n,"recommended":n,"observing":n,"exploring":n,"insufficient":n},
 "daily_limit":5,
 "items":[{"rank":1,"candidate_id":"c_…","pool":"blocked","tier":"B","score":null,
           "reasons":["stale:supply_distribution"],"gaps":[],
           "next_action":"先处理失效货源/复核后重排","inputs_used":{...}},
          {"rank":2,"candidate_id":"c_…","pool":"recommended","tier":"T1","score":100,
           "reasons":["四门槛均 verified","net=190 分/单（complete）","观察时间 3 天内（as_of 基准）","有效 G2 货源稳定","人工 10 分钟"],
           "gaps":[],"next_action":"补样本抽检说明后可试单","inputs_used":{...}}],
 "omitted":[{"rank":8,"candidate_id":"c_…","reason":"超出每日 5 条上限"}]}
```

- `items` 含**全部** blocked/T1/T2/T3/T4 项（全局 `rank` 连续）；`excluded`/`insufficient` 只计数不进 `items`。
- 每项必须能回答"为何此位（`reasons`）/缺什么（`gaps`）/下一步（`next_action`）"；**不含**成功率/收益率预测字段。
- **不写库**、不新增表/列/端点；读时零副作用。

## 7. 与四项门槛、匹配（S4-B1）、情景（S4-B2）的边界

| 组件 | 排序如何使用 | 排序不得如何 |
| --- | --- | --- |
| 四门槛/状态 | 只读 `recompute`/`effective_gate_status` 分池与计分 | 不改状态、不触发核验、不写 `gate_review` |
| 匹配 | 读 `level/dims/gaps/current_g2_supply_id` 判断可用货源与实质缺口 | 不改匹配、不把 `needs_review` 当适配通过、不以名称相似加分 |
| 情景 | 按 §4.1 固定参数读 `complete/net` | 不改金额、不重算、不把未知 net 当 0、不把情景可算当门槛通过 |
| 复核 | 读 blocking open 与 `recompute` 的 stale 归因 | 不创建/关闭复核 |

## 8. 每日一次、最多 5 条口径（PRODUCT D09）

1. **每日一次**：由 S5 流水线触发（本设计不含定时器）。
2. **最多 5 条**：`limit=5` 只作用于**推荐池**（T1→T2 次序）；超出者入 `omitted` 并标全局 `rank`。
3. **不足不凑数**：推荐池不足 5 条按实展示，不用 blocked/观察/探索池补位（后者在 `items` 中单列展示，但不计入"每日 5 条重点机会"）。
4. **完整池可查看**：`pools` 计数 + `items` 全覆盖 + `omitted` 可查（D09）。
5. **失效提醒**：blocked 池置顶并给 `next_action`，与 S5 提醒结合。

## 9. `budget_minutes` 的定位（F-09）

`budget_minutes` **不改变排序、不改变条数**（与 PLAN §8 "在人工 30–60 分钟预算内排序"存在表述偏差，已列 §10 待裁定 ②）；当前仅用于输出 `budget_note` 展示提示。若后续要求按预算截断展示，须先修订本节与"每日 5 条"口径。

## 10. 离线验收矩阵（设计；可构造/可核，本批未执行）

> 说明：构造步骤使用现有导入/门槛/成本 API 与测试夹具；"SQL 夹具"仅用于置时间（如 `last_checked_at`）。所有 case 固定 `as_of` 以保证确定性。

| # | case | 构造 | 期望 |
| --- | --- | --- | --- |
| R-01 | T1 满分路径 | 导入正例 → 逐项 `POST /cost-items` 同值并带 `assumption_note`（取代活跃行）→ `verify_all_gates` → 传 `amortize_orders` 使 `complete=True` | `pool=recommended/tier=T1`、`rank=2`（blocked 空时 rank=1）、`score` 按 §4.3 复算（示例 100：39+15+10+20+8+6+2） |
| R-02a | 同分同桶并列 | 两候选同门槛、同 net、同 7 天内新鲜度、同人工分钟 | 仅 `candidate_id` 终键决定次序；交换构造顺序结果不变 |
| R-02b | 同分后人工分钟键 | 同分、人工分钟 10 vs 40 | 10 分钟者在前（+2 vs +1，若分数因此不同则按分数；构造为同分时验证并列键） |
| R-03 | T2 可达（缺假设） | `testable` + 正一次性成本（如 `one_time=10000`）+ **不传** `amortize_orders` | `complete=false`、`net=None` → `tier=T2`（不显示 0）；再传 `amortize_orders=20` → 变 T1（对照） |
| R-04 | 观察池 | `pending` + 有需求信号 + 货源三许可 `yes`（无 `license_unknown`/`format_unknown`） | 落 T3 观察池，不进推荐、不称已验证 |
| R-05 | 探索池与 −2 区分度 | `pending` + 货源 `commercial_allowed='unknown'`（G2 未核验） | 落 T4 探索池；`gaps` 含 `license_unknown`，score 触发 −2；**对照**：同形但许可 `yes` 的 pending 候选落 T3 且无 −2（证明 `dims_text_only` 不参与扣分） |
| R-06 | blocked 池（失效/异常） | testable 后 `PATCH /supplies/{id}` 置 `invalid`（既有 blocking `supply_invalid` 复核） | `recompute=stale` → blocked 池、`rank=1`、`reasons` 含 `stale:*`、`next_action` 非空；其余池次序不受影响 |
| R-07 | 旧数据 | 导入 `observed_at` 31 天前（相对固定 `as_of`） | 新鲜 +0；同层项中排在更新者之后 |
| R-08 | 负利润 | 高成本/低售价造 `net<0`（complete 且已知） | T1 展示并标负利润；不加正分；不隐藏 |
| R-09 | 超 5 条截断 | 6 个推荐候选（T1/T2 混合） | 前 5 入 `items`；第 6 入 `omitted` 且 `rank` 为真实全局名次；不删数据 |
| R-10 | 不足 5 条 | 仅 2 个推荐候选 | 只展示 2 条重点机会；不补位 |
| R-11 | override 排除 | `manual_override='explore'`/`'archived'`（需 `override_reason`） | 不进 `items`，只在 `pools.excluded` 计数 |
| R-12 | 确定性 + 零写入 | 固定 `as_of`/`scenario_params` 连调两次 | 结果逐字段相同；**全部业务表**全行快照（含时间戳）前后一致 |
| R-13 | 分数不得冒充证据 | 任一 case | 输出无成功率/收益率字段；`rank_version` 固定；`score` 不复用为门槛依据 |
| R-14 | **（实现批后验）** 权重版本化 | 修改权重表为 `rank-v2` | 需改代码/测试，属实现批；本设计只要求输出携带 `rank_version` 且同版本内数值不可变 |
| R-15 | stale 全来源覆盖 | 手工写入 G1 `status='failed'` 门槛行（无 blocking 复核） | 仍落 **blocked** 池（不落观察/探索、不落数据不足），`reasons` 引用 `recompute` 的 `stale:demand` |
| R-16 | 数据不足 | 只建候选行、无 `demand_signal`（或仅成本/货源） | 落 `insufficient` 计数，不进 `items`；不写"无需求"结论 |

## 11. F→修改位置映射表（本轮修订）

| 编号 | 问题（评审） | 修改位置 | 修订要点（前 → 后） |
| --- | --- | --- | --- |
| F-01 | T1/T2 与情景参数未定义；R-03 矛盾 | §2 输入行、§4.1、§4.2、R-03 | 定义排序调用情景的固定参数（缺省无摊销/月销假设，可被调用方覆盖并写入输出）；**T1=testable+complete**、**T2=testable+complete=false**；R-03 改"缺假设"构造 |
| F-02 | R-05 在推荐池 −2 不可能 | R-05、§4.3 | `license_unknown` 属观察/探索池；−2 改为仅在实质 gaps 且用于观察/探索池；R-05 改对照实验 |
| F-03 | 观察/探索条件成环 | §3 表、§4.2 | 探索条件改为**可判定缺口集** `{license_unknown, format_unknown}` 或"无可用货源"；观察=其余 pending；互斥完备 |
| F-04 | `stale` 无池 | §3 第 2 行、§4.2、R-15 | 新增 **blocked** 池覆盖 `recompute` 全部 stale 来源，带 `next_action` |
| F-05 | `observed_at` 取行未定义 | §4.4、§2 | 写死"头版本行"取行规则并写入 `inputs_used`；无 head 行退化规则 |
| F-06 | 新鲜度依赖 now | §2、§4.4、R-12 | 引入调用方 `as_of` 并写入输出；`age=max(0, as_of−observed_at)`；固定 `as_of` 下确定 |
| F-07 | "满分 100"算术错 | §4.3 | 权重改为 T1=39/T2=29 ⇒ 最大 **100**；注明分域非百分比、含 −2 为 98 |
| F-08 | blocked/观察/探索无 tier、全局 rank 未定 | §4.2、§6、§8 | 定义 `pool_order`、`tier=B/T1…T4`、全局连续 `rank`、`items` 范围与 `omitted` 关系 |
| F-09 | `budget_minutes` 与 PLAN 偏差 | §9、§10 待裁定② | 明确"不改变排序/条数，仅 `budget_note`"，偏差列为待裁定 |
| F-10 | R-01 构造缺步骤 | R-01 | 写全"逐项成本+assumption_note+绑定+核验+传假设"步骤与分数复算 |
| F-11 | R-02 不能验并列 | R-02a/R-02b | 拆"同分同桶"与"人工分钟并列键"两个 case |
| F-12 | 数据不足判据未定义 | §3 第 6 行、R-16 | 判据改为 `demand_signal` 行数 = 0；不再混用 `no_supply_rows` |
| F-13 | 人工分钟未取行 | §4.4 | 写死 `manual_labor/per_order/base/active` 合计规则 |
| F-14 | 供应稳定未说明 stale | §2、§4.3 | 明确与 `effective_gate_status` 同源、`stale`/`invalid` 不计 |
| F-15 | −2 无区分度 | §4.3 | 仅实质 gaps 生效，排除 `dims_text_only`/`scope_text_only`；R-05 对照验证 |
| F-16 | R-14 属实现批 | R-14 | 标注"实现批后验" |
| F-17 | "无效 observed_at 作缺失"表述不符 | §2、§4.4 | 改为"`NOT NULL`+导入校验，仅防御性缺失；缺失按无时间处理不伪造" |
| F-18 | R-12 快照范围 | R-12 | 扩为**全部业务表**全行快照 |

## 12. 修订史

- v1（revision 2）：初版（输入、分池、`rank-v1` 层/分/并列、边界、每日 5 条、R-01…R-14、未执行清单）。
- v2（本版，task-85f69a5a4912a1ba30bb05a2df40fad1）：按 `S4_RANKING_REVIEW.md`（F-01…F-18/M-01…M-10）修订：新增情景参数口径与 T2 可达路径、blocked 池与 stale 全覆盖、观察/探索无环判据、`observed_at`/`manual_minutes` 取行规则、`as_of` 确定性、分域修正为 100、−2 区分度修复、blocked/池位次与全局 rank、数据不足判据、R 矩阵重写（R-02 拆分、R-03/R-05 重定、R-14 标实现批、R-12 全表快照、新增 R-15/R-16）、新增 §11 映射表与 §12 修订史。

## 13. 未执行 / 未覆盖 / 待裁定

- **未执行**：本任务为设计稿，§10 全部未运行；`rank_candidates` 未实现、未接入流水线/界面。
- **未覆盖**：S5 每日流水线与提醒、界面呈现、受控词表、结构化交付/售后风险字段、货源稳定性历史序列、真实运行证据。
- **待裁定**：① 权重数值与项（`rank-v1` 启发式，需确认）；② `budget_minutes` 与 PLAN §8 的偏差（§9，当前不参与排序/条数）；③ 每日上限 5 条与 `budget_minutes` 默认值是否按 PRODUCT D09/PLAN 固定；④ 排序结果是否需要进入既有读接口（涉公共接口扩展，须另行授权）；⑤ 观察/探索/blocked 池的界面呈现（单列/折叠/置顶样式）。
- **声明**：全文设计稿、未实现、未联网；不新增网络权限/依赖/表/列/端点/CLI/定时器；不改门槛/匹配/情景语义；**不宣称 S4 完成或排序可用**。
