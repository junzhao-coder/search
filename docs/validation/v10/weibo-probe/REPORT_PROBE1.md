# V10-5 微博未登录探路（第 1 次）：**浏览器未启动，零 HTTP 请求**，非 a/b/c/d 任一分支

> 任务 `task-32c21f6eb4e3bf0b277b6b5a40acd92b`（rev2，计划 v10，小目标 V10-5）。
> 执行时间：2026-10-27 23:05:47–23:06:01 UTC+8（**15:05:47Z–15:06:01Z**，14 秒结束）。
> **只执行 1 次**微博 CLI 调用；未重试、未换关键词、未换 mode、未改代码/测试/期望值、未装依赖、未代填、未读 cookie 值、未引导用户做任何操作。

## 1. 实际命令

| 项 | 值 |
| --- | --- |
| argv | `C:\Users\19183\.dsh\tools\x-collect\venv\Scripts\python.exe -X utf8 -m tools.selection.access.weibo --state-dir docs\validation\v10\weibo-probe\state-probe1 --batch-id weibo-probe-1 --mode authenticated-browser --profile docs\validation\v10\weibo-probe\profile_empty search 学习计划模板 --limit 5 --visible --timeout 60 --diagnostics-dir docs\validation\v10\weibo-probe\diag` |
| cwd / PYTHONPATH | `D:\桌面\two` / `D:\桌面\two` |
| started_utc / finished_utc | **2026-10-27T15:05:47Z** / **15:06:01Z** |
| state-dir / profile | 全新 `state-probe1` / 全新空目录 `profile_empty`（执行后仍为 **0 个文件**） |
| **exit** | **进程以未捕获异常结束**（Start-Process 未回传 ExitCode；以 stderr traceback 为准，Python 默认退出码 1） |
| **stdout** | **空**（0 字节，无任何 JSON） |
| stderr | 2,274 B traceback（见 §2） |
| 180s 外部保护 | **未触发**（14 秒内结束） |
| `wait_for` 硬超时 | **未触发**（失败发生在 `uc.start`，早于任何导航） |

## 2. 真实 stderr（末尾，原文）

```
  File "D:\桌面\two\tools\selection\access\transport.py", line 164, in _start
    return await uc.start(headless=self.headless,
  File "C:\Users\19183\.dsh\tools\x-collect\venv\Lib\site-packages\nodriver\core\browser.py", line 382, in start
    raise Exception(
Exception:
                ---------------------
                Failed to connect to browser
                ---------------------
                One of the causes could be when you are running as root.
                In that case you need to pass no_sandbox=True
```

调用栈：`weibo.main` → `run_search` → `transport.fetch` → `_ensure_browser` → `loop.run_until_complete(wait_for(_start))` → `uc.start` → **`Browser.start` 抛 `Exception("Failed to connect to browser")`**。

## 3. 逐项观测（验收 §3 要求的字段）

| 字段 | 实际值 |
| --- | --- |
| phase | **无**（诊断骨架未生成） |
| ready_state | **未取得** |
| probe_level / probe_elapsed_ms | **未取得** |
| anchors_total / recognized / rejected | **未取得** |
| href_shapes | **未取得** |
| html_bytes | **未取得** |
| final_url / final_url_known | **未取得**（从未导航） |
| wall | **未取得** |
| parse_state | 无 |
| `--diagnostics-dir` 产物 | **目录未创建 / 无文件** |
| 本 profile 的 Chrome 进程 | **0 个**（全程采样 600 次 × 300ms 未捕获到任何带 `weibo-probe` 的 chrome 进程） |

→ 因此**没有任何微博 HTTP 请求发出**：浏览器根本没起来，谈不上导航。

## 4. 四分支归类：**不属于 a/b/c/d**，属"工具链故障"

| 分支 | 判定 | 依据 |
| --- | --- | --- |
| a) 未登录可读 | **否** | 无 anchors、无 title、无 HTML |
| b) 登录/访客墙 | **否** | 无 wall、无最终 URL、无重定向 |
| c) `phase=navigate` 超时、无 DOM | **否** | 没有 phase 字段；失败在**启动**阶段而非导航阶段；`wait_for` 从未触发 |
| d) URL 假设错误 | **否** | 请求从未发出，无法判断 `containerid` 假设是否成立 |

**结论：本次探路无效（invalid），未获得任何关于"微博未登录是否可读"的证据。** 既不能说可读，也不能说需要登录。

## 5. 根因（已用**不访问微博**的对照实验定位）

对照实验脚本 `_diag_profile_path.py`（只访问 `about:blank`，不碰任何站点），同一 Chrome、同一空 profile 目录：

| 变体 | 结果 |
| --- | --- |
| **相对路径** `docs\validation\v10\weibo-probe\profile_empty` + `headless=False` | **LAUNCH_FAILED**：`Failed to connect to browser` |
| **绝对路径** `D:\桌面\two\docs\validation\v10\weibo-probe\profile_empty` + `headless=False` | **OK**：`type(tab)=Tab` |

→ 根因：`--profile` 传的是**相对路径**，`transport._ensure_browser()` 把它原样交给 `uc.start(user_data_dir=...)`；Chrome 的 `--user-data-dir` 语义下相对路径会落到非预期位置，nodriver 随后连不上浏览器。

- 这是**入口参数解析缺陷**（transport 应把 profile 解析为绝对路径），不是微博的风控、也不是节点/网络问题。
- 对照：V10-3 知乎每次都用**绝对** profile 路径（`C:\Users\19183\.dsh\tools\zhihu-collect\profile`），所以从未触发本缺陷。
- 本任务约束为"不改代码"，故**未修**，只报告。

## 6. 预算（真实）

`--state-dir …\state-probe1 budget --ledger 5` 原文：

```json
{"budget": {"batch_id": "weibo-probe-1", "calls": 1, "calls_max": 3,
  "lock_reason": null, "lock_source": null, "locked": false, "polls": 0,
  "polls_max": 120, "records": 0, "records_max": 5, "seconds_max": 300.0,
  "state_dir": "...\\state-probe1"},
 "command": "budget", "exit": 0, "ok": true,
 "ledger": [{"at": 1793113547.8159518, "kind": "charge",
   "detail": "{\"kind\": \"search\", \"detail\": \"https://m.weibo.cn/search?containerid=100103type%3D1%26q%3D…\", \"batch_id\": \"weibo-probe-1\"}"}]}
```

- **本次消耗 1 次额度（calls=1/3）**，`locked=false`、无 lock 记录、ledger 仅 1 条 `charge`（**没有** `transport_error`，因为异常直接冒泡绕过了 note）。
- 批次 300s 窗口自 `started_at` 起算，已过期；剩余 2 次额度**不等于**可直接复用（同 state-dir 会 `budget:time_exhausted`）。
- 另注：该 `charge` 发生在 `fetch` 之前（预扣设计），所以"额度被消耗"与"是否真的发出请求"是两件事——本次是后者为**否**。

## 7. 下一步建议（P5）

1. **先修一处、再探路**（最小改动，1 行）：`transport.AuthenticatedBrowserTransport.__init__` 里把 `self.profile = pathlib.Path(profile)` 改为 `.expanduser().resolve()`；或 `weibo.main` 在 `_make_transport` 前解析绝对路径。同时建议 `_ensure_browser` 把 `uc.start` 的**非超时异常**转成 `browser_start_failed` 结构化结果，避免 CLI 直接抛栈（本次没有 `transport_error` 记录就是因此）。
2. **重新派发 1 次探路**（用新 state-dir，如 `state-probe2`；profile 可继续用空目录，但传**绝对路径**）。届时四分支才有意义：
   - 若 a（可读）→ 补 detail/comments 的最小动作：先取 1 条 `/detail/<mid>` 验证详情解析，再用 `/comments/hotflow` 验证评论 JSON；
   - 若 b（墙）→ 记录墙词与最终 URL，再决定是否扫码登录（登录后需验证：搜索结果、详情正文、评论、翻页游标）；
   - 若 d（URL 假设错）→ 用 m.weibo.cn 首页/搜索入口的真实链接形态修正 `search_url`。
3. **不建议**现在让用户扫码：本次连页面都没打开，登录态能解决什么问题尚未可知；先拿到未登录基线再决定。

## 8. 声明

- **只执行 1 次**微博 CLI 调用；**未重试、未换关键词、未换 mode**。
- **零微博 HTTP 请求**：本 profile 的 Chrome 进程全程为 0，profile 目录执行后仍为空，无 final_url、无诊断骨架。
- 未装依赖、未代填凭据、未读取/输出 cookie 值、未访问微博以外域（对照实验只访问 `about:blank`）、未写业务库/CSV/CONTRACT、profile 未入仓库。
- 未要求用户做任何操作（窗口从未出现）。
