# 百度贴吧六入口：离线就绪状态（2026-10-30）

- 结论：**doctor / login / search / detail / comments / export 六入口已在 `tools/selection/access/tieba.py` 实现**，全部可离线跑通；本批**零网络**（未打开贴吧、未登录、未发真实请求、未建账本）。
- 参照模板：`access/douyin.py` + `docs/validation/v10/douyin/*`；底座复用 `records.make_record(not_applicable=…)`、`EXPORT_FIELDS` 白名单、站点隔离账本、风险持久锁、脱敏诊断。

## 1. 六入口矩阵

| 入口 | 行为 | 网络 | 状态 | 证据（测试） |
| --- | --- | --- | --- | --- |
| `doctor(profile)` | 只读：profile 是否存在、cookie **名称**布尔（`BDUSS/STOKEN/BAIDUID/PTOKEN/SAID`）、浏览器是否找到；`network="none"` | **无** | **可用** | `DoctorTests`（用 `socket.create_connection` 抛错证明不触网） |
| `login(profile, budget=None)` | 只有显式命令且给 `budget` 才谈启动；离线批次返回 `status=unknown / stop=unsupported_offline` | 无（离线分支） | **可用但恒 unknown** | `UnsupportedTests` |
| `search`（解析） | `parse_search_html`：只认 `/p/<tid>` 链接，输出 `type=thread` 记录；无链接 → `empty`，有链接但不识别 → `unsupported` | 解析层无 | **离线可用** | `ParseTests` |
| `detail`（解析） | `parse_thread_html`：`/p/<tid>` + `<title>` → 一条 thread 记录；跨域 URL → `unsupported_content_url`，空页 → `empty` | 解析层无 | **离线可用** | `ParseTests` |
| `comments` | **显式 `unsupported_endpoint`**，`charged=false`，**在预扣之前返回** | 无 | **显式 unsupported** | `UnsupportedTests` |
| `export` | 白名单导出：只保留 `records.EXPORT_FIELDS`，丢弃的键计数返回 | 无 | **可用** | `ExportTests` |

## 2. 账本与约束（与抖音/微博对齐）

| 约束 | 贴吧实现 |
| --- | --- |
| 站点隔离 | `runtime/platform_tieba.sqlite3`（本批**不存在**，未扣费） |
| 预扣先行 | `TiebaLedger.charge()` 先校验锁/窗口/间隔/配额再写事件 |
| 跨实例累计 | 同文件新实例读到相同 `used`（`LedgerTests` 断言） |
| 最小间隔 | `MIN_INTERVAL=15s`，过密直接 `interval_not_elapsed` |
| 记录数 | **默认目标 5，可任意上调**；`reserve_records` 超出返回 `over_cap/over_by`，不拒绝不截断 |
| 风险持久锁 | `lock()` 写 `locks(site)`；`charge()` 检测到锁直接拒（`RiskLockTests`） |
| 脱敏 | `redact_url()` 去查询串；doctor 只回 cookie 名称布尔 |
| 不适用语义 | 帖子记录标 `root_comment_id/parent_id/voteup/reposts` 为 `not_applicable`，**不进 missing**（`NotApplicableTests`） |

## 3. 已实现 vs 未实现（显式）

- **已实现（离线）**：doctor、login（离线分支）、search 解析、detail 解析、export、账本（authorize/charge/lock/summary/events/reserve）。
- **未实现（显式返回，不假装）**：
  - `comments()` → `unsupported_endpoint`（端点未侦察）；
  - `login()` 真实窗口 → `NotImplementedError("tieba.login_window")`（需真实浏览器与用户操作）；
  - 浏览器驱动层（打开贴吧、滚动、点"下一页"）——本批不做，下一批按微博 `probe` 套路接。

## 4. 零网络证据

| 项 | 值 |
| --- | --- |
| `runtime/platform_tieba.sqlite3` | **不存在**（从未建账本/扣费） |
| `runtime/platform_douyin.sqlite3` | 不存在 |
| `runtime/platform_weibo.sqlite3` | mtime 仍 `2026-10-30 16:03:11`（weibo-rpa-21 那次写入，本批未动） |
| 残留 Chrome | `leftover_chrome=0` |

## 5. 测试

`tests.test_access_tieba` **15 OK**（Doctor / Ledger×2 / RiskLock×2 / Parse×4 / Unsupported×2 / NotApplicable / Export×2 / ExitCode）。
**六套全量 462 tests OK**（`test_selection_rpa` 177、`test_access_zhihu`、`test_access_weibo`、`test_access_budget`、`test_access_douyin` 35、`test_access_tieba` 15），无跳过。

## 6. 未做

未读/打印 cookie 值；未打开贴吧；未对真实页面截图；未改业务库/CSV/契约/小红书；未提交 git。
