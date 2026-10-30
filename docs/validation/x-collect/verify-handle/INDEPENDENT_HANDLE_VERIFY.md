# x-collect handle 修复独立复验（计划 v5）

> 任务：`task-8342d41a4402dae804e3952daa13af0f`（revision 2，计划 v5）；依赖修复任务 `task-96edb124949b8eac8761dc6f4cdc2871` 已 **rev4 accept** 后启动。
> 核验者 session-01ba487c…，**非实现者**；未改 scripts/x_collect.py、profile、DSH 配置与业务系统；未发布/点赞/关注/私信。
> 采样：2026-10-22 04:01–04:04 UTC（12:01–12:04 UTC+8）。命令/cwd/UTC/真实 exit 见 `logs/`、`raw/`；UTF-8 无 BOM。
> 结论先行：**两次 doctor 一致返回 `@Johnsmathjyjp`、exit=0（consistency PASS）；但源码仍有 `SETTINGS_HANDLE_JS` 正文 @mention 回退（source-check 未完全通过），且实际账号不等于 `@xluchuan`。**

## 0. 状态表

| 类别 | 结论 | 要点 |
| --- | --- | --- |
| consistency | **PASS** | 两次新进程 doctor 均 `@Johnsmathjyjp`、exit=0，间隔 55s |
| source-check | **FAIL（部分）** | `HANDLE_JS` 已删正文回退；`SETTINGS_HANDLE_JS` 仍保留 `document.body.innerText` 的 @mention 回退 |
| login | **PASS** | `.x.com` cookie 15 行，`auth_token`/`ct0` 名称存在；未读值；doctor `LOGGED_IN` |
| crawl | **PASS** | 一次 search（limit 5，默认间隔）exit=0，5 条/5 唯一 |
| actual-account | **≠ @xluchuan** | 两轮均 `@Johnsmathjyjp`；需用户确认该 profile 是否应为此账号 |
| hashes | **PASS（本轮前后）** | 11 文件 before/after 一致；业务库/脚本/DSH 配置未变 |
| limits | 见 §6 | settings 正文回退、doctor 内部点击账号按钮、账号不一致、未触发 429/未跑其他命令 |

## 1. consistency：两次 doctor

命令（cwd=`C:\Users\19183\.dsh\tools\x-collect`，同一 profile、新进程）：

```powershell
C:\Users\19183\.dsh\tools\x-collect\venv\Scripts\python.exe `
  C:\Users\19183\.dsh\tools\x-collect\scripts\x_collect.py doctor
```

| 运行 | wrapper start UTC | 工具日志时段 | exit | handle |
| --- | --- | --- | --- | --- |
| run1 | 2026-10-22T04:02:08Z | 04:02:09–04:02:15Z（约 6s） | **0** | **`@Johnsmathjyjp`** |
| run2 | 2026-10-22T04:03:03Z | 04:03:04–04:03:09Z（约 5s） | **0** | **`@Johnsmathjyjp`** |

- 两次起点间隔 **55 秒**（≥30s），handle 完全一致；无 `HANDLE_UNKNOWN`、无登录跳转；两次后均无 x-collect Chrome 残留。
- 原始证据：`logs/doctor_run1.log`、`logs/doctor_run2.log`、`raw/doctor_tool_run1.log`、`raw/doctor_tool_run2.log`；摘要 `evidence/handle_summary.json`。
- 过程说明：另有一次未带 `doctor` 参数的 wrapper no-op 误运行，原样保留为 `logs/doctor_run1_noop_attempt.log`，未用于结论。

## 2. source-check：源码是否已删除正文回退

`source_check.py` 对当前脚本（sha256 `06ebace18dca4b6223f50162a682abfcc1cb1b24f3d03951214767bd4776d71d`）做块级检查：

| 代码块 | 行 | 正文 `document.body` | @匹配 | 判定 |
| --- | --- | --- | --- | --- |
| `HANDLE_JS` | 39–49 | **无** | 只匹配账号按钮 innerText/aria-label | 合格（正文回退已删） |
| `SETTINGS_HANDLE_JS` | 52–60 | **有** | `document.body.innerText` 取首个 @mention | **残留正文回退，FAIL** |
| `CLICK_SWITCHER_JS` | 62–69 | 无 | — | 含 `b.click()`（账号切换按钮） |
| `MENU_HANDLE_JS` | 71–86 | 无 | 读取 `AccountSwitcher_Logout_Button`/`[role=menu]` 文本 | 合格（菜单文本） |

- 证据：`evidence/source_check_after.json`；`residual_body_fallbacks=["SETTINGS_HANDLE_JS"]`，`HANDLE_JS_clean=true`，`handle_sequence_has_switcher_click/menu/settings=true`。
- 关键源码（当前）：
  - `HANDLE_JS` 39–47：只从 `SideNav_AccountSwitcher_Button` 的文本/aria-label 取 @handle；取不到返回 null。
  - `SETTINGS_HANDLE_JS` 54–58：先读 `input[name="username"]`；若没有，则 `const text = document.body ? document.body.innerText : ''; const m = text.match(/@(...)/); return m ? m[1] : null;` —— 这正是任务要求删除的“正文回退”，只是移到了 settings 分支。
- 因此：`HANDLE_JS` 本体通过，但 **“脚本已删除正文 @mention 回退路径”未完全满足**；settings 页结构异常时仍可能取到页面正文中的其它 @mention。该路径本轮未被触发（账号菜单成功），但属于源码级缺口，只记录不修复。
- 变更范围：独立 diff 统计 90 个 `+/-` 行，集中于 handle 块与 `_handle`/doctor 分支；脚本当前 hash 与修复提交的 after 一致，未改 search/user/tweet 主体。

## 3. login：登录态与 cookie

- 两次 doctor 均：`COOKIE_CHECK exists=True x_rows=15 auth_token=True ct0=True`；`href=https://x.com/home`；`LOGGED_IN`；exit=0。
- 只读查询 `profile\Default\Network\Cookies`（`mode=ro&immutable=1`）：`.x.com` **15 行**；名称包含 `auth_token`、`ct0`（名称布尔 true）；**未读取/打印任何 cookie 值**。
- 未重新登录、未切换/退出账号、未改 profile 登录态；未读日常 Chrome。
- 说明：账号菜单读取过程由工具内部 `HANDLE_SWITCHER_CLICKED` 触发一次只读点击（见 §6），不是人工点击；未点 Log out。
- 另对工具日志/核验日志做 `auth_token`/`ct0`/`cookie:`/`bearer` 值模式扫描：**0 命中**（`evidence/log_secret_scan.json`）。

## 4. crawl：一次 search 未被改坏

命令（默认间隔，limit 5；cwd 同上）：

```powershell
...\x_collect.py search --keyword "AI tools" --limit 5
```

- 2026-10-22T04:03:11–04:03:24Z，**exit=0**；`collected=5`、`duplicates=4`、`seen_total=41`、`elapsed_s=13.5`、`stop_reason=LIMIT`。
- JSONL：`jsonl/search_run.jsonl`（5 行、5 个唯一 tweet_id；字段 14 个齐全）；样例：
  - https://x.com/ElsaSofia__AI/status/2113118916251984027
  - https://x.com/ethpioneer/status/2113118900397236572
  - https://x.com/ApurbaKR3/status/2113118855900094673
- 字段非空：`tweet_id/url/text/author_handle/author_name/created_at/lang/replies/retweets/likes/discovered_by_keyword/fetched_at` 均 5/5；`views=3/5`、`media_urls=3/5`（页面未展示/无媒体，属正常）。
- 内部 ROUND：04:03:15→04:03:24，间隔 **9 秒**（默认 8–12s）；未触发 429/验证码；运行后无 Chrome 残留。
- 证据：`logs/search_run.log`、`raw/search_tool.log`、`jsonl/search_run.jsonl`、`evidence/search_stats.json`。

## 5. 实际账号结论（需用户确认）

- 两轮独立 doctor 均返回 **`@Johnsmathjyjp`**。
- 任务给定/期望：**`@xluchuan`**；结论：**不等于**（`equals_expected=false`），修复报告与本次复验一致。
- 用户需确认：该专用 profile 是否本应登录 `@xluchuan`；若实际就是要用 `@Johnsmathjyjp`，请更新任务/文档中的期望账号并据此验收；若应是 `@xluchuan`，当前 profile 登录了另一个账号，需要用户本人在可见窗口决定是否重新登录（本轮未做任何账号操作）。
- 策划验收记录已注明“用户确认不是 @xluchuan，后续报告用 @Johnsmathjyjp”；本报告仍把它作为**待用户最终确认项**，不把 handle 当业务结论。

## 6. 只读边界（含关键 caveat）

- 本次未手工点击 Like/Retweet/Follow/Post/DM；未发布/私信/采购/付款。
- 但修复后的 doctor 实现会**点击账号切换按钮**读取 `Log out @handle`，并 `document.body.click()` 关闭菜单；两次日志均出现 `HANDLE_SWITCHER_CLICKED`。这是本轮唯一非 DOM 读取的 UI 动作，不是写操作，也不是人工点击；任务字面要求“不点击任何按钮（只读 DOM）”，与本实现存在冲突，需策划确认是否接受该只读交互。
- search 仍只做 `tab.evaluate`/滚动/读 DOM；未新增点击路径。

## 7. 哈希前后

- `evidence/hashes_before.json`（04:01:32Z）与 `hashes_after.json`（04:03:56Z）：**11 个文件完全一致**，mismatches=0。
- 业务库 `instance/app.db` `e073f828cf0f30d6206361bba3a729826be096be3308f5a5dc204406dae4eb85`（241,664 B，仅文件哈希；WAL/SHM=false）。
- `requirements.txt` `0af19a0f…`；`CONTRACT.md` `826c24cc…`；wiring `bafcf397…`；bilibili_view `b0dc0ced…`；importer `a11eaf4d…`；real_link `46cbd635…`；迁移 `9b049373…`/`34d70a1d…`。
- `x_collect.py` `06ebace1…`（29,253 B，修复后 hash；前后不变）。
- DSH 配置 `cordis.patch.yml` **`b78f7ab0…`**（10,939 B）本轮前后不变；与更早 B 记录 `fda036e9…` 的差异是既有漂移（上一轮已记录），本轮未改/未回滚。

## 8. 限制与未实测

1. **source-check 未完全通过**：`SETTINGS_HANDLE_JS` 仍有正文回退；本轮 doctor 未走该分支（菜单成功），未触发错误 handle，但源码要求未满足。
2. **只读点击冲突**：doctor 内部点击账号切换按钮/关闭菜单是唯一非 DOM 动作；若“不点击任何按钮”按字面执行，本任务无法在不产生该点击的情况下运行 doctor，需策划/用户裁定。
3. **实际账号不一致**：`@Johnsmathjyjp` ≠ `@xluchuan`；用户需确认。
4. 未触发 429/验证码/`SESSION_EXPIRED`/exit2/3；未重跑 user/tweet；仅 search 一次。
5. 运行 Chrome 会更新工具自身 profile 缓存/最后访问；未手工改登录态/cookie 值；cookie 名称/行数前后均为 15。
6. 未跑完整业务测试；未改/重装依赖；未改系统代理；未启动/结束/重启 DSH。

## 9. 证据索引

| 证据 | 路径 |
| --- | --- |
| doctor wrapper 1/2 | [run1](logs/doctor_run1.log) / [run2](logs/doctor_run2.log) |
| doctor 工具日志 | [run1](raw/doctor_tool_run1.log) / [run2](raw/doctor_tool_run2.log) |
| 源码检查（after） | [source_check_after.json](evidence/source_check_after.json) |
| 两次 handle/账号摘要 | [handle_summary.json](evidence/handle_summary.json) |
| search wrapper/工具日志 | [wrapper](logs/search_run.log) / [tool](raw/search_tool.log) |
| search JSONL | [search_run.jsonl](jsonl/search_run.jsonl) |
| search stats | [search_stats.json](evidence/search_stats.json) |
| 哈希前后 | [before](evidence/hashes_before.json) / [after](evidence/hashes_after.json) |
| no-op attempt（保留） | [doctor_run1_noop_attempt.log](logs/doctor_run1_noop_attempt.log) |
| 日志凭据扫描（0 命中） | [log_secret_scan.json](evidence/log_secret_scan.json) |

## 10. 总结

- **通过**：两次 doctor handle 一致（`@Johnsmathjyjp`）、exit=0、间隔 55s；登录态复用（15 行 cookie 名称、auth/ct0 布尔）；search exit=0、5 条唯一结果、默认间隔 9s、无 Chrome 残留；11 个哈希前后一致。
- **未完全通过/待确认**：`SETTINGS_HANDLE_JS` 正文回退仍在；doctor 内部只读点击与前文“不得点击”字面冲突；实际账号不等于 `@xluchuan`，需用户确认。
- 未改代码/登录态/DSH 配置；缺陷只记录，未修复。
