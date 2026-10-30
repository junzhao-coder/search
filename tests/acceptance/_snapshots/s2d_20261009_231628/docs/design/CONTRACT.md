# 数据与接口契约（S1-B v3）

> 状态：**已验收冻结（S2 实现依据）**——Flow 验收通过后正文规则不得改动；实现层与文字口径的差异另见 [S2 核心实现记录](<S2_CORE.md>) §6。
> 适用范围：S2 最小闭环所需的存储、导入、接口、状态与费用规则。`[S3]` 标记的字段提前冻结、实现随对应阶段。
> 上游基线：[产品定位与开发目标](<../../PRODUCT.md>) D01–D11；[开发总体计划](<../../DEVELOPMENT_PLAN.md>)（含附录 A 页面信息架构）；A 的[来源可行性报告](<../research/FEASIBILITY.md>)（Flow 已验收）；D 的 [S1 独立审阅](<../validation/S1_REVIEW.md>) 与 [修后复核](<../validation/S1_REVIEW_REVISED.md>)（Flow 已验收）。
> 各角色状态按 Flow 逐条区分：S0 文档、S1-A 来源、S1-B 契约、S1-C 计划/台账、S1-D 审阅均已验收，**S1 阶段验收通过**；S2 实现进度见 [S2 核心实现记录](<S2_CORE.md>)。
> 非目标：不写实现代码；不设计微服务、向量库、分布式队列、通用插件系统、前端构建链。
> 合成声明：全部 URL 使用 `example.com` 等示例域，示例数据均为合成样例（`data_origin=synthetic`），不代表真实市场样本、真实货源或真实价格。A 的研究标签（`license_reviewed` 等）与本文档无映射，不升级任何货源状态或门槛。
> v3 修订定位（本轮八组）：①→§1.1/§1.2/§2.2/§4.3/§4.5；②→§0.3/§2.2/§4.2/§4.4/§4.7；③→§1.5/§3.5-G3/§4.3/§5.5；④→§4.3/§5.5/S2-21·S4-07；⑤→§3.2/§3.3/§3.5；⑥→§1.8/§2.3-I4/§5.4/§5.5；⑦→§0.7/§1.9/§1.15/§5.3/§5.4；⑧→§6/§7/§9 与矩阵阶段。

## 0. 全局约定

### 0.1 标识

| 项 | 约定 |
| --- | --- |
| 主键 | `TEXT`，格式 `<prefix>_<16位小写hex>`（uuid4 前 16 位），模型生成 |
| 前缀 | `c` 候选 / `d` 需求信号 / `e` 证据 / `sp` 货源 / `ci` 成本项 / `g` 门槛核验 / `dr` 草稿 / `fb` 反馈 / `rv` 复核项 / `r` 运行 / `sc` 搜索覆盖 / `s` 来源 / `ib` 导入批次 / `ik` 幂等记录 |
| 原生标识 | 平台侧 `native_id`、原始 URL 一律原样保存；改写只发生在身份/指纹字段（`identity_key`、`url_norm`、`content_hash`、`title_norm_hash`） |
| 空值 | 业务"未知"一律用 NULL；`''` 只用于有明确默认值的文本字段（如 `format_version`） |

### 0.2 时间与日期

| 项 | 约定 |
| --- | --- |
| `*_at` | UTC ISO-8601 秒精度 `YYYY-MM-DDTHH:MM:SSZ`（TEXT，字典序可比较） |
| `*_date` | 本地日期 `YYYY-MM-DD`，应用时区 `APP_TZ` 默认 `Asia/Shanghai` |
| 互斥 | 同一语义的 `*_at` 与 `*_date` 至多一个非空（`published_at` / `published_date`） |
| 观察时间缺省 | 导入未提供 `observed_at` 时取导入时刻，并置 `observed_at_source='import_time'`；**无需求组的行没有 `observed_at` 落点 → 记 `warning`，不静默丢弃** |
| 拒绝 | 无时区的本地时间串、非 ISO 格式、无效日期 → 行级错误 |

### 0.3 金额、比率与符号规则

| 类别 | 列 | 规则 |
| --- | --- | --- |
| 输入金额（CHECK `>= 0`） | `cost_item.money_minor`、`cost_item.hourly_rate_minor`、`supply_offer.unit_price_minor`、`feedback.amount_minor`、`feedback.unit_price_minor`、`feedback.actual_hourly_rate_minor` | 必须非负；方向由 `role`/`kind`/`basis` 表达 |
| 派生值（允许为负） | `contribution_per_order_minor`、`net_per_order_minor`、`fixed_cost_gap_minor`、`feedback.predicted_net_per_order_minor` | 成本高于售价时为负，如实返回；**不设 `>=0` 约束** |
| 比率 | `*_bp` | 整数 `0..10000` |
| 时间量 | `cost_item.minutes`、`feedback.actual_minutes` | 整数 `0..1440` |

- 乘除取整只作用于非负输入：费率 `(base_minor*bp+5000)//10000`；人工 `(minutes*hourly_rate_minor+30)//60`（均 ½ 分向上）。派生负值只来自求和/差值。例：`9.90×500bp=50 分`；`15 分×3000 分/时=750 分`；`33.33×500bp=167 分`。
- 金额一律整数**分**（`_minor`），`currency` 单列，v1 仅 `CNY`。
- **情景派生值只计算、不落库**：`contribution_per_order_minor`、`net_per_order_minor`、`fixed_cost_gap_minor`、`recurring_monthly_total_minor` 由接口实时计算，不写入任何表。
- **反馈快照落库**：`feedback.predicted_net_per_order_minor` 是成交时写入的**持久快照**（有符号、写入后不可改，I4）。
- JSON：输出金额为 `{"amount_minor": -200, "currency": "CNY"}`；输入金额必须为字符串（十进制元，最多 2 位小数）或白名单内的 `*_minor` 整数键（§4.2）。JSON number 形式的非 `_minor` 金额一律拒绝；`true`/`false` 不是合法金额（bool 排除，§4.4 V5）。

### 0.4 未知与已知零（硬规则）

- 空 / `NULL` = 未知；`0` = 已知为零（**无支出必须显式录入 0**，系统不把"未提供"解释成"无支出"）。
- `cost_item` 允许全部值列为 NULL（该角色/basis 未知）；任何聚合、情景与门槛判定都不得把未知当 0，也不得把 0 当未知。
- 展示约定：未知 → "未知"；已知零 → "¥0.00"。

### 0.5 真实与合成

- `data_origin` ENUM(`real`,`synthetic`) 必填于可展示业务记录；子记录与所属候选一致。
- `synthetic` 记录 URL 只允许空值或示例域（`example.com`/`example.org`/`example.net`）；`real` 记录为 `http(s)` 绝对 URL 且不得用示例域。渠道名（如 `xianyu`）与 `data_origin` 独立：合成样例可用真实渠道名表达归属，URL 仍须为示例域。
- **去重、唯一键与合并均不得跨越 `data_origin`**（§2.2、§4.5、§5.3-13）。
- 每日摘要默认只统计 `real`；`include_synthetic=1` 才纳入合成数据。

### 0.6 外部内容

外部页面文本与模型输出只作为数据：转义渲染（Jinja2 默认 autoescape，禁止 `|safe` 与 innerHTML 注入）、不作为指令执行、不触发命令/文件执行/对外交易。全系统不存在发送、发布、付款、采购的代码路径（D06）。

### 0.7 幂等（持久化）

- 机制：表 `idempotency_key`（§1.15）。写接口可选 `client_ref`（≤64 字符），经请求体、query 或 `X-Client-Ref` 传入。
- `request_hash` 定义：`sha256(method + "\n" + 规范化路径与业务 query + "\n" + body 规范化)`；**文件导入用文件内容哈希 `sha256(file_content)`**；规范化**排除** `multipart` 随机 boundary 与 `client_ref` 本身。
- 同 `(scope, client_ref)`：hash 相同 → 返回已存响应并标 `deduplicated: true`（200）；不同 → `409 conflict`。
- 幂等记录与业务写入**同一事务**；业务回滚时幂等记录一并回滚。**失效重放不改任何时间戳、不重复建复核项**。
- 无 `client_ref` 的写接口采用**同值幂等**：相同输入重复提交返回原记录、`updated_at` 不变、不产生新行、不重复建复核项。
- `scope` 取值：`import`、`evidence`、`supply`、`cost_item`、`gate`、`draft`、`feedback`、`merge`、`override`、`backup`。

### 0.8 阶段标记

`[S2]` 本阶段必须实现（默认）；`[S3]` 自动读取与搜索覆盖；`[S4]` 摊销/归一/排序权重；`[S5]` 运行费用台账与预算保护、实际利润核算；`[S6]` 部署、备份恢复与回归。

## 1. 实体与字段

### 1.1 candidate 候选商品

| 字段 | 类型 | 约束与语义 |
| --- | --- | --- |
| `id` | TEXT PK | `c_...` |
| `title` | TEXT NOT NULL | 去空白后非空，≤300 字符 |
| `identity_key` | TEXT NOT NULL | 带类型与来源命名空间的候选身份（§4.5）：有需求组时沿用其需求身份 `n:...`/`u:...`；无需求组时 `t:<title_norm_hash>` |
| `identity_source` | TEXT NOT NULL | ENUM(`demand_native_id`,`demand_url`,`title`) |
| `category` / `use_case` / `delivery_form` / `notes` | TEXT NULL | 发现用自由文本；`notes` ≤2000 字符 |
| `status` | TEXT NOT NULL | ENUM(`pending`,`testable`,`explore`,`stale`,`archived`)，只由 §3.3 派生函数写入 |
| `status_reason` | TEXT NOT NULL | 机器可读前缀 + 说明 |
| `status_updated_at` | TEXT NOT NULL | `*_at` |
| `manual_override` | TEXT NOT NULL DEFAULT `none` | ENUM(`none`,`explore`,`archived`)，人工优先 |
| `override_reason` / `override_at` | TEXT NULL | override 非 `none` 时原因必填 |
| `title_norm_hash` | TEXT NOT NULL | 归一化标题指纹（§4.5） |
| `data_origin` | TEXT NOT NULL | ENUM(`real`,`synthetic`)，参与唯一键 |
| `import_batch_id` | TEXT NULL | FK `import_batch.id` |
| `created_at` / `updated_at` | TEXT NOT NULL | `*_at` |

### 1.2 demand_signal 需求信号

| 字段 | 类型 | 约束与语义 |
| --- | --- | --- |
| `id` / `candidate_id` / `source_id` | TEXT | `d_...`；FK candidate / FK source |
| `native_id` | TEXT NULL | 平台原生 ID，原样保存 |
| `url` | TEXT NOT NULL | 原始链接（需求组必填，故 `u:` 档恒可达） |
| `url_norm` | TEXT NOT NULL | 规范化 URL（§4.5 固定规则） |
| `identity_key` | TEXT NOT NULL | `n:<source_id>:<native_id>` 或 `u:<source_id>:<url_norm>`（§4.5） |
| `identity_source` | TEXT NOT NULL | ENUM(`demand_native_id`,`demand_url`) |
| `excerpt` | TEXT NOT NULL | 原文摘录，≤4000 字符，不改写原意 |
| `signal_kind` | TEXT NOT NULL | ENUM(`seller_promo`,`specific_ask`,`want_to_buy`,`business_record`,`other`) |
| `engagement_json` | TEXT NULL | 仅展示用互动数据；**不参与门槛与排序证据权重、不冒充成交** |
| `published_at` / `published_date` | TEXT NULL | 互斥 |
| `observed_at` / `observed_at_source` | TEXT NOT NULL | `*_at`；ENUM(`source`,`import_time`) |
| `original_author` | TEXT NULL | 原始作者/发布方 |
| `is_repost` | INTEGER NOT NULL DEFAULT 0 | 0/1 |
| `origin_group_key` / `origin_group_basis` | TEXT NULL | 转载归并键；basis ENUM(`detected`,`manual`) |
| `content_hash` | TEXT NOT NULL | 内容指纹——**仅用于同一身份的版本判定与跨对象疑似重复**，不参与身份 |
| `version_no` | INTEGER NOT NULL DEFAULT 1 | 同 `identity_key` 下递增 |
| `superseded_by` | TEXT NULL | FK `demand_signal.id`；非空表示已被新版本取代 |
| `first_seen_at` / `last_seen_at` | TEXT NOT NULL | `*_at` |
| `data_origin` / `import_batch_id` | TEXT | 与候选一致；可追溯 |

### 1.3 evidence 证据

追加写入；失效只写失效字段，不删行。

| 字段 | 类型 | 约束与语义 |
| --- | --- | --- |
| `id` / `candidate_id` | TEXT | `e_...`；FK candidate |
| `evidence_type` | TEXT NOT NULL | ENUM(`demand`,`supply_distribution`,`cost`,`platform_policy`,`validity`,`other`) |
| `demand_signal_id` | TEXT NULL | 需求信号派生证据 1:1（唯一） |
| `source_id` / `source_url` / `native_id` | TEXT | 出处；URL 必填 |
| `excerpt` | TEXT NOT NULL | 原文摘录，≤4000 字符；**无摘录不创建证据行**（§4.3 货源条款证据） |
| `fact_kind` | TEXT NOT NULL | ENUM(`fact`,`estimate`,`assumption`) |
| `observed_at` | TEXT NOT NULL | `*_at` |
| `expires_at` | TEXT NULL | 自身有效期；为空时门槛按 §3.2 默认 TTL 处理 |
| `invalidated_at` / `invalid_reason` | TEXT NULL | 失效；`invalidated_at` 非空时原因必填 |
| `supersedes_id` | TEXT NULL | FK `evidence.id` |
| `data_origin` / `import_batch_id` / `created_at` | TEXT | 与候选一致；可追溯 |

### 1.4 supply_offer 货源

| 字段 | 类型 | 约束与语义 |
| --- | --- | --- |
| `id` / `candidate_id` | TEXT | `sp_...`；FK candidate |
| `provider_name` / `provider_url` / `url_norm` | TEXT | 提供方、入口（原样）、规范化 URL |
| `native_id` | TEXT NULL | 提供方原生 ID（素材/商品 ID） |
| `origin_type` | TEXT NOT NULL | ENUM(`original_author`,`official`,`open_repo`,`distributor`,`self_made`,`unknown`) |
| `format_version` | TEXT NOT NULL DEFAULT `''` | 版本与格式；参与唯一键 |
| `unit_price_minor` | INTEGER NULL | 单价（分）：**0 = 免费（已知零）**、NULL = 未知 |
| `currency` / `price_basis` | TEXT | v1 仅 CNY；ENUM(`one_time`,`per_unit`,`subscription`) |
| `price_valid_until` | TEXT NULL | `*_date` |
| `license_summary` | TEXT NULL | 许可摘要（要点） |
| `license_scope_note` | TEXT NULL | **结构化适用说明**：本货源用于哪个用途/平台、限制是什么（G2 例外核验的唯一依据形态） |
| `license_evidence_url` | TEXT NULL | 条款证据链接；**即使缺摘录也保留** |
| `license_evidence_id` | TEXT NULL | FK `evidence.id`（`supply_distribution` 类）；仅当提供摘录时存在 |
| `downloadable` / `commercial_allowed` / `redistribute_allowed` / `resale_allowed` | TEXT NOT NULL | 各自 ENUM(`yes`,`no`,`unknown`)；`unknown` 是显式取值 |
| `sample_checked` / `sample_note` | TEXT NOT NULL DEFAULT `none` / TEXT NULL | ENUM(`none`,`partial`,`checked`)；非 `none` 时 `sample_note` 必填 |
| `status` | TEXT NOT NULL | ENUM(`candidate`,`verified`,`invalid`,`stale`)；不由研究标签映射 |
| `last_checked_at` / `check_note` | TEXT NULL | 最近核验 |
| `data_origin` / `created_at` / `updated_at` | TEXT NOT NULL | 与候选一致 |

### 1.5 cost_item 成本与售价项

追加写入：修正 = 新增行并置旧行 `is_active=0`、新行 `supersedes_id` 指向旧行。

| 字段 | 类型 | 约束与语义 |
| --- | --- | --- |
| `id` / `candidate_id` | TEXT | `ci_...`；FK candidate |
| `supply_offer_id` | TEXT NULL | FK `supply_offer.id`：本成本项依据哪个货源计价；计算只使用**选定货源 + 同一 `variant`**（§5.5） |
| `role` | TEXT NOT NULL | ENUM(`sale_price`,`procurement`,`platform_fee`,`payment_fee`,`acquisition`,`refund_reserve`,`manual_labor`,`other`) |
| `basis` | TEXT NOT NULL | ENUM(`per_order`,`one_time`,`recurring`)；`procurement` 可出现在三个 basis |
| `value_kind` | TEXT NULL | ENUM(`money`,`rate`,`minutes`) 或 NULL（=未知；值列须全空） |
| `money_minor` / `rate_bp` / `minutes` | INTEGER NULL | 至多一个非空；`rate` 仅 `basis='per_order'`；`minutes` 仅 `role='manual_labor'` |
| `hourly_rate_minor` | INTEGER NULL | 仅 `manual_labor`；NULL = 人工计价未知（≠0） |
| `period` | TEXT NULL | `basis='recurring'` 必填：ENUM(`monthly`,`yearly`,`quarterly`) |
| `variant` | TEXT NOT NULL DEFAULT `base` | 情景标签 |
| `currency` / `fact_kind` / `assumption_note` | TEXT | v1 仅 CNY；`fact_kind` ENUM(`fact`,`estimate`,`assumption`)；`estimate`/`assumption` 必须填 `assumption_note` |
| `source_evidence_id` / `valid_until` | TEXT NULL | 费用依据证据；有效期 |
| `is_active` / `supersedes_id` / `data_origin` / `created_at` | — | 0 = 已被取代；FK 自指；与候选一致；`*_at` |

### 1.6 gate_review 独立核验状态

追加写入；`current` = 同 `(candidate_id, gate)` 中 `seq` 最大者。

| 字段 | 类型 | 约束与语义 |
| --- | --- | --- |
| `id` / `candidate_id` | TEXT | `g_...`；FK candidate |
| `gate` | TEXT NOT NULL | ENUM(`demand`,`supply_distribution`,`cost`,`platform_policy`) |
| `seq` | INTEGER NOT NULL | 同候选同门槛内递增（从 1 开始），保证确定性"最新"并允许合法重核 |
| `status` | TEXT NOT NULL | ENUM(`unverified`,`verified`,`failed`,`expired`) |
| `evidence_id` | TEXT NULL | FK `evidence.id`；`verified` 时必填且属于同一候选、类型匹配 |
| `supply_offer_id` | TEXT NULL | `supply_distribution` 门槛必填：本次针对哪个货源 |
| `applies_to_platform` | TEXT NULL | `platform_policy` 门槛必填；首版固定 `xianyu` |
| `applies_to_version` | TEXT NULL | `platform_policy` 门槛必填：须与所选货源 `format_version` 一致，或 `*` |
| `verified_by` | TEXT NOT NULL | ENUM(`user`,`system_rule`)；`system_rule` 只能降级（§3.5） |
| `verified_at` / `expires_at` | TEXT | `*_at`；`expires_at` 见 §3.2 |
| `note` / `created_at` | TEXT | 核验说明；`*_at` |

### 1.7 draft 草稿

`id`(`dr_`)、`candidate_id`、`kind` ENUM(`listing_copy`,`reply`,`delivery_note`)、`method` ENUM(`template`,`model_assisted`)、`body`（未核验内容以显式占位标记，不写成保证）、`evidence_refs_json`（仅引用用证据 ID 数组）、`status` ENUM(`draft`,`final`)（无"已发送"状态）、`model_name`、`template_version`、`data_origin`、`created_at`/`updated_at`。

### 1.8 feedback 经营反馈（S2 只记录事件与快照）

| 字段 | 类型 | 约束与语义 |
| --- | --- | --- |
| `id` / `candidate_id` | TEXT | `fb_...`；FK candidate |
| `kind` | TEXT NOT NULL | ENUM(`inquiry`,`sale`,`refund`,`expense`,`manual_time`,`note`) |
| `order_ref` | TEXT NULL | 稳定业务关联键（如平台订单号）；退款/支出填了就必须与其关联的成交一致 |
| `related_feedback_id` | TEXT NULL | **退款必填**：指向同候选、同 `data_origin` 的 `kind='sale'` 行 |
| `occurred_at` | TEXT NOT NULL | `*_at` |
| `quantity` | INTEGER NULL | 数量；非空时必须是**正整数**（CHECK `> 0`） |
| `unit_price_minor` / `amount_minor` | INTEGER NULL | 单价/金额（分）；未知留 NULL |
| `currency` | TEXT NOT NULL DEFAULT `CNY` | v1 仅 CNY |
| `expense_kind` | TEXT NULL | `kind='expense'` 必填：ENUM(`procurement`,`platform`,`acquisition`,`run`,`other`) |
| `expense_basis` | TEXT NULL | `kind='expense'` 时：ENUM(`per_order`,`one_time`,`recurring`) |
| `refund_state` | TEXT NULL | `kind='refund'` 必填：ENUM(`pending`,`settled`) |
| `predicted_net_per_order_minor` / `predicted_snapshot_at` | INTEGER/TEXT NULL | **仅 `kind='sale'` 行、服务端生成**（落库快照，写入后不可改） |
| `actual_net_per_order_minor` / `actual_complete` | INTEGER NULL | **S2 只读、保持 NULL（未核算）**；计算与写入属 S5，且只写唯一 `sale` 行；客户端提交一律 `422 invalid_field` |
| `actual_minutes` / `actual_hourly_rate_minor` | INTEGER NULL | **仅 `kind='manual_time'` 可录入/更正**（`actual_minutes` 为该 kind 必填，`0..1440`）；其他 kind 传这两个字段一律 `422`；同事件同值提交幂等、不新增记录、不改时间戳 |
| `note` / `data_origin` / `created_at` | TEXT | 备注；与候选一致；`*_at` |

### 1.9 review_item 复核项

| 字段 | 类型 | 约束与语义 |
| --- | --- | --- |
| `id` | TEXT PK | `rv_...` |
| `kind` | TEXT NOT NULL | ENUM(`dup_suspect`,`gate_expired`,`supply_invalid`,`evidence_expired`,`license_changed`,`cost_changed`,`import_warning`) |
| `ref_type` | TEXT NOT NULL | ENUM(`candidate`,`demand_signal`,`evidence`,`supply_offer`,`cost_item`) |
| `ref_id` | TEXT NOT NULL | 受影响记录 |
| `ref_gate` | TEXT NULL | 门槛类复核（`gate_expired`/`evidence_expired`/`license_changed`/`cost_changed`）填具体门槛，**使四项门槛各自独立去重** |
| `ref_id_b` | TEXT NULL | 疑似重复的第二记录（`dup_suspect`） |
| `reason` | TEXT NOT NULL | 原因（含触发规则或字段） |
| `status` | TEXT NOT NULL | ENUM(`open`,`resolved_merged`,`resolved_distinct`,`resolved_recheck`,`dismissed`) |
| `blocking` | INTEGER NOT NULL DEFAULT 0 | 1 = 阻止进入 `testable` |
| `created_at` / `resolved_at` | TEXT | `*_at` |
| `note` / `data_origin` | TEXT | 处理说明；与相关候选一致 |

未决去重：部分唯一索引 `UNIQUE(kind, ref_type, ref_id, COALESCE(ref_gate,''), COALESCE(ref_id_b,'')) WHERE status='open'`；`ref_gate` 使**四项门槛各自成键**（同候选的 `gate_expired`/`evidence_expired` 不合并）；`dup_suspect` 写入前把 `ref_id`/`ref_id_b` 按字典序规范化（小者在前），避免 (A,B) 与 (B,A) 各建一条；插入使用 `INSERT ... ON CONFLICT DO NOTHING`（不改时间戳、不增殖）。

### 1.10 source 来源登记

`id`(`s_`)、`name` UNIQUE、`channel` ENUM(`manual`,`xianyu`,`xiaohongshu`,`bilibili`,`other`)、`access_mode` ENUM(`manual_import`,`auto_read`,`official_api`,`unknown`)、`access_verified` ENUM(`yes`,`no`,`unknown`)、`fields_available`、`rate_limit_note`、`cost_note`、`terms_note`、`last_success_at`、`last_error_at`/`last_error`、`enabled`、`created_at`/`updated_at`。

- 冻结种子（`demand_source` 取值即 `name`）：`manual_import`、`xianyu`、`xiaohongshu`、`bilibili`。四行 `access_mode='manual_import'`、`access_verified='yes'`（人工导入自身可用），A 的核验结论摘要写入 `fields_available`/`terms_note`；**不代表自动读取可用**。
- 导入别名：研究侧 `manual` 归一解析为 `manual_import`（种子仍是四个名称）；其他未登记名称 → 行级错误（V9），不静默落到 `manual_import`。

### 1.11 search_coverage 搜索覆盖 `[S3]`

`id`(`sc_`)、`source_id`、`run_id`、`query_text`、`dim_population`/`dim_task`/`dim_tool`/`dim_time_node`、`limit_applied`、`found_count`/`new_count`/`dup_count`、`outcome` ENUM(`ok`,`partial`,`failed`,`blocked_login`,`rate_limited`,`robots_disallowed`,`timeout`)、`failure_reason`、`absence_kind` ENUM(`no_free_source`,`no_ready_supply`,`not_found_yet`)、`coverage_note`（必填）、`started_at`/`finished_at`。失败不得写成"市场无需求"。

### 1.12 run_record 运行记录

`id`(`r_`)、`parent_run_id`（自关联）、`run_type` ENUM(`import`,`collect`,`pipeline`,`summary`,`recompute`,`backup`)、`trigger` ENUM(`manual`,`scheduled`,`system`)、`logical_date`（`*_date`）、`source_id` **NULL 允许**（FK，无来源时为 NULL，不用 `''` 哨兵）、`status` ENUM(`running`,`ok`,`partial`,`failed`,`interrupted`,`skipped_duplicate`)、`started_at`/`finished_at`、`items_found`/`items_new`/`items_dup`、`error_summary`、`notes`。

### 1.13 import_batch / import_row_result

`import_batch`：`id`(`ib_`)、`file_name`、`format` ENUM(`csv`,`json`)、`format_version`、`mode` ENUM(`atomic`,`partial`,**`validate`**)、`encoding`、`status` ENUM(`committed`,`rejected`,`partial_committed`,`validated`)、计数列（`rows_total`/`rows_created`/`rows_duplicate`/`rows_version_added`/`rows_suspect`/`rows_rejected`）、`error_summary`、`created_at`/`finished_at`。`client_ref` 只存于 §1.15。

`import_row_result`：`id`、`batch_id`、`row_no`、`action` ENUM(`created`,`duplicate_skipped`,`version_added`,`suspect_review`,`warning`,`rejected`)、`record_type` ENUM(`candidate`,`demand_signal`,`evidence`,`supply_offer`,`cost_item`)、`record_id`、`reason_code`、`reason_detail`。**同一行可产生多条结果：子记录独立判定（§4.5）。**

### 1.14 schema_migrations

`version` INTEGER PK、`name` TEXT、`applied_at` TEXT。

### 1.15 idempotency_key 幂等记录

| 字段 | 类型 | 约束与语义 |
| --- | --- | --- |
| `id` | TEXT PK | `ik_...` |
| `scope` | TEXT NOT NULL | §0.7 枚举 |
| `client_ref` | TEXT NOT NULL | ≤64 字符 |
| `request_hash` | TEXT NOT NULL | §0.7 定义（文件导入用内容哈希） |
| `response_json` | TEXT NOT NULL | 首次成功响应（重放原样返回） |
| `record_id` | TEXT NULL | 该次写入的主记录 |
| `created_at` | TEXT NOT NULL | `*_at` |

唯一键 `UNIQUE(scope, client_ref)`；与业务写入同事务。

## 2. 关系、约束与不变量

### 2.1 关系

- `candidate` 1—N `demand_signal`、`evidence`、`supply_offer`、`cost_item`、`gate_review`、`draft`、`feedback`。
- `demand_signal` 1—1 `evidence`（`demand_signal_id` 唯一，可空）。
- `cost_item.supply_offer_id`、`gate_review.supply_offer_id` → `supply_offer`；`feedback.related_feedback_id` → `feedback`。
- `source` 1—N `demand_signal`、`search_coverage`、`run_record`。
- `import_batch` 1—N `import_row_result` 与各业务记录。
- `review_item.ref_type/ref_id`（+ `ref_gate`/`ref_id_b`）指向候选及子记录；`blocking=1` 参与状态派生。

### 2.2 数据库约束（原生优先）

- 身份与去重（**均含 `data_origin`**，身份键自带来源命名空间）：`candidate` `UNIQUE(data_origin, identity_key)`；`demand_signal` `UNIQUE(data_origin, source_id, identity_key, content_hash)`；`supply_offer` `UNIQUE(data_origin, candidate_id, url_norm, format_version)`；`evidence` `UNIQUE(demand_signal_id)`（非空时）。
- 成本项活跃唯一：部分唯一索引 `UNIQUE(candidate_id, role, basis, variant) WHERE is_active=1`。
- 门槛序号：`UNIQUE(candidate_id, gate, seq)`。
- 运行每日幂等：`UNIQUE(run_type, logical_date, COALESCE(source_id,'')) WHERE run_type IN ('collect','pipeline','summary','backup')`（索引内空串仅为比较用；`source_id` 本身为 NULL 且 FK 有效）。
- 复核未决唯一：`UNIQUE(kind, ref_type, ref_id, COALESCE(ref_gate,''), COALESCE(ref_id_b,'')) WHERE status='open'`。
- 幂等：`UNIQUE(scope, client_ref)`。
- `CHECK`（仅限输入列与结构）：输入金额列 `>= 0`；`*_bp` 在 `0..10000`；`minutes`、`actual_minutes` 在 `0..1440`；`quantity IS NULL OR quantity > 0`；`cost_item` 值列非空个数 ∈ {0,1}；`value_kind='money'` ⇒ `money_minor` 非空、`='rate'` ⇒ `rate_bp` 非空、`='minutes'` ⇒ `minutes` 非空、`IS NULL` ⇒ 三列全空；`value_kind='rate'` ⇒ `basis='per_order'`；**`value_kind='minutes'` ⇒ `role='manual_labor'`**；`hourly_rate_minor` 非空 ⇒ `role='manual_labor'`；`role='sale_price'` ⇒ `(value_kind IS NULL OR value_kind = 'money')`；`basis='recurring'` ⇒ `period` 非空；`kind='refund'` ⇒ `refund_state` 非空且 `related_feedback_id` 非空；`kind='expense'` ⇒ `expense_kind` 非空；`sample_checked<>'none'` ⇒ `sample_note` 非空；`data_origin ∈ ('real','synthetic')`。
- 索引：`candidate(status)`、`candidate(title_norm_hash)`、子表 FK 列、`review_item(status)`、`run_record(started_at)`。

### 2.3 不变量

| 编号 | 不变量 |
| --- | --- |
| I1 | `candidate.status` 只能由 §3.3 派生函数写入；允许调用点：门槛核验、证据失效、货源更新、成本增改、复核项处理与解决、override、`recompute` 与每日流水线。核验响应返回的 `candidate_status` 即同一结果。 |
| I2 | 模型输出与互动量不得写入 `gate_review` 或 `candidate.status`。 |
| I3 | 未知 ≠ 已知零；聚合与门槛不得吞掉未知项；`cost_item` 值列全空 = 该角色/basis 未知。 |
| I4 | `feedback.predicted_*` 写入后不可改——**任何角色、任何路径（PATCH、重新结算、成本变化、重算）都不得改写或重算**；S2 白名单 = `refund_state`（仅 `kind='refund'`）、`note`、`actual_minutes` 与 `actual_hourly_rate_minor`（仅 `kind='manual_time'` 的录入/更正，同值幂等）；`actual_net_per_order_minor` 与 `actual_complete` 在 S2 **只读且保持 NULL**，其写入白名单自 S5 起生效。 |
| I5 | 四项门槛各自独立核验且须满足 §3.5 准入；任一无有效 `verified` 记录即不得 `testable`。 |
| I6 | 无对外动作端点（发送/发布/付款/采购）；采购与付款由用户线下逐项确认。 |
| I7 | 同一需求下「免费且分发条件适用」的货源排序优先于付费货源；付费货源不自动采购。 |
| I8 | 记录不物理删除：失效用 `invalidated_*`、`status`、`superseded_by`、`is_active=0`、`manual_override='archived'`。 |
| I9 | 每条可展示业务记录带 `data_origin`，子记录与所属候选一致。 |
| I10 | 情景含未知项时不输出单一净收益（§5.5）。 |
| I11 | 每次导入/采集/摘要/重算留 `run_record`；计费与每日类运行同一 `(run_type, logical_date, source_id)` 只有一条有效记录。 |
| I12 | 外部文本与模型输出不能改变任何状态、门槛或金额。 |
| I13 | 符号规则：输入金额非负、派生值可负（§0.3）；输入负金额一律拒绝。 |
| I14 | 去重键、候选身份与合并均不得跨越 `data_origin`；身份键自带来源命名空间，跨来源同 ID 不合并。 |
| I15 | `client_ref` 幂等记录与业务写入同事务；失效重放不改时间戳、不重复建复核项。 |
| I16 | 未提供的成本项一律视为**未知**，不自动视为"无支出"；声明无支出必须显式录入 0（§0.4）。 |

## 3. 状态机与四项门槛

### 3.1 四项门槛

`demand`、`supply_distribution`、`cost`、`platform_policy`。四项各自独立核验、各自引用证据、各自独立复核与去重（`ref_gate`）。

### 3.2 有效期

| 门槛 | 默认 TTL | 说明 |
| --- | --- | --- |
| demand | 90 天 | 需求信号时效较慢 |
| supply_distribution | 30 天 | 价格与分发条款易变 |
| cost | 30 天 | 费用假设易变 |
| platform_policy | 180 天 | 平台规则版本较稳定 |

核验时 `expires_at = min({证据.expires_at} ∪ {verified_at + 默认 TTL} 中的非空值)`——**min 忽略 NULL**；证据无 `expires_at` 时只用默认 TTL。

### 3.3 状态派生（单一函数，读接口与写入路径共用）

`effective_gate_status(gate)`：取同候选同门槛 `seq` 最大的一条；**若该候选在该门槛没有任何 `gate_review` 记录，直接返回 `unverified`**。否则依次判定：

1. 若其 `status='verified'`，但**引用的证据已失效**（`evidence.invalidated_at` 非空）或**所选货源失效/超期**（`supply_offer.status='invalid'`，或 `last_checked_at` 超出 30 天默认 TTL）→ 返回 `expired`。
2. 若其 `status='verified'` 且 `gate='cost'` 且该候选 `base` 情景的必需角色存在未知（三档采购 basis 任一缺行或值为 NULL、`platform_fee`/`payment_fee`/`acquisition`/`refund_reserve`/`other` 未显式取值、或人工计价未知）→ 返回 `expired`。**费用变未知只用于降级曾 `verified` 的成本核验；该判定只看已落库的 `cost_item` 与 `variant='base'`，不依赖任何"绑定集合"字段。**
3. 若其 `status='verified'` 且 `expires_at` 非空且 `<= now` → 返回 `expired`。
4. 否则**保持其原状态**——未核验的 `unverified` 不因费用未知被改判为 `expired`，候选相应保持 `pending`（与 §3.3 状态派生表第 5 行一致）。

**关键约束**：`review_item` 的解决（`resolved_*`）与忽略（`dismissed`）**不得**把仍按上述规则失效的核验恢复为 `verified`；状态只能通过重新核验（新增 `seq`）变为 `verified`。

**读时纯计算**：`GET` 类接口只按上述规则实时计算并返回状态，**不写库、不追加降级或复核记录**（读请求零副作用）；降级记录的物化只发生在写入口（证据失效、货源更新、成本增改、override）与 `recompute`/每日流水线，并按 §1.9 的未决唯一键幂等——重复触发不新增记录、不改时间戳。

`recompute(candidate)` 按顺序取第一个命中：

| 序 | 条件 | 结果 |
| --- | --- | --- |
| 1 | `manual_override='archived'` | `archived` |
| 2 | `manual_override='explore'` | `explore` |
| 3 | 任一门槛 `effective_gate_status` ∈ (`expired`,`failed`)，或存在 `blocking=1` 且 `status='open'` 的复核项 | `stale` |
| 4 | 四门槛均为 `verified` 且无阻断复核项 | `testable` |
| 5 | 其他 | `pending` |

override 优先且不因门槛变化自动清除；`explore` 池不进入可测试推荐与每日摘要重点位。

### 3.4 触发复核的失效来源

| 失效来源 | 影响 | 动作 |
| --- | --- | --- |
| 门槛 `expires_at` 到期 | 对应门槛 | `gate_expired`（`ref_gate=该门槛`，`blocking=1`） |
| `supply_offer.status='invalid'` / `last_checked_at` 超期 | `supply_distribution`、引用该货源的 `cost` | `supply_invalid`（`ref_gate` 分别记录，不合并） |
| `evidence.invalidated_at` 非空 | 引用该证据的门槛 | `evidence_expired`（按门槛去重） |
| 许可条款由允许变为禁止 | `supply_distribution` | `license_changed` |
| 价格/条款变化 | `cost` | `cost_changed` |

**成本实质变化的同事务降级（S2 最小实现）**：四类成本写入口——① `POST /api/candidates/{id}/cost-items`（新增成本项）；② `POST /api/cost-items/{id}/supersede`（取代成本项）；③ `PATCH /api/supplies/{id}`（被选货源价格/版本/依据实质变化）；④ **正式 `POST /api/imports`（`atomic`/`partial`）中由 V17 产生的 `base` 成本新增/取代**——复用同一业务变更规则，并**在各自所在业务事务内**执行：取该候选 `gate='cost'` 中 `seq` 最大的一行；若其 `status='verified'` 且本次为实质变化 → 追加 `seq=max(seq)+1`、`status='expired'`、`verified_by='system_rule'` 的降级核验行，并按 §1.9 未决唯一插入 `cost_changed` 复核项（`ref_gate='cost'`，`ON CONFLICT DO NOTHING`）。

- 实质变化的定义：成本项新增/取代，或货源价格/版本/依据发生实质改变——**即使本次没有新增成本行，也必须降级**（例如仅货源价格或条款依据变化）。
- **不追加**的两种情形：当前 `seq` 最大行已是 `expired`；或本次为**相同语义值重放**（相关字段与值均无实质变化）。
- 事务边界：降级核验行与复核项随所在事务同提交/回滚——`atomic` 批次回滚时它们一并回滚；`partial` 按行处理。
- `mode=validate`（预览）**全程不物化**降级核验行与复核项；只有正式 `atomic`/`partial` 才物化。
- **不使用秒级时间戳比较**，因此同秒取代同样生效；不新增表、不引入通用事件引擎。

物化在写入口（同上）与 `POST /api/runs/recompute`、每日流水线执行；`GET` 类接口按 §3.3 实时计算、**不写库**，两者口径一致。

### 3.5 门槛业务准入

`POST /api/candidates/{id}/gates/{gate}` 置 `verified` 前必须满足下表全部条件；不满足返回 `422 invalid_state` 并在 `details` 列出缺失项。**只有用户可置 `verified`（`verified_by='user'`）；`system_rule` 只能降级为 `expired`/`failed`。**

| 门槛 | 准入条件（全部必须） |
| --- | --- |
| G1 `demand` | 证据 `evidence_type='demand'` 且由该候选的需求信号派生；含 `source_url`、`excerpt`、`observed_at`；`signal_kind` 与摘录一致（卖家宣传不构成需求资格） |
| G2 `supply_distribution` | 指定 `supply_offer_id`（属于本候选、未失效）；**`commercial_allowed`、`redistribute_allowed`、`resale_allowed` 三项均为 `yes`**——任一为 `no` 或 `unknown` 均不自动通过；`sample_checked ≠ none` 且 `sample_note` 记录范围/结果/未核验部分；引用 `supply_distribution` 类证据（`license_evidence_id` 或本次 `evidence_id`）。**例外路径**：若某项许可为 `no`/`unknown` 但用户认为本用途不适用，必须提供结构化适用说明（`license_scope_note` 写明用途/平台/限制）＋条款摘录证据，且 S2 允许该门槛**保持待复核**（不得自动 `verified`） |
| G3 `cost` | 必需角色全部已知：`sale_price`；`procurement` 的**三档 basis（per_order/one_time/recurring）均须有显式取值（含 0；缺行即未知，不强制成 0）**；`platform_fee`、`payment_fee`、`acquisition`、`refund_reserve`、`other` 均须显式取值；`manual_labor` 须有 `minutes` 且 `hourly_rate_minor` 已知；各角色合法 `value_kind` 见 §1.5/§2.2（`money`/`rate`/`minutes` 恰一非空，`rate` 仅 `per_order`，`minutes` 仅 `manual_labor`）；**G3 以 `base` 情景判定并与 G2 所选货源一致**（采购/单价类成本行应经 `supply_offer_id` 指向该货源；未绑定或指向其他货源的行不计入本次核验）；每条 `fact_kind ∈ (estimate, assumption)` 的行须有 `assumption_note`；**已知 0 也须有依据**（`fact_kind='fact'` 且 `source_evidence_id`，或用户明确假设说明） |
| G4 `platform_policy` | 证据 `evidence_type='platform_policy'` **且 `candidate_id` 为本候选**（不得借同供应商其他商品的证据）；`applies_to_platform='xianyu'`（首版常量）；`applies_to_version` 与 G2 所选货源 `format_version` 一致或为 `*`；引用平台规则原文摘录 |

- 反证与缺口示例（全部停在 `pending`）：`resale_allowed='no'`、`commercial_allowed='no'` 而 `resale_allowed='yes'`、`sample_checked='none'`、成本角色缺失或为 NULL、平台证据属其他平台/版本或属其他商品。
- 不构成准入依据：模型输出、互动量、同类标题、纯许可页可读但无本用途条款摘录、A 的研究标签、货源目录可访问性。
- 未知关键成本或人工 → G3 不成立，候选保持 `pending`。

## 4. 导入契约（CSV / JSON，format_version = 1）

### 4.1 结构与参数传递

- CSV：首行表头；一行一个机会（1 候选 + 最多 1 条需求信号 + 最多 1 个货源 + 1 组成本项）。JSON：对象数组，键名与列名一致。
- 编码 UTF-8（可含 BOM）。版本：`?format_version=1` 或 `X-Format-Version: 1`，缺省 1；不支持 → `400 unsupported_format`。
- 批次幂等键：`client_ref` 只在 query 或 `X-Client-Ref`；表内不设该列（批次键与行身份分离，行身份由 §4.5 强键决定）。
- `mode` 取值：`atomic`（默认）、`partial`、**`validate`（预览，不写任何记录，§5.4）**。

### 4.2 列清单与 `_minor` 等价写法

| 组 | 列 | 必填条件 |
| --- | --- | --- |
| 基础 | `title`、`data_origin` | 必填 |
| 基础 | `category`、`use_case`、`delivery_form`、`notes`、`observed_at` | 可选（`observed_at` 缺省取导入时刻；无需求组行给出 warning） |
| 需求 | `demand_url`、`demand_excerpt` | 组内出现任一字段时必填 |
| 需求 | `demand_native_id`、`demand_source`、`demand_kind`、`demand_published_at`、`demand_published_date`、`demand_engagement`、`demand_original_author`、`demand_is_repost`、`demand_origin_group_key` | 可选 |
| 货源 | `supply_provider`、`supply_url`、`supply_commercial_allowed`、`supply_redistribute_allowed`、`supply_resale_allowed` | 组内出现任一字段时必填（许可位可显式填 `unknown`） |
| 货源 | `supply_native_id`、`supply_origin_type`、`supply_format_version`、`supply_price`、`supply_price_basis`、`supply_price_valid_until`、`supply_license_summary`、`supply_license_scope_note`、`supply_evidence_url`、`supply_evidence_excerpt`、`supply_evidence_fact_kind`、`supply_downloadable`、`supply_sample_checked`、`supply_sample_note`、`supply_last_checked_at` | 可选 |
| 成本 | `sale_price`、`platform_fee_bp`、`payment_fee_bp`、`acquisition_cost`、`refund_rate_bp`、`procurement_unit_cost`、`procurement_cost`、`procurement_recurring_cost`、`procurement_period`、`manual_minutes`、`manual_hourly_rate`、`other_cost`、`scenario_variant`、`currency` | 可选；**空 = 未知，0 = 已知零** |
| 成本 | `cost_supply_url` | 可选：本组成本依据的货源入口 |

**`_minor` 等价写法白名单**（分→分，同一目标字段，不做二次换算）：`sale_price_minor`、`supply_price_minor`、`acquisition_cost_minor`、`procurement_unit_cost_minor`、`procurement_cost_minor`、`procurement_recurring_cost_minor`、`other_cost_minor`、`manual_hourly_rate_minor`。白名单外的任何 `*_minor` 键**不接受**：按未知列记为 `warning` 且不参与解析（V18）。

### 4.3 列 → 实体字段映射（显式表）

| 列 | 目标 | 转换或默认 |
| --- | --- | --- |
| `title` | `candidate.title` | 去首尾空白；>300 字符拒绝 |
| `data_origin` | 候选及全部派生记录 | 必填 |
| `category` / `use_case` / `delivery_form` / `notes` | candidate 同名字段 | NULL |
| `observed_at` | `demand_signal.observed_at`、派生 `evidence.observed_at` | 缺省 = 导入时刻并置 `import_time`；**无需求组 → warning** |
| `demand_url` | `demand_signal.url` + `url_norm` | 原样保存 + 规范化 |
| `demand_native_id` | `demand_signal.native_id` | NULL |
| `demand_source` | `demand_signal.source_id` | 名称→`source.id`；缺省 `manual_import`；**别名 `manual`→`manual_import`**；未登记 → V9 |
| `demand_excerpt` | `demand_signal.excerpt` | ≤4000 |
| `demand_kind` | `demand_signal.signal_kind` | 卖家宣传→`seller_promo`、明确求助→`specific_ask`、明确求购→`want_to_buy`、经营记录→`business_record`；缺省 `other` |
| `demand_published_at` / `demand_published_date` | `demand_signal.published_at` / `published_date` | 至多一个 |
| `demand_engagement` | `demand_signal.engagement_json` | JSON 文本；不参与门槛与排序（V20） |
| `demand_original_author` / `demand_is_repost` / `demand_origin_group_key` | 同名字段 | `is_repost` 默认 0 |
| 需求组衍生 | `evidence`（`evidence_type='demand'`） | `fact_kind='fact'`、`source_url`/`excerpt`/`observed_at` 取自需求信号、`demand_signal_id` 回填 |
| `supply_provider` | `supply_offer.provider_name` | 必填（组内出现时） |
| `supply_url` | `supply_offer.provider_url` + `url_norm` | 原样 + 规范化 |
| `supply_native_id` | `supply_offer.native_id` | NULL |
| `supply_origin_type` / `supply_format_version` | `origin_type` / `format_version` | 缺省 `unknown` / `''` |
| `supply_price`（或 `supply_price_minor`） | `supply_offer.unit_price_minor` | 元→分；空 = NULL（未知）；`0` = 免费 |
| `supply_price_basis` / `supply_price_valid_until` / `supply_license_summary` / `supply_license_scope_note` | 对应字段 | NULL |
| `supply_evidence_url` | `supply_offer.license_evidence_url` | **总是保存链接**；缺摘录时只留链接与缺口 |
| `supply_evidence_excerpt`（+ `supply_evidence_fact_kind`） | 派生 `evidence`（`supply_distribution`）+ 回填 `license_evidence_id` | 仅当提供摘录时创建；`fact_kind` 缺省 `fact`；**无摘录不创建证据行、不虚构摘录** |
| `supply_downloadable` / `commercial_*` / `redistribute_*` / `resale_*` | 四个枚举字段 | 缺省 `unknown` |
| `supply_sample_checked` / `supply_sample_note` / `supply_last_checked_at` | 对应字段 | `sample_checked` 缺省 `none` |
| `sale_price`（或 `_minor`） | `cost_item(role=sale_price, basis=per_order, value_kind=money)` | 元→分；**不参与成本求和** |
| `platform_fee_bp` / `payment_fee_bp` | `cost_item(role=platform_fee/payment_fee, basis=per_order, value_kind=rate)` | 整数 bp |
| `acquisition_cost`（或 `_minor`） | `cost_item(role=acquisition, basis=per_order, value_kind=money)` | 元→分 |
| `refund_rate_bp` | `cost_item(role=refund_reserve, basis=per_order, value_kind=rate)` | 整数 bp |
| `procurement_unit_cost`（或 `_minor`） | `cost_item(role=procurement, basis=per_order)` | 元→分；逐单采购，实际计入逐单成本 |
| `procurement_cost`（或 `_minor`） | `cost_item(role=procurement, basis=one_time)` | 元→分；单列 |
| `procurement_recurring_cost`（或 `_minor`，+ `procurement_period`） | `cost_item(role=procurement, basis=recurring)` | 元→分；**缺 `procurement_period` → 行级拒绝（V16）；不自动按月、不落 `period=NULL`** |
| `other_cost`（或 `_minor`） | `cost_item(role=other, basis=per_order)` | 元→分；其他逐单费用 |
| `manual_minutes`（+ `manual_hourly_rate`） | `cost_item(role=manual_labor, basis=per_order, value_kind=minutes)` | 费率元→分；费率空 = 人工未知 |
| `scenario_variant` / `currency` | `cost_item.variant` / 各金额 `currency` | 缺省 `base` / `CNY` |
| `cost_supply_url` | `cost_item.supply_offer_id` | 按 `url_norm` 匹配本候选已有货源；匹配不到 → warning 且保持 NULL（不得当作已匹配） |
| 派生默认 | `cost_item.fact_kind` | 缺省 `assumption`（**不得制造事实依据**）；`assumption_note` 为空则该行视为"假设未说明"，不构成 G3 依据 |
| 计算 | `candidate.identity_key`/`identity_source`、`demand_signal.identity_key`、`content_hash`、`title_norm_hash`、`url_norm` | §4.5 |

### 4.4 校验规则

**执行顺序**：V1（表头与行宽）→ 逐行 V2–V17、V21、V22（**先判双表示与符号，再判未知列**）→ V18/V19/V20 → V23–V27。未知列判定不得吞掉 V21/V22 的冲突。

| 编号 | 规则 | 失败级别 |
| --- | --- | --- |
| V1 | 必填列缺席（表头不含 `title`/`data_origin`） | 整批 `rejected` |
| V2 | `title` 去空白后非空且 ≤300 字符 | 行级 |
| V3 | `data_origin` ∈ (`real`,`synthetic`) | 行级 |
| V4 | `synthetic` 行 URL 为空或示例域；`real` 行为 `http(s)` 绝对地址且不得用示例域 | 行级 |
| V5 | 金额格式：非 `_minor` 列 = 十进制元字符串 `^\d{1,9}(\.\d{1,2})?$`；白名单 `_minor` 列 = 非负整数；**`true`/`false` 等 bool 与非整数一律非法**；拒绝负号、千分位、货币符号、科学计数 | 行级 |
| V6 | `*_bp` ∈ `0..10000`；`minutes` ∈ `0..1440` | 行级 |
| V7 | `*_at` 带 `Z` 或 `±HH:MM`；`*_date` 为有效 `YYYY-MM-DD` | 行级 |
| V8 | `demand_published_at` 与 `demand_published_date` 至多一个 | 行级 |
| V9 | 枚举外值或未登记 `demand_source`（`manual` 例外，归一为 `manual_import`） | 行级 |
| V10 | 组内依赖（§4.2 必填条件） | 行级 |
| V11 | 非 UTF-8 解码失败 | 整批，`encoding_error` |
| V12 | 长度上限：`excerpt` ≤4000、`notes` ≤2000、其他文本 ≤500 | 行级 |
| V13 | 行数 ≤5000 | 整批 |
| V14 | 空文件或仅表头（0 行） | 整批 |
| V15 | `currency` 仅 `CNY` | 行级，`unsupported_currency` |
| V16 | `procurement_recurring_cost` 非空但缺 `procurement_period` | 行级拒绝（原因写明允许值 `monthly`/`quarterly`/`yearly`）；DB CHECK 的 `recurring ⇒ period 非空` 不变 |
| V17 | **按子记录独立去重**：需求信号/派生证据按需求强键判定 `duplicate_skipped`/`version_added`；同行的货源与成本项仍按各自规则处理（更新/新增/取代），**不因需求强键命中而跳过整行** | 规则性说明 |
| V18 | 未知列（含白名单外 `*_minor` 键） | `warning`，不阻断、不解析 |
| V19 | `procurement_cost` 与 `supply_price` 同时非空且不等 | `warning`（可能重复计入） |
| V20 | `demand_engagement` 不参与门槛与排序权重 | 规则性说明 |
| V21 | 同一逻辑金额字段两种写法（如 `sale_price` 与 `sale_price_minor`）同时出现且数值不等 | 行级拒绝；相等时接受并记 `warning` |
| V22 | 输入金额为负 | 行级拒绝 |
| V23 | 无需求组行提供 `observed_at` | `warning`（无落点，不静默丢弃） |
| V24 | 同一批次内同一身份键出现不同 `content_hash` 且无法判定版本 | `suspect_review`，不自动合并 |
| V25 | 行宽与表头列数不一致 | 行级拒绝 |
| V26 | 重复表头（第二个表头行出现在数据区） | 整批 `rejected` |
| V27 | 白名单外后缀键以外的未知列 | 见 V18 |

### 4.5 身份、去重、版本与合并

指纹算法：

- `normalize(text)`：去首尾空白、压缩连续空白、全角转半角、ASCII 转小写。
- `title_norm_hash` = `sha256(normalize(title))` 前 16 字节 hex。
- `content_hash` = `sha256(normalize(excerpt) + "\n" + normalize(title))` 前 16 字节 hex——**仅用于同一身份的版本判定与跨对象疑似重复，不参与身份**。
- `url_norm` 固定规则：scheme/host 小写；去默认端口（`:80`/`:443`）；去 fragment；**仅**删除以下跟踪参数：`utm_*`、`fbclid`、`spm`、`share_*`、`from`、`referer`；其余参数原样保留并按参数名排序重组；path 大小写保留。不使用"等其他"扩大删除范围。

身份（带类型与来源命名空间）：

- 需求信号：`n:<source_id>:<native_id>`（有原生 ID）或 `u:<source_id>:<url_norm>`（需求组 URL 必填，故该档恒可达）；不再使用内容指纹档。此处 `<source_id>` 取**已登记来源名**（如 `xianyu`，与 §4.7 示例及矩阵 S2-05 一致）。
- 候选：有需求组时沿用其需求身份键；无需求组时 `t:<title_norm_hash>`（`identity_source='title'`）。
- 来源命名空间写入身份键本身 ⇒ **不同来源的同 ID 保留为独立候选**（例如 `xianyu:1001` 与 `bilibili:1001` 是两个候选），不以复核标记代替隔离。

强键（均含 `data_origin`）：`demand_signal` `UNIQUE(data_origin, source_id, identity_key, content_hash)`；`supply_offer` `UNIQUE(data_origin, candidate_id, url_norm, format_version)`；`candidate` `UNIQUE(data_origin, identity_key)`。

再导入决策表：

| 情形 | 处理 |
| --- | --- |
| 同身份同内容（原样重导） | 候选/需求信号/派生证据 `duplicate_skipped`（更新 `last_seen_at`）；**同行的货源与成本项仍独立判定**（V17） |
| 同身份、内容变化 | 需求信号 `version_added`（旧行 `superseded_by`），候选复用 |
| 不同来源或不同身份、内容指纹相同 | `suspect_review`（`dup_suspect`，`blocking=0`），不自动合并 |
| 无需求组、无原生 ID 的行重导 | 候选按 `t:<title_norm_hash>` 复用，不增殖 |
| 无需求组但标题变化 | 新候选；同来源且货源 `url_norm` 相同 → `dup_suspect`（确定性提示） |
| 同批次/跨批次同需求、新增费用或货源行 | 需求侧 `duplicate_skipped`；**成本项**：同 `(role,basis,variant)` 值变化 → 新增并取代旧行，值相同 → `duplicate_skipped`；**货源**：命中强键 → 更新价格/条款并记 `cost_changed`，未命中 → 新增 |
| 跨渠道同 `native_id` | 身份含来源命名空间 ⇒ 两个独立候选，各自建记录，互不干扰 |
| `real` 与 `synthetic` 同来源、同 ID、同内容 | 两条独立记录（键含 `data_origin`），分别统计；跨 origin 合并被拒 |

- 冲突：强键命中但载荷不同 → 按上表更新或新版本；无法判定 → `suspect_review`。
- 事务：`atomic` 下任一行失败整批回滚（批次与行结果保留）；`partial` 跳过失败行；`validate` 不写任何业务/批次/运行/幂等记录。
- 转载归并：`origin_group_key` 只做关联展示。
- 合并（`POST /api/candidates/{id}/merge`）：预检 `data_origin`（不同 → `422`）；唯一键冲突记录不迁移、保留在原候选并置 `is_active=0`（成本）/`status='stale'`（货源），生成 `dup_suspect` 且在响应列出；源候选 `manual_override='archived'`、`override_reason='merged:<目标 id>'`。

### 4.6 错误策略与批次

同 §4.5 事务说明；两种写入模式（`atomic`/`partial`）都返回行级结果，不静默丢行；`validate` 返回预览结果并标 `saved=false`。

### 4.7 示例（全部为合成样例）

CSV 正例（38 列，1 行；渠道名 `xianyu` 仅表达归属，URL 为示例域）：

```csv
title,data_origin,category,use_case,sale_price,platform_fee_bp,payment_fee_bp,acquisition_cost,refund_rate_bp,procurement_unit_cost,procurement_cost,procurement_recurring_cost,procurement_period,manual_minutes,manual_hourly_rate,other_cost,cost_supply_url,scenario_variant,currency,observed_at,demand_source,demand_url,demand_excerpt,demand_kind,demand_published_date,supply_provider,supply_url,supply_native_id,supply_origin_type,supply_format_version,supply_price,supply_commercial_allowed,supply_redistribute_allowed,supply_resale_allowed,supply_sample_checked,supply_sample_note,supply_evidence_url,supply_evidence_excerpt
示例-周会纪要模板包,synthetic,模板,小团队周会记录,9.90,500,0,0,0,0,0,0,monthly,15,30.00,0,https://example.com/supply/2001,base,CNY,2026-06-01T08:00:00Z,xianyu,https://example.com/demand/1001,求一份能直接套用的周会纪要模板,specific_ask,2026-05-20,示例开放模板库,https://example.com/supply/2001,tpl-2001,open_repo,v1,0,yes,yes,yes,partial,抽样查看了 3 个文件的结构与占位符,https://example.com/supply/2001/license,本库素材可用于商业用途并允许转售（示例摘录）
```

该行预期：候选 1（身份 `u:xianyu:<url_norm>`）、需求信号 1、需求证据 1、货源 1、`supply_distribution` 证据 1（提供了摘录）、**成本项 10**（`sale_price`、`platform_fee`、`payment_fee=0`、`acquisition=0`、`refund_reserve=0`、`procurement` per_order=0、`procurement` one_time=0、`procurement` recurring=0(monthly)、`other`=0、`manual_labor`；**无支出以显式 0 录入**，不留空），其中 `cost_supply_url` 按 `url_norm` 解析为 `cost_item.supply_offer_id`。人工换算：`manual_hourly_rate=30.00` 元/时 = 3000 分/时 → 15 分钟 = 750 分。**情景数值**：`contribution = 990 − (0+50+0+0+0+0+750) = 190 分`；三档采购与 `other` 均显式取值且固定/周期成本为 0 ⇒ `complete=true`、`net=190`。**定位说明**：这只是"导入成功 + 情景输入可算"，**不等于门槛通过**——导入的成本项默认 `fact_kind='assumption'` 且 `assumption_note` 为空，G3 仍须补假设说明（经 API 补 `assumption_note`，或改 `fact_kind='fact'` 并附依据）。

JSON 正例（费率用元/时字符串 `"30.00"`，等价写法为 `manual_hourly_rate_minor: 3000`；`_minor` 整数是 JSON number 的明确例外）：

```json
[
  {
    "title": "示例-简历模板合集",
    "data_origin": "synthetic",
    "use_case": "应届生投递",
    "sale_price_minor": 1990,
    "platform_fee_bp": 500,
    "payment_fee_bp": 60,
    "acquisition_cost": "0",
    "refund_rate_bp": 200,
    "procurement_unit_cost": "0",
    "manual_minutes": 20,
    "manual_hourly_rate": "30.00",
    "demand_source": "xiaohongshu",
    "demand_url": "https://example.com/demand/1002",
    "demand_excerpt": "有没有可以直接改的简历模板",
    "demand_kind": "want_to_buy",
    "supply_provider": "示例开放素材库",
    "supply_url": "https://example.com/supply/2002",
    "supply_native_id": "tpl-2002",
    "supply_price": "0",
    "supply_commercial_allowed": "yes",
    "supply_redistribute_allowed": "no",
    "supply_resale_allowed": "unknown",
    "supply_sample_checked": "none"
  }
]
```

反例（逐行被拒绝；8 列表头，除末行外每行 8 字段，末行故意 9 字段以触发 V25）：

```csv
title,data_origin,observed_at,sale_price,sale_price_minor,demand_url,demand_excerpt,supply_url
,synthetic,2026-06-01T08:00:00Z,12.00,,,,
示例-金额三位小数,synthetic,2026-06-01T08:00:00Z,12.345,,,,
示例-双表示冲突,synthetic,2026-06-01T08:00:00Z,12.00,1300,,,
示例-负金额,synthetic,2026-06-01T08:00:00Z,-9.90,,,,
示例-时区缺失,synthetic,2026-06-01 08:00:00,9.90,,,,
示例-真实行用示例域,real,2026-06-01T08:00:00Z,9.90,,https://example.com/demand/1005,一条求购信息,
示例-需求组缺摘录,synthetic,2026-06-01T08:00:00Z,9.90,,https://example.com/demand/1003,,
示例-货源组缺许可,synthetic,2026-06-01T08:00:00Z,9.90,,,,https://example.com/supply/2001
示例-行宽不一致,synthetic,2026-06-01T08:00:00Z,9.90,,,,,多余值
```

对应拒绝原因（按行序）：V2；V5；V21（双表示不一致，**先于 V18 判定**）；V22；V7；V4；V10；V10；V25（9 字段 vs 8 列表头）。

语义反例（**不是拒绝**，用于固定未知与负值口径）：

| 输入 | 预期 |
| --- | --- |
| 成本列全空 | 导入成功；情景 `complete=false`、`contribution_per_order_minor=null`、`net_per_order_minor=null`、`unknown_components` 列出缺失角色；**不按 0 计算**（I16） |
| 采购仅录入 `procurement_unit_cost=0`，其余 basis 留空 | 该 basis 已知为 0；其余 basis **未知**（不被掩盖），`complete=false` 直到显式录入 0 |
| 售价 `10.00`、逐单成本合计 `12.00` | 情景与快照可存 `-200` 分；输入列仍全非负 |
| 两渠道各 `native_id=1001` | 身份 `n:xianyu:1001` 与 `n:bilibili:1001` ⇒ 两个独立候选，不是一条加复核项 |
| 同批次再次导入同需求行但新增费用列 | 需求侧 `duplicate_skipped`；新增成本项/货源照常落库（V17），不整行跳过 |

## 5. HTTP API 契约

### 5.1 通用约定

- 基址 `http://127.0.0.1:5000/api`；仅绑定本机（`APP_HOST` 默认 `127.0.0.1`），v1 无鉴权。
- 响应 `application/json; charset=utf-8`；导入接受 `text/csv`、`application/json`、`multipart/form-data`（字段 `file`）。
- 分页：`page`（≥1）、`page_size`（1..100，默认 50）；列表 `{items,total,page,page_size}`。
- 排序：分池顺序 `testable`→`explore`→`pending`→`stale`→`archived`，再按排序分降序（S4 提供，未实现前用 `updated_at`），最后按 `id`；`sort` 仅 `default|updated_desc|created_desc`。
- 状态码：`200` 读取/幂等重放、`201` 新建、`400` 请求格式或字段校验失败、`404`、`409` `client_ref` 冲突或并发调度冲突、`422` 语义/状态不满足、`500`。

### 5.2 错误体与错误码

```json
{"error": {"code": "invalid_state", "message": "门槛准入不满足", "details": [{"field": "supply_offer_id", "reason": "G2: commercial_allowed='no' 而 resale_allowed='yes'"}]}}
```

错误码：`validation_failed`、`invalid_field`、`invalid_state`、`unsupported_currency`、`unsupported_format`、`encoding_error`、`not_found`、`conflict`、`internal_error`。

### 5.3 端点表

| # | 方法 路径 | 用途 | 主要实体 | 幂等（scope） |
| --- | --- | --- | --- | --- |
| 1 | `POST /api/imports?format=&mode=&format_version=&client_ref=` | 导入（`atomic`/`partial`/**`validate`**） | import_batch + 业务记录 | `import` / 强键 |
| 2 | `GET /api/imports/{batch_id}` | 批次与行级结果 | import_batch、import_row_result | — |
| 3 | `GET /api/candidates` | 候选列表 | candidate | — |
| 4 | `GET /api/candidates/{id}` | 详情聚合 | 全部子表 | — |
| 5 | `GET /api/candidates/{id}/scenario?variant=base` | 成本与收益情景（S2：贡献/缺口） | 计算 | — |
| 6 | `POST /api/candidates/{id}/evidences` | 追加证据 | evidence | `evidence` |
| 7 | `POST /api/evidences/{id}/invalidate` | 标记证据失效 | evidence、review_item | 同值幂等 |
| 8 | `POST /api/candidates/{id}/supplies` | 追加货源 | supply_offer | `supply` |
| 9 | `PATCH /api/supplies/{id}` | 更新货源核验 | supply_offer、review_item | 同值幂等 |
| 10 | `POST /api/cost-items/{id}/supersede` | 取代成本项 | cost_item | `cost_item` |
| 11 | `POST /api/candidates/{id}/gates/{gate}` | 记录门槛核验（§3.5） | gate_review、candidate.status | `gate` |
| 12 | `POST /api/candidates/{id}/override` | 人工分池标记 | candidate | `override` |
| 13 | `POST /api/candidates/{id}/merge` | 合并（禁跨界、预检冲突） | candidate、子表、review_item | `merge` |
| 14 | `GET /api/review-items?status=open` | 复核队列 | review_item | — |
| 15 | `POST /api/review-items/{id}/resolve` | 处理复核项 | review_item | 同值幂等 |
| 16 | `POST /api/candidates/{id}/drafts` | 生成草稿 | draft | `draft` |
| 17 | `PATCH /api/drafts/{id}` | 编辑/定稿 | draft | 同值幂等 |
| 18 | `POST /api/candidates/{id}/feedback` | 记录经营事件 | feedback | `feedback` |
| 19 | `GET /api/summary/daily?date=` | 每日摘要（≤5） `[S5]` | 计算 | — |
| 20 | `GET /api/runs?limit=` | 运行记录 | run_record | — |
| 21 | `POST /api/runs/recompute` | 失效物化与状态重算（可同日多次） | run_record、review_item | — |
| 22 | `POST /api/runs/pipeline` | 手动流水线 `[S5]` | run_record + 来源 | 每日唯一键 |
| 23 | `GET /api/sources` | 来源状态 | source | — |
| 24 | `GET /api/health` | 版本与 schema | schema_migrations | — |
| 25 | `POST /api/maintenance/backup` | 备份并校验 `[S6]` | 文件产物 | `backup` |
| 26 | `POST /api/candidates/{id}/cost-items` | **追加**成本项 | cost_item | `cost_item` |
| 27 | `PATCH /api/feedback/{id}` | 事件更新（S2 白名单：`refund_state`、`note`） | feedback | 同值幂等 |

实体↔接口（反向）：`candidate` ← 1/3/4/11/12/13/26；`demand_signal`·`evidence` ← 1/6/7；`supply_offer` ← 1/8/9；`cost_item` ← 1/5/10/26；`gate_review` ← 11；`draft` ← 16/17；`feedback` ← 18/27；`review_item` ← 7/9/13/14/15/21；`run_record` ← 20/21/22；`source` ← 23；`import_batch` ← 1/2；`idempotency_key` ← 全部带 `client_ref` 的写接口。

### 5.4 S2 写接口最小输入/默认/返回/拒绝

| 端点 | 必需输入 | 服务端默认或派生 | 成功返回 | 拒绝条件 |
| --- | --- | --- | --- | --- |
| 1 导入 | 文件或 JSON 体；`mode` | 身份键、指纹、派生需求证据；`mode=validate` 只预览（**不写任何记录、不物化降级核验行与复核项**）；正式 `atomic`/`partial` 中 V17 产生的 `base` 成本新增/取代触发 §3.4 同事务降级（随批次提交或回滚） | `201` 批次+行结果；`validate` → `200` `{"mode":"validate","saved":false,...}` | V1–V27；`400/422` |
| 6 追加证据 | `evidence_type`、`source_url`、`excerpt`、`fact_kind` | `observed_at`=now、`data_origin` 继承 | `201` | 缺摘录或 URL；`404` |
| 7 证据失效 | `invalid_reason` | `invalidated_at`=now、按门槛生成复核项（未决唯一） | `200` | 缺原因 `422` |
| 8 追加货源 | `provider_name`、`provider_url`、三个许可位、`sample_checked` | `url_norm`、`status='candidate'` | `201` | 缺许可位；同 `(url_norm,version)` → `409` |
| 9 更新货源 | 至少一个可改字段 | 价格/条款变化 → `cost_changed` | `200` | 无字段或非法值 `422` |
| 26 追加成本项 | `role`、`basis`（`variant` 默认 `base`） | 同 `(role,basis,variant)` 活跃项自动 `is_active=0` | `201` | 值列 ≥2 个、`rate` 非 `per_order`、`minutes` 非 `manual_labor`、`recurring` 缺 `period` → `422` |
| 10 取代成本项 | 同 `role/basis/variant` 的新值 | `is_active` 切换、`supersedes_id` | `200` | `404`/`422` |
| 11 门槛核验 | `status`；`verified` 时 `evidence_id`（G2 需 `supply_offer_id`，G4 需 `applies_to_*`） | `seq=max+1`、`expires_at`、状态重派生 | `200` 门槛 + `candidate_status` | §3.5 不满足 → `422` |
| 12 override | `manual_override`；非 `none` 需 `override_reason` | 状态重派生 | `200` | 缺原因 `422` |
| 13 合并 | `target_id` | 预检 origin 与唯一键冲突 | `200` 含冲突清单 | 跨界/不存在 `422`/`404` |
| 15 复核处理 | `status`、`note` | `resolved_at`=now、状态重派生（**不恢复已失效核验为 verified**） | `200` | 非法状态 `422` |
| 16 生成草稿 | `kind`、`method` | `body`、`template_version` | `201` | 未配置模型且 `model_assisted` → `422` |
| 17 编辑草稿 | `body` 或 `status='final'` | `updated_at` | `200` | 非法迁移 `422` |
| 18 记录反馈 | `kind`、`occurred_at`（默认 now） | `predicted_*` 仅 `sale` 行由服务端生成 | `201` | 见下方 kind 表 |
| 27 事件更新 | **S2 白名单**：`refund_state`（仅 `kind='refund'`）、`note`、`actual_minutes`/`actual_hourly_rate_minor`（仅 `kind='manual_time'` 的录入/更正） | 同值提交幂等（不新增行、不改时间戳） | `200` | 出现 `predicted_*`、`actual_net_per_order_minor`、`actual_complete` 或白名单外字段 → `422 invalid_field`；对非 `manual_time` 事件传人工字段 → `422` |

feedback 各 kind 输入契约（S2）：

| kind | 必填 | 可选/可改 | 拒绝条件 |
| --- | --- | --- | --- |
| `sale` | `occurred_at`；`amount_minor` 或（`quantity`+`unit_price_minor`） | `order_ref`、`quantity`（正整数） | `quantity <= 0`；`predicted_*`/`actual_*` 由客户端提交 |
| `refund` | `related_feedback_id`（同候选同 origin 的 `sale`）、`refund_state`、`amount_minor` | `order_ref`（如提供须与该 sale 一致）、`note` | 关联不存在或跨候选/跨 origin → `422`；`order_ref` 不符 → `422` |
| `expense` | `expense_kind`、`amount_minor` | `expense_basis`、`quantity`、`unit_price_minor` | `expense_kind` 缺失 → `422` |
| `manual_time` | `actual_minutes` | `actual_hourly_rate_minor` | 分钟为负或 >1440 → `422` |
| `inquiry` / `note` | `occurred_at` | `quantity`、`note` | `quantity <= 0` → `422` |

字段适用性：`actual_minutes`/`actual_hourly_rate_minor` **仅 `kind='manual_time'`** 可写；`refund_state` **仅 `kind='refund'`** 可写；`predicted_*` 由服务端在 `kind='sale'` 行生成、客户端提交一律 `422`；`actual_net_per_order_minor`/`actual_complete` 在 S2 只读且保持 NULL。此处的 `actual_minutes`/`actual_hourly_rate_minor` 是**事件输入数字**（人工时间与费率），与 S5 才产生的派生实际利润字段不是同一类。

S2 与 S5 边界：S2 只负责**完整记录与查询事件、成交时预测快照**；`actual_*` 在 S2 只读且保持 NULL（**不得由缺费用记录推断为 0**）；实际核算（含"全退款 → 实际 0、替换预留"）属 S5-06，且 S5 聚合载体是**唯一 `sale` 行**，事件行不重复存订单净值。

### 5.5 情景口径与请求/响应示例（合成数据）

**S2 分阶段口径**：

1. `contribution_per_order_minor`：仅当**全部 per_order 角色已知**（含 `procurement` 的 per_order 项）时给出 = `sale_price − Σper_order`；否则 `null` 并给 `known_subtotal_minor`。
2. `complete` / `net_per_order_minor`：仅当**每个采购 basis 都已显式给出值（含 0）且 `other` 已声明、关键费用齐备、且固定/周期成本为 0**时，`net = contribution`、`complete=true`；若存在**正额**一次性/周期采购或固定成本未知且缺分摊假设 → `net=null`、`complete=false`、`fixed_cost_gap_minor` 单列（未知时该字段为 `null`，不写 0）。
3. `amortize_orders`：**S2 不使用、不写入**；其净值演算属 `[S4]`（S4-07）。
4. 周期成本：`recurring_monthly_total_minor` 仅当全部 recurring 行为 `monthly` 时给出；出现 `quarterly`/`yearly` 且未归一时，**保留原 `period` 与金额**、该汇总字段为 `null`（不输出伪月额 0）——归一规则属 `[S4]`。
5. `manual_labor` 缺行或费率未知 → 计入 `unknown_components`（人工计价待定，不默认为 0）；`minutes` 已知时仍展示分钟数。
6. `other` 与未提供的采购 basis：**未知**（I16）；声明无支出必须显式录入 0。系统不输出"自动视为无支出"的解释。
7. 只使用选定货源（`supply_offer_id` 非空且匹配本候选）与同一 `variant`；无链接或其他货源价格不得当作已匹配成本。
8. `sale_price` 永不参与成本求和；`sale_price` 未知以 `money_minor IS NULL` 判定。

例 A（全部已知）：售价 1000、逐单采购 300、平台 500bp→50、支付 0、获客 0、退款预留 0、人工 10 分钟×3000 分/时（=30.00 元/时）→500、一次性/周期采购显式 0、`other` 显式 0 → `contribution = 150`，`complete=true`、`net = 150`。
例 B（买断）：同上但采购改为一次性 10000（不再有逐单采购）→ `contribution = 450`；`one_time_total=10000`、`fixed_cost_gap_minor=10000`、`complete=false`、`net=null`；`amortize_orders` 演算（补 20 单 → `net = 450−500 = −50`）标 `[S4]`。
例 C（亏损快照）：售价 1000、逐单成本合计 1200 → `contribution = −200`；`feedback.predicted_net_per_order_minor=−200` 可保存（派生列无 `>=0` 约束）。

情景响应（含未知项）：

```
GET /api/candidates/c_1a2b3c4d5e6f7a8b/scenario?variant=base

200 {"candidate_id": "c_1a2b3c4d5e6f7a8b", "variant": "base", "complete": false,
     "sale_price_minor": 990, "currency": "CNY",
     "per_order": {"procurement_minor": 0, "platform_fee_minor": 50, "payment_fee_minor": null,
                   "acquisition_minor": null, "refund_reserve_minor": 0, "manual_labor_minor": null, "other_minor": 0},
     "known_subtotal_minor": 50, "contribution_per_order_minor": null, "net_per_order_minor": null,
     "one_time_total_minor": null, "fixed_cost_gap_minor": null,
     "recurring_monthly_total_minor": null, "amortize_orders": null,
     "unknown_components": ["payment_fee", "acquisition", "manual_labor", "procurement.one_time", "procurement.recurring"],
     "explanation": ["platform_fee = 500bp × 990 分 = 50 分（ROUND_HALF_UP）",
                     "未提供的采购 basis 与人工计价视为未知，不按 0 计算",
                     "运行支出不计入本情景；摊销归一月额属 S4"]}
```

门槛拒绝示例（§3.5 反证）：

```
POST /api/candidates/c_.../gates/supply_distribution
{"status": "verified", "evidence_id": "e_1", "supply_offer_id": "sp_1"}

422 {"error": {"code": "invalid_state", "message": "G2 准入不满足",
     "details": [{"field": "commercial_allowed", "reason": "commercial_allowed='no'，本用途不允许（no/unknown 均不自动通过）"},
                 {"field": "sample_checked", "reason": "抽样验货为 none"}]}}
```

反馈（S2 只记录事件与快照）：

```
POST /api/candidates/c_.../feedback
{"kind": "sale", "order_ref": "X-1001", "amount_minor": 10000, "quantity": 1}

201 {"id": "fb_a1", "predicted_net_per_order_minor": 9500,
     "predicted_snapshot_at": "2026-06-01T08:00:00Z", "actual_net_per_order_minor": null, "actual_complete": null}

POST /api/candidates/c_.../feedback
{"kind": "refund", "related_feedback_id": "fb_a1", "order_ref": "X-1001", "amount_minor": 10000, "refund_state": "pending"}

201 {"id": "fb_b1", "refund_state": "pending", "related_feedback_id": "fb_a1",
     "actual_net_per_order_minor": null, "actual_complete": null}

PATCH /api/feedback/fb_b1
{"refund_state": "settled"}

200 {"id": "fb_b1", "refund_state": "settled", "related_feedback_id": "fb_a1",
     "actual_net_per_order_minor": null, "actual_complete": null,
     "note_auto": "S2 不核算实际利润；实际核算与「全退款 → 实际 0、替换预留」断言属 S5-06"}
```

## 6. 存储、迁移与备份

- SQLite 单文件：默认 **`instance/app.db`**（对齐 S2-B1 已准备范围），`APP_DB_PATH` 覆盖（测试用独立文件）。
- 连接级 PRAGMA：`foreign_keys=ON`、`journal_mode=WAL`、`busy_timeout=5000`。
- 迁移：`app/storage/migrations/NNNN_*.sql` 升序、事务内执行并写 `schema_migrations`；启动幂等；库版本高于代码支持版本时拒绝启动。
- 单写者假设；调度防重靠 `run_record` 表达式唯一键；复核项防重靠 §1.9 部分唯一索引。
- 备份 `[S6]`：`POST /api/maintenance/backup` 用 `sqlite3.Connection.backup()` 生成 **`instance/backups/app-YYYYMMDD-HHMMSS.db`**，对副本执行 `PRAGMA integrity_check` 与 schema 版本比对；恢复 = 停止应用后替换库文件，再看 `/api/health` 与数据一致。备份与恢复不作为 S2 必做。
- 关键逻辑（金额换算、身份键、门槛派生、情景计算）各留一个标准库 `unittest` 检查；不引入测试框架。
- 安装示例（权限与工具齐备后）：`python -m venv .venv` → **`.venv\Scripts\python -m pip install flask`**（不裸 `pip` 改宿主环境；`pip show flask` 同样用 `.venv` 解释器）；临时下载缓存放 **`.venv/cache`**（已授权路径，不新增写范围），不写系统缓存。
- 有意简化用 `ponytail:` 注释标注上限与升级路径。

## 7. 技术基线与依赖策略（已知 / 待验证）

已知：

- 环境清单工具返回内置运行时路径与包清单（numpy 2.3.5、pandas 3.0.1 等）；**清单未列 Flask/werkzeug——其安装与捆绑状态均待实测（不能由清单推断未安装，也不能推断无法安装）**。
- 工作区文件数按时间点记录：计划 v2 确认时 2 个（历史快照）；本任务首轮返工前 glob 7 个；C 台账 revision 407 观察 8 个（含 D 报告与 A 索引）。当前值以最新 glob 为准。
- `flow_state` 观察：S1 早期各角色 `allowCommands=false`；返工轮次实测执行者 `allowCommands=true`，但**本会话工具集没有命令执行工具**，且本任务指令为仅做设计文档 → 全部运行项未执行。
- 来源结论表述：**A 本轮未核实到发现型自动入口**（闲鱼/小红书需登录或空壳、B站搜索 412；B站详情接口为 S3 候选补全路径，未接入）。不断言"全市场无入口"。
- 各角色状态见文首；**本任务（S1-B）待验收，S1 整体未验收**。

待验证（S2 前置，见 [验收矩阵](<ACCEPTANCE.md>) §2）：宿主 Python 与 venv、pip 与包源、Flask 安装与版本锁定、`sqlite3` 版本、应用启动并仅绑定 `127.0.0.1`、`unittest` 入口、`instance/` 目录可写、端口、依赖边界。

依赖策略：新增直接依赖仅 Flask；其余标准库（`sqlite3`、`csv`、`json`、`decimal`、`datetime`、`hashlib`、`uuid`、`unittest`）；前端无构建链。不引入 ORM、迁移框架、前端框架、向量库、队列或插件系统。若实测 Flask 不可用，属技术基线变更，由策划者提交新计划在 UI 确认。

## 8. D01–D11 覆盖对照

| 决策 | 契约落点 |
| --- | --- |
| D01 免费优先、付费逐项确认 | `supply_offer.unit_price_minor`（0=免费/NULL=未知）、I7；无采购端点 |
| D02 运行预算 100 元/月 | §9 待 S5；本契约冻结"运行支出与商品成本分账" |
| D03 人工 30–60 分钟 | `cost_item(manual_labor, minutes, hourly_rate_minor)`；未知不计 0（§5.5） |
| D04 排序 | §3.3 分池 + `explore` 单列 + 解释字段（S4 实现） |
| D05 货源核验 | §1.4 许可四项 + `sample_checked`/`sample_note` + §3.5-G2 |
| D06 自动化边界 | 无发送/发布/付款/采购端点；`draft.status` 仅 `draft`/`final` |
| D07 首批渠道 | `source` 种子四行（人工导入），别名 `manual` 归一 |
| D08 证据与入池 | `evidence` + `gate_review` + §3.3 派生 + §3.5 准入 + I5 |
| D09 更新与提醒 | `run_record` 每日幂等键、`review_item`（未决唯一）、摘要上限 5 |
| D10 分层验收 | `feedback` 事件与快照分离；S2 不核算实际利润，S5 按唯一 sale 行聚合 |
| D11 自制建议 | `supply_offer.origin_type='self_made'`；四项前提由 S4 复核 |

## 9. 未决项与后续阶段

- S4：`amortize_orders` 净值演算、季度/年度周期归一月额与余分处理、销量假设下项目级收益、排序权重版本化。
- S5：运行费用台账与预算保护（100 元/月上限、累计计费、待发调用预留、未确认计费服务停用）；实际利润核算（唯一 `sale` 行为载体，事件行不存订单净值）。
- S6：备份/恢复路径（`instance/backups/`）、浏览器与异机项在缺工具时留空。
- A 的研究元数据（`evidence_level`、`stats_observed_at`）不新增契约列；`fact_kind` 只对应事实/估算。
- 人工计价方式待定（`hourly_rate_minor` 为空即未知）；分类词表未定（`category` 自由文本）。
- 界面信息架构按 C 的 [开发总体计划](<../../DEVELOPMENT_PLAN.md>) 附录 A（P1–P4）；示例路由不当作已实现接口。
- 币种 v1 仅 CNY；会话调研工具不是应用数据渠道。
