# Topic crawler（f=top + 相关性过滤）三轮采集与三档统计

> 任务：`task-2dc7413defd1825cf142f981c25def9d`（rev5 返工）。范围：`docs/validation/x-collect/topic-crawler`。
> 工具：`C:\Users\19183\.dsh\tools\x-collect`（`x_collect.py` 未修改，sha256 `fcd74b5a…`）；wrapper `tools/collect_search.py` 仅改搜索 URL 为 `f=top` 并收紧风险谓词；profile 未重登。
> 结论：三轮 raw **60×3=180**；engagement≥50 **116**；engagement≥50 且相关性通过 **45**（去重后）；CSV/top20 仅用第三档，top20 满 20 条。

## 1. 三轮执行（f=top）

| 轮次 | 命令 | exit | raw | duplicates | 耗时 | 轮间隔 |
| --- | --- | --- | --- | --- | --- | --- |
| run1 | `tools/collect_search.py --keyword "web scraping" --limit 60` | **0** | 60 | 119 | 335.3 s | — |
| run2 | `tools/collect_search.py --keyword "crawler" --limit 60` | **0** | 60 | 111 | 348.1 s | ~72 s |
| run3 | `tools/collect_search.py --keyword "爬虫" --limit 60` | **0** | 60 | 113 | 275.9 s | ~72 s |

- 实际时段：`2026-10-22T04:27:38Z` ~ `2026-10-22T04:46:22Z`；轮内 8–12s 限速，轮间 sleep 65s（实际 ~72s）。
- 每轮前后确认 **0 个残留 x-collect Chrome 进程**；未重登/改 profile。
- raw（UTF-8 无 BOM）：`raw/top_run1_web_scraping.jsonl`（60）、`raw/top_run2_crawler.jsonl`（60）、`raw/top_run3_pachong.jsonl`（60）。
- 日志：`logs/top_run1_web_scraping.log`、`top_run2_crawler.log`、`top_run3_pachong.log`，以及工具原始日志 `logs/search-2026-10-22T042738Z.log`/`…043433Z`/`…044140Z`。
- 旧 `f=live` 结果已归档 `raw/live_attempt/` 与 `REPORT_live_attempt.md`，不参与本次统计。

## 2. 三档统计与相关性过滤

过滤脚本：`tools/filter_engagement.py`（仅标准库），阈值 **50**，engagement=`likes+retweets+replies`（null→0）。

- **相关性规则**：必须命中网页采集词表（scrap/scraper/scraping/spider/web crawl/crawling/爬虫/反爬/采集/selenium/playwright/puppeteer/beautifulsoup/requests 库/数据抓取），并命中技术语境（website/html/browser/crawl/api/python/proxy/反爬/采集/抓取/网页/网站/数据/代码/接口等）；命中排除词（reptile/爬虫類/爬蟲/爬宠/トカゲ/蜥蜴/pipe crawler/sewer/storm drain/kitten rescue/robotic crawler/Spider-Man/Marvel/wall-crawler/superhero/comic）直接丢弃。排除优先；只对 engaged 行做相关性判断。
- **三档**（`summary.json`）：

| 关键词 | raw | engagement≥50 | 达标且相关 | dropped_irrelevant | raw→达标率 | 达标→相关率 |
| --- | --- | --- | --- | --- | --- | --- |
| web scraping | 60 | 45 | 31 | 14 | 75.0% | 68.9% |
| crawler | 60 | 44 | 7 | 37 | 73.3% | 15.9% |
| 爬虫 | 60 | 27 | 7 | 20 | 45.0% | 25.9% |
| **合计（去重后）** | **180** | **116** | **45** | **71** | 64.4% | 38.8% |

- 跨关键词去重：同 `tweet_id` 保留 engagement 最高（并列首次）；`deduped_removed=0`。
- 阈值敏感性（仅建议用）：相关计数 @50=45、@30=46、@20=48（阈值未下调）。
- 排除样例：旧 `f=live` 中的日文爬虫宠物帖、CBSNews 下水道 pipe crawler 均已不在第三档；`filtered/dropped_irrelevant.jsonl` 保留 71 条被丢弃的达标无关项供审计。

## 3. CSV / top20（仅第三档）

- `filtered/filtered_all.jsonl`（45，UTF-8 无 BOM，engagement 降序）；分关键词 `filtered_web_scraping.jsonl`（31）、`filtered_crawler.jsonl`（7）、`filtered_pachong.jsonl`（7）。
- `filtered/summary.csv`：**UTF-8 with BOM**、LF；列 `engagement,likes,retweets,replies,author_handle,created_at,lang,url,text_snippet`；45 行、engagement 降序、摘要去换行并截断 120 字。
- `top20.md`：20 条（满 20），按 engagement 降序。前 5 条：

| # | engagement | 作者/链接 | 摘要 |
| --- | --- | --- | --- |
| 1 | 7009 | [@josesilesdata](https://x.com/josesilesdata/status/2082194990592069660) | WEB SCRAPING IS DEAD… PixelRAG skips HTML parsing |
| 2 | 5641 | [@DataChaz](https://x.com/DataChaz/status/2105918848067321966) | this is exactly how I imagined a web crawler would look |
| 3 | 5483 | [@Sumanth_077](https://x.com/Sumanth_077/status/1940049003074478511) | Web scraping will never be the same! Firecrawl… |
| 4 | 3498 | [@taozi0929](https://x.com/taozi0929/status/2098683783683985456) | paying $16/month for a web crawler service… |
| 5 | 3346 | [@Lucy_love_AI](https://x.com/Lucy_love_AI/status/2071040656634732984) | 10 GitHub Repositories to Help You Scrape the Internet |

## 4. RISK_JS 误报（待修缺陷）

- 历史 `f=live` 尝试中，`x_collect.py` 的 `RISK_JS` 用 `/Challenge/i` 扫描正文，误命中正常推文 “face several challenges”，产生 **exit=3 RISK_CONTROL**（实际页面正常、无 429/验证码）。
- 这是**工具误报**，不是风控；本任务未改 `x_collect.py`（sha `fcd74b5a…`）；wrapper `tools/collect_search.py` 仅把风险谓词改为 alert/toast/验证码 iframe 选择器（真实风控仍会停）。此缺陷应另行修复（例如把风险检测限定到 toast/alert/iframe，或使用词边界/UI 选择器）。
- 本次三轮 wrapper 均 exit=0，无风控停止。

## 5. 证据/哈希/边界

| 文件/目录 | 内容 |
| --- | --- |
| `raw/top_*.jsonl` | 三轮 60×3 原始数据 |
| `filtered/filtered_*.jsonl`、`summary.csv`、`dropped_irrelevant.jsonl` | 第三档、CSV、丢弃审计 |
| `summary.json` | 三档统计、词表/排除/语境 regex、阈值敏感性、时段、限制 |
| `top20.md` | 20 条相关达标清单 |
| `logs/top_*.log`、`logs/search-*.log`、`logs/attempts/*` | 命令/exit/耗时/误报片段 |
| `tools/collect_search.py`、`tools/filter_engagement.py` | 采集 wrapper 与过滤脚本 |
| `hash_check.json` | requirements/CONTRACT/冻结三/real_link 与业务库均 same（`e073f828…`，wal/shm=false） |

- 未修改 `x_collect.py`（`fcd74b5a…`）、未重登/改 profile、未发布/点赞/关注/私信、未读 cookie 值、未跑 325 业务测试。
- CSV 按约定 UTF-8 BOM；JSONL/日志 UTF-8 无 BOM、LF。

## 6. 限制

1. **相关性为规则启发式**：仍可能把“web crawler 梗图/泛 AI Agent”判为相关（如 DataChaz 梗、browser-use 推文），也可能漏掉未含词表/语境词的帖子；已提供 `dropped_irrelevant.jsonl` 供复核。
2. **`f=top` 含较旧高互动推文**（top20 中有 2023–2025 年内容），互动分受历史累积影响，不代表当前热度；如需近期样本可另跑 `f=live` 或加日期过滤。
3. **第三档 45 条 ≥10**，未触发阈值建议；敏感性 @30=46、@20=48，若需更多可在用户确认后调整，但不得下调冒充达标。
4. `seen.jsonl` 全局去重（此前样本已占 id），三轮仍各采到 60 条新 id；未清理 seen。
5. RISK_JS 误报仍在原工具中（待修）；本任务 wrapper 绕过仅针对误报，真实 alert/toast/captcha iframe 仍会停止。
6. 未跑 325 业务测试；未改 DSH 配置/业务代码。
