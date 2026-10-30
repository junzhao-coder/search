# weibo-rpa-5 首次真实搜索：执行记录（页面未渲染出卡片，0 条）

- 时间：2026-10-30T06:22:06Z 起（UTC）；cwd `D:\桌面\two`；解释器 `C:\Users\19183\.dsh\tools\x-collect\venv\Scripts\python.exe`。
- 一句话：**搜索请求发出去了、页面 http 200、窗口侧全部正常；但 `m.weibo.cn/search` 把 `containerid` 参数丢掉并停在只有 6 个字的首屏，`cards_in=0` → 0 条记录，exit 4。这不是"没搜到"，也不是"被拦"，是页面没渲染出结果卡片。**

## 1. 授权（固定权威账本，只读复核）

| 字段 | 值 |
| --- | --- |
| `batch_id` | `weibo-rpa-5` |
| `authorized_calls` | **3**（2 seed + live-search 1） |
| `seed_used` / `seed_source` | **2** / `history:uncharged_navigation` |
| `used` / `remaining`（授权时刻） | 2 / **1** |
| `records_cap` / `window_seconds` | 5 / 300.0 |
| 窗口 | 06:22:06Z → **06:27:06Z** |
| `note` | `2 次历史追认 + live-search 1；登录已由 cookie 元数据证实，本轮只验证搜索可读性` |

## 2. live-search（06:22:06Z 同秒启动，1 次，不重试）

| 项 | 值 |
| --- | --- |
| argv | `python -X utf8 -m tools.selection.rpa live-search --profile C:\Users\19183\.dsh\tools\x-collect\profile --batch-id weibo-rpa-5 --keyword "学习计划模板" --allow-live --limit 5 --out …\logs\records-rpa5.jsonl`（profile 实际为 `C:\Users\19183\.dsh\tools\weibo-collect\profile`） |
| exit / stop / stage / status | **4** / `unknown` / `extract` / `no_records` |
| `count` / `parsed_structure` | **0** / `dom:cards` |
| `page.final_url` | **https://m.weibo.cn/search**（请求里的 `containerid=…` 被丢掉） |
| `page.http_status` / `text_len` / `title` | 200 / **6** / （空） |
| `diagnostics` | `{"cards_in": 0, "records": 0, "rejected": {}}` |
| `desktop.window_title` / `page_title` | `微博 - Google Chrome` / `微博` |
| `desktop.window_title_matches_page` / `topmost_set` | **true** / **true**（exstyle 2097416） |
| `desktop.foreground_matched` / `window_rect` | true / 1557×1491 @ (24,15) |
| `keepalive` | ticks=1、reassert_count=0、failures=0、still_foreground_at_end=true、topmost_cleared=true |
| 截图 | 无（真实页面不截图） |

原始输出：`logs/step11-search-rpa5.json`；授权：`logs/step10-authorize-rpa5.json`。

## 3. 账本

| 事件 | UTC | source | detail |
| --- | --- | --- | --- |
| `search`（预扣） | 2026-10-30T06:22:06Z | `rpa.search` | `search` |
| `search_result` | 2026-10-30T06:22:08Z | `rpa.search` | `failed` |

`used=3 / authorized=3`、**`remaining=0`**、`records_reserved=0`、`locked=false`；窗口 06:22:06Z→06:27:06Z。

## 4. 记录字段逐条（0 条 → 全部缺失）

| 字段 | 本次结果 |
| --- | --- |
| 内容 ID（native_id） | **缺失**（0 条） |
| 作者 | **缺失** |
| 正文摘要长度 | **缺失**（页面 `text_len=6`，没有卡片正文） |
| 时间 | **缺失** |
| 互动数（转发/评论/赞） | **缺失** |
| 来源链接 | **缺失**（未解析到任何 `/status/<id>`） |

## 5. 这次到底算什么（严格分类）

| 类别 | 结论 |
| --- | --- |
| 真的读到帖子正文 | **没有** |
| 只拿到链接 | **没有** |
| 被拦（403/429/验证码/登录墙/风控） | **没有**：http 200、无锁、无墙词；窗口标题正常 |
| 没搜到（页面正常渲染但结果为空） | **也不是**：`cards_in=0`、`text_len=6`、标题空 —— 页面根本没渲染出搜索结果 |
| 真实情况 | **URL/DOM 不匹配**：请求 `https://m.weibo.cn/search?containerid=100103type%3D1%26q%3D学习计划模板`，最终落到 `https://m.weibo.cn/search`（参数被丢），首屏只有 6 个字 |

## 6. 可能原因（未验证，供下一步）

1. `m.weibo.cn/search` 现在可能需要别的入口参数（如 `&page_type=searchall`、或 `containerid` 的不同拼法），或该路径是 SPA 壳、需要前端路由才渲染；
2. 桌面版搜索 `https://s.weibo.com/weibo?q=<kw>` 的 DOM 与 `CARD_JS` 假设不同（`article, div[class*='card']`）；
3. 也可以用移动端 `api/container/getIndex` 接口拿结构化数据（但那不是"可见 DOM"，需要单独评估是否算 RPA）。

这些都**没有**在本轮验证（1 次额度已用尽、不重试）。

## 7. 下一步（需决定）

1. 本轮额度已尽（3/3，窗口 06:27:06Z 关闭），要再试必须**新批次 + 新授权**。
2. 建议下一批先做**一次"URL 侦察"**（同样是 1 次导航）：分别用 `m.weibo.cn/search?containerid=…` 与 `s.weibo.com/weibo?q=…` 各开一次，记录 `final_url/http_status/text_len/title/cards_in`，确定哪个入口真的会渲染结果，再决定改 `CARD_JS` 还是改 `search_url`。
3. 在确定入口前，不建议继续消耗搜索额度。

## 8. 未做

未读/打印 cookie 值；未对真实页面截图；未重试、未换词、未追加额度；未改账本补额度；未改业务库/CSV/契约/小红书；未提交 git。
