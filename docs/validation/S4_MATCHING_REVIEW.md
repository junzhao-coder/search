# S4-B1 离线货源匹配设计 · 独立评审（非作者评审）

> 评审对象：[docs/design/S4_MATCHING_SPEC.md](<../design/S4_MATCHING_SPEC.md>)（108 行，sha256 `eaa1aa6568c88381e8dee0ee15f5884c54ba313ca149456420ccd44eed6b3359`，16076 bytes）
> 评审者：独立执行者 A（作者为原 B），任务 `task-b19e39b7dd140f0823a16b7558beb051`。评审时点：2026-10-20 13:00 +08:00。
> 性质：**纯只读评审**。未修改被评审文件与任何源码/测试/台账；**未联网、未启动应用、未运行任何测试**；只读复算了 §0.2 的文件哈希。
> 技能：本会话函数清单中**没有 `skill` 工具**，如实标注未加载。
> 结论：**需修订**（不建议直接进入匹配实现批）。阻断项集中在 §8 矩阵的 case 前置/期望与代码实际触发条件不一致（F-01…F-03）、机制引用不精确（F-04）、M-01 与 §2 判级自相矛盾（F-05）、H1 检测规则不可判定（F-06）。H2 的"复用既有机制、不新增 kind"经核对**成立**。

## 0. 方法与输入

### 0.1 评审方法

1. 逐行读 108 行设计稿，按"字段真实性 → 机制引用 → 只读与门槛关系 → H1/H2 → M-01…M-12 → 越界"顺序核对；
2. 对每条代码引用打开原文核行号；对每个矩阵 case 推演"按现步骤能否真正产生期望"；
3. 只读复算哈希；不把静态阅读写成实测证据；无法核实处明确标注。

### 0.2 只读复算哈希（评审时点 live）

| 文件 | sha256 |
| --- | --- |
| `docs/design/S4_MATCHING_SPEC.md`（108 行） | `eaa1aa65…b3359` |
| `app/core/state.py`（210 行） | `4cecfa5c…01dad` |
| `app/core/gates.py`（363 行） | `fc4f481f…f638d` |
| `app/core/supplies.py`（126 行） | `fd7b4530…400a` |
| `app/core/reviews.py`（128 行） | `1efba11a…03da` |
| `app/core/scenario.py`（281 行） | `f36f2844…93ad` |
| `app/storage/migrations/0001_init.sql`（294 行） | `9b049373…62bb` |
| `docs/design/CONTRACT.md`（812 行） | `826c24cc…b4f9` |
| `docs/design/S4_SCENARIO_SPEC.md`（231 行） | `e8fe6936…f75c` |
| `app/api/routes.py`（561 行） | `f3ef63d4…7630` |
| `app/core/importer.py`（991 行） | `a11eaf4d…51f1` |

## 1. §2 逐维字段核对（对照 `0001_init.sql` 行号）

| 维度（稿 L17–L22） | 稿中字段/判级/缺口 | 核对结果 | 依据 |
| --- | --- | --- | --- |
| 用途 | `candidate.category`/`use_case`；`demand_signal.excerpt`/`signal_kind`；`supply_offer.license_summary`/`license_scope_note`；仅提示；缺口"无受控词表" | **真** | `candidate.category` L46、`use_case` L47；`demand_signal.excerpt` L76、`signal_kind` L77；`supply_offer.license_summary` L138、`license_scope_note` L139；CONTRACT §9 L804/L810"分类词表未定（`category` 自由文本）"✓ |
| 内容版本 | `demand_signal.content_hash`/`version_no`/`superseded_by`；`supply_offer.format_version`/`native_id`；半可判定；缺口"无货源内容指纹/等价字段/版本血缘" | **真**（`format_version` 为 `TEXT NOT NULL DEFAULT ''`，自由文本 ✓） | `demand_signal` L87–L89；`supply_offer.format_version` L133、`native_id` L131；`supply_offer` 无内容指纹列（L125–155 全表） |
| 交付形式 | `candidate.delivery_form`；`supply_offer.downloadable`/`origin_type`；半可判定；缺口"无结构化交付形式枚举" | **真** | `candidate.delivery_form` L48；`supply_offer.downloadable` L142、`origin_type` L132（6 值枚举） |
| 适用条件 | G2 三项许可 + `sample_checked`/`sample_note`；`license_scope_note`/`license_evidence_url`/`license_summary`；`price_valid_until`；`status`/`last_checked_at`；G4 `applies_to_version`/`applies_to_platform`；部分可判定；"不存在 `supply_verified_at` 列" | **真**（无 `supply_verified_at` ✓）；**但"无结构化'适用平台/地区/语言/尺寸'等条件列"表述与 G4 两列冲突**（见 F-08） | 许可三值 L143–145、`sample_checked` L146/`sample_note` L147、`license_evidence_url` L140、`price_valid_until` L137、`status` L148、`last_checked_at` L149；`gate_review.applies_to_platform` L208、`applies_to_version` L209 |

**小结**：§2 所列字段**全部真实存在**，未发现虚构/错名/漏缺；仅一处"缺口"表述与同表列出的 G4 列自相矛盾（F-08）。

## 2. 机制引用核对（H2、TTL、状态派生、降级触发）

| # | 稿件引用（行） | 核对结果 | 依据 |
| --- | --- | --- | --- |
| 1 | `_supply_invalid` 的 30 天 supply TTL（L5、§5.2 行 4） | **真** | `state.py:12` `SUPPLY_TTL_DAYS = 30`；`:45-56`（`status='invalid'` 或 `last_checked_at` 超 30 天 ⇒ True）；`_older_than_days` `:24-28` |
| 2 | `effective_gate_status` 的 expired 判定（L5、§4.7、§5.2） | **真**；共 5 个 expired 触发点：证据失效/货源失效超期 `:164-166`、cost 完整性 `:167-172`、当前 G2（含版本）不一致 `:173-174`、`expires_at` 到期 `:175-177` | `state.py:158-178` |
| 3 | `recompute` 的 stale 分支（L5、§4.7） | **真** | `state.py:193-197`（blocking 复核或任一门槛 expired/failed ⇒ `stale:trigger`） |
| 4 | `supplies.py:93–123` 的 price/clause/version/invalidated 触发 | **真** | `supplies.py:93` `price_changed`、`:94` `version_changed`、`:95-99` `clause_changed`、`:100` `invalidated`；`:110-123` 降级与 `add_review` |
| 5 | 既有 review kind 枚举（L68、§5.2） | **真**：`supply_invalid`/`license_changed`/`cost_changed`/`gate_expired`/`evidence_expired` 全部在枚举内 | `0001_init.sql:222`（7 值：dup_suspect/gate_expired/supply_invalid/evidence_expired/license_changed/cost_changed/import_warning） |
| 6 | **H2"不新增 kind"** | **成立**：H2 表 5 行复用的 kind 均在既有枚举内；`reviews._degrade_reason` 只产出 `evidence_expired`/`supply_invalid`/`cost_changed`/`gate_expired`/`license_changed` | `reviews.py:71-92`；`gates.py:55`（append_downgrade 的 review_kind 实参来自 `supplies.recompute` 路径，也都在枚举内） |
| 7 | gate TTL 与 supply TTL 是两套 | **真**，但稿 §5.2 行 4 把两者合并成一行且未区分 | `gates.py:14` `GATE_TTL_DAYS={demand:90,supply_distribution:30,cost:30,platform_policy:180}`；`gate_expires_at` `:64-72`（min(证据 expires_at ∪ verified_at+TTL)）；supply TTL 见 #1 |
| 8 | `reviews.recompute` 物化（§4.7、M-07） | **真** | `reviews.py:96-128`（`_degrade_reason` → `append_downgrade` → `apply_status`；重复运行不增殖） |
| 9 | `_degrade_reason` 对"货源超 30 天"的 kind | **supply_invalid，不是 gate_expired** | `reviews.py:79-80`（`_older_than_days(last_checked_at,30)` ⇒ `("supply_invalid", "所选货源超过 30 天未复核（TTL）")`）；`gate_expired` 只在 `row.expires_at <= now` 时 `:91-92` |
| 10 | `supplies.py` 降级/复核的**前置条件** | **仅当当前门槛行 `status='verified'` 时**才追加降级行与复核；未核验时只更新 `supply_offer` 本身；`add_review('supply_invalid')` 例外——它总会被调用 | `gates.append_downgrade` `:39-44`（`current is None or current["status"] != "verified" → return False`）；`supplies.py:110-123` |

## 3. 只读与 G2/G3/G4 关系核对（§3/§4/§6）

| 稿件主张 | 核对结果 | 依据 |
| --- | --- | --- |
| §4.1 匹配从不写 `gate_review`、不置 verified、不改 `candidate.status`、不建 `review_item` | **与只读约束一致**（设计层面）；GET 零写的契约依据成立 | CONTRACT §3.3 L351"读时纯计算、不写库"；`routes.py:266-330`（详情只查询 + `state.recompute` 纯函数 + `effective_gate_status` 只读）；`state.py:181-182` docstring "never writes" |
| §4.2 "场景与成本只认 `state.current_gate_supply`（有效 verified G2 的最近 seq 货源）" | **不精确**：①情景实际用的是 `gates.selected_supply_id`（`scenario.py:13` 导入、`gates.py:75-88` 定义），它在"无有效 G2 但有唯一非 invalid 货源"时返回该货源作**数值估算**（永不升级门槛，CONTRACT §5.5-7 / `S4_SCENARIO_SPEC.md:112`）；②`current_gate_supply` 返回的是**最新 seq 行的 `supply_offer_id`（可能已 expired）**+有效状态，不是"有效 verified 的货源" | `state.py:123-132`；`gates.py:75-88`；`scenario.py:81-94` |
| §4.3 G2 准入条件 | **基本真**：三项 yes、`sample_checked≠none`+`sample_note`、条款证据（`license_evidence_id` 或本次 `evidence_id`）、货源属于本候选且未失效 | `gates.py:159-187`；**漏了**证据类型必须 `evidence_type='supply_distribution'`（`gates.py:186-187`；CONTRACT §3.5 L392）→ F-10 |
| §4.4 G3 成本须绑定当前 G2 货源、匹配不补成本、无绑定 → `no_cost_binding_to_g2` | **真**：G3 完整性只看当前有效 G2 货源（`state.usable_base_cost_rows`/`base_unknown_components` 的 supply 过滤；`gates._check_cost` 的 procurement 绑定校验） | `state.py:73-120`；`gates.py:190-217`；`scenario.py:90-94` |
| §4.5 G4 版本须等于当前 G2 货源 `format_version` 或 `*`；不一致只能标缺口 | **真** | `gates.py:233-240`；`state.py:147-154`（`_follows_current_g2` 对 platform_policy 的版本判定） |
| §4.7 状态派生、`recompute` 物化只由写入口/recompute 触发 | **真** | `state.py:181-210`（纯派生 + `apply_status` 唯一写点）；`reviews.py:96-128`；CONTRACT L351/L383 |
| §6 情景只取"当前 G2 所选货源"成本行（既有语义） | **不完整**：①有货源时只取 `selected_supply_id`（可为 None ⇒ 全部 unknown）；②无货源时普通行计入；③`sale_price` 例外（不按供给过滤） | `scenario.py:81-94`；`state.py:73-91`（`sale_price` 例外）；`gates.py:75-88` |
| §3/§4/§6 是否有"会写库/改状态"的说法 | **未发现**；设计明确"不落库、不写四表、不改 `selected_supply_id`/金额"（L36、L42、L74） | 稿 L29-L38、L42-L48、L72-L76 |

## 4. H1/H2 可落地性

### 4.1 H1（名称相似/自称可转售 ⇒ 不升级核验）

- **正向**：设计明确"只标 `hint_only`/`needs_review`，不改许可字段、不置 verified、不写表"（L52–L56），与纯读函数结构一致，**不会被实现成隐式核验**的前提是：匹配模块不调用任何写入口。该约束写法成立。
- **缺口**：**"名称相似"与"自称可转售"的判定规则未定义**——没有相似度算法/阈值/字段范围，也没有"可转售/可商用"等关键词清单；M-02/M-03 的 `reasons=[name_only_similarity]/[self_claim_only]` 因此**不可判定、不可核验**（F-06）。
- 建议：H1 给出确定性规则（例如"当且仅当该维无结构化许可能判定、且固定关键词表命中时才标 `self_claim_only`；不做相似度打分，名称仅作人工复核提示"），并在 §8 写明判定输入。

### 4.2 H2（失效/许可变化 ⇒ 触发复核，复用既有机制，不新增 kind）

- **H2"不新增 kind"成立**（见 §2 #5/#6）。
- 触发语义与代码一致（`supply_invalid`/`license_changed`/`cost_changed`/`gate_expired`/`evidence_expired`）。
- **但**：稿 §5.2 表把"既有动作"写成必然结果，实际**仅当对应门槛当前行为 `verified`** 时才产生降级行与复核（`gates.py:39-44`）；未核验时只更新 `supply_offer`（`supplies.py:110-123`）。M-04/M-05/M-06/M-07 的步骤缺"先核验"前置（F-02）。
- **两套 TTL 未区分**：`last_checked_at` 超 30 天 → 读时 expired 由 supply TTL 触发；物化时 `reviews._degrade_reason` 产出的是 `supply_invalid`（不是 `gate_expired`）；`gate_expired` 只对应 `gate_review.expires_at` 到期（F-03）。

## 5. M-01…M-12 可执行性（用现有导入/门槛 API）

> 前提：匹配函数本批不实现（稿 L31/L86），矩阵按"实现批纯读函数"断言；下列判断基于**现有导入/门槛/复核 API 按现步骤能否产生期望**。

| # | 现步骤能否产生期望 | 结论 | 问题/依据 |
| --- | --- | --- | --- |
| M-01 | 部分 | **期望与 §2 判级矛盾** | 稿 §2 判级：用途=仅提示、内容版本=半可判定（无货源指纹/等价字段）、交付=半可判定、适用条件=部分可判定；M-01 却期望"四维均有结构化依据（用途仍 hint_only）"→ 按 §2 自身规则应为 `needs_review`。另 `current_g2_supply_id=None` 与 `gaps 含 g2_not_verified`、候选 `pending` ✓（`state.py:198-200`） |
| M-02 | 是（G2 422、零写入） | **可执行，但 reasons 依赖未定义规则** | G2 准入 `unknown` → 422（`gates.py:170-176`）；失败请求不落库（`_write` 事务封装 `routes.py:107`）；`name_only_similarity` 规则未定义（F-06） |
| M-03 | 是（G2 422；许可字段不被改写） | **可执行，但 `self_claim_only` 规则未定义** | 同 F-06；"自称可转售"需精确关键词表 |
| M-04 | **否（按现步骤）** | **需加前置** | PATCH `status='invalid'` 会 `add_review(supply_invalid, blocking=1)`（`supplies.py:117-119`）→ 候选 `stale` ✓；但 `expired` 降级行只在**当前 G2/cost 行已 verified** 时追加（`gates.py:39-44`），M-04 步骤未先核验 → 期望落空（F-02） |
| M-05 | **否（按现步骤）** | **需加前置** | `license_changed` 降级/复核只在 `supply_distribution` 当前行为 verified 时产生（`supplies.py:113-116` + `gates.py:39-44`）；未核验时仅更新 `supply_offer`。需先做 G2 核验 |
| M-06 | **否** | **期望不实** | ①`cost_changed` 降级只在 `cost` 门槛已 verified 时产生（同上）；②**"情景 contribution 随新价变化（既有行为）"不成立**：`scenario.py` 完全不读 `supply_offer.unit_price_minor`，情景金额只来自 `cost_item`（`scenario.py:85-127`）；`PATCH /api/supplies/{id}` 改价只更新 `supply_offer` 并触发降级（`supplies.py:93,110-112`），**不改 `cost_item`** → contribution 不变（F-01） |
| M-07 | **否（按现期望）** | **kind 期望错误 + 需加前置** | ①需先有 verified G2 行，`effective_gate_status` 才会因 supply TTL 报 expired（`state.py:160-178`）；②`POST /runs/recompute` 对"`last_checked_at` 超 30 天"物化的是 **`supply_invalid`** 复核（`reviews.py:79-80`），**不是 `gate_expired`**（后者对应 `gate_review.expires_at` 到期，`reviews.py:91-92`）；M-07 期望"物化 `gate_expired` 复核"与触发条件不符（F-03） |
| M-08 | 是 | **可执行** | 无货源 → `no_supply_rows`；候选 `pending`（`state.py:198-200`）；"不写无需求" ✓ |
| M-09 | 是（需 import 生成条款证据） | **可执行，注意证据来源** | G2 核验成功需条款证据：导入时若提供 `supply_evidence_excerpt` 会创建 `supply_distribution` 证据并绑定 `license_evidence_id`（`importer.py:673-693`）；G2 通过后 `current_gate_supply` 取最新 seq（`state.py:31-35,123-132`），情景 `selected_supply_id` 取该货源（`gates.py:75-88`）✓；"另一项 needs_review"依赖 H1 规则（F-06） |
| M-10 | **步骤含糊** | **需明确写入方式与比较基准** | 若 `POST gates/platform_policy` 以 `verified` 尝试且版本不一致 → admission 422（`gates.py:233-240`）**不落行**，匹配读不到 v2；只有写 `status='unverified'` 行（`gates.py:316-326` 非 verified 不做准入校验）才可被匹配读到；且 §4.5 比较基准"当前 G2 货源"在无 G2 时未定义（需 fallback）→ F-07 |
| M-11 | 是（设计层面） | **可执行** | GET 详情零写：`routes.py:266-330` 只查询 + `state.recompute`（纯函数）+ `effective_gate_status`（只读）；CONTRACT L351 一致；匹配纯函数零写（实现批断言）；但匹配未实现，本 case 仅实现批可跑 |
| M-12 | 是 | **可执行（引用值已核）** | "833/−683"来自 `S4_SCENARIO_SPEC.md:137`（#5：`recurring_per_order=833`、`net=−683`）；默认路径 `#2` `net=null`；A/B 货源 fallback 用例 `#16`（`:148`）✓；S4 用例"已验收"表述沿用即可 |

## 6. 越界检查

| 检查项 | 结论 | 依据 |
| --- | --- | --- |
| 新表/列/迁移 | **无**（稿 L3 明示；§3 建议实现批新增 `app/core/matching.py` 模块，属实现批范围并已声明） | 稿 L3、L31、L37、L108 |
| 新端点/CLI/定时器 | **无**；如需展示只能扩既有 GET 读路径且需策划确认（L37） | 稿 L37、L108 |
| 新依赖 | **无** | 稿 L3 |
| 自动核验/改门槛 | **无主张**；§4/§6 明确"匹配≠核验、不改 G2/成本/状态" | 稿 L42-L48、L72-L76 |
| 夸大表述 | **基本无**；§9 明确"不宣称 S4 完成、不宣称匹配可用" | 稿 L103-L108；**但** §8 M-01/M-06 的期望与代码实际不符（属期望错误而非越界）；§3 L38"如需排序"与"排序属 S4-B3/情景设计排除排序"边界略混（建议注明排序不在本设计范围） |

## 7. 缺项 / 歧义 / 风险

| 编号 | 严重度 | 问题 | 位置 | 方向 |
| --- | --- | --- | --- | --- |
| F-01 | **阻断** | M-06"情景 contribution 随新价变化"不成立：`scenario.py` 不读 `supply_offer.unit_price_minor`，改价只降级不改 `cost_item`/contribution | §8 M-06 | 期望改为"contribution 不变；仅 cost 门槛降级（若已核验）+ `cost_changed` 复核" |
| F-02 | **阻断** | M-04/M-05/M-06/M-07 缺"先核验 G2（M-06 另需 G3）"前置；未核验时不会产生降级行/复核/expired | §8 M-04…M-07 | 各 case 先 `POST gates/supply_distribution`（M-06 再 `POST gates/cost`），并注明降级只在 verified 时发生 |
| F-03 | **阻断** | M-07 期望 kind 错：`last_checked_at` 超 30 天物化的是 `supply_invalid`（`reviews.py:79-80`），不是 `gate_expired`；两套 TTL 未区分 | §8 M-07、§5.2 行 4 | 拆成两个 case：supply TTL→`supply_invalid`；`gate_review.expires_at` 到期→`gate_expired` |
| F-04 | **阻断** | §4.2/§6 把情景选择说成"只认 `current_gate_supply`"；实际用 `gates.selected_supply_id`（含唯一货源数值 fallback），且该函数定义在 `gates.py` 而非 `scenario.py`（稿 L5 归属错） | §4.2、§6、L5 | 精确引用 `selected_supply_id`（`gates.py:75-88`）+ §5.5-7 fallback；`current_gate_supply` 语义改为"最新 seq 行货源 + 有效状态" |
| F-05 | **阻断** | M-01 期望"四维均有结构化依据"与 §2 自身判级（内容版本仅半可判定/无等价字段）矛盾 | §8 M-01 vs §2 | 期望改为 `needs_review`+对应 gaps，或说明"结构化依据"的确切口径 |
| F-06 | **阻断** | H1 的"名称相似/自称可转售"无确定性判定规则；M-02/M-03 的 reasons 不可核验 | §5.1、M-02/M-03 | 给固定关键词表与"不做相似度"的口径，或把该维限定为人工复核提示（不产出特定 reason） |
| F-07 | 需修订 | M-10 写入方式与比较基准不明（verified 会 422 不落行；无 G2 时基准未定义） | §8 M-10、§4.5 | 明确用 `status='unverified'` 行 + 基准 fallback（当前 G2→唯一非 invalid→不比较并标 gap） |
| F-08 | 需修订 | §2"无结构化适用平台/地区/语言/尺寸条件列"与同表 G4 `applies_to_platform/applies_to_version` 冲突 | §2 表 L22 | 改为"supply_offer 无平台/地区/语言/尺寸列；平台/版本仅在 `gate_review` 门槛行存在" |
| F-09 | 需修订 | §5.2 表把降级/复核写成必然，未写"仅当前行 verified 时发生" | §5.2 | 每行补前置条件 |
| F-10 | 需修订 | §4.3 漏"条款证据类型必须 `supply_distribution`" | §4.3 | 补 `evidence_type` 要求（`gates.py:186-187`） |
| F-11 | 需修订 | §3 L33 `excluded` 的"G2 所选外"语义不清（未选中≠禁用） | §3 | 只保留失效/超期；"非当前选择"单独字段表达 |
| F-12 | 建议 | §3 L38 "如需排序"与 S4-B3/情景设计排除排序的边界 | §3、§6 | 注明排序不在本设计范围 |
| F-13 | 建议 | M-09 依赖导入生成的条款证据；M-12 建议引 S4 矩阵行号（#5/#2/#16） | §8 | 补引用 |

## 8. 结论

**需修订**：设计的**边界与只读约束是扎实的**——§3/§4/§6 明确"匹配≠核验、不写四表、不改 G2/成本/状态/金额"，与 CONTRACT §3.3 读时纯计算一致；字段核对**未发现虚构**；H2"复用既有机制、不新增 kind"**成立**（枚举 `0001_init.sql:222` 全覆盖）。但 §8 矩阵存在 **3 个阻断级期望/前置错误**（M-06 情景数值不实、M-04…M-07 缺先核验前置、M-07 复核 kind 错）+ §4.2/§6 机制引用不精确 + M-01 与 §2 自相矛盾 + H1 规则不可判定。

在 M-01…M-08 修订前，**不建议进入匹配实现批**；修订后本设计的只读边界可直接作为实现批约束。

## 9. 最小修订项

| 编号 | 修订项 | 对应发现 |
| --- | --- | --- |
| M-01 | §4.2/§6 精确引用 `gates.selected_supply_id`（含 §5.5-7 唯一货源数值 fallback）与 `current_gate_supply` 语义（最新 seq 行 + 有效状态）；L5 归属改到 `gates.py` | F-04 |
| M-02 | M-04/M-05/M-06/M-07 增加"先核验 G2（M-06 另加 G3）"前置；M-06 期望改为 contribution 不变 + cost 降级；M-07 拆成 supply TTL→`supply_invalid` 与 gate `expires_at`→`gate_expired` 两个 case | F-01/F-02/F-03/F-09 |
| M-03 | M-01 期望与 §2 判级对齐（`needs_review` + 对应 gaps），明确"结构化依据"口径 | F-05 |
| M-04 | H1 给确定性判定规则（固定关键词表、不做相似度），并把 M-02/M-03 的 reasons 依据写清 | F-06 |
| M-05 | M-10 明确"写 `status='unverified'` 的 G4 行"与比较基准 fallback | F-07 |
| M-06 | §2 缺口表述修正（平台/版本在 `gate_review`，`supply_offer` 无平台/地区/语言/尺寸列） | F-08 |
| M-07 | §4.3 补证据类型 `supply_distribution`；§5.2 每行补"仅当前行 verified 时发生" | F-10/F-09 |
| M-08 | §3 `excluded` 语义拆分；L38 排序归 S4-B3；M-12 补 S4 矩阵行号引用 | F-11/F-12/F-13 |

## 10. 声明与限制

- **未修改**被评审文件（`S4_MATCHING_SPEC.md` 哈希评审前后未变，见 §0.2）与任何源码/测试/迁移/契约/台账。
- **未联网、未启动应用、未运行任何测试**（无 unittest/pytest/Flask/HTTP 调用）；本评审不是实测证据，M 矩阵的结论均为"按现步骤静态推演"。
- 只读复算了 §0.2 的 11 个文件 sha256，未做其它写入。
- 行号以评审时点文件为准；若被评审稿或代码修订需按新哈希重核。
- 本会话**无 `skill` 工具**，未加载任何技能；未核实的推断已在正文标注（如 `_write` 事务封装只按 `routes.py:107` 的命名与调用方式判断失败回滚，未逐行读实现）。
