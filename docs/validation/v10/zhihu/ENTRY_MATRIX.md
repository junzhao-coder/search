# 知乎六入口矩阵（v10 收口，2026-10-30 补写）

- 目的：补齐 CONSISTENCY.md 第 11 条缺口——知乎此前**没有**六入口状态表。
- 口径：只写**已发生的事实**；「无真实样本」就明写，不拿离线单测冒充线上能力。
- 本文件补写时**零网络**（未打开知乎、未登录、未发请求）。

## 1. 六入口

| 入口 | 代码 | 状态 | 证据来源 |
| --- | --- | --- | --- |
| `doctor` | `access/zhihu.py::doctor()` | **本地只读可用**：只读 profile 目录 + cookie **名称**布尔，不启浏览器、不联网 | 本批本地实测：`profile_exists=true`、`cookie_db_exists=true`、`cookie_count=21`、`network="none"`（见 `v11/ACCOUNT_LEDGER.md`）；`OFFLINE_CHECKS_RUN.md` |
| `login` | `access/zhihu.py::login()` | **未完成**：可见窗口代码已就位，但**用户本人扫码登录未发生**；历次尝试被 async/sync 缺陷与风险轮询问题阻塞 | `LOGIN_ATTEMPT_1.md`、`LOGIN_ATTEMPT_2.md`、`LOGIN_ASYNC_FIX.md`、`LOGIN_RISK_POLL_FIX.md` |
| `search` | `run_search()`（transport 注入） | **匿名 public-http：403 blocked**；**已登录浏览器路径：未完成**（依赖 login）。最近一次真实运行：0 记录、原因未判定 | `LIVE_SEARCH_1.md`～`LIVE_SEARCH_4.md`（4 次真实运行） |
| `detail` | `run_detail()` + 结构化解析 | **离线解析可用**（答案/文章/zvideo 结构 → `records` 白名单记录）；**无真实样本验证** | `REPORT.md`、`OFFLINE_CHECKS_RUN.md`；真实页面未取过 |
| `comments` | `run_comments()` | **未实现 → 显式 unsupported**：端点已调研（`GET /api/v4/comment_v5/{content_type}s/{content_id}/root_comment`），但未接实现、不返回空成功 | `RESEARCH.md`（端点与字段表）；实现状态以代码为准 |
| `export` | `export()` | **离线可用**：`records.EXPORT_FIELDS` 白名单 + `not_applicable` 语义，未知键丢弃并计数 | 单测 `test_access_zhihu`（真实 jsonl 往返） |

## 2. 一句话状态

知乎是**四个平台里唯一没拿到真实登录态**的：doctor 与 export 离线可用，search 匿名被 403、登录需用户本人扫码，comments 仍是显式 unsupported。**不得**在平台矩阵里把知乎写成「搜索可用」。

## 3. 已知限制（与代码一致）

1. 真实可读性**未独立核验**——没有一次「登录后读到正文」的成功记录；
2. `login` 需要用户本人扫码，agent 不代填凭据；
3. `comments` 只有端点调研，没有实现；
4. 记录数按 v11 软目标口径（`records_target/records_used/over_cap/over_by`），**不再截断**。
