# V9-3 实现报告：rounds/round_item 状态机 + 幂等 start + pause/resume + B站真实一轮

> 任务：`task-a266288cd4ccfe2efa37b99fdf6bd9bc`（revision 2，计划 v9）；范围仅 `tools/selection/`、`docs/validation/v9/impl/`、`tests/test_selection_rounds_state.py`。
> 工作区 `D:\桌面\two`；实现/测试/真实轮次时间 2026-10-25 19:18–19:22 UTC+8（11:18–11:22Z）。仅标准库，无新依赖/UI/第三平台。

## 1. schema（v3 追加，旧 signals/runs/categories 语义不变）

| 表 | 字段 | 代码 |
| --- | --- | --- |
| `rounds` | id, kind, platform, status(7态), budget_json, cursor_json, idempotency_key UNIQUE, started_at, ended_at, error_count, stats_json | `db.py` SCHEMA_SQL |
| `round_item` | id, round_id, item_key, state(pending/processing/done/failed), attempts, last_error, updated_at；`UNIQUE(round_id,item_key)` | 同上 |

- **rounds 与 runs 关系**：`rounds` 是上层持久轮次（幂等键、预算、cursor、状态）；`runs` 保留为单次执行/采集审计（1 round : N runs）。本版不合并两表，避免改已有 R1 语义；round 执行当前不强制写 runs（B站 item 级 raw/stats 已在 round.stats_json 中）。
- `SCHEMA_VERSION=3`；`init_db` 幂等插入 v1/v2/v3；旧库 `bilibili/xianyu` 不加新表除非被 init（本任务未改源库）。
- `round_item.item_key`：B站用 `bilibili:view`、`bilibili:reply`；信号 item 未来可用 `platform:native_id`。

## 2. 状态迁移（单一函数）

`rounds.transition()` 集中判定；非法迁移抛 `ValueError`，CLI 非 0。允许：

| from → to | 允许 |
| --- | --- |
| draft → running | 是 |
| running → paused / complete / partial / failed | 是 |
| paused → running | 是 |
| partial → running | 是 |
| 任意 → cancelled | 是（已 cancelled 除外） |
| 其他（如 draft→complete、complete→running） | **否**，抛错 |

`cancelled` 时把 pending/processing item 标 failed（last_error=cancelled），不硬删。

## 3. start 幂等 / round_item

- `rounds.start(idempotency_key)`：先查 `idempotency_key UNIQUE`；命中返回既有 round，`reused=true`，不新建行。
- `round_item(round_id,item_key)` 唯一；`add_item` 重复返回既有；`mark_item` 只更新 attempts/state/last_error，failed 增加 round.error_count。
- 测试：同 key 两次 start 返回同一 id、`reused` 第二次 true、rounds 表 1 行。

## 4. pause / resume（B站 item 级）

`bilibili.collect_round()`：

- item 顺序：`bilibili:view` → `bilibili:reply`；每个 item 单独请求/落 raw/标记 done。
- `pause` 只在 item 边界：测试 `--pause-after-items 1` 在 view 后暂停，round=`paused`，cursor=`{"last_item_key":"bilibili:view"}`。
- **pause 原子性**：先校验 `running/partial`，再 `transition(paused)`；只有 transition 成功且 cursor 非空时才写 `cursor_json`。draft、已 paused 调 pause 抛错，原 cursor 不变。
- `resume`：`collect_round` 从 round 状态/cursor 重新进入，**跳过 state=done 的 item**；已用请求数从 `round.stats_json.requests_used` 继续，不重置预算。
- 已 done 的 view 不会重复请求/重复 raw；reply 只请求一次；signals `UNIQUE(platform,native_id)` 防重复。
- round 结束 `complete`；预算耗尽在 item 边界先把最后完成 item 写入 `cursor_json`、`stats.stop_reason=budget_exhausted`，再转 `partial`；风控/非200 转 `failed`。
- **中断语义**：`resume` 时若存在 `state='processing'` 的 item，先标 `failed`、`last_error='interrupted'`（attempts+1），再转 running；测试固定该行为，中断后可见 failed/interrupted。

### 真实轮次（B站，≤3 请求）

| 阶段 | 命令/exit | 请求累计 | signals | round 状态 |
| --- | --- | --- | --- | --- |
| start | `round start --budget 3 --key real-round-1`，exit 0 | 0 | 0 | draft |
| run/pause | `round run --round-id 1 --aid 540769243 --budget 3 --interval 3 --pause-after-items 1`，exit 0 | **1**（view） | **0** | paused，cursor=view |
| resume/complete | `round run --round-id 1 ...`（无 pause 参数），exit 0 | **2**（view+reply） | **3** | complete |

- 证据：`logs/round_start.log`、`logs/round_pause.log`、`logs/round_resume.log`；raw `raw/round_real/bilibili_view_1.json`（sha `c6035571…`）、`bilibili_reply_p1_1.json`（sha `560163cf…`）。
- round 表：id=1、status=complete、requests_used=2、error_count=0、ended_at 11:21:25Z；items 均 done（view/reply 各 attempts=2，因首次 processing+done 计 2）。
- **未重跑采集**；真实轮次即本轮新增的 2 请求（≤3），间隔 3s，无风控。

## 5. CLI

`tools/selection/cli.py` 新增：

```powershell
.\.venv\Scripts\python.exe -X utf8 -m tools.selection.cli --db <db> --raw-dir <raw> round start --budget 3 --key KEY
.\.venv\Scripts\python.exe -X utf8 -m tools.selection.cli --db <db> --raw-dir <raw> round run --round-id 1 --aid 540769243 --budget 3 --interval 3 [--pause-after-items 1]
.\.venv\Scripts\python.exe -X utf8 -m tools.selection.cli --db <db> round status --round-id 1
.\.venv\Scripts\python.exe -X utf8 -m tools.selection.cli --db <db> round pause|resume|cancel --round-id 1
```

- JSON 单行；`round run` 返回 complete/partial/paused→0，failed→3；非法迁移/参数错误→非 0。
- `--raw-dir` 是全局参数，必须放在 `round` 子命令前。

## 6. tests / guards / limits

- `tests/test_selection_rounds_state.py`：8 tests，覆盖非法迁移、cancel、幂等 start、round_item UNIQUE/attempts/error_count、pause→resume 不重复、budget→partial、pause 原子性/cursor 保持、budget partial 写 cursor、processing→interrupted；`logs/tests_selection_rounds_state.log` exit 0，`Ran 8 tests ... OK`。
- 全量 selection：`logs/tests_selection_all_v93.log` exit 0，`Ran 30 tests ... OK`（25 旧 + 5 新），cwd `D:\桌面\two`，UTC 11:21:39Z。
- 未改 app/、tools/workbench/、业务库/CSV/CONTRACT；未接 UI；未新增平台/依赖。
- 限制：rounds 当前只编排 B站 item；未验证多平台并行/第三平台/UI；round 不强制写 runs（1:N 关系已说明但本版不生成 per-run 行）；真实轮次未验证高频/风控阈值。
