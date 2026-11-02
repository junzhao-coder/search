# 贴吧链路四项业务字段现状审计（v18 / field-audit）

> 任务 `task-a48db833e21b640145ad606bca28f4eb`（计划 v18，revision 2）。
> 范围：`docs/validation/v18/field-audit`。只读现有代码与仓内产物；**未联网、未解锁站点、未改 `tools/`、`tests/`、业务库、历史 CSV 或 profile**。
> 结论口径：**已实现**＝代码路径与真实产物同时支持；**部分实现**＝有代码路径或数据源，但字段/覆盖不完整；**未验证**＝没有真实产物，或只有合成 fixture；**结构性不可得**＝现有平台证据表明拿不到（无稳定 ID、无接口）。完全没有代码路径的项在「缺口」列单独写明，避免把缺口伪装成部分实现。
> 代码行号以当前 `tools/selection/access/tieba.py`（2078 行）为准；v11 文档里的旧行号不直接复用。

**一句话**：帖子正文和顶层评论的骨架已经打通；评论点赞只在接口对照里存在，主路径恒为空且被标成“结构性不适用”；帖子点赞和楼中楼 ID 没有接；发布时间只有页面原文；覆盖状态有记录，但 `status=ok` 不能当“采全”。

---

## 0. 结论摘要（先看这 8 条）

1. **正文**：帖子正文解析已实现（`span.pb-text-wrapper[tid][order-id=0]`，真机产物有值），但端到端对 0 评论帖会丢正文行（G2）；顶层评论正文部分实现（v16 导出的 20 条评论中 2 条 `text=null`）；楼中楼正文当前不产出记录。
2. **评论**：只采顶层评论。v16 单帖滚动 18 条，页面声明 63；同帖接口对照 19 条，接口自述顶层 27；v11 三种排序并集 26/27。差距口径见 §4，不能把 18/19/26 当成“全量”。
3. **楼中楼**：DOM 里能看到 `pb-lzl-item` 节点，但当前只计数、不产记录；v11 真实页观察是“无稳定 id”，接口 `sub_post_list` 为空且没有可观察的子回复请求。**ID/父子关系结构性不可得；正文是“可读但当前丢弃”**。
4. **点赞**：帖子点赞**没有任何代码读取**；接口响应里的 `thread.agree_num=34`（v11 文档；字段名与评论 `agree.agree_num` 同源，按点赞理解，语义仍需确认）是真实但未接的来源。评论点赞只在 `parse_comments_api` 里实现（`post_list[].agree.agree_num`），主路径 `parse_comments_html` 把 `likes=None` 并列入 `not_applicable`；接口对照记录不进入导出。v16 导出的 22 行里 **likes 非空 0 行**，`missing` 2 行（帖子），`not_applicable` 20 行（评论）。
5. **发布时间**：只有页面原文，没有规范化、时区、精度或“年份未知”标记。v16 里同时出现 `10-28`、`48分钟前`、`3小时前`；v11 里还出现 `2024-08-03`、`09-30`、`10小时前`。接口路径是 epoch→UTC ISO，与 DOM 口径不同。
6. **身份与归属**：帖子 `native_id=tid`、顶层评论 `native_id=data-id` 已实现；楼中楼无 ID。父子关系只有“评论→帖子”（`parent_id=root_comment_id=tid`），`floor` 只写进证据；没有楼中楼→父评论的边。
7. **缺失/不适用**：机制存在，但同一字段在不同路径语义不一致：滚动评论的 `likes` 被标为 `not_applicable`，帖子 `likes` 却是 `missing`；评论的 `comments`（子回复数）是 `missing` 而非 `not_applicable`。下游无法区分“平台没有”与“没实现”。
8. **覆盖/停止**：`comments()` 有 `status/stop/stop_detail/checkpoint/declared/collector.finished`，但 `status=ok` 可以和 `stop=max_scrolls`、`finished=false` 同时出现；`comments()` 的 `declared` 在这版页面是 `None`（帧只带评论容器），63 是另外从详情页 `tab-全部回复` 取到的；23 列 CSV 本身不带覆盖列；0 评论帖会被 RPA 的“有评论才选帖”逻辑丢掉正文行。

---

## 1. 证据与方法

### 1.1 代码基线

| 位置 | 作用 | 本次核对点 |
| --- | --- | --- |
| `tieba.py:811-862` `_detail_fields` | 帖子详情 DOM 字段 | 正文/作者/时间/评论数/标题；**无点赞** |
| `tieba.py:865-902` `parse_thread_html` | 帖子记录 | `likes` 硬编码 `None`（887）；`not_applicable` 不含 likes（900），因此进 `missing` |
| `tieba.py:916-942` `_own_nodes` / `_comment_fields` | 单条评论字段 | 只取 author/text/published_at；**没有点赞节点扫描** |
| `tieba.py:975-1017` `parse_comments_html` | 可见滚动 DOM → 评论记录 | `likes=None`（1001）；`not_applicable` 含 likes（1012）；lzl 只计数（1013-1017） |
| `tieba.py:1034-1088` `parse_comments_api` | `page_pc` JSON → 评论记录 | `agree.agree_num→likes`（1060-1067）；证据串（1077）；`sub_post_number→comments`（1068） |
| `tieba.py:1091-1097` `declared_comments` | `tab-全部回复 (N)` | 只认 `(N)` 形式 |
| `tieba.py:1100-1118` `parse_comments_frames` | 多帧合并 | `declared` 只从传入帧取；v16 帧只有评论容器 → None |
| `tieba.py:1121-1208` `comments_api` | 接口评论 | 第 1 页 + `last_pid` 游标页；不做排序并集 |
| `tieba.py:1233-1432` `comments` | 可见滚动主路径 | 停止映射 1381-1402；status 1412-1421；declared 1426 |
| `tieba.py:1675-1729` `_rpa_interface_compare` | 接口对照 | 明确“**不作为评论来源**”（1677-1680）；记录只放 `out["interface"]` |
| `tieba.py:1968-2046` `rpa` | 全链路 | 有评论才解析详情（1970-1981）；导出行 = 详情 + 滚动（2025）；`complete` 单独记（2037-2038） |
| `records.py:23-30` | 23 列白名单 | 14 业务列 + 9 元数据列 |
| `records.py:165-189` / `244-252` | `missing` / `not_applicable` | `missing` 只装“该有但没读到”；NA 是结构性不适用 |
| `collector.py:71-79` | 完成/待续 | `finished` 只在 `end_signal`；`pending` 含 `None/pending/batch_expired/error` |
| `transport.py:502-515, 560-561, 625-639, 872-873` | 滚动帧 | 首帧整页；后续帧优先 `.pc-pb-comments` 容器；`keep_frames=False` 时只返回最后一帧 |

### 1.2 产物分层（哪些能当证据）

| 层 | 文件 | 能证明 | 不能证明 |
| --- | --- | --- | --- |
| **v16 当前代码真机** | `docs/validation/v16/tieba-impl/live/*.json/.jsonl/.csv`、`live/state/*.json` | 当前 `tieba.py` 的可见滚动、检查点、接口对照、导出字段 | 没有原始评论 HTML；接口对照记录未进 CSV；只有单帖/小样本 |
| **v11 旧代码真机** | `docs/validation/v11/tieba-*.csv`、`tieba-ai-rpa.json`、`tieba-comment-api.md` 等 | 接口路径 `agree.agree_num` 确实有值；帖子详情字段；v11 评论 DOM 解析 | 旧 `source=tieba:comments`，不等于当前主路径；raw 页面在仓库外 |
| **v18 engine trial** | `docs/validation/v18/engine-trial/fixture.html`、`report.json` | 本地 fixture 上 Playwright/nodriver 的解析一致性 | **合成页面**，不能证明真实贴吧 DOM；其 `.pb-lzl-item[data-id]` 还与真实页“lzl 无 id”的观察冲突 |
| **诊断存档** | `docs/validation/v16/tieba-impl/live/diag-thread.html` | 该次抓取的页面骨架（帖子正文、空评论容器） | 评论 DOM 一条都没有（0 个 `pb-comment-item`），不能验证评论/点赞结构 |

### 1.3 口径说明

- **v11 与 v16 的 source 不同**：v11 导出评论是 `tieba:comments`（旧路径），v16 可见滚动是 `tieba:scroll`，接口对照是 `tieba:page_pc`。同名 `likes` 在不同 source 下含义不同，不能混算。
- **“评论”拆两层**：评论正文（`text`）与评论数/子回复数（`comments`）。本审计分别看。
- **“点赞”拆两层**：帖子点赞与评论点赞。二者数据源和实现状态不同。
- **“覆盖”拆两层**：帖子级覆盖（选没选中、是否 0 评论）与评论级覆盖（18/63、19/27；楼中楼另有 18 节点 / 26 子回复数 / 37 推断，口径不同）。

---

## 2. 逐项能力表

> 状态只用四选一：已实现 / 部分实现 / 未验证 / 结构性不可得。完全没有代码路径的项，在“缺口”列直接写“未实现”；若数据源已存在于现有响应但记录未接（如帖子点赞），仍标“部分实现”并注明“代码未接”，不把它说成平台没有。

### 2.1 四项业务字段

| # | 项目 | 结论 | 代码/产物来源 | 缺口/说明 |
| --- | --- | --- | --- | --- |
| 1 | **帖子正文** | **部分实现** | `tieba.py:822-827`（`span.pb-text-wrapper[tid][order-id=0]` 拼接）、`883-891`；v16 `semantic-chain-20261101T091552Z.csv` 帖子行有正文；v11 `tieba-detail-fields.md:12-18, 51-57` | 解析器已实现；但 0 评论帖在 `rpa` 里不产正文行（G2）；`text_truncated=false` 是“取到节点即完整”的构造假设（889-891），没有“展开全文/长文截断”验证；链接只留锚文本，不保留 href |
| 2 | **评论正文（顶层）** | **部分实现** | `tieba.py:925-942`、`997-1008`；v16 `semantic-thread-20261101T091645Z.csv` 17/18 有 text；`semantic-chain-20261101T091552Z.csv` 1 条评论 text=null；v11 `tieba-comments.md:33-48` 8/8 | 只采 `.pb-comment-item[data-id]` 顶层；2/20 条 v16 评论正文为空（`supported=false`）；楼中楼正文被排除；评论不设 `text_truncated` |
| 3 | **楼中楼正文** | **部分实现** | `tieba.py:916-922`（父字段排除 lzl）、`1013-1017`（只计数）；v16 `semantic-thread...json` `lzl_without_id=18`；v11 `tieba-comments.md:13-20, 55-60` 7 个 lzl 节点 | 节点在 DOM 里，但当前不产记录；v11 真实页说 lzl 无 id，v16 只数节点；**正文可读但被丢弃**，不是平台没有 |
| 4 | **帖子评论数** | **部分实现** | `tieba.py:846-854`（`a#tab-全部回复` 取 `(N)`）、`885`；v16 单帖 `declared_page=63`、另两帖 `comments=1/2`；v11 `tieba-detail-fields.md:18, 57` | 依赖 tab 的 `(N)` 形式；v11 `tieba-wangpan-export.csv` 里 `comments` 也会 missing（该帖评论为 0 或接口首屏空，v11 未定论）；`comments()` 自己的 `declared` 在 v16 是 None（见 §4） |
| 5 | **评论子回复数（`comments`）** | **部分实现** | `tieba.py:1068-1069`（API `sub_post_number`）；滚动路径 `1001` 置 None 且不在 NA → `missing`；v11 API CSV `comments` 有 0/1/2/3/5/6 | 接口路径有值；可见滚动路径 20/20 条 `comments` 为空；DOM 的“展开N条回复”文本没有解析 |
| 6 | **帖子点赞数** | **部分实现** | `tieba.py:887`（`likes=None`）、`900`（不在 NA → missing）；**无任何 `thread.agree_num` 读取**；v11 `tieba-comments-api-entry.md:18` 记录 `thread.agree_num=34`（文档只称“其他计数”，按字段名推定为点赞，语义未单独确认）；v11 四个 thread-only CSV 的 `missing` 都含 `likes` | **代码未实现**；但接口响应里有真实值，属于“数据可得未接”，不是平台没有。DOM 是否有可读点赞节点未验证 |
| 7 | **评论点赞数** | **部分实现** | `tieba.py:925-942`（不扫点赞）、`1001`/`1012`（滚动恒 None+NA）、`1060-1067`/`1077`/`1084`（接口映射）；v11 API 26/26 唯一 id 有 likes；v16 `rpa-20261031T151558Z.json` 接口记录 likes=0；v16 导出 0/22 | **主路径未实现且误标 NA**；接口路径有真实产出，但只作对照、不进导出；真实评论 DOM 是否有可读点赞元素**未验证**（§3.3） |
| 7b | **评论点赞 DOM 可读性** | **未验证** | 生产 `tieba.py` 无评论点赞选择器；仓库无真实评论 HTML；`diag-thread.html` 0 条评论；v18 fixture 是合成页面 | 不能据 fixture 断言“有”或“没有”；需要真实带评论页面做正向/负向扫描（§3.3） |
| 8 | **帖子发布时间** | **部分实现** | `tieba.py:835-842`（`span.post-num` 原文）、`885`；v16 `10-26`、`3小时前`；v11 `09-30`、`2024-08-03`、`10小时前` | 只有原文；没有年份/时区/精度/规范化；同一字段可能是完整日期、月-日、相对时间 |
| 9 | **评论发布时间** | **部分实现** | `tieba.py:931-941`（`comment-desc-left` 下第一个 `span`）、`1025-1031`（epoch→UTC ISO）、`1066`；v16 `10-28`、`48分钟前`；v11 API CSV ISO | 两种口径不可比；位置取“第一个 span”，v11 说第二个是 IP，但没有内容校验；无精度/时区字段 |

### 2.2 身份、归属与状态

| # | 项目 | 结论 | 代码/产物来源 | 缺口/说明 |
| --- | --- | --- | --- | --- |
| 10 | **原生 ID** | **已实现（帖子/顶层评论）**；楼中楼**结构性不可得** | `tieba.py:883`/`892`（tid 来自 URL）、`992-1003`（`data-id`，`\d{6,}`）、`1052-1062`（JSON `id`）；v16/v11 全部记录有 `native_id`；v11 `tieba-comments.md:14, 24` lzl 无 id | 作者只有显示名，没有稳定作者 ID（API 有 `author_id` 但只用于查名；DOM 有 profile 链接但未存）；楼中楼没有稳定 ID，不能伪造 |
| 11 | **父子归属** | **部分实现** | `tieba.py:998-1005`（`parent_id=tid`、`root_comment_id=tid`）、`1062-1073`（`floor` 只写进 `field_evidence.parent_id`）；v11 `tieba-comments-api-entry.md:53-57`；v16 各帖评论 `parent_id` 均为所属 tid（如 `11066015202`） | 只有“评论→帖子”的边；`floor` 不是父 ID；楼中楼→父评论的边不存在；`root_comment_id` 值有设但 `field_evidence.root_comment_id` 为空（证据缺失，不影响当前 supported） |
| 12 | **缺失/不适用** | **部分实现** | `records.py:174-188`（`missing`/NA 分离）、`244-249`；`tieba.py:1001`+`1012` vs `887`+`900`；v16 CSV `missing`/`not_applicable` 分布 | 同一 `likes`：滚动评论 NA、帖子 missing；同一 `comments`：滚动评论 missing、帖子有时有值。下游无法区分“平台结构性没有”与“解析没实现”；v18 存储要求 `likes=NULL` 为未知、`0` 为真实 0，当前滚动路径做不到 |
| 13 | **停止与覆盖状态** | **部分实现** | `tieba.py:1381-1402`（stop 映射）、`1412-1421`（status）、`1426-1431`（declared/checkpoint）、`2037-2046`（complete/status）；`collector.py:71-79`；v16 `thread-20261031T153300Z.json` status=ok/stop=max_scrolls/finished=false；v16 `semantic-thread...json` partial/pending | `status=ok` 不等于采全；`comments()` 的 `declared` 是 None；23 列 CSV 无 stop/coverage；0 评论帖不产正文行（`rpa` 1970-1981）；`max_scrolls` 落进 `else` 分支（1400-1401）后 `pending=false`，所以 status 变 ok |
| 14 | **搜索候选四字段（附加）** | **部分实现（仅 tid/title）** | `tieba.py:768-778`；v11 `tieba-ai-rpa.json` candidates 只有 tid/title/wanted/blocked | 搜索/吧页候选没有正文、评论数、点赞、发布时间；这是阶段二选帖输入，不属于单帖四字段，但会影响“按点赞/时间选帖”的能力 |

---

## 3. 点赞三问（验收要求单独查清）

### 3.1 ① 可见滚动路径为什么把 `likes` 置 None 并列入 `not_applicable`

**代码事实**：

- `_comment_fields`（`tieba.py:925-942`）只返回 `author` / `text` / `published_at`，**没有点赞节点扫描**；
- `parse_comments_html` 构造评论值时 `"likes": None`（`tieba.py:1001`），并在 `not_applicable` 里写死 `"likes"`（`tieba.py:1012`）；
- 因此 `make_record` 不会把 likes 放进 `missing`（`records.py:182`），导出层看到的是“结构性不适用”，而不是“未知/未实现”；
- 生产代码 `tieba.py` 里没有任何评论点赞的 DOM 选择器；唯一出现 `[data-likes]`/`.pb-agree-num` 的地方是实验性的 `tools/selection/engine_trial/extract.py:46,62,72,84`，不在主链路。

**为什么当时这样定**：

- v11 实现评论 DOM 解析时，基于一份真实落盘页（`11066015202` 的 v2 HTML，845,152 B，**在仓库外**）做结构扫描；`docs/validation/v11/tieba-comments.md:8-20` 列出了评论计数/容器/楼中楼/作者/正文/时间/楼层 id，**没有列出点赞选择器**；同文 48 行直接写“评论没有标题、没有顶/转/赞计数”，69 行测试断言 `likes` 在 `not_applicable`。
- 但该文档没有记录“对点赞节点做过负向扫描”的证据，原始 HTML 也不在仓库（`tieba-comments.md:90` 明确“页面体仅在仓库外”）。所以这更像是**一次页面观察后的实现假设**，不是可复核的平台结论。
- v16 沿用了这个假设；v16 的所有评论导出 `not_applicable` 都含 likes（`semantic-thread...json` 分布 `{likes,reposts,title,voteup: 18}`）。

**后果**：

1. 主路径评论点赞永远是空，且不会被 `missing` 统计到；
2. 下游（包括 v18 存储的“未知 vs 0”语义）无法判断这是“平台没有赞”还是“我们没实现”；
3. 即便真实 DOM 有赞，当前代码也不会读；即便真实 DOM 没有赞，当前代码也没有留下负向证据。

### 3.2 ② 接口路径的 likes 来自哪里、真实产出覆盖如何

**来源（代码）**：

- `parse_comments_api` 从 `post_list[].agree.agree_num` 取 likes：`tieba.py:1060-1061`，转 int 在 `1067`，证据串 `json:post_list[].agree.agree_num` 在 `1077`；
- 接口评论的 `not_applicable` 只有 `title/voteup/reposts`（`1084`），所以 likes 为 None 时会进 `missing`，不是 NA；
- `comments_api` 只取第 1 页 + `last_pid` 游标页（`1121-1208`）；v11 实测游标页 `post_list` 为空（`tieba-comments-api-entry.md:22-33`），所以当前单次接口路径上限是 14 条左右。

**真实产出覆盖（只读仓内产物统计）**：

| 产物 | 行数 | likes 非空 | likes missing | likes NA | 说明 |
| --- | ---: | ---: | ---: | ---: | --- |
| v11 `tieba-comments-api-export.csv` | 14 | 14 | 0 | 0 | 旧 `source=tieba:comments` |
| v11 `tieba-comments-api2-export.csv` | 14 | 14 | 0 | 0 | 与上一文件 id 集合相同 |
| v11 `tieba-comments-union-export.csv` | 26 | 26 | 0 | 0 | 三种排序并集；**唯一 id 26/26 有 likes** |
| v11 `tieba-ai-rpa-export.csv` | 15 | 14 | 1 | 0 | 1 帖子（missing）+ 14 评论（14/14 likes） |
| v11 三个滚动导出（comments/2/3） | 26 | 0 | 0 | 26 | 旧滚动路径 0/26，全部 NA |
| **v16 全部 live CSV** | **22** | **0** | **2** | **20** | 2 帖子（missing）+ 20 滚动评论（NA） |
| v16 `rpa-20261031T151558Z.json` 的 `interface.records` | 1 | 1 | 0 | 0 | 当前代码接口对照；likes=0，未进导出 |

补充事实：

- v16 的非空 JSONL 与 CSV 同集（`semantic-thread` 18 + 两个 `semantic-chain` 各 2，共 22 行），likes 非空同样 **0** 行；`missing` 2、`not_applicable` 20。
- v11 API 的 likes 值分布是 `0,1,2,3,4`，其中 0 是真实 0（有 `json:post_list[].agree.agree_num` 证据），不是缺失；这正是 v18 存储要求的“0 与 NULL 分开”。
- v16 接口对照能拿到 19 条顶层评论（`thread-20261031T151752Z.md:20`：`per_replay=[14,14]`，`count=19`，`only_via_interface=4`），但 `rpa` 的导出行只有“详情 + 滚动”（`tieba.py:2025-2026`），接口记录留在 JSON 的 `interface.records` 里。
- `_rpa_interface_compare` 的 docstring 明确写“**不作为评论来源**”（`tieba.py:1677-1680`）；所以“接口有 likes”与“导出有 likes”是两件事。
- 帖子点赞：v11 `tieba-comments-api-entry.md:18` 记录 `thread.agree_num=34`（同帖；文档只称“其他计数”，按字段名推定为点赞，语义需确认），但 `parse_comments_api` 只读 `post_list`，`parse_thread_html` 只读 DOM，**没有任何代码把 `thread.agree_num` 写到帖子记录**。所以帖子点赞是“接口有值、记录未接”，不是“平台没有”。

**当前代码的接口覆盖（本次样本）**：

| 路径 | 本次样本顶层评论 | likes 覆盖 | 是否进导出 |
| --- | ---: | --- | --- |
| `comments_api`（第 1 页 + 游标页） | 14（游标页空） | 14/14（有值） | 否（库函数，未被 RPA 当主路径） |
| `_rpa_interface_compare`（两种排序重放） | 19（v16 实测） | 19/19（按 id 去重后） | 否（只进 `interface` JSON） |
| v11 三排序并集 | 26/27 | 26/26 | 是（v11 CSV，旧代码） |

> 结论：接口路径的 likes 映射是**真实可用**的（v11 唯一 26/26，v16 对照 1/1）；但当前主链路把它当“差额标尺”，没有当数据源，所以 v16 导出 likes 是 0/22。接口能拿到的覆盖也受“只重放两种排序/不翻第 2 页”限制，本次实测 19，不是 26。

### 3.3 ③ 真实贴吧评论 DOM 是否存在可读点赞元素

**结论：未验证（不是“已确认没有”，也不是“已确认有”）。**

离线证据检查：

| 检查 | 结果 | 说明 |
| --- | --- | --- |
| 仓库内真实评论 HTML（含 `pb-comment-item`） | **0 份** | `diag-thread.html` 是唯一 HTML 存档，但它没有评论条目 |
| `diag-thread.html` 的 `pb-comment-item` | **0** | 评论容器 `thread-container` 为空，后面直接是 `div.empty` 空态 |
| `diag-thread.html` 的 `comment-desc-left` / `pb-agree` / `data-id` | **0 / 0 / 0** | 同上；该存档不能验证任何评论 DOM |
| `diag-thread.html` 的 tid | `11156547004` | 是一个零评论页（tab 也没有 `(N)` 数字），不是 `11066015202` 那个有 63 条回复的帖子 |
| v11 真实页（`11066015202` v2，仓库外） | 8 个 `pb-comment-item`、7 个 `pb-lzl-item` | `tieba-comments.md:13-20`；文档断言评论没有赞计数，但没有留下负向选择器扫描或原始 HTML |
| v18 fixture | 有 `.pb-agree-num` / `data-likes` | `docs/validation/v18/engine-trial/fixture.html:15,32,40,47,53`；**合成页面**，不能当平台证据 |
| 生产 `tieba.py` 的评论点赞 DOM 选择器 | **无** | 只有 `engine_trial/extract.py` 的实验选择器 |

**为什么不能据 fixture 断言**：

- fixture 的 `.pb-lzl-item[data-id]`（`fixture.html:43,49`）与 v11 真实页“lzl 无任何 id 属性”（`tieba-comments.md:14`）**直接冲突**；engine trial 的“2 条楼中楼、likes 11/11”是 fixture 结果，不是贴吧结构。
- 因此，`REPORT.md` 里“likes 11/11，来源 `[data-likes]|.pb-agree-num`”只能证明本地 fixture 解析一致，不能证明真实评论有赞。

**要验证需要什么条件**（当前站点锁定、禁止请求，所以只能离线/后续）：

1. 一份**真实**帖子页 HTML，至少含 1 个 `.pb-comment-item[data-id]`（可以来自用户提供的历史抓取，或后续解锁后的可见运行；本轮不发起请求）；
2. 在每个评论条目内、**排除 `.pb-lzl-item`**，扫描候选点赞节点（`[data-likes]`、`.pb-agree*`、含“赞”文本的节点、`aria-label` 等），记录选择器、文本、数值、是否在条目内；
3. 用同一条评论的 `native_id` 与接口 `agree.agree_num` 对照；若值一致，才能确认归属与语义；若不一致，说明选择器取错（可能取到帖子赞/楼中楼赞）；
4. 若找不到，保留 `likes=missing`（未知），**不要**继续标 `not_applicable`；并在文档里留下负向扫描记录；
5. 不要用 v18 fixture、测试 HTML 或猜测的 class 代替真实页面。

> 如果产品接受“接口点赞”作为评论点赞来源，也可以不做 DOM 解析：把 `page_pc` 的 `agree.agree_num` 按 `native_id` 合并进记录，并保留 `json:post_list[].agree.agree_num` 证据、source 标 `tieba:page_pc`。但这需要明确“点赞来自接口，不是页面可见元素”，不能冒充可见采集。

---

## 4. 覆盖与停止状态对账（数字口径）

### 4.1 同一帖（11066015202）的几组数字

| 指标 | 值 | 来源 | 口径 |
| --- | ---: | --- | --- |
| 页面声明（tab） | **63** | v16 `thread-20261031T151833Z.json` `declared_page`；v11 同帖 | `a#tab-全部回复 (63)` |
| 滚动顶层评论（去重 id） | **18** | v16 `thread-20261031T151833Z.json`；`live/state/tieba-11066015202.json` | `div.pb-comment-item[data-id]` |
| 接口顶层评论（两种排序去重） | **19** | v16 `thread-20261031T151752Z.md:20` | `json post_list[].id` |
| 接口自述顶层 | **27** | v11 `tieba-comments-api-entry.md:17`；v16 对照 `declared_api.valid_post_num` | `thread.valid_post_num` |
| 接口自述总回复 | **64** | 同上 | `thread.reply_num`（含楼中楼） |
| 接口 `sub_post_number` 合计 | **26** | v16 `thread-20261031T153300Z.md:20` `lzl_sum` | 19 条接口记录的子回复数之和 |
| DOM 楼中楼节点数 | **18** | v16 `lzl_without_id=18` | `div.pb-lzl-item` 节点数，**不是去重回复数** |
| 滚动/接口集合关系 | 交集 15；仅接口 4；仅滚动 3 | v16 `REPORT-scroll.md:190` | 19 vs 18 的净差 1，但集合差是 4/3 |
| v11 三排序并集 | **26/27** | v11 `tieba-comments-union.md:17-21` | 三种排序去重 |
| v11 推得的楼中楼 | 37（64−27） | v11 `tieba-comments-union.md:49-55` | **推断**；v16 对账报告明确说 63 的构成仍未知（`REPORT-scroll.md:195-200`） |

**必须同时说的三件事**：

1. 18/19/26 是**顶层评论**的不同通道/不同排序覆盖，不是同一口径；不能相加，也不能把 26 当 63 的全量。
2. 楼中楼的 37 是 v11 用 `reply_num - valid_post_num` 推的；v16 的 26 是 `sub_post_number` 合计，18 是 DOM 节点数。三者口径不同，**不能互相加减**；v16 文档自己已把“63 的构成”列为未知。
3. 没有可核验的“到底”信号：`page.has_more`/`total_page` 在 26/27 场景仍为 `1/2`（v11 `route-interface-vs-scroll.md:57-70`）；滚动停在 `max_scrolls`，不是“到底”。

### 4.2 停止状态为什么不能只看 `status`

- `comments()` 的 `status` 规则：`partial` if `box.pending` else `ok`（`tieba.py:1412`）；`pending` 只含 `None/pending/batch_expired/error`（`collector.py:77-79`）。
- `transport.fetch_scroll` 在 `max_scrolls` 到上限时返回 `stop_reason="max_scrolls"`（`transport.py:739-741`）；`comments()` 的 `else` 分支把它原样写进 `box.stop`（`tieba.py:1400-1401`），于是 `pending=false`、`status=ok`，但 `collector.finished=false`。
- v16 `thread-20261031T153300Z.json` 就是 `status=ok, stop=max_scrolls, finished=false`；而 `REPORT-scroll.md` 明确“6 轮是 max_scrolls 上限，不是到底”（`:206-208`）。
- `rpa()` 另外用 `complete=collector.finished`（`tieba.py:2037-2038`），只有 `end_signal` 才算完成；所以 rpa 会把同一种停点标 `partial`。两个入口对同一停点的 status 语义不一致。
- `comments()` 的 `declared` 来自 `parse_comments_frames(frames)`；当前 `comments()` 固定 `keep_frames=False`（`tieba.py:1329`），transport 只返回最后一帧（`transport.py:872-873`），而最后一帧是评论容器（`transport.py:625-639`），不含 `tab-全部回复 (N)`，所以 `declared=None`。63 是 `live_scroll_small.py:121-124` 另外从 `detail_html` 解析出来的，不在 `comments()` 的返回里。

---

## 5. 四处已确认缺口与最小改进（按影响排序）

> 这四项是我按“对第一阶段验收/四字段的影响”排序的已确认缺口；不是策划者给定的固定清单。每项都给最小改动，不重写链路。

### G1｜点赞在主链路缺失且被误标“不适用”（影响最大）

**已确认事实**：

- v16 导出 22 行，likes 非空 **0**；帖子 2 行 `missing`，评论 20 行 `not_applicable`（§3.2 表）。
- 滚动评论 `likes` 硬编码 None + NA（`tieba.py:1001,1012`）；帖子 `likes` 硬编码 None + missing（`tieba.py:887,900`）；`thread.agree_num` 未读。
- 接口路径 likes 真实可用（v11 唯一 26/26；v16 对照 1/1），但只作对照、不进导出（`tieba.py:1677-1680, 2025-2026`）。

**最小改进**：

1. `parse_comments_html` 把 `"likes"` 从 `not_applicable` 移除；没有值时进 `missing`，不再伪装成“平台没有”。
2. 在 `_rpa_interface_compare` / `rpa` 里把接口记录的 `likes`（以及 `comments`）按 `native_id` 合并进滚动记录；保留 `field_evidence.likes="json:post_list[].agree.agree_num"`，不要改其他字段的来源。
3. 先确认 `thread.agree_num` 的语义（v11 只写“其他计数”），确认是点赞后写到帖子记录 `likes`，证据 `json:thread.agree_num`；仅在接口对照执行时写，未执行时保持 `missing`。
4. 合并只补“空值”或“未知”，不覆盖已有 DOM 值；若未来 DOM 点赞验证通过，DOM 值优先，接口只补缺。
5. 如果接口对照默认关闭，导出 likes 仍是未知——这是可接受的，但必须是 `missing`，不能是 `not_applicable`。

### G2｜覆盖状态与“任意帖子”可用性（含 0 评论帖丢正文）

**已确认事实**：

- `status=ok` 可以与 `stop=max_scrolls`、`finished=false` 同时出现（v16 `thread-20261031T153300Z.json`；§4.2）。
- `comments()` 的 `declared=None`；63 只在详情页解析里出现（§4.2）。
- 23 列 CSV 没有 stop/coverage 列；覆盖只在 JSON sidecar。
- `rpa()` 只在 `found and chosen is None` 时解析详情（`tieba.py:1970-1981`）；0 条评论的候选不会被选为 `chosen`，帖子行/正文/时间不会产出。v16 `semantic-chain-20261101T092221Z` 有 7 个候选、两次尝试均 0 条记录，最终 `chosen=None`、CSV 只有表头；这至少证明“0 条记录”的候选不会产出帖子行。至于该帖是真的 0 评论还是解析没读到，本轮不能区分。
- v16 `semantic-chain...` 的 `status=empty`/`stop=no_more_evidence` 是“没有候选产出记录”，不是“帖不存在”。

**最小改进**：

1. `comments()` 的 `status` 改为：只有 `collector.finished`（`end_signal`）才 `ok`；`max_scrolls/no_more_evidence/round_goal/no_target` 一律 `partial`（或新增 `incomplete` 值，但不要叫 ok）。
2. `comments()` 用首帧整页 HTML 调 `declared_comments(first_html)`，把 `declared` 补进返回；没有 `(N)` 时明确 `declared=None`。
3. `rpa()` 对首个候选总是解析 `detail_html` 并保留帖子行；没有评论时导出“帖子行 + 0 条评论 + 覆盖状态”，不要把正文丢掉。
4. 覆盖字段（declared、collected、stop、finished、interface count、only_via_interface）放进 JSON sidecar；23 列保持兼容，不加列。
5. 0 评论帖的 `status` 用 `partial` 或 `empty` 都可以，但 `comments=0` 与 `declared` 必须同时可见，不能只给一个空 CSV。

### G3｜评论/楼中楼覆盖（18/63、19/27、lzl 无 ID）

**已确认事实**：

- 滚动 18/63；接口 19/27；v11 并集 26/27；楼中楼 ID/父子不可得（§4.1）。
- 滚动评论 20/20 条 `comments`（子回复数）为空；DOM 的“展开N条回复”没有解析（`tieba.py:1001`）。
- `lzl_without_id` 统计的是所有 `pb-lzl-item` 节点（`tieba.py:1013-1017`），**代码没有检查它们是否真的没有 id**；如果某个 lzl 有 `data-id`，当前代码仍会把它算进“without id”并丢弃。这个指标名是假设，不是验证。
- v11 真实页 lzl 无 id（`tieba-comments.md:14`）；v16 只数节点，没有原始 HTML 复核。

**最小改进**：

1. 在 `_comment_fields` 或 `parse_comments_html` 里读 `div.show-more-lzl` 的文本，解析 `(\d+)` 作为该评论的 `comments`（子回复数）；没有按钮就保持 `missing`，不要用 lzl 节点数代替回复数。
2. 接口合并时用 `sub_post_number` 补 `comments`（已有解析，`tieba.py:1068-1069`）。
3. 把 `lzl_without_id` 改名为 `lzl_nodes`（或增加 `lzl_with_id`/`lzl_without_id` 两个计数），先检查 `data-id` 再分类；没有 id 的节点只计数，不伪造记录。
4. 覆盖 JSON 里记录 `lzl_nodes`、`lzl_with_sub_count_sum`、`declared`、`valid_post_num`、`reply_num`，并注明“口径不同，不可相加”。
5. 楼中楼正文若要采，按 v18 存储的“无原生 ID 观察”处理：`native_id=NULL`、`parent_known=False/父评论已知时给父 ID`、每次追加；这是下一步，不是本轮最小改动。

### G4｜发布时间只有原文，无法用于时间范围

**已确认事实**：

- v16 DOM 时间：`10-28`（月-日）、`48分钟前`、`3小时前`；v11 还有 `2024-08-03`（完整日期）、`09-30`、`10小时前`。
- 接口时间是 epoch→UTC ISO（`tieba.py:1025-1031`），与 DOM 原文不可比。
- 23 列只有一列 `published_at`；v18 存储需要 `published_at_raw` / `published_at` / `published_at_precision` 三列（`docs/validation/v18/storage/DATA_DICTIONARY.md:146-157`）。
- 评论时间取 `comment-desc-left` 下第一个 `span`（`tieba.py:931-941`），没有内容校验；v11 说第二个 span 是 IP 属地，但这是位置假设。

**最小改进**：

1. 23 列 `published_at` 保持原文（兼容），在 JSON/sidecar 或 v18 存储里加 `published_at_raw`（当前值）、`published_at_precision`（`second/minute/hour/day/relative/unknown`）、`published_at`（只有能无歧义归一化时才写，否则 NULL）。
2. 明确规则：`2024-08-03` → 日期，precision=day；`09-30` → 月-日、年份未知，precision=day、normalized=NULL；`48分钟前`/`3小时前` → precision=relative、normalized=NULL；API epoch → precision=second、UTC ISO。
3. 不要用“当前年份”静默补 `09-30` 的年份；需要年份就写 `year_known=false`，或等页面/接口提供。
4. 评论时间先做内容校验（匹配日期/相对时间模式）再取；第一个 span 不匹配就 `missing`，避免把 IP 当时间。
5. 帖子详情如果后续能从接口 `first_floor` 拿到时间，必须单独验证字段名与语义后再用；本轮没有该证据，不写。

---

## 6. 哪些结论只有真机/真实页面才能确认

> 严格说，很多“结构”问题可以用**真实页面 HTML 离线**确认；但当前仓库没有这样一份带评论的 HTML。因此分成两类：必须真机（涉及交互/网络/动态加载）与真实离线 HTML 即可（不一定要再发请求）。

### 6.1 必须真机（或至少一次真实页面会话）

| # | 待确认 | 为什么必须真机/真实会话 | 需要什么证据 |
| --- | --- | --- | --- |
| 1 | 评论 DOM 是否有可读点赞元素、选择器与值归属 | 评论是动态渲染的；fixture 不可信，仓库没有真实评论 HTML | 可见运行/真实抓取页；条目内点赞节点 + 与接口 `agree_num` 对照 |
| 2 | 帖子 DOM 是否有可读点赞元素 | 同上；目前只有接口 `thread.agree_num=34` | 帖子头部/操作栏的点赞节点 + 值 |
| 3 | 楼中楼是否有稳定 id、展开后是否有子回复请求/`sub_post_list` | 依赖点击“展开N条回复”和网络请求；v11 只观察到一次 | 点击后的 DOM/网络记录；有 id 才建父子边 |
| 4 | 当前页面 `tab-全部回复 (N)` 是否带数字、`comments()` 能否从首帧拿到 declared | 页面版本会变；v16 的 `declared=None` 与详情 63 并存 | 首帧整页 HTML + `declared_comments()` 结果 |
| 5 | 大帖滚动能否超过 18/63；虚拟列表是否回收 | 依赖真实滚动与渲染；v16 只有单帖 18 条 | 多轮 `fed`/`scroll_top`/新增 id |
| 6 | `page_pc` 第 2 页 / `has_more` 是否能作为完成信号 | 需要真实翻页请求；v11 的 `pn`/`last_pid` 替换都空 | 第 2 页响应 + `current_page/has_more` |
| 7 | 长正文是否截断/有“展开全文” | 依赖真实长帖渲染 | 长帖 DOM + 展开前后文本长度 |
| 8 | 0 评论帖是否仍渲染正文/评论数 | 依赖真实页面；代码可解析但 RPA 会丢 | 0 评论帖的详情页 + 导出 |
| 9 | API likes 与页面可见点赞是否一致 | 需要同帖同评论的两种来源对照 | 同一 `native_id` 的 DOM 值与 API 值 |
| 10 | 作者稳定 ID 是否可得（如需要按作者去重） | DOM profile 链接/API `author_id` 都可试，但当前未存 | 同一作者的多次出现 + 稳定 id |

### 6.2 用真实离线 HTML 即可确认（不必再发请求）

| # | 待确认 | 说明 |
| --- | --- | --- |
| 1 | 评论点赞节点是否存在 | 只要有一份带 `pb-comment-item` 的真实 HTML，就能做负向/正向扫描；当前仓库没有 |
| 2 | 楼中楼是否真的没有 `data-id` | v11 说没有，但 raw 页面在仓库外；用真实 HTML 复核 |
| 3 | `tab-全部回复` 的计数格式 | 当前 `diag-thread.html` 是零评论页且无 `(N)`；需要带评论的页面 |
| 4 | 时间原文的格式集合 | 现有 CSV 已给出样本，但更长尾的格式（跨年、昨天、星期）需要更多真实页 |
| 5 | 长正文截断 | 需要长帖 HTML |
| 6 | 楼中楼“展开N条回复”的文本格式 | 需要带楼中楼的真实 HTML；可用于补 `comments` |

---

## 7. 复核后与策划者初判不一致/需补充之处

| # | 策划者初判（任务上下文） | 复核结果 | 依据 |
| --- | --- | --- | --- |
| 1 | `_comment_fields` 只取 author/text/published_at（925-942） | **正确** | `tieba.py:925-942` |
| 2 | 可见滚动路径把 likes 硬编码 None 且 `not_applicable` 含 "likes"（998-1012） | **正确**；补充：`comments`（子回复数）是 `missing` 不是 NA；`lzl_without_id` 统计所有 lzl 节点，代码并未校验 id | `tieba.py:1001,1012,1013-1017` |
| 3 | 接口路径从 `agree.agree_num` 取 likes 并记证据（1039-1077） | **结论正确，行号有漂移**：当前 `parse_comments_api` 是 1034-1088，likes 在 1060-1067、证据 1077 | `tieba.py:1034-1088` |
| 4 | `diag-thread.html` 未检索到 `pb-comment-item`/`comment-desc`/`pb-agree`，存档不足以验证评论点赞 | **正确且更强**：该存档评论容器为空（0 个 `pb-comment-item`，`thread-container` 空 + `div.empty`），且 tid 是 `11156547004` 的零评论页；它不能验证**任何**评论 DOM，不只是点赞 | `diag-thread.html:2721`；全文件 0 次 `pb-comment-item` |
| 5 | v18 engine_trial fixture 用了 `.pb-agree-num`，但那是自造页面，不能当真实结构证据 | **同意**；补充：fixture 还给 `.pb-lzl-item` 加了 `data-id`，与 v11 真实页“lzl 无 id”直接冲突；engine trial 的 2 条楼中楼与 likes 11/11 都是 fixture 结果 | `fixture.html:43,49`；`tieba-comments.md:14` |
| 6 | 接口 likes 真实产出覆盖 | **需要分开说**：v11 接口唯一 26/26 有 likes；v16 当前导出 0/22；v16 接口对照 JSON 1/1 有值但不进导出。不能把“v11 接口覆盖”当成“v16 导出覆盖” | §3.2 表 |
| 7 | 帖子点赞 | 初判未提；**补充**：`thread.agree_num=34` 是真实但未接的来源；其“点赞”语义需确认（v11 只写“其他计数”）；帖子记录 `likes` 恒 missing 不是“平台没有” | `tieba-comments-api-entry.md:18`；`tieba.py:887,900` |
| 8 | 63 的构成 / 楼中楼数量 | 初判未提；**补充**：v11 的 37（64−27）是推断；v16 对账报告明确说 63 构成未知；接口 `sub_post_number` 合计 26、DOM 节点 18，口径不同，不能相减/相加 | `REPORT-scroll.md:190-200`；`tieba-comments-union.md:49-55` |
| 9 | `status` 与覆盖 | 初判未提；**补充**：`status=ok` 可与 `max_scrolls`/`finished=false` 并存；`comments()` 的 `declared=None`；0 评论帖会丢正文行 | §4.2；`tieba.py:1412,1970-1981` |
| 10 | v11 路线建议 | v11 `route-interface-vs-scroll.md` 建议“接口为主、滚动兜底”；v16 当前代码反转为“滚动主路径、接口仅对照”。这是 v16 的可见性选择，但直接导致点赞从主路径消失；不是策划者判断错误，是需要在 v18 明确取舍 | `route-interface-vs-scroll.md:51`；`tieba.py:1677-1680` |

---

## 8. 复核方法（只读、离线、可复跑）

以下命令只读仓内文件，不发请求、不改数据。输出应与表中数字一致。

```python
import csv, json, pathlib

# 1) v16 live CSV：22 行，likes 非空 0，missing 2，NA 20
root = pathlib.Path("docs/validation/v16/tieba-impl/live")
rows = []
for p in sorted(root.glob("*.csv")):
    rows += list(csv.DictReader(p.open(encoding="utf-8", newline="")))
print("v16 rows:", len(rows))
print("likes non-null:", sum(1 for r in rows if r["likes"]))
print("likes missing:", sum(1 for r in rows if "likes" in r["missing"].split(";")))
print("likes NA:", sum(1 for r in rows if "likes" in r["not_applicable"].split(";")))

# 2) v11 API 唯一 id：26/26 有 likes
api = {}
for name in ("tieba-comments-api-export.csv",
             "tieba-comments-api2-export.csv",
             "tieba-comments-union-export.csv"):
    p = pathlib.Path("docs/validation/v11") / name
    for r in csv.DictReader(p.open(encoding="utf-8-sig", newline="")):
        api.setdefault(r["native_id"], r)
print("v11 api unique:", len(api))
print("v11 api likes:", sum(1 for r in api.values() if r["likes"]))

# 3) diag HTML：评论元素 0
t = pathlib.Path("docs/validation/v16/tieba-impl/live/diag-thread.html").read_text(
    encoding="utf-8", errors="replace")
for m in ("pb-comment-item", "comment-desc-left", "pb-agree", "data-id"):
    print("diag", m, t.count(m))
```

预期输出：

```text
v16 rows: 22
likes non-null: 0
likes missing: 2
likes NA: 20
v11 api unique: 26
v11 api likes: 26
diag pb-comment-item 0
diag comment-desc-left 0
diag pb-agree 0
diag data-id 0
```

> 说明：`likes non-null` 用字符串真值判断，`"0"` 会被算作有值（这是对的：0 是真实值）；v16 没有 likes 值，v11 API 有 0 值。

---

## 9. 边界与未做

- 本轮**未联网**，未对贴吧发起任何请求，未解锁站点锁（v16 已因 `text:扫码登录` 落锁；v16 `REPORT-semantic.md:115-122`）。
- 未修改 `tools/`、`tests/`、业务库、历史 CSV、profile、DSH 配置；未提交 git。
- 未新增任何真实页面抓取；`diag-thread.html` 是既有存档，且是零评论页。
- 未把 v18 fixture、测试 HTML、v11 文档里的旧行号当成平台事实；所有“已确认”都给出代码行/产物文件，所有“未验证”都明确说缺什么证据。
- 本审计只回答“现状能力与缺口”，不提出整体计划变更；若需要把接口点赞合并进主链路，涉及行为/口径选择，应由策划者决定后再实施。
