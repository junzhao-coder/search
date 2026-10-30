# 微博预算 / 风险锁 / 授权范围 只读审计（修订版 v2，回应退回意见）

- 修订原因：策划者退回（revision 4）指出五类问题：发现范围未限定、计数口径不严（把"显式搜索尝试"写成"恰好 2 次 HTTP 请求"）、probe3 字节数写错（33824 误作 34068）、授权表述不当（把"已给同意"缩成"仅一次搜索"，且未点出"登录不计调用"与 P5 的冲突）、carryover 方案当成可执行。
- 本轮动作：**纯离线修正本报告**。未触网、未启浏览器、未读 profile/cookie、未改写任何账本、未改业务代码。
- 报告纪律：只写**能指到证据**的话；证据不足处一律标注"未知/缺证"。

## 1. 发现范围、完整性限制（先划边界）

| 项 | 说明 |
| --- | --- |
| 发现方式 | 以 `docs/validation/v10/**/budget.sqlite3` 为起点，**只保留路径中含 `weibo` 且不含 `profile` 的目录**，共 **9 个** state-dir |
| 因此**不覆盖** | `instance/`、`tools/**/runtime/`、`docs/validation/v10` 之外、任何名称不含 `weibo` 的账本；也无法覆盖其它机器/已删除目录 |
| 结论强度 | "9 个 / calls 合计 6"只能表述为"**本次发现范围内**"，**不能**说成"项目所有账本" |
| 读取方式 | `sqlite3` + `mode=ro&immutable=1`（只读） |
| **immutable 的局限** | `immutable=1` 假定库文件不再变化，会**忽略 `-wal`**；若存在未 checkpoint 的 WAL，读到的行可能偏少。**本次事后检查**：在被审范围用 `**/budget.sqlite3-wal` 通配查找 → **无 `-wal` 文件**，故本例未漏读 WAL；但这是事后检查，不是读取机制保证 |
| 数据层级 | `budget` 表 = **权威计数器**（`calls`/`polls`/`locked`/`started_at`/`last_call_at`）；`ledger` 表 = **过程证据**（charge/poll/search_result/transport_error…）。两者不可互相替代 |
| 缺证目录 | `weibo\checks\state_login` 的 `ledger` 为 **0 行**、`calls=0`：只能说明"这次离线 login 没有记账"，**不能**据此推断任何浏览器行为 |
| 未实测 | 浏览器子资源请求数、重定向链、TLS/连接事件、服务端响应码：**全部未知**（无抓包、无 devtools 事件日志） |

## 2. 事实台账（逐目录，来源 = 账本行）

| # | state-dir（相对仓库根） | batch_id | calls | polls | locked | ledger 行数 / kinds | 首行→末行（UTC） | 来源证据 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | `docs\validation\v10\weibo\checks\state_search` | batch-c3a95da8844b | 1 | 0 | 0 | 2 / charge, transport_error | 15:27:25 → 15:27:25 | 账本两行 |
| 2 | `...\weibo\checks\state_detail` | batch-296ca6ae3e1e | 1 | 0 | 0 | 2 / charge, transport_error | 15:27:25 → 15:27:25 | 账本两行 |
| 3 | `...\weibo\checks\state_comments` | batch-0bd57e922206 | 1 | 0 | 0 | 2 / charge, transport_error | 15:27:26 → 15:27:26 | 账本两行 |
| 4 | `...\weibo\checks\state_login` | batch-ccdd90ed2656 | 0 | 0 | 0 | **0 / 无** | — | 无行（缺证） |
| 5 | `...\weibo-probe\state-probe1` | weibo-probe-1 | **1** | 0 | 0 | **1 / charge** | 15:05:47 → 15:05:47 | 仅 charge；**无 transport_error 行** |
| 6 | `...\weibo-probe\state-probe2` | weibo-probe-2 | **1** | 0 | 0 | 2 / charge, search_result | 15:13:13 → 15:13:18 | 账本 + REPORT_PROBE2.md（exit 4，elapsed 4.399s，html_bytes 34068） |
| 7 | `...\weibo-probe\state-probe3` | weibo-probe-3 | **1** | 0 | 0 | 2 / charge, search_result | 15:27:55 → 15:28:02 | 账本 + REPORT_PROBE3.md:74-91（exit 7，elapsed 7.406s，**html_bytes 33824**，render_wait_ms 5250，dom_anchor_count 0，textLen 0，wall null） |
| 8 | `...\weibo-login\state-login` | batch-8fdd2a665a28 | 0 | **100** | 0 | 100 / poll | 15:36:07 → 15:41:06 | 账本 100 行 + REPORT_LOGIN1.md（exit 11，status timeout，302.026s） |
| 9 | `...\weibo-verify\state-login` | batch-1ac1643ee579 | 0 | **100** | 0 | 100 / poll | 15:49:06 → 15:54:04 | 账本 100 行 + REPORT_VERIFY.md |

机读汇总（本次范围，`audit.py` v2 → `audit.json`，生成于 **2026-10-29T13:48:25Z**）：

```json
{"state_dirs": 9, "total_calls": 6, "total_polls": 200, "any_locked": false,
 "units": {"historical_probe_precharges": 3, "historical_login_navigations": 2,
           "planned_check_session": 1, "planned_search": 1, "total": 7}}
```

`audit.json` 现在自带 `scope`（根、include/exclude、9 个目录清单）、`limits`（immutable 忽略 WAL、无抓包、ledger 不参与额度、calls 只由 charge 计）与 `classification`（探路/离线/登录三组，且每条带 `observed_navigation` 布尔值）：

| 分类 | 目录 | calls | polls | `observed_navigation` |
| --- | --- | --- | --- | --- |
| 探路 | state-probe1 | 1 | 0 | **false**（启动失败，未观察到导航） |
| 探路 | state-probe2 | 1 | 0 | true（一次显式浏览器搜索尝试） |
| 探路 | state-probe3 | 1 | 0 | true（一次显式浏览器搜索尝试） |
| 登录 | weibo-login\state-login | 0 | 100 | true（窗口打开并轮询） |
| 登录 | weibo-verify\state-login | 0 | 100 | true（窗口打开并轮询） |
| 离线 | checks\state_{search,detail,comments} | 各 1 | 0 | —（离线，零网络） |

## 3. 分类统计（严格口径）

### 3.1 三次探路预扣（各自 1 次 `calls`）

| 次 | 时间（UTC） | 账本 | 性质（**严格表述**） |
| --- | --- | --- | --- |
| probe1 | 15:05:47 | calls=1，仅 charge | **浏览器启动失败；未观察到任何微博请求**。"未观察"≠"零 HTTP"：无抓包，子资源/重定向无法排除 |
| probe2 | 15:13:13→18 | calls=1，+ search_result{count 0, exit 4} | **一次显式浏览器搜索尝试**（4.399s，html_bytes 34068）。**不是**"恰好 1 次 HTTP 请求"：导航可能带重定向/子资源 |
| probe3 | 15:27:55→28:02 | calls=1，+ search_result{count 0, exit 7} | **一次显式浏览器搜索尝试**（7.406s，**html_bytes 33824**，非 34068） |

### 3.2 三次离线预扣（**独立标注**，不与真实调用混算）

`weibo\checks\state_{search,detail,comments}` 各 `calls=1`，ledger = `charge` + `transport_error: network_disabled_offline_batch`（15:27:25–26）。这是**离线自检**：设计上零网络，但**仍然**各占一个 state-dir 的 1 次 `calls`。它与"微博平台额度"不是同一口径：**不应**用来抵扣首批 3 次，也**不应**被忽略（它证明预扣在失败路径上同样生效）。

### 3.3 两次人工登录（主动导航，**未计入 calls**）

| 次 | 时间（UTC） | 账本 | 记录 |
| --- | --- | --- | --- |
| 登录窗 #1 | 15:36:07→15:41:06 | calls=0，polls=100 | REPORT_LOGIN1.md：`exit=11 / status=timeout / 302.026s`；窗口标题曾变为微博站点（用户自述已登录，程序判定未命中） |
| 登录窗 #2 | 15:49:06→15:54:04 | calls=0，polls=100 | REPORT_VERIFY.md：第二次登录窗；账本**不记录 final_url**，"落到 passport"只有报告文字，账本层面缺证 |

两次都**真实打开浏览器并导航**（`browser.get(LOGIN_URL)` / `SESSION_CHECK_URL`），但 `login()` 只调用 `charge_poll()`，**一次 `charge()` 都没有** → 账本 `calls` 仍为 0。这是 §5.2 口径冲突的直接证据。

### 3.4 轮询

`200` 次 `poll`（2 个目录各 100），`polls_max=120` 是**每目录**上限。轮询不是主动调用，但也不是零成本：每次窗口约 300s。

### 3.5 其它未知量

浏览器子资源数、重定向跳数、每次导航实际 HTTP 事务数、服务端响应码、CDP 错误数：**未知（无抓包/无事件日志）**。因此本报告**不使用**"共发出 N 次 HTTP 请求"这种表述。

### 3.6 「已观察的导航」与「计费单位」必须分开（关键口径）

**已观察到真的发生过的主动导航 = 4 次**：
- probe2：一次显式浏览器搜索尝试（有 `search_result`）；
- probe3：一次显式浏览器搜索尝试（有 `search_result`）；
- 登录窗 #1、#2：窗口打开并轮询（各 100 poll），发生了导航到登录/会话页。

**未观察到导航、但已预扣 1 次 calls**：probe1（启动失败，浏览器没起来）。

**尚未发生**：`check-session`（计划 1）、登录后搜索（计划 1）。

因此 §5.3 里 **3 + 2 + 1 + 1 = 7 是「保守计费单位」合计，不是"已发生 7 次导航"，更不是"7 个 HTTP 请求"**：
- 3 = 历史**探路预扣**（含 probe1 那次未发生导航的预扣）；
- 2 = 历史**登录窗主动导航**（已发生，但账本 calls=0）；
- 1 = 计划中的 `check-session` 主动导航（未执行）；
- 1 = 计划中的登录后搜索（未执行）。

## 4. "无锁"与 `wall=null` 的边界

1. **无锁只限已审范围**：9 个账本 `locked=0`、`lock_reason/lock_source=null`。这只能说明"**在本次发现的 9 个 state-dir 里**没有锁记录"，**不能**推断"项目历史上从未触发风险"，也不能推断"平台侧没有触发风控"。
2. **`wall=null` 不是"排除风险"**：probe3 同一份诊断里 `html_bytes=33824`，而 `dom_anchor_count=0`、`textLen=0`、`render_wait_exhausted=true`（render_wait_ms 5250）。L3 文本扫描读到 0 字符，`wall=null` 只说明"探针没读到文本可供匹配"。**不得**据此说"访客墙已排除"。
3. 锁的**真机**行为（能否拦住后续命令）在这 9 个目录里**无样本**；只有离线测试证据。

## 5. 授权、口径冲突与保守计数

### 5.1 用户已经给出的同意（不要抹掉）

用户当时的同意，是对"**新批次 3 次额度 + 开登录窗口 + 登录后 1 次搜索**"这一描述的回应（选择"要开登录窗口"）。因此已给授权至少包含：新批次 **3 次主动调用**额度；**开登录窗口**（人工登录）；登录后 **1 次搜索**。

**歧义（显式列出，不替用户裁决）**：
1. "3 次"是**总**主动调用（含登录导航/会话检查），还是**仅搜索**？
2. 两次**历史登录窗导航**是否算在这 3 次里？
3. 计划后来新增的 `login --check-session`（主动导航 `https://weibo.com/`）属于"登录"的一部分，还是额外第 4 次？

### 5.2 口径冲突（本小目标 vs P5）

| 口径 | 内容 | 证据/关系 |
| --- | --- | --- |
| **P5（计划）** | 每平台首批**主动导航或显式调用**跨命令/重启/返工累计；失败也预扣 | 登录窗导航、check-session 都属"主动导航" → 应计 |
| **本小目标/实现** | `login()` 只 `charge_poll()`，`calls` 不计 | 账本证据：两个登录目录 `calls=0`、各 100 poll（§3.3） |

结论：**当前实现事实上把"登录/会话检查"当成不占主动调用额度**，与 P5 不一致。本报告**不主张**可以借此绕开约束；下面按 P5 做**保守计数**。

### 5.3 保守计数（按 P5 口径，**计费单位**，非已发生导航数）

| 计费单位 | 数量 | 是否已发生 | 账本 `calls` 是否支撑 |
| --- | --- | --- | --- |
| 历史探路预扣（probe1/2/3） | 3 | 2 次已发生搜索尝试 + 1 次启动失败（未观察导航） | 有（各 1） |
| 历史**登录窗主动导航** | **2** | 已发生 | **无**（calls 均 0） |
| 计划中的 `check-session` 主动导航 | 1 | **未发生** | 无（会只记 poll） |
| 计划中的登录后搜索 | 1 | **未发生** | 无 |
| **计费单位合计** | **7** | 已发生 4 次导航（probe2/3 + 两个登录窗） | 账本只反映 3 次 `calls` |
| 离线自检预扣（不计网络） | 3 | 已发生（离线） | 有（各 1，独立目录） |

> 再次强调：**7 是计费单位，不是 7 次已发生导航，也不是 7 个 HTTP 请求**（§3.6）。严格按 P5，"首批 3 次"历史上已被 3 次探路预扣占满，另有 2 次登录导航未计入；再跑 check-session + 1 次搜索会让"未入账的主动导航"增至 4 次。

## 6. carryover 方案：**设计草案，当前不可执行**

### 6.1 为什么"只写 ledger detail"不行（代码核对）

| 事实 | 证据 |
| --- | --- |
| `calls` 是 `budget` 表的**独立列**，`charge()` 读它并与上限比较 | `budget.py:159-160` `if r["calls"] >= self.max_calls: raise BudgetError("calls_exhausted", …)` |
| 上限常量 `MAX_CALLS = 3`（可按目录用 `open_budget(**limits)` 覆盖） | `budget.py:33`；`open_budget(state_dir, *, batch_id=None, clock=…, **limits)` `budget.py:273` |
| 单次窗口 300s，**从 `started_at` 起算**，超时即 `time_exhausted`（**拒绝，不是刷新**） | `budget.py:40 MAX_SECONDS=300.0`；`:161-162` |
| 最小间隔 15s | `budget.py:39`、`:163-165` |
| 锁是**单目录**的 `budget.locked` 标志 | `budget.py:248-261`（只 `UPDATE … WHERE id=1` 当前库） |
| `batch_id` **只是标签**；计数/窗口/锁都是 state-dir 宽 | `budget.py:273-280` 注释原文 |
| `ledger` 表**不参与**任何额度判定 | 全仓只有 `charge()/charge_poll()` 读 `budget` 表 |

因此：**在 `ledger` 里写一条 `carryover` 不会让 `snapshot()["calls"]` 变成 6**；新目录 `calls` 仍是 0，`charge()` 照放行。若硬把 `calls` 改成 6，`6 > MAX_CALLS=3` 会让**任何** `charge()` 立刻 `calls_exhausted`；300s 窗口到期还会 `time_exhausted`。**所以 v1 的"手工写 carryover"不可执行**，本版明确标注为**设计草案**。

### 6.2 具体修复项（后续任务实现，本轮不改码）

1. **单一权威账本**：一个平台级 state-dir 作为唯一额度源；其它目录只作历史证据（只读），不参与放行判断。
2. **结转进结构，不进 detail**：`budget` 表加 `carryover_calls INTEGER NOT NULL DEFAULT 0`，`charge()` 判定改为 `carryover_calls + calls >= max_calls`；`snapshot()` 同时暴露两者——"6"是结构化已用额度，不靠 ledger 文本假装。
3. **来源导入幂等**：`import_sources([...])` 以"源目录 resolved 路径 + 源库 `max(ledger.id)` + 源 `calls`"做指纹，落 `imported_sources(source_path PRIMARY KEY, calls, last_ledger_id, imported_at)`；重复导入同一源不重复累加。
4. **区分离线测试与生产调用**：离线自检写 `calls` 时带 `kind=offline_check`（或 `mode` 列），平台额度只累加 `mode=live` 的调用；避免把 3 次离线自检和真实探路混在同一个 `calls` 概念里。
5. **历史锁继承**：`open_budget(..., inherit_from=[...])`；打开时任一来源 `locked=1` → 直接 `BudgetError("batch_locked", "inherited:<path>")`，并写 `lock_source="inherited"`。
6. **P5 时间窗管理**：现有 300s 是**单次运行窗口**（到期=拒绝）。平台级另设 `window_started_at` + `window_max_seconds`（如"每批次 N 次 / 24h"），并明确"到期只解除时间窗，不恢复次数"；`snapshot()` 同时暴露两套窗口。

### 6.3 离线测试方案（后续任务）

| 测试 | 期望 |
| --- | --- |
| `carryover_calls=6, max_calls=3` → `charge()` | `BudgetError("calls_exhausted", "6/3")`，`snapshot()` 同时显示 `carryover=6, calls=0` |
| 同源导入两次 | 第二次不改变 `carryover_calls`（幂等） |
| 源 A `locked=1` → `open_budget(inherit_from=[A])` | `BudgetError("batch_locked")`，`lock_source="inherited"` |
| 离线自检 `kind=offline_check` | 不增加 `carryover`/live calls |
| 300s 窗口到期 | `time_exhausted`，且**不**恢复次数（回归断言） |
| ledger 里写 carryover 文本 | **不**改变 `snapshot()["calls"]`（防止再走回旧草案） |

## 7. 已决定的事项 与 仅剩的计量口径

### 7.1 已由用户决定（不再重复询问）

1. **新批次 3 次额度**：已同意。
2. **开登录窗口**：已同意，并且已经实际执行过两次（§3.3）。
3. **登录后 1 次搜索**：已同意，尚未消费（三次探路都在两次登录之前，登录后没跑过搜索）。

本报告不再就以上三项向用户重复确认。

### 7.2 仅剩的计量口径（事实层面，供 P5 裁定；不向用户重复提问）

审计能确定的只有事实，口径需要按 P5 统一：

| 待统一项 | 事实 | 本报告的保守处理 |
| --- | --- | --- |
| `check-session` 是否占用新批次的一次 | 它是主动导航（`weibo.py:324` 导航 `https://weibo.com/`），但实现只记 poll | **按占 1 次**处理（计入 §5.3 的 7 个计费单位），不声称可免费 |
| 两次历史登录窗导航是否追认 | 已发生 2 次导航，账本 `calls=0` | **按已发生的主动导航**列出；是否从新批次扣减，属计划口径，不在此替用户决定 |
| probe1 的启动失败预扣 | 已扣 1 次 calls，未观察到导航 | **保留在"3 次预扣"里**（P5：失败也预扣） |

> 这三项不是"再问用户要不要登录/要不要额度"，而是审计给出的**口径事实**：账本只记了 3 次 calls，实现又不给登录记账。按 P5 保守口径，历史+计划合计 **7 个计费单位**（已发生导航 4 次）。

## 8. 测试与后续任务建议

1. 先做 §6.3 的离线单测（不改现有账本、不触网），再做 §6.2 的代码改造。
2. `audit.py` 把**发现范围**写进 `audit.json`（`scope: {root, include_pattern, exclude_pattern, state_dirs}`）并带 `limits: ["immutable ignores WAL", "no packet capture", "calls only counts charge()"]`。
3. 增加只读子命令 `weibo budget audit`，输出与 `audit.json` 同结构，避免下次靠临时脚本。
4. 报告纪律：凡"已登录/可读/无墙"结论，必须附页面级证据（`final_url` + `ready_state` + `anchors_*` + `wall` + `textLen>0`），**不能**用 cookie 名或 `wall=null` 代替。

## 9. 本报告明确不主张的事

1. 不主张"项目所有微博账本只有 9 个"——只是**本次发现范围**内 9 个。
2. 不主张"从未触发过任何风险"——只说"已审 9 个目录里没有锁记录"。
3. 不主张"访客墙已排除"——`wall=null` 是在 `textLen=0` 状态下取得的。
4. 不主张"cookie 名证明登录"——`doctor` 只读名字。
5. 不主张"URL/参数正确"——`containerid` 等仍属假设。
6. 不主张"登录/会话检查零成本"——按 P5 它们都是主动导航（§5.3 保守计数 7 次）。
7. 不主张"时间窗到期会刷新额度"——300s 到期是 `time_exhausted`（拒绝），不是恢复。
8. 不主张"carryover 手写方案可执行"——它是设计草案（§6.1 有反证）。

## 10. 只读操作清单（本轮）

- 执行 `audit.py` **v2**（`python -X utf8 docs/validation/v10/weibo-budget-audit/audit.py`，exit 0，**2026-10-29T13:48:25Z**），以 `mode=ro&immutable=1` 重新汇总 9 个账本；`audit.json` 现含 `scope` / `limits` / `classification`（每条带 `observed_navigation`）。输出：`state_dirs=9, total_calls=6, total_polls=200, any_locked=false, units.total=7`。
- `glob` 查 `docs/validation/v10/weibo*/**/budget.sqlite3-wal`：**无结果**（"未漏读 WAL"的事后检查）。
- `read` 读取 `REPORT_PROBE3.md:70-91`（核对 `html_bytes=33824`、`render_wait_ms=5250`、`dom_anchor_count=0`、`textLen=0`、`wall=null`）。
- `grep`/`read` 核对 `budget.py`：`MAX_CALLS=3`（:33）、`MAX_SECONDS=300.0`（:40）、`MIN_INTERVAL=15.0`（:39）、`charge()` 判定顺序（:149-180）、`lock()` 单目录语义（:248-261）、`open_budget()` state-dir 宽语义（:273-280）、`charge_poll()` 不校验窗口（:182-205）。
- 未写入任何账本（`audit.py` 只读打开 SQLite，唯一写入是本目录的 `audit.json`）；未读 profile/cookie；未触网；未启浏览器。
