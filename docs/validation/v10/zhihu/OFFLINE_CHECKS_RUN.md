# V10 知乎接入：离线检查执行取证（只执行、不改代码）

> 任务 `task-af1d6afe7628f066802952cbc2e85b31`（rev4，计划 v10）。
> 执行时间 2026-10-27 13:16:23–13:16:42 UTC+8（05:16:23–05:16:42Z）。
> **未修改任何代码/测试、未重跑覆盖、未删除日志、未换解释器、零网络/零浏览器/零知乎请求。**

## 1. 实际命令与结果

| 项 | 值 |
| --- | --- |
| argv | `C:\Users\19183\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe docs\validation\v10\zhihu\offline_checks.py` |
| cwd | `D:\桌面\two` |
| 解释器 | Python **3.12.14**（存在，实测 `-V`） |
| started_utc / finished_utc | **2026-10-27T05:16:23Z** / **05:16:42Z** |
| 总 exit | **1** |
| `all_match` | **false** |
| 场景数 | 23（脚本自报；任务描述写 24，以实际 `runs` 为准） |
| mismatched | **`cli_detail_offline`、`cli_comments_offline`、`login_wall_first_call`** |
| 原件 | `docs/validation/v10/zhihu/logs/offline_checks.json`（16,151 B，`generated_utc=2026-10-27T05:16:42Z`）、`_driver_console.txt`（24,074 B） |

## 2. 逐场景 expect / exit / match

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
| **cli_detail_offline** | **0** | **6** | ❌ |
| **cli_comments_offline** | **0** | **6** | ❌ |
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
| **login_wall_first_call** | **5** | **6** | ❌ |
| login_wall_restart_refused | 6 | 6 | ✅ |

## 3. 失败场景：期望 vs 实得（原样，未修）

### 3.1 `cli_detail_offline`：expect 0，实得 6
stdout（`logs/cli_detail_offline.stdout.txt`）：
```json
{"command":"detail","exit":6,"ok":false,"stop":"budget:interval_not_elapsed","count":0,
 "batch":{"batch_id":"detail-label","calls":1,"calls_max":3,"elapsed_s":1.027,"locked":false}}
```
- 直接原因：同一 `_state` 中上一调用仅过约 1s，未满足 15s 间隔，被预算拦下（`budget:interval_not_elapsed`）。
- 属**场景编排/时序问题**（前序 `cli_budget_after_relabel` 后立刻 detail），不是解析或网络失败。

### 3.2 `cli_comments_offline`：expect 0，实得 6
stdout（`logs/cli_comments_offline.stdout.txt`）：
```json
{"command":"comments","exit":6,"ok":false,"stop":"budget:interval_not_elapsed","count":0,
 "batch":{"batch_id":"comments-label","calls":1,"calls_max":3,"elapsed_s":1.242,"locked":false}}
```
- 同上：紧随 detail 之后 1.2s，未到 15s 间隔。

### 3.3 `login_wall_first_call`：expect 5，实得 6
stdout（`logs/login_wall_first_call.stdout.txt`）：
```json
{"command":"detail","exit":6,"ok":false,"stop":"budget:batch_locked","detail":"text:安全验证",
 "budget":{"batch_id":"zhihu-b09dc3ad1438","locked":true,"lock_reason":"text:安全验证","lock_source":"detail"}}
```
- 直接原因：该场景在 `_state_risk` 上运行，而此前 `risk_first_call` 已把该 state 置为 `locked`（安全验证）；本次 detail 被 `batch_locked` 拦下，返回 6 而非期望 5。
- 属**场景复用同一 risk state 的顺序问题**；登录墙识别本身在 `risk_first_call` 已按 expect 5 通过。

## 4. 关键场景 stdout 片段（≥3）

**unittest**（`logs/unittest.stdout.txt` / `.stderr.txt`）：
```
Ran 72 tests in 12.216s
OK
```
（`unittest` 场景 exit 0，match=true；stderr 9,663B 为 unittest 正常 `-v` 明细。）

**risk_first_call**（expect 5，match）：
```json
{"command":"detail","exit":5,"ok":false,"stop":"risk_marker","detail":"text:安全验证"}
```

**risk_restart_refused / risk_relabel_refused**（expect 6，match）：
```json
{"command":"search","exit":6,"ok":false,"stop":"budget:batch_locked","detail":"risk lock active"}
```

**login_wall_restart_refused**（expect 6，match）：
```json
{"command":"search","exit":6,"ok":false,"stop":"budget:batch_locked"}
```

## 5. logs/ 最终清单

- `offline_checks.json`（16,151 B）、`_driver_console.txt`（24,074 B）
- 23 组 `*.stdout.txt` / `*.stderr.txt`（每组 0–9,663 B；`unittest.stderr.txt` 最大）
- `export_out.jsonl`（1,465 B）、`export_secrets_out.jsonl`（1,465 B）
- `_state/`、`_state_risk/`（脚本每次运行重建）
- 原有 `run_tests.cmd`（146 B，未改动）
- 无删除、无覆盖重跑。

## 6. `_probe.txt`

- `tools/selection/access/_probe.txt` **存在**，217 B，mtime `2026-10-27T05:11:11Z`。
- 属执行者无权删除的遗留探测文件；本任务**未删除、未修改**，如实保留。

## 7. 结论与移交

- 离线检查**真实跑过一次**，总 exit=1；`unittest`（72 例）全过，23 场景中 20 匹配、**3 不匹配**。
- 3 个不匹配均可由**场景编排/时序**解释（15s 间隔预算、risk state 复用），未见代码解析或网络层错误；但按任务约束**未现场修改**，交回原执行者修脚本场景顺序（如 detail/comments 前等待 15s，或为 login_wall 用独立 state）。
- 本报告与日志为原始证据；未重跑覆盖，未改代码/测试，未换解释器，零网络。
