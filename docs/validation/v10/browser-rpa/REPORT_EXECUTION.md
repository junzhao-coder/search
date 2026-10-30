# RPA 真实路径：实测报告（由具备命令权的执行者回填）

- 执行者：本会话（`allowCommands=true`）；解释器 `C:\Users\19183\.dsh\tools\x-collect\venv\Scripts\python.exe`；cwd `D:\桌面\two`。
- 时间：2026-10-30T05:21:42Z 起（各节单独标 UTC）。
- 代码来源：task-3c52d392 交付的 `tools/selection/rpa/`（本任务**未改产品代码**，只新增 `checks/guard_isolated_check.py` 与本报告）。
- 边界：**未执行任何真实站点导航**，未用真实 profile，未读/打印 cookie/token，未改业务库/CSV/契约/小红书，无 git 提交。

## 1. 测试（原始日志保留）

| 命令 | 结果 | 日志 |
| --- | --- | --- |
| `python -X utf8 -m unittest tests.test_selection_rpa -v` | **Ran 81 tests / OK / exit 0**（2026-10-30T05:21:42Z 起） | `logs/tests-rpa-v4.log` |
| `python -X utf8 -m unittest tests.test_selection_rpa tests.test_access_zhihu tests.test_access_weibo tests.test_access_budget -v` | **Ran 316 tests / OK / exit 0**（31.98s） | `logs/tests-all-v4.log` |

无失败、无跳过；未改任何期望值。

## 2. 本地 fixture 桌面级可见性实测（真实 Chrome）

命令（与 REPORT.md §6.2 一致）：

```powershell
& $py -X utf8 docs\validation\v10\browser-rpa\checks\desktop_proof_check.py
```

结果：**exit 0 / `all_pass: true` / `desktop.proven: true`**（2026-10-30T05:22:24Z）

| 字段 | 实测值 |
| --- | --- |
| `desktop.foreground_matched` | **true**（`foreground_before = foreground_after = 12781566`） |
| `desktop.window_rect` | `left=24, top=15, right=1581, bottom=1505, width=1557, height=1490`（`dwm_extended_frame_bounds`, DPI aware） |
| `desktop.window_title` / `class_name` | `DSH-RPA-PROOF-132226 - Google Chrome` / `Chrome_WidgetWin_1` |
| `desktop.matched_by` | `pid+title`（`candidate_count=2`） |
| 整屏截图 | `logs/desktop-proof.png`，**2560×1600，190,749 B**，`mode=rgb8_png` |
| `screenshot_covers_whole_screen` | **true**（`shot=2560x1600 screen=2560x1600`） |
| 网络 | `mode=local`、`dns_blocked=true`、`blocked_patterns=http/https/ws/wss` |
| 导航 | `ready_state=complete`、`redirects=[]`、`escaped=false`、`timed_out=false` |

`checks` 逐项：`session_mode_local / network_blocked / navigation_stable / desktop_supported / window_found / foreground_matched / window_rect_readable / desktop_screenshot_written / screenshot_covers_whole_screen / proven_true` 全部 `true`。

**判读**：`foreground_matched=true` + 非零窗口矩形 + 整屏截图 = 窗口确实在桌面上被置前（截图里能看到 Chrome 前台窗口、任务栏与背后的 DSH 窗口）。这证明"窗口在桌面可见"，**不证明人眼已看到**（脚本自己的 `note` 也这么写）。

## 3. 守卫拒绝矩阵（全部未启动浏览器）

CLI 实测（与 REPORT.md §6.3 一致）：

| # | 命令要点 | exit | stop | stage | browser_started |
| --- | --- | --- | --- | --- | --- |
| 1 | `live-search --keyword …`（无 `--allow-live`） | **6** | `blocked:allow_live_required` | `policy` | **false** |
| 2 | `… --allow-live`（无 batch） | **6** | `blocked:batch_id_required` | `precheck` | **false** |
| 3 | `… --allow-live --batch-id no-such-batch` | **6** | `blocked:no_authorized_batch` | `precheck` | **false** |
| 4 | `… --allow-live --batch-id weibo-verify-1`（真实已耗尽批次） | **6** | `blocked:batch_window_closed` | `precheck` | **false** |
| 5 | `login --batch-id no-such-batch --no-confirm` | **6** | `blocked:no_authorized_batch` | `precheck` | **false** |
| 6 | `window --url https://m.weibo.cn/ --desktop-proof` | **6** | `blocked:non_local_url` | — | — |

原始 JSON：`logs/guard-c1_no_allow_live.json` … `logs/guard-c6_window_http.json`；汇总 `logs/guard-matrix.json`。

**「批次已锁」与「剩余 0」两例**：CLI **故意没有** `--platform-db/--state-dir` 覆盖（安全属性），真实账本里也没有这两种状态，且本任务不允许改它。因此用**真实账本的临时副本**、在进程内把 `platform_budget.DEFAULT_PATH` 指向副本，再走**同一条 `cli.main` 路径**实测（新增 `checks/guard_isolated_check.py`，2026-10-30T05:23:03Z，exit 0）：

| case | 造法 | exit | stop | stage | browser_started |
| --- | --- | --- | --- | --- | --- |
| `platform_locked` | 副本 + `lock("test:locked_case")` | **6** | `blocked:platform_locked` | `precheck` | **false** |
| `calls_exhausted` | 副本 + 新批次（3 次 / 2 seed）+ 用掉最后 1 次（`remaining=0`, `window_open=true`） | **6** | `blocked:calls_exhausted` | `precheck` | **false** |

真实账本 `real_ledger_before == real_ledger_after`（mtime_ns/size 完全一致，`real_ledger_unchanged=true`），文件 mtime 仍是 `2026-10-29 22:46:06`。

## 4. 未实现 / 未实测（不代写代码）

1. **真实登录未实测**：`login` 代码路径存在（可见窗口 + 用户本人登录 + 桌面证据），但本轮**未执行**（需用户授权批次与真实窗口交互，超出本任务范围）。
2. **真实搜索未实测**：`live-search` 代码路径存在，本轮只验证了 6 种守卫拒绝；真实导航未执行。
3. **真实站点选择器未验证**：`CARD_JS` 只在本地 fixture 上验证（`logs/card-js-check.json` 由上一轮生成）。
4. **`weibo-rpa-1` 新批次**：用户已授权，但本任务**未创建/未使用**（授权动作不属于实测任务）。

## 5. 与 REPORT.md 固定命令的差异（如实说明）

1. §6.3 第 5 条 `login --batch-id no-such-batch` 实际会等待确认输入；我加了 `--no-confirm` 以避免交互阻塞（等价路径，仍走 `precheck`）。
2. §6.3 没有给出「批次已锁」「剩余 0」的 CLI 命令，因为 CLI 无账本路径覆盖；我新增 `checks/guard_isolated_check.py` 用临时副本 + 同一 `cli.main` 路径补齐，并在 §3 标明。
3. §6.2 的产物路径/字段与实测一致，无差异。

## 6. 实测结论

**通过**
1. RPA 单套 **81 tests OK**、四套全量 **316 tests OK**，exit 0，无失败无跳过。
2. 桌面级可见性：`foreground_matched=true`、窗口矩形 1557×1490、整屏截图 2560×1600/190,749B、`proven=true`，本地模式封网（DNS 全不解析 + CDP 封 http/https/ws/wss）。
3. 守卫拒绝 6 例全部 exit 6 且 `browser_started=false`（含 `platform_locked` 与 `calls_exhausted` 的隔离实测）；真实账本零写入。

**失败**：无。

**未能验证（原因）**
1. 真实登录/真实搜索：需真实窗口交互与授权批次，本任务范围外。
2. 真实站点选择器：只测了本地 fixture。
3. "人眼确实看到窗口"：`foreground_matched` 只证明窗口被置前，不证明观察者看到（脚本已如实标注）。
