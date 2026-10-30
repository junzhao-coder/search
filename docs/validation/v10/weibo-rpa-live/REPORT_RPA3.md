# weibo-rpa-3 执行记录（可见性闸门误判：窗口标题异步竞态，已修）

- 时间：2026-10-30T06:02:04Z 起（UTC）；cwd `D:\桌面\two`；解释器 `C:\Users\19183\.dsh\tools\x-collect\venv\Scripts\python.exe`。
- 一句话：**批次创建成功、login 已启动，但新加的可见性闸门在"页面标题已变、OS 窗口标题还没刷新"的竞态下误判，exit 12 立即退出；用户没得到扫码机会。该竞态已修复并验证。批次 1 次登录额度已被这次误判消耗，未重试、未搜索。**

## 1. 授权（固定权威账本，只读复核）

| 字段 | 值 |
| --- | --- |
| `batch_id` | `weibo-rpa-3` |
| `authorized_calls` | **3** |
| `seed_used` / `seed_source` | **2** / `history:uncharged_navigation` |
| `used` / `remaining`（授权时刻） | 2 / **1** |
| `records_cap` / `window_seconds` | 5 / 300.0 |
| 窗口 | 06:02:04Z → **06:07:04Z** |
| `source` / `note` | `user:consent:new-batch-3` / `2 次历史追认 + login 1；本轮只验证登录可见性，不搜索；用户选择先只跑登录` |

原始输出：`logs/step6-authorize-rpa3.json`。

## 2. login（可见窗口，exit 12）

| 项 | 值 |
| --- | --- |
| argv | `python -X utf8 -m tools.selection.rpa login --profile C:\Users\19183\.dsh\tools\weibo-collect\profile --batch-id weibo-rpa-3 --timeout 240 --no-confirm` |
| 开始 UTC | 2026-10-30T06:02:04Z（与授权同秒） |
| exit / stop | **12** / `window_showing_other_tab` |
| 判定依据（stderr 原文） | `[rpa] 可见性前提不成立：window_showing_other_tab；窗口标题='新标签页 - Google Chrome' 页面标题='登录 - 微博'；不等待扫码。` |
| `desktop.page_title` | `登录 - 微博`（页面已经就绪） |
| `desktop.window_title` | `新标签页 - Google Chrome`（**OS 标题还没追上**） |
| `desktop.window_title_matches_page` | false（→ 闸门拦截） |
| `desktop.activation` | `{"activated": true, "method": "tab.activate"}` |
| `desktop.foreground_matched` / `window_rect` | true / 1557×1490 @ (24,15) |
| `desktop.desktop_screenshot` | null（真实页面不截图） |
| `polls` | 0（**没有进入扫码等待**） |

原始输出：`logs/step7-login-rpa3.json`。

## 3. 根因（真 bug，已修）

Chrome 更新 **OS 窗口标题是异步的**：`document.title` 先变成 `登录 - 微博`，窗口标题还停在
`新标签页 - Google Chrome`（通常几十~几百毫秒后才刷新）。上一轮（weibo-rpa-2）窗口标题恰好已经刷新，所以闸门通过；
本轮在标题刷新的**同一瞬间**取了证据，闸门按"非 true 即拦"直接 exit 12 —— 属于**假阴性**。

**修复**（`tools/selection/rpa`，本轮已落盘）：

| 位置 | 变更 |
| --- | --- |
| `desktop.title_contains(window, page)` | 纯函数：页面标题是否为窗口标题子串（任一为空 → None） |
| `desktop.wait_title_match(hwnd, page_title, attempts=15, interval=0.2)` | 只读轮询 `GetWindowTextW` 最多 ~3s，返回 `{window_title, matched, waited_ms, polls}`；不抢焦点 |
| `cli._settle_window_title(desktop)` | 已匹配直接返回；否则等标题追上，把 `window_title/window_title_matches_page/title_wait` 回填后再交给闸门 |
| `cli.cmd_login` / `cmd_live_search` | 在 `_visibility_gate` 之前调用 `_settle_window_title` |
| `session.title_consistency` | 改为复用 `desktop.title_contains`，两处判定同一实现 |

**行内验证**（`logs/settle-title-verify.log`，exit 0）：

| case | 结果 |
| --- | --- |
| `already_matched` | `wait_called=false`、gate 放行（null） |
| `stale_then_match` | 以 hwnd=134016 轮询，220ms 后匹配、`matched=true`、gate 放行 |
| `never_match` | 3s 仍不匹配 → `matched=false`、gate 返回 `window_showing_other_tab`（仍会拦真错页） |

回归：`window_title_check` exit 0（标题一致性仍成立）；既有四套全量 **335 tests OK**（未改期望值，`logs/tests-all-settle.log`）。
说明：本轮 scope 不含 `tests/`，所以竞态用例是用行内脚本验证的，没有新增单测文件；建议下轮把这三条固化成 `tests/test_selection_rpa.py` 用例。

## 4. 账本与剩余

| 事件 | UTC | source | detail |
| --- | --- | --- | --- |
| `active_nav`（预扣） | 2026-10-30T06:02:04Z | `rpa.login` | `login` |
| `active_nav_result` | 2026-10-30T06:02:05Z | `rpa.login` | `failed` |

`used=3 / authorized=3`、**`remaining=0`**、`records_reserved=0`、`locked=false`；窗口 06:02:04Z→06:07:04Z（06:03:47Z 复核时仍开）。

## 5. 本轮做了什么 / 没做什么

- 做了：授权、启动可见窗口、激活标签页、桌面证据、置顶与夺回（`topmost_set` 在 `keepalive_start`）、闸门判定、如实退出。
- **没做**：没有让用户扫码（闸门在等待前就退了）、没有 `live-search`（按验收 3）、没有重试/重开窗口/追加额度、没有读 cookie、没有对真实页面截图、没有改账本补额度。

## 6. 下一步（需决定）

1. 本轮额度已用尽（3/3，窗口 06:07:04Z 关闭），**登录可见性仍未真正验证**（用户没看到扫码界面）。
2. 修复已就位；下一批（如 `weibo-rpa-4`，`authorized_calls=3` = 2 seed + 1 login）重跑同一条 login 命令即可，
   预期不再出现假阴性：即使 OS 标题滞后，也会在 ~3s 内追上并通过闸门。
3. 若希望更稳妥：把 `--timeout 240` 保持，并在窗口出现后由我口头提示"现在可以扫码"（本轮没有机会）。
