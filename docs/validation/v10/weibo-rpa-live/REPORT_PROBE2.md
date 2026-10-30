# weibo-rpa-7 桌面搜索侦察（probe，`--keyword`）：入口确认可用，ID 选择器需要换

- 时间：2026-10-30T06:34:11Z 起（UTC）；cwd `D:\桌面\two`；解释器 `C:\Users\19183\.dsh\tools\x-collect\venv\Scripts\python.exe`。
- 一句话：**`requested_url` 与 `final_url` 完全一致（`q` 不再丢失）**，桌面入口 `s.weibo.com` 渲染出 **10 张结果卡片**，`p.txt/a.name/div.from/div.card-act` 都命中；但 **`a[href*="/status/"]` = 0**、`img.avator`/`.card-comment` = 0 —— 现行 `CARD_JS` 的 ID 来源在桌面版上不成立。

## 1. argv 吃参问题已消除（验收重点）

| 项 | 值 |
| --- | --- |
| argv | `python -X utf8 -m tools.selection.rpa probe --profile C:\Users\19183\.dsh\tools\weibo-collect\profile --batch-id weibo-rpa-7 --keyword "学习计划模板"` |
| `requested_url` | `https://s.weibo.com/weibo?q=%E5%AD%A6%E4%B9%A0%E8%AE%A1%E5%88%92%E6%A8%A1%E6%9D%BF&typeall=1&suball=1` |
| `final_url` | **与 `requested_url` 完全相同** |
| 结论 | 之前两次"参数消失"是**命令行 `&` 截断**，不是服务端重定向；`--keyword` 由 CLI 内部 `urlencode` 拼 URL 后已解决 |

## 2. 选择器计数表（10 项，真实页面）

| 选择器 | 计数 | 判读 |
| --- | --- | --- |
| `div.card-wrap` | **10** | 结果卡片外层存在，一页 10 条 |
| `div.card` | **10** | 内层卡片与外层 1:1 |
| `p.txt` | **19** | 正文段落命中（10 张卡共 19 段，含转发展开） |
| `a.name` | **10** | 作者链接命中 |
| `div.from` | **10** | 时间/来源行命中 |
| `div.card-act` | **10** | 互动区命中（转发/评论/赞在里面） |
| `a[href*="/status/"]` | **0** | ❌ 桌面版**不用** `/status/<id>` 这种 href |
| `a[href*="s.weibo.com"]` | **1** | 只有 1 个站内绝对链接（不足以做 ID 源） |
| `img.avator` | **0** | ❌ 这是移动版 class，桌面版没有 |
| `.card-comment` | **0** | ❌ 同上，桌面版没有 |

其它字段：`http_status=200`、`text_len=2435`、`title=微博搜索`、`ready=complete`；
`wall.markers=[]`、`login_wall=[]`（**没有**登录墙/验证码）；`status_ids=[]`（没有 `/status/` 链接，自然为空）。
`desktop`：`window_title_matches_page=true`、`topmost_set=true`、`foreground_matched=true`。

## 3. 结论：桌面入口可用，但 CARD_JS 必须换 ID 源

1. **入口**：`https://s.weibo.com/weibo?q=…&typeall=1&suball=1` 真的渲染结果卡片（10 张、正文 2435 字、无墙）——**移动版 `m.weibo.cn` 可以彻底弃用**（保留代码即可）。
2. **可用选择器**：`div.card-wrap`、`div.card`、`p.txt`、`a.name`、`div.from`、`div.card-act`。
3. **不可用**：`a[href*="/status/"]`、`img.avator`、`.card-comment`。
4. 因此 `CARD_JS` 现在"按 `/status/<id>` 找卡"在桌面版必然 0 条 —— 这正是搜索一直空的原因（不是登录态、不是墙）。

## 4. CARD_JS 改法建议（下一步）

```
容器：  div.card-wrap（外层，10 个）→ 内部 div.card
ID：    div.card-wrap[mid] 或 [mid] 属性（微博桌面版的 mid 就是 status id），
        退路：a[href*="//weibo.com/"] 里的 /<uid>/<bid> 段
正文：  p.txt（合并同一卡内的多段）
作者：  a.name
时间：  div.from 的可见文本
互动：  div.card-act 内文本里的「转发 N / 评论 N / 赞 N」
不要用：a[href*="/status/"]、img.avator、.card-comment
```

**先补侦察再改**（建议，仍只 1 次）：下一批 probe 增加三个选择器/属性统计
`div.card-wrap[mid]`、`a[href*="//weibo.com/"]`、`a[href*="/detail/"]`，并给出每张卡的 `mid` 是否存在（只报布尔/计数，不落 id 值以外的正文）。确认 `mid` 命中后，再把 `CARD_JS` 的 ID 源切到 `mid`，随后才跑真正的 1 次 `live-search`。

## 5. 账本（只读复核）

| 事件 | UTC | source | detail |
| --- | --- | --- | --- |
| `active_nav`（预扣） | 2026-10-30T06:34:11Z | **rpa.probe** | probe |
| `active_nav_result` | 2026-10-30T06:34:15Z | **rpa.probe** | success |

`used=3/3`、**`remaining=0`**、`records_reserved=0`、`locked=false`；窗口 06:34:11Z→06:39:11Z。

## 6. 离线端到端冒烟（返工要求，先于真实额度）

`checks/probe_smoke.py`：本地 fixture + **真实 Chrome（local 模式，DNS 全不解析 + CDP 封 http/https/ws/wss）**，patch `cli._open_ledger`（stub）与 `cli._new_session`（`open_live` → `open_local(fixture)`），**真正执行 `cli.main(["probe", …])`**：

```
{"all_pass": true, "exit": 0,
 "counts": {"a_name":2,"card":2,"card_act":2,"card_comment":2,"card_wrap":2,
            "div_from":2,"img_avator":2,"p_txt":2,"s_weibo_links":4,"status_links":2},
 "requested_url": "file:///…/checks/fixtures/probe-all.html",
 "final_url": "file:///…/checks/fixtures/probe-all.html"}
```

断言：exit=0、10 个 counts 全 ≥1、stdout **不含正文标记**（`正文标记-不应出现在输出里`）、`requested_url` 存在。产物：`logs/probe-smoke.json`、`logs/probe-smoke.stdout.log`。

**这条冒烟正是上一轮缺的东西**：它会在花真实额度前把 `AttributeError`（`session.html` 不存在）抓出来。第一次跑它还抓到了 stub 缺 `audit()` 导致的 `result_write_failed`。

## 7. 测试

- 单测把原来"只查源码字符串"的断言换成**真正执行 `cmd_probe`**：`ProbeRuntimeTests`（`--keyword` 拼 URL、输出含 counts、输出不含正文、`--url`/`--keyword` 互斥）；
- 新增 `VisibleSession.html` 存在性断言；
- `tests.test_selection_rpa` **124 tests OK**；四套全量 **359 tests OK**（`logs/tests-rpa-probe2.log`、`logs/tests-all-probe2.log`），无跳过。

## 8. 未做

未读/打印 cookie 值；未对真实页面截图；未重试、未换词；未改账本补额度；未改业务库/CSV/契约/小红书；未提交 git。
