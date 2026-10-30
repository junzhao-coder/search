# weibo-rpa-9：桌面搜索真实正文已读通（5 条记录）

- 时间：2026-10-30T06:51:42Z 起（UTC）；cwd `D:\桌面\two`；解释器 `C:\Users\19183\.dsh\tools\x-collect\venv\Scripts\python.exe`。
- 一句话：**修好 UA 后第一次真实搜索成功 —— 落在桌面页 `s.weibo.com`，`cards_in=10`，5 条记录全部带 `id_source=mid`、作者、正文（140–149 字）、时间、来源链接；互动字段只部分读到（2 条 comments=1，reposts/likes 为 null）。**

## 1. 执行前离线自检（验收 1，未过不动账本）

`checks/live_search_smoke.py`：本地 fixture `desktop-cards.html` + **真实 Chrome（local 模式、DNS 全不解析 + CDP 封网）**，patch 账本/会话工厂/Keepalive，**真正执行 `cli.main(["live-search", …])`** 全链路：

```
{"all_pass": true, "exit": 0, "count": 2,
 "details": [{"native_id":"4900000000000201","id_source":"mid","author":"作者甲",
              "text_len":15,"published_at":"3小时前 来自 iPhone客户端",
              "reposts":12,"comments":3,"likes":45,
              "url":"https://weibo.com/1111/Nabc201","missing":["parent_id","title","voteup"]},
             {"native_id":"Ndef202","id_source":"bid","author":"作者乙","text_len":12,
              "published_at":"昨天 12:30","reposts":0,"comments":1,"likes":2,
              "url":"https://weibo.com/2222/Ndef202"}],
 "rejected": {"bad_id": 1, "foreign_host": 1}}
```

断言：默认 UA=None、exit=0、count=2、`records_detail` 非空、`id_source∈{mid,bid}`、作者齐全、互动齐全、`rejected` 分类正确、`requested_url` 存在、正文不含「首页/登录」。
产物：`logs/live-search-smoke.json`、`logs/live-search-smoke.stdout.log`。

## 2. 真实搜索（weibo-rpa-9）

| 项 | 值 |
| --- | --- |
| 授权 | 06:51:42Z，`authorized_calls=3`（2 seed + search 1）、`remaining=1`、窗口 06:51:42Z→06:56:42Z，note=`2 次历史追认 + live-search 1；UA 默认已改桌面，验证真实正文提取` |
| argv | `python -X utf8 -m tools.selection.rpa live-search --profile C:\Users\19183\.dsh\tools\weibo-collect\profile --batch-id weibo-rpa-9 --keyword "学习计划模板" --allow-live --limit 5 --out …\logs\records-rpa9.jsonl` |
| exit / stop / stage / status | **0** / （无） / `done` / `records` |
| `count` / `cards_in` / `rejected` | **5** / **10** / `{}` |
| `requested_url` host | `s.weibo.com` |
| `page.url` host（=final） | `s.weibo.com`（**未重定向**；`page.url=https://s.weibo.com/weibo`，站点自身 pushState 去掉了 query） |
| `http_status` / `text_len` / `ready` | 200 / **2248** / `complete` |
| 落盘 | `result_persisted=true`，`logs/records-rpa9.jsonl`（5 行） |

## 3. 逐条记录（正文只给长度与前 30 字）

| # | 内容ID | id_source | 作者 | 正文长度 | 时间/来源 | 转发 | 评论 | 赞 | 链接 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 0 | `5359668689110768` | mid | 秋津日语新区校 | 148 | 今天10:40 来自 微博网页版 | null | null | null | `https://weibo.com/7628996448/Rp2fOCe7S` |
| 1 | `5359392368101832` | mid | 琳琳4996 | 147 | 10月29日 16:22 来自 微博网页版 | null | null | null | `https://weibo.com/5036166994/RoV48xZEI` |
| 2 | `5359037006744647` | mid | 芙因佑心聆 | 142 | 10月28日 16:50 来自 牛与嘻超话 | null | **1** | null | `https://weibo.com/7787227625/RoLOYsiAD` |
| 3 | `5358621166144499` | mid | 双色球摩斯密码 | 149 | 10月27日 13:18 来自 vivo S30 | null | null | null | `https://weibo.com/3271525130/RoB0gpMsP` |
| 4 | `5358608282026807` | mid | ACCA郭老师 | 140 | 10月27日 12:27 来自 ACCA超话 | null | **1** | null | `https://weibo.com/7500830432/RoAFu8vgr` |

正文前 30 字（证明真的读到了正文，不是只有链接）：
0 `职场人急训日语口语，通用教材为什么失灵？职场人赴日出差/跨国`
1 `报高顿考研课程，别被 “高端服务” 的外衣迷惑高顿课程动辄数`
2 `牛与嘻超话 夏风落于课桌旁九月的风褪去了盛夏的燥热，裹挟着`
3 `宏观经济学习计划（面向业余投资人｜周期12周） 学习目标：看`
4 `ACCA超话国际课程加速计划，通过SBR经验总结免9 PA`

缺字段（`missing`，5 条一致）：`parent_id`、`title`、`voteup`；互动里 **reposts/likes 全部 null**，comments 只有 2 条读到 `1`。

## 4. 结论：正文已读通，互动只读了一半

- **读到了正文**：5 条都取到 140–149 字的真实正文（`p.txt` 拼接），作者/时间/链接齐全，`id_source` 全部 `mid`（桌面版 `div.card-wrap[mid]` 可用）。
- **不是"只有链接"**：正文长度与摘要都能对上。
- **互动字段残缺**：`div.card-act` 里命中率低。原因很具体 —— 桌面版互动区多数是**纯数字链接**（`<a>12</a><a>3</a><a>45</a>`，没有「转发/评论/赞」字样），而当前提取用 `转发\\s*(N)` 这类**带标签**的正则，所以只有恰好带「评论 1」的卡片读到了。
- 修法（下一轮）：`card-act` 内按位置取三个 `a` 的数字（空/`转发`/`赞` 视为 0 或 null），保留标签正则作优先匹配；同时把「0 互动」与「未渲染」区分开（空文本 → null，`0` → 0）。

## 5. 账本

| 事件 | UTC | source | detail |
| --- | --- | --- | --- |
| `search`（预扣） | 2026-10-30T06:51:42Z | rpa.search | search |
| `search_result` | 2026-10-30T06:51:45Z | rpa.search | **success** |

`used=3/3`、`remaining=0`、`records_reserved=5`、`locked=false`；批次 weibo-rpa-8 的 `search_result=failed`（06:44:37Z）是上一轮移动 UA 重定向那次。

## 6. 测试与检查

- 单测：`tests.test_selection_rpa` **126 OK**；四套全量 **361 tests OK**（`logs/tests-all-rpa9.log`），无跳过。
- 离线检查：`live_search_smoke`（exit 0，2 条记录）、`probe_smoke`（exit 0）、`desktop_extract_check`（exit 0）。
- 代码补充：`live-search` 输出新增 `final_url`（与 `requested_url` 并排，便于 host 对比）。

## 7. 未做 / 边界

未读或打印 cookie 值；未对真实页面截图；未重试、未换词；未改账本补额度；未改业务库/CSV/契约/小红书；未提交 git。**不宣称"微博已整体接通"**：本轮只验证了单关键词、单页、5 条搜索结果的可读性；评论/转发/赞数量、详情页正文、翻页仍未验证。
