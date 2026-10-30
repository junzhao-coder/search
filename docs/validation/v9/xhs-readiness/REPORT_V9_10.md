# V9-10 直接 URL 版报告（已被点击导航返工版取代）

> 点击导航成功结果见 `REPORT_V9_10_REWORK.md`。本文件保留直接 URL 3 次错误页证据。


> 任务 `task-43dd80ca8bb52a47ea953abca0bdb8e4`（rev2，计划 v9）。2026-10-26 10:51–10:56 UTC+8。
> 可见窗口参数、复用首页骨架、**3 次请求 ≤4**、每条间隔 15s；未登录/扫码/点赞/评论/关注/翻页；未装依赖、未写业务库。

## 1. note-probe（真实运行）

| 项 | 值 |
| --- | --- |
| cmd | `C:\Users\19183\.dsh\tools\x-collect\venv\Scripts\python.exe -X utf8 tools/selection/xhs_probe.py --mode note --max-tries 3 --interval 15` |
| cwd / seed | `D:\桌面\two` / `docs/validation/v9/xhs-readiness/raw/probe_20261026T023927Z.html`（复用骨架，**未再请求首页**） |
| start_utc / exit | **2026-10-26T02:52:42Z** / **exit 1**（真实 exit；原因是跑完后 `db=None` 的 exit 分支 bug，见限制；已修但未重跑） |
| 请求 | **3**（≤4）；每条之间 15s；`headless=False` |
| 登录墙/风控 | 未触发；3 条均错误页 |

逐条：

| # | URL | 判定 | 依据 | raw / sha256 |
| --- | --- | --- | --- | --- |
| 1 | `https://www.xiaohongshu.com/explore/6adc7879000000003202324e` | `error_page` | 标题“小红书 - 你访问的页面不见了”；desc/likes/publish/comment 均无 | `raw/note_try1_20261026T025242Z.html`，18,799B，`a379c6fe…` |
| 2 | `https://www.xiaohongshu.com/explore/6ad98167000000002c00dda9` | `error_page` | 同上 | `raw/note_try2_20261026T025242Z.html`，18,763B，`48155748…` |
| 3 | `https://www.xiaohongshu.com/explore/6adbf882000000002c0209ea` | `error_page` | 同上 | `raw/note_try3_20261026T025242Z.html`，18,763B，`afdf4ede…` |

- 结果摘要：`raw/note_probe_20261026T025242Z.result.json`。每条均保存**脱敏 DOM 骨架**（无文本节点；`/user/profile/...` → `/user/profile/[redacted]`；昵称仅哈希），sha 原件在上述路径。
- **详情页结构未获样本**：3 条链接都指向已删除/不可见笔记；不硬编成功规则。

## 2. fields（期望 vs 实际）

| 字段 | 期望 | 实际（3 条相同） |
| --- | --- | --- |
| native_id | 有 | 有 |
| title | 有 | 有，但为错误页标题“小红书 - 你访问的页面不见了” |
| desc | 有 | **缺失** |
| author_redacted / author_hash | 有 | 有（仅 hash，如 `068fd3ab8ab5`；无原文昵称） |
| likes | 有 | **缺失** |
| publish_time | 有 | **缺失** |
| comment_entry_present | true | **false/缺失** |

**真笔记 vs 错误页判定**（已写入 `tools/selection/xiaohongshu.py` 的 `parse_note_fields/classify_note`（`xhs_probe` 复用））：

- 错误页特征字符串：`你访问的页面不见了` / `页面不见了` / `笔记不存在` / `404`；
- 当前 3 条 `error_page=true`、`complete=false`、`desc` 空、`likes/publish_time` 空；
- `classify_note` 返回 `error_page`，不进入 `_ingest`；旧逻辑只看 title 非空会把错误页误当完整笔记，已阻止。

- 正笔记结构仍未验证；`xiaohongshu.parse_note_fields` 仍为通用 meta/JSON 假设，等有效详情样本再校正。

## 3. db / categorize

- 隔离库 `tools/selection/runtime/xhs_first.sqlite3`：**signals=0**，未写任何行；无 `batch_id`。
- 未运行 `run_categorize/make_cards`（没有完整笔记可写），因此 categories=0、cards=0、review=0（如实记录）。
- 未写默认 selection 库/业务库。

## 4. 台账（两处 diff）

- `docs/validation/v9/xhs-readiness/LEDGER.md:9` 与 `docs/validation/v9/account-safety/ACCOUNT-SAFETY.md:68`：
  - “需重登” → **“可见窗口实测可用（2026-10-26T02:39:27Z，25 条 explore 链接）；headless verify 属无头误判，勿据此重登”**；
  - 附本次 note 结果：3 次均错误页、详情结构未获样本、未入库；
  - 本地 cookie ready，不等于在线长期有效。

## 5. tests

| suite | 结果 | 日志 |
| --- | --- | --- |
| selection（基线 86 + 顺延/字段 1 新） | **87 tests OK** | `tools/selection/logs/tests_selection_v910c.log` exit0 |
| workbench | **218 tests OK** | `tools/selection/logs/workbench_v910c.log` exit0 |
| 项目全套（基线 420 + 1 新） | **421 tests OK** | `tools/selection/logs/project_v910c.log` exit0 |

- 新增 `test_classify_note_skips_error_and_login`（错误页/登录墙/真笔记 → 第 3 条才 note，顺延逻辑）；
- 更新 `test_parse_note_fields`（publish_time/comment_entry_present）；`test_error_page_rejected`、`test_ingest_one_row_into_temp_db` 覆盖拒绝与单条上限；
- cwd `D:\桌面\two`；UTC 02:52–03:02（本地 10:52–11:02）。

## 6. 限制 / 未验证

- **3 条都失败**：详情页结构未获样本，note 字段解析仍属假设；不能据此写“真笔记字段已校正”。
- 真实 probe exit=1 是运行后 `db=None` 分支 bug；已修为 `(db or {})`，但受请求上限/不重试约束未再跑；实际数据/证据不受影响。
- 可见窗口未独立抓取句柄/标题；仅确认 `headless=False` 真实运行。
- 未验证多篇、翻页、评论、搜索页、长期稳定性、登录失效边界。
- raw 为脱敏 DOM 骨架，不是完整 HTML；stderr 有 nodriver/asyncio ResourceWarning 收尾警告。
