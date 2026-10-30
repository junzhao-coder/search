# V9-8e 实现报告：login CDP 轮询 + 关窗复查 + verify 只读在线校验

> 任务 `task-fec8a36a7083db83b01dc83b80ca8f72`（rev2，计划 v9）。2026-10-26 10:24–10:31 UTC+8。
> **未重跑 login、未清 profile、未采集帖子、未装依赖、未读/写 cookie 值**；verify 仅 headless 真跑一次。

## 1. login-detect（`C:\Users\19183\.dsh\tools\xhs-collect\xhs_collect.py`）

| 行号 | 改动 |
| --- | --- |
| `:86-92` | `_browser_has_web_session(browser)`：`await browser.cookies.get_all()`，只取 `cookie.name == "web_session"`；不读值、不写日志 |
| `:145-171` | `login_async`：CDP 每 `poll=2s` 轮询；关窗 `graceful_close` 后 `time.sleep(post_close_wait)`，再 `_has_web_session(PROFILE)` 文件级复查；**任一命中→`LOGIN_OK` exit0；两处都无→`LOGIN_TIMEOUT` exit3** |
| `:73-79` | 原 `graceful_close` 保留，确保 `browser.stop()` 被调用 |
| `:46-70` | `check_profile` 保留只读 cookie 名称布尔（`web_session/a1/webId/customerClientId`） |

- 兼容 stub：`login_async(timeout, poll, post_close_wait)` 可注入短超时/零关窗等待。
- 真实 login 未复跑（需要用户扫码）；CDP 路径仅由 stub 验证。

## 2. verify（只读在线校验）

| 行号 | 内容 |
| --- | --- |
| `:120-142` | `classify_verify(visible_text, error=None, cookie_present=None, dom_html=None)`：risk→5，login_required→4，valid→0，unknown→6 |
| `:95-117` | `_dom_kind`：仅按 class/id/data-testid/src 属性判 captcha/login-mask/login-wall，不把脚本当 DOM |
| `:174-195` | `verify_async`：`headless=True`、单页 `HOME`、总超时≤30s；`document.body.innerText` 做文本判定，`get_content()` 只做 DOM 属性判定；**不截图、不落正文、不写 signals/业务库、不重试** |
| `:198-222` | `main` 新增 `verify --timeout`；异常/超时统一 `online=unknown` exit6 |

**真实运行（最多一次）**：

```
cmd=C:\Users\19183\.dsh\tools\x-collect\venv\Scripts\python.exe -X utf8 C:\Users\19183\.dsh\tools\xhs-collect\xhs_collect.py verify --timeout 30
cwd=C:\Users\19183\.dsh\tools\xhs-collect
start_utc=2026-10-26T02:27:26+00:00
exit=4
online=login_required
```

- 原件：`tools/selection/logs/xhs_verify_20261026.log`（UTF-8，含 argv/cwd/start/exit/stdout/stderr）。
- stderr 有 nodriver/asyncio 的 `ResourceWarning: unclosed transport`（解释器退出时收尾警告）；stdout 判定与 exit 4 正常，未重试。
- 该结果是**单次观察**：本地 profile cookie 名称在（doctor ready），但本次在线页面判定为 `login_required`；不把它推广为永久在线状态，也不声称登录时刻。
- 未读取/输出完整 cookie 对象、页面正文；未写业务库。

## 3. tests（9 项，三情形 + verify 判定/exit）

`tests/test_xhs_collect.py`：

| 测试名 | 断言 |
| --- | --- |
| `test_login_browser_cookie_visible_success` | CDP 看到 `web_session` → exit0，`browser.stop` 调用，`get_calls=1`，不触发文件复查 |
| `test_login_file_recheck_after_close_success` | CDP 不可见、关窗后文件可读 → exit0（复现旧假阴性，必须成功），文件复查恰好 1 次 |
| `test_login_both_absent_timeout_no_retry` | 两处都无 → exit3，`browser.stop` 调用，`get_calls=1`（不重试/不二次导航） |
| `test_verify_valid` | 正常页面、cookie=True → `valid`/0 |
| `test_verify_login_required` | “请登录” → `login_required`/4 |
| `test_verify_risk` | “请完成安全验证” → `risk`/5 |
| `test_verify_unknown_on_error` | error=timeout → `unknown`/6 |
| `test_check_profile_states` / `test_has_web_session_gate` | 保留 doctor/cookie 名称布尔三态与 gate |

**三套真实结果**：

| suite | 结果 | 日志 |
| --- | --- | --- |
| selection（基线 73 + 6 新） | **79 tests OK** | `tools/selection/logs/tests_selection_v98e.log` exit0 |
| workbench | **218 tests OK** | `tools/selection/logs/workbench_v98e.log` exit0 |
| 项目全套（基线 407 + 6 新） | **413 tests OK** | `tools/selection/logs/project_v98e.log` exit0 |

cwd `D:\桌面\two`；UTC 02:27–02:31（本地 10:27–10:31）。

## 4. ledger / guide

- `docs/validation/v9/xhs-readiness/LEDGER.md:9` 与 `docs/validation/v9/account-safety/ACCOUNT-SAFETY.md:68`：
  - 补“检测可靠性已修（CDP 轮询 + 关窗复查）”；
  - doctor 02:13:53Z/02:18:49Z 均 exit0 ready；
  - **verify 2026-10-26T02:27:26Z exit4 online=login_required（单次观察）**；
  - 本地 profile cookie 名称在（ready），但在线未通过，需用户本人重登；不删除本地 cookie。
- `docs/validation/v9/xhs-readiness/LOGIN_GUIDE.md`：新增“需要重登前先跑 verify，避免无谓扫码”，列 valid/login_required/risk/unknown 与 0/4/5/6 语义。

## 5. 限制

- **真实 login 成功路径未复跑**（需用户扫码，本批禁止）；CDP 轮询/关窗复查仅由 3 个 stub 覆盖。
- verify 只跑了一次，`login_required` 是**单次观察**；在线状态可能变化，不能当永久结论。
- verify stderr 有 `ResourceWarning: unclosed transport` 收尾警告；不影响 exit/stdout，但属未清理干净，未重试。
- 未解析 handle；未采集帖子；未验证真实验证码/风控页；未改判重/品类语义。
- 外部脚本 `xhs_collect.py` 不在仓库 scope 列表内，但按任务验收要求修改；仓库内仅新增测试与文档。
