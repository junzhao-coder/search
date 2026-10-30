# 知乎最小接入 + 可跨重启预算 · 实施报告（计划 v10 / 小目标 #82，返工轮）

> 任务 `task-c43b2bf07f057475adaa207a4dede842`（rev 5，返工）。2026-10-27T05:0x UTC（本地 13:0x UTC+8）。
> **本批未访问 zhihu.com、未启动浏览器、未登录、未做新调研网络。**
> 离线检查**未执行**（§7，权限事实）。本文件把“代码已实现”和“真实未验证”严格分开。

## 1. 本轮按返工意见改了什么

| 项 | 上一版问题 | 本轮改法 | 落点 |
| --- | --- | --- | --- |
| **A** 绕锁 | 显式新 `batch_id` 会 INSERT 新行绕过锁；`--force-new-batch` 无凭据即可跳过锁 | 预算改为 **state dir 级单行**；`--force-new-batch`/`--new-batch` **全部删除**；显式 ID 只 `relabel`（写 ledger），计数/窗口/锁全不动 | `budget.py:264 open_budget`、`:239 lock` |
| **B** login 假成功 | 固定 sleep 后无条件 `ok=True/exit0`；登录导航不过预算；不检测风险 | 拆纯函数 `wait_for_login` + 注入 browser；`ok/timeout/poll_limit/unknown/risk` 五态，各自独立非零退出码；**poll 独立配额 10 次**，不占 3 次 active call；锁定时 login 同样拒绝 | `browser.py:74`、`budget.py:173 charge_poll`、`codes.py:13-15` |
| **C** 不复用账号态 | live 分支全是 `HttpTransport`（只有 UA/Accept），profile 完全不复用；`urlopen` 默认跟随重定向 | 显式两模式 `public-http` / `authenticated-browser`；后者用同一 profile 驱动 nodriver，**不读不导 cookie**；public 用 `_NoRedirect` **拒绝 3xx** 并返回非零；域外落地一律中止并锁 | `transport.py:29 _NoRedirect`、`:98 AuthenticatedBrowserTransport`、`:171 _same_site` |
| **D** 导出漏字段 | `dict(raw)` 复制全部键，只删 5 个键名 | `normalize_record` 改为**纯白名单**，从不复制输入；`field_evidence` 前缀白名单 + `evidence_rejected`；`source` 只允许已知后缀，否则 `redacted` | `records.py:125 clean_evidence`、`:145 clean_source`、`:153 normalize_record` |
| **E** 报告失真 | X 用旧 `off` 快照推断“不可用” | 改为“**未完成，原因是本批禁止新调研网络**”；并如实记 x-collect 确实存在 | `RESEARCH.md §1` |
| **F** 权限 | 上一轮尝试 shell | 本轮**零 shell 尝试**，只写代码 + 驱动脚本 | 本文件 §7 |

## 2. 交付物

| 类别 | 路径 | 规模 |
| --- | --- | --- |
| 预算（state-dir 单预算） | `tools/selection/access/budget.py` | 350 行 |
| 退出码（独立模块，避免循环 import） | `tools/selection/access/codes.py` | 15 行 |
| 记录/URL 白名单 | `tools/selection/access/records.py` | 207 行 |
| 知乎适配 + CLI | `tools/selection/access/zhihu.py` | 931 行 |
| 传输（offline / public-http / authenticated-browser） | `tools/selection/access/transport.py` | 191 行 |
| login 纯函数 + 浏览器接缝 | `tools/selection/access/browser.py` | 175 行 |
| 预算测试 | `tests/test_access_budget.py` | 21 例 |
| 知乎测试 | `tests/test_access_zhihu.py` | 约 40 例 |
| 调研 | `docs/validation/v10/zhihu/RESEARCH.md` | — |
| 受控 fixture | `docs/validation/v10/zhihu/fixtures/*`（8 个，含 `records_secrets.jsonl`） | — |
| 离线检查驱动 | `docs/validation/v10/zhihu/offline_checks.py` | 24 场景 |

## 3. 预算语义（A）

**一个 state dir == 一个预算**，这是唯一的计数边界。

- schema：单行 `budget(id=1, state_dir, batch_id, calls, records, polls, last_call_at, locked, lock_reason, lock_source)` + `ledger` + `batches`（仅记录见过的标签）。
- 额度：**3 active calls / 5 records / 间隔 ≥15s / 窗口 300s**；**poll 独立 10 次**（`budget.py:33-37`）。
- 显式 `--batch-id`：只改标签 + 写一条 `relabel` ledger，**calls/records/polls/窗口/锁全不动**（`budget.py:295-306`）。
- 锁：`lock(reason, source)` 写盘后，**任何新进程、任何标签、任何命令**（含 login）都在 `open_budget` 处直接 `batch_locked` 退出 6。**没有**任何 flag 能清除。
- 要新预算只能换 `--state-dir`，那是策划者显式给的新目录；代码里不存在“自己开新预算”的路径。
- 先扣后发：`charge` 在 `BEGIN IMMEDIATE` 内校验+自增+写 ledger，写失败抛 `budget_write_failed` 且调用方不发请求。
- 失败不返还：`transport.fetch` 之后无论成败都不回滚。
- login 用 `charge_poll`：**不占 active call**，也**不受 15s 间隔限制**（登录窗口有自己的 deadline），但仍受锁与 10 次配额约束。

## 4. login 五态（B）

| 状态 | 触发 | 退出码 |
| --- | --- | --- |
| `ok` | 页面出现明确本人登录态（`SIGNED_IN_JS` 命中：账号菜单/头像/导航含“消息/私信/我的主页/创作中心”） | **0** |
| `risk` | 页面出现风控/登录墙文案 | **5**，并 `lock(source="login")` |
| `timeout` | 跑满 `--timeout`（默认 300s）仍无登录态 | **11** |
| `poll_limit` | 10 次 poll 用完仍无登录态 | **12** |
| `unknown` | 窗口起来了但什么都读不到（如 tab 崩） | **13** |
| `locked` / `budget_error` | 预算已锁 / 写失败 | **6** |

**cookie 名永不参与判定**：`doctor` 的 `online` 恒为 `"unverified"`，`cookie_names` 只是布尔辅助信息。最终 URL 一律过 `records.sanitize_url` 再返回。

## 5. 两种传输模式（C）

| 模式 | 用途 | 关键约束 |
| --- | --- | --- |
| `offline`（默认） | 本批与 fixture 解析 | `RefusedTransport`，**不开 socket**，返回 `error=network_disabled_offline_batch` |
| `public-http` | 无账号公开页 | `_NoRedirect`：**3xx 不跟随**，作为结果返回 `redirect_not_followed:<code>` → 退出 7。单次 charge 绝不产生多次跨域请求 |
| `authenticated-browser` | login 之后的 search/detail/comments | 用**同一** `--profile` 驱动 nodriver；每次导航前由 `run_*` 预扣；落地 URL 必须仍在本域，否则 `offsite_redirect:<host>` → 退出 5 并锁。**不读、不导、不打印任何 cookie/localStorage** |

## 6. 导出白名单（D）

`normalize_record` 从 `EXPORT_FIELDS` 逐键取值，**从不 `dict(raw)`**。因此：

- `cookies`/`password`/`credentials`/`profile`/`author`/`nickname`/任意嵌套凭据 → **不可能出现在输出里**（不是“删掉”，是根本没被取）。
- `field_evidence` 只保留 `FIELDS` 内的键，且值必须以 `json:/html:/meta:/url:/input:/derived:/heuristic:/constant:` 开头、≤200 字符；否则置 `null` 并标 `evidence_rejected`。
- `source` 只允许 `zhihu:` + 已知后缀（如 `search_v3:answer`、`comment_v5`），否则 `redacted`。
- 导出返回值带 `dropped_keys` 计数，丢弃是可见的而不是静默的。

## 7. 阻塞：离线检查仍未执行（权限事实）

本执行者会话 `session-2890f16a-...` 的 `allowCommands=false`，工具集**无 shell**。本轮按要求**没有尝试** shell。因此：

- **没有任何真实 exit code**；`docs/validation/v10/zhihu/logs/` 下没有 `offline_checks.json`，没有 `.stdout.txt`。
- 我**不能**声称任何测试通过。

一条命令可跑（请派有权限的执行者）：

```powershell
cd D:\桌面\two
& "C:\Users\19183\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe" `
  docs\validation\v10\zhihu\offline_checks.py
```

它跑 `unittest` + 24 个 CLI 场景，把每条 `argv / cwd / started_utc / finished_utc / expect / exit / match` 写进 `logs/offline_checks.json`，末行打印 `{"all_match": bool, "mismatched": [...]}`。

**预期（按代码推演，非实测）**：`unittest` 0；`cli_search_offline` 0；`cli_search_second_offline` 6；`cli_relabel_no_reset` 6；`cli_detail/comments_offline` 0；`cli_export*` 0/0/9；`cli_input_missing` 8；`risk_first_call` 5；`risk_restart_refused` 6；`risk_relabel_refused` 6；`risk_login_refused` 6；`login_wall_first_call` 5；`login_wall_restart_refused` 6。

**若与实跑不符，以实跑为准，本报告结论作废重写。**

### 残留文件（如实披露）

`tools/selection/access/_probe.txt` 是我用来确认写权限的探测文件。本执行者**没有删除工具**，所以它留在仓库里（内容已改为说明文字，不被任何模块 import）。请顺手删除。

## 8. 实现完成 vs 真实未验证

| 能力 | 状态 |
| --- | --- |
| state-dir 单预算 / 无绕锁 / relabel 不重置 | **代码完成**，21 例测试已写；**未执行** |
| login 五态 + poll 独立配额 + 锁定拒绝 | **代码完成**，fake browser 测试已写；**未执行**，真窗口未开 |
| public-http 拒跟随重定向 | **代码完成**；**未执行**（`_NoRedirect` 单测已写） |
| authenticated-browser 复用 profile | **代码完成**；**未执行**，真实复用效果**未验证** |
| 导出纯白名单 + 递归扫断言 | **代码完成**；**未执行** |
| 知乎真实可读性（登录要求、HTML 选择器、comment_v5 字段、403/429 阈值） | **全部未验证** |
| 知乎登录页“已登录”DOM 特征 | **未验证**，通用形状假设；真跑前必须校正 |
| Chrome / nodriver 本机可用性 | 本执行者**未能枚举** Chrome 路径；策划者已独立确认存在。`browser.available()` 未运行 |

## 9. 下一批建议（3 次主动调用，本批不实施）

| 调用 | 命令 | 目的 |
| --- | --- | --- |
| 0（用户动作） | `login`（可见窗口，≤300s，本人扫码） | 拿到真实账号态；超时/未知均非零，**不得**当作已登录 |
| 1 | `--mode authenticated-browser search "关键词"` | 确认是否需要登录、`search_v3` 还是 HTML 兜底 |
| 2 | `--mode authenticated-browser detail <拼出的 URL>` | 校准 `og:title/description` 与互动字段 |
| 3 | `--mode authenticated-browser comments <同一 URL>` | 校准 `comment_v5` 的 `paging`/`vote_count` |

三次调用之间由账本强制 ≥15s；任何一次命中风控即锁 state dir 并永久停止，**不得为拿 exit 0 重跑**，也不得换 `--batch-id` 或新建 state dir 绕过——那需要策划者明确安排。
