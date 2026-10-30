# V9-6 报告：X 渠道只读验证 + 账号安全规范

> 任务 `task-fe725b18fabe38f48979071b14d82ad0`（rev2，计划 v9）；仅写 `docs/validation/v9/account-safety/`，并改 `MATRIX.md`/`RESEARCH.md` 各一处 X 表述。
> 2026-10-25 20:39–20:41 UTC+8。未登录新平台/未开 login 窗口；未读/打印 cookie 值；未发帖/点赞/关注/私信；未装依赖/改脚本/写业务库。

## 1. doctor

- 命令：`C:\Users\19183\.dsh\tools\x-collect\venv\Scripts\python.exe scripts\x_collect.py doctor`；cwd `D:\桌面\two`。
- wrapper `logs/doctor.log` **exit 0**；工具原始 `logs/doctor_tool.log`；UTC `2026-10-25T12:39:50Z`。
- handle **@Johnsmathjyjp**；cookie 仅名称/布尔：`auth_token=True`、`ct0=True`、`x_rows=14`（不读值）。
- 旧 `docs/validation/x-collect/REPORT.md` 记录 `@xluchuan`；本次不同，**待用户确认归属**，不推断。
- 只证明当前专用 profile 可读，不等于 X 全站可采。

## 2. search

- 命令：`x_collect.py search --keyword "Notion template" --limit 5 --interval-min 8 --interval-max 10`；wrapper `logs/search.log` **exit 0**。
- 5 条、duplicates=0、stop=LIMIT、8.1s；字段 `tweet_id/url/text/author_handle/author_name/created_at/lang/replies/retweets/likes/views/media_urls/discovered_by_keyword/fetched_at`。
- raw `raw/search_5.jsonl`、`raw/search_stats.json`；工具日志 `logs/search_tool.log`。
- 样本极小，不作为需求结论；未翻页/长跑；未遇验证码。

## 3. 账号安全

见 [ACCOUNT-SAFETY.md](ACCOUNT-SAFETY.md)：专用 profile 隔离、只读白名单、限速/单量、风控即停不重试、cookie 只查名称、登录仅用户本人、账号台账、多平台五步、红线。用户三条要求已写成可执行规则：可提供账号、保存登录态不重复登录、不影响/不封禁账号。

## 4. 矩阵/调研表述

- `platform-matrix/MATRIX.md`：新增 **X（扩展候选）** 行，标注 `agent-reach twitter 后端未装；x-collect 可用`，证据等级“实测-只读小样本”；不把它列为 10 个核心国内平台，不删既有受阻记录。
- `research-collection/RESEARCH.md` §1.2：保留“旧 web_search 未命中 X 原帖”的记录；新增“x-collect 可用（doctor exit0、@Johnsmathjypp；search 5 条）”的修正结论，明确 **agent-reach twitter 后端未装**；历史受阻记录不删。

## 5. 限制

- handle 与旧记录不一致，归属待用户确认；不推断。
- 仅 5 条、单次 search；未验证长跑、翻页、评论/楼中楼、其它平台、登录后写能力（禁止）。
- doctor 成功不等于 X 全站可采；样本不代表需求。

## 6. 安全扫描

- 对 `account-safety/` 内 md/log/json/jsonl 做正则扫描：`auth_token`/`ct0` 长值未出现（False），未发现 password 赋值；手机号正则唯一命中是 tweet_id/url 的 15–19 位数字串，非手机号字段。报告/日志只出现 cookie 名称与布尔。

## 7. 证据

- `logs/doctor.log`、`logs/doctor_tool.log`、`logs/search.log`、`logs/search_tool.log`
- `raw/search_5.jsonl`、`raw/search_stats.json`
- `sha_manifest.json`
