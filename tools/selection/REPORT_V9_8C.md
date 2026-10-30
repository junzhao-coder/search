# V9-8c 实现报告：小红书采集骨架（fixture 驱动）+ 风控识别 + doctor 只读版

> 任务 `task-78569f34c8cd2fac3df9ef2ed121f2eb`（rev2，计划 v9）；范围 `tools/selection`、`tests`、`docs/validation/v9/xhs-readiness`。
> 2026-10-25 22:18–22:24 UTC+8。**零真实请求、零浏览器启动、零 pip install**；x-collect 目录只读；未登录、未改业务库/工作单库/CSV。

## 1. design（DESIGN.md）

- x-collect 机制拆解（真实行号）：专用 profile `x_collect.py:25,284`；cookie 名称布尔 `:398-421`；doctor 先 cookie 短路 `:423-435`、`_doctor_once :352-396`；风控 DOM/toast `:149-167`、纯谓词 `:197-214`；采集循环风控即停 `:565-590`、`RISK_CONTROL_PARTIAL :675-681`；上限 `:37-38`；优雅关闭 `:259-273`；CLI `:721-747`。
- 小红书适配与 ACCOUNT-SAFETY 五步映射：见 `DESIGN.md` §2/§4。
- **登录阶段状态（用户已说“开始小红书”）**：本批 scope 不含工具目录，login 脚本**尚未创建（待新派发/授权写 `C:\Users\19183\.dsh\tools\xhs-collect\`）**；DESIGN §3 已写清完整执行方式（复用 x-collect venv/nodriver、300s 超时、不读不填凭据、doctor 验证、ready 后停）。

## 2. parser（tools/selection/xiaohongshu.py）

- `search_url(keyword)` → `https://www.xiaohongshu.com/search_result?keyword=<quoted>`（模板，未请求）。
- `parse_results(html)`：HTMLParser 抽 `/explore/<note_id>` 卡片，quote≤200 字；signal dict：platform=`xiaohongshu`、native_id=note_id、url、title、quote、lang（models.lang_of）、origin_kind='real'、raw_sha256=sha256(html)、content_hash=models.content_hash。
- `parse_replies(json)`：构造笔记 JSON comments→楼层 signal（保留 parent_id）。
- 全部可注入/零网络。

## 3. risk / doctor

- `RISK_MARKERS`：text（安全验证/验证码/登录墙/请登录/访问异常/操作频繁/rate limit/captcha/verify/风控）；DOM（class/id/data-testid/src 含 captcha、login-mask、login-wall）——**DOM 检查经 HTMLParser 属性判定**（修掉了把 CSS 选择器当正则的误命中）。
- `_stop_for(reason)`：`{ok:false, stop:true, stop_reason, retry:false}`；命中即停不重试。
- `check_profile(dir)`：只读 `Default/Network/Cookies`（host_key LIKE '%xiaohongshu.com%'），cookie 名称布尔（web_session/a1/webId/customerClientId），不读值；`state=ready|waiting_user`。
- `doctor(dir)`：ready exit 0；未登录 exit **2** 并打印“等待用户登录”；**绝不 launch 浏览器**。

## 4. fixtures（构造）

`docs/validation/v9/xhs-readiness/fixtures/`：`results_page.html`（3 笔记+评论计数）、`login_wall.html`、`captcha_page.html`、`note_comments.json`（3 楼层含 parent）。**结构假设，首采时按真实页面校正**（见 §7 声明）。

## 5. tests（真实 exit）

`tests/test_selection_xiaohongshu.py` 7 项：`test_search_url`、`test_parse_results_ok`、`test_parse_login_wall_stops`、`test_parse_captcha_stops`、`test_parse_replies_fixture`、`test_doctor_three_states`（不存在/未登录/ready 模拟）、`test_stop_payload_never_retries`。

| suite | 结果 | 日志 |
| --- | --- | --- |
| selection（基线 63 + 7 新） | **70 tests OK** | `tools/selection/logs/tests_selection_v98c.log` exit 0 |
| workbench | **218 tests OK** | `tools/selection/logs/workbench_v98c.log` exit 0 |
| 项目全套（基线 397 + 7 新） | **404 tests OK** | `tools/selection/logs/project_v98c.log` exit 0 |

- cwd `D:\桌面\two`；UTC 22:21–22:24。

## 6. ledger

`docs/validation/v9/xhs-readiness/LEDGER.md`：xiaohongshu 行（profile 计划路径 `C:\Users\19183\.dsh\tools\xhs-collect\profile`、handle=待登录、状态=待用户登录）；同步列出 x/B站/v2ex/github 现状。主台账 `account-safety/ACCOUNT-SAFETY.md` 不在本任务 scope，未改动。

## 7. 声明与限制

- **结构假设待首采校正**：fixtures 页面/JSON 结构是构造的；真实小红书页面的 DOM/字段/风控样式首采时必须校正（选择器、字段名、风控词表）。这是已知限制，不是隐瞒。
- doctor 的“ready 模拟”用本地构造 Cookies sqlite，不是真实 profile。
- 未验证：真实登录后 cookie 集、真实风控页、nodriver 实跑、首采（需新派发确认）。
- 零网络：全程未发请求、未下载、未开浏览器。
