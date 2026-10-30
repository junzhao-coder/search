# weibo-rpa-1 首次真实验证：执行记录（登录超时，未跑搜索）

- 时间：2026-10-30T05:27:30Z 起（UTC，下同）；cwd `D:\桌面\two`；解释器 `C:\Users\19183\.dsh\tools\x-collect\venv\Scripts\python.exe`。
- 结果一句话：**授权成功、可见窗口已开、桌面证据成立；但 150s 内未检测到登录态（`verdict=unknown`/`stop=login_timeout`/exit 11），按指令停止，未执行搜索；账本剩 1 次，300s 窗口在 05:32:30Z 关闭。**

## 1. 授权（固定权威账本，只读复核）

命令（2026-10-30T05:27:30Z，exit 0）：

```python
pb.open_default().authorize_batch('weibo-rpa-1', authorized_calls=4, window_seconds=300.0,
    records_cap=5, source='user:consent:new-batch',
    note='2 次历史登录追认(seed，代码强制，非新调用) + login 1 + live-search 1；真实新增导航 2 次',
    seed_from=('login-window-1','login-window-2'))
```

复核字段（`logs/step1-authorize.json`）：

| 字段 | 值 |
| --- | --- |
| `authorized_calls` | **4** |
| `seed_used` / `seed_source` | **2** / `history:uncharged_navigation` |
| `used` / `remaining` | 2 / **2**（授权时刻） |
| `records_cap` / `window_seconds` | 5 / 300.0 |
| `window` | 05:27:30Z → **05:32:30Z** |
| `source` / `note` | `user:consent:new-batch` / 见上（含"2 次历史登录追认(seed，代码强制，非新调用)"） |

**口径**：账本 4 次 = **2 次历史登录追认（seed，代码强制，不是新调用）** + login 1 + live-search 1；**真实新增导航应为 2 次**（本次实际只发生了 1 次：login）。

## 2. login（可见窗口，桌面证据，未截图）

| 项 | 值 |
| --- | --- |
| argv | `python -X utf8 -m tools.selection.rpa login --batch-id weibo-rpa-1 --timeout 150 --no-confirm` |
| 开始 UTC | 2026-10-30T05:27:30Z（紧跟授权，无空档） |
| exit / stop / status | **11** / `login_timeout` / `timeout` |
| `login_state.verdict` | **unknown**（`final_url=https://passport.weibo.com/sso/signin`，`http_status=200`，`text_len=96`） |
| polls / window_closed | 76 / **true** |
| `browser_started` / `headless` | true / false |
| `desktop.proven` / `foreground_matched` | **true** / **true**（`foreground_before=after=1313550`，`matched_by=pid`） |
| `desktop.window_rect` | 1557×1490 @ (24,15)，`dwm_extended_frame_bounds`，DPI aware |
| `desktop.desktop_screenshot` | **null**（真实页面禁止自动截图） |
| `cookie_values_read` | **false** |
| `result_persisted` | true |

原始输出：`logs/step2-login.json`。

## 3. 账本事件与剩余（只读复核，05:30:23Z）

| 事件 | UTC | source | detail |
| --- | --- | --- | --- |
| `active_nav`（预扣） | 2026-10-30T05:27:31Z | `rpa.login` | `login` |
| `active_nav_result` | 2026-10-30T05:30:03Z | `rpa.login` | `failed` |
| （历史）`search` / `search_result` | 2026-10-29T14:46:02Z / 14:46:06Z | `weibo.search` / `weibo.result` | 上一批 |

`used=3 / authorized=4`、**`remaining=1`**、`records_reserved=0`、`locked=false`（无锁）。
窗口：`05:27:30Z → 05:32:30Z`；05:30:23Z 复核时仍开，**05:32:30Z 关闭**。

## 4. 本次到底拿到了什么（严格区分）

| 类别 | 结论 |
| --- | --- |
| 读到正文 | **没有**（未执行搜索） |
| 只拿到链接 | **没有**（未执行搜索） |
| 被拦（403/429/墙词/锁） | **没有**：登录页 `http_status=200`，无锁，`lock_reason=null` |
| 未知 | **登录态未知**：页面停在 `passport.weibo.com/sso/signin`，150s 内没检测到 logout 控件 |

按你的规则：`verdict=timeout/unknown` → **不跑搜索**，避免把最后 1 次烧在可能撞墙的请求上；保留 `remaining=1` 供你决定下一步。

## 5. 本轮明确没做的事

1. 未执行 `live-search`（不重试、不换词、不追加额度）；
2. 未重开登录窗口、未延长 timeout；
3. 未读/打印 cookie 或 token 值；未对真实页面截图；
4. 未改账本补额度、未改业务库/CSV/契约/小红书、未提交 git。

## 6. 下一步（需要你决定）

- 账本还有 **1 次**，但 `weibo-rpa-1` 的 300s 窗口已于 05:32:30Z 关闭；**同 id 重新 authorize 相同参数只会返回既有行，不会刷新窗口**，要用掉这 1 次必须**新 batch id + 新授权**（或由你确认放弃）。
- 若再次尝试登录：建议把登录窗口与搜索拆成两次授权（登录 1 次 + 搜索 1 次），避免"登录超时就把搜索额度留在过期窗口里"。
- 若直接搜索：登录态未证实，可能撞登录墙并触发锁；届时按"风险即停"处理，不重试。

## 7. 待办（本轮不动）

新批次重复追认同一批历史登录（`seed_from`）会造成跨批次重复计费，这是 `platform_budget` 的既有设计问题，后续单独修。
