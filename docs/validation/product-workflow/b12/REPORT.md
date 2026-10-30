# B12：自制商品界面建单 + 单号归一 + 七项证据录入（交付报告）

- 执行者：B12；范围：`tools/workbench/`、`docs/validation/product-workflow/b12/`
- 结论：**直写库与非常规单号已消除**——自制商品可在界面建单（`GET/POST /worksheet/new`，单号 `wo:yyyymmdd-8hex`），存量单 `wo:c3-prod-20261023` 已**备份后归一化**为 `wo:20261023-88ef9a66`（保留映射）；七项证据可在详情页逐组录入，全流程界面可走通到导出；五套测试全绿；已部署 5015（PID 124916）。

## 1. 自制商品建单入口（新增）

| 项 | 实现 |
| --- | --- |
| 页面 | `GET /worksheet/new` → 「新建自制商品」表单（`name/use_case/deliverable/target_platform` 必填；`fmt/language/version/includes/excludes` 可选；`item_id` 可留空自动生成 `self:<名称>`） |
| 提交 | `POST /worksheet/new`，`self_made=1`，**CSRF + 同源**校验沿用；`submit_key` 由页面生成（双击不重复建单） |
| 服务端 | `workflow.create(..., self_made=True)`：**跳过采集目录校验**，仍校验必填/长度/平台/状态；`item_id` 必须 `self:` 前缀 |
| 快照 | `snapshot_json = {"self_made": true, "note": "自制商品，无采集来源", "item_id": …, "title": …}` |
| 单号 | `wo:{yyyymmdd}-{8hex}`，代码内**正则自检**（`^wo:\d{8}-[0-9a-f]{8}$`），不满足即内部错误 |
| 幂等 | 同 `submit_key` 同内容 → 原单（`?deduplicated=1`）；同键不同内容 → **409** |
| 表结构 | **未新增表**；复用既有列 |

页面入口：`/worksheet` 列表底部新增「新建自制商品」链接。

## 2. 存量单归一化（方案 a：备份后改写，保留映射）

| 项 | 值 |
| --- | --- |
| 备份 | `b12/backup/workflow-20261023T140036Z.sqlite3`（备份 sha `0914b137…` = 归一前生产库 sha） |
| 旧单号 | `wo:c3-prod-20261023`（历史直写，不符合约定） |
| 新单号 | **`wo:20261023-88ef9a66`** |
| 同步更新 | `workorder.workorder_id`、`workorder_event`、`workorder_export`（本次无导出行） |
| 映射 | `b12/id_mapping.json`（old/new/时间/备份 sha/归一后行数与 sha） |
| 核对 | 列表含新单号且**不再含旧单号**；详情 200 且 **6 通过 / 1 未通过**；行数 `workorder=1 / event=2 / export=0` |

选择 (a) 而非 (b) 的理由：目标明确要求“消除非常规单号”，且此处引用只涉及两张同库表、无外键；**先备份再事务内改写**可回滚，映射留档可追溯。

## 3. 七项证据录入（页面内完成，不再直写库）

详情页「录入证据」表单按组呈现，全部走 `POST /worksheet/<id>/evidence`（CSRF + `revision` 乐观锁 + 同事务审计）：

| 组 | 字段 |
| --- | --- |
| 货源 | `selected_supply_id`、`supply_version` |
| 许可 | `supply_license_commercial / redistribute / resell`（`yes/no/unknown`） |
| 样品 | `sample_status`（未核验/核验中/已核对）、`sample_ref`（**兼容提交名 `sample_note`，写入同列，不新增列**） |
| 成本 | `cost_minor`（分）、`cost_known` |
| 平台 | `platform_evidence` |
| 文案 | `copy_status`、`copy_version`、`selling_points`、`price_minor`、`delivery_note`、`aftersales_note`、`faq_json` |

校验：非整数成本 → **400**；旧 revision → **409 且不丢原值**；`status/ready/gate_*` 等越级字段 → **403**；未提交字段保持原值。

## 4. 界面全流程走查（隔离库，真实 HTTP，不直写库）

`walkthrough.json` 记录**操作序列 + 每步响应码 + 详情页文案**（隔离库在系统临时目录，跑完删密钥）：

| 步骤 | 响应 | 页面文案 |
| --- | --- | --- |
| GET `/worksheet/new` | 200 | 含「新建自制商品」表单 |
| POST 建单（`self_made=1`） | 200 | 单号 `wo:20261023-ee6025fc`，格式校验通过 |
| 录 supply | 200 | 2 通过 / 5 未通过 |
| 录 license | 200 | 3 通过 / 4 未通过 |
| 录 sample | 200 | 4 通过 / 3 未通过 |
| 录 cost | 200 | 5 通过 / 2 未通过 |
| 录 copy | 200 | **6 通过 / 1 未通过** |
| GET export（platform 空） | **409** | 含「缺少目标平台条件证据」 |
| 录 demo platform（`demo://b12/walkthrough-only`） | 200 | 7 通过 / 0 未通过 |
| GET export json | **200** | 仅买家字段；无 `cost_minor/supply_note/raw_ref/snapshot` |
| POST export/record | 200 | 写入 1 行导出记录 |

**截图**（`b12/shots/`，均记录 sha 与检查标记）：
- `desktop_new_form.png` 1440×900（新建表单）
- `desktop_detail_6_1.png` 1160×650（**6 通过 / 1 未通过**，导出链接不存在=禁用态）
- `desktop_detail_ready.png` 1160×770（**7 通过**，可导出链接存在）
- `mobile_detail_ready.png` 362×928（390×844 视口裁剪）

## 5. 测试（真实 subprocess + `execution_manifest.json`）

| suite | rc | summary |
| --- | --- | --- |
| `b12_selfmade` | **0** | `Ran 10 tests — OK` |
| `b1_workflow` | **0** | `Ran 27 tests — OK` |
| `b3_export` | **0** | `Ran 24 tests — OK` |
| `workbench_all` | **0** | `Ran 123 tests — OK` |
| `project_full` | **0** | `Ran 334 tests — OK`（47.9s） |

B12 十例：新建表单字段、自制建单成功 + 单号正则、必填缺失 400、幂等、`self:` 前缀强制、七项证据经 UI 录入后 6/1 且导出 409、revision 冲突/非法值回滚、伪造 `ready/status/gate_*` 403、demo 平台后导出 200 且仅买家字段、GET 零写（库 sha 不变）。

## 6. 部署与守卫

- 只停本工具 5015 进程后同端口重启：**PID 124916**；`/worksheet/new` 200（含 `self_made` 与 `submit_key`）、`/worksheet` 200 且含新建链接、列表含归一后单号且**不含旧单号**；`/healthz` 仍 `app_id=workbench-opportunity/1`；5020 已停。
- 守卫未变：`instance/app.db e073f828…`、`CONTRACT.md 826c24cc…`、`scores.csv ab0c3546…`、`sources.csv 13679b60…`；未改评分/货源 CSV、未新增依赖。

## 7. 限制

1. 单号归一化改写了**生产工作单库**的主键（已备份 + 映射留档）；若你此前把旧单号记在别处（如发布记录），需按 `id_mapping.json` 更新。
2. `sample_note` 只是**提交别名**，落库仍在 `sample_ref` 列（不新增列）；页面标签为“样品核验证据”。
3. 自制商品跳过采集来源校验是**产品设计**（自制无采集来源），但仍强制 `self:` 前缀与必填校验；不会因此放宽就绪判定。
4. 走查中的 `demo://b12/walkthrough-only` 仅用于验证“补平台证据后能导出”，**不代表真实平台许可**；生产单的 `platform_evidence` 仍为空（导出 409）。
