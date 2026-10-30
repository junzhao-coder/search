# 微博单次搜索 只读终审（weibo-final-review）

- 对象：用户授权的一次微博搜索（task-e5235708…），产物在 `docs/validation/v10/weibo-live-prep/`。
- 方法：**只读**。平台库与 state 库都用 `sqlite3.connect(uri + "?mode=ro&immutable=1")` 打开；未联网、未启浏览器、未读 profile/cookie/任何凭据、未写任何账本或业务库。
- 时间口径：全部 UTC。平台库 mtime `2026-10-29T14:46:06Z`，无 `-wal`；state 库同刻同大小（24576B）。

## 1. 预算与批次（平台权威库 `tools/selection/access/runtime/platform_weibo.sqlite3`）

| 项 | 实测值 |
| --- | --- |
| 批次 | `weibo-verify-1`，`authorized_calls=3`，`seed_used=2`，`seed_source=history:uncharged_navigation`，`records_cap=5`，`window_seconds=300.0` |
| 批次来源/备注 | `source="user:2026-10-29 reopen window"`，`note="two logins bound as seed; one search left"` |
| 窗口 | `started_at=2026-10-29T14:45:39Z` → **窗口在 14:50:39Z 关闭**（任务时间 14:51:45Z 已过，`window_open=false`） |
| 事件（仅 2 条） | `id=1 search @14:46:02Z source=weibo.search detail=https://m.weibo.cn/search`；`id=2 search_result @14:46:06Z source=weibo.result outcome=success` |
| 已用/剩余 | seed 2 + search 1 = **used 3 / authorized 3 → remaining 0** |
| 记录预留 | `reservations` 1 行：`count=5 @2026-10-29T14:46:06Z`（全平台共享 cap 5） |
| 锁 | `locks` 表**空**（本次范围内无锁） |
| 历史快照 | `imported_at=2026-10-29T14:45:39Z`，`test_only=false`，9 行：probe1/2/3 `pre_deducted`（各 calls=1）、login-window-1/2 `uncharged_navigation`（calls=0）、offline-login 0、offline-search/detail/comments 各 1 |

**只读证明**：以 `mode=ro&immutable=1` 打开（SQLite 层拒绝写入）；平台库 `-wal` 不存在，读数不含未 checkpoint 内容。

## 2. state-search 库（`docs/validation/v10/weibo-live-prep/state-search/budget.sqlite3`）

| 项 | 实测值 |
| --- | --- |
| budget 行 | `batch_id=weibo-verify-1`，`calls=1`，`records=5`，`polls=0`，`locked=0`，`started_at=14:46:02.494Z` |
| ledger（3 行） | `charge(search) @14:46:02Z` → `records(5) @14:46:06Z` → `search_result(count=5, exit=0) @14:46:06Z` |

与 `search.out.txt` 的 `batch` 字段一致（calls 1 / records 5 / locked false / state_dir 指向该目录）。

## 3. 原始输出与字段核对（`search.out.txt` + `diag1/diagnostics.json`）

| 字段 | 值 | 判读 |
| --- | --- | --- |
| `exit` / `stop` / `count` | `0` / `records` / `5` | 命令成功返回 5 条 |
| `readyState` / `state` | `complete` / `result` | 就绪探针判为"有结果" |
| `anchors_total` | `33`（`status=6`、`other_same_origin=22`、`other_cross_origin=4`、`non_http=1`） | 33 个锚点里 6 个是 `/status/<id>` 形态 |
| `html_bytes` | `83479` | 页面 HTML 有内容 |
| `textLen` | **`0`** | L3 文本探针**没读到任何文本** |
| `contentish` | **`0`** | 没识别到结果容器 |
| `wall` | `null` | **在 textLen=0 下无意义**（见 §5） |
| `final_url` / `final_url_known` | `https://m.weibo.cn/search` / `true` | 落在搜索页；query 被既有脱敏去掉 |
| `keyword` | **`null`** | 关键词被脱敏，**输出无法证明搜了什么词** |
| 记录字段 | 5 条均 `type=status`、`native_id` 为数字、`url=https://m.weibo.cn/status/<id>`、`title="全文"`、`text=null`、`source=weibo:search:status` | 见 §4 |

## 4. 已实现 / 真实链接 / 未验证（严格区分）

**已实现（有账本或输出直接支撑）**
1. 恰好 **1 次** `search` 计费事件（平台 event id=1，14:46:02Z），结果事件 1 条（id=2，success）。
2. **records 预留 5**（平台 reservations 与 state `records=5` 一致）。
3. 批次 **seed=2** 已绑定两条历史登录导航（`seed_source=history:uncharged_navigation`），剩余额度 0。
4. 历史 9 源已导入（含 3 条 `pre_deducted`、4 条 `offline_check`、2 条 `uncharged_navigation`），`test_only=false`。
5. 本次范围内**无锁**（`locks` 空）。

**真实链接（只到"是链接"这一层）**
- 5 条 `url` 的形态是 `https://m.weibo.cn/status/<数字id>`，`native_id` 与 URL 末段一致 → **确实是站内 status 链接**，不是凭空构造。
- 但锚文本全是 **「全文」**：这是"查看全文/展开"类链接的文字，**不是帖子标题**；`title` 字段直接来自 `html:a[text]`，所以 5 条记录的 title 都等于"全文"。

**未验证（不能从现有证据推出）**
1. **关键词相关性**：`keyword=null`、`requested_url` 被脱敏为 `https://m.weibo.cn/search` → 无法证明这 5 条与所搜关键词有关。
2. **正文/发布时间/互动**：`text/published_at/voteup/comments/likes` 全为 null，`missing` 已列 6 项 → 没有正文，谈不上"可读"。
3. **登录态**：本次 `search` 路径不评估 `SIGNED_IN_JS`，输出里没有任何会话证据 → 登录成功**未被证实**。
4. **墙是否存在**：`textLen=0` + `contentish=0` → `wall=null` 只说明"没读到文本可匹配"，**不能**说明没有验证码/访客墙。
5. **结果完整性**：`anchors_recognized=6` 但只取 5 条（`limit=5`）；其余 27 个锚点被拒，形态分布见上表——**不代表**页面上只有 6 条相关内容。

## 5. `--diagnostics-dir` 的"错误参数"说法需要更正（本次独立复核）

- **CLI 有该选项**：`weibo.py:893-900` 给 `search/detail/comments` 都注册了 `--diagnostics-dir`；`main()` 在 `weibo.py:1042-1044` 调用 `_write_diagnostics`。
- **实测两种顺序（离线，只调 `build_parser().parse_args`，不联网不启浏览器；结果落 `evidence.json.argparse_order`）**：
  - 选项放在**子命令之前**（`… --diagnostics-dir <路径> search 关键词`）→ `exit=2`，报 `weibo: error: argument command: invalid choice: 'diag1' (choose from doctor, login, search, detail, comments, export, budget)`（与 live-run 报告引用的报错同型）；
  - 选项放在**子命令之后**（`search 关键词 --diagnostics-dir <路径>`）→ `exit=0`，`diagnostics_dir="diag1"`、`keyword="kw"` 均被正确接收。
- 结论：那次失败**不是"CLI 没有该选项"**，而是**选项位置错**（全局 parser 不认它，于是把路径当成子命令名）。argparse 失败发生在 `main()` 之前，**不可能**触发 charge 或网络 —— 这与平台 `events` 只有 1 条 `search` 相符（但只能证明账本里没有，不能证明"从未发生任何别的尝试"）。
- **另一个证据边界**：`diag1/diagnostics.json` 的**文件名不符合** `_write_diagnostics` 的命名规则（`{command}-{YYYYMMDDTHHMMSSZ}.json`，见 `weibo.py:1049-1058`），且 mtime 14:46:16Z 比 `search_result`（14:46:06Z）晚 10s → 该文件**不是**本次 CLI 直接写出的，而是后续单独步骤（或手工复制）产物；其内容与 `search.out.txt` 里的 `diagnostics` 字段一致，可作**派生证据**，不能当作"CLI 自写"证据。

## 6. 历史账本缺证

1. 9 个旧 per-run 账本（`weibo-probe/*`、`weibo-login/*`、`weibo/checks/*`）**窗口早已过期**（约 46–47h），但平台快照只记录 `calls/records/locked`，**不记录**每源的 `started_at/last_call_at`。
2. 两条 `uncharged_navigation`（两次登录）在快照里**没有时间戳**（`seed_note` 为空），时间只能从旧账本的 ledger 行反推（15:36–15:41Z、15:49–15:54Z）。
3. 平台库**没有**记录"第一次 argparse 失败"的任何痕迹——这正常（失败在 main 之前），但也意味着**无法用账本证明**那次尝试的完整参数。

## 7. 下一步需要保留的状态

1. **平台库** `tools/selection/access/runtime/platform_weibo.sqlite3`（含 history 快照、batch、events、reservations、locks）——**审计基线，不要删除/重建**。
2. **state-search** 库 + `search.out.txt` + `diag1/diagnostics.json`（`weibo-live-prep/`）——本次唯一一次真实搜索的原始证据。
3. 9 个旧账本原样保留（历史 seed 的来源）。
4. 该批次 `remaining=0` 且窗口已于 `14:50:39Z` 关闭 → 再做任何微博真实请求都需要**新的授权**（本轮不申请、不执行）。
5. 若要推进"正文/时间/互动"，需要另开任务：`search` 结果解析要抓帖子卡片而非"全文"链接，且要先解决 `textLen=0`（探针读不到文本）的问题。

## 8. 本报告不主张的事

1. 不主张"墙不存在"（`wall=null` 在 `textLen=0` 下无意义）。
2. 不主张"登录成功"（本次无会话证据）。
3. 不主张"结果与关键词相关"（`keyword` 被脱敏为 null）。
4. 不主张"正文可读"（`text=null`，`missing` 含 6 个字段）。
5. 不主张"CLI 没有 `--diagnostics-dir`"（实测有，失败是选项位置问题）。
6. 不主张"第一次失败已被账本记录"（argparse 失败不入账，只能证明账本里没有额外 charge）。
