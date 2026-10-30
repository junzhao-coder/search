# V9-9 实现报告：可见窗口单页探测 + 在线态 + 真实结构校正 + 0/1 条隔离入库

> 任务 `task-83c47148b73e5b5159b66bce7b5c1c81`（rev2，计划 v9）。2026-10-26 10:36–10:45 UTC+8。
> 一次可见窗口；请求 2 次（首页 + 1 篇笔记，≤2）；未登录/扫码/点赞/关注/评论/翻页/采集多篇；未装依赖、未改业务库。

## 1. probe（真实运行）

| 项 | 值 |
| --- | --- |
| cmd | `C:\Users\19183\.dsh\tools\x-collect\venv\Scripts\python.exe -X utf8 tools/selection/xhs_probe.py --wait 8 --interval 15` |
| cwd | `D:\桌面\two` |
| start_utc / exit | **2026-10-26T02:39:26Z** / **exit 0** |
| 窗口 | `headless=False`（可见窗口参数；未独立抓取窗口句柄，见限制） |
| 请求数 | **2**（首页 + 1 篇）；首页等待 8s，第二次前等待 15s |
| 日志 | `tools/selection/logs/xhs_probe_20261026.log`（stdout 中 author 昵称已脱敏为 `[redacted]`） |

## 2. online 判定

- 首页 `online=valid`，依据 `explore_links:25`；`login_wall=false`、`risk=false`。
- 未出现登录弹窗/验证码；实际可见文本无登录墙/风控标记。
- 第 2 次加载后目标笔记返回 **“小红书 - 你访问的页面不见了”**（错误页），不是有效笔记正文。

## 3. raw 证据（脱敏 DOM 骨架，无文本节点）

| 文件 | bytes | sha256 |
| --- | --- | --- |
| `docs/validation/v9/xhs-readiness/raw/probe_20261026T023927Z.html` | 39,670 | `c17b9b72a7afd0c9b88efd51c8c67b847b2a5702dc76ca20b641adaa711d39c0` |
| `docs/validation/v9/xhs-readiness/raw/probe_note_20261026T023927Z.html` | 18,763 | `7473947d7b31b254d74fa2c5889b536df32c1f03f5e902f74dc518f3c71bcfa2` |

- 只保存标签层级/class/id/安全 href；文本节点全部丢弃；`/user/profile/...` 已统一为 `/user/profile/[redacted]`；无昵称/账号字段。
- 原始 stdout 里错误页 author 昵称已在日志中替换为 `[redacted]`；报告只保留 `author_hash`。

## 4. calibration（真实结构 vs 旧假设）

- 旧 `parse_results` 假设 `a > h3/p`；真实首页是：
  `section.note-item > a.title > span`（标题）、`a.author > span.name`（作者）、`span.like-wrapper > span.count`（点赞）。
- 已更新 `tools/selection/xiaohongshu.parse_results`：优先解析 `section.note-item` 真实结构，保留旧 fixture 的 `h3/p` 兼容；新增 `author_hash`/`likes` 字段。
- 新增真实结构脱敏 fixture：`docs/validation/v9/xhs-readiness/fixtures/home_real_structure.html`（两级标签层级、文本为占位）。

字段对照（真实 probe）：

| 页面 | 期望字段 | 实际 | 差异 |
| --- | --- | --- | --- |
| 首页卡片 | native_id/title/author/likes | native_id/title/author/likes（25 链接） | 无 desc（卡片本身不展示）；结构已校正 |
| 目标笔记（错误页） | native_id/title/desc/author/likes | native_id/title/author；desc/likes 缺失 | `error_page=true`，`complete=false`；非有效笔记，不硬凑 |

- 笔记页是错误页，**无法据此验证真实笔记详情结构**；note 详情仍属结构假设，待有效笔记首采校正。

## 5. db（隔离库，0/1）

- 隔离库：`tools/selection/runtime/xhs_first.sqlite3`。
- 初始版本把错误页当作完整 note，写入 1 行；已修正 `parse_note_fields/_ingest`：检测“你访问的页面不见了/页面不见了/笔记不存在/404”即 `error_page`，不写库；并删除该误写行。
- **当前 `signals` 计数 = 0**（没有完整有效笔记，未写默认库；未创建额外业务数据）。
- 若后续有效笔记，写入上限仍为 1 条，`origin_kind=real`、`batch_id=first-real-<UTC>`。

## 6. 与 headless verify 对比

| 运行 | UTC | 结果 |
| --- | --- | --- |
| headless verify | 2026-10-26T02:27:26Z | exit4，`online=login_required` |
| visible probe | 2026-10-26T02:39:27Z | exit0，`online=valid`（25 links，无登录墙） |

- 两者均为**单次观察**；可见窗口未出现登录墙，而 headless 判定 login_required，说明 headless 可能触发登录墙/与可见态不同；不能据此断言会话永久失效，也不能断言在线长期有效。
- 未执行登录/扫码；如后续需登录，另行告知。

## 7. tests（三套真实 exit）

| suite | 结果 | 日志 |
| --- | --- | --- |
| selection（基线 79 + 真实结构/错误页/probe 7 新） | **86 tests OK** | `tools/selection/logs/tests_selection_v99b.log` exit0 |
| workbench | **218 tests OK** | `tools/selection/logs/workbench_v99b.log` exit0 |
| 项目全套（基线 413 + 7 新） | **420 tests OK** | `tools/selection/logs/project_v99b.log` exit0 |

- 新增 `tests/test_selection_xhs_probe.py` 6 项：sanitize 脱敏、classify online、extract links、parse note、error page 拒绝、隔离库单条；
- `tests/test_selection_xiaohongshu.py` 增 `test_parse_real_note_item_structure`。
- cwd `D:\桌面\two`；UTC 02:39–02:47（本地 10:39–10:47）。

## 8. 限制 / 未验证

- **可见窗口未独立抓取句柄/标题**：只确认脚本 `headless=False` 且真实运行；不能提供 Win32 visible 证据（本轮未在运行时抓取）。
- 目标笔记是错误页，**note 详情解析未获真实有效样本**；title/desc/author/likes 的 note 级字段仍是假设，需下次有效笔记校正。
- 首页卡片解析已按真实 `section.note-item` 校正；未验证多页/翻页/评论/搜索页。
- 只 1 次可见 probe、2 请求；未验证长期稳定性、登录失效边界、验证码真实页。
- raw 为 DOM 骨架，不是完整 HTML；这是脱敏选择，不是完整页面复原。
- probe stdout 的 author 昵称已后处理脱敏；原始 stdout 不再保留该昵称。
- stderr 有 nodriver/asyncio `ResourceWarning: unclosed transport` 收尾警告（与上一批相同），不影响 exit/stdout，未重试。
