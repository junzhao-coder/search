# V10-3 authenticated-browser 真实搜索：第 1 次尝试（挂死，未完成）

> 任务 `task-d63fc0163be235f6a76b48e43378183c`（rev2，计划 v10）。
> 执行时间 2026-10-27 16:53:34–17:37:39 UTC+8（08:53:34–09:37:39Z）。
> **只执行 1 次真实调用**；未重试、未换关键词、未换 mode、未改代码/测试/期望值、未装依赖、未代填、未读 cookie 值。

## 1. 实际命令

| 项 | 值 |
| --- | --- |
| argv | `C:\Users\19183\.dsh\tools\x-collect\venv\Scripts\python.exe -m tools.selection.access.zhihu --state-dir docs\validation\v10\zhihu\runtime_live2 --batch-id zhihu-live-2 --mode authenticated-browser --profile C:\Users\19183\.dsh\tools\zhihu-collect\profile search 学习计划模板 --limit 5` |
| cwd / PYTHONPATH | `D:\桌面\two` / `D:\桌面\two` |
| started_utc | **2026-10-27T08:53:34Z** |
| 结束 | **09:37:39Z**（约 44 分钟，人工停止） |
| **exit** | **-1**（被强制停止；非正常返回） |
| stdout / stderr | **均为空（0 字节）** |
| 原件 | `docs/validation/v10/zhihu/live_search_2.out.txt`（0B）、`live_search_2.err.txt`（0B） |

## 2. 预算消耗（已扣费，未锁）

只读查询 `runtime_live2/budget.sqlite3`（脚本 `_inspect_budget.py`）：

```
tables ['budget','ledger','sqlite_sequence','batches']
budget {"batch_id":"zhihu-live-2","calls":1,"records":0,"locked":0,
        "lock_reason":null,"lock_source":null,"polls":0}
ledger_count 1
ledger charge {"kind":"search","detail":"https://www.zhihu.com/search?type=content&q=...","batch_id":"zhihu-live-2"}
```

- **calls=1（3 次预算已用 1 次）**，有 1 条 `charge`；`locked=0`（不是风控锁，是挂死）。
- 未产生 `lock` 记录 → 说明请求已发出但从未拿到响应/判定。

## 3. 现象与根因（只读定位，未改代码）

| 证据 | 内容 |
| --- | --- |
| 进程 | python PID 117372（父 109240）、子 128056；Chrome 主进程 85216 + 7 个渲染/工具进程，持续存在 44 分钟 |
| 窗口 | 8 个 Chrome 进程 `MainWindowTitle` 全为空、`MainWindowHandle=0`（headless 模式，符合 `AuthenticatedBrowserTransport(headless=True)` 默认） |
| 输出 | stdout/stderr 全程 0 字节，无任何 JSON |
| 代码 | `transport.py:121-139 _ensure_browser()` 用 **`asyncio.new_event_loop().run_until_complete(_start())`（事件循环 A）** 启动 nodriver 浏览器；`transport.py:177-191 _navigate()` 又用 **另一个 `asyncio.new_event_loop().run_until_complete(_run())`（事件循环 B）** 去 `await browser.get(url)` |

- **根因（高置信）**：nodriver 的 Browser/连接对象绑定在创建它的事件循环上；跨事件循环 await 同一连接会永久挂起（既无异常也无返回）。这与上一轮登录修复中 `main_tab` 的问题同源：**同一浏览器对象必须跑在同一个事件循环里**。
- 因此：`calls=1` 已扣、请求可能已发出，但**从未拿到 HTML/records**；`records=0`、无 `stop`、无 `parsed_structure`。

## 4. 结论

- 本次 authenticated-browser 搜索**未成功**：挂死 44 分钟、无输出、exit=-1（人工停止），未取得任何记录。
- 这不是 403/429/登录墙（`locked=0`、无 lock 记录），而是**产品代码的事件循环缺陷**（跨 loop 使用同一 nodriver 浏览器）。
- 按任务约束“失败即止、不重试、不换关键词、不换 mode”，已停止进程（python 117372/128056 + zhihu-profile Chrome 全部终止），**未重跑**。
- 预算：`runtime_live2` 已用 1/3，未锁；若后续修好可继续用剩余 2 次，但需另派任务。

## 5. 建议（交回原执行者，不在本任务改）

1. 让 `AuthenticatedBrowserTransport` 的启动与导航**共用同一个事件循环**（例如在 `_ensure_browser` 里保存 loop，`_navigate` 复用 `self._loop.run_until_complete`；或整个 transport 改为 async 由上层 `asyncio.run` 驱动）。
2. 给 `_navigate` 增加**硬超时**（如 `asyncio.wait_for(browser.get(url), timeout)`），避免再次无限挂起。
3. 修复后由新任务重跑 1 次真实搜索（`runtime_live2` 剩余 2 次预算）。

## 6. 声明

- **只执行了 1 次真实调用**；未重试、未换关键词、未换 mode、未改代码/测试/期望值。
- 未装依赖、未代填凭据、未读取/输出 cookie 值、未访问知乎以外域、未写业务库/CSV/CONTRACT。
- 进程已停止；`profile` 未入仓库；无残留 zhihu-profile Chrome/python 进程。
