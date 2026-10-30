# V10 知乎离线检查：修复后重跑取证（exit=0，23/23 match）

> 任务 `task-928ae92233f7e98ec5c17c28ca94f129`（rev2，计划 v10）。
> 执行时间 2026-10-27 13:21:36–13:21:52 UTC+8（05:21:36–05:21:52Z）。
> **未改代码/测试/期望值、未反复重跑、未删日志、未换解释器、零网络/浏览器/知乎请求。**

## 1. 实际命令与结果

| 项 | 值 |
| --- | --- |
| argv | `C:\Users\19183\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe docs\validation\v10\zhihu\offline_checks.py` |
| cwd | `D:\桌面\two` |
| 解释器 | Python **3.12.14** |
| started_utc / finished_utc | **2026-10-27T05:21:36Z** / **05:21:52Z** |
| **总 exit** | **0** |
| **all_match** | **true** |
| **mismatched** | **[]** |
| 场景数 | **23**（与基线一致） |

- 旧基线已另存 `logs/offline_checks.baseline-051642Z.json`（16,151 B，05:16:42Z），未被覆盖丢失；新结果 `logs/offline_checks.json`（16,177 B，05:21:52Z）。
- 本次控制台原件：`logs/_driver_console_rerun.txt`（23,988 B）。

## 2. 逐场景 expect / exit / match（23/23）

| 场景 | expect | exit | match |
| --- | --- | --- | --- |
| unittest | 0 | 0 | ✅ |
| cli_help | 0 | 0 | ✅ |
| cli_login_help | 0 | 0 | ✅ |
| cli_doctor | 0 | 0 | ✅ |
| cli_search_offline | 0 | 0 | ✅ |
| cli_budget | 0 | 0 | ✅ |
| cli_search_second_offline | 6 | 6 | ✅ |
| cli_relabel_no_reset | 6 | 6 | ✅ |
| cli_budget_after_relabel | 0 | 0 | ✅ |
| **cli_detail_offline** | **0** | **0** | ✅（原 0/6） |
| **cli_comments_offline** | **0** | **0** | ✅（原 0/6） |
| cli_export | 0 | 0 | ✅ |
| cli_export_secrets | 0 | 0 | ✅ |
| cli_export_missing | 9 | 9 | ✅ |
| cli_input_missing | 8 | 8 | ✅ |
| cli_import_smoke | 0 | 0 | ✅ |
| risk_first_call | 5 | 5 | ✅ |
| risk_restart_refused | 6 | 6 | ✅ |
| risk_relabel_refused | 6 | 6 | ✅ |
| risk_budget_inspect | 0 | 0 | ✅ |
| risk_login_refused | 6 | 6 | ✅ |
| **login_wall_first_call** | **5** | **5** | ✅（原 5/6） |
| login_wall_restart_refused | 6 | 6 | ✅ |

## 3. 三个此前失败场景的实际 stdout

### 3.1 `cli_detail_offline`：expect 0 → exit 0（转绿）
```json
{"command":"detail","exit":0,"ok":true,"count":1,"stop":null,
 "parsed_structure":"html:meta",
 "batch":{"state_dir":"...\\logs\\_state_detail","locked":false,"records":1}}
```
- 独立 `_state_detail`，`elapsed_s=0.022`，无 interval 拦截；真实解析出 1 条 answer（native_id `111`、title/正文/published_at/voteup）。

### 3.2 `cli_comments_offline`：expect 0 → exit 0（转绿）
```json
{"command":"comments","exit":0,"ok":true,"count":2,"stop":null,
 "parsed_structure":"json:comment_v5",
 "batch":{"state_dir":"...\\logs\\_state_comments","locked":false,"records":2}}
```
- 独立 `_state_comments`，解析出 2 条评论（`c1001`、`c1002`），`next_offset="offset-2"`、`is_end=false`。

### 3.3 `login_wall_first_call`：expect 5 → exit 5（转绿，且路径真实执行）
```json
{"command":"detail","exit":5,"ok":false,"count":0,
 "stop":"text:请登录后查看",
 "batch":{"state_dir":"...\\logs\\_state_login_wall","locked":true,
          "lock_reason":"text:请登录后查看","lock_source":"detail"}}
```
- **stop 实际值 = `text:请登录后查看`**，不再是 `budget:batch_locked`；说明登录墙判定路径**首次真正执行**并正确加锁。
- 随后 `login_wall_restart_refused`（expect 6）在同一新目录返回 6，验证“登录墙后重启被拒”。

## 4. logs 目录最终清单

- `offline_checks.json`（16,177 B，本次）
- `offline_checks.baseline-051642Z.json`（16,151 B，上一轮基线副本）
- `_driver_console.txt`（24,074 B，上一轮）、`_driver_console_rerun.txt`（23,988 B，本次）
- 23 组 `*.stdout.txt` / `*.stderr.txt`
- `export_out.jsonl`、`export_secrets_out.jsonl`
- **state 目录 5 个**：`_state`、`_state_risk`、**`_state_detail`**、**`_state_comments`**、**`_state_login_wall`**（三个新目录均已生成）
- 原 `run_tests.cmd`（146 B，未动）

## 5. 声明

- **未改代码/测试/期望值**：`offline_checks.py` 155 行未动（上一轮已改），`tools/selection/access/*`、`tests/*` mtime 均早于本任务。
- **未反复重跑**：本次仅运行一次；旧基线另存副本，未删日志。
- 零网络、零浏览器、零知乎请求（全部 fixture/本地）。
- 结论：三个此前失败场景全部转绿，23/23 match，总 exit 0；登录墙判定路径已真实覆盖。
