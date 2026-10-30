# B1 商品工作单（选品入口 + 可编辑规格 + 独立持久化）交付报告

- 执行者：C；范围：`tools/workbench/`、`docs/validation/product-workflow/b1/`
- 实测入口：**http://127.0.0.1:5015/worksheet**（部署账户 PID **111864**，仅绑 127.0.0.1）
- 结论：**B1 已完成**——可从已归类商品组建立候选工作单、编辑规格、独立 SQLite 持久化并在重启后保留；
  **B2 货源/验货、B3 文案素材、B4 人工复核、B5 上架包均未实现**，界面明确标注“待后续实现”，无假按钮。

## 1. 字段 / 存储 / 状态设计

**表 `workorder`**（独立库 `tools/workbench/runtime/workflow.sqlite3`，可用 `WORKBENCH_WORKFLOW_DB` 覆盖；**不碰 `instance/app.db`**）

| 组 | 字段 |
| --- | --- |
| 身份 | `workorder_id`（`wo:<yyyymmdd>-<8hex>` 唯一）、`submit_key`（唯一，幂等）、`payload_hash` |
| 来源快照（不可编辑） | `source_group`、`source_item_id`、`source_url`、`source_platform`、`snapshot_json`（title/需求/可售性/毛利/成本/缺失指标/原链接等） |
| 计划规格（可编辑白名单） | `name`、`use_case`、`target_buyer`、`deliverable`、`fmt`、`language`、`version`、`includes`、`excludes`、`target_platform`（仅 `xianyu`） |
| 状态与门槛（服务端持有） | `status`（仅 `pending_supply` 待补/待货源、`in_review` 核验中）、`gate_demand`/`gate_supply_distribution`/`gate_cost`/`gate_platform_policy`（初始全 `unverified`）、`selected_supply_id`（初始 NULL） |
| 版本 | `revision`（乐观锁）、`created_at`、`updated_at` |

另有 `workorder_event`（create/update 审计）。CSRF 密钥持久化在 `runtime/secret_key`，`runtime/` 已由 `.gitignore` 排除，报告中不出现密钥内容。

**初始状态**：四门槛 `unverified`、`selected_supply_id=NULL`、`status=pending_supply`；**本批没有自动通过路径**。

## 2. 实现（新增/改动）

| 文件 | 说明 |
| --- | --- |
| `tools/workbench/workflow.py`（新） | 存储与业务：`connect/connect_ro`、`init_schema`（仅写独立库）、`validate_source`（服务端校验：非商品/教程/未归类/不存在 ID/分组不匹配均拒绝）、`normalize_fields`（白名单+长度+平台+状态；伪造门槛/货源/快照/ready 一律 403）、`create`（幂等）、`update`（revision 冲突 409）、`derive_gaps`、`stages_state`、`secret_key` |
| `tools/workbench/views_worksheet.py`（新） | 列表 / 详情（含来源快照与四门槛）/ 编辑表单（revision 隐藏域、状态只给两项） |
| `tools/workbench/app.py` | 导航加「商品工作单」；`/worksheet`、`/worksheet/<id>`、`/worksheet/<id>/edit`（**只读连接**，GET 零写：库文件不存在时不会创建）、`POST /worksheet/new`、`POST /worksheet/<id>/edit`；CSRF+同源校验；`wf.Reject` 统一 4xx 页面；`/healthz` 增 `workflow{db,workorders}` |
| `tools/workbench/views_grouped.py` | 商品组行加「选为候选商品」表单（提交 csrf/group/item_id/submit_key/初始规格），无 JS 也可用 |
| `tools/workbench/.gitignore`（新） | 排除 `runtime/` 与 `__pycache__/` |
| `tools/workbench/tests/test_workflow.py`（新，16 例） | 见 §4 |

**安全**：POST 必须带会话内 CSRF token（`hmac.compare_digest` 比较）；若带 `Origin`/`Referer` 则必须同源，否则 403；未登录/无 token 一律拒绝。服务端从不信任前端：越级字段在 `normalize_fields` 直接 403 且不改库。

## 3. 隔离库端到端（真实跑，证据 `e2e_evidence.json`）

端口 **5017** 独立实例 + 隔离库 `b1/tmp/workflow_e2e.sqlite3`（合成数据），流程与实测：

| 步骤 | 结果 |
| --- | --- |
| 从 `/opportunities` 抓取「选为候选商品」表单（csrf/group/item_id/submit_key）→ POST 建单 | 303 → `/worksheet/wo:20261023-84ddf559`；DB：`status=pending_supply`、四门槛 `unverified`、`selected_supply_id=NULL`、`revision=1` |
| 同键同内容重复提交 | 303 且 `?deduplicated=1`；**库内仍 1 条** |
| 编辑（revision=1）改名 + 状态改 `in_review` | 303；DB `name=改名后的工作单`、`status=in_review`、`revision=2` |
| 用过期 revision=1 再提交 | **409**；DB 名称与 revision **均未变**（2 / 改名后的工作单） |
| 越级 `status=ready` | **403**；DB 仍 `in_review`、revision 仍 2 |
| 错误 CSRF | **403** |
| 建单时带 `status=verified` | **403**，库内计数仍 1 |
| **停进程 → 重启同库 → GET 详情/列表** | 200；列表含该 ID，详情含新名称，**库内 1 条**（重启保留） |

## 4. 测试（真实 exit）

| 套件 | 命令（cwd） | 结果 |
| --- | --- | --- |
| 工作台全部（含 B1 16 例） | `python -X utf8 -m unittest discover -s tests -t . -v`（`tools/workbench`） | **`Ran 78 tests — OK`，exit=0**（`tests_workbench_all.log`） |
| 原完整套件 | `python -X utf8 -m unittest discover -s tests -v`（仓库根，`APP_DB_PATH=b1/tmp/full.db`） | **`Ran 334 tests — OK`，exit=0，48.1s**（`tests_full.log`） |
| B1 专项 | `python -X utf8 -m unittest tests.test_workflow -v` | **`Ran 16 tests — OK`，exit=0**（`tests_workflow.log`） |

**B1 16 例覆盖**：真实商品建单与快照/门槛断言；教程、未归类、不存在 ID 拒绝；分组不匹配；幂等（同键同内容）/同键异内容 409/缺 submit_key；编辑 revision+1；过期 revision 409 不丢数据；校验失败（空名/超长/非法平台）回滚；`verified/ready`/伪造门槛/伪造快照 403；编辑越级 403；CSRF 缺失与跨站 Origin 403；**GET 不创建库文件**；404；新实例/重开库持久化；缺项与阶段状态。

## 5. UI 与截图（隔离测试库，注明为测试规格）

桌面 **1440×900**、手机 **390×844**，均无整页横向溢出（`overflowX=false`，`scrollW` 1440 / 390）：

| 文件 | 尺寸 | bytes | sha256 前 16 |
| --- | --- | --- | --- |
| `shots/desktop_worksheet_list.jpg` | 1440×900 | 64,595 | `6ae6d5d037322112…` |
| `shots/desktop_worksheet_detail.jpg` | 1440×900 | 76,701 | `62f04309f34604cc…` |
| `shots/desktop_worksheet_edit.jpg` | 1440×900 | 74,886 | `fe2ace700be76378…` |
| `shots/mobile_worksheet_list.jpg` | 390×844 | 40,568 | `265d34ab1de6732e…` |

`shots_manifest.json` 单趟生成并**自校验 4/4 一致（mismatches=0）**，记录 `base=http://127.0.0.1:5017`（隔离库实例）与每个视口的 `innerW/scrollW/overflowX`。

页面要素：列表（ID/名称/来源/状态/缺项数/更新时间/编辑）、详情（计划规格、来源证据快照、**待核验缺项 N 条**、四门槛全部未核验、流程 6 阶段仅“选产品”done）、编辑（revision 隐藏域、状态仅两项、必填标注、保存按钮标注 revision）。

## 6. 部署（用户原入口 5015）

- 停止前按命令行精确匹配 `tools\workbench\run.py --port 5015`，**只停本工具进程**（128732、132820），未动 DSH 与其它端口。
- 以当前代码同端口重启：**PID 111864**，`http://127.0.0.1:5015/`；`/healthz` 返回 `app_id=workbench-opportunity/1` 且新增 `workflow{db,workorders}`。
- 核对：`/worksheet` 200（含导航「商品工作单」、空态提示、B2–B5 待实现说明）；`/opportunities` 含「选为候选商品」表单；**GET 未创建工作单库文件**（`DB_CREATED_BY_GET=False`）；`runtime/secret_key` 已存在且重启不删。
- 端口：5015=1、5016=0、5017=0（测试实例已停）。
- 停止方式：Ctrl+C，或 `Stop-Process -Id 111864`；启动方式：`start_workbench.cmd` 或 `python tools\workbench\run.py --port 5015`。

## 7. 守卫（文件 hash，未 SQL 打开原库）

`instance/app.db e073f828…`、`docs/design/CONTRACT.md 826c24cc…`、`scoring/scores.csv ab0c3546…`、
`app/core/importer.py a11eaf4d…`、`app/sources/wiring.py bafcf397…` —— **前后一致，未变**。
未改迁移/冻结文件/DSH 核心；未做任何采集/登录/发帖/采购/对外发布。

## 8. 限制与未完成项

1. **B2–B5 未实现**：货源查找、验货、文案素材、人工复核、上架包均为“待后续实现”，页面已标注，无假按钮、无自动通过门槛的路径。
2. 目标平台只有 `xianyu` 一个选项（按任务要求）。
3. 工作单只存规格与来源快照；**不写回**采集 CSV、画像或评分文件。
4. 生产库（5015 的 `runtime/workflow.sqlite3`）当前 **0 条**：按“不替用户创建已验证商品”的要求，没有为你预建候选；请自行在机会页点「选为候选商品」。
5. 质量线/缺项由快照字段推导（无参考价、可售性<80、毛利回退、无成本输入、缺失指标等），不构成验货结论。

---

# rev5 窄修（原子性 / 参数健壮性 / 严格零写 / 凭据脱敏）

## 1. 更新原子化 + 并发回归

- `workflow.update()` 改为：`BEGIN IMMEDIATE` → `UPDATE … WHERE workorder_id=? AND revision=?` → **`cur.rowcount != 1` 立即 `rollback` 并 409**；成功审计 `workorder_event(update)` 与 UPDATE **同事务提交**，失败路径**不写审计**；SQLite 异常统一回滚为 409。
- 两条回归（均在隔离 fixture 上）：
  - `test_atomic_update_rowcount_and_no_false_audit`：A 预读 revision=1，B 用 1 改成功→2，A 再用 1 → **409**、最终名称以 B 为准、事件表 **只有 1 条 update**。
  - `test_atomic_update_zero_rows_after_prefetch`：受控构造“预读后版本变化”，直接执行带 revision 条件的 UPDATE 命中 **0 行**，再走 `update()` → **409** 且事件数不变。

## 2. 参数与同源健壮性

- `revision` 只接受 **ASCII 正整数**（正则 `^[0-9]+$`）：`abc`、空串、`1.5`、`-1`、`0`、`1e3`、全角 `９`、空白 → **400 `revision_invalid`**，库不变（此前非整数会 500）。
- CSRF 比较改为**字节级** `compare_digest`，编码异常按 403 处理：Unicode（日文、emoji、超长、含 `\u0000`）坏 token → **403 而非 TypeError**。
- 同源：只要出现 `Origin`/`Referer` 就必须 `scheme ∈ {http,https}` 且 `netloc == request.host`；`null`、`file://x`、`//evil.example`、`http://`（空 netloc）、外站、`chrome-extension://`、`ftp://` 全部 **403**（不再“空 netloc 跳过”）；本地同源 `http://localhost` → 303 正常。

## 3. GET 零写改为严格比对

- `test_get_requests_do_not_write_workorder` / `test_get_zero_write_strict`：GET 前后比较 **`workorder` 与 `workorder_event` 全表快照** 且 **库文件 sha256 相等**（不再用 `GreaterEqual`）。
- `test_get_does_not_create_db`：库不存在时 GET 后**文件仍不存在**（GET 走 `connect_ro`）。
- 新增 `AtomicAndRejectTests` 使用 `WORKBENCH_SOURCE_FIXTURE=<scores.csv>,<top10.csv>` 指向**临时合成 CSV**（3 条：商品/教程/未归类），不再依赖生产 CSV 布局；生产布局仅保留原有 1 套基础用例。

## 4. e2e 凭据脱敏与清理

- 探针不再输出 csrf 值：`e2e_evidence.json` 现为 `csrf_present: true`，`pick.csrf = "***redacted***"`，并写明「测试凭据已脱敏…未触碰生产 runtime/secret_key」。
- 测试库与密钥改到 **`tempfile.mkdtemp()`**（`b1-e2e-*` / `b1-shots-*`），跑完删除密钥；报告目录下旧 `b1/tmp/` 已整体删除（`TMP_DIR_IN_REPORT=False`）。
- 生产 `runtime/secret_key` 前后一致（`d518e321…`，未被动过）。

## 5. 复跑与部署（真实 exit）

| 套件 | 结果 |
| --- | --- |
| B1 专项 | **`Ran 25 tests — OK`，exit=0**（原 16 → 25，新增原子/并发、revision 非法、Unicode CSRF、7 种 Origin/Referer、fixture 来源拒绝、严格零写） |
| 工作台全部 | **`Ran 87 tests — OK`，exit=0** |
| 原完整套件 | **`Ran 334 tests — OK`，exit=0，48.0s** |

**截图（隔离库、临时目录）**：`desktop_worksheet_list.jpg` 1440×900/65,120 B/`88c5ef19295e3a9d…`、`desktop_worksheet_detail.jpg` 1440×900/80,492 B/`73df8ade5a03835f…`、`desktop_worksheet_edit.jpg` 1440×900/74,249 B/`765eedd7487e7ec8…`、`mobile_worksheet_list.jpg` 390×844/42,175 B/`47f19c0d993f3a93…`；manifest **自校验 4/4 一致**，四视口 `overflowX=false`。

**部署**：只停本工具 5015 进程（111864、97968），同端口重启 **PID 98368**；`/worksheet` 200、导航含「商品工作单」、`/opportunities` 含选品表单；`/healthz` 仍 `app_id=workbench-opportunity/1`；5017 已停。
**守卫未变**：`instance/app.db e073f828…`、`CONTRACT.md 826c24cc…`、`importer.py a11eaf4d…`、`wiring.py bafcf397…`。

---

# rev8 补齐（受控 0 行用例 / 真实 subprocess 留痕 / 同源含 scheme / 守卫 baseline 比对）

## 1. 受控 0 行用例改用 `unittest.mock.patch`

`test_atomic_update_zero_rows_after_prefetch`：先建单并 `update` 到 **rev2（B 的改名）**，再 `mock.patch.object(wf, "get", fake_get)` 让 **`update()` 内部首次 `wf.get` 返回旧快照（rev=1）** → 预检放行，`UPDATE … AND revision=1` **命中 0 行**。断言：
- `Reject.status == 409` 且 **message 含「UPDATE 命中 0 行」**；
- `conn.in_transaction is False`（无残留事务）；
- 真实行仍为 **`B 的改名` / revision 2**；
- `workorder_event` 计数不变；
- **库文件 sha256 不变**。
原来的 `types.SimpleNamespace` 占位伪代码已删除。另一条两连接用例改名为 **`test_sequential_conflict_two_connections`（顺序冲突，非多线程并发压测）**。

## 2. 三套测试由真实 `subprocess.run` 执行并留痕

新增 `run_suites.py`：三条命令各自 `subprocess.run(argv, cwd=…, capture_output=True, text=True)`，输出 **`execution_manifest.json`**（`name/argv/cwd/start_utc/end_utc/returncode/summary_lines/stdout_file/stderr_file/stdout_bytes/stderr_bytes`），原始输出分文件保存在 `logs/<name>.stdout.txt`、`logs/<name>.stderr.txt`。**退出码取自 `returncode`，未手填。**

| name | argv | cwd | returncode | summary |
| --- | --- | --- | --- | --- |
| `b1_workflow` | `python -X utf8 -m unittest tests.test_workflow -v` | `tools/workbench` | **0** | `Ran 27 tests — OK` |
| `workbench_all` | `python -X utf8 -m unittest discover -s tests -t . -v` | `tools/workbench` | **0** | `Ran 89 tests — OK` |
| `project_full` | `python -X utf8 -m unittest discover -s tests -v` | 仓库根（`APP_DB_PATH=%TEMP%\b1_full.db`） | **0** | `Ran 334 tests — OK`（48.8s） |

`run_suites.py` 自身 returncode = **0**，`failed = []`。

## 3. 同源比较含 scheme

`require_local_write()` 改为比较 **`urlparse(origin)` 与 `urlparse(request.host_url)` 的 `(scheme, netloc)`**，任一不符即 403（不再只比 netloc、不再跳过空 netloc）。
新增 `test_origin_scheme_must_match_host_url`：服务为 http 时，`Origin: https://localhost`、`Referer: https://localhost/...` **均 403**；真正同源 `http://localhost` → **303**。线上实测：向 `POST /worksheet/new` 发送无 CSRF 的请求 → **403**。

## 4. 守卫清单与可追溯 baseline

新增 `guards_after.py` → `guards_after.json`：覆盖 **15 项**（`instance/app.db`、`CONTRACT.md`、`wiring.py`、`bilibili_view.py`、`importer.py`、`scoring/{scores.csv,items.jsonl,model.md,raw}`、`sourcing/{sources.csv,price_signals.csv,opportunity_sourcing_top10.csv,raw}`、`migrations`、`alembic`），逐文件 sha256 或目录 tree sha256，并记录 `mtime_utc`。

与 **`docs/validation/money-project/verify/baseline_before.json`（上一轮独立只读核验产物，含生成时间）** 及关键 hash 比对：**12 项可比，`changed_by_this_task = []`**。
仅 2 项与旧 baseline 不同，已逐条归因（`changed_external`）：
- `scoring/model.md`：外部评分产物重生成，`mtime 2026-10-22T11:19:49Z`（早于 B1 实施）；
- `sourcing/opportunity_sourcing_top10.csv`：外部货源联动重生成，`mtime 2026-10-22T09:49:48Z`。
`guards_after.py` 的退出码按 **`changed_by_this_task`** 判定，当前为 **exit=0**。

## 5. 部署与截图

- 只停本工具 5015 进程后同端口重启：**PID 127792**；`/worksheet` 200（导航含「商品工作单」）、`/healthz` 仍含 `app_id=workbench-opportunity/1`；5017 已停。
- **UI 未改动**，沿用 rev5 的 4 张截图与 `shots_manifest.json`（自校验 4/4 一致，哈希未变），未重拍以免制造无意义差异。
