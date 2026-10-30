# Browser-RPA 使用说明（v4：真实登录 / 真实搜索 / 桌面证据）

本轮代码已实现三条路径，状态不同：

| 命令 | 网络 | 状态 |
| --- | --- | --- |
| `extract` | 无 | 已实现、已离线验证 |
| `window`（含 `--desktop-proof`） | 只本地 fixture | 已实现；桌面证据需真实桌面会话实测 |
| `login` | 真实（passport.weibo.com） | 已实现、**未实测**（需新授权批次 + 用户本人） |
| `live-search` | 真实（m.weibo.cn） | 已实现、**未实测**（同上） |

真实路径没有“恒拒绝”开关：守卫通过就会真的导航；守卫不通过则**不启动浏览器**。

```powershell
Set-Location "D:\桌面\two"
$py = "C:\Users\19183\.dsh\tools\x-collect\venv\Scripts\python.exe"   # 项目 .venv 没有 nodriver
```

## 1. 本地可见窗口 + 桌面级证据

```powershell
# 只看计划（不启动浏览器）
& $py -m tools.selection.rpa window --profile D:\tmp\demo --dry-run

# 打开 fixtures 页面，导出可见卡片 + 页面截图
& $py -m tools.selection.rpa window --profile D:\tmp\demo `
  --url "file:///D:/桌面/two/docs/validation/v10/browser-rpa/fixtures/card-cases.html" `
  --dump-cards docs\validation\v10\browser-rpa\logs\cards-local.json `
  --screenshot docs\validation\v10\browser-rpa\logs\window-local.jpg --no-wait

# 桌面级证据：置前 + GetForegroundWindow 核对 + 窗口矩形 + 整屏截图
& $py -m tools.selection.rpa window --profile D:\tmp\proof `
  --url "file:///D:/桌面/two/docs/validation/v10/browser-rpa/fixtures/card-cases.html" `
  --desktop-proof `
  --desktop-screenshot docs\validation\v10\browser-rpa\logs\desktop-proof.png --no-wait
```

- `desktop.foreground_matched=true` + `desktop.window_rect` 有尺寸 + `desktop_screenshot_bytes>0`
  才叫“桌面可见”；`--desktop-proof` 失败 → `exit 7` + `stop=desktop_proof_failed:<reason>`。
- `desktop_visibility_proven` 在未加 `--desktop-proof` 时恒为 `false`：页面截图只证明非 headless 渲染。
- 只接受 `about:blank` 与 `fixtures/` 下的 `file://`；其他 → `exit 6`，不启动浏览器。
- 整屏截图包含当时桌面全部内容（含其它窗口），只作本机留证；对外分享前自行审阅/裁剪。

## 2. 离线提取（可见卡片 JSON → 记录）

```powershell
& $py -m tools.selection.rpa extract `
  --cards-json docs\validation\v10\browser-rpa\logs\cards-local.json `
  --out docs\validation\v10\browser-rpa\logs\records-local.jsonl
```

退出码：`0` 成功；`3` 有卡但全被拒；`4` 无卡/未知（含 detail 的任何拒绝原因）；`8` 输入错误。
拒绝原因见 `diagnostics.rejected`。

## 3. 真实登录（用户本人操作）

```powershell
& $py -m tools.selection.rpa login `
  --profile "C:\Users\19183\.dsh\tools\weibo-collect\profile" `
  --batch-id weibo-rpa-1 --timeout 300
```

- 顺序：固定账本 `precheck` → 预扣 `active_nav` → 启动可见窗口 → 导航登录页 → 桌面证据（**不截图**）
  → 等待（按 Enter 可提前结束）→ 关窗 → 风险写锁 → 结果登记 `active_nav_result`（source=`rpa.login`）。
- 代码不代填账号/密码/验证码、不读 cookie 值；登录态只报 `unknown` 或页面 `logout` 控件证据。
- 退出码：`0` 有页面证据；`11` 超时；`13` 未确认/未知；`5` 风险（已写锁）；`6` 守卫拒绝
  （未启动浏览器）或结果登记失败（`result_persisted=false`）；`7` 传输/会话异常。
- 没有 `--platform-db`/`--state-dir`：账本固定 `tools/selection/access/runtime/platform_weibo.sqlite3`。

## 4. 真实搜索

```powershell
& $py -m tools.selection.rpa live-search --keyword "学习计划模板" `
  --profile "C:\Users\19183\.dsh\tools\weibo-collect\profile" `
  --batch-id weibo-rpa-1 --allow-live --limit 5 `
  --out "D:\桌面\two\docs\validation\v10\browser-rpa\logs\rpa-live-records.jsonl"
```

- 缺 `--allow-live` → `exit 6 blocked:allow_live_required`，不开浏览器。
- 顺序：`precheck → 预扣 search → 导航 → 风险(HTTP+墙词) → 可见卡片 → 记录预留 → 结果登记
  search_result(source=rpa.search) → 导出`；风险命中不会构建任何记录；失败不退款、不重试、不换词。
- `wait_ready` 超时（页面从未 `complete`）→ `exit 7 readiness_timeout`，**不解析、不输出记录**。
- 结果登记失败 → `records: []`、不写导出文件、`exit 6`；导出失败 → `exit 9 export_failed:*`。
- `--timeout`/`--user-agent` 传给 `VisibleSession`（CDP 超时 + 浏览器 UA），不是只解析不用。
- 退出码：`0` 有记录 / `3` 空 / `4` 未知 / `5` 风险 / `6` 守卫或结果登记失败 /
  `7` 传输或 readiness 超时 / `9` 导出失败。
- `CARD_JS` 选择器仍是 `(assumed)`：实站不匹配时得到 `empty`/`unknown`，这是有效观测，不是“接通”。

## 5. 记录格式

> **记录数（v11 软目标）**：默认目标 5 条，可任意上调；`reserve_records()` 返回 `records_target/records_used/over_cap/over_by`，**超出目标不拒绝、不截断、记录一条不丢**。软的是存储；硬的是调用次数、15 秒间隔、单批 300 秒时长与风险即停。


沿用 `tools.selection.access.records`：`native_id/type/url/title/text/published_at/voteup/comments/likes`
+ `missing/supported/field_evidence/source`；`source` 为 `weibo:search:status` / `weibo:detail:status`。

## 6. 可见性前提：窗口必须显示目标页

`login` / `live-search` 在导航后会**激活目标标签页**（`Tab.activate()`，失败退 CDP `Target.activateTarget` +
`Page.bringToFront`），然后比对：

| 字段 | 含义 |
| --- | --- |
| `desktop.window_title` | OS 窗口标题（如 `登录 - 微博 - Google Chrome`） |
| `desktop.page_title` | 页面 `document.title`（如 `登录 - 微博`） |
| `desktop.window_title_matches_page` | 页面标题是否为窗口标题子串；任一为空 → `null`（未知，不算成立） |
| `desktop.activation` | `{activated, method, error}` |

**失败判定**：`window_title_matches_page is not True` → `stop=window_showing_other_tab`、**exit 12**，
不再等待扫码、不解析记录。这对应"窗口显示的是空白新标签页/别的标签页"的真实事故。

`login` 同时输出 profile 事实：`profile`（绝对路径）、`profile_exists`、`profile_source`（`explicit`/`default`）、
`default_profile`（`C:\Users\19183\.dsh\tools\weibo-collect\profile`）、`expected_profile`
（`docs/validation/v10/weibo-login/profile`）、`profile_matches_expected`。不一致会显式报出，不再静默用默认值。

本地验证脚本：

```powershell
& $py -X utf8 docs\validation\v10\browser-rpa\checks\window_title_check.py
# -> logs/window-title-check.json，all_pass 必须为 true
```

## 7. 置顶与"被全屏窗口遮挡"

登录/搜索窗口在等待期间会：`SetWindowPos(HWND_TOPMOST, …)` 置顶（回读 `GWL_EXSTYLE` 核对 `WS_EX_TOPMOST`），
并且**只在前台丢失时**重新 `SetForegroundWindow`（`Keepalive.tick()`，默认 2s 节流，不每轮抢焦点）。
`login`/`live-search` 的输出里：

| 字段 | 含义 |
| --- | --- |
| `keepalive_start.topmost_set` | 置顶是否真的生效（回读 exstyle） |
| `keepalive.ticks` / `reassert_count` / `reassert_failures` | 轮询次数 / 成功夺回次数 / 失败次数（失败不静默） |
| `keepalive.still_foreground_at_end` | 结束时窗口是否仍是前台 |
| `keepalive.topmost_cleared` | 结束时是否已清掉置顶（避免长期霸占最前） |

本地验证：

```powershell
& $py -X utf8 docs\validation\v10\browser-rpa\checks\topmost_check.py
# -> logs/topmost-check.json，all_pass 必须为 true（用真实最大化 Notepad 遮挡再夺回）
```
