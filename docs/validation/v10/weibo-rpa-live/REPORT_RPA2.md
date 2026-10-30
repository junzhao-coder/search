# weibo-rpa-2 执行记录（登录页已正确显示，但 150s 内未完成扫码）

- 时间：2026-10-30T05:39:35Z 起（UTC）；cwd `D:\桌面\two`；解释器 `C:\Users\19183\.dsh\tools\x-collect\venv\Scripts\python.exe`。
- 一句话：**可见性缺陷已修复并在真实运行中生效**（窗口标题=登录页标题），但用户在 150s 内未完成扫码，`verdict=unknown`/`exit 11`，按规则**未执行搜索**；账本剩 1 次，窗口 05:44:35Z 关闭。

## 1. 授权（固定权威账本，只读复核）

| 字段 | 值 |
| --- | --- |
| `batch_id` | `weibo-rpa-2` |
| `authorized_calls` | **4** |
| `seed_used` / `seed_source` | **2** / `history:uncharged_navigation` |
| `used` / `remaining`（授权时刻） | 2 / **2** |
| `records_cap` / `window_seconds` | 5 / 300.0 |
| 窗口 | 05:39:35Z → **05:44:35Z** |
| `source` / `note` | `user:consent:new-batch-2` / `2 次历史追认 + login 1 + live-search 1；真实新增导航 2 次；用户本轮再次授权` |

## 2. login（可见窗口，真实运行）

| 项 | 值 |
| --- | --- |
| argv | `python -X utf8 -m tools.selection.rpa login --profile C:\Users\19183\.dsh\tools\weibo-collect\profile --batch-id weibo-rpa-2 --timeout 150 --no-confirm` |
| 开始 UTC | 2026-10-30T05:39:35Z（与授权同秒，无空档） |
| exit / stop / status | **11** / `login_timeout` / `timeout` |
| `login_state.verdict` | **unknown**（`final_url=https://passport.weibo.com/sso/signin`，`http_status=200`，`text_len=96`） |
| `polls` / `window_closed` / `result_persisted` | 76 / true / true |
| **`desktop.window_title`** | **`登录 - 微博 - Google Chrome`** |
| **`desktop.page_title`** | **`登录 - 微博`** |
| **`desktop.window_title_matches_page`** | **true** ✅（上一批的"空白新标签页"缺陷已消失） |
| `desktop.activation` | `{"activated": true, "method": "tab.activate", "error": null}` |
| `desktop.foreground_matched` / `window_rect` | true / **1557×1490 @ (24,15)** |
| `desktop.desktop_screenshot` | null（真实页面不截图） |
| `profile` / `profile_exists` / `profile_source` / `profile_matches_expected` | `C:\Users\19183\.dsh\tools\weibo-collect\profile` / true / `default` / false（与 `docs/.../weibo-login/profile` 不同，已显式报出） |

原始输出：`logs/step4-login-rpa2.json`；授权：`logs/step3-authorize-rpa2.json`。

## 3. 账本事件与剩余（05:42:16Z 只读复核）

| 事件 | UTC | source | detail |
| --- | --- | --- | --- |
| `active_nav`（预扣） | 2026-10-30T05:39:35Z | `rpa.login` | `login` |
| `active_nav_result` | 2026-10-30T05:42:07Z | `rpa.login` | `failed` |

`used=3 / authorized=4`、**`remaining=1`**、`records_reserved=0`、`locked=false`；窗口 05:39:35Z→**05:44:35Z**。

## 4. 未执行搜索（按规则）

`verdict=unknown` → 不跑 `live-search`：不重试、不换词、不重开窗口、不追加额度。因此本轮**没有**读到正文、也没有拿到链接，也不是被拦（登录页 200、无锁、无墙词）。

| 类别 | 结论 |
| --- | --- |
| 读到正文 | 没有（未搜索） |
| 只拿到链接 | 没有（未搜索） |
| 被拦 | 没有 |
| 未知 | **登录态未知**：窗口确实显示登录页（标题一致、前台匹配），但 150s 内未检测到登录完成 |

## 5. 与上一批的关键差异

| 项 | weibo-rpa-1（05:27Z） | weibo-rpa-2（05:39Z） |
| --- | --- | --- |
| `window_title` | `新标签页 - Google Chrome` ❌ | `登录 - 微博 - Google Chrome` ✅ |
| `window_title_matches_page` | 不存在该字段（旧代码） | **true** |
| `activation` | 未激活 | `tab.activate` |
| 结果 | 用户看不到登录页 | **登录页可见**，但未在 150s 内扫码 |

## 6. 下一步（需决定）

- 账本仍剩 1 次，但 `weibo-rpa-2` 的 300s 窗口在 05:44:35Z 关闭；同 id 重新授权不刷新窗口 → 要用掉这 1 次需**新 batch id + 新授权**。
- 登录页已经能正确显示；若再次尝试，建议：①把 `--timeout` 调到接近窗口上限（如 240s）并在你确认"已打开手机扫码页"后再启动；②或先只做 login（1 次）确认登录态，再单独授权 1 次搜索，避免"登录超时把搜索额度留在过期窗口"。

## 7. 未做

未读/打印 cookie 或 token 值；未对真实页面截图；未改账本补额度；未改业务库/CSV/契约/小红书；未提交 git。
