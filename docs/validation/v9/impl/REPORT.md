# V9-1b 实现报告：独立 selection 信号库 + B站首屏评论 + 闲鱼 imported

> 任务：`task-8f57be2722fe88b11bdea4f281814da9`（revision 5，计划 v9）；范围仅 `tools/selection/`、`docs/validation/v9/impl/`、`tests/test_selection_*.py`。
> 工作区：`D:\桌面\two`；实现/测试时间：2026-10-25 18:52–18:59 UTC+8（10:52–10:59Z）。仅标准库（sqlite3/urllib/json/hashlib/csv/argparse），无新增依赖。
> 未接 UI、未写 `instance/app.db`、未写 `tools/workbench/runtime/*.sqlite3`、未改既有 CSV/CONTRACT/冻结快照；真实小批次只写 `docs/validation/v9/impl/runtime/`。

## 1. schema（I1 目标的最小实现）

| 表 | 关键字段/约束 | 代码 |
| --- | --- | --- |
| `schema_migrations` | `version/name/applied_at`；重复 init 不重复 | `tools/selection/db.py:15-20,77-85` |
| `signals` | `id` 自增；`UNIQUE(platform,native_id)`；`origin_kind CHECK ('real','synthetic','imported')`；`collected_at_scope CHECK ('row','batch','unknown')`；`raw_ref NOT NULL`、`raw_sha256`、`content_hash`、`version` | `db.py:21-60` |
| `runs` | `batch_id UNIQUE`、`kind/platform/status`（running/complete/partial/failed/stopped）、`stop_reason`、`budget_json`、`stats_json`、`started_at/ended_at`、`raw_dir` | `db.py:61-64,126-147` |

- `content_hash` = SHA-256(canonical JSON `{platform,native_id,quote,listed_price_minor,effective_price_minor,wants}`)；见 `models.py:30-38`。
- `upsert_signal` 以 `(platform,native_id)` 为身份：新→new；同 `content_hash`→duplicate（0 新增）；内容变化→updated（`version+1`，并写回新 `content_hash`）；`db.py:94-123`。
- `init_db` 用 `CREATE TABLE IF NOT EXISTS` + `schema_migrations`，tempfile 可用；WAL/foreign_keys/busy_timeout 见 `db.py:66-85`。
- `stats` 输出 signals 总数、platform/origin 分布、最近 runs；`db.py:150-159`。

## 2. bilibili（只读、单页、可注入 fetch）

- 代码：`tools/selection/bilibili.py`；`collect` L111-253；`default_fetch` L33-56；`sanitize` L59-85；`_save_raw` L88-93；`_stop_for` L96-108。
- 请求顺序：`view`（aid/bvid）→ 评论 **第 1 页** `...&pn=1&ps=5&sort=2`（`REPLY_URL` L18；collect 内 URL 固定）；可选一次 `x/v2/reply/reply`（L19；仅 `include_subreply=True`）。
- 预算/间隔：默认 `budget=5`、`interval=3.0`；`request()` 在预算耗尽时写 `budget_exhausted`，每请求间隔；无重试。
- 停止条件：非 200、JSON `code` 非 0、`-412/-352`、网络错误；写 `stop_reason`；不翻第 2 页（代码没有 `pn=2`）。
- 脱敏：`sanitize` 移除 `uname/handle/avatar/sign/...`、`member/owner` 下 `name`、个人主页链接，正文 `@` → `@u***`；保留 `rpid/parent/root/mid/正文/count`。
- 真实批次：`bilibili-20261025T105316Z-7b7b2b`，`requests=2`、`comments=3`、`new=3`、`duplicate=0`、`status=complete`、`stop_reason=null`；`view` raw 236,653 B、`reply_p1` 39,578 B；sha 见 `sha_manifest.json`。argv/cwd/UTC/exit 见 `logs/bili_real_run.log`（exit 0）。
- 本批只取首屏，**未验证翻页/楼中楼深度**；可选 subreply 代码有桩测试，真实批次未开启。

## 3. xianyu（JSONL/CSV imported）

- 代码：`tools/selection/xianyu.py`；`_row_to_signal` L38-68；`import_file` L86-130；`native_id_from_href` L14-23；`_prices` L26-30；`_wants` L33-35。
- 实读源：`tools/platform-login/data/xianyu_items.jsonl`（只读，20 行，sha256 `c70f1580…`）。`href` 的 `id` 派生 native_id；缺失/非数字→错误行，不写库。
- `listed_price_minor` 由 `price`；`effective_price_minor` 取 raw 第一个 `¥`（`¥ 1 .88` → 188）；`reference_price_minor` 取第二个 `¥`（3 行）；`wants` 从 `N人想要` 解析，缺失保持 NULL；`lang_source=heuristic`；`collected_at_scope=batch`；`origin_kind=imported`；`raw_sha256` 为原始行字节哈希，`raw_ref=path#Lline`。
- 预算：`max_rows`/`max_errors` 实际检查；超限停止，status=`stopped`，stop_reason=`rows_exceeded`/`errors_exceeded`；`runs.raw_dir` 对导入为 NULL（不再指向输入目录）；`xianyu.py:86-140`。**注意**：本报告的真实 `xianyu.sqlite3` 是返工前旧批次，`runs.raw_dir` 仍为 `tools\platform-login\data`；按“真实批次不重跑”保留旧值，新代码/新测试已验证 NULL，未回写旧库。
- 真实导入：`xianyu_import-20261025T105329Z-ecbcb6`，`rows=20`、`new=20`、`duplicate=0`、`errors=[]`、`wants_missing=4`、`wants_present=16`、`wants_sum=8093`、`reference_present=3`、`effective_price_minor` 实测集合 `{100,109,110,188}`、`origin_kind=imported`、`status=complete`；argv/cwd/UTC/exit 见 `logs/xianyu_import.log`（exit 0）。
- 重导同内容在测试中为 `new=0/duplicate=1`；内容变化 `updated=1`、`version=2`；见 `tests/test_selection_xianyu.py`。

## 4. CLI

`tools/selection/cli.py`（argparse；单行 JSON）：

```powershell
.\.venv\Scripts\python.exe -X utf8 -m tools.selection.cli --db docs\validation\v9\impl\runtime\bilibili.sqlite3 --raw-dir docs\validation\v9\impl\raw run bilibili --aid 540769243 --budget 3 --interval 3
.\.venv\Scripts\python.exe -X utf8 -m tools.selection.cli --db docs\validation\v9\impl\runtime\xianyu.sqlite3 import xianyu --path tools\platform-login\data\xianyu_items.jsonl --collected-at 2026-10-22T08:46:35Z
.\.venv\Scripts\python.exe -X utf8 -m tools.selection.cli --db <db> stats
```

- `--db` 默认 `tools/selection/runtime/selection.sqlite3`；`--raw-dir` 默认 `tools/selection/runtime/raw`；真实批次显式指向 impl 隔离目录。
- `run bilibili` 支持 `--budget/--interval/--include-subreply/--origin`；`import xianyu` 支持 `--collected-at/--batch-id/--max-rows/--max-errors`；`stats` 只读统计。
- 退出码：complete→0；partial→0（stdout 保留 `stop_reason`）；failed→3（stdout `ok:false` + `stop_reason/error`）；参数/未知命令→2。实现见 `cli.py:48-81`。
- 输出示例（真实批次）：B站 `{"ok":true,"requests":2,"comments":3,"new":3,"status":"complete"...}`；闲鱼 `{"ok":true,"rows":20,"new":20,"wants_sum":8093,"origin_kind":"imported"...}`；完整见 `logs/*.log`。

## 5. tests（tempfile，无外网）

| suite | 结果 | 覆盖 |
| --- | --- | --- |
| `tests.test_selection_db` | 5 tests OK | init 幂等、origin CHECK、UNIQUE、content_hash 稳定、runs/stats |
| `tests.test_selection_bilibili` | 5 tests OK | sort=2/第 1 页、无 pn=2、raw 脱敏、预算耗尽、412 停止、重跑 duplicate、可选 subreply |
| `tests.test_selection_cli` | 4 tests OK | CLI complete/partial/failed 退出码、import rows/errors 预算、raw_dir null |
| `tests.test_selection_xianyu` | 4 tests OK | native_id 坏行、effective/wants、imported、重导 duplicate、内容变化 updated、CSV、wants NULL |

- 命令：`.\.venv\Scripts\python.exe -X utf8 -m unittest tests.test_selection_db tests.test_selection_bilibili tests.test_selection_xianyu tests.test_selection_cli -v`；`logs/tests_selection.log` exit **0**，`Ran 18 tests ... OK`，cwd `D:\桌面\two`，UTC 10:58:32Z。
- 所有测试用 `tempfile.TemporaryDirectory`；不连接外网，不写业务库/workbench。

## 6. real-run / guards

- B站真实：2 请求（view + 评论 p1），3 条 real 信号；`bilibili.sqlite3` 40,960 B；stats `{"by_origin":{"real":3},"signals":3}`；日志 `logs/stats_bili.log` exit 0。
- 闲鱼真实：20 行 imported；`xianyu.sqlite3` 69,632 B；stats `{"by_origin":{"imported":20},"signals":20}`；日志 `logs/stats_xianyu.log` exit 0。
- `sha_manifest.json`：raw（B站 view/reply）、只读源 JSONL、隔离 DB 的 bytes/sha256；`guards.json`：`instance/app.db e073f828…`、`workbench workflow.sqlite3 8ae79c58…`、CONTRACT `826c24cc…`、scores `ab0c3546…`、sources `13679b60…`，before==after。
- 未写 `instance/app.db`、workbench runtime、既有 CSV/冻结快照；未改 app/、tools/workbench/、CONTRACT。

## 7. 限制

1. B站只取第 1 页；真实批次未启用 subreply，楼中楼深度/后续分页/全量评论未验证。第 2 页历史实测为空，本实现禁止循环翻页。
2. 未接入其余 8 平台；未接 UI；未建品类/跨轮去重（下一阶段）。
3. 闲鱼是用户导出样本，不是实时采集；`wants` 是兴趣代理、不是订单/成交；`price` 是引流展示价，`effective_price` 仍是展示价；无评论/销量/作者字段。
4. 未验证登录后/高频/并发/长跑；无 cookie/登录；B站 raw view 236,653 B，未截断（任务未要求 200 KiB 上限；文件为脱敏 JSON）。
5. 未跑全量项目测试；只跑本任务 14 项；历史全量基线不在本批宣称。
