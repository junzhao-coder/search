# v18 单帖采集存储：数据字典

> 适用范围：`tools/selection/storage`（v18 第一阶段的最小隔离存储）。
> 本文描述**已实现**的字段与语义；未实现的部分集中在最后一节，不当作已完成能力。
> 旧模块 `tools/selection/access/records.py`、既有业务库、账本与历史导出均未修改。

## 1. 定位与隔离

- 只写调用方显式传入的 SQLite 文件（`Storage(path)` / CLI `--db`），不读也不改
  `tools/selection/access/runtime/*.sqlite3`、平台账本、历史 CSV/JSONL。
- 一个库可放多个平台；**平台不是隐式上下文**，每条记录都带 `platform`。
- 只保存采集结果与必要元信息：正文、评论数、点赞数、发布时间、来源、父关系、
  采集时间、覆盖/停止状态。不保存 cookie、账号、原始 HTML。
- 标准库实现（`sqlite3`），无新增依赖。

## 2. 库身份与 schema 识别

| 项 | 值 |
| --- | --- |
| 应用标识 `PRAGMA application_id` | `1446066176`（`0x56313800`，"V18\0"），**不随 schema 版本变化** |
| schema 版本 `PRAGMA user_version` | `3` |
| 当前版本表/索引 | `runs`、`run_stops`、`items` + 4 个具名索引 |

打开库时的判定顺序（全部是**只读检查**，在 `journal_mode`/DDL 之前）：

| 库的状态 | 行为 |
| --- | --- |
| 空库（无对象、version 0） | 正常创建，并写入应用标识与版本 |
| 本模块 v3：应用标识匹配、版本 3、schema 逐列/索引核对通过 | 直接打开 |
| 本模块 v2：schema 与 v2 逐列/索引核对通过 | 原地迁移到 v3，再打开 |
| 本模块 v1：schema 与 v1 逐列/索引核对通过 | 原地迁移到 v3，再打开 |
| schema 已是当前版本，但应用标识/版本缺失或落后 | 只补 header（stamp），不碰表 |
| 应用标识是别的值 | 拒绝 `not_a_v18_store` |
| 非空且 schema 不可验证（含 user_version=1、同名表不同列、仅 views/triggers、陌生表） | 拒绝 `not_a_v18_store`；**字节、表集合、journal_mode 均不变** |
| 本模块应用标识但 schema 不可验证 | 拒绝 `schema_mismatch` |
| 版本高于当前 | 拒绝 `schema_version_mismatch:N`，不写 |
| 不是 SQLite 文件 | 拒绝 `not_a_v18_store`，不写 |

schema 验证是逐列比对（列名/类型/非空/默认值/主键顺序）、逐索引比对
（唯一性、部分索引、列顺序、`WHERE native_id IS NOT NULL` 谓词）以及对象集合
精确匹配；不是"有同名表就接管"。

**迁移**（仅对验证通过的旧库，在一个事务内完成，失败整体回滚，迁移后再次核对
v3 schema 才提交）：

- v1 → v3：补 `parent_known`（旧评论行一律回填 1，保持旧语义）、`resumes`、
  `run_stops`（把旧库当前 `stop_reason/complete` 补成历史第一条，时间用
  `updated_at`，是近似值）、`recheck_explicit`；把旧库里**无法由身份/父级解释**的
  `needs_recheck=1` 迁成显式复核，再按新规则重算 `needs_recheck`。
- v2 → v3：补 `recheck_explicit`，同样把无法解释的 1 迁成显式复核并重算。

## 3. 表 `runs`（一次采集 = 一行）与 `run_stops`（停止历史）

### `runs`

| 列 | 类型 | 空值语义 |
| --- | --- | --- |
| `run_id` | TEXT PK | 调用方给或自动生成（`<platform>-<12 hex>`）；续跑必须传回同一个 |
| `platform` | TEXT NOT NULL | 平台标识（如 `tieba`） |
| `target_native_id` | TEXT NULL | 被采集帖子的原生 ID；未知时可由首批记录补上 |
| `started_at` | TEXT NOT NULL | 首次开始时间（UTC ISO8601） |
| `updated_at` | TEXT NOT NULL | 最近一次写入/停止时间 |
| `stop_reason` | TEXT NULL | **当前**状态：NULL = 运行中或进程中断；取值见第 7 节 |
| `complete` | INTEGER 0/1 | **当前**是否完成；只有 `end_signal` 才允许为 1；续跑时清零 |
| `declared_count` | INTEGER NULL | 页面声明的评论数；未知为 NULL，不写 0 |
| `note` | TEXT NULL | 自由说明（不参与判定） |
| `resumes` | INTEGER NOT NULL | 被续跑过几次（`begin_run` 遇到已停止的运行 +1） |

### `run_stops`（只追加）

| 列 | 类型 | 语义 |
| --- | --- | --- |
| `stop_id` | INTEGER PK | 自增 |
| `run_id` | TEXT NOT NULL → `runs.run_id` | 所属运行 |
| `stop_reason` | TEXT NOT NULL | 本次停止原因 |
| `complete` | INTEGER 0/1 | 本次停止是否可验证完成 |
| `at` | TEXT NOT NULL | 停止时间 |
| `note` | TEXT NULL | 停止说明 |

`finish_run()` 每次都会追加一行历史，并同步 `runs` 的当前状态；
`begin_run()` 续跑时把 `runs.stop_reason` 清空、`complete` 清零、`resumes` 加一，
但**不动历史**。因此运行中 `run_summary()` 一定是 `pending=True`、`complete=False`，
同时能通过 `previous_stop_reason` / `stop_history` 看到旧的停止原因。

`run_summary(run_id)` 返回：`items_first_seen`、`thread_items`、`declared_count`、
`complete`、`pending`、`resumes`、`previous_stop_reason`、`stop_history`。
**`thread_items == declared_count` 也不自动等于取全**：只有 `complete=1`
（即可验证结束信号）才算结束；其余如实报部分/未知。

## 4. 表 `items`（帖子或评论 = 一行）

### 4.1 身份与关系

| 列 | 类型 | 语义 |
| --- | --- | --- |
| `item_id` | INTEGER PK | 本地自增；不是平台 ID，不对外当身份 |
| `platform` | TEXT NOT NULL | 平台 |
| `kind` | TEXT `post`/`comment` | 帖子 / 评论 |
| `native_id` | TEXT NULL | 平台可核实的原生 ID；**没有就 NULL，绝不合成** |
| `id_verified` | INTEGER 0/1 | `native_id IS NOT NULL`；由 CHECK 强制 |
| `parent_native_id` | TEXT NULL | 直接父级原生 ID；父级未知或帖子为 NULL |
| `parent_kind` | TEXT `post`/`comment` NULL | 父级是帖子还是评论；未知为 NULL |
| `parent_known` | INTEGER 0/1 NULL | 父级是否已知；**评论必须显式给出**，帖子为 NULL |
| `post_native_id` | TEXT NULL | 所属帖子原生 ID；帖子填自身 ID（无 ID 时为 NULL） |
| `url` | TEXT NULL | 回查地址；旧导出规则会去掉查询串（保留 `q`） |

父级是**三态**，不存在"缺省就是顶层"：

| 场景 | `parent_known` | `parent_native_id` | `parent_kind` | 自动复核 |
| --- | --- | --- | --- | --- |
| 已知顶层评论 | 1 | 帖子 ID | `post` | 否 |
| 已知楼中楼（父 ID 已知） | 1 | 父评论 ID | `comment` | 否 |
| 父评论未知 | 0 | NULL | NULL | 是 |
| 帖子本身 | NULL | NULL | NULL | 无 ID 时是 |

- 构造 `Item` 时：给父 ID 视为已知；**没给父 ID 且没显式说"已知顶层"就是未知**，
  不会默认成帖子的直接子评论。要表达顶层请显式 `parent_known=True`。
- 未知父级仍保留 `post_native_id`，可回查所属帖子；`children(post_id)` 不会把它
  当成直接子评论，`thread(post_id)` 仍能取到它。
- **防重键**：`(platform, kind, native_id)`，由部分唯一索引
  `ux_items_identity ... WHERE native_id IS NOT NULL` 强制。同 ID 不同平台、
  同 ID 的帖子与评论都是不同内容。
- **无原生 ID 的内容**：`native_id=NULL`、`id_verified=0`、`needs_recheck=1`，
  正文/作者/时间/父关系/URL 原样保留供回查。这类行是**观察**，每次写入都追加
  一行，不按文本相似度合并（避免把两条不同评论合成一条）；续跑时同一内容可能
  出现多条观察，这是有意的"不丢数据"语义，`save()` 的 `without_native_id`
  会如实计数。
- **旧 23 列导入**（没有三态标记，按证据处理）：
  - 评论有 `parent_id`：视为已知父级；等于所属帖子 ID 时为已知顶层；
  - 只有 `root_comment_id`、没有 `parent_id`：父级**未知**，保留帖子归属；
  - 两者都没有：连帖子归属都不确定，直接报错，不猜。
- **旧 v1/v2 存储库**：旧版本没有三态（v1）或没有显式复核标记（v2），迁移按
  第 2 节规则回填；不替旧数据编造"未知"。

### 4.2 业务字段

| 列 | 类型 | 空值语义 |
| --- | --- | --- |
| `title` | TEXT NULL | 帖子标题；评论不适用（NULL） |
| `text` | TEXT NULL | 正文/评论正文；读不到为 NULL |
| `text_truncated` | INTEGER 0/1 NULL | 0=完整，1=截断，NULL=未知；**有值必须有正文** |
| `author` | TEXT NULL | 作者显示名；读不到为 NULL |
| `likes` | INTEGER NULL | **NULL=未知，0=确实为 0**；负数拒绝 |
| `comments_count` | INTEGER NULL | 评论数/子评论数（页面或接口声明值）；未知 NULL |

### 4.3 时间（三字段一组）

| 列 | 类型 | 语义 |
| --- | --- | --- |
| `published_at_raw` | TEXT NULL | 页面原始时间文本（如 `10-31 12:34`），不加工 |
| `published_at` | TEXT NULL | 规范化时间（UTC ISO8601）；归一化不了就 NULL |
| `published_at_precision` | TEXT NULL | `second`/`minute`/`hour`/`day`/`relative`/`unknown`；**必须伴随规范化时间** |
| `collected_at` | TEXT NOT NULL | 首次采集时间（UTC ISO8601） |
| `last_seen_at` | TEXT NOT NULL | 最近一次看到该内容的时间 |

旧记录导入时，`published_at`（原文）落到 `published_at_raw`，规范化列与精度列
留 NULL——不假装已经归一化。

### 4.4 采集与复核元信息

| 列 | 类型 | 语义 |
| --- | --- | --- |
| `first_run_id` / `last_run_id` | TEXT NULL → `runs.run_id` | 首次/最近一次写入的运行 |
| `needs_recheck` | INTEGER 0/1 | **计算值**：显式复核，或无原生 ID，或评论父级未知 → 1 |
| `recheck_explicit` | INTEGER 0/1 | **用户显式复核要求**；与自动原因分开记账，父级升级不会清掉它 |
| `source` | TEXT NULL | 采集通道标签（如 `tieba:scroll`） |
| `evidence_json` | TEXT NULL | 旧记录的 `field_evidence`（字段→来源标签）JSON |
| `not_applicable_json` | TEXT NULL | 旧记录的 `not_applicable` 列表 JSON（导出时按实际值过滤） |

复核语义：

- `recheck=True`（`Item` 参数）→ `recheck_explicit=1`，`needs_recheck=1`；
  之后普通重采、父级升级都不会悄悄清掉它。
- 仅因无原生 ID / 评论父级未知触发的复核是自动原因：父级升级为已知后
  `needs_recheck` 自动归 0，`recheck_explicit` 保持 0。

## 5. 写入、合并与续跑语义

- **一次 `save()` = 一个事务**：中途异常（含冲突）整批回滚，已提交记录不受影响；
  不存在"写了一半"的批次。
- **有原生 ID**：按 `(platform, kind, native_id)` 查找；不存在则插入，存在则
  合并（`inserted`/`updated` 计数如实返回）。
- **冲突（明确报错 + 回滚）**：
  | 错误 | 触发条件 |
  | --- | --- |
  | `post_conflict:<id>` | 同一内容 ID 的新记录声称属于另一个帖子 |
  | `parent_conflict:<id>` | 已有已知父级，新记录又给出另一个已知父级 |
  | `run_target_mismatch:<id>` | 记录所属帖子与运行的 `target_native_id` 不一致 |
  | `run_target_conflict` | 运行目标未知时，一批记录里出现两个不同帖子 |
  | `platform_mismatch` | 记录平台与运行平台不一致 |
  | `unknown_parent_with_parent` | 声明父级未知却给了父 ID（输入自相矛盾） |
- **合并规则**：
  - 不可变：`native_id`、`kind`、`platform`、`collected_at`、`first_run_id`；
  - 后写的**已知值**覆盖先写的已知值（标题、作者、点赞、评论数、URL、source、
    evidence 按字段合并）；
  - **未知值不会抹掉已知值**（NULL 不覆盖）；
  - 父级：未知 → 已知允许升级；已知 → 未知保留已知；已知 → 另一个已知父级 = 冲突；
  - `recheck_explicit` 只增不减（显式要求一直保留）；`needs_recheck` 每次按
    "显式 + 当前身份完整性"重算；
  - `not_applicable` 与实际值冲突时**实际值优先**：导出时把已有值的字段从不适用
    列表里剔除，保证 `missing` 与 `not_applicable` 互斥（存储保留旧记录带来的
    原始提示，不擅自改写旧语义）。
- **字段证据随实际采纳的值走**：采纳新值时写新来源；新值没有证据时清掉旧来源
  （不把旧值的来源贴到新值上）；拒绝新值（如截断摘要不覆盖完整正文）时保留旧值
  和旧来源；值没变时保留旧来源，旧来源缺失才用新证据补。正文、时间组、点赞、
  标题、作者、URL、父级升级都按同一原则，避免来源串换。
- **时间三字段按一组合并**（见第 6 节），新原文不会和旧的规范时间/精度拼在一起；
  时间组被替换时，`published_at` 的来源也随实际保留值更新或清空。
- **文本三态合并**（见第 6 节）：旧无正文时新正文一律保留；已知完整不被截断摘要
  覆盖；同一文本的完整性可从"未知"升级为已知。
- **run target**：运行已有目标时，每条记录的所属帖子必须等于目标；目标未知时
  从本批记录补上（一批只能有一个帖子，否则 `run_target_conflict`）。补目标与
  写记录在同一事务里，冲突会一起回滚。
- **续跑**：用同一个 `run_id` 调 `begin_run()`（幂等，平台/目标不一致会报错），
  再把检查点里的记录重新 `save()` 一遍即可；原生 ID 相同的行不会重复，
  无 ID 的观察行会再追加一条（有意的、不丢数据的语义）。
- **中断**：进程在 `finish_run()` 之前退出时，`stop_reason=NULL`、`complete=0`，
  `run_summary()` 报 `pending=True`；已提交条目全部保留。
- 没有删除接口；修正靠重新采集后合并或后续版本迁移。

## 6. 无原生 ID、未知值与三态合并

| 情形 | 存储表现 | 导出表现（23 列） |
| --- | --- | --- |
| 有原生 ID | `id_verified=1` | `native_id` 有值，`supported` 视证据而定 |
| 无原生 ID | `native_id=NULL`、`id_verified=0`、`needs_recheck=1`、每次追加 | `native_id` 空、`supported=false`、`missing` 含 `native_id` |
| 父级未知 | `parent_known=0`、`parent_*` 为空、保留 `post_native_id` | `parent_id` 空，`missing` 含 `parent_id`；`root_comment_id` 保留 |
| 点赞未知 | `likes=NULL` | `likes` 空，`missing` 含 `likes`（除非旧记录把它标为不适用） |
| 点赞为 0 | `likes=0` | `likes` 为 `0`，不在 `missing`，也**不会**留在 `not_applicable` |
| 旧记录标了不适用、后来采到值 | 值写入；不适用提示保留在库 | 导出剔除该字段的不适用项（实际值优先） |
| 时间读不到 | 三列均 NULL | `published_at` 空 |
| 时间只有原文 | `published_at_raw` 有值、规范化列为 NULL | `published_at` 用原文 |

**时间组合并**（原文 / 规范化 / 精度）：

| 旧值 | 新值 | 结果 |
| --- | --- | --- |
| 原文 A + 规范 T1 + 精度 P1 | 只有原文 B（B≠A） | 原文 B，规范/精度清空（不把 B 和 T1 拼在一起） |
| 原文 A + 规范 T1 + 精度 P1 | 只有原文 A | 保持原组（同一原文，旧规范仍成立） |
| 原文 A + 规范 T1 + 精度 P1 | 规范 T2 + 精度 P2 | 整组替换（原文按新值，没给就清空） |
| 原文 A + 规范 T1 + 精度 P1 | 规范 T1（无原文/精度） | 保留旧原文与精度（同一规范时间） |
| 任意 | 只有精度、没有规范时间 | 输入被拒绝（精度必须伴随规范时间） |

**文本截断三态合并**：

| 旧 | 新 | 结果 |
| --- | --- | --- |
| 无正文（NULL/空） | 截断摘要（1） | **保留摘要正文并标 1**（唯一可得的正文不能丢） |
| 无正文（NULL/空） | 完整正文（0） | 保留正文并标 0 |
| 完整（0） | 截断（1，文本不同） | 保留完整正文（搜索摘要不能覆盖详情页正文） |
| 截断（1） | 完整（0，文本不同） | 用完整正文替换 |
| 未知（NULL） | 截断（1，文本不同） | 保留旧文本（不能证明新的更好） |
| 同一文本、完整性未知 | 同一文本、截断/完整 | 只更新完整性标记（未知 → 已知） |
| 同一文本、已知完整 | 同一文本、截断 | 保留"已知完整"（不降级） |
| 完整（0） | 文本变化、完整性未知 | 用新文本，完整性记 NULL（如实） |

## 7. 停止原因词表与续跑状态

| 值 | 含义 | 可续跑 | 允许 `complete=1` |
| --- | --- | --- | --- |
| `end_signal` | 可验证的结束信号 | — | 是（唯一） |
| `cancelled` | 用户取消 | 是 | 否 |
| `paused` | 暂停超时 | 是 | 否 |
| `risk` | 平台风险信号（403/429/验证码/墙） | 保留停点 | 否 |
| `batch_expired` | 批次窗口到期（检查点） | 是 | 否 |
| `pending` | 证据不足/未结束 | 是 | 否 |
| `error` | 传输/解析异常 | 是 | 否 |
| `records` | 拿到记录后的正常停 | 是 | 否 |
| `no_more_evidence` | 连续无新增/无位移 | 是 | 否 |

未知字符串直接 `ValueError("stop_reason_invalid:...")`；新增原因先登记再使用。
`begin_run()` 续跑会清空当前 `stop_reason/complete` 并保留历史；
`finish_run()` 只允许 `complete=True` 配 `end_signal`。

## 8. 与既有 23 列导出的兼容映射

23 列即 `access/records.py` 的 `EXPORT_FIELDS`（14 个业务列 + 9 个元信息列）。
兼容导出复用 `records.normalize_record()` 与 `records.write_records()`，
旧模块零修改。

| 存储列 | 23 列 | 说明 |
| --- | --- | --- |
| `native_id` | `native_id` | 无 ID 为空 |
| `kind='post'` | `type='thread'` | 与旧贴吧记录用词一致；评论为 `comment` |
| `parent_native_id` | `parent_id` | 帖子为不适用；父级未知时为空并进 `missing` |
| `url` | `url` | 按旧规则清理查询串 |
| `title` | `title` | 评论为不适用 |
| `text` | `text` | |
| `published_at` 或 `published_at_raw` | `published_at` | 优先规范化值 |
| `collected_at` | `collected_at` | 首次采集时间 |
| （无） | `voteup` | 未采集，按不适用 |
| `comments_count` | `comments` | 声明数，未知为空 |
| `likes` | `likes` | 未知为空，0 为 `0` |
| （无） | `reposts` | 未采集，按不适用 |
| `author` | `author` | |
| `post_native_id`（评论） | `root_comment_id` | 帖子为不适用 |
| — | `missing` | 由 `normalize_record` 重算；未知父级会出现在这里 |
| `not_applicable_json` | `not_applicable` | 导入的旧记录保留原列表；**导出时剔除已有实际值的字段** |
| — | `supported` | 需原生 ID + 证据 + 标题或正文 |
| — | `author_redacted` | 本存储不脱敏，固定 `false` |
| `evidence_json` | `field_evidence` | 只保留已知前缀的标签 |
| `source` | `source` | 未知标签按旧规则写 `redacted` |
| — | `evidence_missing` / `evidence_rejected` | 由 `normalize_record` 规则产生 |
| `text_truncated` | `text_truncated` | 三态，未知时该键不出现 |
| `parent_known` / `recheck_explicit` | （无） | 23 列没有对应列；未知父级只能从 `parent_id` 空 + `missing` 看出 |

**缺失/不适用互斥**：导出前按当前实际值过滤 `not_applicable`，一个字段只会处于
"有值 / 缺失 / 不适用"三者之一。

**23 列没有平台列**：`export_compat()` 必须显式传 `platform`，避免不同平台的
同 ID 混进同一份 CSV。

## 9. 未实现与已知边界

1. **无 ID 父评论的本地父指针**：楼中楼父评论没有稳定 ID 时，`parent_known=0`，
   只保留帖子归属，不按文本猜父级；等能拿到稳定 ID 再扩展本地父指针。
2. **v1 迁移无法恢复旧父级语义**：v1 没有三态，迁移一律回填为"已知"；
   旧库若曾把未知父级默认成帖子，迁移后无法区分。
3. **值变化快照**：不保存点赞/正文的历史快照；后写已知值覆盖先写已知值，
   只保留首次采集时间与最后见到时间。需要趋势时再按采集时点加表。
4. **无 ID 行不自动升级**：事后发现同一内容有原生 ID 时，不做自动合并，
   需人工核对后处理（避免错误合并）。
5. **删除/修正接口**：当前没有，靠重采合并或后续 schema 迁移。
6. **平台列缺失于 23 列**：兼容导出按平台分别生成。
7. **真实平台未运行**：本模块测试全部离线，没有发起任何真实站点请求；
   旧 live 证据的覆盖（顶层 18 条、楼中楼无稳定 ID）不代表全量。
8. **`declared_count` 不参与完成判定**：页面声明数与实际条目数可能口径不同，
   不把相等当取全。
9. **只支持 v1/v2 → v3**：更高版本直接拒绝（`schema_version_mismatch`），
   不尝试降级；迁移是原地写，拒绝的陌生库不会被改动。
