# V10-3 修复报告：authenticated-browser 跨事件循环挂死 + 无超时

> 任务 `task-d63fc0163be235f6a76b48e43378183c`（rev5，计划 v10）。
> 执行时间 2026-10-27 17:39–17:42 UTC+8。
> **本轮只改代码与测试，未真跑搜索**；未装依赖、未代填、未读 cookie 值、未改期望语义。

## 1. 缺陷（上一轮已定位，本轮修复）

| # | 缺陷 | 证据 |
| --- | --- | --- |
| 1 | **跨事件循环 await** | `_ensure_browser()` 在 loop A（`asyncio.new_event_loop().run_until_complete(_start())`）创建 nodriver 连接；`_navigate()` 在**新建 loop B** 里 `await browser.get(url)`。nodriver 的 CDP 连接绑定创建它的 loop，跨 loop await **不抛异常、永久挂起** |
| 2 | **无硬超时** | `_navigate` 里 `await asyncio.sleep(min(timeout, 5.0))` 只是等渲染，没有 `asyncio.wait_for` 包住 `get`/`get_content`，挂死无法自愈 |
| 现象 | 44 分钟无输出、stdout/stderr 均 0 字节、exit=-1（人工停止）；`calls=1`、`locked=0`、无 lock 记录（非风控） |

## 2. 修复（`tools/selection/access/transport.py`）

### 2.1 单 loop（方案：transport 自持 `self._loop`，调用方保持同步）

| 行 | 改动 |
| --- | --- |
| `:19` | 新增 `import asyncio` |
| `:108-122` | `__init__` 新增 `self._loop = None` |
| `:124-129`（新增） | `_get_loop()`：首次创建 `asyncio.new_event_loop()`，之后复用；已关闭则重建 |
| `:131-146` | `_ensure_browser()` 改为 `self._get_loop().run_until_complete(_start())`——**启动用 transport 自己的 loop** |
| `:148-160` | `close()` 关闭浏览器后**同时关闭 `self._loop`** 并置 None，避免 loop 泄漏 |
| `:168-192` | `fetch()` 调 `_navigate(..., loop=self._get_loop())`——**导航复用同一个 loop**；新增 `except TimeoutError` 分支返回 `{"error":"browser:TimeoutError"}` |

- 选这个方案而不是把 `fetch` 改 async：`run_search/run_detail/run_comments` 与 CLI 都是同步调用，改 async 会牵动三处调用链与测试；单 loop 方案改动最小且同样保证“同一连接只在一个 loop 被 await”。

### 2.2 硬超时（`_navigate`）

| 行 | 改动 |
| --- | --- |
| `:201-222` | 签名加 `loop=None`；`browser.get(url)` 与 `tab.get_content()` 都用 `asyncio.wait_for(..., timeout=timeout)` 包住；`tab.evaluate("location.href")` 也加 `wait_for`（best-effort，失败回落 `url`）；`run_until_complete` 跑在传入的 `loop` 上 |

- 超时抛 `TimeoutError` → `fetch` 捕获并返回 `browser:TimeoutError`；**总耗时不超过 `timeout`**（不再用 `sleep` 兜底）。
- 保留：`_same_site` 越站判定、`navigations` 记录、`close()` 语义、offsite/onsite 返回结构。

## 3. 新增测试（`tests/test_access_zhihu.py::TransportTests`）

| 测试名 | 断言 |
| --- | --- |
| `test_authenticated_transport_uses_one_loop` | fake 的 `get` 里记录 `asyncio.get_running_loop()`，断言 `is transport._loop`——**启动与导航同一 loop** |
| `test_authenticated_transport_times_out_instead_of_hanging` | fake `get` 为 `await asyncio.sleep(3600)`，`timeout=0.2` → `fetch` 返回 `error="browser:TimeoutError"`、`status=None`，且实测耗时 `< 5.0s`（不挂死） |
| 现有 `test_authenticated_transport_blocks_offsite_landing` | 不回归：仍 `offsite_redirect:` |
| 现有 `test_authenticated_transport_returns_html_when_on_site` | 不回归：`status=200`、含 content、`error=None` |

## 4. 测试结果（真实 exit）

| 套件 | 结果 |
| --- | --- |
| `tests.test_access_zhihu.TransportTests` | **7 tests OK**（含 2 新增） |
| `tests.test_access_budget` + `tests.test_access_zhihu` | **82 tests OK**（原 80 + 2） |
| 全项目 `unittest discover -s tests -t .` | **OK** |

- cwd `D:\桌面\two`，解释器 `.venv\Scripts\python.exe`；均 exit 0。

## 5. 预算状态（未变）

- 第 1 次真实调用已消耗：`runtime_live2` 的 `calls=1`、`records=0`、`locked=0`、无 lock 记录、ledger 仅 1 条 `charge`。
- **剩余 2 次**；本轮未发任何真实请求，预算未变。
- 修好后需另派任务，用剩余 2 次重跑 1 次真实搜索。

## 6. 真实 nodriver 三条约束（供后续平台接入直接复用）

1. **连接绑定事件循环**：`Browser`/CDP 连接只能在创建它的那个 loop 里被 await；跨 loop await **不会抛错，会永久挂起**。任何 transport 必须自持一个 loop，或整条链路统一 async。
2. **`Browser` 没有 `evaluate`/`tab`，只有 `main_tab`**：JS 求值要走 `browser.main_tab.evaluate(...)`（或 `browser.get()` 返回的 Tab），且都是 **async**。
3. **所有 CDP 调用都必须 await，并且都要有 `asyncio.wait_for` 硬超时**：`get`/`get_content`/`evaluate` 都可能因页面卡住而永不返回；没有超时保护就会像本次一样静默挂死。

## 7. 限制

- 本轮**未真跑搜索**（按要求）；修复仅由单测覆盖，未在真实 nodriver 上复验。
- 超时后不重试、不自动重开浏览器；`close()` 由调用方负责。
- 未验证超时值（默认 20s）对知乎搜索页是否足够；真实页面可能 >20s。
- 未改 `zhihu.py` 的 `_make_transport`/调用链（同步保持不变）。
