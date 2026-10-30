# V9-8d 实现报告（运行前）：xhs-collect login/doctor 脚本 + 台账 + 用户指引

> 本文件是 login 运行前的实施报告；真实运行与 doctor 证据见 `REPORT_V9_8D_RUN.md`。文中“login 未真实运行”描述的是撰写时状态。

> 任务 `task-5e1b5d0def89a1ea4b5672f0584f02e3`（rev2，计划 v9）；范围 `tools/selection`、`docs/validation/v9/xhs-readiness`、`docs/validation/v9/account-safety`。
> 2026-10-25 22:29–22:34 UTC+8。**实现阶段未运行 login、未弹窗**；未 pip install、未改 x-collect、未读 cookie 值、未写业务库。

## 1. script

- 目录：`C:\Users\19183\.dsh\tools\xhs-collect\{xhs_collect.py, profile\}`（profile 空目录已建）。
- 行号：`check_profile :32-58`（cookie 名称布尔，web_session/a1/webId/customerClientId，`host_key LIKE '%xiaohongshu.com%'`）；`graceful_close :61-66`（CDP 关闭 flush）；`_has_web_session :69-71`；`login_async :74-99`（`headless=False`、`user_data_dir=PROFILE`、导航 xiaohongshu.com、**每 2s 轮询 cookie 名称 `web_session`**，300s 超时→`LOGIN_TIMEOUT` exit 3 不重试，成功→关窗 flush 8s→`LOGIN_OK` exit 0）；`main :102-118`（doctor 输出 state/cookie 布尔，ready exit 0）。
- 用 x-collect venv 解释器运行（复用 nodriver，无 pip install）：`C:\Users\19183\.dsh\tools\x-collect\venv\Scripts\python.exe xhs_collect.py ...`。
- 实测：doctor 空库 → `state=waiting_user`、exit **2**（日志见提交）；脚本 import 无 BOM/转义问题（已修两轮）。
- 脚本绝不读/填账号密码验证码、不点击、不截图。

## 2. usage（给策划者/执行者）

```powershell
# login（只在策划者告知用户“现在弹窗”后执行）
C:\Users\19183\.dsh\tools\x-collect\venv\Scripts\python.exe C:\Users\19183\.dsh\tools\xhs-collect\xhs_collect.py login
# doctor（登录前后皆可）
C:\Users\19183\.dsh\tools\xhs-collect\xhs_collect.py doctor   # 用 x-collect venv python 执行
```

成功判定：轮询 cookie 名称 `web_session`（不解析页面内容）；300s 超时退出非零不重试；doctor ready 即停，**首采另批**。

## 3. guide

`docs/validation/v9/xhs-readiness/LOGIN_GUIDE.md`：给用户本人的照做段落（弹窗→本人扫码→脚本自动关窗→`LOGIN_OK`/`LOGIN_TIMEOUT`），安全边界（不代填/不读值/不重复弹窗）。

## 4. ledger（两处 diff）

- `xhs-readiness/LEDGER.md:9`：xiaohongshu 行 → 脚本就绪、**待策划者转告用户后弹窗扫码**；doctor 空库 waiting_user（14:31Z）；真实登录未发生。
- `account-safety/ACCOUNT-SAFETY.md:68`：新增 xiaohongshu 行（handle=待登录/unknown；状态=脚本就绪待扫码；成功判定=web_session 名称出现）。
- 未写 ready——登录还没发生；登录成功后由后续 doctor 结果再改。

## 5. tests（真实 exit）

- 新增 `tests/test_xhs_collect.py` 3 项：`test_check_profile_states`（不存在/未登录/ready）、`test_has_web_session_gate`、`test_login_timeout_path`（stub nodriver：`headless=False`、`user_data_dir=PROFILE`、超时 exit 3、browser.stop 被调用）。
- selection `tools/selection/logs/tests_selection_v98d.log` exit 0 **73 tests OK**（基线 70 + 3）；workbench **218 OK**；项目 **407 OK**（基线 404 + 3）。cwd `D:\桌面\two`，UTC 22:32–22:34。

## 6. limits

- login 未真实运行（按硬约束，等策划者转告用户确认）；`LOGIN_OK`/关窗 flush 路径只在 stub 验证。
- doctor“ready”只对构造 sqlite 验证；真实 profile 待登录后 doctor。
- 未验证 Chrome 窗口实际弹出/扫码流程；未验证 300s 真实超时。
