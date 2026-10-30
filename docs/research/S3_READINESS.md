# S3 首批前置：需求渠道读取路径核验与最小适配就绪报告

> 任务：`task-455130132cb8d8f9b8d982d4bbfb46fc`（计划 v2，S3 首批前置；后续实现批次 `task-a7c515e42c69243f7d4469dd7a524cc3`）　执行者：`session-01ba487c-f808-55a7-a1f7-5f436ee12811`（A 来源与采集）
> 唯一策划者：`session-630d7dac-4fba-4074-b204-b614ddae1b35`；本文件由两批共同维护：探针批只写本文件与 `S3_PROBES.json`；实现批只写本文件、`app/sources/`、`tests/sources/`、`tests/fixtures/sources/`。`FEASIBILITY.md`、`SAMPLES.json`、冻结契约（`docs/design/CONTRACT.md`）、根目录台账与业务库始终未改动。
> 观察时点：**2026-10-14 13:05（Asia/Shanghai）**，时间来源 `https://timeapi.io/api/Time/current/zone?timeZone=Asia/Shanghai`（探针批实测）。
> 请求预算：上限 8 次公开只读请求，**探针批实际使用 7 次**（6 次端点探测 + 1 次时间源），剩余 1 次未使用。工具：仅 `web_fetch`（GET）；未登录、未使用签名/Cookie/代理、未绕过验证码、未抓取用户私信、未付费、未批量下载、未运行任何货源程序、未写业务代码（探针批）。
> 声明：会话工具可达**不等于**应用可调用；下表所有结论只描述"当时、该工具、该 URL"的真实返回。

## 1. 渠道状态矩阵（发现 vs 补全）

| 渠道 | 发现型（关键词检索） | 已知对象补全（给定链接/ID 读取） | 本次依据 | 访问方式结论 |
| --- | --- | --- | --- | --- |
| 闲鱼 | **不可用**：搜索页 HTTP 200 但仅站点标题+Logo（JS 空壳，零字段） | **不可用**：商品页 HTTP 200 同样空壳 | P1、P2 | 仅 `manual_import` |
| 小红书 | **不可用**：搜索页抓取报跨域重定向（无正文）；发现页跳登录 | **未执行/未知**：无可用笔记 ID，且页面需登录 | P3、P4 | 仅 `manual_import` |
| B站 | **不可用**：搜索接口 HTTP 412 `code=-412`（request was banned） | **可用（补全型）**：`x/web-interface/view` 按 `bvid` 返回 HTTP 200 / `code=0` 完整 JSON | P5、P6 | 发现=`manual_import`；补全=可自动读取（前端非授权接口，无 SLA） |

一句话结论：**三条渠道都没有可用的"发现型自动入口"；只有 B站"已知对象补全"在本次实测中可用**。因此 S3 只能**部分完成**：落地"人工导入 + B站已知 bvid 补全"，发现型自动化保持缺口（详见第 4、5 节）。

## 2. 逐渠道证据、字段与访问条款

### 2.1 闲鱼（goofish.com）

- P1 `https://www.goofish.com/search?q=%E6%A8%A1%E6%9D%BF` → HTTP 200，正文仅"闲鱼 - 闲不住？上闲鱼！"与站点 Logo 节点，**无商品/价格/时间字段**。
- P2 `https://www.goofish.com/item?id=1018647119075&categoryId=0` → HTTP 200，同样只有站点标题与 Logo。
- 可得字段：**无**（未获得任何结构化字段）。
- 访问条款（沿用 S1 已读原文，本批未重复请求）：《闲鱼社区卖家服务协议》（生效 2025-09-17）第 3.3.2(六) 禁止含有"未经授权秘密获取闲鱼社区及其他用户的数据、个人资料"的爬虫类程序；第 3.6.4 条限制对站内其他用户展示资料作商业性使用。→ 该渠道自动化**不做**，单列为合规风险项。
- 缺口：商家页规则、保证金档位仍在 S1 缺口清单内，本批未扩大。

### 2.2 小红书

- P3 `https://www.xiaohongshu.com/explore` → HTTP 200，最终落在 `https://www.xiaohongshu.com/login?redirectPath=http%3A%2F%2Fwww.xiaohongshu.com%2Fexplore%3FexSource%3Dnull`，正文仅"小红书 - 你的生活兴趣社区"。
- P4 `https://www.xiaohongshu.com/search_result?keyword=%E6%A8%A1%E6%9D%BF` → 工具层报错：`cross-origin redirect to http://www.xiaohongshu.com is not followed automatically`（重定向异常，未取得正文，无 HTTP 状态码可言）。
- 可得字段：**无**。
- 访问条款：本批**未读到**官方条款原文（规则页为 SPA、开放平台页需登录），登录墙本身即访问限制 → `terms_note=unknown`，不填"允许"。
- 缺口：笔记 ID 级补全未验证（无 ID 且需登录），本批**未执行**，不得写成"不可用"结论之外的其他推断。

### 2.3 B站（bilibili.com）

- P5 `https://api.bilibili.com/x/web-interface/search/type?search_type=video&keyword=%E6%A8%A1%E6%9D%BF` → **HTTP 412**，`code=-412`，`message=request was banned`。→ 发现型触风控，**立即停止该路径**（未做签名/Cookie/代理尝试）。
- P6 `https://api.bilibili.com/x/web-interface/view?bvid=BV1us8MzPEmn` → **HTTP 200 / `code=0`**，返回完整 JSON；本批实测字段：`bvid`、`aid`、`cid`、`title`（"拼多多全域虚拟电商从零到1实操课"）、`pubdate=1753349981`、`ctime=1753349982`、`desc`、`owner.mid=280758032`、`owner.name="有趣知识八分饱"`、`stat.view=5125`/`reply=5`/`favorite=218`/`like=51`/`share=23`/`coin=12`/`danmaku=0`、`pages[]`（7 个分P，含 `cid`/`part`/`duration`）、`duration=9675`、`pic`、`rights`。
- 时间换算：`pubdate=1753349981` → **2025-07-24T17:39:41+08:00**；同一稿件两次观察（2026-10-07、2026-10-14）`pubdate` 一致。
- 访问条款：**未获得官方授权**；该端点是网页前端接口，无公开 SLA、无限速承诺 → `terms_note` 记为"前端接口、无授权文档、未核许可与费用"，不填 yes。
- 缺口：限流阈值、字段变更风险、是否需 Cookie/wbi 签名（搜索路径）**均未验证**；本批未尝试任何绕过手段。

## 3. 与冻结契约的对应（只读引用，不改契约）

- `source`（§1.10）：冻结种子 `manual_import`、`xianyu`、`xiaohongshu`、`bilibili`，四行 `access_mode='manual_import'`、`access_verified='yes'`（人工导入自身可用）。本报告结论可直接写入各行的 `fields_available`/`terms_note`/`last_success_at`/`last_error_at`——**本批不写库、不改契约**，仅提交内容供策划者与 B 协调。
- 建议的登记摘要（供后续批次采用，未执行）：
  - `xianyu`：`access_mode=manual_import`；`fields_available`="仅官方协议文本；网页无字段"；`terms_note`="卖家协议 3.3.2(六)、3.6.4 限制爬虫与站内数据商业使用"；`last_error_at`=本批时点。
  - `xiaohongshu`：`access_mode=manual_import`；`fields_available`="无"；`terms_note`="页面需登录；条款未读取（unknown）"；`last_error`="blocked_login"。
  - `bilibili`：`access_mode=manual_import`（发现）/ 补全读取为前端接口；`fields_available`="view 端点：bvid/aid/title/pubdate/ctime/desc/owner/stat/pages/duration"；`rate_limit_note`="未知（未验证）"；`cost_note`="本次零费用；付费与授权未确认"；`terms_note`="前端接口，无官方授权与 SLA；搜索路径 412"。
- `search_coverage`（§1.11）：发现型尝试的落库枚举以**第 6 节的实现口径**为准——B站搜索 412 → `rate_limited`（保留原始原因），闲鱼空壳/重定向 → `failed`，小红书登录墙 → `blocked_login`；`coverage_note` 必填；**不得**把失败写成"市场无需求"（契约原文要求）。
- `run_record`（§1.12）：`run_type='collect'`，`source_id` 允许 NULL；本批属手工探测，未产生运行记录。
- 身份与去重（§4.5）：补全读取产生的需求信号使用 `n:bilibili:<bvid>`；无原生 ID 时 `u:bilibili:<url_norm>`；`content_hash` 仅用于同身份版本判定。
- `demand_source`（§4.2 映射）：登记名 → `source.id`；未登记名称报 V9，不静默落到 `manual_import`；研究侧 `manual` 归一为 `manual_import`。

## 4. 发现与补全的真实边界（本批结论）

| 能力 | 闲鱼 | 小红书 | B站 |
| --- | --- | --- | --- |
| 关键词发现（自动） | 无 | 无 | 无（412） |
| 已知对象补全（自动） | 无 | 未验证（需登录/无 ID） | **有**（`view?bvid=`，单次实测 200/code 0） |
| 人工导入 | 可用（保底） | 可用（保底） | 可用（保底） |
| 官方授权路径 | `open.goofish.com` 存在但不可读，资质/费用未知 | 开放平台需登录，接口与资质未知 | 开放平台文档 SPA 不可读，门槛未知 |

补充说明：

- **不新增需求平台**；本批不把 Met/Open Access 等供给侧 API 当作需求发现来源。
- 互动量（`stat.*`）只作热度，不冒充成交或盈利；研究标签（如 `license_reviewed`）**不升级四项入池门槛**。
- 未知许可/费用一律 `unknown`，不填 0 或 yes。

## 5. S3 部分完成方案（本批建议）

1. **发现层（当前唯一可行）**：人工导入（用户在浏览器内登录后复制/导出线索），格式统一走冻结契约 `format_version=1`（见 `FEASIBILITY.md` §7 映射，映射细节以 B 最终冻结版为准）。
2. **补全层（第一条真实自动化链路）**：仅对 **B站已知 `bvid`** 做读取补全（已按第 6 节实现，见第 9 节），用于把"用户给出的链接"规范化为带时间与出处的需求信号。
3. **官方授权待确认路径（不启动）**：闲鱼三方开发平台、小红书开放平台、B站开放平台——均需资质/费用评估，属用户确认事项，本批只登记缺口。
4. **诚实状态**：S3 **只能部分完成**；自动化目标未达成，不写"S3 通过"，发现型自动化保持缺口并在来源状态中如实展示。

## 6. 最小适配提案（接口边界；实现见第 9 节）

- **适配单元（仅 1 个）**：`bilibili_known_object`——输入 `bvid`（或可解析出 `bvid` 的链接），输出规范化需求信号字段。
- **输入**：`bvid`（必需）、`observed_at`（可选）；`source_id` 使用固定来源名 `bilibili` 作为身份命名空间，**不使用也不捏造数据库 FK**。
- **信任边界（与 `url_norm` 分开）**：`url_norm` 只是规范化，**不是安全校验**。输入校验独立执行，且 `urlsplit`/hostname/port 的整段解析处于**同一 `try/except ValueError` 保护**内（畸形 IPv6、越界或非数字端口一律判 `invalid_target`）：scheme 仅 http/https；**拒绝任何 userinfo**（按 netloc 是否含 `@` 判定，含空 userinfo `https://@host/...`）；端口必须为 scheme 默认端口；hostname 必须在显式白名单内（`bilibili.com`/`www.bilibili.com`/`m.bilibili.com`）；path 必须精确匹配 `/video/<bvid>`；短链（b23.tv）不跟随；用户给出的 URL **永不**作为网络目标（请求目标恒为按 `bvid` 构造的端点）；非法输入**不触达 transport**。
- **输出字段**（与冻结契约 `demand_signal` 对齐）：`native_id=bvid`、`identity_key=n:bilibili:<bvid>`、`url`（原始链接或规范页链接）、`url_norm`、`title`、`excerpt`、`signal_kind='other'`（不自动判定为求购/求助）、`published_at`（由 `pubdate` 换算为 UTC+8）、`original_author`（`owner.name`）、`engagement_json`（`stat.*`，标注"仅热度"）、`content_hash`、`observed_at`/`observed_at_source`、`unknown_fields`。**类型与身份校验**：返回的 `data.bvid` 必须与请求 `bvid` **严格一致**，缺失或不匹配 → `failed` 且**不输出身份键**；`title` 必须为非空**字符串**（不做强转）；`excerpt` 取 `desc` 或 `title` 并明确执行 **≤4000 字符截取**（不改写原意）；`owner`/`pubdate`/`stat`/`desc` 畸形一律保留"未知"并写入 `unknown_fields`（`pubdate` 的 `bool`、非整数、超出 2009–2100 区间分别标记），全程**不抛裸异常、不做强转造假**。
- **观察时间**：仅接受**带时区的秒精度 ISO 8601 且日期真实合法**（`YYYY-MM-DDTHH:MM:SSZ` 或 `±HH:MM`）→ `observed_at_source='source'`；非法/无时区/非法日期/非字符串 → 回退调用时刻并标 `import_time`，同时把原值记入 `observed_at_rejected`；**`pubdate` 只进 `published_at`，绝不当 `observed_at`**。
- **幂等**：同 `bvid` 再读由现有导入层按 `UNIQUE(data_origin, source_id, identity_key, content_hash)` 判 `duplicate_skipped` / 版本新增；本适配只返回身份与 `content_hash`，不实现去重器、不写 `last_seen_at`/`superseded_by`。`stat` 或 `observed_at` 变化**不改变** `content_hash`，正文变化才改变。
- **失败分类（以已验收 §6 为实现口径，不新造词）**：判定顺序为**先显式错误/登录，后成功**——① 显式登录证据（transport `login_redirect=true` 或 `final_url` 路径含 `/login`）→ `blocked_login`；② `error == "timeout"` → `timeout`；③ 其他显式 transport error（`cross_origin_redirect`、`html_shell`）→ `failed`；④ HTTP 412 / `code=-412` → `rate_limited`，原样保留 `http=412`、`app_code=-412`、`message=request was banned`，不推断限流阈值、不声称 HTTP 429；⑤ `code=-101` → `blocked_login`；⑥ 其余非 `200 + code 0`（含**普通 401/403——不臆测登录**、`62002` 不可见、HTML 空壳、payload/data 非字典）→ `failed`；原状态与应用码如实保留，未知 HTTP 留 `null`。**失败即停**：单项一次请求，无自动重试，失败结果不缓存。
- **限速与缓存**：缓存**只保存对象内容**（标题/摘录/发布时间/作者/互动量/`content_hash`/`unknown_fields`），每次输出按**当前合法输入**重建 `url`/`url_norm`/身份键/`request_url`；仅成功结果进入进程内 24 小时有界缓存（默认 256 项）；不并发；零费用优先。
- **数据回溯**：返回 `request_url`（恒为按 `bvid` 构造的端点）、`http_status`、`app_code`、`failure_reason`；运行信息落 `run_record`（`run_type='collect'`、`source_id='bilibili'`、`status ∈ {ok,partial,failed}`）；发现型失败落 `search_coverage` 并写 `coverage_note`。
- **边界**：不写 `FEASIBILITY.md`/`SAMPLES.json`；不改契约；不新增平台；不自动判定需求真实性；互动量不进门槛与排序（契约 V20）。

## 7. 后续最小代码 scope（进度）

| 序号 | 目标 | 建议/实际写入范围（前缀） | 状态 |
| --- | --- | --- | --- |
| S3-A1a | B站已知对象补全适配（含信任边界、失败分类、限速与缓存） | `app/sources/` | **已实施（本批）**，见第 9 节 |
| S3-A1b | 离线回放测试与 fixture（真实摘录 + 合成失败样本） | `tests/sources/`、`tests/fixtures/sources/` | **已实施（本批）**，测试**未实跑**（无运行通道） |
| S3-A1c | 来源状态登记与 search_coverage 落库字段核对 | 由 B 在 `docs/design/` 与 `app/storage/` 内完成；A 只提交本报告作为输入 | 待派发 |
| S3-A2 | 检索词维度与发现队列（**当前无可用发现入口**，只能先做"导入清单 + 覆盖记录"） | `app/sources/`（无网络调用部分）+ `docs/research/` | 待派发 |
| S3-A3 | 字段规范化/身份与版本/转载归并的核对用例 | `tests/sources/` | 待派发 |

不在本批范围：接 `app/storage`/`app/api`、任何 DB 写入、版本落库、真实网络请求、依赖安装、启动服务、付费调用、任何绕过手段。

## 8. 未核、限制与停止位置

**未核（如实保留）**：小红书笔记级读取；闲鱼任何结构化字段；B站限流阈值与 wbi 签名搜索路径；三个开放平台的接口清单/资质/费用；B站工房发布与结算条款正文；任何付费与授权状态。

**权限与工具限制**：执行者工具集**无命令执行工具**（Flow 登记 `allowCommands=true`，但该会话实际没有命令执行工具），因此测试未实跑、无退出码与日志；无签名工具、无登录态；`web_search`/`web_fetch` 仅调研工具，不构成应用可调用能力。

**探针批停止位置**：第 7 次请求后停止（剩余 1 次预算未用）；未做重试等待，未扩大请求量。

## 9. 实施记录（S3-A1a / S3-A1b，2026-10-14 批次，含第二轮返工）

**交付文件**

| 文件 | 说明 |
| --- | --- |
| `app/sources/bilibili_view.py` | 适配模块：`resolve_target`（信任边界，整段解析受 `ValueError` 保护）、`classify_failure`/`_bad_code`（失败映射与码类型校验）、`_login_marker`（显式登录证据，**路径段精确匹配**）、`_parse_view_response`（先登录/类型错误后成功）、`_excerpt_from`（desc 或 **截断后的 title** 回退，均 ≤4000）、`_author_from`/`_published_from`/`_engagement_from`（畸形字段保留未知）、`_render_ok`（按当前输入重建 URL 派生字段并复制 `unknown_fields`）、`BilibiliViewReader.complete`（注入式 transport + 24h 有界缓存 + 失败不缓存/不重试） |
| `app/sources/__init__.py` | 包标记（无逻辑） |
| `tests/sources/test_bilibili_view.py` | **41 个用例**：字段/身份/hash、观察时间校验（合法 `Z`/`+08:00` 与非法/无时区/非法日期）、输入信任边界（畸形 IPv6、空 userinfo、越界/非数字端口、任意主机、短链，均断言 transport 0 次）、失败映射（登录标记与路径段、401/403 不猜登录、空壳 HTML、跨域重定向、62002、超时）、类型校验（payload/data 非 dict、非整数 `app_code`/`payload.code`、bvid 缺失/不匹配、title 非字符串、owner/pubdate/stat/desc 畸形、title 与 desc 两条 ≤4000 截取路径）、缓存内容共享与逐次 URL 重建、`unknown_fields` 不跨记录共享、失败不缓存不重试、模块无网络客户端 |
| `tests/sources/__init__.py` | 包标记 |
| `tests/fixtures/sources/bilibili_view_ok_BV1us8MzPEmn.json` | **真实摘录**（出处 `S3_PROBES.json` P6，2026-10-14），文件内 `_fixture` 标明 `kind=real_excerpt`、`is_complete_raw_response=false` |
| `tests/fixtures/sources/bilibili_view_failures.json` | **合成失败样本**（`kind=synthetic_failures`、`is_real_log=false`），11 个分支：`rate_limited_412`、`login_redirect_200`、`login_final_url_only`、`login_path_segment`、`http_401_plain`、`http_403_plain`、`html_shell`、`timeout`、`missing_62002`、`cross_origin_redirect`、`server_error_500` |

**只读复用（未重写）**：`app/core/identity.py` 的 `normalize`、`content_hash`、`url_norm`、`demand_identity_key` 直接 import 使用；未新增规范化、hash 或去重框架；未改该文件；未新增依赖（仅 stdlib：`re`、`json`、`urllib.parse`、`datetime`、`typing`）。

**字段映射（实现键 → 契约）**：`native_id`→`demand_signal.native_id`；`identity_key`/`identity_source`→身份与来源；`url`/`url_norm`→`url`/`url_norm`；`title`→`candidate.title`；`excerpt`→`demand_signal.excerpt`；`signal_kind`→`signal_kind`（固定 `other`）；`published_at`→`published_at`（UTC+8，来自 `pubdate`）；`original_author`→`original_author`；`engagement_json`→`engagement_json`（仅热度）；`content_hash`→`content_hash`；`observed_at`/`observed_at_source`→同名字段；`unknown_fields`→研究侧元数据（待 B 协调落点）；`outcome`/`failure_reason`→`search_coverage.outcome`/`failure_reason`；`request_url`/`http_status`/`app_code` 仅用于回溯日志。身份命名空间用来源名 `bilibili`，`source_id` FK 留给后续接线批次。

**第二轮返工（revision 4 → 5）落实点**：① `urlsplit`/hostname/port 整段纳入 `ValueError` 保护，userinfo 改为按 netloc 含 `@` 判定（含空 userinfo），补畸形 IPv6 与越界端口用例并断言 transport 0 次；② 缓存只共享对象内容，`url`/`url_norm`/身份键每次按当前合法输入重建，新增"裸 bvid → URL1 → URL2、transport 仍 1 次"用例；③ 判定顺序改为先显式登录/错误再判成功，新增 `login_redirect_200`、`login_final_url_only`、`http_401_plain`、`http_403_plain`、`html_shell` 用例（401/403 不再视为登录、跨域错误不再可能被判登录）；④ 增加 payload/data 类型、`data.bvid` 与请求一致性、`title` 非空字符串、`excerpt` ≤4000 截取与 `unknown_fields` 标注，全部无裸异常、无强转；⑤ `observed_at` 仅接受带时区秒精度且日期合法的 ISO 8601，非法值回退 `import_time` 并记 `observed_at_rejected`；⑥ 本节与第 6 节同步更新，保留未运行说明与 fixture 出处。

**第三轮返工（revision 7 → 8，依据原 D 独立执行的 3 项真实缺陷与 1 项次要缺陷）落实点**：① `_excerpt_from` 的 title 回退分支改为 `title[:EXCERPT_MAX]`，新增"title 超长 + desc 缺失/全空白 → `excerpt` 恰 4000"两条用例（desc 有效时仍 `desc[:4000]`）；② `_bad_code` 显式校验 `app_code` 与 `payload.code`（`bool` 与非 `int` 均非法）→ `failed`/`unexpected_response`，**不放行、不强转**，新增 `app_code=False`、`payload.code=False`、`app_code="0"` 三例并断言不输出身份键；③ `_login_marker` 改为**路径段精确匹配**（`segment == "login"`），新增 `login_path_segment` fixture（`/users/account/login` → `blocked_login`）与 `/login-tips`、`/loginx` 正常返回 `ok` 两条用例，`login_redirect=True` 优先级不变；④ `_render_ok` 对 `unknown_fields` 做 `list(...)` 复制，新增缓存命中后两记录列表互不影响、且污染其中一个不回流缓存的用例；⑤ §8/§9 的"未运行"原因更正为"执行者工具集无命令执行工具（登记 `allowCommands=true` 但无该工具）"，不再写 Flow 开关状态；⑥ 新增限制：`excerpt` 截断对下游存储 4000 限制的影响本批未验证（由接线批处理）。测试总数为 **41 个用例**，失败 fixture 为 **11 个分支**。

**实跑命令（未运行）**

```text
.venv\Scripts\python.exe -m unittest tests.sources.test_bilibili_view -v
# 或
python -m unittest discover -s tests/sources -t . -v
```

**未运行原因与限制**：执行者工具集**无命令执行工具**（Flow 登记 `allowCommands=true`，但该会话实际没有命令执行工具），因此**没有退出码与日志**，本次返工同样**不声明测试通过**，保留给原 D 独立运行复验（含新增用例）；本批为纯离线验证，无真实网络请求；B站限流阈值、字段稳定性、授权与费用仍未验证；`excerpt` 截断对下游存储 4000 限制的影响**本批未验证**（由接线批处理）；存储接线与版本落库未做；**S3 仍为部分完成**。
