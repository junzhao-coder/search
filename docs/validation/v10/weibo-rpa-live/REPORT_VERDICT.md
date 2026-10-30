# weibo-rpa-4 登录判定复核（只读 doctor + cookie 元数据 + 放宽判定）

- 时间：2026-10-30T06:14–06:18Z（UTC）；cwd `D:\桌面\two`；解释器 `C:\Users\19183\.dsh\tools\x-collect\venv\Scripts\python.exe`。
- 本轮**零网络、零额度**：只读 doctor、只读 cookie 元数据、离线单测。未读/打印任何 cookie 值，未改账本。

## 1. 结论（一句话）

**weibo-rpa-4 的登录已经成功落地**：服务端在 **2026-10-30T06:08:00–06:08:01Z**（登录窗口 06:06:46Z→06:11:46Z 之内）下发了 `SUB / SUBP / SCF / SSOLoginState / ALF / WBPSESS` 等会话 cookie，页面随后停在 `https://weibo.com/`、标题变成微博首页、正文 96→990 字。
之前 `verdict=unknown` 是**判定器假阴性**（只认 `a[href*="/logout"]`），不是登录失败。
（"当前是否仍有效"仍需一次带会话的请求才能确认，本轮零网络，未验证。）

## 2. 只读 doctor（`weibo doctor`，2026-10-30T06:14:05Z，exit 0，`logs/doctor-weibo.log`）

| 项 | 值 |
| --- | --- |
| `profile` / `profile_exists` | `C:\Users\19183\.dsh\tools\weibo-collect\profile` / **true** |
| `cookie_db_exists` / `cookie_count` | true / **9**（doctor 只统计 `COOKIE_NAMES` 白名单内的名称） |
| `online` / `network` | `unverified` / `none`（doctor 不联网） |
| cookie 名称布尔 | `SUB=true`、`SUBP=true`、`SSOLoginState=true`、`XSRF-TOKEN=true`；`SCL/SUHB/_T_WM=false` |
| profile 文件数 / 最近修改 | **581** 个文件 / `2026-10-30 14:10:50`（本地，= 06:10:50Z，正是那次登录结束时刻） |

doctor 明确写着："cookie names only; presence is not proof of a valid session" —— 所以只靠名称布尔还不够，下面是时间戳。

## 3. cookie **元数据**（只读，不含值；`checks/cookie_metadata.py`，`logs/cookie-metadata.log`）

只读 `Default/Network/Cookies` 的 `name/host/creation_utc/last_access_utc/expires_utc/is_persistent`，**没有读取 value 列**（脚本里 `values_read: false`）。

| cookie | host | created_utc |
| --- | --- | --- |
| `SUB` / `SUBP` / `SCF` | `.weibo.com` | **2026-10-30T06:08:00Z** |
| `SUB` / `SUBP` / `SCF` / `SSOLoginState` / `ALF` | `.weibo.cn` | **2026-10-30T06:08:01Z** |
| `ALC` / `X-CSRF-TOKEN` | `.passport.weibo.com` | 06:08:00Z / 06:06:48Z |
| `WBPSESS` / `XSRF-TOKEN` | `weibo.com` | 06:08:01Z |

`SUB` 是微博的会话标识，它在**登录窗口内**被创建（窗口 06:06:46Z 打开，06:08:00Z 写入），且 `.weibo.com` 与 `.weibo.cn` 两套都写了 —— 这与"扫码成功 → passport 下发会话 → 跳回 weibo.com"的时序完全一致。

## 4. 放宽后的登录判定（`tools/selection/access/weibo.py`）

`SIGNED_IN_JS` 新增（**只在为真时**出现的键，保持空白页仍只吐原有 8 个键）：

| 键 | 含义 |
| --- | --- |
| `hasSignout` | `a[href*="/signout"]`、`[class*=logout]`、`[class*=signout]`，或正文含「退出」 |
| `hasOwnProfileLink` | 页头 `a[href^="/u/"]`，或 `userLinkCount>0` |
| `hasComposeBtn` | `a[href*="/compose"]`、`[class*=publish]`、`[class*=compose]`，或正文含「发微博/发布」 |
| `textMarks` | `{signout: 正文含「退出」, profile: 正文含「我的主页」}` |

判定规则（`signed_in_evidence`，`classify_signed_in` 直接复用）：
**业务域且未命中 `/signin|/sso` 排除**，并且满足任一：
1. `hasLogout`；2. `hasSignout`；3. `hasComposeBtn` 且 `userLinkCount>0`；4. 正文命中「退出」或「我的主页」。
公开页的头像、泛 `/u/` 链接、`/setting`、`/account/` 仍然**不能**单独解锁。
`STRONG_SIGNALS` 保留 `("hasLogout",)` 以兼容既有调用方；`cli._login_state` 的 `evidence` 现在会写具体规则（`page:hasLogout` 仍显示为旧名 `page:logout_control`，其余写 `page:hasSignout` / `page:composeBtn+userLink` / `page:text:退出` 等）。

## 5. 单测（真实 `SIGNED_IN_JS` + Node DOM 桩，双向覆盖）

`tests/test_selection_rpa.py::SignedInDomStubTests`（node v24.15.0，不跳过）：

| 用例 | 期望 |
| --- | --- |
| 已登录首页（发微博按钮 + 自有 `/u/` 链接 + 退出文案） | **ok**（evidence ∈ {hasSignout, composeBtn+userLink, text:退出}） |
| 未登录首页（只有公开内容） | unknown |
| passport 登录页即使有按钮/退出文案 | unknown |
| 公开页只有 `/u/` 链接 | unknown |
| 只有发布按钮、没有自有主页链接 | unknown |
| `weibo.com/signin` 即使有退出控件 | unknown |
| 空白页键契约 | 仍是原来 8 个键 |

结果：`tests.test_selection_rpa` **111 tests OK**；四套全量 **346 tests OK**（`logs/tests-rpa-verdict.log`、`logs/tests-all-verdict.log`），**无跳过**、未改任何既有期望值。

## 6. 还缺什么（不夸大）

1. **当时那一刻的页面级信号没有留存**：`step9-login-rpa4.json` 只存了 `page` 的 `final_url/http_status/text_len/title`，没存 `hasLogout/hasSignout/...` 与正文文本，所以无法用新规则对那一次做**回溯重判**；本轮结论靠的是 cookie 元数据 + 跳转 + 页面长度。
2. **会话当前是否仍有效未验证**：需要一次带会话的请求（会消耗额度/触网），本轮明确不做。
3. 若下次再做登录验证，新的 `evidence` 字段会直接写出命中的规则，不必再靠时间戳推断。

## 7. 本轮没做

未访问真实站点、未发任何请求、未消耗任何额度、未改账本；未读或打印 cookie 值；未对真实页面截图；未改业务库/CSV/契约/小红书；未提交 git。
