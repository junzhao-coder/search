# 闲鱼 / 小红书 只读采集可行性验证（计划 v6 B1）

- 执行者：**C**（未参与 x-collect 实现）；方式：本机 Chrome 155 + nodriver 0.50.6（只读复用 x-collect venv）、独立 profile、进程级代理 `127.0.0.1:10808`
- 采集窗口：2026-10-22T06:47:54Z → 2026-10-22T06:48:40Z（UTC），总耗时见 `logs/probe.log` 末行
- 频率纪律：页面操作间隔 ≥8s、每平台 ≤3 次尝试、遇验证码立即停；全程**只读**——未点击关注/点赞/私信/购买，未导入 Cookie，未代登录

## 一、结论总览

| 平台 | 匿名可读？ | 拦截类型 | 可读条目数 | 关键证据 |
| --- | --- | --- | --- | --- |
| 闲鱼（goofish.com） | **否**（搜索结果需登录） | 登录墙：页面可加载但结果区 `加载中...`、仅导航/筛选可见 | **0** | xianyu_home_20261022_144755.html→**login_wall**, xianyu_search_20261022_144810.html→**login_wall** |
| 小红书（xiaohongshu.com） | **搜索否** / 发现页结构可见、正文不可读 | 搜索页=**登录墙**（逐字“登录后查看搜索结果”“手机号登录”“获取验证码”）；发现页有 30 个 `note-item` 节点与 `__INITIAL_STATE__`，但可见正文仅页脚法务信息 | 搜索 **0**；发现页**可靠 0**（见文末更正：内嵌 JSON 抽取的 4 条为未验证误报） | xiaohongshu_explore_*.html→**content_structure_only**；xiaohongshu_search_*.html→**login_wall** |

## 二、逐次尝试（真实 URL / 判定 / 存证）

| 平台 | 尝试 | URL | 判定 | 可见文本长度 | 截图 | HTML 存证 |
| --- | --- | --- | --- | --- | --- | --- |
| xianyu | home | — | login_wall | 6442 | `shots/xianyu_home_20261022_144755.png` | `pages/xianyu_home_20261022_144755.html` |

| xianyu | search | — | login_wall | 930 | `shots/xianyu_search_20261022_144810.png` | `pages/xianyu_search_20261022_144810.html` |

| xiaohongshu | explore | — | captcha | 2070 | `shots/xiaohongshu_explore_20261022_144833.png` | `pages/xiaohongshu_explore_20261022_144833.html` |

| xiaohongshu | search | — | captcha | 1127 | `shots/xiaohongshu_search_20261022_144818.png` | `pages/xiaohongshu_search_20261022_144818.html` |

## 三、字段清单（可读部分）

- **闲鱼**：标题、导航分类、筛选器名称可见；**商品卡片字段（标题/价格/卖家/链接）在匿名态不可得**（结果区未渲染）。
- **小红书**：发现页可见 `note-item` 节点（HTML 计数 30），内嵌 `__INITIAL_STATE__` 存在；抽取字段：`note_id / title / author / liked / type`（缺失写 null）。搜索页 0 条（登录墙）。

## 四、拦截类型与判据

- 闲鱼：`login` 标记命中 ['登录', '立即登录', '登录', '立即登录']；搜索页正文仅 930 字符且含 `加载中...`。
- 小红书搜索页：正文逐字含 `登录后查看搜索结果`、`手机号登录`、`获取验证码`、`登录`（标记 {'login': ['登录', '手机号登录', '登录后查看'], 'captcha': ['验证码', 'captcha'], 'empty': []}）。
- 未出现滑块/验证码弹窗；**未触发任何二次验证**，因此“风控强度”只能记为“未触发”，不能外推。

## 四·补：对 ①`captcha` 判定与 ②抽取 4 条的**自我更正**（追加，不改写上文）

1. **`captcha` 判定系误命中**：`analysis.json` 中两页 `captcha` 标记来自 **JS 资源里的字符串**（`captcha`/`验证码` 出现在打包脚本中），**页面上没有可见的验证码/滑块 UI**，也没有触发二次验证。更正后的判定：小红书**搜索页 = 登录墙**；**发现页 = 仅页面结构可见（content_structure_only）**，正文不可读。
2. **`data/items_xhs.jsonl` 的 4 条为未验证误报**：它们来自 `__INITIAL_STATE__` 里与笔记无关的字典（`note_id` 取到 `travel`/`qa` 这类非笔记 ID），**不能算作可读笔记**。按“字段缺失写 null、不编造”的纪律，本批**两平台可靠可读条目均为 0**。
3. 这份修正意味着：**结论方向不变**（两平台搜索均需登录、匿名态不可采集），但**不能声称已抽到任何小红书笔记**。

## 五、尝试次数与耗时

- 闲鱼 2 次（home、search），小红书 2 次（search、explore），全部 `exit=0`；两次页面间均 ≥8s。
- 总耗时见 `logs/probe.log` 末行（`elapsed=…`）；各步 UTC 时间戳均在 `logs/probe.log`。

## 六、限制与建议

1) **频控与合规**：本批未做并发/高频，未触发风控；生产采集建议保持 ≥8s/请求、每次 ≤3 次尝试、遇验证码即停。
2) **登录门槛**：两平台搜索结果均需登录。**不建议**用他人账号或导入 Cookie；若必须登录，应由用户本人手动登录后复用其会话（需产品/合规确认），本探针不做。
3) **可行替代**：小红书发现页/公开笔记页存在 `__INITIAL_STATE__` 结构化数据，可在**不登录**的前提下抽取“发现流”样本（本批已抽出候选），但**搜索关键词**路径不可用；闲鱼匿名态基本不可用。
4) **未验证项**：翻页、详情页、价格/成交量字段、频控阈值、登录后可用性——均未测，不得据本报告外推。

## 七、产物与复跑

- 脚本：`probe_feasibility.py`（采集）、`analyze_pages.py`（HTML 分析）
- 数据：`data/probe_summary.json`、`data/analysis.json`、`data/items_xhs.jsonl`
- 日志：`logs/probe.log`（UTC/每步 exit）、`logs/run1.log`、`logs/analyze_run*.log`
- 存证：`shots/*.png`（4 张）、`pages/*.html`（4 份，含 sha256 见 `data/analysis.json`）
- 复跑：`<x-collect venv>\python.exe probe_feasibility.py`（cwd=本目录；需本机 Chrome 与代理 10808 在听）

> 边界声明：本批**只读**，未点击关注/点赞/私信/购买，未导入 Cookie、未修改 DSH 配置或 x-collect，未安装新依赖。
