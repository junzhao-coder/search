# 来源与版本（Source provenance）

- 上游仓库：https://github.com/Panniantong/Agent-Reach
- 固定 commit：`94f06c1969dfc1834001269d79d3ad0972d9dee6`（main HEAD，抓取时点 2026-10-21；提交时间 2026-10-07T17:17:26Z）
- 版本（pyproject）：**1.5.0**
- 许可证：**MIT**（原文见同目录 `LICENSE`，版权行保留）
- 安装来源：`https://codeload.github.com/Panniantong/Agent-Reach/tar.gz/94f06c1969dfc1834001269d79d3ad0972d9dee6`
- 安装命令（隔离 venv）：
  `C:\Users\19183\.agent-reach-venv\Scripts\python.exe -m pip install --no-cache-dir "https://codeload.github.com/Panniantong/Agent-Reach/tar.gz/94f06c1969dfc1834001269d79d3ad0972d9dee6"`
- 依赖（base extras，未安装 browser/playwright）：requests、feedparser、python-dotenv、loguru、pyyaml、rich、yt-dlp[default]（实际解析版本见 `DSH-INSTALL-NOTES.md` 或 pip 日志）。

本 skill 目录中的内容：

| 文件 | 来源 |
| --- | --- |
| `SKILL.md` | 上游 `agent_reach/skill/SKILL.md` 的**再创作**（保留平台路由与只读纪律，改为 DSH/Windows 绝对路径，并补充本机实测状态） |
| `references/*.md` | 上游 `agent_reach/skill/references/` 原样快照（career/dev/finance/search/social/video/web） |
| `references/install.md` | 上游 `docs/install.md` 原样快照 |
| `references/README.md` | 上游 `README.md` 原样快照 |
| `LICENSE` | 上游 `LICENSE` 原样 |
| `DSH-INSTALL-NOTES.md` | 本机安装记录（新增，非上游） |

未把上游代码复制进本 skill；CLI 由 pip 安装到独立 venv。上游 brand/名称归其作者所有；本目录仅用于本机安装的来源留存与回滚。

## 本目录修订

- 2026-10-21 rev5：`SKILL.md` 第 25 行本机安装记录引用由 `references/DSH-INSTALL-NOTES.md` 修正为根目录 `DSH-INSTALL-NOTES.md`（该文件实际位于 skill 根目录）；其余内容未变。
