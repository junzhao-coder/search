# 导出补齐 reposts/author + 评论结构侦察（真实侦察未拿到评论，需下一轮）

- 时间：2026-10-30T07:35–07:37Z（UTC）；cwd `D:\桌面\two`；解释器 `C:\Users\19183\.dsh\tools\x-collect\venv\Scripts\python.exe`。
- 一句话：**导出字段补齐完成并通过测试；`probe --dump-comments` 已实现并过四类 fixture；但真实侦察没拿到评论 —— 点到的不是「评论」入口（点到的是动作栏「转发 评论 赞」），详情页初始 HTML 里 0 条评论、无墙。结论只能到"评论不在初始 DOM 里，极可能走 XHR"，具体端点未观测到。**

## 1. 导出字段补齐（验收 1，已完成）

| 项 | 变更 |
| --- | --- |
| `access/records.py` | `FIELDS` 末尾追加 `reposts`、`author`（**前 11 列顺序不变**，向后兼容） |
| `rpa/extract.py` | `_record` 写入 `reposts`/`author` 及其 `field_evidence`（`dom:card counts` / `dom:card a.name`） |
| 旧记录 | 缺这两个键时导出为 `null`，不报错（`make_record` 用 `values.get`） |
| 既有测试 | `tests/test_access_zhihu.py` 原先断言"导出不能出现 author"，已按新契约改为"author 是白名单字段、`nickname` 仍被丢弃" |

单测（`ExportFieldTests`）：新记录带 `reposts=0`/`author` 且**不**进 `missing`（0 不是缺失）；旧行（无这两键）导出成功且两列为 `null`；前 11 列顺序断言稳定。

## 2. `probe --dump-comments`（验收 2–3，已完成）

- 新增 `session.CLICK_COMMENT_JS`（一次点击，返回 `clicked/label`）与 `probe.summarize_comments(html)`：输出容器命中、条目数、作者节点数、正文节点标签分布与总长度、时间节点数、点赞节点数、展开按钮数、墙标记、空态；**不保留任何评论正文**。
- 点击前会**按账本 `MIN_INTERVAL=15s` 等待 16s 再扣费**（否则第二次扣费被 `interval_not_elapsed` 拒绝 —— 这正是 rpa-14 遇到的情况）。
- 四类 fixture 单测：多条评论（2 条、作者 2、正文 `p×2`、时间 2、点赞 1）、子回复嵌套（容器计数 ≥2）、展开更多（1 个）、空态（`empty_state=true`）、登录墙（`wall_markers` 非空）。
- 结果：`tests.test_selection_rpa` **146 OK**；四套全量 **381 OK**（`logs/tests-all-comments.log`）；`counts_check`/`desktop_extract_check`/`live_search_smoke`/`probe_smoke`/`li_counts_check` 全 exit 0。

## 3. 真实侦察（weibo-rpa-14 → weibo-rpa-15）

### 3.1 两处与验收的偏差（如实记录）

1. **`records_cap=10` 被账本拒绝**：`MAX_RECORDS=5`，`authorize_batch` 抛 `invalid_authorization: records_cap=10>5`，未建批次、未扣费。改用 `records_cap=5`（账本上限）。
2. **rpa-14 只完成了导航**：`active_nav`（07:35:37Z）扣费成功，随后 `comments` 扣费被 `platform:interval_not_elapsed` 拒绝（`MIN_INTERVAL=15s`），`used=3/4`、`remaining=1`，凑不齐"导航+点击"两次调用 → 另建 `weibo-rpa-15` 重跑（代码已加 16s 等待）。

### 3.2 weibo-rpa-15 实际结果

| 项 | 值 |
| --- | --- |
| 批次 | `authorized_calls=4`（2 seed + 导航 1 + 评论 1）、`records_cap=5`、窗口 07:36:22Z→07:41:22Z |
| argv | `python -X utf8 -m tools.selection.rpa probe --profile … --batch-id weibo-rpa-15 --url https://weibo.com/3271525130/RoB0gpMsP --dump-comments --out …\logs\probe-rpa15.json` |
| exit / stop / status | **4** / `no_cards` / `no_cards`（详情页没有 `div.card-wrap`，probe 的判定是按卡片数，属预期误判，不影响结构输出） |
| `requested_url` / `final_url` | 完全一致：`https://weibo.com/3271525130/RoB0gpMsP` |
| `page` | `http 200`、`text_len=2355` |
| `comment_click` | `{"clicked": true, "label": "转发 评论 赞"}` —— **点到的是动作栏，不是「评论」入口** |
| `summary.comments` | `items=0`、`containers={}`、`author_present=0`、`text_nodes={}`、`text_len_total=0`、`time_nodes=0`、`like_nodes=0`、`expand_buttons=3`、`wall_markers=[]`、`empty_state=true`、`text_len_after_click=2355` |

账本：`active_nav` 07:36:22Z（probe）→ 07:36:41Z（comments）→ `active_nav_result` 07:36:41Z `failed`；`used=4/4`、`remaining=0`。

## 4. 结论（验收 7，证据不足处直说）

| 问题 | 结论 | 证据 |
| --- | --- | --- |
| 评论是 DOM 直出还是 XHR？ | **不是初始 DOM**；**极可能 XHR**（未观测到请求，只能说"极可能"） | 详情页 200、`text_len=2355`，评论容器 0 命中、条目 0、正文节点 0 |
| 有没有登录墙/验证码 | **没有** | `wall_markers=[]` |
| "展开更多" | **无法确认**：`expand_buttons=3` 是 class 含 `more` 的误报 | 点击前后 `text_len` 都是 2355，说明没有展开动作 |
| 子回复如何嵌套 | **未知** | 0 条评论 |
| 该走 DOM 还是页面 XHR | **倾向页面 XHR**，但要先观测页面自身请求 | 见下 |

**下一轮建议（需要新批次）**：
1. 先修点击选择器：只点**精确文本为「评论」**的入口（排除含「转发」「赞」的动作栏），或用 `a[href*="comment"]`；
2. 用 `session.audit_network(tab)` 记录详情页自身发出的请求（域名/路径），确认是否出现 `weibo.com/ajax/statuses/buildComments` 这类端点；
3. 若确认走 XHR：按页面自身调用登记（`https://weibo.com/ajax/statuses/buildComments?is_reload=1&id=<mid>&is_show_bulletin=2`），**计入显式接口调用**，不自造批量抓取；
4. 拿到首屏评论后再判定字段（评论ID/作者/正文/时间/点赞/父评论）与"查看更多"翻页参数。

## 5. 未做

未读/打印 cookie 值；未对真实页面截图；未重试、未换词；未改账本补额度；未改业务库/CSV/契约/小红书；未提交 git。守卫五哈希未变（`app.db e073f828`、`workflow.sqlite3 8ae79c58`、`CONTRACT.md 826c24cc`、`scores.csv ab0c3546`、`sources.csv 13679b60`）。
