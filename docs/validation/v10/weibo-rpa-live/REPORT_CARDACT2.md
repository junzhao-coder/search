# weibo-rpa-12：card-act 逐卡结构表（数字在 `ul > li` 里，0 = 只有标签）

- 时间：2026-10-30T07:24:51Z 起（UTC）；cwd `D:\桌面\two`；解释器 `C:\Users\19183\.dsh\tools\x-collect\venv\Scripts\python.exe`。
- 一句话：**每张卡的 `div.card-act` 里只有 1 个 `ul`，`ul` 里固定 3 个 `li`（顺序 = 转发 / 评论 / 赞）；数字在对应 `li` 自己的文本里，`ul` 本身没有文本；计数为 0 时该 `li` 只显示标签、不含数字。**

## 1. 批次与执行

| 项 | 值 |
| --- | --- |
| 批次 | `weibo-rpa-12`，`authorized_calls=3`（2 seed + probe 1）、`seed_used=2`、窗口 07:24:51Z→07:29:51Z |
| note | `2 次历史追认 + probe 1；用户不限制额度；修好空元素层级 bug 后重跑，取逐卡 card-act 结构` |
| argv | `python -X utf8 -m tools.selection.rpa probe --profile C:\Users\19183\.dsh\tools\weibo-collect\profile --batch-id weibo-rpa-12 --keyword "学习计划模板" --dump-card-act --out …\logs\probe-rpa12.json` |
| exit / status | **0** / `cards` |
| `requested_url` | `https://s.weibo.com/weibo?q=%E5%AD%A6%E4%B9%A0%E8%AE%A1%E5%88%92%E6%A8%A1%E6%9D%BF&typeall=1&suball=1` |
| `final_url` | 与 `requested_url` **完全一致**（未重定向） |
| `cards_total`（=cards_in） | **9** |
| 本次 dump 的卡数 | **5**（profiler 上限 5；逐卡序号 0–4 对应页面第 1–5 张卡） |

## 2. 逐卡结构表（真实页面）

| 卡序号 | card-act exists | ul 数量 | ul 文本长度/形态 | li 数量 | li 位置 0（转发） | li 位置 1（评论） | li 位置 2（赞） | ul 内部标签分布 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 0 | true | 1 | len=0 / empty | 3 | len=2 chinese 无数字 | len=2 chinese 无数字 | len=1 chinese 无数字 | `other(li)×3` |
| 1 | true | 1 | len=0 / empty | 3 | len=2 chinese 无数字 | len=2 chinese 无数字 | len=1 chinese 无数字 | `other(li)×3` |
| 2 | true | 1 | len=0 / empty | 3 | len=2 chinese 无数字 | len=2 chinese 无数字 | **len=1 digits 含数字** | `other(li)×3` |
| 3 | true | 1 | len=0 / empty | 3 | len=2 chinese 无数字 | len=2 chinese 无数字 | len=1 chinese 无数字 | `other(li)×3` |
| 4 | true | 1 | len=0 / empty | 3 | len=2 chinese 无数字 | len=2 chinese 无数字 | **len=1 digits 含数字** | `other(li)×3` |

- 每个 `li` 都是 `class=[]`、`has_href=false`（互动链接不在 `li` 上，或 `li` 里只有文本节点）。
- 统计：5 卡共 **15 个 li**，**含数字 2 个（都在位置 2 = 赞）**、不含数字 13 个。
- `act_text_len`（card-act 直属文本）全为 0 —— 文本都在 `ul > li` 里。

## 3. 三个关键判定（验收 3）

| 问题 | 答案 | 证据 |
| --- | --- | --- |
| a) 数字在 `ul` 纯文本里还是 `ul` 内的 `span/li` 里？ | **在 `li` 里**（`ul` 自身 `text_len=0`、`form=empty`） | 5 张卡的 `ul` 全为 0 长度，而 `li` 有 1–2 字文本，其中 2 个 `li` 含数字 |
| b) 每个 `ul` 只含一项还是三项？ | **含三项**：固定 3 个 `li`，位置 0/1/2 分别对应转发/评论/赞 | 5 张卡全部 `items=3`，顺序一致 |
| c) 「标签存在但无数字」的 `ul` 有多少个？ | **13 个 li**（不是 ul）：3 张卡（0/1/3）三个 li 全无数字，2 张卡（2/4）只有「赞」li 含数字 | 15 个 li 中 13 个无数字、2 个有数字 |

## 4. 结论：下一步解析怎么读、0 怎么判

1. **读哪里**：读 `div.card-act > ul > li`（按位置），**不要读 `ul` 的 innerText**（它是空的），也**不要读 `a`**（rpa-10 证明 `a` 上没有数字）。
2. **按什么切三项**：**按位置**，`li[0]=转发`、`li[1]=评论`、`li[2]=赞`。**不能按标签识别**——位置 2 的 `li` 在计数 >0 时文本变成纯数字（`len=1 digits`），标签「赞」不见了（很可能是图标）。
3. **0 的表示方式**：**该位置 `li` 只有标签、不含数字** → 判为 **0**（13/15 个 li 属于这种，且与 rpa-10 中「`a` 无数字 → unknown」完全吻合）。
4. **未渲染**：该位置 `li` **不存在**（`items` 少于 3）→ 判为 `null` 并进 `missing`，**不能当 0**。
5. 取数规则建议：`li.innerText` 中匹配第一个数字（支持 `1.2万` 这类单位，保留 unit）；无数字但 li 存在 → 0；li 缺失 → null。

## 5. 仍缺的证据（如实说明）

- 本次 5 张卡的转发/评论计数**都是 0**，所以「转发/评论 **非零**时 li 文本长什么样」**没有被采样到**（是否同样变成纯数字、还是保留标签+数字）。位置判定不受影响，但数值解析要等一次含非零转发的样本才能确认（届时看 `text_form` 即可判断）。
- 只 dump 了前 5 张卡（profiler 上限），第 6–9 张未逐卡验证。

## 6. 账本

| 事件 | UTC | source | detail |
| --- | --- | --- | --- |
| `active_nav`（预扣） | 2026-10-30T07:24:52Z | rpa.probe | probe |
| `active_nav_result` | 2026-10-30T07:24:55Z | rpa.probe | **success** |

`used=3/3`、`remaining=0`、`records_reserved=0`、`locked=false`。

## 7. 本轮代码改动

`probe.summarize_card_act` 下钻一层：每个 `ul` 增加 `items[]`（`li` 的 `tag/classes/has_href/text_len/text_form/has_digit`）与 `tags`（ul 内部标签分布），并给 `ul` 增加 `labels/label_count/label_without_digit`。
顺带修掉一个自身 bug：`_close_item()` 原先往 `card["children"][-1]` 追加，但那时 `ul` 还没进 `children`，导致 `items` 恒为空 —— 改为挂到当前打开的 `self._child` 上。
单测：新增 `test_ul_items_drill_down`（3 个 li、位置 0 含数字、位置 1/2 不含），更新 `test_void_elements_do_not_desync_depth` 断言到 `items`。
`tests.test_selection_rpa` **137 OK**；四套全量 **372 OK**（`logs/tests-all-cardact2.log`）；`counts_check`/`desktop_extract_check`/`live_search_smoke`/`probe_smoke` 全部 **exit 0**。

## 8. 未做

未读/打印 cookie 值；未对真实页面截图；未重试、未换词；未改账本补额度；未改业务库/CSV/契约/小红书；未提交 git。输出里只有长度/形态/布尔，没有任何正文或计数原文。
