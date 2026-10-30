# V10 抖音接入调研：可复用底座与最小实现建议

> 任务：`task-d230ae6753d5aa8266ecfc944d25fe8c`（revision 2，计划 v10）。
> 范围：只写 `docs/validation/v10/douyin-research/`。
> 结论日期：2026-10-29（Asia/Shanghai）。
> **未访问抖音站点、未登录、未使用真实账号、未发微博请求、未安装依赖、未改业务代码/数据。**
> 本报告不是“抖音已接入”的证明；外部项目只做静态阅读，未运行其测试，未在真实抖音页面验证。

## 0. 结论

1. **本地底座可复用，但抖音适配器为零。** `tools/selection/access` 已有传输、预算、记录白名单、登录轮询、诊断形状、站点预算和 `weibo/zhihu` 两个适配器；抖音只存在于人工导入的 URL 规则、工作台下拉项和“未接”矩阵行。
2. **最小可行顺序**：先用**人工导入 + doctor + 本地 export**（完全无网络）跑通抖音 `native_id`/记录/导出；再做**浏览器辅助的单页 search/detail**；`comments` 先只读可见第一页，分页和 API 签名均不先实现。
3. **不建议直接引入 catbus 或 MediaCrawler。** catbus 是 MIT，但 Node 22 + 12 个运行时依赖、签名/设备风控和 CLI；MediaCrawler 是 **NON-COMMERCIAL**，且 Playwright + Node + `a_bogus` 体系。两者只作为机制参考，不 vendor、不作为本项目运行时依赖。
4. **X 渠道本次无结果**：agent-reach 的 twitter-cli 无完整显式凭据，`site:x.com` 搜索没有返回 X 原帖；不以 X 内容支撑任何结论。
5. **不绕过验证码/风险锁**：所有路径遇到 403/429、验证码、登录墙即停并锁；不做自动验证码、设备指纹伪造、Cookie 注入或重试绕过。

## 1. 本地可复用项（逐项）

| 模块 | 现有能力 | 抖音可复用 | 缺口 |
| --- | --- | --- | --- |
| `tools/selection/access/__init__.py:3-5` | 明确“共享骨架：durable budget + URL/record hygiene；解析按平台” | 方向正确 | 没有抖音模块 |
| `access/transport.py:62-107` | `RefusedTransport`（无 socket）、`PublicHttpTransport`（不跟随重定向） | 离线默认、失败即数据 | 抖音网页/接口不是纯静态 HTTP，不能把 public-http 当可用路径 |
| `access/transport.py:124-159` | `AuthenticatedBrowserTransport`：复用 profile、单 loop、总 deadline、host 白名单 | **最适合抖音的底座**；只换 `allowed_host_suffix` 和 `SiteProfile` | 需新增抖音 `SiteProfile`（链接形状/容器/wall/empty/UA） |
| `access/transport.py:345-394` | `SiteProfile` 把站点差异收敛为 shape_rules、selectors、wall/empty markers、UA | 可直接复用；无需复制浏览器 loop | 抖音 selectors/URL 尚未观察，全部是假设 |
| `access/browser.py:48-59` | `available()` 检查 nodriver/Chrome；不启动浏览器 | doctor 可直接复用 | 抖音没有已验证的登录标记 |
| `access/browser.py:77-175` | `wait_for_login`：poll 配额、五态、risk lock、可注入 `signed_in_js` | login 可复用；用户扫码，代码不填凭据 | 当前默认 `SIGNED_IN_JS` 是知乎选择器；抖音必须传自己的 JS，且未验证 |
| `access/records.py:22-31,64-79,158-171` | 字段白名单、URL 去 query/token、`field_evidence`、`missing/supported` | export/detail 可直接复用 | `SOURCE_RULES` 只有 `zhihu:`/`weibo:`（`:39-44`），需加 `douyin:` |
| `access/diagnostics.py:28-49,67-80` | 按站点统计 href 形状、拒绝数、assumed selectors | 加一个 `SITES["douyin"]` 即可 | 目前只有 zhihu/weibo；抖音路径/宿主未登记 |
| `access/platform_budget.py:42-49,193-206` | 站点级 ledger、批次授权、15s 间隔、5 条记录、300s 窗口、平台锁 | 可复用 `PlatformLedger(site="douyin", path=...)` | `DEFAULT_PATH` 固定为 `platform_weibo.sqlite3`；必须显式给抖音路径，不能复用微博账本 |
| `access/weibo.py:1-20,76-92,252-321,379-507,860-869` | 适配器范式：site profile → doctor/login → 三个 parser → 共享 export | **最佳模板**；抖音照此新增一个 `douyin.py` | 微博的 selectors/端点也是假设；不能把微博行为当抖音证据 |
| `access/zhihu.py:460-484,782` | doctor 只读 cookie 名称；export 白名单 | export 直接复用；doctor 结构可参考 | 抖音 cookie 名称未验证，不能硬编码 |
| `tools/selection/manual.py:10-18,21-33,72-83` | `PLATFORMS` 已含 `douyin`；URL 规则 `/video/(\d+)`；人工导入 `origin_kind=imported` | **现在就能用的最小入口** | 只认 `/video/<id>`；不认 `/note/`、`?modal_id=`、`v.douyin.com` 短链；无评论 |
| `tools/workbench/views_leads.py:169` | 工作台下拉已有 `douyin` | 人工贴链接可用 | 无自动采集/卡片动作 |
| `tests/test_selection_manual.py:34` | 已测 `https://www.douyin.com/video/7301234567890` → `7301234567890` | 可直接作为抖音 native_id 回归 | 只覆盖一个 URL 形态 |
| `docs/validation/v9/TOOLS.md:39,74` | 抖音“未接；仅入口模板；无本项目 raw” | 事实基线 | 仍未改变 |
| `docs/validation/v9/platform-matrix/MATRIX.md:11` | 抖音行全部“未验证/需登录/cookie/风控” | 作为风险基线 | 不是实测 |
| `docs/validation/v9/research-collection/RESEARCH.md:95,135` | catbus `item list` 预览、MediaCrawler 两侧都有但均未验证 | 历史候选背景 | 不能当本次实测 |

### 本地结论

- **真正可复用的是“外壳”**：预算、host 白名单、单 loop、记录白名单、URL 清洗、登录轮询、平台锁、导出。
- **不可复用的是“页面知识”**：抖音的搜索入口、详情 DOM、评论结构、登录标记、分页游标，本项目都没有本项目 raw；必须重新观察，不能从微博/知乎推断。
- **现有抖音资料只有**：`manual.py` 的 `/video/<id>`、工作台下拉、矩阵“未接”、一条 manual 测试。没有 `tools/selection/douyin.py`；此前没有 `docs/validation/v10/douyin*` 报告，也没有抖音 raw。

## 2. 外部公开资料核查

### 2.1 渠道与工具

- 读取本机 agent-reach SKILL 目录后，使用 `C:\Users\19183\.agent-reach-venv\Scripts\agent-reach.exe`：
  - `--version` → **Agent Reach v1.5.0**；
  - `doctor --json` → GitHub `warn`（gh CLI 可执行但未检测到显式认证）；Twitter/X `warn`（twitter-cli 已安装但无完整显式凭据）。
- 当前工具面无 `skill` 调用 schema；按任务要求读取了可读的 `agent-reach/SKILL.md`，并**实际调用了 CLI 的 doctor/version**；没有宣称使用未提供的搜索工具。
- GitHub 用公开 REST 搜索 + raw 文件（`curl`）完成；`douyin web api` 查询第 4 次返回 **403 API rate limit exceeded**，已如实记录。
- X：`site:x.com` 三组查询没有 X 原帖；未配置 Cookie，未登录。详见 [X_ATTEMPT.md](sources/X_ATTEMPT.md)。

GitHub 搜索计数（2026-10-29）：

| 查询 | 命中 | 前几项 |
| --- | ---: | --- |
| `douyin crawler` | 158 | Evil0ctal 20,980；videodl 3,165；creatorhub 2,741 |
| `douyin comments` | 115 | stream-rec 1,190；DouyinComments 202；rust-srec 103 |
| `抖音 采集` | 369 | Evil0ctal 20,980；TikTokDownloader 17,194；creatorhub 2,741 |
| `douyin web api` | **403** | API rate limit；无结果 |

原始响应在 [sources/github_search_summary.json](sources/github_search_summary.json) 与 `sources/gh_*.json`。

### 2.2 深度核对的两个候选

| 项 | `cv-cat/catbus` | `NanmiCoder/MediaCrawler` |
| --- | --- | --- |
| URL | https://github.com/cv-cat/catbus | https://github.com/NanmiCoder/MediaCrawler |
| 获取日期 | 2026-10-29（源码 raw）；元数据快照 2026-10-25 | 2026-10-29（源码 raw）；元数据快照 2026-10-25 |
| 版本/commit | **0.2.1**；`0a6e705f95d991ac3cdc896b774570479a23c0ad`（2026-10-22） | pyproject **0.1.0**；`8f583999006d5b692272c608440e193ca282e73b`（2026-10-15） |
| 许可 | **MIT**（LICENSE + package.json） | **NON-COMMERCIAL LEARNING LICENSE 1.1**；GitHub API 显示 `NOASSERTION`，以 LICENSE 文件为准 |
| 语言/规模 | TypeScript；512 stars | Python；68,377 stars |
| 依赖 | Node `^22.22.2 || ^24.15.0 || >=26.0.0`；12 个 runtime deps（`wreq-js`、`onnxruntime-web`、`@napi-rs/canvas`、`opencv-js`、`jsdom`、`protobufjs` 等） | Python ≥3.11；Playwright ≥1.61、httpx、FastAPI、SQLAlchemy、pandas 等；README 另要求 Node ≥16 |
| 实际读过 | `douyin.md`；`package.json`；`api.ts`、`commands.ts`、`client.ts`、`normalize.ts`；LICENSE；SKILL 风险段 | `douyin/client.py`、`core.py`、`field.py`；LICENSE；pyproject；README 的抖音/依赖段 |
| 运行其测试 | **否** | **否** |
| 真实抖音验证 | **否**（本项目未访问抖音） | **否** |
| 适用限制 | CLI/Node；扫码或 cookie；签名/设备风控；写操作基本跑不通；作品 `title` 恒 null；`comment list` 用 cursor；无 `msg list`/`feed hot|following` | 非商用许可；Playwright + Node + `a_bogus`/Argus/session；重依赖；不适合 vendor |

#### catbus：实际看到的机制

- 平台文档明确：`item search/get/media/download/list`、`user ...`、`comment list/replies`、`feed list`（仅推荐）；**写操作基本跑不通**；作品没有标题，描述在 `text`，`title` 恒 null；列表 `stats.views` 恒 null。见 [catbus_douyin_platform.md](sources/catbus_douyin_platform.md:9)。
- 搜索：
  - 综合 `/aweme/v1/web/general/search/single/`，`offset` + `count=15`，翻页用 `search_id`；
  - 视频 `/aweme/v1/web/search/item/`，游标是 `offset,X-Tt-Logid`，`search_id` 取上一页响应头 `x-tt-logid`。
  - 见 [api.ts](sources/src_platforms_douyin_web_api.ts:348) 与 [commands.ts](sources/src_platforms_douyin_web_commands.ts:167)。
- 详情 `/aweme/v1/web/aweme/detail/`，需 `webid/uifid/verifyFp/msToken/a_bogus` 等参数；见 [api.ts](sources/src_platforms_douyin_web_api.ts:275)。
- 评论 `/aweme/v1/web/comment/list/`，`cursor` + `has_more`；回复 `/comment/list/reply/`；见 [api.ts](sources/src_platforms_douyin_web_api.ts:289) 与 [commands.ts](sources/src_platforms_douyin_web_commands.ts:214)。
- 登录有扫码/短信/cookie；cookie 只读够用，写操作需要扫码 ticket/私钥；发布/评论/点赞会触发 dtrait/设备风控。见 [catbus_douyin_platform.md](sources/catbus_douyin_platform.md:7)、[SKILL.md](../../v9/research-collection/raw/src_catbus_SKILL.md:113)（历史副本）。
- **判断**：catbus 的 API 路径是“签名 + 设备/会话 + 反爬参数”的完整实现；把它引入本项目会引入 Node 22 和 12 个依赖，不符合当前 stdlib/最小实现方向。可作为外部只读 CLI 的可选参考，不作为核心。

#### MediaCrawler：实际看到的机制

- 许可文件第 1 行：`NON-COMMERCIAL LEARNING LICENSE 1.1`；第 2 条明确仅学习研究、不得大规模爬取/干扰平台；第 3 条商用需书面同意。见 [license](../../v9/research-collection/raw/license_MediaCrawler.txt:1)。
- `client.py`：
  - `x-tt-argus` 固定值 + `uifid`；
  - `__process_req_params` 从 Playwright 页面 localStorage 取 `xmst`，用浏览器执行 `get_a_bogus`；见 [client.py](sources/media_douyin_client.py:84)；
  - 搜索 `/aweme/v1/web/general/search/single/`，`offset`、`count=15`；见 [client.py](sources/media_douyin_client.py:182)；
  - 详情 `/aweme/v1/web/aweme/detail/`，依赖 `UIFID/UIFID_TEMP` 与 `s_v_web_id` 成套；见 [client.py](sources/media_douyin_client.py:224)；
  - 评论 `/aweme/v1/web/comment/list/` 与回复 `/comment/list/reply/`，`cursor`/`has_more`；见 [client.py](sources/media_douyin_client.py:248)。
- `core.py`：
  - 搜索按页 `offset = page*10`，每页 sleep；见 [core.py](sources/media_douyin_core.py:130)；
  - 评论循环 `has_more`/`cursor`，可选子评论，按 `max_count` 截断；见 [core.py](sources/media_douyin_core.py:237)；
  - 启动 Playwright/CDP，登录后复用 cookie；见 [core.py](sources/media_douyin_core.py:70)。
- **判断**：它的“无需 JS 逆向”是 README 宣传；实际仍依赖浏览器上下文执行 `a_bogus`、Argus 头和登录态。**非商用许可**与重依赖都不适合直接引入。只把它当“评论分页/字段形状”的参考，不复制代码。

### 2.3 仅筛到、未深入的候选

`Evil0ctal/Douyin_TikTok_Download_API`（20,980 stars，Apache-2.0）出现在搜索首位，但本次**没有读其源码**、没有运行、没有验证抖音页面；不纳入建议。记录在 `source_manifest.json`，避免把“stars 多”当可用性。

## 3. doctor / login / search / detail / comments / export / 分页：最简路径

> 下表的“可复用”指现有代码结构；“未验证”指本项目没有抖音真实页面/账号证据，不能写成已通过。

| 能力 | 最简可行路径 | 复用 | 尚未验证/限制 |
| --- | --- | --- | --- |
| **doctor** | 只读：profile 目录、`Default/Network/Cookies` 是否存在、`browser.available()`；**不启动浏览器、不联网、不输出 cookie 值**。抖音 cookie 名称没有确认，`cookie_names` 先返回空并注明“未建立 allowlist”，不要扫描/打印任意 cookie 名。 | `browser.available()`（`browser.py:48-59`）；`zhihu.doctor` 的只读结构（`zhihu.py:460-484`） | 没有抖音 profile；cookie 名称/登录标记未验证；cookie 存在≠有效会话 |
| **login** | 用户可见窗口；复用 `wait_for_login`，注入抖音的 `signed_in_js` 和 wall markers；`risk_wins=True`；用户自己扫码/短信，代码不填凭据、不导出 Cookie；风险即 `lock`。 | `browser.wait_for_login`（`browser.py:77-175`）；`AuthenticatedBrowserTransport`（`transport.py:124-159`） | 抖音登录页 DOM/成功标记未观察；扫码/短信流程未实测；验证码/风险锁不绕过 |
| **search** | 首选**人工贴链接/文本**（已可用，无网络）；自动路径用浏览器打开 `https://www.douyin.com/search/{keyword}`，只解析渲染后的 `/video/<id>` 链接，**第一页**，记录 `anchors_total/recognized/rejected`。 | `manual.py`；`weibo.parse_search_html` 的 `rec.Links` 模式（`weibo.py:379-423`）；`records.make_record` | 搜索 URL、结果容器、链接形状未验证；抖音可能要求登录/验证码；不实现 `a_bogus`/Argus |
| **detail** | 浏览器打开 `https://www.douyin.com/video/<id>`（短链先让浏览器落地到最终 URL），读 `og:title`/`og:description`/可见文本；`title` 可能为空，描述放 `text`；`native_id` 来自 `/video/(\d+)`。 | `records.meta_tags/strip_tags`；`manual.parse_native_id`；`weibo.parse_detail_html` 的 meta/body 模式（`weibo.py:426-454`） | 详情 DOM/字段未验证；短链 `v.douyin.com` 未在 `manual.py` 覆盖；视频页可能异步加载 |
| **comments** | **先不做自动 API**。若必须做，先让用户在可见窗口打开一条作品，只读**可见第一页**评论文本/作者/点赞；不滚动无限加载、不猜 cursor。API 路径（`/comment/list/` + `cursor/has_more`）只作为未来观察后的候选。 | `records` 字段白名单；`weibo.parse_comments_json` 的 cursor/has_more 形状（`weibo.py:457-507`）作为参考，不复制 | 评论区 DOM/虚拟列表/排序未验证；API 需要 `a_bogus`/msToken/verifyFp 等，不是最小路径；不绕过验证码 |
| **export** | 直接复用 `zhihu.export` 白名单；新增 `douyin:` source 规则；只导出 `records.EXPORT_FIELDS`，不导出 cookie/token/作者隐私；本地文件，无网络。 | `zhihu.export`（`zhihu.py:782`）；`records.EXPORT_FIELDS`（`records.py:22-31`）；`weibo.export` 的委托（`weibo.py:860-869`） | 抖音 source 规则/字段映射未验证；`title=null` 的 `supported` 判定要允许 `text` 作为主字段（现有 `make_record` 已允许 title 或 text，见 `records.py:167-170`） |
| **分页** | **第一页 only** 是默认；结果带 `has_more/next_cursor` 也只记录不自动追。未来若观察通过：用服务端返回的**不透明 cursor**（不是自算页码），空页/无新 ID/`has_more=false` 即停；每页间隔与平台预算共用；不并发。 | `platform_budget` 的 15s/5 条/300s 限制（`platform_budget.py:45-49`） | 抖音 search offset、评论 cursor、`X-Tt-Logid` 都只是外部源码观察；本项目未验证；不能把 catbus 的 `offset+15` 当抖音通用规则 |

### 最小实现顺序（建议，不在本任务写代码）

1. **P0 无网络闭环（先做）**
   - `manual.py` 已支持 `douyin` `/video/<id>`；补 `/note/<id>`、`?modal_id=`、短链最终 URL 的解析测试（只改测试/解析，不联网）。
   - 新增 `access/douyin.py` 的 **doctor**：profile/cookie DB 存在性 + browser.available；不读值、不联网。
   - **export** 走 `zhihu.export`；新增 `records.SOURCE_RULES["douyin:"]` 白名单；不新增依赖。
   - 用 fake/HTML fixture 测 doctor、URL identity、export；**不测真实抖音**。

2. **P1 浏览器辅助单页**
   - 新增 `SITE = SiteProfile("douyin", ...)`；`allowed_host_suffix="douyin.com"`；`AuthenticatedBrowserTransport`。
   - `search` 只解析第一页 `/video/<id>`；`detail` 读 meta/body；`comments` 暂不自动。
   - `diagnostics.SITES["douyin"]` + `ASSUMED_BY_SITE["douyin"]` 明确标“assumed”；失败/空/风控分状态。
   - 需要用户可见登录；`login` 用 `wait_for_login`，不自动填凭据。

3. **P2 评论/分页（等真实观察）**
   - 先在用户可见窗口记录一条作品的评论 DOM/接口；确认后再决定“DOM 第一页”还是“API cursor”。
   - 只做有界循环：`max_pages`/`max_records`/空页停止；不猜 cursor、不无限滚动、不重试风控。
   - 任何 403/429/验证码/登录墙 → `lock`，非零退出。

### 未来文件（只列建议，不在本任务创建）

- `tools/selection/access/douyin.py`：`SITE`、`BASE`、`ALLOWED_HOST`、`DEFAULT_PROFILE`、`doctor`、`login`、`search_url`、`url_identity`、`parse_search_html`、`parse_detail_html`、`export`（委托）。
- `tools/selection/access/diagnostics.py`：加 `SITES["douyin"]` 与 assumed selectors。
- `tools/selection/access/records.py`：加 `SOURCE_RULES["douyin:"]`。
- `tools/selection/access/platform_budget.py`：不要复用 `platform_weibo.sqlite3`；显式 `runtime/platform_douyin.sqlite3`（或调用方传 path）。
- `tests/test_access_douyin.py`：fake transport/HTML，不联网；覆盖 doctor 不泄露 cookie、URL 形态、第一页、空页停止、风险即停、export 白名单。
- `manual.py`：仅补 URL 形态；不把短链解析变成网络调用。

## 4. 明确未验证 / 风险

- 没有打开过抖音页面，没有登录，没有真实账号；所有抖音 DOM/URL/字段/分页都是**假设**。
- 没有运行 catbus/MediaCrawler 的测试或真实采集；只读源码/文档；不能把 README/源码里的“支持”当本项目实测。
- catbus 的 API 签名/设备参数、MediaCrawler 的 `a_bogus`/Argus 都是反爬实现；本报告不把它们移植进项目，也不提供绕过验证码/风险锁的步骤。
- X 渠道无结果；GitHub 第 4 个查询 403 限流；GitHub 元数据是 2026-10-25 快照，源码 raw 是 2026-10-29 读取。
- 本报告不涉及搜集策略、关键词、频控业务参数、发布/采购/私信。

## 5. 证据

- [source_manifest.json](source_manifest.json)：本地/外部来源、commit、许可、依赖、实际读取、测试状态。
- [source_hashes.json](source_hashes.json) / [source_hashes_after.json](source_hashes_after.json)：本地 11 个底座文件只读哈希，前后 **11/11 same**。
- [sources/github_search_summary.json](sources/github_search_summary.json)：GitHub 查询计数/前 5；含 403 记录。
- [sources/X_ATTEMPT.md](sources/X_ATTEMPT.md)：X 无凭据/无原帖记录。
- [logs/agent_reach_version.txt](logs/agent_reach_version.txt)、[logs/agent_reach_doctor.json](logs/agent_reach_doctor.json)：Agent Reach v1.5.0 与平台状态。
- 外部源码副本：`sources/catbus_douyin_platform.md`、`sources/catbus_package.json`、`sources/src_platforms_douyin_web_*.ts`、`sources/media_douyin_*.py`。
- 本地回归：`tests/test_selection_manual.py` **8 tests OK / exit 0**（`logs/local_manual_test.log`）；只证明 `/video/<id>` 人工导入，不证明抖音自动采集。
- 本地代码：`tools/selection/access/*`、`tools/selection/manual.py`、`tools/workbench/views_leads.py`；未修改。
- 既有事实：`docs/validation/v9/TOOLS.md:39`、`docs/validation/v9/platform-matrix/MATRIX.md:11`、`docs/validation/v9/research-collection/RESEARCH.md:95,135`。
