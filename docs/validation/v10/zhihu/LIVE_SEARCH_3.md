# V10-3 修复后首次真跑：被预算时间窗口拒绝（未发出请求）

> 任务 `task-fd0770a46d30d0cc56dc22cbb90f8aaa`（rev2，计划 v10）。
> 执行时间 2026-10-27 17:44:13–17:44:14 UTC+8（09:44:13–09:44:14Z）。
> **只执行 1 次真实命令**；未重试、未换词、未换 mode、未改代码/测试/期望值、未装依赖、未代填、未读 cookie 值。

## 1. 实际命令与结果

| 项 | 值 |
| --- | --- |
| argv | `C:\Users\19183\.dsh\tools\x-collect\venv\Scripts\python.exe -m tools.selection.access.zhihu --state-dir docs\validation\v10\zhihu\runtime_live2 --batch-id zhihu-live-2 --mode authenticated-browser --profile C:\Users\19183\.dsh\tools\zhihu-collect\profile search 学习计划模板 --limit 5` |
| cwd / PYTHONPATH | `D:\桌面\two` / `D:\桌面\two` |
| started_utc / finished_utc | **2026-10-27T09:44:13Z** / **09:44:14Z**（1 秒内返回） |
| **exit** | **6** |
| **stop** | **`budget:time_exhausted`** |
| records | **0** |
| parsed_structure | 无（未发出请求） |
| risk_reason | 无 |
| final_url | 无 |
| 外部 180s 超时保护 | **未触发**（命令 1 秒返回） |
| stderr | 空（0 字节） |

stdout 原文（`docs/validation/v10/zhihu/live_search_3.out.txt`）：
```json
{"batch":{"batch_id":"zhihu-live-2","calls":1,"calls_max":3,"elapsed_s":3040.019,
 "last_call_at":1793091214.5465372,"lock_reason":null,"lock_source":null,"locked":false,
 "polls":0,"polls_max":120,"records":0,"records_max":5,"seconds_max":300.0,
 "state_dir":"...\\runtime_live2"},
 "command":"search","count":0,"exit":6,"keyword":"学习计划模板","ok":false,
 "records":[],"stop":"budget:time_exhausted",
 "url":"https://www.zhihu.com/search?q=%E5%AD%A6%E4%B9%A0%E8%AE%A1%E5%88%92%E6%A8%A1%E6%9D%BF"}
```

## 2. 预算（未消耗新调用）

只读查询 `runtime_live2/budget.sqlite3`（`_inspect_budget.py`），执行前后一致：

```
budget {"batch_id":"zhihu-live-2","calls":1,"records":0,"locked":0,
        "lock_reason":null,"lock_source":null,"polls":0}
ledger_count 1
ledger charge {"kind":"search","detail":"...q=学习计划模板...","batch_id":"zhihu-live-2"}
```

- **calls 仍为 1**（本次未扣第 2 次）、`locked=0`、无 lock 记录、ledger 仍只有第 1 次那条 `charge`。
- `elapsed_s=3040.019` > `seconds_max=300` → 批次 300 秒窗口已过期，`open_budget`/`charge` 前置检查直接拒绝，**请求未发出**。

## 3. 原因分析

- `runtime_live2` 批次创建于第 1 次真实调用（08:53:34Z），随后那次挂死 44 分钟；本次执行时距批次开始已 **3040 秒**，超过 `seconds_max=300`。
- 因此 `budget:time_exhausted` 是**预算窗口保护正常工作**，不是新缺陷、不是风控、也不是跨 loop/超时修复失败。
- 修复（单 loop + `wait_for`）在本轮**未获得验证机会**——因为请求根本没走到 transport。

## 4. 结论

- 本次 authenticated-browser 搜索**未发出**：`stop=budget:time_exhausted`、`records=0`、exit=6。
- **“登录后知乎搜索是否可读”仍未回答**。
- 预算状态：`calls=1/3`、未锁、**剩余 2 次**（窗口已过期，需新建批次/state-dir 才能继续）。
- 按约束未重试、未换词、未换 mode、未改代码。

## 5. 建议（需策划者决定）

1. 用**新 state-dir**（如 `runtime_live3`）新建批次，在 300 秒窗口内立即执行 1 次搜索；这样修复后的 transport 才能真正被验证。
2. 或把 `seconds_max` 调大（属预算语义变更，需单独授权）。
3. 本次未消耗新调用，因此“第 2 次”额度仍在（新批次会重置为 3 次）。

## 6. 声明

- **只执行了 1 次真实命令**；未重试、未换关键词、未换 mode、未改代码/测试/期望值。
- 未装依赖、未代填凭据、未读取/输出 cookie 值、未访问知乎以外域、未写业务库/CSV/CONTRACT。
- 180 秒外部超时保护已就位但未触发；无残留 zhihu-profile Chrome/python 进程。
