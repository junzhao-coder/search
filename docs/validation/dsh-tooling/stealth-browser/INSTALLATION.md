# Stealth Browser MCP — 安装与接入记录（DSH 本地 stdio）

> 安装执行者：C（`session-48004521-daf2-548c-a355-487cc6de6e72`）｜任务 `task-fb8e9c8c8ba064c6e9db93d9749fead9`（计划 v4）
> 时间：2026-10-21（UTC 13:20–13:35 区间，逐条见证据文件）
> 本文档只记录**已发生的事实**；未验证项在 §9 明列，不宣称"接入完成"。

## 1. 固定版本与来源

| 项 | 值 |
| --- | --- |
| 上游仓库 | `https://github.com/vibheksoni/stealth-browser-mcp` |
| 固定 commit | `aa6cc9f6f853d6cbc17e4dc9b7946d406caabc6f`（master，2026-10-19T19:23:19Z，"Merge pull request #37 …"） |
| 包版本 | `0.2.5`（`pyproject.toml`），要求 `>=3.10` |
| LICENSE | MIT（仓库 `LICENSE`，1091 B） |
| 下载物 | `https://codeload.github.com/vibheksoni/stealth-browser-mcp/tar.gz/aa6cc9f6…` → 20,215,037 B，sha256 `ea706f805b92d8a82d7c1239f9f045c0c370c37b868f4fd27e0431e8b2130219`（见 `02_download.log`） |
| 落盘位置 | `C:\Users\19183\.dsh\tools\stealth-browser-mcp\repo\`（解包后去掉顶层目录） |

网络说明：本机 WinHTTP 为直连，WinINET 有系统代理 `127.0.0.1:10808`；`git ls-remote` 直连失败，改用 `Invoke-WebRequest`（走系统代理）按 commit 下 tarball，实现同样的"固定 commit"效果。pip 安装前显式设置 `HTTP_PROXY/HTTPS_PROXY=http://127.0.0.1:10808`。

## 2. 独立环境

| 项 | 值 |
| --- | --- |
| 解释器（建 venv 用） | `C:\Users\19183\AppData\Local\Programs\Python\Python310\python.exe`（3.10.9） |
| venv | `C:\Users\19183\.dsh\tools\stealth-browser-mcp\venv`（3.10.9，pip 22.3.1） |
| venv python | `C:\Users\19183\.dsh\tools\stealth-browser-mcp\venv\Scripts\python.exe` |
| 安装命令 | `venv\Scripts\python.exe -m pip install --no-input -r repo\requirements.txt` → **exit 0**（完整可读副本 [03_pip_install.log.utf8.txt](<03_pip_install.log.utf8.txt>)；原件 `03_pip_install.log` 为 PowerShell 三段混合编码，见 §11） |
| 关键版本 | fastmcp 2.11.2、nodriver 0.47.0、pydantic 2.11.7、py2js 1.2.1（git 固定 commit 源）、pillow 11.3.0、psutil 7.0.0、requests 2.33.1、uvicorn 0.35.0；完整 77 行见 `04_pip_freeze.txt` |

- 未安装到工作区 `.venv`，未安装到 DSH bundled site-packages，未改 PATH，未自动更新浏览器。

## 3. 浏览器与隔离

| 项 | 值 |
| --- | --- |
| 浏览器 | `C:\Program Files\Google\Chrome\Application\chrome.exe`（另检测到 Edge：`C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe`，未使用） |
| 选定方式 | 通过 env `STEALTH_BROWSER_EXECUTABLE` 固定，不依赖自动探测 |
| 专用 profile | `C:\Users\19183\.dsh\tools\stealth-browser-mcp\profiles\chain1`（调用时用 `user_data_dir` 显式指定，不写 `%TEMP%\uc_*`） |
| 孤儿 profile 清扫 | 设 `BROWSER_ORPHAN_PROFILE_MAX_AGE=0`。**代码依据**：`src/process_cleanup.py:531–532` — `if self.orphan_profile_max_age_seconds == 0: return 0`，即启动时不做 `%TEMP%\uc_*` 全量清扫；默认值 21600s 时才会扫（`:524–566`） |
| 文件上传白名单 | `BROWSER_FILE_UPLOAD_ALLOWED_DIRS=C:\Users\19183\.dsh\tools\stealth-browser-mcp\profiles\uploads`（空目录，未指向个人文件/业务工作区） |
| 未启用 | HTTP transport / 公网监听 / 认证 token / 101 全套 / CDP 与动态网络改写钩子（用 `--minimal`，仅核心段） |
| 私人数据 | 未读取用户日常 Chrome profile、Cookie 或账号 |

## 4. 启动方式（stdio，`--minimal`）

```
command : C:\Users\19183\.dsh\tools\stealth-browser-mcp\venv\Scripts\python.exe
args    : C:\Users\19183\.dsh\tools\stealth-browser-mcp\repo\src\server.py --minimal
cwd     : C:\Users\19183\.dsh\tools\stealth-browser-mcp\repo
env     : STEALTH_BROWSER_EXECUTABLE, BROWSER_ORPHAN_PROFILE_MAX_AGE=0,
          BROWSER_FILE_UPLOAD_ALLOWED_DIRS, STEALTH_BROWSER_DEBUG=0, PYTHONIOENCODING=utf-8
```

- 正常日志走 stderr；本次实测 stdout 仅承载 MCP JSON-RPC（`05_tools_list.json`、`06_call_chain.json` 均为单行 JSON 结果）。
- 精简工具集实测：`--minimal` → **21 个工具**（与 README 宣称一致）。

## 5. 本地 stdio 握手实证（未经由 DSH）

- 脚本：`C:\Users\19183\.dsh\tools\stealth-browser-mcp\probe_stdio.py`（用 venv 里的 `mcp` 客户端，按上表 command/args/env/cwd 拉起）
- 结果：`initialize` 成功，`protocolVersion=2025-11-25`，`serverInfo.name="Browser Automation MCP"`；`tools/list` = **21** 个工具，名称见 `05_tools_list.json`（`spawn_browser`、`list_instances`、`close_instance`、`get_instance_state`、`navigate`、`go_back`、`go_forward`、`reload_page`、`query_elements`、`click_element`、`type_text`、`paste_text`、`press_key`、`file_upload`、`select_option`、`get_element_state`、`wait_for_element`、`scroll_page`、`execute_script`、`get_page_content`、`take_screenshot`）；**exit 0**。
- 真实链路（同一 command/args/env/cwd）：`spawn_browser` → `navigate https://example.com` → `get_page_content`（正文含 `Example Domain`）→ `take_screenshot`（`file_path` 落盘）→ `close_instance` → `list_instances` 返回 `[]`；**exit 0**（`06_call_chain.json`）。
- 截图：`06_call_chain_screenshot.png`，49,944 B，PNG magic `89504e470d0a1a0a`，1258×702（已用 `read_image` 目视确认是 example.com 真实渲染）。
- 关闭清理：链路结束后 `chrome_after=[]`（无本工具遗留 chrome 进程），profile 目录保留在自有 tools 目录内。

## 6. DSH 正式登记（当前实例）

- 登记位置：**live profile 的 patch 层** `C:\Users\19183\.dsh\profiles\desktop\cordis.patch.yml`（该文件头注明它就是"user patch layer"，`patchReload: live`）。
- 追加的注册行（`07_patch_apply.json` 记录前后：6 → 7 条）：

```yaml
- insert:
    - id: stealth-browser-mcp
      name: "@deepseek-ai/dsh-mcp-client"
      config:
        serverName: stealth
        transport: stdio
        command: "C:\\Users\\19183\\.dsh\\tools\\stealth-browser-mcp\\venv\\Scripts\\python.exe"
        args: ["…\\repo\\src\\server.py", "--minimal"]
        cwd: "…\\repo"
        env: { STEALTH_BROWSER_EXECUTABLE: "…chrome.exe", BROWSER_ORPHAN_PROFILE_MAX_AGE: "0",
               BROWSER_FILE_UPLOAD_ALLOWED_DIRS: "…\\profiles\\uploads", STEALTH_BROWSER_DEBUG: "0",
               PYTHONIOENCODING: "utf-8" }
        failOnStartupError: true
```

- **未使用**非正式手段：没有改 DSH 核心、没有手改 `cordis.yml`、没有塞 `node_modules`、没有覆写其它插件/MCP 配置、没有碰 AgentReach 目录与技能。
- **同名检测**（写入前）：`C:\Users\19183\.dsh\tools\stealth-browser-mcp` 不存在；patch 内既无 `serverName: stealth`，也无其它 `dsh-mcp-client` 行（`existing_mcp_servers: []`）；`DSH_HOME\skills\stealth-browser-mcp` 不存在。
- **备份**：
  - `C:\Users\19183\.dsh\tooling-backups\stealth-browser\20261021T132001Z\`（`package.json`、`cordis.patch.yml` 原件）
  - `C:\Users\19183\.dsh\tooling-backups\stealth-browser\cordis.patch.yml.pre-stealth-20261021T132904Z`（写入前一刻副本）

### 6.1 登记后的实证

| 检查 | 结果 |
| --- | --- |
| Host `Config.listConfigs`（`@deepseek-ai/dsh-mcp-client`） | 返回 `include:stealth-browser-mcp`，`patchId=stealth-browser-mcp`，`status=schema`（行已在 live Loader） |
| Host `Tool.listTools`（本 Agent 可见工具） | 出现 **21** 个 `mcp__stealth__<raw>`，与 stdio 的 21 个一一对应（`08_live_state.txt` 记录了该次统计来源） |
| DSH 是否真的拉起了服务 | 运行中进程 `pid=122680`（父 `97764` = DSH 宿主）`venv\Scripts\python.exe …\server.py --minimal`，另有子进程 `108032`（同一命令的启动 shim） |
| 热加载 | 未重启 DSH：写入 patch 后约数秒，行与工具即在 live 实例可见（`patchReload: live`） |

## 7. Skill

- 已安装：`C:\Users\19183\.dsh\skills\stealth-browser-mcp\SKILL.md`（4,005 B，sha256 `9c48bf657f87918d7856d5e29b8bbd1394e6981f5b7f032446459080009824d6`）＋ `agents\openai.yaml`（197 B），来源为仓库 `skills/stealth-browser-mcp/`。
- 可发现性：本会话的 Skill 目录已出现 `stealth-browser-mcp` 条目（描述与仓库 SKILL.md 一致）。
- 未安装仓库里其余非必需 skill/reference（`--minimal` 之外的能力不需要）。

## 8. 卸载 / 回滚（按顺序）

1. **停服务**：结束 DSH 侧登记（见第 2 步）后该 stdio 进程随之退出；如需立即手动结束：`Stop-Process -Id 122680`（先确认 `CommandLine` 含 `stealth-browser-mcp`，只杀自启 PID）。
2. **撤登记**：把 `cordis.patch.yml` 恢复到
   `C:\Users\19183\.dsh\tooling-backups\stealth-browser\cordis.patch.yml.pre-stealth-20261021T132904Z`
   （或删除文件末尾 `# --- stealth-browser-mcp …` 起的那个 `- insert:` 块）。恢复后 live 实例会自动卸载该行。
3. **删 Skill**：删除 `C:\Users\19183\.dsh\skills\stealth-browser-mcp\`。
4. **删运行物**（可选，确认没有其它引用后）：删除 `C:\Users\19183\.dsh\tools\stealth-browser-mcp\`（含 repo、venv、profiles）。
5. 核对：`Config.listConfigs` 不再有 `stealth-browser-mcp`；`Tool.listTools` 不再有 `mcp__stealth__*`；无残留 `python.exe … server.py --minimal`。

## 9. 未验证 / 限制（不宣称接入完成）

1. **DSH 会话内的模型级调用链未跑**：MCP 工具已登记且对 Agent 可见（Host `Tool.listTools` 明确列出 21 个 `mcp__stealth__*`），但**本会话的模型函数表未包含**这些名字（`skill`/`plugin_manager` 也未出现在本会话函数表中）——这是**会话工具表未刷新**，不是 Flow 拒绝；也未用脚本反向调用 host 工具（见 `10_permission_probe.md`）。需要**正式新会话**（或 GUI 刷新后的会话）跑一遍 spawn→navigate→正文→截图→close；本文件第 5 节的链路是**同一 command/args/env/cwd 的 stdio 实证**，不能替代 DSH 内调用。
   - 分类（与策划者核对口径一致）：**stdio 独立探针＝已做**；**DSH 登记＝已做**；**DSH 内实际调用＝待新会话**。
2. 截图 `06_call_chain_screenshot.png` 来自上述 stdio 链路，不是 DSH 会话内截图。
3. `03_pip_install.log` 是 PowerShell 5.1 造成的**三段混合编码**（`Out-File -Encoding utf8` 的 BOM 头两行 + `*>>` 追加的 UTF-16LE 正文 + `Out-File -Append -Encoding utf8` 的 ASCII 尾两行）。原件**保留不改**；完整规范副本 [03_pip_install.log.utf8.txt](<03_pip_install.log.utf8.txt>)（19,550 B、306 行、UTF-8 无 BOM/LF），其中包含真实 `PIP_INSTALL_EXIT=0` 与 `END_UTC=`；编码与等价判据见 §11。`03_pip_install_summary.txt` 只是关键行摘要，**不替代**该完整副本。
4. 未做 Cloudflare/反爬的站点级验证（README 自述"结果随站点/地区/版本而变"），本记录不背书任何绕过效果。
5. 未启用 HTTP transport、认证 token、CDP/动态钩子段；如需这些能力，属**范围扩展**，要另行确认。
6. 未验证多实例并发、长时间空闲回收（`BROWSER_IDLE_TIMEOUT`）的实行为。

## 11. 编码与转码记录（原件保留 + 完整规范副本）

方法：先做严格 UTF-8 解码判定；对非规范文件按**检测到的真实编码**解码（三段混合文件按锚点拆分：第 2 个 CRLF 结束 UTF-8 头、`PIP_INSTALL_EXIT=` 开始 UTF-8 尾），生成**完整** UTF-8 无 BOM + LF 副本；判据为「逐段重编码回原件字节相等」＋「文本等价（换行归一后）」双条件。逐件机器可读结果：[11_encoding_copies.json](<11_encoding_copies.json>)。

| 原件 | 形态 | 原件字节 | 原件 sha256 | 规范副本 | 副本字节 | 副本 sha256 | 判定 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `03_pip_install.log` | 3-part mix: utf-8-sig + utf-16-le + utf-8 | 39,428 | `0f536a6be42a801c013dfccaad0354844f94298e02ade61aa70958938acad1a4` | `03_pip_install.log.utf8.txt` | 19,550 | `5ef79e8ee8ed954d14fe26657b8cdc3506a543e441a69ac53b909b780a1e622e` | **equivalent** |
| `05_tools_list.json` | utf-8 with CRLF | 6,076 | `ad6b1d104097b4ec6b7a523e20f825c36c227ecbadaeb10ddf69b56cf8351847` | `05_tools_list.json.utf8.txt` | 5,939 | `09a413dba144885fb621fb9a450594e89a4a0db7bfdd037af8d7445fa25817bf` | **equivalent** |
| `06_call_chain.json` | utf-8 with CRLF | 3,093 | `eb2f992590af999c35622ea04ed951701f8ce73d4ea907524f5bcfba1d447cae` | `06_call_chain.json.utf8.txt` | 3,001 | `d6cdb17d65f9ff342c63eb40794f3ce4a518a72b47de543809e9a58890eb2c56` | **equivalent** |
| `10_permission_probe.md` | utf-8 with embedded NUL characters（4 个 NUL） | 1,917 | `8e9380a958a075cce0f5c31f3e8c838840f01339e9254b5b162da79784d9da87` | `10_permission_probe.md.utf8.txt` | 1,914 | `649ab9c4ddc3a63fddaeaf6d9ffdb3257b724c70093c25c4cc620b2049f714ab` | **equivalent** |

- 可读副本直链（报告内引用一律指向这些副本）：[03_pip_install.log.utf8.txt](<03_pip_install.log.utf8.txt>)、[05_tools_list.json.utf8.txt](<05_tools_list.json.utf8.txt>)、[06_call_chain.json.utf8.txt](<06_call_chain.json.utf8.txt>)、[10_permission_probe.md.utf8.txt](<10_permission_probe.md.utf8.txt>)。
- 其余 9 个文件（`01_baseline_hashes.json`、`02_download.log`、`03_pip_install_summary.txt`、`04_pip_freeze.txt`、`07_patch_apply.json`、`08_live_state.txt`、`09_post_hashes.json`、`11_encoding_copies.json`、`INSTALLATION.md`）本就为 **UTF-8 无 BOM + LF**，不生成副本。
- 可读副本里可见 `Successfully installed …`（77 个包）、真实 `PIP_INSTALL_EXIT=0` 与 `END_UTC=2026-10-21T13:25:49.7474613Z` —— **真实 exit 与失败原文未被摘要替代**（`03_pip_install_summary.txt` 仅为摘要，明确不替代完整副本）。
- `10_permission_probe.md` 原件含 4 个嵌入 NUL（读工具会按 binary 处理），副本为去 NUL 的等价文本；**原件保留不改**。

## 12. 独立核验的交接约定（决策 A）

- 策划已通过 Flow 建立**独立核验任务** `task-8b14f417fd9800b3512069581b1aa140`，由**正式新执行者会话** `session-2ec5f901-e129-5a00-a488-80333567fa52` 执行两工具核验；**本执行者不创建子会话/下级代理**，不修改 Flow 策略，不以脚本反向调用被拒或未暴露的 host 工具。
- 核验者将在 `C:\Users\19183\.dsh\tools\stealth-browser-mcp\profiles\verify-<UTC>` 建立**自己的** profile，与本记录的 `profiles\chain1` 互不影响。
- 本批**冻结**安装物：不修改 `repo`／`venv`／DSH patch 行／Skill；不重启 DSH；不新建浏览器实例。
- DSH 内模型级调用链仍为 **PENDING**，待独立会话回填；本文件不宣称接入完成。
