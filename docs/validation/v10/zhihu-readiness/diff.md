# B10-fresh 改动摘要（tiered probe + timeout 60s）

> 范围：`tools/selection/access/`、`tests/test_access_zhihu.py`、本目录。

## `tools/selection/access/transport.py`

- **删除** `READY_JS`（一次重求值：整页 `innerText` + 最多 400 锚点 + 多组 `querySelectorAll`）。
- **新增三级探针**：
  - `PROBE_LIGHT_JS`（L1）：`readyState` + `a[href]` 数量 + **前 20 个** href 的形态计数；无 innerText、无 href 列表。
  - `PROBE_MEDIUM_JS`（L2）：结果/列表容器类名计数。
  - `PROBE_TEXT_JS`（L3）：`innerText` 截断 4000 字符的风险/空结果文案（只在 L1/L2 成功但未就绪时运行）。
  - `PROBE_LEVEL_TIMEOUTS = (2.0, 2.0, 4.0)`。
- **新增 `_parse_probe(raw, level)` / `_probe(tab, level, deadline)`**：每级一次计时 evaluate，**独立短超时**，预算 = `min(该级上限, 剩余 × 0.5)`（留一半给内容读取）；超时返回 `None`（该级 unknown），不抛整体失败。
- **`_wait_ready` 重写**：L1 → L2 → L3 顺序推进；L1 认出内容链接且 `readyState=complete` → `result`；L2 有容器 → `ready`；L3 命中风险文案 → `risk`、命中空结果文案 → `empty`；任一级超时 → `state=unknown` + `level_timeout=true` + `level=N`；总 deadline 不因分级重置。
- **默认 `timeout` 20.0 → 60.0**。
- **诊断新增** `probe_level`、`probe_elapsed_ms`（每级毫秒）；`probe.timings_ms` 同时保留。
- `_navigate` / 总 deadline / 最终 URL unknown / 风险锁 等 B10 既有行为不变。

## `tools/selection/access/zhihu.py`

- `search`/`detail`/`comments` 新增 `--timeout`（默认 60）与既有 `--diagnostics-dir`。
- `_make_transport` 在 `authenticated-browser` 模式下把 `args.timeout` 传给传输层（默认 60）。

## `tools/selection/access/diagnostics.py`

- `ALLOWED_KEYS` 增加 `probe_level`、`probe_elapsed_ms`（仍只允许白名单键）。

## `tests/test_access_zhihu.py`

- `FakeTab` 改为**按 `level:1/2/3` 脚本分别应答**，新增 `hang_levels` 与 `levels_seen`；`_page_state` 展开为三级 payload。
- 新增：`test_light_probe_success_then_heavier_levels_run`、`test_light_probe_timeout_degrades_to_unknown`、`test_heavier_probe_timeout_degrades_to_unknown`、`test_probe_timings_and_level_are_in_diagnostics`、`test_default_timeout_is_60_seconds`、`test_stuck_light_probe_stops_without_resetting_deadline`、`test_cli_timeout_and_diagnostics_dir_reach_the_transport`。
- 原 15 例就绪/脱敏用例保留并按三级探针适配；`import re` 补齐。

## `docs/validation/v10/zhihu-readiness/`

- `REPORT.md` 更新（分级方案、60s、判读顺序、未验证项）、`diff.md`（本文件）、`execution_manifest.json`、`logs/`、`diag/`。
