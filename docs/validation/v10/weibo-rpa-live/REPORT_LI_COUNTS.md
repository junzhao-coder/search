# weibo-rpa-13：按 ul>li 位置解析互动字段 —— 真实页可用

- 时间：2026-10-30T07:29:11Z 起（UTC）；cwd `D:\桌面\two`；解释器 `C:\Users\19183\.dsh\tools\x-collect\venv\Scripts\python.exe`。
- 一句话：**互动字段终于读通了。** 5 条记录全部 `count_source=position`、无互动字段进 `missing`；4 条是 `0/0/0`（真实零），2 条是 `0/0/1`（赞=1），与 weibo-rpa-12 的结构画像完全吻合（13 个 li 只有标签、2 个位置 2 的 li 是纯数字）。

## 1. 解析重写（验收 1–3）

`session.DESKTOP_CARD_JS` 的互动部分整体替换：

| 规则 | 实现 |
| --- | --- |
| 取值位置 | `div.card-act > ul > li`，**位置即类型**：`li[0]=reposts`、`li[1]=comments`、`li[2]=likes` |
| li 存在且含数字 | 取该数字；`1.2万` → `12000`，保留 `unit="万"` 与 `raw` |
| li 存在但无数字 | **记 0**（真实零） |
| li 不存在（`items<3`） | `null` + 写入 `missing` |
| 多个数字 | `count_source="ambiguous"`，值留 `null`，**不猜**（保留 `text_len`） |
| `count_source` | `position`（li 存在）/ `absent`（li 缺失）/ `ambiguous`（形态异常） |

明确**不按标签识别**（已证实计数 >0 时标签会消失、li 变成纯数字）。
同时修掉一个自身缺陷：原先先 `replace(/\s+/g,'')` 再匹配，会把 `12 13` 并成 `1213`；改为先按空白切 token 再找数字。

## 2. 离线六类 fixture（真实 Chrome、local 模式封网）

`checks/li_counts_check.py` + `checks/fixtures/li-{a..f}.html`：

| fixture | 场景 | reposts | comments | likes | count_source | unit | missing(互动) |
| --- | --- | --- | --- | --- | --- | --- | --- |
| a | 三项都有非零 | **12** | **3** | **45** | position×3 | – | 无 |
| b | 全 0（三个 li 只有标签） | **0** | **0** | **0** | position×3 | – | 无 |
| c | 只有赞非零（模拟真实页） | **0** | **0** | **1** | position×3 | – | 无 |
| d | items 只有 2 个 | **7** | **2** | **null** | position/position/**absent** | – | `likes` |
| e | 带单位 `1.2万` | **12000** | **0** | **0** | position×3 | **万** | 无 |
| f | 一个 li 含多个数字 | **null** | **0** | **0** | **ambiguous**/position/position | – | `reposts` |

`all_pass=true`，产物 `logs/li-counts-check.json`。

## 3. 回归（验收 5）

| 检查 | 结果 |
| --- | --- |
| `tests.test_selection_rpa` | **138 tests OK**（新增 `test_ambiguous_count_is_null_not_guessed`） |
| 四套全量 | **373 tests OK**（`logs/tests-all-li.log`），无跳过 |
| `counts_check` | exit 0（fixture 已改为 ul>li 结构） |
| `desktop_extract_check` | exit 0 |
| `live_search_smoke` | exit 0 |
| `probe_smoke` | exit 0 |
| `li_counts_check`（新） | exit 0 |

## 4. 真实搜索（weibo-rpa-13）

| 项 | 值 |
| --- | --- |
| 批次 | `authorized_calls=3`（2 seed + search 1）、窗口 07:29:11Z→07:34:11Z，note 按验收原文 |
| argv | `python -X utf8 -m tools.selection.rpa live-search --profile C:\Users\19183\.dsh\tools\weibo-collect\profile --batch-id weibo-rpa-13 --keyword "学习计划模板" --allow-live --limit 5 --out …\logs\records-rpa13.jsonl` |
| exit / status | **0** / `records` |
| `count` / `cards_in` / `rejected` | **5** / **9** / `{}` |
| `requested_url` / `final_url` | **完全一致**（`s.weibo.com/weibo?q=…&typeall=1&suball=1`，未重定向） |

### 逐条记录

| # | 内容ID | 作者 | 正文长度 | 时间 | 转发 | 评论 | 赞 | count_source | unit | missing | 链接 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 0 | 5359668689110768 | 秋津日语新区校 | 148 | 今天10:40 来自 微博网页版 | **0** | **0** | **0** | position×3 | – | parent_id,title,voteup | https://weibo.com/7628996448/Rp2fOCe7S |
| 1 | 5359392368101832 | 琳琳4996 | 147 | 10月29日 16:22 来自 微博网页版 | **0** | **0** | **0** | position×3 | – | parent_id,title,voteup | https://weibo.com/5036166994/RoV48xZEI |
| 2 | 5359037006744647 | 芙因佑心聆 | 142 | 10月28日 16:50 来自 牛与嘻超话 | **0** | **0** | **1** | position×3 | – | parent_id,title,voteup | https://weibo.com/7787227625/RoLOYsiAD |
| 3 | 5358621166144499 | 双色球摩斯密码 | 149 | 10月27日 13:18 来自 vivo S30 | **0** | **0** | **0** | position×3 | – | parent_id,title,voteup | https://weibo.com/3271525130/RoB0gpMsP |
| 4 | 5358608282026807 | ACCA郭老师 | 140 | 10月27日 12:27 来自 ACCA超话 | **0** | **0** | **1** | position×3 | – | parent_id,title,voteup | https://weibo.com/7500830432/RoAFu8vgr |

**与结构画像完全吻合**：rpa-12 的 probe 里 15 个 li 中 13 个只有标签、2 个（位置 2）是纯数字 → 本轮正好得到 13 个 0、2 个 1。

## 5. 结论：能否登记为"真实页实测可用"（验收 7）

| 能力 | 状态 |
| --- | --- |
| 正文/作者/时间/链接 | **实测可用**（5/5） |
| 互动字段（转发/评论/赞） | **本轮实测可用**：5/5 条都有 `position` 来源的三个值，无互动字段进 missing |
| "0" 的可信度 | 有证据：li 存在但只有标签 = 0；13 个 li 属此类，且与 probe 结构一致 |
| 非零转发/评论 | **仍未采样到**（本页转发/评论全是 0），所以"非零时 li 文本形态"仍属推断 |

**结论**：互动字段可以登记为"真实页实测可用（含 0 的判定）"，但要带两条限定：
1. 非零的**转发/评论**样本尚未出现，取值逻辑靠位置+首个数字，理论上成立但缺实证；
2. 只覆盖单关键词、单页、5 条记录。

## 6. 账本

| 事件 | UTC | source | detail |
| --- | --- | --- | --- |
| `search`（预扣） | 2026-10-30T07:29:11Z | rpa.search | search |
| `search_result` | 2026-10-30T07:29:14Z | rpa.search | **success** |

`used=3/3`、`remaining=0`、`records_reserved=5`、`locked=false`。

## 7. 未做

未读/打印 cookie 值；未对真实页面截图；未重试、未换词；未改账本补额度；未改业务库/CSV/契约/小红书；未提交 git。
