# V9-0C 前置研究：需求→方向、跨轮品类归并、可暂停本地轮次

> 任务：`task-eb464e4dd390466e0682443b3f51a4dd`（v9，前置借鉴研究）。
> 边界：只写本目录；不安装依赖、不运行陌生项目、不接付费模型、不碰业务库/现有配置。**本轮没有实现任何系统**；下文的代码/数据模型是待验证设计。

## 1. 方法与工具（实际结果）

### 1.1 技能/工具检查

- `agent-reach`：本机 **1.5.0**，`C:\Users\19183\.agent-reach-venv\Scripts\agent-reach.exe`；已实际运行 `doctor --json`：
  - GitHub：**warn**（gh CLI 可执行，但未检测到显式认证；公开 REST 可用）；
  - Twitter/X：**warn**（`twitter-cli` 未安装，无可用后端）；
  - web/Bilibili：ok。
- `ponytail`：系统技能目录列出名称，但本机 skill 根只有 `agent-reach`/`stealth-browser-mcp`，且当前工具面无 `skill` 调用入口；**未假装加载**。本设计按“最小实现/拒绝重型依赖”的原则手工执行；这是工具缺口，不是完成声明。
- 未使用浏览器 MCP；未登录任何平台。

### 1.2 GitHub 检索（真实 API）

请求时间约 `2026-10-25T04:55Z`；结果 JSON 原始文件在 `sources/gh_*.json`。

| 关键词 | 实际结果 | 链接 |
| --- | --- | --- |
| `resumable crawler sqlite` | 15 repos；top: Pryodon/Webspider(10★, AGPL-3.0)、abbysallord/oppy(4★, MIT)、Zaalar/resumable-catalog-crawler(0★, no license) | https://github.com/search?q=resumable+crawler+sqlite&type=repositories |
| `incremental crawl checkpoint python` | 0 | https://github.com/search?q=incremental+crawl+checkpoint+python&type=repositories |
| `fuzzy duplicate categories python` | 1（menu-clone-hunter，0★，无 license） | https://github.com/LJrobinson/menu-clone-hunter |
| `demand mining product ideas python` | 0 | https://github.com/search?q=demand+mining+product+ideas+python&type=repositories |
| `rapidfuzz fuzzy string matching` | 24；top RapidFuzz(4177★, MIT) | https://github.com/rapidfuzz/RapidFuzz |
| `scrapy jobdir resume` | 0（用直接 repo 元数据/文档核验，见 CANDIDATES） | https://github.com/scrapy/scrapy |

- **结论**：没有找到“本地单用户、需求→商品方向、跨轮品类台账”这一组合的成熟小项目；可用的是局部机制（Scrapy 持久 job、RapidFuzz 字符串候选）。
- 小仓库只做筛查，**未深读/未安装**；不作为依赖候选（见 `CANDIDATES.md` 表）。

### 1.3 X 检索（实际受阻）

| 尝试 | 结果 |
| --- | --- |
| `curl https://x.com/search?q=%22crawler%22%20resume&src=typed_query&f=live` | **exit 35**；schannel TLS handshake failure；0 bytes（`sources/x_search_probe.txt`） |
| `agent-reach doctor` | twitter **warn**：`twitter-cli` 未安装，无后端 |
| `web_search site:x.com ...`（兼容检索） | **无结果** |

**因此本轮没有 X 原帖证据**；不把 GitHub 开发参考或 web 二手摘要当作 X 用户需求。若后续需要 X 证据，需用户提供可用会话/后端，另开有界采集轮。

## 2. 三个子域的发现

### A. 需求原话 → 商品方向

- GitHub 搜索 `demand mining product ideas python` **0 命中**；没有可直接复用的小项目。
- 现有项目中的可借鉴素材：
  - 闲鱼 20 条价格信号（`docs/validation/money-project/sourcing/price_signals.csv`）：3 条参考价、16 条 wants，合计 8093；**是价格/兴趣代理，不是需求访谈**。
  - B25 反馈表 2 行 **synthetic**（`docs/validation/product-workflow/b25/feedback-log.csv`），不能作为真实需求。
- 设计取向：**保留原文 evidence → 人工确认方向卡**；不从标题/热度直接生成商品，不把互动量当需求/成交。
- 方向卡最小字段：`job_statement`（用户原话）、buyer、task、deliverable、format、locale、evidence_ids、确认状态；平台/作者/价格只作为 evidence 元数据。

### B. 跨平台/跨轮品类归并

- GitHub 只找到字符串匹配库（RapidFuzz）；**没有“平台无关品类身份 + 可撤销合并/拆分”的现成小项目**。
- RapidFuzz 能给出相似度候选，但不能证明同一商品/任务；相似度阈值会造成“同大类不同任务”误并。
- 设计取向：
  - `identity_key = audience + task + deliverable_family + locale`，**平台、标题、格式、载体不参与**；
  - exact key / 人工 alias 才合并；相似度只进 `review_queue`，不自动合并；
  - 旧品类新证据 = `update`，不新建；排除状态可恢复；merge/split 用事件日志可撤销；
  - 不采用“组均分 × log/AND 阈值”等未验证公式。

### C. 主动开轮/可暂停续跑的本地任务

- Scrapy 的 `JOBDIR` 是最接近的成熟参考：持久 scheduler、dupefilter、spider state；但它的语义是 **单 job、clean pause、同版本、可序列化请求**，且运行时依赖 Twisted/lxml/parsel 等重栈。
- 设计取向：
  - `round`（budget/cursor/status/idempotency_key）+ `round_item`（唯一键/attempts/error）；
  - 每个 item 成功后在同一事务提交 evidence upsert + round_item done + cursor；失败记 failed，不伪造成功；
  - `max_items/max_pages/max_seconds/max_errors` 硬停；`paused/partial` 可 resume；重放按 content_hash/唯一键幂等；
  - 复用 Flask/SQLite/stdlib，**不引入 Celery/Redis/Scrapy**；单进程手动轮次即可。

## 3. 国内受众证据（与开发参考分开）

> 本任务**没有新采集/访谈**；以下只是现有项目产物，不能代表国内受众总体。

| 材料 | 规模 | 能说明 | 不能说明 |
| --- | --- | --- | --- |
| 闲鱼价格信号 `sourcing/price_signals.csv` | 20 行；参考价 3 行；wants 16 行，合计 8093 | 数字商品供给的**价格/兴趣代理** | 不是需求访谈、不是成交、不是支付意愿 |
| Bilibili 种子 `scoring/raw/bilibili_search.json` | 20 条公开视频 | 中文内容侧的教程/主题样本 | 不是买家需求，不代表购买 |
| B25 反馈 `b25/feedback-log.csv` | 2 行 | 演示四个指标/脚本 | **synthetic，虚构，不是经营数据** |

- GitHub/X 是**开发参考**，不能替代国内买家证据；国内受众的结论仍需真实访谈/发布后数据。
- 本文不把 `wants`、播放量或 Star 当作需求/收入/审核结论。

## 4. 候选结论（深读见 `CANDIDATES.md`）

| 候选 | 角色 | 决策 |
| --- | --- | --- |
| Scrapy 2.19.0（BSD-3，commit 171ccb…） | JOBDIR 持久队列/去重/恢复 | **只用概念，不引依赖**；重框架不适合本地 Flask 小工具 |
| RapidFuzz 3.14.6-1（MIT，commit 093284…） | 字符串相似度候选 | **默认不用**；规模增长后只做 review 候选，不自动合并 |
| 小型 crawler 仓库 | 关键词筛查 | 规模/许可/维护不足；不采用（见 CANDIDATES 表） |

## 5. 推荐的最小方案与不采用项

**推荐**：独立 `research` SQLite（非业务库）+ 7 张最小表（evidence、direction_card、category、category_alias、discovery_event、review_queue、round/round_item；workorder 仅引用）；exact/alias 匹配 + 人工复核 + 事件撤销；单进程、有预算、可暂停/续跑。详见 `MINIMAL_DESIGN.md`。

**不采用**：
- Scrapy 全框架（Twisted/lxml/parsel 等重依赖）；
- RapidFuzz/向量库/embedding 作为默认分类器（不可解释、误并、额外依赖）；
- Redis/Celery/RQ/APScheduler（本地单用户不需要 broker/daemon）；
- 自动相似度阈值合并、组均分×log/AND 等未验证公式。

## 6. 限制/待验证

1. **X 无证据**：TLS/后端受阻，只有受阻记录；不能声称已检索 X 内容。
2. **GitHub 只是开发参考**：没有国内买家访谈；Xianyu/Bilibili 是代理指标。
3. **未安装/未运行外部项目**：Scrapy/RapidFuzz 只读源码/文档/API；未做性能/兼容实验。
4. **设计未实现**：`synthetic_examples.py` 只验证 identity/merge/round 思路，非系统；表结构/事务/并发待实现验证。
5. **中文分词/同义**：先用 exact/alias + 人工；不引入分词/embedding；同义覆盖不足会进 review。
6. **工具缺口**：ponytail 未在本地 skill 根找到、无 skill 调用入口；agent-reach 的 X 后端未安装。按实际记录，不伪造加载。

## 7. 证据索引

- `source_manifest.json`：查询、时间、链接、实际 counts、候选版本/commit/license、国内证据
- `CANDIDATES.md`：2 个深读候选 + 筛查未采用
- `MINIMAL_DESIGN.md`：数据关系、反例、撤销、轮次状态机
- `synthetic_examples.py` / `synthetic_examples.json`：**synthetic** 离线示例
- `sources/`：GitHub API 原始 JSON、LICENSE、Scrapy/RapidFuzz 关键文件、X 受阻记录
