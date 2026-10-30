# 桌面版卡片提取 + weibo-rpa-8 真实搜索（被移动 UA 重定向，0 条）

- 时间：2026-10-30T06:44:32Z 起（UTC）；cwd `D:\桌面\two`；解释器 `C:\Users\19183\.dsh\tools\x-collect\venv\Scripts\python.exe`。
- 一句话：**桌面版提取器已按实测结构重写好并通过真实浏览器 fixture 检查**；但真实 `live-search` 仍被重定向回 `m.weibo.cn`（`live-search` 的 `--user-agent` 默认还是移动 UA），`cards_in=0`、0 条记录，exit 4。已修 UA 默认 + 加"跨域重定向"判定，**但本轮额度已被这次失败消耗，未重试**。

## 1. 按实测结构重写提取（验收 1、2）

`session.DESKTOP_CARD_JS`（新）：
- 容器 `div.card-wrap`（只取可见）；
- **ID 优先 `mid`**（纯数字，`id_source="mid"`）；无 mid 时回退卡内 `a[href]` 的 `/<uid>/<bid>`（`id_source="bid"`），同时保留 `bid` 供校验；
- 正文 `p.txt`：只取**本卡**的段落（`p.closest(card)===el`）、按顺序拼接、去重；
- 作者 `a.name`；时间/来源 `div.from`；互动取 `div.card-act` 文本里的「转发/评论/赞 N」，缺项为 `null`；
- 链接归一化为 https，且必须是**本卡自己的**链接。

`extract._check` 新增桌面分支（保留旧移动分支）：
- `id_source` 存在 → ID 允许 `[0-9A-Za-z]{5,}`；`bad_scheme`/`foreign_host` 照旧；
- `url_id_mismatch`：mid 卡要求 **bid 出现在链接路径**里，bid 卡要求 ID 本身出现在路径里；
- 其余拒绝原因（hidden/missing_keys/bad_id/no_text）保持，全部计入 `rejected`。

`extract.extract_cards` 新增 `details[]`（每条的 `native_id/id_source/author/text_len/published_at/reposts/comments/likes/url/missing`），`cmd_live_search` 把它输出为 `records_detail`。**注意**：`access/records.py` 的 `FIELDS` 不含 author/reposts（`tests/test_access_zhihu.py:781` 明确断言导出里不能出现 `author`），所以作者/转发只出现在 RPA 输出的 `records_detail`，不写进导出记录。

## 2. 离线真实浏览器检查（验收 3）

`checks/desktop_extract_check.py` + `checks/fixtures/desktop-cards.html`（5 张卡：mid 卡、无 mid 的 bid 卡、隐藏卡、跨域卡、无 id 卡），**真实 Chrome（local 模式、封网）**：

```
{"all_pass": true, "records": 2, "rejected": {"foreign_host": 1, "bad_id": 1},
 "ids": ["4900000000000201", "Ndef202"]}
details:
  [{"native_id":"4900000000000201","id_source":"mid","author":"作者甲","text_len":15,
    "published_at":"3小时前 来自 iPhone客户端","reposts":12,"comments":3,"likes":45,
    "url":"https://weibo.com/1111/Nabc201","missing":["parent_id","title","voteup"]},
   {"native_id":"Ndef202","id_source":"bid","author":"作者乙","text_len":12,
    "published_at":"昨天 12:30","reposts":0,"comments":1,"likes":2,
    "url":"https://weibo.com/2222/Ndef202","missing":["parent_id","title","voteup"]}]
```

断言全部通过：`mid_id_source`、`p_txt_joined`（两段拼接）、`author_from_name`、`time_from_div_from`、
`counts_from_card_act`（12/3/45）、`bid_fallback`、`bid_url_https`、`no_nav_text`（不含「首页/登录」）、
`no_hidden_text`、`hidden_card_not_dumped`、`foreign_rejected`、`no_id_rejected`。
产物：`logs/desktop-extract-check.json`。

## 3. 真实搜索（weibo-rpa-8）——失败，0 条

| 项 | 值 |
| --- | --- |
| 授权 | 06:44:32Z，`authorized_calls=3`（2 seed + search 1）、`remaining=1`、窗口 06:44:32Z→06:49:32Z |
| argv | `python -X utf8 -m tools.selection.rpa live-search --profile C:\Users\19183\.dsh\tools\weibo-collect\profile --batch-id weibo-rpa-8 --keyword "学习计划模板" --allow-live --limit 5 --out …\logs\records-rpa8.jsonl` |
| exit / stop / stage | **4** / `unknown` / `extract` |
| `cards_in` / `rejected` / `count` | **0** / `{}` / **0** |
| `page.final_url` | **https://m.weibo.cn/search**（而 `search_url()` 当时已返回 `s.weibo.com`；`requested_url` 字段是这次失败**之后**才加进输出的，所以本条日志里为空） |
| `http_status` / `text_len` | 200 / **6** |
| 账本 | `search` 06:44:32Z → `search_result(failed)` 06:44:37Z；`used=3/3`、`remaining=0`、无锁 |

**根因**：`live-search` 的 `--user-agent` 默认仍是 `weibo.MOBILE_UA`（移动 UA）。桌面入口 `s.weibo.com` 见到移动 UA 会**重定向到 `m.weibo.cn`**，于是又回到"壳页 6 个字、0 卡片"。

## 4. 已修复（本轮落盘）

1. `live-search --user-agent` 默认改为 **None**（浏览器自带桌面 UA）；帮助文案写明"桌面入口用移动 UA 会被重定向"。
2. `live-search` 新增**跨域重定向判定**：`requested` 与 `final` host 不同 → `exit 4 / stop=redirected_elsewhere / status=redirected`，输出 `requested_url`、`final_url`、两个 host，且**不解析、不输出记录**（不再把"被重定向"伪装成"没搜到"）。
3. 单测：`test_default_user_agent_is_desktop`、`test_redirect_to_other_host_is_flagged`；测试夹具里的 page URL 统一改成桌面入口。

## 5. 测试

`tests.test_selection_rpa` **126 tests OK**；四套全量 **361 tests OK**（`logs/tests-all-desktop.log`），无跳过。
两个离线检查均通过：`probe_smoke`（exit 0，10 选择器全命中）、`desktop_extract_check`（exit 0，2 条记录）。

## 6. 逐条记录字段（本轮 0 条 → 全部缺失）

| 字段 | 结果 |
| --- | --- |
| 内容ID / id_source | 缺失（0 条） |
| 作者 | 缺失 |
| 正文摘要长度 | 缺失（`text_len=6`，没有卡片） |
| 时间 / 转发 / 评论 / 赞 | 缺失 |
| 来源链接 | 缺失 |

**分类**：不是"读到正文"，也不是"只有链接"；也**不是被拦**（200、无锁、无墙）；是**被移动 UA 重定向到 m.weibo.cn 的壳页**。

## 7. 下一步（需决定）

- 本轮额度已尽（3/3，窗口 06:49:32Z 关闭）。要完成"真实搜索读到正文"，需**新批次**（3 = 2 seed + 1 search）。
- 修复已就位（桌面 UA + 重定向判定），下一次 `live-search --keyword "学习计划模板"` 预期直接落在 `s.weibo.com`；若再重定向，会明确报 `redirected_elsewhere` 而不是"0 条"。

## 8. 未做

未读/打印 cookie 值；未对真实页面截图；未重试、未换词；未改账本补额度；未改业务库/CSV/契约/小红书；未提交 git。
