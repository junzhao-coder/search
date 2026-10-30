# V10-5 微博未登录探路（第 2 次，绝对路径）：页面能加载，但拿到 0 条可识别内容

> 任务 `task-ff2fc9076b3624b77cd7d464e74f8186`（rev2，计划 v10，小目标 V10-5）。
> 执行时间：2026-10-27 23:13:12–23:13:19 UTC+8（**15:13:12Z–15:13:19Z**，7 秒）。
> **恰好 1 次**真实微博请求；未重试、未换关键词、未换 mode、未改代码/测试/期望值、未装依赖、未代填、未读 cookie 值、未引导用户做任何操作。

## 1. 实际命令与窗口证据

| 项 | 值 |
| --- | --- |
| argv | `C:\Users\19183\.dsh\tools\x-collect\venv\Scripts\python.exe -X utf8 -m tools.selection.access.weibo --state-dir D:\桌面\two\docs\validation\v10\weibo-probe\state-probe2 --batch-id weibo-probe-2 --mode authenticated-browser --profile D:\桌面\two\docs\validation\v10\weibo-probe\profile_empty2 search 学习计划模板 --limit 5 --visible --timeout 60 --diagnostics-dir D:\桌面\two\docs\validation\v10\weibo-probe\diag2` |
| cwd / PYTHONPATH | `D:\桌面\two` / `D:\桌面\two` |
| started / finished | **2026-10-27T15:13:12Z** / **15:13:19Z** |
| **exit** | **4**（`EXIT_UNSUPPORTED`） |
| **stop** | **`unknown`** |
| count / records | **0 / 0** |
| 180s 外部保护 | **未触发**（7 秒结束） |
| `wait_for` 硬超时 | **未触发**（`phase=read`，正常读完） |
| 启动失败 | **无**（修复生效，`browser_start_failed` 未出现） |

**窗口可见性（客观证据，已过滤为本 profile）**：

```json
{"sampled_utc":"2026-10-27T15:13:15.739Z","pid":108204,"title":"新标签页 - Google Chrome",
 "handle":1969362,"visible":true,"responding":true,"rect":"10,10,1060,1009"}
```

- Python 进程 PID 133668；本 profile 的 Chrome 主进程 **PID 108204**，窗口标题「新标签页 - Google Chrome」，`IsWindowVisible=True`，handle 非零。
- 采样过滤条件：命令行含 `profile_empty2`——**用户自己的 Chrome 不可能被误记**（第 1 次那台的 pid 115716 未出现）。
- 窗口全程约 7 秒；**用户不需要做任何操作**，我也没有引导登录/扫码。

## 2. 完整 stdout（原文）

```json
{"batch": {"batch_id": "weibo-probe-2", "calls": 1, "calls_max": 3, "elapsed_s": 4.399,
 "last_call_at": 1793113993.800055, "lock_reason": null, "lock_source": null, "locked": false,
 "polls": 0, "polls_max": 120, "records": 0, "records_max": 5, "seconds_max": 300.0,
 "state_dir": "D:\\桌面\\two\\docs\\validation\\v10\\weibo-probe\\state-probe2"},
 "command": "search", "count": 0,
 "diagnostics": {"anchors_recognized": 0, "anchors_rejected": 13, "anchors_total": 13,
   "elapsed_ms": 0, "html_bytes": 34068, "parse_state": "unknown", "phase": "read",
   "probe": {"anchorCount": 0, "anchors_recognized": 0, "anchors_rejected": 0,
             "anchors_total": 0, "contentish": 11, "emptyish": false, "level": 2,
             "readyState": "complete", "sampled": 0, "state": "ready", "textLen": 0,
             "wall": null},
   "probe_elapsed_ms": {"1": 0, "2": 0, "3": 16}, "probe_level": 2,
   "requested_url": "https://m.weibo.cn/search",
   "selectors_assumed": ["result_container (assumed)",
     "candidate_links=/detail/<id>, /status/<id>, /<uid>/<bid> (assumed)",
     "empty_markers text (assumed)", "wall_markers text (assumed)"],
   "state": "no_recognized_anchors", "web_state": "no_recognized_anchors"},
 "exit": 4, "keyword": "学习计划模板", "ok": false, "parsed_structure": "html:unknown",
 "records": [], "stop": "unknown", "url": "https://m.weibo.cn/search"}
```

stderr：**空**（0 字节）。

## 3. 诊断骨架原文（`diag2/search-20261027T151318Z.json`）

```json
{
 "anchors_recognized": 0, "anchors_rejected": 13, "anchors_total": 13,
 "elapsed_ms": 0, "html_bytes": 34068, "parse_state": "unknown", "phase": "read",
 "probe": {"anchorCount": 0, "anchors_recognized": 0, "anchors_rejected": 0,
           "anchors_total": 0, "contentish": 11, "emptyish": false, "level": 2,
           "readyState": "complete", "sampled": 0, "state": "ready", "textLen": 0,
           "wall": null},
 "probe_elapsed_ms": {"1": 0, "2": 0, "3": 16}, "probe_level": 2,
 "requested_url": "https://m.weibo.cn/search",
 "selectors_assumed": ["result_container (assumed)",
   "candidate_links=/detail/<id>, /status/<id>, /<uid>/<bid> (assumed)",
   "empty_markers text (assumed)", "wall_markers text (assumed)"],
 "state": "no_recognized_anchors", "web_state": "no_recognized_anchors"
}
```

## 4. 逐项观测（验收 §3 字段）

| 字段 | 实际值 | 说明 |
| --- | --- | --- |
| **phase** | **`read`** | 导航完成并读到内容，**不是** navigate 超时 |
| **ready_state** | **`complete`** | 文档已加载完 |
| **probe_level** | **2** | L1 通过（但 0 锚点）→ L2 命中 `contentish=11` → 判为 ready，未再跑 L3 判定 |
| **probe_elapsed_ms** | **`{"1":0,"2":0,"3":16}`** | 毫秒级，无阻塞 |
| **anchors_total / recognized / rejected** | **13 / 0 / 13** | 来自 HTML 解析：13 个锚点，**没有一个**匹配假设的 `/detail/<id>`、`/status/<id>`、`/<uid>/<bid>` |
| probe 内部 anchors | **0 / 0 / 0** | DOM 里当时**没有** `a[href]`（HTML 是 34KB 外壳，链接是后补/内联的） |
| **href_shapes** | **未取得** | 当前 transport 未把形态直方图写进诊断（缺口，建议补） |
| **html_bytes** | **34,068** | 页面确实取到内容，不是空壳 0 字节 |
| **final_url / final_url_known** | **未记录（未知）** | transport 只在"最终 URL 读不到"时才写该键；正常路径没写，`run_search` 也未透出。**这是观测缺口** |
| **wall** | **`null`** | **没有任何墙词**（安全验证/访问异常/访问过于频繁/登录后查看…均未命中） |
| **parse_state** | **`unknown`** | 解析器进入但无可用形态 |
| web_state/state | `no_recognized_anchors` | 有锚点、但全部不被识别 |
| textLen | **0** | 探针读到 `body.innerText` 为空 |
| contentish | **11** | 11 个元素匹配 `card/feed/m-panel` 类名（说明有页面结构，但不是我们假设的结果容器） |
| emptyish | **false** | 页面**没有**说"没有找到/暂无内容" |

## 5. 四分支归类（明确，不模糊）

| 分支 | 判定 | 证据 |
| --- | --- | --- |
| **a) 未登录可读** | **不成立** | `anchors_recognized=0`，`count=0`，无 title/text 记录 |
| **b) 登录/访客墙** | **不成立** | `wall=null`（9 个墙词全未命中）；无 passport/login 跳转证据；页面 34KB 且 `contentish=11`、`emptyish=false`——**没有出现访客墙** |
| **c) phase=navigate 超时、无 DOM** | **不成立** | `phase=read`、`readyState=complete`、`html_bytes=34068`、两级探针都在毫秒级返回 |
| **d) 搜索 URL/参数假设不成立（落到非结果页）** | **最可能（主因）** | ①13 个锚点**全部**不匹配我们假设的三种内容形态；②DOM 探针 `anchorCount=0`、`textLen=0`，说明渲染后的页面几乎没有可见正文；③`contentish=11` 只匹配到泛化类名，不是结果容器；④`emptyish=false` → 页面并非"搜索无结果"，而是**不是结果页** |

**排序与保留**：
1. **主因：d（URL/参数假设不成立）**——证据强度最高：13/13 锚点不识别 + 正文为空 + 没有"无结果"文案。
2. **次因（不能排除）：SPA 未渲染**——`probe.anchorCount=0`、`textLen=0` 与 34KB HTML 并存，最自然的解释是：探针读到的 DOM 还是外壳，结果由 JS 异步注入；而 HTML 里的 13 个链接是页面骨架链接（导航/登录/下载 App 之类），因此形态不匹配。
3. **明确排除 b**：**本次没有任何未登录访客墙的证据**。这一点与 V9 旧结论（访客墙）**不一致**，应视为"旧结论未被本次观测复现"，但也不能反证需要登录。

**所以"是否需要扫码登录"的判断：本次证据不支持"必须登录"这一结论**——页面能加载 34KB、无墙词；真正的阻断在**URL/渲染/解析**这一层，而不是登录态。

## 6. 预算（真实）

```json
{"budget": {"batch_id": "weibo-probe-2", "calls": 1, "calls_max": 3, "locked": false,
  "lock_reason": null, "lock_source": null, "records": 0, "polls": 0,
  "state_dir": "...\\state-probe2"},
 "command": "budget", "exit": 0, "ok": true,
 "ledger": [
   {"at": 1793113998.180797, "kind": "search_result", "detail": "{\"count\": 0, \"exit\": 4}"},
   {"at": 1793113993.800055, "kind": "charge",
    "detail": "{\"kind\": \"search\", \"detail\": \"https://m.weibo.cn/search?containerid=100103type%3D1%26q%3D…\", \"batch_id\": \"weibo-probe-2\"}"}]}
```

- 新批次消耗 **1/3**；`locked=false`、无 lock 记录（未命中风险，符合"无墙"观测）。
- ledger 两条：`charge` + `search_result{count:0, exit:4}`——**请求确实发出并完成了读取**（与第 1 次"零请求"不同）。
- `profile_empty2` 执行后含 **41 个条目**（Chrome 自建默认文件，**未登录、未填任何凭据**）；目录在 `docs/` 下，**未提交入库**（本批无 git 提交）。无残留 Chrome 进程。

## 7. P5 下一步建议

**先补观测能力，再决定是否登录。** 理由：本次已证明"页面能取到、无访客墙"，但三个关键证据缺失，导致 d 与 SPA 两种解释无法区分。

1. **记录 final_url**（1 处小改）：transport 在 `phase=read` 正常路径也应写入 `final_url/final_url_known`，否则永远不知道"落到了哪个页面"，分支 d 只能靠链接形态间接推断。
2. **落一份脱敏 HTML 快照**（新能力）：把 13 个锚点的**形态**（而不是 URL）写进诊断，才能判断是"骨架链接"还是"异形结果链接"。当前 `href_shapes` 键存在但从未被填充。
3. **给 SPA 留渲染时间**：现在 L1 立即读，`anchorCount=0/textLen=0`。可先等 `readyState=complete` 后再等 1–2 秒或等 `a[href]` 数量 >0（有界）。
4. **人工确认搜索 URL 形态**：`m.weibo.cn/search?containerid=100103type%3D1%26q%3D<kw>` 是假设；也可用 `m.weibo.cn` 首页搜索入口观察真实跳转（需人工/MinIO 侧确认，或在下一次允许的真实访问里记录 final_url 后判断）。
5. **暂不扫码登录**：本次无墙证据，登录未必是瓶颈；先把 URL 与渲染两步做实，再决定是否需要登录态（若届时出现 `/login`、`passport` 跳转或墙词，再走登录）。

## 8. 声明

- **只执行 1 次**真实微博请求（第 2 次尝试，新批次 `weibo-probe-2`）；**未重试、未换关键词、未换 mode**、未改代码/测试/期望值。
- **全程绝对路径**（验收要求）：`--state-dir D:\桌面\two\…\state-probe2`、`--profile D:\桌面\two\…\profile_empty2`、`--diagnostics-dir D:\桌面\two\…\diag2`。
- 未装依赖、未代填凭据、未读取/输出 cookie 值、未访问微博以外域、未写业务库/CSV/CONTRACT、profile 未入仓库。
- 未要求用户做任何操作（窗口仅存在约 7 秒，未引导登录）。
