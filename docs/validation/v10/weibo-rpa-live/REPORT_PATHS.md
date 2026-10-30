# 三条评论路径 + 详情页 surface 修复：都拿到 0 条，但样本本身可能就是 0 评论

- 时间：2026-10-30T07:43–07:44Z（UTC）；cwd `D:\桌面\two`；解释器 `C:\Users\19183\.dsh\tools\x-collect\venv\Scripts\python.exe`。
- 一句话：**详情页 exit 4 误判已修（surface=detail → exit 0）；三条路径（`?type=comment`+滚动、移动端页面、桌面详情页滚动）全部 exit 0、`text_len` 2355/2182/2355，但评论条目都是 0、网络钩子一条请求都没捕到。交叉验证显示这条微博本身 `comments=0`（weibo-rpa-13 已解析出 position 来源的 0），所以本轮更可能是样本问题。**

## 1. 详情页 surface 修复（验收 1）

| 变更 | 说明 |
| --- | --- |
| `probe.surface_of(url)` | `weibo.com/<uid>/<bid>` 或 `m.weibo.cn/status/<id>` → `detail`，其余 → `search` |
| `probe.verdict()` | `detail`：`text_len ≥ 100` 或评论条目 > 0 → **exit 0**；否则 `EXIT_EMPTY(3)` + `detail_empty`（**不再** `no_cards`）；`search` 仍按卡片数判定 |
| 输出 | `summary.surface = detail\|search` |

单测 `SurfaceVerdictTests`（5 例）：surface 识别、详情页有正文→ok、详情页有评论→ok、详情页空→exit 3、搜索页仍按卡片。
结果：RPA **155 OK**；四套全量 **390 OK**（`logs/tests-all-surface.log`），无跳过。

## 2. 三条路径（weibo-rpa-17，同一批次）

| 路径 | URL | 动作 | exit | surface | text_len | 评论条目 | 容器 | 捕获请求 | comment_like |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| **A** | `https://weibo.com/3271525130/RoB0gpMsP?type=comment` | `--scroll 3` | **0** | detail | 2355 | **0** | `{}` | **0** | 无 |
| **B** | `https://m.weibo.cn/status/5358621166144499`（移动 UA） | `--scroll 3` | **0** | detail | 2182 | **0** | `{}` | **0** | 无 |
| **C** | `https://weibo.com/3271525130/RoB0gpMsP` | `--scroll 3`（3 段 scrollTo） | **0** | detail | 2355 | **0** | `{}` | **0** | 无 |

- 三条路径**都没有登录墙/验证码**（`wall_markers=[]`）。
- 三条路径 `network.count=0`：钩子装上后页面**一条微博域请求都没发**（含滚动到页面底部），说明这三条路径都没有触发评论加载。
- 每次调用之间按 `MIN_INTERVAL=15s` 等待（A→B→C 各间隔 16s）。
- 账本：`active_nav` 07:43:07Z / 07:43:40Z / 07:44:01Z，三次 `active_nav_result` 全 `success`；`used=5/5`、`remaining=0`。

## 3. 交叉验证：这条微博大概率真的 0 评论（验收 5、6）

用我们**已经验证过的**互动解析回查 weibo-rpa-13 的同一条记录（mid `5358621166144499`）：

```
{"native_id":"5358621166144499","comments":0,"reposts":0,"likes":0,
 "count_source":{"comments":"position","reposts":"position","likes":"position"},
 "missing":["parent_id","title","voteup"]}
```

`count_source=position` 表示这三个值来自 `ul>li` 的真实位置解析（rpa-13 已验证可用），即：**这条微博的评论数就是 0**。

所以本轮的"三条路径都拿不到评论"更可能是**样本问题**：一个 0 评论的帖子，无论走哪条路径都不会渲染出评论列表，也自然不会有评论 XHR。

## 4. 结论（验收 5，含缺什么）

| 问题 | 结论 |
| --- | --- |
| 哪条路径有效 | **无法判定**（三条都是 0 条、0 请求；样本本身 0 评论，路径未被真正检验） |
| 评论端点与参数名 | **仍未观测到** |
| 首屏能拿多少条 / 翻页参数 / 子回复表示 | **未知** |
| 缺什么 | ①一条**确实有评论**的微博（样本）；②一次能观测到页面自身评论请求的审计；③移动端页面的评论容器选择器可能不同，需拿到真实 DOM 才能定 |

**验收 6 的"换一条有评论的微博再试 1 次"没做成**：本批次 5 次调用已用尽（2 seed + 3 路径），无法再加第 4 条路径。这一点如实记录，不假装做过。

## 5. 下一步建议（需新批次）

1. **先选对样本**：用已验证的 `live-search` 找一条 `comments > 0` 的帖子（rpa-13 那 5 条全是 0 评论，需换关键词或翻页）。
2. 拿到有评论的 mid 后，先跑桌面详情页 + `--scroll 3 --audit-network --dump-comments`；若 `network.count>0` 且出现 `buildComments`/`comments` 类 path，即锁定端点。
3. 若桌面仍无请求，再试移动端（移动页评论常直出 DOM），但**先用 `--dump-comments` 确认容器选择器是否匹配**（必要时把 `comment-item` 之外的候选 class 也纳入）。
4. 只有确认端点后，才把"评论抓取"登记为能力；在此之前评论仍是**未验证**。

## 6. 未做

未读/打印 cookie 值；未对真实页面截图；未重试、未换词；未改账本补额度；未改业务库/CSV/契约/小红书；未提交 git。守卫五哈希未变。
