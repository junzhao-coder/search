# V9-1a-A｜B站与微博只读小批次实测（含 B 站返工）

> 任务：`task-0112f5bb3367632cbeb900dc299750dd`（revision 5，计划 v9）；范围仅 `docs/validation/v9/platform-matrix/`。
> 执行命令：`python docs/validation/v9/platform-matrix/tools/probe_platforms.py`（初次，见 `logs/probe_run2.log`）与 `python docs/validation/v9/platform-matrix/tools/probe_bili_rework.py`（B站返工，见 `logs/bili_rework_run.log`）。
> 实际探测：2026-10-25 13:32:03–13:32:36 与 13:42:33–13:42:39 UTC+8（05:32:03–05:32:36Z、05:42:33–05:42:39Z）。只读公开 GET；无 cookie、无登录、无发布/点赞/关注/私信、无批量翻页、无第三方采集库。
> 请求预算：B站 **累计 7/10**（1 次失败脚本 view + 3 次初次成功批次 + 3 次返工）；微博 **1/5**（未重跑）。同主机间隔 3–4 秒（`logs/requests.jsonl:1-7`；失败尝试 `logs/attempt1_requests.jsonl`）。原始响应已截断/最小脱敏并哈希，见 [`sha_manifest.json`](sha_manifest.json)。
> 方法限制：本会话无 `skill` 工具，`agent-reach` CLI 不在 PATH；使用 Python 标准库直连，未安装依赖。

## 1. B站（api.bilibili.com）

### 1.1 请求与结果（含缺参假阴性）

| # | UTC | 请求 | 状态 | 响应字节 | 耗时 | JSON code | 结果 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 0 | 05:32:03Z | `GET /x/web-interface/view?aid=540769243`（失败脚本） | **200** | 112,307 | 203 ms | 0 | 工具首次尝试；脚本随后因缺少 `risk` 键崩溃，非平台结论；raw 为 `attempt1_bili_view.json` |
| 1 | 05:32:26Z | `GET /x/web-interface/view?aid=540769243` | **200** | 112,307 | 172 ms | 0 | `aid=540769243`、`bvid=BV11i4y147FS`、`videos=1`、`stat.reply=67` |
| 2 | 05:32:29Z | `GET /x/v2/reply?type=1&oid=540769243&pn=1&ps=5`（**无 sort**） | **200** | 789 | 109 ms | 0 | **假阴性**：`page={num:0,size:0,count:0}`、`replies=null` |
| 3 | 05:32:32Z | `GET /x/v2/reply?type=1&oid=540769243&pn=2&ps=5`（**无 sort**） | **200** | 789 | 110 ms | 0 | 同样空；与 #2 同 sha |
| 4 | 05:42:33Z | `GET /x/v2/reply?type=1&oid=540769243&pn=1&ps=5&sort=2` | **200** | 50,174 | 219 ms | 0 | **可读**：`page={num:1,size:5,count:67,acount:67}`、`replies` 3 条，root rpid `3000819542` |
| 5 | 05:42:36Z | `GET /x/v2/reply?type=1&oid=540769243&pn=2&ps=5&sort=2` | **200** | 789 | 94 ms | 0 | **翻页未成立**：`page={num:0,size:0,count:0}`、`replies=0`；未出现 -412 |
| 6 | 05:42:39Z | `GET /x/v2/reply/reply?type=1&oid=540769243&root=3000819542&pn=1&ps=2` | **200** | 9,530 | 125 ms | 0 | **楼中楼入口可用**：`page={num:1,size:2,count:1}`、1 条子回复 |

- 请求日志：`logs/requests.jsonl:1-7`（#0 在 `logs/attempt1_requests.jsonl:1`；#0 与 #1 的重复 view 是失败脚本重试，不是重试轰炸）。
- raw/清洗：`raw/bili_view.json`（107,067 B，sha256 `c466f794…`）、`raw/bili_reply_p1.json`（1,162 B，`ce4de6d5…`）、`raw/bili_reply_p2.json`（同 sha）、`raw/bili_sort2_p1.json`（21,578 B，`5d26f5d2…`）、`raw/bili_sort2_p2.json`（789 B，`ae076cdb…`）、`raw/bili_subreply_3000819542.json`（4,770 B，`aa7e3e77…`）。
- 脱敏：已移除 `member.uname/handle/avatar/...` 等昵称/头像/个人简介字段，保留 `mid`、`rpid/parent/root`、正文和计数；正文中 `@用户名` 已替换为 `@u***`。

### 1.2 字段、分页、楼中楼、错误码

- **`sort=2` 是必要参数（本轮观察）**：同一端点、同一 `oid/pn/ps`，无 `sort` 时 `page.count=0`、`replies=null`；加 `sort=2` 后 `page.count=67`、返回 3 条真实评论。**缺参会造成“评论不可见”的假阴性**，这是可复用的平台坑；不等于所有请求都必须固定 `sort=2`，但本视频/本端点本轮如此。
- **page 字段**：`page.num`、`page.size`、`page.count`、`page.acount`；#4 为 `num=1,size=5,count=67,acount=67`；#5 为 `num=0,size=0,count=0`。
- **replies 字段**：#4 的 3 条 root 评论分别 `rpid=3000819542/2942044412/2943543325`，`root=0`、`parent=0`（root 评论）；`like`/`rcount`/`count` 可见；`content.message` 正文可见；`member.mid` 保留（昵称已脱敏）。
- **子回复内嵌数量**：#4 三条 root 的 `replies` 列表长度分别为 **1、2、1**；对应 `rcount/count` 为 1、2、1。
- **楼中楼入口**：#6 使用 #4 的 root `3000819542` 调 `x/v2/reply/reply`，返回 `page={num:1,size:2,count:1}`、1 条子回复：`rpid=3005231967`、`root=3000819542`、`parent=3000819542`。**只验证了入口和第一页 1 条子回复**，未验证更深层级、子回复翻页或全量深度。
- **分页/去重键**：#4 与 #5 的 `replies` 集合无交集（#5 为空）；不能用这两页建立可靠的翻页去重结论。第 2 页 `pn=2&ps=5&sort=2` 仍 `count=0`，这是一个**受限结果**；没有继续尝试其他参数（避免重试轰炸）。
- **是否需要 cookie/登录**：所有请求无 Cookie 头、无登录；`view`、`sort=2` 第 1 页、subreply 均 200。不能据此断言所有评论场景都免登录。
- **-412/-352/验证码**：**本轮未出现**；没有触发停止词。`sort` 缺失是参数问题，不是 -412。
- **停止点**：B站第 2 页空后未再追加 B 站请求；楼中楼只取第一页 `ps=2`，未递归。

## 2. 微博（m.weibo.cn / s.weibo.com）

> 本节与返工前一致；**未重跑微博**，结论保留。

### 2.1 请求与结果

| # | UTC | 请求 | 结果 |
| --- | --- | --- | --- |
| 1 | 05:32:36Z | `GET https://m.weibo.cn/api/container/getIndex?containerid=102803&page=1` | **HTTP 200，但最终 URL 为 `visitor.passport.weibo.cn/visitor/visitor?...`，HTML title `Sina Visitor System`，9,756 B** |

- 请求日志：`logs/requests.jsonl:4`；原始/清洗：`raw/weibo_feed_p1.html`（9,756 B，sha256 `e9ec4a1f…`）。
- 脱敏：未保存 cookie/token、用户昵称、主页链接；`@` 提及已替换为 `@u***`。

### 2.2 结论（逐条）

- **是否需登录/访客验证**：**是**。公开 `m.weibo.cn` API 被重定向到 `visitor.passport.weibo.cn` 的 `Sina Visitor System`；不是 JSON 数据页。
- **能取字段**：**未取得**任何微博正文、用户、时间、互动字段；只取得访客验证 HTML 壳。
- **是否只有第一页**：**未验证**。首请求即触发访客墙，按“登录墙立即停止”规则未请求第 2 页；不能推断“只有第一页”。
- **搜索页**：未继续请求 `s.weibo.com`；未用搜索摘要替代实测。
- **停止点**：第 1 次请求后立即停止微博；微博计数 **1/5**。
- **替代**：知乎/贴吧仅作为**未验证**替代入口，不声称已接入或可读。

## 3. 请求计数与安全边界

| 平台 | 请求数（含失败尝试） | 成功请求 | 上限 | 间隔 | 风险/停止 |
| --- | --- | --- | --- | --- | --- |
| B站 | **7**（1 次失败脚本 view + 6 次成功：3 初次 + 3 返工） | 6 | 10 | 05:32:03（失败）；05:32:26→29→32；05:42:33→36→39（均 ≥3s） | 无 -412/-352；评论第 2 页空，主动停止 |
| 微博 | **1** | 1 次入口（最终被重定向到访客墙） | 5 | —（首请求即停） | `Sina Visitor System` 访客/登录墙，立即停止 |

- 无 Cookie 头、无登录态、无第三方 cookie；`logs/requests.jsonl` 每条 `cookie_header_sent=false`。
- 原始响应均小于 200 KiB；`bili_view`/`attempt1` 以 compact JSON 保存，未截断；评论/子回复/HTML 均未截断。
- 只写 `docs/validation/v9/platform-matrix/`；未写业务库/工作单库/既有 CSV/源码/依赖。

## 4. 未验证项

1. B站楼中楼**深度**、子回复后续分页、全量 `rcount` 展开：只验证入口和 1 条子回复。
2. B站第 2 页/翻页去重：`sort=2&pn=2&ps=5` 返回空，未能建立两页 rpid 集合；翻页稳定性未证。
3. B站高频/并发/长跑/`-412` 阈值：只做低量 7 次请求。
4. 微博任何数据字段、第一页/第二页、搜索页：首请求即访客墙。
5. 登录后能力：未登录；不推断登录后可见内容。
6. 其他平台：未测；知乎/贴吧替代未验证。
