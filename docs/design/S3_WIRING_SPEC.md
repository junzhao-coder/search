# S3 已知对象离线接线最小设计（设计稿，不实施）

> 状态：**仅设计**。本批不写实现、不跑应用或测试、不建网络入口、不写业务库；只维护本文件。文末为修订记录。
> 目标：为"B站已知对象补全"建立**最短且可检验**的离线接线方案，明确与既有导入/去重/版本/来源状态的复用边界与验收矩阵；并把 ABA 版本语义修复列为**接线前置**（已由 D 实跑证实）。
> 依据（均已读）：[冻结契约](<CONTRACT.md>) §0.5 真实与合成（L53–59）、§0.7 幂等（L64–71）、§1.1 candidate（L79–97）、§1.2 demand_signal（L98–121）、§1.9 review_item（L223–240）、§1.10 source（L241–247）、§1.11 search_coverage（L248–251）、§1.12 run_record（L252–255）、§1.13 批次与行结果（L256–261）、§2.2 约束（L291–301）、§4.5 身份/去重/版本/合并（L499–533）、§5.3 端点表（L626–658）、§6 存储与迁移（L763–772）、§9 未决项（L804–812）。
> 现有代码：`app/sources/bilibili_view.py`（334 行，A 的适配器：注入式 transport、失败不缓存不重试、`_observation` 生成 `observed_at`/`observed_at_source`/`observed_at_rejected`）、`app/core/importer.py`（917 行：`validate_row` 重建行对象 219–445、`process_row` 544–566 只比 latest、`apply_status` 717、`handle_import` 809/887/889–891、`run_record` 868–870）、`app/core/identity.py`（84 行）、`app/storage/db.py`（94 行）、`app/api/routes.py`（`GET /api/sources` 134–140、`GET /api/runs` 143–154、`GET /api/candidates/{id}` 266+）。
> 迁移现状：`0001_init.sql`（294 行，含四行 `source` 种子与 `ux_demand_strong` 第 97 行）、`0002_draft_feedback.sql`；**`search_coverage` 不存在且本批不建**。
> 技能：本会话未暴露 `skill` 工具，ponytail 以磁盘读取 SKILL.md（120 行）遵循；无新依赖、无费用。

## 1. 复用边界（先查再决定，不复制导入逻辑）

| 层 | 现状可复用点 | 是否复用 |
| --- | --- | --- |
| 行校验 | `importer.validate_row(row_no, raw, cfg, source_names)`：title ≤300、`data_origin` 枚举、真实/合成 URL 规则、`observed_at` 格式、38 列白名单 | **复用**（不复制、不绕过） |
| 写入与身份 | `importer.process_row`：候选/需求身份、`content_hash` 版本判定、`superseded_by`、派生证据、`dup_suspect` | **复用**（版本判定按 §4.4 修复后使用） |
| 批次与事务 | `importer.handle_import`：`BEGIN/COMMIT/ROLLBACK`、批次状态、行结果、幂等、`run_record` | **复用**（**自管事务**，见 §4） |
| 指纹 | `identity.title_norm_hash` / `content_hash` / `url_norm` / `demand_identity_key` | **复用**（与适配器同一实现） |
| 读取适配 | `bilibili_view.BilibiliViewReader.complete(value, observed_at=…)` | **复用（不修改 A 的模块）** |
| 详情回溯 | `GET /api/candidates/{id}` 已返回 `observed_at_source`/`content_hash`/`version_no`/`superseded_by` 与证据 | **直接复用**，本批不加端点 |
| 迁移 | `db.ensure_schema` 升序单事务 + `schema_migrations` | **复用**；本批**不新增迁移** |

接线层只做"读取记录 → 导入行"的**白名单映射**与编排；全部校验/去重/版本/事务继续由 importer 承担；A 的模块保持"只读取"。

## 2. 调用链（下一批拟新增；无端点、无网络、无定时器、无 collect）

```
caller(测试 / 后续批次)
  └─ BilibiliViewReader(transport=<假 transport，离线回放>).complete(target, observed_at=…)
       ├─ outcome != 'ok' → wiring.record_failure(conn, cfg, record, source_id='s_bilibili')
       │                      └─ 单事务写一条 run_record(status='failed')；不写业务行、不写 batch、不写覆盖
       └─ outcome == 'ok' → wiring.build_row(record, data_origin='synthetic')
              ├─ 契约性拒绝（标题 >300 / URL 规则等）→ record_failure(...)
              └─ 通过 → importer.handle_import(conn, cfg, fmt='json', body=<单行 JSON>,
                              mode='atomic', format_version=1,
                              filename='s3:bilibili:<bvid>.json',
                              run_source_id='s_bilibili',              # 内部可选参数，校验 FK 存在
                              internal_observation={...})              # 内部可选参数，见 §4.5
```

- `handle_import` **自管事务**：调用方必须处于**无事务**状态（SQLite 无嵌套 `BEGIN`）；本设计**不**引入 `owns_transaction` 之类的参数，也不额外写 `collect` 聚合（§4）。
- **无网络**：唯一 transport 由调用方注入；离线回放入口只允许 `data_origin='synthetic'`，**不提供 real 网络路径**。

## 3. 字段映射表（读取记录 → 导入行列 → 库内落点）

| 读取记录字段（`bilibili_view`） | 导入列 | 库内落点 | 规则 |
| --- | --- | --- | --- |
| `title` | `title` | `candidate.title` | 去空白后 1..300；**>300 直接拒绝该行，不截断**（拒绝原因记同行 warning/失败 run） |
| `excerpt` | `demand_excerpt` | `demand_signal.excerpt`、`evidence.excerpt` | 适配器已保证 ≤4000 |
| `bvid`（=`native_id`） | `demand_native_id` | `demand_signal.native_id` | 原样 |
| `source_name`（恒 `bilibili`） | `demand_source` | `demand_signal.source_id`(FK) | 必须是已登记来源名（0001 种子 `bilibili`）；**不改种子** |
| `signal_kind`（恒 `other`） | `demand_kind` | `demand_signal.signal_kind` | 适配器固定 `other` |
| `published_at` | `demand_published_at` | `demand_signal.published_at` | 与 `published_date` 互斥 |
| `original_author` | `demand_original_author` | `demand_signal.original_author` | 缺失即 NULL |
| `engagement_json` | `demand_engagement` | `demand_signal.engagement_json` | **仅展示**，不参与门槛/排序；不放元数据 |
| `url`（真实 bili URL） | **不直接落库** | —（仅作来源文本） | 见 §5-3 两阶段：映射器按已校验 `bvid` 生成**示例域 URL** 写入 `demand_url`，再由 `validate_row` 校验 |
| `url_norm` / `identity_key` | 不传（由 importer 重算） | `demand_signal.url_norm` / `identity_key` | 身份恒 `n:bilibili:<bvid>`（来源命名空间，§4.5） |
| `observed_at` + `observed_at_source` | `observed_at`（经 §4.5 内部注入） | `demand_signal.observed_at` / `observed_at_source` | **始终保留适配器的合法回退时间戳**：`source` ⇒ 源观察时间；`import_time` ⇒ 适配器生成的回退时间戳（**不是 DB 的 `now`**） |
| `content_hash` | 不传 | 由 importer 用 `content_hash(excerpt, title)` 重算 | 必须与适配器值一致；不一致即拒绝（避免"改内容却复用指纹"） |
| `unknown_fields`（`desc_malformed`/`owner_name_missing`/`pubdate_out_of_range`/`stat_malformed`…） | 不设列 | **同行** `import_row_result(action='warning')` | 契约 §9 明确 A 的研究元数据不新增契约列；不写入 `engagement_json` |
| `observed_at_rejected`（非法观察时间原值） | 不设列 | **同行** warning（`S3_OBSERVED_AT_REJECTED`） | 只作文本留痕，**不得**当作源观察时间 |
| `outcome`/`failure_reason`/`http_status`/`app_code`（失败记录） | 不设列 | `run_record.status='failed'` + `error_summary`（原文） | 失败不写业务行、不写覆盖、不写"零需求"；**无 batch** |
| `request_url` | 不传 | `run_record.notes`/`error_summary` 文本 | 合成回放时它是**模板串**，不是本次真实请求 |
| `data_origin` | `data_origin` | 候选/子记录 | **由可信调用上下文给定**（离线回放恒 `synthetic`），不由 `record` 携带 |

**字段白名单（硬规则）**：接线层只允许**基础组 + 需求组**列。外部 `record` 若携带 `supply_*`、成本列或门槛/证据状态键，`build_row` **必须丢弃并记 warning**（或整行拒绝），**绝不透传**——外部读取结果不得改写货源、成本、门槛或授权状态。

## 4. 事务、幂等、计数与审计

- **事务（自管，禁止嵌套）**：`handle_import` 自 `BEGIN`（809）至 `COMMIT`（887），异常 `ROLLBACK` 后**冒泡**（889–891）。调用方必须在**无事务**状态调用；本设计**不引入** `owns_transaction`，也**不额外写 `collect` 聚合**。每个已知对象各自成批、各自事务，失败互不牵连。
- **三条失败路径的落点与回滚范围**（矩阵 S3W-06/07/08/20）：

| 路径 | 触发 | 批次 | 运行记录 | 业务行/回滚范围 |
| --- | --- | --- | --- | --- |
| (a) 适配器失败 | reader `outcome != 'ok'` | **无 `import_batch`** | `wiring.record_failure` 在**自身事务**写一条 `run_record(run_type='import', trigger='manual', logical_date=今天, source_id, status='failed', started_at/finished_at, error_summary=原始原因, notes=…)`；三个计数列**省略**（用 schema 默认 `0`） | 无任何业务写入 |
| (b) 映射/校验 422 | `build_row` 契约性拒绝；或 `handle_import` 的 `atomic` 致命路径 | 前者**无 batch**；后者有 `import_batch(status='rejected')` + `import_row_result(action='rejected', reason_code/reason_detail)`（该批在 819–820 先 `COMMIT`，893–917 在自动提交下补写行原因，**保留**） | 该路径 `handle_import` **不写** `run_record` ⇒ 由 `record_failure` 补一条 `status='failed'`（**单对象 atomic 只用 `failed`**；`partial` 属既有导入的多行语义，补全不新开多行） | 致命路径无业务行（未进入 `process_row`） |
| (c) SQL 异常（如修前 ABA 强键冲突） | `process_row`/`INSERT` 抛 `sqlite3.Error` | 事务内 batch 行与业务写入**一并回滚**（无残留） | 调用方捕获后由 `record_failure` 在**新事务**写 `status='failed'` + `error_summary=<异常类:消息>` | 全部回滚，不留半成品 |

- **计数列约束（勘误，0001 L262–264）**：`run_record.items_found/items_new/items_dup` 三列均为 `INTEGER NOT NULL DEFAULT 0`，**不存在 NULL 选项**。因此 (a)/(b)/(c) 三条失败路径的 run 行**一律省略这三个计数列**（等价于显式 `0`），不得也无法写 NULL；同时 `error_summary`/`notes` 必须写明：**"未成功取得可计数结果；零为失败运行的技术默认值，不是已观测的市场零需求"**——即不得把"不知道"伪装成成功计数，也不得让 0 被读成需求为零。
- **幂等**：强键含 `data_origin`（`candidate UNIQUE(data_origin, identity_key)`、`demand_signal UNIQUE(data_origin, source_id, identity_key, content_hash)`）。补全**不传 `client_ref`**（避免内容变化被 `409` 误伤）：同内容重放 → `duplicate_skipped`（仅 `last_seen_at`）；**从未出现过**的新内容 → `version_added`；**旧版本重见** → 见 §4.4。适配器 24h 缓存只影响是否再次调用 transport，不影响入库判定。
- **计数如实映射**（按现实现，不美化）：`run_record.items_found = rows_total`、`items_new = counts.created`、`items_dup = counts.duplicate_skipped`（868–870）。**`version_added` 只体现在 `import_batch.rows_version_added` 与行结果**，因此"版本新增"场景下 `items_new` 仍为 0 —— 这是现状口径，本批**不**改（把版本新增算作 `items_new` 属另议）。
- **运行类型**：补全用既有 `run_type='import'`（**不冒充 `collect`**，不占 `collect` 每日唯一键，同日可多次补全/重试）。`run_source_id` 写入 `run_record.source_id`，**必须校验 FK 实存**（不在 `source` 表则拒绝），缺省保持 `NULL`（既有调用点行为不变）。
- **状态派生 vs 禁止自动核验**：`process_row` 是完整导入写入函数，末尾调用 `apply_status`（717），首次插入候选硬编码 `status='pending'`、`status_reason='derived:pending|gates_incomplete'`（532）。裁定：补全**沿用既有导入行为**，**不新增任何 `gate_review` 行、不把门槛置 `verified`**；但**不承诺**"所有候选仍为 pending"——**新候选**首次插入即 `pending`，**已有候选**（可能已 `testable`/`archived`/`explore`，或有人工 `manual_override`）状态按既有派生/override 保持不变，**不得为"不自动升级"强制降级**。`apply_status` 既有调用保留，**不改 I1、不改契约**。

### 4.4 ABA 版本语义：已实跑证实的功能 FAIL（接线前置修复）

- **复现（D，联合镜像）**：同一 `(data_origin, source_id, identity_key)` 连续三次语句（内容 A → B → A）得 **201/201/500**，第三次 `internal_error`/`IntegrityError`。证据：`tests/acceptance/_tmp/s3s4_joint_v1/run_20261015_124602_joint/evidence/09_identity_ABA_probe.log`（同名 `.json`）。**不再是静态推断。**
- **成因**：`process_row` 取"同身份最新一行"后**只比较该行的 `content_hash`**（544–548），而插入受强键 `UNIQUE(data_origin, source_id, identity_key, content_hash)` 约束（§2.2 / 0001 第 97 行 `ux_demand_strong`）。latest ≠ 历史全部行，于是 A 重见时走插入分支却与既有行冲突 ⇒ `ROLLBACK` + 冒泡。
- **修复口径（独立最小任务，先于接线；不删索引、不改契约、不加列）**：写入前按**现有强键**查 `SELECT id, version_no, superseded_by FROM demand_signal WHERE data_origin=? AND source_id=? AND identity_key=? AND content_hash=?`：
  1. **命中（旧版本重见）**：**只更新该旧行 `last_seen_at`**；**不新增 version、不追加证据、不改 `superseded_by` 链、不复活旧证据**（`evidence.invalidated_at`/`invalid_reason` 原样）、不重建 `gate_review`。**不承诺整行绝不触碰 review**：同一行的其它子记录（如货源/成本部分）仍按 §4.5/V17 的**原有独立判定**处理。
  2. **未命中（真正新内容）**：维持现有行为——按 `latest.version_no + 1` 追加，旧头部置 `superseded_by`。
  3. 默认**不加新 `review_item.kind`**，也**不强制**引入新 `reason_code`（如 `S3_HASH_REVISIT`）；若修复本身已使行为可解释，行级结果沿用既有 `duplicate_skipped` 即可（是否需要额外标记属另议）。
- **回归定位**：`import`（HTTP 导入）与 `completion` 共用 `process_row`，故 A→B→A 在**两条路径**各测一次（S3W-17），并要求联合镜像连续三次不再出现 500。

### 4.5 观察时间的内部注入（不改公共列、不改默认行为）

- **问题**：`ParsedRow` 由 `validate_row` **从原始列重建**（433–436 只存 `observed_at`），`observed_at_source` 在写入时按"是否非空"推断（542–543）。因此：不传 ⇒ 丢掉适配器的原始回退时间戳（会被写 `now`）；直接传 ⇒ 回退时间被误标 `source`。**仅由 `build_row` 在内部 dict 里塞键没有用——会在重建时被丢弃，不构成完整方案。**
- **方案（内部可选调用参数，最小形状）**：`handle_import(..., internal_observation: dict | None = None)`，仅由接线层传入，**HTTP 路由永不设置**（缺省 `None` ⇒ 默认行为逐字段不变）。内部结构只含三个最小键，**不新增类/DTO/通用元数据框架**：
  | 内部键 | 形状 | 作用 |
  | --- | --- | --- |
  | `observed_at` | `str`（**适配器生成的**合法时间戳） | 落库的 `demand_signal.observed_at` |
  | `observed_at_source` | `'source'` 或 `'import_time'` | 落库的 `observed_at_source`（白名单外即拒绝） |
  | `warnings` | **既有** `(code, reason)` 元组列表 | 行级 warning（`unknown_fields`/`observed_at_rejected` 等） |
  传递与落库路径（全部走**既有**代码路径，不造新通道）：`build_row`/编排产出该内部结构 → `handle_import` 在 **`validate_row` 之后**为**唯一行**设置两个观察时间 hint 并把 `warnings` **追加**到该行既有的 `ParsedRow.warnings` → `process_row` 经既有 `outcome["warnings"]` 返回 → `handle_import` 按既有分支持久化为 `import_row_result(action='warning')`——**与该行业务写入同属一个事务**。
  规则：
  1. **单行限定**：`internal_observation` 非空时要求本批恰好 1 行，否则拒绝（校验/参数错误），杜绝误套多行。
  2. **白名单**：`observed_at_source ∈ {'source','import_time'}`；时间戳须通过与 `_check_at` 同级的 ISO-8601（带时区、真实日历日）校验；`source` 时须与本行 `observed_at` 列一致，`import_time` 时该列为空、由参数提供**适配器生成的回退时间戳**。
  3. **注入时点**：写入该 `ParsedRow` 的**内部**属性（如 `observed_at_hint`/`observed_at_source_hint`，不进 `ALL_COLUMNS`）；`process_row` 改为"有 hint 用 hint，否则回落现有推断"。
  4. **可信来源与未知键**：该参数只由内部调用方构造；出现未列出的内部键即**直接拒绝**（不做兼容忽略），因为 HTTP 公共 JSON/CSV 从不读取它。
- **兼容**：公共 CSV/JSON 列不变，Web 导入路径不传该参数，行为与改动前一致（S3W-15 回归断言）。

## 5. 六类必答边界（最终裁定）

1. **超长标题**：`candidate.title ≤300`，而适配器 `content_hash` 含**原始 title**。裁定：**>300 直接拒绝该行，不截断**（拒绝原因保留原始长度摘要，记同行 warning / 失败 run）。
2. **观察时间语义**：`observed_at_source` 必须原样保留。裁定：**始终保留适配器的合法回退时间戳**（`import_time` 时用适配器的时间戳，**不是 DB `now`**），非法/缺时区的原值只作同行 warning；实现路径见 §4.5 内部参数。
3. **synthetic URL 与生产链接（两阶段）**：① reader 返回的**可信 bili 原 URL 只作来源文本**（可进 warning/日志，**不进任何存储 URL 字段**）；② 映射器按**已校验 `bvid`** 生成示例域 URL（如 `https://example.org/bilibili/video/<bvid>`）写入 `demand_url`，**再由 `validate_row` 按其真实/合成 URL 规则校验**（示例域 + `synthetic` 通过；真实域 + `synthetic` 被拒）。身份用 `n:bilibili:<bvid>`，不受 URL 影响。**当前入口只允许 `synthetic`，不提供 real 网络路径**（真实读取与 `real` 写入需另批授权）。
4. **身份、版本与合并**：身份命名空间取**来源名**（`n:bilibili:<bvid>`），`source_id` 仅作 FK；`content_hash` 复用同一实现；**stat/观察时间变化不产生新版本**；内容变化追加版本；旧行不删、证据不删/不清空、失效字段不改；门槛不自动升级；旧版本重见见 §4.4。
5. **`search_coverage` 与迁移**：**本批不建 `0003`、不建 `search_coverage`**，不改 `0001`/`0002`、不改四行 `source` 种子。该表属 S3-A2（发现型覆盖）之后的另批工作；若将来新建迁移，**失败走事务回滚**，已写入数据的修正靠**版本兼容的备份恢复或前向修复**，**不得**用"删历史表 + 删 `schema_migrations` 行"来清理。
6. **`collect` 每日唯一与多对象/重试**：已知对象补全用 `import` 型运行记录，**不写 `collect`、不做每日聚合、不写覆盖行**（无检索维度即无覆盖主张）；同日可多次补全/重试，各自成行。`run_record.status` 与 `search_coverage.outcome` 是**两套枚举**，不得互相冒充：

| 情形 | `run_record.status` | 覆盖写入 | 业务写入 |
| --- | --- | --- | --- |
| 单对象补全成功 | `ok` | 无 | 候选/需求/证据 |
| 同内容重放 | `ok`（`items_dup`） | 无 | `duplicate_skipped` |
| 内容变化（新 hash） | `ok`（`items_new` 仍按 `counts.created` 口径） | 无 | `version_added` |
| 旧版本重见 | `ok` | 无 | 仅更新旧行 `last_seen_at`（§4.4） |
| 限流 412 / 需登录 / 超时 / 空壳 / 业务失败 | `failed` | 无（发现型才用 `rate_limited`/`blocked_login`/`timeout`） | **不写**候选/需求；不写"零需求" |
| 单批多行部分失败 | `partial` | 无 | 成功行入库、失败行只留原因 |

## 6. 下一实施任务建议 scope（精确文件与顺序）

**顺序**：先做 ① ABA 修复（独立最小任务，§4.4），再做 ② 接线（本设计）。

| 文件 | 动作 |
| --- | --- |
| `app/core/importer.py` | ① `process_row` 插入分支前增加**强键历史命中**检测（§4.4）；② `handle_import` 新增内部可选参数 `internal_observation`（§4.5：单行限定 + 三键最小形状 + 白名单/时间戳校验后注入 hint，并把 `warnings` 追加到既有 `ParsedRow.warnings`；缺省 None）；③ `handle_import` 新增内部可选参数 `run_source_id`（写 `run_record.source_id`，**校验 FK 实存**，缺省 `NULL`）。三处均**加法**，默认路径行为不变 |
| `app/sources/wiring.py`（新） | `build_row(record, *, data_origin)`（白名单映射 + 标题/URL/观察时间规则，返回行 dict 或契约性拒绝原因）；`complete_known_object(conn, cfg, *, reader, target, observed_at=None, data_origin='synthetic')`（**无外层事务**调用 `handle_import`；捕获 `sqlite3.Error` → `record_failure`）；`record_failure(conn, cfg, record, *, source_id)`（单事务写失败 `run_record`，不写业务行/批次/覆盖） |
| `tests/sources/test_wiring_offline.py`（新） | §8 矩阵；全部假 transport + 离线 fixture，断言零网络 |
| `docs/design/S3_WIRING_SPEC.md`（本文件） | 实施批只追加"实施记录"与哈希/日志引用，不改历史与裁定 |

不做（本批与下一批）：新 HTTP 端点、真实网络/`real` 写入、定时器/CLI、`search_coverage`/`0003`、`collect` 聚合、`source` 种子改写、`owns_transaction`/I1/契约改动、新依赖。

## 7. 已裁定（收敛，无遗留阻塞项）

1. 超长标题：**拒绝**（不截断）。2. `unknown_fields`/`observed_at_rejected`：**同行 warning**。3. 观察时间：**始终保留适配器合法回退时间戳**，经 §4.5 内部参数注入。4. synthetic URL：**两阶段**（原 URL 仅来源文本 → 生成示例域 → `validate_row` 校验）；当前只有 synthetic 入口。5. **不建** `0003`/`search_coverage`、**不改**四行 `source` 种子、**不做** collect 聚合；迁移失败=事务回滚，数据修正=备份恢复/前向修复，**不删历史表**。6. `handle_import` **保持自管事务**、不加 `owns_transaction`；`run_source_id` 校验 FK；**计数按现实现如实映射**（不把 `version_added` 说成 `items_new=1`）。7. 状态：新候选 `pending`、`gate_review` 不新增；**已有** `testable`/`archived`/`explore` 与 `manual_override` 按既有派生保持，**不强制降级**。8. ABA：**D 已实跑证实**，作为接线前置独立修复；重见只更新旧行 `last_seen`、不改链与旧证据效力；同行其它子记录仍独立判定；默认不加新 `review.kind`、不强制新 `reason_code`。9. 失败三条路径的批次/运行/审计与回滚范围见 §4。

> 仍需**另批授权**（非本批阻塞项）：真实网络读取与 `data_origin='real'` 写入、`search_coverage`/`0003`、每日 `collect` 聚合、把版本新增计入 `items_new` 的口径变更、新增 `review_item.kind`。

## 8. 验收矩阵（下一批执行，含期望）

| # | 场景 | 期望 |
| --- | --- | --- |
| S3W-01 | 真实摘录 fixture + 合法 `observed_at` | 候选 1（新插入 `status='pending'`）、需求 v1、派生证据 1；`identity_key='n:bilibili:BV1us8MzPEmn'`；`observed_at_source='source'`；`demand_kind='other'`；`run_record(run_type='import', source_id='s_bilibili', status='ok')` |
| S3W-02 | 同输入重放 | `duplicate_skipped`；候选/需求行数不变；仅 `last_seen_at` 更新；`items_dup` 反映重复 |
| S3W-03 | 改 `title`/`desc` 后重放 | `version_added`、`version_no=2`、旧行 `superseded_by`、候选复用；**同时断言口径**：`import_batch.rows_version_added=1` 而 `run_record.items_new=0`（如实映射） |
| S3W-04 | 仅 `stat` 变化 | `duplicate_skipped`；**不新增版本** |
| S3W-05 | `observed_at` 非法（无时区/非法日期） | 落库 `observed_at` = **适配器生成的回退时间戳**（不是 `now`）、`observed_at_source='import_time'`；原值以同行 warning 留痕 |
| S3W-06 | 失败样本 `rate_limited_412` | **无 `import_batch`、无候选/需求/证据**；`run_record.status='failed'`、`error_summary` 含原文；无覆盖行、无零需求 |
| S3W-07 | `login_redirect_200` / `timeout` / `html_shell` / `62002` | 同 S3W-06（失败原因文本区分），不写覆盖枚举 |
| S3W-08 | 标题 301 字 | 行被拒；**无截断写入**；拒绝原因含原长度；无候选；审计 run 记录存在 |
| S3W-09 | 合成回放 URL（两阶段） | 库内 `demand_signal.url`/`url_norm` 为**示例域**；`data_origin='synthetic'`；**任何存储 URL 字段都不含 bilibili.com**；原 URL 仅出现在 warning/日志文本 |
| S3W-10 | 直接构造违规导入行（`data_origin='synthetic'` + 真实 bili URL）交给 `handle_import` | `validate_row` 按既有规则**拒绝该行**（不写入）；验证"两阶段"的校验落在校验层，而非"同一输入两种结果" |
| S3W-11 | 同 `bvid` 不同来源名；`real` 与 `synthetic` 同名同 ID | 各自独立记录（身份含来源名与 `data_origin`），互不覆盖 |
| S3W-12 | 补全后查详情与 `/api/sources` | 详情可见 `observed_at_source`/`content_hash`/`version_no`/证据；四行 `source` 未被改写（仍 `manual_import`/`yes`、`last_success_at` 未动） |
| S3W-13 | 状态与既有 override | `gate_review` **零新增行**；**新候选**首次插入为 `pending`；**已有** `testable` 候选与 `manual_override='archived'` 候选在补全后状态**保持不变**（不强制降级、不保证仍 pending） |
| S3W-14 | 零网络 | 模块导入不触发网络；非法目标 transport 0 次调用；`bilibili_view.py` 未被修改（哈希不变） |
| S3W-15 | **默认原路径兼容** | 同一 fixture 内容分别走：①接线（带 §4.5 内部参数）②既有 CSV/JSON HTTP 导入（无参数）——② 的 `observed_at`/`observed_at_source` 推断、warnings、批次/运行记录与改动前逐字段一致 |
| S3W-16 | S4 联合回归 | S4 默认路径逐字段兼容、显式假设公式（`−50`/`833`/`−683`/`858`/`−708`）、GET 零写、成交快照不可变且 `actual_*` 为 NULL —— 全部不退化 |
| S3W-17 | **A→B→A**（同 `bvid` 摘录 A→B→A），补全与 HTTP 导入各一次 | 修前须复现 D 的 FAIL（引 09 证据）；修后：无 500、不新增行、`version_no` 不变、`superseded_by` 链不变、仅旧行 `last_seen_at` 更新、`evidence` 行数与失效字段不变；**同行其它子记录仍按原规则独立判定** |
| S3W-18 | 越权字段（含 `supply_url`/`supply_price`/`procurement_unit_cost`/`gate_cost`） | 被丢弃并记 warning（或整行拒绝）；`supply_offer`/`cost_item`/`gate_review` **零新增**；候选仅由需求组产生 |
| S3W-19 | §4.5 内部参数规则 | 多行传入 → 拒绝；`observed_at_source` 非白名单 → 拒绝；时间戳非法 → 拒绝；`source` 与列值不一致 → 拒绝；出现未列出的内部键 → 拒绝；合法时 hint 与该行业务写入**同一事务**、`warnings` 以**既有 `(code,reason)` 形状**追加到该行并经既有 `outcome.warnings` 持久化为 `import_row_result(action='warning')`；`run_source_id` 指向不存在的 FK → 拒绝 |
| S3W-20 | 失败路径审计（§4，逐路径一致） | **(a)** 适配器失败：**无 batch** + `record_failure` 写一条 `run_record(status='failed')`（计数列**省略→默认 0**、`error_summary`/`notes` 注明"技术默认 0 ≠ 零需求"）；**(b1)** `build_row` 契约性拒绝：**无 batch** + failed run；**(b2)** `handle_import` `atomic` 校验 422：有 `import_batch(status='rejected')` + `import_row_result(action='rejected')`（保留）+ 另由 `record_failure` 补 failed run；**(c)** 注入 `sqlite3.Error`：批内 batch 行与业务写入**全部回滚**（无残留）+ 新事务 failed run；四条均无半成品业务行，且 run 计数列一律为 schema 默认 `0`（**不写 NULL**） |
| S3W-21 | 计数口径 | `items_found=rows_total`、`items_new=counts.created`、`items_dup=counts.duplicate_skipped`；`version_added`/`suspect_review`/`rejected` 仅体现在 `import_batch.rows_*` 与行结果（与现实现一致，不美化） |

## 9. 本批声明

- 本批**只维护本设计文件**：未写实现、未跑应用或测试、未联网、未建网络入口、未写业务库 `instance/app.db`、未改契约/源码/测试/根台账/迁移、无新依赖与费用。
- 未实现、未运行如实列出：接线与 ABA 修复**均未实施**；`tests/sources/test_bilibili_view.py`（A 的 41 项）不在本批执行范围；`search_coverage` 不存在且本批不建；D 的 ABA 复现证据为**只读引用**。
- 不声称 S3 已完成或阶段通过；不把"已知对象补全"当发现能力；失败一律不写成"市场无需求"。

## 10. 修订记录

- 初版（revision 2 提交）：复用边界、映射表、调用链、六类边界、矩阵 16 行、7 条待裁定。
- 第二次（revision 3 提交）：补 `handle_import` 嵌套禁令；§4.4 ABA 静态疑点与最小策略；§4.5 观察时间内部键方案；状态派生与禁止自动核验；矩阵补 17–21 行。
- 本次（revision 5 返工，按最终裁定收敛为单一方案）：长标题定为**只拒绝**（删除旧备选表述）；观察时间改为**内部调用参数 + 校验后注入**（并注明内部 dict 键会被重建丢弃）；synthetic URL 定为**两阶段**并改写 S3W-10；**删除** `0003`/`search_coverage` DDL 与"删表删版本行"回滚建议，改为不建表 + 迁移治理；`handle_import` 保持自管事务（不加 `owns_transaction`、不额外 collect）、`run_source_id` 校验 FK、计数如实映射；三条失败路径的批次/运行/审计与回滚逐条写清；状态段落改为"新候选 pending、已有候选/override 保持不变、不强制降级"；ABA 标注 **D 已实跑证实**并明确"同行其它子记录独立判定、不加新 review kind、不强制新 reason_code"；§7 由 11 条待决收敛为已裁定 9 条 + 另批授权项。
- **勘误（task-222a0543b032804de0ead5b7eebb50，前次验收遗漏由策划者复核发现；不回写旧验收结论）**：① 更正 §4 失败表 (a) 与新增"计数列约束"说明——`run_record.items_found/items_new/items_dup` 实为 `INTEGER NOT NULL DEFAULT 0`（`0001_init.sql` L262–264），**不存在 NULL**，失败 run 一律省略三列取默认 `0`，并在 `error_summary`/`notes` 注明"技术默认 0 ≠ 已观测的零市场需求"；② §4 失败表 (b) 去掉 `partial` 选项（单对象 `atomic` 只用 `failed`），并把 S3W-20 拆为 **(a)/(b1)/(b2)/(c)** 四条路径，与 §4 表述逐条一致；③ §4.5 明确内部参数的最小形状（`observed_at`/`observed_at_source`/`warnings` 三键）与 warnings 的既有传递链（`build_row` → 注入 `ParsedRow.warnings` → `process_row` 既有 `outcome.warnings` → 既有行结果持久化，同事务），声明**不新增类/DTO/框架**、未知内部键直接拒绝；同步更新 S3W-19。ABA 证据（§4.4）与上述历史记录均保留，本次仅此三处。

## 11. 实施记录（task-665f3cd3865b5880602a5e8d759c2d37）

§1–§10 为设计与勘误历史，未改动；本节只记本批**实际实现与实测**。

### 11.1 落点与哈希（实测）

| 文件 | 内容 | live=mirror SHA256 |
| --- | --- | --- |
| `app/sources/wiring.py`（新） | `build_row`（白名单映射：仅基础+需求列，丢弃外部 supply/cost/门槛键并记 warning；title>300、bvid/来源/摘录、重算 `content_hash` 一致性校验；示例域存储 URL 与 bvid 生成）、`complete_known_object`（无外层事务编排：读取 → 映射 → `handle_import`）、`record_failure`（单事务审计 run，自管事务、失败冒泡） | `B7AD7AB2…` |
| `app/core/importer.py` | 新增 `_INTERNAL_OBSERVATION_KEYS` 与 `_apply_internal_observation`（单行限定、未知键拒绝、白名单、时间戳校验、`source` 与列一致/`import_time` 列空、`(code,reason)` 追加到既有 `ParsedRow.warnings`）；`ParsedRow` 增两个内部 hint 字段；`process_row` observed_at/source 改为"有 hint 用 hint，否则回落现状"；`handle_import` 增内部可选参数 `run_source_id`（**预校验 FK 实存**）与 `internal_observation`，并把 `source_id` 写入 `run_record`（缺省仍 `NULL`） | `A11EAF4D…` |
| `tests/sources/test_wiring_offline.py`（新） | 21 项（S3W-01…S3W-21），全部离线 fixture + 假 transport，无网络 | `947924FC…` |

### 11.2 实测（只在本 run 镜像内；`cwd=<run>/mirror`，`PYTHONDONTWRITEBYTECODE=1`）

run 目录：`tests/sources/_tmp/s3_wiring_impl_v1/run_20261015_220946_20e8fa88/`。子进程内路径实证（`06_path_probe.txt`，exit=0）：`probe.cwd`/`env_current_directory`/`app.__file__`/`importer.__file__`/`wiring.__file__` 全部落在镜像，`probe.inside_scope=True`，`probe.db_path=…\mirror\instance\app.db`。

| 步骤 | 结果（真实 exit） | 日志 |
| --- | --- | --- |
| `tests\sources\test_wiring_offline.py` | **Ran 21 … OK，exit=0** | `21_wiring_offline.log`（首轮 6 失败→修正 8 处测试期望的中间日志 `10_/11_/12_` 保留） |
| `tests\api\test_import_api.py` | Ran 33 … OK，exit=0 | `21_import_api.log` |
| `tests\api\test_gates_scenario.py` | Ran 82 … OK，exit=0 | `21_gates_scenario.log` |
| `tests\api\test_feedback_draft.py` | Ran 8 … OK，exit=0 | `21_feedback_draft.log` |
| `tests\sources\test_bilibili_view.py` | Ran 41 … OK，exit=0 | `21_sources_bilibili.log` |
| `tests\core\test_money.py` / `test_identity.py` / `tests\storage\test_migrations.py` | 7 / 7 / 4，均 exit=0 | 同名日志 |
| 全量 discover | **Ran 217 … OK，exit=0**（196 既有 + 21 新增） | `21_discover.log` |
| 镜像内 HTTP E2E（复制脚本，镜像已备 `.venv`） | **RESULT PASS / E2E_OK，exit=0**，`business_db_unchanged=True` | `31_isolated_e2e_mirror.log` |

守护与范围（`01_/33_` 业务库、`02_/34_` 根三文档、`04_/35_` host tmp、`30_/32_` live `s2_boundaries`）：业务库 `E073F828…4EB85` 前后一致（wal/shm 均 MISSING）；根三文档哈希前后一致；live `tests/api/_tmp` 条目 **3236 → 3236** 且清单哈希一致；live `s2_boundaries` 清单哈希**完全一致**（E2E 产物全在镜像内 `…\mirror\tests\api\_tmp\s2_boundaries\e2e_20261015_221435_ed88c6f1\`）；live↔mirror 三个改动文件哈希一致（见 §11.1）。

### 11.3 与设计的两处口径澄清（不改历史，仅记录实测）

1. **S3W-13 状态语义**：补全沿用既有导入行为——`process_row` 末尾调用 `apply_status`，因此**门槛未核验的候选在补全后派生为 `pending`**（既有行为，未新增降级）；`manual_override='archived'` 被既有派生尊重（实测补全后仍 `archived`）；`gate_review` 零新增。§8 中"已有 `testable` 候选保持不变"应理解为"**已真正核验**的候选不被强制降级"，其实测覆盖在既有门槛套件（`test_gates_scenario` 82 项，本 run 同批执行）。
2. **失败路径多出一种"hint 校验失败"**：`internal_observation` 自身不合法时，`handle_import` 在**建立批次之前**即抛 `AppError`（无 batch），由接线层转为失败 run —— 这是 §4 表 (b1) 之外的相邻情形，实测记录于 `07_diag_b2.txt`。

### 11.4 未做 / 限制

未实现 §6 之外任何内容：无新端点、无真实网络与 `real` 写入（`build_row` 仅接受 `synthetic`）、无 `0003`/`search_coverage`、无 `collect` 聚合、未改 `0001`/`0002`/契约/`source` 种子/计数口径/`review.kind`；`S3W-11` 按裁定为**低层导入**用例（未借接线开放可变来源）；本批**不是** S3 阶段完成，也**不以自测替代原 D 的独立复验**（D 复验 scope：`tests/acceptance/_tmp/s3_wiring_recheck_v1`）。

### 11.5 返工：stray 告警误报修复（task-8f54daee876a13217f26fd017f712fc6）

- **缺陷（原 D 独立实测，逐字证据）**：`tests/acceptance/_tmp/s3_wiring_recheck_v1/run_20261015_222105_wire/evidence/09_wiring_strays.log` —— 真实 `BilibiliViewReader` 干净成功返回 **21 键**记录，而 §11.1 的 `_RECORD_KEYS` 只有 **12 键**，strays 恒为 10 键（`app_code, http_status, identity_key, identity_source, observed_at, observed_at_source, request_url, unknown_fields, url, url_norm`）⇒ **每次干净成功都会写一条误导性 `S3_UNKNOWN_FIELDS` 告警**；其中 `observed_at`/`observed_at_source` 实际被消费进内部 hint，`url`/`url_norm` 是设计允许的来源文本，都不应算"被丢弃"。越权记录只是该 10 键再加 4 个越权键，因此**旧 S3W-18 的"存在该 warning"断言不具判别性**。
- **修法（最小，不动其它语义）**：`_RECORD_KEYS` 改为**已消费/已映射的适配器键集合**（原 12 键 + 上述 10 键 + `observed_at_rejected`，共 23 键，并在注释中区分"映射/告警/审计/由 importer 重算/常量"五类）；`unknown_fields` 与 `observed_at_rejected` 的告警**仍只在适配器实际上报时产生**；`S3W-18` 改为**互补可判别**断言——干净成功时断言行级 warning 数为 **0** 且 `build_row` 返回空 warnings，越权记录时断言恰有一条 `S3_UNKNOWN_FIELDS` 且 reason 中点名的键**恰好等于**4 个越权键。观察时间/hint/白名单/事务/失败审计/计数/ABA 强键等一律未动。
- **返工后权威哈希（live=mirror 一致）**：`app/sources/wiring.py` = `bafcf3974cbfb3ed4da99936e5d65d10d6f02c663b6325008255b4eaecc0da05`；`tests/sources/test_wiring_offline.py` = `c66d72ee36f7697c105a87934784a0abb552ae4bdf8c5c60ad7179c4c264da4f`；`app/core/importer.py` 未变 = `a11eaf4d39541ac11459eb1cebb8586f4922838b96714d7f7f3d2e253cff51a1`。**§11.1 表中的 `B7AD7AB2…`（wiring）与 `947924FC…`（测试）为返工前值**，以本节为新权威。
- **偏差①（`request_url`）**：§3 映射表把失败记录的 `request_url` 归入 `run_record.notes/error_summary` 文本；在**成功**路径上它被 `_RECORD_KEYS` 视为已消费但**不落任何字段**（无对应列），同理 `http_status`/`app_code`（成功路径）、`identity_key`/`identity_source`/`url`/`url_norm`（由 importer 依来源名与 bvid 重算）——即"**被消费但未持久化**"，既非"被丢弃告警"，也不写库。
- **返工实测**（新 run `tests/sources/_tmp/s3_wiring_fix_v1/run_20261015_223500_fixb/`，cwd=该 run 镜像；子进程内实证 `20_path_probe.txt`：`cwd`/`app.__file__`/`importer.__file__`/`wiring.__file__`/`db` 全在镜像）：`30_wiring_offline` **21 OK exit=0**、`31_import_api` 33、`32_gates_scenario` 82、`33_feedback_draft` 8、`34_sources_bilibili` 41、`35_core_money` 7、`36_core_identity` 7、`37_storage_migrations` 4 均 **exit=0**、`38_discover` **217 OK exit=0**、`39_isolated_e2e_mirror` **exit=0（RESULT PASS / E2E_OK，`business_db_unchanged=True`）**；逐字对照 `41_warnings_verbatim.log`：`clean_record_keys= 21`、`clean_strays= []`、`clean_warnings= []`、`violation_strays= ['gate_cost','procurement_unit_cost','supply_price','supply_url']`、`violation_warnings=[["S3_UNKNOWN_FIELDS","记录含非需求字段，已丢弃：gate_cost,procurement_unit_cost,supply_price,supply_url"]]`。守护：业务库 `E073F828…4EB85` 前后一致（wal/shm MISSING）、根三文档哈希一致、live `tests/api/_tmp` **3236→3236**、live `s2_boundaries` 清单哈希前后一致（E2E 产物仅在镜像 `…\mirror\tests\api\_tmp\s2_boundaries\e2e_20261015_223525_0027702e`）；`60_evidence_readback.txt` 逐件核验证据文件 **无 BOM、无 CRLF**；旧 run 的 `05_mirror_manifest.txt` 只**追加**了一行 `CORRECTION(...)` 说明其为返工前基线（未覆盖）。
