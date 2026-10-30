# Browser-RPA：真实登录 / 真实搜索 / 桌面级可见性证据（v4）

- 范围：`tools/selection/rpa/`（新增 `desktop.py`，改 `session.py` / `cli.py` / `guard.py` /
  `__init__.py`）、`tests/test_selection_rpa.py`、本目录（`checks/desktop_proof_check.py`、
  `REPORT.md`、`USAGE.md`）。
- 本轮**没有**真实站点导航、没有用真实 profile 登录、没有改业务库/CSV/契约/小红书、无 git 提交。
- **已实现 ≠ 已实测**。本执行者会话没有命令执行权（Flow `allowCommands=false`，宿主无
  bash/pwsh），因此本文件里所有“实测”位置都留空并由具备命令权的执行者按 §6 回填；
  不预填任何通过数、不把静态审阅写成实测。

## 1. 桌面级可见性证据（回应「并没有看到有页面弹出」）

`window --desktop-proof` 用**标准库 ctypes**（无新依赖）走完 4 步，每步结果都进 JSON：

1. 找窗口：`EnumWindows` → `IsWindowVisible` + `GetClassNameW == Chrome_WidgetWin_1`
   + 非空标题；优先 `GetWindowThreadProcessId == 浏览器进程 PID`（nodriver `_process_pid`）；
   PID 失配时才允许按调用方生成的**一次性标题 nonce**（`DSH-RPA-PROOF-xxxxxxxx`）跨进程兜底。
   两者都没有 → **不猜**（否则可能抢到用户日常 Chrome）。
2. 置前：`AllowSetForegroundWindow` → `ShowWindow(SW_RESTORE)` → `SetWindowPos(HWND_TOP)` →
   `SetForegroundWindow`；仍未置前则 `AttachThreadInput` + `BringWindowToTop` + `SetFocus`
   重试一次；还是不行再合成一次 Alt 键事件（前台锁校验的“最后输入”条件）后重试，
   三次尝试的每一步都记进 `attempts`。
3. 判定：`GetForegroundWindow()` **等于**目标 `hwnd` 才算 `foreground_matched=true`；
   再读窗口矩形（DWM 扩展边框优先，回退 `GetWindowRect`）。
4. 截图：`GetDC(0)` + `BitBlt` 抓**整个虚拟桌面**，BGRA→RGB 后用 zlib 写成 PNG
   （`desktop_screenshot_bytes` 是文件字节数）。

输出字段（`window` 与 `login`/`live-search` 的 `desktop` 对象同构）：

| 字段 | 含义 |
| --- | --- |
| `supported` / `proven` | 平台可调用 / 证据成立（前台匹配 + 矩形可读 + 截图非空） |
| `reason` | 失败原因，见下表；`proven=true` 时为 `null` |
| `hwnd` / `pid` / `matched_by` | 命中的窗口与匹配方式（`pid` / `pid+title` / `title`） |
| `foreground_before` / `foreground_after` | 置前前后的前台句柄 |
| `foreground_matched` | `foreground_after == hwnd` |
| `attempts` | 置前尝试序列（含每个 API 的成败） |
| `window_rect` | `left/top/right/bottom/width/height` |
| `rect_source` | `dwm_extended_frame_bounds` / `get_window_rect` |
| `screen` / `dpi_aware` | 虚拟桌面矩形 / 是否设置 per-monitor DPI 感知 |
| `desktop_screenshot` / `desktop_screenshot_bytes` | PNG 路径与字节数（登录页恒为 `null`/`0`） |

失败原因（都会 `proven=false` 且带原因，不抛异常）：

`winapi_unavailable:*`（非 Windows/加载失败）、`window_not_found`、`foreground_not_matched`、
`window_rect_unreadable`、`desktop_screenshot_failed`。

`window --desktop-proof` 的输出还会把 `foreground_matched` / `window_rect` /
`desktop_screenshot_bytes` **镜像到顶层**，便于外部按字段名直接核对。

边界：
- **只对本地 fixture 截图**：`window` 只接受 `about:blank` 与 `fixtures/` 下的 `file://`；
- **真实登录页不截图**：`login` 调 `desktop_proof(screenshot=None)`，只报前台匹配与矩形；
- 前台锁（Windows foreground lock）、锁屏、服务会话下必然 `foreground_not_matched`——这是结论，
  不是缺陷；`--desktop-proof` 会因此返回 **exit 7**，不会用“窗口存在”冒充“窗口可见”；
- PID/页面截图/`document.visibilityState` 都不作为证据，只作为定位或渲染信息。
- 整屏截图会包含当时桌面上的全部内容（含其它窗口）；它只用于本机留证，
  对外分享前请自行审阅/裁剪。

## 2. `login`：可见窗口 + 用户本人登录

固定顺序（任何一步失败都在启动浏览器之前停）：

```
固定权威账本 precheck → 预扣 active_nav → 启动可见浏览器 → 导航 passport 登录页
→ 桌面证据(不截图) → 轮询页面信号 / 用户按 Enter / 超时 → 关窗 → 风险写锁 → 结果登记
```

- 账本路径固定 `tools/selection/access/runtime/platform_weibo.sqlite3`；CLI **没有**
  `--platform-db` / `--ledger` / `--state-dir` 之类覆盖入口，换目录不可能重置额度或锁。
- 不代填账号密码/验证码，不读 cookie 值；输出里 `cookie_values_read: false`。
- 登录态只报两种：`ok`（页面出现 **logout 控件**，`page:logout_control`）或 `unknown`。
  cookie 存在、头像、`/u/` 链接一律不算。
- 风险判定先于一切记录：HTTP 403/429/432/418 或真实墙词（安全验证/访问异常/操作频繁/
  访问过于频繁/请求过于频繁/系统繁忙/账号异常/访问受限/captcha）→ 写平台锁 + `exit 5`。
- 轮询间隔 2s；`--timeout` 默认 300s；用户按 Enter 提前结束（必须 TTY，否则只走超时）。

退出码：`0` 页面证据已登录；`11` 超时；`13` 未确认/未知；`5` 风险（已写锁）；`6` 守卫拒绝；
`7` 传输/会话异常。所有已扣费路径都会登记 **`active_nav_result`（source=`rpa.login`）**；
登记写失败 → `exit 6 result_write_failed`（输出 `result_persisted=false`）。

## 3. `live-search`：真实搜索（有守卫才导航）

固定顺序：

```
--allow-live → precheck → 预扣 search → 启动可见浏览器(m.weibo.cn) → 单次导航
→ 风险判定(HTTP 状态 + 墙词) → 可见卡片提取 → 记录预留(cap 5) → 结果登记
```

- **未授权/已锁/窗口已关/剩余 0/预扣失败 → 一律不启动浏览器**（`factory.created` 为空有测试）。
- **风险先于记录**：风险命中时不会调用 `dump_cards`，输出 `records: []` 且 `exit 5`。
- 失败**不退款**、**不重试**、**不换词**、**不换 UA**；UA 是启动开关（默认 `weibo.MOBILE_UA`），
  不是被拦后的重试手段。
- 卡片提取沿用 `extract.py` 的严格来源校验（host ∈ weibo.com/weibo.cn/m.weibo.cn，
  路径 `status|detail/<id>`，URL id 必须等于卡片 id）。
- 记录只在 `reserve_records` 成功后输出；预留被拒 → 不输出任何记录并 `exit 6`。
- **readiness 超时**：`wait_ready.timed_out=true`（页面从未 `complete`）→ `exit 7
  readiness_timeout`，**不解析、不输出记录**；风险判定仍然先于超时判定（墙页先锁）。
- **结算顺序**：先登记结果（`search_result`，source=`rpa.search`），**再**写导出文件。
  登记失败 → `records: []`、不写导出文件、`exit 6 result_write_failed`、`result_persisted=false`；
  导出失败 → `exit 9 export_failed:<Exc>`（`output: null`、`export_error` 有值）。
- `--timeout` / `--user-agent` 会**真的传到** `VisibleSession`（CDP 单步超时 + 浏览器启动 UA），
  不是只解析不生效。

退出码：`0` 有记录；`3` 有卡全被拒/空；`4` 无卡/未知；`5` 风险（已写锁）；`6` 守卫拒绝或
结果登记失败；`7` 传输/会话异常或 readiness 超时；`9` 导出失败。

## 4. 守卫拒绝矩阵

| 场景 | 预期 exit | `stop` | 浏览器 |
| --- | --- | --- | --- |
| 缺 `--allow-live` | 6 | `blocked:allow_live_required` | 不启动 |
| 缺 `--batch-id` | 6 | `blocked:batch_id_required` | 不启动 |
| 批次不存在/未授权 | 6 | `blocked:no_authorized_batch` | 不启动 |
| 平台已锁 | 6 | `blocked:platform_locked` | 不启动 |
| 剩余 0 | 6 | `blocked:calls_exhausted` | 不启动 |
| 批次窗口已关 | 6 | `blocked:batch_window_closed` | 不启动 |
| 预扣失败（并发/历史锁） | 6 | `blocked:platform:<code>` | 不启动 |

## 5. 测试覆盖（新增，纯离线）

`tests/test_selection_rpa.py` 新增的类：

- `LiveSessionModeTests`：local 封 DNS / live 不封、`open_live` 只接受 http(s) 且必须 live、
  `read_page`/`read_signals` 解析、`wait_ready` 超时如实标记；`_new_session` 把
  `timeout`/`user_agent` 带进 `VisibleSession` 且 `browser_args()` 里确有 `--user-agent=…`。
- `LiveSearchGuardTests`：未授权/已锁/缺批次/剩余 0/窗口关/预扣失败**都不启动浏览器**；
  风险文本与 HTTP 403 **先于**记录构建；固定调用顺序（预扣→启动→导航→读页→证据→提取→预留→登记）；
  锁写失败非零；**结果写失败 → records=[]、无导出文件、exit 6**；**导出失败 → exit 9**；
  **readiness 超时 → exit 7 且不 dump_cards、不输出记录**；`--timeout/--user-agent` 透传；
  预留被拒不输出记录；启动失败仍登记 `search_result`（source=`rpa.search`）。
- `LoginGuardTests`：未授权/已锁/预扣失败不启动浏览器；**预扣早于 `session.start`（时间线断言）**；
  页面 logout 控件 → `exit 0` + `page:logout_control`；无信号 → `13`/`unknown`；风险 → `5` + 写锁；
  结果写失败非零；**启动失败仍登记 `active_nav_result`（source=`rpa.login`）**；
  **登录页调用 `desktop_proof(screenshot=None)`**（不自动截图）。
- `WindowDesktopProofTests`：非本地 URL 在启动前拒绝；证据成立 → `exit 0`；
  证据失败 → `exit 7` + `desktop_proof_failed:<reason>`；未加 flag 不宣称桌面证据。
- `DesktopEvidenceTests`：PNG 签名/IHDR/IDAT 可解压；找不到窗口时 `proven=false` 且有原因；
  失败时不写截图文件；非 Windows 只报 `supported=false`。
- `StaticSafetyTests`：RPA 包内无 cookie 读取、无 `--platform-db`/`--ledger-path`、
  仍用固定 `guard_mod.open_guard()`。

## 6. 固定实测命令（复制即可跑）

统一前置（PowerShell）：

```powershell
Set-Location "D:\桌面\two"
$py = "C:\Users\19183\.dsh\tools\x-collect\venv\Scripts\python.exe"
```

### 6.1 单测

```powershell
& $py -X utf8 -m unittest tests.test_selection_rpa -v 2>&1 | Tee-Object `
    docs\validation\v10\browser-rpa\logs\tests-rpa.log

# 与上一轮同样的“四套全量”（272 项的来源）
& $py -X utf8 -m unittest tests.test_selection_rpa tests.test_access_zhihu `
    tests.test_access_budget tests.test_access_weibo 2>&1 | Tee-Object `
    docs\validation\v10\browser-rpa\logs\tests-all.log

# 更宽的可选入口（会带上 selection 其它套件）
& $py -m unittest discover -s tests -p "test_*.py" -v
```

预期：`exit 0`、`Ran N tests`、`OK`；`RecordedCardJsTests` 若 `logs/card-js-check.json`
缺失会 skip（不是失败）。日志存 `docs\validation\v10\browser-rpa\logs\`。

### 6.2 本地 fixture 桌面证据（真实浏览器）

```powershell
& $py -X utf8 docs\validation\v10\browser-rpa\checks\desktop_proof_check.py
# 预期：exit 0；all_pass=true
# 关键字段（logs/desktop-proof-check.json）：
#   desktop.foreground_matched = true
#   desktop.window_rect.width/height > 0
#   desktop.desktop_screenshot_bytes > 1000
#   desktop.proven = true
#   checks[desktop_screenshot_written] / checks[screenshot_covers_whole_screen] = true
# 产物：logs/desktop-proof.png（整屏，不是页面截图）
```

需要**交互桌面会话**；锁屏/服务会话下会得到 `foreground_not_matched` 且 exit 1（如实失败）。

### 6.3 守卫拒绝（全部不启动浏览器，可对现网账本安全执行）

```powershell
& $py -m tools.selection.rpa live-search --keyword "学习计划模板"
# exit 6, stop=blocked:allow_live_required, stage=policy, browser_started=false

& $py -m tools.selection.rpa live-search --keyword "学习计划模板" --allow-live
# exit 6, stop=blocked:batch_id_required

& $py -m tools.selection.rpa live-search --keyword "学习计划模板" --allow-live --batch-id no-such-batch
# exit 6, stop=blocked:no_authorized_batch

& $py -m tools.selection.rpa live-search --keyword "学习计划模板" --allow-live --batch-id weibo-verify-1
# exit 6；耗尽批次通常是 blocked:batch_window_closed（窗口早过期），
# 若账本已被锁则 blocked:platform_locked；open 窗口内剩余 0 才是 blocked:calls_exhausted

& $py -m tools.selection.rpa login --batch-id no-such-batch
# exit 6, stop=blocked:no_authorized_batch；profile 不会被打开

& $py -m tools.selection.rpa window --profile D:\tmp\rpa-demo --url "https://m.weibo.cn/" --desktop-proof
# exit 6, stop=blocked:non_local_url（桌面证据只服务本地 fixture）
```

判定：前五条必须 `browser_started=false` 且**没有任何 Chrome 窗口弹出**；最后一条（`window`
非本地 URL）在启动前就被 block，输出里没有 `browser_started` 字段，同样不应有窗口。

### 6.4 真实 login / live-search 模板（**本轮不执行**）

前提：① 用户已授权新批次；② 批次已在固定账本里授权（`authorize_batch`，**不由 RPA CLI 提供入口**，
避免自授权）；③ 用户在电脑前。授权形如：

```python
# 由策划者按用户授权执行，不属于本任务：
# led.authorize_batch("weibo-rpa-1", authorized_calls=3, window_seconds=300,
#                     records_cap=5, source="user:consent:rpa-1",
#                     seed_from=("login-window-1", "login-window-2"))
```

登录（预扣 `active_nav` 1 次）：

```powershell
& $py -m tools.selection.rpa login `
  --profile "C:\Users\19183\.dsh\tools\weibo-collect\profile" `
  --batch-id weibo-rpa-1 --timeout 300
# 关键字段：browser_started=true, desktop.foreground_matched, desktop.window_rect,
#          status=signed_in|timeout|unknown|risk, login_state.verdict/evidence,
#          polls, window_closed=true, result_kind=active_nav, result_source=rpa.login,
#          result_persisted=true
# exit：0 页面证据已登录 / 11 超时 / 13 未确认 / 5 风险(已锁) / 6 守卫或结果登记失败 / 7 传输
```

搜索（预扣 `search` 1 次，单次导航）：

```powershell
& $py -m tools.selection.rpa live-search --keyword "学习计划模板" `
  --profile "C:\Users\19183\.dsh\tools\weibo-collect\profile" `
  --batch-id weibo-rpa-1 --allow-live --limit 5 `
  --out "D:\桌面\two\docs\validation\v10\browser-rpa\logs\rpa-live-records.jsonl"
# 关键字段：stage(navigate/read/risk/extract/reserve/done)、page.http_status、
#          desktop.foreground_matched、count/records[].native_id/url/title/text、
#          parsed_structure、diagnostics.rejected、result_kind=search、
#          result_source=rpa.search、result_persisted、output、export_error
# exit：0 有记录 / 3 空 / 4 未知 / 5 风险(已锁) / 6 守卫或结果登记失败 /
#       7 传输或 readiness_timeout / 9 导出失败
```

说明：`login --timeout` 是**登录等待窗口**（默认 300s）；`live-search --timeout` 是
**CDP 单步超时**（默认 60s），两者都会真的生效（`login` 用于轮询截止，`live-search` 传给
`VisibleSession`）；本批窗口上限 300s 来自 `platform_budget.MAX_SECONDS`，未改动。

## 7. 未实测项与所需授权

| 项 | 状态 | 需要什么 |
| --- | --- | --- |
| 单测 | 已写、**未跑**（本会话无命令权） | 具备命令权的执行者按 §6.1 跑并回填日志 |
| 桌面证据 | 已实现、**未跑** | 同上，§6.2，需交互桌面会话 |
| 守卫拒绝 | 已实现、**未跑** | 同上，§6.3（只读 precheck，不扣费） |
| 真实 login | 已实现、**未实测** | 用户授权的新批次 + 用户在电脑前 + 专用 profile |
| 真实 live-search | 已实现、**未实测** | 同上；`CARD_JS` 选择器仍是 `(assumed)`，实站不匹配会返回 `empty/unknown`（有效结论） |

不得据此称“微博已接通”：真实登录与真实采集都还没有一次实测记录。

## 8. 已知限制

1. **批次窗口上限 300s**：`platform_budget.MAX_SECONDS = 300` 保持不变；真实批次一律按
   ≤300 秒窗口授权（`weibo-rpa-1` 示例用 300s），本轮不再出现 600s 说法，也不改常量。
2. `CARD_JS` 选择器（`article, div[class*='card']` 等）从未在真实微博页面核对，全部标记
   `(assumed)`；真实结果可能是 `empty`/`unknown`。
3. `search_url` 走 `m.weibo.cn/search?containerid=100103type=1&q=<kw>`（假设），移动 UA 是
   启动开关；实站若重定向到桌面站，卡片结构可能不匹配。
4. 桌面证据依赖 Windows 前台锁行为；`AttachThreadInput` 重试也可能失败，失败即如实 false。
5. 多显示器时截图为整个虚拟桌面（所有屏幕并集），不是单屏裁剪。
6. 登录态判定只认 logout 控件（与既有 `access/weibo.classify_signed_in` 同源），
   实站若改了控件结构，会返回 `unknown` 而不是误报 `ok`。
7. 本轮没有 `detail`/`comments` 的 RPA 入口；它们仍由既有 `tools.selection.access.weibo`
   的 HTTP 路径承担。
8. `logs/demo-blocked-live.json` 是**上一轮**「live-search 恒拒绝」行为的留档，与当前代码
   不一致；当前行为见 §3 与 §6.3，新的运行日志会覆盖 `logs/tests-rpa.log` / `tests-all.log`。

## 9. 变更清单

| 文件 | 变更 |
| --- | --- |
| `tools/selection/rpa/desktop.py` | 新增：ctypes 找窗口/置前/前台校验/矩形/整屏 PNG |
| `tools/selection/rpa/session.py` | 新增 live 模式、`open_live`、`read_page`、`read_signals`、`wait_ready`、`set_title`、`desktop_proof`；live 不封 DNS、local 仍封 |
| `tools/selection/rpa/cli.py` | `window --desktop-proof/--desktop-screenshot`；真实 `login`；真实 `live-search`；`--allow-live` 闸门；`--timeout/--user-agent` 透传到 `VisibleSession`；`_settle` 先登记后导出 |
| `tools/selection/rpa/guard.py` | 新增 `charge_nav`；`record_result(kind, outcome, *, source)` 分型登记 `active_nav_result`/`search_result` 并写正确 source；`RISK_STATUS` 补 432 |
| `tools/selection/rpa/__init__.py` | 导出 `charge_nav`、更新说明 |
| `tests/test_selection_rpa.py` | 新增 5 个测试类（live 模式/搜索守卫/登录守卫/桌面证据/桌面纯函数），并扩充 `WindowPolicyTests`、`StaticSafetyTests`；`live-search` 旧“恒拒绝”用例改为“缺 `--allow-live` 拒绝” |
| `docs/validation/v10/browser-rpa/checks/desktop_proof_check.py` | 新增真实浏览器桌面证据检查脚本 |
| `docs/validation/v10/browser-rpa/REPORT.md`、`USAGE.md` | 本文与使用说明 |

## 10. 修复：可见窗口必须显示目标页（window_title_matches_page）

**事故复盘（weibo-rpa-1 首次真实登录，2026-10-30T05:27–05:30Z）**：`step2-login.json` 里
`desktop.window_title = "新标签页 - Google Chrome"`，而页面 `page_title = "登录 - 微博"` —— 被置前的
是空白新标签页，登录页在后台标签，用户看不到登录页、150s 内未扫码（exit 11 / verdict unknown）。
根因：`open_live/open_local` 导航后**没有激活目标标签页**，`desktop_proof` 也没比对窗口标题与页面标题。

**修复**

| 位置 | 变更 |
| --- | --- |
| `session.open_local` / `open_live` | 导航后调用 `activate(tab)`：先 `Tab.activate()`，失败再退 CDP `Target.activateTarget` + `Page.bringToFront`；结果存 `last_activation`（失败只记录不抛） |
| `session.desktop_proof(tab=…)` | 新增 `page_title`、`window_title`（OS）、`window_title_matches_page`（页面标题是否为窗口标题子串；任一为空 → `None`，不当作成立）、`activation` |
| `cli._visibility_gate` | `window_title_matches_page is not True` → `window_showing_other_tab`；`login`/`live-search` 在等待扫码/解析之前就退出，**非零（`EXIT_VISIBILITY = 12`）** |
| `cli.cmd_login` | 输出 `profile`、`profile_exists`、`profile_source`（`explicit`/`default`）、`default_profile`、`expected_profile`、`profile_matches_expected`，不再静默用默认 profile |

**真实本地浏览器实测**（`checks/window_title_check.py`，2026-10-30T05:34Z，exit 0，`logs/window-title-check.json`）：

| check | 结果 |
| --- | --- |
| `activation_reported` | `{"activated": true, "method": "tab.activate"}` |
| `window_title_matches_page_true` | `window_title="RPA-TITLE-PROOF-babbf4ea - Google Chrome"`、`page_title="RPA-TITLE-PROOF-babbf4ea"` |
| `os_title_contains_page_title` | true |
| `gate_allows_when_matched` | `None`（放行） |
| `window_title_not_matching_after_other_tab` | 另开 `about:blank` 后 `window_title="about:blank - Google Chrome"`、`match=null`（未知也拦） |
| `os_title_no_longer_contains_page_title` | true |
| `gate_blocks_other_tab` | `window_showing_other_tab` |

**单元/行为测试**（新增 10 例，`tests.test_selection_rpa` 共 **91** 例）：
`TitleConsistencyTests`（命中/空白页/空值→None）、`ActivationTests`（`tab.activate` 优先、CDP 失败只记录）、
`DesktopProofFieldsTests`（`page_title`/match 字段、窗口显示别页时为 false）、`VisibilityGateTests`（false/None 都拦、
仅 true 放行、`EXIT_VISIBILITY=12` 非零且区别于 0）。

**profile 事实核对**：`weibo.DEFAULT_PROFILE = C:\Users\19183\.dsh\tools\weibo-collect\profile`（本次真实登录实际用的就是它，`profile_source=default`）；
任务上下文写的 `docs/validation/v10/weibo-login/profile` 是 `expected_profile`，两者**不一致**（`profile_matches_expected=false`）。
现在 `login` 会显式打印这组字段，不再静默。是否要改默认 profile 属产品决策，本轮不动。

**回归**：`card_js_check` exit 0（4 卡/3 记录）、`desktop_proof_check` exit 0（foreground_matched=true，截图 173,280B）、
四套全量 **326 tests OK**（`logs/tests-all-window-title.log`）。

## 11. 置顶 + 持续夺回前台（窗口被全屏窗口遮挡）

**现实场景**：窗口弹出瞬间确实在前台（`foreground_before=foreground_after`），但用户正在与本聊天界面交互，
焦点被切回、全屏的聊天窗口把它整个盖住 —— 于是"根本没看到任何新窗口"。

**实现**

| 位置 | 变更 |
| --- | --- |
| `desktop.set_topmost(hwnd, on=True)` | `SetWindowPos(HWND_TOPMOST, SWP_NOMOVE\|SWP_NOSIZE\|SWP_NOACTIVATE\|SWP_SHOWWINDOW)`，随后**回读** `GetWindowLongW(GWL_EXSTYLE)` 核对 `WS_EX_TOPMOST`，输出 `topmost_set`/`exstyle` |
| `desktop.topmost_flag(exstyle)` | 纯函数：`exstyle & WS_EX_TOPMOST` |
| `desktop.reassert(hwnd)` | **先看前台**：已是目标窗口 → 直接返回 `was_foreground=true`，不抢焦点；否则 `force_foreground` 并回读，失败记 `foreground_not_reclaimed` |
| `desktop.Keepalive(hwnd, interval=2.0)` | `start()` 置顶；`tick()` 按 interval 节流、只在前台丢失时夺回，累计 `ticks/reassert_count/reassert_failures`；`finish()` 记录 `still_foreground_at_end` 并**清掉置顶** |
| `cli._wait_login(keepalive=…)` | 登录轮询每轮 tick 一次（扫码期间持续夺回） |
| `cli.cmd_live_search` | `wait_ready(keepalive=…)` 同样每轮 tick（搜索页就绪期间也保持可见） |
| `session.wait_ready(keepalive=…)` | 每轮 tick，语义不变（attempts/interval/timed_out 原样） |

**真实本机实测**（`checks/topmost_check.py`，2026-10-30T05:57:10Z，exit 0，`logs/topmost-check.json`，all_pass=true）：

| check | 结果 |
| --- | --- |
| `window_found` | hwnd=2426554，`window_title="RPA-TOPMOST-1224efe5 - Google Chrome"` |
| `topmost_set_via_exstyle` / `exstyle_has_ws_ex_topmost` | **true** / exstyle=2097416（含 `0x8`） |
| `cover_window_found` / `chrome_covered_by_other_window` | Notepad hwnd=264958 / 前台确实变成 Notepad（Chrome 被盖住） |
| `reassert_after_cover` | `reasserted=true`、`foreground_after=2426554`（夺回） |
| `user_switched_away` / `reassert_after_user_switch` | 再切回 Notepad 后，下一次 tick 再次夺回 |
| `reassert_count_ge_2` / `still_foreground_at_end` / `topmost_cleared` | 2 / **true** / **true** |
| `no_reassert_failures` | 0 |

**单测**（新增 9 例，`tests.test_selection_rpa` 共 **100** 例）：`topmost_flag` 位判定、`start()` 置顶、
"已在前台不抢焦点"（`force_foreground` 未被调用）、丢失时夺回计数、失败计数与 `last_error`、
interval 节流（第二次 tick 不再夺回）、`finish()` 的 `still_foreground_at_end`/清置顶、`wait_ready` tick 计数、
`cmd_login` 携带 keepalive 汇总。

**回归**：`window_title_check` exit 0、`desktop_proof_check` exit 0、`card_js_check` exit 0；四套全量 **335 tests OK**（`logs/tests-all-topmost.log`）。

**说明**：清理时发现一个 **不属于本脚本** 的 Notepad（pid 11532，标题 `HK-SOCKS-启动.ps1 - Notepad`），未动它；
脚本自己启动的无标题 Notepad 已 `terminate()` 回收。
