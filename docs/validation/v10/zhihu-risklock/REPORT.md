# V10-3 / risklock：验证码墙不锁批次 + readyState 恒空 —— 修复留证

- 范围：`tools/selection/access/`、`tests/test_access_zhihu.py`、本目录。
- **本轮没有联网、没有启动浏览器、没有登录、没有装依赖、没有发真实请求、没有做全套回归、没有写业务库/CSV/CONTRACT。**
- **不宣称已解决知乎可读性**：可读性由服务端风控决定，与本修复无关；本修复只保证“风控出现时不再静默放行”。

## 1. 缺口来自实测（task-19b549b9）

可见窗口下那次真实 `search` 返回：

```
exit=7  stop=browser:risk:text:验证码  phase=read
html_bytes=126059  anchors_total=47（全未识别）  wall="验证码"  textLen=590
batch.locked=false  lock_reason=null      ← 关键缺口
```

即：**风控墙被看见了、也非零退出了，但没有持久锁**。计划 P5 要求“验证码/403/429/登录墙/平台风险即停、非零退出、不自动重试”，此前只做到后两项。这套代码后面要给微博/抖音/贴吧复用，带着“风控静默放行”的缺口跑新平台风险很大。

## 2. 根因与修复（复用既有 lock，不新建风控框架）

| # | 根因 | 证据行号 | 修复 |
| --- | --- | --- | --- |
| 1 | transport 已把墙写进返回 dict 的 `error` | `transport.py:238` `"error": f"browser:risk:text:{probe['wall']}"` | 保持原样（诊断字段不变） |
| 2 | `_risk_or_error()` 只对 `offsite_redirect:` 给锁定语义，其它 error 一律 `(text, False)` | `zhihu.py:613` 起的分支 | 新增 `RISK_ERROR_PREFIX = "browser:risk:"`（`zhihu.py:56`），在 `zhihu.py:623` 判定为**锁**：`return text, True`，与 403/429 **同等**待遇 |
| 3 | 探针读 `document.documentElement.readyState`（实测恒为空字符串） | `transport.py:295` | 改为 `const state = document.readyState \|\| '';` |

- 锁定仍走既有 `budget.lock(reason, source=...)`：`source` 为 `search`/`detail`/`comments`，`lock_reason` 完整记下 `browser:risk:text:验证码`。
- 锁是**持久化**的（同 state dir 重开也会 `batch_locked`），因此同批后续命令**在发请求前**就被拒。
- `browser:TimeoutError`、`network_disabled_offline_batch` 等仍然**不锁**（既有行为不变）；`offsite_redirect:` 锁定不变。

## 3. 离线测试（`RiskLockTests`，7 例）

| 用例 | 断言 |
| --- | --- |
| `test_captcha_wall_locks_the_batch` | `exit=EXIT_RISK`、`snapshot.locked=True`、`lock_source="search"`、`lock_reason` 含“验证码” |
| `test_other_wall_markers_lock_too` | 安全验证/访问异常/操作频繁/请求过于频繁 四个标记各自锁（每个标记独立 state dir） |
| `test_lock_survives_restart_and_blocks_the_next_command` | 关闭后重开同 state dir → `BudgetError(code="batch_locked")` |
| `test_locked_batch_sends_no_second_request` | 同批第二次 `run_search` → `EXIT_BUDGET` / `budget:batch_locked`，**第二个 transport 的 urls 为空**、calls 仍为 1 |
| `test_detail_and_comments_paths_lock_as_well` | `run_detail` 走风险 → 锁、`lock_source="detail"` |
| `test_non_risk_errors_still_do_not_lock` | `browser:TimeoutError` → `EXIT_TRANSPORT` 且**未锁**（不回归） |
| `test_offsite_redirect_lock_unchanged` + `test_probe_reads_document_ready_state` | offsite 仍锁、普通错误仍不锁；探针源码含 `document.readyState`、**不含** `documentElement.readyState` |

**运行记录**（`execution_manifest.json`，两个套件都记录真实 argv/cwd/UTC/exit，network=none、browser=none）：

| 套件 | argv | cwd | start → end (UTC) | rc | 结果 |
| --- | --- | --- | --- | --- | --- |
| `tests.test_access_zhihu` | `python -X utf8 -m unittest tests.test_access_zhihu -v` | `D:\桌面\two` | 2026-10-27T14:16:57Z → 14:17:06Z | 0 | Ran 96 — OK |
| `tests.test_access_budget` | `python -X utf8 -m unittest tests.test_access_budget -v` | `D:\桌面\two` | 2026-10-27T14:17:06Z → 14:17:07Z | 0 | Ran 20 — OK |

（合计 116 例；原 88 + 20 例零回归，新增 8 例全绿。）

## 4. 本次修复**没有**做的事

- 没有改 `budget.py`（锁语义、阈值、配额一律不动）。
- 没有新增风控框架/中间件；只是在既有 `_risk_or_error` 里多认一个前缀。
- 没有改 `export` 字段、没有加 triage/categories。
- 没有动 `docs/validation/v10/zhihu`、`zhihu-readiness`、`zhihu-visible-prep`。
- **没有**发真实请求去验证“修完之后真实验证码页会不会锁”——那是下一轮真实调用才能确认的。

## 5. 下一轮真实验证时怎么看（本轮不执行）

- 若再遇到验证码墙，正确输出应是：`exit=7`、`stop=browser:risk:text:验证码`、**`batch.locked=true`**、`lock_reason=browser:risk:text:验证码`、`lock_source=search`。
- 紧接着的同批第二条命令应返回 `exit=6` / `stop=budget:batch_locked`，且**不再有新的网络请求**（`calls` 不增加）。
- `readyState` 现在应出现真实值（`complete` / `interactive` / `loading`），不再是空字符串；若仍为空，说明 `document.readyState` 在该求值上下文里不可读，属新问题。

## 6. 仍未验证

1. 真实验证码页在修复后是否**确实**落锁——只有一条离线证据链，真实页面未复测（本轮禁止真实调用）。
2. `document.readyState` 修复后真实返回值未观测（此前的“恒空”是实测现象，修复效果待确认）。
3. 4 次真实调用中另一次“0 记录”是否也与风控有关，未定位。
4. 按要求只跑 `tests.test_access_zhihu` + `tests.test_access_budget`，**未做全套回归**。
