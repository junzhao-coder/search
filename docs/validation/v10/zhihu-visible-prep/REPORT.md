# V10-3 / visible-prep：opt-in 可见窗口开关（默认仍 headless）

- 范围：`tools/selection/access/`、`tests/test_access_zhihu.py`、本目录。
- **本轮没有联网、没有启动浏览器、没有登录、没有装依赖、没有发任何真实请求、没有做全套回归。**
- 真实调用需要用户明确同意（计划 P5：超出 3 次真实预算须用户决定；当前已累计 4 次）。

## 1. 动机（来自实测，不是猜测）

同一台机器、同一个 profile、同一套 `tab.evaluate` 机制，两次真实运行表现**完全相反**：

| 真实运行 | 窗口模式 | 结果 |
| --- | --- | --- |
| `login`（已验收） | **可见窗口**（`--headless` 是 `store_true`，默认 False） | `signed_in=true / polls=26 / elapsed 75.579s` —— `tab.evaluate` **连续 26 次正常返回** |
| `search`（4 次真实调用） | **headless**（`_make_transport` 没传 headless，吃默认 `True`） | public-http 403 / 挂死 44min / 0 记录 / `browser:TimeoutError`（`anchors` 与 `ready_state` 全未取得，未进解析函数） |

可见窗口里求值正常、headless 里一次都不返回 → 需要一个“**搜索也走可见窗口**”的开关来做对照实验。

**不宣称已证明 headless 检测**：目前只有两条真实运行的现象对照，样本各一次，且没排除 profile 复用、页面差异、网络时序等因素；这个开关只是**让对照实验可做**，结论要等下一轮真实调用。

## 2. 改了什么（一个 flag，不重构）

- `search` / `detail` / `comments` 三个子命令各加 `--visible`（`action="store_true"`）：
  ```
  --visible   open a visible browser window instead of headless (opt-in; default headless)
  ```
- `_make_transport` 在 `authenticated-browser` 模式下：`headless=not args.visible`
  （其它模式完全不受影响；`offline` 仍返回 `RefusedTransport`，`public-http` 不变）。
- **默认行为不变**：不传 `--visible` → `headless=True`，与之前逐字节一致。
- `login` 子命令的既有 `--headless`（默认 False）**未改**，两者互不影响。
- `--timeout`（默认 60）与 `--diagnostics-dir` 保持原样。

实测解析结果：`default_headless=True / visible_headless=False / timeout=60.0`；`search --help` 已列出 `--visible`。

## 3. 离线测试（`tests/test_access_zhihu.py::VisibleWindowFlagTests`）

| 用例 | 断言 |
| --- | --- |
| `test_default_construction_is_headless` | 不传 `--visible` → `transport.headless is True`、`timeout == 60.0` |
| `test_default_visible_is_false_for_every_command` | search/detail/comments 三个子命令默认 `visible is False` |
| `test_visible_flag_reaches_transport_for_every_command` | 三个子命令加 `--visible` → `transport.headless is False` |
| `test_visible_does_not_touch_other_modes` | `--mode offline` 仍返回 `RefusedTransport`（别的模式语义没变） |

`_make_transport` 构造传输层**不会启动浏览器**（懒启动），所以这些用例是纯离线的。

**运行记录**（`execution_manifest.json`）：`python -X utf8 -m unittest tests.test_access_zhihu -v`，cwd=`D:\桌面\two`，`2026-10-27T14:04:21Z` → `14:04:29Z`，**rc=0，Ran 88 tests — OK**（network=none、browser=none）。原 84 例**无一回归**，新增 4 例全绿（最终复跑同结果：rc=0 / Ran 88 OK）。

## 4. 下一轮真实诊断入口（**本轮不执行**）

```powershell
python -X utf8 -m tools.selection.access.zhihu `
  --state-dir "docs\validation\v10\zhihu-visible-prep\state-$(Get-Date -Format yyyyMMddHHmm)" `
  --mode authenticated-browser `
  --profile "C:\Users\19183\.dsh\tools\zhihu-collect\profile" `
  search "学习计划" --visible --timeout 60 `
  --diagnostics-dir "docs\validation\v10\zhihu-visible-prep\diag"
```

- **新 state-dir**（用新预算，别复用已花掉/已锁的旧目录）；**原 profile 只读不改**；仍然只读浏览。
- 加 `--visible` 时**会弹出一个真实窗口**，属于用户可见操作，必须先拿到用户明确同意再跑。
- 判读：
  1. `state=result` 且有 `anchors_*` → 可见窗口能求值，**headless 差异**是最可能的解释方向（仍需再跑一次 headless 对照才能说“证明”）。
  2. `probe_level=1 且 level_timeout=true` 仍然出现 → 可见窗口也求值不了，问题不在 headless，回到探针/环境层。
  3. `browser:TimeoutError / phase=navigate` → 连 `get` 都没回来，与上次 headless 现象一致，说明差别不在窗口可见性。
- 对照实验建议：同一天、同一 profile、同一关键词，**先 `--visible` 再 headless**，两次都带 `--diagnostics-dir`，比对 `probe_level/probe_elapsed_ms/state/anchors_*`。

## 5. 仍未验证

1. **headless 是否真的被知乎检测**——未验证。本轮只加开关，没有真实调用；现象对照各只有一次样本。
2. 可见窗口跑搜索是否真能拿到 `anchors`/`ready_state`——未知。
3. `--visible` 下 60s 是否足够——未知（无真实耗时样本）。
4. 未排除 profile 复用、页面 A/B、网络时序等混杂因素。
5. 按要求只跑 `tests.test_access_zhihu`（88 例），**未做全套回归**；未改 `budget.py`/`records.py`/`zhihu_cli.py` 语义，未改 `docs/validation/v10/zhihu` 与 `docs/validation/v10/zhihu-readiness`。
