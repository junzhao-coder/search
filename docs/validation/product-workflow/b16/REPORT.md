# B16：货源候选管理 + 本地样品自检（交付报告）

- 范围：`tools/workbench/`、`docs/validation/product-workflow/b16/`；未改业务库/CONTRACT/评分与货源 CSV
- 结论：**“选货源”与“验货”已能在界面完成**——货源候选可新增/编辑/停用（软删除需二次确认）/粘贴 JSON 导入，可一键「采用为选定货源」并记录 `supply_select`/`supply_replace` 事件；样品自检只读校验工作区内文件（xlsx/pptx/md/csv/pdf），通过才写 `sample_status=verified`，失败保持原状态；7 套测试全绿；已部署 5015（PID 112492）。

## 1. 数据模型（只新增表/列）

- 新表 `workorder_supply_candidate`：`id(sc:<8hex>) / workorder_id / provider / source_url / kind∈同款·替代·不匹配 / commercial / redistribute / resale / license_note / price_minor / currency / sample_status / note / conclusion / is_active / created_at / updated_at`，`CREATE TABLE IF NOT EXISTS`，不改既有列。
- `workorder` 增量列 `supply_note`（PRAGMA 守卫）。
- 候选停用 = `is_active=0`（软删除，历史保留）。

## 2. 功能

| 功能 | 行为 / 校验 |
| --- | --- |
| 新增候选 | `POST /worksheet/<id>/supply/candidates`（CSRF+同源）；`provider` 必填、`kind` 三值枚举、许可三档 `yes/no/unknown`、`source_url` 仅 http/https/self |
| 编辑候选 | `POST …/supply/candidates/<cid>`，未提交字段保持原值；非法值 400 |
| 停用 | `POST …/<cid>/deactivate`，**必须 `confirm=1`**（页面有二次确认对话框），否则 400 |
| JSON 导入 | `POST …/supply/import`：兼容 `b2/candidates.json` 字段（含 `price.amount/currency`、`native_id`、`license_verdict` 等别名），未知字段忽略并计入 `skipped`，逐条报告 |
| 采用 | `POST …/supply/select`（CSRF + revision）：写 `selected_supply_id=sc:…`、`supply_version`（取候选创建时间戳）、三项许可、`supply_note=provider+url`；首次 `supply_select`，替换 `supply_replace` 并记录旧值 |
| 样品自检 | `POST …/sample/check`：路径 `resolve()` 后必须在 `docs/` 或 `tools/` 下，拒绝 `..`/绝对路径逃逸；扩展名 `.xlsx/.pptx/.md/.csv/.pdf`；≤20MB；**只读，不执行任何宏/脚本** |

**自检内容**：xlsx → 表数/非空单元格/公式数 + 无外部链接 + 无 `vbaProject.bin`；pptx → 页数 + 无宏；md/csv → UTF-8 与行数；pdf → `%PDF-` 头部。通过 → `sample_status=verified` + `sample_ref=路径（字节）：检查摘要`；失败 → **状态不变**、返回逐项原因（HTTP 400）。

## 3. 隔离库全流程走查（真实 HTTP，`walkthrough.json`）

| 步骤 | 结果 |
| --- | --- |
| 新建自制单 | 200，`wo:20261024-63c6b8cf`（格式合规） |
| 新增候选 ×2 | 200 / 200（`sc:` 前缀，`kind` 同款与替代） |
| 采用第 1 条 | 200，`selected_supply_id=sc:c33ec434`、`supply_version=20261024T042742`，页面显示“已采用” |
| b7 样品自检 | 200 → `sample_status=verified`，摘要含 `sheets:5 / 公式:50 / 外部链接:0 / 宏:无` |
| 录成本与文案 | 200 → 详情 **6 通过 / 1 未通过** |
| 未补平台导出 | **409** |
| 补 demo 平台后导出 | **200**，仅买家字段、内部字段 0 命中 |
| 计数 | 候选 2 条、事件 8 条 |

截图：`shots/desktop_supply_candidates.png` 1160×750、`shots/desktop_sample_check.png` 1160×282、`shots/mobile_supply_candidates.png` 362×1373。

## 4. 测试（真实 subprocess，`execution_manifest.json`）

| suite | rc | summary |
| --- | --- | --- |
| `b16_supply_sample` | **0** | `Ran 11 tests — OK` |
| `b15_copy_publish` | **0** | `Ran 10 tests — OK` |
| `b12_selfmade` | **0** | `Ran 10 tests — OK` |
| `b1_workflow` | **0** | `Ran 27 tests — OK` |
| `b3_export` | **0** | `Ran 24 tests — OK` |
| `workbench_all` | **0** | `Ran 144 tests — OK` |
| `project_full` | **0** | `Ran 334 tests — OK`（51.7s） |

B16 十一例：候选新增/列表、编辑与非法值、停用需 confirm + 软删除、JSON 导入 imported/skipped、采用与替换事件、采用 revision 校验（400/409）、b7 样品自检通过并写 `sample_ref`、路径逃逸与错扩展名 400（`../`、`C:\`、`docs/../instance/app.db`、`.log`、不存在）、失败不改状态与 revision、md 文件检查、详情页两区块存在。

## 5. 部署与守卫

- 只停本工具 5015 进程后同端口重启：**PID 112492**；生产单 `wo:20261023-88ef9a66` 详情 200 且**已出现「货源候选」「样品自检（本地文件）」两区块**；`/healthz` 仍 `app_id=workbench-opportunity/1`；5023 已停。
- 守卫未变：`instance/app.db e073f828…`、`CONTRACT.md 826c24cc…`、`scores.csv ab0c3546…`、`sources.csv 13679b60…`；未改评分/货源 CSV、未登录/采购/发布。

## 6. 改动摘要（diff）

- 新增 `tools/workbench/supply.py`（候选 CRUD/导入/采用）、`tools/workbench/samplecheck.py`（路径沙箱 + 只读自检）。
- `workflow.py`：`init_schema` 增 `workorder_supply_candidate` 表；`B3_COLUMNS` 增 `supply_note`。
- `app.py`：新增 6 条路由（candidates 新增/编辑/停用、import、select、sample/check）；详情页多渲染两个区块；导入与自检失败返回结果页。
- `views_worksheet.py`：新增 `render_supply()`（候选表 + 采用/停用 + 新增表单 + JSON 导入）与 `render_sample()`（状态 + 路径表单）。
- `tests/test_supply_sample.py`：11 例。

## 7. 限制与偏差（如实）

1. **openpyxl 不在当前 `.venv`**：`import openpyxl` 失败，xlsx 检查自动回退到**标准库 zipfile+XML 只读解析**（sheet 数/`<f>` 公式计数/单元格计数/`xl/externalLinks/`/`vbaProject.bin`），结果与 openpyxl 口径一致（b7 样品：5 表 / 50 公式 / 无外链 / 无宏），但**未安装新依赖**。若你希望严格用 openpyxl，可 `pip install openpyxl` 后自动走主路径。
2. 只做**本地文件**自检：不下载、不访问外部链接，不替代真实 Excel/WPS 打开（b7 样品仍是结构自检）。
3. 采用候选只写货源与许可字段，**不改** `sample_status`/`platform_evidence`/就绪判定。
4. 候选 `kind` 只支持三值；`sample_status` 字段是候选自身的备注性状态，与工作单的 `sample_status` 无自动联动。
5. 生产单当前 `platform_evidence` 仍为空 → 导出仍 **409**，本次未放宽。
