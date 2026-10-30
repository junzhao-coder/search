# V9-8d 运行报告（证据纠正版）：小红书专用 profile 登录窗口 + doctor

> 任务 `task-c9b56db4d019ff4dfd23ad094f7001a5`（rev5，2026-10-26 用户授权再次尝试）。
> 运行时间 2026-10-26 10:05–10:19 UTC+8（02:05–02:19Z）。真实执行一次 login，未双启、未重复弹窗；profile 保留；未截图登录屏、未导出 cookie 值、未采集帖子。
> 本版只纠正证据口径：不把 Cookies 文件 mtime 当登录时刻，不声称已查明实时检测失败原因，不从源码补造 login exit。

## 1. 启动证据（可见窗口，已实读）

| 项 | 值 |
| --- | --- |
| run_id | `xhs-login-20261026T020529Z`（Start-Process 独立进程；无 DSH job id） |
| 命令 | `C:\Users\19183\.dsh\tools\x-collect\venv\Scripts\python.exe -X utf8 C:\Users\19183\.dsh\tools\xhs-collect\xhs_collect.py login` |
| cwd | `C:\Users\19183\.dsh\tools\xhs-collect` |
| 启动 / 超时 | **02:05:29Z** / **02:10:30Z**（300s） |
| Python PID | **130584**（启动后 RUNNING=True） |
| Chrome PID | **101568**；命令行含 `--user-data-dir=C:\Users\19183\.dsh\tools\xhs-collect\profile` |
| 窗口标题 | **“小红书 - 你的生活兴趣社区 - Google Chrome”** |
| 窗口句柄 / 可见 | `458988` / **IsWindowVisible=True**；Responding=True；RECT=10,10,1060,1009 |
| 日志 | `tools/selection/logs/xhs_login_20261026.out.log` / `.err.log`；PID `...pid` |

## 2. 等待结果（不做因果推断）

- 等待到 02:10:30Z；脚本 stdout 为 **`LOGIN_TIMEOUT`**，stderr 空；Python/Chrome 随后退出（02:10:55Z 检查均为 False）。
- **login exit code：not captured**。Start-Process 的进程对象未跨 shell 保留；不从源码补造 exit，也不为补 exit 重跑 login。
- 未自动再开窗口；profile 保留。
- **Cookies 文件 mtime 观察值：2026-10-26T02:08:39Z**。这是文件时间戳观察值，**不是登录准确时刻**；登录准确时刻未知。
- 实时检测在 300s 时超时；关窗后本地 cookie 名称可读。**原因待查**，不把 Windows/SQLite/WAL/flush 等当作已查明结论。

## 3. doctor 检查（两次真实运行，分开列原件）

### 3.1 主证据：02:13:53Z

```
cmd=C:\Users\19183\.dsh\tools\x-collect\venv\Scripts\python.exe -X utf8 C:\Users\19183\.dsh\tools\xhs-collect\xhs_collect.py doctor
cwd=C:\Users\19183\.dsh\tools\xhs-collect
start_utc=2026-10-26T02:13:53+00:00
exit=0
state=ready
cookie db_exists=True
cookie web_session=True
cookie a1=True
cookie webId=True
cookie customerClientId=False
```

原件：`tools/selection/logs/xhs_doctor_20261026_run.log`（UTF-8，含 cmd/cwd/start_utc/exit/stdout/stderr）。

### 3.2 复查：02:18:49Z

```
cmd=C:\Users\19183\.dsh\tools\x-collect\venv\Scripts\python.exe -X utf8 C:\Users\19183\.dsh\tools\xhs-collect\xhs_collect.py doctor
cwd=C:\Users\19183\.dsh\tools\xhs-collect
start_utc=2026-10-26T02:18:49+00:00
exit=0
state=ready
cookie db_exists=True
cookie web_session=True
cookie a1=True
cookie webId=True
cookie customerClientId=False
```

原件：`tools/selection/logs/xhs_doctor_20261026_recheck.log`（UTF-8，含 cmd/cwd/start_utc/exit/stdout/stderr）。

- 只列有独立原件（start_utc/exit/stdout）的两次检查；无原件的检查不写入证据。
- **local 与 online 区分**：两次 doctor 只证明本地 profile 中 cookie 名称存在且 state=ready；**在线会话是否有效未独立验证**（未再开浏览器、未访问个人页）。不能把本地 cookie 当作在线认证成功或具体登录时刻的证明。

## 4. 台账更新（两处，基于 02:13:53Z + 02:18:49Z 真实日志）

- `docs/validation/v9/xhs-readiness/LEDGER.md`：xiaohongshu → ready（本地 profile）；doctor 两次均 exit0/ready；Cookies mtime 02:08:39Z 仅观察值；登录准确时刻未知；实时检测超时、关窗后本地 cookie 可读，原因待查；在线有效性未知；handle unknown（未解析页面，不推断）。
- `docs/validation/v9/account-safety/ACCOUNT-SAFETY.md`：同上。
- login exit 统一写 **not captured**；未写猜测 handle、未导出 cookie 值。

## 5. 限制

- login exit code 未捕获；只有 stdout `LOGIN_TIMEOUT` 与两次 doctor exit0 的真实原件。
- login 实时检测超时；关窗后本地 cookie 可读；具体原因未查，不能声称已查明。
- doctor 只证明本地 profile cookie 名称；在线认证有效性与登录准确时刻均未知。
- 未采集任何帖子；登录检测可靠性修复留后续最小任务。
