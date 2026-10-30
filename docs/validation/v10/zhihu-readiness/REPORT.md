# B10-fresh（zhihu-readiness / V10-3）：就绪探针分级轻量化 + 传输超时 60s

- 范围：`tools/selection/access/`、`tests/test_access_zhihu.py`、本目录。
- **本轮没有联网、没有启动浏览器、没有登录、没有装依赖、没有做全套回归、没有写业务库/CSV/CONTRACT。**
- 动机来自**实测**，不是猜测：`task-722c2745` 那次真实搜索 `exit=7 / stop=browser:TimeoutError / phase=navigate / state=unknown`，`anchors` 与 `ready_state` **一个都没取到**，**根本没走到 `parse_search_html`**；硬超时首次真实触发耗时 20.059s。同一环境里 `data:` URL 离线对照证明 nodriver 接口本身正常。也就是说：**真实知乎搜索页的 CDP 求值不返回**，而当时探针恰恰是“一次重求值读 `document.body.innerText` + 最多 400 个锚点 + 多个 `querySelectorAll`”。

## 1. 改动（先轻后重，逐级独立超时，失败降级）

| 层级 | 内容 | 独立预算 |
| --- | --- | --- |
| L1 轻 | `document.documentElement.readyState` + `document.querySelectorAll('a[href]').length` + **前 20 个** href 的形态计数（answer/question/article/video/other）。**不读 innerText，不返回 href 列表。** | `min(2.0s, 剩余×0.5)` |
| L2 中 | 结果容器类名计数（`[class*="Result"/"Search"/"List"/"Card"/"Item"]`），不含正文 | `min(2.0s, 剩余×0.5)` |
| L3 重 | 仅在 L1/L2 成功但页面仍未就绪时才跑：`document.body.innerText` **截断 4000 字符**扫风险/空结果文案 | `min(4.0s, 剩余×0.5)` |

- **不再**有任何“一次重 evaluate 读整页 innerText + 数百锚点”的首要判定。
- **每一级超时 = 该级 unknown 并停止等待**，不把整次导航判成硬失败；`probe_level` / `level_timeout` 如实记录。
- 每级只用**一半剩余预算**（`_probe` 里 `_remaining(deadline) * 0.5`），保证探针卡住时**仍留一半预算给内容读取**——这才是“降级而不是整体失败”。
- **总 deadline 仍然只有一个、逐段递减**，分级不重置（`_deadline` / `_remaining`）。
- 诊断新增最小字段：`probe_level`、`probe_elapsed_ms`（`{"1":ms,"2":ms,"3":ms}`），仍属既有白名单，不含正文/账号信息。

## 2. 默认超时 20s → 60s

- `AuthenticatedBrowserTransport(timeout=60.0)`；CLI `search/detail/comments` 新增 `--timeout`（默认 60），经 `_make_transport` 传入。
- 60s 仍是**一个**总预算：启动 → 导航 → 就绪（三级）→ 内容 → 最终 URL 全部从这 60s 里扣。

## 3. 离线测试（fake 异步 tab，无网络无浏览器）

新增/改写覆盖验收第 4 条：

| 场景 | 用例 |
| --- | --- |
| L1 超时→降级 unknown（不是整体失败） | `test_light_probe_timeout_degrades_to_unknown`（status 仍 200，`probe.state=unknown`，`level=1`，`level_timeout=True`，`diagnostics.probe_level=1`） |
| L1 未就绪→进入下一级 | `test_light_probe_success_then_heavier_levels_run`（`levels_seen` 含 2、3） |
| L2 超时→降级 unknown | `test_heavier_probe_timeout_degrades_to_unknown`（`level=2`） |
| 分级不重置总 deadline | `test_stuck_light_probe_stops_without_resetting_deadline`（1.2s 预算内结束） |
| 每级耗时可见 | `test_probe_timings_and_level_are_in_diagnostics` |
| 60s 默认生效 | `test_default_timeout_is_60_seconds`、`test_cli_timeout_and_diagnostics_dir_reach_the_transport` |
| 全部失败仍非零 | `test_always_loading_times_out_as_unknown` + `test_unreadable_page_is_not_reported_as_empty_success`（`stop=readiness_timeout`） |

原有 8 例就绪/deadline 测试与 7 例脱敏测试全部保留（fake 已改成按 `level:1/2/3` 分别应答）。

**运行记录**（`execution_manifest.json`）：`python -X utf8 -m unittest tests.test_access_zhihu -v`，cwd=`D:\桌面\two`，2026-10-27T13:59:43Z → 13:59:51Z，**rc=0，Ran 84 tests — OK**（network=none、browser=none）。CLI 冒烟（全新临时 state-dir，离线 `--input`）`--timeout 60 --diagnostics-dir` → **exit=0**，诊断只写 5 个计数字段。

## 4. 下一轮真实诊断入口（**本轮不执行**）

```powershell
python -X utf8 -m tools.selection.access.zhihu `
  --state-dir docs/validation/v10/zhihu-readiness/state-probe-$(Get-Date -Format yyyyMMddHHmm) `
  --mode authenticated-browser `
  --profile C:\Users\19183\.dsh\tools\zhihu-collect\profile `
  search "学习计划" --timeout 60 `
  --diagnostics-dir docs/validation/v10/zhihu-readiness/diag
```

- **新 state-dir**（用新的预算，别复用已花掉/已锁的旧目录），**原 profile 只读不改**，仍然只读浏览。
- 判读顺序：
  1. `probe_level` = 1 且 `level_timeout=true` → **轻探针本身**就会被 CDP 卡住：问题不在探针过重，得怀疑 headless/环境层面（下一步再谈，不在本轮范围）。
  2. `probe_level` = 2 或 3 且 `level_timeout=true` → 轻探针能过、重探针被卡：探针过重的假设**成立**，继续把 L3 拆小或延后。
  3. 三级都成功但 `state=unknown` → 页面结构/选择器假设不对，按 `anchors_*/href_shapes/contentish` 校正。
  4. 拿到 `state=result` 但 `count=0` → 才轮到 `parse_search_html` 的形态假设问题。

## 5. 仍未验证

1. **真实页是否因“探针过重”而阻塞——未验证**：本轮只做了离线准备，没有发任何真实请求，假设尚未被证实也未被推翻。
2. **60s 是否足够——未知**：如果真实页 `get` 本身就要几十秒，60s 也可能不够；本轮没有真实耗时样本。
3. **知乎是否对 headless 另有检测——未知**：`data:` URL 对照只证明 nodriver 接口可用，不证明知乎页面允许 headless 求值。
4. **三级选择器全是假设**：`[class*="Result"]` 等容器类名、空结果文案、风险文案都未在真实页面上核对过，诊断里仍标 `selectors_assumed`。
5. `probe_elapsed_ms` 反映的是**客户端等到的时长**，不等于页面内部执行时长；CDP 阻塞时两者可能差很多。
6. 按要求只跑变更相关模块（84 例），**未做全套回归**；未改 `budget.py`/`records.py`/`zhihu_cli.py` 语义，未改 `docs/validation/v10/zhihu`。
