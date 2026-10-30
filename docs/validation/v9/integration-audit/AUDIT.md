# V9-5a 独立联调审计（非实现者）

> 任务：`task-6a539632221b537065c0e96bed257e5e`（revision 2，计划 v9）。
> 范围：只写 `docs/validation/v9/integration-audit/`；源码、业务库、工作单库、历史 CSV 未改。
> 方法：隔离临时 DB + Flask `test_client` + 仅替换 B 站 fetch 传输桩；状态机、路由、分类、卡片、导入均为真实实现。没有启动浏览器、没有联网、没有登录/发布/采购。

## 0. 结论摘要

- **9/9 关键联调实验 FAIL**（0 PASS）；不是测试全绿就代表链路可用。
- 最严重：**merge 在有卡片时抛 UNIQUE 且留下半合并状态**；**undo 把 target 原有事件全部搬走**；**UI resume 只改状态不发请求**；**UI start 后没有品类/卡片**；**cancel 后仍发 reply 并以非法 transition 结束**。
- 已证实可复现；非“配置问题/截图问题”。单模块测试（38 项）全绿，但没有覆盖这些边界。

## 1. 复现方式

```powershell
D:\桌面\two\.venv\Scripts\python.exe -X utf8 docs\validation\v9\integration-audit\run_audit.py
# exit=0；结构化结果 audit_results.json；日志 audit_run.log

D:\桌面\two\.venv\Scripts\python.exe -X utf8 -m unittest `
  tests.test_selection_db tests.test_selection_bilibili tests.test_selection_xianyu `
  tests.test_selection_cli tests.test_selection_categories tests.test_selection_rounds `
  tests.test_selection_rounds_state tests.test_selection_leads -v
# exit=0；Ran 38 tests / OK；日志 selection_tests.log
```

- 环境变量在导入 app 前设置：`V9_SELECTION_DB`、`WORKBENCH_WORKFLOW_DB`、`WORKBENCH_SECRET_FILE`、`APP_DB_PATH` 全部指向 `TemporaryDirectory`。
- 网络传输桩只控制 `/view`/`/reply` 的响应；`collect_round`、`rounds.*`、`categories.*`、Flask 路由均真实执行。
- 未使用默认 `tools/selection/runtime/selection.sqlite3`、`instance/app.db`、`tools/workbench/runtime/workflow.sqlite3`。

## 2. 实验总表

| # | 实验 | 预期 | 实际 | 判定 | 代码/证据 |
| --- | --- | --- | --- | --- | --- |
| E1 | UI 开轮后卡片 | POST `/leads/round` 请求 2 次，signals≥1，categories/cards≥1 | 303；calls=2；signals=2；**categories=0/cards=0/events=0**；round complete | **FAIL** | `app.py:1403-1434`；`categories.py:162-205`；`audit_results.json` E1 |
| E2 | UI Continue/Resume 实际请求 | paused 后 POST resume 触发 reply，requests_used 增加，reply 不再 pending | 303；calls **1→1**；status running；reply **pending**；signals=0；stats requests_used=1 | **FAIL** | `app.py:1436-1454`；`rounds.py:105-120`；E2 |
| E3 | 重复 categorize | 重复扫描不新增事件；review 不重复 | events **1→3→5**；categories=1；run2/3 各 update=2；review **2**（同一 unknown 跑两次） | **FAIL** | `categories.py:162-175`；E3 |
| E4 | 卡片新证据刷新 | 同品类新 signal 后 card.evidence_ids 含 1,2 | card.evidence_ids 仍 **`[1]`**；`make_cards` created=0 | **FAIL** | `categories.py:178-205`；E4 |
| E5 | excluded/merged 归属 | excluded→review/new；merged→target 或 review | 两者均 `update` 到 **source id=1**；excluded 状态仍 excluded，merged source 仍 merged | **FAIL** | `categories.py:106-126,224-237`；E5 |
| E6 | split/undo | undo 恢复 signal 事件/卡片到原 category | split 后 signal1 事件在 new id=2；卡片仍 `[1,2]`；undo 只追加事件，**new id=2 保留、事件仍在 2** | **FAIL** | `categories.py:240-266,289-313`；E6 |
| E7 | 导入坏 JSON + max_rows | 坏行报告后继续第三行，status partial；max_rows=1 只处理 1 行 | 坏 JSON **JSONDecodeError** 抛到外层；status failed；signals=1（第三行未导入）；max_rows 侧 rows=1/stopped | **FAIL** | `xianyu.py:71-83,105-133`；E7 |
| E8 | 载体/来源隔离 | notion→excel 同需求 1 category；imported→real 不静默覆盖 | **2 categories**；同内容 real=duplicate（保持 imported）；**改内容 real=updated 后 origin_kind=real/version2** | **FAIL** | `categories.py:30-36,58-61`；`db.py:45,175-204`；E8 |
| E9 | merge 有卡片 + undo | 两 category 各有卡时 merge 可原子完成；undo 不搬 target 原事件 | merge 抛 **UNIQUE constraint failed: direction_card.category_id**；source 已 merged、events 已移；undo 后 target events **1→2→0**，source=4 | **FAIL** | `db.py:93-103`；`categories.py:224-266`；E9 |
| E10 | cancel/interval/idempotency | cancel 后停；interval=3 实际等待；同 key 不同参数冲突 | cancel 后仍发 reply（calls=2），最终 `illegal_transition:cancelled->complete`；interval 0.016s；同 key 不同 budget 复用 draft | **FAIL** | `bilibili.py:284-372`；`rounds.py:44-56`；E10 |

> E3/E4 同一次实验拆成两条验收点；E5 同时测 excluded 和 merged；E9/E10 是额外的数据完整性/轮次反例，不是凑数。

## 3. 关键复现证据

### E1 UI 开轮后无卡片

- 真实 `POST /leads/round`（fetch 桩）→ `303 /leads?msg=round 1 complete requests=2`。
- DB：`signals=2`、`categories=0`、`direction_card=0`、`discovery_event=0`、round=`complete`。
- 原因：`leads_round_start` 只 `start + transition + collect_round`，没有调用 `categories.run_categorize`/`make_cards`；这两个只在 CLI `categorize` 中被调用（`cli.py:103-110`）。
- 影响：用户从选品页开轮只能得到 raw signals，不能看到商品方向卡；与 V9-5“开轮→卡片”不符。

### E2 UI resume 只改状态

- 先让 round 在 view 后暂停：`paused`，cursor=`bilibili:view`，reply `pending`，requests_used=1，fetch calls=1。
- POST `/leads/round/<id>/resume` → 303 成功；round=`running`，reply 仍 `pending`，requests_used=1，fetch calls **仍 1**，signals=0。
- 原因：`app.py:1444-1445` 只调用 `sel_rounds.resume`，无 `collect_round`；`rounds.resume` 仅把 processing→failed/interrupted 并转 running。
- 影响：页面显示“继续成功”，实际没有继续采集；用户需再点“run”但 UI 没有该动作。

### E3/E4 重复 categorize 与卡片不刷新

- 第一次：events=1，card=1，evidence=`[1]`。
- 加同品类 signal 2，再跑：events=3（2 条 update 各一条），card created=0，evidence 仍 `[1]`。
- 再跑一次：events=5（无新信号仍每信号 update）。
- unknown signal 跑两次：`review_queue=2`，同一 signal 重复 pending。
- 原因：`run_categorize` 全表重扫，`categorize_signal` 对 exact key 无条件 `_event(update)`；`make_cards` 对已有 card 直接 `continue`，不更新 `evidence_ids_json`；review 无唯一约束/去重。

### E5 excluded/merged 归属

- 先 `exclude(c1)`；新增 exact 同 identity signal → outcome=`update`，`category_id=1`（status=excluded）。
- 先 `merge(c1→c2)`；新增 exact c1 signal → outcome=`update`，`category_id=1`（status=merged），target=2 未被选中。
- 原因：`_category(conn, key)` 不检查 status；`categorize_signal` 不把 merged 转到 `merged_into`，也不把 excluded 送 review。

### E6 split/undo

- 原 category 有 signal1/2 + card evidence `[1,2]`；split signal1 → new category 2；signal1 的 `new/split` 事件均在 2；原卡仍 `[1,2]`（无新卡）。
- `undo(split_event)` 只写 `undo` 事件；new category 2 仍 active，signal1 事件仍在 2，卡片仍 `[1,2]`。
- 原因：`undo` 只处理 `merge`/`exclude`，无 `split` 分支；`split` 移动 `discovery_event`，不动 `direction_card`。

### E7 导入坏 JSON

- 输入：有效行（id=1001）→ 坏 JSON → 有效行（id=1002）。
- 结果：第一行已写；第二行 `json.loads` 在 `_read_rows` 生成器内抛出，外层 `import_file` 捕获后 `finish_run(failed)` 并 **re-raise**；第三行未读；signals=1，status=failed。
- `max_rows=1` 时 3 行输入只处理 1 行，status=stopped，stop_reason=rows_exceeded；预算这一项 PASS。
- 原因：JSONL 解析在单行 `try` 之外；`for` 捕获不到生成器解析异常。

### E8 载体/来源

- `学习计划 Notion` 与 `学习计划 Excel`（同 audience/task/locale）→ **2 个 categories**，因 `deliverable_family` 进入 identity；违反“仅换载体不算新品”。
- imported signal 写 `native_id=50`；同内容 real → `duplicate`，origin 仍 imported；**改内容 real** → `updated`，`origin_kind=real`、version=2。即 provenance 会被合法更新路径覆盖，不是不可变。

### E9 merge 有卡片

- 两 category 均有 card；`merge(c1→c2)` 在 `UPDATE direction_card SET category_id=2 WHERE category_id=1` 处抛 `UNIQUE constraint failed: direction_card.category_id`。
- 抛出前已 `UPDATE categories source status=merged`、`UPDATE discovery_event category`，**无事务回滚**；最终 source merged、events 已移、两张 card 各指原 category。
- `undo` 后 target 事件 1→2→0，source=4；说明 undo 把 target 原本事件也迁回 source，不是只回滚 source 的部分。

### E10 cancel/interval/idempotency

- cancel 由 fetch 在 view 请求内触发；循环只检查 `status == "paused"`，于 是继续发 reply；结束后 `transition(cancelled→complete)` 抛 `ValueError`。最终 status cancelled，但 items view/reply 都 done，signals=2，调用 2 次。
- interval=3.0 传入 `collect_round` 未被使用；两请求总耗时 **0.016s**。
- 同 idempotency key、不同 budget（3→5）第二次 `start` 返回同一 round（reused=true），budget_json 仍 3，无参数冲突检测；视频 aid/bvid 也未纳入 key。

## 4. P2–P7 缺口矩阵

| 判据 | 当前证据 | 结论 |
| --- | --- | --- |
| **P2** 10 平台矩阵 + ≥3 真实适配器（评论+交易） | 矩阵 10 行；真实自动仅 B站 1（A 任务），闲鱼 20 条 imported；微博/贴吧受阻；其余未验证 | **未达成**（只有 1 个真实自动 + 1 个导入） |
| **P3** 开轮/进度/暂停/继续/取消/历史 | 页面有按钮；E2 resume 不发请求；E10 cancel 越界、interval 失效、idempotency 不校验；E1 无卡片 | **未达成** |
| **P4** 可追溯商品方向卡 | 卡由 CLI `categorize` 生成，UI 开轮不生成；E4 新证据不刷新卡；规则字段/人群词硬推断 | **部分/未达成**（单模块可生成，UI 全链路不通） |
| **P5** 跨轮去重、旧更新、待判重、撤销 | E3 事件/review 重复；E5 merged/excluded 误归属；E6 split undo 不恢复；E8 载体分裂 | **未达成** |
| **P6** 新信号→品类→工作单→货源→文案→四门/七项→导出→发布→反馈 | 无 UI 从 signal 到 category/card 的桥；本审计未发现选品→工作单路由；无真实交易 | **未达成**（仅单模块/合成片段） |
| **P7** 数据/回归/部署/回滚/隔离 | 临时 DB 隔离、10 guards 哈希 same；但 origin 可被更新覆盖；无真实经营 | **部分**（隔离与哈希 PASS，数据语义未完全隔离） |

### 状态分层（不要混用）

- **单模块测试通过**：selection 38 tests OK；不覆盖 UI resume/start、merge 有卡、bad JSON。
- **合成链路可运行**：本审计 E1/E2/E3 在 temp DB 跑通调用，但结果正是 FAIL。
- **真实平台可采**：B站 1 平台（A 实测）；闲鱼导入；其他未验证。
- **真实经营**：无（未登录/发布/采购，无真实成交/反馈）。

## 5. 最小修复顺序

### P0（数据完整性/状态错误，先修）

1. **merge 原子性 + 卡片冲突**：`BEGIN IMMEDIATE`；两卡存在时先明确策略（合并证据到 target card / 保留 source card 标记 merged，不可 UNIQUE 失败）；失败必须 rollback，source 不得半 merged。
2. **undo(merge) 精确回滚**：按 before/after 记录 source-origin 的 event/alias/card id；只迁回属于 source 的部分，不搬 target 原有事件；split undo 恢复 `discovery_event.category_id`/卡片 evidence 并保留审计。
3. **cancel 循环**：每 item 前后检查 `cancelled`；cancelled 不执行 `transition(complete)`；已发请求/已完成 item 如实记录，不追加 reply。

### P1（用户可见主链路）

4. **UI resume**：`/leads/round/<id>/resume` 在 `rounds.resume` 后调用 `collect_round`（或统一 `run_round` 动作），并返回真实 requests/done/pending；不能只改状态。
5. **UI start→卡片**：开轮完成后（同一事务或明确的下一步）调用 `run_categorize + make_cards`；页面展示新卡；失败不得显示 complete。
6. **persist interval / idempotency**：budget_json 写入 interval/max_pages；同 key 但 aid/bvid/budget/interval 不同时拒绝/新建并提示，不能静默复用。

### P2（去重/卡片/导入）

7. **categorize 幂等**：按 signal/处理版本记录已处理；`discovery_event`/`review_queue` 去重；`make_cards` 对已有卡更新 evidence/gaps，而不是 continue。
8. **状态感知归类**：excluded → review/new；merged → `merged_into` target 或 review；不向 source 追加 update。
9. **identity 载体**：从 identity 移除/归一化 carrier（notion/excel 同交付族），或显式版本规则；卖家商品卡与用户需求分层；origin 不进入 identity 但写入 signal 的可变更新需审计/冲突。
10. **JSONL 坏行**：逐行 `try json.loads`，坏行记 errors 后继续；`max_errors` 达限时 partial/stopped；不要把整批作 failed。
11. **测试**：为上述 10 条各加最小回归；特别是 merge-with-cards、split-undo、UI resume、cancel、bad JSON。

## 6. 已知限制/未验证

- E1/E2 使用 Flask `test_client` + fetch 桩，没有真实 5015/浏览器；不能证明真实网络/登录行为。
- E3–E10 是纯函数/临时 SQLite 复现；不代表生产 selection 库；未改生产数据。
- 没有验证真实平台采集的 3 平台、真实发布/反馈/复盘；B站仅 A 任务已有 1 页证据，闲鱼仅导入。
- 未跑 workbench/项目全量回归；本轮 selection 38 项通过，但“全绿不等于行为正确”。
- 未调用 `ponytail`/`impeccable`/`stealth-browser-mcp` 工具（当前工具面无 skill 调用入口）；按最小实现/静态审阅完成；页面仅 headless test_client，无截图。
- 所有 DB/secret 在 `TemporaryDirectory`；`audit_results.json` 里为临时路径，运行结束已清理。

## 7. 证据

- [run_audit.py](run_audit.py)：复现脚本（9 实验；temp DB；fetch 桩）
- [audit_results.json](audit_results.json)：结构化结果（verdict/actual/code_refs/hashes）
- [audit_run.log](audit_run.log)：真实 argv/cwd/UTC/exit=0
- [selection_tests.log](selection_tests.log)：38 tests / OK / exit=0
- [guard_compare.json](guard_compare.json)：B14 守卫 10/10 same；workorder 8ae79c58…
- [sha_manifest_audit.json](sha_manifest_audit.json)：AUDIT/脚本/结果/日志哈希
- 代码：`tools/workbench/app.py:1403-1454`、`tools/selection/bilibili.py:256-374`、
  `tools/selection/categories.py:106-313`、`tools/selection/db.py:45,175-204`、
  `tools/selection/rounds.py:44-120`、`tools/selection/xianyu.py:71-138`
