# V9-10 返工报告：改为首页 DOM 点击导航（成功 1 条入隔离库）

> 任务 `task-43dd80ca8bb52a47ea953abca0bdb8e4`（rev5，返工仅改导航方式）。2026-10-26 11:07–11:13 UTC+8。
> 可见窗口；**2 次页面加载**（首页 + 点击，≤2）；间隔 15s；未登录/扫码/点赞/评论/关注/翻页；未装依赖、未写业务库。
> 前版直接 `browser.get(note_url)` 的 3 次错误页结果保留在 `REPORT_V9_10.md`；本报告是点击导航的最终结果。

## 1. note-probe（点击导航）

| 项 | 值 |
| --- | --- |
| cmd | `C:\Users\19183\.dsh\tools\x-collect\venv\Scripts\python.exe -X utf8 tools/selection/xhs_probe.py --mode note --max-tries 1 --interval 15` |
| cwd | `D:\桌面\two` |
| start_utc / exit | **2026-10-26T03:07:54Z** / **exit 1**（运行完成后 `online` 分支 KeyError；已改为纯 `exit_code(result)` 并加单测，未重跑网络） |
| 页面加载 / 请求 | **2 / 2**（首页 1 + 点击 1，≤2）；间隔 15s；`headless=False` |
| 点击目标 | 首页 `section.note-item a.title`（首选），成功进入 `/explore/6adb175e000000002a029839` |
| 点击后 query | `xsec_source` 长度 7、`xsec_token` 长度 46；**仅记录键名/长度，不落 token 明文** |
| 登录墙/风控 | 未触发；非错误页 |

**与直接 URL 的对比**：前版直接 `https://www.xiaohongshu.com/explore/<id>` 三次均“页面不见了”；本次首页点击带 referer/token 后同域名正常打开笔记，说明前版失败至少部分是导航方式/缺少 `xsec_token` 导致，不能把链接判死。点击后的 URL 查询长度证明 `xsec_token` 存在（值未保存）。

## 2. fields（期望 vs 实际）

| 字段 | 期望 | 实际 |
| --- | --- | --- |
| native_id | 有 | 有：`6adb175e000000002a029839` |
| title | 有 | **有**（正文标题，报告不展开） |
| desc | 有 | **有**（摘要已入隔离库，报告不展开） |
| author_redacted / author_hash | 有 | true / `068fd3ab8ab5`（hash；无昵称原文） |
| likes | 有 | **缺失** |
| publish_time | 有 | **缺失** |
| comment_entry_present | true | **true** |

- 真笔记判定：无 `ERROR_MARKERS`，`error_page=false`，`desc` 非空，`complete=true`。
- 错误页判定仍保留：标题含“你访问的页面不见了”等即拒绝；前版 3 条均被拒，本版未误收。
- `likes/publish_time` 缺失：当前页面/meta 结构未提供或未命中；未硬编假值。

## 3. raw / 脱敏

- 点击页 DOM 骨架：`docs/validation/v9/xhs-readiness/raw/note_click_20261026T030754Z.html`，**56,981 B**，sha256 `f14536fd3fab005063ddaf434bab5ac725876c537484b1d5c612371158bd11f5`。
- 已检查：无 `小红薯`/`nickname`/未脱敏 `/user/profile/`；文本节点全部丢弃；query 不写入 raw。
- 首页 href query 只记录键名/长度；无 token 明文。

## 4. db / categorize

- 隔离库：`tools/selection/runtime/xhs_first.sqlite3`。
- 写入 **1 条**：`signals=1`；`signal_id=2`；`origin_kind=real`；`batch_id=first-real-2026-10-26T03:07:54Z`；`content_hash=6e43568ef4f7a3aa973eec4364ba76a23e03c1cde3819373c8fd7ca01c0b7b54`。
- `run_categorize`：`signals=1, new=0, update=0, review=1, categories=0`；`make_cards`：`created=0, cards=0`；review=1。
- 0 的 categories/cards 如实记录（本条进入复核，未生成品类/卡）；未写默认 selection 库/业务库。

## 5. 台账（两处）

- `docs/validation/v9/xhs-readiness/LEDGER.md:9` 与 `docs/validation/v9/account-safety/ACCOUNT-SAFETY.md:68`：
  - 保留“可见窗口实测可用（02:39:27Z，25 条 explore 链接）；headless verify 属无头误判，勿据此重登”；
  - 追加 note-click **03:07:54Z 成功 1 条**（title/desc/author_hash/comment；likes/publish_time 缺；signals=1、review=1、categories=0、cards=0；batch）。
- 未写“笔记详情不可采”；点击已证明可采。

## 6. tests

| suite | 结果 | 日志 |
| --- | --- | --- |
| selection（基线 87 + exit_code 1） | **88 tests OK** | `tools/selection/logs/tests_selection_v910e.log` exit0 |
| workbench | **218 tests OK** | `tools/selection/logs/workbench_v910e.log` exit0 |
| 项目全套（基线 421 + 1） | **422 tests OK** | `tools/selection/logs/project_v910e.log` exit0 |

- 新增 `test_note_exit_code_completed`：note-click completed→0；未完成→6；
- 其余 note 错误页/顺延/字段/单条上限测试保留。
- cwd `D:\桌面\two`；UTC 03:07–03:13（本地 11:07–11:13）。

## 7. 限制 / 未验证

- 真实运行 exit=1 是运行后的 exit 分支 bug（`online` KeyError）；已改为 `exit_code()` 并由单测断言 0，但**未重跑网络**（页面加载上限已用 2 次）。
- 仅 1 条有效笔记、单次观察；`likes/publish_time` 缺失，未验证其真实结构；未验证多篇/翻页/评论/搜索页/长期稳定性。
- 可见窗口未独立抓取句柄/标题；只确认 `headless=False` 真实运行。
- raw 为脱敏 DOM 骨架，不是完整 HTML；query 仅长度，无明文 token。
- stderr 有 nodriver/asyncio ResourceWarning 收尾警告，不影响结果。
