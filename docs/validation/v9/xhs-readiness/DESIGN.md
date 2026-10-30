# 小红书登录前就绪（V9-8c）：设计说明

> 任务 `task-78569f34c8cd2fac3df9ef2ed121f2eb`（rev2，计划 v9）。**零真实请求**；fixture 全部构造。
> **结构假设声明**：fixtures 的小红书页面结构是构造的（没有真实页面样本），首采时必须按真实页面校正选择器/字段；这是已知限制，不是隐瞒。

## 1. x-collect 机制拆解（只读，`C:\Users\19183\.dsh\tools\x-collect\scripts\x_collect.py`）

| 机制 | 行号 | 说明 |
| --- | --- | --- |
| 专用 profile | `x_collect.py:25`（`PROFILE = ROOT/"profile"`）、`:284`（`user_data_dir=...`） | 独立 user-data-dir，不碰日常 Chrome |
| cookie 名称布尔 | `:398-421`（`_cookie_auth`，`SELECT name FROM cookies WHERE host_key LIKE '%x.com%'`） | 只读名称/计数，不读值 |
| doctor | `:423-435`（未登录直接 `SESSION_EXPIRED`，不开浏览器）、`:352-396`（`_doctor_once` 登录态/handle） | 先 cookie 短路再 headless |
| 风控识别 | `:149-167`（`RISK_JS` 抓 toast/captcha/error DOM）、`:197-214`（`RISK_TOAST_RE`+`risk_from_signals` 纯谓词） | 结构化信号 → 风控布尔 |
| 采集循环风控 | `:565-590`（`_check_state`：SESSION_EXPIRED / RISK_CONTROL 即停）、`:675-681`（stop=`RISK_CONTROL_PARTIAL`，exit 3） | 命中即停，不重试 |
| 收集上限 | `:37-38`（`MAX_LIMIT=60`、`MAX_SECONDS=900`） | 预算硬停 |
| 优雅关闭 | `:259-273`（`_graceful_close`） | 关浏览器 flush cookie |
| CLI | `:721-747`（doctor/login/search/user/tweet 子命令） | 本批不执行 |

## 2. 小红书适配设计（本批实现，`tools/selection/xiaohongshu.py`）

| 项 | 设计 | 状态 |
| --- | --- | --- |
| `search_url(keyword)` | `https://www.xiaohongshu.com/search_result?keyword=<quoted>` | 骨架（URL 模板，未请求） |
| `parse_results(html)` | HTMLParser 抽 `/explore/<note_id>` 卡片 title/正文摘要≤200 字；signal dict 含 `platform/xiaohongshu`、`origin_kind='real'`、`content_hash`（models） | fixture 驱动；**结构假设待首采校正** |
| `parse_replies(json)` | 构造笔记 JSON 的 comments→楼层 signal（parent_id 保留） | fixture 驱动；待真实样本 |
| `RISK_MARKERS` | text：安全验证/验证码/登录墙/请登录/访问异常/操作频繁/captcha/verify…；DOM：class/id/data-testid/src 含 captcha、login-mask、login-wall | 命中即 `_stop_for`（`ok=false, stop=true, retry=false`） |
| `_stop_for(reason)` | 即停返回，不重试、不翻页 | 已实现 |
| `doctor(profile_dir)` | 只查 `profile/Default/Network/Cookies`（只读 sqlite，`host_key LIKE '%xiaohongshu.com%'`）；cookie 名称布尔：`web_session/a1/webId/customerClientId`；`state=ready|waiting_user`；未登录 exit **2** 并打印“等待用户登录”；**绝不 launch 浏览器** | 三态测试通过 |

**真实采集时计划**（复用 x-collect venv 的 nodriver，本批不 pip install）：`C:\Users\19183\.dsh\tools\x-collect\venv\Scripts\python.exe` 直接运行本项目脚本（`sys.path` 注入 x-collect venv 或以该解释器执行），`uc.start(user_data_dir=<xhs profile>, headless=True)`；doctor 未 ready 不得启动浏览器；采集循环每步 `_check_state` 风控即停（对齐 x-collect `:565-590`）；单轮 `limit≤5`、`MAX_SECONDS≤300`。

## 3. 登录阶段（用户已说“开始小红书”；**本批未执行，状态=待建/待新派发**）

按用户 2026-10-25 steer 要点，登录阶段要做：

1. 在 `C:\Users\19183\.dsh\tools\xhs-collect\` 建独立目录与专用 profile（**复用** x-collect 的 venv/nodriver，不 pip install）。
2. 提供 `login` 脚本：打开可见窗口由用户本人扫码；**脚本不读不填账号/密码/验证码**；等待 300s，超时不重试只报告。
3. 登录完成后自动关窗 → `doctor` 验证 cookie 名称布尔 → 写台账。
4. doctor ready 后停；首采 1 条需新确认派发，不自动采。

**本批范围只含 tools/selection、tests、docs/validation/v9/xhs-readiness；工具目录脚本不在此 scope**，login 脚本本身尚未创建——需要新派发（或明确授权写 `C:\Users\19183\.dsh\tools\xhs-collect\`）后执行。DESIGN 已写清调用方式，随时可建。

## 4. 与 ACCOUNT-SAFETY 五步的映射

| 五步 | 本批状态 |
| --- | --- |
| 1 专用 profile | 设计完成（`C:\Users\19183\.dsh\tools\xhs-collect\profile\`，计划路径）；未创建 |
| 2 用户本人登录 | 等用户操作；login 脚本待新派发 |
| 3 doctor 验证 | `xiaohongshu.doctor` 已实现（cookie 名称布尔，未登录 exit 2） |
| 4 单条小样本 | 未做（需新派发/确认） |
| 5 记录台账 | `LEDGER.md` 登记 xiaohongshu 行（handle=待登录，状态=待用户登录） |

## 5. 已知限制

- 页面结构是**构造假设**，首采必须校正；风控词表/DOM 特征同样需按真实页面对照。
- 本批零网络、零依赖、零浏览器启动；doctor 只读 sqlite。
- 未验证：真实登录后 cookie 集、真实风控页样本、nodriver 实跑。
