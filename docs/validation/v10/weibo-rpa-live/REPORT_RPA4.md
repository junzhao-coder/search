# weibo-rpa-4 执行记录（标题竞态已固化单测；窗口保持可见，登录态仍 unknown）

- 时间：2026-10-30T06:06:46Z 起（UTC）；cwd `D:\桌面\two`；解释器 `C:\Users\19183\.dsh\tools\x-collect\venv\Scripts\python.exe`。
- 一句话：**竞态三条用例已进单测（104/339 全绿）；weibo-rpa-4 登录窗口置顶并在 240s 内被夺回前台 11 次、标题一致性 202ms 内成立 —— 用户这次确实有机会看到并扫码；但登录控件未被检测到（verdict=unknown），按规则未搜索。**

## 1. 单测（先做，离线）

`tests/test_selection_rpa.py` 新增 `WindowTitleSettleTests`（fake/duck-typed，不依赖真实桌面）：

| 用例 | 断言 |
| --- | --- |
| `test_already_matched_does_not_wait` | 窗口标题已含页面标题 → `wait_title_match` **不被调用**、`_visibility_gate` 返回 `None` |
| `test_stale_then_match_waits_and_passes` | 旧标题 → `wait_title_match(hwnd, page_title)` 被调用，返回 `matched=True/waited_ms=220` → gate 放行 |
| `test_never_match_is_blocked` | 始终不匹配 → gate 返回 `window_showing_other_tab` |
| `test_title_contains_pure_function` | `desktop.title_contains` 的 true/false/None 三态 |

结果：`tests.test_selection_rpa` **Ran 104 / OK / exit 0**（`logs/tests-rpa-rpa4.log`）；
四套全量 **Ran 339 / OK / exit 0**（`logs/tests-all-rpa4.log`）；**无跳过**。

## 2. 授权（06:06:46Z，exit 0，`logs/step8-authorize-rpa4.json`）

| 字段 | 值 |
| --- | --- |
| `batch_id` | `weibo-rpa-4` |
| `authorized_calls` | **3**（2 seed + login 1） |
| `seed_used` / `seed_source` | **2** / `history:uncharged_navigation` |
| `used` / `remaining`（授权时刻） | 2 / **1** |
| `records_cap` / `window_seconds` | 5 / 300.0 |
| 窗口 | 06:06:46Z → **06:11:46Z** |
| `note` | `2 次历史追认 + login 1；重跑被窗口标题竞态误拦的登录验证；用户此前选择先只跑登录` |

## 3. login（06:06:46Z 同秒启动，`logs/step9-login-rpa4.json`）

| 项 | 值 |
| --- | --- |
| argv | `python -X utf8 -m tools.selection.rpa login --profile C:\Users\19183\.dsh\tools\weibo-collect\profile --batch-id weibo-rpa-4 --timeout 240 --no-confirm` |
| exit / stop / status | **11** / `login_timeout` / `timeout` |
| `login_state.verdict` | **unknown** |
| `login_state.final_url` / `http_status` / `text_len` | **https://weibo.com/** / 200 / 990 |
| `polls` / `window_closed` / `result_persisted` | 121 / true / true |
| `desktop.page_title` | `登录 - 微博` |
| `desktop.window_title` | `登录 - 微博 - Google Chrome` |
| **`desktop.window_title_matches_page`** | **true** |
| `desktop.title_wait` | `{"matched": true, "polls": 2, "waited_ms": 202, "hwnd": 2624166}` ← 竞态修复生效 |
| **`desktop.topmost_set`** | **true**（`exstyle=2097416`，含 `0x8`） |
| `desktop.foreground_matched` / `window_rect` | true / **1557×1491 @ (24,15)** |
| `desktop.desktop_screenshot` | null（真实页面不截图） |
| `keepalive.ticks` / **`reassert_count`** / `reassert_failures` | 121 / **11** / **0** |
| `keepalive.still_foreground_at_end` / `topmost_cleared` | **true** / **true** |

**这组数字说明**：窗口全程置顶；期间被别的窗口抢走前台 **11 次**，每次都被夺回且 0 次失败 —— 即使用户在跟聊天窗口交互，登录窗口也会持续回到最前。这次不存在"根本没看到窗口"的问题。

## 4. 登录态判定（不夸大）

- 页面从 `passport.weibo.com/sso/signin` 跳到了 **`https://weibo.com/`**，这**可能**意味着扫码已完成；
- 但 `SIGNED_IN_JS`（logout 控件）在 240s 内**始终没有命中**，所以 `verdict=unknown`、`exit 11`；
- 按规则：**不执行搜索、不重试、不重开窗口、不追加额度**。

## 5. 账本（06:11:01Z 只读）

| 事件 | UTC | source | detail |
| --- | --- | --- | --- |
| `active_nav`（预扣） | 2026-10-30T06:06:47Z | `rpa.login` | `login` |
| `active_nav_result` | 2026-10-30T06:10:50Z | `rpa.login` | `failed` |

`used=3 / authorized=3`、**`remaining=0`**、`records_reserved=0`、`locked=false`；窗口 06:06:46Z→06:11:46Z。

## 6. 分类

| 类别 | 结论 |
| --- | --- |
| 窗口可见（能看到登录页） | **是**：topmost=true、标题一致（202ms 内）、11 次夺回、0 失败 |
| 登录成功 | **未证实**：logout 控件未命中，虽然页面停在 weibo.com |
| 读到正文 / 拿到链接 | 没有（本轮不搜索） |
| 被拦 | 没有（http 200、无锁、无墙词） |

## 7. 下一步（需决定）

1. 本轮额度已尽（3/3），窗口 06:11:46Z 关闭。
2. 如果你**确实已经扫码登录成功**：profile 里的会话可能已就绪，下一批只需 **1 次搜索**（因 seed 规则，批次仍要写 `authorized_calls=3` = 2 seed + 1 search），直接 `live-search` 即可；但登录态在采集侧仍属**未证实**，可能撞墙。
3. 若想先把登录态确认清楚：再开一批（3 次 = 2 seed + 1 login）重跑 login，或把 `SIGNED_IN_JS` 的判定放宽（例如同时认 `a[href*='/u/']`/「我的主页」等可见控件）——这属于代码改动，需要单独立项。

## 8. 未做

未读/打印 cookie 值；未对真实页面截图；未执行 `live-search`；未重试/重开窗口/追加额度；未改账本补额度；未改业务库/CSV/契约/小红书；未提交 git。
