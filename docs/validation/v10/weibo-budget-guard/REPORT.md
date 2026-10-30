# V10-6 预算守卫（第 4 轮返工）：清单绑定 + 事务内锁 + 结算失败清空

> 任务 `task-b8a8fa649709c34f8412ed81e1aee5df`（rev11，计划 v10）。
> **纯离线**：未联网、未启动浏览器、未读 profile/cookie、未改真实账本与业务库。
> 执行日期：**2026-10-29**（UTC 14:14–14:21）。

---

## 1) 历史清单绑定规范路径（禁止"同库冒充所有来源"）

- 每个清单项解析为**唯一规范路径** `canonical_source_path(spec)` = `REPO_ROOT / spec.path / budget.sqlite3`。
- `import_snapshot(sources, manifest=None)`：
  - 默认用生产清单 `HISTORY_SOURCES`；**注入清单**必须显式传入，快照内标 `test_only=True`。
  - **生产账本**（`allow_test_manifest=False`）读到 `test_only` 快照 → `history_manifest_not_allowed`。
  - 未声明的 key → `history_source_undeclared`；同一规范路径出现两次 → `history_manifest_duplicate_path`；行路径与声明不符 → `history_source_mismatch`。
- `_verify_history_gate()`（**在 charge 事务内**）逐项校验：快照存在 → 清单路径唯一 → 行路径 == 规范路径 → **现查非空 `-wal`/`-shm`** → 现读源库 → **先判锁** → 再比指纹。
- 锁继承：gate 在**同一权威库事务内** `INSERT locks`，返回拒绝对象；`charge` **先 COMMIT（锁落库）再抛 `history_locked`**。锁写失败 → 回滚并抛 `lock_write_failed`（调用方映射为非零、fail closed），**不 suppress**。
- **不用过时快照判未锁**：每次都现读源库的 `locked` 列；快照指纹只用于判"变更"。

测试：`test_snapshot_may_not_point_two_keys_at_one_source`、`test_locked_source_is_inherited_and_blocks_the_charge`、`test_wal_appearing_after_the_import_blocks_the_charge`、`test_charge_refuses_after_a_source_changes`、`test_charge_refuses_without_an_imported_snapshot`、`test_missing_source_fails_closed`、`test_corrupt_source_fails_closed`、`test_wal_sidecar_is_treated_as_uncertain`。

---

## 2) 详情解析 risk 也写平台锁

`run_detail` 的解析层 `risk:` 分支（`parse_detail_html` 判墙）现在：本地 `batch.lock()` + **平台 `_platform_lock()`**；写失败 → `exit=6, stop=platform:lock_write_failed`。
测试：`test_detail_parse_risk_locks_the_platform_across_state_dirs` —— 详情墙后平台已锁，**换一个 state-dir** 再搜索仍被 `platform:platform_locked` 拒绝。

---

## 3) 结算失败：非零 + 清空记录

- `_platform_result()` 写失败 → payload 置 `ok=False`、`exit=EXIT_BUDGET`、`records=[]`、`result_persisted=False`、`stop=platform:result_write_failed:<Exc>`。
- `fetch` 抛异常：装饰器捕获 → **结算 unknown**，返回 `ok=False`、`exit=EXIT_TRANSPORT`、`records=[]`、`stop=adapter_exception:<Exc>`，并记录 `search_result`（预扣不退）。
- 登录：`browser unavailable`、启动异常、超时、risk 全部经 `_login_settle()` 落 `active_nav_result`。

测试：`test_settle_failure_clears_records_and_exits_nonzero`、`test_fetch_exception_settles_unknown_and_fails_closed`、`test_login_browser_unavailable_still_records_its_outcome`、`test_result_write_failure_is_not_silent`。

---

## 4) 豁免只认"已知永不联网"的拒绝型传输

- 删除任意 `offline` 属性判断；改为 **`type(transport) is transport_mod.RefusedTransport`**（其 `fetch` 直接返回 `network_disabled_offline_batch`）。
- `PublicHttpTransport`、`AuthenticatedBrowserTransport`、测试替身**一律必须带平台账本**；缺账本 → `platform:guard_required`，不 fetch、不启动浏览器。
- 测试：`test_public_http_without_a_ledger_is_refused`、`test_direct_search_without_guard_is_refused_before_any_fetch`、`test_login_without_guard_is_refused_and_never_launches`。

---

## 5) 上限与"审计种子"

- `records_cap` 硬上限 **5**；`authorized_calls` ∈ [1, 20]；`seed_used` ∈ [0, authorized_calls-1]；`window_seconds` ∈ (0, 300]；越界 → `invalid_authorization`。
- **种子来自已审计来源**：`authorize_batch(..., seed_from=("login-window-1","login-window-2"))` 从快照的 `uncharged_navigation` 行推导 `seed_used`；key 不存在或分类不符 → `seed_source_unaudited`。**两次已发生登录不会被漏计**，也不接受调用方随手填数。
- 对已批准批次 `weibo-verify-1`（cap 3 + seed 2）实测：`used=2, remaining=1` → 扣 1 次后 `remaining=0`，再扣 `calls_exhausted`；**seed 不受滚动窗口过滤**（超过 300s 仍算已用，窗口关闭拒绝且不重开）。
- 两个 state-dir 行为级测试：`test_records_cap_is_shared_by_two_state_dirs_and_never_over_emits`（3+3>5 → 第二次零输出）、`test_interval_is_enforced_across_two_state_dirs`。

---

## 6) 执行记录（UTF-8 + 精确 UTC）

```json
{"total_tests": 229, "total_skipped": 0, "all_green": true}
  tests.test_access_weibo      exit=0 ran=90 skipped=0 failures=0 errors=0
  tests.test_access_zhihu      exit=0 ran=96 skipped=0 failures=0 errors=0
  tests.test_access_budget     exit=0 ran=43 skipped=0 failures=0 errors=0
```

- `RUN_MANIFEST.json`：每模块 argv / cwd / **精确 UTC** / exit / skip / failures / errors
- 原始日志（UTF-8、无 BOM）：`test_access_{weibo,zhihu,budget}_stderr.log` 与 `*_stdout.log`
- 期间修掉：重复类定义互相遮蔽、测试夹具把 9 个 key 指向同一临时库（改为 9 个独立临时源 + 注入清单）、账本未在临时目录清理前关闭、`unmetered` 残留、锁继承被回滚吞掉。

---

## 7) 历史与真实库状态

- 9 个历史 `budget.sqlite3` 只读打开（`mode=ro&immutable=1`），mtime 仍 **2026-10-27**。
- **真实权威库未初始化**：`tools/selection/access/runtime/platform_weibo.sqlite3` 不存在。
- profile 未触碰；业务库/CSV/CONTRACT 五哈希不变。

---

## 8) 配额算术（不擅自执行）

上限 3 − 已发生 2 次登录（由审计来源推导的 seed）= **账本强制 remaining=1**；`check-session` + 搜索需 2 次 → **不能同时执行**。本轮未执行任何真实动作，未追加额度、未改历史。

---

## 9) 未实现项与限制

1. **真实站点未验证**：全部结论来自离线测试与 stub。
2. **真实权威库未落库**：默认路径不存在；真实历史快照**未导入**真实库。
3. 测试用**注入清单**（`test_only=True`）指向临时源；生产清单的真实路径绑定由 `history_source_mismatch` 逻辑保证，但**未在真实库上跑过**。
4. `seed_from` 依赖已导入快照；若尚未导入快照，`authorize_batch` 会因 `seed_source_unaudited` 拒绝（这是有意的 fail closed）。
5. `_open_guard` 仍是代码级接缝（信任边界）。
6. 两次登录导航无时间戳、probe1 是否真发请求无法判定。


---

## 10) 第 5 轮最小补丁（rev14）

1. **`_login_settle` 结算失败 = 真失败**：`status=unknown`、`signed_in=false`、`exit=EXIT_BUDGET(6)`、`ok=false`、`result_persisted=false`、`record_error`，并**保留原 risk 字段**。测试走真实 CLI：`weibo.main([... login ...])` 在 mock `record_result` 失败后**退出码 6**，payload 逐字段断言（不只是 `stop`）。
2. **两个账本 + 返回 payload 全部脱敏**：`run_search/detail/comments` 传给旧 state 账本与平台账本的 detail 一律 `scheme://host/path`；payload 的 `url/api` 同规则；**搜索关键词不再进入 payload**（`keyword=None`）。测试用 `秘密关键词ABC` 与 `?token=TOKEN_SECRET123` 跑隔离流程，直接查 `budget.sqlite3` 的 `ledger` 表、平台 `events` 表与返回 JSON，断言关键词/`token`/`q=` **零出现**；知乎未改。
3. **快照必须与固定 `HISTORY_SOURCES` 一致**：`_check_manifest_against_declaration()` 逐 key 比对**分类、必需性**（生产账本另比**规范路径**），拒绝重复 key、分类伪装、缺项、多项 → `history_manifest_invalid`/`history_source_mismatch`；测试清单只允许 `allow_test_manifest=True` 的隔离账本。
4. **两次登录关联强制**：生产账本（非测试）授权新批次时，快照里的 `uncharged_navigation` 必须由 `seed_from` **完整覆盖**，否则 `seed_association_incomplete`；覆盖后 `seed_used=2`、`remaining=1`。不允许 `seed=0` 当新额度。

验证：`{"total_tests":235,"total_skipped":0,"all_green":true}`（weibo 92 / zhihu 96 / budget 47）；真实权威库仍未创建；历史账本 mtime 未变。
