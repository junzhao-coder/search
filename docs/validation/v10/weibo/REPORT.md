# V10-4 微博接入（离线批次）报告

> 任务 `task-d0f8c614abbc346b5f06749fcbe7e874`（rev4，计划 v10）。
> 执行窗口：2026-10-27 22:27–22:40 UTC+8。
> **本批零真实请求**：未向 weibo.com / m.weibo.cn / api.weibo.com / passport.weibo.com 发过任何请求；未打开任何浏览器窗口；未登录；未装依赖。

## 1. 复用了哪些既有模块（不是"参考"，是直接 import）

| 模块 | 复用方式 | 微博侧新增了什么 |
| --- | --- | --- |
| `transport.AuthenticatedBrowserTransport` | **直接使用**（单 loop `_get_loop`、单一递减 `_deadline/_remaining`、`asyncio.wait_for` 硬超时、三级探针、`browser.get`→`_wait_ready`→`get_content`） | 只提供 `SiteProfile`（链接形态/容器选择器/墙词/空词），未复制任何代码 |
| `transport.SiteProfile`（本批新增，约 40 行） | 新抽象，默认值 = `ZHIHU_SITE`，知乎行为零变化 | `WEIBO_SITE` 只是数据 |
| `budget` | **直接使用**：`open_budget/charge/charge_poll/reserve_records/lock/note/peek/read_ledger`，≤3 calls / ≤5 records / ≥15s / ≤300s | 无（仅把自动 batch 标签从 `zhihu-` 改为中性 `batch-`，因为账本由多适配器共用） |
| `records` | **直接使用**：`FIELDS/EXPORT_FIELDS/make_record/normalize_record/read_records/write_records/sanitize_url/strip_tags/meta_tags` | `SOURCE_RULES` 增加 `weibo:` 白名单；把知乎的锚点解析器**上移**为 `records.Links(pattern)` 供两个适配器共用 |
| `diagnostics` | **直接使用**：`sanitize` 白名单、`classify_href/count_href_shapes` | `SITES` 增加 `weibo`（detail/status/post/profile 形态 + weibo.cn/weibo.com 同源判定）、`ASSUMED_BY_SITE["weibo"]` |
| `browser.wait_for_login` | **直接使用**（五态、poll 独立配额、风险锁、`polls_for_window`） | 新增 `signed_in_js` / `wall_markers` 两个可选参数，微博传入自己的标记 |
| `zhihu._charge/_finish/_risk_or_error/_merge_diagnostics` | **直接 import**（编排层只有一份；风险策略必须一致） | 无 |
| `codes` | 直接使用全部退出码 | 无 |

> 结论：微博模块 730 行里，真正微博特有的只有 **URL 规则 + 三个解析器 + 标记词表 + CLI 装配**；传输/预算/记录/诊断/登录轮询全部是共享实现。

## 2. 六个子命令的真实离线 argv 与 exit

驱动脚本 `docs/validation/v10/weibo/offline_checks.py`，日志 `docs/validation/v10/weibo/logs/offline_checks.json`。
统一前缀：`D:\桌面\two\.venv\Scripts\python.exe -X utf8 -m tools.selection.access.weibo`，cwd `D:\桌面\two`。

| 子命令 | argv（省略前缀） | exit | 说明 |
| --- | --- | --- | --- |
| doctor | `--state-dir …\state_doctor --profile …\checks\profile doctor` | **0** | 本地只读；`network="none"`、`online="unverified"` |
| login | `--state-dir …\state_login --profile …\checks\profile login --timeout 5` | **7** | `browser_unavailable`（本 venv 无 nodriver）→ **在启动浏览器之前就返回**，未开窗、未联网 |
| search | `--state-dir …\state_search --mode offline search 学习计划模板 --limit 5` | **7** | `stop=network_disabled_offline_batch`（`RefusedTransport` 不建 socket） |
| detail | `--state-dir …\state_detail --mode offline detail https://m.weibo.cn/detail/4900000000000001` | **7** | 同上 |
| comments | `--state-dir …\state_comments --mode offline comments https://m.weibo.cn/detail/4900000000000001` | **7** | 同上 |
| export | `--state-dir …\state_export export --input …\fixtures\records.jsonl --output …\fixtures\export.jsonl` | **0** | 白名单导出；`dropped_keys=["cookies","nickname"]`、`url_query_stripped=1`、`evidence_rejected=0` |
| （预算读取） | `--state-dir …\state_search budget --ledger 5` | **0** | 账本 `batch-2cc0c992ba26`、`calls=1`、`locked=false` |

汇总：**7/7 场景 exit 与预期一致，驱动 exit 0**。

失败路径也**不是空成功**：`search/detail/comments` 在离线模式一律非零退出（7），未识别锚点时 `stop=unknown → exit 4`，profile URL 调 detail/comments 时 `stop=unsupported_content_url → exit 8`。

## 3. 测试：145 项全绿

| 套件 | 数量 | 结果 |
| --- | --- | --- |
| `tests.test_access_weibo`（新增） | **29** | OK |
| `tests.test_access_zhihu` | 96 | OK（回归） |
| `tests.test_access_budget` | 20 | OK（回归） |
| 合计 | **145** | **OK / rc=0** |

真实命令与时间：

```
cwd   = D:\桌面\two
argv  = D:\桌面\two\.venv\Scripts\python.exe -X utf8 -m unittest tests.test_access_budget tests.test_access_zhihu tests.test_access_weibo -q
UTC   = 2026-10-27T14:39:2xZ（本地 22:39）
exit  = 0    输出尾部：Ran 145 tests in 10.249s / OK
```

### 3.1 风险锁与预算的测试名 + 断言

| 测试 | 断言 |
| --- | --- |
| `SearchTests.test_wall_locks_the_batch` | `error="browser:risk:text:验证码"` → `exit=5`、`batch.locked=True`、`lock_source="search"`、`lock_reason` 含"验证码" |
| `SearchTests.test_locked_batch_refuses_the_next_search` | 已锁批次再次 `open_budget` 抛 `BudgetError(code="batch_locked")`——锁不可绕 |
| `DetailAndCommentsTests.test_detail_on_a_wall_page_locks` | 详情页命中墙词 → `exit=5`、`stop` 以 `risk:` 开头、批次被锁 |
| `SearchTests.test_search_charges_one_call_before_fetching` | 一次搜索后 `calls=1`、`records=2`（预扣发生在取数之前） |
| `SearchTests.test_budget_refusal_happens_before_the_transport_is_touched` | 调用额度已耗尽 → `exit=6`、`stop=budget:calls_exhausted`、**`transport.urls == []`**（预扣先于取数） |
| `LoginTests.test_signed_in_is_ok_without_spending_a_call` | 登录成功不吃数据预算（`calls=0`），只吃 poll 配额 |
| `LoginTests.test_timeout_and_poll_limit_are_different_nonzero_exits` | `timeout→11`、`poll_limit→12`，两者都是非零且不同 |
| `ReuseTests.test_diagnostics_skeleton_is_whitelisted_and_names_the_phase` | 诊断骨架只留白名单键（`nickname`/`cookies`/`SECRET` 全被丢弃），并保留 `phase` |
| `ReuseTests.test_transport_reports_navigate_phase_when_get_hangs` | `get` 挂死 → `error=browser:TimeoutError`、`diagnostics.phase="navigate"`、`state="unknown"`（**phase=navigate 与 phase=read 可区分**） |

其余：doctor 只读（2 项）、登录五态（5 项）、搜索 HTML/空页/未知锚点区分（3 项）、detail/comments 父子关系（5 项）、导出白名单（2 项）、复用与站点配置（7 项）。

## 4. RESEARCH.md 的关键结论（读到 vs 实测）

**读到（README/元数据原文，已记 commit 与许可）**

- `Xarrow/weibo-scraper`（MIT，commit `0a8cce7…`）："inspect mobile site which has it's own API"；`tweet_container_id='1076033637346297'` 形态；`get_weibo_profile/get_weibo_tweets/get_realtime_hotwords`。
- `Praeviso/crawl4weibo`（MIT，commit `5391055…`）：默认无需 cookie（移动 UA 初始化会话）；Playwright 取 cookie + 可选人工登录持久化会话（`browser_headless=False`、`login_timeout=180`）；**"432 保护" + 指数退避**；`User/Post/Comment` 模型与评论分页、长文展开。
- `lucasjinreal/weibo_terminater`（**无许可**，2019 后未推送，2318★）：仅概念层。
- `w4n9hu1/hot-hub-web`（MIT，已归档）、`goesByhc/cn-scraper-mcp`（MIT）：仅元数据，未读实现。

**实测：全部为空。** 我们**没有**安装、运行或访问上述任何项目，也**没有**访问微博——RESEARCH.md 每条都标了"我们的实测：无"。

**未获取（已如实标注）**：X（Twitter）讨论（无 agent-reach 技能、无 `reach` CLI、`web_search` 端点不可用）、各仓库的具体接口路径/选择器/参数（只读 README）、GitHub issues 检索（返回 198,848 条噪声，无可用结论）。

**对实现的直接影响**：选"真实浏览器 + 移动 UA/会话"为主路径（与 V10-3 已验收的登录方式同型），把 432/403/429 与墙词统一为持久锁，**不采用**指数退避重试（与"风险即锁、不重试"冲突）。

## 5. 微博是否需要登录（如实）

**未实测，无法回答。** V9 旧结论是"访客墙"，本批按红线没有访问微博，因此**既不能确认也不能否认**。已写入 limitations：如果 W4 实测发现微博必须登录才能读任何内容，本适配器会以 `stop=unknown`（不可识别锚点）或墙词锁批次的形式**失败而非假成功**，届时需要按真实页面修正 `WEIBO_SITE` 与解析器。

## 6. 边界与守卫

- 未写业务库/CSV/CONTRACT；未触发 triage/categories。
- guards 五哈希**不变**：`app.db e073f828`、`workflow 8ae79c58`、`CONTRACT 826c24cc`、`scores ab0c3546`、`sources 13679b60`。
- 微博 profile 目录（`docs/validation/v10/weibo/checks/profile`）为空目录，**不含任何凭据**，也不入仓库（仅本地空目录）。
- 未触碰 `docs/validation/v10/zhihu*` 四个已验收目录。
- 无残留浏览器进程。

## 7. 已知限制

1. **微博真实页面结构、登录方式、反爬策略全部未实测**；`WEIBO_SITE` 的链接形态、容器选择器、墙词/空词、`SIGNED_IN_JS` 标记**均为 assumed**，诊断里 `selectors_assumed` 明确写出。
2. 搜索 URL（`containerid=100103type=1&q=…`）、详情（`/detail/<mid>`）、评论（`/comments/hotflow?id=&mid=`）都是**假设**，来自公开文档的形态推断，未经真实响应验证。
3. `parse_comments_json` 的字段名（`data.data[].id/text/created_at/like_count`）是**假设**；真实字段可能不同。
4. 未做真实登录、未建 weibo profile、未验证会话复用。
5. 已知缺口：`url_identity` 对 `/<uid>/<bid>` 形态的 `native_id` 用 bid（非数字 mid），与 `/detail/<mid>` 的 mid 可能不是同一标识体系——真实环境需统一，本轮**未验证**。
6. 离线模式只能证明"命令装配正确、失败不伪装成功"，不能证明微博可读。
