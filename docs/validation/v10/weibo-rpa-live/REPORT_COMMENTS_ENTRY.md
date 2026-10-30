# weibo-rpa-20：comments 入口首次真实取评论（数据拿到了，结算写账本有 bug）

> **v11 注记（2026-10-30）**：本文是**历史快照**。文中「`records_cap=5` < 38 条 → 被拒 / 改为截断 / 需把 cap 提到 ≥40」均为 **v10 当时行为**；
> v11 起记录数改为**软目标**，超出只标记 `over_cap/over_by`，**不再拒绝、不再截断、记录一条不丢**。


- 时间：2026-10-30T07:57–07:58Z（UTC）；cwd `D:\桌面\two`；解释器 `C:\Users\19183\.dsh\tools\x-collect\venv\Scripts\python.exe`。
- 一句话：**评论真的取到了** —— 一次调用拿到 **20 条顶层 + 18 条子回复 = 38 条**，`total_number=147`，`max_id` 非空（可翻页），父子关系正确；但 CLI 退出码是 **6**，原因是两个账本侧 bug：`RESULT_EVENTS` 里没有 `comments`（→`result_write_failed`）和 `records_cap=5` 小于 38 条（→`reserve_refused`）。两处都已修，但本批只剩 1 次调用，凑不齐"导航+取评论"两步，**没有重跑**。

## 1. 离线实现（验收 1–3）

| 件 | 内容 |
| --- | --- |
| `rpa/comments.py` | `page_url(mid, count, max_id, flow)` 生成页面自身端点 URL（`/ajax/statuses/buildComments`，参数 `is_reload=1&id=<mid>&is_show_bulletin=2&is_mix=0&count=N&fetch_level=0&locale=zh-CN`，翻页追加 `max_id`+`flow`）；`parse_page(payload)` 解析为统一记录；`merge_pages` 去重合并 |
| 记录字段 | `comment_id / parent_id / author / text / text_len / published_at / like_counts / root_comment_id / floor`；顶层 `parent_id=null`，子回复 `parent_id=父评论 id` |
| `cli.cmd_comments` | `comments --mid <id> --limit N [--max-pages K]`：预扣 `active_nav`（详情上下文）→ 每次取页前预扣 `comments`（`MIN_INTERVAL=15s` 等 16s 重试一次）→ 页面内 `fetch` 同源端点 → 解析 → `reserve_records` → 落盘；响应原文**不落盘** |
| `session.fetch_json` | 页面内 `fetch(credentials:'include')`，只回 `{status, json, text_len}` |

单测 `CommentParseTests`（6 例）：单页多条（含 `<a>` 清洗）、子回复 `parent_id`/`root_comment_id`、`total_number>本页`（有翻页）、`max_id` 空（无更多）、`ok=false`/空 `data`、URL 参数。RPA **167 OK**；四套 **402 OK**（`logs/tests-all-comments-entry.log`），无跳过。

## 2. 真实调用（weibo-rpa-20，mid=5348595884891806）

| 项 | 值 |
| --- | --- |
| 批次 | `authorized_calls=5`（2 seed + 导航 1 + buildComments 1~2）、`records_cap=5` |
| argv | `python -X utf8 -m tools.selection.rpa comments --profile … --batch-id weibo-rpa-20 --mid 5348595884891806 --limit 20 --max-pages 1 --out …\logs\comments-rpa20.jsonl` |
| HTTP | **200**、响应 **155,275 B**、`ok=true` |
| 本页 | **20 条顶层 + 18 条子回复 = 38 条** |
| `total_number` | **147** |
| `max_id` | **138895085386350**（非空 → 可翻页） |
| exit / stop / status | **6** / `result_write_failed` / `reserve_refused` |

### 逐条（前 8 条，正文只给长度 + 前 30 字）

| comment_id | parent_id | 作者 | 长度 | 前 30 字 | 时间 | 赞 |
| --- | --- | --- | --- | --- | --- | --- |
| 5348595939157490 | null | 校园活动君 | 116 | 太痛苦了，父母嘴上说着不要有压力好好备考，实际上过几天一个电话就… | Tue Sep 29 21:21:47 2026 | 1890 |
| 5349265727554676 | 5348595939157490 | Zaynie0905Moli | 3 | 知己啊 | Thu Oct 01 17:43:17 2026 | 37 |
| 5350024959496095 | 5348595939157490 | 阿狸小队长 | 36 | 不要失去美好的愿景，撑过去了考上了就有解了。当然人生也不是只有考研… | Sat Oct 03 20:00:12 2026 | 15 |
| 5348596060784726 | null | 社畜青年李大嘴 | 69 | 如果有几个比你优秀的表姐表哥表弟更是天崩了，跟我差不多同龄的，我考研… | Tue Sep 29 21:22:16 2026 | 762 |
| 5348773293460499 | 5348596060784726 | 徐徐2940 | 33 | 我就输身边近亲都上岸了。只有我没上岸。我爸妈对我就是横竖看不顺眼。 | Wed Sep 30 09:06:31 2026 | 78 |
| 5348843589206110 | 5348596060784726 | nzbdhiwiwbwhwkn | 33 | 表哥考编、他对象考编都毕业即上岸 ，今年结婚买房一条龙了[淡淡的] | Wed Sep 30 13:45:50 2026 | 38 |
| 5348771083061584 | null | 天下谁人不识猫- | 27 | 别信，有时候待在家考公考研要比盲目找工作随便干好得多 | Wed Sep 30 08:57:44 2026 | 336 |
| 5348855408495600 | 5348771083061584 | 孙悟空超级无敌粉丝 | 36 | 唉，有的家庭里的父母真的很难理解孩子的处境，只会责怪孩子为什么老在… | Wed Sep 30 14:32:49 2026 | 127 |

（其余 30 条同结构，均在 `logs/step45-comments-rpa20.json` 的 `pages[0].records` 中；`floor` 字段部分有值：1/2/3/4/5/9/16/20/21/23/30/33/44/53/56/76/90/103/108。）

## 3. 两个账本侧 bug（已修，未重跑）

1. **`RESULT_EVENTS` 缺 `comments`** → `record_result` 抛 `unknown_result_kind` → `_settle` 把结果改写成 `result_write_failed`（exit 6），即使数据已取到。**已加 `"comments": "comments_result"`**。
2. **`records_cap=5` < 38 条** → `reserve_records` 被拒（`reserve_refused`）。**已改为按 `records_cap` 截断**（`kept_records`/`truncated` 会如实报出）。

修完 `tests.test_selection_rpa` **167 OK**、四套 **402 OK**。**没有重跑**：本批只剩 1 次调用（`used=4/5`），而一次 comments 需要"导航 1 + 取页 1"两步。

## 4. 结论（验收 6）

| 问题 | 回答 |
| --- | --- |
| 评论能力能否登记为实测可用 | **可以（数据层面）**：真实端点返回 200、38 条记录、字段齐全、父子关系正确；但**结算路径还没跑出 exit 0**，需一次干净重跑才能说"端到端可用" |
| 子回复是否真的拿到 | **是**：18 条 `parent_id` 非空，全部指向同页的顶层评论（`root_comment_id` 一致） |
| 翻页是否可用 | **是（可翻）**：`max_id=138895085386350` 非空；`flow` 参数已在 `page_url` 里预留，尚未真实验证第 2 页 |
| 首屏条数 | 一次 20 条顶层（+18 子回复），`total_number=147` |
| 具体停止点 | 结算阶段：`result_write_failed`（已修）+ `reserve_refused`（已修，改为截断） |

## 5. 账本

| 事件 | UTC | source | detail |
| --- | --- | --- | --- |
| `active_nav`（详情上下文） | 07:57:56Z | rpa.comments | detail |
| `comments`（第 1 页） | 07:58:14Z | rpa.comments | page1 |

`used=4/5`、`remaining=1`、`records_reserved=0`、`locked=false`（没有 `comments_result` 事件，正是 bug 1 的表现）。

## 6. 下一步建议

1. 用**新批次**跑一次干净的 `comments --mid 5348595884891806 --limit 20 --max-pages 2`，确认 exit 0、`comments_result=success`、`kept_records=5`（受 cap）与第 2 页 `max_id` 生效。
2. ~~若要保留全部 38 条，需要账本 `records_cap` 提到 ≥40（当前 `MAX_RECORDS=5`）。~~ **v11 已改**：38 条全部保留，只回报 `over_cap/over_by`（默认目标 5），无需再提 cap。
3. 之后再把 comments 接进统一导出（记录已含 `comment_id/parent_id/author/text/published_at/like_counts`，与 `records.FIELDS` 的映射需再定：`parent_id` 已有，`likes` 可映 `like_counts`）。

## 7. 未做

未读/打印 cookie 值；未对真实页面截图；未重试、未换词；未改账本补额度；未改业务库/CSV/契约/小红书；未提交 git。守卫五哈希未变。
