# B4 三路决策对照：A 自制 / B 求授权 / C 换品类

> **草案：本文未验货、未定价、未上架。** 许可结论引用 B2（`../b2/candidates.json`、`../b2/REPORT.md`），不替代法律意见。本文只写决策材料，不写代码、不做模板成品、不联网、不联系作者、不采购。
> 目标商品：Notion 学习笔记模板（学生/自学，Notion 可复制页面）；默认来源 `x:1824402140070285653`（@aeshoui 公开推文，2024-08-16）。
> 关联文档：[spec-a.md](spec-a.md)（A 路线规格）、[copy-draft.md](copy-draft.md)（文案骨架）；就绪口径引用 [B3 REPORT](../b3/REPORT.md) 与 [readiness.py](../../../../tools/workbench/readiness.py)。

## 0. 结论摘要（先看）

| 路线 | 最短可行时间（估算，未实测） | 最大风险 | 适用判断 |
| --- | --- | --- | --- |
| **A 自制 Notion 学习笔记模板** | **1–2 个工作日** | 内容质量/需求不确定；自制内容与第三方素材边界 | **默认优先**：许可最可控、可复用，但需自己做样品和文案 |
| **B 向现有作者求授权** | **≥7 个日历日**（等作者回复；不是制作时间） | 授权范围不足/作者不回复；MIT 是否覆盖 Notion 页面/素材未核验 | 仅当用户愿意等且有联系渠道；不能先上架后补授权 |
| **C 换品类（自制学习计划/复习清单等）** | **1–2 个工作日 + 新品类核验** | 新品类需求/许可/平台条件未核验；容易变成“另一个 A” | A 的内容或平台不适配时的兜底；**必须先做 B2 式检索** |

**建议**：先选 **A**（可控、最快形成可复制样品）；B 只作为有联系渠道时的并行谈判，不作为默认；C 只在 A 的样品/需求验证失败或用户明确换品类时启动。三路都**不包含**自动上架、自动发布、采购/付款、收益承诺。

## 1. 输入证据（实际读取）

### 1.1 B2：8 条公开货源，当前没有“可直接转售”的已核验货源

- 分布：同款 3、替代 4、不匹配 1；许可 **6 条禁止或不明、2 条 MIT**；样品 3 条已核对、5 条部分（`../b2/candidates.json`，`evidence/candidate_validation.json`）。
- Notion Marketplace 条款：`Reposting of content or work, in whole or in part, purchased from other creators is strictly prohibited.`（`../b2/REPORT.md` §3；原链接 https://www.notion.com/help/template-gallery-guidelines-and-terms）。
- StudySphere：MIT 原文允许 use/copy/modify/merge/publish/distribute/sublicense/sell copies，但 **MIT 是否覆盖 Notion 外链页面、封面/第三方素材未核验**（`github-studysphere`，`license_scope` 字段）。
- GPA95 仅 `personal or academic use`；aliaxandra/tfxhk 无 LICENSE；MalandinX MIT 但非模板（`../b2/candidates.json`）。
- 结论引用 B2：**没有任何一条同时满足“同款 + 三档许可 + 已核对交付入口”的可直接上架货源**；A 路线因此是“自己做供给”，不是复制 B2 候选。

### 1.2 B3：七项就绪检查（服务端推导，不能点“完成”）

来自 `../b3/REPORT.md` §1 与 `../../../../tools/workbench/readiness.py`（`readiness()`）：

| key | 通过条件 |
| --- | --- |
| `specs` | `name/use_case/deliverable/target_platform` 非空 |
| `supply` | `selected_supply_id` 非空 |
| `license` | `supply_license_commercial/redistribute/resell` 均为 `yes` |
| `sample` | `sample_status=verified` |
| `cost` | `cost_minor>0` 或 `cost_known=yes` |
| `platform` | `platform_evidence` 非空 |
| `copy` | `copy_status=final` 且 `copy_version` 非空 |

### 1.3 需求证据（仅代理指标，非成交）

- `categories.json`（`../../money-project/product-taxonomy/categories.json`）：`Notion 学习笔记模板` **count=14、share=0.2333、demand_sum=57113.0、demand_max_norm=0.931、sellability_mean=0.4393、margin_range=[0.35,0.95]、max_total_score=0.7635**；`source_sha256=ab0c3546…`（scores.csv）。
- `profiles.json` 实际路径是 `../../money-project/product-analysis/profiles.json`（**任务所写 `product-taxonomy/profiles.json` 不存在**）：60 行，其中 10 行含 Notion 学习/学生信号；`type_counts` 中“学习或生活规划模板”11、“学生”target_user 11；`price_stats` 20 条、有效价 1.0–1.88。
- **口径**：`demand_sum=57113` 是需求/互动代理，不是成交、收入或利润；`margin_range` 是模型假设，不是实际毛利。引用时不把它当销量或盈利证据。

## 2. 三路对照表

| 维度 | A 自制 | B 求授权 | C 换品类 |
| --- | --- | --- | --- |
| 依据 | B2 8 条无“可直接转售”货源；B3 七项 readiness | B2 `github-studysphere`；Notion Marketplace 条款；B3 | taxonomy 需求仅参考；C 货源/许可未核验 |
| 做法 | 按 [spec-a.md](spec-a.md) 自建 Notion 页面/数据库/视图；自己写文案 | 向 StudySphere 作者或 Notion 模板作者请求书面授权，取得模板/素材与三档许可 | 改做“学习计划/复习清单”等不同交付形态（表格/PDF/文档）；重新核验品类与平台 |
| 时间成本 | **1–2 个工作日**（估算：结构 0.5 天、示例/自测 0.5–1 天、文案 0.5 天；未实测） | **≥7 个日历日**（等回复；谈判/补证另计；不是制作时间） | **1–2 个工作日 + 新品类检索/核验 1–2 天**（估算，未实测） |
| 现金成本 | 采购 0；人工时间未计价；Notion 账号按用户现有条件 | 采购/授权费 **未知**（需作者报价）；人工沟通时间 | 采购 0；人工时间未计价；可能需模板工具/导出工具（未核验） |
| 许可风险 | **低–中**：全部自写/自制则三档可主张；若使用第三方字体/图片/模板片段则回到 B2 的不确定 | **高**：无书面授权=不可；MIT 是否覆盖实际模板页面/素材未核验；作者可能拒绝或限制转售 | **中**：新品类可能涉及第三方资料/字体/平台条款；需重新核验，不能沿用 B2 结论 |
| 所需证据 | 页面/数据库/视图清单、示例数据、Duplicate/导出自测、自制素材声明、平台条件 | 作者身份与授权原文（明确 commercial/redistribute/resale）、模板版本、可复制入口、素材范围 | 新品类需求证据、许可/素材来源、样品/交付入口、平台条件 |
| 可复用性 | **高**：结构可复用到不同学科/学期；文案可版本化 | **取决于授权**：若只允许自用，复用价值低；若允许转售，仍需版本管理 | **中**：可复用到学习计划/复习场景，但离开 Notion 模板叙事 |
| 失败情形 | 结构搭完但不可复制/关系错；内容质量不足；无需求 | 7 天无回复；拒绝；只允许 personal use；授权不覆盖素材/转售 | 新品类无许可清晰来源；平台不适用；需求证据不足 |
| 退出条件（可判断） | **2 个工作日**内没有可复制、可自测的样张，或连续 2 次 Duplicate 测试失败 → 停止 A，转 C；不投入 UI 美化 | **7 个日历日**无书面回复，或回复缺少 commercial/redistribute/resale 任一项，或拒绝 → 退出 B，转 A 或 C；不得先上架后补 | **2 个工作日**内没有许可清晰/可自制且平台条件有证据的样品 → 暂停 C，不硬凑；不以“关键词命中”替代货源 |

## 3. 逐路展开

### A. 自制 Notion 学习笔记模板（默认）

- **交付**：按 [spec-a.md](spec-a.md) 做出可 Duplicate 的 Notion 页面（或导出文件），最小范围是 7 页、4 个数据库、7 个视图、示例数据；不含 UI 美化、自动化脚本、客服代做。
- **现金**：采购 0；主要是人工时间。不要用“零成本”掩盖时间成本。
- **许可**：自写内容可主张三档；但**字体、图标、第三方模板/图片**必须替换或取得许可，否则不能宣称可商用/可转售（B2 的教训：MIT 代码不等于模板页面/素材）。
- **B3 就绪**：`license` 与 `sample` 在“全部自制 + 自测通过”前提下可天然为 `yes`；`supply` 需登记 `self:a-v1`（自定义 ID，非外部货源）；`specs`、`cost`、`platform`、`copy` 仍需用户/执行者决定（详见 §4）。
- **失败/退出**：结构自测失败、Duplicate 不可复现、示例数据/关系错、用户内容标准不通过；按上表 2 个工作日退出。
- **来源**：B2 的 8 条中没有可直接转售的货源（`../b2/REPORT.md` §5）；B3 七项检查（`../b3/REPORT.md` §1）。

### B. 向现有作者求授权（StudySphere 为首个谈判对象）

- **对象**：`github-studysphere`（B2 唯一 MIT + 公开 Duplicate 链接的同款；`../b2/candidates.json`）。备选可向 Notion 模板作者询价，但 B2 的 Marketplace 条款已明确 repost 禁止，谈判成本更高。
- **要问清楚的五项**：①是否允许商业使用；②是否允许再分发；③是否允许转售（三档必须分别书面 yes）；④授权是否覆盖 Notion 页面、封面、示例数据和第三方素材；⑤版本/后续修改如何确认。只拿到“MIT”不够。
- **时间**：**≥7 个日历日**等待回复（估算/约定）；若作者要求报价，现金未知；不要假设免费。
- **许可风险**：StudySphere 的 MIT 文本覆盖 Software/associated documentation，**Notion 外链页面与第三方素材未逐项列明**（B2 `license_scope`）；MIT 原文不能自动推出“页面/封面可转售”。
- **B3 就绪**：`license` 只有在三档书面 yes 后才可通过；`sample` 需要真实模板/交付入口；`cost`、`platform`、`copy` 仍需用户决定；`supply` 用作者/仓库 ID。
- **退出条件**：7 天无回复、拒绝、只允许 personal/academic、授权不含转售或素材范围不清 → 退出 B，转 A/C；**不先上架后补授权、不默认 MIT=整包可转售**。
- **来源**：B2 `github-studysphere` 的 `license_excerpt`/`license_scope`；Notion Marketplace 条款（B2 REPORT §3）。

### C. 换品类（兜底，先核验再选）

- **定义（本文采用的 C）**：从“Notion 学习笔记模板”换到**自制“学习计划/复习清单”**（CSV/PDF/文档交付，或不同载体的学习规划件），面向学生/自学人群；不以第三方 Notion 模板为货源。另一个可选方向是“Notion 使用教程/导入设置”内容型商品，但同样需重新核验。
- **为什么不是直接选 B2 的其它 Notion 模板**：B2 的 Notion Marketplace 三条受 repost 条款限制；GPA/aliaxandra/tfxhk 无商业许可；换品类不能把“无 LICENSE”洗成可售。
- **时间/现金**：1–2 个工作日制作（估算）+ 1–2 天新品类检索/核验；采购 0，人工时间未计价；若使用表格/导出工具，成本未核验。
- **许可风险**：中；自制内容可控，但新品类可能使用第三方模板/字体/资料，需重新做 B2 式来源核验；不能援引 B2 的 Notion 结论。
- **B3 就绪**：`specs` 需重写（品类/交付物变化）；`supply` 若为自制用 `self:c-v1`；`license`/`sample` 依新品类而定；`cost`/`platform`/`copy` 仍需用户决定。
- **退出条件**：2 个工作日内没有“许可清晰/可自制 + 平台条件有证据 + 可复制样品”的组合 → 暂停 C；不以 taxonomy 的高需求分代替成交/许可证据。
- **来源**：taxonomy `categories.json` 的“学习或生活规划模板”相邻需求（11 条，`profiles.json` type_counts），仅作方向参考；**C 的具体货源/许可未核验**。

## 4. B3 readiness 七项：选 A 后哪些天然为是，哪些仍需决定

| B3 key | 选 A 后状态 | 说明 |
| --- | --- | --- |
| `specs` | **仍需填写** | 用 [spec-a.md](spec-a.md) 的页面/数据库/视图；不等于已填工作单 |
| `supply` | **需设定** | 自制货源建议 `self:a-v1`；不是外部供应商，不能伪造供应商 |
| `license` | **可天然为是（有前提）** | 全部自写/自制且无第三方素材时可三档 yes；用了第三方字体/图片/模板片段则不是 |
| `sample` | **可天然为是（需自测）** | 做出可复制页面并完成 Duplicate/导出测试后设 `verified`；未测不得填 |
| `cost` | **需用户决定** | 现金 0 也要明确 `cost_known=yes` 或记录人工成本；B3 不接受“成本未知” |
| `platform` | **需用户提供证据** | 闲鱼类目/虚拟交付/标题限制等平台条件；不能以“看到同类在卖”代替 |
| `copy` | **需用户/编辑定稿** | [copy-draft.md](copy-draft.md) 只是草案；需 `copy_status=final` 与 `copy_version` |
| `price`（导出字段） | **需用户决定** | 不写价格；最终售价由用户填，B3 导出只带建议售价/待定 |

**结论**：A 路线天然解决“许可（自制前提下）+ 样品（自测后）”，但**不会自动解决** specs、supply 登记、成本/定价、平台条件、文案定稿；不要把“自制”误当成“已就绪”。

## 5. 未核验项（明确）

- 三路时间均为**估算**，未实测；现金/授权费均未询价。
- B2 的 StudySphere MIT 对 Notion 页面/素材覆盖未核验；未联系作者、未取得模板正文。
- C 的具体品类需求、可售来源、平台条件未核验；taxonomy 的 57113 只是需求代理，不是成交。
- 未定价、未上架、未购买、未登录平台、未发布、未联系卖家/作者；本文件不替代法律意见。

## 6. 证据索引

| 证据 | 路径/字段 |
| --- | --- |
| B2 候选 8 条/许可/样品 | [candidates.json](../b2/candidates.json)、[REPORT.md](../b2/REPORT.md) |
| Notion 条款原文 | `../b2/REPORT.md` §3；https://www.notion.com/help/template-gallery-guidelines-and-terms |
| B3 七项 readiness | [B3 REPORT](../b3/REPORT.md) §1、[readiness.py](../../../../tools/workbench/readiness.py) `readiness()` |
| 需求代理 | [categories.json](../../money-project/product-taxonomy/categories.json)（`count`/`demand_sum`/`max_total_score`） |
| 画像（实际路径） | [profiles.json](../../money-project/product-analysis/profiles.json)（60 行；任务所写 product-taxonomy/profiles.json 不存在） |
| A 规格/文案 | [spec-a.md](spec-a.md)、[copy-draft.md](copy-draft.md) |
