# DSH 双工具独立核验报告（执行者 A · 非安装者 · 全新 Flow 会话）

> 核验会话：`session-2ec5f901-e129-5a00-a488-80333567fa52`（计划 v4 / 任务 `task-8b14f417fd9800b3512069581b1aa140`）
> 时间：2026-10-21 13:45–14:00 UTC（本地 21:45–22:00 +08:00）｜DSH `0.2.1-rc.2`｜GUI `http://127.0.0.1:11949`｜工作区 `D:\桌面\two`
> 角色：只读核验。未安装、未修改任何软件/配置/策略，未建下级，未使用脚本或 Host 桥接绕过任何未暴露能力。

**一句话结论**：两个工具的**来源、路径、Skill 内容、DSH 登记、备份与回滚**在全新会话中静态复核一致（PASS）；但本会话的函数表里**没有 `skill`、没有 shell、没有任何 `mcp__stealth__*`**，所以**原生 Skill 加载、CLI 复跑、DSH 原生浏览器调用链均未能执行**（PENDING，未暴露）。不宣称全通过。

---

## 0. 分项状态表

| # | 判据 | 状态 | 本轮证据 |
| --- | --- | --- | --- |
| 1 | **installed**（两工具落盘、独立环境、实际模块路径） | ✅ PASS（静态） | [03](03_static_install_check.json)：`agent-reach.exe`、stealth `venv\Scripts\python.exe`、`repo\src\server.py`、`chrome.exe` 全部 glob 命中；`pyproject.toml` 实读 version=`0.2.5`、`requires-python>=3.10` |
| 2 | **source**（固定版本/提交） | ✅ PASS | [05](05_public_read_commit.json)：GitHub API HTTP 200 独立确认 commit `94f06c19…` 为真实签名合并提交（2026-10-07T17:17:26Z）；stealth 包版本 0.2.5 实读，与协议层 `serverInfo.version=1.30.0` 明确分开 |
| 3 | **skill-discovered**（catalog 可见） | ✅ PASS | [02](02_catalog_observed.txt)：本会话 available_skills 同时含 `agent-reach`、`stealth-browser-mcp` |
| 4 | **native-skill-loaded**（原生 `skill` 工具加载） | ⏳ **PENDING（未暴露）** | [01](01_session_tool_table.json)/[04](04_native_capability_probe.md)/[07](07_native_call_attempt.md)：21 个函数中无 `skill`，无调用面，未发出调用、未伪造 |
| 5 | **CLI-call**（`--version/--help/doctor --json` 复跑，真实 exit） | ⏳ **PENDING（无 shell）** | 本会话无 exec/powershell 函数；`flow_peers` 显示本执行者 `allowCommands=false` |
| 6 | **public-read**（公开内容读取） | ⚠️ 替代通道 PASS / 原口径 PENDING | 原口径（Agent Reach CLI / curl）未执行；改用 DSH 原生 `web_fetch` 独立读取 GitHub API（HTTP 200，[05](05_public_read_commit.json)），**明确不冒充 CLI** |
| 7 | **public-search**（无账号搜索） | ⚠️ 替代通道 PASS / 原口径 PENDING | 原口径（B站 API / GitHub REST via curl）未执行；DSH 原生 `web_search` 返回 8 个来源含上游 issue #566、v1.5.0 release 页（[06](06_public_search_sources.json)） |
| 8 | **MCP-registered**（DSH 配置登记） | ✅ PASS（静态） | [03](03_static_install_check.json)：`cordis.patch.yml` 365–383 行 insert 块，stdio/绝对路径/`--minimal`/env 与安装记录逐项一致；delta 为**纯追加 20 行** |
| 9 | **native-MCP-visible**（本会话函数表可见 `mcp__stealth__*`） | ⏳ **PENDING（未暴露）** | 21 个函数中无任何 `mcp__stealth__*`；连 `list_mcp_resources` 也不存在（形态区分见 [07](07_native_call_attempt.md)） |
| 10 | **native-MCP-call-chain**（spawn→navigate→读正文→截图→close） | ⏳ **PENDING** | 无调用面，无法执行；未用 SDK/stdio 脚本冒充 DSH 内调用（[07](07_native_call_attempt.md)） |
| 11 | **screenshot** | ⏳ PENDING | 本会话未产生截图；不引用 C 的 stdio 截图冒充 |
| 12 | **own-instance-closed** | ➖ N/A | 本会话未创建任何浏览器实例，无需关闭；未创建 `profiles\verify-*`，未触碰 `profiles\chain1` |

---

## 1. 版本、实际模块与隔离环境

| 项 | 实读结果 |
| --- | --- |
| Agent Reach 上游 | `Panniantong/Agent-Reach`，commit `94f06c1969dfc1834001269d79d3ad0972d9dee6`（API 200，`verified=true`） |
| Agent Reach 版本声明 | SKILL.md frontmatter `version: 1.5.0` / `license: MIT`；**该 commit 本身只是删 `CLAUDE.md` 并改 SKILL.md/llms.txt 措辞，不含版本号跃迁** —— 版本标签来自更早历史，不能单独用这次提交证明 |
| CLI | `C:\Users\19183\.agent-reach-venv\Scripts\agent-reach.exe`（存在） |
| venv | `C:\Users\19183\.agent-reach-venv`（Scripts 下 python/pip/yt-dlp 等，属隔离环境，未进系统 Python） |
| Skill | `C:\Users\19183\.dsh\skills\agent-reach\`，**13 文件**，`references/*.md` 七篇 + install.md + README.md 全部存在，SKILL.md 第 84–90 行引用的每个相对链接都可解析 |
| Stealth 包 | `stealth-browser-mcp` **0.2.5**，`>=3.10`，MIT；关键钉版 `fastmcp==2.11.2`/`nodriver==0.47.0`/`pydantic==2.11.7`（实读 pyproject） |
| Stealth 模块 | `repo\src\server.py`（3123 行）、`venv\Scripts\python.exe`、`C:\Program Files\Google\Chrome\Application\chrome.exe` 均存在 |
| Stealth Skill | `C:\Users\19183\.dsh\skills\stealth-browser-mcp\`，2 文件（SKILL.md、agents/openai.yaml） |
| 版本口径 | **包版本 0.2.5 ≠ 协议 serverInfo 1.30.0**，两者不可混称"代码版本" |

## 2. 全新会话的真实函数表与 Skill 加载

- 本会话可用函数共 **21 个**，全部为 `flow_*` + 文件（read/write/edit/glob/grep）+ `web_search/web_fetch` + `job_*` + `todo_write` + `goal/*` + `ask_user_question`（完整清单见 [01](01_session_tool_table.json)）。
- **缺失**：`skill`、shell/exec/powershell、`mcp__stealth__*`（21 个）、`list_mcp_resources`/`read_mcp_resource`、`plugin_manager`、`list_agents`/`send_message`/subagent。
- 于是"Skill 是否原生加载"**无法在本会话验证**：没有可发出的调用面。按纪律**未用任何脚本/其它代理/Host 工具反向调用**，也**没有伪造一次不存在的调用**。
- 三层不混淆：**catalog 可见 = PASS**（真实观测）；**registry 已登记 = PASS（静态）**；**模型函数可用 = 未暴露**。
- 成因边界：缺函数只能证明"未进入本会话模型函数表"。是 **Flow 角色过滤**（可观测信号：本执行者 `allowCommands=false`，同台其余 4 位为 `true`）、**会话工具表快照时序**，还是**其它桥接原因**，本会话内**无法区分**，不做单一归因。
- 对照（不作因果断言）：安装者 B 的会话里 `skill` 存在但被 Flow 拒绝（返回"Flow 当前角色不允许此工具…"），安装者 C 的会话有 PowerShell 但无 `skill`/MCP。三个会话的函数表各不相同，说明这是**按会话/角色生成**的表，而非固定全集。

## 3. CLI 与公开读取/搜索（本轮未执行的部分）

**未执行**（无 shell）：`agent-reach.exe --version`、`--help`、`install --env=auto --dry-run`、`doctor --json`、`curl` 公开读取与 B站/GitHub 公开搜索。**exit 码不适用**——没有进程被启动，因此不存在"真实 exit 可报"。不引用安装者日志当本轮 exit。

**本轮实际拿到的独立网络证据（另一条通道，单列不混用）**：

1. `web_fetch https://api.github.com/repos/Panniantong/Agent-Reach/commits/94f06c19…` → **HTTP 200**，返回 sha、author date、`verification.verified=true`、`stats{additions:2,deletions:49}`、files 列表（[05](05_public_read_commit.json)）。→ 证明**本会话出网正常**且**固定提交真实存在**。
2. `web_search "Panniantong Agent Reach v1.5.0 MIT MCP"` → **8 条来源**，含 [v1.5.0 release 页](https://newreleases.io/project/github/Panniantong/Agent-Reach/release/v1.5.0)、[上游 issue #566](https://github.com/Panniantong/Agent-Reach/issues/566#1)、[glama MCP 列表](https://glama.ai/mcp/servers/M0-AR/agent-reach-mcp/tree#1)（[06](06_public_search_sources.json)）。→ 第三方独立佐证 v1.5.0 存在；issue #566 亦佐证"doctor=ok ≠ 渠道可用"的判断。

**逐渠道限制（引用安装者 B 的 doctor + 实测，本轮未复跑，标为未独立验证）**：bilibili ✅ 公开搜索；web（Jina）❌ 本机超时 exit 28；v2ex ❌ 超时；rss 未单独实测；github ⚠️ 仅公开 REST；twitter/reddit/facebook/instagram/小红书/linkedin/boss/小宇宙/雪球/exa ⛔ 未配置（需账号/Cookie/Key）。**本轮无法新增任何渠道结论。**

## 4. DSH 原生浏览器链路

- 本会话**没有** `mcp__stealth__*`，链路（spawn→navigate→`get_page_content`→`take_screenshot`→`close_instance`→`list_instances` 为空）**未执行**，**无截图**。
- 明确不做的三件事：不用 SDK/stdio 探针冒充 DSH 内调用；不把 C 的 `06_call_chain_screenshot.png`（stdio 来源）当成本会话证据；不改配置试图"刷新"工具表。
- 结果：**PENDING**，需主 GUI 普通会话复测（见 §7）。
- 附带只读复核（不改变结论）：用 `read_image` 看过安装者 C 的 `stealth-browser\06_call_chain_screenshot.png` —— **1258×702、49,944 B、sha256 `84c2462a33b538eaf4243476b0bc4aa347b2f946ea8144b92a1c686982e97d55`**，画面是 example.com **现版多语言说明页**（与计划 v4"现页已是多语言说明、不要求经典 Example Domain 大标题"的说明一致），不是占位图/空白页。这说明 **stdio 探针链路确实渲染过真实网页**，但**它仍不是本会话 DSH 模型级调用的产物**，因此 `screenshot` 判据保持 PENDING，不用它冒充。

## 5. 业务基线与冻结文件

- 本会话**唯一写目标**：`docs/validation/dsh-tooling/verification/`（本目录）。未对 `instance/`、`app/`、`tests/`、`docs/design/CONTRACT.md`、迁移文件发起任何写操作。
- **未用 SQL 打开业务库**；未读写日常 Chrome profile/Cookie；未导入任何凭据。
- **未独立复算 sha256**（无 shell、无 hash 工具）。因此"业务库/冻结文件 hash 不变"本轮**不给出 PASS**，只能给出"本轮未触碰"的行为证据；既有快照（`instance/app.db` = `E073F828…4EB85`、CONTRACT `826C24CC…`）仍由 B/C 证据支撑，且本会话未改动它们。
- 同理，安装者清单里对 `INSTALLATION.md` 等自身的 hash 是转码前历史快照，**当前 manifest 需由有 shell 的会话重算**（本轮无法提供）。

## 6. 边界与未触碰清单

未安装/卸载任何软件；未改 `cordis.patch.yml`、`package.json`、Skill、repo、venv；未重启/结束任何 DSH 实例；未开新 DSH；未建子代理；未改 Flow 策略或白名单；未购买服务；未做发布/私信/采购/付款；未做站点级反爬测试。

## 7. 需要用户主会话做的最小验证（可粘贴）

> 请在**主 GUI 的普通会话**（非 Flow 执行者角色、带正常工具权限）中依次执行，并把每步原始输出回贴：
>
> 1. `skill(name="agent-reach")` —— 期望：返回 Agent Reach 的 SKILL.md 正文。若报"工具不存在"，说明该会话没有 skill 工具；若报"角色不允许"，说明是角色过滤。
> 2. `skill(name="stealth-browser-mcp")` —— 期望：返回 Stealth Browser MCP 的 SKILL.md 正文。
> 3. 终端（cwd=`D:\桌面\two`）：`C:\Users\19183\.agent-reach-venv\Scripts\agent-reach.exe --version` → 期望 `Agent Reach v1.5.0`，记真实 exit。
> 4. `...\agent-reach.exe doctor --json` → 记真实 exit 与各渠道 status。
> 5. 无账号搜索：`C:\Windows\System32\curl.exe -sS --max-time 25 -H "User-Agent: Mozilla/5.0" -H "Referer: https://www.bilibili.com/" "https://api.bilibili.com/x/web-interface/search/type?search_type=video&keyword=AI"` → 期望 `"code":0`，记真实 exit。
> 6. 浏览器链路：调用 `mcp__stealth__spawn_browser`（headless=true）→ `mcp__stealth__navigate` 到 `https://example.com` → `mcp__stealth__get_page_content`（核对 URL/title/正文）→ `mcp__stealth__take_screenshot` → `mcp__stealth__close_instance` → `mcp__stealth__list_instances`（应为空）。把截图文件路径与截图本身回贴。
> 7. 若第 1/2/6 步工具仍不出现：在该会话里确认 `flow`/角色白名单是否对该会话生效，并回报"哪一层缺"（catalog / registry / 函数表）。

## 8. 回滚要点（静态复核）

- **最小回滚**：只删 `C:\Users\19183\.dsh\profiles\desktop\cordis.patch.yml` 第 364–383 行（空行 + 注释 + 单个 `- insert:` 块），保留上方全部条目。
- **不要**整体还原 `cordis.patch.yml.pre-stealth-20261021T132904Z`（363 行）：若该文件之后还有别的改动，整体还原会连带回退。备份仍在，可 diff 使用。
- Agent Reach：删 `C:\Users\19183\.dsh\skills\agent-reach` 与 `C:\Users\19183\.agent-reach-venv`；无 PATH/代理/全局包改动需要还原。
- stealth：删 Skill 目录；需要时再删 `C:\Users\19183\.dsh\tools\stealth-browser-mcp`（repo/venv/profiles）。
- 备份齐全：[03](03_static_install_check.json) 列出 5 个备份文件均存在（stealth 3 + agent-reach 2）。

## 9. 本轮证据清单（全部本会话自写，UTF-8）

| 文件 | 内容 |
| --- | --- |
| [01_session_tool_table.json](01_session_tool_table.json) | 21 个函数清单、缺失项、三层分离、角色信号 |
| [02_catalog_observed.txt](02_catalog_observed.txt) | 本会话 skill catalog 原始条目 |
| [03_static_install_check.json](03_static_install_check.json) | 版本/路径/Skill 文件/配置 delta/备份/回滚 |
| [04_native_capability_probe.md](04_native_capability_probe.md) | 原生 skill/MCP/shell 探针与精确阻塞层级 |
| [05_public_read_commit.json](05_public_read_commit.json) | 独立公开读取（HTTP 200）与结论 |
| [06_public_search_sources.json](06_public_search_sources.json) | 无账号搜索来源清单与限制 |
| [07_native_call_attempt.md](07_native_call_attempt.md) | 为何"未暴露"≠"被拒绝"≠"返回空"；一次尝试的结论与不做替代执行的理由 |

- 本报告目录内文件均由 `write` 生成（UTF-8、LF）；**本会话无法自算 sha256**，请策划或有 shell 的会话补一份 `manifest.sha256`。
- 每条"未执行"都写明原因（无调用面），不以"不适用"掩盖。

## 10. 本轮明确缺口（不宣称完成）

1. 原生 `skill` 加载：PENDING（未暴露）。
2. CLI 复跑与真实 exit：PENDING（无 shell）。
3. DSH 原生 MCP 调用链 + 截图 + 实例清理：PENDING（未暴露）。
4. 业务库/冻结文件 hash 独立复算：PENDING（无 hash 工具），仅有"未触碰"行为证据。
5. 当前工作树/清单的 `manifest.sha256`：PENDING，需有 shell 的会话生成。
