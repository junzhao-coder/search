# B2：Notion 学习笔记模板 — 公开真实货源检索与核验

> 任务：`task-a9b14e0c9f62dab2865c23d6072429be`（revision 2，计划 v7）；执行者 session-01ba487c…。
> 范围：`docs/validation/product-workflow/b2`；只读检索公开页面/仓库，不登录、不采购/付款、不联系卖家、不发布。
> 采样：2026-10-23 10:44–10:54 UTC（18:44–18:54 UTC+8）；证据 UTF-8 无 BOM；cmd/cwd/UTC/exit 见 `logs/`、`raw/`。
> 目标：Notion 学习笔记模板（学生/自学，Notion 可复制页面）；默认来源 `x:1824402140070285653`（@aeshoui 公开推文，2024-08-16，原文称 “notion template for your class … selling it for 5 php … DM”）。未采购。

## 0. 结论表

| 类别 | 结果 | 要点 |
| --- | --- | --- |
| candidates | **8 条** | 同款 3 / 替代 4 / 不匹配 1；详见 `candidates.json` |
| license | **6 条禁止或不明；2 条可商用（MIT）** | 每条均有原文/API 字段与链接；Notion Marketplace 条款明确禁止 repost |
| sample | **3 条已核对 + 5 条部分** | StudySphere / GPA95 / Notion Lecture Notes；均未购买、未执行代码 |
| price | 免费 7 / 付费 1 | College Planner USD 4.50；其余公开免费；Gumroad 未取得 |
| first-choice | **StudySphere（有条件）** | 唯一 MIT + 公开 Duplicate 链接的同款；MIT 覆盖面/实际模板正文待确认 |
| blocked | 见 §5 | 官方 Notion 模板不可转售；无 LICENSE 的仓库不可商业转售；软件不匹配 |
| gaps | 见 §7 | Notion 动态页只返回 shell；Gumroad 超时；无工作单 DB；未购买/未联系 |

## 1. 检索范围与路径

- **技能入口**：当前会话的 `available_skills` 列出 `agent-reach`/`ponytail`，但函数表**无 `skill` 工具**；按任务要求记录一次，改用公开 `web_search` + `curl` + GitHub API；未反调 Host、未用脚本桥接被拒工具。
- **工作单**：`tools/workbench/runtime/workflow.sqlite3` **不存在**；`runtime/` 仅有 `secret_key`（`raw/workbench_runtime_listing.json`）。因此按默认目标执行，未读取/修改任何工作单 DB。
- **检索词**：`GitHub notion study notes template student planner license`、`Notion student notes template free copy official`、`GitHub notion template study notes MIT license`、`Notion template resale license terms`、`site:notion.com/templates study notes template students`、`Notion study notes template Gumroad price`、`site:github.com Notion study template student notes`、`Notion template gallery terms resale redistribution`。
- **GitHub API**：`GET /search/repositories?q=notion+study+template&per_page=20&sort=stars` → `total_count=18`（`raw/gh_search_notion_study_template.json`）；对 5 个候选读取 repo metadata、root contents、README/LICENSE。
- **Notion**：读取 `College Notes`、`Lecture Notes Database`、`College Planner & Dashboard` 三个公开模板页及 Marketplace 条款；解析 JSON-LD（价格/描述）与 “View template”。
- **目标来源**：`https://api.fxtwitter.com/status/1824402140070285653` HTTP 200 → `raw/target_tweet.json`（仅公开元数据，不登录 X）。
- **付费平台**：尝试 Gumroad `177slh/studynotes2`、`digitalixstudios/crmgue`，均 `curl exit=28`（超时，HTTP 000）；未购买，价格/许可标未核验（`logs/page_gumroad_*.log`）。
- 所有原始响应在 `raw/`，命令日志在 `logs/`（含真实 exit；失败的 56/28 原样保留）。

## 2. 候选表（8 条）

| # | ID / provider | kind | 许可结论 | 价格 | 样品 |
| --- | --- | --- | --- | --- | --- |
| 1 | `notion-college-notes` / Notion Marketplace / Zoe | 同款 | 禁止或不明（Marketplace 条款） | USD 0（免费） | 部分 |
| 2 | `notion-lecture-notes-database` / Notion Marketplace | 同款 | 禁止或不明（Marketplace 条款） | USD 0（免费） | **已核对** |
| 3 | `notion-college-planner-dashboard` / Notion Marketplace / Naomi | 替代 | 禁止或不明（Marketplace 条款） | USD 4.50 | 部分 |
| 4 | `github-studysphere` / GitHub / SenaThenu | 同款 | **可商用（MIT，范围待确认）** | 免费 | **已核对** |
| 5 | `github-gpa95-academic-workspace` / GitHub / GPA95 | 替代 | 禁止或不明（个人/学术使用） | 免费 | **已核对** |
| 6 | `github-aliaxandra-learnspace` / GitHub / aliaxandra | 替代 | 禁止或不明（无 LICENSE） | 免费 | 部分 |
| 7 | `github-tfxhk-notion-templates` / GitHub / tfxhk | 替代 | 禁止或不明（无 LICENSE） | 免费 | 部分 |
| 8 | `github-malandinx-studynotes-ai` / GitHub / MalandinX | 不匹配 | 可商用（MIT，但非模板） | 免费 | 部分 |

> 完整字段（kind_reason、license_excerpt、commercial/redistribute/resale、sample_note、stale_risk、fit_note、checked_at、searched_via）见 [candidates.json](candidates.json)；字段校验 `evidence/candidate_validation.json`（count=8、problems=[]）。

## 3. 许可原文（关键摘录）

1. **StudySphere — MIT（可商用）**  
   链接：https://raw.githubusercontent.com/SenaThenu/StudySphere/main/LICENSE  
   原文：`Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software …`  
   范围提示：MIT 文本覆盖 Software/associated documentation；**Notion 外链页面与封面/第三方素材未逐项列明**，转售前需另行确认。

2. **GPA95 — README 自定义使用说明（禁止或不明）**  
   链接：https://raw.githubusercontent.com/GPA95/Student_Academic_Workspace_Notion/main/README.md  
   原文：`This template is free to use and customize for personal or academic use. If you publish a modified version, giving credit would be appreciated.`  
   无 LICENSE 文件；只允许个人/学术使用，未授予商业/转售权。

3. **Notion Marketplace — 平台条款（禁止或不明）**  
   链接：https://www.notion.com/help/template-gallery-guidelines-and-terms  
   原文：`Reposting of content or work, in whole or in part, purchased from other creators is strictly prohibited.`  
   适用于三条 Notion Marketplace 候选；“View template”不等于再分发/转售许可。

4. **aliaxandra / tfxhk — 无 LICENSE（禁止或不明）**  
   链接：https://api.github.com/repos/aliaxandra/RS-School-LearnSpace、https://api.github.com/repos/tfxhk/Notion-templates  
   原文（API 字段）：`"license": null`；root contents 分别为 `README.md/img/`、`README.md + 6 个 zip`，均无 LICENSE。

5. **MalandinX — MIT（可商用，但非模板）**  
   链接：https://raw.githubusercontent.com/MalandinX/studynotes-ai/master/LICENSE  
   原文：`MIT License … to deal in the Software without restriction … sell copies of the Software …`；该仓库是 AI 工具，不是 Notion 模板本体，故 kind=不匹配。

## 4. 样品/交付入口核对

| 候选 | 方式 | 结果 |
| --- | --- | --- |
| StudySphere | README/API + root file list + Duplicate 链接 | **已核对**：README 明确 open-source Notion template、Duplicate 链接、v1.0.0；root 含 LICENSE/templates.py/manager.py；公开 Notion 链接 HTTP 200 但返回 JS shell，未读模板正文 |
| GPA95 | README 107 行 + notion-link.txt + Notion 链接 | **已核对**：README 列出 timetable/course list/ILI tracker/exam schedules/calendar；公开链接 HTTP 200（shell）；未复制模板 |
| Notion Lecture Notes | 公开模板页 JSON-LD + View template | **已核对**：description 明确“one row per lecture with summary, key points, questions, key terms and review status”；USD 0；有 View template |
| Notion College Notes | 公开模板页 | 部分：description 为 lecture/reading/study note space；有 View template；正文未取得 |
| Notion College Planner | 公开模板页 | 部分：planner/dashboard；USD 4.50；正文未取得 |
| aliaxandra | README 158 行 + 公开链接 | 部分：有详细模块列表；Notion 链接 shell；无 LICENSE |
| tfxhk | GitHub contents（zip 列表） | 部分：`study space (NOTION).zip` 等 6 个 zip；未下载/解压 |
| MalandinX | README/API | 部分：确认是 AI 工具；无模板文件 |

- 未购买、未向卖家索取样品、未登录任何平台；未执行下载脚本/宏；tfxhk zip 未打开。

## 5. 首选建议与阻断清单

### 首选（有条件）：`github-studysphere`

- 理由：8 条中唯一同时具备 **同款用途（Notion 学习/课堂笔记模板）+ 公开 Duplicate 链接 + MIT 许可 + 免费** 的候选；README/API/文件清单可追溯。
- 但**不能直接称为可上架货源**，至少需完成：
  1. 确认 MIT 是否覆盖实际 Notion 模板页面、封面/第三方素材（当前 LICENSE 只明确 Software/associated documentation）；
  2. 取得并核对真实模板正文/可复制入口（当前 Notion 页面只返回 JS shell，正文未核验）；
  3. 用户确认授权范围后，再进入 B3 验货/成本；不默认“MIT=整包可转售”。
- 若上述任一不成立，首选应降级为 **无可用货源**；官方 Notion 模板内容最匹配但不可转售，其他仓库无许可。

### 阻断清单（为什么不能用）

| 候选/来源 | 阻断原因 |
| --- | --- |
| Notion College Notes / Lecture Notes / College Planner | Marketplace 条款禁止 repost；免费/付费均无转售权；只能自用/结构参考（College Planner USD 4.50 也未购买） |
| GPA95 | README 仅 personal/academic use；无 LICENSE、无商业/转售授权 |
| aliaxandra | 无 LICENSE；README 仅文档，不能推定为可商用 |
| tfxhk | 无 LICENSE；zip 内容未核对，不能把“有模板文件”当授权 |
| MalandinX | MIT 但为 AI 软件，不是可复制 Notion 模板；kind=不匹配 |
| Andrew Bouras（未列入 8 条候选） | 公开页 USD 15.00（JSON-LD/PreOrder）但无 LICENSE/terms，且为另一创作者产品；不可作为可转售货源 |
| Gumroad `177slh/studynotes2`、`digitalixstudios/crmgue` | curl exit=28，页面/价格/许可未取得；不纳入候选，不做推断 |

## 6. 与 B1 的绑定字段示例（仅示例，不写 DB）

```json
{
  "work_order_id": "WO-EXAMPLE",
  "product": {
    "category": "Notion 学习笔记模板",
    "use_case": "学生/自学课堂笔记",
    "deliverable": "Notion 可复制页面模板"
  },
  "selected_supply_id": "github-studysphere",
  "supply": {
    "provider": "GitHub / SenaThenu",
    "source_url": "https://github.com/SenaThenu/StudySphere",
    "delivery_url": "https://slicky.notion.site/1e47d591140f81d4b788f742300dab8f",
    "kind": "同款",
    "license_verdict": "可商用",
    "license_scope": "MIT Software；Notion 外链页面/素材待确认",
    "sample_status": "已核对",
    "price": {"amount": 0, "currency": "USD", "free": true, "charging": "free"},
    "checked_at": "2026-10-23T10:54:03Z"
  },
  "state": "待用户确认授权范围 / 待B3验货",
  "blocking": ["MIT 对 Notion 页面/素材的覆盖范围待确认", "模板正文未取得"]
}
```

## 7. 覆盖缺口与限制

1. **工作单 DB 缺失**：`tools/workbench/runtime/workflow.sqlite3` 不存在（仅 `secret_key`），无法按用户既有 use_case/交付物校正；本次按默认目标。
2. **动态页面**：StudySphere/GPA/aliaxandra 的 Notion 页面只返回 JS shell；真实模板正文、字段、复制入口未深度核对；仅 README/文件清单/页面元数据。
3. **Gumroad 超时**：两条付费页 curl exit=28（HTTP 000）；未取得价格/许可，不纳入候选；没有购买/联系卖家。
4. **GitHub 搜索有限**：API 搜索 `total_count=18`，只深读少量相关 repo；无认证代码搜索；可能遗漏其它仓库/私有模板。
5. **许可解释**：MIT 覆盖面（模板页面 vs 代码/文档）需用户/实现者确认；Notion Marketplace 条款是平台条款，不替代创作者单独授权；本报告不是法律意见。
6. **未购买/未上架**：无任何采购、付款、联系卖家、发布；目标推文价格（5 PHP，DM）仅作来源参考，不是可用报价。
7. **未执行**：未运行下载的脚本/宏、未打开 zip、未登录平台账号、未改 tools/workbench、scoring/sourcing CSV、业务库/CONTRACT/迁移/冻结文件。

## 8. 证据索引

| 证据 | 路径 |
| --- | --- |
| 候选表 + 校验 | [candidates.json](candidates.json) / [candidate_validation.json](evidence/candidate_validation.json) |
| GitHub 搜索原始 JSON | [gh_search_notion_study_template.json](raw/gh_search_notion_study_template.json) |
| GitHub repo metadata/contents | `raw/gh_repo_*.json`、`raw/gh_contents_*.json` |
| README/LICENSE | `raw/readme_*.txt`、`raw/license_*.txt` |
| Notion 页面/条款 | `raw/notion_college_notes.html`、`raw/notion_lecture_notes.html`、`raw/notion_college_planner.html`、`raw/notion_terms.txt`、`raw/notion_terms_excerpt.txt` |
| 目标推文 | [target_tweet.json](raw/target_tweet.json) |
| 工作单缺失证据 | [workbench_runtime_listing.json](raw/workbench_runtime_listing.json) |
| 命令/exit/UTC | [command_index.json](evidence/command_index.json)、`logs/*.log` |

- 关键真实 exit：GitHub 搜索/仓库/README/Notion 页面/目标推文均 0；`fetch_readme_StudySphere` 56（raw.githubusercontent 连接重置，随后 API 成功）；Gumroad 两条 28（超时）；原始失败日志保留。
- `checked_at`：2026-10-23T10:54:03Z（候选生成时点）。
