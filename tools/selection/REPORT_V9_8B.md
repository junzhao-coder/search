# V9-8b 实现报告：/leads 人工贴一条 + native_id 解析 + triage 可见可改判 + 分开计数

> 任务 `task-48f781d178d0897627bc8e341f2674d3`（rev2，计划 v9）；范围 `tools/selection`、`tools/workbench`、`tests`。
> 2026-10-25 22:06–22:12 UTC+8。未装依赖、未登录、未改业务库/工作单库/CSV/CONTRACT；未新增侧栏。

## 1. 表单 / 路由

- `views_leads.py`：`/leads` 页内新增“人工贴一条”区块（platform 下拉 xiaohongshu/douyin/weibo/zhihu/tieba/other；url/title/text）；POST `/leads/manual`（`app.py` 新路由，位于 `/healthz` 前）。
- url 与 text 至少一项必填，缺失 303 + 可读 err；全部走 `require_local_write()` + CSRF hidden；复用现有 `_leads_flash`。
- 未新增侧栏项；NAV 不变。

## 2. native_id 解析（tools/selection/manual.py）

| platform | 规则 | 兜底 |
| --- | --- | --- |
| xiaohongshu | `/explore/(\w+)` 或 `[?&]note_id=(\w+)` | derived |
| douyin | `/video/(\d+)` | derived |
| weibo | `/status/(\w+)` | derived |
| zhihu | `/question/(\d+)` 或 `/p/(\w+)` | derived |
| tieba | `/p/(\d+)` | derived |
| other | 无 URL 规则 | derived |

- derived：`content_hash` 前 16 位（同一文本重复贴 → 同 hash → 幂等）；**存放位置**：`signal_triage.native_id_source='derived'`（v8 新列）+ `note='manual paste; native_id_source=derived'`；未加 signals 列。
- 入库：`origin_kind='imported'`、`collected_at_scope='batch'`、quote=text 截断 200、lang 用 `models.lang_of`；重复 `(platform,native_id)` 走 `upsert_signal` 幂等（UI 二次提交返回 `manual duplicate`）。

## 3. triage 联动 / 改判

- 入库后立即 `triage.store`（label 与命中词随行）；页面“人工分流（前 20）”表显示 signal/platform/native_id/label/override/命中(demand)/命中(promo)/改判。
- 改判：`POST /leads/triage/<id>`（demand/promo/noise），写 `signal_triage.manual_override`（v8 新列；报告即此存储方案，无 before/after JSON）；非法 label 303 可读。
- `triage.store` 在存在 `manual_override` 时保留 override 为 label，只刷新命中词/规则版本；`triage.refresh()` 全量重跑也不会覆盖 override（测试固定）。
- 改判只标注：不改 identity_key、不写 discovery_event、不动品类归属。

## 4. 可见性 / 分开计数

- `load_lead_data` 新增 `imported_count`；页面顶部：`signals N · origin … · platform … · pending review N · 人工导入 N（人工导入≠自动采集，分开计数）`。
- 提交后 303 回 `/leads`，by_platform 立即变化（测试断言 `zhihu=1`）。

## 5. 测试（真实 exit）

`tests/test_selection_manual.py` 8 项：
`test_native_id_parse_rules_and_derived`、`test_manual_add_and_idempotent`、`test_form_rendered_and_counts`、`test_manual_post_success_and_counts`、`test_manual_missing_fields_303`、`test_manual_csrf_missing_403`、`test_manual_repeat_idempotent`、`test_triage_override_survives_refresh`。

| suite | 结果 | 日志 |
| --- | --- | --- |
| selection（基线 55 + 8 新） | **63 tests OK** | `tools/selection/logs/tests_selection_v98b.log` exit 0 |
| workbench | **218 tests OK** | `tools/selection/logs/workbench_v98b.log` exit 0 |
| 项目全套（基线 389 + 8 新） | **397 tests OK** | `tools/selection/logs/project_v98b.log` exit 0 |

- cwd `D:\桌面\two`；UTC 22:10–22:12。

## 6. 未验证 / 限制

- 各平台 URL 正则只用了构造样例，未验证真实帖子链接（尤其微博/抖音/知乎专栏的变体）。
- manual 表单只支持单条；无批量/去重提示；`other` 平台一律 derived。
- 改判 UI 仅前 20 条；改判不参与品类/卡片更新。
- `signal_triage` 未回填历史 signals（github_v2ex 库 8 行已有；默认 selection 库老数据无 triage 行）。
