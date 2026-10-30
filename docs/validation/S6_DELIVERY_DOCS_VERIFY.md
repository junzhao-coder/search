# S6 交付文档 · 独立核验（README / .gitignore / discover / 守护）

> 核验对象：仓库根 [README.md](<../../README.md>)（**95 行**，5734 bytes，sha256 `6cf5b683f8a857a21d44a011f62b81817c53b2e99a596054852635c84ff7bc7d`）与 [.gitignore](<../../.gitignore>)（**53 行**，1373 bytes，sha256 `15fb62dad3e2d36c5a48c621906e4b27f4ee81d44b25d272ae624b8be8c3a3ac`，与 B 自述 `15FB62DA…` 一致）。
> 核验者：独立执行者 A（作者为 B），任务 `task-5f4ce314ac2964c02f07d8c47ee45d43`；核验时点 2026-10-20 14:48–14:55 +08:00。
> 性质：**独立只读核验 + 隔离探针**。未修改 README/.gitignore/`app/**`/`tests/**`/契约/迁移/台账/业务库；**未联网、未启动服务**；git 探针在 `<run>/probe/` 的一次性仓库内执行，未在仓库根建 `.git`。
> 结论：**需修订（仅 README 文字层面；.gitignore 语义、测试与守护全部通过）**。阻断级问题 0；需修正的文档表述 4 项（F-01…F-04），另有 2 项记录/建议。**不宣称 S6 完成**。

## 0. 运行目录与证据

- 唯一 run：`tests/acceptance/_tmp/s6_docs_verify_v1/run_20261020_144858_docsverify/`
- 探针目录：`<run>/probe/`（一次性 git 仓库骨架，含复制来的 `.gitignore` 与 14 个骨架文件；保留为证据，见 §6）
- 证据：[01_readme_check.json](<../../tests/acceptance/_tmp/s6_docs_verify_v1/run_20261020_144858_docsverify/evidence/01_readme_check.json>)、[03_git_probe.json](<../../tests/acceptance/_tmp/s6_docs_verify_v1/run_20261020_144858_docsverify/evidence/03_git_probe.json>)、[04_mirror.json](<../../tests/acceptance/_tmp/s6_docs_verify_v1/run_20261020_144858_docsverify/evidence/04_mirror.json>)、[05_discover_cmd.log](<../../tests/acceptance/_tmp/s6_docs_verify_v1/run_20261020_144858_docsverify/evidence/05_discover_cmd.log>)、[08_facts.json](<../../tests/acceptance/_tmp/s6_docs_verify_v1/run_20261020_144858_docsverify/evidence/08_facts.json>)、[09_evidence_check_cmd.log](<../../tests/acceptance/_tmp/s6_docs_verify_v1/run_20261020_144858_docsverify/evidence/09_evidence_check_cmd.log>)

## 1. README 事实逐条核对（对照代码/文件）

| README 主张（行号） | 核对结果 | 依据 |
| --- | --- | --- |
| L8 Python 3.12.14；L9 `flask==3.1.3`、sqlite3 3.53.1 | **准确**（venv 只读查询：3.12.14 / 3.1.3 / 3.53.1；`requirements.txt` 仅该 pin） | venv 查询；`requirements.txt:3` |
| L18–L29 6 个 `APP_*` 变量与默认值；无 `SECRET_KEY` | **变量名与存在性准确**（config.py 恰 6 个 `os.environ.get`）；默认值：HOST `127.0.0.1`、PORT `5000`、TZ `8`、MAX_BODY_BYTES `5*1024*1024`、MAX_ROWS `5000`、DB_PATH `ROOT/instance/app.db`；**README 对 MAX_BODY_BYTES/MAX_ROWS 只写"见 config.py"未列字面值**（F-03） | `app/core/config.py:11-24` |
| L29 "不存在 SECRET_KEY；无登录/鉴权" | **准确**（config 无 SECRET_KEY；`app/` 无鉴权/会话端点） | `config.py`；routes 无 auth |
| L33–L46 启动 `python -m app`、默认 `127.0.0.1:5000`、threaded=True、无 reloader；health 返回 `ok/schema_version/time`；停止用 `Get-NetTCPConnection`/`Stop-Process` | **入口与字段准确**：`app/__main__.py` 存在（22 行，`host/port` 来自 cfg、`debug=False`、`use_reloader=False`、`threaded=True`）；health 实际字段 `{ok,schema_version,time}`（`routes.py:123-131`）。**停止命令未实际执行**（未启动服务，属未覆盖） | `app/__main__.py:9-18`；`routes.py:123-131` |
| L50–L56 测试命令与"当前基线 253 项" | **准确**：隔离镜像内 `-X utf8 -m unittest discover -s tests -t .` → **Ran 253 tests, OK, exit=0**（44.299s） | [05_discover_cmd.log](<../../tests/acceptance/_tmp/s6_docs_verify_v1/run_20261020_144858_docsverify/evidence/05_discover_cmd.log>) |
| L60–L64 业务库只由应用写、备份/恢复演练在隔离副本、冻结快照只读、`.gitignore` 否定例外与"92 个 `.db`"、顶层显式清单 6 项、不用递归模式 | **准确**：快照实际 **92 个 `.db`** + 2 个 `*.manifest.sha256`；`.gitignore` 恰 6 项顶层 `tests/*/_tmp/`；否定例外在排除规则之后；git 语义见 §2 | `tests/acceptance/_snapshots`；`.gitignore:26-53`；[08_facts.json](<../../tests/acceptance/_tmp/s6_docs_verify_v1/run_20261020_144858_docsverify/evidence/08_facts.json>)（事实文件） |
| L68–L75 能力现状：导入/门槛/状态、S4 情景、S4-B1 匹配、S4-B3 排序、S5 摘要"已实现并验收（纯函数）"；读路径未接入（提案文件存在）；S3 真实链路未接通；**"每日定时触发、提醒、界面 未实现"** | **大部分准确**：核心文件均在（`matching/ranking/daily/scenario`）、routes 无匹配/排序/摘要引用、提案文件存在、S3 边界一致；**但"界面 未实现"与代码不符**——现有 4 条页面路由（`/`、`/opportunity/<id>`、`/import`、`/ops`）+ 6 个模板 + 2 个静态文件（S2 最小界面）（F-01）；"已实现并验收"中 S4 情景未在 `docs/validation/` 找到独立验收报告（F-04） | `app/api/routes.py`（`@pages` ×4）；`app/templates/*`；`app/static/*`；`docs/validation/` 列表 |
| L79 "现有 23 条路由中无该端点" | **不完整**：routes.py 实为 **27 条** HTTP 路由（23 条 `@bp` API + 4 条 `@pages` 页面）；"无 backup/maintenance 端点"本身准确（F-02） | `routes.py` 统计；[08_facts.json](<../../tests/acceptance/_tmp/s6_docs_verify_v1/run_20261020_144858_docsverify/evidence/08_facts.json>) |
| L80–L84 已知差距 1–6 | **与代码一致**：无 maintenance/backup 端点；health 无版本字段；`db.ensure_schema` 无"高版本拒绝启动"；读路径未接；ranking `PENDING_CONFIRMATION=True`、`rank-v1`、`budget_note` 存在；仓库根无 `.git`；S6 设计稿存在 | `routes.py`；`db.py:38-64`；`ranking.py`；`.git` 不存在 |
| L86–L95 目录速览 | **准确**（app/tests/docs/instance/requirements 均存在；`instance/` 被 `.gitignore` 忽略） | 目录检查；git probe |

- **README 行数**：实测 **95 行**（任务上下文称"实读 94 行"——以实测为准；评审前后 hash 未变，见 §4）。
- README 事实核对工具独立写就（17 项断言）：修正我方一次断言口径后 **17/17 PASS**（[01_readme_check.json](<../../tests/acceptance/_tmp/s6_docs_verify_v1/run_20261020_144858_docsverify/evidence/01_readme_check.json>)）。

## 2. .gitignore 的独立 git 语义复验（不复用 B 的 probe）

- 探针：`<run>/probe/` 新建骨架（app/main.py、docs/a.md、README.md、tests/fixtures/x.json、快照内嵌套 `tests/api/_tmp/a/app.db`、快照顶层 `app.db` 与 `manifest.sha256`、`tests/{api,core,storage}/_tmp/*.db`、`tests/acceptance/_tmp/z/app.db`、`instance/app.db`、`.venv/pyvenv.cfg`、`__pycache__/q.pyc`），复制 live `.gitignore`，`git init` 后执行 **git 2.54.0.windows.1** 的 `check-ignore`（非 `-v` 退出码判定忽略性，`-v` 仅作规则诊断）、`status --short -uall`、`add -n .`、`ls-files --others [--ignored] --exclude-standard`。
- 结果（**21/21 断言 PASS**，[03_git_probe.json](<../../tests/acceptance/_tmp/s6_docs_verify_v1/run_20261020_144858_docsverify/evidence/03_git_probe.json>)）：
  - **不被忽略**（`check-ignore` exit=1）：`README.md`、`app/main.py`、`docs/a.md`、`tests/fixtures/x.json`、`tests/acceptance/_snapshots/s2d_x/app.db`、`.../manifest.sha256`、**`.../snapshots/s2d_x/tests/api/_tmp/a/app.db`（快照内嵌套 `tests/*/_tmp/` 的 .db）**。
  - **被忽略**（exit=0，规则命中）：`tests/api/_tmp/x/app.db`、`tests/core/_tmp/c/app.db`、`tests/storage/_tmp/y/app.db`、`tests/acceptance/_tmp/z/app.db`、`instance/app.db`、`.venv/pyvenv.cfg`、`__pycache__/q.pyc`。
  - `git add -n .` 会加入快照内嵌套 .db、不加入任何被忽略路径；`git status --short -uall` 显示可见文件、隐藏被忽略项；`ls-files --others --ignored` 含 `instance/app.db` 与 `tests/*/_tmp`、**不含**快照内 .db。
- 结论：**.gitignore 的否定例外与"顶层显式清单 + 不递归"设计在真实 git 语义下成立，不误伤冻结快照与 fixtures**；B 自述的 5 条断言被本 probe 的 21 条断言超集复现。

## 3. 完整 discover（隔离镜像）

- 镜像：复制 live `app/**`+`tests/**`+`requirements.txt` 到 `<run>/mirror/`（排除 `__pycache__`/`_tmp`/`_snapshots`/`.venv` 与 reparse；**75 件**、逐件 parity `mismatched=0/extra=0`）→ [04_mirror.json](<../../tests/acceptance/_tmp/s6_docs_verify_v1/run_20261020_144858_docsverify/evidence/04_mirror.json>)、[04_mirror_cmd.log](<../../tests/acceptance/_tmp/s6_docs_verify_v1/run_20261020_144858_docsverify/evidence/04_mirror_cmd.log>)（**exit=0**）。
- 命令（`cwd=<run>/mirror`、`PYTHONPATH=<run>/mirror`、`PYTHONDONTWRITEBYTECODE=1`、venv python 3.12.14）：`-X utf8 -m unittest discover -s tests -t .` → **Ran 253 tests, OK，真实 exit=0（44.299s）**，与 README 基线 **253 一致**。

## 4. 前后哈希与业务库守护

| 项 | 结果 |
| --- | --- |
| README / .gitignore sha256（核验前后） | `6cf5b683…bc7d` / `15fb62dad3e2…a3ac`，**未变** |
| live 树前后清单（README+.gitignore+`app/**`+`tests/**`，排除 `_tmp`/`__pycache__`） | **188 文件、1,951,989 bytes、digest `2c61ea8a…1d3` 三次一致**（before / after / final）→ [02_fs_before.json](<../../tests/acceptance/_tmp/s6_docs_verify_v1/run_20261020_144858_docsverify/evidence/02_fs_before.json>)、[06_fs_after.json](<../../tests/acceptance/_tmp/s6_docs_verify_v1/run_20261020_144858_docsverify/evidence/06_fs_after.json>)、[10_fs_final.json](<../../tests/acceptance/_tmp/s6_docs_verify_v1/run_20261020_144858_docsverify/evidence/10_fs_final.json>) |
| 业务库 `instance/app.db` | `e073f828cf0f30d6206361bba3a729826be096be3308f5a5dc204406dae4eb85`，前后一致；`-wal`/`-shm` 均不存在 |
| 仓库根 `.git` | 不存在（git 探针只在 `<run>/probe/` 内 `git init`，未改仓库根） |
| 证据文本 | 17 件 UTF-8 无 BOM/LF、读回 **exit=0**（[09_evidence_check_cmd.log](<../../tests/acceptance/_tmp/s6_docs_verify_v1/run_20261020_144858_docsverify/evidence/09_evidence_check_cmd.log>)） |

## 5. 发现的问题（均仅 README 文字层面）

| 编号 | 严重度 | 问题 | 位置 | 最小修订 |
| --- | --- | --- | --- | --- |
| F-01 | 需修订 | "每日定时触发、提醒、**界面 未实现**"与代码不符：已有 4 条页面路由（`/`、`/opportunity/<id>`、`/import`、`/ops`）、6 个模板、2 个静态文件（S2 最小界面） | README L75 | 改为"每日定时触发/提醒未实现；S5 摘要与匹配/排序的可视化未接入，现有 S2 最小页面 4 个" |
| F-02 | 需修订 | "现有 23 条路由"未区分范围：实际 27 条（23 条 API `@bp` + 4 条页面 `@pages`） | README L79 | 改为"23 条 API 路由（另有 4 条页面路由，共 27 条）" |
| F-03 | 需修订 | 环境变量表称"均有默认值"，但 `APP_MAX_BODY_BYTES`/`APP_MAX_ROWS` 仅写"见 config.py"（实际 5242880 / 5000） | README L26–L27 | 直接写出数值，或把表头改为"默认值见 config.py" |
| F-04 | 需修订 | 能力现状"已实现并验收"中，S4 情景在 `docs/validation/` 未见独立验收报告（其余匹配/排序/摘要均有验收文档） | README L70–L72 | 注明依据（`S4_SCENARIO_SPEC.md` §10 实施记录 + 测试）或补索引；"验收"最终状态以策划为准 |
| F-05 | 建议 | "无 README 之外的运行手册历史（本文件为首版）"不可验证（无 VCS） | README L83 | 删去"历史/首版"表述或注明不可核 |
| F-06 | 记录 | README 实测 **95 行**（任务上下文称 94 行）；前后 hash 未变 | — | 以实测为准 |

> 文件事实更正记录：B 自述 `.gitignore` sha `15FB62DA…` **与实测一致**；README/.gitignore 均未被本核验修改。

## 6. 探针保留与清理说明

- `<run>/probe/` **保留**（一次性骨架 + 复制来的 `.gitignore` + `git init` 产生的 `.git`），仅位于 `tests/acceptance/_tmp/s6_docs_verify_v1/` 内，不影响仓库根与交付树；证据 JSON 内已逐条记录骨架文件、命令、真实输出与退出码。
- 隔离镜像 `<run>/mirror/`、临时 DB 未创建（discover 在镜像 `tests/**/_tmp` 内自建，均在上限隔离目录内）；未在 live `tests/**` 写任何临时文件（前后清单 188 件 digest 一致可证）。
- 核验过程修正史（如实保留）：attempt1 我方两处**探针口径错误**——① 用 `git check-ignore -v` 的退出码判"未忽略"（否定规则命中时 `-v` 也返回 0，应以不带 `-v` 的退出码为准）；② README 断言把 `schema_version` 子串当作含 "version" 字段。修正后 README 17/17、git 21/21 全过；失败件保留为 `*_attempt1_probe_bug.*`。

## 7. 未执行 / 未覆盖（不标 PASS）

- **未启动服务**：README 的启动/停止/端口命令只做静态核对（`app/__main__.py` 与 routes 代码证据），未实际运行 `python -m app`、未执行 `Get-NetTCPConnection`/`Stop-Process`；"health 200"仅由代码字段核对，未做真实 HTTP 请求。
- **未联网**；**未在仓库根执行 git 提交/检出**（仓库根无 `.git`，探针为一次性 `git init` 于 run 目录）；未验证 git 版本以外的 Windows 文件系统特例（如大小写敏感挂载）。
- **未覆盖**：S6 备份/恢复演练（设计仍未实现脚本）；`instance/` 内既有非库文件（`env_checks.txt`/`http_e2e.txt`/`test_run.txt`/`_e2e.csv`/`_e2e.ps1`）的交付处置（README L47 说按交付策略人工复制，未核）；README 能力表中"已实现并验收"的最终验收状态属策划权限（本报告只核对文档与代码/验收文档的一致性）；`docs/design/S4_S5_READ_PATH_PROPOSAL.md` 的"待用户裁定"状态未核。
- 结论仅限本核验（上述哈希与证据）；**不宣称 S6 完成或交付可用**。

## 8. 结论

- **.gitignore 语义核验：通过**——真实 git 2.54.0 下，快照内嵌套 `.db`、快照 manifest、fixtures、app/docs/README 均不被忽略；`tests/*/_tmp`、`instance/`、`.venv/`、`__pycache__/` 均被忽略；B 的 5 条断言被 21 条独立断言复现/扩展。
- **discover：通过**——隔离镜像 253/253 OK、真实 exit=0，与 README 基线一致。
- **守护：通过**——live 树前后 digest 完全一致、业务库哈希与 WAL/SHM 不变、未改被验文件。
- **README：需修订（仅文字层面）**——F-01（界面未实现的不实表述）、F-02（23 条路由未区分 API/页面）、F-03（两个默认值未写出）、F-04（S4 情景验收依据需注明）。修正后即可视为通过；不涉及代码/语义变更。

## 9. 证据索引

| 证据 | 路径 |
| --- | --- |
| README 事实核对（17 断言） | [01_readme_check.json](<../../tests/acceptance/_tmp/s6_docs_verify_v1/run_20261020_144858_docsverify/evidence/01_readme_check.json>) |
| 独立 git probe（21 断言/命令原文） | [03_git_probe.json](<../../tests/acceptance/_tmp/s6_docs_verify_v1/run_20261020_144858_docsverify/evidence/03_git_probe.json>) |
| 镜像 parity | [04_mirror.json](<../../tests/acceptance/_tmp/s6_docs_verify_v1/run_20261020_144858_docsverify/evidence/04_mirror.json>) |
| discover 日志（253 OK） | [05_discover_cmd.log](<../../tests/acceptance/_tmp/s6_docs_verify_v1/run_20261020_144858_docsverify/evidence/05_discover_cmd.log>) |
| 前后树清单（digest 一致） | [02_fs_before.json](<../../tests/acceptance/_tmp/s6_docs_verify_v1/run_20261020_144858_docsverify/evidence/02_fs_before.json>) / [06_fs_after.json](<../../tests/acceptance/_tmp/s6_docs_verify_v1/run_20261020_144858_docsverify/evidence/06_fs_after.json>) / [10_fs_final.json](<../../tests/acceptance/_tmp/s6_docs_verify_v1/run_20261020_144858_docsverify/evidence/10_fs_final.json>) |
| 快照/路由/常量事实 | [08_facts.json](<../../tests/acceptance/_tmp/s6_docs_verify_v1/run_20261020_144858_docsverify/evidence/08_facts.json>) |
| 证据文本读回 | [09_evidence_check_cmd.log](<../../tests/acceptance/_tmp/s6_docs_verify_v1/run_20261020_144858_docsverify/evidence/09_evidence_check_cmd.log>) |
