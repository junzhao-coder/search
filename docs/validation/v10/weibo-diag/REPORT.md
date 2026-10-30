# weibo-diag：补齐微博探路三个观测缺口 + containerid 核对

- 范围：`tools/selection/access/{transport.py,diagnostics.py}`、`tests/test_access_weibo.py`、本目录。
- 触发：第 2 次探路（task-ff2fc907，已验收）暴露的三个观测缺口。
- **本轮零真实请求、不启浏览器、不登录、不装依赖、不写业务库/CSV/CONTRACT；不改风险策略与预算语义、不放宽断言。**
- 三模块回归 **158 例 rc=0**（weibo 42 / zhihu 96 / budget 20）。

## 0. 第 2 次探路的实测事实（缺口从哪来）

```
请求真发出：7s、exit=4、stop=unknown、html_bytes=34068、phase=read
readyState=complete、contentish=11、emptyish=false、wall=null   → 明确排除访客墙
anchors 13 / 0 / 13（全不匹配），但探针内部 anchorCount=0 / textLen=0
```

三处缺口：①正常路径不写 `final_url`；②`href_shapes` 从未填充（13 个被拒锚点形态未知）；③探针 DOM 与 `get_content` 的 HTML 不同步（内容取得太早）。

## 1. 缺口①：正常路径透出 `final_url` / `final_url_known`（已修）

改动前：`transport.fetch` 只在“读不到 URL”的分支写 `final_url`，成功路径的诊断里**根本没有这两个字段**，事后无从知道真正落到哪。

改动后 `transport.py:255-272`（read 阶段一次性写入）：

| 字段 | 来源 |
| --- | --- |
| `final_url` | `rec.sanitize_url(final_url)`（已知时），未知时为 `None` —— `transport.py:270` |
| `final_url_known` | `bool(final_known)` |
| 另外补 `state` / `ready_state` / `anchors_*` / `href_shapes` / `dom_anchor_count` / `render_wait_ms` / `render_wait_exhausted` | 同一处 |

运行时核验（fake tab 正常返回）：

```
final_url= https://m.weibo.cn/search | known= True | result.final_url= https://m.weibo.cn/search?containerid=x
```

> 说明：诊断里的 `final_url` 经过既有脱敏（`sanitize_url` 只保留白名单 query 键），所以 `containerid` 值被丢弃——这是**有意**的：`containerid` 里含搜索词。要判断“落到哪个页面”，host+path 足够。

## 2. 缺口②：`href_shapes` 真实填充（已修）

改动前：L1 探针只统计 site 自己的 4 个形态 + 一个 `other`，13 个被拒锚点**落在同一个桶里**，无法区分“骨架导航链接”和“异形结果链接”。

改动后：

- `transport.py:387` 给形态对象加上四个兜底类目：`other_same_origin` / `other_cross_origin` / `relative_other` / `non_http`。
- `transport.py:388-402` 分类顺序：site 的 `shape_rules`（先匹配先算）→ 空/`#`/`javascript:`/`mailto:`/`tel:`/`data:` 记 `non_http` → 有 scheme 或 `//` 开头按 host 比 `document.baseURI` 分 `other_same_origin` / `other_cross_origin` → 其余记 `relative_other`。
- 采样上限从 20 提到 **600**，并且 `anchors_total` 改为**直方图求和**（`transport.py:556` 附近），保证“各形态计数之和 == `anchors_total`”。
- `_wait_ready` 会把直方图规范化（缺的键补 0）后写回 `probe["shapes"]`，`fetch` 再写进 `diagnostics["href_shapes"]`（`transport.py:263`）。

运行时核验（13 个异形链接的 fake 页面）：

```
state= ready | total= 13 | rec= 0 | rej= 13
href_shapes= {"detail":0,"status":0,"post":0,"profile":1,"other":0,
              "other_same_origin":3,"other_cross_origin":2,"relative_other":6,"non_http":1}
sum= 13
```

这正是第 2 次探路“13 全不匹配”的形状——下一次真跑就能看出这 13 个到底是同站导航（`other_same_origin`）、跨站跳转（`other_cross_origin`）还是相对路径。

## 3. 缺口③：SPA 有界渲染等待（已修）

改动前：`readyState=complete` 且探针里 `anchorCount=0` 时，流程直接往下取内容 → 探针 DOM 与 HTML 不同步，拿到的是**未渲染**骨架。

改动后（`_wait_ready`，`transport.py:523-620`）：

| 场景 | 行为 |
| --- | --- |
| `complete` + 有识别锚点 | 立即 `state=result`（不变） |
| `complete` + 0 锚点（空壳） | **同一总 deadline 内**反复只读 L1（便宜）等待注入，上限 `RENDER_WAIT_MAX=5.0s`（`transport.py:457`），超时 → `state=unknown` + `render_wait_exhausted=True`（`transport.py:617`） |
| `complete` + 有锚点但**全不匹配** | 记 `state=ready` 并**立即返回**（这是“页面可读、形态未知”，不是“还在加载”）——第 2 次探路就是这一类，之前会被拖到超时 |
| L2/L3 只跑第一轮 | 之后每轮只重读 L1，降低 CDP 负担 |

运行时核验：

```
先空壳后注入锚点   → state= result，anchors_recognized= 2（L1 被重读 ≥2 次）
始终空壳（上限 0.3s 测试值）→ state= unknown，render_wait_exhausted= True，render_wait_ms= 530
```

`state=unknown` 时上层 `run_search` 走 `readiness_timeout`（非零），**不会**被当成“空但完成”。

> 途中踩到的坑（值得记下）：`_light_js` 里原本用 `new URL(href, location.href)` 解析相对链接，结果测试 fake 把任何含 `location.href` 的脚本都当作“取 URL”，导致探针被误判成 legacy、`anchorCount` 恒 0。已改成 `document.baseURI`（`transport.py:396`）——既是更正确的 base，也不再和 `location.href` 脚本撞车。

## 4. containerid 与入口形态核对（只核对，不下结论）

| 项 | 当前实现 | 文档记载（RESEARCH.md） | 判定 |
| --- | --- | --- | --- |
| 主机 | `https://m.weibo.cn`（`weibo.py:42`，`ALLOWED_HOST="weibo.cn"`） | 移动站路线：Xarrow“inspect mobile site which has its own API”（L31）；crawl4weibo“移动 UA + 免 cookie”（L45） | **一致方向**（移动站）；**未实测** |
| 搜索路径 | `/search?containerid=...`（`weibo.py:123-126`） | RESEARCH 只记了 Xarrow 的 **`107603+uid` 时间线 container**（L31），**没有记搜索 container** | **不同用途**：我们用 `100103` 搜索容器，文档记的是 `107603` 用户时间线容器；两者都是移动站 containerid 形态，但**搜索形态文档里没有** |
| containerid 组成 | `100103type=1&q=<keyword>` 整段 URL-encode 后作为 `containerid` 值 | 文档未见搜索容器组成 | **纯假设**，待第 3 次真跑验证 |
| 评论入口 | `/comments/hotflow?id=&mid=&max_id_type=0`（`weibo.py:129`） | RESEARCH L100：(a) 路线“移动站 JSON API”作为 comments 参考 | **假设**（路径与参数均未实测） |
| UA | 未显式设置（用 Chrome 默认可视/headless UA） | crawl4weibo 明确“mobile User-Agent” | **不一致**：我们没设移动 UA —— 可能是第 3 次真跑的一个变量，但**本轮不改**（不在验收范围，且不能靠猜改） |
| 会话 | 复用 nodriver profile（可登录态） | crawl4weibo “免 cookie 自动初始化会话” | **不同路线**：我们走登录态，文档记的是匿名初始化 |

**所有结论仍属假设**，不得因为文档写了就当成已实测；本轮没有发出任何微博请求。

## 5. 第 3 次真跑（最后一次额度）必须记录的字段

跑之前先看这些字段**是否齐全**，缺一个就别跑：

1. `requested_url` / `final_url` / `final_url_known` —— 确认真的落在 m.weibo.cn 搜索页（缺口①）。
2. `href_shapes` + `anchors_total` / `anchors_recognized` / `anchors_rejected` —— 13 个锚点到底属于哪类（缺口②）；**先看直方图再谈解析**。
3. `state` / `ready_state` / `render_wait_ms` / `render_wait_exhausted` —— 区分“未渲染”“渲染了但形态不符”“空结果”（缺口③）。
4. `probe_level` / `probe_elapsed_ms` —— 判断卡在哪一级。
5. `html_bytes` / `phase` / `elapsed_ms` / `error` —— 与第 2 次（34068B、phase=read）对比是否同型。
6. `contentish` / `emptyish` / `wall` —— 继续确认不是访客墙（第 2 次 wall=null）。

**判读顺序**：`error` 先看（有没有超时/启动失败）→ `state` → `render_wait_exhausted` → `href_shapes` → 最后才看 `count`/`stop`。

## 6. 测试与执行清单

新增 5 例（`tests/test_access_weibo.py::ObservationGapTests`）：

| 用例 | 断言 |
| --- | --- |
| `test_normal_path_reports_final_url_and_known` | 正常返回时 result 与 diagnostics 都有非空 `final_url`，`final_url_known is True` |
| `test_rejected_anchor_shapes_are_a_filled_histogram` | 13 个异形链接 → `href_shapes` 非零项与预期一致、`anchors_total=13`、`recognized=0`、`rejected=13`、**求和 == anchors_total**；并断言 L1 脚本含四个兜底类目 |
| `test_shell_then_anchors_is_read` | 空壳→注入锚点后 `state=result`、`recognized=2`、L1 被重读 ≥2 次 |
| `test_shell_that_never_renders_is_unknown_not_empty` | 始终空壳 → `state=unknown`、`render_wait_exhausted=True`、`anchors_total=0`，且在 render 上限内结束（<3s） |
| `test_render_wait_keeps_the_one_deadline` | render 上限放大到 10s、总预算 0.8s → 仍在 2s 内结束、`state=unknown`、`run_search` 非零且**不是** EXIT_EMPTY |

执行器：`docs/validation/v10/weibo-diag/run_tests.py`；清单：`execution_manifest.json`；原始输出：`logs/`。

| 模块 | start→end (UTC) | exit | 结果 |
| --- | --- | --- | --- |
| `tests.test_access_weibo` | 2026-10-27T15:22:43Z → 15:22:47Z | 0 | Ran 42 — OK |
| `tests.test_access_zhihu` | 2026-10-27T15:22:47Z → 15:22:55Z | 0 | Ran 96 — OK |
| `tests.test_access_budget` | 2026-10-27T15:22:55Z → 15:22:57Z | 0 | Ran 20 — OK |

合计 **158 例**（基线 153 + 新增 5）；argv=`<repo>\.venv\Scripts\python.exe -X utf8 -m unittest <module> -v`，cwd=`D:\桌面\two`。

## 7. 守卫（实测未变）

`instance/app.db e073f828`、`tools/workbench/runtime/workflow.sqlite3 8ae79c58`、`docs/design/CONTRACT.md 826c24cc`、`scores.csv ab0c3546`、`sources.csv 13679b60`。

## 8. 仍未验证

1. **真实页面是否真的需要渲染等待**——本轮的 shell→anchors 是 fake 场景；第 2 次探路里 `anchorCount=0` 也可能是“页面根本没有那些锚点”（HTML 有但 DOM 无），需第 3 次真跑用 `href_shapes` 区分。
2. `RENDER_WAIT_MAX=5.0s` 是**拍的值**，没有真实页面渲染时长样本；可能过长（浪费额度）或过短（误判 unknown）。
3. `100103type=1&q=` 这个搜索容器形态**未被任何文档证实**；含空格/中文关键词的编码行为也未实测。
4. 未设移动 UA，与 crawl4weibo 的记载不一致，是否需要改未知。
5. 只跑三个 access 模块，**未做全套仓库回归**。
