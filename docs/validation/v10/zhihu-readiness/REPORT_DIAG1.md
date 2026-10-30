# V10-3 带诊断真实搜索：wait_for 硬超时在 navigate 阶段触发（20s），未取得页面状态

> 任务 `task-722c2745a65fd926c2476c3021632665`（rev2，计划 v10）。
> 执行时间 2026-10-27 21:23:51–21:24:13 UTC+8（13:23:51–13:24:13Z）。
> **恰好 1 次真实调用**、全新 state-dir `runtime_diag1` + 新批次 `zhihu-diag-1`；headless 后台、无可见窗口；未重试、未换词、未换 mode、未改代码/测试/期望值、未装依赖、未代填、未读 cookie 值。

## 1. 实际命令与结果

| 项 | 值 |
| --- | --- |
| argv | `C:\Users\19183\.dsh\tools\x-collect\venv\Scripts\python.exe -X utf8 -m tools.selection.access.zhihu --state-dir docs\validation\v10\zhihu-readiness\runtime_diag1 --batch-id zhihu-diag-1 --mode authenticated-browser --profile C:\Users\19183\.dsh\tools\zhihu-collect\profile search 学习计划模板 --limit 5 --diagnostics-dir docs\validation\v10\zhihu-readiness\diag_real` |
| cwd / PYTHONPATH | `D:\桌面\two` / `D:\桌面\two` |
| started_utc / finished_utc | **2026-10-27T13:23:51Z** / **13:24:13Z** |
| **exit** | **7** |
| **stop** | **`browser:TimeoutError`** |
| records / count | **0 / 0** |
| parsed_structure | 无（未进入解析） |
| risk_reason | 无（`locked=0`、`lock_reason=null` → **风险锁未命中**） |
| final_url / final_url_known | **无 / 未知**（导航未完成） |
| web_state | `unknown` |
| parse_state | `empty` |
| ready_state | **未取得**（见 §3） |
| anchors 计数（total/recognized/rejected） | **未取得**（见 §3） |
| href_shapes / query_key_counts | **未取得**（见 §3） |
| html_bytes | 未取得 |
| elapsed | batch 内 `elapsed_s=20.059`（≈ transport 的 20s 超时） |
| stderr | 见 §5（一条 RuntimeWarning） |

stdout 原文（`docs/validation/v10/zhihu-readiness/diag_real_search.out.txt`）：
```json
{"batch":{"batch_id":"zhihu-diag-1","calls":1,"calls_max":3,"elapsed_s":20.059,
 "lock_reason":null,"lock_source":null,"locked":false,"polls":0,"polls_max":120,
 "records":0,"records_max":5,"seconds_max":300.0,
 "state_dir":"...\\runtime_diag1"},
 "command":"search","count":0,
 "diagnostics":{"error":"browser:TimeoutError","parse_state":"empty","phase":"navigate",
   "requested_url":"https://www.zhihu.com/search?q=%E5%AD%A6%E4%B9%A0%E8%AE%A1%E5%88%92%E6%A8%A1%E6%9D%BF",
   "selectors_assumed":["result_container (assumed)",
     "candidate_links=/question/<id>(/answer/<id>)?, /p/<id>, /zvideo/<id> (assumed)",
     "empty_markers text (assumed)","wall_markers text (assumed)"],
   "state":"unknown"},
 "exit":7,"keyword":"学习计划模板","ok":false,"records":[],
 "stop":"browser:TimeoutError",
 "url":"https://www.zhihu.com/search?q=%E5%AD%A6%E4%B9%A0%E8%AE%A1%E5%88%92%E6%A8%A1%E6%9D%BF"}
```

## 2. 诊断文件原文（`--diagnostics-dir` 产出）

`docs/validation/v10/zhihu-readiness/diag_real/search-20261027T132413Z.json`：
```json
{
  "requested_url": "https://www.zhihu.com/search?q=%E5%AD%A6%E4%B9%A0%E8%AE%A1%E5%88%92%E6%A8%A1%E6%9D%BF",
  "phase": "navigate",
  "state": "unknown",
  "parse_state": "empty",
  "selectors_assumed": [
    "result_container (assumed)",
    "candidate_links=/question/<id>(/answer/<id>)?, /p/<id>, /zvideo/<id> (assumed)",
    "empty_markers text (assumed)",
    "wall_markers text (assumed)"
  ],
  "error": "browser:TimeoutError"
}
```

## 3. 逐项真实观测

| 观测项 | 实际值 |
| --- | --- |
| ready_state | **未取得** |
| anchors_total / recognized / rejected | **未取得**（三者均无） |
| href_shapes 分布 | **未取得** |
| query_key_counts | **未取得** |
| final_url 是否已知 | **否**（`final_url_known` 未产出；诊断里 state=unknown） |
| web_state | `unknown` |
| parse_state | `empty` |
| risk 命中 | **否**（`locked=0`、`lock_reason=null`、诊断无 wall 标记） |
| html_bytes | 未取得 |
| phase | **`navigate`** |
| 诊断文件是否落盘 | **是**（`diag_real/search-20261027T132413Z.json`，433 B） |

## 4. 0 记录的原因区分（按验收要求）

**结论：不是“结果页确实为空”，而是“仍未就绪 / 导航在读取页面状态阶段阻塞”。** 证据：

1. 诊断 `phase=navigate`、`state=unknown`——失败发生在**导航/就绪等待**阶段，**未进入** `parse_search_html`；因此本轮根本没有“结果页内容可解析”这一前提。
2. `parse_state=empty` 是**默认值**（解析函数未被调用），不是“解析后为空”的观测。
3. 三个锚点计数、href 形态、query 键、ready_state、html_bytes **全部缺失**，说明 `_read_state` 的第一次 `await tab.evaluate(READY_JS)` 未返回 → 页面状态**从未被读到**。
4. `_wait_ready` 的循环体先 `_read_state(tab)` 再判断，因此**没有 probe 就没有 anchors 统计**；`html:links` 这类标签本轮不成立（与上一轮 `LIVE_SEARCH_4` 不同）。
5. 与上一轮差异：上一轮 1.53s 返回 `stop=empty`（说明 `evaluate` 当时能返回）；本轮在同一条路径上 20s 超时 → **页面响应存在波动**，本次是更靠前的阻塞点。

## 5. 超时与 stderr（明确区分）

| 项 | 结果 |
| --- | --- |
| **180 秒外部超时（执行侧）** | **未触发**（命令 21.3s 自行返回，远小于 180s） |
| **`asyncio.wait_for` 硬超时（transport 内）** | **已触发**（`stop=browser:TimeoutError`，elapsed 20.059s ≈ transport timeout 20s）——这是该保护第一次在真实调用中被触发并留下证据 |
| stderr | `transport.py:336: RuntimeWarning: coroutine 'Tab.get_content' was never awaited`（取消 `wait_for` 时的收尾告警，指向 `get_content` 未完成即被取消） |

## 6. 离线对照（不访问任何站点，仅 data: URL）

为排除“对象/接口用错”，用 `data:text/html,...` 做了**离线**检查（不访问知乎、不访问任何站点）：

```
type(browser.get(...)) = Tab
has evaluate: True ; has get_content: True
evaluate ok: None
get_content ok, len: 59
probe: {"rs":"complete","n":1}
```

- 结论：`browser.get()` 在本环境返回的**确实是 Tab**，`evaluate`/`get_content` 均可用；本次超时**不是**“把假对象当真对象用”的旧型错误。
- 剩下的解释指向**知乎真实搜索页让 `Runtime.evaluate` 迟迟不返回**（反自动化/长任务阻塞 CDP 求值），需另派任务验证（例如把 probe 换成更轻的表达式、延长 timeout、或改用 `get_content` 先取 HTML 再离线解析）。

## 7. 预算（只读）

```
budget {"batch_id":"zhihu-diag-1","calls":1,"records":0,"locked":0,"lock_reason":null,"lock_source":null}
ledger 1) charge        {"kind":"search","detail":"https://www.zhihu.com/search?type=content&q=..."}
       2) transport_error  "browser:TimeoutError"
```
- 新批次消耗 **1/3**，`locked=0`（风险锁未命中），无 lock 记录；剩余 2 次（**同 state-dir 的 300s 窗口会过期**）。

## 8. 结论

- ✅ 本轮**首次取得真实诊断证据**：wait_for 硬超时在 `phase=navigate` 触发（20s），诊断文件落盘，明确了卡点位置。
- ✅ 0 记录**不是**“结果页为空”，而是**页面状态从未被读到**（无 ready_state/anchors/html_bytes）。
- ✅ 硬超时保护在真实调用中**被触发并留证**（此前两轮均未触发）。
- ❓ **“登录后知乎搜索是否可读”仍未判定**：原因收敛为“真实搜索页阻塞 CDP 求值 / 页面未就绪”，而非解析白名单问题；本轮仍无 anchors/形态数据，无法判断是否存在异形链接。
- 未采集任何帖子正文，未改产品代码。

## 9. 声明

- **只执行 1 次真实调用**、用的是**全新 state-dir**（`runtime_diag1`）+ 新批次（`zhihu-diag-1`）；未重试、未换关键词、未换 mode、未改代码/测试/期望值。
- headless 后台运行，无可见窗口；profile 只读未改。
- 未装依赖、未代填凭据、未读取/输出 cookie 值、未写业务库/CSV/CONTRACT。
