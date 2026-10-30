# DSH 双工具独立运行与当前哈希核验（计划 v4 · 执行者 A）

> 任务：`task-fa97c7e8dfc0fc75f2779928b7156469`（revision 2，计划 v4，goal `goal-9fd9f5d2f1fb9c394c5a1283c8baab0e`）。
> 角色：独立核验执行者 `session-01ba487c-f808-55a7-a1f7-5f436ee12811`，**未参与 B/C 安装**；`flow_peers` 显示本会话 `allowCommands=true`，planner 与静态核验会话 `allowCommands=false`。
> 范围：本 `runtime/` 子目录与 `../manifest.sha256`；**只读**安装目录/现有工具目录/私人目录中的必要文件，不改已装软件、配置、原证据。
> 采样窗口：2026-10-21 14:03–14:10 UTC（22:03–22:10 UTC+8）；所有命令日志/报告 UTF-8 无 BOM、LF，含 `cmd/cwd/start_utc/end_utc/exit`；`*.raw.out/*.raw.err` 为原始字节捕获（可能保留 CRLF）。
> 工具入口记录：本会话函数表**无 `skill` 工具**（仅有命令/文件/网络读取等），按任务要求记录一次后改用计划允许的绝对路径 CLI；**未**用 Host 脚本、其它代理或 SDK 反调受限 Skill/MCP。

## 0. 结论表（按汇报要求分类）

| 类别 | 状态 | 真实 exit / 证据 |
| --- | --- | --- |
| CLI（AgentReach version/help/doctor） | **PASS** | 3 次均 exit=0；`logs/cli/agent_reach_{version,help,doctor}.log` |
| doctor（渠道状态） | **PASS** | exit=0；16 渠道状态已记录；绿灯不等于实际可用（§2） |
| public-read | **PASS** | 首源 exit=56（已保留），替代源 GitHub Contents API exit=0；22,830 B，sha256 `7b723bcd…`（§3） |
| public-search | **PASS** | GitHub REST exit=0；`total_count=2970`，3 条样本原链接（§4） |
| dependency-check | **PASS** | 两 venv `pip check` 均 exit=0；版本/路径/direct_url 已独立读取（§5） |
| provenance | **PASS** | AgentReach commit `94f06c19…`（direct_url+本地 commit.json）；Stealth commit `aa6cc9f6…`（GitHub API 返回同 sha）；0.2.5 与 mcp 1.30.0 分开（§5） |
| current-hashes | **PASS** | 业务/冻结/DSH 核心/两 Skill 当前 sha 复算，expected 不一致 **0**；业务库 `e073f828…`、无 WAL/SHM（§6） |
| patch-delta | **PASS** | 当前 383 行/10899 B/`fda036e9…`，备份 363 行/9980 B/`7fe68433…`；字节/规范化/行前缀均真，仅追加 1 个 insert block（§7） |
| manifest | **PASS** | `../manifest.sha256` 生成后覆盖原 8 文件 + 本 runtime 全部产物（排除自身），复核见 §8/提交证据 |
| 原生 Skill/MCP 端到端 | **PENDING** | 本任务不代调；函数表无 skill 工具；浏览器 MCP/stdio 未测试，留普通 DSH 主会话（§9） |

## 1. CLI：AgentReach 绝对路径运行

- CLI：`C:\Users\19183\.agent-reach-venv\Scripts\agent-reach.exe`；cwd=`C:\Users\19183`（普通目录，不依赖工作区 `.venv`/PATH）。
- `--version` exit=0 → `Agent Reach v1.5.0`（`logs/cli/agent_reach_version.log`，20 B stdout）。
- `--help` exit=0 → 子命令 `{setup,install,configure,doctor,uninstall,skill,format,transcribe,check-update,watch,version}`（`logs/cli/agent_reach_help.log`）。
- `doctor --json` exit=0 → 合法 JSON 6,229 B（`logs/cli/agent_reach_doctor.out.txt`；状态摘要 `evidence/doctor_status.json`）。
- 说明：CLI 本身**不提供** read/search 子命令；公开读取/搜索按本机 Skill 中已审查的 Windows 绝对路径 `curl.exe` 通道执行（§3/§4），未使用 `web_fetch`/`web_search` 冒充 CLI。

## 2. doctor 逐渠道状态（exit=0；不把绿灯当能力）

| 状态 | 渠道 |
| --- | --- |
| `ok`（4） | bilibili（B站搜索 API）、web（Jina Reader）、v2ex（V2EX API public）、rss（feedparser） |
| `warn`（3） | github（无显式认证）、twitter、xueqiu |
| `off`（9） | youtube、reddit、facebook、instagram、xiaohongshu、linkedin、boss、xiaoyuzhou、exa_search |

- 本批**只实测** GitHub 公开读取/搜索（§3/§4）；bilibili 本轮未重跑；web/v2ex 按安装报告已知本机超时，**未重复打 Jina/V2EX**；其余 off/warn 渠道未配置/未验证。
- 因此：doctor 的 `ok` 仅表示检测通过，**不等于**实际读取/搜索能力；未实测渠道不报 PASS。

## 3. public-read：一次公开内容读取（含失败与替代源）

| 尝试 | 命令（cwd=`C:\Users\19183`） | 结果 |
| --- | --- | --- |
| 首源 | `curl.exe -sSL --max-time 60 https://raw.githubusercontent.com/Panniantong/Agent-Reach/94f06c19…/README.md` | **exit=56**，stderr `curl: (56) Recv failure: Connection was reset`，0 B；`logs/public/public_read_readme.log` 保留 |
| 替代源（仅 1 次） | `curl.exe -sS --max-time 30 -H "User-Agent: agent-reach-dsh" -H "Accept: application/vnd.github+json" https://api.github.com/repos/Panniantong/Agent-Reach/contents/README.md?ref=94f06c19…` | **exit=0**，JSON 32,440 B；`logs/public/public_read_readme_api.log` |

- 替代源解码后 README **22,830 B**，sha256 `7b723bcd4e5992c37ad1c25c3a2badd89c723a105b787fde9d1aa19a215f7ff7`（与安装报告 §8.1 的 README 快照同哈希）；首行 `<h1 align="center">👁️ Agent Reach</h1>`；原链接 = GitHub Contents API 的 `download_url`（pinned commit）。
- 原始响应：`logs/public/public_read_readme_api.out.txt`；解码正文：`logs/public/public_read_readme.md`；元数据：`evidence/public_read_meta.json`。
- 未用 `web_fetch`/`web_search`；未访问账号/Cookie/Key；失败原样保留。

## 4. public-search：一次无需账号搜索

- 命令：`curl.exe -sS --max-time 30 -H "User-Agent: agent-reach-dsh" -H "Accept: application/vnd.github+json" "https://api.github.com/search/repositories?q=agent+reach&per_page=3"`，cwd=`C:\Users\19183`。
- **exit=0**；原始 JSON 17,363 B（`logs/public/public_search_github.out.txt`）；`incomplete_results=false`，`total_count=2970`。
- 提取样本（`evidence/public_search_meta.json`）：
  1. `Panniantong/Agent-Reach` — https://github.com/Panniantong/Agent-Reach — 100,504 stars，MIT；
  2. `EdisonChenAI/agent-reach` — https://github.com/EdisonChenAI/agent-reach — 147 stars，MIT；
  3. `Danau5tin/multi-agent-coding-system` — https://github.com/Danau5tin/multi-agent-coding-system — 1,469 stars，Apache-2.0。
- 未登录、未配置 Token；GitHub 公开 REST 有限速，本批仅 1 次搜索 + 1 次读取。

## 5. 环境、依赖与来源（两套独立 venv）

### 5.1 Agent Reach

| 项 | 值 |
| --- | --- |
| venv / Python | `C:\Users\19183\.agent-reach-venv`，Python **3.12.10**（`in_venv=true`，base `…\Python312`） |
| 包版本 | `agent-reach` **1.5.0**（importlib.metadata） |
| PEP610 direct_url | `https://codeload.github.com/Panniantong/Agent-Reach/tar.gz/94f06c1969dfc1834001269d79d3ad0972d9dee6`，archive sha256 `d608cc61…` |
| 模块实际路径 | `…\.agent-reach-venv\Lib\site-packages\agent_reach\__init__.py`（version 属性 1.5.0） |
| `pip check` | **exit=0**，`No broken requirements found.`（`logs/dep/pip_check_agent_reach.log`） |
| 来源 | 官方 commit `94f06c19…`；本地 `references/commit.json` 同 sha；License MIT（安装 LICENSE sha `e94c131a…`） |

### 5.2 Stealth Browser MCP

| 项 | 值 |
| --- | --- |
| venv / Python | `C:\Users\19183\.dsh\tools\stealth-browser-mcp\venv`，Python **3.10.9**（`in_venv=true`，base `…\Python310`） |
| 包声明 | `pyproject.toml` **version 0.2.5**；包本身**未作为 pip distribution 安装**（从源码树运行，`stealth-browser-mcp` metadata `installed=false`） |
| MCP 库（分开） | `mcp` **1.30.0**、`fastmcp` **2.11.2**、`nodriver` **0.47.0**、`pydantic` **2.11.7**；模块实际路径均在该 venv 的 `Lib\site-packages` |
| `pip check` | **exit=0**，`No broken requirements found.`（`logs/dep/pip_check_stealth.log`）；stderr 仅有 `AuthlibDeprecationWarning: authlib.jose…`，非依赖破损 |
| 来源 | 官方 commit `aa6cc9f6f853d6cbc17e4dc9b7946d406caabc6f`；GitHub API 返回同 sha（2026-10-19T19:23:19Z，`evidence/stealth_commit_meta.json`）；License MIT |
| 关键文件 | `pyproject.toml` `bd0dd9e0…`（1456 B）、`src/server.py` `30baa58f…`（104222 B）、`LICENSE` `4cf9ac50…`（1091 B） |

### 5.3 DSH 本体

- `@deepseek-ai/dsh-desktop-runtime` **0.2.1-rc.2**；`@deepseek-ai/dsh-mcp-client` **0.2.1-rc.2**；对应 `package.json` 与 mcp-client `lib/index.js` 哈希均与 B/C 基线一致（§6）。
- **未启动/结束/重启 DSH**，未开端口，未做浏览器 MCP/stdio 测试；未安装/升级任何包，未改 PATH/代理/全局环境。

## 6. 当前哈希独立复算（与 B/C 基线对比）

- 证据：`evidence/current_hashes.json`（复算时点 2026-10-21T14:05:47Z）；expected 不一致 **0**。
- 业务/冻结文件（当前 = 基线）：

| 文件 | bytes | sha256 |
| --- | --- | --- |
| `instance/app.db` | 241,664 | `e073f828cf0f30d6206361bba3a729826be096be3308f5a5dc204406dae4eb85` |
| `requirements.txt` | 179 | `0af19a0f1c100e99483b79e7f11b500ccf6a5a1477d8ac4b560c077b2bea7731` |
| `docs/design/CONTRACT.md` | 74,839 | `826c24cc6c99551178875bed617e085231bd23998b6a049f396116e1e70fb4f9` |
| `app/sources/real_link.py` | — | `46cbd635b5e70cc2d1b6441befde31e25b8203caf28d39b772203c43b8f5802c` |
| `app/sources/wiring.py` | 8,402 | `bafcf3974cbfb3ed4da99936e5d65d10d6f02c663b6325008255b4eaecc0da05` |
| `app/sources/bilibili_view.py` | 12,866 | `b0dc0ced1bc3be3eca85116559d5acae52f7753dca1dcbbac259e573cc73f98e` |
| `app/core/importer.py` | 49,011 | `a11eaf4d39541ac11459eb1cebb8586f4922838b96714d7f7f3d2e253cff51a1` |
| `0001_init.sql` | 14,102 | `9b0493731305c2e3de3c89a1a16dcc8a53ca5882d014f63333b34e7c872e62bb` |
| `0002_draft_feedback.sql` | 2,688 | `34d70a1d501ba1aaf2fb93de1351ea80c470dcac9e6bc040617b19c5446c3aed` |

- DSH 核心：`dsh/package.json` `b67a65b9…`（17,100 B）；`@deepseek-ai/dsh-mcp-client/lib/index.js` `758d8fc4…`（35,041 B）；`profiles/desktop/package.json` `10424b6b…`。
- `cordis.patch.yml` 当前 `fda036e9…`（10,899 B，383 行），与 B 的 after 基线一致。
- Agent Reach Skill：13/13 文件逐个 sha 与安装清单 `15_skill_listing.json` 一致（SKILL.md `1bb7eae7…`，6,316 B）；目录共 13 文件。
- Stealth Skill：2 文件（`SKILL.md` `9c48bf65…` 4,005 B；`agents/openai.yaml` `32b804f0…` 197 B）；安装报告未提供这 2 个基线哈希，本轮记录当前值，不虚构"与基线一致"。
- 业务库 `wal=false`、`shm=false`；业务库/备份/旧证据未打开 SQL、未修改。

## 7. patch-delta：只追加本工具条目的字节/文本核验

- 证据：`evidence/patch_delta.json`；当前 `C:\Users\19183\.dsh\profiles\desktop\cordis.patch.yml`，备份 `…\tooling-backups\stealth-browser\cordis.patch.yml.pre-stealth-20261021T132904Z`（备份文件本身只读打开）。
- 当前：383 行、10,899 B、sha256 `fda036e9aec82a7e07054df16e0ec425c0276ce6b6107e158239198fdb13c355`（与 B 的 after 记录一致）。
- 备份：363 行、9,980 B、sha256 `7fe6843373d8ae1e772d0db38f08b2a360b19966aa5b073e03f7f1af3fadefde`（与 B 的 before 记录一致）。
- 比较：**字节前缀相等 true**（共同前缀 9,980 B）、**规范化文本前缀相等 true**、**行前缀相等 true**；当前 = 备份 + 20 行（1 空行 + 1 注释 + 18 行单个 `- insert:` block）。
- 追加 block（仅输出本工具字段，其它配置/凭据未打印）：
  - id `stealth-browser-mcp`；name `@deepseek-ai/dsh-mcp-client`；serverName `stealth`；transport `stdio`；`failOnStartupError: true`；
  - command `C:\Users\19183\.dsh\tools\stealth-browser-mcp\venv\Scripts\python.exe`；args `…\repo\src\server.py --minimal`；cwd `…\repo`；
  - env keys（仅键名）：`STEALTH_BROWSER_EXECUTABLE`、`BROWSER_ORPHAN_PROFILE_MAX_AGE`、`BROWSER_FILE_UPLOAD_ALLOWED_DIRS`、`STEALTH_BROWSER_DEBUG`、`PYTHONIOENCODING`；
  - 追加 block 规范化文本 sha256：`8af9ecdd26473656e3501fa457ad05c31d89feb7e31ce6e9f950e069f016e2af`。
- 回滚评审：删除末尾 20 行即可**逐字节**恢复备份（前缀相等已证）；**未实际回滚**、未改当前 patch；原 6 个条目未被重写，新增后 entries=7。
- 说明：`fda036e9…`/`7fe68433…` 也与 B 的 `09_post_hashes.json`/`01_baseline_hashes.json` 一致；未打印其它 DSH 配置内容。

## 8. 证据与 manifest

- 本目录产物：`INDEPENDENT_RUNTIME.md`、`tools/`（run_proc/dep_probe/hash_current/patch_delta）、`logs/`（cli/dep/public/hash/patch；含首源失败与首轮 parser 失败保留）、`evidence/`（doctor/public read/public search/provenance/current_hashes/patch_delta/command_index）。
- `../manifest.sha256`：覆盖原 8 个核验文件 + 本 runtime 全部文件，**排除 manifest 自身**；首行记录采样时点，避免自引用旧 hash；生成后逐条复核（见提交证据）。
- 所有命令日志/报告 UTF-8 无 BOM/LF，含真实 exit；`*.raw.out/*.raw.err` 保留原始字节（可能 CRLF）；`evidence/command_index.json` 列出每个日志的 cmd/cwd/UTC/exit（含 `public_read_readme` exit=56 与 `patch_delta_attempt1_parser` exit=1 的保留记录）。

## 9. 未实测 / 限制 / 用户动作

- **PENDING**：原生 `skill` 加载与 DSH 内 MCP 工具调用未在本任务验证——本会话函数表无 `skill` 工具，且任务明确禁止代调受限 Skill/MCP、禁止浏览器 MCP/stdio 测试；需普通 DSH 主会话（或新会话）验证"可加载/可调用"。本报告**不宣称** DSH 端到端接入完成。
- 公开读取首源 `raw.githubusercontent.com` exit=56（连接重置）；仅一次替代源成功，不能据此断言该主机稳定可用。
- doctor 的 bilibili/web/v2ex/rss `ok` 未在本批全部重测；web/v2ex 已知本机超时未重复请求；off/warn 渠道仍未配置。
- Stealth 包从源码树运行、非 pip distribution；`mcp 1.30.0` 是库版本，`0.2.5` 是项目版本，二者已分开记录。
- 未运行完整业务测试（本批无业务代码变化）；未验证真实浏览器启动/截图/清理（禁止）。
- 用户动作（如需）：在普通 DSH 会话中重载/新建会话，确认两 Skill 可被 `skill` 工具加载、Stealth MCP 工具出现在工具表并可 `spawn→navigate→…→close`；这不属于本执行者可代做的范围。

## 10. 不修改声明

- 仅新增 `docs/validation/dsh-tooling/verification/runtime/**` 与 `docs/validation/dsh-tooling/verification/manifest.sha256`；**未修改**已装软件、DSH 配置、AgentReach/Stealth 安装目录、原 8 个核验文件、安装报告/证据、业务库/冻结文件。
- 所有安装路径仅只读访问；`PYTHONDONTWRITEBYTECODE=1` 仅进程级设置；未永久改 PATH/代理/全局环境；未读取账号/Cookie/Key。
- 原 `INDEPENDENT_ACCEPTANCE.md`（123 行）保持冻结；本报告是其"有命令权限执行者"的补充，不替代它。
