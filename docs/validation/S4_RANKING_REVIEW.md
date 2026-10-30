# S4-B3 机会排序设计 · 独立评审（非作者评审）

> 评审对象：[docs/design/S4_RANKING_SPEC.md](<../design/S4_RANKING_SPEC.md>)（152 行，sha256 `5d5db568050098a040d26515fdf92935970d7972bf2298bf85e4243d6259604e`）
> 评审者：独立执行者 A（作者为原 B），任务 `task-e2177a8926c47647072e7f41d768d077`；评审时点 2026-10-20 13:47 +08:00。
> 性质：**纯只读评审**。未修改被评审文件与任何源码/测试/契约/台账；**未联网、未启动应用、未运行测试**；只读复算 §0.2 哈希。
> 技能：本会话函数清单中**没有 `skill` 工具**，如实标注未加载。
> 结论：**需修订**（不建议直接进入排序实现批）。阻断项：T2 与 R-03 矛盾、R-05 与分池矛盾、R-04 与观察/探索边界矛盾、`stale` 无归属池、并列键 `observed_at` 取行未定义、新鲜度依赖 now 破坏确定性、"满分 100"算术错误、blocked 池无 tier/全局位次（F-01…F-08）。

## 0. 方法与输入

### 0.1 方法

逐行读 152 行设计稿 → 核对 §2 输入字段与 `state/scenario/matching/candidates` 实际返回 → 推演 §3 分池与 `recompute` 语义 → 逐项复算 §4 计分与并列 → 逐条推演 §9 R-01…R-14 的构造与期望 → 越界检查。静态阅读，不把推演写成实测。

### 0.2 只读复算哈希（评审时点 live）

| 文件 | sha256 | 行数 |
| --- | --- | --- |
| `docs/design/S4_RANKING_SPEC.md` | `5d5db568…9604e` | 152 |
| `app/core/state.py` | `4cecfa5c…01dad` | 210 |
| `app/core/scenario.py` | `f36f2844…93ad` | 281 |
| `app/core/matching.py` | `5cd186c8…dcade` | 258 |
| `app/core/candidates.py` | `475b8fb2…f0e` | 30 |
| `app/core/reviews.py` | `1efba11a…03da` | 128 |
| `app/storage/migrations/0001_init.sql` | `9b049373…62bb` | 294 |
| `docs/design/S4_MATCHING_SPEC.md` | `27e90bd5…f372df` | 149 |
| `docs/design/S4_SCENARIO_SPEC.md` | `e8fe6936…f75c` | 231 |
| `DEVELOPMENT_PLAN.md` | `0a50d317…63c6` | 253 |
| `PRODUCT.md` | `1639891d…2083a2` | 107 |
| `docs/design/CONTRACT.md` | `826c24cc…b4f9` | 812 |

## 1. §2 排序输入逐项核对

| 输入（稿 L15–L26） | 核对结果 | 依据 |
| --- | --- | --- |
| 候选状态/池：`state.recompute`/`effective_gate_status` | **真**（`recompute` 返回 `(status, reason)`；四态 `unverified/verified/failed/expired`） | `state.py:181-210`、`:158-178`；schema `:205` |
| 四门槛有效状态 | **真** | `state.py:158-178`；`GATES` `:9` |
| 当前有效 G2 所选货源 | **真**（`current_gate_supply` = 最新 `seq` 行货源 + 有效状态） | `state.py:123-132`、`:31-35` |
| 情景完整性/净值：`complete`/`net_per_order_minor`/`contribution_per_order_minor`/`unknown_components` | **真**；`net` 仅在 `complete` 为真时非 None | `scenario.py:257-281`、`:194-201` |
| 观察时间 `demand_signal.observed_at` | **字段存在**（`NOT NULL`）；但"无效值只作缺失"与 schema/导入校验不符（见 F-17），且**未规定多条需求信号取哪一行**（见过 F-05） | schema `:81`；`importer.py` 的 `_check_at` 校验 |
| 匹配输出 `level/dims/gaps/is_selected_by_g2/current_g2_supply_id` | **真**（用途恒 `hint_only`；非失效项恒 `needs_review` 且恒带 `dims_text_only`） | `matching.py:145-146`、`:193-194` |
| 供应稳定性：`supply_offer.status`/`last_checked_at`/三许可/`format_version`；有效 G2 状态 | **真**（字段齐全） | schema `:142-149`；`state.py:45-56,164-166` |
| 交付/售后负担：唯一代理 `cost_item` 的 `manual_labor.minutes` | **真**（无结构化交付/售后字段，诚实标缺口） | schema `:169`；`matching.py` 无该字段 |
| 阻塞复核：`review_item` `blocking=1 AND status='open'` | **真** | schema `:229`；`state._blocking_reviews` `:59-70` |
| 人工预算 `budget_minutes` | **真**（外部参数，非库内字段；与 PLAN §8 的用法有偏差，见 F-09） | 稿 L26/L151；`DEVELOPMENT_PLAN.md:123` |

**小结**：§2 无虚构字段/错名；问题在"观察时间取行未定义"与"无效值表述"两处精度。

## 2. §3 分池与 `recompute` 语义核对

| 分池（稿 L30–L37） | 核对结果 | 依据 |
| --- | --- | --- |
| 排除：`manual_override ∈ {archived, explore}` | **真**（枚举 `none/explore/archived`；override 即改状态） | `candidates.py:10`；schema `:53`；`state.apply_status` |
| 失效提示：blocking open 复核 或 有效 G2 货源 invalid/TTL | **部分真**：与 `recompute` 的 `stale` 有交集但不覆盖——`stale` 还可能由 G1 `failed`、G4 版本不一致、手工写入 `status='failed'/'expired'` 的门槛行（不建复核）导致，这些候选**无池可归**（F-04） | `state.py:193-197`；`gates.record_gate` `:311-326`（非 verified 不做准入、不建复核） |
| 推荐池：`status='testable'` | **真**（testable = 四门槛 verified 且无 blocking） | `state.py:198-199` |
| 观察池：`pending` 且有需求信号、不具备探索条件 | **歧义**：由于 matching 对所有非失效货源恒 `needs_review` 且恒含 `dims_text_only`，"pending+有货源"按探索池行文字会命中探索池；"探索条件"未给可判定定义，与观察池条件循环引用（F-03） | `matching.py:145-146,193-194`；稿 L35-L36 |
| 探索池：`pending` 或弱证据：匹配 `needs_review` 且存在 `gaps`；或只有自由文本/名称线索 | **歧义**：条件过宽（几乎覆盖全部 pending+有货源）且"或弱证据"无判定口径 | 同上 |
| 不排序：无需求信号（`no_supply_rows` 且无 demand）等无法解释情形 | **混淆**：`no_supply_rows` 是匹配的"无货源"缺口，不涉及"需求信号"；"有需求信号"如何判定未定义（F-12） | 稿 L37；`matching.py:229-232` |
| "分池只用既有读时派生，与 `recompute` 口径一致" | **部分真**：推荐/观察/排除与 recompute 一致；"失效提示"未以 `status` 为准，`stale` 覆盖面大于判据（F-04） | `state.py:181-210` |

## 3. T1/T2/T3/T4 自洽性（含"是否可能为空集"）

- **T1（推荐池 + complete + net 已知，稿 L49）**：`net` 非 None **当且仅当** `complete=True`（`scenario.py:200-201`），故两个条件中 `net 已知` 已蕴含 `complete`；二者不是冲突而是**重复**（轻微冗余）。
- **T1 与 cost 门槛不矛盾，但可能为空集**：G3 verified 只要求"当前有效成本集完整"（`gates._check_cost` `:190-217`；`state.base_unknown_components`），**不要求**摊销/月销量假设；而 `complete` 还要求 `assumptions_known`：一次性成本 >0 时须 `amortize_orders`、周期成本 >0 时须 `monthly_orders`（`scenario.py:194-200`）。默认参数下，凡有正一次性/周期成本的 testable 候选都会 `complete=false` → 落 T2；**若全库如此，T1 可为空**。设计**未规定排序以什么参数调用情景**（默认？调用方传假设？）→ T1/T2 边界不可判定（F-01）。
- **T2（推荐池 + net 未知，L50）可达路径只有"缺假设"**：缺成本角色会先使 G3 不成立 → 候选 `pending`（非 testable），不会进推荐池。因此 R-03 用"成本缺角色（complete=false）"构造 T2 **与该定义矛盾**（F-01/F-11）。
- **T3（观察池，L51）**：受 F-03 边界影响，可能被探索池抢走。
- **T4（探索池，L52）**：条件过宽（见 §2）。
- **跨层比较**：tier 为第一排序键、不跨层比较 ✓ 与"未知金额不被分数挤掉证据充分"意图一致（正面）。

## 4. §4 计分与并列核对（逐项复算）

| 计分项（稿 L56–L69） | 可否由现有字段确定性复算 | 说明 |
| --- | --- | --- |
| 基础分 T1=40/T2=30/T3=15/T4=5 | **是** | 依赖分池（受 §2/F-04 影响） |
| `net` 已知 +15 | **是** | `complete=True` 且 `net` 非 None（与 T1 条件重复） |
| `net` 为正 +10 | **是**（`net>0`；0 不加、负只标注） | `scenario.py:201` |
| 四门槛 verified 数 +5×n | **是**（`effective_gate_status` 计数） | `state.py:158-178`；但 T1/T2 恒为 4，仅 T3/T4 有区分度 |
| 观察时间新鲜 ±8/+4/0 | **可算但不确定**：依赖"取哪条 demand_signal.observed_at"（F-05）与当前时钟 now（F-06：跨 7/30 天边界会改变分数/次序，违反"相同输入相同顺序"） | `demand_signal.observed_at` `:81` |
| 供应稳定 +6 | **可算**（有效 G2 verified + G2 货源 status∈{candidate,verified} + 三许可 yes + TTL 内） | `state.py:123-132,158-178`；schema `:142-149` |
| 人工时间已知 +2/+1/0 | **可算，但未指定行**：`cost_item` 可有多行 manual_labor（不同 basis/variant），须明确 `role='manual_labor' AND basis='per_order' AND variant='base' AND is_active=1`（与情景同口径） | schema `:164-172`；`scenario.py:123-127` |
| 匹配缺口 −2 | **可算但无区分度**：T1/T2 候选的 `dims_text_only` 恒真、`license_unknown` 在 testable 候选不可能出现（G2 需三许可 yes）→ −2 对推荐池恒为常量（F-15） | `matching.py:145-146,164-171` |

**"满分 100"错误（F-07）**：最大组合 = 40+15+10+20+8+6+2 = **101**（再减 −2 则为 99），分值域不是 0–100 百分比；稿 L56 的标尺需删改。

**并列链（稿 L71–L78）**：
1. `net` 降序（None 最后）✓ 可在 T1 内区分；T2 内全为 None（等于不做区分）。
2. 观察时间降序（缺失最后）——**取行未定义**（F-05）。
3. 四门槛 verified 数降序 ✓。
4. 人工分钟升序（未知最后）——**行选择未定义**（F-13）。
5. `candidate_id` 升序 ✓ 唯一终键，保证全序。
- 结论：链**结构唯一**（终键保证确定性），但第 2/4 项依赖未定义行选择；且第 1 项在 T2 内退化为同值。

## 5. §5 边界（未知≠0 / 负利润 / 非 testable / H1）

| 边界（稿 L80–L87） | 核对 |
| --- | --- |
| 未知≠0：`net` 未知只落 T2、不参与正负比较、不填 0、不加分 | **与 CONTRACT §0.4 / scenario 语义一致** ✓（`scenario.py:194-201`；CONTRACT §0.4 L47-51） |
| 负利润：展示并标注、不加正分、不隐藏 | **可算** ✓（`net<0`） |
| 非 testable 不进推荐池、pending 不得显示为已验证 | **与 recompute 一致** ✓（`state.py:198-200`） |
| 匹配 `excluded` 货源：不删除候选；有效 G2 失效时整体降级"失效提示" | **与代码一致**（PATCH invalid 会无条件建 blocking=1 `supply_invalid` 复核，`supplies.py:117-119`）✓ 但"非有效 G2 情形下其它 invalid 货源"未定义（观察池/探索池归属不明，见 F-03） |
| H1 提示只作提示、不加分 | **与匹配/H1 一致** ✓（`matching.py:60-65`） |
| 数据不足：无需求信号/无货源 → 计数"数据不足" | **判据未定义**（F-12） |

## 6. §6 输出（只读、不落库）

- 纯函数 `rank_candidates(conn, *, limit=5, budget_minutes=30, rank_version="rank-v1")`、GET 零副作用、不新增表/列/端点 ✓ 与 §1"不做"一致；`inputs_used` 提供了可解释输入 ✓；无"成功率/收益率预测"字段 ✓；`rank_version` 固定可追溯 ✓。
- **缺口**：`items` 是否含 blocked/观察/探索池、全局 `rank` 如何跨池编号、`pools` 计数与 `items` 的关系未定义（F-08）；`budget_minutes` 参数在输出中无体现（F-09）。

## 7. §8 每日 5 条口径（PRODUCT D09）

- D09（`PRODUCT.md:33`）："目标每天更新一次，每次最多 5 条重点机会，完整候选池可查看；不足按实展示，不凑数；重要失效信息发现后提醒。" → 稿 §8（L122–L126）五项**逐条对应一致**：每日一次由 S5 触发（本文无定时器）✓；仅推荐池前 5、超出放 `omitted` 且标真实名次 ✓；不足不补位 ✓；完整池可查看 ✓；失效提醒置顶 ✓。
- D04（`:28`）弱证据高潜力单列 ✓（探索池）；D08（`:32`）四项证据入池前提 → 推荐池=testable 且四门槛 verified ✓。
- **偏差**：PLAN §8 S4-B3（`DEVELOPMENT_PLAN.md:123`）"在人工 30–60 分钟预算内…排序"；稿 §2/L151 把 `budget_minutes` 只作展示提示、不参与排序——需明确此偏差或给出用途（F-09）。

## 8. §9 R-01…R-14 可执行性

| # | 可执行？ | 问题/依据 |
| --- | --- | --- |
| R-01 | **部分可执行** | `net=190` 来自 CONTRACT §4.7 正例（`CONTRACT.md:547`），但导入的成本行 `fact_kind='assumption'` 且无 `assumption_note` → G3 需逐项补说明；`verify_all_gates` helper 自带 DEFAULT_COSTS（net≠190）。须写明"按 role/basis 逐项 POST /cost-items（同值+说明）取代活跃行后再核验"（F-10） |
| R-02 | **不可按现构造验证并列链** | "net 相同、门槛相同、观察时间不同" → 新鲜度分不同 ⇒ **分数不同**，不构成并列；同分需同新鲜度桶（如都在 7 天内不同时刻）再依次验人工分钟/`candidate_id`（F-11） |
| R-03 | **构造与 T2 定义矛盾** | 缺成本角色 → G3 不成立 → pending（非 testable）→ 不进推荐池；T2 只能来自"testable 但缺假设"（F-01） |
| R-04 | **归属不可判定** | pending+货源：按现文字可同时满足观察池与探索池；"探索条件"未定义（F-03） |
| R-05 | **不可能成立** | `license_unknown` ⇒ G2 未 verified ⇒ 非 testable ⇒ 不在推荐池；"推荐池内 −2"不可发生（F-15） |
| R-06 | **可执行且语义正确** | PATCH 货源 invalid → 无条件 blocking=1 `supply_invalid` 复核（`supplies.py:117-119`）→ recompute=stale，且按 §3 失效提示（blocking）✓；"置顶"位次仍待 F-08 |
| R-07 | **可执行** | 观察时间可造 31 天前（导入 observed_at 校验格式即可）✓；但"同层项"并列/分数关系需明确（与 F-06 相关） |
| R-08 | **可执行** | 负 net 可由高成本/低售价构造；T1 允许负 net（complete 且已知）✓ |
| R-09 | **可执行** | 6 个 testable 候选可由 helper/API 构造；`limit=5`+`omitted` ✓ |
| R-10 | **可执行** | 2 个推荐候选 ✓ |
| R-11 | **可执行** | override 枚举真实（`candidates.py:10`；schema `:53`）✓；override 需 `override_reason`（`candidates.py:20-22`） |
| R-12 | **可执行但需固定 as_of** | 同一输入两次调用在跨新鲜度阈值时可能不同（F-06）；四表快照可验证零写，但排序还读 scenario/cost_item，建议全表快照（F-18） |
| R-13 | **可执行** | 断言输出无成功率/收益率字段、`rank_version` 固定 ✓ |
| R-14 | **属实现批** | 修改权重表为 `rank-v2` 需实现批代码；本设计批不可执行，应标注（F-16） |

## 9. 越界检查

| 检查 | 结论 |
| --- | --- |
| 新接口/端点/CLI/定时器 | **无**（L3、L105；每日触发留 S5） |
| 新表/列/迁移/依赖 | **无**（L3、L105） |
| 自动核验/改状态/改金额/写库 | **无主张**；§7 明确只读 ✓ |
| 模型打分/互动量/热度 | **无**；§4.2 明确不用 ✓ |
| 权重被写成"已校准" | **无**；L4、L43、L151 明确启发式、不称已由经营数据训练 ✓ |
| 进 GET 的承诺 | **无**；L151 待裁定④，未承诺 ✓ |
| 夸大 | L56"满分 100"算术错误（F-07）；R-01/R-02/R-05 的构造与期望不实（F-10/F-11/F-15）——属内部不实，非越界 |

## 10. 缺项 / 歧义 / 风险

| 编号 | 严重度 | 问题 | 位置 | 方向 |
| --- | --- | --- | --- | --- |
| F-01 | **阻断** | T1/T2 与情景参数未定义：`complete=false` 的另一主因是缺 amortize/monthly 假设；R-03 用"缺成本角色"造 T2 与定义矛盾 | L49–L50、R-03 | 明确排序调用情景的参数口径；T2 改为"testable+正固定成本+不传假设" |
| F-02 | **阻断** | R-05 在推荐池计 −2 不可能：`license_unknown` ⇒ 非 testable | R-05 | 改为待核验池的提示或删除 |
| F-03 | **阻断** | 观察池/探索池边界循环定义；matching 恒 `needs_review`+`dims_text_only` → pending+货源默认落探索池，R-04 期望落空 | L35–L36、R-04 | 定义可判定的"探索条件"（如 license_unknown/format_unknown 等具体缺口），写死默认归属 |
| F-04 | **阻断** | `stale` 候选（G1 failed、G4 版本不一致、手工 failed/expired 门槛行无 blocking）无池可归 | L33、§3 | 以 `recompute` 的 stale 为准补"待处理/失效提示"兜底池 + next_action |
| F-05 | **阻断** | 新鲜度/并列键的 `observed_at` 未规定取哪条 demand_signal（多版本） | L21、L74 | 明确"最新未 superseded 版本"或"最近 last_seen"并写入 inputs_used |
| F-06 | **阻断** | 新鲜度用当前 now，跨 7/30 天边界会改变分数/次序，违反"相同输入相同顺序" | L64、R-12 | 引入 `as_of`（默认 now 但入输出/入参）或按自然日取整 |
| F-07 | **阻断** | "满分 100"算术不成立（最大 101；含 −2 为 99） | L56 | 删改分值域表述（非百分比） |
| F-08 | **阻断** | blocked/观察/探索池无 tier；`items` 是否含各池、全局 rank 顺序（"置顶"vs T1 rank1）未定义 | L45–L54、L94–L102 | 定义 pool_order + 全局连续 rank + items 范围 |
| F-09 | 需修订 | `budget_minutes` 只作提示，与 PLAN §8"在 30–60 分钟预算内排序"不一致 | L26、L151 | 明确偏差或给出用途（展示截断/next_action） |
| F-10 | 需修订 | R-01 构造缺"补 assumption_note/绑定"的步骤，helper 成本 net≠190 | R-01 | 写全构造步骤 |
| F-11 | 需修订 | R-02 不能验证并列链（时间不同 ⇒ 分数不同） | R-02 | 拆"同分"与"同分后并列键"两 case |
| F-12 | 需修订 | 观察池"有需求信号"与"不排序"判据未定义/混用 `no_supply_rows` | L35、L37 | 定义查询口径（如 demand_signal COUNT>0） |
| F-13 | 需修订 | 人工分钟未指定行（role/basis/variant/is_active） | L66 | 与情景同口径取 `manual_labor/per_order/base/active` |
| F-14 | 需修订 | 供应稳定排除 supply `stale` 未说明；应与 `effective_gate_status`/matching 同源 | L65 | 注明口径与引用 |
| F-15 | 需修订 | 匹配 −2 对推荐池恒定（`dims_text_only` 恒真）；`license_unknown` 在 testable 不可能 | L67 | 仅计非恒真缺口或注明无区分度 |
| F-16 | 需修订 | R-14 属实现批（改权重表） | R-14 | 标注实现批后验 |
| F-17 | 建议 | "无效 observed_at 只作缺失"与 NOT NULL+导入校验不符（防御性分支） | L21 | 注明仅防御，不误导为常见情况 |
| F-18 | 建议 | R-12 建议全表快照（排序还读 scenario/cost_item） | R-12 | 扩为全表 |

## 11. 结论

**需修订**：设计在"只读、分池优先、tier 不作跨层比较、未知≠0、权重启发式、每日 5 条口径"这些边界上是**扎实且与代码/契约/产品一致**的（§1/§5/§7/§8 逐项核对通过；`manual_override` 枚举、blocking 复核、D04/D08/D09 引用均真；R-06 语义正确；无越界承诺）。但 §3 分池边界与 §4 计分/并列存在 **8 项阻断级缺口**（F-01…F-08），集中在：T1/T2 与情景参数未定义、R-03/R-04/R-05 三条矩阵期望不可实现、`stale` 无归属池、观察/探索池边界循环、`observed_at` 取行与 now 依赖破坏确定性、分值域算术错误、blocked 池位次未定义。

在 M-01…M-10 修订前，**不建议进入排序实现批**；修订后本设计的只读边界与分池框架可直接作为实现约束。

## 12. 最小修订项

| 编号 | 修订项 | 对应 |
| --- | --- | --- |
| M-01 | 明确排序调用情景的参数口径（variant/amortize_orders/monthly_orders 由调用方传入并记录；无参数时 complete 可能为 false）；T1=testable+complete+net 已知，T2=testable+complete=false；R-03 改为"testable+正一次性成本+不传假设→T2" | F-01/F-11 |
| M-02 | 修 R-05：`license_unknown` 属待核验池；把"匹配缺口 −2"限定为推荐池可能出现的恒真缺口并说明不具区分度，或删除该计分项 | F-02/F-15 |
| M-03 | 定义"探索条件"可判定规则（如：matching 有 `license_unknown`/`format_unknown`/`scope_text_only` 或缺结构化字段），明确 pending+有货源 的默认归属，R-04 与之一致 | F-03 |
| M-04 | 以 `recompute` 的 `stale` 为准补"待处理/失效提示"兜底池（含 G1 failed、G4 版本不一致、手工 failed/expired 无复核情形）；定义 pool_order（blocked→T1→T2→T3→T4）与全局连续 rank、items 范围 | F-04/F-08 |
| M-05 | 明确 `observed_at` 取行规则（最新未 `superseded_by` 版本，或按 last_seen），写入 inputs_used；人工分钟行选择与情景同口径 | F-05/F-13 |
| M-06 | 引入 `as_of`/自然日口径使新鲜度可复现；R-12 固定 as_of 并扩为全表快照 | F-06/F-18 |
| M-07 | 修正分值域表述（最大 101/含 −2 为 99；非百分比）；核对各 tier 上限 | F-07 |
| M-08 | 与 PLAN §8 对齐 `budget_minutes` 语义（明确偏差，或用于展示截断/next_action） | F-09 |
| M-09 | 修 R-01 构造（补 assumption_note/供给绑定步骤）、R-02 拆分同分/并列两 case、R-14 标实现批 | F-10/F-11/F-16 |
| M-10 | 细化观察池"有需求信号"判据、供应稳定口径与引用、`observed_at` 无效值说明 | F-12/F-14/F-17 |

## 13. 声明与限制

- **未修改**被评审文件（哈希评审前后未变，见 §0.2）与任何源码/测试/契约/迁移/台账。
- **未联网、未启动应用、未运行测试**；本文不是实测证据，R 矩阵结论均为"按现有 API/字段静态推演"。
- 只读复算了 §0.2 的 12 个文件 sha256；未做其它写入。
- 行号以评审时点文件为准；若稿或代码修订需按新哈希重核。
- 本会话**无 `skill` 工具**，未加载任何技能；未核实处（如 `_check_at` 对异常 observed_at 的具体落库存量）已按"防御性"标注。
