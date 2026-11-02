# v18 单帖引擎试点：Playwright 主引擎 / nodriver 备用（本地 fixture）

- 生成时间：2026-11-02T18:56:42+08:00
- 命令：`C:\Users\19183\.dsh\tools\x-collect\venv\Scripts\python.exe -m tools.selection.engine_trial --engine nodriver --runs 3 --out docs/validation/v18/engine-trial --merge-existing --fixture docs/validation/v18/engine-trial/fixture.html`
- 输出目录：`D:\桌面\two\docs\validation\v18\engine-trial`
- Playwright 数据生成时间：2026-11-02T18:56:33+08:00
- Playwright 命令：`C:\Users\19183\AppData\Local\Programs\Python\Python312\python.exe -m tools.selection.engine_trial --engine playwright --runs 3 --out docs/validation/v18/engine-trial --merge-existing --fixture docs/validation/v18/engine-trial/fixture.html`

## 结论
- **playwright**：verified；stop=no_growth,no_growth,no_growth; ids=12/12; missing=0; extra=0; actions_ok=True; visibility=proven。
  - 桌面可见性：`desktop.prove` 前台窗口匹配 + 窗口矩形通过。
- **nodriver**：verified；stop=no_growth,no_growth,no_growth; ids=12/12; missing=0; extra=0; actions_ok=True; visibility=proven。
  - 桌面可见性：`desktop.prove` 前台窗口匹配 + 窗口矩形通过。
- **两引擎对照**：compared；

| 对照项 | 值 |
| --- | --- |
| 共同 ID | 12 |
| 仅 Playwright | 无 |
| 仅 nodriver | 无 |

## 环境

| 项 | 值 |
| --- | --- |
| 操作系统 | Windows-11-10.0.26200-SP0 |
| Python | 3.12.10 |
| 解释器 | `C:\Users\19183\AppData\Local\Programs\Python\Python312\python.exe` |
| 工作目录 | `D:\桌面\two` |
| nodriver 解释器 | `C:\Users\19183\.dsh\tools\x-collect\venv\Scripts\python.exe` |
| nodriver Python | 3.12.10 |
| nodriver venv | `C:\Users\19183\.dsh\tools\x-collect\venv` |
| playwright 版本 | 1.60.0 |
| playwright Chrome | `C:\Program Files\Google\Chrome\Application\chrome.exe` |
| playwright 浏览器版本 | 156.0.8078.79 |
| nodriver 版本 | 0.50.6 |
| nodriver Chrome | `C:\Program Files\Google\Chrome\Application\chrome.exe` |
| nodriver 浏览器版本 | 156.0.0.0 |

> 环境边界：项目 `.venv` 未安装 playwright；Playwright 使用已存在的 Python 3.12.10（playwright 1.60.0），nodriver 使用本机已有的 x-collect venv（nodriver 0.50.6）；未安装或修改任何环境。

- **playwright** 临时 profile：`C:\Users\19183\AppData\Local\Temp\dsh-engine-trial-pw-z9cmfaxy`（运行结束删除）
- **nodriver** 临时 profile：`C:\Users\19183\AppData\Local\Temp\dsh-engine-trial-nd-7rk6bx14`（运行结束删除）

## Fixture 与地面真值

- 文件：`D:\桌面\two\docs\validation\v18\engine-trial\fixture.html`
- URL：`file:///D:/%E6%A1%8C%E9%9D%A2/two/docs/validation/v18/engine-trial/fixture.html`
- 帖子 ID：`900000001`；正文、作者、时间、点赞均来自页面 DOM。
- 地面真值：9 条顶层评论 + 2 条楼中楼 + 1 条帖子；页面声明 12 条评论。

## 计时（每次运行独立启动浏览器）

### playwright（n=3）

| 阶段 | n | min ms | median ms | max ms |
| --- | --- | --- | --- | --- |
| 启动浏览器 | 3 | 875.3 | 898.2 | 1037.8 |
| 导航 | 3 | 97.5 | 101.8 | 108.2 |
| 首次读取 | 3 | 3.9 | 3.9 | 4.0 |
| 证据采集（截图/置前） | 3 | 221.4 | 226.5 | 285.2 |
| 动作后截图 | 3 | 30.2 | 37.1 | 42.7 |
| 动作+读取 | 3 | 1413.3 | 1419.8 | 1438.2 |
| 关闭 | 3 | 283.3 | 308.9 | 309.6 |
| 总计（含证据） | 3 | 2974.5 | 2977.9 | 3194.4 |

### nodriver（n=3）

| 阶段 | n | min ms | median ms | max ms |
| --- | --- | --- | --- | --- |
| 启动浏览器 | 3 | 846.9 | 886.2 | 1217.6 |
| 导航 | 3 | 78.8 | 127.3 | 193.2 |
| 首次读取 | 3 | 2.9 | 6.3 | 12.7 |
| 证据采集（截图/置前） | 3 | 1057.9 | 1058.8 | 1084.5 |
| 动作后截图 | 3 | 1041.5 | 1066.5 | 1084.3 |
| 动作+读取 | 3 | 1653.6 | 1656.8 | 1661.7 |
| 关闭 | 3 | 387.7 | 562.5 | 573.0 |
| 总计（含证据） | 3 | 5163.4 | 5355.7 | 5741.6 |

样本量 n=3，同一台机器、同一 Chrome、同一本地 fixture；只用于引擎自身对照，不能外推到真实站点或用户网络。

## 计时差异说明

- 启动/导航/首次读取量级接近；动作+读取中位：Playwright 1419.8 ms，nodriver 1656.8 ms。
- 关闭中位：Playwright 308.9 ms，nodriver 562.5 ms；nodriver 的关闭包含 `aclose`、进程 wait 与 transport close，Playwright 使用 context.close，属于驱动清理路径差异。
- 证据采集中位：Playwright 226.5 ms，nodriver 1058.8 ms；动作后截图中位：Playwright 37.1 ms，nodriver 1066.5 ms。这部分已从动作/关闭阶段扣除，只计入总计；截图与 desktop.prove 的驱动实现差异不影响 ID/动作/位移结论。
- 两边均固定 1280×720 CSS 视口（nodriver 用 CDP `Emulation.setDeviceMetricsOverride`），使用同一 Chrome 156 二进制；ID、动作与页面位移完全一致，计时差异不改变数据判据。
- 扣除证据采集后的总计约：Playwright 2714.3 ms，nodriver 3230.4 ms；差异主要来自关闭清理与点击定位/滚动路径，不是页面数据量差异。

## 实际动作证据

### playwright（run 1）

- 页面事件：wheel=3/3，click=2/2，expand=1，load_more=1，lazy_load=1。
- 可信输入（`isTrusted=true`）：click=2，wheel=3，expand=1，load_more=1。
- 页面位移：scrollY 0 → 931；scrollHeight 729 → 1651。
- 自检：通过；checks={"wheel_events": true, "click_events": true, "expand_event": true, "load_more_event": true, "scroll_event": true, "page_moved": true, "height_grew": true, "trusted_input": true}
- 动作后截图：`D:\桌面\two\docs\validation\v18\engine-trial\shots\playwright-run1-final.png`（31902 bytes）。

### playwright run 1 动作时间线

| 时间线 ms | 阶段 | 细节 |
| --- | --- | --- |
| 0.0 | `start_begin` | `{}` |
| 1037.8 | `start_done` | `{"engine": "playwright", "browser_version": "156.0.8078.79", "channel": "chrome", "headless": false, "profile": "C:\\Users\\19183\\AppData\\Local\\Temp\\dsh-engine-trial-pw-z9cmfax` |
| 1146.0 | `navigate` | `{"driver_ms": 106.6, "url": "file:///D:/%E6%A1%8C%E9%9D%A2/two/docs/validation/v18/engine-trial/fixture.html", "status": 200}` |
| 1149.9 | `first_read` | `{"ids": 4, "records": 3}` |
| 1487.2 | `expand` | `{"clicked": true, "selector": "div.show-more-lzl", "box": {"x": 222.33334350585938, "y": 345.7708435058594, "width": 113.80209350585938, "height": 24}, "via": "playwright_locator_c` |
| 1746.8 | `expand_read` | `{"ids": 6}` |
| 1794.3 | `load_more` | `{"clicked": true, "selector": "#load-more", "box": {"x": 222.33334350585938, "y": 977.3125, "width": 116, "height": 39.3333740234375}, "via": "playwright_locator_click"}` |
| 2054.3 | `load_more_read` | `{"new_ids": ["910000004", "910000005", "910000006", "910000007", "910000008", "910000009"], "ids": 12}` |
| 2318.7 | `scroll_1` | `{"new_ids": [], "scroll_dy": 352, "action": {"dx": 0, "dy": 700, "via": "playwright_mouse_wheel"}}` |
| 2583.1 | `scroll_2` | `{"new_ids": [], "scroll_dy": 0, "action": {"dx": 0, "dy": 700, "via": "playwright_mouse_wheel"}}` |
| 2846.0 | `scroll_3` | `{"new_ids": [], "scroll_dy": 0, "action": {"dx": 0, "dy": 700, "via": "playwright_mouse_wheel"}}` |
| 2848.4 | `final_read` | `{"ids": 12}` |
| 3194.4 | `close` | `{"closed": true, "profile_removed": true, "errors": []}` |

### nodriver（run 1）

- 页面事件：wheel=3/3，click=2/2，expand=1，load_more=1，lazy_load=1。
- 可信输入（`isTrusted=true`）：click=2，wheel=3，expand=1，load_more=1。
- 页面位移：scrollY 0 → 931；scrollHeight 729 → 1651。
- 自检：通过；checks={"wheel_events": true, "click_events": true, "expand_event": true, "load_more_event": true, "scroll_event": true, "page_moved": true, "height_grew": true, "trusted_input": true}
- 动作后截图：`D:\桌面\two\docs\validation\v18\engine-trial\shots\nodriver-run1-final.png`（84285 bytes）。

### nodriver run 1 动作时间线

| 时间线 ms | 阶段 | 细节 |
| --- | --- | --- |
| 0.0 | `start_begin` | `{}` |
| 886.2 | `start_done` | `{"engine": "nodriver", "version": "0.50.6", "chrome": "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe", "headless": false, "profile": "C:\\Users\\19183\\AppData\\Local\` |
| 965.0 | `navigate` | `{"driver_ms": 77.6, "url": "file:///D:/%E6%A1%8C%E9%9D%A2/two/docs/validation/v18/engine-trial/fixture.html", "status": null}` |
| 967.9 | `first_read` | `{"ids": 4, "records": 3}` |
| 2083.2 | `expand` | `{"clicked": true, "selector": "div.show-more-lzl", "box": {"x": 279.2343864440918, "y": 357.7708435058594, "left": 222.33334350585938, "top": 345.7708435058594, "width": 113.802085` |
| 2335.6 | `expand_read` | `{"ids": 6}` |
| 2687.8 | `load_more` | `{"clicked": true, "selector": "#load-more", "box": {"x": 280.3333435058594, "y": 644.3125419616699, "left": 222.33334350585938, "top": 624.6458740234375, "width": 116, "height": 39` |
| 2940.7 | `load_more_read` | `{"new_ids": ["910000004", "910000005", "910000006", "910000007", "910000008", "910000009"], "ids": 12}` |
| 3199.2 | `scroll_1` | `{"new_ids": [], "scroll_dy": 352, "action": {"dx": 0, "dy": 700, "via": "nodriver_cdp_mouse_wheel", "scrolled": true}}` |
| 3453.8 | `scroll_2` | `{"new_ids": [], "scroll_dy": 0, "action": {"dx": 0, "dy": 700, "via": "nodriver_cdp_mouse_wheel", "scrolled": true}}` |
| 3707.5 | `scroll_3` | `{"new_ids": [], "scroll_dy": 0, "action": {"dx": 0, "dy": 700, "via": "nodriver_cdp_mouse_wheel", "scrolled": true}}` |
| 3709.2 | `final_read` | `{"ids": 12}` |
| 5163.4 | `close` | `{"closed": true, "profile_removed": true, "errors": []}` |

## 数据对照

| 引擎 | 运行数 | ID 并集 | 地面真值 | 缺失 | 额外 | 每次一致 |
| --- | --- | --- | --- | --- | --- | --- |
| playwright | 3 | 12 | 12 | 0 | 0 | True |
| nodriver | 3 | 12 | 12 | 0 | 0 | True |

- **playwright**：记录 11（顶层评论 9，楼中楼 2）；likes 已知 11，时间已知 11。
- **nodriver**：记录 11（顶层评论 9，楼中楼 2）；likes 已知 11，时间已知 11。

### 原生 ID 集合

| 类别 | 地面真值 | playwright | nodriver |
| --- | --- | --- | --- |
| 帖子 | 1 | 1/1 | 1/1 |
| 顶层评论 | 9 | 9/9 | 9/9 |
| 楼中楼 | 2 | 2/2 | 2/2 |

- 顶层评论 ID：`910000001, 910000002, 910000003, 910000004, 910000005, 910000006, 910000007, 910000008, 910000009`
- 楼中楼 ID：`920000001, 920000002`

### 字段归属

- **playwright**：11 条记录
  - `native_id`：11/11；来源 `div[data-id]` (11)
  - `text`：11/11；来源 `span.pb-text-wrapper` (11)
  - `author`：11/11；来源 `a.head-name` (11)
  - `published_at`：11/11；来源 `div.comment-desc-left > span` (11)
  - `likes`：11/11；来源 `[data-likes]|.pb-agree-num` (11)
- **nodriver**：11 条记录
  - `native_id`：11/11；来源 `div[data-id]` (11)
  - `text`：11/11；来源 `span.pb-text-wrapper` (11)
  - `author`：11/11；来源 `a.head-name` (11)
  - `published_at`：11/11；来源 `div.comment-desc-left > span` (11)
  - `likes`：11/11；来源 `[data-likes]|.pb-agree-num` (11)

## 停止语义

- **playwright run1**：`no_growth`；连续 2 次滚动无新增原生 ID 且无页面位移；页面声明 12 条，可见 9 条。没有可核验的到底标记，按部分/未知处理，不宣称取全。
- **playwright run2**：`no_growth`；连续 2 次滚动无新增原生 ID 且无页面位移；页面声明 12 条，可见 9 条。没有可核验的到底标记，按部分/未知处理，不宣称取全。
- **playwright run3**：`no_growth`；连续 2 次滚动无新增原生 ID 且无页面位移；页面声明 12 条，可见 9 条。没有可核验的到底标记，按部分/未知处理，不宣称取全。
- **nodriver run1**：`no_growth`；连续 2 次滚动无新增原生 ID 且无页面位移；页面声明 12 条，可见 9 条。没有可核验的到底标记，按部分/未知处理，不宣称取全。
- **nodriver run2**：`no_growth`；连续 2 次滚动无新增原生 ID 且无页面位移；页面声明 12 条，可见 9 条。没有可核验的到底标记，按部分/未知处理，不宣称取全。
- **nodriver run3**：`no_growth`；连续 2 次滚动无新增原生 ID 且无页面位移；页面声明 12 条，可见 9 条。没有可核验的到底标记，按部分/未知处理，不宣称取全。

## 桌面可见性

- **playwright**：proven=True，reason=None，matched_by=title，candidates=2，window=单帖采集基线：本地 fixture_百度贴吧 - Google Chrome，foreground=True，rect={'left': 24, 'top': 15, 'right': 1950, 'bottom': 1287, 'width': 1926, 'height': 1272}
  - 证据边界：前台窗口匹配 + 窗口矩形证明窗口被置前；页面截图只证明页面渲染，不证明人眼已经看到，也不移动系统鼠标指针。
- **nodriver**：proven=True，reason=None，matched_by=title，candidates=2，window=单帖采集基线：本地 fixture_百度贴吧 - Google Chrome，foreground=True，rect={'left': 24, 'top': 15, 'right': 1581, 'bottom': 1505, 'width': 1557, 'height': 1490}
  - 证据边界：前台窗口匹配 + 窗口矩形证明窗口被置前；页面截图只证明页面渲染，不证明人眼已经看到，也不移动系统鼠标指针。

## 本地测试与停止语义

项目 venv（不启动浏览器；playwright/nodriver 不在该解释器，浏览器相关项按环境跳过）：

```powershell
.venv\Scripts\python.exe -m unittest tests.test_v18_engine_trial -v
```

真实有头 Playwright（Python 3.12.10 + playwright 1.60.0）：

```powershell
$env:DSH_ENGINE_TRIAL_REAL = "1"
C:\Users\19183\AppData\Local\Programs\Python\Python312\python.exe -m unittest tests.test_v18_engine_trial.PlaywrightRealTests -v
```

真实有头 nodriver（x-collect venv，nodriver 0.50.6）：

```powershell
$env:DSH_ENGINE_TRIAL_REAL = "1"
C:\Users\19183\.dsh\tools\x-collect\venv\Scripts\python.exe -m unittest tests.test_v18_engine_trial.NodriverRealTests -v
```

覆盖：无增长停止、取消保留部分数据、错误保留部分数据、重复读取去重、缺失字段与父关系、ID 双向差异；完整输出见 `tests.log`。

## 限制与未证明

- 本地 fixture，不是真实贴吧；真实站点选择器、会话、风控均未验证。
- 页面声明 12 条、可见 9 条；no_growth 只证明本次动作无新增/无位移，没有可核验的到底标记，按部分/未知处理。
- Playwright 使用 CDP 合成输入，不移动系统鼠标指针；不是物理鼠标轨迹。
- 样本量为配置的重复次数，同一台机器、同一 Chrome；不能外推到真实站点速度。
- 桌面可见性以 desktop.prove 结果为准；若未 proven，不能声称用户已看到。
- 未访问真实贴吧、未读取或修改用户 profile；每次启动使用临时独立 profile。
- 桌面证据不含整屏截图；只保存页面截图与前台窗口/矩形证据，避免截入无关桌面内容。
- Playwright 使用项目外已存在的 Python 3.12.10 + playwright 1.60.0；未安装或修改环境。
- nodriver 使用 `C:\Users\19183\.dsh\tools\x-collect\venv\Scripts\python.exe`（nodriver 0.50.6）；与 Playwright 使用同一 Chrome 二进制、同一 fixture、同样 n=3 和临时独立 profile。
- nodriver 页面截图按浏览器窗口尺寸输出（本次 1920×1080），布局视口仍固定 1280×720；截图尺寸差异不影响 DOM 提取与滚动位移。

## 复现

```powershell
# 1) Playwright 3 次（已有数据可跳过）
C:\Users\19183\AppData\Local\Programs\Python\Python312\python.exe -m tools.selection.engine_trial --engine playwright --runs 3 --out docs/validation/v18/engine-trial --merge-existing --fixture docs/validation/v18/engine-trial/fixture.html
# 2) nodriver 3 次并合并到既有报告
C:\Users\19183\.dsh\tools\x-collect\venv\Scripts\python.exe -m tools.selection.engine_trial --engine nodriver --runs 3 --out docs/validation/v18/engine-trial --merge-existing --fixture docs/validation/v18/engine-trial/fixture.html
```

单测（不启动浏览器）：

```powershell
C:\Users\19183\AppData\Local\Programs\Python\Python312\python.exe -m unittest tests.test_v18_engine_trial -v
```

可选真实有头集成测试：

```powershell
$env:DSH_ENGINE_TRIAL_REAL = "1"
C:\Users\19183\AppData\Local\Programs\Python\Python312\python.exe -m unittest tests.test_v18_engine_trial.PlaywrightRealTests -v
```
