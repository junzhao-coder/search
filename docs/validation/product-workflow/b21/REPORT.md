# B21：侧栏收敛为「选品 / 选源 / 起草介绍」三项

> 这是**菜单收敛**，不是新增自动找货源功能；选品统计、分类/筛选、货源变更失效、文案/导出语义均未改。

## 1. 导航与入口

| 项 | 之前 | 现在 |
| --- | --- | --- |
| 主侧栏 | 8 项（选品向导/总览/机会线索/教程与内容/商品工作单/货源与价格/采集来源/每日快照） | **3 项：选品 `/pick`、选源 `/source`、起草介绍 `/copy`** |
| 根入口 `/` | 渲染「总览」 | **302 → `/pick`** |
| 顶部三步条 / 页面标题 | ① 选品 / ② 找货源 / ③ 写介绍 | **选品 / 选源 / 起草介绍**（与侧栏同名） |
| 旧页面 | 侧栏入口 | 侧栏不再出现；URL 与后端路由**全部保留可用**（`/opportunities`、`/content`、`/sources`、`/collect`、`/daily`、`/worksheet*`） |

- 侧栏高亮：当前步 `aria-current="page"`；移动端复用**同一个** `nav[aria-label="主导航"]`（`aria-controls="sidebar"` 的按钮切换），不产生第二个导航。
- 品牌与数据快照保留在侧栏底部，不占主导航。

## 2. 工作单上下文（不新增状态引擎）

- `layout()` 通过 `_current_wo()` 取 `request.view_args["workorder_id"]` 或 `?wo=` / 表单 `wo`：
  - 有 wo：三项链接都带 `?wo=<id>`，切换步骤不丢当前单；
  - 无 wo：`选源`/`起草介绍` 以 `<span class="nav-label nav-disabled" aria-disabled="true" title="请先选品">` 呈现，**不自动挑生产旧单、不自动建单**；直接访问 `/source`、`/copy` 仍返回 **400** 并提示先选品。
- 未改动：`source/confirm` 守卫、CSRF + revision、导出与就绪限制、候选/文案/发布数据。

## 3. 测试（真实 subprocess，`execution_manifest.json`）

| suite | argv（cwd） | rc | summary |
| --- | --- | --- | --- |
| `b21_wizard_nav` | `python -X utf8 -m unittest tests.test_wizard -v`（`tools/workbench`） | **0** | `Ran 38 tests — OK` |
| `workbench_all` | `… discover -s tests -t . -v`（`tools/workbench`） | **0** | `Ran 188 tests — OK` |
| `project_full` | `… discover -s tests -v`（仓库根，`APP_DB_PATH=%TEMP%\b21_full.db`） | **0** | `Ran 334 tests — OK`（47.2s） |

新增 `NavTests`（6 例）：主导航**恰好 3 项且文本精确**、旧 8 个标签不出现、根入口 302→`/pick`、带 wo 时三项链接均含 `?wo=`、无 wo 时禁用并提示、`aria-current` 与移动端单一导航、旧页面仍 200 且导航无旧入口。

**按需求更新的既有断言（逐项说明）**
- `test_pick_renders_with_wizard_bar`：原断言 ①②③ 文案 → 改为「选品/选源/起草介绍」，**需求 #2（同一组名称）**。
- `test_old_routes_still_work` / `test_real_root_pages_and_healthz` / `test_get_does_not_create_db_file` / `test_no_business_db_write`：原断言 `/` 为 200 → 改为 **302 且 Location=`/pick`**（或改为直接探测 `/pick`），**需求 #4（默认入口落选品）**；未删除任何测试、未放宽任何后端守卫。

## 4. 截图（隔离库示例单 `wo:20261024-1defa51d`，真实 JPEG）

| 文件 | 尺寸 | bytes | sha256 前 10 | 说明 |
| --- | --- | --- | --- | --- |
| `shots/nav_pick_desktop.jpg` | 1440×900 | 118,576 | `5891c30bc6` | 侧栏仅 3 项，选品高亮 |
| `shots/nav_source_desktop.jpg` | 1440×900 | 80,662 | `11754ce94e` | 选源高亮，链接带 wo |
| `shots/nav_copy_desktop.jpg` | 1440×900 | 90,831 | `addb0f6388` | 起草介绍高亮 |
| `shots/nav_mobile_menu.jpg` | 390×844 | 49,550 | `c9f71a2057` | 手机展开菜单（`aria-expanded=true`），可见同一 3 项 |

`shots_manifest.json` 记录尺寸/字节/sha256/`format=jpeg`/`openable=true`（JPEG SOI/EOI 校验，脚本内未装 Pillow）。

## 5. 部署与存活（同一 5015）

- 只停**本工具**父/子进程（`tools\workbench\run.py --port 5015` 命令行匹配，共 2 个），分离重启：父 **PID 91928**（`.venv\Scripts\python.exe`）、监听 **PID 120664**（其子进程）；日志 `tools\workbench\runtime\workbench-5015{,.err}.log`。
- 线上核对：`/healthz` **200** + `app_id=workbench-opportunity/1`；`/` → **302 `…/pick`**；`/pick`、`/source?wo=…`、`/copy?wo=…`、`/worksheet` 均 **200**；无 wo 的 `/source`、`/copy` → **400**；侧栏 `NAV_LABELS=选品,选源,起草介绍`、`HAS_WO_LINKS=True`、`HAS_OLD=False`。
- 停止：按上述命令行匹配 `Stop-Process`（或停 120664、91928）；重启：重复分离启动命令。
- 守卫未变：`instance/app.db e073f828…`、`CONTRACT.md 826c24cc…`、`scores.csv ab0c3546…`、`sources.csv 13679b60…`；未改冻结文件/DSH；未登录/采购/发布。

## 6. 改动摘要（diff）

- `app.py`：`NAV` 由 8 项改为 3 项；`layout()` 重写导航渲染（携带 wo、无 wo 禁用、`aria-current`）；新增 `_current_wo()`；根路由 `index()` 改为 `redirect("/pick", 302)`；向导页标题改为「选品 / 选源 / 起草介绍」。
- `views_wizard.py`：`STEPS` 标签改为「选品 / 选源 / 起草介绍」（顶部三步条与页面标题同名）。
- `tests/test_wizard.py`：新增 `NavTests`（6 例）；更新 2 处文案/根入口断言。
- `tests/test_workbench.py`、`tests/test_workflow.py`：根入口断言改为 302→`/pick`（或在只读用例改探测 `/pick`）。

## 7. 未覆盖项

1. 旧页面（总览、机会线索、教程与内容、商品工作单、货源与价格、采集来源、每日快照）**仍可从 URL 直接访问**，只是不进主导航——这是“保留兼容、不删数据/路由”的要求；若你希望彻底下线，需要单独确认（会破坏既有接口/测试）。
2. 侧栏没有“更多/高级”折叠入口；所有次要信息（数据快照、计数）只在侧栏底部与页面内容里。
3. 无 wo 时侧栏的「选源/起草介绍」是禁用态而非可点空态页（页面本身 400 有引导）；如果你更希望“可点但显示引导”，我可以改，但那会多一次点击。
4. 本次未改选品算法、货源失效传导、文案版本与导出语义；截图用隔离库测试单，非生产数据。
