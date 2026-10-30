# weibo-rpa-1 预检：批次额度与「登录 + 1 次搜索」的冲突（未执行真实导航）

- 时间：2026-10-30T05:2xZ（本机 UTC；下同）
- 状态：**未创建真实批次、未打开浏览器、未执行任何真实导航**。本文件只记录只读核对与**账本副本**上的算术验证。
- 范围：`docs/validation/v10/weibo-rpa-live`。

## 1. 验收要求（原文要点）

1. 在固定权威账本创建 `weibo-rpa-1`：`authorized_calls=3`、`records_cap=5`、`window_seconds=300`；
2. `login`：先 precheck 并**预扣 `active_nav`** 再启动；
3. 登录成功后**在同一批次**跑 1 次 `live-search`：预扣 `search` → 单次导航 → 风险判定 → 提取 → 预留 ≤5 条 → 登记。

## 2. 代码事实

| 事实 | 位置 |
| --- | --- |
| 计费种类含 `active_nav` | `platform_budget.CALL_KINDS = ("active_nav","search","detail","comments")` |
| 已用量 = 窗口内事件数 + `seed_used` | `platform_budget.py:362-371` |
| 生产批次**必须**绑定两条历史登录导航（否则 `seed_association_incomplete`） | `platform_budget.py:241-250` + `HISTORY_SOURCES` 的 `login-window-1/2` |
| `login` 在启动浏览器**之前** `charge_nav(..., "login")` | `tools/selection/rpa/cli.py::cmd_login` |

## 3. 副本上的算术验证（真实账本**只读**，未写入）

用真实账本的临时副本执行（`platform_budget.DEFAULT_PATH` 只在子进程内指向副本）：

```
after_authorize: {"authorized_calls": 3, "seed_used": 2, "used": 2, "remaining": 1, "window_open": true}
after_login_charge: {"used": 3, "remaining": 0, "window_open": true}
search_precheck: blocked: calls_exhausted 3/3
```

## 4. 结论

按验收要求创建 `authorized_calls=3` 的批次时：

- 2 次额度被**历史登录导航**以 `seed_used=2` 占用（代码强制，不可跳过）；
- 剩下**只有 1 次**；
- `login` 会先预扣这 1 次 → **`live-search` 必然 `blocked:calls_exhausted`**。

也就是说：**「登录」与「1 次真实搜索」在 `authorized_calls=3` 下互斥**，验收 2 与 3 无法同时满足。这不是代码 bug，而是"新批次仍要继承两次历史登录"的既有规则与"3 次额度"叠加的结果。

## 5. 可选方案（需要策划者/用户裁定）

| 方案 | 做法 | 代价/风险 |
| --- | --- | --- |
| **A（推荐）** | 同 id `weibo-rpa-1`，`authorized_calls=4`：2 seed + login + 1 search | 比用户口头"最多 3 次"多 1 次；需用户确认"4 次"这个数 |
| B | 保持 3 次：只做 `login`（1 次），搜索留待下一批 | 本轮拿不到正文，验收 3 不成立 |
| C | 保持 3 次：跳过 login，直接 1 次 search | 登录态未知，可能撞登录墙；验收 2 不成立 |
| D | 3 次 + 新 batch id 再做搜索 | 等于绕开"3 次"的授权边界，**不做** |

## 6. 本轮未做的事

1. 未创建 `weibo-rpa-1`（避免把 300s 窗口和 batch 参数锁死，导致方案 A 需要换 id）；
2. 未打开任何浏览器窗口（避免用户在电脑前空等，也避免预扣那 1 次）；
3. 未写真实账本：`real_ledger_unchanged` 仅 stat 核对（mtime `2026-10-29 22:46:06`、size 45056 未变）。

## 7. 方案 A 的执行顺序（裁定后即可跑）

```powershell
# 0) 授权（一次性；写入真实账本）
& $py -X utf8 -c "import sys; sys.path.insert(0,r'D:\桌面\two'); from tools.selection.access import platform_budget as pb; l=pb.open_default(); print(l.authorize_batch('weibo-rpa-1', authorized_calls=4, window_seconds=300.0, records_cap=5, source='user:consent:new-batch', note='2 historical logins seeded; login + 1 search', seed_from=('login-window-1','login-window-2'))); print(l.summary('weibo-rpa-1')); l.close()"

# 1) 登录（可见窗口；用户本人扫码；桌面证据；150s 超时）
& $py -X utf8 -m tools.selection.rpa login --batch-id weibo-rpa-1 --timeout 150

# 2) 登录成功后立即 1 次搜索（同一批次）
& $py -X utf8 -m tools.selection.rpa live-search --batch-id weibo-rpa-1 --keyword "学习计划模板" --allow-live --limit 5
```

注意：`window_seconds=300` 从授权时刻起算；登录窗口最长 150s，登录后必须**立刻**跑搜索，否则窗口会关（`batch_window_closed`）。
