# D3：侧栏三项改名 + 无工作单时可点引导

## 1. 改名（全站统一）

| 之前 | 现在 |
| --- | --- |
| 选品（未变） | **选品** |
| 选源 | **找货源** |
| 起草介绍 | **写文案** |

同步位置：侧栏 `NAV`、顶部三步条 `STEPS`、页面标题（`/pick` `/source` `/copy`）、快捷按钮（**继续找货源** / **继续写文案**）、“从最近工作单继续”表格。
代码里已无 `选源` / `起草介绍` / `选品向导` 残留（`grep` 校验为 0）。

## 2. 点不开的根因与修复

**根因**：B21 为表达“必须先选品”，在无 `wo` 时把后两项渲染成 `<span aria-disabled>`，点击无任何反应。

**修复**：
1. `layout()`：三项**始终**渲染为 `<a>`；有 `wo` 时带 `?wo=`，无 `wo` 时指向 `/source`、`/copy`。
2. `/source`、`/copy` 缺 `wo` 时**不再 400**，改为 **200 引导页**（`views_wizard.render_need_wo`）：
   - 文案「还没有选中商品。请先选品，或从下面的最近工作单继续。」；
   - 两条 CTA：**① 去选品**（`/pick`）、**新建自制商品**（`/worksheet/new`）；
   - 「从最近工作单继续」表格（最近 10 条，含就绪 `n/7`、更新时间、**继续找货源** / **继续写文案** 按钮）；
   - **不自动选中、不自动建单**。
3. 有 `wo` 的行为完全不变（候选/自检/确定、文案表单/导出/发布回填）。

## 3. 测试（真实 exit）

| suite | 命令（cwd） | rc | summary |
| --- | --- | --- | --- |
| `tests.test_wizard` | `python -X utf8 -m unittest tests.test_wizard -v`（`tools/workbench`） | **0** | `Ran 66 tests — OK` |
| `workbench_all` | `… discover -s tests -t .` | **0** | `Ran 218 tests — OK` |
| `project_full` | `… discover -s tests`（仓库根，`APP_DB_PATH=%TEMP%\d3_full.db`） | **0** | `Ran 334 tests — OK`（52.2s） |

**按需求更新的断言（逐项给依据）**：
- `test_source_and_copy_require_wo`（400）→ **`test_source_and_copy_without_wo_show_guidance`（200 + 引导）**：依据验收 #2「无 wo 时点入 200 引导页」。
- 新增 `test_guidance_page_lists_recent_orders_with_buttons`：引导页列出最近工作单且含「继续找货源/继续写文案」（验收 #2）。
- `test_nav_disabled_without_wo` → **`test_nav_clickable_without_wo`**：断言无 `aria-disabled`、存在 `href="/source"` 与 `href="/copy"`（验收 #2「无 wo 时三项都是可点链接」）。
- 导航文本断言由 `["选品","选源","起草介绍"]` 改为 `["选品","找货源","写文案"]`；`继续选源/继续起草介绍` 计数改为 `继续找货源/继续写文案`（验收 #1）。
- 未删除任何测试、未放宽后端守卫（就绪/导出/CSRF/revision 语义未动）。

## 4. 截图（隔离库示例单 `wo:20261024-2c32ceac`，真实 JPEG）

| 文件 | 尺寸 | bytes | sha256 前 10 | 内容 |
| --- | --- | --- | --- | --- |
| `shots/nav_pick.jpg` | 1440×900 | 110,878 | `ad9a48ab03` | 侧栏三项「选品/找货源/写文案」，选品高亮 |
| `shots/nav_source.jpg` | 1440×900 | 75,201 | `4cd801b460` | 找货源页（带 wo） |
| `shots/nav_copy.jpg` | 1440×900 | 107,850 | `5f02886b9c` | 写文案页（带 wo） |
| `shots/guide_source_no_wo.jpg` | 1440×900 | 61,369 | `360249eec3` | **无 wo 引导页**（两条 CTA + 最近工作单表） |
| `shots/nav_mobile_menu.jpg` | 390×844 | 33,417 | `386f5cbcd2` | 手机展开菜单，同一三项 |

`shots_manifest.json` 记录尺寸/字节/sha256/`format=jpeg`/`openable=true`（SOI/EOI 校验）。

## 5. 部署与线上核对（同一 5015）

- 只停本工具父子进程后分离重启：**父 PID 106184 / 监听 PID 104620**。
- 线上实测：`NAV=选品,找货源,写文案`；**无旧名**（`NO_OLD=True`）；`ALL_LINKS=True`、`NO_DISABLED=True`（三项都是链接）；
  `/source` 无 wo **200** 且含「还没有选中商品」与「从最近工作单继续」；`/copy` 无 wo **200** 且含引导；`/source?wo=…` **200**；
  `/healthz` 含 `app_id=workbench-opportunity/1`。
- 守卫未变：`instance/app.db e073f828…`、`CONTRACT.md 826c24cc…`、`scores.csv ab0c3546…`、`sources.csv 13679b60…`。

## 6. 改动摘要（diff）

- `app.py`：`NAV` 三项改名；`layout()` 去掉禁用分支、三项恒为 `<a>`（有 wo 带参数）；`/source`、`/copy` 缺 wo 分支改为 200 引导页（`render_need_wo`），页面标题改为「找货源 / 写文案」。
- `views_wizard.py`：`STEPS` 改名；新增 `render_need_wo()`（两条 CTA + 最近 10 条表）；`继续选源/继续起草介绍` 文案改为 `继续找货源/继续写文案`。
- `tests/test_wizard.py`：见第 3 节（1 处改名断言、1 处 400→200、1 处禁用→可点、新增 1 例）。
- `d3/`：`REPORT.md`、截图与 manifest、`logs/`、`shot_nav3.py`、`fix_labels.py`。

## 7. 未覆盖 / 说明

1. 引导页的“最近 10 条”与 `/pick` 的“继续已有工作单”同源（同一 `_recent_workorders()`），两处列表一致；超过 10 条仍需从 `/worksheet` 取。
2. 无 wo 时侧栏链接指向裸 `/source`、`/copy`（不带参数）；进入后再选单，URL 会带上 `?wo=`，之后三项切换保留。
3. 本次只改导航与无 wo 分支；就绪判定、导出白名单、候选/文案/发布语义一字未改。
