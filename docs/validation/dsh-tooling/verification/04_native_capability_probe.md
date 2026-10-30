# 原生能力探针记录（Session A / 独立核验）

- 记录时点（UTC）：2026-10-21T13:50:57Z（本地 21:50:57 +08:00）
- 会话：`session-2ec5f901-e129-5a00-a488-80333567fa52`（Flow 执行者 A，非安装者，全新会话）
- 工作区/cwd：`D:\桌面\two`
- 方式：只读观察本模型步骤被注入的函数 schema + 只读观察 skill catalog；未使用 shell、未用脚本、未用其它代理或 Host.Tool 桥接。

## 1. skill 工具

- 结果：**本会话函数表中不存在 `skill`**（21 个可用函数见 `01_session_tool_table.json`）。
- 因此**没有发出** `skill(name="agent-reach")` / `skill(name="stealth-browser-mcp")` 调用：调用面不存在，发出即等于伪造一次不存在的原生调用。
- 与安装者 B 的形态不同：B 的会话里 `skill` 存在但被 Flow 拒绝（`Flow 当前角色不允许此工具；未知工具及其他代理/脚本通道默认拒绝`）；本会话是**未暴露**。

## 2. MCP 原生工具（mcp__stealth__*）

- 结果：**本会话函数表中不存在任何 `mcp__stealth__*`**，也不存在 `list_mcp_resources` / `read_mcp_resource`。
- 因此 spawn→navigate→get_page_content→take_screenshot→close 的原生链路**无法在本会话执行**，截图与实例清理证据不可能由本会话产生。
- 本会话**没有创建任何浏览器实例**，因此 `own-instance-closed` 判据为 **N/A（未创建，无需关闭）**；`profiles\verify-<UTC>` 未创建，未触碰 `profiles\chain1`，未读写日常 Chrome profile。

## 3. 命令执行面

- 结果：**本会话没有 shell / exec / powershell 函数**，因此 `agent-reach.exe --version / --help / doctor --json`、`curl` 公开读取与搜索**均未执行**。
- 可观测的角色信号：`flow_peers` 显示本执行者 `allowCommands=false`，同台其余 4 个执行者为 `true`。这是角色级可见事实，但**不足以证明**它就是 skill/MCP 缺失的唯一原因。

## 4. 精确层级（不混淆三层）

| 层 | 结论 | 依据 |
| --- | --- | --- |
| catalog 可见（DSH 技能发现面） | **PASS** | 本会话 available_skills 中出现 `agent-reach`、`stealth-browser-mcp` |
| registry 已登记（配置层） | **PASS（静态）** | `cordis.patch.yml` 第 365–383 行 insert 块存在且与安装记录一致；Host 侧 `Tool.listTools=21` 为安装者记录，本会话未复测 |
| 本会话模型函数暴露 | **未暴露** | 21 个函数里无 `skill`、无 `mcp__stealth__*`、无 shell |
| 模型级真实调用 | **PENDING** | 无调用面，未执行、未伪造 |

## 5. 成因判断的边界

"未暴露"只能说明**工具没有进入本会话的模型函数表**。究竟是：
1. Flow 角色过滤（`allowCommands=false` 一类的白名单机制），还是
2. 会话工具表生成时的快照/时序（全新会话仍沿用某次快照），还是
3. 其它登记→会话桥接原因，

**本会话内无法区分**，不做单一归因。需要在用户主 GUI 的普通非 Flow 会话中复测才能定性。

## 6. 未使用的通道（合规声明）

- 未用 SDK/脚本直接拉起 MCP server 冒充 DSH 内调用（安装者 C 的 stdio 证据不重复、不冒名）。
- 未调用 Host 内部工具（无该入口）。
- 未修改 Flow 策略、未改 DSH 配置/软件、未重启或结束任何 DSH 实例。
- 未建子代理/下级（本会话也没有该函数）。
