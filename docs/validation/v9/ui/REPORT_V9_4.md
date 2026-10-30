# V9-4 实现报告：/leads 只读页 + 受控开轮/暂停/继续/取消

> 任务：`task-d733e3208b73aa1fe35e48ff9a864cfc`（revision 3，计划 v9）；范围 `tools/workbench`、`tools/selection`、`tests`、`docs/validation/v9/ui`。
> 工作区 `D:\桌面\two`；实现/测试/截图时间 2026-10-25 19:34–19:43 UTC+8。未改 app/、生产 workflow/selection 库、业务 CSV、就绪/导出/文案语义、NAV 三项。

## 1. 页面 `/leads`（只读）

- 入口：`views_leads.py`；GET `/leads` 路由 `app.py`（`leads_page`）。`/pick` 页内新增链接 `查看需求线索与轮次 →`，不新增侧栏项；`NAV` 仍为 选品/找货源/写文案（`app.py:41`）。
- 数据源：`V9_SELECTION_DB` 或默认 `tools/selection/runtime/selection.sqlite3`；`load_lead_data()` 只读 `sqlite3 mode=ro`；缺库/缺表返回空态，不 500（`views_leads.py`）。
- 展示：
  - signals 总数、按 `origin_kind`/`platform` 分布；
  - categories：id、canonical_label、status、证据数、最近事件时间；
  - direction_card：id/category/deliverable/evidence_ids/gaps/status；gaps JSON 转可读；
  - review_queue：pending 总数 + 前 10 条；
  - rounds：id/status/cursor/requests_used/budget/started_at/done items。
- 顶部明示“规则推断，不是市场结论；样本极小”；只读展示不触发采集。

## 2. 受控轮次动作

- `POST /leads/round`：bvid/aid 二选一；budget `max(1,min(5))`；interval `max(3.0, …)`；idempotency_key 空则自动；调用 `sel_rounds.start()` + 一次 `sel_bili.collect_round()`，不循环；成功/异常都 303 回 `/leads` 带 `msg`/`err`。
- `POST /leads/round/<id>/pause|resume|cancel`：直接调用 `sel_rounds.pause/resume/cancel`；非法状态/未知操作捕获为 303 + 可读 `err`，不 500、不静默。
- 页面不复制状态机；所有状态变更走 `tools.selection.rounds.*`。
- 安全：所有 POST 先 `require_local_write()`（现有 CSRF + 同源校验，`app.py:898-915`）；表单 hidden `csrf` 由 `csrf_token()` 生成；不写 `instance/app.db`、生产 `workflow.sqlite3`、业务 CSV。

## 3. 测试

| suite | 结果 | 日志 |
| --- | --- | --- |
| `tests.test_selection_leads` | **5 tests OK** | `logs/tests_leads.log` exit 0 |
| workbench 全套 | **218 tests OK** | `logs/workbench_all.log` exit 0 |
| 项目全套 | **372 tests OK** | `logs/project_full.log` exit 0 |

- `tests/test_selection_leads.py` 覆盖：GET 空态、GET 有数据 + `/pick` 链接、POST 开轮成功（stub `collect_round`，断言只调用一次、budget=3/interval=3）、CSRF 缺失 403、非法 pause 303 可读错误。
- 真实 argv/cwd/UTC/exit 见三个 log；cwd `D:\桌面\two`；无外网（开轮 stub）。

## 4. 截图 / 视口

- 用隔离 selection 库 `docs/validation/v9/ui/runtime/ui_demo.sqlite3`（merged23 6 品类/6 卡/1 review + round_real 1 round/2 items）；
- 隔离 5015（PID 130832，临时 workflow DB）启动、截图后停止；当前 5015 无监听。
- 截图（JPEG 字节，已按真实格式 `.jpg`）：
  - `shots/leads_1440x900.jpg`：1440×900，innerWidth 1440，scrollWidth 1440，**overflowX=false**；
  - `shots/leads_390x844.jpg`：390×844，innerWidth 390，scrollWidth 390，**overflowX=false**。
- `ui_metrics.json` 记录 metrics；`sha_manifest.json` 记录截图/日志/DB 的 bytes+sha256。
- 截图显示侧栏仍 3 项；页面标题“需求线索”；顶部样本极小提示；类别/卡片/复核/轮次区可见。

## 5. 边界 / 未改动

- 未改就绪判定、导出白名单、文案版本语义、三栏 NAV；未接 UI 之外的流程/LLM/依赖。
- 未改 `instance/app.db`、生产 `tools/workbench/runtime/workflow.sqlite3`、既有 CSV、CONTRACT；guards 哈希与之前一致。
- 限制：`/leads` 只读展示 selection 库，不做品类/去重/自动推荐；开轮只支持 B站 view/reply 单次推进；未验证多平台并行/第三平台/长跑；截图使用隔离 demo 库，不是生产 selection 库。
