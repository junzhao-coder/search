# 抖音六入口：离线就绪状态（2026-10-30）

- 结论：**六个入口（doctor / login / search / detail / comments / export）在 `tools/selection/access/douyin.py` 已实现，全部可离线跑通**；本批 **零网络**（未打开抖音、未登录、未发真实请求、未建账本）。
- 复用底座：固定权威账本（预算预扣 + `MIN_INTERVAL=15` + `MAX_SECONDS=300`）、风险持久锁、脱敏诊断、`records.FIELDS` 白名单导出、页面自身请求思路、以及"CDP 钩子必须 `Page.enable()` 才生效"的教训。
- **记录数口径（v11）**：`DEFAULT_RECORDS_TARGET=5` 是**默认目标值**，可任意上调；超出目标不拒绝、不截断，只由 `reserve_records()` 返回 `records_target/records_used/over_cap/over_by`。软的是存储，硬的是调用次数、15 秒间隔、单批时长与风险即停。

## 1. 六入口矩阵

| 入口 | 行为 | 网络 | 状态 | 证据（测试） |
| --- | --- | --- | --- | --- |
| `doctor` | 只读：profile 是否存在、cookie **名称**布尔、浏览器可用性；`network="none"` | 无 | **可用（离线）** | `DoctorTests` |
| `login` | 可见窗口给用户扫码/登录；**一律报 `unknown`**（从未观测到真实登录态页面，不假装确认） | 真实（用户主动） | **可用但判定保守** | `DoctorTests`/`CliTests` |
| `search` | 关键词搜索页 → 解析视频卡片；无结果/无识别 → 非零 `unsupported`/`empty`，**不猜游标** | 真实（需批次） | **离线可用**（解析+预算+锁已测） | `ParseTests`/`LedgerTests`/`RiskLockTests` |
| `detail` | 单视频页 → 一条记录（og/meta/title）；拿不到就 `unsupported` | 真实（需批次） | **离线可用** | `DetailSettleTests`/`DetailExceptionTests` |
| `comments` | 评论区入口；**当前显式 `unsupported`**（端点未侦察，只有骨架，不返回空成功） | 真实（需批次） | **显式 unsupported** | `CommentsTests` |
| `export` | 统一白名单导出（`records.EXPORT_FIELDS`） | 无 | **可用（离线）** | `ExportTests` |

## 2. 关键约束（与微博对齐）

| 约束 | 抖音实现 | 微博对照 |
| --- | --- | --- |
| 预算预扣 | `DouyinLedger`：`CALL_KINDS=(active_nav, search, detail, comments)`，先扣后跑 | 同（`platform_weibo.sqlite3`） |
| 跨实例累计 | 账本落盘在 `runtime/platform_douyin.sqlite3`，跨进程累计 | 同 |
| 最小间隔 | `MIN_INTERVAL=15s`（调用过密直接拒） | 同（实测踩过） |
| 记录数 | **默认目标 5，可任意上调**；超出以 `over_cap/over_by` 标记，不拒绝不截断 | 同口径（v11 起微博也不再截断） |
| 风险锁 | `RISK_MARKERS` 命中即持久锁，后续调用被拒 | 同 |
| 脱敏 | 诊断里抹掉关键词/URL 查询值；`_scrub` | 同 |
| 不适用语义 | 复用 `records.make_record(not_applicable=...)` | 本轮刚修 |

## 3. 本批零网络证据

- `tools/selection/access/runtime/platform_douyin.sqlite3` **不存在**（从未建账本、从未扣费）；
- 微博账本 `platform_weibo.sqlite3` mtime 仍为 `2026-10-30 16:03:11`（上一批 weibo-rpa-21 写入，本批未动）；
- 无残留 Chrome 进程（`leftover_chrome=0`）。

## 4. 测试

`tests.test_access_douyin` **35 OK**（16 个测试类：Doctor / OfflineDefault / Ledger / Parse / Comments / Export / Cli / KeywordLeak / HostValidation / RiskLock / TransportErrorScrub / DetailSettle / WallVsDescription / DetailException / RiskReasonScrub）。
**五套全量 447 tests OK**（含 `test_selection_rpa` 177），无跳过。

## 5. 仍需真实访问才能定的（下一批，需用户同意）

1. 搜索结果页与详情页的真实 DOM/选择器（当前解析器按"可见文本 + og/meta"写，未对真实页校准）；
2. 评论端点（推测同样走页面自身 XHR；需先 `Page.enable()` 再挂钩子，用 `network` 审计定位）；
3. 登录态判定信号（现在一律 `unknown`，需真实登录页采样才能放宽）；
4. 风险标记词表（当前来自静态假设，需真实拦截页校准）。

## 6. 未做

未读/打印 cookie 值；未打开抖音；未对真实页面截图；未改业务库/CSV/契约/小红书；未提交 git。
