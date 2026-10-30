# Dash / 评分 / 采购 / E2E 只读核验报告（计划 v6 B6，rev5 窄修版）

- 执行者：**C**（非实现者）；写入范围：`docs/validation/money-project/verify/`（**只写此目录**）
- 被测对象：`app/dash/`、`templates/dash/`、`tests/dash/`、`scoring/*`、`sourcing/*`、`e2e/{run_manifest.json,shots_after,logs}`
- 结论：**未发现实现缺陷**；只读性、完整测试套件、像素基线、数据/许可抽样、评分复算均通过；价格—机会联动口径见 §4（已给出结论与偏差评估）

## 1. 只读性（哈希前后）

| | 结果 |
| --- | --- |
| 被测对象 | **14 项**（排除 `__pycache__`） |
| 运行后复算 | **14/14 完全一致，0 变化** |
| 证据 | `verify/baseline_before.json`、`verify/baseline_after.json` |

本次仅写 `verify/`（临时 DB 与日志也在其中），**未改动任何被测文件**。

## 2. 测试复跑

### 2.1 完整套件（本次新增）

| 项 | 值 |
| --- | --- |
| 命令 | `python -X utf8 -m unittest discover -s tests -v`（`APP_DB_PATH=verify/tmp/verify_full.db`，先删旧库） |
| 结果 | **Ran 334 tests — OK**，`exit=0`，**49.856s**，**0 FAIL / 0 ERROR** |
| 日志 | `verify/tmp/full_suite.log`（51,863 B，含 cmd/cwd/UTC/exit 与全量输出） |

### 2.2 `tests/dash` 子集（上轮结论，保留）

`python -X utf8 -m unittest discover -s tests/dash -t . -v` → **9/9 OK，exit=0，0.530s**（`verify/tmp/tests_dash.log`）。

## 3. 自截图与像素基线

| 页面 | 自截图 | 结果 |
| --- | --- | --- |
| `/dash/`（overview） | `verify/shots_self/overview.png` | **与基线字节完全一致**：1440×1400、114,182 B、`ffe85a894e245933bcc9e48c093f97671c755e93aa3d1f3c4853755835e2bdf7` |
| `/dash/opportunities`（本次新增） | `verify/shots_self/opportunities.png` | 1440×1400、180,641 B、`f561e750592fada86539f0e0365c282f136697e65fadf341e7aad5a8d329e958` |

服务均为 `python -m app` + **5011** + 临时 DB（`verify/tmp/verify_opp.db`、`verify/tmp/verify_src.db`），无头 Chrome（`--headless=new --window-size=1440,1400`，**未使用任何已登录 profile**）；每次结束停进程，**5011 残留监听 0**。

## 4. 机会—货源联动口径（把上轮"需人工确认"改为结论）

**读取对象更正**：上轮报告正文写作 `opportunity_selling_top10.csv` 是**笔误**；实际读取的是 **`docs/validation/money-project/sourcing/opportunity_sourcing_top10.csv`**（本次已实读复核）。

**实读结构（10 行）**：列 = `rank, opportunity_id, platform, title, url, score, price_category, price_scope, price_signal_count, effective_low, effective_high, reference_max, wants_sum, source_id, source_name, source_url, license_spdx, license_verdict, source_evidence_url, match_quality, match_reason, source_alternatives, gross_margin_low, gross_margin_high, gross_margin_mid, assumptions`。

- `opportunity_id` 族：**仅 `x:` 与 `bili:`**（无 `gh:`）；`platform` ∈ {`x`,`bilibili`}
- `price_category` ∈ {`notion`,`prompt`,`design`}
- `price_scope` ∈ {**`all_20_fallback`**（rank 1，无同品类货源 → 用全部 20 条闲鱼信号）、**`category_filtered`**（按品类过滤，`price_signal_count` = 3 / 17 / …）}
- `price_signal_count`（10 行）：`20,3,17,20,20,20,20,20,3,20`
- `match_quality`（5 种）：`同品类：Notion 模板/站点源`、`同品类：提示词库源`、`同品类：简历/求职模板源`、`替代匹配：作品集/站点模板源（教程机会无同款商品）`、`近似匹配：站点/Notion 模板源（内容教程非直接商品）`

**结论（替代原"需人工确认"）**：`top10.opportunity_id` 属 `x:`/`bili:` 机会族，`price_signals.item_id` 属**闲鱼数字 id 族**，**二者不做逐条连接**；联动为**按品类聚合 fallback**——有同品类时用 `category_filtered`（3–17 条），无同品类时退化为 `all_20_fallback`（全部 20 条）。`effective_low/high`、`reference_max`、`wants_sum` 即该聚合的产物（`assumptions` 逐字写明"all 20 digital-goods signals used as basket proxy … wants is interest proxy, not paid orders"）。

**对毛利估计的影响（偏差方向与不可比之处）**

1. **毛利并未由价格信号推导**：10 行的 `gross_margin_low/high/mid` **完全一致**（0.7 / 0.95 / **0.825**），与 `assumptions` 中"$9–49 price, $0.5–3 cost"的**模型假设**一致 ⇒ 价格口径变化**不会传导到毛利**，毛利对机会**无区分度**（这是本报告最重要的一条口径事实）。
2. **偏差方向（对价格聚合本身）**：品类聚合会把单品价差抹平——**高价值机会被系统性低估**（其自身可卖更贵，却被品类均值压低），**低价值机会被抬高**；`all_20_fallback`（rank 1）偏差最大，因它跨品类混合（Notion + 提示词 + 设计）；
3. **不可比之处**：①闲鱼 `¥1` 为引流价，`effective_low/high` 是品类篮子的**区间代理**，非该机会自身成交价；②`reference_max`（如 `699.0`）是被"划线参考价"命中的极值，不代表可成交；③`wants_sum` 是**兴趣代理**而非付费订单；④`x:`/`bili:` 内容平台与闲鱼交易平台**跨平台价格不可直接比较**。
4. **可观测性缺口**：`/dash/sources` 的联动表**不显示 `price_scope`**（HTML 中 `all_20_fallback`/`category_filtered` 出现 0 次），读者无法从界面看出某行用的是"全量回退"还是"品类过滤"。

## 5. 页面行数与 CSV 核对（本次新增）

| 页面 | 表格数据行 | 对应 CSV | 一致 |
| --- | --- | --- | --- |
| `/dash/opportunities` | **60**（`TR_WITHOUT_TH=60`） | `scoring/scores.csv` **60 行** | ✅ |
| `/dash/sources` 联动表 | 面板自述 **10 行**，`<tr>` 11（表头 + 10） | `sourcing/opportunity_sourcing_top10.csv` **10 行** | ✅ |

说明：`app/dash/data.py:18` 把 top10 载入为 `join`；`templates/dash/sources.html` 渲染全部 10 行，`index.html` 渲染前 3 行；`routes.py:61` 的 `/opportunities` 传的是 `scores`（60 行，按 `total_score` 降序），**不含** `join`。

## 6. 数据比对（3 条，保留上轮结论）

| # | 比对 | 结果 |
| --- | --- | --- |
| 1 | `scores.demand_raw` ↔ `x_search.jsonl` 的 `likes+retweets+replies` | **5968 = 5968** ✅（原始字段为 `tweet_id/likes/retweets/replies`） |
| 2 | `scores.csv` ↔ `items.jsonl` 行数 | **60 = 60** ✅ |
| 3 | top10 ↔ price_signals 连接 | 见 §4：**不做逐条连接**，为品类聚合（`all_20_fallback`/`category_filtered`） |

## 7. 许可复核（3 行，保留上轮结论）

| 仓库 | `sources.csv` | `raw/license_checks.json` | `raw/licenses/*.json` | 判定 |
| --- | --- | --- | --- | --- |
| `enescingoz/awesome-n8n-templates` | `NOASSERTION` / 需授权（`license_file`） | `NOASSERTION` / `Other` | LICENSE 正文（base64）解码为 *Creative Commons Attribution…* | **一致** |
| `InlitX/Obsidian-Dashboard-Gallery` | `MIT` / 可商用（`api_license`） | `MIT` / `MIT License` | —（证据在 checks） | **一致** |
| `vercel-labs/marketing-team-eve-template` | `MIT` / 可商用（`api_license`） | `MIT` / `MIT License` | —（同上） | **一致** |

GitHub API 实时（无 token，3 次请求）：SPDX **3/3 一致**；stars **2/3 精确**，`enescingoz` 26,045 → **26,046**（实时计数漂移，非造假）。

## 8. 评分复算（3 行，保留上轮结论）

| 行 | item | 复算 | 报告 | 分差 |
| --- | --- | --- | --- | --- |
| rank 1 | `x:1467843989533442054` | **0.800** | 0.800 | 全 0.0 |
| rank 4 | `bili:BV19A411f7cH` | **0.760** | 0.760 | 全 0.0 |
| rank 12 | `gh:enescingoz/awesome-n8n-templates` | **0.705** | 0.705 | 全 0.0 |

按 `model.md`（`log1p` 平台内百分位 `rank/(n-1)` 并列取首；`1-clamp(prior+0.05·(同作者数-1))`；毛利=区间 mid；其余=raw；权重 .30/.20/.20/.10/.10/.10），**≤1e-3 全部通过**。

## 9. 限制

- 完整套件在本机临时库上跑（334 例、49.9s）；未做跨环境复跑。
- 截图覆盖 `/dash/` 与 `/dash/opportunities`；未覆盖 `/collect`、`/sources`、`/daily` 的像素级比对（行数已核对）。
- 许可抽 3/14 行；GitHub API 复核 3 仓库（限额 60/h）。
- 评分复算 3 行（跨平台各一），未做全 60 行批量。
- 未发布/点赞/关注/私信/下单；未重新登录任何平台；除 GitHub API 外无其它网络请求。

## 10. 上轮窄修对照（rev5）

| 要求 | 状态 |
| --- | --- |
| 1) 完整套件 334 OK + 真实 exit | **已做**（334 OK，exit=0，§2.1） |
| 2) 报告文件名更正 + 实读列/内容 | **已做**（§4） |
| 3) "需人工确认"→结论 + 毛利影响 | **已做**（§4，含偏差方向与不可比之处） |
| 4) `/dash/opportunities` 自截 + 行数核对 | **已做**（§3、§5；并补核 `/dash/sources` 联动 10 行） |
| 5) 其它项保留原结论 | **已保留**（§6–§8） |
