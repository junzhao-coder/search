# V10-3 知乎登录窗口：执行结果（block：当前解释器缺 nodriver）

> 任务 `task-4f73e623e9dbe1078e5e8fe61175f172`（rev2，计划 v10，V10-3）。
> 执行时间 2026-10-27 16:29:02–16:29:33 UTC+8（08:29:02–08:29:33Z）。
> **未代填凭据、未读取/输出 cookie 值、未安装依赖、未改代码、未重试、未弹窗。**

## 1. doctor（前置，只读、不触网）

```json
{"command":"doctor","cookie_db_exists":false,"cookie_names":{},"exit":0,"network":"none",
 "note":"cookie names only; presence is not proof of a valid session","ok":true,
 "online":"unverified","profile":"C:\\Users\\19183\\.dsh\\tools\\zhihu-collect\\profile",
 "profile_exists":false}
```
- profile **不存在**（与策划者 glob 结论一致，属预期，非错误）。
- cookie 名称布尔：`{}`（无 z_c0/d_c0/_xsrf/__zse_ck/q_c1/SESSIONID）。
- `online=unverified`；exit 0。

## 2. login（执行一次，未开窗）

| 项 | 值 |
| --- | --- |
| argv | `C:\Users\19183\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe -m tools.selection.access.zhihu --state-dir docs\validation\v10\zhihu\runtime_login --profile C:\Users\19183\.dsh\tools\zhihu-collect\profile login --timeout 300` |
| cwd | `D:\桌面\two` |
| started_utc / finished_utc | **2026-10-27T08:29:11Z** / **08:29:21Z** |
| **exit** | **7** |
| status | **`unavailable`** |
| polls | 0（未进入轮询） |
| final_url | 无（未打开浏览器） |
| stderr | 空 |

stdout 原文（`docs/validation/v10/zhihu/login_run.out.txt`）：
```json
{"command":"login","detail":{"chrome":"C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
 "nodriver":false,"nodriver_version":null,"usable":false},
 "error":"browser_unavailable","exit":7,
 "profile":"C:\\Users\\19183\\.dsh\\tools\\zhihu-collect\\profile","status":"unavailable"}
```

- **无 Chrome 进程、无窗口**：`Get-Process chrome` 无带标题窗口；`Win32_Process` 中无 `zhihu-collect` 命令行进程。
- 未发生任何登录交互，未代填、未读 cookie。

## 3. 阻塞原因（只读诊断）

| 检查 | 结果 |
| --- | --- |
| `importlib.util.find_spec('nodriver')` | **False** |
| 解释器 | `C:\Users\19183\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe`，Python 3.12.14 |
| Chrome | `C:\Program Files\Google\Chrome\Application\chrome.exe` **存在** |
| `nodriver` 位置 | 仅 `C:\Users\19183\.dsh\tools\x-collect\venv\Lib\site-packages\nodriver` 存在；系统 Python312 与 xhs-collect venv 均无 |

- 结论：登录代码运行到“浏览器可用性检查”即返回 `browser_unavailable`；**当前解释器缺 nodriver**，按硬约束不自行安装/不换解释器。

## 4. doctor（登录失败后，只读）

```json
{"command":"doctor","cookie_db_exists":false,"cookie_names":{},"exit":0,"network":"none",
 "ok":true,"online":"unverified",
 "profile":"C:\\Users\\19183\\.dsh\\tools\\zhihu-collect\\profile","profile_exists":false}
```
- 与前置一致：profile 仍不存在、cookie 名称布尔仍为空、`online=unverified`；exit 0。

## 5. 声明

- **未代填凭据、未读取或输出任何 cookie/token 值**；无敏感画面截图。
- 未安装依赖、未改代码/测试/期望值、未重试、未自动重开窗口。
- 未访问知乎以外域名；未写业务库/CSV/CONTRACT；profile 未入仓库（尚未创建）。

## 6. 需要用户/策划者决定

- A) 用 `C:\Users\19183\.dsh\tools\x-collect\venv\Scripts\python.exe` 跑 login（该 venv 有 nodriver，但可能缺本项目其它依赖）；
- B) 授权在 dsh-primary-runtime 安装 nodriver（需联网/装依赖）；
- C) 暂缓知乎登录。

已按“失败即 block”停住；未重试。
