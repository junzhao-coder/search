# weibo-rpa-21：comments 端到端跑通（exit 0 + comments_result=success + 第 2 页翻页）

> **v11 注记（2026-10-30）**：本文是**历史快照**。文中「保留 5 条 / 丢弃 53 条 / `truncated=true` / cap=5 硬限制」均为 **v10 当时行为**；
> v11 起记录数改为**软目标**（`records_target/records_used/over_cap/over_by`），**不再截断、记录一条不丢**。软的是存储，硬的是调用次数、15 秒间隔、单批时长与风险即停。


- 时间：2026-10-30T08:02:35–08:03:11Z（UTC）；cwd `D:\桌面\two`；解释器 `C:\Users\19183\.dsh\tools\x-collect\venv\Scripts\python.exe`。
- 一句话：**干净重跑成功** —— `exit 0`、账本出现 **`comments_result(success)`**、jsonl 落盘 5 行；**第 2 页真的发出去了**（第 1 页 `max_id=138895085386350`，第 2 页 `max_id=138207987459347`，两者不同）。

## 1. 批次与执行

| 项 | 值 |
| --- | --- |
| 批次 | `weibo-rpa-21`，`authorized_calls=5`（2 seed + 导航 1 + 取页 2）、`records_cap=5`、窗口 08:02:35Z→08:07:35Z |
| note | `2 次历史追认 + 导航 1 + 取页 2；用户不限制额度；验证 comments 端到端 exit 0 与第 2 页` |
| argv | `python -X utf8 -m tools.selection.rpa comments --profile … --batch-id weibo-rpa-21 --mid 5348595884891806 --limit 20 --max-pages 2 --out …\logs\comments-rpa21.jsonl` |
| exit / status | **0** / `comments` |
| 落盘 | `logs/comments-rpa21.jsonl`（**5 行**） |

## 2. 两页实际结果（验收 3、4）

| 页 | http | bytes | 顶层 | 子回复 | `max_id` |
| --- | --- | --- | --- | --- | --- |
| 1 | 200 | 155,222 | 20 | 18 | **138895085386350** |
| 2 | 200 | 54,560 | 20 | 0 | **138207987459347**（与第 1 页不同 → 翻页生效） |

合并：`total_number=147`、**解析到 58 条**、保留 **5 条**、丢弃 **53 条**、`truncated=true`。

**截断规则（本轮已改）**：优先保留**顶层评论及其子回复**（按顶层出现顺序整组放入），而不是只留前 5 条。
本轮保留 5 条 = **2 条顶层 + 3 条子回复**（`kept_tops=2`、`kept_children=3`）。

## 3. 保留的 5 条（验收 5）

| # | comment_id | parent_id | 作者 | 长度 | 前 30 字 | 时间 | 赞 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 5348595939157490 | null | 校园活动君 | 116 | 太痛苦了，父母嘴上说着不要有压力好好备考，实际上过几天一个电… | Tue Sep 29 21:21:47 +0800 2026 | 1890 |
| 2 | 5349265727554676 | 5348595939157490 | Zaynie0905Moli | 3 | 知己啊 | Thu Oct 01 17:43:17 +0800 2026 | 37 |
| 3 | 5350024959496095 | 5348595939157490 | 阿狸小队长 | 36 | 不要失去美好的愿景，撑过去了考上了就有解了。当然人生也不是只… | Sat Oct 03 20:00:12 +0800 2026 | 15 |
| 4 | 5348596060784726 | null | 社畜青年李大嘴 | 69 | 如果有几个比你优秀的表姐表哥表弟更是天崩了，跟我差不多同龄的… | Tue Sep 29 21:22:16 +0800 2026 | 762 |
| 5 | 5348773293460499 | 5348596060784726 | 徐徐2940 | 33 | 我就输身边亲都上岸了。只有我没上岸。我爸妈对我就是横竖看不… | Wed Sep 30 09:06:31 +0800 2026 | 78 |

（jsonl 里每条还带 `root_comment_id`、`floor`、`text_len`。）

## 4. 账本（验收 3）

| 事件 | UTC | source | detail |
| --- | --- | --- | --- |
| `active_nav` | 08:02:36Z | rpa.comments | detail |
| `comments` | 08:02:55Z | rpa.comments | page1 |
| `comments` | 08:03:11Z | rpa.comments | page2 |
| **`comments_result`** | **08:03:11Z** | **rpa.comments** | **success** |

`used=5/5`、`remaining=0`、`records_reserved=5`、`locked=false`。

## 5. 结论（验收 6）

| 问题 | 回答 |
| --- | --- |
| 评论能力能否登记为**端到端实测可用** | **能**。两个硬条件都满足：**exit 0** + 账本 **`comments_result=success`**；jsonl 落盘；记录含 `comment_id/parent_id/author/text/published_at/like_counts/root_comment_id/floor` |
| 翻页是否已验证 | **已验证**。第 2 页真实发起（`comments` page2 事件），`max_id` 从 `138895085386350` 变成 `138207987459347`，两页都 200 |
| 子回复是否拿到 | **拿到**，保留的 5 条里有 3 条 `parent_id` 非空且指向保留的父评论 |
| 截断 | cap=5 硬限制：解析 58 条、保留 5 条、丢弃 53 条（`truncated=true`），规则为"顶层优先 + 其子回复" |

## 6. 仍需注意

1. ~~`records_cap=5`（`MAX_RECORDS=5`）是硬上限：一次能保留的评论永远 ≤5 条。~~ **v11 已改**：记录数是软目标，默认 5 可任意上调，超出只标记 `over_cap/over_by`，**不再截断、一条不丢**（本文顶部注记同此）。
2. 第 2 页 `child_count=0`（该页返回的都是顶层评论），符合 `flow` 分页语义；第 3 页及以后未验证。
3. 评论记录目前只在 RPA 输出/jsonl 里，**尚未映射进统一导出**（`records.FIELDS` 已有 `parent_id/comments/likes`，但 `comment_id→native_id`、`like_counts→likes` 的映射还没做）。

## 7. 未做

未读/打印 cookie 值；未对真实页面截图；未重试、未换词；未改账本补额度；未改业务库/CSV/契约/小红书；未提交 git。守卫五哈希未变。
