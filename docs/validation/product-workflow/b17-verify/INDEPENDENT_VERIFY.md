# B17-B 独立核验：B16 货源候选 / 样品自检

> 任务：`task-bbcf055b38b7bdfc32ea211291293755`（计划 v7，独立核验；只写 b17-verify，不改代码/数据）。
> 结论：**安全路由/路径/基础语义 PASS；选中候选被修改/停用后的绑定语义 FAIL**。另记录旧 B1 文案与新七项并存、samplecheck 结构限制；W1 懒初始化经临时副本验证可用。

## 0. 总体判定

| 项 | 判定 | 说明 |
| --- | --- | --- |
| 六路由 CSRF/同源/白名单 | **PASS** | 全部 `require_local_write`；伪造/跨站 403；未知字段不写状态 |
| 路径逃逸/文件安全 | **PASS** | 7 类拒绝均 400；工作区内绝对路径通过；样品 sha 不变 |
| 初始采用/替换/事件 | **PASS** | supply_select / supply_replace 事件，旧导出因 supply/version 变化失效 |
| 选中候选修改/停用绑定 | **FAIL** | 修改许可/来源/价格、停用已选 A 后，workorder 旧许可仍 yes、readiness 7/7、旧 export valid=true、GET 200 |
| 换候选后的旧样品/成本 | **FAIL/限制** | 换 B 后 sample_ref/cost 原样保留且 readiness 仍 7/7；旧证据未按新候选重验 |
| 旧 B1 文案并存 | **WARN** | 生产页同时出现“四门槛未核验/未验货/B2–B5 待实现”和七项就绪区；来源快照旧文案未随当前状态更新 |
| W1 生产 candidate 表 | **PASS（懒初始化）** | 生产库无表；临时副本首次 HTTP add 303 并建表；生产库 sha 未变 |
| samplecheck 范围 | **受限 PASS** | PDF 只验头部；xlsx 只结构计数，不渲染/不等内容质量/授权 |

**硬缺陷 D2/D3 见 §3；可复现步骤在 `binding_probe.json`。**

## 1. routes（源码审查）

| 路由 | 行号 | require_local_write | 行为 |
| --- | --- | --- | --- |
| POST `/supply/candidates` | `app.py:1055-1064` | 是 | `sup.add()` 新增 + `supply_candidate_add` |
| POST `/supply/candidates/<cid>` | `app.py:1066-1075` | 是 | `sup.update_candidate()` 白名单字段 + 事件 |
| POST `/supply/candidates/<cid>/deactivate` | `app.py:1077-1085` | 是 | `confirm=1` 才软删除 |
| POST `/supply/import` | `app.py:1087-1100` | 是 | JSON 数组；未知字段忽略并报告 |
| POST `/supply/select` | `app.py:1102-1111` | 是 | `select_candidate(revision)` 写 selected/version/license/supply_note |
| POST `/sample/check` | `app.py:1113-1134` | 是 | `check_and_apply`；失败 400 不改状态 |
| GET `/worksheet/<id>` | `app.py:938-950` | 只读 | `connect_ro`；渲染 supply/sample 两区块 |
| 本地保护 | `app.py:863-880` | — | CSRF + Origin/Referer scheme+netloc |

- 表 `workflow.py:181-199`；`supply_note` 列 `workflow.py:255`；视图 `views_worksheet.py:69/128`。
- 采用 `supply.py:199-238` 写 selected/version/三项许可/supply_note，并 `supply_select` / `supply_replace`；自检 `samplecheck.py:156-191` 仅在通过后 UPDATE sample_status/ref。

## 2. path-safety（真实 HTTP，隔离库）

| 输入 | 响应 | 结论 |
| --- | --- | --- |
| `../etc/passwd` | 400 | 逃逸拒绝 |
| `D:\桌面\two\instance\app.db` | 400 | 工作区外绝对路径拒绝 |
| `docs/../instance/app.db` | 400 | resolve 后落 instance，拒绝 |
| `.../b7/00_build.log` | 400 | 扩展名白名单拒绝 |
| `docs/not-exists.xlsx` | 400 | 不存在拒绝 |
| `C:\Windows\win.ini` | 400 | 工作区外拒绝 |
| 21MB `b17-verify/tmp/oversize.xlsx` | 400 | >20MB 拒绝 |
| 绝对路径 b7 样品 | `check_path.ok=true`，7 checks | 工作区内绝对路径允许 |

- 失败后 sample_status/sample_ref/revision 不变；b7 样品 sha `ed3c4efa44607d67127595448c2ee0fcb30171a19cce99d933732015f1e3adad` 前后一致。
- `.xlsx` 只读检查（openpyxl/stdlib 兜底），检测 VBA/外部链接；**不执行宏/脚本**。未实测恶意宏样本。

## 3. 选中候选绑定（隔离库实测）

### 基线

- 新建工作单；候选 A（许可 yes）采用；b7 样品自检 verified；cost_minor=500、cost_known=yes、synthetic `demo://b17/...` 平台证据、copy final；readiness **7/7**；POST export/record 200（`dedup=false`），导出 id=1。
- 控制组：修改**未选**候选 C（commercial no、price 111）→ workorder 快照/readiness/旧 export 有效性**完全不变**；PASS。

### (a) 修改已选 A：许可 yes→no，来源 A→A-v2，价格 100→222

- 候选 A 表：`commercial=no`、`source_url=self:A-v2`、`price_minor=222`。
- workorder：`selected_supply_id=A`、`supply_version` 不变、三项许可仍 **yes/yes/yes**、`supply_note` 仍 `A self:A`。
- readiness：**7/7 全 true**；旧 export `valid=true`；GET export **200**。
- **D2（FAIL）**：已选候选许可/来源/价格变化没有传导到 workorder，未使旧导出失效；仍可导出/记录。根因：`supply.py:125-142` 只更新候选表；`readiness.py:59-80` 读 workorder 副本；`readiness.py:445-455` validity 不含候选许可/价格/source。

### (b) 停用已选 A（confirm=1）

- 候选 A：`is_active=0`；workorder 仍 `selected_supply_id=A`、许可 yes、样品/cost 不变。
- readiness **7/7**；旧 export `valid=true`；GET export **200**。
- **D3（FAIL）**：`readiness` 仅检查 selected_supply_id 非空，不检查候选 active；导出有效性也不含 is_active。已停用候选仍被视为有效绑定。

### (c) 用候选 B 替换 A

- B（yes）select 303：workorder `selected_supply_id=B`、`supply_note=B self:B`、revision 5，旧 export `valid=false`（changed 含工作单版本/货源），GET 仍 200（新内容）。
- workorder `sample_ref` 仍为 A 时的 b7 样品；`cost_minor=500` 不变；readiness **7/7**。
- **D4（FAIL/限制）**：换货源后旧样品/成本被直接沿用，没有标记“需按 B 重验”；`sample_cost_preserved=true`。旧导出虽因 supply 变化失效，但新导出的证据仍来自 A/旧证据。
- **D5（WARN）**：`supply.update_candidate` 不检查 `is_active`，已停用 A 仍可编辑；不会重新激活或绕过 select，但语义偏松。

### 复现

按 `binding_probe.py` 顺序：建单→add A/C→select A→sample b7→evidence→export record→改 C（控制）→改 A→停用 A→add/select B。结果在 `binding_probe.json`。

## 4. 旧 B1 文案与七项就绪并存（实际生产页）

`state_text_check.json` 对 5015 生产单 `wo:20261023-88ef9a66` 的只读 GET：

- 同时存在：`四门槛均未核验`、`未选定货源（selected_supply_id 为空）`、`未验货（B2 待实现）`、`未准备文案与素材（B3 待实现）`、`未人工复核（B4 待实现）`、`未生成上架包（B5 待实现）`；以及 **“上架准备检查（服务端判定）”**、货源候选、样品自检。
- 来源：`workflow.py:288-307` `derive_gaps()` 的旧固定文案，`:310-315` `stages_state()` 仍把 B2–B5 标 pending；它们描述的是**来源快照/旧阶段模型**，而七项 readiness 是当前检查。生产单实际 `selected_supply_id=self:c3-v1`，旧文案仍说“未选定货源”，属状态/文案不一致。
- **WARN（中）**：用户会误读为 B2–B5 全未实现；不能把新七项就绪区当成全流程已完成，也不能用旧文案否定新能力。

## 5. W1 懒初始化（临时副本，生产不 POST）

- 生产 `runtime/workflow.sqlite3` 只读快照到系统临时副本；副本初始无 `workorder_supply_candidate`。
- 在**副本**上 GET 详情 200（货源候选区块存在）；首次 POST `/supply/candidates` → **303**，表创建且 candidate_count=1。
- 生产库 sha 前后均 `8ae79c58…`，未 POST 生产。
- 结论：**懒初始化可用**，W1 从“功能缺陷”降为**部署提醒**：生产需首次写或迁移后才有候选表；在首次写前，生产候选列表为空但页面不报错。

## 6. samplecheck 结构范围

- `samplecheck.py:151-153` PDF 只验前 8 字节 `%PDF-`，不解析内容/签名/页数。
- `samplecheck.py:90-99` xlsx 只读统计 sheet/非空/公式/外部链接；`公式` 项固定 `ok=True`（0 公式也通过）；不计算、不渲染、不验证公式正确性。
- `samplecheck.py:170-184` 通过才写 `sample_status=verified` + `sample_ref`；**verified 仅表示结构检查通过，不是全面验货、授权确认或买家可用性证明**。

## 7. tests

| suite | cwd | UTC | exit | Ran/OK |
| --- | --- | --- | --- | --- |
| b16_supply_sample | tools/workbench | 04:39:45–04:39:49 | 0 | 11 |
| b15_copy_publish | tools/workbench | 04:39:49–04:39:51 | 0 | 10 |
| b12_selfmade | tools/workbench | 04:39:51–04:39:53 | 0 | 10 |
| b1_workflow | tools/workbench | 04:39:53–04:39:58 | 0 | 27 |
| b3_export | tools/workbench | 04:39:58–04:40:02 | 0 | 24 |
| workbench_all | tools/workbench | 04:40:24–04:40:40 | 0 | 144 |
| project_full | 项目根 | 04:40:40–04:41:32 | 0 | 334 |

- 验收文字称“八套”，仓库只有 **7 个可区分 suite**（b13/b15 共用 `test_copy_publish`）；已按实际 7 个复跑，不伪造第 8 个。
- 日志均含 argv/cwd/UTC/returncode：`logs/*.log`。

## 8. prod-check / hashes

- 5015 `/healthz` 200，`app_id=workbench-opportunity/1`；生产单详情 200：两区块 + candidate form；GET export **409**（平台条件阻断）。
- 生产工作单库 sha `8ae79c58…` 前后一致；未写生产。
- 10 个守卫文件与 B14 基线 all same：`instance/app.db e073f828…`、CONTRACT `826c24cc…`、scores `ab0c3546…`、sources/price_signals、wiring/bilibili_view/importer、migrations 2 文件；wal/shm=false。
- b7 样品 sha `ed3c4efa…` 前后一致；`b17-verify/tmp` 空。

## 9. 缺陷/限制

1. **D2（FAIL）**：修改已选候选的许可/来源/价格，不更新 workorder 副本、不 bump revision、不使旧 export 失效；readiness 仍 7/7、GET 200。
2. **D3（FAIL）**：停用已选候选后 selected_supply_id 仍保留，readiness 仍通过、旧 export valid、GET 200。
3. **D4（FAIL/限制）**：换候选 B 后旧 sample/cost 原样保留，readiness 仍 7/7；旧证据没有标记需按新候选重验。
4. **D1（WARN）**：生产页旧 B1 文案（四门槛/未选定货源/B2–B5 待实现）与新七项就绪区并存；旧文案是来源快照，不是当前状态。
5. **W1（部署提醒）**：生产库无 candidate 表；临时副本首次 HTTP add 可懒初始化，生产未迁移时列表为空。
6. **D5（WARN）**：已停用候选仍可被 update_candidate 编辑；未知字段被忽略而非 400。
7. 未做恶意宏样本、并发/多进程、浏览器截图；samplecheck 的 verified 不代表全面验货/授权。

## 10. 证据

- [binding_probe.json](binding_probe.json)、[binding_probe.py](binding_probe.py)、[logs/binding_probe.log](logs/binding_probe.log)
- [w1_lazy_init.json](w1_lazy_init.json)、[w1_probe.py](w1_probe.py)、[logs/w1_probe.log](logs/w1_probe.log)
- [state_text_check.json](state_text_check.json)
- [probe.json](probe.json)、[production_before.json](production_before.json)、[production_check.json](production_check.json)
- [guard_hashes.json](guard_hashes.json)、[guard_compare.json](guard_compare.json)
- 七套日志：`logs/{b16_supply_sample,b15_copy_publish,b12_selfmade,b1_workflow,b3_export,workbench_all,project_full}.log`
