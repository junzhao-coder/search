# missing 语义修复：「不适用」与「未读到」拆开

- 时间：2026-10-30T08:10Z（UTC）；纯离线，零网络、零额度。
- 一句话：**记录结构新增 `not_applicable`**，结构性缺项（顶层评论的 `parent_id`、评论的 `reposts/comments`、帖子的 `root_comment_id`）不再写进 `missing`；`missing` 只表示"该有但没读到"。

## 1. 规则

| 字段 | 归属 | 理由 |
| --- | --- | --- |
| 顶层评论的 `parent_id` | **not_applicable** | 顶层评论本来就没有父评论；进 `missing` 会让下游误判"父关系丢失" |
| 评论的 `reposts` / `comments` | **not_applicable** | 评论本身没有转发数/子评论数（接口不提供） |
| 帖子的 `root_comment_id` | **not_applicable** | 帖子不是评论，没有根评论概念 |
| 评论的 `title` / `voteup` | **not_applicable** | 微博评论没有标题/赞同数 |
| `text` / `published_at` / `likes` / `author` 为空 | **missing** | 这些是"该有但没读到" |

## 2. 实现

- `access/records.py::make_record(..., not_applicable=())`：记录里多一个 `not_applicable` 列（排序后的字段名列表），`missing` 计算改为 `[f for f in FIELDS if record[f] is None and f not in na]`。
- `EXPORT_FIELDS` 追加 `not_applicable`（白名单内，列集合对帖子/评论一致）。
- `rpa/comments.py::to_records`：评论一律标 `reposts/comments/root_comment_id/title/voteup` 不适用，顶层评论再加 `parent_id`。
- `rpa/extract.py::_record`：帖子标 `root_comment_id` 不适用。
- 旧记录兼容：老 jsonl 没有 `not_applicable` 也能正常导出（列集合不变，新增列只在经 `make_record` 的记录上出现）。

## 3. 导出演练（用 comments-rpa21.jsonl 的 5 行真实数据重跑）

```
{"rows": 5, "columns_consistent": true, "all_parents_resolved": true,
 "zero_likes_not_missing": true, "top_level_missing_clean": true}
```

- `top_level_missing_clean=true` → **顶层评论的 `missing` 里不再出现 `parent_id`**（验收 1②）；
- `columns_consistent=true` → 评论与帖子列集合一致；
- `all_parents_resolved=true` → 子回复 `parent_id` 仍能在同批记录里找到父评论；
- `zero_likes_not_missing=true` → `like_counts=0` 不算缺失。

产物：`logs/comments-export-rpa21.jsonl`、`logs/comments-export-rpa21.check.json`。

## 4. 单测（验收 1③）

`MissingSemanticsTests` 5 例：
1. 顶层评论 `parent_id` ∈ `not_applicable`、∉ `missing`；`reposts/comments` 同理；
2. 子回复 `parent_id` 既不进 `not_applicable` 也不进 `missing`，且值等于父评论 id；
3. 真正缺字段（`text`/`published_at`/`likes`）仍进 `missing`；
4. 帖子 `root_comment_id` ∈ `not_applicable`；
5. 老 jsonl（无 `not_applicable`）导出仍可读、列集合 ⊆ `EXPORT_FIELDS`。

另外 `CommentExportMappingTests` 的列集合断言同步更新为含 `not_applicable`。

## 5. 测试

`tests.test_selection_rpa` **177 OK**；**五套全量 447 tests OK**（含 `tests.test_access_douyin`），无跳过。

## 6. 未做

未读/打印 cookie 值；未触网；未改业务库/CSV/契约/小红书；未提交 git。
