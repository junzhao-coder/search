# 本地机会工作台（独立 UI）交付报告

- 执行者：**C**（`session-c1428bc7…`）；范围：`tools/workbench/`、`start_workbench.cmd`、`docs/validation/money-project/workbench-ui/`
- 时间：2026-10-22T10:34Z 启动实测；报告生成 2026-10-22T10:46Z
- 结论：**五页 UI 已可独立启动并浏览器直达**，筛选/排序/清空/展开**真实生效**，桌面无整页横向溢出，**390×844 窄屏实测无溢出**；**原 334 套件出现 1 个外部引发失败**（非本任务改动，见 §8）

## 1. 已实测 URL 与启动/停止

| 项 | 值 |
| --- | --- |
| 实测 URL | **http://127.0.0.1:5015/**（仅绑定 `127.0.0.1`） |
| 当前服务 | **保留运行中**：PID **123132**（`python -X utf8 tools\workbench\run.py --port 5015 --no-browser`），健康检查 `/healthz` 200 |
| 停止 | 在启动窗口按 **Ctrl+C**；或 `Stop-Process -Id 123132`（保留原因：交付要求"浏览器直达"，留一个独立进程供你直接打开） |
| 一键启动 | 双击 **`start_workbench.cmd`**（自动用 `.venv\Scripts\python.exe`，打开浏览器） |
| 普通终端 | `python tools\workbench\run.py`（默认 5015；`--port 5016` 换端口；`--no-browser` 供测试） |
| 端口冲突 | 启动前自检，占用时打印换端口提示并 `exit 3`，**不会结束任何其它进程** |
| 依赖 | 现有 `.venv` 的 Flask；**未装任何新包**；无 CDN/外网静态资源；无 DSH/MCP/`__DSH_BOOT__` 依赖 |

**零业务库写入**：`app.py` 以**文件路径**加载 `app/dash/data.py`（`importlib.util.spec_from_file_location`），**不 import `app` 包**，因此不会触发 `create_app/ensure_schema`；`instance/app.db` 在本次全部运行前后 sha256 均为 `e073f828…4eb85`（未变化）。工作台单测亦断言该库哈希不变（`tearDownClass`）。

## 2. 五页与设计系统

| 页面 | 内容 |
| --- | --- |
| `/` 总览 | 首屏「当前最值得先核验的一条」+ 下一步动作；四条关键数字；机会—货源联动前 5 行 |
| `/opportunities` | 60 条评分机会：关键词/平台/最低分筛选、评分与需求排序、**行内展开**证据与评分构成 |
| `/sources` | 14 货源（许可结论/理由/关键句/证据链接）+ 20 条价格信号 + 10 行联动（**显式显示 `price_scope`**） |
| `/collect` | 9 个数据文件状态（存在性/行数/坏行/体积/UTC mtime）+ 平台样本 40 条（可筛平台/关键词） |
| `/daily` | 批次快照：计数、许可分布、价格区间；**明确"不是经营日报"** |

设计系统（`tools/workbench/DESIGN.md`）：冷中性底 `#f5f7fa` + 面板白 + 克制蓝 `#1d4ed8`；侧栏 232px 深色导航 + 顶部工作区；正文 15px/1.6；统一 8–10px 圆角与 16px 间距；**无渐变/无炫光/无粗彩色左边框**；状态一律用文字+浅色 chip；表格为唯一重元素，容器内滚动。

## 3. 浏览器真实交互（nodriver，headless，本机 127.0.0.1:5015）

| 动作 | 前后证据 |
| --- | --- |
| 初始 | `筛后 60 / 共 60`，`tbody tr = 60` |
| 关键词 `notion`（真实表单提交） | **`筛后 55 / 共 60`**，`tr = 55` |
| 排序 `demand`（点击表头） | 首行由 `43 …Gumroad…` → `11 enescingoz/awesome-n8n-templates … 0.674` |
| 再次点击同表头（方向切换） | 首行再次变化（asc/desc 往返） |
| 清空条件 | **`筛后 55` → `筛后 60`**（恢复全量） |
| 展开证据 | `details[open] = 1`；截图 `desktop_opportunities_expanded.jpg` |

> 诚实说明：我最初用 `.evidence` 的 `offsetParent` 统计"可见证据数"，得到 60（不论展开与否）——该指标无效，已以 `details[open]` 与展开截图为准。

## 4. 响应式与溢出（真实测量）

| 视口 | 页面 | innerWidth | scrollWidth | 整页横向溢出 |
| --- | --- | --- | --- | --- |
| 1440×900 窗口 | / · /opportunities · /sources · /collect · /daily | **1418** | 1418 | **否** |
| 390×844（CDP 设备模拟） | / | **390** | 390 | **否** |
| 390×844 | /opportunities | 390 | 390 | **否** |
| 390×844 | /sources | 390 | 390 | **否** |

- 窄屏下最宽元素是 `TABLE`（669–797px），但位于 `.table-wrap{overflow-x:auto}` 内 → **表格内部滚动，不撑破整页**。
- 侧栏在 ≤900px 结构折叠（`body.nav-collapsed`，实测 `navCollapsed=true`、`nav display:none`），JS 不可用时导航仍以列表呈现。
- **本任务修复的真实缺陷**：首版窄屏实测 500px 时 `overflowX=True`（`scrollWidth` 705/685/813 > 500）——原因是 grid 子项 `min-width:auto` 被表格最小内容撑开。已加 `main>*/\.panel{min-width:0}`，复测 390×844 全部 `False`。

## 5. 资源与控制台

- 资源请求 **2 个**（`/static/app.css`、`/static/app.js`），**external_resources = 0**，`external_images = 0`（零外网依赖）。
- 网络失败事件 **0**；控制台事件 **1**，内容为**我的探针自身**的 `cdp subscribe skipped: AttributeError`（事件订阅降级，非页面报错）。
- 静态资源全部本机；表格无图片资源依赖。

## 6. 截图（真实拍摄，JPEG 实际编码，已按内容改名 `.jpg`）

| 文件 | 尺寸 | 说明 |
| --- | --- | --- |
| `desktop_index.jpg` | 1418×802 | 总览 |
| `desktop_opportunities.jpg` | 1418×802 | 机会列表（60 行） |
| `desktop_opportunities_expanded.jpg` | 1258×926 | 展开证据态 |
| `desktop_sources.jpg` | 1418×802 | 货源 + 价格 + 联动 |
| `desktop_collect.jpg` | 1418×802 | 采集来源 |
| `desktop_daily.jpg` | 1418×802 | 每日快照 |
| `mobile_index.jpg` | **390×844** | 手机总览 |
| `mobile_opportunities.jpg` | **390×844** | 手机机会 |
| `mobile_sources.jpg` | **390×844** | 手机货源 |

> 桌面实测视口为 **1418×802**（`--window-size=1440,900` 扣除 headless 窗口边框），非精确 1440×900 内容区；窄屏为 CDP 设备模拟的真实 **390×844**。

## 7. 测试

| 套件 | 命令 | 结果 |
| --- | --- | --- |
| 工作台单测 | `python -X utf8 -m unittest discover -s tests -t . -v`（cwd=`tools/workbench`） | **11/11 OK，exit=0**（`tmp/workbench_tests.log`） |
| 原项目完整套件 | `python -X utf8 -m unittest discover -s tests -v`（`APP_DB_PATH=workbench-ui/tmp/guard_full.db`） | **Ran 334，1 failure，exit=1** ← 见 §8 |

## 8. 外部引发的失败（如实记录，非本任务改动）

失败用例：`tests/dash/test_routes.py::test_opportunities_shows_model_rows_and_links`，断言 `assertIn("0.800", body)` 不成立。

根因（时间线证据，均为**他人写入**，我只读）：

| 对象 | 我上一任务基线（09:08Z 记录） | 现在 | mtime | 结论 |
| --- | --- | --- | --- | --- |
| `scoring/scores.csv` | `ef8310fb…` | `ab0c3546…` | **2026-10-22T10:33:01Z** | 被重新生成（榜首分不再是 0.800） |
| `sourcing/opportunity_sourcing_top10.csv` | `0c365fb8…` | `da5e4461…` | 09:49:48Z | 被重新生成 |
| `templates/dash/base.html` | `b9876a57…`(tree) | `e034c32f…`(tree) | 09:47:07Z | 被修改 |
| `tests/dash`（含 `test_routes.py`） | `3b43f151…`(tree) | `943d92b0…`(tree) | 09:52:17Z | 被修改 |

我的全部写入都在 `tools/workbench`（最新 10:44Z）、`start_workbench.cmd`（10:39Z）、`docs/.../workbench-ui`（10:46Z），**未写过上述四个对象**。因断言写死 `0.800` 而数据已变，属**外部数据/测试不同步**；按边界我**不修改** `tests/dash` 与评分文件，交由策划者指派原责任人处理。

**未变（守卫通过）**：`app/dash` `33f13cce…`、`scoring/model.md` `41c2809b…`、`items.jsonl` `ccb5d307…`、`scoring/raw` `d9694423…`、`sources.csv` `13679b60…`、`price_signals.csv` `e5b04a97…`、`sourcing/raw` `ab6deba3…`、`e2e/*`、`instance/app.db` `e073f828…`、`docs/design/CONTRACT.md` `826c24cc…`。

## 9. 数据口径与诚实性

- 毛利=**低置信估算**（模型假设），界面统一标"毛利估算，待价格核验"；**不显示订单/收益/已赚金额**。
- 可售性字段未就绪 → 一律显示 **未评估**，不写假分（B8 字段接入后可直接替换）。
- `想要≠销量`、`划线价≠成交`、`可商用需保留声明（≠附带素材可转售）` 均写在界面上。
- `/collect` 只显示**文件快照时间**，不标"实时在线"；刷新仅重读产物，不触发采集。
- 联动口径在 `/sources` 明确显示 `price_scope`（`all_20_fallback` / `category_filtered`），并说明两表 id 族不同、不做逐条连接。
- 原始标题仅在展示层清理空白/控制字符，**不改原文件**。

## 10. 偏离与限制

1. **无 `skill` 工具入口**：catalog 列出 `impeccable`/`ponytail`，但本会话未暴露 `skill` 调用，按要求只记一次、未用 Host 脚本反调；设计按任务书给定约束执行。
2. 未使用 Jinja 模板目录，而由 `app.py` 内统一 `layout()` 生成五页（SSR + 原生 JS），以保证五页同一设计系统与零额外依赖；`templates/` 目录未创建（如需可后续迁移）。
3. 桌面截图为 1418×802 内容视口（headless 边框），非精确 1440×900 内容区。
4. 手机 390×844 通过 CDP 设备模拟取得（`--window-size` 在 Windows headless 有最小宽度 ~500）。
5. 未做自动化无障碍审计（无 axe 等工具，未装新依赖）；已提供 `skip` 链接、`aria-current`、`aria-expanded`、`label` 包裹、可见 focus ring、`prefers-reduced-motion`；对比度按 `#101828/#ffffff`、`#5b6778/#ffffff`（≈ 7:1 / 4.9:1）自检。
6. 未做键盘全流程手工回归（Tab 顺序按 DOM 顺序，表格行内 `details` 可聚焦）。
7. 服务仍在运行（PID 123132），如需我停止请告知。

## 11. 复跑命令

```powershell
# 一键
.\start_workbench.cmd
# 或
.\.venv\Scripts\python.exe tools\workbench\run.py --port 5015
# 测试
cd tools\workbench; ..\..\.venv\Scripts\python.exe -X utf8 -m unittest discover -s tests -t . -v
# 浏览器验证（需服务在跑）
C:\Users\19183\.dsh\tools\x-collect\venv\Scripts\python.exe docs\validation\money-project\workbench-ui\browser_check.py
C:\Users\19183\.dsh\tools\x-collect\venv\Scripts\python.exe docs\validation\money-project\workbench-ui\mobile_check.py
```

---

# rev5 窄修结果（2026-10-22T19:1xZ，本节覆盖上文冲突之处）

| # | 要求 | 状态与证据 |
| --- | --- | --- |
| ① | 毛利百分比/区间、未知 `—`、货币只用于真实价格 | **已改**：`82.5%（70%–95%，估算）`；缺失→`—`；`¥1.88` 仅出现在价格信号。单测 `test_margin_is_percent_without_currency_and_price_keeps_currency` **PASS** |
| ② | 可售性按现有字段动态显示分数+中文理由，四档筛选 | **已改**：`sellability()` 派生（阈值见页面 footnote 与 `app.py` docstring：较强售卖=合规≥70%且履约≥70%且可复制≥60%；需求赠送=需求≥75%且合规<70%；不明确=部分缺失/未齐备；未评估=三项全缺）。分数=`100×(0.5合规+0.3履约+0.2可复制)`，仅 UI 提示、不改模型。单测四档计数与理由均 **PASS** |
| ③ | 同表头 desc↔asc 双向、保留条件与计数 | **已改**：`sort_link()` 重写。**3 次真实点击**实测：`?q=模板&platform=x&min_score=0.3&sell=较强售卖` → `&sort=demand&dir=desc` → `dir=asc` → `dir=desc`，每步 `筛后 2 / 共 60`、`rows=2` 不丢失（`interaction_evidence_v2.json`） |
| ④ | 许可"待核验"映射真实"禁止/不明" | **已改**：`待核验` 映射为 `verdict ∉ {可商用, 需授权}`。单测三档：可商用=1、需授权=1、待核验=**2**（禁止+不明）**PASS** |
| ⑤ | 修恒真单测、隔离 fixture | **已改**：全新 `tests/test_workbench.py` 使用**临时 root + 合成 CSV**，断言 min_score 逐行（0.9/0.6 命中、0.3/0.2 排除）、排序链接保留条件且方向翻转、字段存在/缺失两场景；**不再依赖共享榜首 0.800** |
| ⑥ | 手机目录按钮横排可点 + 键盘证据 + 1440×900 精确重拍 | **已改/已测**：移动端品牌与「目录」同排，按钮**高 50px**；键盘实测 Tab×6 依次落到 `跳到主要内容 → 总览 → 机会线索 → 货源与价格 → 采集来源 → 每日快照`，`Space` 展开 `details[open]=1`；截图 **桌面 1440×900**（`inner=1440×900`、`scrollW=1440`、无溢出）、**手机 390×844**（`scrollW=390`、无溢出）。**未完全验证**：Focus 在当前页链接上按 Enter 未发生跳转（URL 未变），筛选框 Enter 提交后计数仍 60/60 —— 这两条**不标 PASS** |
| ⑦ | 端口已是本工作台 → 提示已在运行；其它进程占用仍报错不杀 | **部分验证**：场景 A（端口已是本工作台）实测 **exit=0** 并打印"已在运行 http://127.0.0.1:5015/"；场景 B（外部进程占用）**未取得有效证据** —— 我的 dummy 监听进程未成功启动，测试变成了"端口空闲正常启动"，故**不标 PASS**。同时修掉一个真实缺陷：`port_in_use` 原用 `SO_REUSEADDR` 在 Windows 会误判占用端口为空闲，导致重复启动真的去 bind 并挂住；已移除该选项 |
| ⑧ | 重跑 UI 单测与原 334+ | 工作台单测 **10/10 OK，exit=0**（`tmp/workbench_tests_v2.log`）；原 334 套件本轮**未重跑**（上一轮为 Ran 334 / 1 failure / exit=1，外部 `scores.csv` 10:33Z 重生成导致 `0.800` 断言失效；待 B8 修同步后重跑，**不标绿**） |

**产物（本轮重建）**：`shots/desktop_{index,opportunities,opportunities_expanded,sources,collect,daily}.jpg`（**1440×900**）、`shots/mobile_{index,opportunities,sources}.jpg`（**390×844**）、`shots_manifest.json`（路径/宽高/bytes/sha256）、`interaction_evidence_v2.json`（3 次点击 + 9 条键盘步进 + 视口/溢出）、`tmp/workbench_tests_v2.log`、`tmp/serve_v2.log`。**旧失败记录保留**：`tmp/original_suite.log`（334/1F）与旧截图未删除。

**仍未完成（如实列出）**：⑥ 的 Enter 导航/Enter 提交两条键盘路径、⑦ 场景 B、⑧ 原 334 重跑。原因分别是焦点落在当前页、提交按钮焦点未触发 submit、dummy 监听未启动、以及 B8 数据同步未完成。

---

# rev11 收尾（2026-10-22T19:4xZ）——全部关键项已闭合

| 项 | 结果（真实） |
| --- | --- |
| ① `tests/dash` 解耦确认 | **已解耦**：`tests/dash/test_routes.py:64-67` 改为从 fixture CSV 读 `expected_score` 再断言，不再硬编码 `0.800`（task-0093effe 生效） |
| ② 完整套件 | **`Ran 334 tests — OK`，`exit=0`，50.309s**（`APP_DB_PATH=workbench-ui/tmp/full_final.db`），日志 `tmp/full_suite_final.log` → **真绿** |
| ③ 工作台单测 | **`Ran 11 tests — OK`，`exit=0`，0.253s**，日志 `tmp/workbench_tests_final.log` |
| ④ 截图与清单一致性 | **已消除不一致**：单趟重建（先删旧 jpg/清单），同进程写截图→读回 `bytes+sha256` 入清单→**末尾自校验 9/9 一致、mismatch=0、ok=True**；抽查 `desktop_opportunities.jpg` 133,852B/`999d5b1f…`、`desktop_index.jpg` 128,219B/`0f229b00…`、`mobile_index.jpg` 45,546B/`4b88a33f…` 均与磁盘相同。清单字段含 `file/path/width/height/bytes/sha256/viewport/captured_utc` |
| ⑤ 键盘 Enter 判定依据 | **同法在最小原生 form 上也不提交**：`data:text/html` 页面（`<form><input name=q value=AI><button type=submit>`）聚焦 button 后 `rawKeyDown Enter` → `submitted=false`（URL 未变）。据此判定为 **CDP 注入限制**，`keyboard_enter_verdict = "CDP 注入限制（原生 form 同样不提交）"`；工作台 Enter 提交保持**未验证**，未改 HTML |
| ⑥ 边界 | `instance/app.db` `e073f828…4eb85`、`docs/design/CONTRACT.md` `826c24cc…`、`scoring/scores.csv` `ab0c3546…` **均未变**；未改 scoring/真实 CSV/旧测试语义；未加依赖 |

**已知瑕疵（如实记录）**：重建后的 3 次点击证据所用示例 URL 为 `?q=模板&platform=x&min_score=0.3&sell=较强售卖`，在新（只读 `sellability_norm`）口径下匹配行数为 **0**，因此该段落每步都是 `筛后 0 / 共 60`——**参数保留与方向翻转仍成立**，但"非零计数"演示不足；非零场景由单测 `test_sort_link_preserves_filters` 与 `test_sort_direction_flips_rows`（4 行 fixture）覆盖。

**产物**：`shots/*.jpg`（桌面 5 × 1440×900、手机 3 × 390×844）、`shots_manifest.json`（9 条，含自校验）、`interaction_evidence_v2.json`（含 `manifest_verification`、`native_form_probe`、`keyboard_enter_verdict`）、`keyboard_port_evidence.json`（键盘 4 例 + 外部端口 exit=3）、`tmp/full_suite_final.log`、`tmp/workbench_tests_final.log`。旧失败记录继续留档。

