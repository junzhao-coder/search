# B22：选品页「继续已有工作单」

> 侧栏仍严格三项（选品 / 选源 / 起草介绍）；本区块只做**只读列表 + 带 wo 跳转**，不自动选中、不自动建单。

## 1. 实现

- `views_wizard.render_continue()`：表格列 = 名称/单号 · 状态 · 就绪进度（`n/7`）· 更新时间 · 操作（**继续选源** `/source?wo=ID`、**继续起草介绍** `/copy?wo=ID`）。
- `app._recent_workorders(limit=10)`：`wf.connect_ro()` 读取（**库不存在返回空**）；`wf.list_all()` 后按 `updated_at` **倒序**取前 10；每条调用 `rd.readiness(record)` 统计通过项（不改判定逻辑）；只读异常也返回空列表，**不会 500**。
- 区块位置：`/pick` 顶部（向导条下方、选品表上方）；空态文案「**还没有工作单，先在上面选一个商品**」。
- 未新增侧栏入口；未改就绪判定与导出白名单。

## 2. 测试（subprocess，`execution_manifest.json`）

| suite | argv（cwd） | rc | summary |
| --- | --- | --- | --- |
| `b22_continue` | `python -X utf8 -m unittest tests.test_wizard -v`（`tools/workbench`） | **0** | `Ran 57 tests — OK` |
| `workbench_all` | `… discover -s tests -t . -v` | **0** | `Ran 207 tests — OK` |
| `project_full` | `… discover -s tests -v`（仓库根，`APP_DB_PATH=%TEMP%\b22_full.db`） | **0** | `Ran 334 tests — OK`（48.3s） |

新增 `ContinueWorkorderTests`（3 例）：
1. 两条单时区块列出、`/source?wo=` 与 `/copy?wo=` 链接指向正确单号、`继续选源`/`继续起草介绍` 各 2 个、出现 `n/7` 进度；
2. 无单时空态文案；
3. 侧栏仍恰好 3 项，且跳转 `/source?wo=`、`/copy?wo=` 均 200、导航链接保留 `?wo=`。

## 3. 截图

`shots/pick_continue_block.jpg` 1440×900 / 108,078 B / `cb8917ebde…`（`format=jpeg`、`openable=true`，隔离库两条示例单 `wo:20261024-7b23cdf8`、`wo:20261024-de434d48`）；`shots_manifest.json` 记录尺寸/字节/sha/格式。

## 4. 部署与线上核对（同一 5015）

- 只停本工具父子进程后分离重启：**父 PID 112008**、监听 **PID 108960**；日志 `tools\workbench\runtime\workbench-5015{,.err}.log`。
- 线上 `/pick`：**出现「继续已有工作单」区块**，含生产单 **`wo:20261023-88ef9a66`** 的链接，进度显示 `n/7`；`NAV_LABELS=选品,选源,起草介绍`（仍 3 项）；`/healthz` 200 且 `app_id=workbench-opportunity/1`。
- 守卫未变：`instance/app.db e073f828…`、`CONTRACT.md 826c24cc…`、`scores.csv ab0c3546…`、`sources.csv 13679b60…`。

## 5. 改动摘要（diff）

- `views_wizard.py`：新增 `render_continue(workorders)`；`render_pick(..., workorders=None)` 并在向导条下方渲染该区块。
- `app.py`：新增 `_recent_workorders()`（只读、倒序、限 10、含就绪进度、异常容错）；`/pick` 传入该列表。
- `tests/test_wizard.py`：新增 `ContinueWorkorderTests`（3 例）。

## 6. 限制

1. 仅列**最近 10 条**（按 `updated_at` 倒序）；更多历史仍可通过 `/worksheet` 查看（旧页保留，只是不进侧栏）。
2. 进度是“当前通过项/7”，随证据变化实时计算；不代表可导出（导出仍需 7/7 且 `platform_evidence` 非空）。
3. 区块只读：不会自动把某条设为“当前单”，也不改变 `_current_wo()` 的取值规则。
4. 无单空态时也不会引导建单，只是提示先在上面选一个商品（建单仍走「选这个」或「新建自制商品」）。
