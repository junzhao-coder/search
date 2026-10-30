# 微博平台状态矩阵（收口）

> **v11 更新（2026-10-30）**：记录数**已从硬上限改为软目标**。本文第 2 节原来的「`records_cap=5` 会截断 / 保留 5 条丢弃 53 条 / `truncated=true`」是 **v10 当时的行为**，现状不再截断——
> `records_target/records_used/over_cap/over_by` 四个字段由 `reserve_records()` 返回并在 CLI 输出里透出；超过目标只标记 `over_cap=true`，**记录一条不丢**。
> **软的是存储；硬的是调用次数、15 秒间隔、单批 300 秒时长与风险即停。**


- 更新时间：2026-10-30T08:05Z（UTC）；cwd `D:\桌面\two`。
- 结论：**微博（桌面版 `s.weibo.com`）的登录、搜索、正文、互动、评论、翻页、导出 已逐项实测可用**；两条限制写在表下。

## 1. 能力矩阵（逐项实测）

| 能力 | 状态 | 证据（批次 / 报告） |
| --- | --- | --- |
| 登录（会话 cookie） | **实测可用** | weibo-rpa-4：`SUB/SUBP/SSOLoginState` 在登录窗口内由服务端下发；`REPORT_VERDICT.md` |
| 搜索（桌面入口） | **实测可用** | weibo-rpa-9/13/19：`s.weibo.com/weibo?q=…` 渲染 `div.card-wrap`，`cards_in=9~10` |
| 搜索排序（热度） | **实测可用** | weibo-rpa-19：`--sort hot` → `xsort=hot`，5 条样本 66/29/147/41/136 评论 |
| 正文 | **实测可用** | weibo-rpa-13：5/5 条正文 140–149 字（`p.txt`） |
| 作者 | **实测可用** | weibo-rpa-13：`a.name` → `author`，5/5 有值 |
| 时间/来源 | **实测可用** | weibo-rpa-13：`div.from` → `published_at` |
| 链接 | **实测可用** | weibo-rpa-13：`https://weibo.com/<uid>/<bid>`，`id_source=mid` |
| 转发数 | **实测可用** | weibo-rpa-13：`ul>li[0]`，5/5 `count_source=position` |
| 评论数 | **实测可用** | weibo-rpa-13：`ul>li[1]`；0 记 0，不写 missing |
| 赞数 | **实测可用** | weibo-rpa-13：`ul>li[2]`；0/1 与结构画像吻合 |
| 评论内容 | **实测可用** | weibo-rpa-21：`buildComments` HTTP 200、20 顶层 + 18 子回复、`exit 0`、`comments_result=success` |
| 子回复（楼中楼） | **实测可用** | weibo-rpa-21：子回复 `parent_id` 指向父评论，`root_comment_id` 一致 |
| 评论翻页 | **实测可用** | weibo-rpa-21：第 1 页 `max_id=138895085386350` → 第 2 页 `138207987459347` |
| 统一导出（帖子 + 评论同列） | **实测可用** | `comments.to_records` 映射 + 演练 `logs/comments-export-rpa21.jsonl`（5 行，列集合一致、父子全部可还原） |

## 2. 两条限制（必须随结论一起引用）

1. **记录数是软目标（v11 起）**：账本目标是 5 条，但**可以任意上调**；超出目标不再拒绝、不再截断，只回报 `over_cap/over_by`。v10 时 weibo-rpa-21 解析 58 条只保留 5 条，那是**当时的行为**，现已不成立。
2. **第 3 页起未验证**：翻页只验证到第 2 页（`max_id` 变化、两页均 200）；第 3 页及以后、以及跨页的子回复归属都还没跑过。

## 3. 统一导出字段（`records.FIELDS`）

```
native_id, type, parent_id, url, title, text, published_at, collected_at,
voteup, comments, likes, reposts, author, root_comment_id
```

- 帖子：`type=status`，`native_id=<mid>`，`reposts/comments/likes` 来自 `ul>li` 位置解析；
- 评论：`type=comment`，`native_id=<comment_id>`，`parent_id=<父评论 id>`（顶层为 `null`），
  `root_comment_id` 供跨层追溯，`likes=like_counts`，`url` 指向所属微博；
- 缺项写进 `missing`；`like_counts=0` **不算**缺失（单测 `CommentExportMappingTests` 覆盖）。

## 4. 导出演练（离线，不触网）

`checks/comments_export_drill.py` 读已落盘的 `logs/comments-rpa21.jsonl`（5 行真实数据）→
`logs/comments-export-rpa21.jsonl`：

```
{"rows": 5, "columns_consistent": true, "all_parents_resolved": true,
 "zero_likes_not_missing": true}
```

配对结果（child → parent）：

| child | parent | resolved | root |
| --- | --- | --- | --- |
| 5348595939157490 | –（顶层） | ✔ | 5348595939157490 |
| 5349265727554676 | 5348595939157490 | ✔ | 5348595939157490 |
| 5350024959496095 | 5348595939157490 | ✔ | 5348595939157490 |
| 5348596060784726 | –（顶层） | ✔ | 5348596060784726 |
| 5348773293460499 | 5348596060784726 | ✔ | 5348596060784726 |

## 5. 相关报告索引

`REPORT.md`（窗口机制）、`REPORT_VERDICT.md`（登录判定）、`REPORT_RPA9.md`（首次正文）、
`REPORT_COUNTS.md` / `REPORT_CARDACT2.md` / `REPORT_LI_COUNTS.md`（互动字段三步收敛）、
`REPORT_HOT_HOOK.md`（评论端点定位）、`REPORT_COMMENTS_OK.md`（评论端到端）、
`REPORT_COMMENTS_ENTRY.md`（映射前的原始结构）、本文件（收口矩阵）。
