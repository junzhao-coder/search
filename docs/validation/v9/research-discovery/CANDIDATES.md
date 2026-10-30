# 外部候选深读（GitHub）

> 仅读源码/文档/API 元数据，**未安装、未运行陌生项目**；许可以仓库 LICENSE 原文为准。X 检索受阻，见 `RESEARCH.md` §1.3。

## C1. Scrapy（可暂停/续跑参考）

- 仓库：[scrapy/scrapy](https://github.com/scrapy/scrapy)
- 元数据：**BSD-3-Clause**，Python，约 **65,001 stars**，open issues **173**，archived=false，pushed `2026-10-22T21:57:27Z`（GitHub API `sources/scrapy_repo.json`）。
- 版本/commit：
  - release **2.19.0**（`2026-09-10`，`sources/scrapy_release.json`）
  - commit **`171ccbedb734c988fd86708fd5e0803029b6c730`**（`2026-10-22`，`sources/scrapy_commit.json`）
- 许可原文：`sources/scrapy_LICENSE.txt`（BSD 3-Clause；允许再分发，保留版权/条件/免责声明）。
- 关键文件与行号：
  - `docs/topics/jobs.rst:7-17`：JOBDIR 持久化 scheduler、dupefilter、spider state；`:25-29` 单 job 目录；`:45-50` 同一命令恢复；`:104-114` 必须 clean pause、同一 Scrapy 版本；`:138` Request 必须可序列化；`:202` RFPDupeFilter 的 `requests.seen`。
  - `scrapy/dupefilters.py:72-205`：`RFPDupeFilter` 以 canonical URL/method/body 指纹去重；有 `DiskDupeFilter`（SQLite）在 `:179-205`。
  - `scrapy/pyproject.toml:9-36`：运行时依赖 Twisted/lxml/parsel/w3lib/cryptography/aiohttp 等。
- 实际机制：把待抓请求队列、已见请求指纹、spider key/value 状态写入 JOBDIR；暂停/恢复只保证“同一版本、clean pause、可序列化请求”的**单 job**；不是通用任务编排。
- 局限/成本：Twisted 异步栈和一组解析/网络依赖很重；JOBDIR 不适合直接嵌入现有 Flask 小工具；状态文件是实现细节，升级/版本不一致有恢复风险；cookie 可能过期。**复用概念，不引入依赖**。
- 复用决策：采用“**持久游标 + 已处理集合 + 预算 + 可恢复**”的语义；不引入 Scrapy 运行时。

## C2. RapidFuzz（品类近似候选参考）

- 仓库：[rapidfuzz/RapidFuzz](https://github.com/rapidfuzz/RapidFuzz)
- 元数据：**MIT**，Python/C++，约 **4,177 stars**，open issues **36**，archived=false，pushed `2026-10-21T13:56:25Z`（`sources/rapidfuzz_repo.json`）。
- 版本/commit：
  - release **v3.14.6-1**（`2026-08-30`，`sources/rapid_release.json`）
  - commit **`09328422916b13181238660cd3b23a71905d1ec9`**（`2026-10-19`，`sources/rapid_commit.json`）
- 许可原文：`sources/rapid_LICENSE.txt`（MIT，允许商用/修改/再分发/再许可/销售，保留版权与许可声明）。
- 关键文件与行号：
  - `src/rapidfuzz/process_py.py:21-124`：`extract_iter` 的 `scorer/processor/score_cutoff` 接口；按 scorer 返回距离或相似度并过滤；`extractOne`/`extract` 同族。
  - `README.md`：要求 **Python ≥3.11**、Windows 需 VC++ 2019 redistributable；主要是 C++ 扩展，MIT。
  - `pyproject.toml:11` `requires-python >=3.11`；numpy 只在 `optional-dependencies.all`（`:34-36`）。
- 实际机制：对 query 与 choices 计算字符串相似度/距离，支持 cutoff 与 processor；返回候选排序，**没有品类身份、证据、别名、合并/撤销、人工复核语义**。
- 局限/成本：C++ 扩展/轮子与 Python 版本约束；相似度阈值不是“同一商品”的充分条件；中文分词/同义改写仍要自定义；对 60 条本地样本没有必要引入。
- 复用决策：**默认不引入**；仅当品类/证据规模增长到需要候选召回时，作为“建议候选”工具，**不自动合并**；先用标准库 exact/alias + 人工复核。

## 被筛查但未采用的仓库（来自 GitHub 搜索，非深读）

| 仓库 | 搜索来源 | 观察 | 未采用原因 |
| --- | --- | --- | --- |
| [Pryodon/Webspider](https://github.com/Pryodon/Webspider) | `resumable crawler sqlite`（15 hits，top） | 10 stars，AGPL-3.0 | 小项目/AGPL 传染性；未证明本地单用户场景 |
| [abbysallord/oppy](https://github.com/abbysallord/oppy) | 同上 | 4 stars，MIT | 规模过小，未见品类/证据语义 |
| [Zaalar/resumable-catalog-crawler](https://github.com/Zaalar/resumable-catalog-crawler) | 同上 | 0 stars，无 license | 无许可/无维护证据，不能作为依赖 |
| [LJrobinson/menu-clone-hunter](https://github.com/LJrobinson/menu-clone-hunter) | `fuzzy duplicate categories python`（1 hit） | 0 stars，无 license | 与品类归并无关，不能证明机制 |

## X 检索结果

- X 直连 `https://x.com/search?q=%22crawler%22%20resume...`：curl **exit 35**，schannel TLS handshake failure，0 bytes（`sources/x_search_probe.txt`）。
- `agent-reach doctor`：`twitter` warn，`twitter-cli` 未安装；无可用 X 后端。
- 兼容 web 搜索 `site:x.com ...`：**无结果**。
- 因此本轮**没有 X 原帖证据**；不把 GitHub 开发参考伪装成 X 用户需求。详见 `RESEARCH.md` §1.3 与 `source_manifest.json`。
