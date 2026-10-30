# weibo-startfix：profile 相对路径导致启动失败（三处入口）+ 启动失败结构化/入账

- 范围：`tools/selection/access/{transport.py,zhihu.py,weibo.py}`、`tests/test_access_weibo.py`、本目录。
- 触发：`task-32c21f6e`（微博未登录探路，已验收为“无效但根因定位”）的真实失败。
- **本轮未联网、未启浏览器、未登录、未装依赖、未写业务库/CSV/CONTRACT；未改预算语义与阈值；未动探针与风险策略；未放宽任何断言。**
- 结果：三个模块 **153 例 rc=0**（weibo 37 / zhihu 96 / budget 20）。

## 1. 真实失败（实测现象，不是推测）

`task-32c21f6e` 用 **相对** profile 路径跑真实探路：

```
--profile docs\validation\v10\weibo-probe\profile_empty
stdout             : 0 字节
stderr             : transport._ensure_browser → uc.start → Browser.start
                     → Exception("Failed to connect to browser")
诊断目录            : 未创建
chrome 进程采样     : 0
profile 目录        : 仍为空（说明浏览器根本没起来）
微博 HTTP 请求      : 0（没有一条请求发出）
```

对照实验：`about:blank` + **相对**路径 → `LAUNCH_FAILED`；同一页面 + **绝对**路径 → 正常启动。**结论：相对 `user_data_dir` 会让 nodriver 启动后连不上浏览器。**

## 2. 修了什么（三处入口一起修）

| 入口 | 改动前 | 改动后 |
| --- | --- | --- |
| transport（搜索/详情/评论都走这里） | `transport.py:134` `self.profile = pathlib.Path(profile)`（原样拼给 `uc.start`） | `transport.py:148` `self.profile = pathlib.Path(profile).expanduser().resolve()` |
| 知乎登录 | `zhihu.py:540` `pathlib.Path(profile)` 未绝对化，`user_data_dir=str(profile)` 直接传 | `zhihu.py:539` 先 `profile = pathlib.Path(profile).expanduser().resolve()`，之后 `mkdir`/`uc.start` 都用它（`zhihu.py:541-542`） |
| 微博登录 | `weibo.py:243` 同上 | `weibo.py:242` 同样先绝对化，`weibo.py:244-245` 使用 |

判据（新增测试）：传相对路径与绝对路径，最终传给 `uc.start` 的 `user_data_dir` **都是绝对路径**。

**为什么知乎线从没暴露**：知乎全程用绝对路径（`DEFAULT_PROFILE = C:\Users\19183\.dsh\tools\zhihu-collect\profile`，`zhihu.py:34`），所以这条路径上的缺陷一直没被触发；微博探路是第一次有人传相对路径。

## 3. 启动失败结构化 + 入账（不再裸栈）

改动前：`uc.start` 抛非超时异常时，`_ensure_browser` 没有捕获，异常一路冒到 `fetch` 之外 → **裸栈**、stdout 0 字节、诊断目录都没建，账本里只有 `charge` 没有 `transport_error`，事后无法区分“启动失败”与“请求失败”。

改动后：

| 位置 | 内容 |
| --- | --- |
| `transport.py:103-108` | 新增 `class BrowserStartFailed(RuntimeError)`，带 `.reason` |
| `transport.py:111-114` | `_short_reason(exc)`：单行、去换行、截断 120 字符（`类型名:消息`），保证诊断可读且不刷屏 |
| `transport.py:184-190`（`_ensure_browser`） | 超时仍抛 `TimeoutError("browser_start_timeout")`；**其它异常**包成 `BrowserStartFailed(_short_reason(exc))` |
| `transport.py:218-226`（`fetch`） | **先** catch `BrowserStartFailed`（它是 `RuntimeError` 子类，顺序必须在 `RuntimeError` 之前），返回 `{"status": None, "error": "browser_start_failed:<简短原因>", "diagnostics": {phase:"start", state:"start_failed", error:...}}` |
| 上层（`weibo.run_search` / `zhihu.run_search` 等） | 该 error 走既有 `_risk_or_error` → **不锁**（不是风险）、`batch.note("transport_error", reason)` → **账本落一行**，退出 `EXIT_TRANSPORT`（非零） |

**账本可区分性**（测试断言，非口头）：
- `budget.read_ledger(...)` 里出现 `kind="transport_error"`；
- 该行 `detail` 含 `browser_start_failed`；
- `snapshot["locked"] is False`（启动失败绝不锁批次）。

## 4. 新增测试（`tests/test_access_weibo.py::StartFailureTests`，5 例）

| 用例 | 断言 |
| --- | --- |
| `test_relative_profile_becomes_absolute` | `transport.profile.is_absolute()` 且等于 `Path(relative).resolve()` |
| `test_absolute_profile_is_unchanged` | 绝对路径解析后不变（`== absolute.resolve()`） |
| `test_failed_launch_is_structured_and_not_a_risk` | `status is None`、`error.startswith("browser_start_failed:")`、含 `Failed to connect`、`diagnostics.state=="start_failed"`、`phase=="start"`、`uc.start` 只调 1 次、收到的 `user_data_dir` 是**绝对**路径 |
| `test_failed_launch_exits_nonzero_without_locking_and_is_in_the_ledger` | `exit==EXIT_TRANSPORT`（非 0）、`locked is False`、`stop` 含 `browser_start_failed`、ledger 有 `transport_error` 且 detail 含该前缀 |
| `test_login_path_passes_an_absolute_user_data_dir` | 知乎与微博的 `_login_with_real_browser` 在收到相对路径时，传给 `uc.start` 的 `user_data_dir` 都是绝对路径，且登录流程照常 `status=="ok"` |

测试实现：`_StubNodriver` / `_StubLoginBrowser` + `mock.patch.dict(sys.modules, {"nodriver": stub})`，**不安装、不启动真实浏览器**。

## 5. 测试执行清单（真实 argv / cwd / UTC / exit）

执行器：`docs/validation/v10/weibo-startfix/run_tests.py`；清单：`execution_manifest.json`；原始输出：`logs/*.stdout.txt`、`logs/*.stderr.txt`。

| 模块 | argv | cwd | start (UTC) | end (UTC) | exit | 结果 |
| --- | --- | --- | --- | --- | --- | --- |
| `tests.test_access_weibo` | `.venv\Scripts\python.exe -X utf8 -m unittest tests.test_access_weibo -v` | `D:\桌面\two` | 2026-10-27T15:10:25Z | 15:10:26Z | **0** | Ran 37 — OK |
| `tests.test_access_zhihu` | 同上（换模块名） | `D:\桌面\two` | 2026-10-27T15:10:26Z | 15:10:35Z | **0** | Ran 96 — OK |
| `tests.test_access_budget` | 同上（换模块名） | `D:\桌面\two` | 2026-10-27T15:10:35Z | 15:10:36Z | **0** | Ran 20 — OK |

合计 **153 例**（基线 148 + 新增 5）；`network=none`、`browser=none`。

## 6. 守卫（实测未变）

| 守卫 | 路径 | SHA256 前 16 位 |
| --- | --- | --- |
| app.db | `instance/app.db` | `e073f828cf0f30d6` |
| workflow.sqlite3 | `tools/workbench/runtime/workflow.sqlite3` | `8ae79c58d8ea5c30` |
| CONTRACT.md | `docs/design/CONTRACT.md` | `826c24cc6c995511` |
| scores.csv | `docs/validation/money-project/scoring/scores.csv` | `ab0c3546c3e9e46f` |
| sources.csv | `docs/validation/money-project/sourcing/sources.csv` | `13679b60d2ba1c32` |

## 7. 本轮**没有**验证的

1. **没有重跑真实探路**（任务明确不让）：相对路径修复后真实 Chrome 是否确实能起来，只能由下一轮真实调用确认。
2. `expanduser().resolve()` 在 Windows 上对 `~`、UNC 路径、含空格路径的展开行为，只做了单元级断言（`is_absolute` + 等于 `Path(...).resolve()`），没有真实 Chrome 实测。
3. `uc.start` 其它失败形态（端口占用、Chrome 被占用、无可用二进制）是否都会走到 `browser_start_failed`，只用一个合成异常验证；真实 nodriver 的异常类型未逐一枚举。
4. 结构化错误只保证**不锁批次**且**非零退出**；是否需要单独的退出码（现在是通用 `EXIT_TRANSPORT=7`）未改，避免动既有语义。
5. 只跑三个 access 模块，**未做全套仓库回归**。
