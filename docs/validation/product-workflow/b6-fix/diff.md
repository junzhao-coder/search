# D1 修复改动摘要（diff）

> 仅列改动点与语义，不贴整段补丁；文件均在 `tools/workbench/`。

## `app.py`

1. **`GET /worksheet/<workorder_id>/export`**
   - 连接：`wf.connect()` → **`wf.connect_ro()`**（库不存在时返回 `None`，直接 404，不建文件）；
   - 逻辑：只调用 `rd.readiness()` / `rd.build_export()` / `payload["version_stamp"]`；
   - 删除：`rd.record_export(conn, record, payload, fmt)`（原写入点）；
   - 响应：交给新 helper `_export_response(payload, fmt, stamp, recorded=False)`，头 `X-WB-Recorded: false`。

2. **新增 `POST /worksheet/<workorder_id>/export/record`**
   - `require_local_write()`（CSRF `compare_digest` + Origin/Referer 的 scheme+netloc 校验）；
   - `format` 校验 `md|json`；`rd.readiness()` 未就绪 → `Reject("export_not_ready", …, 409)`；
   - `rd.build_export()` → `rd.record_export()`（写 1 行 `workorder_export`）→ `_export_response(..., recorded=True)`，头 `X-WB-Recorded: true`。

3. **新增 `_export_response(payload, fmt, stamp, *, recorded)`**
   - 统一 `Content-Disposition`、`X-WB-Revision`、`X-WB-Stamp`、`X-WB-Copy-Version`、`X-WB-Supply`、`X-WB-Recorded`；
   - 消除原 GET 路由内的重复渲染代码。

## `views_worksheet.py`

- `render_readiness()` 就绪分支：在两条 GET 导出链接旁新增
  `<form method="post" action="/worksheet/<id>/export/record">`（隐藏 `csrf` + 格式下拉 + `button`「记录本次导出」）；
- 新增一行说明：「GET 导出仅生成内容、**不写库**；点「记录本次导出」才会写入导出记录（版本戳入库，供失效比对）」。

## `tests/test_export.py`

- `test_stamp_invalidates_old_export`：首次/再次「记录」改为 `POST /export/record`（原用 GET）；
- 新增 `GetExportZeroWriteTests`（4 例）：GET 就绪/未就绪零写、POST 需 CSRF 且写 1 行、POST 未就绪 409 不写。

## `readiness.py`

- **未改动**：`record_export()` 仍是唯一写入口（由 POST 调用）；`build_export()` 白名单与内部标记自检（409 `export_internal_leak`）保持不变。
