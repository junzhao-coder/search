# weibo-rpa-11：card-act 结构画像（拿到关键结论，但 profiler 有 bug 已修）

- 时间：2026-10-30T07:19:55Z 起（UTC）；cwd `D:\桌面\two`；解释器 `C:\Users\19183\.dsh\tools\x-collect\venv\Scripts\python.exe`。
- 一句话：**真实 card-act 的直接子元素是 `ul`（每卡 1 个、无 href、无 title），数字就藏在这个 `ul` 的文本里（7–8 字、含中文、9 个里 3 个含数字），根本不在 `a` 上** —— 这解释了 rpa-10 为什么 13/15 是 `unknown`。但本轮 profiler 有层级 bug（只抓到 1 张卡、9 个 `ul` 被并到一起），已修复并补回归测试，逐卡表需要下一轮重跑。

## 1. 离线新增（`probe --dump-card-act`）

`probe.summarize_card_act(html, limit=5)`：纯 Python 解析（不依赖页面 JS，可离线单测），对最多 5 张 `div.card-wrap` 输出：

| 字段 | 含义 |
| --- | --- |
| `exists` | 该卡是否有 `div.card-act` |
| `tags` | 直接子元素标签分布（`a/span/em/i/svg` + `other`） |
| `children[]` | 每个子元素：`tag`、`classes[]`、`has_title`、`has_href`、`href_shape`（like/comment/repost/other/none）、`text_len`、`text_form`（digits/unit/chinese/empty/other）、`has_digit` |
| `act_text_len` | card-act 直属文本长度 |

**只输出结构，不输出任何正文或计数文本**（单测断言 JSON 里不含数字文本）。

## 2. 单测（离线，四类结构 + 两个回归）

| 用例 | 断言 |
| --- | --- |
| 三个纯数字 `a` | `tags={"a":3}`、`href_shape=[repost,comment,like]`、`text_form=[chinese,chinese,digits]`、`has_digit=[F,F,T]`、JSON 不含 `"12"` |
| `span`/`em` 无 `a` | `tags={"span":1,"em":1}`、`text_form=[chinese,unit]`、全部 `has_href=false`、`href_shape=none` |
| card-act 为空 | `exists=true`、`tags={}`、`children=[]`、`act_text_len=0` |
| card-act 缺失 | `exists=false`、`tags={}`、`children=[]` |
| 上限 5 张 | 7 张卡只返回 5 条 |
| **空元素不破坏层级**（回归） | 3 张卡各带 `<img>` → 仍解析出 3 张卡、每卡 1 个 `ul` |
| **每卡各取自己的 card-act**（回归） | 2 张卡 → 2 条，各 1 个 child |

结果：`tests.test_selection_rpa` **136 tests OK**；四套全量 **371 tests OK**（`logs/tests-all-cardact.log`），无跳过；`counts_check`/`desktop_extract_check`/`live_search_smoke`/`probe_smoke` 全部 **exit 0**。

## 3. 真实 probe（weibo-rpa-11）

| 项 | 值 |
| --- | --- |
| 批次 | `authorized_calls=3`（2 seed + probe 1）、窗口 07:19:55Z→07:24:55Z，note 按验收原文 |
| argv | `python -X utf8 -m tools.selection.rpa probe --profile C:\Users\19183\.dsh\tools\weibo-collect\profile --batch-id weibo-rpa-11 --keyword "学习计划模板" --dump-card-act --out …\logs\probe-rpa11.json` |
| exit / status | **0** / `cards` |
| `requested_url` / `final_url` | **完全一致**（`s.weibo.com/weibo?q=…&typeall=1&suball=1`，未重定向） |
| `cards_total`（=cards_in） | **9** |
| 选择器计数 | `card_wrap=9, card=9, p_txt=18, a_name=9, div_from=9, card_act=9, status_links=0, s_weibo_links=1, img_avator=0, card_comment=0` |

### card-act 结构画像（本轮实际输出）

| 卡 | exists | 子元素标签分布 | 子元素形态 |
| --- | --- | --- | --- |
| 0（聚合了全部 9 张卡，见 §4 bug） | true | `other(ul) × 9` | 9 个 `ul`：`class=[]`、`title=false`、`href=false/none`、`text_len` 7–8、`text_form=chinese`、其中 **3 个 `has_digit=true`** |

`act_text_len=0`（card-act 本身没有直属文本，全部文本都在 `ul` 里）。

## 4. profiler 的 bug（已修，必须说清楚）

本轮只抓到 **1 张卡**、却把 **9 个 `ul`** 都塞进了这张卡 —— 根因是 `_CardAct` 的 depth 计数被**空元素**（`<img>`、`<br>` 等）打乱：`handle_starttag` 加 1 却没有对应的 `handle_endtag`，层级永久漂移，后续卡片被当成"仍在第一张卡内部"。

修复：`VOID_TAGS` 集合 + `handle_startendtag` 直接返回，空元素不参与层级；并补了两条回归测试（`<img>` 不破坏层级、每卡各取自己的 card-act），现已 **136 项通过**。

**因此本轮"每张卡"的逐卡表不可用**；上面 9 个 `ul` 是**按文档顺序**排列的（大概率 1:1 对应 9 张卡：第 3、5、8 个含数字），但这是推断，未逐卡验证。

## 5. 结论（验收 6）

1. **互动数字在哪类子元素里**：不在 `a` 上。card-act 的直接子元素是 **`ul`**（每卡 1 个），数字与「转发/评论/赞」标签**同处 `ul` 的文本**里（`text_len` 7–8、含中文、部分含数字）。
2. **是否有 href**：`ul` 层 **无 href、无 title、无 class**；`a` 层（rpa-10 用的）文本里**没有数字** —— 两条证据互相印证，rpa-10 的 13/15 `unknown` 是必然结果。
3. **文本形态**：不是纯数字，也不是纯图标；是"标签+数字"混合的中文文本（9 个 `ul` 里 3 个带数字、6 个不带数字）。
4. **下一步解析应该从哪取值**：改为解析**每张卡自己的 `ul` 文本**，按「转发 / 评论 / 赞」标签切分取值；标签存在但无数字 → 很可能是 **0**（微博常把 0 渲染成只有标签），标签缺失 → `null`。**"标签在但无数字=0"这条还需一次真实采样确认**，不能直接写死。
5. 下一轮建议：用**修好的 profiler** 再跑 1 次 probe（同 `--dump-card-act`），拿到真正的逐卡表（每卡 1 个 `ul`、是否含数字、`li` 级结构），再决定是否下钻到 `li`/`span`。

## 6. 账本

| 事件 | UTC | source | detail |
| --- | --- | --- | --- |
| `active_nav`（预扣） | 2026-10-30T07:19:55Z | rpa.probe | probe |
| `active_nav_result` | 2026-10-30T07:19:58Z | rpa.probe | **success** |

`used=3/3`、`remaining=0`、`records_reserved=0`、`locked=false`。

## 7. 未做

未读/打印 cookie 值；未对真实页面截图；未重试、未换词；未改账本补额度；未改业务库/CSV/契约/小红书；未提交 git。输出里不含任何正文或计数原文（只有长度、形态、布尔）。
