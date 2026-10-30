# Notion 模板 / 数字商品机会榜（样本评分）

> 数据样本：X 30 条（f=top）、Bilibili 20 条、GitHub 10 仓库；评分是**可解释的启发式**，不是收入预测。

## 数据覆盖

| 平台 | items | 真实 exit | 耗时 | UTC 时段 | 原始文件 |
| --- | --- | --- | --- | --- | --- |
| X | 30 | 0 | 127.5s | 06:57:50–07:00:04 | `raw/x_search.jsonl` |
| Bilibili | 20 | 0 | 1.2s | 07:01:29–07:01:30 | `raw/bilibili_search.json` |
| GitHub | 10 | 0 | 1.1s | 07:02:35–07:02:37 | `raw/github_search.json` |

## 方法与权重

| 指标 | 权重 | 说明 |
| --- | --- | --- |
| 需求强度 | 0.30 | X=likes+retweets+replies；B站=play；GitHub=stars；平台内 log1p 分位 |
| 竞争稀疏度 | 0.20 | 平台供给先验 + 同作者重复惩罚，取反 |
| 毛利空间 | 0.20 | 公开售价区间 - 估计履约成本（缺成本输入，区间估计） |
| 履约容易度 | 0.10 | 数字交付 0.8-0.9；视频内容 0.6；服务 0.55 |
| 合规安全度 | 0.10 | IP/许可证/“AI 暴富”话术风险 |
| 可复制性 | 0.10 | 模板/仓库更易复制，视频内容较难 |

公式：`total = Σ(w_i × norm_i) / Σ(w_i)`；缺失指标从分子分母同时剔除（本轮无缺失）。

## Top10

| # | 分数 | 平台 | 机会（证据） | 建议 |
| --- | --- | --- | --- | --- |
| 1 | 0.800 | x | [•ଓ.° template notion •ଓ.° — a thread by me *̥₊˚‧☆ﾐ](https://x.com/booorenjiiy/status/1467843989533442054) | 推荐验证 |
| 2 | 0.790 | x | [CARA MENCARI & REKOMENDASI TEMPLATE NOTION GEMAS UNTUK KALIA](https://x.com/mareidaily/status/1674662364057317382) | 推荐验证 |
| 3 | 0.769 | x | [work! adaaa yang butuh template notion buat ngedata lamaran ](https://x.com/worksfess/status/1747215882965979516) | 推荐验证 |
| 4 | 0.760 | bilibili | [Notion模板怎么导入？简单！](https://www.bilibili.com/video/BV19A411f7cH) | 推荐验证 |
| 5 | 0.759 | x | [Stop scrolling if you are a student. I’m giving away this FR](https://x.com/heyeaslo/status/1580068264650022912) | 推荐验证 |
| 6 | 0.759 | x | [notion template <3 some of you asked for a notion reveal, so](https://x.com/opteemisty/status/1674994814016954371) | 推荐验证 |
| 7 | 0.748 | x | [˗ˋˏ°• notion template for your class! •°ˎˊ˗ here's the notio](https://x.com/aeshoui/status/1824402140070285653) | 推荐验证 |
| 8 | 0.744 | bilibili | [【Notion教程】小白友好：如何拷贝模板？如何设置中文版？](https://www.bilibili.com/video/BV1vr421K7EJ) | 推荐验证 |
| 9 | 0.738 | x | [I created a Search Planner for ChatGPT. This Notion template](https://x.com/IAmPascio/status/1641088397874802688) | 推荐验证 |
| 10 | 0.728 | bilibili | [177 Notion 教程 No.46 template-1：学习笔记模板（Template Study-Notes）](https://www.bilibili.com/video/BV11i4y147FS) | 推荐验证 |

## Top10 详情

### 1. •ଓ.° template notion •ଓ.° — a thread by me *̥₊˚‧☆ﾐ
- 分数：**0.800**（推荐验证）；平台：x；作者：@booorenjiiy
- 证据：[https://x.com/booorenjiiy/status/1467843989533442054](https://x.com/booorenjiiy/status/1467843989533442054)；来源：`x.com search f=top keyword=notion template`；raw：`raw/x_search.jsonl`
- 指标：需求 1.00（原始 5968.0）、竞争稀疏 0.40、毛利 0.82（区间 0.70-0.95）、履约 0.90、合规 0.80、可复制 0.85
- 理由：强项 需求1.00、履约0.90；弱项 合规0.80、竞争稀疏0.40。
- 毛利假设：digital Notion template: $9-49 price, $0.5-3 payment/hosting cost (estimated)（缺成本输入，区间估计，非精确值）。

### 2. CARA MENCARI & REKOMENDASI TEMPLATE NOTION GEMAS UNTUK KALIAN! A thread by @mareidaily
- 分数：**0.790**（推荐验证）；平台：x；作者：@mareidaily
- 证据：[https://x.com/mareidaily/status/1674662364057317382](https://x.com/mareidaily/status/1674662364057317382)；来源：`x.com search f=top keyword=notion template`；raw：`raw/x_search.jsonl`
- 指标：需求 0.97（原始 5896.0）、竞争稀疏 0.40、毛利 0.82（区间 0.70-0.95）、履约 0.90、合规 0.80、可复制 0.85
- 理由：强项 需求0.97、履约0.90；弱项 合规0.80、竞争稀疏0.40。
- 毛利假设：digital Notion template: $9-49 price, $0.5-3 payment/hosting cost (estimated)（缺成本输入，区间估计，非精确值）。

### 3. work! adaaa yang butuh template notion buat ngedata lamaran kerja yang kita apply? sender 
- 分数：**0.769**（推荐验证）；平台：x；作者：@worksfess
- 证据：[https://x.com/worksfess/status/1747215882965979516](https://x.com/worksfess/status/1747215882965979516)；来源：`x.com search f=top keyword=notion template`；raw：`raw/x_search.jsonl`
- 指标：需求 0.90（原始 3577.0）、竞争稀疏 0.40、毛利 0.82（区间 0.70-0.95）、履约 0.90、合规 0.80、可复制 0.85
- 理由：强项 履约0.90、需求0.90；弱项 合规0.80、竞争稀疏0.40。
- 毛利假设：digital Notion template: $9-49 price, $0.5-3 payment/hosting cost (estimated)（缺成本输入，区间估计，非精确值）。

### 4. Notion模板怎么导入？简单！
- 分数：**0.760**（推荐验证）；平台：bilibili；作者：心愉自寂
- 证据：[https://www.bilibili.com/video/BV19A411f7cH](https://www.bilibili.com/video/BV19A411f7cH)；来源：`api.bilibili.com search/type video keyword=notion template`；raw：`raw/bilibili_search.json`
- 指标：需求 1.00（原始 16937.0）、竞争稀疏 0.55、毛利 0.62（区间 0.45-0.80）、履约 0.75、合规 0.80、可复制 0.70
- 理由：强项 需求1.00、合规0.80；弱项 毛利0.62、竞争稀疏0.55。
- 毛利假设：template/course upsell: ¥15-99 price, ¥5-30 production/support cost (estimated)（缺成本输入，区间估计，非精确值）。

### 5. Stop scrolling if you are a student. I’m giving away this FREE Notion template for student
- 分数：**0.759**（推荐验证）；平台：x；作者：@heyeaslo
- 证据：[https://x.com/heyeaslo/status/1580068264650022912](https://x.com/heyeaslo/status/1580068264650022912)；来源：`x.com search f=top keyword=notion template`；raw：`raw/x_search.jsonl`
- 指标：需求 0.93（原始 4369.0）、竞争稀疏 0.30、毛利 0.82（区间 0.70-0.95）、履约 0.90、合规 0.80、可复制 0.85
- 理由：强项 需求0.93、履约0.90；弱项 合规0.80、竞争稀疏0.30。
- 毛利假设：digital Notion template: $9-49 price, $0.5-3 payment/hosting cost (estimated)（缺成本输入，区间估计，非精确值）。

### 6. notion template <3 some of you asked for a notion reveal, so I created this simple templat
- 分数：**0.759**（推荐验证）；平台：x；作者：@opteemisty
- 证据：[https://x.com/opteemisty/status/1674994814016954371](https://x.com/opteemisty/status/1674994814016954371)；来源：`x.com search f=top keyword=notion template`；raw：`raw/x_search.jsonl`
- 指标：需求 0.86（原始 2210.0）、竞争稀疏 0.40、毛利 0.82（区间 0.70-0.95）、履约 0.90、合规 0.80、可复制 0.85
- 理由：强项 履约0.90、需求0.86；弱项 合规0.80、竞争稀疏0.40。
- 毛利假设：digital Notion template: $9-49 price, $0.5-3 payment/hosting cost (estimated)（缺成本输入，区间估计，非精确值）。

### 7. ˗ˋˏ°• notion template for your class! •°ˎˊ˗ here's the notion template as requested by eve
- 分数：**0.748**（推荐验证）；平台：x；作者：@aeshoui
- 证据：[https://x.com/aeshoui/status/1824402140070285653](https://x.com/aeshoui/status/1824402140070285653)；来源：`x.com search f=top keyword=notion template`；raw：`raw/x_search.jsonl`
- 指标：需求 0.83（原始 1592.0）、竞争稀疏 0.40、毛利 0.82（区间 0.70-0.95）、履约 0.90、合规 0.80、可复制 0.85
- 理由：强项 履约0.90、可复制0.85；弱项 合规0.80、竞争稀疏0.40。
- 毛利假设：digital Notion template: $9-49 price, $0.5-3 payment/hosting cost (estimated)（缺成本输入，区间估计，非精确值）。

### 8. 【Notion教程】小白友好：如何拷贝模板？如何设置中文版？
- 分数：**0.744**（推荐验证）；平台：bilibili；作者：Estela也是蛋挞
- 证据：[https://www.bilibili.com/video/BV1vr421K7EJ](https://www.bilibili.com/video/BV1vr421K7EJ)；来源：`api.bilibili.com search/type video keyword=notion template`；raw：`raw/bilibili_search.json`
- 指标：需求 0.95（原始 14291.0）、竞争稀疏 0.55、毛利 0.62（区间 0.45-0.80）、履约 0.75、合规 0.80、可复制 0.70
- 理由：强项 需求0.95、合规0.80；弱项 毛利0.62、竞争稀疏0.55。
- 毛利假设：template/course upsell: ¥15-99 price, ¥5-30 production/support cost (estimated)（缺成本输入，区间估计，非精确值）。

### 9. I created a Search Planner for ChatGPT. This Notion template will help you organize search
- 分数：**0.738**（推荐验证）；平台：x；作者：@IAmPascio
- 证据：[https://x.com/IAmPascio/status/1641088397874802688](https://x.com/IAmPascio/status/1641088397874802688)；来源：`x.com search f=top keyword=notion template`；raw：`raw/x_search.jsonl`
- 指标：需求 0.79（原始 1387.0）、竞争稀疏 0.40、毛利 0.82（区间 0.70-0.95）、履约 0.90、合规 0.80、可复制 0.85
- 理由：强项 履约0.90、可复制0.85；弱项 需求0.79、竞争稀疏0.40。
- 毛利假设：digital Notion template: $9-49 price, $0.5-3 payment/hosting cost (estimated)（缺成本输入，区间估计，非精确值）。

### 10. 177 Notion 教程 No.46 template-1：学习笔记模板（Template Study-Notes）
- 分数：**0.728**（推荐验证）；平台：bilibili；作者：177_bilibili
- 证据：[https://www.bilibili.com/video/BV11i4y147FS](https://www.bilibili.com/video/BV11i4y147FS)；来源：`api.bilibili.com search/type video keyword=notion template`；raw：`raw/bilibili_search.json`
- 指标：需求 0.89（原始 13311.0）、竞争稀疏 0.55、毛利 0.62（区间 0.45-0.80）、履约 0.75、合规 0.80、可复制 0.70
- 理由：强项 需求0.89、合规0.80；弱项 毛利0.62、竞争稀疏0.55。
- 毛利假设：template/course upsell: ¥15-99 price, ¥5-30 production/support cost (estimated)（缺成本输入，区间估计，非精确值）。

## 平台覆盖提示

- GitHub 样本中 star 最高的 `enescingoz/awesome-n8n-templates`（26k）排第 13，未进 Top10：许可证为 NOASSERTION（合规 0.55）+ GitHub 竞争先验 0.70；若要把仓库服务化，需先核对许可证与商标。
- GitHub 直连 API 命中共享 IP rate limit；经本机进程代理仅重试 1 次 search 请求成功（无 token），未扩大配额。
- B 站样本多为教程/内容，不是直接商品；榜单把它们定位为“内容流量入口”，可导向模板/课程，而不是把播放量直接当收入。
- 样本没有实体囤货/重售后品类；这是**覆盖不足**，不是“无机会”。

## 不推荐/暂缓（样本内）

说明：关键词搜索会召回非商品内容（乐谱软件、手机安装教程、泛语录等），即使互动高也不应当作数字商品机会；以下按分数列出并标注原因。

- **Notion 安卓手机 免费下载安装方法 一起高效起来**（0.638，不推荐（关键词误召回/非商品））：[证据](https://www.bilibili.com/video/BV1qWVRzaEVY)；强项 需求0.84、履约0.60；弱项 可复制0.55、毛利0.53。
- **🔥 J人实录｜用Notion频繁的记录自己真的太爽啦！！**（0.594，谨慎验证）：[证据](https://www.bilibili.com/video/BV1FXDyBWEyF)；强项 合规0.75、需求0.63；弱项 可复制0.55、毛利0.53。
- **notion is, amongst other things, - a portable, editable memory across **（0.593，谨慎验证）：[证据](https://x.com/wustep/status/2112084330390675474)；强项 履约0.90、可复制0.85；弱项 竞争稀疏0.35、需求0.34。
- **Top 20 Finance tracker Template for Budget Management | Notion**（0.593，谨慎验证）：[证据](https://x.com/MONABLIZUIUX/status/2113159521321222261)；强项 履约0.90、可复制0.85；弱项 竞争稀疏0.40、需求0.31。
- **[Notion模板]追星女孩必备的爱豆主题模板**（0.592，谨慎验证）：[证据](https://www.bilibili.com/video/BV18v411W7EL)；强项 合规0.80、履约0.75；弱项 竞争稀疏0.50、需求0.47。
- **lakshaybhushan/nextjs-notion-waitlist-template**（0.590，谨慎验证）：[证据](https://github.com/lakshaybhushan/nextjs-notion-waitlist-template)；强项 履约0.80、可复制0.70；弱项 合规0.50、竞争稀疏0.30。
- **万物皆可Notion｜『折叠条』内无法分列？一步操作轻松搞定**（0.579，谨慎验证）：[证据](https://www.bilibili.com/video/BV1Gm4y1S7Ey)；强项 合规0.75、履约0.60；弱项 可复制0.55、毛利0.53。
- **What does Notion add that Grok Bot cannot do on its own? Is it visibil**（0.572，谨慎验证）：[证据](https://x.com/prossarx/status/2112022643314487666)；强项 履约0.90、可复制0.85；弱项 竞争稀疏0.40、需求0.24。

## 缺失值与假设

- **没有成本输入**：毛利均用公开售价区间减估计履约成本，`margin_low/high` 为假设区间，`margin_mid` 用于评分；不得当作真实利润。
- 竞争稀疏度是**样本供给先验**（X 0.60 / B站 0.45 / GitHub 0.70）加同作者重复惩罚，不是全市场竞品计数。
- 需求为平台内分位，跨平台不可直接比较绝对热度；GitHub stars 受历史累积影响。
- 所有指标 0-1；确定性：无随机数，按 total_score 降序、item_id 升序处理并列。

