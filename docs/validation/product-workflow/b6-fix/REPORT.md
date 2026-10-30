# B6-fix D1：GET 导出写库缺陷修复

## 1. 缺陷与根因

- 现象（B6 核验）：`GET /worksheet/<id>/export` 就绪导出后 `workorder_export` 行数 **0→1**，库文件 sha 变化 —— 违反「GET 零写」，且外部链接（如 IM 里贴的 URL）被点开即触发写库。
- 根因：`app.py` 的 GET 导出用 `wf.connect()`（读写连接），并调用 `readiness.record_export()` 执行 `INSERT … commit`。

## 2. 修复方案（采用方案①：GET 只生成、POST 才记录）

| 位置 | 改动 |
| --- | --- |
| `GET /worksheet/<id>/export?format=md\|json` | 改用 **`wf.connect_ro()`**（库不存在返回 None），只调用纯函数 `build_export()` / `version_stamp()`；**不调用 `record_export`**；响应头新增 `X-WB-Recorded: false` |
| `POST /worksheet/<id>/export/record`（新增） | `require_local_write()`（CSRF + 同源 scheme/netloc）→ 就绪检查（未就绪 **409**）→ `record_export()` 写 1 行 → 返回同一份导出内容，响应头 `X-WB-Recorded: true` |
| `_export_response()`（新增 helper） | 统一生成 md/json 响应与 `Content-Disposition`、`X-WB-Revision/Stamp/Copy-Version/Supply`，避免两条路由重复代码 |
| `views_worksheet.render_readiness()` | 就绪态在导出链接旁新增 **「记录本次导出」** 表单（`csrf` + 格式下拉 md/json，`button` 提交），并注明「GET 导出仅生成内容、不写库；点此才写入导出记录」 |
| `readiness.record_export()` | **未改动**（仍由显式动作调用）；`build_export` / 就绪判定 / 买家字段白名单 **均未放宽** |

**为何选①**：导出记录是审计动作，应由用户显式点击产生；GET 保持纯读，外部链接被点开不会写库。方案②（完全无记录、后续人工补记）会丢失「谁在何时导出过」的可追溯性，故不采用。

## 3. 隔离库实测（`export_probe.json`，端口 5019，临时库/密钥跑完即删）

| 步骤 | 状态 | `workorder_export` 行数 | 库 sha256 | 头 |
| --- | --- | --- | --- | --- |
| GET 导出（未就绪） | **409** | 0 → 0 | **不变** | — |
| GET 导出（就绪） | **200** | 0 → 0 | **不变** | `X-WB-Recorded: false` |
| POST `export/record` | **200** | **0 → 1** | 改变（预期） | `X-WB-Recorded: true` |

`verdict = {"get_zero_write": true, "d1_fixed": true}`。

## 4. 回归测试（真实 subprocess，`execution_manifest.json`）

| suite | rc | summary |
| --- | --- | --- |
| `b1_workflow` | **0** | `Ran 27 tests — OK` |
| `b3_export` | **0** | `Ran 24 tests — OK` |
| `workbench_all` | **0** | `Ran 113 tests — OK` |
| `project_full` | **0** | `Ran 334 tests — OK`（49.4s） |

新增 `GetExportZeroWriteTests`（4 例）：
1. `test_get_export_ready_does_not_write`：就绪 GET md/json → 200 且 `X-WB-Recorded=false`，**导出行数与库 sha 均不变**；
2. `test_get_export_not_ready_409_does_not_write`：未就绪 GET → 409 且不写；
3. `test_post_record_requires_csrf_and_writes_one_row`：无/错 CSRF → 403 不写；正确 CSRF → 200 且 **+1 行**、`X-WB-Recorded=true`；再次显式记录**按规则再 +1**（不静默覆盖）；
4. `test_post_record_not_ready_409_and_no_write`：未就绪 POST → 409 不写。

**版本戳语义保持**：`test_stamp_invalidates_old_export` 改用 POST 记录后仍验证「改 `copy_version` → 旧戳失效 → 重新记录恢复有效」；就绪判定与导出白名单未改动（B3 原有用例全绿）。

## 5. 部署与守卫

- 只停本工具 5015 进程后同端口重启：**PID 115932**；`/worksheet` 200；`/healthz` 含 `app_id=workbench-opportunity/1`；含新路由 `export/record`；5019 已停。
- 生产库未创建（0 条）；守卫未变：`instance/app.db e073f828…`、`CONTRACT.md 826c24cc…`、`scores.csv ab0c3546…`、`sources.csv 13679b60…`、`importer.py a11eaf4d…`。
- 未改评分/货源原始数据、业务库/CONTRACT/迁移/冻结文件；未新增依赖。

## 6. 限制

1. **每次显式记录都会新增一行**（含同 revision 重复记录），未做去重；若后续要求「同戳只记一次」，可加唯一约束或幂等键（本次未做，避免改动既有表结构语义）。
2. GET 预览**不产生记录**，因此详情页「上次导出」只反映**最近一次显式记录**；未记录前显示“尚未导出过”。
3. 记录动作不校验 `revision`（只校验就绪）：同一 revision 下多次记录属预期；若需要“记录必须匹配当次 revision”，需追加参数（本次未加）。
4. 内部标记自检仍为关键词扫描（成本/利润/打分/毛利等），非语义级 DLP。
