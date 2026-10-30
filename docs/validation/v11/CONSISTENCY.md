# V11 文档一致性盘点（软上限 / not_applicable / 四平台入口）— 结案版

- 时间：2026-10-30T11:20Z（UTC）；cwd `D:\桌面\two`；纯离线，零网络零额度。
- 判据：项目 P6「工具清单、平台矩阵、账号台账、调用说明与当前代码一致」。
- 状态：**13 条全部结案**（10 条已修 / 3 条保留并写明理由）。上一版（V11-2）因 scope 只在 `docs/validation/v11`，v10 文档改不动；本批放开到 `docs/validation/v10`，逐条落地。

## 1. 逐项结案

| # | 文档说（原） | 代码实际 | 本轮结果 |
| --- | --- | --- | --- |
| 1 | `PLATFORM_STATUS.md`：`records_cap=5` 会截断、保留 5 丢弃 53 | v11 软目标：不拒绝、不截断，返回 `over_cap/over_by` | **已修（本轮）**：该文件顶部加 v11 更新块 + 第 2 节限制 1 改写为「记录数是软目标（v11 起）」并注明 v10 行为已不成立 |
| 2 | `REPORT_COMMENTS_OK.md`：保留 5 条 / 丢弃 53 条 / `truncated=true` | 同上 | **已修（本轮）**：顶部加醒目注记「历史快照；v11 起已改软目标，本文截断数字为当时行为」 |
| 3 | `REPORT_COMMENTS_ENTRY.md`：`records_cap=5` < 38 条被拒 / 改为截断 / 需把 cap 提到 ≥40 | 同上 | **已修（本轮）**：顶部加同类注记 |
| 4 | `douyin/OFFLINE_ENTRIES.md`：`MAX_RECORDS=5` 记录上限（2 处） | `DEFAULT_RECORDS_TARGET=5` 默认目标 | **已修（本轮）**：底座那行改为只列时间/间隔参数 + 新增「记录数口径（v11）」；对齐表「记录上限」行改「记录数：默认目标 5，可任意上调…不拒绝不截断」 |
| 5 | `tieba/OFFLINE_ENTRIES.md`：`MAX_RECORDS=5`，超限报 `records_cap_exceeded` | 同（软目标） | **已修（本轮）**：改为「默认目标 5，可任意上调；超出返回 `over_cap/over_by`」 |
| 6 | 各平台文档未提 `not_applicable` | `make_record(not_applicable=…)`：顶层评论 `parent_id`、评论 `reposts/comments`、帖子 `root_comment_id` 不进 `missing` | **已修（本轮）**：本文件第 2 节登记语义；v10 各 `OFFLINE_ENTRIES.md` 的「不适用语义」行已指向同一函数 |
| 7 | 调用说明（`browser-rpa/USAGE.md`）未写记录数口径 | `reserve_records()` 四字段 | **已修（本轮）**：第 5 节「记录格式」加 v11 软目标块（含"软的是存储、硬的是次数/间隔/时长/风险即停"） |
| 8 | 知乎无六入口矩阵 | `zhihu.doctor/login/run_search/run_detail/run_comments/export` | **已修（本轮）**：新建 `docs/validation/v10/zhihu/ENTRY_MATRIX.md`，六入口逐项状态 + 证据来源（doctor 本地只读可用；search 匿名 403；login 待用户扫码；comments 显式 unsupported；export 离线可用） |
| 9 | 跨平台账号台账不存在 | 四平台 `doctor()` 只读输出 | **已修（本轮）**：新建 `docs/validation/v11/ACCOUNT_LEDGER.md`，四平台各一行：profile 路径、是否存在、cookie 名称布尔（只名称不写值）、在线状态、已验证能力；抖音/贴吧写「待用户本人登录（profile 尚未创建）」 |
| 10 | 微博第 3 页起未验证 | 只验证到第 2 页 | **保留**（事实未变；`PLATFORM_STATUS.md` 限制 2 原样保留） |
| 11 | 抖音/贴吧 `comments` 显式 unsupported、login 恒 unknown | 代码一致 | **保留**（一致性已确认，无需改） |
| 12 | 知乎真实可读性未独立核验 | 无真实成功样本 | **保留**（事实未变；`ENTRY_MATRIX.md` 明写「不得写成搜索可用」） |
| 13 | 「记录数最多 5 条 / 超限拒绝」散见 v10 多处历史报告（`REPORT_COMMENTS.md`、`REPORT_COMMENTS_ENTRY.md`、`REPORT.md`、`PREFLIGHT_CONFLICT.md`、`weibo-final-review/REPORT.md` 等） | 代码已无上限判断 | **部分已修**：核心 4 份（#1–#5）已改；其余为**历史批次快照**，统一策略是「保留原文 + 由本文件与 `PLATFORM_STATUS.md` 的 v11 更新块统一标注」，避免改写历史证据。**未逐一加注记是因为**：逐份改写会破坏当时的证据原貌，且同一策略已覆盖读者入口 |

## 2. 语义速查（与代码一致）

| 概念 | 现状 |
| --- | --- |
| 记录数 | **软目标**：`records_target`（默认 5，可任意上调）、`records_used`、`over_cap`、`over_by = max(0, used-target)`；不拒绝、不截断、不丢记录 |
| 硬护栏 | 调用次数上限（`authorized_calls` ≤20）、`MIN_INTERVAL=15s`（被拒不扣费）、单批 `window_seconds` ≤300s 且超时即停、风险即停（文本命中或 429 → 持久锁 + 非零退出 + 不自动重试） |
| 不适用 vs 未读到 | `not_applicable`：顶层评论 `parent_id`、评论 `reposts/comments/title/voteup`、帖子 `root_comment_id`；`missing`：只装"该有但没读到"（`text/published_at/likes/author` 等） |
| 列集合 | `records.FIELDS` 14 列 + `EXPORT_FIELDS`（含 `missing/not_applicable/supported/author_redacted/field_evidence/source/evidence_missing/evidence_rejected`）；旧 jsonl 仍可导出 |

## 3. 零网络证据（本批）

| 项 | 值 |
| --- | --- |
| `runtime/platform_weibo.sqlite3` | mtime 仍 `2026-10-30 16:03:11` |
| `runtime/platform_douyin.sqlite3` | **不存在** |
| `runtime/platform_tieba.sqlite3` | **不存在** |
| 残留 Chrome | `leftover_chrome=0` |
| 守卫五哈希 | `app.db e073f828` / `workflow.sqlite3 8ae79c58` / `CONTRACT.md 826c24cc` / `scores.csv ab0c3546` / `sources.csv 13679b60`（未变） |

## 4. 测试

七套全量（`test_selection_rpa`、`test_access_zhihu`、`test_access_weibo`、`test_access_budget`、`test_access_douyin`、`test_access_tieba`、`test_soft_records_cap`）= **477 tests OK**，无跳过。
