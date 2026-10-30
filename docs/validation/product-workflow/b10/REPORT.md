# B10：C3 上架准备隔离库预演（工作单 A 真实材料 / B synthetic 演示）

- 执行者：B10；范围：`docs/validation/product-workflow/b10/`（代码未改动；只在系统临时库预演）
- 结论：**材料齐备，只差平台条件** —— 工作单 A 七项就绪检查中 **6 项通过**，唯一未通过 `platform`（`platform_evidence` 为空），导出返回 **409**；工作单 B（**synthetic**）七项全过、导出 200 且内容仅买家字段、内部字段扫描 0 命中。

## 1. 隔离库与工作单

- 库：系统临时目录 `…/b10-rehearsal-*/workflow.sqlite3`（`WORKBENCH_WORKFLOW_DB` 覆盖；**未写生产 `runtime/workflow.sqlite3`**），密钥同目录、跑完删除。
- 建单方式：脚本**直接写入隔离库**（app 的建单入口只接受已归类商品来源，`self:c3-v1` 不在采集目录中），随后走**真实路由**做就绪检查 / GET 导出 / POST 记录。
- 行数：`workorder=2`、`workorder_export=1`、`workorder_event=2`；`verify.json` 记 `db_sha256`。

| 工作单 | 名称 | platform_evidence | 用途 |
| --- | --- | --- | --- |
| A | `学习计划 Excel 模板｜课程/考试倒计时/周计划/复习进度（单文件）` | **空**（诚实留空） | 真实材料 + 平台未知 |
| B | `[SYNTHETIC 演示] 学习计划 Excel 模板…` | `synthetic-demo://xianyu/category-sheet` | **仅演示导出链路，不代表真实平台许可** |

A/B 共用字段：`source=self:c3-v1`；规格取 B7（5 表 / 50 公式 / 14,000 B 级 xlsx）；卖点 5 条、内容清单、交付售后、FAQ 6 条取 **B8 COPY.md**；`sample_ref=b7:selfcheck 17/17（结构/公式自检；非真实 Excel 打开）`；`copy_status=final`、`copy_version=c3-v1-copy`；`cost_minor=500`、`price_minor=990`（**均为假设，非实测/非成交价**）。

## 2. 工作单 A：七项就绪检查逐项结果

| key | 检查项 | 结果 | 说明 |
| --- | --- | --- | --- |
| `specs` | 产品规格完整 | **通过** | 名称/用途/交付物/平台齐备 |
| `supply` | 已选货源 | **通过** | `self:c3-v1`（自制） |
| `license` | 许可三档均允许 | **通过** | 自制作品的作者权利声明（非平台许可） |
| `sample` | 样品/交付入口已核验 | **通过** | 依据 B7 selfcheck 17/17；**不是真实 Excel 打开** |
| `cost` | 成本已知 | **通过（假设）** | `cost_minor=500` 为假设 |
| `platform` | 目标平台条件有证据 | **未通过** | `platform_evidence` 为空 → **blocker** |
| `copy` | 文案定稿 | **通过** | `copy_status=final` + `copy_version` |

- **GET 导出**：`/worksheet/wo:c3-a/export?format=md` → **409**，页面逐字含
  「目标平台条件有证据（xianyu）：缺少目标平台条件证据（platform_evidence 为空）」。
- 页面检查表渲染：**6 个「通过」+ 1 个「未通过」**（`rows.ok_chips=6 / warn_chips=1`）。
- **归类**：其它六项均已具备（数据齐备），缺失项属**平台核验缺失**，不是数据缺失或门槛设计问题。

## 3. 工作单 B（synthetic）：全过 + 导出 + 记录

- 就绪：**7/7 通过**（`ready=True`），页面 `ok_chips=7 / warn_chips=0`。
- `GET /export?format=md|json` → **200**，头 `X-WB-Recorded: false`（GET 零写）。
- **内部字段扫描**（JSON 递归：键名 + 字符串同时扫 `cost/profit/margin/score/internal/raw_ref/snapshot` 与中文「成本/利润/毛利/打分/内部」）：**命中 0**。
- `POST /export/record`（CSRF + 同源）→ **200**，`X-WB-Recorded: true`，`workorder_export` **0 → 1**。
- 导出内容仅买家字段：`title / selling_points / contents / format / price / delivery / aftersales / faq`（+ 版本戳）。

## 4. 导出 ↔ B8/COPY.md 对照

| 字段 | 导出值 | COPY.md | 一致 | 说明 |
| --- | --- | --- | --- | --- |
| 标题 | `[SYNTHETIC 演示] 学习计划 Excel 模板…` | 标题候选 1 | ✅（去前缀后完全相同） | B 带 synthetic 前缀为**显著标注** |
| 卖点条数 | 5 | 5 | ✅ | — |
| 卖点关键词 | 5 张 / 50 个 / TODAY / COUNTIF | 同 | ✅ | 压缩改写，保留可证明关键词 |
| 内容清单·包含 | 5 张表 + 50 个公式 + 下拉/条件格式/打印 + 虚构示例 | §3.1 | ✅ | 改写为单行摘要，事实一致 |
| 内容清单·不包含 | 不含宏/外部链接/图片/第三方字体；三场景未制作；不含代做代填 | §3.1/§4 | ✅ | — |
| FAQ 条数 | 6 | 6 | ✅ | Q/A 取自 COPY §5 |
| 交付说明 | `.xlsx + usage.md`；不代登录、不第三方素材、不含宏 | §6.1 | ✅ | 一致 |
| 售后说明 | 范围/时限/退款**未定**；不含代做/代填/维护/效果保证 | §6.2 | ✅ | 一致 |

`compare_all_same = true`（8 项全一致；2 项为“改写但事实一致”，已在“说明”列注明）。

## 5. 证据

| 文件 | 内容 |
| --- | --- |
| `verify.json` | 两次就绪检查逐项、A 导出 409、B 导出 200、POST 记录行数变化、内部字段扫描、8 项对照、库路径/行数/sha |
| `exports/B_export_synthetic.md` / `.json` | synthetic 导出样例（含版本戳） |
| `exports/A_export_blocked.txt` | A 的 409 阻断页（含 blocker 原文） |
| `PRE-PUBLISH-CHECKLIST.md` | b8 六项硬门槛 + B3 七项就绪检查合并表（含 3 个下一步动作） |
| `seed_and_verify.py` | 可复跑脚本（临时库；跑完删密钥） |

运行：`python -X utf8 docs\validation\product-workflow\b10\seed_and_verify.py`，真实 exit=**0**（cwd=`b10`）。

## 6. 限制与未覆盖

1. **A 不能通过是设计的正确行为**：平台条件未取得（B9 会话失效），**没有编造 `platform_evidence`**；补上之前导出会一直是 409。
2. **B 是 synthetic 演示**，`platform_evidence=synthetic-demo://…`，**不代表闲鱼真实许可/类目允许**；文件名与标题均带 synthetic 标记。
3. `sample_status=verified` 的依据是 **B7 selfcheck 17/17（结构/公式自检）**，**不是真实 Excel/WPS 打开验证**；该验证仍需用户完成。
4. 成本 `cost_minor=500`、价格 `price_minor=990` 均为**假设**：**非成交价、非实测毛利**，导出中亦标注“定价建议，最终以卖家填写为准”。
5. 三场景版本（期末冲刺/英语分项/课程表）**未制作**，不得宣称已包含。
6. 未发布、未登录平台、未采购、未使用第三方素材；未修改 `tools/workbench`、b7/b8、业务库/CONTRACT。
