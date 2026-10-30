# V9-1a 平台能力矩阵（10 个核心平台组）

> 本文件是**桌面研究矩阵**，不是接入验收。除 B站/微博引用 A 任务的实测外，其余行仅来自 V9-0 原始件、候选 README/源码观察或公开入口模板；**没有本轮探测**。
> 证据等级定义：`实测`（本轮/并行任务真实请求并留 raw+sha）/`源码观察`（读了锁定 commit 的代码/文档）/`README声称`（项目自述，未复核）/`样本观察`（只读既有导入样本，不代表平台实时）/`未验证`（只有入口模板或二手线索）。
> `2026-10-25` 为桌面核对日期；B站/微博为 A 任务 UTC 实测时间。**不得以“URL 能打开”判定可用**。

| 平台组 | 搜索入口模板 | 榜单/热销入口（若公开） | 正文/详情 | 评论/楼中楼 | 价格 | 销量/想要 | 登录要求 | 获取方式 | 限速/风控已知点 | 证据等级 | 最近核对 | 来源（文件:行） |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| **B站** | `https://search.bilibili.com/all?keyword={q}`（公开入口模板，未验证） | `https://www.bilibili.com/v/popular/rank/all`（公开入口模板，未验证） | `https://www.bilibili.com/video/{bvid}`；A 实测 `view` 可取 aid/bvid/videos/stat.reply | **A 实测**：`/x/v2/reply?type=1&oid={aid}&pn=1&ps=5&sort=2` 可取 first page；缺 `sort` 假阴性；第 2 页 `pn=2` 空；楼中楼 `/x/v2/reply/reply?root={rpid}` 仅入口+1 条 | 无（内容平台）；A 未测商品价 | 无销量/想要；A 有 `stat.reply` 评论数 | A 实测无 cookie/登录；不能外推所有场景 | 公开 HTTP GET（官方 web API 形态）；不是官方开放 API 承诺 | A：7/10 请求、3s 间隔、无 -412/-352；第 2 页空即停；高频/并发未测 | **实测（A）**：公开 view 可读、评论需 sort、翻页未成立、子回复入口 | 2026-10-25 05:32–05:42Z | `MATRIX_ROWS.md:8`；`PROBES.md:9-37` |
| **小红书** | `https://www.xiaohongshu.com/search_result?keyword={q}`（V9-12 可见搜索；但本批超限+风控后继续，测量不合格） | `https://www.xiaohongshu.com/explore`（首页 feed；V9-10/11 点击可开，不作需求源） | `/explore/{id}`（点击可开；直开缺 xsec_token 会“页面不见了”）；搜索卡标题 href `/search_result/{id}` | 未验证；不采集评论 | 无商品价；`N/A` | 无销量/想要；`N/A` | **未验证**（最后一次可见搜索未触发登录墙；但测量不合格，登录要求同样未验证）；headless verify 曾 login_required，不据此重登 | 可见窗口 + 搜索页导航/DOM 点击；`xhs_probe.py --mode search`；非 API | **违规**：7 次运行 17 加载（>8）、两次 risk 后继续 5 次；exit 全 0 不可信（已修） | **测量不合格（超限+风控后继续+规则假阳性）**：规则 7/18=38.9%，人工复核 2/18=11.1%（选品口径 1/18=5.6%）；**需求能力未验证** | 2026-10-26T03:50:35Z（最后运行） | `REPORT_V9_12_REWORK.md`、`ACCOUNT-SAFETY.md` 违规记录、`raw/search_*.html` |（另：指定会话代码已迁移至 `tools/selection/vendor_xhs/xhs_collect.py`，按用户要求未测试、未运行、未接本项目流程）
| **抖音** | `https://www.douyin.com/search/{q}`（公开入口模板，未验证） | `https://www.douyin.com/hot`（公开入口模板，未验证） | `https://www.douyin.com/video/{id}`（模板，未验证字段） | 未验证；仅 V9-0 候选 README 声称有评论；无本项目 raw | `未验证`；电商价/团购价未登记 | `未验证`；无成交/销量证据 | **需登录/cookie/风控**（候选 README 声称；未实测） | 浏览器辅助/用户登录态；不自动 | 未验证；不假设无限翻页 | **README声称/未验证**（RESEARCH:133） | 2026-10-25（未探测） | `RESEARCH.md:133`（README声称；入口模板未验证） |
| **贴吧** | `https://tieba.baidu.com/f?kw={q}`（公开入口模板；本次 403） | 无经核实的公开热销榜；`未验证` | `https://tieba.baidu.com/p/{tid}`（未取得 tid，未请求） | **实测-验证码/安全验证**：列表页 403 百度安全验证；无 d_post_content/core_title/p_postlist/pagination；不可读 | 无（论坛）；`N/A` | 无销量/想要；`N/A` | 未验证；无 cookie 公开请求被安全验证拦截 | 网页 GET（本次不可读）；需用户浏览器/登录或导入 | 1/5 请求；403 即停；无 tid/分页，未验证翻页 | **实测-验证码/安全验证（403）** | 2026-10-25T11:02:51Z | `PROBE_TIEBA.md`；`raw/tieba_list.html`；`logs/requests_tieba.jsonl` |
| **微博** | `https://s.weibo.com/weibo?q={q}`（公开入口模板，未验证） | `https://s.weibo.com/top/summary`（公开入口模板，未验证） | A 尝试 `m.weibo.cn/api/container/getIndex` 被重定向访客墙，未取得正文 | **A 实测：登录墙**；无评论字段；只一级/翻页未验证 | 无（内容平台）；`N/A` | 无销量/想要；`N/A` | **需登录/访客验证**（A 实测） | 浏览器/用户登录态；或用户导出 | A：1/5 请求，首请求即停；登录后能力未验证 | **实测（A）：登录墙**（MATRIX_ROWS:9；PROBES:39-59） | 2026-10-25 05:32Z | `MATRIX_ROWS.md:9`；`PROBES.md:39-59` |
| **知乎** | `https://www.zhihu.com/search?type=content&q={q}`（公开入口模板，未验证） | `https://www.zhihu.com/hot`（公开入口模板，未验证） | `https://www.zhihu.com/question/{qid}/answer/{aid}`（模板，未验证字段） | 未验证；V9-0 仅代码层平台位（源码观察）；无本项目 raw | 无（内容平台）；`N/A` | 无销量/想要；`N/A` | 公开页/登录要求未验证；通常需登录（未实测） | 网页/浏览器；不自动 | 未验证 | **源码观察/未验证**（RESEARCH:74,136） | 2026-10-25（未探测） | `RESEARCH.md:74,136`（源码观察；入口模板未验证） |
| **闲鱼** | `https://www.goofish.com/search?q={q}`（公开入口模板，未验证） | 无经核实的公开热销榜；`未验证` | `https://www.goofish.com/item?id={id}`；`xianyu_items.jsonl` 20 条有 href/title/price/raw_text | 未验证；20 条导入样本**无评论字段**；不把商品标题当评论 | `price` = `¥1`（20/20）；`effective_price` 1.00–1.88（样本派生）；`reference_price` 3/20 | `wants` 16/20，合计 8093（兴趣代理，非成交）；无销量/真实成交 | 需登录/用户导出；样本来自已登录采集（不代表当前实时） | **manual imported**（用户导出）；不自动采集 | 风控/频控未验证；样本只有 20 条；不推断平台上限 | **样本观察（20 JSONL）**；平台入口/实时未验证 | 2026-10-25（样本） | `tools/platform-login/data/xianyu_items.jsonl` 20 行；`import_sample_stats.json`；入口模板未验证 |
| **淘宝/天猫** | `https://s.taobao.com/search?q={q}`（公开入口模板，未验证） | `https://www.taobao.com/`（仅首页，非热销榜；未验证） | `https://item.taobao.com/item.htm?id={id}`（模板，未验证字段） | 未验证；候选文档声称有，但本项目无 raw/未运行 | `未验证`；商品价字段未登记 | `未验证`；销量字段未登记 | **登录/cookie/风控强**（V9-0 候选 README 声称；未实测） | 用户导入（P1/P2 提案）；自动采集未批准 | 未验证；不假设可抓 | **README声称/未验证**（RESEARCH:138,159-164） | 2026-10-25（未探测） | `RESEARCH.md:138,159-164`（README/提案；入口模板未验证） |
| **京东** | `https://search.jd.com/Search?keyword={q}`（公开入口模板，未验证） | `https://www.jd.com/`（仅首页，非热销榜；未验证） | `https://item.jd.com/{sku}.html`（模板，未验证字段） | 未验证；评论接口/字段未登记 | `未验证`；商品价字段未登记 | `未验证`；销量字段未登记 | 登录/风控未验证 | 用户导入；自动未批准 | 未验证 | **README声称/未验证**（RESEARCH:139,159-164） | 2026-10-25（未探测） | `RESEARCH.md:139,159-164`（README/提案；入口模板未验证） |
| **拼多多** | `https://mobile.yangkeduo.com/search_result.html?search_key={q}`（公开入口模板，未验证） | 无经核实的公开热销榜；`未验证` | `https://mobile.yangkeduo.com/goods.html?goods_id={id}`（模板，未验证字段） | 未验证；无候选深读/本项目 raw | `未验证` | `未验证` | 登录/风控未验证 | 用户导入；自动未批准 | 未验证；catbus 仅“即将上线”，不能当已支持 | **未验证/源码观察（缺口）**（RESEARCH:140） | 2026-10-25（未探测） | `RESEARCH.md:140`（源码/缺口；入口模板未验证） |

### 扩展候选（不计入 10 个核心平台组）

| 平台组 | 搜索入口模板 | 榜单/热销入口（若公开） | 正文/详情 | 评论/楼中楼 | 价格 | 销量/想要 | 登录要求 | 获取方式 | 限速/风控已知点 | 证据等级 | 最近核对 | 来源（文件:行） |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| **X（Twitter，扩展候选）** | `https://x.com/search?q={q}&f=live`（本轮 `Notion template`） | 无公开热销榜；`未验证` | `https://x.com/{handle}/status/{id}`（公开帖模板；本轮 5 条有 url/text/author/created_at） | 评论/楼中楼未验证 | 无商品价；`N/A`（内容平台） | 无销量/想要；replies/retweets/likes/views 页面展示，`null` 不编造 | **需登录态**（专用 profile；doctor 只读） | **x-collect** 专用 profile（只读 doctor/search）；**agent-reach twitter 后端未装；x-collect 可用** | 单次 ≤5、8–12s；遇 412/429/验证码即停；本轮 5 条、0 重复、exit0、未遇风控 | **实测-只读小样本（V9-6）**：doctor exit0 `@Johnsmathjyjp`、search 5；不等于全站可采 | 2026-10-25 12:39–12:41Z | `docs/validation/v9/account-safety/REPORT.md`；`raw/search_5.jsonl`；`logs/doctor.log` |

## 矩阵来源与边界

- B站/微博行：**A 任务** `MATRIX_ROWS.md:8-9`、`PROBES.md:9-79`、`raw/`、`logs/requests.jsonl`、`sha_manifest.json`；本文件未复制原始响应。
- 其余平台映射：V9-0 `research-collection/RESEARCH.md:127-140`（平台组支持矩阵）、`:159-164`（P1/P2/P3）、`:74`（MediaCrawler 平台位）、`:88-98`（catbus 限制）；`baseline/BASELINE.md:103-108`（data_origin 仅 real/synthetic）。
- B站之外的 URL 是**公开入口模板**，不是已核验 API；没有官方开放 API 证据。`未验证` 表示未取得字段/未实测，不表示“不可用”。
- 价格/销量/想要：只有闲鱼 20 条样本有 `price` 与 `wants`；B站/微博无商品价格/销量；其他平台未验证。
- 评论/楼中楼：只有 B站 A 实测了第一页和一个子回复入口；微博登录墙；其余未验证。不能把“有评论页”当“可分页/可全量”。
- 证据等级之外不写 `全自动/已接入/稳定`；本矩阵不改变任何代码或平台状态。

- **贴吧行（V9-1c-A）**：2026-10-25T11:02:51Z 单次公开 GET `https://tieba.baidu.com/f?kw=notion&ie=utf-8` → **403 百度安全验证**；无 `d_post_content/core_title/p_postlist/pagination`，未取得 tid，未发第 2 次；raw `raw/tieba_list.html`、日志 `logs/requests_tieba.jsonl`、报告 `PROBE_TIEBA.md`。
## 结论（供下一阶段）

- **可先做**：B站公开评论第一页（sort=2，单视频、低量）作为评论源；闲鱼 20 条导入作为交易源；小红书/知乎/贴吧仅作为**用户导入或未验证**补充，不先自动采集。
- **不能做**：把微博访客墙当“无内容”；把抖音/淘宝/京东/拼多多的候选 README 当实测；把闲鱼 `wants` 当成交；把入口 URL 能打开当 API 可用。
- 具体最小适配器清单见 `IMPORT_CONTRACT.md` 的“下一阶段”。
