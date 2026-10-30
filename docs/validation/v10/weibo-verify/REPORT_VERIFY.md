# V10-6 验证报告（更正版）：判定器已收紧并真跑 JS；登录自判仍**未完成**

> 任务 `task-ef7a52fc80f7a6e5d1ea032ef0b0d763`（rev5 返工，计划 v10，V10-6）。
> 本文件**更正**上一版的三处过度结论（见 §5），并补上精确清单与原始输出引用。
> 本轮（返工）**只做离线工作**：未开窗、未联网、未搜索、未装依赖、未动 profile/state 账本。

---

## 1. 返工做了什么（离线）

| 项 | 内容 |
| --- | --- |
| 判定器收紧 | `SIGNED_IN_JS` 只采集信号（host/path/text/hasLogout/hasSettings/hasCompose/avatarCount/userLinkCount），判定交给纯谓词 `classify_signed_in`；**只有 `hasLogout`（明确登出控件）可判 `ok`**；`/setting`、`/account/` 降为诊断信号（公开页也有），与公共头像、任意 `/u/` 链接、单独「消息」、空文本一律 `unknown`；host 必须 `weibo.com`/`*.weibo.com` 且排除 `passport./login./signin.`，path 排除 `/signin|/login|/sso` |
| 入口选项 | 新增 `login --check-session`：**只导航** `https://weibo.com/`，不 fallback、不重开；保留原 `login`（passport 人工登录）；**未**做任意 URL 框架 |
| 同 tab 证据 | `_poll_login_state(..., verdict=None, wall_of=...)`：**逐 tab 各自算风险**，返回 `(url, signed, text, risk_reason, risk_url)` 且同源；**风险优先**（weibo `risk_wins=True`，任一 tab 命中墙词即锁，不许用另一 tab 的登录态绕过）；知乎不传该标志，保持"已登录优先于验证码文案" |
| 测试 | Node v24 + 最小 DOM stub **真实执行同一份 `SIGNED_IN_JS`**（**13 条**，含"仅 `/setting`/`/account/` → unknown"、node 可用性守卫）；轮询控制流 **8 条**（明确标注**不是** DOM 测试，含三条风险优先边界）；`--check-session` 导航地址 2 条 |
| 结果 | 三模块 **186 tests / 0 skipped / exit 0**；Node 类 **13 / 0 skipped**（`RUN_MANIFEST.json`） |

细节见 `PHASE1_DETECTOR.md`。

---

## 2. 精确执行清单（真实值，无占位）

### 2.1 本轮离线测试（UTF-8 日志 + 机器可读清单）

运行器：`docs/validation/v10/weibo-verify/run_tests.py`（Python 子进程捕获 UTF-8，避免 PowerShell `*>` 写出 UTF-16 二进制）。

```json
{"total_tests_across_modules": 186, "total_skipped": 0,
 "node_js_class_tests": 13, "all_green": true}
  test_access_weibo    exit=0 ran=70 skipped=0 failures=0 errors=0
  test_access_zhihu    exit=0 ran=96 skipped=0 failures=0 errors=0
  test_access_budget   exit=0 ran=20 skipped=0 failures=0 errors=0
  signed_in_js         exit=0 ran=13 skipped=0 failures=0 errors=0
```

- 完整 argv / cwd / **精确 UTC（每模块 started/finished）** / exit / skip：`RUN_MANIFEST.json`
- 原始日志（UTF-8、无 BOM）：`test_access_weibo_stderr.log`（10,681 B，尾部 `OK`）、`test_access_weibo_stdout.log`（0 B）等
- **Node 测试未被跳过**：`node_js_class_tests=13`、`skipped=0`，并有 `test_node_is_available_so_js_tests_never_skip_silently` 守卫

### 2.2 上一轮（rev2）真机登录窗——原始记录，未改动

```
argv  = C:\Users\19183\.dsh\tools\x-collect\venv\Scripts\python.exe -X utf8
        -m tools.selection.access.weibo
        --state-dir D:\桌面\two\docs\validation\v10\weibo-verify\state-login
        --profile D:\桌面\two\docs\validation\v10\weibo-login\profile
        login --timeout 300
cwd   = D:\桌面\two ;  PYTHONPATH = D:\桌面\two
started_utc = 2026-10-27T15:49:03Z ; finished_utc = 2026-10-27T15:54:05Z
exit  = 11
stdout 原文（login.out.txt）：
  {"command":"login","elapsed_s":301.737,"exit":11,
   "final_url":"https://passport.weibo.com/sso/signin","polls":100,
   "risk_reason":null,"signed_in":false,"status":"timeout","stop_reason":"timeout"}
stderr 原文（login.err.txt）：仅 asyncio 收尾告警（Event loop is closed /
  I/O operation on closed pipe），无产品异常。
窗口证据（window_evidence.txt）：
  {"python_pid":104324,"chrome_pid":116560,"title":"新标签页 - Google Chrome",
   "handle":2296312,"visible":true,"responding":true,"rect":"10,10,1060,1010"}
```

搜索侧：`state-search1` **未创建**（已核验），即**那次搜索从未发起**。

---

## 3. 观测事实（只写看到什么）

| 事实 | 证据 |
| --- | --- |
| 登录窗打开、可见 | 上面的 `window_evidence.txt`（Python 104324 / Chrome 116560，`IsWindowVisible=true`） |
| 40 秒后窗口标题为「登录 - 微博」 | 现场 `Get-Process` 采样（标题字符串） |
| 最终 URL 停在 `https://passport.weibo.com/sso/signin` | `login.out.txt` 的 `final_url` |
| 判定结果 `signed_in=false` / `status=timeout` | 同上 |
| 会话 cookie 名称存在 | doctor：`SUB/SUBP/SSOLoginState/XSRF-TOKEN=true`，`cookie_count=9`，`online=unverified` |
| 搜索未发起 | `state-search1` 不存在 |

---

## 4. 结论（收紧后的口径）

1. **登录自判未完成**：那一次窗口停在 passport 登录页，页面证据始终不足，`status=timeout`。
2. **"入口 URL 是原因"只是候选解释**，不是唯一根因。可能的候选至少有三类：
   - a) 入口停在 passport（观测到的事实）；
   - b) 该 profile 的会话**可能已过期**（未验证；cookie 名称存在不等于会话有效）；
   - c) 旧判定器把弱信号当充分条件 / 读错 tab（本轮已修，但**未**在真机上复验）。
3. **单元测试通过不证明真实会话有效**：Node 测试只证明"给定 DOM 信号时谓词判定正确"，不证明真实微博页面上的选择器成立（选择器仍 **assumed**）。
4. **登录后的微博搜索尚未尝试**：因此既不能说"登录后不可读"，更不能说"微博搜索路线已死"。上一版这两句已删除。
5. 现有 profile 保留未动；**会话是否有效未知**，不承诺"无需再扫码"。

---

## 5. 对上一版报告的三处更正

| # | 上一版说法 | 更正为 | 依据 |
| --- | --- | --- | --- |
| 1 | "根因是登录入口 URL（passport 不跳转）" | "**观测**停在 passport；入口是**候选原因之一**，另有会话过期、旧判定器缺陷两类候选" | 只有一次观测，且会话有效性从未被独立证实 |
| 2 | "判定器已修好并证明有效" | "判定器**已收紧**，其**谓词**在 Node+DOM stub 下被真跑验证；**真实页面有效性未证明**（选择器 assumed）" | 本轮才第一次真正执行 JS；真机未复验 |
| 3 | "cookie 已写入 → 登录成功" | "cookie **名称**存在；按验收第 4 条不得据此判 ok，会话有效性**未知**" | doctor 只输出布尔，`online=unverified` |
| 4 | "`hasSettings` 与 `hasLogout` 同为强信号" | "**只有 `hasLogout`** 可判 ok；`/setting`、`/account/` 在公开页也存在，单独出现一律 `unknown`" | 本轮返工要求；已加真实 JS 测试覆盖 |

---

## 6. 待复核命令（本轮**未执行**，交策划者独立验收后处理真机）

```bash
# 1) 只导航 weibo.com 的会话检查（不 fallback、不重开）
D:\桌面\two\.venv\Scripts\python.exe -X utf8 -m tools.selection.access.weibo \
  --state-dir D:\桌面\two\docs\validation\v10\weibo-verify\state-check1 \
  --profile D:\桌面\two\docs\validation\v10\weibo-login\profile \
  login --check-session --timeout 120

# 2) 仅当上一步 status=ok（页面强证据）后，才跑这一次搜索
D:\桌面\two\.venv\Scripts\python.exe -X utf8 -m tools.selection.access.weibo \
  --state-dir D:\桌面\two\docs\validation\v10\weibo-verify\state-search1 \
  --batch-id weibo-verify-1 --mode authenticated-browser \
  --profile D:\桌面\two\docs\validation\v10\weibo-login\profile \
  --diagnostics-dir D:\桌面\two\docs\validation\v10\weibo-verify\diag1 \
  search "学习计划模板" --limit 5 --visible --timeout 60
```

> 注意：第 2 条会消耗微博本批 1 次真实额度；若第 1 条非 ok，**不得**执行第 2 条。

---

## 7. 派发命令勘误（单列，防照抄）

| # | 问题 | 事实 | 影响 |
| --- | --- | --- | --- |
| 1 | 早前验收命令**缺 `--state-dir`** | CLI 把它设为必填；照抄报 `error: the following arguments are required: --state-dir`（`weibo-login/login.err.txt` 299 B 留证） | 该次**未开窗**、零副作用 |
| 2 | 早前验收命令给 `login` 加了 **`--visible`** | `weibo.py` 的 login 只定义 `--timeout` / `--headless`（后者 store_true，默认即可见）；`--visible` 仅存在于 search/detail/comments | 照抄会被 argparse 拒绝；已按"可加可不加"省略 |

> 两处均为**派发文本**问题，非执行问题。

---

## 8. 边界声明

- 本轮**未开窗、未联网、未搜索、未装依赖**；未修改 profile 与既有 state 账本。
- 未读/未输出 cookie 值（doctor 仅布尔与计数）；未写业务库/CSV/CONTRACT；profile 未入库。
- 未改预算语义、风险策略、探针、知乎行为（知乎 96 项通过）。
- 未自动重开、未重试。
