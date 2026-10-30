# 百度贴吧前置借鉴：GitHub 仓库核查（2026-10-30）

- 检索方式：GitHub REST API `search/repositories?q=tieba+爬虫+OR+spider+OR+scraper&sort=stars`（2026-10-30T08:25Z 抓取，`total_count=1778`），取前 5 个逐条核查。
- **声明**：仅**元数据级**核查（日期/许可/语言/描述），**未克隆、未运行、未验证可用性**；不把 README 当实测能力。本批零访问贴吧。

## 1. 核查表

| # | 仓库 | 日期 | commit / pushed_at | 许可 | 依赖（据元数据） | 可借鉴点 | 局限 / 是否采纳 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | [Sitoi/dailycheckin](https://github.com/Sitoi/dailycheckin) | created 2021-05-26 | commit 未取到；`pushed_at 2026-07-09` | **MIT** | Python（Docker/青龙），topics 含 `tieba` | 多平台签到脚本里**cookie 复用**与请求节流的工程写法；与我们"预算预扣 + 最小间隔"同思路 | 是**签到**不是采集，没有帖子/评论解析；**部分采纳**（只借节流与 cookie 名称管理，不借业务逻辑） |
| 2 | [HuanCheng65/TiebaLite](https://github.com/HuanCheng65/TiebaLite) | created 2020-04-05 | commit 未取到；`pushed_at 2024-02-17` | **GPL-3.0** | Android（Java/Kotlin，默认分支 `4.0-dev`） | 第三方客户端，可了解贴吧**接口/字段命名**（吧、帖、楼中楼） | GPL-3.0 **不可直接复用代码**；只能作为字段语义参考；**仅参考** |
| 3 | [CharlesPikachu/videodl](https://github.com/CharlesPikachu/videodl) | created 2018-07-10 | commit 未取到；`pushed_at 2026-10-30` | **NOASSERTION（other）** | Python，纯标准库风格 | 贴吧**视频直链**解析思路（帖子内嵌视频） | 许可不明确，**不采纳代码**；仅记思路 |
| 4 | [MoeNetwork/Tieba-Cloud-Sign](https://github.com/MoeNetwork/Tieba-Cloud-Sign) | created 2014-04-13 | commit 未取到；`pushed_at 2026-10-22` | **NOASSERTION** | PHP | 长期维护的贴吧接口封装（登录态、吧列表、签到），可参考**接口路径命名** | 许可不明确 + 语言不同；**不采纳代码** |
| 5 | [GuhDoy/TiebaTS](https://github.com/GuhDoy/TiebaTS) | created 2021-02-19 | commit 未取到；`pushed_at 2024-08-07` | **GPL-3.0** | Kotlin（Xposed，**已归档**） | 客户端 UI 改动，与采集无关 | 已归档、GPL、非采集；**不采纳** |

> 5 个仓库的 commit SHA 均未取到（GitHub 搜索接口只给 `pushed_at`），已按要求标注。

## 2. 对我们的取舍

- **采纳**：①cookie **名称**级管理与请求节流（#1，与我们的账本/间隔一致）；②吧/帖/楼中楼的字段语义（#2，只作命名参考，不复制代码）。
- **不采纳**：任何 GPL/NOASSERTION 仓库的代码；任何"绕过登录/签名"的做法（贴吧没有类似 a_bogus 的强制签名，我们也不需要）。
- **路线**：与微博/抖音一致——**页面自身请求 + 预算预扣 + 风险锁**；先结构侦察（列表页 `/f?kw=`、帖子页 `/p/<tid>`）再谈评论。

## 3. 下一步（真实访问需新批次与用户同意）

1. 先跑离线 `tieba doctor`（只读 profile/cookie 名称）；
2. 首次真实访问做一次**结构侦察**：列表页 `https://tieba.baidu.com/f?kw=<kw>`（`/p/<tid>` 链接与标题）、帖子页 `https://tieba.baidu.com/p/<tid>`（标题/楼层/楼中楼 DOM）；
3. 评论若走页面 XHR，先 `Page.enable()` 再挂钩子（微博踩过的坑），并用 `network` 审计确认端点；
4. 拿到端点前，`comments` 保持**显式 unsupported**（当前实现即如此，且在预扣前返回）。
