# 预装网络钩子 + 有评论样本：钩子时机已改，但样本仍全 0 评论，端点未定位

- 时间：2026-10-30T07:46–07:48Z（UTC）；cwd `D:\桌面\two`；解释器 `C:\Users\19183\.dsh\tools\x-collect\venv\Scripts\python.exe`。
- 一句话：**钩子改成"导航前注入"（CDP `Page.addScriptToEvaluateOnNewDocument`）并有顺序单测；`考研` 5 条样本 `comments` 全为 0；`学习计划` 那次被 `records_cap` 卡住（exit 6，不是 0 评论）；detail probe 只拿到 `text_len=361`、评论 0、**网络 0 条** —— 钩子是否真的注入**本轮没能验证**（缺 `hook_installed` 回读，已补代码但没再跑真实页）。**

## 1. 钩子时机修复（验收 1）

| 项 | 变更 |
| --- | --- |
| `session.open_live_hooked(url)` | 先开 `about:blank` → `cdp.page.addScriptToEvaluateOnNewDocument(source=NET_HOOK_JS)` → 再 `tab.get(url)`；注入失败才退回导航后 `evaluate` |
| `cmd_probe` | `--audit-network` 时改走 `open_live_hooked`（钩子先于导航），否则仍用 `open_live` |
| 回读 | 新增 `session.hook_installed(tab)`，probe 输出 `payload["hook_installed"]`（本轮真实页**没跑到**这一版） |

单测（`HookOrderTests` 3 例）：
- `open_live_hooked` 的调用序列是 `["hook", "nav"]` —— **钩子确实在导航之前**；
- 普通 `open_live` 序列只有 `["nav"]`（不注入）；
- `cmd_probe --audit-network` 实际调用的是 `open_live_hooked`（用假 session 记录）。

结果：RPA **158 OK**；四套全量 **393 OK**（`logs/tests-all-hook.log`），无跳过。

## 2. 找有评论的样本（验收 2、3）

| 关键词 | exit | 记录数 | 各条 `comments` | 结论 |
| --- | --- | --- | --- | --- |
| **考研** | 0 | 5 | `0, 0, 0, 0, 0` | 5 条全是 0 评论 |
| **学习计划** | **6** | 0 | — | **被 `records_cap` 卡住**（第一批已 `reserve_records(5)`，cap=5），不是"0 评论"结果 |

候选列表（考研，reposts/comments/likes 全为 0/0/0）：

| mid | 作者 | 正文长度 | 链接 |
| --- | --- | --- | --- |
| 5359745528759301 | 尚硕教育-山财考研 | 155 | https://weibo.com/7035093610/Rp4fKAKH3 |
| 5359745510936238 | 一块不像石头的木头 | 103 | https://weibo.com/6180592025/Rp4fJ3VyC |
| 5359745468992305 | 猴子棒棒鸡 | 100 | https://weibo.com/7415230699/Rp4fEBJjb |
| 5359745427049065 | 猴子棒棒鸡 | 119 | https://weibo.com/7415230699/Rp4fAtzMB |
| 5359745201342878 | 猴子棒棒鸡 | 58 | https://weibo.com/7415230699/Rp4fe5Dlk |

**没有 `comments>0` 的候选**，验收 3 的"挑 comments 最大的那条"无对象可选；按验收 7 不硬凑。

## 3. detail probe（预装钩子 + scroll 3 + comments + audit）

| 项 | 值 |
| --- | --- |
| URL | `https://weibo.com/7035093610/Rp4fKAKH3` |
| exit / surface | **0** / `detail`（surface 修复生效，不再误判 no_cards） |
| `page` | `http 200`、`text_len=**361**`、`title=微博正文 - 微博` |
| 评论 | before `0` / after `0`，容器 `{}` |
| 网络 | **count=0**、`dropped_non_weibo=0`、`by_path={}`、`comment_like` 空 |
| 钩子回读 | **本轮版本没有该字段**（`hook_installed` 是这之后才加的） |

账本：`search` 07:46:39Z success、`search` 07:47:04Z **failed**（records_cap）、`active_nav` 07:47:37Z → `active_nav_result` 07:47:42Z success；`used=5/5`、`remaining=0`、`records_reserved=5`。

## 4. 结论（验收 6，含更硬的否定结论与缺口）

| 问题 | 结论 |
| --- | --- |
| 钩子是否真的在导航前装上 | **单测证明顺序正确**；**真实页未验证**（缺 `hook_installed` 回读，且本轮 `network.count=0` 有两种可能：页面真没发微博域请求，或注入未生效/被 `tab.get` 新开标签页绕过） |
| 有评论样本 | **没找到**（考研 5 条全 0；学习计划被 cap 挡住） |
| 评论端点/参数/首屏/翻页/子回复 | **全部未知** |
| 「有评论却抓不到」这个硬否定 | **本轮没得到** —— 因为没有一条 comments>0 的样本 |

**缺什么（明确列出）**：
1. 一条**确实有评论**的微博（`comments>0`）——本轮两个关键词都没命中，且第二批被 `records_cap` 挡住；
2. 一次带 `hook_installed=true` 的真实探测，证明预装钩子生效（代码已就绪，未跑）；
3. 若钩子确认生效而仍 `network.count=0`，则说明该页评论由**首屏内联数据**渲染或走 `fetch` 之外的通道（如 `sendBeacon`/`WebSocket`），需要扩展钩子覆盖面。

## 5. 下一步建议（需新批次）

1. 先用 `live-search` 找一个 `comments>0` 的样本（关键词换更"热"的，或对同一关键词翻页/换 `--limit`），**并允许第二批 search**（`records_cap` 是 5，两批 search 会互相挤占 reserve，建议一批只做一次 search）。
2. 拿到样本后跑 1 次 `probe --url <detail> --scroll 3 --dump-comments --audit-network`，**先看 `hook_installed`**：
   - `true` + `network.count>0` → 直接读 `comment_like` 的 path/参数名；
   - `true` + `network.count==0` → 扩钩子（覆盖 `sendBeacon`、`EventSource`、`WebSocket`）；
   - `false` → 修注入方式（`tab.get` 是否新开标签页）。
3. 确认端点前，评论能力继续标"未验证"。

## 6. 未做

未读/打印 cookie 值；未对真实页面截图；未重试、未换词；未改账本补额度；未改业务库/CSV/契约/小红书；未提交 git。守卫五哈希未变。
