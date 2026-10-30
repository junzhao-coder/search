# V10-3 修复报告：登录页 risk 误判 + poll 配额，login 真跑成功（ok/exit 0）

> 任务 `task-8b3ffad73b811ccc1c332511bef6ec60`（rev2，计划 v10，V10-3）。
> 执行时间 2026-10-27 16:42–16:49 UTC+8（08:42–08:49Z）。
> **未装依赖、未代填凭据、未读取/输出 cookie 值、未放宽其他断言、未改五态语义与预算逻辑。**

## 1. 判定改动（登录路径 vs 非登录路径）

### 1.1 `tools/selection/access/zhihu.py`

| 行 | 改动 |
| --- | --- |
| `:41-43` | `RISK_MARKERS` **保持不变**（非登录场景语义不变，仍含“验证码”） |
| `:45-51`（新增） | 新增 `LOGIN_WALL_MARKERS = ("安全验证","访问异常","操作频繁","请求过于频繁","unhuman","系统检测到","captcha")`——**不含“验证码”**，注释说明 `/signin` 正常文案即含“获取验证码/短信验证码” |
| `:117-130`（新增） | 新增 `detect_login_wall(text)`：仅用 `LOGIN_WALL_MARKERS` 扫描，返回 `text:<marker>` 或 None |
| `detect_risk` / `html_risk` | **未改动**，search/detail/comments 行为完全不变 |

### 1.2 `tools/selection/access/browser.py`

| 行 | 改动 |
| --- | --- |
| `:18-19` | 新增 `from .budget import polls_for_window` |
| `:92-97` | `limit = max_polls if 显式传入 else max(budget.max_polls, polls_for_window(timeout, poll))` |
| `:99-124` | 循环：先判 `timeout`；`polls >= limit` → `poll_limit`；`charge_poll` 若 `polls_exhausted` 则继续等待（保持窗口）而非提前关闭；`batch_locked`/写失败仍返回 6 |
| `:129-141` | **已登录优先**：`signed_in` 判定放在 risk 之前，已登录直接 `stop_reason="signed_in"` |
| `:142-146` | risk 判定改用 `_login_wall_of(...)` → `detect_login_wall`（不再走 `detect_risk`） |
| `:162-165`（新增） | `_login_wall_of(text)` 包装 `detect_login_wall` |
| `:150-158` | `poll_limit` 与 `timeout` 分支恢复/保留，各自 exit 12 / 11 |

### 1.3 `tools/selection/access/budget.py`

| 行 | 改动 |
| --- | --- |
| `:33-45` | `MAX_POLLS` 10 → **120**；新增 `polls_for_window(timeout, poll) = max(MAX_POLLS, ceil(timeout/poll)+5)`（300/3 → 105 → 取 120） |
| 注释 | 说明 poll 配额是**记账护栏**、不是墙钟上限；固定 10 会在 ~30s 关窗 |

- poll 计数仍独立于 active call（`charge_poll` 独立配额）、仍写 ledger、仍受 batch 锁约束（`batch_locked` → exit 6）。

## 2. 新增/修改测试（`tests/test_access_zhihu.py`）

| 测试名 | 断言 |
| --- | --- |
| `test_signin_copy_is_not_a_wall` | `/signin` 含“获取验证码/短信验证码” → `detect_login_wall` 返回 None；轮询结果 **非 risk**、`risk_reason=None`、exit≠EXIT_RISK |
| `test_real_wall_still_locks_login` | “安全验证”/“访问异常” → 判 risk；`budget.locked=true`、`lock_source=login` |
| `test_signed_in_wins_over_captcha_copy` | 已登录 + 页面含“验证码 安全验证” → `status=ok`、`risk_reason=None`、exit 0 |
| `test_detect_risk_unchanged_for_non_login` | `detect_risk("获取验证码")="text:验证码"`、`"请登录后查看"` 命中、普通正文 None（回归保护） |
| `test_poll_quota_covers_full_window` | `polls_for_window(300,3)>=100`、`MAX_POLLS==120` |
| `test_poll_limit_is_its_own_nonzero_exit`（保留） | 显式 `max_polls=2` → `stop_reason=poll_limit`、exit 12、polls=2 |

- 原有 5 处 `wait_for_login` 调用已改 `asyncio.run(...)`（上一轮 async 修复时完成），本轮未放宽任何断言。

## 3. 测试真实结果

| 套件 | 结果 |
| --- | --- |
| `tests.test_access_zhihu.LoginTests` | **15 tests OK** |
| `tests.test_access_budget` + `tests.test_access_zhihu` | **80 tests OK** |

- cwd `D:\桌面\two`，解释器 `.venv\Scripts\python.exe`；exit 0。

## 4. login 真跑（成功）

| 项 | 值 |
| --- | --- |
| argv | `C:\Users\19183\.dsh\tools\x-collect\venv\Scripts\python.exe -m tools.selection.access.zhihu --state-dir docs\validation\v10\zhihu\runtime_login4 --profile C:\Users\19183\.dsh\tools\zhihu-collect\profile login --timeout 300` |
| cwd / PYTHONPATH | `D:\桌面\two` / `D:\桌面\two` |
| started_utc / finished_utc | **2026-10-27T08:47:08Z** / **08:48:37Z** |
| **exit** | **0** |
| **status** | **`ok`** |
| **signed_in** | **true** |
| stop_reason | **`signed_in`** |
| polls | **26** |
| elapsed_s | **75.579** |
| final_url | `https://www.zhihu.com/`（脱敏） |
| risk_reason | null |
| Python PID / Chrome PID | 88816 / 90140（窗口标题「知乎 - 有问题，就会有答案 - Google Chrome」，handle 722816，Responding=True；用户扫码后正常关闭） |

stdout 原文（`docs/validation/v10/zhihu/login_run6.out.txt`）：
```json
{"command":"login","elapsed_s":75.579,"exit":0,"final_url":"https://www.zhihu.com/",
 "polls":26,"risk_reason":null,"signed_in":true,"status":"ok","stop_reason":"signed_in"}
```

- **窗口确实保持打开**：08:47:08Z 启动 → 08:48:37Z 因检测到已登录而正常结束，存活 **75.6 秒**（远超上一版 30.6 秒的 poll_limit 截断；若用户未登录会继续到 300s timeout）。
- 启动后 10 秒内即已 `flow_send(wake=true)` 告知策划者 PID/标题/handle/超时点。

## 5. doctor（login 后，只记布尔）

```json
{"command":"doctor","cookie_count":20,"cookie_db_exists":true,
 "cookie_names":{"SESSIONID":true,"__zse_ck":false,"_xsrf":true,
                 "d_c0":true,"q_c1":false,"z_c0":false},
 "exit":0,"network":"none","online":"unverified","profile_exists":true}
```
- `cookie_count=20`，`SESSIONID/_xsrf/d_c0=true`；`online=unverified` 是设计（cookie 名不等于在线态）；真实登录态由 `SIGNED_IN_JS` 判定为 true。
- 未读取/输出任何 cookie 值。

## 6. 结论

- **登录页 risk 误判已修**：`/signin` 的“获取验证码/短信验证码”不再触发 risk；真墙（安全验证/访问异常/操作频繁/captcha）仍锁停。
- **已登录优先**：先判 `SIGNED_IN_JS`，已登录即使页面含风险词也判 ok。
- **poll 配额已解耦**：`MAX_POLLS=120` + `polls_for_window()`，窗口可撑满 300s；`poll_limit`(12) 与 `timeout`(11) 仍区分。
- **login 真跑成功**：`status=ok / exit=0 / signed_in=true`，用户已完成扫码登录，profile 已落盘。
- 非登录场景（search/detail/comments）的 `detect_risk`/`html_risk` 未改动。

## 7. 限制

- 仅 1 次成功登录（单账号、单 profile）；未验证多账号/长期会话有效性。
- doctor 的 `online=unverified` 不代表失败；真实在线态需后续 authenticated-browser 请求验证。
- 未做登录后的真实搜索/详情调用（需另派任务，且要遵守预算）。
- `polls_for_window` 为纯函数，已由单测覆盖；未做 300s 全窗口的真实超时跑（用户已登录提前结束）。
