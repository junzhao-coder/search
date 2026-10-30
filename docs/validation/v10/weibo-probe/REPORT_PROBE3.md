# V10-5 微博未登录探路（第 3 次，移动 UA，本批最后一次额度）

> 任务 `task-bc5a638c08c9ce79bd6ad444054d7255`（rev2，计划 v10，小目标 V10-5）。
> 阶段一（离线 UA + 测试）→ 阶段二（真机 1 次）。阶段一守卫满足后才执行阶段二。
> 阶段一时间：2026-10-27 23:25–23:27 UTC+8；阶段二：23:27:54–23:28:03（**15:27:54Z–15:28:03Z**，9 秒）。
> **恰好 1 次**真实微博请求（本批第 3 次、最后一次额度）；未重试、未换词、未换 mode、未装依赖、未代填、未读 cookie 值、未引导用户操作。

---

# 阶段一：移动 UA（离线）

## 1. 实现方式与理由

| 位置 | 改动 |
| --- | --- |
| `transport.SiteProfile` | 新增 `user_agent: str \| None = None`（None = 不干预 Chrome 默认 UA）+ `with_user_agent(ua)` 返回副本 |
| `transport._launch_kwargs(info)` | 集中生成 `uc.start` 参数；UA 非空时加 `browser_args=["--user-agent=<UA>"]`；`_ensure_browser` 是唯一调用点 |
| `weibo.MOBILE_UA` | `Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Mobile Safari/537.36` |
| `weibo.SITE` | `user_agent=MOBILE_UA` |
| `weibo` CLI | `search/detail/comments` 新增 `--user-agent`，覆盖时用 `SITE.with_user_agent(...)`，**不改模块默认** |
| `transport.ZHIHU_SITE` | **`user_agent=None`**（知乎零变化） |

**选 `--user-agent=` 启动开关而非 CDP `Network.setUserAgentOverride`**：①开关在浏览器启动即生效，**第一次请求**就带移动 UA——这正是"服务端据此决定渲染分支"的关键时机；CDP override 通常在首次导航后才设置，第一发仍是桌面 UA。②开关只加一个参数，CDP 方案要拿 tab + 两次 CDP + 失败回退，按 ponytail"一个字段、不重构"应当选小改动。③不引入新的 await 点，与"单 loop / 单 deadline"约束无交互。

## 2. 测试（全绿，守卫满足）

| 测试 | 断言 |
| --- | --- |
| `test_only_weibo_carries_a_mobile_user_agent` | weibo UA 非空且含 `Mobile`；**`ZHIHU_SITE.user_agent is None`** |
| `test_launch_kwargs_turn_the_ua_into_a_browser_switch` | 微博 kwargs 含 `--user-agent=<UA>`；知乎**不含** `browser_args` |
| `test_uc_start_actually_receives_the_mobile_ua` | stub `nodriver` + stub `available`（**不启真浏览器**）：`uc.start` 收到 UA、`headless=False`、profile 已 resolve、`close()` 调 `stop()` |
| `test_cli_override_copies_the_profile_instead_of_mutating_it` | `--user-agent UA-X` 生效且 `weibo.SITE.user_agent` 不变 |
| `test_no_override_keeps_the_site_default` | 无覆盖时 `built.site is weibo.SITE` |

```
argv = D:\桌面\two\.venv\Scripts\python.exe -X utf8 -m unittest tests.test_access_weibo.UaTests -q
cwd  = D:\桌面\two ;  UTC 2026-10-27T15:27:1xZ ; exit = 0   (Ran 5 tests … OK)

全量回归 argv = … -m unittest tests.test_access_budget tests.test_access_zhihu tests.test_access_weibo -q
exit = 0   Ran 163 tests in 12.852s … OK        （知乎 96 + 预算 20 + 微博 47；知乎不回归）

离线六入口 argv = … offline_checks.py
exit = 0   7/7 匹配（15:27:23Z→15:27:26Z）
```

清单：`docs/validation/v10/weibo-probe/PHASE1_UA.md`。**阶段一无任何失败，故进入阶段二。**

---

# 阶段二：真机（移动 UA，第 3 次也是最后一次额度）

## 3. 命令与窗口证据

| 项 | 值 |
| --- | --- |
| argv | `C:\Users\19183\.dsh\tools\x-collect\venv\Scripts\python.exe -X utf8 -m tools.selection.access.weibo --state-dir D:\桌面\two\docs\validation\v10\weibo-probe\state-probe3 --batch-id weibo-probe-3 --mode authenticated-browser --profile D:\桌面\two\docs\validation\v10\weibo-probe\profile_empty3 search 学习计划模板 --limit 5 --visible --timeout 60 --diagnostics-dir D:\桌面\two\docs\validation\v10\weibo-probe\diag3` |
| cwd / PYTHONPATH | `D:\桌面\two` / `D:\桌面\two` |
| started / finished | **15:27:54Z** / **15:28:03Z**（9 秒） |
| **exit** | **7**（`EXIT_TRANSPORT`） |
| **stop** | **`readiness_timeout`** |
| 180s 外部保护 | **未触发**（9 秒） |
| `wait_for` 硬超时 | **未触发**（`phase=read`，正常读完；`readiness_timeout` 是"页面始终不可读"的诚实信号，不是传输层超时） |

**窗口（按 `profile_empty3` 过滤，用户自己的 Chrome 不会误记）**：
```json
{"sampled_utc":"2026-10-27T15:27:56.216Z","pid":104392,"title":"新标签页 - Google Chrome",
 "handle":2162740,"visible":true,"responding":true,"rect":"10,10,1060,1009"}
```
Python PID 92840；Chrome PID 104392；窗口约 9 秒；**未要求用户做任何操作**。

## 4. 完整 stdout（1,703 B）

```json
{"batch": {"batch_id": "weibo-probe-3", "calls": 1, "calls_max": 3, "elapsed_s": 7.406,
 "locked": false, "records": 0, "seconds_max": 300.0, "state_dir": "...\\state-probe3"},
 "command": "search", "count": 0,
 "diagnostics": {"anchors_recognized": 0, "anchors_rejected": 0, "anchors_total": 0,
   "dom_anchor_count": 0, "elapsed_ms": 0,
   "final_url": "https://m.weibo.cn/search", "final_url_known": true,
   "href_shapes": {"detail": 0, "non_http": 0, "other": 0, "other_cross_origin": 0,
                   "other_same_origin": 0, "post": 0, "profile": 0,
                   "relative_other": 0, "status": 0},
   "html_bytes": 33824, "parse_state": "unknown", "phase": "read",
   "probe": {"anchorCount": 0, "contentish": 0, "emptyish": false, "level": 1,
             "readyState": "complete", "render_wait_exhausted": true,
             "render_wait_ms": 5250, "state": "unknown", "textLen": 0, "wall": null},
   "probe_elapsed_ms": {"1": 0, "2": 31, "3": 0}, "probe_level": 1,
   "ready_state": "complete", "render_wait_exhausted": true, "render_wait_ms": 5250,
   "requested_url": "https://m.weibo.cn/search", "state": "unknown",
   "web_state": "no_recognized_anchors"},
 "exit": 7, "ok": false, "parsed_structure": "html:unknown", "records": [],
 "stop": "readiness_timeout", "url": "https://m.weibo.cn/search"}
```
stderr：**空**。诊断骨架：`diag3/search-20261027T152802Z.json`（1,282 B，内容与上面 diagnostics 一致）。

## 5. 逐项观测（验收 §6 字段全覆盖）

| 字段 | 值 |
| --- | --- |
| requested_url | `https://m.weibo.cn/search`（`containerid` 被 `sanitize_url` 剥离） |
| **final_url / final_url_known** | **`https://m.weibo.cn/search` / `true`** ← 首次拿到落地地址 |
| state / web_state | `unknown` / `no_recognized_anchors` |
| **ready_state** | **`complete`** |
| **render_wait_ms / exhausted** | **5,250 / `true`** |
| probe_level / probe_elapsed_ms | **1** / `{1:0, 2:31, 3:0}` |
| **anchors_total / recognized / rejected** | **0 / 0 / 0** |
| **href_shapes** | 全 0（detail/status/post/profile/other*/relative/non_http 皆 0） |
| **dom_anchor_count** | **0** |
| **html_bytes** | **33,824** |
| phase / elapsed_ms | **`read`** / `0` |
| contentish / emptyish / textLen | **0** / `false` / **0** |
| **wall** | **`null`** |
| parse_state | `unknown` |

## 6. 四分支归类（明确）

| 分支 | 判定 | 依据 |
| --- | --- | --- |
| a) 未登录可读 | **不成立** | `anchors_recognized=0`、`count=0`，无 title/text |
| b) 需登录（墙/跳转） | **不成立** | `wall=null`；**`final_url` 明确停在 `https://m.weibo.cn/search`**，未被重定向到 passport/login |
| c) `phase=navigate` 超时无 DOM | **不成立** | `phase=read`、`readyState=complete`、HTML 33.8KB 已取回 |
| d) 落到非搜索页/错误页 | **部分排除** | 落地 URL **就是** `/search`，不是首页/错误页 → **路径层 URL 假设成立**（参数是否被接受无法从脱敏 URL 判断） |

**结论：四分支都不成立 —— 这是第五种形态：页面是 JS 空壳，内容始终没有渲染。** 硬证据：`readyState=complete` + 33.8KB HTML + `render_wait` 5.25 秒耗尽后 `dom_anchor_count=0`、`textLen=0`、`contentish=0`、`href_shapes` 全 0、无墙词。

**因此"微博未登录是否可读"仍然不可判定**（既没读到，也没遇到墙）。

## 7. 移动 UA 是否改变了结果（显式对比第 2 次）

| 指标 | 第 2 次（桌面 UA，无渲染等待） | 第 3 次（**移动 UA**，5s 渲染等待） | 变化 |
| --- | --- | --- | --- |
| html_bytes | 34,068 | 33,824 | **−244（−0.7%）** |
| anchors_total | **13** | **0** | **−13** |
| contentish | **11** | **0** | **−11** |
| textLen / emptyish | 0 / false | 0 / false | 不变 |
| dom_anchor_count | 未记录 | 0 | — |
| wall | null | null | **不变（都无墙）** |
| final_url | 未知 | `/search`（已知） | 新证据 |
| exit / stop | 4 / `unknown` | 7 / `readiness_timeout` | 信号更诚实 |
| records | 0 | 0 | **不变** |

**明确判断：移动 UA 没有让内容变得可读。** 页面体积几乎不变（−0.7%），但可识别结构**反而更少**（锚点 13→0、容器 11→0），5.25 秒渲染等待后 DOM 仍为空。**UA 不是杠杆**；同时两次都 `wall=null`、落地都在 `/search`。

## 8. 预算（真实）

```json
{"budget": {"batch_id": "weibo-probe-3", "calls": 1, "calls_max": 3, "locked": false,
  "lock_reason": null, "records": 0, "polls": 0, "state_dir": "...\\state-probe3"},
 "command": "budget", "exit": 0, "ok": true,
 "ledger": [
   {"at": 1793114882.504058, "kind": "search_result", "detail": "{\"count\": 0, \"exit\": 7}"},
   {"at": 1793114875.1136618, "kind": "charge",
    "detail": "{\"kind\": \"search\", \"detail\": \"https://m.weibo.cn/search?containerid=100103type%3D1%26q%3D…\"}"}]}
```
- 新批次消耗 **1/3**、`locked=false`、无 lock 记录。
- **微博本批累计 3 次真实额度已用尽**（第 1 次零请求、第 2 次真请求、第 3 次真请求）。
- `profile_empty3` 事后 41 个 Chrome 默认文件（未登录、无凭据，未入库）；**无残留 Chrome 进程**。

## 9. 收口建议（不再要预算）

1. **本批判定：不可判定。** 三次调用（含 1 次零请求）均未取得内容；UA 与渲染等待都试过，均无效。**不宣称可读，也不宣称被墙。**
2. **剩余三条假设（按可检验性排序）**：
   - **H1 内容接口需要登录态**：外壳先到、列表由 XHR 拉取并带 cookie → 若成立必须登录（也解释了"无墙但无内容"）。
   - **H2 反自动化**：缺 JS 生成的令牌（如 `_T_WM`/`XSRF-TOKEN`）导致 XHR 返回空/403，页面因此永远空壳。
   - **H3 `containerid` 参数形态不对**：落在 `/search` 但未进入结果态；真实入口可能还需 `luicode`/`lfid` 等参数（**注意：脱敏 URL 剥掉了 containerid，本轮无法直接核对**）。
3. **不需新额度的区分办法**（推荐先做）：
   - 用户用**日常 Chrome 手动**打开同一条 `m.weibo.cn/search?containerid=…` 链接，看是否出结果、是否要求登录 → 一次性区分 H1/H2/H3（人工观察，不算采集调用）；
   - 或走**人工导入**：把结果页 HTML/JSON 存盘，用已有 `export`/离线解析处理（零采集、零风控）。
4. **若仍要自动化**：唯一值得再试的变量是**登录态（H1）**，且必须接受"登录后仍可能空壳"；这需要新批次额度，属产品决策，本执行者不再申请。
