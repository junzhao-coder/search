# x-collect（B1+B2）安装、登录与 doctor 记录

> 任务：`task-74ef1f9bb8cc648a919097a9966473c2`（计划 v5，执行者 B）。范围：`docs/validation/x-collect`。
> 记录时点：2026-10-22（UTC+8）。DSH 已重启，GUI 端口 2681；未重启/结束 DSH。
> **结论：目录与独立 venv 已建立；用户本人已在专用 profile 完成 X 小号登录；doctor 返回 `LOGGED_IN handle=@xluchuan`，退出码 0。**

## 0. 状态总表

| 项目 | 状态 |
| --- | --- |
| root / venv | ✅ `C:\Users\19183\.dsh\tools\x-collect\{profile,venv,data,logs,scripts}`；venv Python 3.12.10；`nodriver 0.50.6` |
| login-window | ✅ 可见 Chrome（`user_data_dir=profile`，进程级代理 `127.0.0.1:10808`），用户本人登录小号；等待到 `/home` 约 **72 秒** |
| doctor | ✅ `LOGGED_IN handle=@xluchuan utc=2026-10-22T02:49:43Z`，**exit=0**；本次 headless 直接成功 |
| collection | ✅ search 5 条 / user 5 条 / tweet 1 条 / replies 5 条，均 exit=0；字段统一、去重、8–12s 限速已实测（见 §8） |
| hashes | ✅ 工作区 8 个关键文件、业务库、DSH 核心 package.json、mcp-client 目录树前后一致 |
| 凭据 | ✅ 未读取/记录任何 cookie 值、密码、验证码、邮箱/手机号；未截图登录页 |
| 边界 | ✅ 仅写本工具目录 + 报告目录；未碰日常 Chrome/DSH 配置；未装浏览器；未做发布/点赞/关注/私信 |

## 1. 路径与目录

| 项 | 值 |
| --- | --- |
| DSH_HOME | `C:\Users\19183\.dsh` |
| 工具根 | `C:\Users\19183\.dsh\tools\x-collect` |
| Chrome | `C:\Program Files\Google\Chrome\Application\chrome.exe`（v155.0.8059.86，4,720,792 B） |
| venv Python | `C:\Users\19183\.dsh\tools\x-collect\venv\Scripts\python.exe`（3.12.10） |
| CLI 脚本 | `scripts\x_collect.py`、`scripts\baseline.py` |
| 专用 profile | `profile\`（仅本工具使用） |
| 日志 | `logs\` |

目录清单（`login/tree.json`）：

| 目录 | 文件数 | 字节 |
| --- | --- | --- |
| `profile` | 3,144 | 476,486,462 |
| `venv` | 1,227 | 18,971,868 |
| `scripts` | 2 | 15,661 |
| `logs` | 15 | 18,691 |
| `data` | 0 | 0 |

## 2. 基线哈希（before/after 完全一致）

证据：`login/before.json`、`login/after.json`、`login/hash_compare.json`（`changed_workspace_files=[]`）。

| 文件/目标 | sha256（前后相同） |
| --- | --- |
| `requirements.txt` | `0af19a0f1c100e99483b79e7f11b500ccf6a5a1477d8ac4b560c077b2bea7731` |
| `docs/design/CONTRACT.md` | `826c24cc6c99551178875bed617e085231bd23998b6a049f396116e1e70fb4f9` |
| 冻结三文件 `wiring.py` / `bilibili_view.py` / `importer.py` | `bafcf397…` / `b0dc0ced…` / `a11eaf4d…`（完整值见 after.json） |
| `app/sources/real_link.py` | `46cbd635b5e70cc2d1b6441befde31e25b8203caf28d39b772203c43b8f5802c` |
| 迁移 0001 / 0002 | `9b049373…` / `34d70a1d…` |
| 业务库 `instance/app.db` | `e073f828cf0f30d6206361bba3a729826be096be3308f5a5dc204406dae4eb85`（**仅文件哈希，未 SQL 打开**；`-wal/-shm` 均不存在） |
| DSH 核心 `dsh/package.json` | `b67a65b9…`（前后相同） |
| `@deepseek-ai/dsh-mcp-client` 目录树 | `9fc3a99a4b5eddf6facc485a60e5fecfd6764314ad9028b7cca88fce2a8a9ea4`（6 文件，前后相同） |

## 3. 登录过程（可见窗口）

1. 启动：`venv\Scripts\python.exe scripts\x_collect.py login --timeout 1200`（后台 job），Chrome `headless=False`，`user_data_dir=...\profile`，进程级 `--proxy-server=http://127.0.0.1:10808`（读取系统代理，仅本进程；未改系统代理）。
2. 窗口打开后打印 `WAITING_FOR_USER_LOGIN`，并弹窗提示用户“可以登录”；**执行者不旁观输入、不截图、不读取页面输入**。
3. 用户在窗口内自行登录 X 小号；02:47:16 页面进入 `https://x.com/home`，窗口标题为 `(2) Home / X`（已登录态）。
4. 由于 Chrome 打开期间 cookie 只在内存、磁盘 Cookies 表暂为 0 行，执行者停止等待进程，并用 **CDP `Browser.close`** 优雅关闭（`close_and_flush.json`：reply `{"id":1,"result":{}}`，`chrome_left=0`）；关闭后 Cookies 表 `.x.com` 共 14 行，**`auth_token=True`、`ct0=True`**（仅名称/行数，未读取值）。
5. 脚本已修正：登录检测改为 DOM 账号按钮 handle；关闭后先校验 `auth_token/ct0` 再运行 doctor，避免再次出现“只看 URL 误判”或反复弹窗。

时间：窗口 02:46:04 打开，02:47:16 到 `/home`（约 72 s），02:49 前后关闭；总窗口约 3.5 分钟，远小于 20 分钟上限。

## 4. doctor 结果

命令（同一 profile，headless 优先）：

```powershell
C:\Users\19183\.dsh\tools\x-collect\venv\Scripts\python.exe `
  C:\Users\19183\.dsh\tools\x-collect\scripts\x_collect.py doctor
```

真实输出（`login/logs/doctor-2026-10-22T024937Z.log`，已复制到报告）：

```text
2026-10-22T02:49:37Z COOKIE_CHECK exists=True x_rows=14 auth_token=True ct0=True
2026-10-22T02:49:37Z START doctor headed=False profile=C:\Users\19183\.dsh\tools\x-collect\profile
2026-10-22T02:49:41Z DOCTOR href=https://x.com/home title='(2) X' bodylen=130 html_len=836676
2026-10-22T02:49:43Z LOGGED_IN handle=@xluchuan utc=2026-10-22T02:49:43Z
LOG=...\logs\doctor-2026-10-22T024937Z.log EXIT=0
```

- **handle：`@xluchuan`**；**exit=0**；UTC `2026-10-22T02:49:43Z`。
- 本次 doctor **headless 直接成功**，未触发 headed 兜底（`doctor_result.json`：`headless_fallback=false`）。
- 历史对照：未登录时 headless 曾返回 `chrome-error://chromewebdata/`（X 拦截无登录态 headless），headed 兜底可打开登录页——已记录在 `logs/doctor-2026-10-22T022442Z.log` 等；这解释了此前反复弹窗，现已在 doctor 启动前用 cookie 检查短路，**未登录不会再开窗口**。

## 5. 证据清单（`docs/validation/x-collect/`）

| 证据 | 内容 |
| --- | --- |
| `login/before.json` / `after.json` / `hash_compare.json` | 前后哈希、业务库/Chrome/DSH 核心/mcp-client、目录统计 |
| `login/profile_diagnosis.json` | 未登录根因：仅 guest cookies、无 auth_token/ct0；URL 误判；headed 兜底弹窗 |
| `login/10_chrome_processes.json` | 所有 Chrome 进程命令行（均指向 x-collect profile；仅结束本工具进程） |
| `login/tree.json` | 工具目录清单/大小/脚本 sha |
| `login/doctor_result.json` | doctor 的 handle/exit/UTC/headless 标志 |
| `login/logs/doctor-2026-10-22T024937Z.log` | doctor 原始日志（含 LOGGED_IN） |
| `login/attempt_024603_stdout.txt` | 登录等待 job stdout 摘录（登录日志因进程被停止未落盘，如实注明） |
| `login/close_and_flush.json` | CDP 优雅关闭与关闭后 cookie 名称/行数 |
| `scripts/x_collect.py` / `scripts/baseline.py` | 工具脚本（可复现） |

日志/报告不含任何 cookie/token/密码/验证码/邮箱手机号；cookie 仅检查名称与行数，未读取或打印值。

## 6. 卸载步骤

```powershell
# 1) 只结束本工具启动的 Chrome / python（按 profile 命令行过滤，勿碰日常 Chrome）
Get-CimInstance Win32_Process -Filter "Name='chrome.exe'" |
  Where-Object { $_.CommandLine -like '*x-collect*' } |
  ForEach-Object { Stop-Process -Id $_.ProcessId -Force }
Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
  Where-Object { $_.CommandLine -like '*x_collect.py*' } |
  ForEach-Object { Stop-Process -Id $_.ProcessId -Force }

# 2) 删除工具根（profile/venv/data/logs/scripts 一并删除）
Remove-Item -Recurse -Force "C:\Users\19183\.dsh\tools\x-collect"

# 3) 报告目录可保留或按需删除（不影响 DSH）
# Remove-Item -Recurse -Force "D:\桌面\two\docs\validation\x-collect"
```

不触碰：`%LOCALAPPDATA%\Google\Chrome\User Data`（日常 Chrome）、DSH profiles/cordis、AgentReach/Stealth 目录与 Skill、DSH 配置。

## 7. 限制与说明

1. **登录等待脚本的日志文件缺失**：检测到已登录后执行者停止了等待进程（避免继续轮询），`RunLog.close()` 未执行；已用 job stdout 摘录 + doctor 日志 + CDP 关闭记录补证，未伪造日志。
2. **手动优雅关闭**：本次用 CDP `Browser.close` 代替脚本关闭，以验证 cookie 落盘；脚本已改为自动 DOM 检测 + 优雅关闭 + 关闭后 auth cookie 校验，但该修订版**未再执行登录**（避免再次弹窗）。
3. **headless 依赖登录态**：未登录时 headless 被 X 拦截（chrome-error），doctor 会 fallback headed 并打开登录页；现已在启动前检查 `auth_token/ct0`，未登录直接 exit 2、不开窗口。
4. **profile 含加密 cookie**：`profile\` 体积 476 MB，包含会话凭据（加密），不得复制/外发；报告与日志只记录名称/行数。
5. 未运行 325 业务测试（无业务代码变更）；未做任何发布/点赞/关注/私信/采集动作；未访问非 x.com 站点。
6. **B3 限制**：`search/user/tweet` 已实现并跑通小样本；真实 exit 2（登录失效）与 exit 3（429/验证码）未触发（当前会话正常），仅代码路径；`views`/互动数页面不展示时为 null/0，不编造；`--with-replies` 取页面可见线程文章（最多 20），不保证严格父子层级；本轮未跑 15 分钟超时上限（样例均在 LIMIT/SINGLE 停止）。

## 8. B3 只读采集（search / user / tweet）

> 实现：`scripts\x_collect.py` 新增 `search` / `user` / `tweet`；同一 profile、headless、只读 DOM 提取；不点赞/转推/关注/私信/发布；不读 cookie 值。

| 运行 | 命令（摘要） | exit | 条数 | 耗时 | 重复 | 证据 |
| --- | --- | --- | --- | --- | --- | --- |
| search | `search --keyword Anthropic --limit 5 --interval-min 8 --interval-max 8` | **0** | 5 | 5.1 s | 0 | `collect/samples/search-2026-10-22T031103Z.jsonl`、`stats_search.json`、`logs/search-2026-10-22T031058Z.log` |
| user | `user --handle OpenAI --limit 5 --interval-min 8 --interval-max 8` | **0** | 5 | 35.5 s | 6 | `collect/samples/user-2026-10-22T031155Z.jsonl`、`stats_user.json`、`logs/user-2026-10-22T031120Z.log` |
| tweet | `tweet --url https://x.com/OpenAI/status/2107895002022187411` | **0** | 1 | 5.1 s | 0 | `collect/samples/tweet-2026-10-22T031452Z.jsonl`、`stats_tweet.json`、`logs/tweet-2026-10-22T031447Z.log` |
| tweet + replies | 同上加 `--with-replies --limit 5` | **0** | 5 | 27.6 s | 13 | `collect/samples/tweet-2026-10-22T031552Z.jsonl`、`stats_tweet_replies.json`、`logs/tweet-2026-10-22T031525Z.log` |
| 解析空分支 | `tweet --url https://x.com/OpenAI/status/1` | **4** | 0 | 24.7 s | 0 | `logs/tweet-2026-10-22T031709Z.log`（PARSE_EMPTY） |

- 统一字段（每行一条，UTF-8 无 BOM）：`tweet_id / url / text / author_handle / author_name / created_at / lang / replies / retweets / likes / views / media_urls / discovered_by_keyword / fetched_at`；`views` 页面未展示时写 `null`（已实测）。
- 样例（原链接可点，公开推文）：
  - search：`https://x.com/marksoze/status/2113105731519946861`（text=`Ask Anthropic for a no limit key and you do it yourself`）；
  - user：`https://x.com/OpenAI/status/2107894997538525580`；
  - tweet：`https://x.com/OpenAI/status/2107895002022187411`（`Create interactive tools you can use right in the conversation…`）。
- 限速：导航/滚动之间 `sleep(random 8–12s)`；`--interval-min` 不得低于 8；单批 `limit≤60`、`wall-clock≤900s`（超时且有部分结果 exit 0；无结果 exit 3；样例均未触顶）。
- 去重：`data/seen.jsonl`（当前 23 个 tweet_id）；同批/历史重复只保留首次，重复数写入 stats（user=6、replies=13）；`seen_total` 随样本增长。
- 错误分支（代码实现）：登录跳转/无 auth → **exit 2**；429/验证码/Challenge/"Something went wrong" → **exit 3** 并保存 `data/errors/*.txt`（仅 URL/标题/正文片段，无凭据）；页面正常但无 article → **exit 4**（已用无效 tweet 实测）。
- 停止条件：达到 limit、连续 3 轮无新增（END）、15 分钟上限（TIMEOUT）；本轮样例分别在 LIMIT/SINGLE 停止。
- 未触发：exit 2/exit 3 的真实页面（当前会话正常，无验证码/429）；代码路径已实现但未做破坏性触发。`views`/互动数依赖页面 aria-label，页面不展示时为 null/0，未编造。

### B3 证据

- `collect/samples/*.jsonl`：search 5 / user 5 / tweet 1 / replies 5；
- `collect/stats_*.json`：每轮 stats（exit、elapsed、collected、duplicates、nonempty_text_ratio、jsonl 路径）；
- `collect/logs/*.log`：命令/URL/ROUND/STATS/EXIT（UTF-8）；
- `collect/summary.json`、`collect/hash_after_collect.json`（工作区关键文件与业务库仍一致，`wal/shm=false`）。

