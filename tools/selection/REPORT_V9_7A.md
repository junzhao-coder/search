# V9-7a 实现报告：resume 真采集 / start 自动归纳 / cancel 立即停 / interval 生效 / 幂等冲突

> 任务 `task-f7945f12b63e1c1222fea0e4d28dd8a6`（rev2，计划 v9）；范围 `tools/selection`、`tools/workbench`、`tests`。
> 2026-10-25 20:46–20:57 UTC+8。未装依赖、未接 LLM、未改数据结构语义、未写 `instance/app.db`/`workflow.sqlite3`/业务 CSV；未动 merge/undo/split/判重。
> 注：Flow 范围不含 `docs/validation/v9/impl`，报告暂放 `tools/selection/`（范围内）。

## 1. 前后对比（审计 E1/E2/E10）

审计脚本复制到 temp 运行（`ROOT` 指向真实仓库；不改 `docs/validation/v9/integration-audit/`）；为离线验证，temp 副本注入 stub fetch，并捕获 E10 的冲突断言。原始审计目录未改。

| 实验 | 修复前 | 修复后 | 证据 |
| --- | --- | --- | --- |
| E1 `ui_start_cards` | FAIL：categories=0/cards=0/events=0 | **PASS**：requests=2、categories=1、cards=1、events=2、round complete | 303 Location 含 `new=1 update=1 categories=1 cards=1` |
| E2 `ui_resume_requests` | FAIL：after_calls=1、reply pending、round running | **PASS**：after_calls=2、reply done、requests_used=2、signals=2、round complete | `collect_round` 被再次调用 |
| E10 `round_edges` | ERROR：idempotency_conflict 未捕获；cancel 后 illegal_transition；interval 0.016s | **PASS**：cancel 后 1 请求即停、status=cancelled；interval 3.031s；同 key 不同 budget → `idempotency_conflict` | 见 §5 |

> 其余 6 项审计（repeat_categorize_cards、merged_excluded_attribution、split_undo、import_bad_json_budget、identity_carrier_origin、merge_cards_undo）仍 FAIL，属下一批（不改 merge/undo/split/判重）；本任务未声称修复。

## 2. resume 真执行（F1）

- `app.py:1452-1468`：`POST /leads/round/<id>/resume` 先 `sel_rounds.resume`，再取 round `budget_json`（aid/bvid/max_requests/interval），调用 `sel_bili.collect_round` 继续同一 round；不再只改状态。
- `bilibili.py:256-396`：`collect_round` 按 item 推进；done item 跳过；`rounds.resume` 只由调用方一次；内部兼容直接调用 paused/partial。
- 桩测：`tests/test_selection_rounds_state.py::test_start_route_categorizes_and_resume_route_collects`：paused（view done）→ POST resume → fetch 1→2、reply done、requests_used=2、signals 同 native_id 仍唯一（1 条）。

## 3. start 自动归纳（F2）

- `app.py:1429-1438`：`collect_round` 后调用 `sel_categories.run_categorize(conn)` + `make_cards(conn)`；303 消息并入 `new/update/review/categories/cards`。
- 桩测同一测试：start 返回 303，Location 含 `categories=1`；DB 断言 categories≥1、cards≥1、events≥1。
- 页面口径行仍为“规则推断，不是市场结论；样本极小”（`views_leads.py` 未改）。

## 4. cancel / interval（F3）

- `bilibili.py:293-300`：每个 item 开始前读 round 状态；`cancelled` 立即 return `status=cancelled`，不再 fetch、不 transition；`paused` 立即 return paused（修复旧代码 paused 后 break→complete 的非法迁移）。
- `bilibili.py:385-392`：循环结束前再查 cancelled/paused，避免 cancelled→complete 的 `illegal_transition`。
- `bilibili.py:324-331`：每次 fetch 前按 `interval` sleep（首次不 sleep；`sleep/clock` 可注入），并从 `budget_json.interval` 恢复。
- 桩测：`test_collect_round_interval_sleeps_and_cancel`：2 请求仅 1 次 sleep≥2.9s；cancel 后仅 1 请求、status=cancelled。审计实测 interval 3.031s。

## 5. 幂等冲突（F3）

- `rounds.py:44-55`：同 `idempotency_key` 命中时比较 `budget_json`；不同（含 budget/interval/aid/bvid）抛 `ValueError("idempotency_conflict")`，不静默复用。
- 页面/CLI 捕获异常后 303/非 0 + 可读错误。
- 测试：`test_start_idempotency_conflict_budget`、`test_start_idempotency_conflict_aid`。

## 6. 测试（真实 exit）

| suite | 结果 | 日志 |
| --- | --- | --- |
| selection（基线 38 + 新增 4） | **42 tests OK** | `docs/validation/v9/impl/logs/tests_selection_v97.log` exit 0 |
| workbench | **218 tests OK** | `docs/validation/v9/impl/logs/workbench_v97.log` exit 0 |
| 项目全套（基线 372 + 新增 4） | **376 tests OK** | `docs/validation/v9/impl/logs/project_v97.log` exit 0 |

- cwd `D:\桌面\two`；UTC 20:54–20:56；新增测试在 `tests/test_selection_rounds_state.py`（12 tests，含 4 个新场景）。
- 验收写的“selection 38 / 项目 372”是**修复前基线**；新增 4 项后实际 42/376，未删旧测试。

## 7. 未修 / 限制

- 未修：merge/undo/split、判重语义、重复 categorize 卡片刷新、excluded/merged 归属、import bad JSON 预算、identity carrier/origin（审计其余 6 FAIL，下一批）。
- 未改 rounds/round_item schema 语义；`start` 把 interval/aid/bvid 放进 `budget_json`（不是新列），冲突比较也基于该 JSON。
- 未跑真实 B站；审计用 stub fetch；未验证长跑/翻页/多平台。
- temp 审计曾写 `docs/validation/v9/impl/raw/leads`（stub 写 raw），已删除该测试生成目录；未写业务库/CSV。
