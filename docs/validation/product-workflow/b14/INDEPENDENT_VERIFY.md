# B14 独立核验：B12/B13 只读、回滚、去重与隔离

> 任务：`task-b4ee6810f70b969d02a50b537087ada4`（v7 独立核验；只写 b14，不改代码/生产数据）。
> 结论：**代码与隔离库行为 PASS**；生产库状态 **WARN（B13 两表未初始化）**；去重为应用级、无唯一约束 **WARN（并发未验证）**。未发现 GET 写库或回滚越界。

## 1. 源码审查（文件/行号）

| 对象 | 位置 | 结论 |
| --- | --- | --- |
| `workorder_copy_version` 表 | `workflow.py:161-170` | 版本号唯一 `(workorder_id, version_no)`；快照 JSON + content_hash |
| `workorder_publish` 表 | `workflow.py:171-180` | 单工作单 PK；status/publish_version |
| `workorder_export` 增量 | `workflow.py:188-198` | `dedupe_key`、`publish_version`；仅普通索引，**无唯一约束** |
| copy snapshot | `readiness.py:165-174` | 只含文案 11 字段；不含 supply/license/sample/cost/platform |
| 版本插入 | `readiness.py:197-209` | 与最新 content_hash 相同则不新增；version_no=max+1 |
| evidence 保存 | `readiness.py:260-299` | revision 乐观锁；同事务更新+审计+版本 |
| export 记录 | `readiness.py:303-322` | `dedupe_key = revision|copy_version|supply_id|supply_version`；命中不 INSERT |
| rollback | `readiness.py:325-368` | 只 UPDATE `COPY_FIELDS`；生成新版本；不改证据字段 |
| publish | `readiness.py:383-419` | 状态三档、URL http/https、sold 非负整数、备注≤500 |
| GET `/worksheet/new` | `app.py:964-967` | 只渲染表单，无 DB 连接 |
| POST `/worksheet/new` | `app.py:969-985` | `require_local_write` + 写 |
| POST evidence | `app.py:1008-1026` | `require_local_write` + 写 |
| POST `/copy/rollback` | `app.py:1028-1037` | `require_local_write` + 写 |
| POST `/publish` | `app.py:1039-1048` | `require_local_write` + 写 |
| GET `/export` | `app.py:1050-1075` | `connect_ro` 只读；**GET 零写**（B6 D1 已修） |
| POST `/export/record` | `app.py:1077-1097` | `require_local_write` + 就绪检查 + 写 1 行 |
| 本地写保护 | `app.py:863-880` | CSRF + `Origin/Referer` scheme+netloc 同源 |
| 只读连接 | `workflow.py:92-102` | `mode=ro` URI |

- 未发现绕过 `readiness()` 的 ready 捷径；`normalize_fields`/`normalize_evidence` 拒绝 `ready/verified/gate_*`。
- 回滚只写 `COPY_FIELDS`（`readiness.py:347-352`）；证据五组不在 UPDATE 列。

## 2. 六套测试（独立 subprocess）

| 套件 | 命令/cwd | UTC | exit | 结果 |
| --- | --- | --- | --- | --- |
| b13_copy_publish | `python -m unittest tests.test_copy_publish -v` / tools/workbench | 14:53:15–14:53:17 | **0** | Ran **8** / OK |
| b12_selfmade | `... tests.test_selfmade -v` / tools/workbench | 14:53:17–14:53:19 | **0** | Ran **10** / OK |
| b1_workflow | `... tests.test_workflow -v` / tools/workbench | 14:53:19–14:53:23 | **0** | Ran **27** / OK |
| b3_export | `... tests.test_export -v` / tools/workbench | 14:53:23–14:53:28 | **0** | Ran **24** / OK |
| workbench_all | `... discover -s tests -v` / tools/workbench | 14:53:58–14:54:09 | **0** | Ran **131** / OK |
| project_full | `... discover -s tests -v` / 项目根 | 14:54:09–14:54:59 | **0** | Ran **334** / OK |

- 与 B13 报告声称的 8/10/27/24/131/334 完全一致。
- 证据：`logs/{b13_copy_publish,b12_selfmade,b1_workflow,b3_export,workbench_all,project_full}.log`（含 argv/cwd/UTC/exit）。

## 3. 隔离库闭环实测（`probe.json`）

临时 `WORKBENCH_WORKFLOW_DB`/`WORKBENCH_SECRET_FILE`/`WORKBENCH_SOURCE_FIXTURE`；未动生产库。

| 步骤 | 结果 |
| --- | --- |
| GET `/worksheet/new` | 200；库计数 0→0 |
| 建单 | 303；`wo:20261023-b8065d52` |
| 未就绪 GET export | **409**，含“未选货源”；export 0→0 |
| 录七项证据 | 303；copy_version 1 条；export 0 |
| 就绪 GET export（预览） | **200**；export **0→0**（零写） |
| POST export/record 第 1 次 | 200；`X-WB-Deduplicated: false`；export **0→1** |
| 第 2 次同戳 | 200；`X-WB-Deduplicated: true`；export **1→1** |
| 改文案 `copy_version=copy-v2` + selling_points | 303；版本 **[2,1]**；旧戳 `valid=false`，changed 含工作单/文案版本 |
| POST record 新戳 | 200；`false`；export **1→2**；dedupe_key `3|copy-v2|sup-mit-1|v1` |
| 回滚 v1 | 303；版本 **[3,2,1]**；最新 `rollback:v1` |
| 回滚五组字段 | **10/10 不变**：selected_supply_id/supply_version/三项许可/sample_status/sample_ref/cost_minor/cost_known/platform_evidence |
| 回滚文案字段 | selling_points 变化；快照 keys 仅 11 个文案字段，无证据字段 |
| 发布非法 | 状态“已上架”、ftp URL、sold=-1、sold=1.5 → **400/400/400/400** |
| 发布合法 | 303；publish_version=1；发布变更提示 changed=true |
| 伪造 ready/verified/gate_cost/status | **403**；库值不变 |
| 无 CSRF / 外站 / 跨协议 | **403 / 403 / 403** |
| revision=abc/1.5/-1 | **400/400/400** |

- 终态：workorder 1、event 7、export 2、copy_version 3、publish 1。
- `record_export` 去重按 `(revision, copy_version, supply_id, supply_version)`；同戳行数不变，改文案后新 revision 生成新行。
- **注意**：`copy_version` 单独变化不会生成新文案版本（快照不含 copy_version），但会使旧导出戳失效；版本需改 `selling_points` 等快照字段才新增。这是“版本只含文案字段”的语义结果，不是篡改。

## 4. 生产库与 B12 备份

- 生产 `tools/workbench/runtime/workflow.sqlite3`：sha **d9349c03…**；只读查询 workorder=1、event=2、export=0；id `wo:20261023-88ef9a66`。
- **WARN W1**：生产库 **没有** `workorder_copy_version` / `workorder_publish` 表（`no such table`）。B13 代码读取时 catch 为空，用户可打开详情，但生产单暂无版本历史/发布回填；需一次写操作触发 `init_schema` 或显式迁移后才算生产闭环。
- B12 backup：`b12/backup/workflow-20261023T140036Z.sqlite3` 存在，sha `0914b137…` 与 `id_mapping.backup_sha256` **一致**；mapping old `wo:c3-prod-20261023` → new `wo:20261023-88ef9a66`；生产列表含 new、不含 old（`production_state.json`/`b12_backup_check.json`）。

## 5. 守卫哈希 / 隔离

- `instance/app.db` `e073f828…`、CONTRACT `826c24cc…`、wiring/bilibili_view/importer、scores `ab0c3546…`、sources/price_signals、migrations 2 文件：共 **10/10 same**；wal/shm=false（`guard_hashes.json`/`guard_compare.json`）。
- 生产工作单库 before/after sha 均 `d9349c03…`；B14 只读打开/查询，未改。
- B14 临时库/密钥在系统临时目录；`b14/tmp` 为空；未登录平台、未采购、未发布。

## 6. 缺陷/警告清单

1. **W1（生产状态，WARN）**：生产工作单库没有 B13 两表；代码可回退读取为空，但生产版本历史/发布回填尚未可用。B13 “已部署 5015”只能确认代码，不确认生产数据层已初始化。
2. **W2（并发，WARN）**：`record_export` 去重是应用层 `SELECT` + INSERT；`dedupe_key` 只有普通索引，无 UNIQUE 约束；串行重复已验证不增行，但并发同戳可能产生重复行。未做并发压力测试。
3. **非缺陷但需知**：`copy_version` 单独变化不新增文案版本（快照不含该字段）；回滚不回写证据；去重键含 revision；发布状态三档；`published_at` 自由文本；sample 未真实打开。均列于 `CURRENT-STATE.md` 的 7 项限制。

## 7. 未覆盖 / 限制

- 用 Flask `test_client` + 隔离临时库；未对生产 5015 做写操作，未做真实浏览器截图。
- 未验证并发导出、多进程去重、真实文件下载、买家文案语义/平台审核。
- 未做生产库 schema 迁移；本任务只核验，不修改。
- `b13` 版本历史快照只含文案字段的行为按设计记录；不视为越界。

## 8. 证据

- [CURRENT-STATE.md](CURRENT-STATE.md)：五阶段/闭环/7 限制/3 待办。
- [probe.json](probe.json)、[probe.py](probe.py)、[logs/probe.log](logs/probe.log)
- [production_state.json](production_state.json)、[b12_backup_check.json](b12_backup_check.json)
- [guard_hashes.json](guard_hashes.json)、[guard_compare.json](guard_compare.json)
- 六套测试日志：`logs/{b13_copy_publish,b12_selfmade,b1_workflow,b3_export,workbench_all,project_full}.log`
