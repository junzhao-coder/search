# x-collect 独立核验（计划 v5 B4 · 非实现者）

> 任务：`task-7e6e716b2315014d7fb4699ce842bef7`（revision 2，计划 v5）；核验者 session-01ba487c…，**未参与 x-collect 实现**（实现者 session-2e7e3159）。
> 范围：`docs/validation/x-collect/verify`；**未改**工具代码、登录态、profile 内容、DSH 配置与业务系统；未发布/点赞/关注/私信。
> 采样时间：2026-10-22 03:43–03:48 UTC（11:43–11:48 UTC+8）。命令/cwd/UTC/真实 exit 均见 `logs/`、`raw/`；日志 UTF-8 无 BOM。
> 结论先行：**search / de-dupe / read-only / rate-limit / hashes 通过；doctor 的 handle 字段失败**——两次新进程 doctor 返回 `@5ay9jxad693631` 与 `@bianokx_momo`，均非 `@xluchuan`，不能宣称“doctor 确认 handle”通过。

## 0. 状态表（按要求分列）

| 类别 | 结论 | 关键证据 |
| --- | --- | --- |
| persistence | **PASS（登录态）/ FAIL（handle）** | 新进程 doctor exit=0、`LOGGED_IN`、auth cookie 名称存在；但两次 handle 不同且非 @xluchuan（§1） |
| search | **PASS** | 两次 search 均 exit=0；5 条 + 8 条真实结果；字段统计见 §2 |
| de-dupe | **PASS** | 第二次 `duplicates=22`，输出 8/8 唯一；seen 23→28→36 只增不改（§3） |
| read-only | **PASS** | 脚本静态扫描 0 个 click/type/send/Post/DM/like/follow 动作；仅 evaluate/滚动/读取 DOM（§4） |
| rate-limit | **PASS** | 第二次搜索 ROUND 间隔 10/10/9 秒（≥8）；两轮 search 起点间隔 82 秒（≥60）（§4） |
| credentials | **PASS** | 工具/核验日志 0 条凭据值命中；脚本 0 条；cookie 仅名称/行数（14 行，含 auth_token/ct0 名称）（§5） |
| hashes | **PASS（本轮前后）** | 业务库/冻结/requirements/CONTRACT/迁移/x_collect.py 前后一致；DSH 配置本轮前后一致（§6） |
| limits | 见 §7 | doctor handle 缺陷、run1 未触发内部间隔、未触发 429/验证码、既有 DSH 配置漂移 |

## 1. doctor（新进程 / 同一 profile）

命令（cwd=`C:\Users\19183\.dsh\tools\x-collect`）：

```powershell
C:\Users\19183\.dsh\tools\x-collect\venv\Scripts\python.exe `
  C:\Users\19183\.dsh\tools\x-collect\scripts\x_collect.py doctor
```

### 1.1 第一次（验收指定命令）

- `logs/doctor_run.log`：`start_utc=2026-10-22T03:44:07+00:00`，**exit=0**，耗时约 7 秒。
- 工具日志 `raw/doctor_tool_run1.log`：
  - `COOKIE_CHECK exists=True x_rows=14 auth_token=True ct0=True`（仅名称/布尔，不打印值）；
  - `PROXY=system process-level (127.0.0.1:10808)`；
  - `DOCTOR href=https://x.com/home title='Home / X' bodylen=147 html_len=848688`；
  - `LOGGED_IN handle=@5ay9jxad693631 utc=2026-10-22T03:44:14Z`；`EXIT=0`。
- 运行后无 x-collect Chrome 残留（进程检查为空）。

### 1.2 第二次（同一 profile，新进程复核）

- `logs/doctor_run2.log`：`start_utc=2026-10-22T03:44:33+00:00`，**exit=0**，耗时约 5 秒。
- `raw/doctor_tool_run2.log`：`LOGGED_IN handle=@bianokx_momo utc=2026-10-22T03:44:38Z`；`EXIT=0`。
- 两次均无登录跳转，`href=https://x.com/home`；但 handle **不相同**，且都不是任务给定的 `@xluchuan`（B 报告 §4 当时记录为 `@xluchuan`）。

### 1.3 判定与根因（只记录，不修复）

- **persistence：登录态复用成立**——新进程/同一 profile、doctor exit=0、`LOGGED_IN`、14 个 x.com cookie 名称（含 `auth_token`/`ct0`，未读值），且 search 成功取到真实结果（§2）。
- **doctor handle：FAIL**——两次输出不同随机 handle，不能确认当前账号为 `@xluchuan`。源码 `HANDLE_JS`（x_collect.py 39–51 行）先找 `SideNav_AccountSwitcher_Button`，找不到时**回退扫描页面正文第一个 `@mention`**；doctor 页面 `bodylen=126~147`，账户按钮可能未出现，回退会取到信息流作者 handle。该字段不可作为账号身份的可靠证据。
- 未改工具代码/登录态；该缺陷留待实现者修复。

## 2. 独立 search

命令（同一 cwd；`--interval-min 8 --interval-max 8`）：

```powershell
...\python.exe ...\x_collect.py search --keyword "notion template" --limit 5 --interval-min 8 --interval-max 8
...\python.exe ...\x_collect.py search --keyword "notion template" --limit 8 --interval-min 8 --interval-max 8
```

| 运行 | 起止 UTC | exit | 条数 | duplicates | seen_total | 原始 JSONL |
| --- | --- | --- | --- | --- | --- | --- |
| run1（limit 5） | 03:44:56–03:45:01 | **0** | 5 | 0 | 28 | `jsonl/search_run1.jsonl`；工具日志 `raw/search_run1_tool.log` |
| run2（limit 8） | 03:46:18–03:46:52 | **0** | 8 | **22** | 36 | `jsonl/search_run2.jsonl`；工具日志 `raw/search_run2_tool.log` |

> run2 使用 limit 8 是为强制至少一次滚动、实测内部限速；两次关键词相同，limit 不同（5/8）已作为限制记录。

### 2.1 字段非空率（0 计为有值；空串/空数组/null 计为空）

| 字段 | run1（5 条） | run2（8 条） |
| --- | --- | --- |
| tweet_id / url / text / author_handle / author_name / created_at / lang | 5/5（100%） | 8/8（100%） |
| replies / retweets / likes / views | 5/5（100%） | 8/8（100%） |
| discovered_by_keyword / fetched_at | 5/5（100%） | 8/8（100%） |
| media_urls | 0/5（0%，本批无媒体） | 2/8（25%） |

完整统计：`evidence/search_analysis.json`。

### 2.2 三条 tweet 的公开入口核对（web_fetch，不是自家抓取）

方法：用 `web_fetch https://api.fxtwitter.com/status/<id>`（HTTP 200），比对 tweet_id/url/author/created_at 与正文片段；fxtwitter 仅作外部核对，不作为 x-collect 的抓取结果。

| tweet_id | 原链接 | fxtwitter | 作者/时间 | 正文片段 |
| --- | --- | --- | --- | --- |
| 2113079963796516926 | https://x.com/bulba_gunwook/status/2113079963796516926 | 200 | bulba_gunwook / 2026-10-22T01:28:17Z | “Found it. To track individual days I use a template…” 匹配 |
| 2113042387169853575 | https://x.com/bulba_gunwook/status/2113042387169853575 | 200 | bulba_gunwook / 2026-10-21T22:58:58Z | “I use a notion template that runs numbers…” 匹配 |
| 2112996273897005393 | https://x.com/Arjun432992/status/2112996273897005393 | 200 | Arjun432992 / 2026-10-21T19:55:43Z | “If you are looking for an effective note taking strategy…” 匹配 |

- 三条均 `text_probe_match=true`；本地/外部 author 与 created_at 一致；证据 `evidence/fxtwitter_compare.json`。
- 本地正文可能去掉 @mention 前缀（X `tweetText` 行为），比对采用去空白后的有效片段，不要求字节完全相等。

## 3. 两次运行去重与 seen.jsonl

- run1：5 条、5 个唯一 tweet_id；run2：8 条、8 个唯一 tweet_id；**两次输出内部 0 重复**；合计 13 个唯一 id。
- run2 `duplicates=22`（首轮 5 个已见 + 后续滚动重复），未写入重复 id；满足“第二次 duplicates>0 且输出不重复”。
- `seen.jsonl`：**23 → 28 → 36** 行；`before_prefix_after1=true`、`before_prefix_after2=true`、`after1_prefix_after2=true`；唯一 id 23→36，重复 id 0。只增不改。
- 快照：`raw/seen_before.jsonl`、`raw/seen_after1.jsonl`、`raw/seen_after2.jsonl`；对比 `evidence/search_analysis.json`。

## 4. 只读边界与限速

### 4.1 只读静态检查

- `evidence/static_scan_after.json`：脚本中 **0** 个 `click/type/send_keys/keyboard/mouse/like/retweet/follow/post/dm` 动作模式；工具日志/核验日志 **0** 条凭据值命中；脚本 **0** 条凭据值命中。
- 脚本实际只做：`tab.evaluate(...)`（读取 DOM/执行 `window.scrollBy`）、`tab.get_content()`、`browser.close()`（CDP 关闭）；没有按钮点击、输入、发送、发布路径。
- 未执行 Like/Retweet/Follow/Post/DM；未导入账号/Cookie/Key。

### 4.2 限速实测

- 第二次搜索工具日志：`ROUND=0 03:46:23` → `ROUND=1 03:46:33` → `ROUND=2 03:46:43` → `ROUND=3 03:46:52`；间隔 **10、10、9 秒**，均 ≥8s。
- run1 首轮即达 limit（visible 6，added 5），无滚动轮次，故 run1 本身没有内部间隔样本；run2 补足。
- 两次 search 起点间隔 **82 秒**（03:44:56→03:46:18），run1 结束到 run2 开始 **77 秒**，均 ≥60 秒。
- 代码将 `imax` 下限抬到 12（`imax=max(args.interval_max, imin, 12)`），因此传入 `--interval-max 8` 实际仍会在 8–12 秒随机；实测 9–10 秒。未触发 429/验证码。

## 5. 凭据与 profile 检查

- 脚本/工具日志/核验日志：`auth_token`/`ct0`/`cookie:`/`bearer` 值模式 **0 命中**；doctor 日志只打印 `auth_token=True`、`ct0=True` 布尔和 `x_rows=14`。
- `profile\Default\Network\Cookies` 只读查询（`mode=ro&immutable=1`）：
  - `.x.com` cookie **14 行**；名称包含 `auth_token`、`ct0`（名称存在=true）；
  - **未读取/未打印任何 cookie 值**；仅名称/行数。
- 未读取日常 Chrome profile；未复制/外发 profile；未截图登录页。

## 6. 哈希前后对比

- `evidence/hashes_before.json`（03:43:48Z）与 `hashes_after.json`（03:47:48Z）：10 个受控文件 **完全一致**，mismatches=0。
- 业务库 `instance/app.db`：`e073f828cf0f30d6206361bba3a729826be096be3308f5a5dc204406dae4eb85`（241,664 B，仅文件哈希，未 SQL 打开）；`wal=false`、`shm=false`。
- 其余：`requirements.txt` `0af19a0f…`；`CONTRACT.md` `826c24cc…`；`wiring.py` `bafcf397…`；`bilibili_view.py` `b0dc0ced…`；`importer.py` `a11eaf4d…`；`real_link.py` `46cbd635…`；两迁移 `9b049373…`/`34d70a1d…`；`x_collect.py` `efd95bca…`。
- **DSH 配置**：`C:\Users\19183\.dsh\profiles\desktop\cordis.patch.yml` 本轮前后均为 `b78f7ab0…`（10,939 B，mtime `2026-10-21T14:11:28Z`），未因本轮改变。
- 既有差异（记录，不归因本轮）：B 报告记录的该配置 after 值为 `fda036e9…`（10,899 B），当前已是 `b78f7ab0…`（+40 B）；变化发生在 2026-10-21T14:11:28Z（本轮之前），本轮未改、未回滚。

## 7. 限制与未实测项

1. **doctor handle 不可信（FAIL）**：两次不同随机 handle，均非 `@xluchuan`；根因是 `HANDLE_JS` 回退取正文首个 @mention。登录态本身可由 auth cookie 名称 + search 成功支持，但账号 handle 不能确认；需实现者修复后才可宣称 doctor 通过。
2. **run1 无内部滚动间隔**：limit 5 在首轮达到，未触发 `sleep(8–12)`；run2 用 limit 8 补测。两次运行关键词相同但 limit 不同（5/8），不是严格同参数复跑。
3. **未触发错误分支**：未构造 429/验证码/`SESSION_EXPIRED`/exit 2/3；无破坏性测试。
4. **只测 search**：未重跑 user/tweet/replies（B3 已有样本）；无完整业务测试（本批无业务代码变化）。
5. **profile 正常读写**：运行 Chrome 会让工具自身 profile 更新缓存/最后访问，未手工修改登录态或 cookie 值；cookie 名称/行数前后均为 14。
6. **DSH 配置基线漂移**：B 的 `fda036e9…` → 当前 `b78f7ab0…` 发生在核验前；本轮前后不变，但“与 B after 相同”不成立。
7. **无发布/点赞/关注/私信**；未改工具代码、未重装依赖、未改系统代理。

## 8. 证据索引

| 证据 | 路径 |
| --- | --- |
| doctor 运行 1/2（wrapper，真实 exit） | [doctor_run.log](logs/doctor_run.log) / [doctor_run2.log](logs/doctor_run2.log) |
| doctor 工具日志 | [run1](raw/doctor_tool_run1.log) / [run2](raw/doctor_tool_run2.log) |
| search 运行日志（wrapper） | [run1](logs/search_run1.log) / [run2](logs/search_run2.log) |
| search 工具日志 | [run1](raw/search_run1_tool.log) / [run2](raw/search_run2_tool.log) |
| JSONL 副本 | [run1](jsonl/search_run1.jsonl) / [run2](jsonl/search_run2.jsonl) |
| 字段/去重/限速分析 | [search_analysis.json](evidence/search_analysis.json) |
| fxtwitter 比对 | [fxtwitter_compare.json](evidence/fxtwitter_compare.json) |
| 只读/凭据/静态扫描 | [static_scan_after.json](evidence/static_scan_after.json) |
| 哈希前后 | [before](evidence/hashes_before.json) / [after](evidence/hashes_after.json) |
| 首轮 DSH 配置差异留档 | [hashes_before_attempt1.json](evidence/hashes_before_attempt1.json) |
| seen 快照 | [before](raw/seen_before.jsonl) / [after1](raw/seen_after1.jsonl) / [after2](raw/seen_after2.jsonl) |

## 9. 总结

- **可确认通过**：search 真实结果（5+8）、字段完整（除 media_urls 依赖内容）、两次去重（duplicates=22、输出唯一、seen 只增）、只读动作扫描 0、内部间隔 ≥8s、两轮间隔 ≥60s、日志无凭据值、业务/冻结/代码/DSH 配置本轮前后哈希一致。
- **不能宣称通过**：doctor 的 `handle` 字段（两次随机且非 `@xluchuan`）；`LOGGED_IN` 状态与登录态复用有证据，但账号身份未确认。按“未实测/失败不报 PASS”，doctor handle 记为 **FAIL**，其余按上表。
- 未改代码/登录态/DSH 配置；缺陷只记录，未修复。
