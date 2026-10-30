# 机会列表 → 产品分析视图（交付报告，rev2 意图优先）

- 执行者：C；范围：`tools/workbench/`、`docs/validation/money-project/product-analysis/`
- 实测地址：**http://127.0.0.1:5015/opportunities**（只绑 127.0.0.1，PID 96412）
- 结论：主列 = **产品定位 / 选择理由 / 主要风险**（+ 评分、可售性），原始标题与链接收在「原始证据」；全部文案由 `scores.csv` 字段**确定性生成**，无模型、无联网；**先判生意形态、notion 只作载体**。

## 1. 本轮返工要点（对应 rev4 退回意见）

| 要求 | 落地方式 |
| --- | --- |
| 先判生意形态、再判载体 | `INTENT_RULES` 按序：求职简历资料 → 学习笔记模板 → 教学内容 → 内容引流 → 提示词库 → 自动化模板 → 作品集模板 → 设计素材 → 未分类；`notion` **不参与类型**，只作为载体追加在 positioning 末尾 |
| target_user 来自意图 | 求职者 / 学生 / 教师 / 设计师 / 独立开发者 / 内容创作者；推不出统一写 **「人群未明确」**（不再对有行套“自由职业者、小团队运营”） |
| 风险逐行差异化、字段支持才出现 | 见 §3 阈值表；每行 ≤2 条，文案内嵌该行真实数值 |
| 不改布局/评分/数据 | 表格结构与评分、`scores.csv` 等原始数据均未改动 |

## 2. 类型与人群分布（60 行，真实）

| 生意形态 | 条数 | 目标人群 | 条数 |
| --- | --- | --- | --- |
| 未分类 | **45** | 人群未明确 | **45** |
| 教学内容 | 8 | 教师 | 8 |
| 学习笔记模板 | 4 | 学生 | 4 |
| 求职简历资料 | 1 | 求职者 | 1 |
| 提示词库 | 1 | 内容创作者 | 1 |
| 自动化模板 | 1 | 独立开发者 | 1 |

> 未分类占比高是**数据现实**：这批标题绝大多数只有 “notion template” 这类载体词，没有求职/学生/教程/推荐/提示词/自动化等意图词；按新规则不再把 `notion` 当产品类型，故落到未分类（界面写「人群未明确 / 待确认」）。

## 3. 生成规则（详见 `model.md`）

**选择理由（≤3，挂真实数值）**：优先级 `需求分位 > 可售性 > 毛利 > 竞争稀疏 > 综合评分`；仅字段存在时生成。

**主要风险（≤2，严格阈值）**

| 严重度 | 触发条件 | 文案要点 |
| --- | --- | --- |
| 0.0 | `sellability_norm` 缺失/非数值 | 可售性未评估… |
| 0.1 | `sellability_norm ≤ 0.2` | 可售性仅 NN（低信号）：reason 原文 |
| 1.0 | `margin_assumption` 含 `all 20`/`fallback`/`basket proxy`/`全量回退` | 使用品类回退价（毛利 X%），非自身成交价 |
| 1.1 | `margin_high − margin_low > 0.3` | 区间宽度 X%（A%–B%），估计范围过宽 |
| 2.0 | `competition_norm < 0.5` | 竞争偏密：稀疏度仅 X%（低于 50% 阈值） |
| 3.0 | `missing_metrics` 非空 | 缺失指标：原文 |
| 4.0 | 有毛利区间且 `cost_input` 空/`missing` | 成本缺失：毛利 X% 为假设区间 |
| 9.0 | 以上都不成立 | 未见明显风险项；仍需人工核验链接 |

**逐行差异化实测**：60 行共产生 **11 种**不同风险组合（`profiles.json.risk_variant_count = 11`），无“行行相同”。

**许可待核验：不生成**。`scores.csv` 没有逐条 `license_verdict`，`sources.csv` 也没有可与 60 条机会连接的键（`scores.source` 是采集描述字符串）。按“只在字段支持时出现”，界面不写该风险，此缺口已写入 `model.md` 与本节。

## 4. 可审计产物

| 文件 | 内容 | sha256（前 16） |
| --- | --- | --- |
| `profiles.json`（60 行，含 `carrier`） | `item_id/platform/rank/product_type/target_user/deliverable/carrier/positioning/why[]/risks[]/evidence_fields[]` + `source_sha256=ab0c3546…` + `price_stats` + `type_counts/target_user_counts/risk_variant_count` | `370665d0290454ce` |
| `model.md` | 意图表、载体规则、理由/风险阈值表、数据缺口说明、复跑 | `9ee99c5bd1a7d15e` |

**样例（原样）**：`item x:1824402140070285653` → `product_type=未分类`、`target_user=人群未明确`、`positioning=…；载体为 Notion 模板（可复制到自己的工作区）`；`why` 三条分别带 83% 分位 / 可售性 85 / 毛利 82%（区间 70%–95%）。

## 5. 搜索与筛选

- 关键词同时匹配**产品摘要**（意图/人群/载体/理由/风险）与**原始标题**；`q=教学内容` 或 `q=notion` 都能命中相应条目（`test_search_blob_covers_product_summary`、`test_notion_is_carrier_not_type`）。
- 平台 / 最低分 / 可售性四档 / 排序 / 计数 / 清空保持；排序入口在表格上方「排序：评分 · 需求分位 · 毛利 · 排名」。

## 6. 测试（真实 exit）

| 套件 | 结果 |
| --- | --- |
| 工作台（含分析测试） | **`Ran 21 tests — OK`，exit=0**（`tests_workbench.log`） |
| 原项目完整套件 | **`Ran 334 tests — OK`，exit=0**，48.3s（`tests_full.log`，`APP_DB_PATH=product-analysis/tmp_full.db`） |

新增/改写测试覆盖：未分类→「人群未明确」、缺字段不臆造百分比、`prompt pack`→提示词库、`resume`→求职简历资料、**竞争偏密仅在 `<0.5` 出现**（0.49 有 / 0.50 无）、`notion` 只作载体、意图优先于工具词、**两行风险不相同**。

## 7. 截图与清单（1440×900 / 390×844）

| 文件 | 尺寸 | bytes | sha256（前 16） | 清单一致 |
| --- | --- | --- | --- | --- |
| `desktop_index.jpg` | 1440×900 | 128,219 | `0f229b00676f25d9` | ✅ |
| `desktop_opportunities.jpg` | 1440×900 | 194,199 | `a7dcccc87fe6d25d` | ✅ |
| `mobile_opportunities.jpg` | 390×844 | 49,960 | `a739941d98c174a8` | ✅ |

清单由浏览器脚本单趟生成并自校验 **checked=9 / mismatches=0 / ok=true**；三份副本与清单**逐字节一致**；五桌面页与三手机页 `overflowX=False`。

## 8. 守卫与边界

`instance/app.db e073f828…`、`docs/design/CONTRACT.md 826c24cc…`、`scoring/scores.csv ab0c3546…`（= `profiles.json.source_sha256`）均未变；未改 `scoring/`、`sourcing/` 原始数据、`app/dash`、旧测试语义；未新增依赖。

## 9. 限制（如实）

1. **45/60 未分类**：标题只有载体词（notion），没有意图词；这是数据现实，不是分类器偏好。若要更细类型，需要补充标题以外的信息（如正文/关键词），本任务不做采集改动。
2. 关键词表对英文、印尼语标题可能误判（如 `lamaran` 归求职）；建议人工抽查 `教学内容 8`、`学习笔记模板 4` 两类。
3. **许可风险未输出**：缺少逐条 verdict 与连接键（见 §3），不臆造。
4. 毛利为模型假设区间，无成本输入时更不确定；界面已标「模型假设」，并单列“成本缺失”风险。
5. 可售性为 `sellability_norm` 规则分档，非实测转化率；理由为 `sellability_reason` 原文。
6. 理由 ≤3、风险 ≤2 条（按验收），更细核对需打开原始链接。

## 10. 复跑

```powershell
.\.venv\Scripts\python.exe tools\workbench\run.py --port 5015        # 页面
.\.venv\Scripts\python.exe tools\workbench\gen_profiles.py           # 产物
cd tools\workbench; ..\..\.venv\Scripts\python.exe -X utf8 -m unittest discover -s tests -t . -v
```

---

# rev8 收尾（术语表扩容 + 未分类按“商业形态 × 需求档”区分）

只改「无品类时如何描述」，**未动布局、评分、数据**。

## A. 术语表（5 类 + 未分类，先意图后载体）

| 优先级 | 生意形态 | 关键词 | 人群 | 交付形态 |
| --- | --- | --- | --- | --- |
| 1 | 学习或生活规划模板 | class / course / student / school / study / notes / planner / tracker / habit / goal / budget / meal / workout / travel | 学生 | 学习/生活规划模板（可复制页面或文档） |
| 2 | 求职简历资料 | cv / resume / job / internship / lamaran / apply / interview | 求职者 | 简历·求职排版与投递资料 |
| 3 | 设计素材 | portfolio / design / psd / figma / ui kit | 设计师 | 设计素材包（PSD/Figma 源文件） |
| 4 | 提示词或数字包 | prompt / pack / bundle / gumroad / checkout / buy / sell | 内容创作者 | 提示词/数字包（文本库、模板包或下载文件） |
| 5 | 教学内容 | teaching / tutorial / guide / how to / import / setup | 教师 | 图文或视频教程 |
| 6 | 未分类 | 都不命中 | 人群未明确 | 待确认（需人工判断） |

`notion` 仍只作载体，追加在 positioning 末尾。

## B. 未分类条目的差异化描述

- 商业形态：`可售`（`sellability_norm ≥ 0.8`）/ `免费引流`（`≤ 0.2`）/ `无价格信号`（其余，含缺失）
- 需求档：`高`（`≥ 0.7`）/ `中`（`0.4–0.7`）/ `低`（`< 0.4`）/ `需求未评估`（缺失）
- 句式：`<商业形态>（可售性 NN / 无价格信号）的<需求档>需求线索（需求分位 NN%），品类待确认，需人工打开原始链接判断交付形态；载体为 Notion 模板（…）`

**实际样例（两条未分类，句式相同但数值不同、互不重复）**

```
无价格信号（可售性 50（未达可售））的高需求线索（需求分位 100%），品类待确认，需人工打开原始链接判断交付形态；载体为 Notion 模板（可复制到自己的工作区）
无价格信号（可售性 50（未达可售））的高需求线索（需求分位 97%），品类待确认，需人工打开原始链接判断交付形态；载体为 Notion 模板（可复制到自己的工作区）
```

`profiles.json` 新增可审计字段 `commercial_form`、`demand_tier`。

## C. 分布（60 行，真实）

`学习或生活规划模板 11 · 教学内容 9 · 提示词或数字包 3 · 求职简历资料 1 · 设计素材 1 · 未分类 35`；
人群：`学生 11 · 教师 9 · 内容创作者 3 · 求职者 1 · 设计师 1 · 人群未明确 35`；风险组合仍为 **11 种**。

## D. 测试与产物

| 项 | 结果 |
| --- | --- |
| 工作台单测 | **`Ran 24 tests — OK`，exit=0**（新增：未分类三条定位两两不同且含真实数值、`pack`→提示词或数字包、`planner`→学习或生活规划模板） |
| 原完整套件 | **`Ran 334 tests — OK`，exit=0**，49.1s |
| `profiles.json` | 60 行，sha256 前 16 `76ee0391d91d5938`，含 `carrier/commercial_form/demand_tier` |
| `model.md` | sha256 前 16 `dc8f2c09b11e8b75`（术语表与阈值已同步） |
| 截图 | `desktop_index.jpg` 1440×900 / 128,219 B / `0f229b00…`；`desktop_opportunities.jpg` 1440×900 / **193,338 B / `61689525…`**；`mobile_opportunities.jpg` 390×844 / **51,187 B / `124e06c7…`** |

manifest 单趟生成并自校验 **checked=9 / mismatches=0 / ok=true**，副本与清单逐字节一致；无横向溢出。守卫：`instance/app.db e073f828…`、`CONTRACT.md 826c24cc…`、`scores.csv ab0c3546…` 未变。

## E. 限制

1. 仍有 **35 条未分类**：标题只有 `notion template` 这类载体词，无任何意图词；已按要求用「商业形态 × 需求档」区分，但**品类本身仍需人工判断**（界面已写明）。
2. 关键词表对英文/印尼语标题可能误判（如 `travel` 命中旅行、`design` 命中设计素材），建议抽查。
3. 许可风险仍不输出（数据缺口）；毛利为模型假设区间；可售性为规则分档。

---

# rev9 按品类聚合（默认视图）

机会页默认改为「按品类聚合」：同品类合并一行；未判品类的按**载体**归组。`view=items` 可切回逐条。

## A. 分组键与组名

| 条件 | group_key | 组名 |
| --- | --- | --- |
| 已判品类 | `type:<品类>` | 品类名（如「教学内容」） |
| 未分类且 carrier 含 Notion | `carrier:notion` | **Notion 模板（品类待定）** |
| 未分类且无 carrier | `carrier:unknown` | **载体未明确（品类待定）** |

## B. 实际分组（60 条 → **7 组**，数值可复算）

| 组名 | 条数 | 需求合计 | 最高分位 | 可售性均值 | 毛利区间（假设） | 近似货源 |
| --- | --- | --- | --- | --- | --- | --- |
| 学习或生活规划模板 | 11 | 24,544 | 93.1% | 0.4591 | 45%–95% | 0 |
| **Notion 模板（品类待定）** | **29** | 59,748 | 100% | 0.4724 | 35%–95% | 2 |
| 求职简历资料 | 1 | 3,577 | 89.7% | 0.5000 | 70%–95% | 0 |
| 教学内容 | 9 | 44,580 | 100% | 0.5000 | 35%–95% | 0 |
| 提示词或数字包 | 3 | 698 | 48.3% | 0.8500 | 70%–95% | 0 |
| 载体未明确（品类待定） | 6 | 27,604 | 100% | 0.5000 | 45%–95% | 0 |
| 设计素材 | 1 | 1,248 | 69.0% | 0.5000 | 70%–95% | 0 |

> 未分类 35 条正好拆成 29（含 Notion 载体）+ 6（载体也未明确），合计守恒。

## C. 每组一行展示的内容

条数、`demand_raw` 合计与 `demand_norm` 最高分位、`sellability_norm` 均值、`margin_low..margin_high` 并集区间（标「假设」）、组内高频风险前 2、评分最高 3 条代表链接、`sources.csv` 关键词匹配的 1–2 条货源（标**近似匹配**，不代表已授权）。行内「展开组内明细（N 条）」列出成员的产品定位/选择理由/主要风险/评分。

视图切换：`按品类`（默认） · `按条目`（`view=items`）；组排序：`按最高评分`（默认） / `按条数`。切换后筛选、计数、清空条件均保留。

## D. 新增产物 `groups.json`

字段：`group_key / group_name / members[] / count / demand_sum / demand_max_norm / sellability_mean / margin_range / risks_top / representative_urls / representatives / sources[] / max_total_score / risk_variants`，并带 `source_sha256=ab0c3546…`（= scores.csv）。sha256 前 16：`0799d68f2ff79c6c`（`profiles.json` 同步重建为 `1eb1d0656ac5e2d7`）。

## E. 测试与截图

| 项 | 结果 |
| --- | --- |
| 工作台单测 | **`Ran 30 tests — OK`，exit=0**（新增 6 例：同载体合并、不同品类不合并、无 carrier 归 unknown、空数据、组统计可复算、展开条数之和=60） |
| 原完整套件 | **`Ran 334 tests — OK`，exit=0**，49.2s |
| 聚合页截图 | `desktop_opportunities.jpg` 1440×900 / 128,953 B / `5314fb359c3a0586…` |
| 展开态截图 | `desktop_opportunities_expanded.jpg` 1440×900 / 181,486 B / `2a2b92d45e2e74be…` |
| 手机截图 | `mobile_opportunities.jpg` 390×844 / 45,779 B / `d602aebcdf63ff77…` |
| 首页截图 | `desktop_index.jpg` 1440×900 / 128,219 B / `0f229b00676f25d9…` |

manifest 单趟生成、自校验 **checked=9 / mismatches=0 / ok=true**，四份副本与清单逐字节一致；五桌面 + 三手机页 `overflowX=False`。守卫：`instance/app.db e073f828…`、`CONTRACT.md 826c24cc…`、`scores.csv ab0c3546…` 未变。

## F. 限制

1. **货源近似匹配命中率低**：7 组中只有「Notion 模板（品类待定）」匹配到 2 条（`sources.type` 含“模板”），其余为 0——因 `sources.csv` 的类型词与组名不完全对齐，界面已标「近似匹配」，**不代表授权**。
2. 组统计是**组级聚合**，不能替代逐条核验；毛利区间为并集（可能跨度很大，已标假设）。
3. `未分类` 仍占 35 条（29 + 6），品类本身需人工判断。
4. 组排序只有「最高评分 / 条数」两种，未做按需求或按可售性排序。
