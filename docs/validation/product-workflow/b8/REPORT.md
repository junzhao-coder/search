# B8 · C3 三场景差异化、文案、平台规则与定价（交付报告）

> **草案：未验货、未定价、未上架。** 本文汇总 [DIFFERENTIATION.md](DIFFERENTIATION.md)、[COPY.md](COPY.md)、[PLATFORM-RULES.md](PLATFORM-RULES.md)、[PRICING.md](PRICING.md)；只写文档，不改代码/样品/其他验收目录，未采购、未登录平台、未发布。
> 依据：[B7 REPORT](../b7/REPORT.md)（v1 5 表/50 公式/selfcheck 17/17）、[B7 usage](../b7/usage.md)、[B7 samples-public](../b7/samples-public.json)、[B5 C-candidates](../b5/C-candidates.md)、[B3 REPORT](../b3/REPORT.md)。
> 采样：2026-10-23 20:46–20:48 UTC+8（12:46–12:48Z）；规则页 HTTP 200，原始响应在 `raw/`。

## 0. 结论摘要

| 项 | 结果 |
| --- | --- |
| 差异化 | 3 场景 × 5 项 = **15 项差异**；现有能力 3 / 需新增公式 3 / 需手工维护 6 / 暂不可实现 3 |
| 文案 | 标题 3、卖点 5（均对应 v1/差异表/公式）、购买须知 8、FAQ 6、内容清单/交付售后；全部草案 |
| 平台规则 | 取得闲鱼官方《社区信息发布规范》（HTTP 200，最新修订 2026-09-07）；摘录 6 条；**未取得**电子表格类目细则/逐词敏感词表/C3 在售页 |
| 定价 | B7 C3 公开中位 $29.95–$99.99（Gumroad 三组）、BOOTH 1,500 JPY；给出 ¥9.9–19.9 / ¥29.9–39.9 / ¥49.9–69.9 三档**假设** |
| 边界 | 未制作三场景成品、未在真实 Excel/WPS 打开 v1、未定价/上架/采购/登录 |

## 1. 差异化（详见 DIFFERENTIATION.md）

v1 基线：5 张表（使用说明/课程与考试/考试倒计时/周计划/复习进度）、50 个公式、条件格式/下拉/打印区域；selfcheck 17/17（B7 §4–§5）。三版各加 1 张表：

| 场景 | 新增表 | 买家能感知的差异 | 实现方式统计 |
| --- | --- | --- | --- |
| 期末冲刺 | `冲刺日计划` | 按考试日倒排每日任务 + 今天/3 天/7 天状态 + 完成率 | 新公式 `IF/TODAY/COUNTIF`；字段/打印手工；自动导入暂不可 |
| 考研/四六级 | `英语分项` | 词汇/听力/阅读/写作/翻译分项完成率/正确率 | 新公式 `IF/AVERAGE`；计划/正确率手工；自动评分暂不可 |
| 学期周计划 | `课程表` | 星期+时段课程冲突提示 + 按周/按天查看 | 新公式 `COUNTIFS`；课表/打印手工；教务导入暂不可 |

- **15 项差异**：现有公式/能力 3（三版视图）、需新增公式 3（三版各 1 组）、需手工维护 6（字段+打印）、暂不可实现 3（自动导入/评分）。
- 每项都写明具体字段/公式/视图/打印；不包含 UI 美化、宏、AI、云同步、代做；不写“提升效率 X 倍/包过/保证提分”。

## 2. 文案（详见 COPY.md）

- 标题候选 **3**：单文件基础版 / 期末冲刺（规划）/ 考研四六级（规划）。
- 卖点 **5**：v1 5 表 50 公式 → 考试倒计时 `TODAY/IF` → `冲刺日计划` `IF/TODAY/COUNTIF` → `英语分项` `IF/AVERAGE` → `课程表` `COUNTIFS`；每条对应 [DIFFERENTIATION.md](DIFFERENTIATION.md) 或 B7。
- 内容清单：v1 5 表/50 公式/示例；三场景为规划，各加 1 表，**未制作**。
- 购买须知 **8**、FAQ **6**、交付与售后说明；全部标“草案/待验货/未定价/未上架”。
- 未写绝对化/收益/效果承诺；当前可交付仅 v1，规划版不得单独售卖。

## 3. 平台规则（详见 PLATFORM-RULES.md）

- 官方页：**闲鱼社区信息发布规范** `https://h5.m.goofish.com/wow/moyu/moyu-project/doc/pages/5cgFQkDGBXlA`，curl HTTP **200**，267,924 B；页面最新修订 **2026-09-07**；原文 `raw/goofish_publish_rules.html`，抽取文本 `raw/goofish_publish_rules_text2.txt`。
- 关键摘录（6 条）：虚假夸大/误导宣传（L130）；商品实际不存在/信息与实物不一致（L152）；学术/考试作弊、代接电话/代体检等（L152）；盗版/侵犯著作权（L156）；“不可查询的虚拟服务商品”（L160）；电子出版物/经营性卖家资质（L167–170，**是否适用于 Excel 未核验**）。
- 标题/文案避坑清单 **10 条**：不写包过/保证提分/绝对化/代做/代写/盗版/虚假原价/永久更新/官方认证/外部引流；每条附规则依据或“未核验”说明。
- 尝试 `goofish.com/search?q=学习计划表`：HTTP 200 但返回反爬/登录壳（baxia），无可读列表/价格；**未取得**同类闲鱼页面。官方页未给出逐词敏感词表，本文按规则语义整理，不冒充平台词库。

## 4. 定价（详见 PRICING.md）

B7 `samples-public.json`（2026-10-23T12:30Z）C3 价格带：

| 来源 | 中位 / 区间 | 说明 |
| --- | --- | --- |
| Gumroad excel dashboard | **$99.99**；P90 $349 | 国际平台、USD、数据日 2026-08-05；rating 非销量 |
| Gumroad planner printable | $29.95；P90 $299 | 相邻品类 |
| Gumroad budget spreadsheet | $36.99；P90 $199.99 | 相邻品类 |
| BOOTH 学習計画Excel | **1,500 JPY**（B7 约 $10） | 单品；页面禁止再配布/转卖 |
| 中文摘要（非 C3） | 9.9 / 19.9 CNY | 仅 C1/C4 搜索摘要，非 C3 页面 |

三档假设（人民币）：

| 档位 | 假设价 | 适用 | 主要不确定性 |
| --- | --- | --- | --- |
| 入门/单版本 | **¥9.9–19.9** | v1 或单场景 | 无闲鱼 C3 成交数据；低价可能覆盖不了人工 |
| 标准/双版本 | **¥29.9–39.9** | v1 + 1 个已完成场景 | 场景版未制作；用户是否愿为多一表多付未核验 |
| 打包/三场景 | **¥49.9–69.9** | v1 + 3 个场景 | 三版未制作/未验货；可能超出闲鱼心理价 |

> 不把 Gumroad/BOOTH 价直接换算成闲鱼价；不写“必卖/稳赚/保证回本”；价格均为假设，不是成交价。

## 5. 证据与采样

| 证据 | 路径/URL |
| --- | --- |
| B7 报告/样品/自检 | [REPORT.md](../b7/REPORT.md)、[sample-study-planner-v1.xlsx](../b7/sample-study-planner-v1.xlsx)、[selfcheck.json](../b7/selfcheck.json)（17/17 PASS）、[usage.md](../b7/usage.md) |
| B7 公开抽样 | [samples-public.json](../b7/samples-public.json)（20 条；C3 四条；`sampled_at_utc=2026-10-23T12:30:00Z`） |
| B5 C3 定义 | [C-candidates.md](../b5/C-candidates.md) §C3 |
| B3 七项 | [B3 REPORT](../b3/REPORT.md) §1；`../../../../tools/workbench/readiness.py` |
| 闲鱼规则 | 官方 URL（上文）；[raw/sampling.json](raw/sampling.json)、[raw/goofish_publish_rules.html](raw/goofish_publish_rules.html)、[raw/goofish_publish_rules_text2.txt](raw/goofish_publish_rules_text2.txt) |
| 搜索页尝试 | [raw/goofish_search_study_planner.html](raw/goofish_search_study_planner.html)（200 但反爬/登录壳） |
| 本报告四份文档 | DIFFERENTIATION / COPY / PLATFORM-RULES / PRICING |

- 真实命令/exit：规则页 `curl` exit 0 / HTTP 200；搜索页 `curl` exit 0 / HTTP 200 但反爬壳。`raw/sampling.json` 记录采样时点与字节。
- **未核验**：闲鱼电子表格类目细则、平台逐词敏感词表、C3 闲鱼在售价/销量、v1 在真实 Excel/WPS 的公式计算、三场景版本实际制作与打印效果。

## 6. 限制（必须与文档一起读）

当前会话函数表没有 `skill` 工具；公开检索使用 `web_search` + `curl` 页面级抓取，未反调 Host/未桥接被拒工具。

1. 当前只有 v1 样品且**未在真实 Excel/WPS 打开**；三场景为规划，未制作、未验货；不能宣称“已可交付/已可上架”。
2. 平台规则只读到社区信息发布规范；**电子表格/电子资源类目、虚拟交付入口、敏感词过滤**未取得；搜索页反爬，未做同类闲鱼页面核验。
3. 定价全部为假设；B7 价格来自 Gumroad/BOOTH 与中文摘要，标价≠成交，rating≠销量；无闲鱼 C3 成交数据。
4. 未采购、未登录平台账号、未联系卖家、未发布、未制作模板成品；不替代法律/平台审核意见。
5. 未改 `tools/workbench`、`b7/sample-study-planner-v1.xlsx`、scoring/sourcing、业务库/CONTRACT/迁移/冻结文件；只写 `docs/validation/product-workflow/b8/`。
