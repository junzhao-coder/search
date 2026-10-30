# V10-3 修复报告：async/sync 缺陷已修 + login 真跑（被登录页 risk 文案拦下）

> 任务 `task-f9c6bf5ec14d130200056818d168b1a7`（rev2，计划 v10，V10-3）。
> 执行时间 2026-10-27 16:34–16:40 UTC+8（08:34–08:40Z）。
> **未装依赖、未代填凭据、未读取/输出 cookie 值、未放宽断言、未改期望值。**

## 1. 代码改动（diff 摘要）

### 1.1 `tools/selection/access/browser.py`

| 行 | 改动 |
| --- | --- |
| `:13-15` | 新增 `import asyncio`、`import inspect` |
| `:156-176` | `_eval` 改为 **`async def`**：依次解析目标为 `browser`（若有 `evaluate`）→ `browser.tab` → **`browser.main_tab`**（真实 nodriver `Browser` 只有 `main_tab`，无 `evaluate`/`tab`）；对返回值 `inspect.isawaitable(...)` 则 `await`，兼容同步 fake |
| `:74-76` | `wait_for_login` 改为 **`async def`** |
| `:110-127` | 循环内改为 `await _eval(...)` 三处；`_sleep` 改为 `await _sleep(...)` |
| `:166-173` | `_sleep` 改为 **`async def`**：注入 clock 带 `advance` 时仍走 `advance`（保持可测），否则 `await asyncio.sleep` |

### 1.2 `tools/selection/access/zhihu.py`

| 行 | 改动 |
| --- | --- |
| `:16` | 新增 `import asyncio` |
| `:518-520` | `_login_with_real_browser` 内改为 **`await browser_mod.wait_for_login(...)`**（不再在事件循环里同步调用） |
| `:497-500` | `login()` 的 fake-browser 分支改为 `asyncio.run(browser_mod.wait_for_login(...))`，保持 CLI 同步入口不变 |

- 五态语义（ok/risk/poll_limit/timeout/unknown）、`charge_poll` 独立配额、risk 即锁、`final_url` 脱敏均未改动。

## 2. 测试改动（`tests/test_access_zhihu.py`）

| 行 | 改动 |
| --- | --- |
| `:9-14` | 新增 `import asyncio`、`import inspect` |
| `:120-127` | `FakeBrowser.evaluate` 改为 **`async def`**（与真实 nodriver 签名一致） |
| `:505-566` | 5 处 `wait_for_login(...)` 调用改为 `asyncio.run(browser_mod.wait_for_login(...))` |
| 新增 `test_fake_evaluate_is_async_like_nodriver` | `inspect.iscoroutinefunction(FakeBrowser.evaluate)` 为真 |
| 新增 `test_wait_for_login_is_async` | `inspect.iscoroutinefunction(browser_mod.wait_for_login)` 为真 |
| 新增 `test_eval_awaits_coroutine_and_sync_values` | `_eval` 对 async 与 sync 两种 `evaluate` 都能取值（直接覆盖本次 bug） |

## 3. 测试结果（真实 exit）

| 套件 | 结果 |
| --- | --- |
| `tests.test_access_budget` + `tests.test_access_zhihu` | **75 tests OK**（原 72 + 3 新增） |
| 全项目 `unittest discover -s tests -t .` | **505 tests OK** |

- cwd `D:\桌面\two`，解释器 `.venv\Scripts\python.exe`；exit 0。

## 4. login 真跑（一次）

| 项 | 值 |
| --- | --- |
| argv | `C:\Users\19183\.dsh\tools\x-collect\venv\Scripts\python.exe -m tools.selection.access.zhihu --state-dir docs\validation\v10\zhihu\runtime_login2 --profile C:\Users\19183\.dsh\tools\zhihu-collect\profile login --timeout 300` |
| cwd / PYTHONPATH | `D:\桌面\two` / `D:\桌面\two` |
| started_utc / finished_utc | **2026-10-27T08:39:39Z** / **08:39:53Z** |
| **exit** | **5** |
| status | **`risk`** |
| polls | **2** |
| elapsed_s | 3.895 |
| final_url | `https://www.zhihu.com/signin`（脱敏） |
| signed_in | false |
| **risk_reason** | **`text:验证码`** |
| 窗口 | 进程在 14s 内已退出；**未形成可交互窗口** |

stdout 原文：
```json
{"command":"login","elapsed_s":3.895,"exit":5,"final_url":"https://www.zhihu.com/signin",
 "polls":2,"risk_reason":"text:验证码","signed_in":false,"status":"risk","stop_reason":null}
```

- **async 缺陷已修复的正面证据**：`polls=2`、`final_url=https://www.zhihu.com/signin`、`elapsed_s=3.895` —— 说明浏览器真的启动、导航到登录页、并成功执行了 `location.href` 与页面文本读取（旧版是 polls=1、elapsed 0.006、`browser_error:RuntimeError`）。
- **但登录窗口被 risk 判定立即关闭**：`RISK_MARKERS`（`zhihu.py`）包含“验证码”，而知乎 `/signin` 页正常文案即含“验证码”，`detect_risk` 命中 `text:验证码` → `status=risk`、`exit=5`、`budget.lock(..., source="login")`，用户来不及扫码。

## 5. doctor（login 后）

```json
{"profile_exists":true,"cookie_db_exists":true,"cookie_count":0,
 "cookie_names":{"SESSIONID":false,"__zse_ck":false,"_xsrf":false,
                 "d_c0":false,"q_c1":false,"z_c0":false},
 "online":"unverified","exit":0}
```
- 仍未登录（cookie 全 false、cookie_count=0）；只记布尔。

## 6. 结论与待决定

- **async/sync 缺陷已修复并通过测试**（75 + 505 OK，含 3 个守护测试）。
- **login 仍未能让用户完成扫码**：不是 async 问题，而是**登录页文案触发风控判定**——`RISK_MARKERS` 的“验证码”在 `/signin` 正常页面即出现，导致 `status=risk` 立即锁停。
- 这需要产品层决策（不属于本次“只修 async”范围，未擅自改动）：
  - A) 登录流程改用独立的“登录页专用判定”（例如只看 `安全验证/访问异常/操作频繁` 等墙类标记，或仅在非 `/signin` 路径应用“验证码”标记）；
  - B) 登录期间忽略 risk 文本、仅依赖 `SIGNED_IN_JS` + 超时；
  - C) 保持现状，接受无法在此环境扫码登录。
- 本轮**未改** `RISK_MARKERS`/`detect_risk`（超出授权范围），交策划者决定。

## 7. 证据

- `login_run4.out.txt` / `login_run4.err.txt`（stderr 仅 asyncio 收尾告警）、`login_run4.pid`（PID 87736 已退出）
- `login_doctor_post3.out.txt`
- `docs/validation/v10/zhihu/_repro_eval.py`（只读复现脚本，证明 `Browser` 无 `evaluate`/`tab`、有 `main_tab`）
- 未重试、未重开窗口、未装依赖、未代填、未读 cookie 值。
