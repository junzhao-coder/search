# /dash 只读 Dashboard 交付报告

> 任务：`task-9dfcba2e896a1a024eabd26f77781b3e`（计划 v6 B4）。范围：`app/dash`、`templates/dash`、`tests/dash`、`docs/validation/money-project/ui`。
> 结论：新增 5 个只读页面（总览 + 四工作页），数据全部来自现有 CSV/JSONL 产物；完整测试 **334/334 通过，exit=0**；业务库与 CONTRACT 未变。

## 1. 路由

| 路径 | 状态 | 说明 |
| --- | --- | --- |
| `/dash` | 302 → `/dash/` | 便捷跳转 |
| `/dash/` | 200 | 总览：计数、机会 Top5、许可概览、联动 Top3 |
| `/dash/collect` | 200 | 采集产物状态、闲鱼/小红书各前 12 条、topic-crawler Top20 |
| `/dash/opportunities` | 200 | 60 条评分全表，搜索 + 表头排序 |
| `/dash/sources` | 200 | 14 条货源、20 条价格信号、10 条联动 |
| `/dash/daily` | 200 | 只读每日摘要（Top5 + 联动提示 + 数据完整性） |

- 蓝图 `app/dash/`：`__init__.py`（Blueprint + 模板目录）、`routes.py`、`data.py`；在 `create_app` 注册。
- 页面使用 `templates/dash/` 的独立 `base.html`，不重构旧模板；CSS 复用 `app/static/style.css`，仅内联 Dashboard 小样式。
- 每个页面顶部显示**数据来源**与**文件更新时间（UTC）**；缺失文件显示 `文件缺失/暂无数据`。

## 2. 数据读取（只读）

`app/dash/data.py` 仅用标准库 `csv/json/pathlib`，无数据库连接、无写入：

- scoring：`scores.csv`（60×35）、`report.md`
- sourcing：`sources.csv`（14）、`price_signals.csv`（20）、`opportunity_sourcing_top10.csv`（10）
- 采集：`tools/platform-login/data/{xianyu_items,xiaohongshu_items}.jsonl`（各 20；兼容 `login/data/` 路径）
- topic-crawler：`top20.md`、`filtered/summary.csv`
- 缺失/坏 JSONL 不抛 500：返回空列表、`bad_lines` 计数与页面提示。
- 更新时间为文件 mtime（UTC），不是伪造的生成时间；没有文件时为“暂无数据”。

## 3. 测试

命令（项目根目录）：

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

- 真实 exit：**0**
- 结果：`Ran 334 tests in 48.651s` → **OK**（原 325 + 新增 9）
- 新增 `tests/dash/test_routes.py`：5 路由 200/HTML、关键字段、缺文件友好降级、坏 JSONL 计数、API health 不变。
- **一处既有测试调整**：`tests/api/test_daily_endpoint.py` 的“非 API/静态路由恰好 4 条”旧断言，现排除 `/dash` 命名空间后仍断言旧四页=4；这是新增 `/dash` 路由的必然调整，旧页面与 API 未改。
- 证据：`test.log`（UTF-8，含命令、334 tests、exit=0）。

## 4. 截图（无头 Chrome，1440×1400）

本地 Flask 使用 `serve_dash.py`，端口 **5010**（避开 5000），`db_path` 为 `ui/tmp/server.db` 临时库；截图后服务与 Chrome 均已停止。

| 页面 | 截图 |
| --- | --- |
| 总览 | [overview.png](shots/overview.png) |
| 采集 | [collect.png](shots/collect.png) |
| 机会 | [opportunities.png](shots/opportunities.png) |
| 货源 | [sources.png](shots/sources.png) |
| 每日摘要 | [daily.png](shots/daily.png) |

截图清单/哈希：`routes.json`。

## 5. 变更摘要

- 新增 `app/dash/{__init__,data,routes}.py`。
- 新增 `templates/dash/{base,index,collect,opportunities,sources,daily}.html`。
- 新增 `tests/dash/{__init__,test_routes}.py`。
- `app/__init__.py`：注册 dash 蓝图 + `DASH_DATA_ROOT` 测试覆盖配置。
- `tests/api/test_daily_endpoint.py`：旧“4 页”断言排除 `/dash`。
- 未改任何 `/api/*` 响应结构、迁移、业务库、CONTRACT、x-collect/platform-login 脚本。
- `diff.patch`：统一 diff（新文件 + 两处修改）。

## 6. 哈希/边界

`hash_check.json`：

- 业务库 `instance/app.db` = `e073f828…`（same）；wal/shm=false。
- CONTRACT `826c24cc…`、requirements、冻结三、real_link 均 same。
- 新增 Dashboard 仅读文件；测试使用临时 DB；截图服务使用 `ui/tmp/server.db`。

## 7. 限制

1. **静态只读**：页面每次请求重新读文件，无缓存/自动刷新/定时任务；数据更新需刷新页面。
2. **无鉴权**：沿用本地单用户假设；不暴露写操作，但任何本机访问者可查看。
3. **前端排序/搜索**：客户端 JS；无服务端分页；机会页一次渲染 60 行，采集页只展示前 12 条。
4. **daily 页非业务摘要接口**：只做静态产物聚合，未调用 `daily_digest`/业务库，避免写库与数据源混淆；业务摘要仍以现有 API 为准。
5. **样式简单**：复用既有极简 CSS；截图在 1440×1400 下验证，未做移动端逐页回归。
6. **旧测试调整**：为允许 `/dash` 新命名空间，修改了 1 条旧路由计数断言（见 §3），不是放宽功能测试。
