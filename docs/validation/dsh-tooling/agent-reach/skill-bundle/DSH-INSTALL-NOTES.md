# DSH 本机安装记录（Agent Reach v1.5.0）

> 记录时点：2026-10-21（UTC+8 本机）。本文件是安装/验证/回滚的**事实记录**；不含账号、Cookie、Key 或代理凭据。

## 1. 路径

| 用途 | 绝对路径 |
| --- | --- |
| DSH_HOME | `C:\Users\19183\.dsh`（默认，环境变量存在且一致） |
| DSH skill（本任务） | `C:\Users\19183\.dsh\skills\agent-reach\` |
| CLI venv | `C:\Users\19183\.agent-reach-venv\`（Python 3.12.10） |
| CLI | `C:\Users\19183\.agent-reach-venv\Scripts\agent-reach.exe` |
| 工具配置/未来持久数据 | `C:\Users\19183\.agent-reach\`（本安装未创建/未写入） |
| 本任务备份 | `C:\Users\19183\.dsh\tooling-backups\agent-reach\<UTC>\` |
| 工作区报告/证据 | `D:\桌面\two\docs\validation\dsh-tooling\agent-reach\` |

未改动：DSH 核心文件、DSH MCP 主登记、`~/.openclaw`、Stealth 目录、系统 PATH、系统代理、全局 pip/npm 设置、工作区业务代码/业务库。

## 2. 安装步骤（实际执行）

1. 检测：`DSH_HOME` 存在；`skills` 目录**原本不存在**；`~/.agent-reach`/`~/.agent-reach-venv` **原本不存在** → 全新安装，无同名旧 Skill 可备份（仍创建备份目录并留存"安装前状态"记录）。
2. `C:\Users\19183\AppData\Local\Programs\Python\Python312\python.exe -m venv C:\Users\19183\.agent-reach-venv`（exit=0）。
3. `pip install --no-cache-dir "https://codeload.github.com/Panniantong/Agent-Reach/tar.gz/94f06c1969dfc1834001269d79d3ad0972d9dee6"`（exit=0；agent-reach 1.5.0 + base 依赖；未装 browser/playwright）。
4. 未运行 `agent-reach install --system`（会改动外部/全局环境）；只运行了只读检查 `install --env=auto --dry-run`（exit=0，输出显示只会装 mcporter/Exa，未执行）。
5. 创建 DSH 用户级 skill 目录并复制 `SKILL.md`、`references/*`、`LICENSE`、`SOURCE.md`、本文件；DSH skill-filesystem 配置为 `dshHome=C:\Users\19183\.dsh`、`watch=true`，按插件文档新增 skill 无需重启即可进入下一次 catalog。

## 3. doctor 快照（`agent-reach doctor --json`，2026-10-21T13:17Z 前后）

| 通道 | status | active_backend | 备注 |
| --- | --- | --- | --- |
| bilibili | **ok** | B站搜索 API | curl 直连公开搜索可用 |
| web | ok | Jina Reader | 本机 `r.jina.ai` 超时，实际用原始网页 curl |
| v2ex | ok | V2EX API (public) | 本机 curl 超时，未验证 |
| rss | ok | feedparser | 未单独实测 |
| github | **warn** | — | `gh` 已装但无显式认证；公开 REST 可用 |
| twitter | warn | — | 未安装 twitter-cli；不配置 |
| xueqiu | warn | — | 需登录 Cookie；不配置 |
| youtube | off | — | 未在 PATH 安装 yt-dlp（venv 内有库但 CLI 不在 PATH） |
| reddit/facebook/instagram/xiaohongshu/linkedin/boss/xiaoyuzhou/exa_search | off | — | 需登录态/额外安装/Key；本任务不安装 |

## 4. 实测命令与结果

| 项目 | 命令 | 结果 |
| --- | --- | --- |
| CLI 版本 | `agent-reach --version` | exit=0，`Agent Reach v1.5.0` |
| CLI 帮助 | `agent-reach --help` | exit=0，列出 setup/install/configure/doctor/skill/... |
| 只读检查 | `agent-reach install --env=auto --dry-run` | exit=0；gh/Node 已存在；仅提示会装 mcporter+Exa（未执行） |
| doctor | `agent-reach doctor --json` | exit=0；6229 B 合法 JSON；状态见上表 |
| 公开搜索（无账号） | `curl.exe ... https://api.bilibili.com/x/web-interface/search/type?search_type=video&keyword=AI` | exit=0；`code:0`，20 条结果，例如 `BV15UpLzLESs` / `http://www.bilibili.com/video/av115194948816067` |
| 公开搜索（无账号，备用） | `curl.exe ... https://api.github.com/search/repositories?q=agent+reach&per_page=3` | exit=0；`total_count=2970`，首条 `Panniantong/Agent-Reach`（https://github.com/Panniantong/Agent-Reach） |
| 公开内容读取 | `curl.exe -sSL https://raw.githubusercontent.com/Panniantong/Agent-Reach/94f06c.../README.md` | exit=0；22830 B；标题 `<h1>👁️ Agent Reach</h1>` |
| Web(Jina) | `curl.exe -sS -L https://r.jina.ai/https://github.com/panniantong/Agent-Reach` | **exit=28 超时**（未就绪，改用原始网页） |
| V2EX | `curl.exe https://www.v2ex.com/api/topics/hot.json` | **exit=28 超时**（未就绪） |

完整命令/exit/日志见工作区 `evidence/`（UTF-8 无 BOM）。

## 5. DSH 发现/加载

- skill 位于用户级根 `C:\Users\19183\.dsh\skills\agent-reach\SKILL.md`；`dsh-skill-filesystem`（DSH 0.2.1-rc.2）扫描该根并 watch（父目录缺失时探测至出现），文档说明新增 skill 会在下一次 catalog 生效、无需重启。
- 本会话的 `skill` 工具被 Flow 角色策略拒绝（"Flow 当前角色不允许此工具"），**无法由本执行者直接加载验证**；已记入限制，交由独立核验者或用户侧验证加载。

## 6. 回滚 / 卸载

1. 删除 skill：`Remove-Item -Recurse -Force "C:\Users\19183\.dsh\skills\agent-reach"`（DSH 不重启也会在下次 catalog 移除）。
2. 删除 venv：`Remove-Item -Recurse -Force "C:\Users\19183\.agent-reach-venv"`。
3. 可选删除工具目录（本安装未创建）：`Remove-Item -Recurse -Force "C:\Users\19183\.agent-reach"`（若存在且确认无用户数据）。
4. 恢复备份（若有）：把 `C:\Users\19183\.dsh\tooling-backups\agent-reach\<UTC>\` 中备份的旧 skill 目录复制回 `C:\Users\19183\.dsh\skills\`；本次安装前该目录不存在，因此回滚=删除，无需恢复。
5. 不需要还原 PATH/代理/全局包（均未改动）；DSH 核心/MCP 登记未改。

## 7. 限制

- 未配置任何需要账号/Cookie/Key 的渠道；未安装 `--system` 外部工具（mcporter/Exa/OpenCLI 等），doctor 中 off/warn 通道均未就绪。
- 本机网络对 Jina、V2EX 超时；GitHub `gh` 未认证（公开 REST 可用但有限速）。
- `skill` 工具被 Flow 拒绝，DSH 侧"实际加载"未能由本执行者证明；仅文件+插件配置证据。
