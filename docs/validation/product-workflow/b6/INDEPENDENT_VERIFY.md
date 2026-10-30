# B6 独立核验：就绪检查与导出

> 任务：`task-a792efc59b99150cc3f639f8ff6672c4`（计划 v7，独立核验；只读验证，不改代码/数据）。
> 结论：**整体 FAIL（1 个硬缺陷）**。就绪推导、导出白名单/版本戳、越级与跨站防护、四套测试、守卫哈希均 PASS；但 **`GET /worksheet/<id>/export` 会写 `workorder_export`**，违反“GET 零写”验收项。缺陷只记录，未修。

## 1. 环境与边界

- 工作台入口：`http://127.0.0.1:5015/healthz` 返回 `app_id=workbench-opportunity/1`（只 GET，未改生产数据）。
- 独立探测使用系统临时目录的 `WORKBENCH_WORKFLOW_DB` / `WORKBENCH_SECRET_FILE` / `WORKBENCH_SOURCE_FIXTURE`，未使用生产 `runtime/workflow.sqlite3`。
- 未打开/写 `instance/app.db`；只计算文件 sha256。
- 未登录平台、未采购、未发布；未改 `tools/workbench`、`runtime`、`scoring/sourcing`。

## 2. 源码审查（READ-ONLY / WRITE）

| 路由 | 行号 | 写库行为 | 保护 | 结论 |
| --- | --- | --- | --- | --- |
| GET `/worksheet` | `app.py:913-922` | `connect_ro()` 只读 | — | PASS |
| GET `/worksheet/<id>` | `app.py:924-944` | `connect_ro()` 两次只读 | — | PASS |
| GET `/worksheet/<id>/edit` | `app.py:946-957` | `connect_ro()` 只读 | — | PASS |
| POST `/worksheet/new` | `app.py:959-971` | `wf.connect()` + INSERT | `require_local_write()` | PASS |
| POST `/worksheet/<id>/edit` | `app.py:973-992` | UPDATE + 审计 | `require_local_write()` | PASS |
| POST `/worksheet/<id>/evidence` | `app.py:994-1012` | UPDATE + 审计 | `require_local_write()` | PASS |
| GET `/worksheet/<id>/export` | `app.py:1014-1052` | `wf.connect()` + `rd.record_export()` **INSERT** | 无 CSRF/Origin（GET） | **FAIL** |

- `require_local_write()`：`app.py:863-880`，校验 session CSRF + `Origin/Referer` 的 `(scheme, netloc)` 与本站一致；缺失 token 403，外站/跨协议 403。
- `connect_ro()`：`workflow.py:92-102`，`mode=ro` URI；列表/详情/编辑均使用它。
- `readiness()`：`readiness.py:46-83`，七项由记录字段/证据推导，`overall_ready=all(checks)`；没有“标记就绪”入口。
- `normalize_evidence()` 拒绝 `status/ready/gate_*/verified` 等字段（`readiness.py:165-207`；`workflow.FORBIDDEN_FIELDS`）。

**缺陷 D1（高）**：`app.py:1019` 为导出打开 **读写** `wf.connect()`，`app.py:1034` 调用 `rd.record_export()`，后者 `INSERT INTO workorder_export` 并 commit（`readiness.py:247-256`）。因此 GET 导出会新增导出行；外部 GET 链接可触发该写。与 `g1` “GET 不写库”冲突。同时 `b3_export` 测试未断言导出行数，未捕获此回归。

## 3. 四套测试（独立复跑）

| 套件 | 命令（cwd） | UTC（start→end） | exit | 结果 |
| --- | --- | --- | --- | --- |
| b1_workflow | `...\.venv\Scripts\python.exe -m unittest tests.test_workflow -v`（`tools/workbench`） | 12:06:20→12:06:24 | **0** | Ran **27** / OK |
| b3_export | `...\python.exe -m unittest tests.test_export -v`（`tools/workbench`） | 12:06:24→12:06:26 | **0** | Ran **10** / OK |
| workbench_all | `...\python.exe -m unittest discover -s tests -v`（`tools/workbench`） | 12:08:18→12:08:24 | **0** | Ran **99** / OK |
| project_full | `...\python.exe -m unittest discover -s tests -v`（项目根） | 12:08:24→12:09:12 | **0** | Ran **334** / OK |

- 实测 workbench_all 为 **99**，不是提供方声称的 98；不影响通过，但基线数字需更正。
- 日志：`logs/{b1_workflow,b3_export,workbench_all,project_full}.log`，均含 argv/cwd/UTC/exit。
- 测试均使用临时 DB/secret；无生产库写入。

## 4. 导出两态实测（隔离库）

脚本：`probe_export.py`；结果：`export_probe.json`；日志：`logs/export_probe.log`。

| 检查 | 结果 | 结论 |
| --- | --- | --- |
| 未就绪 GET export | **409**；body 含“未选货源”；export 行 0→0 | PASS |
| GET 详情 | workorder 1→1、export 0→0 | PASS |
| 就绪 GET export | **200**，`Content-Disposition: attachment`；export 行 **0→1** | **FAIL：GET 写库** |
| buyer 白名单 | `buyer_visible_fields = title, selling_points, contents, format, price, delivery, aftersales, faq` | PASS |
| 内部字段扫描 | 递归 key/string：`internal_keys=[]`、`internal_hits=[]`、`has_cost=false` | PASS |
| 版本戳 | `revision, copy_version, supply_id, supply_version, generated_utc, contents, stamp_hash` 均存在 | PASS |
| 旧戳失效 | 改 `copy_version` 后 `valid=false`，`changed=['工作单版本','文案版本']` | PASS |
| 泄露自检 | `build_export` 含内部标记 → **409 `export_internal_leak`** | PASS |

- 导出 JSON 包含 `version_stamp`/`buyer_visible_fields` 元数据；业务内容无 cost/profit/margin/score/internal/raw_ref/snapshot。
- `record_export` 的写行为是 D1 的证据；非测试误报。

## 5. 越级与串改

| 场景 | 响应 | 库状态 | 结论 |
| --- | --- | --- | --- |
| POST evidence 伪造 `ready/verified/gate_cost/status` | **403** | 不变 | PASS |
| POST evidence 跨站 `Origin: http://evil.example` | **403** | 不变 | PASS |
| POST evidence 跨协议 `Origin: https://localhost` | **403** | 不变 | PASS |
| `revision=abc / 1.5 / -1` | **400 / 400 / 400** | 不变 | PASS |
| 无 CSRF | 403（代码审查 + 现有 B1 测试） | 不变 | PASS |

- 没有发现绕过 `readiness()` 直接置 ready 或导出的 POST/GET 捷径。
- `selected_supply_id` 只作为证据字段保存；未通过 `readiness` 不会导出。

## 6. 守卫哈希（B6 前后）

`baseline_before.json` / `baseline_after.json` / `hash_compare.json`：

- `instance/app.db`：`e073f828…4EB85`，前后 same；`wal=false, shm=false`。
- `docs/design/CONTRACT.md`：`826c24cc…` same。
- `app/sources/{wiring,bilibili_view}.py`、`app/core/importer.py`：same。
- `scoring/scores.csv`：`ab0c3546…` same；`sourcing/{sources,price_signals}.csv` same。
- `app/storage/migrations/*` 2 个文件：same。
- 共 **10** 个守卫文件全部 same；B6 未写生产库/契约/迁移。

## 7. 缺陷与未覆盖

**D1（高，FAIL）**：GET 导出写 `workorder_export`，违反 GET 零写；无 CSRF/Origin，因 GET 可被外部链接触发。修复建议（仅记录，未执行）：将导出记录改为 POST 显式动作，或使用只读/不落库的导出并以服务端版本戳校验，不因 GET 产生状态变更。

**未覆盖/限制**：

1. 用 Flask `test_client` 而非独立 5015 生产实例做两态导出/越级；只对 5015 做 `/healthz` 只读确认。
2. 未做真实浏览器/手机 UI 截图；B6 对象是路由与数据边界。
3. `workbench_all` 实际 99 项（声称 98），未逐项比对差异；只记录实际 Ran。
4. `GET export` 的写行为是设计选择还是回归需实现者确认；本报告按验收项判 FAIL。
5. 未验证并发导出、导出文件下载完整性、真实买家内容语义正确性。
6. 未打开生产 `instance/app.db` SQL，只做文件哈希。

## 8. 证据

- `INDEPENDENT_VERIFY.md`（本文件）
- `export_probe.json`、`probe_export.py`、`logs/export_probe.log`
- `baseline_before.json`、`baseline_after.json`、`hash_compare.json`
- `logs/{b1_workflow,b3_export,workbench_all,project_full}.log`
- `logs/health.json`（5015 只读 healthz）
