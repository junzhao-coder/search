# 机会工作台 独立核验报告（非实现者）

> 核验者：执行者 C（`session-48004521-daf2-548c-a355-487cc6de6e72`），**非实现者**
> 任务：`task-738d5c453b87cc42dfecc732851c6b5e`（revision 4，计划 v6）
> 被测：`tools/workbench/{app.py,run.py,analysis.py,static/*,tests/*}`、`start_workbench.cmd`、`docs/validation/money-project/workbench-ui/`
> 观测时点：2026-10-22 UTC 13:00:49 → 13:0x（逐条见各节 UTC）
> 纪律：**未修改任何被测文件**；业务库只做文件 sha（未用 SQL 打开）；未读账号资料/Cookie；只在本机回环访问。

## 0. 结论速览

| 维度 | 结论 | 关键证据 |
| --- | --- | --- |
| readonly（只读性） | **符合**：不 import 业务 `app` 包、不调用业务 `create_app`、无 sqlite/DB 写入、无外部联网 | `app.py:19,21,38–48`；grep 无 `sqlite3/INSERT/UPDATE`；`run.py:34–42` 仅 localhost `/healthz` |
| tests（测试） | **通过**：工作台 **Ran 24 / OK / exit 0**；完整 **Ran 334 / OK / exit 0** | `01_workbench_tests.log`、`02_full_suite.log` |
| field-projection（字段投影） | **一致 4/4**（3 条要求 + 0.85 端点补充），页面文案可由 `scores.csv`+`profiles.json` 逐字复算 | `05_field_projection.json`、`03_candidates.json` |
| isolation（启动隔离） | **符合**：`instance/app.db` sha 前后不变、无 WAL/SHM；两场景端口行为正确；未动用户的 5015 | `07_port_cases.json`、`08_isolation.json` |
| 无数据断言扫描 | **未发现违规断言**：4 处 `成交/爆款` 命中均为免责声明或原始标题原文；5 页 `src` 外链 **0** | `06_claims_scan.json`、`09_claim_contexts.json` |
| 缺陷 | **本次未发现需上报的实现缺陷**（见 §7 差异与限制） | — |

## 1. readonly 只读性审查（源码静态 + 运行时）

- **不 import 业务 `app` 包**：`app.py` 导入仅 `html / importlib.util / pathlib / sys / urllib.parse`、`flask`（`Flask, Response, request`）与同目录 `analysis`（`app.py:19–21`）。全文无 `import app`、无 `from app …`；`app.py` 内**无** `sys.path` 操作。
- **按路径只读加载数据模块**：`_load_data_module()` 用 `importlib.util.spec_from_file_location("dash_data_readonly", ROOT/"app"/"dash"/"data.py")` 执行（`app.py:38–48`），模块名为独立别名；`app/dash/data.py` 仅 `csv/datetime/json/pathlib`，其 `SOURCES` 全部为工作区本地文件（`data.py:13–23`），无 DB、无网络。
- **不调用业务 `create_app`/`ensure_schema`**：本仓库业务包 `app/` 的 `create_app` 未被引用的唯一入口是路径加载的 `data.py`（纯函数）；工作台自身的 `create_app`（`app.py:691`）只是 Flask 工厂。
- **无 DB 写入**：`tools/workbench` 全目录 grep **无** `sqlite3`、无 `INSERT/UPDATE/DELETE/commit(`、无 `instance/app.db` 打开；唯一出现 `instance/app.db` 的位置是单测 `test_workbench.py:221–226` 的 **sha 前后比对**。
- **无联网采集**：`app.py` 中 `urllib` 仅 `urllib.parse`（`app.py:17`，用于拼查询串）；`run.py:34–42` 的 `urllib.request` **只**请求 `http://127.0.0.1:<port>/healthz` 判定"本应用是否已在运行"，不访问外网。静态资源：`static/app.css`、`static/app.js`、`app.py` 中 `http://`/`https://` 命中 **0**（无 CDN）。
- **业务库只读**：核验全程仅 `Get-FileHash instance/app.db`，未执行任何 SQL。

## 2. tests 独立复跑（真实 exit）

| 套件 | 命令（cwd=`D:\桌面\two`，UTC 2026-10-22T13:00:49Z） | 结果 | exit |
| --- | --- | --- | --- |
| 工作台单测 | `.venv\Scripts\python.exe -X utf8 -m unittest discover -s tools/workbench/tests -t tools/workbench -v` | `Ran 24 tests in 0.230s` / `OK` | **0** |
| 完整套件 | `.venv\Scripts\python.exe -X utf8 -m unittest discover -s tests -t .` | `Ran 334 tests in 49.603s` / `OK` | **0** |

- 原始日志（UTF-8 无 BOM/LF）：[01_workbench_tests.log](<01_workbench_tests.log>)、[02_full_suite.log](<02_full_suite.log>)。
- 计数口径说明：旧任务文本写"工作台 11 OK"，本轮实际 discover 为 **24** 个用例（实现者已扩充；以实际 `Ran 24` 为准），完整套件 **334** 与派发事实一致。
- 复跑后：`instance/app.db` sha 不变、无 WAL/SHM（见 §5）。

## 3. field-projection 字段投影抽检（逐字比对）

方法：实际读 `scoring/scores.csv`（60 行）与 `product-analysis/profiles.json`（60 行，`source_sha256=ab0c3546…`），用与页面同一纯函数 `analysis.build_analysis(row, price_stats)` **复算**文案；再对运行中的实例发真实 HTTP `GET /opportunities?q=<item_id>`，把复算文案与页面 HTML（`html.escape` 后）**逐字**比对；同时校验该条 `profiles.json` 行与之完全一致。

| # | 抽样定位 | item_id | CSV：score / 需求分位 / 可售性 | 页面复原（chip） | 页面逐字命中 | 判定 |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | **已判品类：求职简历资料** | `x:1747215882965979516` | `0.728621` / `89.6552%→90%` / `0.5`（理由"无价格/购买入口/赠送信号，按中性"） | `不明确 50` | 定位/理由×3/风险×2/理由原文/品类名 全部命中 | **PASS** |
| 2 | **未分类 + 需求分位 100%** | `x:1467843989533442054` | `0.755` / `100%` / `0.5` | `不明确 50` | 同上；文案为"无价格信号（可售性 50（未达可售））的高需求线索（需求分位 100%），品类待确认…" | **PASS** |
| 3 | **未分类 + 低可售性** | `bili:BV1qWVRzaEVY` | `0.556987` / `84%` / `0.1`（理由"含 free/赠送/领取/求推荐等低可售词"） | `低信号 10` | 同上；风险首条为"可售性仅 10（低信号）：含 free/…" | **PASS** |
| 4 | 端点补充：**可售性 0.85** | `x:1824402140070285653` | `—/—/0.85` | `较强售卖 85` | chip 与理由原文命中 | **PASS** |

- 逐条布尔断言（含 `positioning_on_page`、`why_*`、`risks_*`、`sell_chip_on_page`、`sell_reason_on_page`、`unclassified_not_named_category`）见 [05_field_projection.json](<05_field_projection.json>)；抽样行原始数据见 [03_candidates.json](<03_candidates.json>)。
- **画像与 CSV 同源校验**：`profiles.json.source_sha256` = `scores.csv` 实际 sha256 = `ab0c3546c3e9e46ffe726aa036aecce7e535c38fd54f3423c4e4b4bb03967cd1`（`match=true`，`generated_utc=2026-10-22T12:55:44Z`，`rules_version=analysis.py@rev2-intent-first`，行数 60）—— 说明页面所用 CSV、画像文件、生成规则三者同源，见 [10_data_sync.json](<10_data_sync.json>)。
- **未分类未被写成已知品类**：`q=` 过滤后页面只含该条，检查确认 chip 为 `未分类`、且行内不出现"求职简历资料/设计素材/教学内容/提示词或数字包/学习或生活规划模板"任一品类名（4/4 通过）。
- 可售性展示口径与源码一致：`sellability()` 只读 `sellability_norm`，展示 `round(100×norm)`，理由取 `sellability_reason` 原文（`app.py:107–120`）；阈值 `≥0.8 较强售卖 / ≤0.2 低信号 / 其余不明确 / 缺失未评估`（`analysis.py:104–106`）。

## 4. 无数据断言扫描（页面文案）

- 5 个页面（`/`、`/opportunities`、`/sources`、`/collect`、`/daily`）全文扫描 `稳赚/包赚/躺赚/保证/已验证需求/成交/成交量/订单数/绝对/爆款/无风险`：
  - `成交` 共 3 处 + `爆款` 1 处，**全部为免责声明或原始标题原文**：
    - `/`："想要数不是销量，划线价不是成交价。"
    - `/opportunities`："毛利为低置信估算（模型假设，非成交数据）…"
    - `/collect`："已登录采集的只读样本…"想要/点赞"不代表成交。"
    - `/collect`：`爆款` 出现在**采集到的原始标题**"爆款场景AI女装指令💥新手也能出赞藏99+ …"中（数据原文，非平台断言）。
  - `稳赚/包赚/躺赚/保证/已验证需求/成交量/订单数/绝对/无风险`：**0 命中**。
- 外链性质：5 页 `src="https://…"` **均为 0**；`href` 外链 60/14/40 条为**原始机会/许可/商品链接**（证据跳转，非加载资源）。
- 证据：[06_claims_scan.json](<06_claims_scan.json>)、[09_claim_contexts.json](<09_claim_contexts.json>)（含逐条上下文；后者在用户 5015 实例上只读 GET 复核，结论一致）。

## 5. isolation 启动隔离

### 5.1 独立起服务（避开 5015，用 5017）

- 命令：`.venv\Scripts\python.exe -X utf8 tools\workbench\run.py --port 5017 --no-browser`（`PYTHONDONTWRITEBYTECODE=1`）
- `/healthz` 实测：`{"status":"ok","counts":{"scores":60,"sources":14,"prices":20,"xianyu":20,"xiaohongshu":20,"join":10,"topic_summary":45,"topic_top20":25},"generated_at":"2026-10-22T11:21:59Z","root":"D:\\桌面\\two"}`
- 服务日志：[04_server_5017.log](<04_server_5017.log>)

### 5.2 业务库与端口

| 检查 | 前 | 后 | 结论 |
| --- | --- | --- | --- |
| `instance/app.db` sha256 | `e073f828cf0f30d6206361bba3a729826be096be3308f5a5dc204406dae4eb85` | 同值 | **未变** |
| `instance/app.db-wal` / `-shm` | 不存在 | 不存在 | **未产生** |
| 我起的 5017 | 监听中（pid 124944） | 已停止（命令含 `tools\workbench\run.py --port 5017` 才动手） | **已释放** |
| 用户的 5015 | 监听 pid 118500（父 130188） | 同 pid 118500（父 130188） | **未触碰** |

证据：[08_isolation.json](<08_isolation.json>)。

### 5.3 端口两场景（各一次）

| 场景 | 命令 | 观察输出 | exit |
| --- | --- | --- | --- |
| A 本应用已占用 5017 | `run.py --port 5017 --no-browser` | "本地机会工作台已在运行：地址 http://127.0.0.1:5017/" | **0** |
| B 用户应用占用 5015 | `run.py --port 5015 --no-browser` | 同样识别为工作台并提示已在运行；5015 的 pid 前后均为 118500 | **0** |
| C 外部程序占用 5018（我起的临时 listener） | `run.py --port 5018 --no-browser` | "[错误] 端口 5018 已被占用。请换一个端口…本程序不会结束其它进程。" | **3** |

临时 listener 用后即停（`5018 listening=False`）；证据：[07_port_cases.json](<07_port_cases.json>)。

### 5.4 环境事实（非缺陷）

`.venv\Scripts\python.exe` 在本机表现为**转发型启动器**：真正监听的是其子进程（dsh-runtime 的 `python.exe`）。因此同一服务会同时看到两个 PID（如 5015 的 130188 → 118500）。这只影响"如何定位进程"，不影响行为结论。

## 6. 与实现者自述的对照

| 实现者/派发自述 | 本次独立观察 | 是否一致 |
| --- | --- | --- |
| 完整 334 OK exit=0 | `Ran 334 tests … OK`，exit 0 | **一致** |
| 工作台 11 OK（旧文本） | 实际 `Ran 24 tests … OK`，exit 0 | **数量不同**（用例已扩充；以 24 为准） |
| `run.py` 绑 127.0.0.1:5015、本应用占用走 `/healthz`、外部占用 exit=3 | 三场景逐一复现（5017→0、5015→0、外部占用→3） | **一致** |
| `app.py` 用 importlib 按路径加载 `app/dash/data.py`，不 import `app` 包 | 源码与运行时均成立 | **一致** |
| 可售性只读 `sellability_norm`（0.8/0.2），理由取 `sellability_reason` | 4 条抽样逐字一致（含 0.1 与 0.85 两端） | **一致** |

## 7. 差异、缺陷与限制

**未发现需上报的实现缺陷**。以下为需要如实记录的观察与边界：

1. **测试数量口径**：旧任务文本的"11 OK"已过时，当前工作台套件为 **24**；若文档仍写 11，属文档待同步（仅记录，不改）。
2. **我这次复跑刷新了字节码**：`tools/workbench/__pycache__/` 与 `tools/workbench/tests/__pycache__/` 下的 `.pyc`（mtime 2026-10-22T13:00:49Z）由本次 unittest 运行产生/刷新；**被测 `.py` 源文件 mtime 未变**（12:36–12:57）。建议后续核验统一设 `PYTHONDONTWRITEBYTECODE=1`（`start_workbench.cmd` 已设）。
3. **`/collect` 的"爆款"是数据原文**：来自已采集的小红书标题，不是平台对机会的断言；如后续做文案审计，应区分"数据原文"与"平台结论"。
4. **未覆盖**：其它浏览器（只用系统默认/无头访问 HTTP，不验证前端 JS 交互）；并发/负载；跨机器；`start_workbench.cmd` 的双击路径（只审阅其内容：`PYTHONUTF8=1`、`PYTHONDONTWRITEBYTECODE=1`、`.venv` 优先、失败提示换端口）。
5. **数据正确性不在本核验范围**：只核"页面 ↔ CSV/画像"的投影一致性，不评价 `scoring`/`sellability` 上游打分是否合理。
6. 全程只读回环；未登录、未读 Cookie/账号资料；未修改 `tools/workbench`、`start_workbench.cmd`、`app/dash`、`scoring`、`tests`。

## 8. 产物清单（本目录）

| 文件 | 说明 |
| --- | --- |
| `01_workbench_tests.log` / `02_full_suite.log` | 两套测试原始输出（含 `Ran`/`OK`） |
| `03_candidates.json` | 抽样行定位与 CSV/画像原文 |
| `04_server_5017.log` | 独立起服务日志 |
| `05_field_projection.json` | 4 条逐字比对与布尔断言 |
| `06_claims_scan.json` / `09_claim_contexts.json` | 无数据断言扫描与上下文 |
| `07_port_cases.json` | 三场景端口行为与 exit |
| `08_isolation.json` | DB sha 前后、WAL/SHM、端口归属 |
