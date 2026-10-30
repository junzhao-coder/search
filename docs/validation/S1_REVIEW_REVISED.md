# S1-D 修后复核报告（S1-B v2 修稿）

> 任务：`task-3c19b60359c00298e640e1def4f03d3a`（revision 2，计划 v2）；执行者 `session-c1428bc7-460b-511e-aaea-719314ba8cbc`（D 独立质量槽位）。
> 观察时点：`flow_state` revision 440 / board 68；本任务 revision 2 / running；B 原任务 `task-254ec97f52b2f282d53d9bd5fdf61d8d` revision 6 / **review（尚未验收）**。
> 读稿版本（只读）：[CONTRACT.md](<../design/CONTRACT.md>) v2 **767 行**、[ACCEPTANCE.md](<../design/ACCEPTANCE.md>) v2 **115 行**；对照基线 [PRODUCT.md](<../../PRODUCT.md>) 107 行、[DEVELOPMENT_PLAN.md](<../../DEVELOPMENT_PLAN.md>) 236 行（附录 A P1–P4）、A 报告 [FEASIBILITY.md](<../research/FEASIBILITY.md>) 321 行 / [SAMPLES.json](<../research/SAMPLES.json>) 665 行 12 条、D 原稿 [S1_REVIEW.md](<S1_REVIEW.md>) 129 行、B 原任务九组退回反馈（Flow 原文）。
> 性质：**静态契约复核 + 文档反例检查**（内存 SQLite、标准库解析，见 §6）。**没有任何应用代码、迁移、HTTP、界面或集成测试被执行**；契约与矩阵仍属 review，未冻结，本报告不代表 S1 通过。

## 1. 结论摘要

- 九组返工**全部落实**，无一组原样保留；R1–R7 原缺陷已消除或按最小范围收口；三组（②③⑤）经内存 SQLite / 算术独立复算通过（§2、§6）。
- 修后仍有 **2 项 P1（建议冻结前修，各为 1–2 句规则澄清）**、**5 项 P2**、**5 项 P3（可实施约定 / 后续阶段）**。无需要重写契约的问题。
- 未发现"为改而改"的过度设计：新增仅一张最小幂等表（§1.15）与三类采购 basis，符合最小实现；阶段归位（备份→S6）与"未执行"标注准确。

## 2. 九组逐组核对

| 组 | 已修定位（CONTRACT/ACCEPTANCE） | 我方最小输入验证 | 结论 / 剩余 |
| --- | --- | --- | --- |
| ① 非负输入 / 负派生 / NULL 未知 / 0 | §0.3 表 35–36、规则 40–44；§0.4 46–51；§2.2 294–295；§4.7 语义反例 575–581；G3 373；S2-11/17 | 内存 SQLite：全空值行 **ACCEPT**（未知不被强制为 0）、输入负额 **REJECT**、双值 **REJECT**、`value_kind='money'` 而值为空 **REJECT**、`predicted=-200` **ACCEPT**、`amount=-100` **REJECT**；`(3333*500+5000)//10000=167`、`(15*3000+30)//60=750` 与 §0.3/§5.5 一致 | 已修。**残留 P1-1**（§2.2 295 行"派生值不落库存储"与落库快照冲突） |
| ② 可空来源 FK / 每日唯一键 / 同秒复核 | 246（`source_id` NULL）、292（`COALESCE` 表达式部分唯一索引）、188/291（`seq` + `UNIQUE(candidate_id,gate,seq)`）、302（I1 唯一写入点）、S2-01/15 | 内存 SQLite：同日第二条无来源 `pipeline` **REJECT**（索引生效）；`recompute` 同日两次 **ACCEPT**；带来源 `pipeline` **ACCEPT**；`source_id=''` **REJECT**（外键悬空，证明 v1 问题已消除）；未登记来源 **REJECT**；`seq=2` 首插 **ACCEPT**、重复 `seq=2` **REJECT** | 已修，无剩余 |
| ③ 身份 / URL 兜底 / 真实合成隔离 / 复用 / 版本 / 子项 / 合并 | 289（三张表强键均含 `data_origin`）、484（兜底链）、492–503（再导入决策表）、501（子记录独立判定）、505（冲突不静默）、508（合并禁跨界 + 冲突预检） | 逐情形走查七行决策表：原样重导→`duplicate_skipped`、内容变化→`version_added`+复用候选、异 URL 同文→`dup_suspect`、无需求组标题变化→新候选+复核、仅成本/货源变化→子记录独立、补第二货源→API 追加、real/synthetic 同键→两条独立记录 | 已修。**残留 P2-2**（候选身份未含来源命名空间）、**P3-4**（第三档身份不可达） |
| ④ 显式映射 / 渠道归属 / 版本 / client_ref / `_minor` | §4.3 406–444（40+ 行映射表）、230–232（四行来源种子 + 未登记名行级错误）、386–387（`format_version`、`client_ref` 只在 query/头）、44（JSON `_minor` 例外）、V21 470 | 标准库解析：CSV 正例 **35 列自洽且无未列名列**（与 518 行声明一致）；来源名解析、金额元→分、`supply_price` 空=未知/0=免费均可逐行落地 | 已修。**残留 P1-2**（`_minor` 列形式未进 §4.2/§4.3 而 V5/V21/正例在用） |
| ⑤ 逐单采购 / 买断摊销 / 人工与费率取整 / 取代 | 437–439（拆 `per_order`/`one_time`/`recurring`）、168（`supply_offer_id`）、373（G3）、§5.5 658–661（contribution / `fixed_cost_gap` / `amortize_orders`）、290（活跃项唯一）、S2-18/19 | 算术复算：`1000-200=800`（与 S2-18 一致）；买断例 `1000-50-500=450`、`amortize_orders=20` → `net=-50`（与 S2-19 的 `contribution−1000` 口径一致）；内存 SQLite：`recurring` 缺 `period` **REJECT**、同 `(role,basis,variant)` 活跃重复 **REJECT** | 已修。周期归一月额/余分处理按 §9 765 行留 S4，与本阶段一致 |
| ⑥ 四门槛业务准入与反例 | §3.5 365–378（G1–G4、`system_rule` 只能降级）、I5 306、S2-13/14 | 逐条走查四个反证：`resale_allowed='no'` / `sample_checked='none'` / `payment_fee` NULL / 平台证据针对他平台 → 均在 G2/G3/G4 被挡，返回 `422 invalid_state`；§5.5 682–691 给出拒绝示例 | 已修。**残留 P3-1**（`value_kind='minutes'` 未限 `manual_labor`，可绕过 G3 的"已知值"） |
| ⑦ 成交/退款关联、结算、成本追加 | §1.8 204–220（`order_ref`/`related_feedback_id`/`refund_state`/`actual_*`/`actual_complete`）、#26 631、#27 632、I4 305、§5.5 693–715、S2-23/25 | 走查 D-11 断言：成交 10000 + 预留 500 → 快照 9500；退款 10000 `pending` 不计入 → `settled` 实际 0（非 −500）；重复结算不二次扣减；`predicted_*` 沿用快照 | 已修。**残留 P2-5**（`actual_*` 载体未明） |
| ⑧ 持久幂等 / 白名单 / 写入口闭合 | §0.7 64–70、§1.15 262–274、§5.2 600（`invalid_field`）、§5.4 636–654（逐端点必需输入/默认/成功/拒绝）、S2-24/26 | 逐端点走查：草稿/反馈/门槛/导入等有 scope；`PATCH /api/feedback/{id}` 拒绝 `predicted_*` 与非白名单字段；幂等记录与业务写入同事务、重启可重放 | 已修。**残留 P2-3**（复核项可增殖）、**P3-2**（`request_hash` 对 multipart 未定义） |
| ⑨ 阶段与运行证据口径 | ACCEPTANCE 13（状态取值含"留空（缺工具）"）、19（已知事实按时间点）、34（T-12 标 S6）、100（S6-02）、66（S2-27 异机留空）、68（S2-29 缺浏览器留空）、110（D 用例映射） | 机器计数：矩阵 **67 行**、状态列无"通过/失败"（唯一"通过"字样出现在 13 行的取值说明）；备份恢复归 S6 不再冒充 S2 必做 | 已修，无剩余（验收时保持"未执行"即可） |

## 3. 修后新增缺陷（按严重度）

### P1-1 · §2.2 295 行"派生值不落库存储"与反馈快照落库冲突

- 依据：[295 行](<../design/CONTRACT.md#L295>) 声明"派生列不设 `>=0` 约束（`predicted_net_per_order_minor`、`actual_net_per_order_minor`）。**派生值不落库存储、仅接口计算**"；但 [§0.3 36 行](<../design/CONTRACT.md#L36>) 要求"必须如实返回与存储"，[§1.8 216–217 行](<../design/CONTRACT.md#L216-L217>) 把二者定义为 `feedback` 列，[I4 305 行](<../design/CONTRACT.md#L305>) 规定"写入后不可变 + 白名单更新"。
- 最小输入：成交 10000 分、预留 500 → 需落库 `predicted_net_per_order_minor=9500`；亏损候选需落库 `-200`。若实现者按 295 行字面建表（不建这两列），则 I4 白名单、[S2-17②](<../design/ACCEPTANCE.md#L56>)、[S2-23](<../design/ACCEPTANCE.md#L62>) 无处校验。
- 预期：区分两类——**情景派生值**（`contribution_per_order_minor`/`net_per_order_minor`/`fixed_cost_gap_minor`）仅接口计算、不落库；**反馈快照**（`predicted_*`/`actual_*`）落库且无 `>=0` 约束。
- 最小修法：把 295 行改为"派生列不设 `>=0` 约束（`predicted_*`/`actual_*` 落库）；情景计算值（contribution/net/gap）仅接口返回、不落库"。一句话，不新增字段。

### P1-2 · `_minor` 列形式未被 §4.2/§4.3 收录，却在 V5/V21 与正例中使用

- 依据：[§0.3 44 行](<../design/CONTRACT.md#L44>) 允许 `sale_price_minor` 这类键（JSON number）；[V5 454](<../design/CONTRACT.md#L454>)、[V21 470](<../design/CONTRACT.md#L470>) 明确区分"无 `_minor` 后缀列"与"`*_minor` 列"；但 [§4.2 列清单 395–402 行](<../design/CONTRACT.md#L395-L402>) **不含任何 `_minor` 列**（机器计数：`_minor` 在 §4.2 出现 **0** 次），[§4.3 映射表 406–444 行](<../design/CONTRACT.md#L406-L444>) 也没有 `sale_price_minor → cost_item` 行。
- 最小输入（机器验证）：JSON 正例 [535 行](<../design/CONTRACT.md#L535>) 使用 `"sale_price_minor": 1990`。按 §4.2 该键不在列清单 → 命中 [V18 467 行](<../design/CONTRACT.md#L467>)（未知列，**仅 warning**）→ 不产生 `sale_price` 成本项 → 情景缺必需角色、`complete=false`，与 [S2-03](<../design/ACCEPTANCE.md#L42>) 的"成本项按 §4.3 建行 / 返回真实实体 ID"不符。反例表头 [562 行](<../design/CONTRACT.md#L562>) 同样依赖该未列名写法。
- 预期：金额列存在两种等价写法（元字符串 / `_minor` 整数），V21 负责二者冲突判定，且其判定**先于** V18。
- 最小修法：在 §4.2 增一句"金额列另有 `_minor` 整数形式（如 `sale_price_minor`），与元字符串形式等价、至多出现一种；二者同时出现按 V21 判定"；并注明 V18 的"未知列"仅指真正未定义列名。不新增列、不改金额单位。

### P2-1 · 反例 CSV 首行列数 9 ≠ 表头 8，且契约无"列数不一致"规则

- 依据：[§4.7 反例块 561–571 行](<../design/CONTRACT.md#L561-L571>) 声明 8 列表头；[573 行](<../design/CONTRACT.md#L573>) 声称首行应按 V2（`title` 空）拒绝；但 [V1–V24（446–473 行）](<../design/CONTRACT.md#L446-L473>) 未定义"行字段数与表头不一致"如何处理。
- 最小输入（机器验证）：首行 `,synthetic,2026-06-01T08:00:00Z,12.00,,,,,` 解析为 **9 个字段**（表头 8 列），其余 7 行均为 8。
- 预期：该行以明确定义的原因被拒，且拒绝原因可预测（V2 或新增的列数规则）。
- 最小修法：补一条校验（如"V25 行字段数 ≠ 表头列数 → 行级拒绝，原因含期望/实际列数"），并把该样例行补齐为 8 列。属样例自洽问题，不阻塞设计。

### P2-2 · 候选身份未含来源命名空间，跨来源同名原生 ID 会落到同一候选

- 依据：[484 行](<../design/CONTRACT.md#L484>) 候选身份"有需求组时沿用其需求信号键"，需求键第一档为**原始 `native_id`**；[289 行](<../design/CONTRACT.md#L289>) 候选唯一键为 `UNIQUE(data_origin, identity_key)`，**不含 `source_id`**；[490 行](<../design/CONTRACT.md#L490>) 命中即"复用它，不重建"。
- 最小输入（机器验证）：`source=xianyu, native_id='1001'` 与 `source=bilibili, native_id='1001'` 两行 → 候选唯一键相同（内存 SQLite 第二次插入 **REJECT**，即实现必须复用）→ 两个不同平台的商品成为**同一候选**，且不产生 `dup_suspect`（[492–503 行](<../design/CONTRACT.md#L492-L503>) 决策表未覆盖"异来源同 native_id"）。
- 预期：或视为两条独立机会，或至少进入 `dup_suspect` 人工复核；不得静默合并。
- 最小修法：身份键带来源命名空间（如 `<source_id>|<native_id>`），或对"异 source、同 native_id"生成 `dup_suspect`（`blocking=0`）。一句话，不动强键结构。

### P2-3 · 复核项无"同一引用未决唯一"约束，重复物化会增殖

- 依据：[296 行](<../design/CONTRACT.md#L296>) 索引仅 `review_item(status)`；[§3.4 363 行](<../design/CONTRACT.md#L363>) 在每个 `recompute`/流水线物化；[292 行](<../design/CONTRACT.md#L292>) 与 [I11 312 行](<../design/CONTRACT.md#L312>) 明确 `recompute` 允许同日多次；[#7 612 行](<../design/CONTRACT.md#L612>)、[#9 614 行](<../design/CONTRACT.md#L614>) 也可重复触发。
- 最小输入：同一门槛 `expires_at` 置过去 → 连续两次 `recompute`（或先 `invalidate` 再 `recompute`）→ 预计出现 **2 条** 同一 `(ref_type, ref_id, kind='gate_expired')` 的 `open` 复核项；[S2-14/15](<../design/ACCEPTANCE.md#L55-L56>) 只断言存在与阻断位，不断言条数，故实现差异不会被现有行发现。
- 预期：同一引用同一原因只保留一条未决复核项（或明确允许重复并在读取端聚合）。
- 最小修法：加部分唯一索引 `UNIQUE(ref_type, ref_id, kind) WHERE status='open'`；重复触发命中即幂等跳过。不影响 S2 其他行。

### P2-4 · C 的 P3 导入页要求"预览"，契约端点表无 validate/dry-run 模式（跨范围）

- 依据：[DEVELOPMENT_PLAN.md 190 行](<../../DEVELOPMENT_PLAN.md#L190>) P3 主路径为"CSV/JSON 选择→**预览**→校验→确认写入"；契约端点表 [#1 606 行](<../design/CONTRACT.md#L606>) 只有 `POST /api/imports`（写入型），[#2 607 行](<../design/CONTRACT.md#L607>) 只回读批次结果，无试运行入口。
- 最小输入：S2-C 按 IA 实现两步导入 → 无接口可调用（前端解析会把校验规则复制一份，违反"单一口径"）。
- 预期：预览/校验与写入同源。
- 最小修法（择一，由策划者定）：① 契约增 `mode=validate`（不写业务数据、返回同结构行级结果）；② 或 C 把 IA 措辞改为"提交后行级校验结果即为预览"。属 B↔C 协调项，我不代改任一方。

### P2-5 · `actual_*` 的载体与多笔聚合口径未明

- 依据：[§1.8 217–219 行](<../design/CONTRACT.md#L217-L219>) 把 `actual_*` 定义在 `feedback` 任意行；[§5.5 707–715 行](<../design/CONTRACT.md#L707-L715>) 的结算 PATCH 落在**退款行** `fb_b1` 并返回该订单实际值；[I4 305 行](<../design/CONTRACT.md#L305>) 白名单允许更新任意反馈行的 `actual_*`。
- 最小输入：成交 5000 + 成交 15000 + 一笔退款 5000（S2-23 同款场景）→ 该退款结算后，实际值写在退款行、成交行、还是读取时按 `order_ref` 聚合？跨行时"每单实际利润"的分母（`quantity`）也未定义。
- 预期：订单级实际值有唯一承载与可复算口径；S5 统计与 D-11 断言不因实现选择而分歧。
- 最小修法：一句规则即可——"实际值按 `order_ref` 聚合计算（读取时），可物化到对应 `sale` 行；退款/支出行只记自身字段"，或"结算时写回对应 `sale` 行的 `actual_*`"。

### P3（可实施约定，不阻塞 S2 冻结）

- **P3-1** `value_kind='minutes'` 未限定 `role='manual_labor'`：[294 行](<../design/CONTRACT.md#L294>) 只对 `hourly_rate_minor` 设了角色约束；机器验证 `role='platform_fee', value_kind='minutes'` **ACCEPT** → 该角色没有金额值却算"有行"，G3 的"已知值"判定需额外口径。修法：补 `value_kind='minutes' ⇒ role='manual_labor'`，或在 G3 注明每角色允许的 `value_kind`。
- **P3-2** `request_hash` 对文件导入未定义：[269 行](<../design/CONTRACT.md#L269>) 只写"body 关键字段"，multipart 场景无 body 字段。修法：注明文件内容 sha256（或批次文件哈希）+ 路径/查询参数规范化算法；并说明 [#7](<../design/CONTRACT.md#L612>)/[#9](<../design/CONTRACT.md#L614>)/[#14–15](<../design/CONTRACT.md#L619-L620>)/[#17](<../design/CONTRACT.md#L622>)/[#27](<../design/CONTRACT.md#L632>) 为何无需 `client_ref`（同值幂等）。
- **P3-3** 无需求组行的 `observed_at` 无落点：[411 行](<../design/CONTRACT.md#L411>) 只映射到需求信号与派生证据，而 `candidate` 无该字段；只填基础+成本/货源的行给出 `observed_at` 会被静默忽略。修法：该情形记 `warning`（或写入 `notes`），与"不静默丢弃字段"口径一致。
- **P3-4** 身份第三档不可达：[472 行](<../design/CONTRACT.md#L472>) 的"字段缺失时用内容指纹"在需求组 `url` NOT NULL（[103 行](<../design/CONTRACT.md#L103>)）+ V10 必填下无法触发，候选侧已用 `t:<title_norm_hash>`。修法：注明该档仅适用于无需求组的标题身份，或删除以免实现者误放空 URL。
- **P3-5** D-12 端到端未单行覆盖：矩阵已把 D-01–D-11 映射进 S2 各行（[110 行](<../design/ACCEPTANCE.md#L110>)），但"导入→补成本/货源/证据→四门槛→草稿→反馈→重启"的**一次贯通**没有单行（S2-02/14/22/23 分散）。修法：补一行端到端（用冻结合成样本，含重启），供 S2-D 直接引用。

## 4. D-01–D-12 与矩阵映射核对

D-01→S2-03 ✓；D-02→S2-04/05 ✓；D-03→S2-06 ✓；D-04→S2-07 ✓；D-05→S2-11 ✓；D-06→S2-17 ✓；D-07→S2-01 ✓；D-08→S2-13 ✓；D-09→S2-18 ✓；D-10→S2-24 ✓；D-11→S2-23 ✓；D-12→分散覆盖（见 P3-5）。R1–R7 七组均已在上表九组中收口；原稿"负利润违反 CHECK""无 ID 身份""去前缀同名""逐单采购漏扣""门槛无业务准入""退款无归属""幂等无落点"七个具体冲突，我逐条按最小输入复算后**确认已消除**。

## 5. A / C 一致性

- A §7.1（[256 行](<../research/FEASIBILITY.md#L256>)）把研究侧 `manual` 与 `xianyu`/`xiaohongshu`/`bilibili` 并列，标注"待 B 冻结"；契约现已冻结为**四个种子名** `manual_import`/`xianyu`/`xiaohongshu`/`bilibili`（[230 行](<../design/CONTRACT.md#L230>)），且未登记来源名 → **行级错误**（[232 行](<../design/CONTRACT.md#L232>)、[V9 458 行](<../design/CONTRACT.md#L458>)）。即研究侧 `manual` 直传会被拒。建议：由策划者决定在 A 报告加一行归一说明（`manual → manual_import`）或在 §4.3 增别名；我未改任一方成果。
- A 的 `license_reviewed`/`lead`/`blocked` 等标签与 `supply_offer.status` 无映射已双向落实（[A 188 行](<../research/FEASIBILITY.md#L188>)、[CONTRACT 157](<../design/CONTRACT.md#L157>)/[377](<../design/CONTRACT.md#L377>)/[761](<../design/CONTRACT.md#L761>) 行），S4-04 有对应检查行；研究索引不建契约列（[760 行](<../design/CONTRACT.md#L760>)）与 A 的"保留研究元数据"一致。
- 货源"只有证据 URL、无摘录"的处理已双向一致：契约只存链接、不建证据行（[428–429 行](<../design/CONTRACT.md#L428-L429>)），G2 因此不满足（S2-10③），符合"不虚构摘录"要求。
- C 侧：附录 A 的六个信息域与 P1–P4 均被契约 §9（[766 行](<../design/CONTRACT.md#L766>)）与矩阵（[S2-29](<../design/ACCEPTANCE.md#L68>)、[S6-06](<../design/ACCEPTANCE.md#L104>)）引用；唯一摩擦点是 P3 的"预览"步骤（见 P2-4）。

## 6. 本次实际执行的检查、工具与限制

**实际执行的命令类检查（仅内存/只读，无工作区文件产出）**：用 `load_workspace_dependencies` 返回的内置 Python（`C:\Users\19183\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe`）经 stdin 运行只读脚本，内容为：① 标准库 `csv`/`json` 解析 CONTRACT 的 §4.2 列清单与三个样例块（列数、未知列集合、逐行列宽）；② 内存 SQLite（`:memory:`，未落盘）按契约 §2.2 字面翻译建表并插入 10 个成本项反例、7 个 `run_record` 情形、`gate_review.seq`、反馈快照、候选唯一键；③ 整数分算术复算。输出要点：

- CONTRACT 767 行 / ACCEPTANCE 115 行（与读取器一致）；§4.2 解析出 **51** 个列名；CSV 正例 **35 列 = 35 列且无未列名列**。
- JSON 正例 **23 键**，其中 `sale_price_minor` **不属于** §4.2 列清单（§4.2 内 `_minor` 出现 0 次）→ P1-2。
- 反例块表头 8 列含 `sale_price_minor`；**第 1 行为 9 字段**，其余 7 行为 8 → P2-1。
- 矩阵行数 **67**；状态列无"通过/失败"字样（唯一"通过"样本出现在状态取值说明行）→ 第⑨组口径成立。
- SQLite：未知全空 **ACCEPT**、输入负额 **REJECT**、双值 **REJECT**、`value_kind='money'` 值空 **REJECT**、无 `value_kind` 有值 **REJECT**、`rate` 行 **ACCEPT**、`hourly_rate_minor` 非人工角色 **REJECT**、`recurring` 缺 `period` **REJECT**、`minutes` 非人工角色 **ACCEPT**（P3-1）、活跃重复 **REJECT**。
- 运行记录：无来源 `pipeline` 首次 **ACCEPT**、同日重复 **REJECT**；`recompute` 同日两次均 **ACCEPT**；`source_id=''` **REJECT**；未登记来源 **REJECT**。门槛 `seq` 递增 **ACCEPT**、重复 `seq` **REJECT**。反馈 `predicted=-200` **ACCEPT**、输入 **-100 REJECT**。跨来源同 `native_id` 候选键 **REJECT（须复用）**（P2-2）。算术：50 / 750 / 167 / 800 / 450 / -50。

**技能**：本任务匹配 `ponytail`。执行者角色无 `skill` 加载工具（此前同角色调用曾被 Flow 拒绝），故按已知磁盘路径读取 [ponytail SKILL.md](<C:/Users/19183/.dsh/profiles/desktop/node_modules/dsh-ponytail-skills/skills/ponytail/SKILL.md>) 全部 120 行并按其阶梯执行（最小修订、stdlib/SQLite 原生约束优先、不新增框架），**属磁盘读取而非工具化加载**。无下级代理。

**边界与限制**：
1. 未执行任何应用测试：没有 Flask/SQLite 应用、迁移、HTTP、并发、界面或端到端运行；上述 SQLite 检查只是把契约条款翻译成 DDL/DML 的**文档反例检查**，证明约束可表达、行为与预期一致或不一致，不构成实现或性能证据。
2. 契约与矩阵仍在 review（B revision 6，未验收）；若后续修订，行号以本次读稿版本（CONTRACT 767 / ACCEPTANCE 115）为准，冲突处以修订稿复核。
3. 未复测 A 的任何原始链接，未做网络调研；A 结论按其提交文本引用。未读取实现代码（不存在），未核对 UI 实现。
4. 仅新建本报告文件；S1_REVIEW.md 原稿、A/B/C 成果与根目录台账均未改动；无依赖安装、无账号/采购/发布/发送动作、无范围外文件产出（脚本经 stdin 传入，未在工作区落盘）。
5. 本次提交只进入待验收；九组落实结论与 P1/P2/P3 定级由策划者在冻结决定中采纳或调整，最终验收与 S1 冻结由策划者负责。
