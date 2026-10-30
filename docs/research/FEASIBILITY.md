# S1-A 来源与货源可行性核验报告

> 任务：`task-b337765c10e4f503e6a84776d1984e06`（计划 v2，S1-A）　执行者：`session-01ba487c-f808-55a7-a1f7-5f436ee12811`（A 来源与采集）
> 唯一策划者：`session-630d7dac-4fba-4074-b204-b614ddae1b35`；本文件仅写入 `docs/research/`，公共契约与台账由 B/C 维护。
> 观察时间基准：**2026-10-07 17:50（Asia/Shanghai）**，由 `https://timeapi.io/api/Time/current/zone?timeZone=Asia/Shanghai` 实测返回（同日另一次时间源尝试 `worldtimeapi.org` 抓取失败）。
> 核验方式：`web_search` + `web_fetch` 公开只读抓取；**未登录任何账号、未联系供应商、未下载资源、未运行货源软件、未调用 Shell、未写业务代码**。
> 声明：本次核验**不代表任何渠道"应用已接入"**；`web_search`/`web_fetch` 只是调研工具，不是本系统可以调用的数据 API；报告中的关键词、品类与链接均为线索，不是需求证据或销售许可。
> 版本说明：本版为按策划者返工意见修订后的版本——① 分离"许可原文核对 / 页面可读 / API 文档条件 / 端点本次调用 / 应用已接入"五个维度并改用研究标签；② 第 7 节统一以 B 契约 `format_version=1` 为应用格式；③ 追加策划者本轮独立观察（第 10 节）；④ 收窄库级许可边界并给出计数差异。

## 1. 结论摘要

| 渠道 | 一句话结论 | 公开可读 | 人工导入 | 应用可用接口 | 应用已接入 |
| --- | --- | --- | --- | --- | --- |
| 闲鱼 | 网页为 JS 空壳拿不到商品数据；官方协议全文可读；未发现/未验证公开数据接口 | 仅协议文本 | 推荐（保底） | 未验证（`open.goofish.com` 存在但正文不可读） | 否 |
| 小红书 | 网页跳登录、搜索页重定向异常、规则页与开放平台页为 SPA 空壳；官方规则标题可见但正文未读取 | 基本否（仅索引标题） | 推荐（保底） | 未发现 | 否 |
| B站 | 搜索页验证码、公开搜索接口 -412、热门接口 -352；**稿件详情 JSON 接口未登录实测可用（执行者本轮 B5 单次调用 HTTP 200 / `code=0`）** | 部分（详情接口） | 推荐（发现维度） | **是：`api.bilibili.com/x/web-interface/view`（仅"已知对象详情"，非发现型）** | 否 |

推荐首条接入路径（含证据，详见第 6 节）：

1. **需求侧先落"人工导入 + B站详情接口补全"**：B站 `x/web-interface/view` 是本次唯一实测返回结构化数据的渠道接口（HTTP 200、`code=0`），可用于按 `bvid` 自动补全标题、发布时间、UP主、统计字段；但它是页面前端接口、非官方授权 API，且不承担"发现"功能。
2. **货源侧首条自动化候选建议用 Met Open Access API**：许可（CC0）与 API **文档条件**（无需 Key；文档给出 80 请求/秒上限，**上限≠推荐频率**）均有文档证据；**端点调用目前只有策划者本轮的一次只读观察**（objectID=45734，见第 10 节），执行者未调用过端点——接入前须在应用内实测并设定更低速率。
3. **若要求"发现型自动入口"（关键词搜索）**：三渠道本次均**未获得可用入口**，属明确缺口，不得以本报告推断为已有能力（见第 6.3）。
4. **研究标签说明**：`SAMPLES.json` 只使用 `license_reviewed`、`lead`、`blocked`、`synthetic` 四种**研究标签**，只描述"本轮读到了什么"；它与 B 契约 `supply_offer.status`（`candidate`/`verified`/`invalid`/`stale`）以及四项入池门槛**没有任何映射**，不能作为可测试依据。观察者（执行者 / 策划者）单列为 `observer` 字段，**不新增第五种状态**，避免 legend 与计数歧义。

## 2. 四态口径与五个独立维度

### 2.1 四态（渠道状态，本报告统一使用）

| 状态 | 定义 | 判定要求 |
| --- | --- | --- |
| 公开可读 | 无需登录即可人工阅读页面文本 | 有实际抓取原文 |
| 人工导入 | 由用户把线索复制/导出为 CSV/JSON 交给系统 | 保底路径，不需要对方接口 |
| 应用可用接口 | 应用可程序化调用且本次有真实返回 | 调用证据（状态码/返回体） |
| 应用已接入 | 已在本系统内运行并可复现 | 本次**无任何一项**满足 |

`web_search`、搜索引擎索引、第三方教程文章都**不属于**"应用可用接口"；"页面能打开"不等于"可以免费自动获取"，更不等于"应用已接入"。

### 2.2 五个必须分开记录的维度（货源样例同样适用）

| 维度 | 含义 | 本次可核到的情况 |
| --- | --- | --- |
| 许可原文核对 | 是否读到了许可/条款原文并留有引用 | S-001～S-007 均读到；S-008/S-010 未读；S-009 被拦截 |
| 页面可读 | 页面本身是否可抓取（人工可读） | 多数来源可读；S-009 被反爬拦截 |
| API 文档条件 | 官方是否公布可自动访问的条件（限速、鉴权、计费） | 仅 S-001 读到明确条件；S-002 有 Feed/API 入口但条件未读；其余未读 |
| 端点本次调用 | 是否真的调用过接口并拿到返回 | 货源侧**执行者未调用任何端点**；Met 对象接口仅策划者本轮调用一次（第 10 节） |
| 应用已接入 | 系统内是否可复现运行 | **全部为否** |

**许可读过 ≠ 自动访问条件已核实**；"页面/raw 文件可读"只是页面维度，不能当作 API 条件。各维度未核到的一律保留为 **unknown**，不填 `true`。

## 3. 逐渠道核验记录

### 3.1 闲鱼（goofish.com，阿里巴巴旗下）

| # | 原始 URL | 实测结果 | 结论 |
| --- | --- | --- | --- |
| X1 | `https://www.goofish.com/search?q=%E6%A8%A1%E6%9D%BF` | HTTP 200，正文仅站点标题+Logo（JS 空壳），无任何商品字段（策划者本轮复测一致） | 商品搜索页公开可读=否 |
| X2 | `https://www.goofish.com/item?id=1018647119075&categoryId=0` | HTTP 200，同样空壳 | 商品详情页公开可读=否 |
| X3 | `https://open.goofish.com/` | HTTP 200，仅标题「闲鱼三方开发平台」，正文未渲染 | 存在第三方开发平台入口；接口清单、资质门槛、费用**均未验证** |
| X4 | `https://terms.alicdn.com/legal-agreement/terms/platform_service/20220929192826912/20220929192826912.html` | HTTP 200，全文可读；《闲鱼社区卖家服务协议》**版本生效日期 2025-09-17**（策划者本轮复测含 3.3.2/3.6.4/4.1 原文一致） | 官方协议公开可读 |
| X5 | `https://terms.alicdn.com/legal-agreement/terms/platform_service/20220929192101114/20220929192101114.html` | HTTP 200，全文可读；《闲鱼社区买家保障服务协议》**版本生效日期 2024-04-07** | 官方协议公开可读 |
| X6 | `https://h5.m.goofish.com/wow/z/activity/v1/DK25zQPCWkiaGQ63JaJf` | HTTP 200，仅标题「闲鱼社区保证金管理规范」，正文未渲染 | 保证金**具体金额标准未读取（缺口）**，未知不等于 0 |

官方协议原文依据（节选，供核对）：

- X4 第 3.3.2 条（六）禁止性信息包含"存在可能破坏、篡改、删除、影响闲鱼社区任何系统正常运行或**未经授权秘密获取闲鱼社区及其他用户的数据、个人资料的病毒、木马、爬虫等恶意软件、程序代码**的"。
- X4 第 3.3.3 条（禁止销售范围）："（一）国家禁止或限制的；（二）侵犯他人知识产权或其它合法权益的；（三）闲鱼社区规则、公告、通知或各平台与您单独签署的协议中已明确说明不适合在闲鱼社区上销售及/或提供的。"
- X4 第 3.6.4 条（数据使用）："除您依据相关法律有权进行商业性使用的数据外，您同意不对闲鱼社区上其他任何数据作商业性使用，包括但不限于在未经闲鱼事先书面批准的情况下，以复制、传播或向他方披露等方式使用在闲鱼社区站上其他用户展示的任何资料。"
- X4 第 4.1 条（费用）："除闲鱼社区明示的收费业务外，闲鱼向您提供的服务目前是免费的。"（费用线索，非报价）
- X5 第 2.1.1 条：经营者义务含"如实描述、七天无理由退货、其他保障义务"；第 3.3.1 条：类目/行业保证金"不应少于闲鱼社区公布的额度标准要求"，标准见《闲鱼社区保证金管理规范》（即 X6，正文未读取）。

得到/未得到的字段：

- 程序化字段：**无**（未获得任何商品条目、价格、时间等结构化字段）。
- 可读文本：官方协议条款（发布义务、禁售范围、数据使用限制、费用说明）。
- 时间信息：协议版本生效日期可读（2025-09-17 / 2024-04-07）；商品原始发布时间**不可得**。
- 发布条件：经营性卖家身份需资质核验/个人声明（X4 第 3.2.1 条）；禁售范围受第 3.3.3 条约束；虚拟商品是否有专门细则、保证金档位**待核验**。
- 费用线索：平台服务当前免费（X4 第 4.1 条）；保证金与"明示收费业务"的具体金额**未知**。
- 合规边界：X4 第 3.3.2(六)、3.6.4 对爬虫类程序与站内数据的商业性使用有明确限制，本系统后续若做该渠道自动化，须单列为风险项，不得引用本报告作为获取许可。

### 3.2 小红书

| # | 原始 URL | 实测结果 | 结论 |
| --- | --- | --- | --- |
| R1 | `https://www.xiaohongshu.com/search_result?keyword=%E6%A8%A1%E6%9D%BF` | 抓取报错：跨域重定向循环（http↔https www 之间），未取得正文 | 搜索页公开可读=否 |
| R2 | `https://www.xiaohongshu.com/explore` | 重定向到 `https://www.xiaohongshu.com/login?redirectPath=...`，返回登录页（策划者本轮复测一致：跳登录） | **需登录**；笔记与搜索公开读取不可用 |
| R3 | `https://open.xiaohongshu.com/` | HTTP 200，仅标题「小红书」 | 开放平台存在，正文 SPA 未渲染，接口与资质**未验证** |
| R4 | `https://school.xiaohongshu.com/rule/detail/36/10014`（搜索索引标题：虚拟商品交易争议处理细则） | HTTP 200，仅「小红书电商学习中心」空壳 | 官方规则**存在**（标题级证据），正文未读取（缺口） |
| R5 | `https://school.xiaohongshu.com/rule/detail/149/49587`（搜索索引标题：合规经营承诺函（电子资源）） | HTTP 200，同样空壳 | 同上；"电子资源"类目线索 |
| R6 | `https://miniapp.xiaohongshu.com/doc/DC950793` | HTTP 200，正文可读；文档更新时间 **2026-01-20**；内容为小程序/小组件"开放数据校验与解密"（`signature = sha1(rawData + session_key)`、AES-128-CBC 解密 `encryptedData`） | 开放平台文档**不等于**需求数据接口：面向小程序开发者与已授权用户会话，不提供笔记/需求检索 |

得到/未得到的字段：

- 程序化字段：**无**（未登录，笔记、评论、搜索均未取得）。
- 可读文本：仅 R6 的开发者文档正文；R4/R5 仅有搜索索引暴露的页面标题。
- 时间信息：R6 文档更新时间 2026-01-20（官方文档自带）；需求线索的原始发布时间**不可得**。
- 发布条件：官方学习中心确有"虚拟商品""电子资源"相关规则页面（标题级证据）；**正文未读取，规则细节待核验**。第三方文章所称"个人店保证金 1000 元"等仅作检索线索，本报告不采用为结论。
- 费用线索：**未知**（不得填 0）。

### 3.3 B站（bilibili.com）

| # | 原始 URL | 实测结果 | 结论 |
| --- | --- | --- | --- |
| B1 | `https://search.bilibili.com/all?keyword=%E6%A8%A1%E6%9D%BF` | HTTP 200，返回「验证码_哔哩哔哩」 | 搜索页风控拦截 |
| B2 | `https://api.bilibili.com/x/web-interface/search/type?search_type=video&keyword=%E6%A8%A1%E6%9D%BF` | **HTTP 412**，`{"code":-412,"message":"request was banned","ttl":1}`（策划者本轮复测一致） | 无签名/无 Cookie 直接调用被拒；未验证 wbi 签名路径 |
| B3 | `https://api.bilibili.com/x/web-interface/popular?ps=5&pn=1` | HTTP 200，`{"code":-352,"message":"-352","ttl":1}` | 风控 |
| B4 | `https://www.bilibili.com/video/BV14uUSBgEqM/` | HTTP 200，验证码页 | 视频 HTML 页公开可读=否 |
| B5 | `https://api.bilibili.com/x/web-interface/view?bvid=BV1us8MzPEmn` | **HTTP 200，`{"code":0,"message":"OK",...}` 完整 JSON**（策划者本轮复测一致） | **未登录可用**（详情维度；单次调用证据，非长期稳定性证明） |
| B6 | `https://api.bilibili.com/x/web-interface/view?bvid=BV14uUSBgEqM` | HTTP 200，`{"code":62002,"message":"稿件不可见"}` | 接口对不可见稿件返回明确状态码；不代表全部稿件可读 |
| B7 | `https://www.bilibili.com/blackboard/activity-obSbdouTvg.html`（哔哩哔哩工房使用规范） | HTTP 200，仅标题 | 工房规则存在，正文未渲染（缺口） |
| B8 | `https://openhome.bilibili.com/doc/4/eaf0e2b5-bde9-b9a0-9be1-019bb455701c`、`https://open-live.bilibili.com/document/849b924b-b421-8586-3e5e-765a72ec3840` | 均 HTTP 200，仅标题（SPA） | 官方开放平台存在，内容不可读，接口门槛/费用**未验证** |

B5 实测可得字段（原样取自返回 JSON）：

- 标识：`bvid`、`aid`、`cid`（分P）、`tid`
- 文本：`title`（"拼多多全域虚拟电商从零到1实操课"）、`desc`、`pages[].part`（分P标题）
- 主体：`owner.mid`、`owner.name`（UP主）
- 时间：`pubdate=1753349981`、`ctime=1753349982`；`pubdate` 换算为 **2025-07-24（Asia/Shanghai 约 17:39）**
- 统计：`stat.view/danmaku/reply/favorite/like/share/coin`（互动量，**只作热度，不作成交或盈利证据**）
- 其他：`duration`、`pic`、`rights`

时间缺失说明：B2/B3/B5 三次调用均未取得"原生发布时间以外的可靠时间字段"以外的信息；B1/B4 因风控无法读取页面上可能存在的其他时间。

发布条件线索：B站工房存在《哔哩哔哩工房使用规范》《工房违规及纠纷处理规范》等页面（搜索索引与 B7 标题级证据），**正文未读取**，虚拟物品发布条件待核验（缺口）。

> 渠道层复测：策划者本轮独立复测 X1、X4、R2、B2、B5，结果与本表一致（见第 10 节）。历史观察按当时时点保留，不因本轮结果改写。

## 4. 需求发现维度与搜索覆盖

### 4.1 扩词方法（人群 × 具体任务 × 行业/工具 × 时间节点）

| 维度 | 说明 | 扩词示例（**模板，非需求证据，非销售许可**） |
| --- | --- | --- |
| 人群 | 具体身份/处境 | 应届生、考公考研、教资、留学生、宝妈、个体店主、自由职业、教师、护士、程序员、财务 |
| 具体任务 | 要交付的成果物 | 简历、开题/论文、答辩PPT、周报月报、标书、合同台账、成绩分析、排班表、海报、LOGO、剪辑、脚本、数据整理 |
| 行业/工具 | 领域与工具链 | Excel/Word/PPT/WPS、剪映、PS/AI、LaTeX、Notion/飞书、小程序、电商运营、宠物、汽车、装修 |
| 时间节点 | 触发时点 | 开学/期末、3–4 月复试、6 月毕业、9 月秋招、11 月大促、年末年初总结、报税季 |

组合方式示例：`{人群} × {任务} × {时间节点}`（如"应届生 × 简历模板 × 9月秋招"）、`{行业/工具} × {任务}`（如"装修 × 报价单模板"）。新增品类一律**先入线索池**，不作为可发布商品。

### 4.2 信号类型（必须区分，不得混用）

卖家宣传 / 用户明确求助 / 明确求购 / 可复查经营记录；互动量（浏览、点赞、收藏）**只作热度**，不冒充成交、不证明盈利。

### 4.3 本次实际执行的检索与覆盖边界

本次实际执行 `web_search` 共 5 次、合计 20 条查询（用途均为渠道可达性、官方规则与官方开发平台定位，未做系统性关键词采样），按主题归并如下：

1. 闲鱼开放平台 API 接口 文档 / 闲鱼 虚拟商品 发布规则 官方 社区公约
2. 小红书开放平台 接口文档 open.xiaohongshu.com / 哔哩哔哩开放平台 开发者文档 open.bilibili.com
3. 闲鱼 规则中心 site:goofish.com / 闲鱼开放平台 官方 申请 API / 小红书 商家学习中心 虚拟商品 类目 规则 / 哔哩哔哩工房 虚拟商品 规则 官方
4. 闲鱼 规则中心 goofish.com/rule 发布规范 / 小红书 电商学习中心 虚拟商品 规则 school.xiaohongshu.com / site:bilibili.com/video 虚拟商品 教程 / 闲鱼 帮助中心 交易规则 官方
5. 闲鱼社区信息发布规范 site:goofish.com / 闲鱼 规则中心 goofish 官方 入口 / site:xiaohongshu.com/explore 求推荐 / site:goofish.com/item 求购
6. site:school.xiaohongshu.com 虚拟商品 类目 规则 / 闲鱼 保证金 管理规范 虚拟商品 发布 规则 / 哔哩哔哩 工房 虚拟物品 交易 规范 / 小红书 电子资源 类目 保证金 官方规则

覆盖边界（必须随结论一起使用）：

- 本次只验证"渠道是否可达、是否有官方规则/接口入口"，**没有做系统化的需求关键词采样**；
- 因此本报告不包含任何"某品类有真实需求"的结论，第 4.1 的示例词只是扩词模板；
- 检索结果中的第三方文章（阿里云开发者社区、腾讯云社区、知乎、法律问答、自媒体等）**仅作检索线索，未采用为结论**；
- 会话搜索工具与搜索引擎索引不属于本系统的数据渠道；
- 本轮返工未新增公开查询（仅本地读取 B 契约 `docs/design/CONTRACT.md`），避免为数量追加检索。

## 5. 货源可行性核验（与 `SAMPLES.json` 对应）

样例索引见同目录 [`SAMPLES.json`](SAMPLES.json)，编号一一对应；**该文件是研究索引，不是应用导入文件**（转换规则见第 7 节）。当前共 **12 条**：`license_reviewed` 8 条（执行者 7 + 策划者转记 1）、`lead` 2 条、`blocked` 1 条、`synthetic` 1 条；状态集合只有这四种，观察者由 `observer` 字段单独标明。

### 5.1 样例摘要（状态为"研究标签"，非应用状态）

| 编号 | 名称 | 类别 | 许可（实测） | 可商用 | 可转售 | 自动访问条件 | 研究标签 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| S-001 | The Met Open Access（API） | 数字馆藏图片/元数据 | CC0 1.0 | 是 | 是 | **文档条件已读**：无 Key；上限 80 请求/秒（非推荐频率）；端点仅策划者单次调用 | license_reviewed |
| S-002 | Openclipart | 矢量剪贴画 | 公有领域（CC0） | 是（FAQ 明示 "unlimited commercial use"） | 依 CC0 允许（建议逐件复核 `pd_issue` 标记） | 站点可读；**Feed/API 条件未读** | license_reviewed |
| S-003 | Simple Icons | 品牌图标（库） | CC0 1.0 | 是 | 是（商标权不随 CC0 授予） | 仅知 GitHub raw 可读；**API 条件未读** | license_reviewed |
| S-004 | Lucide | 通用图标（库） | ISC（Feather 派生部分 MIT） | 是 | 是（需保留版权与许可声明） | 官网/仓库可读；**API 条件未读** | license_reviewed |
| S-005 | 得意黑 Smiley Sans | 中文字体（库） | SIL OFL 1.1 | 是 | **字体本身不得单独售卖**，可随文档/软件分发 | 仅知 GitHub raw 可读 | license_reviewed |
| S-006 | 霞鹜文楷 LXGW WenKai | 中文字体（库） | SIL OFL 1.1 + 保留字体名附加许可 | 是 | 同上，不得单独售卖字体本身 | 仅知 GitHub raw 可读 | license_reviewed |
| S-007 | billryan/resume | LaTeX 简历模板 | MIT | 是 | 是（保留版权与许可声明） | 仅知 GitHub raw 可读 | license_reviewed |
| S-008 | 微软 OfficePLUS | PPT/Word/Excel 模板 | **未读取**（页面另有会员权益入口） | 未知 | 未知 | 站点可访问；批量/接口条件未验证 | lead（付费候选，价格未知） |
| S-009 | Unsplash | 摄影图库 | **未读取**（官方许可页被反爬拦截） | 未知 | 未知 | 抓取被 Anubis 拦截（HTTP 401） | blocked |
| S-010 | 国家标准全文公开系统 | 标准文件（信息整理类） | **未读取**；页脚标注"版权所有 侵权必究" | 未知 | 未知 | 站点可访问（部分条目"可在线阅读和下载"） | lead |
| S-011 | Pexels | 摄影图库 | 许可正文已读并留有逐字摘录（observer=planner；见 5.5） | 交付场景条件：允许用于售卖模板（策划者转述） | 限制：不得原样出售、不得在其他素材/壁纸平台再分发（策划者转述） | 站点可访问；**API 条件未验证、单件素材/API 价格未逐件核验** | license_reviewed（observer=planner） |
| SYN-001 | 合成示例条目 | 仅演示字段格式 | 无（合成） | — | — | — | synthetic |

### 5.2 规则与边界（本轮修订重点）

- **维度分离**：上表"自动访问条件"列只写本轮真实核到的内容；未读到的条件保留为 unknown（在 `SAMPLES.json` 中为 `null`），不写 `true`；"许可读过"不等于"自动访问条件已核实"。
- **库级许可 ≠ 单件素材明确授权**：S-003、S-004 等核到的是**库/文件级许可**；单件素材的商标、品牌使用规范、嵌入依赖与平台单独条款**未逐件读取**，一律保留 unknown。真正用于某件商品前，必须逐件复核。
- **免费且可商用 ≠ 已通过销售四门槛**：四项门槛（需求、货源及分发条件、成本、对应平台发布条件）各有独立证据要求；`license_reviewed` 只是研究标签，**不构成可测试依据**，也不映射 B 契约 `supply_offer.status` 或四项门槛判定。
- **免费且满足需求的现成来源优先**：S-001～S-007 属于"许可原文已读"的免费来源，但**一律未下载、未验货**；
- **付费来源只列待确认候选**：S-008 会员价格未知（未知≠0）；未做任何采购、付款或联系；
- **未知不填假值**：所有未读取到的字段在 `SAMPLES.json` 中为 `null` 并登记在 `unknowns`。

### 5.3 访问失败记录与"时点差异"（原样留档，不互相否定）

| URL | 执行者 2026-10-07 观察 | 策划者本轮复测/新观察 |
| --- | --- | --- |
| `https://unsplash.com/license` | HTTP 401，Anubis 反爬验证页 | （未复测） |
| `https://www.pexels.com/license/` | HTTP 403，Cloudflare "Just a moment..." | **HTTP 200，正文完整**（条件见第 10 节） |
| `https://pixabay.com/service/license-summary/` | HTTP 403，Cloudflare | （未复测） |
| `https://www.metmuseum.org/about-the-met/policies-and-documents/open-access` | HTTP 429，Vercel Security Checkpoint | 官方 API 文档页 `metmuseum.github.io` 可读（CC0/无 Key/80 rps/v1.1 迁移） |
| `https://www.si.edu/openaccess` | HTTP 403，Smithsonian 请求验证页 | （未复测） |
| `https://commons.wikimedia.org/wiki/Commons:Licensing` | 连续 3 次 `fetch failed` | （未复测） |
| `https://openclipart.org/faq` / `/share` | `/faq` 超时；`/share` 二次尝试成功返回 FAQ 正文 | `/share` 复测两次 30s 超时 |
| `https://raw.githubusercontent.com/...`（多条） | smiley-sans / lxgw / simple-icons / billryan 均 HTTP 200；twbs/icons 与 Awesome-CV 为 404；adobe source-han-sans `fetch failed` | 两条 raw 请求 `fetch failed`（新时点） |
| `https://worldtimeapi.org/api/timezone/Asia/Shanghai` | `fetch failed`（改用 timeapi.io 成功） | （未复测） |
| `https://www.slidescarnival.com/terms-of-use` | HTTP 200 但正文未呈现，条款未读取（未采用） | （未复测） |

> 读法：同一 URL 在不同时点可能返回不同结果（地区、风控策略、反爬强度变化）。**新观察不否定旧观察，两者都留档**；后续接入必须以接入时点的实测为准。

### 5.4 目录入口（可复查，均未批量下载）

Openclipart 的 `/feed` 与 `/developers`；Met 的 `metmuseum.github.io` 与 GitHub 数据集仓库 `https://github.com/metmuseum/openaccess`；各 GitHub 仓库的 raw 许可文件路径（见 `SAMPLES.json` 的 `license_evidence_url`）。

### 5.5 S-011（Pexels）条目说明：observer、逐字摘录与"许可摘要 / 交付场景条件"分开

- **观察者与来源**：`observer=planner`（策划者本轮独立调用 `https://www.pexels.com/license/`，HTTP 200、正文完整；此前执行者观察到 403，两次观察并存）。本条为**转记**，不并入执行者证据链；**确切观察时点未提供**，因此 `license_verified_at=null`，来源与轮次写入独立的 `observation_note`，不放进时间字段。
- **许可原文状态**：`license_text_read=true`（策划者已读完整许可原文），并**留有逐字摘录**（`quote_recorded=true`，`quote_source=planner_web_fetch`）。摘录如下（本报告转记）：
  - 「All photos and videos on Pexels can be downloaded and used for free.」
  - 「Use the photos and videos online ... a template you sell.」
- **交付场景条件（与许可摘要分开记录）**：**允许**在售卖模板等交付场景中使用；**限制**：不得原样出售，且不得在其他素材/壁纸平台再分发（沿用原稿要点）。限制条款的完整边界未逐条读取。
- **价格边界（不得外推）**：许可页明确 **Pexels 资源可免费下载并使用**；但**所选单件素材与 API 的价格条件未逐件核验**——**不得由"许可免费"推断 API 免费，也不得据此推断转售已通过**。价格字段保持未知（`null`），未采购。
- **尚未验证**：API 条件（是否提供接口、限速与鉴权）未验证；未下载、未验货。
- **标签**：沿用 `license_reviewed`（不新增状态值）；"是否读过原文"与"是否留下逐字摘录"由 `license_text_read` 与 `quote_recorded` 两个字段分别记录。

## 6. 推荐首条接入路径（证据、理由与限制）

### 6.1 需求侧：人工导入为发现层 + B站详情接口为补全层（建议先做）

- 证据：B5 实测 `https://api.bilibili.com/x/web-interface/view?bvid=BV1us8MzPEmn` 返回 HTTP 200 与 `code=0` 的完整 JSON（含 `title/pubdate/owner/stat/pages`），未登录；策划者本轮复测一致；B6 说明接口对不可见稿件会返回 `code=62002`，行为可预期。
- 理由：这是三条渠道中**唯一**在本次核验里拿到真实结构化数据的接口；用户人工把线索链接（含 B站视频链接）导入系统后，系统可用该接口自动补全标题、发布时间、UP主与统计字段，形成"导入 → 标准化 → 存储 → 详情回溯"的第一条可用链路。
- 限制：① 它是网页前端接口，**未获得官方授权**，无契约与 SLA，可能变更或限流；② 只解决"已知 bvid 的详情"，**不解决关键词发现**；③ B站搜索接口已实测 -412、搜索页验证码；④ 后续接入必须限速、缓存、失败重试有上限，且不得作为唯一证据来源。

### 6.2 货源侧：Met Open Access API（建议作为第一条自动化候选）

- 证据（**文档条件**）：`https://metmuseum.github.io/` 原文 "select datasets of information on more than 470,000 artworks ... for unrestricted commercial and noncommercial use"，已用 CC0；"we do not require API users to register or obtain an API key to use the service. Please limit request rate to 80 requests per second"；文档同时说明 `v1/search` 于 2026-10-01 退役、改用 `v1.1` 分页。
- 证据（**端点调用**）：仅策划者本轮单次只读调用对象接口（objectID=45734，HTTP 200，返回真实 JSON，含 `isPublicDomain=true`、`primaryImage`、`metadataDate`；见第 10 节）。**执行者未调用过端点**，因此"可用性"目前只有一次独立观察，不是长期稳定性结论。
- 理由：许可与访问条件（文档级）同时核到，无需付费与 Key，适合做小批量、可缓存的素材查询，符合"免费且现成货源优先"。
- 限制：① 80 请求/秒是**文档上限，不是推荐频率**，接入时须设更低速率、缓存并记录失败；② 数据结构是"馆藏元数据/公版图像"，只能服务素材型虚拟商品；`isPublicDomain` 需逐件核对，未下载验货；③ CC0 不授予商标等第三方权利。

### 6.3 明确缺口：发现型自动入口

闲鱼、小红书、B站三条渠道本次**都没有**取得可用的"关键词发现"入口：闲鱼/小红书需登录或受风控直接拒绝；B站搜索接口返回 -412、搜索页验证码。若策划者要求"发现型自动链路"，当前应如实保留为缺口，建议的候选方向（需用户确认后再排任务，均未验证）：

1. 用户在自己的浏览器中登录后，把可见结果**人工复制/导出**为 CSV/JSON 交给系统（即第 7 节导入方案）；
2. 用户提供"链接清单"（如搜索结果页链接、笔记链接），系统按 6.1 的方式做读取与补全；
3. 长期再评估官方开放平台（闲鱼三方开发平台、小红书开放平台、B站开放平台）的资质与费用——本次三处均只有 SPA 空壳，**接口清单、资质门槛、费用一律未知**。

## 7. 人工导入保底建议（统一以 B 契约 format_version=1 为应用格式）

本节不定义第二套 CSV/JSON 格式；应用导入格式以 `docs/design/CONTRACT.md` §4（**`format_version=1`**）为准。下表只把研究侧字段对齐到契约列名，凡契约仍在修订的命名/取值均标注**待 B 冻结**。

### 7.1 研究字段 → 契约列映射（映射仍在 B 侧修订，未冻结）

| 研究字段（本报告 / `SAMPLES.json`） | B 契约列（format_version=1） | 落地实体 | 备注 |
| --- | --- | --- | --- |
| `source_channel` | `demand_source` | 经 `demand_signal.source_id` 关联 `source` | 契约缺省 `manual_import`；`xianyu`/`xiaohongshu`/`bilibili`/`manual` 的规范化命名**待 B 冻结** |
| `source_url` | `demand_url` | `demand_signal.url` | 需求组出现任一字段时必填 |
| `raw_text_excerpt` | `demand_excerpt` | `demand_signal.excerpt` | ≤4000 字符，不改写原意 |
| `signal_type` | `demand_kind` | `demand_signal.signal_kind` | 卖家宣传→`seller_promo`；明确求助→`specific_ask`；明确求购→`want_to_buy`；经营记录→`business_record` |
| `native_id` | `demand_native_id` | `demand_signal.native_id` | 可空 |
| `observed_at` | `observed_at` | `demand_signal.observed_at` | `*_at` 带时区；缺省取导入时刻 |
| `published_at` | `demand_published_at` 或 `demand_published_date`（至多一个） | `demand_signal` | 不可得留空 = 未知 |
| `interaction_stats` | `demand_engagement` | `demand_signal.engagement_json` | 契约 V20：不参与门槛与排序证据权重 |
| `evidence_level` | **无等价列** | — | 保留为研究元数据；契约用 `evidence.fact_kind`（`fact`/`estimate`/`assumption`），"事实/估算"可对应，"待核验"无等价物 → **待 B 协调** |
| `stats_observed_at` | **无等价列** | — | 保留研究元数据（或并入 `notes`）→ **待 B 协调** |
| `notes` | `notes` | `candidate.notes` | ≤2000 字符 |

### 7.2 合成示例（引用 B 契约列名；`data_origin=synthetic` + 示例域）

```csv
title,data_origin,observed_at,demand_source,demand_url,demand_excerpt,demand_kind,demand_native_id
示例-合成演示行-不得作为真实线索,synthetic,2026-10-07T18:00:00+08:00,manual_import,https://example.com/demand/demo-0001,（合成示例摘录）,specific_ask,
```

- 该行**不是第二套可导入格式**，只是引用契约列名演示映射关系；也不是本报告采集到的真实线索。
- `stats_observed_at`、`evidence_level` 等尚无契约列的字段**不进入示例行**，仅作为研究元数据保留。

### 7.3 转换与幂等（研究侧建议，不构成契约）

- **转换**：`SAMPLES.json` 是研究索引，不是应用导入文件；如需导入，先由 B 冻结映射，再按契约校验（V1–V20）执行。**转换不得自动升级任何门槛或状态**——"免费可商用"不等于四项门槛通过，`license_reviewed` 不等于 `supply_offer.status='verified'`。
- **幂等/去重**：唯一依据为 B 契约 **§4.5（最终冻结版为准；B 正在返工，本报告不引用其旧稿中的具体强键，避免与将冻结的键冲突）**。研究侧需该节明确的三点协调项：① 去重范围必须包含**真实/合成隔离**（不得跨 `data_origin` 归并）；② `native_id` 缺失时使用**规范化 URL 兜底**；③ 同一机会**整行再导入不得丢成本项**（货源/费用更新不得因需求指纹命中而被整体跳过）。以上均为待冻结事项，研究侧不预设实现，也不另建一套规则。
- **未知值**：契约 §0.4 规定 `NULL`=未知、`0`=已知零；研究侧空值一律留空，不写 0、不写"无"。
- **时间**：统一 ISO 8601 带时区；来源只给日期时用 `*_date`。

## 8. 未覆盖与后续建议（缺口清单）

1. 闲鱼虚拟商品的专门规则与保证金档位：X6 正文未渲染，**未读取**；需另找官方渠道（如规则中心可达页面）核对。
2. 小红书"虚拟商品/电子资源"细则正文、保证金与类目准入：R4/R5 仅有标题；**未读取**。
3. B站工房（虚拟物品）发布与结算规则正文：B7 仅有标题；**未读取**。
4. 三个官方开放平台的接口清单、资质门槛、费用：均为 SPA 空壳，**未验证**。
5. B站 `wbi` 签名后的搜索接口是否可用：本次**未尝试**（无 Shell、无签名工具），不得假设可用。
6. 所有货源样例**未下载、未验货**；S-001～S-007 只核到**库/文件级许可**与页面可读性，**除 S-001 的文档条件外未核任何站点 API 条件**。
7. 付费来源价格（S-008）、平台费用（保证金、支付费率）**全部未知**。
8. 未做需求关键词的系统化采样，因此**没有任何品类层面的需求结论**。
9. 单件素材条款（商标/品牌规范/嵌入依赖/字体随文档嵌入与保留名适用）**未逐件读取**，保留 unknown。
10. S-011（Pexels，observer=planner）：许可原文已读并留有逐字摘录（见 5.5）；**仍未核**：API 条件、所选单件素材与 API 的价格条件（不得由许可免费外推）、限制条款完整边界、验货；观察时点未提供（`license_verified_at=null`，来源见 `observation_note`）。

## 9. 工具、技能与失败记录

- 技能目录检查：本会话技能目录为 Office/Cordis/前端/代码精简类，**没有匹配"公开来源核验"的专用技能**；本会话工具集中也未提供技能加载工具，故未加载任何技能（如实记录，未假称已加载）。任务匹配的工具为 `web_search`、`web_fetch` 与文件工具（`read/write/glob/grep`）。
- Shell：保持关闭，未执行任何命令；未安装依赖、未启动程序、未跑测试。
- 写入范围：仅 `docs/research/FEASIBILITY.md` 与 `docs/research/SAMPLES.json`；未改动 `PRODUCT.md`、`DEVELOPMENT_PLAN.md`、`DEVELOPMENT_PROGRESS.md` 及 B/C 范围文件（本轮仅为对齐格式**只读** B 的 `docs/design/CONTRACT.md`）。
- 本轮修订：① 五个维度分离 + 研究标签 `license_reviewed`（替代原 `verified` 表述）；② 第 7 节改用 B 契约 `format_version=1`；③ 新增第 10 节（策划者独立观察转记）；④ 收窄库级许可边界、修正原"许可与访问条件均可复查"的过度概括。
- 失败记录汇总见第 5.3 节与第 3 节各表。所有失败按"时点 + 来源"原样保留，未以推断替代。

## 10. 策划者本轮独立观察（转记，非执行者调用）

以下为策划者在本轮核验中**自行调用工具**得到的结果，本报告只做转记并标明来源；这些观察不并入执行者的证据链，也不改变第 3、5 节的执行者观察记录。

| # | 观察者 | 对象 | 结果 |
| --- | --- | --- | --- |
| P1 | 策划者 | 闲鱼 X1 / X4 | X1 HTTP 200 仅标题/Logo；X4 卖家协议含生效日期 2025-09-17 及 3.3.2 / 3.6.4 / 4.1 原文——与执行者一致 |
| P2 | 策划者 | 小红书 R2 | 跳登录——与执行者一致 |
| P3 | 策划者 | B站 B2 / B5 | B2 HTTP 412 / `code=-412`；B5 HTTP 200 / `code=0` 完整 JSON——与执行者一致 |
| P4 | 策划者 | Met 官方 API 文档 | 实读 CC0、无需 Key、80 请求/秒及 v1.1 分页迁移说明 |
| P5 | 策划者 | Lucide 许可页 | HTTP 200，明确 ISC / MIT 与保留声明 |
| P6 | 策划者 | **Met 对象接口** | 只读调用 objectID=45734 返回 HTTP 200 真实 JSON，含 `isPublicDomain=true`、`primaryImage`、`metadataDate`；**无图像下载**（已登记为 S-001 的端点调用证据） |
| P7 | 策划者 | **Pexels 许可页** | 本轮 HTTP 200 且正文完整（执行者此前记录为 403，两次观察并存）；许可原文已读并留有**逐字摘录**（见 5.5 与 S-011 的 `license_evidence_quote`）：资源可免费下载使用、允许用于售卖模板；**限制原样出售**、限制在**其他素材/壁纸平台再分发**；**API 条件与单件素材/API 价格均未核**（不得由许可免费外推）。已登记为 **S-011**，标签沿用 `license_reviewed`、观察者单列 `observer=planner`、观察时点未提供（`license_verified_at=null`） |
| P8 | 策划者 | Openclipart `/share`、GitHub raw | `/share` 复测两次 30s 超时；两条 raw 请求 `fetch failed`——属新时点观察，与执行者此前的成功记录并存，不互相否定 |

> 核对提示（给策划者与后续执行者）：可复测的关键链接为 X1、X4、X5、R2、R6、B2、B5、B6、`https://metmuseum.github.io/`、`https://openclipart.org/share`、`https://www.pexels.com/license/`，以及第 5.3 节失败表中任意两条拦截类 URL。**结果可能因时点、地区、风控策略与登录状态而不同**（例如 Pexels 许可页在两次观察中分别为 403 与 200、Openclipart `/share` 一为成功一为超时）；出现差异时应**留档并存**，不以单次观察否定另一次，也不得据此推断长期可用性。
