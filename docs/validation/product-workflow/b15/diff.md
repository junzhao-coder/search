# B15 改动摘要（diff）

## `workflow.py`

1. `_ensure_export_columns()` 末尾改为调用新函数 `_ensure_export_unique(conn)`（增量列逻辑不变：`dedupe_key`、`publish_version`、`workorder_publish.publish_version`，均 `PRAGMA table_info` 守卫）。
2. 新增 `_ensure_export_unique(conn)`：
   - 回填 `dedupe_key IS NULL` 的旧行（`revision|copy_version|supply_id|supply_version`）；
   - 历史重复分组：保留 `MAX(id)`，其余 `dedupe_key` 置 `NULL`（**保留行，不删数据**）；
   - `DROP INDEX IF EXISTS idx_export_dedupe`；`CREATE UNIQUE INDEX IF NOT EXISTS idx_export_dedupe_unique ON workorder_export (workorder_id, dedupe_key)`；
   - `conn.commit()`（可重复执行）。
3. `init_schema()` 仍只做 `CREATE TABLE IF NOT EXISTS` + 上述守卫；**未新增/重建表、未删列**。

## `readiness.py`

- `record_export()`：INSERT 包在 `try/except` 中；捕获 `IntegrityError`/UNIQUE 冲突 → `rollback()` → 回查同 `dedupe_key` 行 → 返回 `{"deduplicated": True, "export_id": …, "created_utc": …}`；若回查不到则原样抛出。
- 其余（`dedupe_key` 计算、先查后插、`publish_version` 记录）保持 B13 语义，未弱化“同戳不新增”。

## `tests/test_copy_publish.py`

- 新增 `test_export_dedupe_unique_index_and_concurrency`：两连接并发写同戳 → 最终 1 行、至少一方 `deduplicated=true`、唯一索引存在、旧非唯一索引已删除。
- 新增 `test_unique_index_allows_multiple_nulls`：两行 `dedupe_key IS NULL` 可共存（SQLite 唯一索引对 NULL 不冲突）。

## 迁移脚本（证据目录，非产品代码）

- `b15/migrate.py`：备份 → 调 `init_schema` 两次 → 记录 before/after sha 与行数/索引 → 真实路由验证两区块与导出零写 → `migration.json`。
- `b15/run_suites.py`：六套 subprocess 留痕；`b15/shot_b15.py`：生产页截图 + 隔离库 dedup 实测（`walkthrough.json`）。
