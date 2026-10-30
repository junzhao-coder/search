# B13 改动摘要（diff）

## `workflow.py`

1. `init_schema` 新增两张表（`CREATE TABLE IF NOT EXISTS`，不改既有列）：
   - `workorder_copy_version(id, workorder_id, version_no, snapshot_json, content_hash, created_at, created_by, UNIQUE(workorder_id, version_no))`
   - `workorder_publish(workorder_id PK, status, published_url, published_at, platform_note, sold_count, publish_version, updated_at)`
2. 新增 `_ensure_export_columns()`：为 `workorder_export` 增量加 `dedupe_key`、`publish_version`（`PRAGMA table_info` 守卫），并建 `idx_export_dedupe(workorder_id, dedupe_key)` 非唯一索引；同时为 `workorder_publish` 补 `publish_version`（兼容旧库）。
3. `create(..., self_made=...)`（B12 已加）保持不变；单号仍 `wo:yyyymmdd-8hex`。

## `readiness.py`

- 新增 `COPY_FIELDS`、`copy_snapshot()`、`copy_hash()`、`list_copy_versions()`、`_insert_version()`（同 hash 不新增）。
- `save_evidence()`：UPDATE 后在同一事务内调用 `_insert_version(created_by='ui')`，新增版本时写 `copy_version` 审计事件。
- 新增 `rollback_copy(conn, wid, version_no, revision)`：`BEGIN IMMEDIATE` + `rowcount==1` 校验 → 回写旧快照 → 生成新版本（`created_by='rollback:vN'`）→ 审计。
- `record_export()`：计算 `dedupe_key`，命中则返回既有记录 + `deduplicated=True`；未命中插入并记录 `publish_version`。
- 新增 `PUBLISH_STATUS`、`publish_info()`、`save_publish()`（状态枚举/URL 协议+域名/销量非负整数/备注长度校验；`ON CONFLICT` 时 `publish_version+1`）、`publish_changed()`（比较 `publish_version` 与导出记录中的值）。

## `app.py`

- 详情路由：读取 `list_copy_versions` / `publish_info`（只读连接），计算 `publish_changed`，追加渲染 `render_copy_history()` 与 `render_publish()`。
- 新增 `POST /worksheet/<id>/copy/rollback`、`POST /worksheet/<id>/publish`（均 `require_local_write()`）。
- `_export_response(..., deduplicated=...)` 新增 `X-WB-Deduplicated` 头；`/export/record` 透传 `info["deduplicated"]`。

## `views_worksheet.py`

- 新增 `render_copy_history()`：版本表（版本号/时间/来源/摘要+hash/回滚按钮）与空态说明。
- 新增 `render_publish()`：状态徽章、链接/时间/销量、变更横幅（`notice notice-warn`）、回填表单（状态枚举 + URL + 时间 + 销量 + 备注）。

## `tests/`

- 新增 `tests/test_copy_publish.py`（8 例）。
- `tests/test_export.py`：`test_post_record_requires_csrf_and_writes_one_row` 的后半段由「重复记录再 +1 行」改为「同戳幂等（`X-WB-Deduplicated: true`，行数不变）+ 改 `copy_version` 后新增 1 行」。
