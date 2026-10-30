# weibo-rpa-19：hot 排序拿到有评论样本，钩子生效并抓到评论端点

- 时间：2026-10-30T07:51–07:54Z（UTC）；cwd `D:\桌面\two`；解释器 `C:\Users\19183\.dsh\tools\x-collect\venv\Scripts\python.exe`。
- 一句话：**三件事都成了** —— ①hot 排序拿到高互动样本（评论 66/29/147/41/136）；②详情页渲染等待生效（`text_len` 361→1217，`render_wait.waited_ms≈1s`、`stable=true`）；③`hook_installed=true`、`network.count=19`，**评论端点被捕获：`/ajax/statuses/buildComments`，3 次调用，参数与响应键名都拿到了。**

## 1. 三个修复（验收 1、2）

| 修复 | 实现 | 证据 |
| --- | --- | --- |
| 详情页渲染等待 | `session.wait_render_stable(tab, min_len=500, attempts=20, interval=0.5)`：连续两次 `text_len` 相同且 ≥500 才算稳定，最多 ~10s，记录 `waited_ms` | 本轮 `render_wait={"stable":true,"text_len":934,"waited_ms":1014}`；页面 `text_len` 从 361（上一轮）变成 **1217** |
| hot 排序 | `live-search --sort hot` 在 URL 追加 `xsort=hot`（在 RPA 层拼，不动 access 层） | `requested_url=…&typeall=1&suball=1&xsort=hot`，5 条全有互动 |
| 钩子回读 | `open_live_hooked` 先 `Page.enable()` 再 `addScriptToEvaluateOnNewDocument`，失败/回退都把原因写进 `payload["hook_error"]` | 第一次探测 `hook_installed=False`（当时没开 Page 域）；补 `Page.enable()` 后 **`hook_installed=True`** |

单测：`SortAndRenderWaitTests`（hot 追加 `xsort=hot`、稳定即停、`text_len<500` 判未渲染）+ `HookOrderTests`（注入发生在导航前、普通 `open_live` 不注入、probe 用 hooked）。
`tests.test_selection_rpa` **161 OK**；四套全量 **396 OK**（`logs/tests-all-hot.log`），无跳过。

## 2. 候选样本（考研 + hot）

| mid | 作者 | 正文长度 | 转发 | 评论 | 赞 | 链接 |
| --- | --- | --- | --- | --- | --- | --- |
| 5359714560901366 | 民法岳业鹏 | 19 | 1 | 66 | 447 | https://weibo.com/2685653721/Rp3rO3Mua |
| 5358567843956855 | 何凯文 | 182 | 84 | 29 | 1870 | https://weibo.com/1742944894/RozCggBmf |
| **5348595884891806** | **大学安利君** | 52 | 217 | **147** | 13627 | https://weibo.com/5518250456/RkocskwA6 |
| 5359139148531490 | 不要輕易戳破那層紗_ | 108 | 17 | 41 | 809 | https://weibo.com/7818375998/RoOtIzNqG |
| 5355650899250443 | 老师我好笨我是猪吗 | 123 | 161 | 136 | 3223 | https://weibo.com/2284120985/RnlJvCOsH |

**选中 `5348595884891806`（评论 147，最大）**。

## 3. 详情页探测（两次，第二次成功）

| 项 | 第一次（07:51:48Z） | 第二次（07:54:22Z，补 `Page.enable` 后） |
| --- | --- | --- |
| exit / surface | 0 / detail | 0 / detail |
| `text_len` | 1217 | 1217 |
| `render_wait` | `{stable:true, text_len:934, waited_ms:1000}` | `{stable:true, text_len:934, waited_ms:1014}` |
| **`hook_installed`** | **False** | **True** |
| `network.count` | 0 | **19** |
| `comment_like` | 空 | **4 条**（含 3 次 `buildComments`） |

`hook_error`（第一次）为空字符串 —— 说明当时 `Page.enable()` 缺失导致 CDP 注入静默无效、且回退 `evaluate` 也没生效；补上 `Page.enable()` 后一次成功。

## 4. 捕获到的评论端点（验收 5）

**端点**：`GET https://weibo.com/ajax/statuses/buildComments`

| # | 参数名（值未记录） | status | 响应大小 | 响应顶层键 |
| --- | --- | --- | --- | --- |
| 1 | `is_reload, id, is_show_bulletin, is_mix, count, uid, fetch_level, locale` | 200 | 162,732 B | `ok, filter_group, data, rootComment, total_number, tip_msg, max_id, trendsText` |
| 2 | `flow, is_reload, id, is_show_bulletin, is_mix, max_id, count, uid, fetch_level, locale` | 200 | 58,228 B | 同上 |
| 3 | `flow, is_reload, id, is_show_bulletin, is_mix, max_id, count, uid, fetch_level, locale` | 200 | 59,062 B | 同上 |

同时捕获到正文接口：`/ajax/statuses/show`（参数 `id, locale, isGetLongText`，200，3,032 B，顶层键含 `id/mid/mblogid/user/textLength/source/...`）。

其它 15 条为页面框架请求（`config/get_config`、`getNavConfig`、`feed/allGroups`、`log/rum`、`message/unreadHint`、`checkReward`、`checkAllowCommentWithPic`、`hreward/...`），与评论无关。

## 5. 结论（验收 6，选 a）

**a) 钩子生效且抓到评论端点。**

| 问题 | 结论 |
| --- | --- |
| 评论走哪个端点 | `GET https://weibo.com/ajax/statuses/buildComments`（页面自身发起） |
| 需要哪些参数 | 必需：`id`（= mid）、`is_reload=1`、`is_show_bulletin`、`is_mix`、`count`、`uid`、`fetch_level`、`locale`；翻页追加：`flow`、`max_id` |
| 首屏能拿到多少条 | 首屏一次 162 KB 响应（`data` 为评论数组），具体条数需解析 `data`/`total_number` 才能确认（本轮只记结构，不落正文） |
| 翻页参数 | **`max_id`**（第 2、3 次请求都带 `max_id`，且响应里也回传 `max_id`）＋ `flow` |
| 子回复如何表示 | 响应键里有 `rootComment`（疑似楼中楼/根评论）与 `data`；**具体嵌套结构需下一次解析 `data` 才能确认** |
| 评论在 DOM 里为什么 0 条 | 我们的 `summarize_comments` 容器选择器（`comment-item` 等）与真实 DOM 不匹配 —— 评论是 JS 渲染的，选择器需按真实结构重写 |

## 6. 账本

| 事件 | UTC | source | detail |
| --- | --- | --- | --- |
| `search`（hot） | 07:51:22Z | rpa.search | search |
| `search_result` | 07:51:25Z | rpa.search | **success** |
| `active_nav`（详情 1） | 07:51:48Z | rpa.probe | probe |
| `active_nav_result` | 07:51:54Z | rpa.probe | success |
| `active_nav`（详情 2） | 07:54:22Z | rpa.probe | probe |
| `active_nav_result` | 07:54:28Z | rpa.probe | **success** |

`used=5/5`、`remaining=0`、`records_reserved=5`、`locked=false`。

## 7. 下一步建议

1. **按端点取评论**（页面自身调用，计入显式接口调用）：`buildComments?id=<mid>&is_reload=1&is_show_bulletin=2&is_mix=1&count=20&fetch_level=0&locale=zh-CN`，翻页用响应里的 `max_id`。
2. 解析 `data[]` 的字段（评论 id/作者/正文/时间/点赞/父评论）与 `rootComment` 的嵌套关系——需要一次「取到响应并解析」的受控调用（可先用本地 fixture 把解析器写好）。
3. 修 `summarize_comments` 的容器选择器（用真实 DOM 校准），否则 DOM 路径永远 0 条。

## 8. 未做

未读/打印 cookie 值；未对真实页面截图；未重试、未换词；未改账本补额度；未改业务库/CSV/契约/小红书；未提交 git。守卫五哈希未变。
