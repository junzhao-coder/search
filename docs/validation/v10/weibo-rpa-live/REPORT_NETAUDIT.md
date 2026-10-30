# 评论点击选择器修复 + 网络审计：端点仍未出现（结论：点「评论」不触发加载）

- 时间：2026-10-30T07:39:56Z 起（UTC）；cwd `D:\桌面\two`；解释器 `C:\Users\19183\.dsh\tools\x-collect\venv\Scripts\python.exe`。
- 一句话：**点击选择器修好了（这次确实点中精确文本「评论」的 `div`），但点击前后 `text_len` 都是 2355、评论条目都是 0，页面自身只发出两条无关 XHR（`/ajax/message/unreadHint`、`/ajax/log/read`）—— 评论端点仍未出现。**

## 1. 点击选择器修复（验收 1）

`CLICK_COMMENT_JS` 重写：
- **排除** `div.card-act` 内的任何节点（上一轮就是点中了「转发 评论 赞」那一行）；
- 优先级：**精确文本 === 「评论」** → `a[href*="comment"]` → 文本形如「评论 12」的入口；
- 返回值新增 `tag`、`href_shape`，并在 CLI 里记录**点击前后**的 `text_len` 与评论容器/条目数。

本轮实际命中：`{"clicked": true, "label": "评论", "tag": "div", "href_shape": "other"}` —— **点对了**。

## 2. `probe --audit-network`（验收 2–3）

`session.NET_HOOK_JS`：在页面内包装 `fetch` 与 `XMLHttpRequest`，只记录
`{host, path, method, params(仅参数名), status, size, keys(响应顶层键名)}`；
**不记录请求头、cookie、authorization、响应正文**。
`probe.summarize_network()` 再过滤：只留 `weibo.com` / `weibo.cn`（含子域），其余计入 `dropped_non_weibo`，并给出 `by_path` 与 `comment_like`（path 命中 `comment|buildComments|hotflow`）。

单测（`NetworkAuditTests`，4 例）：多条请求保留 + `method` 归一化 + `comment_like` 命中；非微博域被过滤；响应非 JSON 不崩（`keys=[]`）；**参数值不落盘**（断言 JSON 里没有 mid 值）。
`tests.test_selection_rpa` **150 OK**；四套全量 **385 OK**（`logs/tests-all-net.log`），无跳过。

## 3. 真实侦察（weibo-rpa-16）

| 项 | 值 |
| --- | --- |
| 批次 | `authorized_calls=4`（2 seed + 导航 1 + 评论触发 1）、`records_cap=5`（账本上限）、窗口 07:39:56Z→07:44:56Z |
| argv | `python -X utf8 -m tools.selection.rpa probe --profile … --batch-id weibo-rpa-16 --url https://weibo.com/3271525130/RoB0gpMsP --dump-comments --audit-network --out …\logs\probe-rpa16.json` |
| exit / stop | **4** / `no_cards`（详情页无 `div.card-wrap`，probe 判定按卡片数，属预期误判） |
| `requested_url` / `final_url` | 完全一致：`https://weibo.com/3271525130/RoB0gpMsP` |
| 点击 | `{"clicked": true, "label": "评论", "tag": "div", "href_shape": "other"}` |
| 点击前/后 | 评论条目 `0 → 0`；容器 `{} → {}`；`text_len` `2355 → 2355` |
| 捕获请求 | **2 条**，`dropped_non_weibo=0` |

### 捕获到的请求（按 path 归类）

| host | path | method | 参数名 | status | size | 响应顶层键 |
| --- | --- | --- | --- | --- | --- | --- |
| weibo.com | `/ajax/message/unreadHint` | GET | `group_ids` | 200 | 241 | `data`, `ok` |
| weibo.com | `/ajax/log/read` | POST | （无） | 200 | 350 | `data`, `ok` |

`comment_like` = **空**：没有任何 `buildComments` / `comments` / `hotflow` 类端点出现。

账本：`active_nav` 07:39:57Z（probe）→ 07:40:15Z（comments）→ `active_nav_result` 07:40:15Z `failed`；`used=4/4`、`remaining=0`。

## 4. 结论（验收 6，证据不足处直说）

| 问题 | 结论 |
| --- | --- |
| 点击是否命中「评论」入口 | **命中**（label 精确为「评论」），但**没有任何加载效果**（0 条、text_len 不变） |
| 评论走哪个端点 | **仍未观测到**。页面自身只发了 `unreadHint` 和 `log/read` 两条，均与评论无关 |
| 需要哪些参数 | **未知**（未捕获到端点） |
| 首屏能拿到多少条 | **未知** |
| 翻页参数 | **未知** |
| 子回复如何表示 | **未知** |

**推断（明确标注为推断）**：`weibo.com/<uid>/<bid>` 这个详情页的评论区大概率不是"点一下「评论」就拉"，而是
① 需要 `?type=comment` 这类路由/锚点；或
② 需要滚动到评论区触发懒加载（IntersectionObserver），而点击不会触发；或
③ 该页的评论由另一条接口按 `id=<mid>` 拉取（如 `ajax/statuses/buildComments`），但本轮没有任何触发路径命中它。

## 5. 下一轮建议（需新批次，每条只跑 1 次）

1. 直接导航 `https://weibo.com/3271525130/RoB0gpMsP?type=comment`（带审计 + 评论结构转储）；
2. 或换移动端 `https://m.weibo.cn/status/5358621166144499`（移动页评论区通常是直出 DOM）；
3. 或在详情页**滚动到底**再审计（验证懒加载假设）；
4. 若确认走 `ajax/statuses/buildComments`，按页面自身调用登记参数（`id=<mid>`、`is_reload=1`、`is_show_bulletin=2`），并**计入显式接口调用**，不自造批量抓取。

## 6. 未做

未读/打印 cookie 值；未对真实页面截图；未重试、未换词；未改账本补额度；未改业务库/CSV/契约/小红书；未提交 git。守卫五哈希未变。
