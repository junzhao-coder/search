# V10 知乎首次真实搜索调用（恰好 1 次，public-http）

> 任务 `task-4086320c86d7e741427bb6e9f8058f27`（rev2，计划 v10，V10-2）。
> 执行时间 2026-10-27 16:11:12–16:11:21 UTC+8（08:11:12–08:11:21Z）。
> **只执行 1 次真实搜索**；未重试、未换关键词、未改 mode、未改代码/测试/期望值、未删日志；无 cookie/token 输出。

## 1. 实际命令与结果

| 项 | 值 |
| --- | --- |
| argv | `C:\Users\19183\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe -m tools.selection.access.zhihu --state-dir docs\validation\v10\zhihu\runtime_live --batch-id zhihu-live-1 --mode public-http search 学习计划模板 --limit 5` |
| cwd | `D:\桌面\two` |
| started_utc / finished_utc | **2026-10-27T08:11:12Z** / **08:11:13Z** |
| **exit** | **5** |
| records | **0** |
| stop | **`http_403`** |
| parsed_structure | 无（未取得正文，0 条记录） |
| 是否 locked | **true**（`lock_reason=http_403`，`lock_source=search`） |
| stderr | 空 |

## 2. 完整 stdout JSON（原样）

```json
{"batch": {"batch_id": "zhihu-live-1", "calls": 1, "calls_max": 3, "elapsed_s": 0.249, "last_call_at": 1793088673.27405, "lock_reason": "http_403", "lock_source": "search", "locked": true, "polls": 0, "polls_max": 10, "records": 0, "records_max": 5, "seconds_max": 300.0, "state_dir": "D:\\桌面\\two\\docs\\validation\\v10\\zhihu\\runtime_live"}, "command": "search", "count": 0, "exit": 5, "keyword": "学习计划模板", "ok": false, "records": [], "stop": "http_403", "url": "https://www.zhihu.com/search?q=%E5%AD%A6%E4%B9%A0%E8%AE%A1%E5%88%92%E6%A8%A1%E6%9D%BF"}
```

- 原件：`docs/validation/v10/zhihu/live_search_1.out.txt`（stdout）、`live_search_1.err.txt`（空）。

## 3. budget 子命令（预扣证据）

| 项 | 值 |
| --- | --- |
| argv | `... -m tools.selection.access.zhihu --state-dir docs\validation\v10\zhihu\runtime_live budget --ledger 5` |
| UTC | 08:11:21Z |
| exit | **0** |

```json
{"budget": {"batch_id": "zhihu-live-1", "calls": 1, "calls_max": 3, "locked": true,
 "lock_reason": "http_403", "lock_source": "search", "records": 0, "records_max": 5,
 "seconds_max": 300.0, "state_dir": "...\\runtime_live"},
 "command": "budget", "exit": 0,
 "ledger": [
   {"at": 1793088673.4678662, "kind": "lock",
    "detail": "{\"reason\": \"http_403\", \"source\": \"search\", \"batch_id\": \"zhihu-live-1\"}"},
   {"at": 1793088673.27405, "kind": "charge",
    "detail": "{\"kind\": \"search\", \"detail\": \"https://www.zhihu.com/search?type=content&q=...\", \"batch_id\": \"zhihu-live-1\"}"}
 ], "ok": true}
```

- **预扣生效证据**：`calls=1`（3 次预算用掉 1 次）+ `charge` 记录 + `lock` 记录；`locked=true`。
- 原件：`live_budget_1.out.txt` / `live_budget_1.err.txt`（空）。
- state 目录 `runtime_live/` 仅 `budget.sqlite3`（24,576 B）。

## 4. 结论

- 匿名 `public-http` 搜索被知乎以 **HTTP 403** 拒绝；按设计 `_NoRedirect` + 风险即锁，返回 exit 5、`http_403`、`locked=true`，**未重试、未绕过**。
- 403 通常意味着匿名访问被拒（需登录/风控）；是否改用 `--mode authenticated-browser`（依赖用户登录态）或暂停知乎路线，需用户决定。
- 预算消耗：3 次中已用 **1 次**，该 state-dir 已 locked，后续调用会被预算锁拒绝（不会发请求）。

## 5. 声明

- **只执行了 1 次**真实搜索；未重试、未换词、未改 mode。
- 未改代码/测试/期望值，未删日志；无 cookie/token 值输出。
- 未访问知乎以外域名；未写业务库/CSV/CONTRACT。
