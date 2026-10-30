# 微博实机执行报告：1 次登录态搜索（2026-10-29）

> 任务 `task-e523570821e7b18e408c87a1a63f52f1`（rev2，计划 v10）。
> 用户明确授权：重开一次最长 300 秒窗口，执行此前同意的那一次搜索。
> **结论先说**：搜索**已执行并成功**（exit 0，5 条 status 链接，state=result）；
> **登录态未被证实**，因此**不能**标"登录后可读"，只能记"链接级内容可读、登录态未知"。

---

## 1. 执行前预检（同一执行内，只读）

| 项 | 结果 |
| --- | --- |
| 9 个历史来源 | 全部存在、**无锁**、**无 `-wal`/`-shm`** |
| probe1/2/3 | calls=1 each，locked=false |
| login-window-1/2 | calls=0，locked=false |
| offline-login/search/detail/comments | calls=0/1/1/1，locked=false |
| 固定权威账本 | 执行前**不存在**（无冲突、未重置） |

## 2. 账本准备（真实写入固定权威库）

```json
{"import": {"status": "recorded", "sources": 9, "test_only": false,
            "sha256": "6656d1f1…597236"},
 "batch": {"batch_id": "weibo-verify-1", "authorized_calls": 3,
           "seed_used": 2, "records_cap": 5, "window_seconds": 300.0},
 "summary": {"used": 2, "remaining": 1, "window_open": true},
 "history": {"pre_deducted_calls": 3, "offline_checks": 4, "uncharged_navigations": 2}}
```

- 两次历史登录以 `seed_from=("login-window-1","login-window-2")` **强制绑定**（生产账本不接受 seed=0）。
- 授权来源：`user:2026-10-29 reopen window`，备注 `two logins bound as seed; one search left`。

## 3. 唯一一次搜索

| 项 | 值 |
| --- | --- |
| argv（脱敏） | `C:\Users\19183\.dsh\tools\x-collect\venv\Scripts\python.exe -X utf8 -m tools.selection.access.weibo --state-dir …\weibo-live-prep\state-search --batch-id weibo-verify-1 --mode authenticated-browser --profile …\weibo-login\profile search 学习计划模板 --limit 5 --visible --timeout 60` |
| cwd | `D:\桌面\two` |
| started / finished UTC | **14:46:02Z** / **14:46:06Z**（elapsed 3.824 s） |
| exit / stop | **0** / `records` |
| profile 复用 | 是（既有微博专用 profile，未新建、未复制） |
| 可见窗口 | Chrome PID **17968**，标题「新标签页 - Google Chrome」（无需用户操作） |
| 导航次数 | **1**（未登录、未 session-check、未重试、未换词） |

## 4. 结果（payload 实测）

```json
{"count": 5, "exit": 0, "stop": "records",
 "state": "result", "final_url": "https://m.weibo.cn/search",
 "html_bytes": 83479, "anchors_total": 33, "anchors_recognized": 6,
 "wall": null, "textLen": 0}
```

- 5 条记录均为 `weibo:search:status`，形如 `https://m.weibo.cn/status/<id>`；`title` 全为「全文」（链接文本），`text/published_at/voteup/comments/likes` 为 null（`missing` 已标注）。
- `textLen=0`、`contentish=0`：**没有正文文本**，只有链接级内容。
- `wall=null` 只说明**本次未命中已知墙词**，不据此排除墙（按验收第 4 条）。

## 5. 账本事后状态

```json
{"platform": {"used": 3, "remaining": 0, "records_reserved": 5,
              "locked": false, "lock_reason": null},
 "events": [{"kind": "search", "detail": "https://m.weibo.cn/search"},
            {"kind": "search_result", "detail": "success"}],
 "state_ledger": [charge, records(5), search_result(5, exit 0)]}
```

- 1 次预扣已持久化并**不退款**；记录配额 5 条已原子预留；**无风险锁**。
- 该批次 3 次额度**用尽**（seed 2 + 本次 1），剩余 **0**。

## 6. 登录态判定（关键，不夸大）

- **未执行 session-check**（验收只允许 1 次导航，且不额外检查）。
- 访问的是公开移动搜索页，`textLen=0`，**没有账号专属控件证据**。
- 因此：**登录态未确认（unknown）**；本次只能证明"搜索页返回了 5 条 status 链接"，**不能**称"登录后可读"。

## 7. 派发文本与实现的偏差（留档）

- 验收 argv 含 `--diagnostics-dir`，但微博 CLI **没有该选项**（`weibo.py` 的 search 子命令只接受 `--limit/--visible/--timeout`）。
- 首次照抄该 argv 时 argparse 直接失败：`invalid choice: '…\diag1'`，**在任何网络/预扣之前**退出，账本 `used` 仍为 2、`events=0`（已核验）。
- 处理：去掉该参数执行；诊断改为从 payload 的 `diagnostics` 落盘到 `diag1/diagnostics.json`。

## 8. 产物

- `search.out.txt`（完整 payload）、`search.err.txt`（空）
- `diag1/diagnostics.json`（脱敏诊断骨架）
- `prep.json`（导入/授权/剩余额度）
- 未触碰业务库/CSV/CONTRACT/小红书封存；未安装依赖；未读取 cookie/token 值。

## 9. 限制

1. 只有 1 次真实请求的样本，且 `textLen=0`，无法判断登录态下的正文可读性。
2. 该批次额度已用尽（remaining=0）；再做真实请求需用户**新的明确授权**，本次不自动追加。
3. 选择器仍标 assumed；`wall=null` 不构成"无墙"证明。
4. 真实页面 33 个锚点仅 6 个被识别，27 个被拒——拒绝原因未逐条审计。
