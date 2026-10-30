# S3 真实链路前置设计（设计稿：未实现、未联网、未接入真实渠道）

> 状态：**设计稿 / 未实现 / 未联网**。本文不新增任何网络权限、依赖、表、端点、CLI 或定时器，不改 `app/**`、`tests/**`、迁移、契约、根台账与业务库 `instance/app.db`。
> 真实性声明：**尚无任何真实网络证据**。现有证据仅为离线回放（fixture transport）与 `test_client` 模拟——[S3_PUBLIC_PATH_COMPATIBILITY.md](../validation/S3_PUBLIC_PATH_COMPATIBILITY.md) **§4.2** 明确「`tc-*` 是 HTTP 处理栈模拟，不是 loopback 真实 HTTP」；真实网络批次须由**用户逐项另行授权**后才可执行（§8）。
> 本版为**修订 v2**：按独立评审 [S3_REAL_LINK_REVIEW.md](../validation/S3_REAL_LINK_REVIEW.md)（182 行，结论「需修订」）的 F-01…F-08 与 M-01…M-09 逐条修订；F→修改位置见 §12。评审行号对应 v1（121 行）；本文行号以本文件为准。
> 依据（只读已阅）：[S3_WIRING_SPEC.md](<S3_WIRING_SPEC.md>)（231 行；观察时间内部注入在 **§4.5**，即 `S3_WIRING_SPEC.md:94–110`；§11.5 为 stray 告警返工）· `app/sources/bilibili_view.py`（334 行；`observed_at` 回退 `:126–132`，`published_at` 由 `pubdate` 换算 `:108–111`、`:261`，失败分类 `:66–87`/`:208–268`，transport 调用 `:327`，无重试 `:298`）· `app/sources/wiring.py`（166 行，冻结 `bafcf397…`；`build_row:52–103`、synthetic-only `:58–59`、示例域 URL `:87`、`record_failure:106–131`、适配器失败→失败 run `:141–147`、异常/422→失败 run `:160–164`）· `app/core/importer.py`（991 行，冻结 `a11eaf4d…`；内部参数 `:763–800`/`:803–809`、`run_record` 写入 `:939–945`）· [CONTRACT.md](<CONTRACT.md>) §0.5/§0.7/§1.10–§1.12/§2.2/§3.3/§4/§4.5 · `0001_init.sql`（`run_record.status` 枚举 `:259`、三计数 `NOT NULL DEFAULT 0` `:262–264`、`search_coverage` 未建 `:2`）· `DEVELOPMENT_PLAN.md` §7 · [S3_OFFLINE_WIRING_ACCEPTANCE.md](../validation/S3_OFFLINE_WIRING_ACCEPTANCE.md)。
> 技能：本会话**未暴露 `skill` 工具**，如实标注未加载；无新依赖、无费用。

## 1. 目标与不可越界边界

- **目标**：给出"单来源（B 站详情接口 `x/web-interface/view?bvid=`）低频只读补全"的最小可行设计，使真实拉取仍走**已验收的离线接线路径**（`wiring` → 既有导入/去重/版本），不新造第二套落库通道。
- **范围外**：发现型检索（无可用入口）、非 B 站来源、登录态/扫码/Cookie、验证码或风控绕过、代理池、批量爬取、付费服务、新 HTTP 端点、CLI、定时器/后台任务、新表/迁移、`search_coverage`（该表**未建**，`0001_init.sql:2`）、改 `source` 四行种子的 `access_mode`/`access_verified`/`last_success_at`、把失败写成"无需求"。
- **证据边界**：真实链路是否可用，只能由"用户授权批次的真实运行证据"证明；本文不得被引用为"已接通"。
- **引用口径**：本文引用的代码行号对应当前 live 文件（哈希见上），若上游变更需重核；`CONTRACT` 中 §0.7/§1.10–§1.12/§2.2/§3.3 仅核验"段落存在"，未逐字比对（评审 F-18），实现批前须由作者/策划确认。

## 2. 授权与合规前置（逐项、可拒绝、可停止）

启动真实批次前用户须**逐项**确认（未确认任一即不得运行）。下表"执行方式"列说明该项**现在**能由什么来保证——**注意：当前代码内唯一的强制点是"注入式 transport"本身；runner 级授权闸门尚不存在（见 F-09）**。

| # | 授权项 | 必须明确的内容 | 执行方式（现状 → 实现批） |
| --- | --- | --- | --- |
| A1 | 来源与端点 | 仅 `bilibili`；仅 `GET …/x/web-interface/view?bvid=<bvid>`；不搜索、不跟随短链（`b23.tv` 不解析，`resolve_target:33–63`） | 人工确认；实现批在 runner 校验端点模板 |
| A2 | 目标清单 | 用户给定 bvid 白名单、批次对象数上限（默认 ≤20） | 人工确认；实现批 runner 校验规模 |
| A3 | 频次 | 请求数上限（默认 ≤20）、同对象最小间隔（默认 ≥5 秒）、批次时长上限（默认 ≤10 分钟） | 人工确认；**预算/间隔的代码化属实现批**（§3） |
| A4 | 费用 | 本轮为免费公开接口、设计不含付费调用；`cost_note` 由用户确认；不买第三方接口/代理 | 人工确认 |
| A5 | 合规 | 不登录、不绕风控/验证码、不伪造 UA/Referer、不落盘他人隐私 | 人工确认；实现批 transport 不得携带登录态 |
| A6 | 条款与 robots | 记录本次访问的条款/robots 观察（文本），不把"未验证"写成"允许" | 人工确认；**外部前置检查结果由调用方传入，适配器不产出该分类**（F-05） |
| A7 | 数据保留 | 字段范围与保留/删除方式由用户确认 | 人工确认 |
| A8 | 可停止 | 可随时终止；终止后不再请求，已写入与失败记录保留 | 人工确认；实现批停止逻辑 |
| A9 | 失败口径 | 失败不得写成"市场无需求"，只写"本批未取得可计数结果" | 人工确认 + 代码既有行为（失败 run 文案） |

- **绕过口（须由实现批关闭）**：现可直接 `BilibiliViewReader(transport=真实)` 或 `complete_known_object(reader=…)`，两者**代码内均无授权校验**（`bilibili_view.py:297–322`、`wiring.py:134–166`）。故实现批必须新增 runner 级闸门，并把"**未授权批次 transport 调用 = 0 次**"作为验收断言（§9.2）。
- `access_mode`/`access_verified` 保持现状（四行种子仍 `manual_import`/`yes`）；一次真实成功**不足以**改称 `auto_read`，也不得写 `last_success_at` 伪造成功。

## 3. 限流、退避与请求预算

- **预算**：以"请求次数"为唯一预算单位（1 次 transport 调用 = 1 次请求，**含重试**）。达到上限立即停止。**预算耗尽不得写成 `run_record.status`**——`run_record.status` 枚举只有 `running/ok/partial/failed/interrupted/skipped_duplicate`（`0001_init.sql:259`），**无 `budget_exhausted`**；新增枚举需改迁移（本设计不采用）。落点约定：`run_record.notes`/`error_summary` 写文本标记 `BUDGET_EXHAUSTED`，状态取既有合法值（有已成功对象→`partial`；一个都没成功→`failed`）。
- **限流**：同对象最小间隔 ≥5 秒、批次内串行（并发 1）；**代码化属实现批**（当前无 runner）。
- **退避**：仅对**可重试**失败（`timeout`、`5xx`）重试，**最多 1 次**，即"首次失败 → 等待 2 秒 → 重试一次；仍失败即止"（不存在 4 秒档；原稿"2s→4s"与"最多 1 次"自相矛盾，已按 F-16 修正）。`rate_limited`（HTTP 412 / `app_code -412`）、`blocked_login`（`-101` / 登录跳转）、`failed` 一律**不重试**（适配器本身零重试，`bilibili_view.py:298`）。
- **缓存**：适配器 24h 进程内缓存只缓存内容、**不缓存失败**（`:307–333`）；缓存命中不消耗网络预算，但仍计入目标对象数（既有测试见 §9.1 R-11）。
- **停止条件**（任一即停）：预算用尽（`BUDGET_EXHAUSTED` 文本）；连续 2 次 `rate_limited`；出现 `blocked_login`；用户中断；批次时长超限。停止后写失败/部分完成审计（§4），不继续补请求。
- **未产出/未建**：适配器**不产出** `robots_disallowed`（失败分类仅 `timeout`/`rate_limited`/`blocked_login`/`failed`，`:66–87`/`:208–268`）；若未来需要该分类，须由调用方前置检查传入并在实现批补分类，**不得**写成现有能力；`search_coverage` 表未建，不在本设计范围。

## 4. 失败与重试语义（按代码改写）

`handle_import` 内部若抛异常会向上传；**接线层 `complete_known_object` 捕获 `(sqlite3.Error, AppError)` 后写失败 run 并返回**（`wiring.py:160–161`），**只有"失败审计自身写入失败"才冒泡**（`:128–131`）——原稿"异常冒泡、不吞不伪成功"与此相反，已按 F-03 修正。

| 触发 | 业务写入 | 审计（谁写） | 重试 |
| --- | --- | --- | --- |
| `ok` 首见 | 候选/需求 v1/派生证据 | `handle_import` 同事务写 `run_record(status='ok', run_type='import', source_id='s_bili')` | — |
| `ok` 同内容重放 | 仅 `last_seen_at` 刷新、`duplicate_skipped` | 同上 | — |
| `ok` 内容变化 | 新版本 `version_no+1`、旧行 `superseded_by`、为新 `demand_signal` 行建证据 | 同上；`rows_version_added=1` 而 `items_new=counts.created` | — |
| `ok` 旧版本重见 A→B→A | 只刷新旧行 `last_seen_at`，不新增版本/证据 | 同上 | — |
| **`WiringReject`**（标题>300/缺 bvid/哈希不符/记录非 `ok`） | **零业务行、无批次** | `record_failure` → `run_record(status='failed')`（`wiring.py:146–147`） | 不重试 |
| 适配器失败（限流/登录/超时/空壳/业务失败） | 零业务行、无批次 | `record_failure` → `status='failed'`，`error_summary` 原文（`:141–147`） | 仅 `timeout`/`5xx` ≤1 次 |
| `handle_import` 422（映射/校验驳回） | 无业务行；`import_batch(status='rejected')` + `import_row_result` 保留 | `complete_known_object` 补失败 run（`:162–164`） | 不重试 |
| `handle_import` 内部 `sqlite3.Error`/`AppError` | 批内业务写入随事务回滚 | **wiring 捕获 → 另写失败 run**（`:160–161`） | 不自动重试 |
| 失败审计自身写入失败 | — | **冒泡**（不吞、不递归、不伪成功，`:128–131`） | 不重试 |
| **transport 抛异常（F-08 风险）** | 现状：适配器 `self._transport(...)`（`bilibili_view.py:327`）无 try/except，异常会穿透、**不写失败 run** | 约定：transport 必须"绝不抛异常、以 `error` 字段返回"；**实现批必须在调用层加 try/except → 转失败 run**（不得吞、不得当成功），并补单测（§9.2 R-14） | — |

- **计数约定**：`run_record.items_found=rows_total`、`items_new=counts.created`、`items_dup=counts.duplicate_skipped`（`importer.py:939–945`）；`version_added`/`suspect_review`/`rejected` 只在 `import_batch.rows_*` 与行结果。
- **技术默认 0 ≠ 已观测零需求**：失败 run 因三列 `NOT NULL DEFAULT 0`（`0001_init.sql:262–264`）省略写入取 0，`error_summary`/`notes` 必须写明"未成功取得可计数结果；零为失败运行的技术默认值，不代表已观测的零需求"（`wiring.py:117–118`）。
- **失败历史保留**：不删除失败批次/行结果/run；重试是新的一行 run。

## 5. 观察时间保真（源时间优先、回退留痕、绝不用 now 覆盖）

设计依据：S3_WIRING_SPEC **§4.5**（`S3_WIRING_SPEC.md:94–110`，观察时间内部注入与断言）；§11.5 仅佐证"stray 告警返工未改动观察语义"，不是本节依据（F-01）。**必须区分两个时间字段**（F-02）：

| 字段 | 来源（现状代码） | 真实批次规则 |
| --- | --- | --- |
| `observed_at` / `observed_at_source` | **由调用方传入**；不合法/缺省时适配器用**调用时刻**回退并标 `import_time`（`bilibili_view.py:126–132`）；合法时标 `source`（`:114–123`） | runner **显式传入**（可把 `pubdate`/`ctime` 换算后作为观察时间传入）；**适配器不自行换算 `observed_at`** |
| `published_at` / `published_date` | 由接口字段 `pubdate` 经 `_iso_utc8` 换算成 UTC+8 ISO（`bilibili_view.py:108–111`、`:261`） | 仅用于 `published_at`；**不得冒充观察时间** |

1. 只有通过与适配器同级校验（带 `Z` 或 `±HH:MM`、秒精度、真实日历日）的入参才判为 `source`。
2. 回退时间戳**原样落库**（经 `internal_observation` 提示），**绝不用 DB 的 `now` 覆盖**；被拒原值只进同行 warning（`S3_OBSERVED_AT_REJECTED`）。
3. 观察时间变化**不产生新版本**（指纹只含 excerpt+title）。
4. 失败/回放场景不得用本地抓取时刻冒充发布时间或源观察时间。

## 6. 身份、去重、版本与旧证据效力（沿用既有强键）

- 身份：`n:bilibili:<bvid>`（来源名命名空间；`source_id` 仅 FK，`identity.py:73–77`）；同 bvid 不同 `data_origin` ⇒ 两条独立记录（键含 origin）。**`real`/`synthetic` 共存无法离线验证，列实现批后验**（§9.2，F-12）。
- 强键：`demand_signal UNIQUE(data_origin, source_id, identity_key, content_hash)`（`0001_init.sql:97`）；`content_hash` 为 `sha256(normalize(excerpt)+"\n"+normalize(title))` 前 16 字节/32 hex（`identity.py:34–45`）。
- 重导决策：同内容 → `duplicate_skipped`；真正新内容 → `version_no+1` + 旧头部 `superseded_by`；旧版本重见 → 只刷新历史行 `last_seen_at`、不改链。
- **旧证据效力（限定路径，F-11）**：在**导入重放路径**上不修改 `evidence.invalidated_at`/`invalid_reason`、不复活旧证据、不重建 `gate_review`；注意**失效 API 会按其语义改写这两列**（非导入行为）；**`version_added` 会为新 `demand_signal` 行建 1 条证据**（`evidence UNIQUE(demand_signal_id)`，每行至多 1 条），这不是"复活旧证据"。
- 门槛不自动升级（真实拉取成功 ≠ 任一门槛核验）；`stat` 只进 `engagement_json` 供展示，不参与指纹/门槛/排序（`bilibili_view.py:263`）。

## 7. 与既有 wiring 的复用边界

- **完全复用**：`wiring.build_row`（23 键白名单、title ≤300 拒绝、重算 `content_hash` 校验、示例域 URL、外部 supply/cost/门槛键丢弃+告警）· `wiring.complete_known_object`（无外层事务编排、显式 `client_ref=None`、注入 `run_source_id='s_bili'` 与 `internal_observation`）· `wiring.record_failure`（单事务失败审计、技术 0 语义）· `importer.validate_row`/`process_row`/`handle_import` · `BilibiliViewReader`（注入式 transport、失败分类、缓存）。
- **"两阶段"的准确含义（F-15）**：指**整体链路**——① 适配器从输入得到 canonical/原始 URL（`resolve_target`/`CANONICAL_URL`），② `build_row` 只写入**示例域 URL**（`wiring.py:87` 一步完成）；并非 `build_row` 内部两阶段。
- **真实链路唯一差异**：注入**真实 transport**。**本设计不修改 `build_row` 的 synthetic-only**（`wiring.py:58–59`）；受控 `real` 模式（`data_origin='real'` + 真实 URL 规则 + 授权闸门）须由后续**单独授权**的实现批接入，验收前真实批次不得运行。
- **notes 审计通道（F-06，当前不存在）**：成功路径的 `run_record.notes` 现固定为 `batch=<id>`（`importer.py:939–945`），失败路径为固定文本+bvid（`wiring.py:117–125`）——**没有任何注入口**。因此 A1–A9 的 `S3AUTH{…}`、请求 URL 审计与 `BUDGET_EXHAUSTED` 文本**不能写成现在可执行**；实现批须新增**内部可选 notes 注入参数**（类比 `internal_observation` 的内部参数，公共契约不暴露），或退化为"仅写批次 run 目录审计文件、不入库"。二者取舍见 §11-1。
- **已知偏差（延续）**：`request_url` 在成功路径未落任何字段（无对应列）；真实批次须在**审计通道**（上条）记录请求 URL，不得为此新增列或改契约。
- 禁止：不复制导入逻辑、不新造 DTO/框架、不加 `owns_transaction`、不在 `handle_import` 外层再开事务、不向公共 HTTP 端点暴露内部参数。

## 8. 真实批次执行前置清单（未满足即不得运行）

- [ ] A1–A9 逐项已由用户确认（人工确认项见 §2"执行方式"列）。
- [ ] **runner 级授权闸门已实现并验收**：未授权批次 transport 调用 **0 次**（§9.2）。
- [ ] 受控 `real` 模式实现批已独立验收（真实 URL 规则、`data_origin='real'`、请求 URL 审计通道）。
- [ ] 预算/频次/超时参数已填；目标清单 ≤ 上限；停止后 `notes` 文案已定（`BUDGET_EXHAUSTED` 文本 + 合法状态）。
- [ ] **transport 异常兜底**已在实现批落地（§4 末行），并有单测。
- [ ] 隔离运行目录、独立 DB、业务库前后哈希清单已备；网络证据（时间/URL/状态码/原因）的落点已定（notes 通道或批次审计文件）。
- [ ] 明确停止与回滚流程；失败按 §4 记录，不写成"无需求"。
- [ ] 用户显式授权"允许真实网络调用"的批次编号与有效期。

## 9. 验收集合（拆分：现状可验 / 实现批后验）

> 原稿把 R-07/R-08 也列为"离线最小验收"并称"一切机制"，属夸大（F-07），已拆分。下面所有"现状可验"项应引用既有断言或 fixture，**不得**声称已执行——本任务为设计稿，未运行任何测试。

### 9.1 现状可验（fixture transport，无需新功能；每 case 须**新建 reader 实例**避免 24h 缓存命中导致 transport 计数为 0）

| # | case | 步骤 | 期望（可核验） | 既有对应 |
| --- | --- | --- | --- | --- |
| R-01 | 真实摘录成功回放 | `complete(BV1us8MzPEmn, observed_at='2026-06-01T08:00:00Z')` | `ok`；transport 调用 1 次；`observed_at_source='source'` 且值等于入参；`content_hash` 与适配器一致；无 warning | `test_wiring_offline.py` s3w01；adapter 测试 |
| R-02 | 同内容重放 | 同上再执行 | `duplicate_skipped=1`；候选/需求/证据行数不变；仅 `last_seen_at` 刷新 | s3w02；compat C5 |
| R-03 | 内容变化 | 改 `desc` 后执行 | `version_added=1`、`version_no=2`、v1 `superseded_by=v2`；**`import_batch.rows_version_added=1`、`counts.created=0`、`run_record.items_new=0`** | s3w03 |
| R-04 | 旧版本重见 A→B→A | A→B→A 三次 | 不 500（HTTP 201）；不新增行/版本；链 A→B 不变；`evidence` 行与 `invalidated_*` 不变 | s3w17；compat §7.7 C6 |
| R-05 | 观察时间非法 | 传无时区字符串 | `observed_at_source='import_time'`，落库值=**适配器回退戳**（固定 clock 下确定值），**不等于 DB now**；原值以 `S3_OBSERVED_AT_REJECTED` 同行 warning 留痕 | s3w05；adapter 观察时间测试 |
| R-06 | 失败分类（不重试口径） | `rate_limited_412`/`login_redirect_200`/`timeout`/`html_shell`/`missing_62002` | 零业务行、无批次；`run_record.status='failed'`；`error_summary` 保留 `http=`/`app_code=`/`message=` 原文；**断言 transport 调用次数=1 且失败不被缓存**（"不重试"不可判别，因为适配器本就零重试） | s3w06/s3w07/s3w20；adapter 失败不缓存测试 |
| R-09 | 失败审计技术 0 | 任一失败样本 | 三计数均 0（schema 默认）；`notes` 含"技术默认值，不代表已观测的零需求" | s3w20；`wiring.py:117–118` |
| R-10 | 零网络 | 全部用例 | 模块导入不建连；非法目标 transport 0 次；`app/sources/*` 无 HTTP 客户端导入 | s3w14；adapter 测试 |
| R-11 | 缓存语义 | 同 bvid 两次调用（**同一实例**）；再跨 24h（固定 clock） | 第二次 transport 0 次（内容缓存）；TTL 过期后重新拉取；**失败不缓存** | adapter 缓存/TTL/失败不缓存测试（引用既有） |
| R-12 | `WiringReject` 失败审计 | 构造 301 字标题 / 哈希不符 / 非 `ok` 记录 | 零业务行、无批次；`run_record(status='failed')`；`error_summary` 含拒绝码 | s3w08/s3w21 |
| R-13 | 未知外来字段 | 记录附 `supply_*`/成本/门槛键 | 字段被丢弃+告警；`supply_offer/cost_item/gate_review` 零新增 | s3w18 |

### 9.2 实现批后验（当前不可执行，列为实现批交付项与验收断言）

| # | case | 为什么现在不能验 | 期望（实现批） |
| --- | --- | --- | --- |
| R-07 | 预算/停止 | 无 runner，`budget_exhausted` 非合法状态 | 预算=3、对象=5 时第 4 个**不发起请求**；`notes` 含 `BUDGET_EXHAUSTED`，状态取 `partial`/`failed`；已成功对象保留；**重试计入预算** |
| R-08 | 成功路径请求 URL 审计 | notes 无注入口（§7 F-06） | 审计通道（notes 注入或批次审计文件）记录本次请求 URL；库内不新增 URL 列 |
| R-14 | transport 抛异常 | 适配器无 try/except（`bilibili_view.py:327`） | 调用层捕获 → 失败 run（不得吞、不得当成功）；transport 调用计数可断言 |
| R-15 | 并发=1 / 最小间隔 | 无 runner | 串行调度、间隔 ≥5 秒可观测（日志时间戳差） |
| R-16 | `real`/`synthetic` 共存 | `build_row` 仅接受 synthetic | 受控 real 模式落地后，同 bvid 两 origin 为两条独立记录 |

## 10. 未实现 / 未联网 / 未执行 / 未覆盖（逐条）

- **未实现**：受控 `real` 模式（`data_origin='real'`+真实 URL 规则）、真实 transport、预算/退避/停止 runner、runner 级授权闸门、**notes/审计注入通道**、`request_url` 审计写入、外部 robots/条款前置检查、transport 异常兜底、`WiringReject` 专项 case 的执行。
- **未联网**：本任务与既有全部批次均**无真实 HTTP 请求**；现有证据只有离线回放与 `test_client` 模拟。
- **未执行**：§9.1 与 §9.2 全部未运行（设计稿）；真实批次未授权、未排期。
- **未覆盖**：发现型检索、其它来源（闲鱼/小红书）、`search_coverage`（未建表）、`source` 状态更新、S5 运行费用台账与预算保护、S6 部署与备份。

## 11. 待用户/策划者裁定

1. **notes 审计通道**：实现批新增"内部 notes 注入参数"（入库）还是"仅批次 run 目录审计文件、不入库"？两者都不改公共契约与表结构，但验收断言不同。
2. 预算耗尽的状态表达：`notes` 文本 `BUDGET_EXHAUSTED` + 既有状态（推荐，无需迁移）还是申请新枚举（需改迁移，超出本设计）。
3. 外部 robots/条款前置检查的归属与是否需要适配器新增 `robots_disallowed` 分类（当前不产出）。
4. 是否批准"受控 real 模式"实现批；批准后每次真实运行仍需批次授权（§8）。
5. 预算/频次上限（默认 ≤20 请求、≥5 秒间隔、≤10 分钟）、缓存 TTL（默认 24h）、失败不缓存是否维持。
6. 是否允许把一次真实成功写入 `source.last_success_at`（本设计默认**不允许**）。
7. `transport` 契约的最终形态：要求 transport 绝不抛异常（优先）还是由调用层兜底（两者都要有，见 §4/R-14）。

## 12. F→修改位置映射表（本轮修订）

| 编号 | 问题（评审） | 修改位置（本文件） | 修订要点 |
| --- | --- | --- | --- |
| F-01 | L60 引用 §11.5 错误 | §5 首段 + 依据行 | 改引 **§4.5（S3_WIRING_SPEC:94–110）**；§11.5 仅作"未改观察语义"佐证 |
| F-02 | `pubdate→observed_at` 混淆 | §5 表格 | 分列 `observed_at`（调用方传入/回退 `import_time`）与 `published_at`（`pubdate` 换算）；明确 runner 显式传入观察时间 |
| F-03 | "SQL 异常冒泡"与代码相反 | §4 首段 + 表格 | 改为"wiring 捕获 `(sqlite3.Error, AppError)` → 写失败 run；仅审计写入失败冒泡"；补 `handle_import 内部异常→wiring 记账` 行 |
| F-04 | `budget_exhausted` 非法状态 | §3 预算段、§4、§8、§11-2 | 改为 `notes/error_summary` 文本 `BUDGET_EXHAUSTED` + 合法状态；明确新增枚举需迁移、本设计不采用 |
| F-05 | `robots_disallowed` 无产出 / `search_coverage` 未建 | §3 末段、§1 范围外、§10 | 删除其为现有能力；明确"适配器不产出，需则由调用方前置检查传入、实现批补分类"；`search_coverage` 不在范围 |
| F-06 | S3AUTH/URL 审计无 notes 通道 | §2 引言、§7 notes 段、§8、§9.2 R-08、§11-1 | 明确"notes 注入口**当前不存在**"，只能作为实现批前置能力（内部参数或审计文件），不得写成现在可执行 |
| F-07 | §9 夸大/不可执行项 | §9 标题与拆分、§9.1/§9.2、§10 | 拆为"现状可验 R-01…R-06/R-09…R-13"与"实现批后验 R-07/R-08/R-14…R-16"；删除"一切机制" |
| F-08 | transport 抛异常绕过审计 | §4 末行、§8、§9.2 R-14、§11-7 | 约定 transport 不抛异常；实现批必须调用层兜底转失败 run 并补单测 |
| F-09 | A1–A9 无强制点/绕过口 | §2 表格"执行方式"列、§2 绕过口段、§8 | 标注各 A 项人工/代码归属；列出直调绕过口；实现批须 runner 闸门 + "未授权=0 次 transport"断言 |
| F-10 | 缺 `WiringReject` 行/case | §4 表格、§9.1 R-12 | 补 `WiringReject → record_failure(status='failed')` 行与可验 case |
| F-11 | 旧证据表述未限定路径 | §6 旧证据段 | 限定"导入重放路径"；注明失效 API 会改列；注明 `version_added` 为新行建证据 |
| F-12 | real/synthetic 共存不可离线验 | §6、§9.2 R-16 | 标注实现批后验 |
| F-13 | 缺缓存/TTL/失败不缓存/并发/重试计数 case | §9.1 R-11、§9.2 R-15、§3 预算 | 引用既有适配器缓存测试；并发与重试计数列实现批 |
| F-14 | R-03 期望值欠具体 | §9.1 R-03 | 写明 `rows_version_added=1`、`counts.created=0`、`items_new=0` |
| F-15 | "两阶段"歧义 | §7 两阶段段 | 明确为整体链路（适配器 canonical URL → build_row 示例域 URL），非 build_row 内部两阶段 |
| F-16 | 退避 2s→4s 与 1 次重试矛盾 | §3 退避段 | 改为"失败→等 2 秒→重试一次；仍失败即止" |
| F-17 | R-06"不重试"不可判别 | §9.1 R-06 | 改为断言 transport 调用次数=1 且失败不缓存 |
| F-18 | 契约引用未逐字核对 | §1 引用口径 | 明确 §0.7/§1.10–§1.12/§2.2/§3.3 仅核验存在性，实现批前确认 |
| F-19 | compat 报告引用 §4 可精确 | 首段 | 精确到 **§4.2** |

## 13. 修订记录

- v1（提交 revision 2）：初版设计（授权前置、限流退避、失败语义、观察时间、身份版本、复用边界、离线验收集合）。
- v2（本版，task-19e502b9c10f321a108addec59c235ca）：按独立评审 `S3_REAL_LINK_REVIEW.md`（F-01…F-19 与 M-01…M-09）逐条修订：引用改 §4.5；分离 `observed_at`/`published_at`；失败矩阵按代码重写并补 `WiringReject`；`budget_exhausted` 改为 notes 文本；删除 `robots_disallowed` 现有能力表述；notes 审计通道标注为**实现批前置能力、当前不存在**；§9 拆为现状可验/实现批后验并补 R-11…R-16；补 transport 异常兜底约定；A1–A9 增加"执行方式"列与绕过口说明；另补 §12 F→修改位置映射表。全文仍标注设计稿/未实现/未联网。
