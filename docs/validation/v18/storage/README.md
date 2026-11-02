# v18 单帖采集存储：实现与验证说明

> 状态：执行者提交、**待策划者独立验收**（未自行通过）。
> 范围：`tools/selection/storage/`、`tests/test_v18_storage.py`、本目录文档。
> 本任务只新增文件；旧模块 `records.py`、既有业务库/账本/历史导出均未改动
> （工作区里既有的未提交改动不属于本任务）。

## 1. 做了什么

面向单帖采集的最小隔离持久化：

- 库有**持久应用标识 + schema 版本**（`application_id=0x56313800`、`user_version=3`）；
  非空陌生库在任何写操作前拒绝，旧 v1/v2 库只有在 schema 逐列/索引核对通过后才原地迁移；
- 帖子/评论分表内区分（`kind`），身份 = `(platform, kind, native_id)`，部分唯一索引防重；
- 父级是**三态**：已知顶层 / 已知楼中楼父 ID / 父级未知；未知保留帖子归属并标
  复核，**不会默认成帖子的直接子评论**；
- 无原生 ID 的内容不伪造 ID，作为观察逐条保留，不按文本启发式合并；
- 未知值与 0 分开：`likes=NULL` 是未知，`0` 是确实为 0；旧记录标"不适用"的字段
  一旦采到实际值，导出时按实际值优先剔除不适用项，`missing`/`not_applicable` 互斥；
- 发布时间（原文/规范化/精度）作为一组合并，不会把新原文和旧规范时间拼在一起；
- 字段证据随实际采纳的值合并：拒绝的新值不改来源，采纳但没给证据时清空旧来源，
  正文/时间组/点赞/标题/作者/URL/父级升级都一致处理，避免来源串换；
- 正文截断 true/false/None 三态合并：旧无正文时新正文一律保留；已知完整不被
  截断摘要覆盖；同一文本的完整性可从"未知"升级为已知；
- 复核分两种：用户显式 `recheck=True` 一直保留；仅因无 ID/父级未知的自动复核
  在父级升级后自动清除；
- 同一内容 ID 的所属帖子/父级冲突、运行 target 不一致都会明确报错并整批回滚；
  父级允许"未知 → 有证据的已知"升级；
- 一次 `save()` 一个事务；同 `run_id` 续跑不重复，`begin_run()` 会清掉"已完成"
  但把旧停止原因留在 `run_stops` 历史里；
- 可读导出：完整 JSONL（含平台/父级三态/显式复核/精度/原始时间）＋ 23 列兼容 CSV/JSONL；
- 命令行入口与独立数据字典。

字段级语义见 [DATA_DICTIONARY.md](<DATA_DICTIONARY.md>)。

## 2. Python 调用示例

```python
from tools.selection.storage import Storage, Item, export_compat

with Storage(r"D:\data\v18.sqlite3") as box:
    run = box.begin_run("tieba", target_native_id="11066015202")
    box.save([
        Item(platform="tieba", kind="post", native_id="11066015202",
             url="https://tieba.baidu.com/p/11066015202", title="标题",
             text="正文", likes=None, comments_count=63,
             published_at_raw="10-31 12:34",
             published_at="2026-10-31T04:34:00Z",
             published_at_precision="minute", source="tieba:detail"),
        # 已知顶层评论：显式 parent_known=True
        Item(platform="tieba", kind="comment", native_id="1001",
             post_native_id="11066015202", parent_known=True,
             text="顶层评论", likes=0),
        # 已知楼中楼：给父评论 ID
        Item(platform="tieba", kind="comment", native_id="1002",
             post_native_id="11066015202", parent_native_id="1001",
             parent_kind="comment", text="回复"),
        # 父评论未知：保留帖子归属，parent 留空
        Item(platform="tieba", kind="comment", native_id="1003",
             post_native_id="11066015202", parent_known=False,
             text="父级不明的评论"),
        # 用户显式要求复核：普通重采/父级升级都不会清掉
        Item(platform="tieba", kind="comment", native_id="1004",
             post_native_id="11066015202", parent_known=True,
             text="需要人工复核", recheck=True),
    ], run_id=run)
    box.finish_run(run, stop_reason="cancelled")   # 取消：可续跑，不算完成
    export_compat(box, "tieba.csv", platform="tieba")   # 23 列兼容视图
```

续跑：`begin_run("tieba", run_id=run)` 传回同一 ID，再把检查点记录重新
`save()`；有 ID 的行合并、无 ID 的行追加观察。续跑会清空"已完成"状态，
旧停止原因仍能在 `run_summary()["stop_history"]` 里看到。

## 3. 命令行入口

```text
python -m tools.selection.storage init   --db <库路径>
python -m tools.selection.storage ingest --db <库路径> --platform tieba \
       --records <JSONL或JSON数组> [--run-id R] [--target <帖子ID>] \
       [--stop cancelled|end_signal|...] [--complete] [--declared N]
python -m tools.selection.storage export --db <库路径> --platform tieba \
       --out <文件> [--fmt csv|jsonl] [--full]
python -m tools.selection.storage stats  --db <库路径>
```

- `ingest` 只读本地文件，不联网、不启动浏览器；`--complete` 仅 `--stop end_signal` 可用。
- 记录文件按 UTF-8 读取，容忍 Windows 编辑器/PS 写出的 BOM；数字 ID 按文本保存。
- 旧 23 列记录导入时：`parent_id` 存在 → 已知父级；只有 `root_comment_id` →
  父级未知；两者都没有 → 拒绝导入（不猜帖子归属）。
- `export` 默认 23 列兼容视图（必须给 `--platform`）；`--full` 输出完整存储视图 JSONL。
- `init`/`stats` 输出 JSON；错误以非零退出码与 JSON 错误返回。

## 4. 库身份、拒绝与迁移

- 新建库写入 `PRAGMA application_id=0x56313800` 与 `PRAGMA user_version=3`；
  schema 创建在一个事务里，中断只会留下空库，不会留下半套表。
- 打开任何非空库前，先只读核对应用标识、版本、对象集合、逐列定义与具名索引：
  - 陌生库（含 `user_version=1`、同名表不同列、仅 views/triggers、非 SQLite 文件）
    → `not_a_v18_store`，**拒绝发生在 journal_mode/WAL/DDL 之前**，字节/表/journal_mode
    不变（有测试断言）；
  - 应用标识是别的值 → 同样拒绝；
  - 本模块 v1/v2（旧版生成的库）→ 逐列/索引核对通过后原地迁移到 v3：
    v1 补 `parent_known`、`resumes`、`run_stops` 并回填旧停止历史；v1/v2 都补
    `recheck_explicit`，把无法由身份/父级解释的复核标记迁成显式复核；迁移失败整体回滚；
  - 版本高于当前 → `schema_version_mismatch:N`，不写。
- 空库正常创建；自己创建的库重开可用。

## 5. 测试（精确命令与输出）

```powershell
$env:PYTHONUTF8='1'; .venv\Scripts\python.exe -m unittest tests.test_v18_storage -v
```

最近一次运行（完整日志：[evidence/tests_v18_storage.log](<evidence/tests_v18_storage.log>)）：

```text
Ran 87 tests in 1.600s

OK
```

覆盖与验收的对应关系：

| 验收点 | 测试 |
| --- | --- |
| 同 ID 不同平台 | `IdentityTests.test_same_native_id_on_different_platforms_is_two_rows` |
| 同 ID 帖子/评论不冲突 | `IdentityTests.test_post_and_comment_with_same_native_id_do_not_collide` |
| 同 ID 重复写入幂等、首见时间保留 | `IdentityTests.test_same_identity_is_idempotent_and_keeps_first_seen` |
| 无 ID 不伪造、可回查 | `NoIdTests.test_no_id_content_is_kept_without_fake_id` |
| 无 ID 不错误合并、重复观察计数 | `NoIdTests.test_no_id_observations_are_never_merged` |
| 无 ID 导出不冒充 supported | `NoIdTests.test_no_id_row_does_not_claim_support_in_compat_export` |
| 父级未知不默认成顶层 | `ParentTests.test_unknown_parent_is_not_defaulted_to_post` |
| 已知顶层 / 已知楼中楼 | `ParentTests.test_known_top_level_is_explicit`、`test_known_nested_parent` |
| 未知父级可升级为已知 | `ParentTests.test_unknown_parent_upgrades_to_known` |
| 已知父级不被未知降级 | `ParentTests.test_unknown_parent_does_not_downgrade_known` |
| 父级冲突回滚 | `ParentTests.test_parent_conflict_rolls_back` |
| 所属帖子冲突回滚 | `ParentTests.test_post_conflict_rolls_back` |
| 发布时间三字段成组 | `TimeGroupTests`（5 项） |
| 文本三态：旧无正文→截断→完整整链 | `TextTriStateTests.test_missing_body_then_truncated_then_full_chain` |
| 同文本完整性未知→已知 | `TextTriStateTests.test_same_text_completeness_upgrades_from_unknown` |
| 已知完整不被降级 | `TextTriStateTests.test_same_text_known_full_is_not_downgraded` |
| 完整不被截断摘要覆盖 | `TextTriStateTests.test_truncated_snippet_does_not_replace_full_body` |
| 不适用 vs 实际值互斥 | `NotApplicableTests.test_not_applicable_dropped_when_value_arrives` |
| 不适用保持（值仍未知） | `NotApplicableTests.test_not_applicable_kept_when_value_still_unknown` |
| 旧未知→新 0 不进 missing/不适用 | `NotApplicableTests.test_unknown_then_zero_is_neither_missing_nor_na` |
| 其他字段不丢失 | `NotApplicableTests.test_other_fields_survive_na_cleanup` |
| 完整视图同样清理不适用 | `NotApplicableTests.test_full_export_also_cleans_not_applicable` |
| 拒绝截断摘要时保留详情页来源 | `EvidenceMergeTests.test_rejected_summary_keeps_detail_evidence` |
| 缺正文→摘要→完整：来源随值走 | `EvidenceMergeTests.test_missing_body_then_summary_then_full_evidence_follows_value` |
| 时间组替换后不携带旧来源 | `EvidenceMergeTests.test_time_group_evidence_cleared_when_group_replaced` |
| 点赞来源随值走 | `EvidenceMergeTests.test_likes_evidence_follows_value` |
| 同值保留旧来源 | `EvidenceMergeTests.test_same_value_keeps_old_evidence` |
| 标题来源随值走 | `EvidenceMergeTests.test_title_evidence_follows_value_on_posts` |
| 显式复核：普通重采保留 | `RecheckTests.test_explicit_recheck_survives_ordinary_recollect` |
| 显式复核：父级升级保留 | `RecheckTests.test_explicit_recheck_survives_parent_upgrade` |
| 自动复核：父级升级清除 | `RecheckTests.test_auto_recheck_clears_on_parent_upgrade` |
| 无 ID 复核是自动的 | `RecheckTests.test_no_id_recheck_is_automatic` |
| 未知 vs 0 | `UnknownVsZeroTests.test_unknown_likes_stay_null_and_zero_stays_zero`、`test_unknown_is_not_exported_as_zero` |
| 重启恢复、续跑不重复 | `RunStateTests.test_restart_resumes_without_duplicates` |
| 中断的运行如实报 pending | `RunStateTests.test_interrupted_run_is_pending_not_complete` |
| 续跑清掉已完成、保留停止历史 | `RunStateTests.test_resume_clears_complete_and_keeps_stop_history` |
| complete 只允许 end_signal | `RunStateTests.test_complete_requires_end_signal` |
| run target 从证据补齐/冲突回滚 | `RunTargetTests`（5 项） |
| 两运行不串帖 | `RunTargetTests.test_two_runs_do_not_cross_posts` |
| 23 列映射（真实贴吧解析器产物） | `CompatTests.test_legacy_tieba_comment_round_trips_through_23_columns` |
| 23 列映射（帖子记录） | `CompatTests.test_legacy_thread_record_round_trips_through_23_columns` |
| 旧记录父级按证据处理 | `CompatTests.test_legacy_parent_equals_thread_is_top_level`、`test_legacy_missing_parent_is_unknown` |
| 23 列列名/顺序/数量 | `CompatTests.test_compat_csv_has_exactly_the_legacy_23_columns` |
| 旧 JSON 数字 ID 按文本保存 | `CompatTests.test_numeric_legacy_ids_are_kept_as_text` |
| 空库创建并打标识 / 自身重开 | `IsolationTests.test_empty_file_creates_store_and_stamps_identity`、`test_reopening_own_store_keeps_identity` |
| 陌生库拒绝且字节/表/journal_mode 不变 | `IsolationTests.test_foreign_db_rejected_unchanged`、同名表、仅 views、非 SQLite、别的 app id、未来版本各一项 |
| v1 旧库安全迁移 + 历史回填 | `IsolationTests.test_legacy_v1_store_is_migrated_with_history` |
| v2 旧库迁移 + 显式复核回填 | `IsolationTests.test_legacy_v2_store_is_migrated` |
| v1 旧库多表/多列拒绝且不变 | `IsolationTests.test_legacy_v1_with_extra_table_rejected_unchanged`、`test_legacy_v1_with_wrong_columns_rejected_unchanged` |
| 导入文件带 UTF-8 BOM | `CliTests.test_cli_ingest_accepts_utf8_bom_records_file` |
| 命令行入口可用 | `CliTests.test_ingest_export_stats_roundtrip`、`test_cli_rejects_complete_without_end_signal` |

23 列兼容的验证方式：把 `access.tieba.parse_comments_api` / `records.make_record`
产出的真实旧记录导入存储，再导出，断言与 `records.normalize_record(旧记录)`
**逐字段相等**；CSV 表头断言等于 `records.EXPORT_FIELDS`（23 列）。

## 6. 未实现与边界（与数据字典第 9 节一致）

1. 无稳定 ID 的楼中楼父评论：`parent_known=0`，不建本地父指针，只保留帖子归属。
2. v1 迁移无法恢复旧父级语义：v1 没有三态，迁移一律回填"已知"。
3. 点赞/正文变化快照：未做；后写已知值覆盖先写已知值，保留首见与最后见到时间。
4. 无 ID 行不自动升级为有 ID（避免错误合并），需人工核对；续跑时同一无 ID 内容
   会出现多条观察（有意语义，`save()` 的 `without_native_id` 如实计数）。
5. 无删除/修正接口；依赖重采合并或后续迁移。
6. 23 列没有平台列，兼容导出按平台分别生成；也没有 `parent_known` /
   `recheck_explicit`，未知父级只能从 `parent_id` 空 + `missing` 看出。
7. 未跑真实平台：本模块与测试全程离线，未发起任何真实站点请求；旧 live 证据的
   覆盖（顶层 18 条、楼中楼无稳定 ID、字段缺失）不代表全量。
8. `declared_count` 只记录声明值，不参与完成判定。
9. 只支持 v1/v2 → v3 迁移；更高版本拒绝，不降级；拒绝的陌生库不会被改动。

## 7. 隔离与安全

- 只写 `--db` / `Storage(path)` 指定的文件（没有隐式默认路径），示例不含真实账号信息。
- 打开非空、又不是本模块可验证 schema 的 SQLite 文件时直接拒绝，拒绝发生在任何
  写操作之前；测试断言字节哈希、表集合与 journal_mode 不变。
- 不读取 profile/cookie，不打印任何敏感内容。
- 本任务未改动旧 `records.py`、旧库、旧账本、历史导出（仅新增文件）。
