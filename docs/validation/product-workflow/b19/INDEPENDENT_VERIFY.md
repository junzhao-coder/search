# B19-B 独立核验：B18 货源变更传导与数据隔离

> 任务：`task-1860c48015bd9b9948d226dffc43b9f5`（v7 独立核验；只写 b19，不改代码/数据）。
> 结论：**PASS（D2/D3/D4/control/recovery）**；生产预计仍需补 `platform_evidence`；B18 只在 sample/cost 失效，`platform_evidence` 保留，属已知限制 WARN。

## 0. 判定

| 项 | 判定 | 关键证据 |
| --- | --- | --- |
| D2 改已选许可 | **PASS** | 许可同步为 no；sample/cost 清空；readiness 不足 7/7；export 409；旧戳失效；恢复可回 7/7 |
| D3 停用已选 | **PASS** | selected 清空；许可 unknown；sample/cost 清空；readiness 不足；export 409；旧戳失效 |
| D4 换源 | **PASS** | selected B2；sample/cost 清空；readiness sample/cost false；export 409；旧戳失效；重检+重填回 7/7 |
| 控制组（改未选） | **PASS** | 工作单记录逐字段完全不变；readiness 7/7；GET export 200 |
| 旧 B1 区块标注 | **PASS** | 生产页含“来源快照与历史阶段（非当前状态）”；旧文案被明确标为历史，不再与当前就绪混淆 |
| 八套测试 | **PASS** | 6/11/10/10/27/24/150/334，全 rc=0 |
| 生产只读 | **PASS** | `/healthz` 200；两区块；export 409；生产库 sha 前后一致 |
| 守卫哈希 | **PASS** | 10/10 same；wal/shm=false |

## 1. 源码审查（B18）

| 对象 | 行号 | 结论 |
| --- | --- | --- |
| `_invalidate_sample_cost` | `supply.py:125-128` | 清 sample_status/ref、cost_known=no、cost_minor=NULL；**不清 platform_evidence**（限制） |
| `_sync_selected` | `supply.py:131-142` | 更新 supply_version/三项许可/note、revision+1，调用 invalidate |
| `update_candidate` 传导 | `supply.py:145-175` | 已选候选更新后调用 `_sync_selected`（同事务）；未选不调用 |
| `deactivate` 传导 | `supply.py:178-207` | 已选停用：selected=NULL、许可 unknown、sample/cost 清空、revision+1；未选只软删 |
| `select_candidate` 换源 | `supply.py:248-289` | old 且不同 → invalidate sample/cost；更新 selected/version/license/note，revision+1 |
| readiness | `readiness.py:59-80` | supply 只看 selected_supply_id 非空；license 读 workorder 副本；sample/cost 读字段 |
| 旧区块标题 | `views_worksheet.py:253-276` | “来源快照与历史阶段（非当前状态）”，明确不代表当前状态 |
| 六路由 | `app.py:1055-1134` | 全部 `require_local_write`（CSRF+同源）；GET detail 只读 |

## 2. D2/D3/D4/控制/恢复（隔离库）

基线：采用 A、b7 样品自检、证据补齐（cost 500/copy/synthetic `demo://b19/...`）→ 7/7；POST export/record 200，id=1，valid=true。

### 控制组（先做）

- 修改未选 B：`resale=no`；停用 B confirm=1。
- `before_control == after_control` **true（逐字段）**；readiness 7/7；旧 export valid=true；GET export 200。PASS。

### D2：已选 A 许可 yes→no

- 更新 303；workorder：`supply_license_resell=no`，sample_status/ref=NULL，cost_known=no/cost_minor=NULL，revision 5，`supply_note` 仍 A。
- readiness：license/sample/cost **false**，其余 true；blockers 含三项；旧 export `valid=false`（工作单/货源版本变化）；GET export **409**。
- 恢复：A 改回 yes（再次同步清空）→ sample check → evidence cost=500 → readiness **7/7**；GET export **200**。PASS。

### D3：停用已选 A

- 303；workorder：selected=NULL、三项许可 unknown、sample/cost 清空、revision 9；readiness supply/license/sample/cost false；旧 export valid=false；GET export **409**。PASS。
- `supply_note`/`supply_version` 仍保留旧值，但 supply 检查因 selected 空而 false；无导出风险。

### D4：换源到 B2

- B2 全 yes；select 303；workorder selected=B2、revision 10、sample/cost 清空、license yes；readiness sample/cost false（5/7 通过，非 7/7）；旧 export valid=false；GET export **409**。
- 恢复：sample check → evidence cost=500 → readiness **7/7**；GET export **200**。PASS。
- **WARN W4**：`platform_evidence=demo://b19/...` 仍是 A 时的旧值；`_invalidate_sample_cost` 不清 platform，所以恢复 7/7 可沿用旧平台证据。若平台条件与货源相关，需额外清理/重验。

完整前后字段、readiness、validity、GET 状态见 `binding_probe.json`。

## 3. 测试（八套按实际模块）

| suite | cwd | UTC | rc | Ran/OK |
| --- | --- | --- | --- | --- |
| b18_binding | tools/workbench | 05:17:12–05:17:14 | 0 | 6 |
| b16_supply_sample | tools/workbench | 05:17:14–05:17:16 | 0 | 11 |
| b15_copy_publish | tools/workbench | 05:17:16–05:17:19 | 0 | 10 |
| b12_selfmade | tools/workbench | 05:17:19–05:17:21 | 0 | 10 |
| b1_workflow | tools/workbench | 05:17:21–05:17:25 | 0 | 27 |
| b3_export | tools/workbench | 05:17:25–05:17:29 | 0 | 24 |
| workbench_all | tools/workbench | 05:17:38–05:17:54 | 0 | 150 |
| project_full | 项目根 | 05:17:54–05:18:43 | 0 | 334 |

- 与 B18 声称 6/11/150/334（以及 b1/b3/b12/b15）一致；日志含 argv/cwd/UTC/returncode。
- 本次不重跑其他套件；仅上述八套。

## 4. 生产只读核对

- `GET /healthz` 200，`app_id=workbench-opportunity/1`。
- 生产单 `wo:20261023-88ef9a66` 详情 200：包含 **“来源快照与历史阶段（非当前状态）”** 与 **“上架准备检查（服务端判定）”** 两区；旧四门槛/B2–B5 文案仍存在但已明确标为历史，不算当前状态。
- GET export **409**，含平台条件阻断；生产库 sha `8ae79c58…` 前后一致。
- 生产库仍无 `workorder_supply_candidate` 表（懒初始化提醒；B17 副本已验证首次 HTTP add 会建表，未在生产 POST）。
- 生产单 readiness 6/7（`platform_evidence` 空），未上架。

## 5. 守卫哈希

`guard_compare.json`：10 个文件与 B14 基线 **10/10 same**：

- `instance/app.db e073f828…`、CONTRACT `826c24cc…`、scoring `ab0c3546…`、sourcing sources/price_signals、wiring/bilibili_view/importer、migrations 2 文件。
- `wal=false, shm=false`；b7 样品 sha `ed3c4efa…`；生产工作单库 `8ae79c58…` 前后一致。

## 6. 缺陷 / 限制

1. **W4（中）**：`_invalidate_sample_cost` 不清 `platform_evidence`；换源后仅补 sample/cost 可回 7/7，但平台证据仍是旧源。需确认平台条件是否 source-specific。
2. **W1（部署提醒）**：生产库无 candidate 表；首次写懒初始化；非功能失败，但生产列表在首次写前为空。
3. **D5（WARN）**：`update_candidate` 不检查 inactive，已停用候选仍可编辑；不影响 select（active 检查）。
4. 版本历史只含文案；回滚不回写证据；去重键含 revision；发布三档；`published_at` 自由文本；sample 未真实打开。
5. samplecheck PDF 仅头部、xlsx 仅结构计数；`verified` 不代表全面验货/授权/可渲染。
6. 未做恶意宏样本、并发、浏览器截图；生产只读，未 POST。
7. B16 `update_candidate` 未知字段忽略而非 400（弱白名单）。

## 7. 证据

- [binding_probe.json](binding_probe.json)、[binding_probe.py](binding_probe.py)、[logs/binding_probe.log](logs/binding_probe.log)
- [prod_check.json](prod_check.json)、[production_state](../../product-workflow/b17-verify/production_state.json)（生产快照参考）
- [guard_hashes.json](guard_hashes.json)、[guard_compare.json](guard_compare.json)
- 八套日志：`logs/{b18_binding,b16_supply_sample,b15_copy_publish,b12_selfmade,b1_workflow,b3_export,workbench_all,project_full}.log`
- 五阶段/闭环/限制：`CURRENT-STATE.md`
