# V9-0C Research Discovery（前置研究，非实现）

本目录只做**前置借鉴研究**与离线 synthetic 设计验证；不改现有代码/数据/配置/部署，不新增依赖，不接业务库。

## 先读

1. [RESEARCH.md](RESEARCH.md) — 检索方法/实际结果/X 访问受阻、三个子域发现、国内证据边界、推荐与不采用项。
2. [CANDIDATES.md](CANDIDATES.md) — Scrapy / RapidFuzz 深读（版本、commit、许可原文、关键文件行号、机制/局限/依赖成本/复用决策）。
3. [MINIMAL_DESIGN.md](MINIMAL_DESIGN.md) — 证据→方向卡→品类台账→工作单；四种反例、可撤销合并/拆分、轮次状态机与中断恢复。
4. [synthetic_examples.py](synthetic_examples.py) / [synthetic_examples.json](synthetic_examples.json) — **仅 synthetic** 的纯标准库思路验证；不是系统。
5. [source_manifest.json](source_manifest.json) — 查询关键词/时间/链接/count、候选元数据、证据索引。

## 状态

- GitHub：公开 REST 可用；已检索 6 组关键词并留原始 JSON。
- X：**访问受阻**（无 twitter-cli；curl TLS exit 35；兼容 web 搜索无结果）；没有 X 原帖证据。
- `ponytail`：本地 skill 根未找到、当前无 `skill` 调用入口；未假装加载（见 RESEARCH §1.1）。
- 外部候选：Scrapy / RapidFuzz 仅读源码/文档/API；**未安装、未运行**。
- 业务库/代码：未修改；本目录外只读核查现有证据路径。

## 明确不是

- 不是已实现的需求挖掘/品类归并/任务调度系统；
- 不是真实用户需求、成交、收益或平台审核结论；
- 不是对 Scrapy/RapidFuzz 的性能/兼容性验证。
