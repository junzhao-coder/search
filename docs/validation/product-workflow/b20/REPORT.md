# B20：工作台收敛为三步向导（选品 → 找货源 → 写介绍）交付报告

- 范围：`tools/workbench/`、`docs/validation/product-workflow/b20/`；未改业务库/CONTRACT/评分与货源 CSV
- 结论：新增 **`/pick` → `/source` → `/copy`** 三步向导（顶部向导条 + 下一步/返回），首屏只放当前步骤需要的内容；旧路由 `/`、`/opportunities`、`/content`、`/worksheet` 等**全部保留可用**；三步复用同一工作单库、同一套 CSRF+revision 校验与七项就绪判定，未放宽任何门槛。3 套测试全绿；已部署 5015（PID 119132）。

## 1. 三步与路由

| 步骤 | 路由 | 内容 |
| --- | --- | --- |
| ① 选品 | `GET /pick` | 按已归类商品型聚合：商品类型 / 条数 / 需求分位（最高评分）/ 可售性均值 / 竞争稀疏（自用·不明许可来源数）/ 代表链接；关键词 `q` 与平台筛选保留状态；每行「选这个」→ 复用 `POST /worksheet/new` 建单 → **303 到 `/source?wo=<id>`**；无效参数有提示；空态引导「新建自制商品」 |
| ② 找货源 | `GET /source?wo=` | 顶部显示当前商品摘要（名称/用途/交付物/平台/revision）+ 样品状态；候选新增/编辑入口（复用 B16 路由）、一键采用、停用（confirm）、样品自检；**「确定上架商品」仅在 `selected_supply_id` 非空时可用**（按钮禁用 + 文案说明；`POST /worksheet/<id>/source/confirm` 服务端再校验，未采用则 303 回 `/source?...&err=no_supply`），成功后跳 `/copy?wo=` |
| ③ 写介绍 | `GET /copy?wo=` | 标题/卖点/价格/文案版本/状态/包含/不包含/交付/售后/FAQ 表单；保存走 `POST /worksheet/<id>/copy/save`（CSRF+revision）→ 名称变更走既有 `update`，其余走既有证据接口，**自动生成不可变文案版本**；右侧显示七项就绪摘要+阻断项、导出区（未就绪禁用并给原因，就绪给导出链接与「记录本次导出」）、最近 5 条版本 |

- 向导条：当前步 `aria-current="step"` 高亮，已完成步可点（带 `wo` 参数），未到步灰显；`/pick` 链接保留筛选参数。
- 缺 `wo`：`/source`、`/copy` 返回 **400** 并提示“还没有选定商品，请先去选品/找货源”；`wo` 不存在 → **404**。
- 导航：`NAV` 顶部新增「选品向导」入口；旧「商品工作单」保持原样。

## 2. 复用与边界

- `/pick` 直接复用现有数据链：`filter_opportunities` + `build_analysis` + `build_categories` + `build_text_index`，**没有重造查询**；建单复用 `POST /worksheet/new`（采集来源按既有 `validate_source` 规则校验，自制仍走 `/worksheet/new`）。
- `/source` 的候选/采用/自检复用 B16 路由；`/copy` 保存复用 `readiness.save_evidence` 与 `workflow.update`。
- **未新增写权限语义**：所有 POST 仍 `require_local_write()`（CSRF 字节比较 + scheme/netloc 同源）+ revision 乐观锁；未就绪仍无法导出。
- 旧页面未改动渲染逻辑，新增页面只在 B20 分支。

## 3. 测试（真实 subprocess，`execution_manifest.json`）

| suite | rc | summary |
| --- | --- | --- |
| `b20_wizard` | **0** | `Ran 10 tests — OK` |
| `workbench_all` | **0** | `Ran 160 tests — OK` |
| `project_full` | **0** | `Ran 334 tests — OK`（48.1s） |

B20 十例：向导条渲染与当前步、筛选状态保留、无效参数提示、`/source`/`/copy` 缺 wo 400 与无效 wo 404、找货源摘要与“未采用不可确定”、采用后可确定并跳 `/copy`、写介绍保存生成版本且未就绪导出 409、就绪后导出链接与 200、旧路由仍可用。

## 4. 截图（隔离库，示例单 `wo:20261024-77a1fa23`，未就绪状态）

| 文件 | 尺寸 | bytes |
| --- | --- | --- |
| `shots/pick_desktop.png` | 1440×900 | 102,769 |
| `shots/source_desktop.png` | 1440×900 | 93,810 |
| `shots/copy_desktop.png` | 1440×900 | 88,139 |
| `shots/copy_mobile.jpg` | 390×844 | 40,682 |

截图脚本 `shot_wizard.py`：隔离库建单 → 新增并采用一条候选 → 执行 b7 样品自检 → 逐页截图；`shots_manifest.json` 记录尺寸/字节/sha256。

## 5. 部署与守卫

- 只停本工具 5015 进程后同端口重启：**PID 119132**；`/pick`、`/source?wo=wo:20261023-88ef9a66`、`/copy?wo=…` 均 **200** 且含向导条；`/opportunities`、`/worksheet` 仍 200（不做向导条）；`/healthz` 仍 `app_id=workbench-opportunity/1`；5024 已停。
- 守卫未变：`instance/app.db e073f828…`、`CONTRACT.md 826c24cc…`、`scores.csv ab0c3546…`、`sources.csv 13679b60…`；未改评分/货源 CSV、未登录/采购/发布。

## 6. 改动摘要（diff）

- 新增 `views_wizard.py`：`wizard_bar()`、`render_pick()`、`render_source()`、`render_copy()`（共用既有 CSS 类，新增 `.wizard/.wiz-step` 少量样式）。
- `app.py`：新增 `GET /pick`、`GET /source`、`POST /worksheet/<id>/source/confirm`、`GET /copy`、`POST /worksheet/<id>/copy/save`；`NAV` 增「选品向导」。
- `static/app.css`：追加向导条样式（3 行媒体查询，移动端收窄）。
- `tests/test_wizard.py`：10 例。

## 7. 限制

1. `/pick` 的「选这个」用**该类型代表条目**预填名称/用途/交付物（代表条目取首个成员），不是逐条精确规格——建单后仍可在 `/worksheet/<id>/edit` 调整。
2. `/copy` 保存时若改了「标题（名称）」，会先走 `workflow.update`（revision+1）再走证据保存（revision+1），因此**一次保存可能消耗 2 个 revision**；这是为不越权改规格字段（证据接口不接受 `name`）。
3. 向导条只在三步页面出现；旧页面不显示（避免改动既有测试与既有布局）。
4. 「竞争稀疏」按来源许可结论（自用/不明/未知）计数近似，不是真实竞品数量。
5. `/source` 的候选编辑仍是接口级（页面提供新增/采用/停用与导入入口；编辑沿用 B16 的 POST 接口，向导页暂未放编辑表单以保持首屏精简）。
6. 未就绪导出仍 409；生产单仍缺 `platform_evidence`。

---

# rev5 窄修（截图格式对齐 / 补手机选品图 / copy 保存提示）

## 1. 截图扩展名与真实格式一致（重拍，先删旧文件）

- 原因：`nodriver.save_screenshot()` 实际输出 **JPEG**，旧文件却命名为 `.png`。
- 处理：重跑前清空 `shots/`（确认 `SHOTS_LEFT=0`），统一输出 **`.jpg`**；`shots_manifest.json` 全部重写，新增 `format`、`openable`、`check` 字段。
- **校验方式（如实）**：当前 x-collect venv 与项目 `.venv` 均**无 Pillow**，因此改用 **JPEG SOI/EOI 头尾字节校验**（`FF D8 FF` 开头、`FF D9` 结尾）判定可打开，全部 5 张 `openable=true`、`format=jpeg`。

| 文件 | 尺寸 | bytes | sha256 前 10 | format / openable |
| --- | --- | --- | --- | --- |
| `shots/pick_desktop.jpg` | 1440×900 | 102,769 | `ae0a051dec` | jpeg / true |
| `shots/source_desktop.jpg` | 1440×900 | 93,737 | `954fa88564` | jpeg / true |
| `shots/copy_desktop.jpg` | 1440×900 | 91,751 | `b7d9925b8d` | jpeg / true |
| `shots/pick_mobile.jpg` | 390×844 | 41,904 | `ed68526a1f` | jpeg / true |
| `shots/copy_mobile.jpg` | 390×844 | 40,682 | `12301d1bc2` | jpeg / true |

共 **5 张**：三步各有桌面证据，选品与写介绍各有手机证据（示例单 `wo:20261024-6c1929ef`，未就绪态）。

## 2. `/copy` 保存按钮旁补提示（不改功能）

- 保存按钮下方新增一行灰色说明：**「改标题（名称）会额外产生一个版本号（一次保存可能 +2 revision）；只改文案字段则 +1。」**
- 线上核对：`/copy?wo=wo:20261023-88ef9a66` 返回 200 且包含该提示。

## 3. 复跑与部署

- 只跑 B20 专项（真实 subprocess → `execution_manifest_b20_only.json`）：`b20_wizard` **rc=0，`Ran 10 tests — OK`**（未重跑原项目全套，按要求）。
- 只停本工具 5015 进程后同端口重启：**PID 99536**；`/copy` 200 且含新提示；`/healthz` 仍 `app_id=workbench-opportunity/1`。
- 守卫未变：`instance/app.db e073f828…`、`CONTRACT.md 826c24cc…`、`scores.csv ab0c3546…`、`sources.csv 13679b60…`。

---

# rev8 修选品页数据与准入（不重做向导）

## 1. 准入：只列商品型且非待人工

- `/pick` 现在用 `taxonomy.CONTENT_NAMES` 过滤**内容型**（教程 / 资源推荐清单 / 教学变现），并统计 `hidden_content_groups`；页脚一句「内容型（教程 / 资源推荐清单 / 教学变现）不在本页，请到「教程与内容」页查看」。
- `taxonomy.FALLBACK_NAME`（未归类（待人工））与「Notion 其它（待人工）」保留在列表里，但**不渲染「选这个」按钮**，改灰色说明「需先人工确认品类（不会建单）」+ 行首 `待人工确认` 徽章。

## 2. 两列改为真实可解释值（不再用 `—` / `0` 冒充）

| 列 | 之前 | 现在 |
| --- | --- | --- |
| 可售性 | 整列 `—` | 组内 `sellability_norm` **算术平均**（2 位）；无任何值 → **「未评估」**；单元格 `title` 标 `n=k 条有该字段的样本` |
| 竞争稀疏 | 整列 `0` | **统一「未评估」**，单元格与表头都带 `title`：「无竞品数量数据：未做平台搜索，无法计算稀疏度；不以 0 冒充」 |

## 3. 表头下方加口径说明

新增一行 `hint dim`：**数据快照：`data.generated_at`（无则“未知”）· 样本量：商品型 N 组 / 共 M 条 · 均值算法：组内 sellability_norm 算术平均（仅统计有该字段的条目，无值显示“未评估”） · 竞争稀疏：暂无可靠竞品数据，统一显示“未评估”**。

## 4. 截图重拍与测试

- 删除 `pick_desktop.jpg`、`pick_mobile.jpg` 后重拍（脚本一次生成 5 张，manifest 全量同步，其它三张内容未变）。
- `pick_desktop.jpg` 1440×900 / 118,431 B / `99b5765ee9…`、`pick_mobile.jpg` 390×844 / 49,883 B / `7a26b44992…`（均 `format=jpeg`、`openable=true`）。
- 测试增补 3 条：内容型不出现在行内（页脚另有指向）、待人工行无「选这个」且有灰字、可售性/稀疏「未评估」+ 口径说明行存在。
- 仅重跑 B20 专项（`execution_manifest_b20_only.json`）：**rc=0，`Ran 13 tests — OK`**（10 → 13）。
- 部署：只停本工具 5015 进程后同端口重启 **PID 99808**；`/pick` 200，页面含「数据快照/样本量/均值算法」「未评估」19 处、「不以 0 冒充」「教程与内容」「需先人工确认品类」。

---

# rev10 修两列取值（不动准入与布局）

## 1. 可售性 → 优先组级真实值

- `/pick` 取 `g["sellability_mean"]`（`groups.py` / `taxonomy.build_categories` 已产出，`categories.json` 与 `groups.json` 均有该字段）；
- 仅当组级值为 `None` 时才回退为组内 `sellability_norm` 算术均值；两者都无 → 「未评估」。
- 单元格格式 **`0.44（n=14）`**，`title` 写「组内 sellability_norm 均值，n=N 条有该字段的样本」。

## 2. 竞争稀疏 → 组内 `competition_norm` 均值

- 数据来自每条 `scores.csv` 行的 `competition_norm`（0–1，**越高越少竞争**），取组内算术均值（4 位后显示 2 位）；无值组才写「未评估」。
- 单元格 `0.62（n=14）`，`title` 写「组内 competition_norm 均值，n=N 条；**1=竞争者最少**」；表头 `title` 同步。
- **不再出现整列 0，也不再是整列「未评估」**（线上实测 16 个数值单元格）。

## 3. 口径行与测试

- 口径行改为实际算法：「可售性：优先组级 `sellability_mean`，缺则组内 `sellability_norm` 均值（两位小数，括号内为样本数） · 竞争稀疏：组内 `competition_norm` 均值（0–1，1=竞争者最少；不是平台竞品数量）」。
- 新增两例：`test_pick_sellability_numeric`（至少一个单元格匹配 `\d\.\d{2}（n=\d+）`、∈[0,1]，且与 `build_categories` 的 `sellability_mean` 差 ≤0.01）、`test_pick_competition_numeric`（≥3 行数值、∈[0,1]、非整列 0、表头含「1=竞争者最少」）。
- 仅跑 B20 专项：**rc=0，`Ran 15 tests — OK`**（13 → 15）。

## 4. 截图与部署

- 重拍 `pick_desktop.jpg` 1440×900 / 124,002 B / `080180b9e4…`、`pick_mobile.jpg` 390×844 / 51,236 B / `cb0e7f9913…`（`.jpg`、`format=jpeg`、`openable=true`），manifest 同步。
- 只停本工具 5015 进程后同端口重启：**PID 96340**；线上 `/pick` 200，数值单元格 **16 个**、`1=竞争者最少`、口径行含 `competition_norm 均值` 与 `sellability_mean`；守卫四哈希未变。

---

# rev13 修可售性计数语义（n 不得为 0）

## 1. 根因

可售性的**值**取自组级 `g["sellability_mean"]`（正确），但 **n** 取自 `analyses[m]["sellability_norm"]` —— `build_analysis()` 的输出里**没有这个键**，于是恒为 0，出现「0.44（n=0）」。取值与计数走了两条链路。

## 2. 修复（只改计数）

| 路径 | 值 | n |
| --- | --- | --- |
| 组级均值存在（`sellability_mean`） | 组级值 | **`len(members)`**，与左侧「条数」完全一致 |
| 组级缺失 → 回退 | 组内 `sellability_norm` 均值（来源改为 `row_index[m]`，即 `scores.csv` 列） | `len(sell_vals)`（带该字段的成员数） |
| 两者皆无 | 「未评估」 | — |
| 防御 | 万一“有值但 n=0” → 渲染 `0.44（组均值）`，**不写 n** | — |

## 3. 测试与验证

- 新增 `test_pick_sellability_n_never_zero_and_same_scale`：逐行解析「条数」与 `（n=X）`，断言 `X ≥ 1`、`X ≤ 条数`、`X ≥ max(1, 条数//2)`。
- B20 专项：**rc=0，`Ran 16 tests — OK`**（15 → 16）。
- 线上实测：`（n=0）` 出现次数 **0**；带 n 的可售性单元格 **8 个**、竞争单元格 **8 个**。
- 截图重拍：`pick_desktop.jpg` 1440×900 / 123,493 B / `9bd231d3b5…`、`pick_mobile.jpg` 390×844 / 51,236 B / `cb0e7f9913…`（`.jpg`、`format=jpeg`、`openable=true`；手机视口首屏在表单区，数值表格在下方，故手机图与上版像素一致，桌面图可见计数变化）。
- 部署：只停本工具 5015 进程后同端口重启 **PID 114536**；`/pick` 200、`/healthz` 含 `app_id`；守卫四哈希未变。
