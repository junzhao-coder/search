# 阶段一（第 3 轮返工）：只认登出控件 + 多 tab 风险不绕过 + 真跑 JS

> 任务 `task-ef7a52fc80f7a6e5d1ea032ef0b0d763`（rev8 返工，计划 v10，V10-6）。
> **纯离线**：未启动浏览器、未访问网络、未发搜索、未读 cookie/token 值、未动 profile。
> 执行日期：**2026-10-29**（UTC 13:34–13:36）。

## 1. 判定器：只有「登出控件」能判 ok

| 项 | 本轮 |
| --- | --- |
| `STRONG_SIGNALS` | **`("hasLogout",)`** —— 原先的 `hasSettings` 已移除 |
| `hasSettings`（`/setting`、`/account/`） | 降为**诊断信号**，**永不单独放行**；公开页/登录引导页常见此类链接，故一律 `unknown` |
| 仍可判 `ok` 的组合 | 业务域门禁通过 **且** `hasLogout=true`（明确登出控件） |
| 业务域门禁 | host 必须 `weibo.com` / `*.weibo.com`；排除 `passport.`/`login.`/`signin.`；path 排除 `/signin|/login|/sso` |
| 选择器 | 全部标 **assumed**（真实登录页从未被观察），不宣称绝对有效 |
| 其他弱信号 | 公共头像、任意 `/u/` 链接、单独「消息」、空文本 → `unknown` |

## 2. 多 tab：风险优先，禁止绕过

`browser._poll_login_state()` 现在返回 `(url, signed, text, risk_reason, risk_url)`，且：

- **逐个可读候选 tab 各自计算风险文本**（不再只保留"第一个非空正文"）。
- **风险优先**：`wait_for_login(..., risk_wins=True)`（weibo 传）时，任一 tab 命中墙词即结束并 **`budget.lock()`**，即使另一 tab 看起来已登录。
- **证据同 tab**：返回的 `risk_url` 与该 tab 的文本同源；结果里新增 `risk_url` 字段（脱敏）。
- **知乎不变**：zhihu 不传 `risk_wins`（默认 False），保持"已登录优先于验证码文案"，96 项知乎测试全绿。
- **死 tab**：所有候选都抛异常时仍重抛 → `browser_error → unknown`（不吞成 timeout）。

## 3. 测试（真跑 JS + 安全边界）

### 3.1 真实执行 `SIGNED_IN_JS`（Node v24 + 最小 DOM stub）

`SignedInJsTests` **13 条**，其中新增/改写：

| 用例 | 期望 |
| --- | --- |
| 公开页仅 `/setting` 链接 | **`unknown`**（原为 ok，已改） |
| 公开页仅 `/account/` 链接 | **`unknown`** |
| `/setting` + `/account/` 同时存在 | **`unknown`** |
| 明确登出控件（`hasLogout`） | **`ok`** |
| 公开 feed（多头像 + 多 `/u/` + 「消息」） | `unknown` |
| 登录表单含弱信号甚至 logout（passport） | `unknown` |
| 非微博 tab 有控件 | `unknown` |
| `weibo.com/signin` + logout | `unknown` |
| 空文本 + 仅公共 `/u/` | `unknown` |
| 单独「消息」 | `unknown` |
| JS 只输出白名单键 | 键集合精确相等 |
| **`node` 可用性守卫** | 断言 `NODE` 存在 —— **JS 测试不允许被静默 skip** |

### 3.2 轮询控制流（明确标注：**不是** DOM 测试）

`LoginPollingTests` **8 条**，新增三条安全边界：

| 用例 | 期望 |
| --- | --- |
| **主 tab 普通正文 + 后续 tab 验证墙** | `risk` + 锁；`risk_url` = 墙 tab 的 URL |
| **墙在第一个 tab、登录态在第二个** | `risk`（墙胜出），`risk_url` = 墙 tab |
| **同一 tab 同时有登录态与墙词** | `risk`，`signed_in=false` |
| 账号控件 tab | `ok` |
| 弱信号 tab | 非 ok |
| 登录落后续 tab | `ok`，`final_url` 为后 tab |
| url 与文本同 tab | `final_url` 必须是持控件 tab 的 |
| 死 tab | `unknown`（非 timeout） |

### 3.3 入口

`SessionCheckEntryTests` **2 条**：`--check-session` 首个导航必须是 `https://weibo.com/`；默认 `login` 仍导航 passport。**本轮未执行该命令。**

## 4. 执行清单（UTF-8 日志 + 机器可读 manifest）

运行器：`docs/validation/v10/weibo-verify/run_tests.py`（用 Python 子进程捕获 UTF-8，避免 PowerShell `*>` 产生 UTF-16 二进制日志）。

```json
{"total_tests_across_modules": 186, "total_skipped": 0,
 "node_js_class_tests": 13, "all_green": true}
  test_access_weibo    exit=0 ran=70 skipped=0 failures=0 errors=0
  test_access_zhihu    exit=0 ran=96 skipped=0 failures=0 errors=0
  test_access_budget   exit=0 ran=20 skipped=0 failures=0 errors=0
  signed_in_js         exit=0 ran=13 skipped=0 failures=0 errors=0
```

- 完整 argv / cwd / **精确 UTC** / exit / skip：见 `RUN_MANIFEST.json`（每模块的 `started_utc`/`finished_utc` 精确到秒）。
- 原始日志（**UTF-8、无 BOM、非二进制**）：
  - `test_access_weibo_stderr.log`（10,681 B，尾部 `OK`）
  - `test_access_weibo_stdout.log`（0 B）
  - 同理 `test_access_zhihu_*`、`test_access_budget_*`、`signed_in_js_*`
- 期间修掉 3 处失败：
  1. 风险与登录同时命中时被 `_poll_login_state` 提前返回成 risk，导致知乎"已登录优先"回归 → 改为**同时返回两类事实**，由 `wait_for_login` 按 `risk_wins` 决定；
  2. `ReuseTests` 仍断言 `STRONG_SIGNALS` 含 `hasSettings` → 更新为 `("hasLogout",)`；
  3. `test_render_wait_keeps_the_one_deadline` 时序抖动（第二次 fetch 可能读到含链接的 HTML → exit 0）→ 给该断言用**独立空壳 tab**，使路径确定；**未放宽断言**。

## 5. 未证明事项（验收口径）

- **真实微博上尚未验证**：Node 测试只证明"给定 DOM 信号时谓词判定正确"；`a[href*="/logout"]` 等选择器仍 **assumed**，真实页面可能用别的控件 → 那会得到 `unknown`（宁可不判 ok）。
- **会话当前状态未知**：现有 profile 未动，cookie 名称存在不等于会话有效；未执行 `--check-session`。
- 登录后的微博搜索**尚未尝试**，既不能说可读，也不能说路线已死。
- 多 tab 风险扫描目前只有控制流覆盖，真实 SSO 换 tab 场景未复验。
