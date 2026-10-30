# V9-0B｜国内多平台采集/评论抽取：候选调研（修订版：锁定 commit + 行级证据）

> 执行者：C（`session-48004521-daf2-548c-a355-487cc6de6e72`）｜任务 `task-57465e927bcc43f7d1b7147da63ce765`（计划 v9，revision 5）
> 范围：仅 `docs/validation/v9/research-collection/`；**未下载运行任何候选代码、未安装 npm 包、未登录平台、未采集数据、未改本项目实现/依赖/配置/库/CSV**。
> 证据等级（全文强制）：
> - **【源码观察】**＝我在**锁定 commit** 的原始文件里实际读到的行（给永久链接＋行号）；
> - **【文档观察】**＝锁定 commit 的文档/README/SKILL 原文；
> - **【元数据】**＝GitHub API 返回值；
> - **【未运行】**＝本任务不执行候选程序，任何"能采到数据"都不成立。
> 行号以**锁定 commit 的文件**为准；永久链接形如 `https://github.com/<owner>/<repo>/blob/<sha>/<path>#L<n>`。

## 0. 工具与能力实测（含本项目自有 X 工具的有界只读探测）

| 能力 | 实测结果（UTC 2026-10-25） |
| --- | --- |
| `skill` 工具 | **本会话函数表中不存在** → 无法"加载 agent-reach / ponytail / stealth-browser 技能"；不伪称 |
| agent-reach CLI | `agent-reach` / `reach` / `agentreach` / `areach` 在 PATH 上**均 not found**；`%APPDATA%\npm` 无相关 bin |
| `mcp__stealth__*` | 本会话**无可调用的 MCP 浏览器工具**；未使用浏览器 |
| GitHub REST API | **可用**（`/rate_limit` 200，60/hr）。本次共 21 次：rate_limit 1 + 检索 7 + repo 详情 5 + contents 4 + commits 4 |
| raw.githubusercontent | **可用**；本轮统一「下载字节 → UTF-8 严格解码 → LF」，44 个原始件**全部通过 UTF-8 严格解码**（`bad=0`） |
| 本项目 X 工具（`docs/validation/x-collect/REPORT.md` 指向） | **存在且可只读探测**：`C:\Users\19183\.dsh\tools\x-collect\scripts\x_collect.py`；`--help` **exit=0**（子命令 doctor/login/search/user/tweet）；`doctor` **exit=0**，`LOGGED_IN handle=@Johnsmathjyjp utc=2026-10-25T05:23:40Z`。证据：[x_collect_probe.log](x_collect_probe.log) |
| X 工具检索（search/user/tweet） | **未运行**：该 CLI 的输出落它自己的 `data/` 目录，超出本任务 scope；按"不写 scope 外"处理（这是本轮唯一可做的 X 实采通道，记录为"可用但未用"） |

> 关于 `doctor` 的两点事实：① 它只读 DOM、不读 cookie 值（日志只出现 `COOKIE_CHECK … x_rows=14 auth_token=True ct0=True` 这类**名称/行数**）；② 本轮 handle 为 `@Johnsmathjyjp`，与 [x-collect REPORT](<../../x-collect/REPORT.md>) 记录的 `@xluchuan` **不同**——说明该 profile 的登录账号已变化；**不推断原因**，只记录事实，也不据此认定"当前会话长期可用"。

## 1. 检索记录（关键词 / 日期 / 原始 URL / 响应）

日期统一 UTC 2026-10-25；原始响应在 [`raw/`](raw/)，逐件 sha256 见 [source_manifest.json](source_manifest.json)。

### 1.1 GitHub（`GET /search/repositories?sort=stars&order=desc`）

| # | 关键词 | 命中 | top 结果 | 文件 |
| --- | --- | --- | --- | --- |
| 1 | `MediaCrawler` | 200 | `NanmiCoder/MediaCrawler` 68,376★ | `raw/gh_search_q_mediacrawler.json` |
| 2 | `多平台 采集 评论 爬虫` | 7 | 无相关（措辞非社区用法） | `raw/gh_search_q_multi_cn.json` |
| 3 | `xhs 评论 爬虫` | 19 | `xhs996/xhs_spider` 369★（无许可）、`Cialle/RedCrack` 244★ MIT | `raw/gh_search_q_xhs_comment.json` |
| 4 | `闲鱼 爬虫 商品 采集` | 17 | `DropsDevopsOrg/ECommerceCrawlers` 5,750★ MIT | `raw/gh_search_q_xianyu.json` |
| 5 | `bilibili 评论 爬虫` | 60 | `Ghauster/BilibiliCommentScraper` 474★ MIT | `raw/gh_search_q_bili_comment.json` |
| 6 | `catbus` | 64 | `cv-cat/catbus` 512★ MIT | `raw/gh_search_catbus.json` |
| 7 | `小红书 抖音 B站 微博 贴吧 采集 CLI` | **0** | 检索式过窄，0 命中（不等于"没有项目"） | `raw/gh_search_小红书_抖音_B站_微博_贴吧_采集_CLI.json` |

### 1.2 X（Twitter）——**站点限定检索未命中，第三方线索**

| 查询 | 工具 | 实际结果 |
| --- | --- | --- |
| `site:x.com MediaCrawler 采集 开源` | `web_search` | **未返回任何 X 原帖**；返回 npm 包页、GitHub `danfeistar/busybee-mcp`、AtomGit 镜像等 |
| `site:x.com 小红书 评论 爬虫 开源 推荐` | `web_search` | **未返回任何 X 原帖**；返回 V2EX 帖《catbus：用一套命令操作小红书、抖音、B 站、X 等 10 个平台的 CLI》→ 据此**追溯到仓库** `cv-cat/catbus` |

**结论（不冒充 X 来源）**：X 渠道**没有拿到任何 X 原帖文本**；唯一可用线索是**第三方（V2EX）帖子**指向的 GitHub 仓库。若必须覆盖 X 内容，通道是 §0 的自有 CLI（需 `search` 且输出落该类工具目录），本轮按 scope 未运行。

**2026-10-25 V9-6 修正（保留上方旧记录）**：**agent-reach twitter 后端未装；x-collect 可用**。本机专用 profile 的 `doctor` exit 0（handle `@Johnsmathjyjp`，与旧记录 `@xluchuan` 不同，待用户确认归属），只读 `search` 5 条 exit 0；证据 [account-safety/REPORT.md](../account-safety/REPORT.md)、`raw/search_5.jsonl`、`logs/doctor.log`。这只证明当前专用会话可读，**不等于 X 全站可采**；上方“未拿到 X 原帖”只适用于上一轮 `web_search`，不删除；§8 第 3 条“未运行 search”由本次取代。

### 1.3 锁定 commit（`GET /repos/{o}/{r}/commits?per_page=1`）

| 仓库 | commit sha（锁定） | commit 时间 | 说明 |
| --- | --- | --- | --- |
| `NanmiCoder/MediaCrawler` | `8f583999006d5b692272c608440e193ca282e73b` | 2026-10-15T04:53:36Z | `raw/gh_commit_NanmiCoder__MediaCrawler.json` |
| `cv-cat/catbus` | `0a6e705f95d991ac3cdc896b774570479a23c0ad` | 2026-10-22T15:21:45Z | `raw/gh_commit_cv-cat__catbus.json` |
| `Cialle/RedCrack` | `a557e328b6e723f63dcd75f1c52640794f2c84b5` | 2026-05-30T05:48:51Z | `raw/gh_commit_Cialle__RedCrack.json` |
| `Ghauster/BilibiliCommentScraper` | `0b39e0659c78fe695d2c675edc1f9c0042935ee4` | **2023-04-25T12:01:18Z** | `raw/gh_commit_Ghauster__BilibiliCommentScraper.json` |

## 2. 候选深读（锁定 commit 的行级观察）

### 2.1 `NanmiCoder/MediaCrawler` @`8f58399` —— **只借鉴设计，不复用代码**

**许可（源码观察）**：[`LICENSE`](https://github.com/NanmiCoder/MediaCrawler/blob/8f583999006d5b692272c608440e193ca282e73b/LICENSE) 首行 `NON-COMMERCIAL LEARNING LICENSE 1.1`；第 13 行授权"for **non-commercial learning purposes**"；第 18 行"**may not be used for any commercial purposes** without the written consent"。文件头注释亦写入 `# Licensed under NON-COMMERCIAL LEARNING LICENSE 1.1`（`media_platform/bilibili/field.py:7`）【源码观察】。

| # | 观察点 | 永久链接 | 行 | 观察 |
| --- | --- | --- | --- | --- |
| 1 | 分页粒度固定 | [`media_platform/bilibili/core.py`](https://github.com/NanmiCoder/MediaCrawler/blob/8f583999006d5b692272c608440e193ca282e73b/media_platform/bilibili/core.py) | `202–204` | `bili_limit_count = 20  # bilibili limit page fixed value`；若 `CRAWLER_MAX_NOTES_COUNT < 20` 会被抬到 20（**列表页每页固定 20**） |
| 2 | 起始页与翻页循环 | 同上 | `205`, `210–212` | `start_page = config.START_PAGE`；`while (page - start_page + 1) * bili_limit_count <= config.CRAWLER_MAX_NOTES_COUNT:` → 以"页数×20 ≤ 上限"控制；`page < start_page` 时跳过 |
| 3 | 页间限速 | 同上 | `248–249`（另 `329–330` 同构） | `await asyncio.sleep(config.CRAWLER_MAX_SLEEP_SEC)` 后打印 `Sleeping for … seconds after page {page-1}` → **限速是"每页后 sleep 固定秒数"，不是令牌桶/每分钟配额** |
| 4 | 评论排序枚举 | [`media_platform/bilibili/field.py`](https://github.com/NanmiCoder/MediaCrawler/blob/8f583999006d5b692272c608440e193ca282e73b/media_platform/bilibili/field.py) | `46–54` | `class CommentOrderType(Enum)`：`DEFAULT = 0`（按热度）、`MIXED = 1`、`TIME = 2` → 评论可按时间/混合排序取数 |
| 5 | 登录态与 CDP 默认 | [`config/base_config.py`](https://github.com/NanmiCoder/MediaCrawler/blob/8f583999006d5b692272c608440e193ca282e73b/config/base_config.py) | `28–29`, `53`, `59`, `63`, `83` | `LOGIN_TYPE = "qrcode"  # qrcode or phone or cookie`、`COOKIES = ""`、`SAVE_LOGIN_STATE = True`、`ENABLE_CDP_MODE = True`（**默认走 CDP 连本地 Chrome**）、`CDP_DEBUG_PORT = 9222`、`CDP_CONNECT_EXISTING = True` |
| 6 | 落库格式 | 同上 | `90`, `96` | `SAVE_DATA_OPTION = "jsonl"`（可选 csv/db/json/jsonl/sqlite/excel/postgres）、`USER_DATA_DIR = "%s_user_data_dir"` |
| 7 | 平台开关 | 同上 | `21` | `PLATFORM = "xhs"  # xhs | dy | ks | bili | wb | tieba | zhihu` → **知乎/贴吧在代码层有平台位**（README 表格未列知乎为独立行时以此为准） |

**未核实**：二级评论的具体拉取实现（`get_sub_comments` 等函数名在本次抓取的 `core.py` 前 833 行内未出现，需读完整文件或其父类）；`CRAWLER_MAX_SLEEP_SEC` 默认值（本轮未取 `config` 该行）。因此本节只声明"读过这几个文件与行"，**不声明整份实现已读完**。

### 2.2 `cv-cat/catbus` @`0a6e705` —— **待验证候选（不预先批准为全局依赖）**

**许可（源码观察）**：`LICENSE` 首行 `MIT License`；GitHub API `license.spdx_id=MIT`【元数据】。
**用途表述（文档观察，与许可并列记录，不做裁定）**：
- `README.md` 定位为"一个命令，开往 11 个平台"的 CLI 工具（含搜索/详情/评论/下载/**发布/私信**等能力枚举）；
- `.claude/skills/catbus/SKILL.md:91–99` 自设红线：**登录交给用户**（`:95`，不索要/保存密码、验证码、cookie，不读 `~/.catbus/` 凭证）、**写操作先确认**（`:96`，危险操作只在该次同意后加 `-y`）、**风控就停**（`:99`，不循环重试、不并发）。
- 两者**一个是许可文本、一个是使用约定**；本报告只并列陈述差异，**不判断可商用范围**。

| # | 观察点 | 永久链接 | 行 | 观察 |
| --- | --- | --- | --- | --- |
| 1 | 验证码/挑战**不自动处理** | [`.claude/skills/catbus/workflows/errors.md`](https://github.com/cv-cat/catbus/blob/0a6e705f95d991ac3cdc896b774570479a23c0ad/.claude/skills/catbus/workflows/errors.md) | `28–35` | `RISK_CONTROL`（退出码 5）时 `detail.kind` 为 `captcha` / `rate_limit` / `blocked`；小红书 461/471 给出 `detail.verify_url`，要求**把链接原样交给用户**、让用户在已登录浏览器里完成，"**不要自己去打开或尝试通过验证**" |
| 2 | 只读路径能停在挑战处 | 同上 | `30`, `35` | 只读命令遇到 `captcha` 即抛 `RISK_CONTROL`（退出码 5）并停；文档另要求"连续请求同一平台留间隔、不并发"（`SKILL.md:99`） |
| 3 | 写操作隔离机制 | [`src/cli/confirm.ts`](https://github.com/cv-cat/catbus/blob/0a6e705f95d991ac3cdc896b774570479a23c0ad/src/cli/confirm.ts) | `6–17` | `confirm(question, yes)`：`yes` 直接放行；**非 TTY 且未带 `-y` → 抛 `CONFIRM_REQUIRED`**（退出码 2）；TTY 下才在 stderr 问 y/N |
| 4 | 命令能力状态可自描述 | [`.claude/skills/catbus/SKILL.md`](https://github.com/cv-cat/catbus/blob/0a6e705f95d991ac3cdc896b774570479a23c0ad/.claude/skills/catbus/SKILL.md) | `52`, `63` | `-e app\|pc` 未实现（`NOT_IMPLEMENTED`）；`status=planned` 的命令会报 `NOT_IMPLEMENTED`，调用前应看 `note` |
| 5 | 评论能力的**已知限定**（自述） | [`docs/capabilities.md`](https://github.com/cv-cat/catbus/blob/0a6e705f95d991ac3cdc896b774570479a23c0ad/docs/capabilities.md) | `148–155` | bilibili `comment list` 支持视频/专栏/动态，**图文动态走非上游相簿接口、没有对拍**；`comment replies`（楼中楼）**非上游、没有对拍**，纯文字/转发动态未验证不支持；weibo `comment list` **只有一级评论**（`:150`）；kuaishou 二级评论只核对过一组参数（`:153`） |
| 6 | 分页限制（自述） | 同上 | `85`, `88` | weibo `item search` **只能取第一页**（m.weibo.cn 访客第二页起要登录）；douyin `item list` 取作品预览 |
| 7 | 登录态与限频（自述） | `SKILL.md` / `errors.md` | `95` / `99` | 登录态按平台隔离（`~/.catbus/`，文档称 0700/0600）；限频靠"留间隔、不并发"，**未见令牌桶式每分钟配额**（未见即未核实，不是"没有"） |

**结论**：catbus 的**工程形态（统一命令+JSON、写操作需 `-y`、风控即停、错误码分层）值得借鉴**；但**降级为"待验证候选"**——不预先把它列为项目全局依赖，理由：① 仓库 2026-09 新建、活跃但年轻；② 评论能力多处标注"非上游/没有对拍"；③ 未在本项目环境验证安装与只读路径。

> **不称"无执行干跑"**：`npx --help`／`npx <pkg>` 都可能触发**下载并执行**包；本任务**未安装、未运行** catbus（含 `--help`）。上一版把它写成"干跑"已更正。

### 2.3 `Cialle/RedCrack` @`a557e32` —— 不采用（首批）

| # | 观察点 | 永久链接 | 行 | 观察 |
| --- | --- | --- | --- | --- |
| 1 | 一级评论接口与游标分页 | [`request/web/apis/comments.py`](https://github.com/Cialle/RedCrack/blob/a557e328b6e723f63dcd75f1c52640794f2c84b5/request/web/apis/comments.py) | `17–36` | `get_comments(note_id, xsec_token, cursor="", …)` → `POST https://edith.xiaohongshu.com/api/sns/web/v2/comment/page`，body 含 `cursor`、`xsec_token` |
| 2 | 二级评论 | 同上 | `42–59` | `get_sub_comments(note_id, root_comment_id, num=30, cursor="")` → `…/comment/sub/page` |
| 3 | 写操作也在同一模块 | 同上 | `64, 84, 106, 124` | `create_comment` / `reply_comment` / `delete_comment` / `like_comment` —— **写操作与读操作混在同一客户端**，无确认层 |
| 4 | 自带翻页节奏 | 同上 | `160` | `get_all_comments(..., crawl_interval: int = 2, max_crawl_times: int = 3)` |

**许可**：`LICENSE`＝MIT（首行 `MIT License`）【源码观察】；`README` 声明"仅供个人学习、技术研究和交流使用"+法律免责【文档观察】。**两者口径不同，本报告只并列，不做法务裁定。**

### 2.4 `Ghauster/BilibiliCommentScraper` @`0b39e06` —— 只借鉴字段与断点

- 末次 commit **2023-04-25**（距观测日 2026-10-25 为 **42 个月**）；repo `pushed_at=2024-02-21`（距观测日 **32 个月**）【元数据】。上一版"停更约 1.5 年"为错误推算，已更正。
- `LICENSE`＝MIT【源码观察】；README 自述 Selenium 路线、二级评论字段（一级评论计数/隶属关系/被评论者昵称与 ID/评论者昵称与 ID/内容/时间/点赞）、`progress.txt` 断点、`cookies.pkl` 单次登录【文档观察】。
- **不采用其实现**（Selenium 重、停更）；借鉴字段清单与断点文件思路，落 SQLite 断点表。

### 2.5 旁证（只筛选，不深入）

| 仓库 | 观察 | 结论 |
| --- | --- | --- |
| `DropsDevopsOrg/ECommerceCrawlers` | 5,750★ MIT，`pushed_at=2024-05-22`；README 自述 **mitmproxy + selenium**、"免 cookie"抓淘宝系，含 `XianyuCrawler` 子目录【文档观察】 | **不采用**（中间人/绕过检测路线，与本项目边界冲突） |
| `dataabc/weibo-crawler` | 4,674★，根目录**无 LICENSE 文件**（contents 观察）；`open_issues_count=408`（**计数**，不等于已核对的已知故障） | 不采用（无许可声明） |
| `Nemo2011/bilibili-api` | 4,169★，**archived=true**、根目录**无 LICENSE**；`open_issues_count=141`（计数） | 不采用（归档+无许可） |

> 关于 issue 数：本报告一律写 `open_issues_count` 的**计数**，不代表我核对了具体故障内容。

## 3. 10 平台组 × 候选支持映射（研究层，不是接入验收）

| 平台组 | MediaCrawler（NC） | catbus（MIT，待验证） | RedCrack（MIT/README 冲突） | BiliScraper（MIT，停更） | 备注 |
| --- | --- | --- | --- | --- | --- |
| **B站** | 有（代码层有平台位；评论排序见 §2.1 #4） | 有（评论/楼中楼**非上游未对拍**） | — | 有（评论+二级） | 证据最足的一组 |
| **小红书** | 有 | 有（扫码常被拦，建议 cookie 导入） | 有（纯算逆向） | — | 风控最强 |
| **抖音** | 有 | 有 | — | — | 两侧都有，均未验证 |
| **贴吧** | 有（代码层 `tieba` 平台位） | **未列** | — | — | **覆盖缺口（唯一候选是 NC 许可）** |
| **微博** | 有 | 有（`item search` 只第一页；`comment list` 只一级） | — | — | 能力有明确限定 |
| **知乎** | 有（`zhihu` 平台位） | 仅"即将上线" | — | — | 两侧都不成熟 |
| **闲鱼（交易源）** | 未列 | 有（平台文件存在） | — | — | 只有 catbus 一侧 |
| **淘宝/天猫（交易源）** | 未列 | 有（cookie 登录） | — | — | 同上 |
| **京东（交易源）** | 未列 | 有 | — | — | 同上 |
| **拼多多（交易源）** | 未列 | 仅"即将上线" | — | — | 缺口 |

> 所有"有"均来自**锁定 commit 的代码/文档**或 README 自述，**未运行**；"平台 URL 能打开 ≠ 接通"仍然成立。

## 4. 复用立场（明确不预先批准）

| 候选 | 立场 | 理由（引用上面的行级证据） |
| --- | --- | --- |
| MediaCrawler | **只借鉴设计** | NC 许可（`LICENSE` 13/18 行）禁止商用；借鉴点：固定页长+页间 sleep（`core.py:202/248`）、评论排序枚举（`field.py:46–54`）、CDP 登录态默认（`base_config.py:59/83`） |
| catbus | **待验证候选（不作为全局依赖）** | MIT 只解决代码许可；评论能力多处"非上游/没有对拍"（`capabilities.md:148–155`）；本轮未安装未运行 |
| RedCrack | **首批不采用** | 纯算逆向 + 写操作无确认层（`comments.py:64–124`）+ 许可与 README 口径不同 |
| BiliScraper | **只借鉴字段/断点** | 42 个月未更新（`0b39e06` @2023-04-25）+ Selenium 重 |

## 5. 首批范围：给**与 V9 目标相容**的探测/替补路径（提案，不是裁定）

> V9 目标要求**≥3 平台且含交易源**。上一版"仅 B站 + 小红书/闲鱼降级为导入"**只是提案**，本版改为**三条可选路径**，每条都标注前置、验证点与失败替代；不需要你逐项拍板技术取舍，选一条即可启动。

| 路径 | 平台组合（含交易源） | 前置 | 最小验证点 | 失败后的替补 |
| --- | --- | --- | --- | --- |
| **P1（推荐先试）** | **B站**（公开只读评论）+ **微博**（公开只读，接受"只第一页/只一级评论"）+ **闲鱼（用户导入 CSV/JSON）** | B站/微博无需登录即可读公开页；闲鱼由你导出样例文件 | B站单视频评论第 1 页 20 条能取到 `cursor` 与二级入口；微博第一页可读；导入件能落库去重 | 微博若被拦 → 换知乎公开页；闲鱼导入失败 → 换淘宝/京东导入 |
| **P2** | **B站** + **知乎**（公开只读）+ **淘宝或京东（用户导入）** | 同上；知乎公开页可读性待测 | 知乎回答/评论第 1 页可取；导入件字段对齐 | 知乎若需登录 → 退回 P1 的微博 |
| **P3（最保守）** | **B站** + **小红书（用户导入）** + **闲鱼（用户导入）** | 你已有小红书/闲鱼导出或截图数据 | 两个导入件字段归一 + B站公开取数 | 导入质量不足 → 转 P1 |

- 三条路径都**不依赖 catbus 落地**（catbus 只作为后续加速选项）；也都不要求先解决登录。
- 交易源一律先走**用户导入**（风险最低）；自动采集交易源（闲鱼/淘宝/京东）需要先用 §7 的探测清单验证风控表现，再决定。

## 6. 风险与待你处理

1. **平台 ToS/个人数据**：评论含用户 ID/昵称/内容 → 本项目计划只存 `author_hash`（不存昵称与主页链接），不对外提供查询接口；**不绕过验证码**。
2. **许可**：MediaCrawler 的 NC 条款限制商用；catbus 的 MIT 不覆盖平台授权；RedCrack 的 MIT 与 README 口径不同。三者均**未做法务判断**。
3. **catbus 的验证码行为**：文档明确"不自动处理、把 `verify_url` 交用户"（`errors.md:35`），但这是**文档承诺**，未做行为验证；若将来引入，必须用只读路径实测"遇挑战即停在 exit 5"。
4. **登录**：任何平台登录只能你本人完成；本项目不读取/记录 cookie 值；`x-collect` 现有 profile 的账号已变为 `@Johnsmathjyjp`，**不等于长期可用**。
5. **稳定性**：catbus 仓库年轻（2026-09 建）；MediaCrawler `open_issues_count=217`（计数）；BiliScraper 42 个月未更新。

## 7. 下一阶段最小探测清单（交下一任务，本轮不执行）

| # | 探测 | 目的 | 前置/限制 |
| --- | --- | --- | --- |
| 1 | B站单公开视频评论第 1 页（20 条，只读） | 拿 `cursor`/`has_more`/二级入口字段 | 无需登录；单次请求 |
| 2 | 微博公开页第一页只读 | 核实"只第一页"的实际边界 | 无需登录 |
| 3 | 交易源导入：闲鱼/淘宝/京东任一份 CSV | 字段对齐 + 去重 + 落库 | 你提供样例（脱敏） |
| 4 | catbus 只读路径验证（**需你同意安装**） | 验证 `--help`/`doctor`/读命令遇挑战即停（exit 5） | Node ≥22；先装到隔离目录 |
| 5 | 贴吧候选补充检索 | 补唯一缺口 | 新一轮检索 |
| 6 | `RateLimiter` + 断点表（DDL 见上一版 §4，仍适用） | 让采集可恢复、可限频 | 不改实现前先评审 |

## 8. 本版修正记录（按退回意见逐项）

| # | 退回点 | 本版处理 |
| --- | --- | --- |
| 1 | 未锁 commit / 未读源码 | **锁定 4 个 commit sha**（§1.3）；对 MediaCrawler/catbus/RedCrack 各读 **2–3 个**与评论/分页/限流/登录直接相关的文件，给**永久链接＋行号＋实际观察**（§2.1–§2.3）；对**未读到**的实现（二级评论拉取、`CRAWLER_MAX_SLEEP_SEC` 默认值）明确标 **未核实**，**不再给"已完成源码深读"这类总括结论** |
| 2 | catbus 需与 RedCrack 同标准；不预先批准 | 并列记录 **MIT 许可**与 **README/SKILL 用途约定**（§2.2），**不做法务裁定**；新增三项专查：**验证码不自动处理**（`errors.md:28–35`）、**只读路径停在 exit 5**（`errors.md:30`）、**写操作需 `-y`/非 TTY 抛 `CONFIRM_REQUIRED`**（`confirm.ts:6–17`）；结论降为 **待验证候选**；并更正 **未运行 `npx`（含 `--help`）**，不称"无执行干跑" |
| 3 | X 证据 | 保留两条 `web_search` 查询与结果，明确 **"站点限定检索未命中，第三方线索"**（§1.2）；补读 `docs/validation/x-collect/REPORT.md` 并对**本机 x-collect 工具**做**有界只读** `--help` + `doctor`（exit=0，handle `@Johnsmathjyjp`，与旧报告 `@xluchuan` 不同），证据 [x_collect_probe.log](x_collect_probe.log)；**未运行 search**（输出落工具目录，超 scope） |
| 4 | 首批范围不能当成裁定 | 改为 **P1/P2/P3 三条与"≥3 平台且含交易源"相容的路径**（§5），各给前置/验证点/失败替代，**不要求你逐项拍板** |
| 5 | 可核对错误 | ① BiliScraper 末次 commit **2023-04-25 → 距观测日 42 个月**（repo `pushed_at` 2024-02-21 → 32 个月），删除"停更约 1.5 年"；② 两个同名 README **sha256 相同**（重复件，内容一致，非"不同版本"）；③ 44 个原始件**全部通过 UTF-8 严格解码**（`bad=0`），上一版"字段乱码"是**控制台按 ANSI 显示**所致，**文件本身未损坏**；④ issue 一律写 `open_issues_count` **计数**，注明不等于已核对故障 |

## 9. 仍未验证（如实列出）

1. 任何候选的**实际运行**：未安装、未 `npx`、未执行脚本、未采集。
2. **二级评论拉取实现**（MediaCrawler `get_sub_comments` 类）与 `CRAWLER_MAX_SLEEP_SEC` 默认值：未核实。
3. catbus 的 **captcha 行为**只有文档承诺，无行为验证；**未验证"只读命令遇挑战是否一定停在 exit 5"**。
4. 交易源（闲鱼/淘宝/京东）的**风控表现**、导入字段质量：未验证。
5. 贴吧、拼多多的可用候选：**缺口未补**。
6. 平台 ToS 与个人数据合规：未与条款逐条比对，本报告不做合规背书。
