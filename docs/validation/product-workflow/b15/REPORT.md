# B15：生产库迁移（W1）+ dedupe_key 唯一约束（W2）交付报告

- 范围：`tools/workbench/`、`docs/validation/product-workflow/b15/`；未改业务库/CONTRACT/评分与货源 CSV
- 结论：**W1 已迁移**——生产库创建 `workorder_copy_version` / `workorder_publish` 并补齐 `workorder_export.dedupe_key`、`publish_version`，生产单两区块可见；**W2 已加唯一索引**——`idx_export_dedupe_unique(workorder_id, dedupe_key)`，写入路径捕获 `IntegrityError` 回查既有行返回 `deduplicated=true`；迁移幂等（连跑两次 sha 与行数不变）；六套测试全绿；已部署 5015（PID 122620）。

## 1. 迁移前备份与前后对照

| 项 | 值 |
| --- | --- |
| 备份 | `b15/backup/workflow-20261023T153152Z.sqlite3`（sha `d9349c03faf29df3…` = 迁移前生产库 sha） |
| 迁移前 | sha `d9349c03…`；行数 `workorder=1 / event=2 / export=0` |
| 迁移后（第 1 次） | sha `8ae79c58d8ea5c30…`；表含 `workorder_copy_version`、`workorder_publish`；索引 `idx_export_dedupe_unique(unique=true)` |
| 迁移后（第 2 次） | sha **`8ae79c58d8ea5c30…`（与第 1 次相同）**；行数不变 → **幂等** |
| 迁移后行数 | `workorder=1 / event=2 / export=0 / copy_version=0 / publish=0`（**既有行未变、未清空、未重建表**） |

迁移直接调用 `workflow.init_schema()`（`CREATE TABLE IF NOT EXISTS` + `PRAGMA table_info` 守卫），**没有另写一份 DDL**；重复执行无异常。

## 2. W2：dedupe_key 唯一约束

- 先在 `_ensure_export_unique()` 内：①回填旧行 `dedupe_key`（`revision|copy_version|supply_id|supply_version`）；②历史重复保留最大 `id`，其余置 `NULL`（**保留行不删数据**；SQLite 唯一索引允许多个 NULL）；③`DROP INDEX IF EXISTS idx_export_dedupe`（旧非唯一）后 `CREATE UNIQUE INDEX IF NOT EXISTS idx_export_dedupe_unique`。
- `record_export()`：先查同键 → 命中直接返回 `deduplicated=true`；未命中执行 INSERT；**并发下唯一索引冲突 → 回滚并回查既有行，返回 `deduplicated=true`**（不弱化“同戳不新增”）。
- 实测（隔离库 HTTP，`walkthrough.json`）：首次记录 `X-WB-Deduplicated: false`，第二次 `true`，`workorder_export` **行数=1**，索引仅 `idx_export_dedupe_unique`。
- 并发用例（单测 `test_export_dedupe_unique_index_and_concurrency`）：两个独立连接对同戳各写一次 → **最终 1 行**，至少一方 `deduplicated=true`，唯一索引存在且旧索引已删除；`test_unique_index_allows_multiple_nulls` 验证多 NULL 合法。

## 3. 迁移后验证（真实路由，生产库）

| 检查 | 结果 |
| --- | --- |
| 生产单 `wo:20261023-88ef9a66` 详情 | **200** |
| 页面含「文案版本历史」 | ✅（当前 0 个版本，因该单尚未保存过文案） |
| 页面含「发布回填」 | ✅ |
| `GET /export?format=md` | **409**（`platform_evidence` 仍空，正确阻断） |
| GET 导出前后库 sha | **不变**（零写） |

截图：`shots/prod_copy_history.png` 1160×252、`shots/prod_publish.png` 1160×164（均在生产 5015 页面实拍）。

## 4. 测试（真实 subprocess，`execution_manifest.json`）

| suite | rc | summary |
| --- | --- | --- |
| `b13_copy_publish` | **0** | `Ran 10 tests — OK`（原 8 + 并发唯一约束 2 例） |
| `b12_selfmade` | **0** | `Ran 10 tests — OK` |
| `b1_workflow` | **0** | `Ran 27 tests — OK` |
| `b3_export` | **0** | `Ran 24 tests — OK` |
| `workbench_all` | **0** | `Ran 133 tests — OK` |
| `project_full` | **0** | `Ran 334 tests — OK`（50.4s） |

## 5. 部署与守卫

- 只停本工具 5015 进程后同端口重启：**PID 122620**；生产单详情 200 且两区块可见；`/healthz` 仍 `app_id=workbench-opportunity/1`；5022 已停（测试实例）。
- 守卫未变：`instance/app.db e073f828…`、`CONTRACT.md 826c24cc…`、`scores.csv ab0c3546…`、`sources.csv 13679b60…`；未改评分/货源 CSV、无新依赖。

## 6. 限制与说明

1. **生产库 sha 发生了变化**（`d9349c03…` → `8ae79c58…`），这是迁移本身（建表/加列/加索引）的预期结果；**行数未变**，旧单可用，备份保留在 `b15/backup/`。
2. 迁移把历史重复导出行（若有）的 `dedupe_key` 置 NULL 以保留数据；这些行不参与去重查询，属**历史遗留记录**而非新导出。
3. `workorder_copy_version` / `workorder_publish` 当前为空（生产单尚未保存文案、也尚未回填发布），页面显示空态，不是缺表。
4. 唯一索引对 `dedupe_key IS NULL` 不生效（SQLite 语义），故「同戳不新增」靠“先查 + 唯一索引兜底 + IntegrityError 回查”三重保证。
5. 生产单 `platform_evidence` 仍为空 → 导出仍 409；本次未放宽就绪判定。
