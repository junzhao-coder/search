# P1 前置借鉴核查（微博采集）

> 任务 `task-d0f8c614abbc346b5f06749fcbe7e874`（V10-4，离线批次）。
> 检索日期：**2026-10-27**（UTC+8 22:29–22:33）。
> **本批零真实请求**：未向 weibo.com / m.weibo.cn / api.weibo.com 或任何微博域名发过请求；本文所有微博相关结论均来自**公开仓库文档与元数据**，不是我们的实测。

## 0. 检索方式与工具可用性（必须先读）

| 项 | 状态 |
| --- | --- |
| `agent-reach` 技能 | **未获取 / 不可用**：本机 `node_modules` 下无该技能目录，`PATH` 中无 `reach` / `agent-reach` CLI。 |
| 替代方案 | 用内置 `web_fetch` 直连 **GitHub 公开 API**（`api.github.com`）与 `raw.githubusercontent.com` 读取仓库元数据与 README。 |
| `web_search` | **不可用**（端点未配置返回错误），因此无法做关键词广搜。 |
| **X（Twitter）讨论** | **未获取**：无 X 检索通道（无 agent-reach、无 web_search），本批没有读到任何 X 帖子。**本文不含任何 X 结论**。 |
| 微博站点 | **全程未访问**（本批硬约束）。 |

> 结论口径：下文每条都标注 `读到`（README/API 元数据原文）或 `实测`。**本批"实测"列全部为空**，因为我们没有运行任何被借鉴项目、也没有访问微博。

## 1. 逐条记录

### 1.1 Xarrow/weibo-scraper

| 项 | 值 |
| --- | --- |
| 原链接 | https://github.com/Xarrow/weibo-scraper |
| 仓库/项目名 | `Xarrow/weibo-scraper`（PyPI 包名 `weibo-scraper`） |
| 版本/commit | **`0a8cce7edfd797b106236186d64922732a5007db`**（2022-11-26，"feat: update version to `1.0.7rc1.dev3`"）；README 版本文档写作 `weibo-scraper-1.0.7-beta` |
| 许可 | **MIT**（README "LICENSE: MIT"，GitHub API `license.spdx_id=MIT`） |
| 语言/依赖 | Python 3.6+；PyPI 安装 `pip install weibo-scraper`（README 未列全量依赖树） |
| 规模/热度 | 110★ / 19 fork（GitHub API 检索时点） |
| 可借鉴点（**读到**） | ①**移动站自带 API** 的思路："we can inspect mobile site which has it's own API by Chrome"；②**container id 形态**：`get_weibo_tweets(tweet_container_id='1076033637346297')`，示例值可读作 `107603` + `uid`（`3637346297`）的拼接；③入口函数分层 `get_weibo_profile(name/uid)`、`get_weibo_tweets_by_name(name, pages)`、`get_realtime_hotwords()`；④返回 `UserMeta`/`cards_node`/`mblog` 这类字段名，说明其解析对象是**移动端卡片结构**而不是桌面 DOM。 |
| 局限（**读到 + 推断**） | ①最后提交 2022-11，距本次核查近 4 年，微博前端与反爬已多次变更（**推断**，未验证）；②README 自称 "without authorization"，但**未说明**是否仍能匿名读到搜索/评论（**未获取**）；③**未提供**任何风控/限速/432 处理说明（**读到**：README 无相关章节）。 |
| 我们的实测 | **无**（未安装、未运行、未访问微博） |

### 1.2 Praeviso/crawl4weibo

| 项 | 值 |
| --- | --- |
| 原链接 | https://github.com/Praeviso/crawl4weibo |
| 仓库/项目名 | `Praeviso/crawl4weibo`（PyPI `crawl4weibo`） |
| 版本/commit | **`53910553e677fab0209ce347d8b8d14825a50f68`**（2026-10-25，dependabot 提升 certifi） |
| 许可 | **MIT** |
| 语言/依赖 | Python；**依赖 Playwright + 需 `playwright install chromium`**；可选代理池；`uv`/`pip` 均可 |
| 规模/热度 | 43★ / 7 fork；仓库有 "Daily Availability" 工作流徽章 |
| 可借鉴点（**读到**） | ①**默认无需 cookie**："No Cookie Required: Runs without cookies, automatically initializes session with mobile User-Agent"——即**移动 UA + 会话初始化**是主流可行路径；②**用真实浏览器补 cookie**："Uses Playwright to simulate real browsers for enhanced anti-scraping bypass"，另有**可选登录**：`login_cookies=True, browser_headless=False, login_timeout=180`，首次人工登录后持久化 `storage_state` 复用——**与我们"可见窗口人工登录 + 专用 profile 复用"的做法同型**；③**432 保护**："Built-in 432 Protection: Handles anti-scraping protection with exponential backoff retry mechanism"——把 **HTTP 432** 当作反爬信号并退避；④数据模型 `User`/`Post`/`Comment`，评论支持**分页 + 嵌套回复**；⑤长文展开、关键词搜索、用户搜索、代理池 TTL/轮询。 |
| 局限（**读到 + 推断**） | ①README 未给出具体接口路径与选择器，**真正的端点清单未获取**；②Playwright 属于**新依赖**，与本批"不装依赖"冲突；③退避重试与我们"风险即锁、不重试"的策略相反，只能借鉴"432 是风控信号"这一点，**不能照搬重试**；④代理池/去重下载等能力本批不需要。 |
| 我们的实测 | **无**（未安装、未运行、未访问微博） |

### 1.3 lucasjinreal/weibo_terminater

| 项 | 值 |
| --- | --- |
| 原链接 | https://github.com/lucasjinreal/weibo_terminater |
| 版本/commit | 未取（仅元数据；`pushed_at=2019-10-25`） |
| 许可 | **无许可声明**（API `license=null`）→ **不可复用代码** |
| 规模/热度 | 2318★ / 448 fork |
| 描述（**读到**，API description） | "Final Weibo Crawler Scrap Anything From Weibo, comments, weibo contents, followers, anything." |
| 可借鉴点 | **仅概念层**：说明"评论 / 正文 / 关注关系"是常见采集对象集合。 |
| 局限 | 无许可证 → 不能借用实现；2019 年后未推送，时效性差。 |
| 我们的实测 | **无** |

### 1.4 w4n9hu1/hot-hub-web

| 项 | 值 |
| --- | --- |
| 原链接 | https://github.com/w4n9hu1/hot-hub-web |
| 版本/commit | 未取（仅元数据） |
| 许可 | **MIT** |
| 规模/热度 | 218★；仓库 topics 含 `archived` |
| 可借鉴点（**读到**） | 只做**热点榜**聚合（topics: hot-topics/weibo-scraper），与"搜索/详情/评论"不同路；可借鉴"热点入口单独建模"的产品划分。 |
| 局限 | 已归档；不含搜索/详情解析细节（**未获取**）。 |
| 我们的实测 | **无** |

### 1.5 goesByhc/cn-scraper-mcp

| 项 | 值 |
| --- | --- |
| 原链接 | https://github.com/goesByhc/cn-scraper-mcp |
| 版本/commit | 未取（仅元数据；`pushed_at=2026-07-29`） |
| 许可 | **MIT** |
| 规模/热度 | 72★ |
| 可借鉴点（**读到**，API description） | 把中文平台采集**包装成 MCP 工具**给 agent 用，微博是其一；提示"多平台统一工具面"是可行产品形态。 |
| 局限 | 未读实现，**具体微博端点未获取**。 |
| 我们的实测 | **无** |

### 1.6 GitHub issues 检索（替代 X 讨论）

| 项 | 值 |
| --- | --- |
| 查询 | `api.github.com/search/issues?q=weibo 432 OR "visitor system" scraper`（2026-10-27） |
| 结果 | **未获取可用结论**：返回 198,848 条噪声（如 `dygraphs#432`、日文 XMPP issue），与微博反爬无关。 |
| 处理 | 按"访问受阻或无结果必须标注未获取"，**不据此写任何结论**。 |

### 1.7 X（Twitter）讨论

**未获取**。无 agent-reach、无 web_search，本批不接触 X。**不编造任何"X 上有人说…"的内容。**

## 2. 对我们的直接结论（可执行）

1. **路径选择**：两条主流路线——(a) 移动站自带 JSON API（Xarrow），(b) 真实浏览器会话 + 移动 UA（crawl4weibo）。我们已有 nodriver 浏览器底座，**选 (b) 为默认、把 (a) 作为 comments 的接口形态参考**。
2. **登录策略**：crawl4weibo 的"首次可见窗口人工登录 + 持久化会话复用 + 之后可 headless"与 V10-3 已验证的知乎做法**同型**，直接沿用（`--visible` opt-in、默认 headless、300s 窗口）。
3. **风控信号**：把 **HTTP 432 / 429 / 403** 与非空 wall 标记（验证码、安全验证、访问过于频繁…）都视为**持久锁**信号——但我们**不采用** crawl4weibo 的指数退避重试（与"风险即锁、不重试"冲突）。
4. **字段模型**：`User`/`Post`/`Comment` → 映射到既有 `records.FIELDS`：`Post` → `type="status"`、`Comment` → `type="comment"` 且 `parent_id=status_id`（与知乎 answer/comment 的父关系同构）。
5. **未取到的关键情报**（必须在 W4 之后用真实页面补齐，不能靠猜）：搜索页 URL 形态与容器类名、详情页是否为服务端渲染、评论接口的参数与分页游标、桌面站与移动站的内容差异。

## 3. 明确未获取项汇总

- X（Twitter）讨论：**未获取**（无通道）。
- agent-reach 技能：**本机未安装**（无目录、无 CLI）。
- 各仓库的**具体接口路径/选择器/参数**：**未获取**（只读 README 与元数据，未读源码实现细节）。
- 微博站点任何响应：**本批按约束完全未访问**。
