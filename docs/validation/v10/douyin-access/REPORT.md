# 抖音适配器（最小可运行）：入口、解析、独立账本与能力登记

> 任务 `task-494e1d6240af1cde98e22eb1941eb451`（rev2，计划 v10）。
> **本轮纯离线**：未向抖音/微博发任何真实请求、未打开浏览器、未登录、未读凭据值。
> 真实能力**尚未验证**：本文所有"能做什么"都指**离线可运行并已测**，不指"已接通真实站点"。

---

## 1. 入口（独立 CLI）

```bash
D:\桌面\two\.venv\Scripts\python.exe -X utf8 -m tools.selection.access.douyin \
  --state-dir <dir> [--profile <dir>] [--batch-id <id>] \
  [--mode offline|public-http|authenticated-browser] \
  doctor | login [--timeout N] [--headless] \
  | search <关键词> [--limit 5] [--visible] [--timeout 60] \
  | detail <url> | comments <url> | export <input> [--output] | budget
```

| 子命令 | 状态 | 说明 |
| --- | --- | --- |
| `doctor` | **可用（离线）** | profile 是否存在、cookie **名称**布尔、浏览器是否可用；`network="none"`、`online="unverified"` |
| `login` | **入口可用，结论恒为 unknown** | 需要用户自己操作的可见窗口；本适配器**没有**观察过真实登录态页面，即使出现登出样式节点也**不**判已登录 |
| `search` | **离线解析可用** | 默认 `--mode offline`（RefusedTransport，不开 socket）；解析 `/video/<id>` 锚点 |
| `detail` | **离线解析可用** | 只接受 `https://www.douyin.com/video/<id>`；取 `og:title`/`og:description`，取不到即 `unsupported` |
| `comments` | **明确 unsupported（非零）** | 无可证端点，**不猜 cursor**、不返回空成功 |
| `export` | **可用** | 复用知乎/微博同一套白名单导出器 |

## 2. 解析字段与"缺失"语义

统一 `records.FIELDS`：`native_id / type / parent_id / url / title / text / published_at /
collected_at / voteup / comments / likes`，另带 `missing / supported / field_evidence / source`。

| 来源 | 字段证据 |
| --- | --- |
| 搜索锚点 | `native_id=url:/video/<id>`、`type=url:/video/<id>`、`url=html:a[href]`、`title=html:a[text]` |
| 详情页 | `title=meta:og:title`、`text=meta:og:description`、`url=input:video_id` |

**不把通用锚文本当正文**：`title` 若等于「全文」等通用标签则置空并计入 `missing`（测试 `test_generic_anchor_text_is_not_used_as_the_body`）。
**去重**：同一 `video_id` 多次出现只保留一条（测试 `test_search_parses_and_deduplicates_video_ids`）。

## 3. 独立账本（抖音专用，固定路径）

`tools/selection/access/douyin.py::DouyinLedger`，落盘 `tools/selection/access/runtime/douyin_platform.sqlite3`：

- 表：`batches`（显式授权）、`events`（仅追加）、`reservations`（记录配额）、`locks`（按 site 唯一）。
- `charge()`：`BEGIN IMMEDIATE` 内**先查锁**再计数 → 同批 **15 s 间隔 / 5 条记录 / 300 s 窗口**；窗口关闭拒绝、不重开；失败**不退款**。
- **跨 state-dir / 重启不重置**：账本路径固定、按 site 记录（测试 `test_charge_is_shared_across_state_dirs_and_restarts`、`test_risk_lock_survives_a_new_ledger_and_blocks_other_dirs`）。
- **不复用微博历史 gate**：抖音没有历史快照要求，代码里不引用 `platform_budget` 的历史校验。
- 真实网络路径：`--mode authenticated-browser` 且 `--batch-id` **已授权**才建 transport；否则 `platform:no_authorized_batch` / `platform:batch_id_required`，**不建 transport**（测试 `test_real_network_mode_requires_an_authorized_batch`）。

## 4. 风险即停

`RISK_MARKERS` 与 `EMPTY_MARKERS` 见模块顶部；`detect_risk` 命中 → 本地 `batch.lock()` + 抖音账本 `lock()`，`exit=EXIT_RISK(5)`，无自动重试（测试 `test_risk_lock_survives_a_new_ledger_and_blocks_other_dirs`）。
`403/429` 由共享 transport 归入风险/传输错误分支，同样非零退出。

## 5. 测试与执行记录（UTF-8 原始日志）

| 模块 | exit | 结果 | UTC |
| --- | --- | --- | --- |
| `tests.test_access_douyin` | 0 | Ran 16 tests … OK | 2026-10-29T15:18:38Z |
| `tests.test_access_weibo` | 0 | Ran 92 tests … OK | 15:18:38Z → 15:18:59Z |
| `tests.test_access_zhihu` | 0 | Ran 96 tests … OK | 15:18:59Z → 15:19:07Z |
| `tests.test_access_budget` | 0 | Ran 47 tests … OK | 15:19:07Z → 15:19:16Z |

- 原始日志：`tests.test_access_douyin.log`、`tests.test_access_weibo.log`、`tests.test_access_zhihu.log`、`tests.test_access_budget.log`
- 清单：`RUN_MANIFEST.json`（模块 / exit / UTC 起止 / 结果尾部）
- 抖音 16 条覆盖：doctor 离线与 cookie 名称、默认 offline 传输、失败仍计费、跨目录/重启额度、间隔与窗口、记录上限 5、风险锁跨实例、解析去重与「全文」处理、详情 meta 与 unsupported、非视频 URL 输入错误、comments 非零 unsupported、导出白名单、CLI 未授权拒绝、login 恒 unknown。

## 6. 能力登记（明确不宣称）

| 能力 | 状态 |
| --- | --- |
| doctor 离线体检 | ✅ 已实现并测试 |
| 搜索 HTML 解析（`/video/<id>`） | ✅ 离线测试通过；**真实页面未观察**，选择器标 assumed |
| 详情 meta 解析 | ✅ 离线测试通过；真实页面未观察 |
| 评论 / 子回复 / 分页 | ❌ **unsupported**（无端点证据，返回非零，不猜 cursor） |
| 登录态判定 | ❌ **unknown**（无真实登录页证据，绝不判 ok） |
| 真实网络采集 | ⛔ 默认关闭；需显式授权批次，且**从未真实执行过** |
| 可见窗口 | 未打开、未验证（本轮离线） |

## 7. 后续真机验证命令（本轮**未执行**）

```bash
# 1) 体检（离线，安全）
python -X utf8 -m tools.selection.access.douyin --state-dir <state> doctor

# 2) 用户自行登录（可见窗口；结果只会是 unknown）
python -X utf8 -m tools.selection.access.douyin --state-dir <state> --batch-id <id> login --timeout 300

# 3) 授权后的一次搜索（真实网络；需先 authorize_batch）
python -X utf8 -m tools.selection.access.douyin --state-dir <state> --batch-id <id> \
  --mode authenticated-browser --profile <profile> search "关键词" --limit 5 --visible --timeout 60
```

## 8. 边界与限制

- 未发任何抖音/微博真实请求；未打开浏览器；未登录；未读 cookie/token 值。
- 未修改业务库 / CSV / CONTRACT / 旧小红书封存；未安装依赖（仅标准库）。
- 选择器全部 **assumed**；真实页面结构未知，解析可能整体落到 `unsupported`。
- 抖音账本文件在本轮测试中只使用临时目录，真实路径 `runtime/douyin_platform.sqlite3` **未创建**。


---

## 9) 第 2 轮返工（rev5）：login 降级、关键词零泄漏、风险双锁、host 校验

1. **`login` 改为显式 unsupported（预扣前）**：`status=unsupported`、`exit=4`、`stop=login_not_supported:no_visible_window_implemented`，**不调用 charge、不建浏览器、不导航**；CLI 的 login 分支在账本网关之前返回。测试：`test_login_is_unsupported_and_charges_nothing`（`used==0`、`events==[]`）、`test_cli_login_exits_unsupported_without_charging`（真实 CLI 退出码 4）。
2. **关键词零泄漏**：搜索账本 detail 固定为 `"search"`（操作名），payload `url` 固定为 `https://www.douyin.com/search`；对返回 payload 递归擦除关键词的**明文与 `quote()` 编码**形式（含 diagnostics 里的 URL）。测试：`test_chinese_keyword_never_leaks`、`test_english_keyword_never_leaks`、`test_cli_search_keyword_never_reaches_the_ledgers` —— 同时扫描 `budget.sqlite3`、抖音账本与输出 JSON，两种编码均零出现。
3. **风险双作用域持久锁**：搜索墙、详情墙、**详情解析层 `risk:`** 均要求 `batch.lock()` 与 `ledger.lock()` 都成功；任一写失败 → `exit=6`、`stop=platform:lock_write_failed`（不再 suppress）。结算写失败 → `exit=6`、`ok=false`、`records=[]`。测试：`test_parse_detail_risk_locks_both_scopes`（新实例仍见锁）、`test_lock_write_failure_is_nonzero`、`test_settle_failure_is_not_a_success`。
4. **host/scheme 前置校验**：`parse_search_html` 只接受解析后属于 `douyin.com` 的链接（离站锚点计 rejected）；`run_detail` 在 charge/fetch **之前**校验 `allowed_url`，非法即 `EXIT_INPUT` 且不 fetch。测试：`test_off_host_anchors_never_become_records`、`test_detail_rejects_foreign_hosts_before_fetch`（断言 `transport.urls == []`）。
5. **能力状态更新**：登录窗口**未实现**（不再声称会打开）；其余能力登记同 §6。

验证：`tests.test_access_douyin` **25 条**、weibo 92、zhihu 96、budget 47，全部 exit 0；日志见 `tests.test_access_*.log` 与 `RUN_MANIFEST.json`。


---

## 10) 第 3 轮返工（rev8）：失败路径脱敏、detail 必结算、墙词与描述层区分

1. **search 全路径脱敏（含失败）**
   - `transport.fetch` 包 try/except：异常 → `exit=EXIT_TRANSPORT`、`records=[]`、`stop=adapter_exception:*`，并结算 `search_result`（预扣不退）。
   - 传输错误分支**先脱敏再写本地账本**：`batch.note("transport_error", _scrub(reason, keyword))`。
   - 所有返回路径（成功/传输错误/异常/预算拒绝）统一 `_scrub(payload, keyword)`，覆盖嵌套 `diagnostics.requested_url/final_url` 与 `error` 字段的**明文与 `quote()`** 形式。
   - 测试 `TransportErrorScrubTests`：fake transport 的 `error` 与 `diagnostics` 均携带**原始搜索 URL**，跑中文关键词；同时扫 `budget.sqlite3`、抖音账本、输出 JSON —— 明文与 `%E5%AD%A6…` 编码均零出现，且本地账本仍有 `transport_error` 行（说明写入的是脱敏后的 reason）。
2. **detail 预扣后必结算**
   - 成功 / 失败 / **fetch 异常** 三条路径都经 `_settle(...)` 落 `detail_result`；结果写失败 → `exit=6`、`ok=false`、`records=[]`。
   - 测试 `DetailSettleTests`：成功路径断言账本 `detail_result=success`；mock `record_result` 抛错 → `exit=6` 且 `records=[]`。
3. **登录墙/验证码 vs 普通讨论**
   - 扫描范围改为 **head + description + body**（meta-only 页面此前会漏检，这是本轮修掉的真 bug）。
   - 规则：墙词出现在 **`<title>`/`og:title`** 或**正文**（且不在 description）→ **真风险**：双作用域持久锁、`exit=5`；墙词**只在 `og:description`** → **不加锁**，`stop="risk_ambiguous"`、`exit=4`、`records=[]`。
   - 取舍：描述层是"用户讨论验证码"和"伪装墙"共同出现的地方，无法可靠区分，因此**不锁也不放行**（不产生记录、该次额度已消耗、真实网络默认关闭）。宁可 unknown，不误杀正常内容，也不静默成功。
   - 测试 `WallVsDescriptionTests`：描述含「安全验证」→ `risk_ambiguous`、`records=[]`、`ledger.locked()==False`；标题含「安全验证」→ `exit=5` 且锁持久（新实例仍见）。

验证：`tests.test_access_douyin` **31 条**、weibo 92、zhihu 96、budget 47，全部 exit 0；日志 `tests.test_access_*.log`、清单 `RUN_MANIFEST.json`。


---

## 11) 第 4 轮返工（rev11）：detail 异常分支修正 + 锁 reason 预脱敏

1. **`run_detail` fetch 异常分支修正**（原为真 bug：误用 search 的 `safe_url`/`keyword`，命令与结算种类也写成 search，触发 `NameError`）
   - 现为：`_finish("detail", exit_code=EXIT_TRANSPORT, records_out=[], stop=adapter_exception:*, url=target)` → `_settle(..., "detail", EXIT_TRANSPORT, payload)`，落 `detail_result=unknown`、`exit=7`、`records=[]`。
   - 测试 `DetailExceptionTests`：**真实 CLI**（`main`）+ fake transport 抛异常 → 退出码 **7**、`records==[]`、平台事件含 `detail_result=unknown`；同路径叠加 `record_result` 抛错 → 退出码 **6**、`records==[]`、`stop=platform:result_write_failed:*`。
2. **搜索风险 reason 先脱敏再落锁**
   - `clean_reason = _scrub(reason, keyword)` 在 `batch.lock()` 与 `ledger.lock()` **之前**计算，本地锁、平台锁与 payload `stop` 全部使用脱敏值。
   - 测试 `RiskReasonScrubTests`：fake transport 返回 `offsite_redirect:<原始搜索URL>`（`locks=True` 路径），中英文关键词各一条；直接检查**两个账本的锁记录**与输出 JSON，原文与 `quote()` 编码零出现，且锁确实持久。

回归：`tests.test_access_douyin` **35 条**、weibo 92、zhihu 96、budget 47，全部 exit 0；日志 `tests.test_access_*.log`、清单 `RUN_MANIFEST.json`（UTC 2026-10-30T04:19Z）。
