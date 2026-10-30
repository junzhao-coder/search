# 闲鱼 / 小红书 人工登录 + 登录后只读搜索验证（计划 v6）

- 执行者：**C**（未参与 x-collect 实现）
- 方式：本机 Chrome **155.0.8059.86** + nodriver **0.50.6**（只读复用 `C:\Users\19183\.dsh\tools\x-collect\venv`）、**独立 profile**、进程级代理 `127.0.0.1:10808`
- 登录：**两平台均由用户本人**在可见窗口完成（扫码/手机号）；执行者**只开窗、轮询检测、关闭**，未代填账号密码、未索取验证码、未读输入框内容
- 检测口径：**只认登录态专属 cookie 名称**（闲鱼 `unb`、小红书 `web_session`）+ **连续 2 次轮询确认**；不凭 URL 判断
- 搜索：`AI模板`（闲鱼 `goofish.com/search?q=AI模板`、小红书 `search_result?keyword=AI模板`），滚动 1–2 屏，取 10–20 条，字段缺失写 `null`

## 一、结果总览

| 平台 | 登录 | 登录态 cookie（名称/行数） | 等待耗时 | 搜索条数 | 验证码 | 状态 |
| --- | --- | --- | --- | --- | --- | --- |
| 闲鱼 | **成功** | `unb`（共 11 个 cookie 名称） | **271.7s**（91 次轮询，3s/次） | **20** | 无 | `stopped=ok` |
| 小红书 | **成功** | `web_session`（共 16 个 cookie 名称） | **3.0s**（2 次轮询；沿用同一 profile 已登录态） | **20** | 无 | `stopped=ok` |

> 小红书首轮（新 profile）曾 300s 超时未登录；用户登录后**同一 profile 复跑**，`web_session` 首次轮询即命中并于第 2 次确认，故耗时 3.0s。

## 二、字段与样例

**闲鱼**（`data/xianyu_items.jsonl`，20 行）：字段 `href / title / price / raw_text`
- 例：`【自动发货】2026最新最全AI提示词合集 170+细分行业门类…`，`price="¥ 1"`，`raw_text` 含 `2514人想要`、`江苏`、`发货极快`
- 价格字段可用（`¥` 前缀），卡片文本含“想要人数/地区/发货时效”等附加信号

**小红书**（`data/xiaohongshu_items.jsonl`，20 行）：字段 `href / title`（`price` 为 `null`，该平台卡片不显示价格）
- 例：`有合适的AI生图网站推荐吗`、`博士生必备科研skills(2) 绘图篇`、`小红薯6A2B3332`
- 笔记链接形如 `https://www.xiaohongshu.com/explore/<24位hex>`

## 三、存证

| 平台 | 截图 | HTML |
| --- | --- | --- |
| 闲鱼 | `tools/platform-login/shots/xianyu_search_20261022_151124.png`（369,554 B，`888bbbd11f31`） | `tools/platform-login/pages/xianyu_search_20261022_151124.html`（266,690 B，`08241d2b31af`） |
| 小红书 | `tools/platform-login/shots/xiaohongshu_search_20261022_152314.png`（235,654 B，`11ee3163de05`） | `tools/platform-login/pages/xiaohongshu_search_20261022_152314.html`（229,997 B，`b72db69a0086`） |

- 数据：`data/xianyu_items.jsonl`（`ab6053415049`）、`data/xiaohongshu_items.jsonl`（`ad723c87791a`）
- 摘要：`data/summary_run1_xianyu.json`（`27cc0decc8ae`，闲鱼轮）、`data/login_search_summary.json`（`d8b33f2f9177`，小红书轮）
- 日志：`logs/login_search_run1.log`（`f791682585c3`）、`logs/login_search.log`（`dc0e27ce7d54`），均含 **UTC 时间 + 每步 exit**
- 脚本：`tools/platform-login/login_and_search.py`（`e27d97dbe17c`）

## 四、过程中的两次自我更正（如实记录）

1. **误判“登录成功”**：首版检测把 `_m_h5_tk`（匿名访问也会写入）当作闲鱼登录标志，开窗 4s 即误报“已登录”。→ 已停掉重开，改为**只认 `unb`**并要求连续 2 次确认。
2. **检测盲区**：小红书 `web_session` 为 **HttpOnly**，`document.cookie` 读不到，导致首轮即使已登录也检测不到。→ 改为 **CDP `Network.getCookies`** 读取全部 cookie 名称（仍只记名称、不读值）后，登录态立即命中。

## 五、限制与建议

1. **风控**：本次两平台均**未触发**滑块/验证码；但这是**单账号、单次、低频率**（页面操作间隔 ≥8s）下的结果，**不能外推**为“风控宽松”。建议生产侧保持 ≥8s/请求、单平台每次 ≤3 次尝试、遇验证码即停并告警。
2. **登录依赖人工**：两平台搜索均需登录；本次由用户本人在可见窗口完成。**不建议**自动化账号密码输入或短信验证码代收；若要长期运行，应复用**用户本人已登录的 profile**（本批 `tools/platform-login/profile`、`tools/platform-login/profiles/xhs` 即为两份独立 profile）。
3. **字段缺失**：小红书卡片不含价格（`price=null`）；闲鱼价格与“想要人数”可直接从卡片文本解析。两者均**未取**正文/详情页数据（只读搜索列表）。
4. **未验证**：翻页、详情页、发布时间/点赞数等结构化字段、多关键词与多时段稳定性、登录态有效期、频率上限阈值——均未测。
5. **合规**：仅只读搜索，未发布/点赞/关注/私信/下单；未导入他人 Cookie、未改业务系统、未装依赖。

## 六、复跑

```powershell
cd D:\桌面\two\tools\platform-login
& C:\Users\19183\.dsh\tools\x-collect\venv\Scripts\python.exe .\login_and_search.py --wait 1200 --platforms xiaohongshu --profile profiles/xhs
# 闲鱼同理：--platforms xianyu --profile profile
```

> 复跑会复用对应 profile 的登录态；若登录过期，窗口会停在登录页等待用户本人操作。
