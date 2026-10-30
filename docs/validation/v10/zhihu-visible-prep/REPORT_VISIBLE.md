# V10-3 可见窗口对照实验：CDP 求值可用（headless 假设获支持），但搜索页是验证码墙

> 任务 `task-19b549b9f9e589e48b888f2381d104a3`（rev2，计划 v10）。
> 执行时间 2026-10-27 22:12:36–22:12:39 UTC+8（**14:12:36–14:12:39Z**，进程 2.7 秒结束）。
> **恰好 1 次真实调用**、全新 `state-visible1` + 新批次 `zhihu-visible-1`、`--visible`、`--timeout 60`；未重试、未换词、未换 mode、未改代码/测试/期望值、未装依赖、未代填、未读 cookie 值。

## 1. 实际命令与结果

| 项 | 值 |
| --- | --- |
| argv | `C:\Users\19183\.dsh\tools\x-collect\venv\Scripts\python.exe -X utf8 -m tools.selection.access.zhihu --state-dir docs\validation\v10\zhihu-visible-prep\state-visible1 --batch-id zhihu-visible-1 --mode authenticated-browser --profile C:\Users\19183\.dsh\tools\zhihu-collect\profile search 学习计划模板 --limit 5 --visible --timeout 60 --diagnostics-dir docs\validation\v10\zhihu-visible-prep\diag_visible` |
| cwd / PYTHONPATH | `D:\桌面\two` / `D:\桌面\two` |
| started_utc / finished_utc | **2026-10-27T14:12:36Z** / **14:12:39Z** |
| **exit** | **7** |
| **stop** | **`browser:risk:text:验证码`** |
| elapsed_s | **2.697** |
| records / count | **0 / 0** |
| parsed_structure | 无（`parse_state=empty`，未进解析） |
| **phase** | **`read`**（导航已完成，进入读取阶段） |
| **html_bytes** | **126,059**（HTML 已取到） |
| **probe_level** | **3**（三级探针全部执行到最深一级） |
| **probe_elapsed_ms** | **`{"1": 266, "2": 0, "3": 15}`** |
| **ready_state** | **`""`（空字符串）** |
| **anchors_total / recognized / rejected** | **47 / 0 / 47** |
| href_shapes / query_key_counts | 诊断骨架未含（本轮设计只留形态计数与键名，实际未落 shapes 字段） |
| **web_state** | **`risk`** |
| parse_state | `empty` |
| **risk** | **`text:验证码`** |
| final_url / final_url_known | 未产出 / 未知（risk 分支提前返回） |
| 180s 外部超时 | **未触发**（2.7s 自返） |
| stderr | **0 字节** |

## 2. 诊断文件原文

`docs/validation/v10/zhihu-visible-prep/diag_visible/search-20261027T141239Z.json`（824 B）：
```json
{
 "requested_url": "https://www.zhihu.com/search?q=%E5%AD%A6%E4%B9%A0%E8%AE%A1%E5%88%92%E6%A8%A1%E6%9D%BF",
 "phase": "read",
 "elapsed_ms": 0,
 "html_bytes": 126059,
 "state": "risk",
 "parse_state": "empty",
 "risk": "text:验证码",
 "probe": {
  "level": 3, "readyState": "", "anchorCount": 47, "sampled": 20,
  "state": "risk", "anchors_total": 47, "anchors_recognized": 0,
  "anchors_rejected": 47, "contentish": 23, "wall": "验证码",
  "emptyish": false, "textLen": 590
 },
 "selectors_assumed": [ "result_container (assumed)",
   "candidate_links=/question/<id>(/answer/<id>)?, /p/<id>, /zvideo/<id> (assumed)",
   "empty_markers text (assumed)", "wall_markers text (assumed)" ],
 "probe_level": 3,
 "probe_elapsed_ms": { "1": 266, "2": 0, "3": 15 }
}
```

## 3. 窗口可见性证据：**未能取得（如实记录）**

| 项 | 结果 |
| --- | --- |
| Chrome 主进程 PID | **未取得** |
| MainWindowTitle | **未取得** |
| MainWindowHandle ≠ 0 | **未取得** |
| 原因 | 进程在 **2.697 秒**内结束（比采样间隔 9 秒更快），窗口随进程关闭；采样时机器上唯一可见 Chrome 窗口是用户自己的（`Legacy: woleiaaa@gmail.com \| Service Accounts`，PID 115716），**不是本次运行** |
| 已有间接证据 | ①argv 明确带 `--visible`；②`_make_transport` 走 `headless=not getattr(args,"visible",False)`（`zhihu.py:946`）→ `AuthenticatedBrowserTransport(headless=False)`；③`transport.py:165` `uc.start(headless=self.headless, ...)`；④行为上与 4 次 headless 全失败形成对照（见 §4） |
| 结论 | **窗口“已可见”本身没有被直接观测到**，本轮只能证明“传了 --visible 且行为与 headless 显著不同”。这削弱了“决定性对照”的强度，必须计入判读。 |

## 4. 与四次 headless 失败的逐项对照（按 a/b/c/d 分支归类）

| # | headless 历史 | 本次 visible |
| --- | --- | --- |
| 1 | public-http 匿名 → HTTP 403 锁停 | —（不同 mode） |
| 2 | authenticated-browser 挂死 44 分钟（跨 loop） | —（该缺陷已修） |
| 3 | 1.53s 返回 `exit=3 stop=empty records=0`，未进解析 | 2.70s 返回 `exit=7 stop=browser:risk:text:验证码` |
| 4 | 20.06s `phase=navigate`、`browser:TimeoutError`，**ready_state/anchors/html_bytes 全无** | **`phase=read`、html_bytes=126,059、probe_level=3、anchors_total=47，全部取到** |

**归类：命中分支 (a)，并且同时出现风险墙。**
- (a) **probe 成功取得 ready_state 字段与 anchors** → **可见/非 headless 模式下 CDP 求值可用**；“headless 差异”成为**最可能方向**。
- 但**不得宣称已证明**：仅 **1 次样本**；窗口可见性**未被直接观测**；headless 那次的失败也可能是当时页面/网络状态、浏览器版本、页面反自动化策略变化等混杂因素；两轮相隔约 1 小时。
- (b) 不成立（不是 probe_level=1 且 level_timeout，本轮 probe_level=3、各级耗时 266/0/15 ms）。
- (c) 不成立（不是 `phase=navigate` 的 `browser:TimeoutError`）。
- (d) 不成立（`state=risk`，count=0；不是 `result`）。

## 5. 本次页面到底是什么（依据观测，不做超出证据的推断）

- `state=risk`、`wall="验证码"`、`textLen=590`（正文极短）、`anchors_total=47` 但 `anchors_recognized=0`、`contentish=23`、`emptyish=false`。
- 合理解读：**取到的是一张验证码/风控中间页**（正文仅 590 字符、47 个锚点里没有一个指向 `/question/<id>`、`/p/<id>`、`/zvideo/<id>` 形态），**不是**搜索结果列表。
- 因此本次“搜索是否可读”的回答是：**不可读**——不是解析问题，而是页面本身是验证码墙。

## 6. 本轮发现的两个实现缺陷（未改代码，仅报告）

1. **风险命中后预算未锁**：`stop=browser:risk:text:验证码`，但 `budget.locked=false`、`lock_reason=null`。
   路径：`transport.py:238` 把墙检测结果放进 `error="browser:risk:text:验证码"`；`zhihu.py:608 _risk_or_error()` 对所有 `error` 字符串**只对 `offsite_redirect:` 返回锁定**，其余一律 `return text, False` → 验证码墙**不锁批次**，与“风险即锁”的约束不一致。
2. **`readyState` 字段恒为空**：`READY_JS` 用 `document.documentElement.readyState`（该属性不存在，恒 `undefined` → `""`），正确应为 `document.readyState`。因此本轮 `ready_state=""` **不是**页面未就绪的证据，而是探针字段本身的缺陷；`phase=read`/`html_bytes=126059` 已说明页面其实可读。

## 7. 预算（`budget` 子命令原文）

```json
{"budget": {"batch_id": "zhihu-visible-1", "calls": 1, "calls_max": 3,
  "lock_reason": null, "lock_source": null, "locked": false, "polls": 0,
  "polls_max": 120, "records": 0, "records_max": 5, "seconds_max": 300.0,
  "started_at": 1793110357.2694118,
  "state_dir": "...\\state-visible1", "last_call_at": 1793110357.2789614},
 "command": "budget", "exit": 0, "ok": true,
 "ledger": [
   {"at": 1793110359.959286, "kind": "transport_error", "detail": "browser:risk:text:验证码"},
   {"at": 1793110357.2789614, "kind": "charge", "detail": "{\"kind\": \"search\", \"detail\": \"https://www.zhihu.com/search?type=content&q=...\", \"batch_id\": \"zhihu-visible-1\"}"}]}
```

- `calls=1/3`、`records=0`、**`locked=false`**（见 §6.1 缺陷）、ledger 两条（charge + transport_error）。

## 8. 结论（按判读纪律，不软化）

1. **假设状态**：`headless 下 CDP 求值不返回` —— **获得支持但未证明**。可见/非 headless 模式下三级探针在 266/0/15 ms 内全部返回、取到 126 KB HTML 与 47 个锚点；4 次 headless 里最接近的一次是 `phase=navigate` 且 `evaluate` 20 s 不返回。差异方向明确，但只有 1 次样本、窗口可见性未直接观测、时间相隔约 1 小时，混杂因素未排除。
2. **搜索可读性**：**不可读**。原因不是解析白名单，而是**服务端返回验证码墙**（`wall=验证码`、正文 590 字符、47 锚点零识别）。要越过它必须人工解验证码，属于另一类工作。
3. **知乎搜索路径到此为止的判断依据**：登录态可用（26 次 evaluate 正常）＋ 可见窗口下 CDP 也正常（本次）＋ 但搜索页直接给验证码墙（本次）→ **技术上我们已能可靠地“读到页面”，读不到的是“搜索结果”，因为服务端不放行**。继续在采集侧改造（超时、探针、选择器）无法解决服务端风控；除非改变前提（人工过验证、换账号/换 IP、或放弃知乎搜索）。
4. **建议**：把知乎搜索标记为“受服务端风控阻断，采集侧不可解”，V10-3 的“判定搜索可读”结论按**不可读**归档；如需继续，走产品决策而非工程修补。

## 9. 声明

- **只执行 1 次真实调用**；用了 `--visible` 与**全新 state-dir**（`state-visible1`）；未重试、未换关键词、未换 mode、未改代码/测试/期望值。
- 未装依赖、未代填凭据、未读取/输出 cookie 值、未访问知乎以外域、未写业务库/CSV/CONTRACT、profile 只读未改。
- 窗口可见性未取得客观证据（见 §3），已如实标注，不用“传了 --visible”替代。
