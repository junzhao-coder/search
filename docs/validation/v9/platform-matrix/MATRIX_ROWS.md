# V9-1a-A｜平台能力矩阵行（B站 / 微博）

> 供 `platform-matrix` 合并；仅这两行，不外推其他平台。证据均来自本轮 `PROBES.md`、`raw/`、`logs/requests.jsonl`，验证时间为 **2026-10-25T05:32:03–05:42:39Z**。
> 证据等级：`实测-可读（需 sort 参数）` / `实测-空响应` / `实测-登录墙` / `未验证`。本轮没有“全自动已验收”或高频稳定性结论。

| 平台组 | 能力/入口 | 本轮可确认字段 | 登录/访问 | 采集方式 | 本轮限速/计数 | 证据等级 | 验证时间 | 限制/下一步 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| **B站** | `GET https://api.bilibili.com/x/web-interface/view?aid=540769243`；评论第 1 页 `GET https://api.bilibili.com/x/v2/reply?type=1&oid=540769243&pn=1&ps=5&sort=2`；第 2 页同端点 `pn=2&ps=5&sort=2`；楼中楼 `GET /x/v2/reply/reply?type=1&oid=540769243&root=<rpid>&pn=1&ps=2` | view：`code=0`、`aid=540769243`、`bvid=BV11i4y147FS`、`videos=1`、`stat.reply=67`；评论 p1：`page={num:1,size:5,count:67,acount:67}`、3 条 root，`rpid=3000819542/2942044412/2943543325`，`root/parent=0`，内嵌 `replies` 数量 1/2/1；subreply：`page={num:1,size:2,count:1}`、`rpid=3005231967,root=parent=3000819542` | 无 cookie、无登录；view/评论/子回复均 200 | 直接 HTTP GET（Python stdlib；正常 UA） | 累计 7/10（1 失败尝试 + 6 成功；返工 3）；间隔 3s；未触发 -412/-352 | **实测-可读（需 sort 参数）** | 2026-10-25T05:32:03–05:42:39Z | 缺 `sort` 时同一端点 `count=0/replies=null`（假阴性，已保留）；`sort=2&pn=2&ps=5` 仍空，翻页/两页去重未成立；子回复只验证入口+1 条，深度/后续分页未验证；高频/并发/长跑未测 |
| **微博** | 公开入口尝试 `GET https://m.weibo.cn/api/container/getIndex?containerid=102803&page=1`；搜索页 `s.weibo.com` 未请求 | 未取得微博字段；仅取得 `Sina Visitor System` HTML（title、脚本/return_url），无 JSON 数据 | **需登录/访客验证**：200 后最终 URL `visitor.passport.weibo.cn/visitor/visitor?...` | 直接 HTTP GET（无 cookie、无登录） | 1 次；首请求即停；上限 5 | **实测-登录墙** | 2026-10-25T05:32:36Z | 无正文/分页字段；“是否只有第一页”未验证；未请求第 2 页或搜索页。需用户登录态或改走未验证的知乎/贴吧；不把搜索摘要当实测 |

## 合并提示

- B站行说明“公开 view 可读、加 `sort=2` 后第 1 页评论可读、子回复入口可读”，但缺 `sort` 会假阴性；第 2 页仍空，翻页/去重未成立。**不是**“B站评论已全量接入”。
- 微博行只说明“公开 API 当前被访客墙拦截”，**不是**“微博不可采集”；登录后能力未验证。
- 两行都不覆盖评论楼中楼深度、翻页上限、频率阈值、长跑/并发；不得据此宣称平台已接通。
- 原始证据：[`PROBES.md`](PROBES.md)、[`raw/bili_view.json`](raw/bili_view.json)、[`raw/bili_reply_p1.json`](raw/bili_reply_p1.json)、[`raw/bili_sort2_p1.json`](raw/bili_sort2_p1.json)、[`raw/bili_subreply_3000819542.json`](raw/bili_subreply_3000819542.json)、[`raw/weibo_feed_p1.html`](raw/weibo_feed_p1.html)、[`logs/requests.jsonl`](logs/requests.jsonl)、[`sha_manifest.json`](sha_manifest.json)。
