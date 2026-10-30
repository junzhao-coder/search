# V10-6 微博登录（可见窗口 300s）：**页面证据未命中 → status=timeout，未跑搜索**

> 任务 `task-42ce1746ada1541b787b48eda12fd9ce`（rev2，计划 v10，小目标 V10-6）。
> 执行时间：2026-10-27 23:36:05–23:41:18 UTC+8（**15:36:05Z–15:41:18Z**）。
> **登录窗口只开一次**；未代填、未索取、未读 cookie 值；**未跑搜索**（因 status≠ok）；超时后未重开、未重试。

## 1. 实际命令（与验收原文有两处偏差，必须说明）

验收原文：`… weibo --profile D:\…\weibo-login\profile login --timeout 300 --visible`

| 问题 | 证据 | 我的处理 |
| --- | --- | --- |
| 缺 **`--state-dir`**（CLI 必填） | 首次照抄原文 → `weibo: error: the following arguments are required: --state-dir`，`login.err.txt`（299 B）、**那次没有开窗** | 补 `--state-dir D:\…\weibo-login\state-login` |
| **`--visible` 未定义给 login** | `weibo.py:600-601`：login 只有 `--timeout` / `--headless`（store_true）；`--visible` 仅加在 search/detail/comments | 省略 `--visible`（login 默认 `headless=False`，**本来就是可见窗口**；派发上下文也写"可加可不加"） |

实际 argv：
```
C:\Users\19183\.dsh\tools\x-collect\venv\Scripts\python.exe -X utf8 -m tools.selection.access.weibo
  --state-dir D:\桌面\two\docs\validation\v10\weibo-login\state-login
  --profile D:\桌面\two\docs\validation\v10\weibo-login\profile
  login --timeout 300
```
cwd / PYTHONPATH = `D:\桌面\two`；started_utc **15:36:05Z**。

## 2. 窗口证据（窗口一开已立即 wake 告知）

```json
{"sampled_utc":"2026-10-27T15:36:07.xxxZ","python_pid":93032,"chrome_pid":129988,
 "title":"新标签页 - Google Chrome","handle":3804216,"visible":true,"responding":true,
 "rect":"10,10,1060,1009"}
```

- 采样过滤：命令行含 `weibo-login`（用户自己的 Chrome 不会误记）。
- **用户随后确认「已登录」**；窗口标题从「新标签页」变为 **「微博 – 随时随地发现新鲜事 - Google Chrome」**（15:38:12Z 观测），说明 SSO 已跳回 `weibo.com`。

## 3. 登录五态结果（如实）

```json
{"command": "login", "elapsed_s": 302.026, "exit": 11, "final_url": "https://weibo.com/",
 "polls": 100, "risk_reason": null, "signed_in": false, "status": "timeout",
 "stop_reason": "timeout"}
```

| 字段 | 值 |
| --- | --- |
| **status** | **`timeout`**（五态之一，非 ok） |
| **signed_in** | **false**（`SIGNED_IN_JS` 页面标记始终未命中） |
| polls | **100**（300s / 3s） |
| elapsed_s | **302.026** |
| final_url（脱敏） | **`https://weibo.com/`** |
| stop_reason | `timeout` |
| risk_reason | `null`（**无墙**，未被判风险） |
| **exit** | **11**（`EXIT_LOGIN_TIMEOUT`） |
| stderr | 仅 asyncio 收尾告警（`Event loop is closed` / `I/O operation on closed pipe`），非产品异常 |

## 4. doctor（登录后，只读，只记布尔）

```json
{"command":"doctor","cookie_count":9,"cookie_db_exists":true,
 "cookie_names":{"SCL":false,"SSOLoginState":true,"SUB":true,"SUBP":true,
                 "SUHB":false,"XSRF-TOKEN":true,"_T_WM":false},
 "exit":0,"network":"none","online":"unverified",
 "profile":"D:\\桌面\\two\\docs\\validation\\v10\\weibo-login\\profile",
 "profile_exists":true,"site":"weibo"}
```

- profile **已落盘**（44 个条目）；`SUB/SUBP/SSOLoginState/XSRF-TOKEN = true` → **会话 cookie 确实写入**。
- 但按验收第 2 条：**cookie 名称存在不等于在线，只有 `SIGNED_IN_JS` 页面证据才能判 ok** → 因此 status 仍是 `timeout`。
- 日志中检索 `SUB=|SUBP=|SCF=|XSRF-TOKEN=` 命中 **0** 次（未落任何 cookie 值）。
- 无残留 Chrome（本 profile 匹配数 0）。

## 5. 为什么页面证据没命中（根因假设，未改代码）

`SIGNED_IN_JS` 现在只看 `document.body.innerText` 是否含 `退出|我的主页|发微博|账号设置`。两个可能：

1. **标记与真实文本不匹配**：`weibo.com` 桌面首页登录后文本可能是「首页/热门/视频/关注/消息/我的」等，**不含**这四个词中的任何一个 → 永远 false。
2. **`main_tab` 指向的不是跳转后的那个 tab**：`browser.get(LOGIN_URL)` 之后 SSO 若新开/切换 tab，`main_tab` 可能仍停在旧页面（innerText 为空），于是 100 次轮询都读不到登录态。

两者都不影响"用户确实登录了"（窗口标题变化 + 用户确认 + 会话 cookie 已写入），但都让**页面证据判定**失效。

## 6. 未跑搜索（合规说明）

验收第 4 条：**"登录成功后（status=ok）才进行"**。本次 status=`timeout`，因此**我没有执行那 1 次搜索**，`state-login1` / `diag1` 均未创建，本批 3 次额度**一次未用**。

## 7. 下一步选项（需你/用户决定）

| 选项 | 内容 | 代价/风险 |
| --- | --- | --- |
| **A（推荐）修标记 + 复用已登录 profile 重开一次登录窗口** | 把 `SIGNED_IN_JS` 改成能匹配真实登录态（例如检测 `a[href*="/u/"]` + 页面含「我的」/「消息」/「发微博」任一，或直接判 `location.host` 为 weibo.com 且非 passport），并用**现有已登录 profile** 再跑一次 login → 大概率**立即判 ok**（几秒） | 需要改代码（tiny）+ **再开一次窗口**（与"只开一次"冲突，需授权）；**零搜索额度**消耗 |
| **B 授权放行这一次搜索** | 承认 `status=timeout` 是标记缺陷，凭"窗口标题已到微博首页 + 用户确认 + SUB/SSOLoginState 存在"放行 1 次搜索 | **偏离**验收第 2 条（cookie 不得冒充在线）；消耗 1 次额度，结果仍可能是空壳 |
| **C 收口** | 把 V10-6 判为"登录可达但判定器失效"，微博搜索路线按已验收的 V10-5 结论收口 | 不消耗额度；但用户的登录动作没有换来搜索结论 |

**我的建议：A。** 理由：不烧搜索额度、能把"判定器"这个真缺陷修掉，而且现有 profile 已经登录，重开窗口预期几秒内即 ok，用户无需再扫码。

## 8. 声明

- 登录窗口**只开一次**，300s 结束；**未自动重开、未重试**。
- **未代填凭据、未索取凭据、未读取/输出任何 cookie 值**（日志扫描 0 命中）。
- **未执行搜索**（status≠ok），本批额度 0 消耗。
- 未装依赖、未访问微博以外域、未写业务库/CSV/CONTRACT；profile 与登录态目录在 `docs/` 下，**未入库**。
