# 采集账号台账（按 ACCOUNT-SAFETY 模板）

> 台账只记 handle/profile/状态/布尔；不记录任何 cookie 值。
> 模板来源：`docs/validation/v9/account-safety/ACCOUNT-SAFETY.md` §3.4。
> 注：本任务写入范围是 `docs/validation/v9/xhs-readiness/`；`account-safety/ACCOUNT-SAFETY.md` 主台账由后续任务同步此行。

| 平台 | profile 路径（计划） | handle | 上次验证 UTC | 状态 | 需重登判断 |
| --- | --- | --- | --- | --- | --- |
| xiaohongshu | `C:\Users\19183\.dsh\tools\xhs-collect\profile` | 待补（未解析页面 handle，不推断） | 检测可靠性已修（CDP 轮询+关窗复查）；可见窗口 2026-10-26T02:39:27Z online=valid（25 条 explore 链接，无登录墙）；headless verify 02:27:26Z login_required 属无头误判，勿据此重登；note-click 03:07:54Z 成功 1 条；**batch 03:21:16Z 成功 5 条**（batch=first-batch-2026-10-26T03:21:17Z；signals=6 含前序1、review=6、categories=0、cards=0；页面加载10）；likes/publish_time 字段路径已尝试但批内值不可信/不可得 | 可用（可见窗口）；本地 ready；批量 5 条已入隔离库；品类 0、卡片 0 | 否（可见窗口实测可用）；不要因 headless verify 重登 |
| x | `C:\Users\19183\.dsh\tools\x-collect\profile` | @Johnsmathjyjp（旧记录 @xluchuan，归属待用户确认） | 2026-10-25T12:39:50Z | doctor exit0；search 5 条 exit0（V9-6） | 否（当前可读） |
| bilibili | 公开 API，无 profile | — | 2026-10-25（多轮实测） | 可读（V9-1b/3/7a） | 否 |
| v2ex / github | 公开 API，无 profile | — | 2026-10-25T13:55Z | 可读（V9-8a，3 请求） | 否 |
