# V9-11 报告：5 条点击式批量 + 隔离入库 + likes/publish 可信度校正

> 任务 `task-4926aef85ad6319fb639c1a3d079c456`（rev2，计划 v9）。2026-10-26 11:19–11:27 UTC+8。
> 可见窗口；**10 次页面加载**（首页 1 + 5 点击 + 4 返回 =10，≤10）；5 条（≤8），间隔 15s；未登录/扫码/点赞/评论/关注/翻页；未装依赖、未写业务库。

## 1. batch（真实运行）

| 项 | 值 |
| --- | --- |
| cmd | `C:\Users\19183\.dsh\tools\x-collect\venv\Scripts\python.exe -X utf8 tools/selection/xhs_probe.py --mode batch --max-notes 8 --max-loads 10 --interval 15` |
| cwd | `D:\桌面\two` |
| start_utc / 子进程 exit | **2026-10-26T03:21:17Z** / **exit=0**（runner 日志；页面/DB 均完成） |
| 实际条数 | **5**（`batch_limit(8,10)=5`，受 10 次加载上限） |
| 页面加载 / 请求 | **10 / 10**（≤10）；每条间隔 15s；`headless=False` |
| 停止 | 未触发登录墙/风控；5 条均 `note` |

每条（按首页顺序点击，不挑主题）：

| # | URL | 判定 | raw / sha256 |
| --- | --- | --- | --- |
| 1 | `/explore/6ada4538000000003102d284` | note | `raw/batch_1_20261026T032117Z.html`，74,959B，`ca029a2e…` |
| 2 | `/explore/6adbddf1000000002b02a267` | note | `raw/batch_2_...html`，63,644B，`bc751d48…` |
| 3 | `/explore/6ad7ac560000000028021342` | note | `raw/batch_3_...html`，55,625B，`ee817bdb…` |
| 4 | `/explore/6adb48ab000000003102c716` | note | `raw/batch_4_...html`，71,908B，`fa027a32…` |
| 5 | `/explore/6ad86d40000000003300f1aa` | note | `raw/batch_5_...html`，82,129B，`ac2d8b54…` |

- 每条点击后 URL 均带 `xsec_source`/`xsec_token`（只记长度，不落明文）；raw 为脱敏 DOM 骨架，无昵称/账号/文本节点。
- 第 1 条点击后等待渲染再解析；返回首页用 `tab.back()`，计入页面加载。

## 2. fields（likes / publish_time 可信度）

| 字段 | 本次批量实际 | 结论 |
| --- | --- | --- |
| native_id / title / desc | 5 条均有 | 可用 |
| author_redacted / author_hash | 有（仅 hash） | 可用 |
| comment_entry_present | true | 可用 |
| likes | 路径 `like-wrapper.count / engage-bar.count` 命中，但旧解析把多个嵌套 count 串联（如超长数字+“赞”串） | **批内值不可信，标为不可得**；已修 `_Likes` 只取 `like-wrapper .count` 首值并加测试，未重跑网络 |
| publish_time | 曾命中 `json-ld:datePublished`，但值等于本次运行时刻（03:21:28、03:21:51…），不是可信发布时间 | **标为不可得**；已移除 JSON-LD 兜底，只信 `meta[article:published_time]`/`time[datetime]` |

- 因页面加载已达 10 次上限，未再开一次校准；likes/publish_time 的“字段路径/不可得”已明确，不硬编假值。

## 3. db

- 隔离库 `tools/selection/runtime/xhs_first.sqlite3`：
  - 5 条本批全部 `new`；`batch_id=first-batch-2026-10-26T03:21:17Z`；`origin_kind=real`；
  - 总计 `signals=6`（含 V9-10 点击的 1 条）；`review=6`；`categories=0`；`cards=0`。
  - 5 条 content_hash 已写入（`cf7971e5…/bf7707ac…/d01acbb4…/49b39a87…/69351eee…`）。
- 未写默认 selection 库/业务库；重复 native_id 走 upsert 幂等。

## 4. categorize 原因

`run_categorize`: `signals=5, new=0, update=0, review=5, skipped=1, categories=0`；`make_cards`: `cards=0`。

- **不是字段不足**：5 条 title/desc 均有值。
- **主因文本无关**：本批是生活/社交/情感类内容，未命中现有品类关键词/家族规则；是否“规则过窄”未被证明（5 条样本不足以判断）。
- 未为了出品类挑选主题；按首页顺序取。

## 5. 台账

两处 xiaohongshu 行：
- 保留“可见窗口实测可用（02:39:27Z，25 条 explore 链接）；headless verify 属无头误判，勿据此重登”；
- 追加 batch 03:21:16Z 成功 5 条、batch_id、signals=6/review=6/categories=0/cards=0、页面加载10；
- 注明 likes/publish_time 批内值不可信/不可得，不伪造。

## 6. tests

| suite | 结果 | 日志 |
| --- | --- | --- |
| selection（基线 88 + batch/likes 2） | **90 tests OK** | `tools/selection/logs/tests_selection_v911.log` exit0 |
| workbench | **218 tests OK** | `tools/selection/logs/workbench_v911.log` exit0 |
| 项目全套（基线 422 + 2） | **424 tests OK** | `tools/selection/logs/project_v911.log` exit0 |

- 新增 `test_batch_limit_and_stop`（8/10→5；login/risk 即停；error/note 不停止）、`test_like_wrapper_first_count_only`；
- cwd `D:\桌面\two`；UTC 03:21–03:26（本地 11:21–11:26）。

## 7. 限制

- 仅 5 条（10 加载上限），未达 8；未验证翻页/评论/搜索页/长期稳定性。
- likes/publish_time 本次批内值不可信/不可得；代码已修但未重跑，不能声称已验证真实值。
- raw 为脱敏 DOM 骨架，不是完整 HTML；query 仅长度，无明文 token。
- 可见窗口未独立抓取句柄/标题；只确认 `headless=False`。
- stderr 有 nodriver/asyncio ResourceWarning 收尾警告，不影响结果。
