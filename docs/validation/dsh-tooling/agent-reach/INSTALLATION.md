# Agent Reach 安装与接线记录（DSH · 执行者 B）

> 任务：`task-a76071e5b1a3888f1ea915f0a9e3340c`（计划 v4）；范围：`docs/validation/dsh-tooling/agent-reach`。
> 记录时点：2026-10-21（UTC+8）。本机 DSH `0.2.1-rc.2`，工作区 `D:\桌面\two`。
> **结论：安装完成、CLI 可复现调用、DSH catalog 已发现 skill、公开读取与无账号搜索均实测通过；`skill` 工具加载被 Flow 角色策略拒绝（见 §5/§13），未宣称"加载已验证"。**

## 0. 状态总表（按验收要求分开列出）

| 项目 | 状态 | 证据 |
| --- | --- | --- |
| **installed** | ✅ Agent Reach v1.5.0 装入独立 venv；DSH 用户级 skill 及 references 安装完成 | [04 pip 日志](evidence/04_pip_install_agent_reach.log)、[15 skill 清单](evidence/15_skill_listing.json)、[20 变更清单](evidence/20_changed_files.json) |
| **DSH-discovered** | ✅ 会话 skill catalog 出现 `agent-reach` 条目（描述与本 skill 一致，无需重启） | [17 catalog 记录](evidence/17_catalog_and_tool.txt)、[15 skill 清单](evidence/15_skill_listing.json) |
| **DSH-loaded** | ⚠️ **未验证**：`skill(name="agent-reach")` 被 Flow 拒绝（"Flow 当前角色不允许此工具"） | [17 catalog 记录](evidence/17_catalog_and_tool.txt) |
| **CLI-called** | ✅ `--version`/`--help`/`install --dry-run`/`doctor --json` 全部 exit=0；受限 PATH 下仍可调用 | [05](evidence/05b_version.out.txt)、[06](evidence/06b_help.out.txt)、[07](evidence/07b_dryrun.out.txt)、[09](evidence/09_doctor.json)、[18 受限 PATH](evidence/18_restricted_path.txt) |
| **public-read** | ✅ 公开 README 读取成功（22,830 B，标题 `<h1>👁️ Agent Reach</h1>`） | [14 README 快照](evidence/14_public_read_raw_readme.md)、[16 汇总](evidence/16_summary.json) |
| **public-search** | ✅ B站公开搜索 API（code=0，20 条/页）与 GitHub 公开 REST（total_count=2970）均无需账号 | [12 B站 JSON](evidence/12_bilibili_search.json)、[10 GitHub JSON](evidence/10_public_search_github.json)、[16 汇总](evidence/16_summary.json) |
| **unconfigured** | ⚠️ twitter/reddit/facebook/instagram/xiaohongshu/linkedin/boss/xiaoyuzhou/xueqiu/exa_search/youtube 均未配置；Jina/V2EX 本机超时 | [09 doctor](evidence/09_doctor.json)、[11 Jina 错误](evidence/11_public_read_jina.err.txt)、[13 V2EX 错误](evidence/13_v2ex_hot.err.txt) |

## 1. 来源、版本与许可证

| 项 | 值 |
| --- | --- |
| 上游仓库 | https://github.com/Panniantong/Agent-Reach |
| 固定 commit | `94f06c1969dfc1834001269d79d3ad0972d9dee6`（main HEAD，抓取时点 2026-10-21） |
| 版本 | **1.5.0**（`pyproject.toml`） |
| LICENSE | **MIT**（[LICENSE 快照](references/LICENSE)，版权行保留） |
| 安装包来源 | `https://codeload.github.com/Panniantong/Agent-Reach/tar.gz/94f06c1969dfc1834001269d79d3ad0972d9dee6` |
| 上游安装说明 | [references/install.md](references/install.md)（原样快照） |
| 仓库元数据 | [references/commit.json](references/commit.json) |

未从 PyPI 安装同名包；未使用 `--channels=all`；未导入任何账号、Cookie 或 Key。

## 2. 隔离环境与依赖路径

| 用途 | 路径 |
| --- | --- |
| Python（venv 基础） | `C:\Users\19183\AppData\Local\Programs\Python\Python312\python.exe`（3.12.10） |
| 独立 venv | `C:\Users\19183\.agent-reach-venv\`（Python 3.12.10，pip 26.1.2） |
| CLI | `C:\Users\19183\.agent-reach-venv\Scripts\agent-reach.exe` |
| CLI Python | `C:\Users\19183\.agent-reach-venv\Scripts\python.exe` |
| DSH skill | `C:\Users\19183\.dsh\skills\agent-reach\`（用户级根） |
| 工具配置/未来持久数据 | `C:\Users\19183\.agent-reach\`（本安装**未创建**） |
| 本任务备份 | `C:\Users\19183\.dsh\tooling-backups\agent-reach\20261021T132029Z\`（空状态记录） |

- 依赖解析（base extras，未装 browser/playwright）：agent-reach 1.5.0、requests 2.34.2、feedparser 6.0.14、python-dotenv 1.2.4、loguru 0.7.3、PyYAML 6.0.3、rich 15.0.0、yt-dlp 2026.8.19、yt-dlp-ejs 0.8.0 等（完整见 [04 pip 日志](evidence/04_pip_install_agent_reach.log)）。
- 未向 DSH 内置依赖、工作区 `.venv`、系统 Python、全局包目录安装任何东西（venv 独立；未运行 `install --system`）。

## 3. 现有安装检测与备份

- 安装前检测：`DSH_HOME=C:\Users\19183\.dsh`（存在）；`C:\Users\19183\.dsh\skills` **不存在**；`C:\Users\19183\.dsh\skills\agent-reach` **不存在**；`C:\Users\19183\.agent-reach`、`C:\Users\19183\.agent-reach-venv` **均不存在** → 全新安装，无旧 Skill/config 需覆盖。
- 备份目录（空状态留证）：`C:\Users\19183\.dsh\tooling-backups\agent-reach\20261021T132029Z\before.json`、`README.txt`；未复制任何凭据（安装过程未接触凭据）。
- 未修改 DSH 核心、MCP 主登记、`~/.openclaw`、Stealth 目录、系统 PATH/代理、全局 pip/npm 设置。

## 4. 安装步骤与真实 exit

| # | 命令（cwd=`D:\桌面\two`） | exit | 日志 |
| --- | --- | --- | --- |
| 1 | `Python312\python.exe -V` | 0 | [01](evidence/01_python312_version.log) |
| 2 | `Python312\python.exe -m venv C:\Users\19183\.agent-reach-venv` | 0 | [02](evidence/02_create_venv.log) |
| 3 | `.agent-reach-venv\Scripts\python.exe -V` | 0（3.12.10） | [03](evidence/03_venv_python_version.log) |
| 4 | `.agent-reach-venv\Scripts\python.exe -m pip install --no-cache-dir "https://codeload.github.com/Panniantong/Agent-Reach/tar.gz/94f06c19…"` | 0 | [04](evidence/04_pip_install_agent_reach.log) |
| 5 | `agent-reach.exe --version` | 0（`Agent Reach v1.5.0`） | [05b](evidence/05b_version.out.txt) |
| 6 | `agent-reach.exe --help` | 0 | [06b](evidence/06b_help.out.txt) |
| 7 | `agent-reach.exe install --env=auto --dry-run`（只读检查，不执行安装） | 0 | [07b](evidence/07b_dryrun.out.txt) |
| 8 | `agent-reach.exe doctor --json` | 0（JSON 合法，见证据） | [09](evidence/09_doctor.json) |
| 9 | DSH skill 文件复制（SKILL.md/references/SOURCE/LICENSE/notes） | 0 | [15](evidence/15_skill_listing.json) |

- 未执行 `agent-reach install --system`：dry-run 显示会安装 mcporter/Exa（全局改动），按任务要求改为"经审查的定向独立安装"——只装 Agent Reach 本体到独立 venv，公开能力用现有 `curl.exe`（System32）与 GitHub/B站公开 API；未装 mcporter/OpenCLI/Exa。
- `--channels=all` 未使用；未安装可选登录渠道。

## 5. DSH Skill（用户级）与发现证据

安装位置与文件（13 个文件，含 9 个 references：7 个上游分类文档 + install.md + README.md）：

```
C:\Users\19183\.dsh\skills\agent-reach\
  SKILL.md                     (6316 B, sha256 1bb7eae7…)
  SOURCE.md                    (1679 B)
  DSH-INSTALL-NOTES.md         (6000 B)
  LICENSE                      (1067 B, MIT)
  references\
    career.md dev.md finance.md search.md social.md video.md web.md
    install.md (22167 B)  README.md (22830 B)
```

- 完整路径/字节/sha256 见 [15_skill_listing.json](evidence/15_skill_listing.json)；上游来源与再创作说明见 [SOURCE.md](skill-bundle/SOURCE.md)。**本地引用校验**：已安装 SKILL.md 与报告内 `skill-bundle` 副本的 7 个 references 链接及根目录 `DSH-INSTALL-NOTES.md` 均存在（[26_reference_check.json](evidence/26_reference_check.json)）；`skill-bundle/references/` 另存同一套 9 个上游快照，供报告侧复现。
- **发现证据**：安装完成后，本会话的 available-skills catalog 出现 `agent-reach` 条目，描述与本 `SKILL.md` frontmatter 完全对应（只读互联网调研/搜索/读取）。DSH 0.2.1-rc.2 的 `dsh-skill-filesystem` 扫描 `<dshHome>/skills` 并 watch，新增 skill 无需重启即可进入下一次 catalog；本次实际观察符合该行为。记录见 [17_catalog_and_tool.txt](evidence/17_catalog_and_tool.txt)。
- **加载证据缺失**：尝试 `skill(name="agent-reach")` 返回 `Flow 当前角色不允许此工具；未知工具及其他代理/脚本通道默认拒绝`。这是 Flow 角色策略，不是 skill 文件错误；因此"可发现"已证，"可加载"未由本执行者验证（见 §13）。

## 6. CLI 在 DSH 调用环境的可复现绝对路径

- 绝对路径：`C:\Users\19183\.agent-reach-venv\Scripts\agent-reach.exe`；skill 内所有命令均使用绝对路径，不依赖 PATH。
- **受限 PATH 实测**：将 `PATH` 收窄为 `C:\Windows\System32;C:\Windows` 后，`agent-reach.exe --version` 仍 exit=0（`Agent Reach v1.5.0`）；`curl.exe`（System32）调用 B站搜索 API 也 exit=0。见 [18_restricted_path.txt](evidence/18_restricted_path.txt)、[22 B站结果](evidence/22_restricted_path_bili.json)。
- 未永久修改系统 PATH；DSH 技能通过绝对路径调用。

## 7. doctor 逐渠道状态（`agent-reach doctor --json`，2026-10-21T13:17Z）

| 通道 | status | active_backend | 本机说明 |
| --- | --- | --- | --- |
| bilibili | **ok** | B站搜索 API | 实测 curl 搜索成功 |
| web | ok | Jina Reader | `r.jina.ai` 本机超时（exit 28），改用原始网页 curl |
| v2ex | ok | V2EX API (public) | `v2ex.com` 本机超时（exit 28），未验证 |
| rss | ok | feedparser | 未单独实测 |
| github | **warn** | — | `gh` 已装但未认证；公开 REST 可用 |
| twitter | warn | — | 未安装 twitter-cli；未配置 |
| xueqiu | warn | — | 需登录 Cookie；未配置 |
| youtube | off | — | PATH 无 yt-dlp CLI（venv 有库）；未配置 |
| reddit / facebook / instagram / xiaohongshu / linkedin / boss / xiaoyuzhou / exa_search | off | — | 需登录态/额外安装/Key；未配置 |

完整 JSON：[09_doctor.json](evidence/09_doctor.json)；结构化摘要：[16_summary.json](evidence/16_summary.json)。

## 8. 公开读取与无需账号搜索（真实结果）

### 8.1 公开读取
- 命令：`curl.exe -sSL --max-time 60 "https://raw.githubusercontent.com/Panniantong/Agent-Reach/94f06c1969dfc1834001269d79d3ad0972d9dee6/README.md"`；exit=0；22,830 B。
- 内容首行：`<h1 align="center">👁️ Agent Reach</h1>`（完整快照：[14](evidence/14_public_read_raw_readme.md)）。

### 8.2 B站公开搜索（无需账号）
- 命令：`curl.exe -sS -H "User-Agent: Mozilla/5.0…" -H "Referer: https://www.bilibili.com/" "https://api.bilibili.com/x/web-interface/search/type?search_type=video&keyword=AI"`；exit=0；`code=0`；`numResults=1000`（每页 20 条）。
- 结果示例（[12 原始 JSON](evidence/12_bilibili_search.json)，标题已去高亮标签）：
  1. `AI5` — `BV15UpLzLESs` — http://www.bilibili.com/video/av115194948816067
  2. `[AI MV]人工智能的效果已经如此之大了` — `BV1wZYZzvEdi` — http://www.bilibili.com/video/av115070646358956
  3. `简单的ai 帝王般的享受` — `BV1Uojm64E4M` — http://www.bilibili.com/video/av116800494769299

### 8.3 GitHub 公开搜索（无需账号，备用）
- 命令：`curl.exe -sS -H "User-Agent: agent-reach-dsh" "https://api.github.com/search/repositories?q=agent+reach&per_page=3"`；exit=0；`total_count=2970`。
- 前 3 条（[10 原始 JSON](evidence/10_public_search_github.json)）：
  1. `Panniantong/Agent-Reach` — https://github.com/Panniantong/Agent-Reach
  2. `EdisonChenAI/agent-reach` — https://github.com/EdisonChenAI/agent-reach
  3. `Danau5tin/multi-agent-coding-system` — https://github.com/Danau5tin/multi-agent-coding-system

## 9. 失败与未配置渠道（单列，不冒充成功）

| 项目 | 结果 | 说明 |
| --- | --- | --- |
| Jina Reader（web 通道） | curl **exit=28**，0 B | 本机网络超时；doctor 标 ok 但实际不可用 |
| V2EX 公开 API | curl **exit=28**，0 B | 同上 |
| `skill` 工具加载 | 拒绝（Flow 角色） | 加载未验证 |
| GitHub `gh` 搜索 | 未使用 | `gh` 未认证；改用公开 REST |
| yt-dlp CLI | 未在 PATH | 仅 venv 内库；YouTube 通道未就绪 |
| B站 `bili-cli` | 未安装 | 公开 API 已够用；不额外安装 |
| twitter/reddit/facebook/instagram/xiaohongshu/linkedin/boss/xiaoyuzhou/xueqiu/exa_search | 未配置 | 需账号/Cookie/Key/额外安装；未索取凭据 |

## 10. 边界与"原业务项目不变"

- 未改动工作区代码/测试/契约/迁移/台账/文档基线：`requirements.txt`、`CONTRACT.md`、迁移 0001/0002、`wiring.py`、`bilibili_view.py`、`importer.py`、`real_link.py` 的 sha256 前后一致（[19_baseline_after.json](evidence/19_baseline_after.json)，`all_match=true`）。
- 业务库 `instance/app.db` sha256=`E073F828…4EB85` 前后一致，`-wal`/`-shm` 不存在；未用 SQL 打开业务库（仅文件哈希）。
- 未改 DSH 核心、MCP 主登记、Stealth 目录、系统 PATH/代理/全局包设置；未导入任何账号/Cookie/Key；未做发布/私信/采购/付款等写动作；未买服务。

## 11. 回滚 / 卸载

```powershell
# 1) 移除 DSH skill（无需重启，下一次 catalog 会移除）
Remove-Item -Recurse -Force "C:\Users\19183\.dsh\skills\agent-reach"
# 2) 移除独立 venv（CLI 与其依赖全部在此）
Remove-Item -Recurse -Force "C:\Users\19183\.agent-reach-venv"
# 3) 可选：本安装未创建工具数据目录；如未来出现且确认无用户数据
# Remove-Item -Recurse -Force "C:\Users\19183\.agent-reach"
# 4) 备份目录仅作记录；本次安装前无旧 skill，回滚=删除，无需恢复
```

- 无需还原 PATH/代理/全局包（均未改动）；DSH 核心/MCP 未改。
- 本任务备份：`C:\Users\19183\.dsh\tooling-backups\agent-reach\20261021T132029Z\`（before.json + README.txt，空状态）。

## 12. 证据清单（全部 UTF-8 无 BOM）

| 证据 | 内容 |
| --- | --- |
| [00_install_meta.txt](evidence/00_install_meta.txt) | 安装命令/exit 汇总 |
| [01–04](evidence/04_pip_install_agent_reach.log) | Python/venv/pip 安装日志 |
| [05b/06b/07b](evidence/05b_version.out.txt) | version/help/dry-run 原始 stdout |
| [09_doctor.json](evidence/09_doctor.json) | doctor 完整 JSON |
| [10](evidence/10_public_search_github.json)、[12](evidence/12_bilibili_search.json)、[14](evidence/14_public_read_raw_readme.md) | 公开搜索/读取原始结果 |
| [15_skill_listing.json](evidence/15_skill_listing.json) | skill 13 文件清单+sha256 |
| [16_summary.json](evidence/16_summary.json) | 结构化汇总（doctor/搜索/读取/失败） |
| [17_catalog_and_tool.txt](evidence/17_catalog_and_tool.txt) | catalog 发现 + skill 工具拒绝记录 |
| [18_restricted_path.txt](evidence/18_restricted_path.txt) | 受限 PATH 复现 |
| [19_baseline_after.json](evidence/19_baseline_after.json) | 工作区基线前后哈希 |
| [20_changed_files.json](evidence/20_changed_files.json) | 变更清单（skill/venv/backup/report） |
| [21_utf8_check.txt](evidence/21_utf8_check.txt) | UTF-8 读回检查 |

## 13. 限制（如实）

1. **DSH 加载未验证**：`skill` 工具被 Flow 角色策略拒绝，原始信息为 `Flow 当前角色不允许此工具；未知工具及其他代理/脚本通道默认拒绝`；本执行者无法证明 `skill` 加载，仅证明 catalog 已发现。**主会话验证步骤**：① 在一个新的主会话（非 Flow 执行者角色）调用 `skill(name="agent-reach")`，成功时应返回本文档正文；② 或由用户在 DSH GUI 侧触发该 skill 并确认加载；③ 由独立核验者复跑 `agent-reach --version` 与 B站公开搜索，确认同一安装。不得把读取 SKILL.md 文件正文当作原生加载成功，也不得绕过 Flow 角色策略。
2. **doctor ≠ 可用**：web/V2EX 虽标 ok，本机 curl 均超时；只有 B站搜索、原始网页读取、GitHub 公开 REST 实测通过。
3. **未配置需账号的渠道**：Twitter/Reddit/Facebook/Instagram/小红书/LinkedIn/Boss/雪球/小宇宙/Exa 均未安装/未配置；未索取或导入任何凭据。
4. **GitHub `gh` 未认证**：公开 REST 有限速（未认证 10 请求/分钟量级），不适合高频；本报告只用于验证一次搜索。
5. **未安装 `--system` 外部工具**：mcporter/Exa/OpenCLI/yt-dlp CLI/bili-cli 未装；`doctor` 中相关通道保持 off/warn。
6. **网络不稳定**：Jina/V2EX 超时可能随时变化；换网络后需重新实测，不能引用本次"ok"状态。
7. **证据位置**：本报告与证据在 `docs/validation/dsh-tooling/agent-reach/`；DSH skill/venv/备份在外部白名单目录。未提交到 git（工作区无 `.git`）。

## 14. 变更记录

| 日期 | 修订 | 变更 |
| --- | --- | --- |
| 2026-10-21 | rev3 | 首次提交：安装/发现/CLI/公开读取/搜索证据；DSH 加载未验证 |
| 2026-10-21 | rev5 | 修正 SKILL.md 本机记录引用为根目录 `DSH-INSTALL-NOTES.md`（第 25 行与第 37 行；同步 skill-bundle 与已安装副本）；报告技能文件数统一为实际 13；移除 doctor 硬编码字节数（改为"JSON 合法，见证据"）；新增主会话加载验证步骤与本变更记录；**未改动原网络成功/失败证据** |
