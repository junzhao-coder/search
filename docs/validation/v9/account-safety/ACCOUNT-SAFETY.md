# X 渠道只读验证与账号安全规范（V9-6）

> 任务：`task-fe725b18fabe38f48979071b14d82ad0`（revision 2，计划 v9）；范围 `docs/validation/v9/account-safety/`，另对 `platform-matrix/MATRIX.md`、`research-collection/RESEARCH.md` 各改一处 X 表述。
> 验证时间：2026-10-25 20:39–20:41 UTC+8（12:39–12:41Z）；工具 `C:\Users\19183\.dsh\tools\x-collect\`（专用 profile/venv）。
> **边界**：只读 doctor/search；未开 login 窗口、未登录新平台、未发帖/点赞/关注/私信/改资料；未读/打印 cookie 值、密码、验证码、手机号；未改 x-collect 脚本、未装依赖、未碰日常 Chrome profile、未写业务/工作单库/CSV。

## 1. 只读 doctor

| 项 | 结果 |
| --- | --- |
| 命令 | `C:\Users\19183\.dsh\tools\x-collect\venv\Scripts\python.exe scripts\x_collect.py doctor`（cwd `D:\桌面\two`） |
| exit | **0** |
| UTC | 2026-10-25T12:39:50Z（wrapper 起始 12:39:17Z） |
| handle | **@Johnsmathjyjp** |
| cookie | 仅名称/布尔：`exists=True`、`x_rows=14`、`auth_token=True`、`ct0=True`；**未读取值** |
| 日志 | `logs/doctor.log`（wrapper，含 exit 0）、`logs/doctor_tool.log`（工具原始日志） |
| 旧记录对照 | `docs/validation/x-collect/REPORT.md` 记录 `@xluchuan`；本次 **@Johnsmathjyjp** 不同，**待用户确认归属**，不推断原因/不认定长期可用 |

- doctor 成功只证明当前专用 profile 的 X 会话可被读取；**不等于 X 全站可采**，也不证明长跑/翻页/其它平台。

## 2. 小样本 search（≤5，只读）

| 项 | 结果 |
| --- | --- |
| 命令 | `x_collect.py search --keyword "Notion template" --limit 5 --interval-min 8 --interval-max 10`（cwd `D:\桌面\two`） |
| exit | **0** |
| 条数 | **5**（requested_limit=5、collected=5、duplicates=0、seen_total=377） |
| stop | **LIMIT**（不是风控/验证码） |
| 耗时 | 8.1s；日志显示脚本实际 interval 8–12s |
| 字段 | `tweet_id, url, text, author_handle, author_name, created_at, lang, replies, retweets, likes, views, media_urls, discovered_by_keyword, fetched_at` |
| raw | `raw/search_5.jsonl`（5 行）、`raw/search_stats.json`；`logs/search.log`（wrapper）、`logs/search_tool.log` |
| 样本 | 5 条均 `discovered_by_keyword="Notion template"`；**样本极小，不作为需求结论** |

- 未遇验证码/风控；未继续翻页/长跑。原始终端输出与工具样本已复制到本目录；未把样本写进业务库。

## 3. 账号安全规范（可执行规则，不是口号）

### 3.1 用户明确要求（2026-10-25）

用户要求：**可提供账号、必须保存登录态不要重复登录、不得影响或封禁账号**。对应执行规则：

1. **可提供账号**：只使用用户提供的专用 profile；登录动作由用户本人在可见窗口完成，执行者不代填账号/密码/验证码。
2. **保存登录态、不重复登录**：复用 `profile\`；先 `doctor`（只查 cookie 名称/布尔），已登录则**不再开 login**；doctor 失败即停并报告，不自动重登、不反复弹窗。
3. **不影响/不封禁账号**：只读白名单 + 限速 + 单量上限 + 风控即停不重试；不模拟人工、不绕过验证码、不并发轰炸、不读取/导出 cookie。

### 3.2 隔离与只读白名单

- **专用 profile 隔离**：X 使用 `C:\Users\19183\.dsh\tools\x-collect\profile\`；**绝不**使用/复制 `%LOCALAPPDATA%\Google\Chrome\User Data` 或日常浏览器 profile。
- **只读白名单**：`doctor`、`search`、`user`、`tweet`（只读页面）；**禁止** `login` 之外的写操作、发帖、回复、点赞、转推、关注、私信、改资料、改设置、上传媒体。
- **不读取凭据**：只允许 cookie 名称/布尔/行数；禁止读取/打印/导出 `auth_token`、`ct0`、密码、验证码、手机号；报告/日志不出现 cookie 值。
- **不装依赖/不改脚本**：使用现有 venv；不修改 `x_collect.py`；不新增第三方包。

### 3.3 限速与单量

| 项 | 规则 |
| --- | --- |
| 单次 search | `--limit ≤5`（本轮 5） |
| 间隔 | `--interval-min/--interval-max` 8–12s（本轮日志 8–12s） |
| 单轮请求 | 最多 5 条；不翻页、不并发、不长跑 |
| 风控 | 遇验证码/429/登录墙/异常页**立即停**；记录 stop_reason；**不重试轰炸** |
| 登录 | `doctor` 已登录则不再 login；失败即停，需用户本人处理 |

### 3.4 账号台账（本轮）

| 平台 | profile 路径 | handle | 上次验证 UTC | 状态 | 需重登判断 |
| --- | --- | --- | --- | --- | --- |
| X | `C:\Users\19183\.dsh\tools\x-collect\profile` | **@Johnsmathjyjp** | 2026-10-25T12:39:50Z | doctor exit 0；search 5 条 exit 0；只读小样本 | 否（当前可读）；与旧 @xluchuan 不一致，**归属待用户确认** |
| xiaohongshu | `C:\Users\19183\.dsh\tools\xhs-collect\profile` | 待补（未解析页面 handle，不推断） | 检测可靠性已修（CDP 轮询+关窗复查）；可见窗口 2026-10-26T02:39:27Z online=valid（25 条 explore 链接，无登录墙）；headless verify 02:27:26Z login_required 属无头误判，勿据此重登；note-click 03:07:54Z 成功 1 条；**batch 03:21:16Z 成功 5 条**（batch=first-batch-2026-10-26T03:21:17Z；signals=6 含前序1、review=6、categories=0、cards=0；页面加载10）；likes/publish_time 字段路径已尝试但批内值不可信/不可得 | 可用（可见窗口）；本地 ready；批量 5 条已入隔离库；品类 0、卡片 0 | 否（可见窗口实测可用）；不要因 headless verify 重登 |

> 台账只记 handle；不记 cookie 值。handle 不同不推断原因，也不认定长期可用。

### 3.4.1 违规记录（2026-10-26，小红书）

| 项 | 内容 |
| --- | --- |
| 时间 | 2026-10-26T03:36:26Z / 03:46:29Z（UTC） |
| 事实 | 两次命中 `risk_marker:captcha` 与 `risk_marker:dom`；之后仍执行 5 次运行（03:43、03:44、03:45、03:48、03:50），合计 7 次运行 / 17 次页面加载（任务上限 8） |
| 性质 | **流程违规**：违反“遇风控即停、不重试”和“总加载 ≤8”；提交曾只报最后一次 7 加载 |
| 当前会话状态 | **未知**（risk 后未再验证；未再发请求） |
| 建议 | 冷却 ≥24h 或换号，由用户决定；重启前先只读 doctor + 单条小样本 |
| 退出码缺陷 | 上述 7 次运行均 exit=0，不能作为成功证据；已修 search exit 语义并加 stub（见 `REPORT_V9_12_REWORK.md`） |


### 3.5 多平台扩展五步

1. 建**专用 profile**（每平台独立，路径写入台账；不复用日常浏览器）。
2. **用户本人**在可见窗口登录（执行者不代填、不索要验证码）。
3. `doctor` 验证（exit/handle/cookie 名称布尔；失败即停，不重试）。
4. **单条小样本**只读采集（≤5、8–12s、遇风控即停）。
5. 记录台账（平台/profile/handle/UTC/状态/需重登），并标注未验证项（长跑/翻页/其它平台）。

### 3.6 红线

- 不得为通过验证**模拟人工行为**、绕过验证码/风控、批量注册/撞库、并发/高频请求。
- 不得读取、复制、外发 profile 中的 cookie/凭据；不得把专用 profile 当日常浏览器。
- 不得把 doctor 成功写成“X 全站可采/稳定”；不得把 5 条样本当需求或市场结论。
- 不得在未获用户明确确认时登录新平台或扩大采集范围。

## 4. 证据与未验证

- raw：`raw/search_5.jsonl`、`raw/search_stats.json`；logs：`logs/doctor.log`、`logs/doctor_tool.log`、`logs/search.log`、`logs/search_tool.log`；`sha_manifest.json`。
- 未验证：X 长跑/翻页/评论深度、其它平台、登录后的写能力（禁止）、账号长期可用性；handle 归属待用户确认。
