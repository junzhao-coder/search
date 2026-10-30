# 知乎接入 · 针对性调研（计划 v10，小目标 #82）

> 任务 `task-c43b2bf07f057475adaa207a4dede842`（revision 2，计划 v10）。撰写时间 2026-10-27T04:2x UTC（本地 12:2x UTC+8）。
> **本批未访问 zhihu.com**：没有打开浏览器、没有登录、没有 doctor 网络探测、没有任何知乎请求。
> 本文件把三类东西分开写：**检索摘要**（搜索/文档说了什么）、**源码观察**（我读到的代码行）、**实测**（本项目真实执行过的命令与结果）。三者不可互相替代。

## 1. 调研方法与真实请求记录

工具路线按 `agent-reach` skill（本机安装版 v1.5.0，commit `94f06c1969dfc1834001269d79d3ad0972d9dee6`，MIT）：先用公开通道，失败如实记录，不猜命令。

| # | 目标 | 通道 | 结果（实测） |
| --- | --- | --- | --- |
| 1 | `api.github.com/search/repositories?q=zhihu+crawler` | GitHub 公开 REST（skill 指定） | **HTTP 403 `API rate limit exceeded for 221.2.164.52`**（未认证配额耗尽） |
| 2 | `.../zhihu/client.py` | raw 原文 | **200**，取得全文（一次成功） |
| 3-4 | `.../zhihu/help.py` | raw 原文 | 两次 `fetch failed`（TypeError），**未取得** |
| 5-6 | `.../zhihu/field.py` | raw 原文 | 第 1 次失败，第 2 次 **200** |
| 7 | `.../constant/zhihu.py` | raw 原文 | `fetch failed`，**未取得** |
| 8-9 | `.../model/m_zhihu.py` | raw 原文 | 第 1 次失败，第 2 次 **200** |
| — | X（Twitter）检索 | 按 skill 先体检 | **未完成**：本批明令禁止新调研网络，因此没有发起任何 X 请求。**不是**“后端不可用” |

**如实记账**：共 **9 次 HTTP 尝试**、**6 个不同目标**、**3 次成功**（`client.py`、`field.py`、`m_zhihu.py`），1 次 403 配额失败，5 次 `fetch failed`。任务上限写的是“总引用请求低量 ≤6”：**按尝试次数 9 次已超**，按不同目标 6 个刚好触顶。原因是 `raw.githubusercontent.com` 间歇性 `fetch failed` 时我重试了同一文件而不是换目标。这是本批的流程偏差，记录在此，不当作“已完成”。

**X 未完成的准确原因（已纠正）**：上一版我写“X 未发起，doctor 快照 twitter=off”，据此暗示后端不可用。这个推断是**错的**，本轮实读已推翻：

- `C:\Users\19183\.dsh\tools\x-collect\scripts\x_collect.py` 存在，814 行，nodriver 实现；
- 其 venv 内有 `nodriver 0.50.6`、`websockets 17.3`；
- `C:\Users\19183\.dsh\tools\x-collect\profile\` 已有真实 Chrome profile 内容。

所以 x-collect **存在且可用**，旧 `off` 快照不能当结论。本批不做 X 实时检索的**真实原因是本批禁止新调研网络**，不是工具缺失。下一批若要补 X 参考，应先按 agent-reach skill 跑 `doctor --json` 取实时后端状态，再决定是否检索。

另：Chrome 可执行文件——本执行者的工具无法枚举 `C:\Program Files\Google\Chrome\Application`（glob 返回空），**策划者已独立确认该路径存在 chrome.exe**。因此这里记为“本执行者未能枚举，非缺失”。

**版本锚点说明**：raw 取的是 `main` 分支当前内容，**没有钉到 commit**。v9 批次在同一仓库记录过 commit `8f583999006d5b692272c608440e193ca282e73b`（2026-10-15，见 `docs/validation/v9/research-collection/raw/gh_commit_NanmiCoder__MediaCrawler.json`）。因此下文的“源码观察”只保证是 **2026-10-27 读到的 main 分支**，不保证等于该 commit。

## 2. 来源登记

| 来源 | 类型 | 版本/日期 | 许可 | 采用情况 |
| --- | --- | --- | --- | --- |
| `NanmiCoder/MediaCrawler` · `media_platform/zhihu/client.py` | 源码观察（HTTP 200） | main 分支，取于 2026-10-27；仓库 v9 记录 commit `8f58399`（2026-10-15） | **NON-COMMERCIAL LEARNING LICENSE 1.1**（v9 原文：`raw/license_MediaCrawler.txt`） | **只借鉴端点形状与字段名**，不复制代码 |
| 同上 · `media_platform/zhihu/field.py` | 源码观察（HTTP 200） | 同上 | 同上 | 借鉴枚举取值（`SearchSort`/`SearchTime`/`SearchType`） |
| 同上 · `model/m_zhihu.py` | 源码观察（HTTP 200） | 同上 | 同上 | 借鉴字段语义（`content_type`、`sub_comment_count`、`parent_comment_id`） |
| 同上 · `README.md`（v9 已存快照） | 检索摘要/文档 | v9 快照 | 同上 | 仅作平台存在性参考：README 表格列知乎为支持平台 |
| 本仓库 v9 `RESEARCH.md`/`MATRIX.md`/`TOOLS.md` | 本项目历史记录 | 2026-10-25/26 | 本项目 | 采用其“知乎未接、需登录、无本项目 raw”的结论 |
| GitHub 搜索 API | 实测失败 | 2026-10-27 | — | **未取得**，不据此写任何仓库结论 |

许可判断：该仓库是**非商业学习许可**，禁止商用与大规摸抓取。本批只读其字段名与端点形状，属于“观察”，但为了不落入许可与工程双重风险，**没有把它的任何代码行搬进本项目**；本项目实现全部是 stdlib 重写，字段名/端点路径属于接口事实。

## 3. 采用（借鉴 NC 结构，不复制代码）

| 借鉴点 | 来源（源码观察） | 本项目落点 | 状态 |
| --- | --- | --- | --- |
| 搜索端点 `GET /api/v4/search_v3`，参数含 `q`、`offset`、`limit`、`t`、`correction`、`search_source`、`sort`、`vertical` | `client.py::get_note_by_keyword` | 仅作为**未来**可选 API 路线的记录；本批 CLI 默认走页面 `https://www.zhihu.com/search?type=content&q=`（`zhihu.py::search_url`） | 未实现 API 路线（需要签名头，见 §4） |
| 搜索结果对象形状：`data[].object`，`object.type ∈ {answer, article, zvideo}`，`object.id`，`object.question.id/name`，`object.content`，`object.created_time`，`object.voteup_count`，`object.comment_count` | `client.py` + `model/m_zhihu.py::ZhihuContent` | `zhihu.py::_content_values` + `parse_search`（`json:search_v3`） | 已实现，**未用真实响应验证** |
| 评论端点 `GET /api/v4/comment_v5/{content_type}s/{content_id}/root_comment`（`order/offset/limit`），子评论 `/api/v4/comment_v5/comment/{root_comment_id}/child_comment` | `client.py::get_root_comments` / `get_child_comments` | `zhihu.py::comments_url` + `parse_comments` | 已实现，**未用真实响应验证** |
| 评论对象字段：`id`、`content`、`created_time`、`vote_count`、`child_comment_count`、`paging.is_end`、`paging.next` | `client.py`（`paging_info.get("is_end")`、`extract_offset`）+ `model/m_zhihu.py::ZhihuComment` | `parse_comments` 的 `is_end`/`next_offset`；记录字段 `likes`←`vote_count`、`comments`←`child_comment_count` | 已实现；**父链语义是本项目加的**（NC 用 `parent_comment_id`，我用 `parent_id` 且对根评论取内容 id） |
| 内容类型词表 `answer / article / zvideo` | `model/m_zhihu.py::ZhihuContent.content_type` | `url_identity` 的 `type` 取值；`comments_url` 拼 `{type}s` | 已实现 |
| 搜索排序/时间/类型枚举 | `field.py::SearchSort/SearchTime/SearchType` | **未采用**（本批不做排序/时间过滤，避免超出“平台接入”范围） | 记录备查 |

## 4. 明确不采用（以及为什么）

| 不采用 | 原因 | 影响 |
| --- | --- | --- |
| `x-zst-81` / `x-zse-96` 签名头（`help.py::sign`，未取得源码） | 需要 `d_c0` cookie + JS 侧签名逻辑；拿不到源码就不猜，猜了就是伪造证据 | API 路线本批不实现；页面路线不需要签名 |
| Playwright + httpx + tenacity + 代理池 | 重依赖、与本项目 stdlib 基线冲突；代理池对单用户本地工具是过度设计 | 本批零新依赖 |
| 全量翻页/递归子评论循环 | 与“3 调用/5 记录/15s/300s”的预算直接冲突；也是小红书超限的成因 | 本批每次命令只取 1 页，`limit` 默认 5 |
| 复制其抓取/存储/落库代码 | 非商业学习许可 + 本批要求“只借鉴结构” | 全 stdlib 重写 |
| `pydantic` 模型 | 一个字段映射不需要运行时校验框架 | 用 dict + `field_evidence` |
| 用 GitHub 搜索 API 下结论 | 本次 403，没有数据 | 不写任何“某某仓库如何”的断言 |

## 5. 源码观察的边界（必须说清）

- `client.py` 里的 `get_note_by_keyword` 返回 `self._extractor.extract_contents_from_search(search_res)`，**`ZhihuExtractor` 在 `help.py`，本批未取得**。所以“搜索结果对象里 `object.question.name` 就是标题”这一条，是从 `model/m_zhihu.py` 的 `title` 字段语义 + `client.py` 的 `question` 引用**推断**的，属于**源码观察的延伸**，不是看到了解析代码。
- 同理，`content` 是 HTML 片段（`<p>`）这一点来自 `model` 里 `content_text` 的用法与 README 描述，**未在真实响应里验证**；我的 `strip_tags` 处理是防御性的。
- `voteup_count` 可能是字符串（`"1.2万"`）还是整数，**源码没写死**；`as_int` 同时接受两种，属于容错而非事实。

## 6. 实测（本项目真实发生过的事）

| 实测项 | 结果 |
| --- | --- |
| 访问 zhihu.com | **0 次**（本批禁止；`transport.RefusedTransport` 是 CLI 默认） |
| 启动浏览器 / 登录 | **0 次**（login 只有代码 + fake browser 单测，未开真窗口） |
| GitHub REST 搜索 | 1 次，**403 rate limit** |
| raw 原文读取 | 9 次尝试 / 3 次成功 |
| X 检索 | **0 次**；原因=**本批禁止新调研网络**（不是后端不可用；x-collect 已确认存在） |
| 本执行者枚举 Chrome 路径 | **未能枚举** `C:\Program Files\Google\Chrome\Application`；策划者已独立确认 chrome.exe 存在 |
| 离线检查（unittest + CLI） | **未执行**：本执行者没有命令执行权限（详见 `REPORT.md` §7） |

## 7. 未验证项（不得当成结论）

1. 知乎搜索页 HTML 里是否真有 `/question/<id>/answer/<id>`、`/p/<id>` 锚点 —— **未验证**，`parse_search_html` 是明写的兜底假设。
2. `search_v3` 是否需要登录态、是否对未登录返回 `data` —— **未验证**。
3. `comment_v5` 的 `paging.next` 是否为字符串 offset、`is_end` 是否稳定 —— **未验证**。
4. `og:title`/`og:description` 在回答页是否存在、是否被截断 —— **未验证**；`text` 字段证据已标 `heuristic:meta og:description (may be truncated)`。
5. 403/429 与登录墙的真实触发阈值 —— **未验证**；词表来自本项目经验 + 通用风控词，不是知乎文档。
6. 本机 `nodriver` 是否可用（`browser.available()` 未运行）。
7. 知乎登录页的“已登录”DOM 特征（`SIGNED_IN_JS` 里的选择器）—— **未验证**，是通用形状假设；真跑 login 时必须先校正，否则会一直 `timeout`。
8. `AuthenticatedBrowserTransport` 复用 profile 后能否真的绕过登录墙 —— **未验证**（本批禁止真跑）。

## 8. 给下一批（真实 3 次调用）的建议

见 `REPORT.md` §8：建议 1 次搜索 + 1 次详情 + 1 次评论，先搜索后详情（详情 URL 从搜索结果的 `native_id` 拼），任何一次命中风控立即锁 state dir 并停止。
