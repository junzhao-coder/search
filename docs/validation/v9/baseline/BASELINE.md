# V9-0A 当前实现基线（只读核对）

> 任务：`task-3740c52d554a8d2832734912356f8570`（revision 2，计划 v9）；范围仅 `docs/validation/v9/baseline/`。
> 核对时间：2026-10-25 12:55–13:08 UTC+8（05:00–05:08Z）；工作区 `D:\桌面\two`。
> 方式：静态阅读 + 只读进程/HTTP 探测；未启动/重启/停止 5015，未调用应用工厂，未打开/写入 `instance/app.db` 或 `workbench.sqlite3`，未改产品文档、源码、依赖、配置、浏览器 profile、业务/工作单库、CSV/冻结快照。
> 技能/工具说明：本会话函数表未暴露 `skill` 调用器；目录中 `ponytail` 原则按“最小、复用、不重复实现”人工套用，未声称已加载工具；网页/GitHub/X 不在本任务范围（由其他执行者负责）。

## 0. 结论摘要

1. **四项证据门槛已有真实实现，但只在原业务核心 `app/core`**：`GATES=("demand","supply_distribution","cost","platform_policy")`（`app/core/state.py:9`），入口 `record_gate()`（`app/core/gates.py:311-363`），不是 README 旧表格里的“未实现”。
2. **七项就绪在独立工作台 `tools/workbench`**：`readiness()` 的 7 个 key 为 `specs/supply/license/sample/cost/platform/copy`（`tools/workbench/readiness.py:46-83`），服务端推导，无“标记完成”入口。
3. **两者没有一对一映射，也没有现成桥接**：工作单表虽有 `gate_demand/gate_supply_distribution/gate_cost/gate_platform_policy` 四列（`tools/workbench/workflow.py:128-131`），但只有默认值，代码中无写入/读取这些门的路径；`readiness()` 不读它们。四门槛是候选/证据级，七项是工作单材料级。
4. **两项旧任务均为 `revision 14 / paused`**：live-check 与 D3 的历史提交仍在；当前 5015 **无监听、无工作台 python 进程**，`curl /healthz` 与 `/pick` 均 exit 7（connection refused）。历史 PID 99804/96704、106184/104620 不是当前在线证据；未恢复、未改状态。
5. **当前代码与 D3 的守卫哈希一致**：`instance/app.db e073f828…`、`CONTRACT.md 826c24cc…`、`scores.csv ab0c3546…`、`sources.csv 13679b60…`；但测试未在本任务重跑，历史 d1/d3 的 334/218 只能作历史证据。
6. **V9 不能直接复用七项当作四项**：七项里的 `cost_known=yes`、`platform_evidence` 非空、`selected_supply_id` 非空都不等于四项证据充分；反过来 `demand` 在七项中没有对应项，`specs`/`copy` 在四项中没有对应门。

**校正两条容易误判的事实**：① D1 的 synthetic 9/9 步与 d1/d3 的 334 项全量测试说明“受控合成链路已验证”，不等于真实经营数据或真实平台链路已验证；**缺真实经营 ≠ 缺 synthetic 链路验证**。② D08 四门槛不是“未实现”：`app/core/gates.py` 已有 G1–G4 admission、TTL、downgrade 与候选状态派生；本次核对未重跑测试，但不能据此断言原业务核心未实现。

## 1. 模块—代码/接口—历史验证—当前核对—v9 可复用点—缺口

| 模块 | 真实代码/接口（输入→输出） | 历史验证 | 本次核对 | v9 可复用点 | 缺口 |
| --- | --- | --- | --- | --- | --- |
| 来源注册/采集 | `source` 表（channel/access_mode/access_verified，`app/storage/migrations/0001_init.sql:4-20`）；种子仅 manual/xianyu/xiaohongshu/bilibili（`:285-294`）；`BilibiliViewReader`（`app/sources/bilibili_view.py:297`）、`run_real_batch`（`app/sources/real_link.py:215-409`） | S3 受控 real 2 bvid（README 历史）；D 链路 334；本次不联网 | 只有 B 站适配器；闲鱼/小红书仅 `manual_import` 种子；`wiring.py` 只允许 synthetic（`:52-59`） | 复用 source/run_record 的审计、B 站 reader、失败 run 记录 | **10 平台组能力矩阵不存在**；抖音/贴吧/微博/知乎/淘宝/京东/拼多多无 adapter；无每平台字段/分页/限流登记；无采集批次游标/暂停 |
| 导入/规范化/去重 | CSV/JSON 列定义 `app/core/importer.py:29-57`；`handle_import()` `:803-991`；身份 `demand_identity_key`/`candidate_identity_key`（`app/core/identity.py:73-84`） | d1/d3 的 334 全量测试；D1 synthetic 9/9 步 | 支持 demand/supply/cost 一体导入、版本/重复/证据派生；`data_origin` 仅 `real/synthetic`（`:51`；schema CHECK 见 `0001:57,92,116,151,180`；`0002:13,41`） | 复用导入校验、重复/版本、证据派生；V9 原始证据保留可借其 batch/row_result | **无 `imported` 来源类型**；无跨平台同义/语义去重；身份键是 source+native/url/title，平台名进入身份；无父评论/楼中楼字段；无 V9 统一信号表 |
| 四项证据门槛 | `app/core/state.py:9`；`_check_demand` `gates.py:139-156`，`_check_supply` `:159-187`，`_check_cost` `:190-217`，`_check_platform` `:220-240`；`record_gate()` `:311-363`；`effective_gate_status` `state.py:158-178`；`recompute` `:181-210` | 334 测试覆盖；D1 使用工作台七项，不是 app core 四门；无独立四门端到端报告 | **已实现且为写入路径**：候选+证据/G2/G3/G4 → `gate_review` 行 + 候选 `status`；TTL 90/30/30/180 天（`gates.py:14`）；G2 要求三许可 yes、sample 非 none 且有 note、条款证据；G3 要求当前 G2、无未知角色/basis、采购绑定 G2；G4 仅 xianyu 且版本一致 | **直接复用** `record_gate`/`recompute`/`GATES`，不要重写四门；V9 桥接应读其状态而非用七项推导 | 独立 V9 选品库没有 candidate/evidence/gate 外键桥；工作单四列是死字段（见 §3.3）；`data_origin` 无 imported，V9 导入无法诚实落 origin |
| 七项就绪 | `readiness(record)` `tools/workbench/readiness.py:46-83`；证据字段 `:28-34`；`save_evidence` `:260-299`；`normalize_evidence` `:210-257` | D1 6/7→7/7，未就绪导出 409；D3 工作台 218/项目 334；d1 日志 334 | 7 项服务端推导；`overall_ready` 仅全 7 ok；无“一键就绪”；`FORBIDDEN_FIELDS` 拒 ready/verified（`workflow.py:47-50`） | **直接复用** `readiness`、`save_evidence`、导出/发布守卫；V9 品类卡最终落到工作单材料 | 7 项不是证据质量：`supply` 仅 selected ID，`license` 仅三值，`sample` 仅状态，`cost` 允许 `cost_known=yes` 无金额，`platform` 仅非空字符串；不能与四门互换 |
| 货源/许可/样品 | 业务核心 `add_supply`/`update_supply`（`app/core/supplies.py:24-126`）；工作台候选 `supply.py:56-207`；选中同步/失效 `:248-290` | D1 候选→选源→改许可使 sample/cost 失效；D3 218/334 | 两套货源：业务核心 `supply_offer`（candidate 级）与工作台 `workorder_supply_candidate`（workorder 级）；工作台选中会清空 sample/cost 并 revision+1 | 工作台侧复用候选/选择/失效逻辑；业务核心侧复用许可三档和 G2 规则 | **两套未桥接**；工作台候选的 sample 字段与 business `sample_checked` 语义不同；无 V9 货源目录跨轮台账 |
| 成本/情景 | `costs.py:10-13` 角色/基础；`state.py:10` required roles、`:94-120` unknown；`scenario.py` 计算；`workbench/readiness.py:72-74` 的浅检查 | D1 反馈/成本；d1 项目 334；D1 改许可→成本失效 | 业务核心有完整成本角色/未知不为 0/情景；工作台 readiness 只看 `cost_minor>0` 或 `cost_known=yes` | 复用业务核心成本/情景和 `base_unknown_components`；工作台保持七项的门槛说明 | 两套成本口径；工作单无 `cost_item` 明细；V9 若只用 workbench 会丢失成本完整性；未知成本不得当 0 |
| 文案/导出 | 业务核心 `drafts.py:14-16,72-124`；工作台 `readiness.py:118-138` buyer 白名单、`:303-335` 导出记录、`:458-469` 失效；UI `app.py:1333-1363` | D1 GET 200/200、导出记录 0→1、重复 dedup；D3 218/334 | 工作台 copy 版本/导出戳/买家白名单有真实守卫；导出前 `overall_ready`，内部标记泄漏 409 | 复用工作台 copy version/export stamp；不要再建第三套文案 | 业务 `draft` 与工作台 copy 两套；V9 新品类没有 copy 字段/版本初始化；无自动从需求卡生成完整文案（可后续模板） |
| 发布/反馈/复盘 | 工作台 `workorder_publish` 表（`workflow.py:171-180`），`save_publish`/`publish_changed`（`readiness.py:396-445`）；业务核心 `feedback.py:14-17,37-121,124-164`；review `reviews.py:41-63,96-128` | D1 发布 200、非法 400；复盘 CSV `review.py` rc=0 但四指标 na；D1 问题 #6：发布数据不自动进 feedback CSV；D2 修反馈表头 | 工作台有状态/URL/sold_count；业务反馈有询单/成交/退款/支出/人工时间；`actual_net_per_order_minor`/`actual_complete` 在 S2 仍为 NULL/只读（`feedback.py:3-5,15-16`） | 复用工作台发布回填 + 业务 feedback 事件；复盘脚本/CSV 作为导入/导出参考 | **发布回填与 feedback 未自动连接**；实际净利未计算；工作单无 query/退款/人工时间明细；V9 需要新增关联而非重建 |
| UI/运行 | 工作台 `NAV` 三栏（`app.py:41`），`/pick` 组卡（`:949-1005`）、`/source`/`/copy` 向导（`:1015-1048`）；`run.py:18` 5015；app dash 文件只读（`app/dash/data.py:13-25`，`routes.py:35-73`） | D3 三栏改名/可点、5 张截图；live-check 历史在线 | **5015 当前未监听**；无工作台 python 进程；dash 是文件型只读，不是 5015 | 复用三栏、工作单向导、readiness/export 页面；V9 在 `/pick` 增加“开始一轮” | 无“开始一轮/暂停/取消/历史批次”；`/pick` 仍从 `scores.csv` 组卡；`workflow.derive_gaps`/`stages_state` 是旧文案（`:334-361`） |
| 文档/测试/进程 | `PRODUCT.md:32` D08；`README.md:58` 317、`:94-108` 能力表；`DEVELOPMENT_PROGRESS.md:12` S2 口径；`DEVELOPMENT_PLAN.md:3` v2 | d1/d3：项目 334；workbench 218；D3 218/334；live-check 历史 PID | 未重跑测试；5015 exit7；当前 guard 哈希与 D3 一致；workflow.sqlite3 49,152 B，app.db 241,664 B（只读元数据，不打开） | 复用测试隔离/日志格式、guard 核对方法 | 根文档仍为 v2/S2 旧口径（README 317、交互未实现等）；V9 文档尚未落盘；无当前运行实例 |

## 2. 四项证据 ↔ 七项就绪的准确映射

### 2.1 四项（D08）在代码中的名字

`PRODUCT.md:32` 的四项是“需求、货源及分发条件、成本、对应平台发布条件”。代码门名是：

| D08 证据 | 代码 gate | 判定函数 | 输入 | 输出/失败 |
| --- | --- | --- | --- | --- |
| 需求 | `demand` | `_check_demand` `gates.py:139-156` | candidate + `evidence_id`（类型 demand、source_url/excerpt/observed_at、demand_signal 属于本候选） | 通过则 `gate_review` verified；缺证据/类型/信号/卖家广告 → 422 details |
| 货源及分发条件 | `supply_distribution` | `_check_supply` `:159-187` | candidate + supply_id、三许可（commercial/redistribute/resale）、sample_checked+note、条款证据（supply_distribution） | 任一许可非 yes、sample=none/无 note、缺条款证据 → 422 |
| 成本 | `cost` | `_check_cost` `:190-217` | candidate + 当前有效 G2 + 活跃 base cost 行 | 任一 required 角色/basis 未知、无 fact+依据/assumption_note、采购未绑 G2 → 422 |
| 平台发布条件 | `platform_policy` | `_check_platform` `:220-240` | candidate + platform=xianyu、applies_to_version、platform_policy 证据、当前 G2 | 平台非 xianyu、缺版本、证据类型错、版本与 G2 format_version 不符 → 422 |

`record_gate`（`:311-363`）在 verified 时执行 admission、算 `min(verified_at+TTL, evidence.expires_at)`（`:64-72`）、写 `gate_review`、必要时对 G2 变更做 G3/G4 downgrade（`:277-308`），最后 `apply_status`。TTL：`demand 90 / supply_distribution 30 / cost 30 / platform_policy 180` 天（`:14`）；供应另受 30 天 `last_checked_at` TTL（`state.py:12,45-56`）。候选 `testable` 的条件是四门 effective 全 verified 且无 blocking review（`state.py:193-200`）。

### 2.2 七项（工作单材料）的真实 key

`readiness.py:46-83` 固定 7 个 key：

| key | 判定（输入→ok） | 行 |
| --- | --- | --- |
| `specs` | `name/use_case/deliverable/target_platform` 非空 | 53-57 |
| `supply` | `selected_supply_id` 非空 | 59-60 |
| `license` | 三许可值均在 `YES`（`yes/true/1/允许/可`） | 62-66 |
| `sample` | `sample_status in (verified/已核对/ok)` | 68-70 |
| `cost` | `cost_minor` 为正整数 **或** `cost_known=yes` | 72-74 |
| `platform` | `platform_evidence` 非空 | 76-77 |
| `copy` | `copy_status=final` 且 `copy_version` 非空 | 79-80 |

`overall_ready = all(7)`（`:82`）。`save_evidence` 只接收 `EVIDENCE_FIELDS`（`:28-34`），拒绝 `ready/verified`（`workflow.py:47-50`），每项保存走 revision 乐观锁（`readiness.py:260-299`）。因此七项是**工作单材料完整性**，不是证据来源、原始链接、观察时间或 G1–G4 的证明。

### 2.3 映射与边界（不得合并）

| 四项 | 对应七项 | 是否等价 | 边界/反例 |
| --- | --- | --- | --- |
| `demand` | **无** | 否 | `specs` 只查名称/用途/交付物/平台，不要求需求原话、来源、时间；需求证据缺失仍可 `specs` ok。 |
| `supply_distribution` | `supply` + `license` + `sample`（拆成 3 项） | 否 | 七项 `supply` 只查 ID；`license` 不检查条款证据；`sample` 只有状态；G2 还要求 sample_note 和 supply_distribution 证据。三 OK 可能 G2 仍失败。 |
| `cost` | `cost` | 否 | 七项接受 `cost_known=yes` 即使没有 `cost_minor`；G3 要求 required roles/bases 无未知、fact+证据或 assumption_note、采购绑 G2。 |
| `platform_policy` | `platform` | 否 | 七项只查非空字符串；G4 要 platform_policy 证据、仅 xianyu、版本与 G2 `format_version` 一致。 |
| 无 | `specs` | 否 | `specs` 无四门对应；它只描述“要做什么商品”。 |
| 无 | `copy` | 否 | `copy` 是文案定稿+版本，不是四项证据。 |

**结论**：四门通过 → 候选 `testable`；七项通过 → 工作单 `overall_ready`。二者是不同对象、不同字段、不同失败语义，不能用一个的 `yes` 冒充另一个；UI 应并列展示并解释“需求线索/可测试/材料就绪/真实经营”的差别（V9 计划 P6）。

### 2.4 工作单四列是“死字段”，旧缺项文案也已过期

- `workorder` 表有 `gate_demand/gate_supply_distribution/gate_cost/gate_platform_policy` 四列，默认 `'unverified'`（`workflow.py:128-131`）。
- 在 `tools/workbench/*.py` 中这四个列只在建表/禁止字段列表出现，**无 UPDATE/读取门状态的业务路径**；`readiness()` 不读它们。
- `derive_gaps()` 无条件加“四门槛均未核验…”并保留“B2/B3/B4/B5 待实现”（`workflow.py:334-352`），`stages_state()` 只把 `select` 设为 done（`:356-361`）；这些是旧阶段文案，不能作为当前四门/七项状态。
- 因此 V9 桥接时：**不要把七项结果写进 workorder.gate_* 冒充四门，也不要用 derive_gaps 的静态文本判断门已过**；要么读取原业务 candidate/gate_review，要么明确“四门未接入”。

## 3. 数据库、schema、来源标签、导入器

### 3.1 默认/环境路径

| 库/路径 | 代码 | 当前证据 |
| --- | --- | --- |
| 业务库默认 | `app/core/config.py:17`：`APP_DB_PATH`，默认 `ROOT/instance/app.db`（`ROOT` 见 `config.py:8`） | `instance/app.db` 存在，241,664 B，mtime 2026-10-09T11:53Z，sha256 `e073f828…`；本次只读元数据/哈希，未打开、未迁移 |
| 业务 schema | `app/storage/db.py:11-13`（迁移目录）、`:48-83`（ensure_schema）；`app/storage/migrations/0001_init.sql`、`0002_draft_feedback.sql` | 代码支持最大 schema 2（迁移文件最大前缀 2）；未启动应用、未读业务库内容 |
| 工作单库默认 | `tools/workbench/workflow.py:34-35`：`WORKBENCH_WORKFLOW_DB` 或 `runtime/workflow.sqlite3`；密钥 `WORKBENCH_SECRET_FILE` 或 `runtime/secret_key` | `workflow.sqlite3` 49,152 B，mtime 2026-10-23T15:31Z，sha256 `8ae79c58…`；`secret_key` 32 B；未打开/未写 |
| 工作台端口 | `tools/workbench/run.py:18`：默认 `127.0.0.1:5015`；`:55-67` 只探测/不杀进程 | 当前无监听、无工作台 python；5015 历史日志 mtime 2026-10-24T14:26Z |
| 工作台数据来源 | `tools/workbench/workflow.py:31-32` 读 `scores.csv`/`opportunity_sourcing_top10.csv`；`app/dash/data.py:13-25` 读多个文件（含登录 JSONL） | 均为文件，不是 V9 独立库；`app/dash` 无 DB 写入 |

### 3.2 schema 事实

- 业务核心 schema 共 14 张表：`0001` 的 `source/import_batch/candidate/demand_signal/evidence/supply_offer/cost_item/gate_review/review_item/import_row_result/run_record/idempotency_key`（12 张）与 `0002` 的 `draft`/`feedback`（2 张）。
- `candidate` 有 `category/use_case/delivery_form`，无标准品类 ID/别名/语义要素；`demand_signal` 有 `source_id/native_id/url/excerpt/signal_kind/observed_at/...`，`evidence` 有 `evidence_type/fact_kind/source_url/excerpt/observed_at/expires_at`；`supply_offer` 有 `license_*`/`sample_checked`；`cost_item` 有 role/basis/value_kind；`gate_review` 有 gate/seq/status/evidence/supply/ttl；`feedback` 有 kinds/amounts/refund/manual_time（表定义见 `0001:41-237`、`0002:3-51`）。
- 无 V9 表：无 `v9_signal`/`v9_category`/`v9_category_alias`/`v9_run_cursor`/`v9_workorder_link`；无跨平台父内容/评论关系；无“本轮新发现/旧品类更新/待判重”持久化状态。

### 3.3 来源标签

- `data_origin` 在 candidate/demand_signal/evidence/supply_offer/cost_item/draft/feedback 都是 `CHECK (data_origin IN ('real','synthetic'))`（`0001:57,92,116,151,180`；`0002:13,41`）；`importer.DATA_ORIGINS={"real","synthetic"}`（`:51`）。
- `source.channel` 仅 `manual/xianyu/xiaohongshu/bilibili/other`，`access_mode` 仅 `manual_import/auto_read/official_api/unknown`（`0001:4-20`）；种子 4 行（`:285-294`）。
- `wiring.py` 明确只接受 synthetic（`:52-59`），`real_link.py` 有受控 real 的 B 站入口（`:35-37,96-108,215-409`）。
- **V9 目标 `real/synthetic/imported` 三态当前无法在业务核心落库**；若强行把 imported 写成 real/synthetic 会失真。V9 独立库可以有自己的 `origin_kind`，但桥接到 app core/四门时必须显式处理，不能静默映射。

### 3.4 导入器输入/输出

- 输入：CSV/JSON `BASE_COLUMNS` + `DEMAND_COLUMNS` + `SUPPLY_COLUMNS` + `COST_COLUMNS`（`importer.py:29-48`）；`handle_import(conn,cfg,fmt,body,filename,mode,format_version,client_ref,run_source_id,internal_observation)`（`:803-991`）。
- 输出：`import_batch`/`import_row_result`/run_record，以及 candidate/demand_signal/evidence/supply_offer/cost_item；重复/版本/校验在 importer 内；G1–G4 不自动通过（新 candidate 默认 pending，见 `state.recompute`）。
- **不要**调用 `ensure_schema`/应用工厂做基线核对；本次只读代码和守卫哈希。

## 4. 两项 paused 历史任务

### 4.1 `task-89750fe829b47487de293e313e64acf2`（live-check）

- 当前 metadata：`revision 14 / status=paused / planVersion=8`，执行者 `session-c1428bc7…`，有历史提交、无 feedback。
- 历史 rev3 提交内容：5015 在线且最新；监听 PID 99804、父 96704、启动 2026-10-24 21:42:19；`/healthz` 200 + `app_id=workbench-opportunity/1`；导航/继续区块/`/copy` platform_evidence/`/worksheet` 文案提示均在线；证据 `docs/validation/product-workflow/live-check/REPORT.md`。
- 当前核对：**该在线结论不适用于现在**。5015 无监听，`curl /healthz` exit 7；历史 PID 不是当前 PID。旧任务保持 paused，不恢复、不修改。
- 需独立复核：若用户之后启动 5015，需重新核对 `/healthz`、实际监听 PID、三栏/`/copy`/`/worksheet` 特征；不能引用旧 PID 或旧提交。

### 4.2 `task-6d21477af9a03bed985ab794eab947ad`（D3）

- 当前 metadata：`revision 14 / status=paused / planVersion=8`，执行者 `session-c1428bc7…`，有历史提交、无 feedback。
- 历史 rev3 提交内容：三项改名「选品/找货源/写文案」；无 wo 时 `/source`/`/copy` 200 引导页；`tests.test_wizard` 66 OK、`workbench_all` 218 OK、`project_full` 334 OK；截图 5 张；部署父 106184/监听 104620；证据 `docs/validation/product-workflow/d3/REPORT.md`、`shots/`、`logs/`。
- 当前核对：代码/守卫与 D3 记录一致（app.db `e073f828…`、CONTRACT `826c24cc…`、scores `ab0c3546…`、sources `13679b60…`）；但 **5015 不在线**，未重跑 66/218/334；旧任务保持 paused，不把历史提交当本次验收。
- 需独立复核：重跑 workbench/项目测试；启动后进行三栏/无 wo 引导/移动菜单页面核对；旧 PID 106184/104620 不作当前证据。

## 5. 5015 当前探测

- `Get-NetTCPConnection -State Listen`：5015/5000/19387 均无监听；仅 3553（DSH GUI）监听（`raw/5015_process.json`）。
- `curl http://127.0.0.1:5015/healthz`：exit **7**，HTTP 000（connection refused）；`/pick`：exit **7**（`logs/5015_health.log`、`logs/5015_probe.log`、`raw/5015_http.json`）。
- 无 `tools\workbench\run.py` 的 python 进程；`workbench-5015.log`/`.err.log` 最后修改 2026-10-24，属于历史运行记录，不是当前进程。
- **未启动/重启/停止任何服务**；当前状态就是“未运行”。历史 live-check 的“在线”只作历史证据。

## 6. 最小 V9 模块边界与数据桥接建议（只建议，不改）

### 6.1 边界

1. **V9 独立选品库**（新 SQLite，建议 `tools/selection/runtime/selection.sqlite3`，`V9_DB_PATH` 可覆盖）：存原始信号、批次/游标、平台能力、品类台账、跨轮去重、待判重、旧品类更新；不复用业务库表硬塞。建议最小表：`v9_run`、`v9_signal`、`v9_signal_raw`（证据文件引用）、`v9_category`、`v9_category_alias`、`v9_category_evidence`、`v9_workorder_link`。字段至少含 `platform/native_id/parent_id/url/excerpt/published_at/captured_at/metrics_json/origin_kind/batch_id/status`；`origin_kind` 显式 `real/synthetic/imported`。
2. **四项门槛只复用 `app/core`**：不要在新库重写 G1–G4。V9 品类确认建单后，若要四门状态，读取关联 candidate 的 `gate_review`/`effective_gate_status`；没有 candidate 就显示“四门未接入”，不得用七项推导。
3. **七项只复用 `tools/workbench/readiness.py`**：新品类卡填 `name/use_case/deliverable/target_platform`，货源走现有 `supply.py`，成本/许可/样品/平台/文案按现有字段；不要把七项复制到 V9 库，也不要把七项写回 `workorder.gate_*`。
4. **桥接点**：新增 `create_from_v9(snapshot)`（工作台侧）——不经过 `scores.csv` 的 `validate_source`；校验必填规格、`snapshot_json` 保存 `v9_category_id/v9_signal_ids/v9_origin/captured_at`、代表 URL；`source_item_id` 用品类 ID 而非类别名占位；`submit_key` 用 category+snapshot 哈希幂等；成功后写 `v9_workorder_link`（V9 库）+ workorder（工作台库），失败用 outbox/重试，不双写强事务。
5. **结果面**：`/pick` 增加“本轮新发现/旧品类更新/待判重/待核验”，最多 5 条重点；完整池分页；新品类确认才建单；旧品类新增证据单列，不重复推荐。现有 `/source`/`/copy` 保留，不重建三栏。

### 6.2 受影响文件（仅建议）

| 文件/路径 | 建议 | 风险 |
| --- | --- | --- |
| 新 `tools/selection/`（模型/采集/去重/迁移） | 新库、批次/游标、品类台账；独立迁移表 + 备份 | 新代码，不碰业务库；避免与 workbench `runtime` 混用 |
| `tools/workbench/workflow.py` | 增加 `create_from_v9`/snapshot 校验；保留 `create` 旧路径 | 工作单库隐式 schema（`init_schema` ALTER，无版本表）；需加显式迁移/备份，测试隔离 |
| `tools/workbench/app.py`、`views_wizard.py` | `/pick` 接 V9 结果；“开始一轮/暂停/继续/取消”；保留三栏 | 不破坏现有 7 项/导出守卫；避免重复 `derive_gaps` 旧文案 |
| `tools/workbench/readiness.py`、`supply.py` | 复用，不重写；必要时只加只读链接 | 改动会破坏就绪/导出守卫，优先级最低 |
| `app/core/gates.py`、`state.py`、`api/routes.py` | 如四门桥接：只经 API/函数复用；不复制 | 业务核心 schema CHECK/权限；不要在 V9 直接写 `gate_review` |
| `app/core/importer.py`、`app/storage/migrations/0003_*.sql` | 仅在批准“imported origin/四门桥接”时改；需表重建/迁移 | SQLite CHECK 不能简单 ALTER；影响 7 表 + 导入器/测试；风险最高，默认不做 |
| `app/dash/data.py` | 可选的只读展示桥；不写库 | 目前是文件型只读；不要变成第二套 V9 存储 |
| `tests/v9/*`、`tests/workbench/*` | 隔离临时库；两轮去重/暂停恢复/坏行/迁移 | 不得指向 `instance/app.db` 或 `runtime/workflow.sqlite3` |

### 6.3 迁移/隔离风险

- **双库无跨库事务**：workorder 建单与 V9 link 必须用 outbox/幂等重试；失败不能留下“有单无证据/有证据无单”且无标记。
- **业务 schema 的 `data_origin` 只有 real/synthetic**：把 imported 强映射为 real 会污染“真实采集”语义；增加 imported 需迁移 7 张表 CHECK + importer + 测试，默认不在 V9-0 做。
- **工作单 schema 无版本表**：`workflow.init_schema` 用 `CREATE IF NOT EXISTS` + `ALTER`，多次启动隐含改表；V9 新表必须独立显式迁移/备份，不能靠 `init_schema` 当迁移。
- **工作单四门列是死字段**：不要把七项结果写进 `gate_*`；否则会制造“已过四门”的假象。
- **5015 当前未运行**：部署/重启属于后续批次，本任务不启动；历史 PID 不可复用。
- **守卫**：`instance/app.db`、`CONTRACT.md`、`scores.csv`、`sources.csv` 当前哈希与 D3 一致；任何 V9 迁移/测试必须保持这些文件不变。

## 7. 缺口清单与下一步

**已确认可复用**：四门 `record_gate/recompute`；七项 `readiness/save_evidence`；工作台 copy/export/publish 守卫；workorder 三栏/向导；B 站受控采集与审计；测试隔离/guard 方法。

**必须先补的 V9-0/1 缺口**：

1. 平台能力矩阵（10 平台组）与统一信号/批次/游标 schema；当前 `source.channel` 只有 5 个值，且无 douyin/tieba/weibo/zhihu/taobao/jd/pdd adapter。
2. 跨平台/跨轮品类台账与三层去重；当前 identity 是 source-scoped，`candidate.category` 不是标准品类。
3. 四门与七项的桥接策略；先解决 `imported` origin 与“四门未接入”的显示，不能把七项当四门。
4. `create_from_v9` 与 workorder snapshot/link/outbox；当前 `workflow.create` 只接受 scores/自制来源。
5. 主动开轮/暂停/继续/取消/历史批次；当前只有 `/pick` 静态组卡，无 run 控制。
6. 发布回填→feedback/复盘自动关联；当前发布与 feedback 是两套（D1 问题 #6），实际净利未计算。
7. 文档/测试更新：README 317/旧交互口径、`DEVELOPMENT_PROGRESS` v2/S2、`derive_gaps/stages_state` 旧文案；需 V9 文档任务单独处理。

**建议顺序**：先做 V9-1 平台 registry/小样本 + V9-2 signal schema/有界 run（隔离库）；再做 V9-3/4 品类卡/台账；最后 V9-5 桥接 workorder/四门；四门桥接若需 imported schema 迁移，另列影响与备份，不在本批实施。

## 8. 证据与未验证项

**已读证据**：`PRODUCT.md`、`README.md`、`DEVELOPMENT_PLAN.md`、`DEVELOPMENT_PROGRESS.md`；`app/core/{config,gates,state,evidence,supplies,costs,feedback,reviews,drafts,importer,identity}.py`；`app/storage/{db.py,migrations/0001,0002}`；`app/sources/{wiring,real_link,bilibili_view}.py`；`app/dash/{data,routes}.py`；`tools/workbench/{workflow,readiness,supply,app,run}.py`；d1/d2/d3/live-check 报告与日志；两项 paused Flow 任务 metadata/submission。

**实际运行/探测**：仅 `curl 5015 /healthz`、`/pick`（各 exit 7）、端口/进程查询、文件哈希/元数据读取；没有启动应用、没有打开业务/工作单库、没有跑测试、没有网络采集。`CHECKS.json` 记录路径、时间、命令/结果/未执行项。

**未验证**：当前全量测试是否仍 334/218（未重跑）；5015 页面特征（未运行）；真实 10 平台能力（未做）；V9 新代码（不存在）；imported origin 迁移（未做）；四门桥接（未实现）。历史 d1/d3 的 334/218 是历史证据，不是本次重跑结果。
