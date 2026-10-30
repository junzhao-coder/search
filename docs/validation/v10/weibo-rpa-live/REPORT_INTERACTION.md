# weibo-rpa-10：互动字段真实命中率复核 —— 结论是"还不能算实测可用"

- 时间：2026-10-30T07:12:44Z 起（UTC）；cwd `D:\桌面\two`；解释器 `C:\Users\19183\.dsh\tools\x-collect\venv\Scripts\python.exe`。
- 一句话：**搜索成功（exit 0、5 条记录、正文照旧读通），但互动字段 15 个槽位里 13 个 `unknown`、2 个 `type`，`position` 一次都没触发 —— 数字顺序无法证实；且同一批卡片上一轮记 `comments=1`、这一轮记 `likes=1`，说明归属还不可信。结论：互动字段目前只能算"离线可用"，不能登记为实测可用。**

## 1. 批次与执行

| 项 | 值 |
| --- | --- |
| 批次 | `weibo-rpa-10`，`authorized_calls=3`（2 seed + search 1）、`seed_used=2`、窗口 07:12:44Z→07:17:44Z |
| note | `2 次历史追认 + live-search 1；用户本轮明确授权开一批额度，验证互动字段在真实页的顺序与命中率` |
| argv | `python -X utf8 -m tools.selection.rpa live-search --profile C:\Users\19183\.dsh\tools\weibo-collect\profile --batch-id weibo-rpa-10 --keyword "学习计划模板" --allow-live --limit 5 --out …\logs\records-rpa10.jsonl` |
| exit / status / count | **0** / `records` / **5** |
| `cards_in` / `rejected` | 10 / `{}` |
| `requested_url` | `https://s.weibo.com/weibo?q=%E5%AD%A6%E4%B9%A0%E8%AE%A1%E5%88%92%E6%A8%A1%E6%9D%BF&typeall=1&suball=1` |
| `final_url` | 与 `requested_url` **完全一致**（未重定向） |
| `page` | `http 200`、`text_len=2228` |

## 2. 逐条记录（互动字段是重点）

| # | 内容ID | 作者 | 正文长度 | 时间 | reposts | comments | likes | count_source（r/c/l） | unit | missing | 链接 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 0 | 5359668689110768 | 秋津日语新区校 | 148 | 今天10:40 来自 微博网页版 | null | null | null | unknown / unknown / unknown | – | parent_id,title,voteup,comments,likes,reposts | https://weibo.com/7628996448/Rp2fOCe7S |
| 1 | 5359392368101832 | 琳琳4996 | 147 | 10月29日 16:22 来自 微博网页版 | null | null | null | unknown / unknown / unknown | – | 同上 | https://weibo.com/5036166994/RoV48xZEI |
| 2 | 5359037006744647 | 芙因佑心聆 | 142 | 10月28日 16:50 来自 牛与嘻超话 | null | null | **1** | unknown / unknown / **type** | – | parent_id,title,voteup,comments,reposts | https://weibo.com/7787227625/RoLOYsiAD |
| 3 | 5358621166144499 | 双色球摩斯密码 | 149 | 10月27日 13:18 来自 vivo S30 | null | null | null | unknown / unknown / unknown | – | 同 0 | https://weibo.com/3271525130/RoB0gpMsP |
| 4 | 5358608282026807 | ACCA郭老师 | 140 | 10月27日 12:27 来自 ACCA超话 | null | null | **1** | unknown / unknown / **type** | – | parent_id,title,voteup,comments,reposts | https://weibo.com/7500830432/RoAFu8vgr |

正文前 30 字（正文依旧读通）：`职场人急训日语口语，通用教材为什么失灵？…` / `报高顿考研课程，别被 “高端服务” 的外衣迷惑…` / `牛与嘻超话 夏风落于课桌旁…` / `宏观经济学习计划（面向业余投资人｜周期12周）…` / `ACCA超话国际课程加速计划…`

## 3. 命中率与顺序判断（验收 4）

| 指标 | 数值 |
| --- | --- |
| 互动槽位总数 | 15（5 卡 × 3 字段） |
| `count_source=position` | **0** |
| `count_source=type` | **2**（都是 likes） |
| `count_source=unknown` | **13** |
| `absent` | 0（`div.card-act` 存在） |
| 有值的字段 | 仅 `likes`（2 条，值都是 1）；`reposts`/`comments` **一次都没读到** |

**结论：数字顺序「转发→评论→赞」无法证实。** 证据是 `position` 通道一次都没触发 —— 如果 `card-act` 里真有三个纯数字链接，按位置归属必然会给出 `position`；实际情况是 13 个槽位连数字都没解析到，说明这些计数**不在可见的 `<a>` 文本里**（大概率在 `<span>`/`<em>` 里、或默认不渲染、或只有图标）。

**更值得警惕的一致性证据**：同样这两张卡（`5359037006744647`、`5358608282026807`），
- weibo-rpa-9（旧解析，带标签正则）记为 **`comments=1`**；
- weibo-rpa-10（新解析，类型优先）记为 **`likes=1`**。

同一个数字被两套解析归到了不同字段 —— 说明**归属逻辑尚不可信**，不是"顺序对不对"的问题，而是"这个 1 到底属于哪一项"还没定论。

## 4. 结论（验收 7，不夸大）

| 说法 | 是否成立 |
| --- | --- |
| 正文/作者/时间/链接已实测可读 | **成立**（5/5，与 rpa-9 一致） |
| 互动字段**离线**可用（四类 fixture 全过） | **成立** |
| 互动字段**真实页实测可用** | **不成立**：13/15 未知，仅 2 个 likes=1，且与上一轮归属冲突 |
| 「转发→评论→赞」顺序已证实 | **不成立**（position 从未触发） |

## 5. 下一步建议（需新批次）

1. **先抓结构，再改解析**：probe 增加对 `div.card-act` 的结构统计 —— 子元素标签分布（`a/span/em/i`）、每个子元素的 `class`/`title`/`href` 关键词、可见文本是否含数字、`innerText` 长度（不落正文）。拿到真实结构后，才能确定数字到底在哪个节点、顺序如何。
2. 若数字在 `<span class="...count">`：解析应从 `card-act` 的**子元素按位置**取，而不是只看 `<a>`。
3. 在拿到结构证据前，**不要把互动字段写进任何"已验证"清单**；`count_source` 字段保留，用于继续标注不确定性。

## 6. 账本

| 事件 | UTC | source | detail |
| --- | --- | --- | --- |
| `search`（预扣） | 2026-10-30T07:12:44Z | rpa.search | search |
| `search_result` | 2026-10-30T07:12:47Z | rpa.search | **success** |

`used=3/3`、`remaining=0`、`records_reserved=5`、`locked=false`。

## 7. 未做

未读/打印 cookie 值；未对真实页面截图；未重试、未换词；未改账本补额度；未改业务库/CSV/契约/小红书；未提交 git。
