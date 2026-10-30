# 抖音前置借鉴：GitHub 仓库核查（2026-10-30）

- 检索方式：GitHub REST API `search/repositories?q=douyin+comments+scraper`（2026-10-30 08:15Z 抓取），结果 8 个仓库，取与"评论采集"最相关的 5 个逐条核查。
- **声明**：以下只按仓库元数据与描述记录**可借鉴思路**，**没有克隆运行、没有实测**；不把 README 当能力证明。被测站点（抖音）本批零访问。

## 1. 核查表

| # | 仓库 | 日期 | commit | 许可 | 语言/依赖（据元数据） | 可借鉴点 | 局限 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | [Yang-hua6/CommentHound](https://github.com/Yang-hua6/CommentHound) | created 2026-08-04，pushed 2026-08-04 | `c2eb74231c42099c75d0c73a97ffcf4f74af714c`（Initial commit） | MIT | Python + Playwright（描述：XHR 拦截 + Flask + 钉钉签名） | **与我们微博的做法同源**：用 Playwright **拦截页面自身的 XHR** 拿评论，不破解签名；可借鉴"只信页面自己发的请求"这一判定思路 | 单 commit、2 star；无 CI/测试；未说明翻页与子回复处理；本批未运行 |
| 2 | [feng93321-netizen/douyin-comment-scraper](https://github.com/feng93321-netizen/douyin-comment-scraper) | created 2026-10-15，pushed 2026-10-18 | `174aa70d9641d88adcb18117643e1a0f315cb745`（"UI: 移除主/子评论类型标签列"） | **无 license 文件** | Python + Tkinter + iv8 + bdms SDK（描述：a_bogus 签名 + 主/子评论 + Excel 导出） | 明确区分**主评论/子评论**并导出，可借鉴其父子字段命名与"子评论属于主评论"的表达 | 依赖 `a_bogus` 签名逆向（iv8/bdms），**与我们的"页面自身请求"路线相反**；无 license 不可复用代码；1 star、无测试 |
| 3 | [yufeiyang111/douyin-mall-comments](https://github.com/yufeiyang111/douyin-mall-comments) | created 2026-09-05，pushed 2026-09-06 | 未取到 SHA（仅知 `main` 分支 pushed_at 2026-09-06） | MIT | Python + Playwright（描述：真实 Chrome + 商品弹窗自动化，"无需破解接口签名"） | **证明"不破签名、走浏览器自动化"可行**，与我们微博 RPA 路线一致；可借鉴其"等弹窗出现再取"的时序处理 | 面向**商城评价**而非视频评论；49KB 小仓、5 star；未运行 |
| 4 | [Annoyingwinter/douyin-comment-screen](https://github.com/Annoyingwinter/douyin-comment-screen) | created 2026-10-04，pushed 2026-10-04 | 未取到 SHA（`main`，pushed_at 2026-10-04） | MIT | Python + Electron + Playwright（描述：搜索/推荐流双模式 + IP 属地筛选） | "搜索流 vs 推荐流"两种入口的区分，可借鉴到我们 search/detail 的 surface 划分 | 桌面工具形态、2 star；未说明反爬与限速；未运行 |
| 5 | [EpicSaber/douyin-comments-scraper](https://github.com/EpicSaber/douyin-comments-scraper) | created 2026-06-14，pushed 2026-06-14 | 未取到 SHA | 无 license | 无代码（2KB，指向 Apify actor 的壳） | 仅作"托管式 actor"形态参考 | **无实际代码**，不可借鉴实现；0 star |

## 2. 对我们的取舍

- **采纳**：①"只调页面自身端点/拦截页面自身 XHR"（#1 与微博经验一致）；②主/子评论的父子字段表达（#2）；③等待目标容器出现再取（#3 的弹窗时序）。
- **不采纳**：`a_bogus`/`x-bogus` 签名逆向路线（#2）——与我们已验证的"页面自身请求 + 预算预扣"路线冲突，且会引入未文档化批量抓取风险。
- **明确标注**：以上均为**元数据级核查**，日期来自 GitHub API（`created_at`/`pushed_at`/commit `author.date`），**未克隆、未运行、未验证是否仍可用**。

## 3. 下一步（真实访问需新批次与用户同意）

1. 先用离线 `douyin doctor`（本地只读）确认 profile 是否存在；
2. 首次真实访问前，按微博经验先做一次**结构侦察**（`probe` 式），确认搜索结果与评论区的真实 DOM/端点是哪一类；
3. 评论优先走"页面自身 XHR + CDP 钩子（必须先 `Page.enable()`）"，与微博同一套路。
