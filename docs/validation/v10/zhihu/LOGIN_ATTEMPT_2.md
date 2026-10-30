# V10-3 知乎登录窗口：第二次尝试（x-collect venv）— block：产品代码 async/sync 缺陷

> 任务 `task-4f73e623e9dbe1078e5e8fe61175f172`（rev4，计划 v10，V10-3）。
> 执行时间 2026-10-27 16:31:13–16:32:21 UTC+8（08:31:13–08:32:21Z）。
> **未代填凭据、未读取/输出 cookie 值、未安装依赖、未改代码、未重试。**

## 1. 解释器切换（策划者放行）

| 项 | 值 |
| --- | --- |
| 解释器 | `C:\Users\19183\.dsh\tools\x-collect\venv\Scripts\python.exe` |
| Python | **3.12.10** |
| nodriver | **0.50.6** |
| PYTHONPATH | `D:\桌面\two` |
| import 验证 | `import tools.selection.access.zhihu / browser / nodriver` → **ok, exit 0** |

- 说明：主运行时（3.12.14）无 nodriver；x-collect venv 有 nodriver 0.50.6 与 websockets 17.3，import 成功，无需安装依赖。

## 2. login 执行（一次）

| 项 | 值 |
| --- | --- |
| argv | `C:\Users\19183\.dsh\tools\x-collect\venv\Scripts\python.exe -m tools.selection.access.zhihu --state-dir docs\validation\v10\zhihu\runtime_login --profile C:\Users\19183\.dsh\tools\zhihu-collect\profile login --timeout 300` |
| cwd | `D:\桌面\two`（PYTHONPATH=D:\桌面\two） |
| started_utc / finished_utc | **2026-10-27T08:31:20Z** / **08:31:32Z** |
| **exit** | **13** |
| status | **`unknown`** |
| polls | **1** |
| elapsed_s | **0.006** |
| final_url | `null` |
| signed_in | false |
| stop_reason | **`browser_error:RuntimeError`** |
| 窗口 | **无**（无 Chrome 进程/带标题窗口） |

stdout 原文（`docs/validation/v10/zhihu/login_run2.out.txt`）：
```json
{"command":"login","elapsed_s":0.006,"exit":13,"final_url":null,"polls":1,
 "risk_reason":null,"signed_in":false,"status":"unknown",
 "stop_reason":"browser_error:RuntimeError"}
```

stderr（`login_run2.err.txt`）：仅 asyncio 收尾告警 `RuntimeError: Event loop is closed` / `ValueError: I/O operation on closed pipe`，无产品 traceback。

## 3. 根因（只读确认，未改代码）

| 证据 | 内容 |
| --- | --- |
| `browser.py:156-163` | `_eval(browser, script)` 调用 `browser.evaluate(script)` 后直接 `str(...)`，为**同步**调用 |
| nodriver API | `inspect.iscoroutinefunction(Tab.evaluate)` = **True**（async） |
| 结果 | `_eval` 拿到的是 coroutine，无法取值 → 抛 `RuntimeError`；`wait_for_login` 记 `browser_error:RuntimeError` |
| 调用链 | `zhihu.py:501-526 _login_with_real_browser` 在 `asyncio.run(_run())` 内 `await browser.get(...)`，随后**同步**调用 `browser_mod.wait_for_login(...)`（:518），事件循环内无法 await |

- 因此：`browser.available()` 通过、浏览器可启动，但**第一轮轮询即失败**（polls=1、elapsed 0.006s），窗口未形成可交互状态。
- 这是**产品代码 async/sync 混用缺陷**，不是解释器缺失、不是依赖问题。按任务约束未现场修改，交回原执行者修（`_eval`/`wait_for_login` 改 async，或在 `_run` 内 `await` 轮询）。

## 4. doctor（两次，只记布尔）

### 4.1 前置（rev2 时，profile 未创建）
```json
{"command":"doctor","cookie_db_exists":false,"cookie_names":{},"exit":0,"network":"none",
 "online":"unverified","profile_exists":false}
```

### 4.2 本次失败后
```json
{"command":"doctor","cookie_count":0,"cookie_db_exists":true,
 "cookie_names":{"SESSIONID":false,"__zse_ck":false,"_xsrf":false,"d_c0":false,
                 "q_c1":false,"z_c0":false},
 "exit":0,"network":"none","online":"unverified","profile_exists":true}
```
- profile 目录已被本次尝试创建（mtime 08:31:22Z），但 **cookie 名称全部 false、cookie_count=0、online=unverified** → 未登录成功。
- 只记布尔，未读取/输出任何 cookie 值。

## 5. state / 证据

- `docs/validation/v10/zhihu/runtime_login/`：仅 `budget.sqlite3`（24,576 B）。
- 证据文件：`login_run2.out.txt`、`login_run2.err.txt`、`login_run2.pid`（PY_PID 102836 已退出）、`login_doctor_post2.out.txt`。
- 未重试、未自动重开窗口。

## 6. 声明与下一步

- **未代填账号/密码/验证码；未读取或输出 cookie/token 值；未安装依赖；未改代码/测试/期望值；未访问知乎以外域；未写业务库/CSV/CONTRACT。**
- 结论：登录窗口**未能打开**（产品代码 async/sync 缺陷导致第一轮轮询即失败）。
- 下一步需原执行者修 `browser.py::_eval` / `wait_for_login` 的 async 调用（或改为在 `_run` 内 await），修完后由后续任务重跑 login。
