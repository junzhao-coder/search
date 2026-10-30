# weibo-rpa-6 桌面搜索侦察（probe）：入口已改桌面版，侦察因代码缺陷中断

- 时间：2026-10-30T06:27:25Z 起（UTC）；cwd `D:\桌面\two`；解释器 `C:\Users\19183\.dsh\tools\x-collect\venv\Scripts\python.exe`。
- 一句话：**入口已按验收改为桌面版 `s.weibo.com`；`probe` 子命令已实现并有 4 类 fixture 单测；但真实那次 probe 在我自己的代码缺陷（`session.html` 不存在）上抛异常，exit 7，没拿到选择器计数。页面本身确实加载了内容（http 200、text_len 2241），批次 1 次额度已消耗，未重试。**

## 1. 离线改动（验收 1、2）

| 项 | 变更 |
| --- | --- |
| `weibo.search_url` | **默认桌面版**：`https://s.weibo.com/weibo?q=<urlencode>&typeall=1&suball=1`；`surface="mobile"` 保留原 `m.weibo.cn/search?containerid=…`（不删） |
| 差异说明（写进 docstring） | 桌面版结果由服务端直出 `div.card-wrap`，适合直接数结构；移动版实测导航后 `containerid` 被丢、`text_len≈6`、`cards_in=0`，不再作为默认 |
| `rpa/probe.py` | 纯函数 `summarize(html, …)`：只输出结构与计数，**不保留正文**；`verdict(summary)` → (exit, stop)：风险优先 → 有卡片 → 零命中 |
| `rpa/cli.py::cmd_probe` | 单次导航；`precheck → charge_nav("probe", source="rpa.probe") → 导航 → 桌面证据/标题闸门 → wait_ready → 风险判定 → summarize → 登记`；不截图、不读 cookie |
| `session.html(tab)` | 新增：取渲染后的整页 HTML（供 probe 数结构） |

`probe` 输出字段：`final_url / http_status / title / text_len / ready`；选择器计数
`div.card-wrap / div.card / p.txt / a.name / div.from / div.card-act / a[href*="/status/"] / a[href*="s.weibo.com"] / img.avator / .card-comment`；
前 5 条 `/status/` 链接的 `href_id` 与 `data-id` 是否一致；`wall.markers / wall.login_wall`。

## 2. 单测（离线，4 类 fixture + 入口 + 抓取）

| 用例 | 覆盖 |
| --- | --- |
| `ProbeSummaryTests::test_all_selectors_hit` | 全部 10 个选择器命中；`status_ids[0].consistent=true`；verdict=0；**输出里不含正文摘要** |
| `..._partial_hits_still_count` | 只有 `div.card` + 一个 `/status/` 链接 → 计数 1/1，verdict=0 |
| `..._zero_hits_is_nonzero` | 零命中 → `(4, "no_cards")` |
| `..._captcha_marker_wins_over_cards` | 正文含「安全验证」→ `(5, "risk:text:安全验证")`，即使有卡片 |
| `..._data_id_mismatch_is_reported` | `href_id≠data_id` → `consistent=false` |
| `SearchUrlTests` | 默认 `s.weibo.com` + `typeall/suball`；`surface="mobile"` 仍保留 |
| `HtmlFetchTests` | `session.html()` 真取 `get_content()`；`cmd_probe` 确实用 `session.html`/`summarize`/`charge_nav(source="rpa.probe")` |
| `ProbeCliGuardTests` | 无批次 → 在启动浏览器前 `exit 6` |

结果：`tests.test_selection_rpa` **119 tests OK**；四套全量 **356 tests OK**（`logs/tests-rpa-probe.log`、`logs/tests-all-probe.log`），无跳过。

## 3. 真实 probe（weibo-rpa-6）

| 项 | 值 |
| --- | --- |
| 授权 | `authorized_calls=3`（2 seed + probe 1）、`seed_used=2`、`remaining=1`、`records_cap=5`、窗口 06:27:25Z→06:32:25Z；note=`2 次历史追认 + probe 1；侦察桌面搜索入口与选择器，不取数据` |
| argv | `python -X utf8 -m tools.selection.rpa probe --profile C:\Users\19183\.dsh\tools\weibo-collect\profile --batch-id weibo-rpa-6 --url "https://s.weibo.com/weibo?q=%E5%AD%A6%E4%B9%A0%E8%AE%A1%E5%88%92%E6%A8%A1%E6%9D%BF&typeall=1&suball=1" --out …\logs\probe-rpa6.json` |
| exit / stop / stage / status | **7** / `probe_exception:AttributeError` / `exception` / `error` |
| `page.final_url` / `http_status` / `text_len` | `https://s.weibo.com/weibo`（**`q` 参数又被丢掉**）/ **200** / **2241** |
| `desktop` | `window_title_matches_page=true`、`topmost_set=true`、`foreground_matched=true` |
| `summary`（选择器计数） | **空**（异常发生在 `summarize` 之前） |

**根因**：`cmd_probe` 调用了 `session.html(tab)`，但 `VisibleSession` 当时**没有**这个方法 → `AttributeError`。这是我上一版代码的缺陷，不是站点问题。

**账本**：`active_nav` 06:27:26Z（detail=`probe`）→ `active_nav_result` 06:27:29Z（`unknown`）；`used=3/3`、**`remaining=0`**、`locked=false`。

## 4. 修复（已落盘并测过）

1. `session.html(tab)` 新增：`return self._run(tab.get_content())`；
2. `guard.charge_nav(..., source=...)` 支持来源，`cmd_probe` 用 `source="rpa.probe"`（此前记成 `rpa.login`）；
3. 新增 `HtmlFetchTests`（含"cmd_probe 必须用 session.html/summarize/charge_nav"的静态断言）。

## 5. 结论（验收 7，严格）

1. **桌面入口是否真的渲染结果卡片：仍不能确认。** 本次只拿到 `http 200 / text_len 2241 / final_url=https://s.weibo.com/weibo`；HTML 结构没取到，`counts` 为空。
2. **哪几个选择器可用：未知**（没有计数）。
3. **CARD_JS 暂不改**：在拿到 `div.card-wrap`/`p.txt` 等真实计数之前改选择器仍是盲改。
4. 两个可用的信号：①桌面页 `text_len=2241` vs 移动版 `6`，说明**桌面入口确实有内容**；②两次导航后 `q` 参数都从 `final_url` 消失，需下一次 probe 判断是"服务端重定向"还是"参数被前端路由吃掉"。

## 6. 下一步（需决定）

- 本轮额度已尽（3/3，窗口 06:32:25Z 关闭）。再跑一次 probe 需**新批次**（3 = 2 seed + 1 probe）。
- 下一次 probe 建议直接观察 `final_url` 是否保留 `q`；若仍被丢，改试 `https://s.weibo.com/weibo?q=…`（去掉 `typeall/suball`）或 `https://s.weibo.com/weibo/<kw>` 路径式入口，仍只跑 1 次、不重试。

## 7. 未做

未读/打印 cookie 值；未对真实页面截图；未重试、未换 URL；未改账本补额度；未改业务库/CSV/契约/小红书；未提交 git。
