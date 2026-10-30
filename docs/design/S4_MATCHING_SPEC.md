# S4-B1 离线货源匹配设计（设计稿：未实现、未联网、未接入）

> 状态：**设计稿 / 未实现**。本文不新增表/列/迁移/端点/CLI/定时器/依赖，不改 `app/**`、`tests/**`、契约、台账与业务库；不改既有门槛（G1–G4）、情景（S4 摊销/归一）与状态派生语义。
> 边界声明：匹配只回答"**货源是否适配该需求**"，不改变任何金额与 `net` 计算；「匹配可为适配」**不等于**任何门槛通过（§4）。S4 情景设计（[S4_SCENARIO_SPEC.md](<S4_SCENARIO_SPEC.md>)）明确排除"排序/匹配大包"；**排序/权重属 S4-B3，不在本设计范围**（§6）。
> 本版为**修订 v2**：按独立评审 [S4_MATCHING_REVIEW.md](../validation/S4_MATCHING_REVIEW.md)（159 行，结论「需修订」，6 项阻断）的 F-01…F-13 与 M-01…M-08 逐条修订；F→修改位置见 §10，修订历史见 §11。评审行号对应 v1（108 行），本文行号以本文件为准。
> 依据（只读已阅，评审已复算哈希）：[CONTRACT.md](<CONTRACT.md>) §3.3 状态派生与四门槛（`:340–363`）、§3.4 失效来源与降级（`:365–383`）、§3.5 准入（`:385–398`）、§4.5 身份/强键、§4.7 导入样例定位（`:538–547`）、§5.5 情景口径 · `app/core/gates.py`（`GATE_TTL_DAYS :14`；`gate_expires_at :64–72`；**`selected_supply_id :75–88`（唯一定义处）**；`append_downgrade :39–44`（仅当前行 `verified` 才降级）；G2 准入含证据类型 `:159–187`（`:186–187` 要求 `evidence_type='supply_distribution'`）；G4 版本 `:233–240`；非 `verified` 行不做准入校验）· `app/core/state.py`（**`SUPPLY_TTL_DAYS=30 :12`**；`_supply_invalid :45–56`；`_follows_current_g2 :147–154`；`effective_gate_status :158–178`；`recompute :181–210`；`current_gate_supply :123–132`=最新 seq 行的 `supply_offer_id` + 有效状态）· `app/core/scenario.py`（`:13` 导入 `selected_supply_id`；`:81–94` 成本只取该货源，`sale_price` 例外，无货源时普通行计入；`:85–127` **金额只来自 `cost_item`，不读 `supply_offer.unit_price_minor`**）· `app/core/supplies.py`（`price_changed :93`/`version_changed :94`/`clause_changed :95–99`/`invalidated :100`；降级与 `add_review :110–123`）· `app/core/reviews.py`（`_degrade_reason :66–92`：`last_checked_at` 超 30 天 ⇒ **`supply_invalid`**「所选货源超过 30 天未复核（TTL）」`:79–80`；`gate_review.expires_at` 到期 ⇒ `gate_expired` `:91–92`）· `0001_init.sql`（`review_item.kind` 枚举 7 值 `:222`）· [S3_OFFLINE_WIRING_ACCEPTANCE.md](../validation/S3_OFFLINE_WIRING_ACCEPTANCE.md) 与 [S3_PUBLIC_PATH_COMPATIBILITY.md](../validation/S3_PUBLIC_PATH_COMPATIBILITY.md)（离线接线已冻结、真实链路未接通）。
> 技能：本会话**未暴露 `skill` 工具**，如实标注未加载；无新依赖、无费用。

## 1. 目标与不做什么

- **目标**：为"需求候选 ↔ 货源"给出**只读、可解释、不写库**的适配判断，供人工挑选货源与安排复核；明确每维的可判定依据与缺口。
- **不做**：自动切换/改写 G2 所选货源、自动核验任何门槛、写入匹配分数/匹配表、替代人工复核、改变情景金额、把匹配结果当证据、把"无货源"写成"无需求"、做排序/权重（S4-B3）。

## 2. 匹配维度：可判定字段与缺口（不假设不存在的列）

判级：**可判定**＝有结构化字段且规则确定；**半可判定**＝字段存在但为自由文本，只能相等/枚举比对；**仅提示**＝只能人工阅读；**缺口**＝现有模型无对应字段（**如实列出，不新增列**）。

| 维度 | 现有可判定字段 | 判级 | 缺口 |
| --- | --- | --- | --- |
| 用途（做什么用） | `candidate.category`/`use_case`（自由文本）；`demand_signal.excerpt`/`signal_kind`；`supply_offer.license_summary`/`license_scope_note`（自由文本） | **仅提示** | 无受控词表/标签（CONTRACT §9 `category` 自由文本、分类词表未定）；无"用途—素材适用用途"结构化映射 |
| 内容版本（是否同一版本） | 需求侧 `demand_signal.content_hash`/`version_no`/`superseded_by`；货源侧 `supply_offer.format_version`（`TEXT NOT NULL DEFAULT ''`，自由文本）/`native_id` | **半可判定** | 无货源内容指纹、无"货源内容↔需求内容"等价字段、无版本血缘；`format_version` 只可判"相等"，不等不能断言"不同" |
| 交付形式（怎样交付） | `candidate.delivery_form`（自由文本）；`supply_offer.downloadable`（yes/no/unknown）、`origin_type`（6 值枚举） | **半可判定** | 无结构化交付形式枚举（文件/链接/服务/定制…）；无单次/多次交付约束 |
| 适用条件（许可/范围/限制） | G2 三项 `commercial_allowed`/`redistribute_allowed`/`resale_allowed` + `sample_checked`/`sample_note`；`license_scope_note`/`license_evidence_url`/`license_summary`；`price_valid_until`；`status`/`last_checked_at`。**平台/版本只在门槛行**：`gate_review.applies_to_platform`/`applies_to_version`（自由文本） | **部分可判定** | `supply_offer` **没有**平台/地区/语言/尺寸列（平台与版本仅存在于 `gate_review` 门槛行，且为自由文本）；**不存在 `supply_verified_at` 列**（最接近为 `last_checked_at` 与 G2 的 `verified_at`/`expires_at`） |

**判定规则（纯函数式，无写库）**：
- 维度"适配"仅当该维有结构化字段且规则命中（如 `format_version` 与 G4 `applies_to_version` 相等或 `*`；三项许可均 `yes` 且 `sample_checked≠none`）。
- 只能靠自由文本的维度标 **`hint_only`**，整体结果降级为 `needs_review`，**不得**升级为 `adaptable`。
- 缺口维度一律标 `gap`（不是"通过"、也不是"拒绝"），并列出缺什么字段。

## 3. 匹配结果的表示（只读、不落库）

- 建议实现为**纯读函数**（实现批新增 `app/core/matching.py::match_supplies(conn, candidate_id) -> dict`，本批**不实现**）：返回
  - `candidate_id`、`current_g2_supply_id`（来自 `state.current_gate_supply`：最新 `seq` 行的货源 id；**可能为过期货源**）、`is_current_g2_valid`（有效 verified 与否）；
  - `items[]`：每货源 `{supply_offer_id, level, is_selected_by_g2, dims{用途/内容版本/交付形式/适用条件}, reasons[], gaps[], gate_refs}`；
    `level ∈ {adaptable, needs_review, not_applicable, excluded}`，其中 **`excluded` 仅用于"失效/超期"**（`status='invalid'` 或 supply TTL 超 30 天）；**"非当前 G2 选择"用独立字段 `is_selected_by_g2=false` 表达，不算 `excluded`**（F-11）。
  - `gaps[]`（全局）：`no_supply_rows` / `license_unknown` / `scope_text_only` / `format_unknown` / `no_cost_binding_to_g2` / `g2_not_verified` / `dims_text_only` / `g4_baseline_undefined`（无 G2 且无唯一非 invalid 货源时，版本比较无基准）；
  - `display_note`：固定口径"**匹配结果仅供挑选与复核，不构成门槛核验或证据**"。
- **不落库**：不写 `supply_offer`/`gate_review`/`review_item`/`candidate` 任何字段；GET 类读取零副作用（沿用 §3.3 读时纯计算）。
- **不新增表/列/端点**：本批交付 = 设计；实现批若需展示，只能走既有 `GET /api/candidates/{id}` 的读路径扩展（需策划者另行确认公共接口变更）或由调用方直接调用纯函数。
- **排序**：本设计**不做排序/权重/分数**（属 S4-B3）；如需稳定展示次序，仅按既有可解释字段（如 `is_selected_by_g2`、`status`、`last_checked_at`）确定性排序，且不得作为证据。

## 4. 与四项门槛及当前有效 G2 的关系

1. **匹配 ≠ 核验**：匹配**从不**写 `gate_review`、**从不**置 `verified`、**从不**改变 `candidate.status`（状态只由 `state.apply_status`/`recompute` 按 §3.3 派生）；`review_item` 也不由匹配创建（§5）。
2. **情景的货源选择机制（F-04 更正）**：情景与成本使用的是 **`gates.selected_supply_id`**（唯一定义 `gates.py:75–88`，由 `scenario.py:13` 导入），规则为：
   - 有**有效 verified G2** → 返回 G2 当前所选货源；
   - 否则（无有效 G2）→ 若候选**恰有唯一非 `invalid` 货源**，返回该货源，**仅供纯数值估算**（CONTRACT §5.5-7 / `S4_SCENARIO_SPEC.md:112`），**绝不升级任何门槛**；否则返回 `None`（成本按"无货源时的普通行"处理，`sale_price` 例外）。
   `state.current_gate_supply` 的语义**不是**"有效 verified 的货源"，而是**最新 `seq` 门槛行的 `supply_offer_id` + 该门槛的有效状态**（可能已 `expired`）。
3. **G2 准入条件**（§3.5，`gates.py:159–187`）：指定 `supply_offer_id`（属于本候选、未失效）；三项许可均为 `yes`（`no`/`unknown` 不自动通过，例外路径需结构化 `license_scope_note` + 条款摘录证据且保持待复核）；`sample_checked≠none` 且 `sample_note` 记录范围/结果/未核验部分；**引用证据类型必须为 `evidence_type='supply_distribution'`**（`gates.py:186–187`；F-10），由 `license_evidence_id` 或本次 `evidence_id` 提供。匹配不得替代其中任一项。
4. **G3**：成本须绑定当前有效 G2 货源（`cost_item.supply_offer_id`，`state.usable_base_cost_rows`/`gates._check_cost` 的供给过滤）；匹配**不**改成本、不补成本；无绑定 → `no_cost_binding_to_g2` 缺口，G3 仍不成立。
5. **G4**：`applies_to_version` 必须等于当前有效 G2 货源的 `format_version` 或 `*`（`gates.py:233–240`）；**比较基准**：有有效 G2 → 当前 G2 货源；无有效 G2 → 唯一非 `invalid` 货源（与 `selected_supply_id` fallback 一致，仅作提示）；两者皆无 → `g4_baseline_undefined` 缺口，**不比较**、不判通过。
6. **G1**：与货源无关（需求证据），匹配不触碰。
7. **状态派生**：匹配读取 `effective_gate_status` 的结果做**解释**（如 G2 为 `expired` ⇒ 该货源不进入 `adaptable`），但不参与派生；物化仍只由既有写入口与 `recompute` 触发。

## 5. 两条硬约束（触发条件与复用方式）

### 5.1 硬约束 H1：仅名称相似 / 供应商自称可转售 ⇒ 不升级核验

- **"名称相似"不做机器判定（F-06）**：本设计**不定义相似度算法/阈值，也不产出 `name_only_similarity` reason**；`provider_name`/标题只作为 `display_note` 的人工阅读提示，所在维度一律 `hint_only`。**不得**把名称比较结果写成"适配"或证据。
- **"供应商自称可转售"采用固定关键词表**（确定性、可核验）：仅在 `supply_offer.license_summary`/`license_scope_note`/`check_note` 三个既有自由文本字段中、按固定词表（如 `可转售`/`可商用`/`可二次分发`/`可转授权`/`授权齐全`；词表本身在实现批冻结并写进常量，**不做模糊匹配、不做相似度**）命中文命中，且**同时**满足 `resale_allowed != 'yes'` 或 `commercial_allowed != 'yes'` 时，才产出 `reasons=[self_claim_only]`；否则不产出该 reason。
- **处理**：该维 `hint_only`、整体 `needs_review`；**不改**三项许可字段、**不改** `sample_checked`、**不置** G2 `verified`、**不写**任何表。人工须按 §3.5 补齐结构化字段与证据后自行核验，匹配不代办。
- **当前不可机器验证项**：用途维的"是否真的适配"、名称提示、以及未来受控词表（词表未定 ⇒ M-02/M-03 只能靠上述固定词表/人工输入，不得称机器可判定）。

### 5.2 硬约束 H2：货源失效 / 许可变化 ⇒ 触发复核（复用既有机制，不新增 kind）

**前置（F-09）**：降级核验行与对应复核**仅当该门槛当前最新行 `status='verified'`** 时才会追加（`gates.append_downgrade :39–44`；`reviews.py:66–70`）；未核验时只更新 `supply_offer` 本身（`supplies.py:110–123`）。

**两套 TTL 必须分开（F-03）**：
| TTL | 值 | 依据 | 触发/产出的 kind |
| --- | --- | --- | --- |
| **门槛 TTL**（G1–G4） | `demand 90 / supply_distribution 30 / cost 30 / platform_policy 180` 天 | `gates.py:14`（`GATE_TTL_DAYS`）、`gate_expires_at :64–72`（`min(证据 expires_at ∪ verified_at+TTL)`） | `gate_review.expires_at` 到期 ⇒ 读时 `expired`；物化 **`gate_expired`**（`reviews.py:91–92`） |
| **货源 TTL** | `last_checked_at` 超 **30 天** | `state.py:12`（`SUPPLY_TTL_DAYS=30`）、`state.py:45–56`（`_supply_invalid`） | 读时 `expired`；物化 **`supply_invalid`**（`reviews.py:79–80`，文案「所选货源超过 30 天未复核（TTL）」），**不是 `gate_expired`** |

| 触发（既有写入口） | 既有动作（`supplies.py:100–124` + §3.4；**仅当前行 verified 时**） | 匹配侧只读反映 |
| --- | --- | --- |
| `PATCH /api/supplies/{id}` 置 `status='invalid'` | `add_review(kind='supply_invalid', ref_gate='supply_distribution', blocking=1)`（**该复核无条件添加**，不受 verified 前置限制）；`supply_distribution`/`cost` 的 `expired` 降级行仅在各自当前行 `verified` 时追加 | 该项 `level='excluded'`，`reasons=[supply_invalid]`；不复活 |
| 许可由 `yes` 变 `no`/`unknown`，或 `format_version`/许可依据变化 | 仅当 `supply_distribution` 当前行 verified 时：`license_changed` 降级 + 复核 | 该维 `not_applicable`/`gap`，`reasons=[license_changed]` |
| 价格变化 | 仅当 `cost` 当前行 verified 时：`cost_changed` 降级 + 复核 | `reasons=[cost_changed]`（金额影响由成本项负责，见 §6） |
| supply TTL 超 30 天 | 读时 `expired`；`recompute` 物化 **`supply_invalid`**（「所选货源超过 30 天未复核（TTL）」） | `level='excluded'`，`reasons=[supply_ttl_expired]`；提示重新核验 |
| 门槛 `expires_at` 到期 | 读时 `expired`；`recompute` 物化 **`gate_expired`** | 标 `reasons=[gate_expired]`（不是 supply_invalid） |
| 证据失效 | 既有 `evidence_expired` 复核（§3.4） | 标缺口；匹配不写 |

- **不新增 `review_item.kind`**：以上全部复用既有 7 值枚举内的 kind（`dup_suspect`/`gate_expired`/`supply_invalid`/`evidence_expired`/`license_changed`/`cost_changed`/`import_warning`，`0001_init.sql:222`）。若未来需要"匹配疑似"类复核，须在实现批申请新枚举 + 新迁移（`0001/0002` 不可改），本设计**不采用**。
- 匹配**不创建**复核项：复核只能由既有写入口或 `recompute` 物化（§3.3 读时纯计算）。

## 6. 与 S4 情景（摊销/归一/收益）的边界

- **匹配**决定"货源是否适配"；**情景**决定"金额与净值"。情景的**货源选择**用 `gates.selected_supply_id`（§4.2：有效 G2 → G2 货源；否则唯一非 invalid 货源作纯数值 fallback；再否则无），**金额只来自 `cost_item`**（`scenario.py:85–127`），**不读 `supply_offer.unit_price_minor`**。
- 因此：改 `supply_offer` 价格**不改变** `contribution`/`net`；要改变情景金额必须改**成本行**（`cost_item`，经 `POST /cost-items` 或 `supersede`，并触发相应降级）。匹配不介入金额。
- 匹配**不**改 `selected_supply_id`、**不**改 `contribution/net/complete`、**不**触发 `net` 计算；若用户依据匹配建议换货源，必须**先重新核验 G2**（新 `seq`），之后情景按新 G2 货源计算（既有行为），匹配本身不介入。
- **排序/权重不在本设计/本节范围**（S4-B3）；情景设计排除排序/匹配（`S4_SCENARIO_SPEC.md`）。
- 反向边界：情景可算（`complete=true`）**不代表**货源适配或门槛通过（§4.7 定位说明沿用）。

## 7. 不可匹配 / 信息不足时的解释口径

- 输出固定句式：**"未找到可确证的适配货源"** + 缺口枚举（`no_supply_rows`/`license_unknown`/`scope_text_only`/`format_unknown`/`dims_text_only`/`no_cost_binding_to_g2`/`g2_not_verified`/`g4_baseline_undefined`）+ 下一步人工动作（补证/重新核验/补成本绑定）。
- **禁止**：把"无适配货源"写成"市场无需求/零需求"；不得把匹配缺口写成事实否定；不得用匹配结论替代覆盖统计（`search_coverage` 未建表，不涉及）。
- 未知≠0、缺口≠拒绝：区分"未知/缺字段"（`gap`）、"明确不匹配"（`not_applicable`，需结构化反证如 `resale_allowed='no'`）、"失效/超期"（`excluded`）、"非当前选择"（`is_selected_by_g2=false`，不是排除）。

## 8. 离线最小验收矩阵（现有 CSV/JSON 导入 + 既有门槛 API，可执行；本批未执行）

> 匹配函数本批不实现，矩阵按"实现批纯读函数"断言；下列"前置"指按现有 API 先完成的写操作。每个 case 前后对四表做全行快照，验证匹配侧零写入。

| # | case | 步骤 | 期望值 |
| --- | --- | --- | --- |
| M-01 | 完整正例（§4.7 38 列 CSV，含货源与 10 项成本） | 导入 → 读取匹配结果 | 依 §2 判级：用途 `hint_only`、内容版本/交付 `半可判定`、适用条件 `部分可判定` ⇒ 整体 **`needs_review`**（**不是** `adaptable`）；`current_g2_supply_id=None`、`is_current_g2_valid=false`；`gaps` 含 `g2_not_verified`、`dims_text_only`；候选 `pending` |
| M-02 | 许可未知（名称仅供参考） | 导入（`supply_commercial_allowed='unknown'`）→ 匹配 → 尝试 G2 | 匹配 `needs_review`，`gaps` 含 `license_unknown`；**不产出** `name_only_similarity`（H1 明定不做相似度）；G2 → `422`；零写入 |
| M-03 | 供应商自称可转售（固定词表命中） | 导入：`license_summary` 含「可转售」但 `resale_allowed='unknown'` → 匹配 → 尝试 G2 | 匹配 `needs_review`，`reasons=[self_claim_only]`（关键词表命中且许可非 yes）；三项许可字段未被改写；G2 `422`；不升级核验 |
| M-04 | 货源失效（**前置：先核验 G2**） | 导入 → 核验 G2（`supply_distribution` verified）→ `PATCH /supplies/{id}` 置 `invalid` → 匹配 | 既有 `supply_invalid` 复核（blocking）+ `supply_distribution`/`cost` 各追加 `expired` 降级行（因已 verified）；匹配该项 `excluded`、`reasons=[supply_invalid]`；候选状态派生 `stale`；匹配零写入 |
| M-05 | 许可由允许变禁止（**前置：先核验 G2**） | 导入 → G2 verified → PATCH 许可 `no` → 匹配 | `license_changed` 降级 + 复核仅在 `supply_distribution` 当前行 verified 时出现；匹配该维 `not_applicable`、`reasons=[license_changed]` |
| M-06 | 价格变化（**前置：G2 与 G3 均已核验**） | 导入（成本绑定该货源）→ G2+G3 verified → PATCH 价格 → 匹配 → 读情景 | `cost_changed` 降级 + 复核（因 `cost` 已 verified）；**`contribution` 不变**（情景金额只来自 `cost_item`，PATCH 货源价不改成本行）；若要改金额须改成本项（另行 `POST /cost-items`/`supersede`，会再次触发降级） |
| M-07a | 货源 TTL 超 30 天（**前置：先核验 G2**） | 导入 → G2 verified → 夹具直改 `supply_offer.last_checked_at` 为 31 天前 → GET 详情/匹配 → `POST /runs/recompute` | 读时 G2 `expired`（`state.py:45–56`）；匹配 `excluded`、`reasons=[supply_ttl_expired]`；`recompute` 物化 **`supply_invalid`** 复核（`reviews.py:79–80` 文案「所选货源超过 30 天未复核（TTL）」），**不是 `gate_expired`** |
| M-07b | 门槛 TTL 到期（**前置：先核验 G2**） | 导入 → G2 verified → 夹具把该 `gate_review.expires_at` 置为已过期 → GET → `recompute` | 读时 `expired`；物化 **`gate_expired`**（`reviews.py:91–92`）；匹配 `reasons=[gate_expired]`，与 M-07a 的 kind 明确区分 |
| M-08 | 完全没有货源 | 仅需求行导入 → 匹配 | 输出"未找到可确证的适配货源" + `no_supply_rows`；候选 `pending`；**不写"无需求"**；零写入 |
| M-09 | 两个货源：一个 G2 已验证、一个名称更像 | 导入两货源（**含 `supply_evidence_excerpt` 以便导入生成 `supply_distribution` 证据**，`importer.py:673–693`）→ 核验 G2 → 匹配 | 匹配标 `current_g2_supply_id`=已核验者、`is_selected_by_g2=true`；另一项 `is_selected_by_g2=false` 且 `needs_review`（名称不作判定）；情景 `selected_supply_id` 仍为已核验者；匹配不改选择 |
| M-10 | `format_version` 与 G4 版本不一致（**写 unverified 行，不做 verified 冒烟**） | 导入货源 v1 → 通过 API 写入 `platform_policy` 行 `status='unverified'`、`applies_to_version='v2'`（非 verified 行不做准入校验）→ **先核验 G2** → 匹配 | 匹配标 `format_unknown`/版本不一致缺口（基准=当前 G2 货源）；若已 verified 则 G4 准入会 422 且不落行；**任何情况下不自动通过** |
| M-11 | 匹配零写入（含 GET 两次） | 任一 case 后连读两次匹配与候选详情 | 四表全行（含时间戳）前后一致；`gate_review`/`review_item` 零新增 |
| M-12 | S4 情景不退化 | 复用已验收 S4 用例：默认路径（`S4_SCENARIO_SPEC.md` 矩阵 **#2**，`net=null`）、显式假设 `quarterly=10001 + normalize + M=4`（**#5**：`recurring_per_order=833`、`net=−683`）、A/B 货源 fallback（**#16**） | 匹配功能**不影响** `net/complete/selected_supply_id`；三个用例期望与 `S4_SCENARIO_SPEC.md:137/:148` 一致 |

## 9. 未执行 / 未覆盖 / 待裁定

- **未执行**：本任务为设计稿，§8 全部未运行；匹配函数未实现、未接入任何读路径。
- **当前不可机器验证**：用途维"是否真的适配"、名称提示（H1 明定不做相似度）、受控词表相关判定（词表未定）；M-02/M-03 的 `self_claim_only` 依赖实现批冻结的固定关键词表（若词表未冻结则该 reason 不可核验，应在实现批先冻结）。
- **未覆盖**：受控词表/标签、结构化适用条件（平台/地区/语言/尺寸）、货源内容指纹与版本血缘、排序/权重（S4-B3）、发现型检索、`search_coverage`、界面、S5/S6。
- **待裁定**：① 匹配结果是否进入 `GET /api/candidates/{id}`（公共读接口扩展，需另行授权）；② 是否引入受控词表（涉契约与迁移）；③ 是否需要"匹配疑似"复核 kind（需新枚举+迁移，本设计不采用）；④ H1 固定关键词表的冻结清单（实现批前置）。
- **声明**：本稿**不宣称 S4 完成、不宣称匹配可用**；不新增网络权限/依赖/表/列/端点/CLI/定时器。

## 10. F→修改位置映射表（本轮修订）

| 编号 | 问题（评审） | 修改位置（本文件） | 修订要点（前 → 后） |
| --- | --- | --- | --- |
| F-01 | M-06"contribution 随新价变化"不成立 | §6、M-06 | 改为"`contribution` **不变**；情景金额只来自 `cost_item`；改金额须改成本行（另触发降级）" |
| F-02 | M-04…M-07 缺"先核验"前置 | M-04/M-05/M-06/M-07a/M-07b | 每 case 补"先核验 G2（M-06 另加 G3）"；标注降级仅当前行 verified 时发生 |
| F-03 | M-07 kind 错、两套 TTL 混写 | §5.2 TTL 表、M-07a/M-07b | 拆开 **gate TTL（90/30/30/180，`gates.py:14/64–72`）** 与 **supply TTL（30 天，`state.py:12/45–56`）**；supply TTL ⇒ `supply_invalid`，gate 到期 ⇒ `gate_expired` |
| F-04 | 情景选择机制引用不精确/归属错 | §4.2、§6、依据行 | 改为 **`gates.selected_supply_id`（`gates.py:75–88`，`scenario.py:13` 导入）**：有效 G2 → G2 货源；否则唯一非 invalid 货源**纯数值 fallback**（不升级门槛）；`current_gate_supply` = 最新 seq 行货源 + 有效状态（可能过期） |
| F-05 | M-01 与 §2 判级矛盾 | M-01 | 期望改为 **`needs_review`** + `gaps`（`g2_not_verified`/`dims_text_only`），去掉"四维均有结构化依据" |
| F-06 | H1 无可判定规则 | §5.1、M-02/M-03 | 明定**不做相似度**、不产出 `name_only_similarity`；"自称可转售"用**固定关键词表 + 许可非 yes** 确定性判定；用途维 `hint_only` |
| F-07 | M-10 写入方式/基准不明 | §4.5、M-10 | 写明用 **`status='unverified'` 的 G4 行**（非 verified 不做准入校验）；基准=当前 G2 → 唯一非 invalid → 皆无则 `g4_baseline_undefined` 不比较 |
| F-08 | §2 适用条件缺口与 G4 列冲突 | §2 表 | 改为"`supply_offer` 无平台/地区/语言/尺寸列；平台/版本仅在 `gate_review` 门槛行（自由文本）" |
| F-09 | 降级/复核写成必然 | §5.2 前置段+表头 | 补"**仅当前行 `status='verified'` 时**追加降级行与复核（`append_downgrade :39–44`；`reviews.py:66–70`）；`add_review('supply_invalid')` 例外（无条件）" |
| F-10 | G2 证据类型漏写 | §4.3 | 补 `evidence_type='supply_distribution'`（`gates.py:186–187`） |
| F-11 | `excluded` 语义混淆 | §3 | `excluded` 仅"失效/超期"；"非当前 G2 选择"用 `is_selected_by_g2=false` |
| F-12 | 排序边界 | §1/§3/§6 | 明写排序/权重属 S4-B3，不在本设计范围 |
| F-13 | M-09/M-12 依据 | M-09/M-12 | M-09 补"导入需提供 `supply_evidence_excerpt` 以生成条款证据（`importer.py:673–693`）"；M-12 补 S4 矩阵行号 #2/#5/#16 与 `S4_SCENARIO_SPEC.md:137/:148` |

## 11. 修订记录

- v1（提交 revision 2）：初版设计（四维匹配与缺口、只读结果表示、与门槛/G2 关系、H1/H2、情景边界、解释口径、M-01…M-12、未执行清单）。
- v2（本版，task-001c8e439806dddc93b14d60e667617d）：按独立评审 `S4_MATCHING_REVIEW.md`（F-01…F-13 与 M-01…M-08）逐条修订：情景选择改为 `gates.selected_supply_id`（含唯一货源 fallback）并更正归属；两套 TTL 分列；M-07 拆 07a/07b 并改正为 `supply_invalid`；M-06 改为 contribution 不变；M-01 对齐 §2 判级；H1 改为"不做相似度 + 固定关键词表"；适用条件缺口改为"平台/版本仅在门槛行"；G2 补证据类型；降级补 verified 前置；`excluded` 语义拆分；补排序边界说明与 S4 矩阵行号引用；新增 §10 F→修改位置映射表。全文仍标注设计稿/未实现。
