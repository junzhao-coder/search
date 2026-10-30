---
name: agent-reach
description: >
  MUST USE when the user asks to research, search, read, or look up anything on the
  internet (调研/搜索/查资料/看网页/搜帖子/看视频信息), or mentions a platform or URL:
  Bilibili/B站, GitHub, V2EX, RSS, web pages, Twitter/X, Reddit, YouTube, 小红书,
  Facebook, Instagram, LinkedIn, Boss直聘, 雪球, 小宇宙. Provides read-only web access
  through the locally installed Agent Reach CLI plus per-platform tools. Not for writing
  posts, comments, messages, purchases, or any account action; not for content editing.

metadata:
  homepage: https://github.com/Panniantong/Agent-Reach
  version: 1.5.0
  commit: 94f06c1969dfc1834001269d79d3ad0972d9dee6
  license: MIT
  installed_for: DeepSeek Harness (user-level skill root)
---

# Agent Reach（本机安装版 · 只读互联网访问）

> 安装：`C:\Users\19183\.agent-reach-venv`（隔离 venv，Python 3.12.10）+ 本 skill
> `C:\Users\19183\.dsh\skills\agent-reach\`。CLI 绝对路径：
> `C:\Users\19183\.agent-reach-venv\Scripts\agent-reach.exe`。
> 来源与版本：GitHub `Panniantong/Agent-Reach` commit `94f06c1969dfc1834001269d79d3ad0972d9dee6`（v1.5.0，MIT）。
> 本机安装记录见 `DSH-INSTALL-NOTES.md`（skill 根目录）；上游文档见 `references/install.md`、`references/README.md`。

## 常驻规则

1. **只读**：只做搜索/读取；**绝不**发帖、评论、点赞、私信、采购、付款、登录、导入 Cookie/账号/Key。用户要求写操作时明确拒绝并说明本 skill 只读。
2. **先体检**：多后端/登录态平台先运行 doctor（见下），按 `active_backend` 选命令；`active_backend` 为 null 不代表后端不存在，只代表 doctor 未实时验证。
3. **声明后端**：开始前说明"使用 agent-reach 的 X 平台 / Y 后端"；失败按 references 的重试链处理，不猜命令。
4. **不写入工作区**：临时文件放 `%TEMP%`；持久数据只在 `C:\Users\19183\.agent-reach\`（本安装未初始化可选渠道，目录可能不存在）。
5. **无账号优先**：默认使用无需账号的公开通道（B站搜索 API、GitHub 公开 REST、RSS、原始网页）；需要登录态的渠道当前**未配置**，不要索取凭据。

## 本机可用通道（doctor 快照 + 实测）

doctor（`--json`）结果（2026-10-21，完整见根目录 `DSH-INSTALL-NOTES.md`）：

| 通道 | doctor | 本机实测 | 用法 |
| --- | --- | --- | --- |
| bilibili | **ok**（B站搜索 API） | ✅ 搜索 API curl 直连成功（code=0，20 条） | 见下方 curl 命令（无需账号） |
| web | ok（Jina Reader） | ⚠️ `r.jina.ai` 本机超时（curl exit 28）；改用原始网页 curl 读取 | 见下方 raw 读取 |
| v2ex | ok（公开 API） | ⚠️ 本机 curl 超时（exit 28），未验证 | 需网络恢复后重试 |
| rss | ok（feedparser） | 未单独实测 | `python -c` + feedparser |
| github | warn（gh 已装、无显式认证） | ✅ GitHub 公开 REST 搜索可用（无需账号，限速） | 见下方 curl 命令 |
| twitter/reddit/facebook/instagram/xiaohongshu/linkedin/boss/xiaoyuzhou/xueqiu/exa_search | off/warn | **未配置**（需要账号/Cookie/Key 或额外安装） | 不要使用，不要索取凭据 |

> 说明：doctor 绿灯不等于实际可用（web/v2ex 本机超时）；以实际命令结果为准。

## 命令（Windows / PowerShell；全部使用绝对路径）

```powershell
# 版本 / 帮助 / 体检
& C:\Users\19183\.agent-reach-venv\Scripts\agent-reach.exe --version
& C:\Users\19183\.agent-reach-venv\Scripts\agent-reach.exe doctor --json

# B站公开搜索（无需账号；返回 JSON，含 title/bvid/arcurl）
& C:\Windows\System32\curl.exe -sS --max-time 25 `
  -H "User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124 Safari/537.36" `
  -H "Referer: https://www.bilibili.com/" `
  "https://api.bilibili.com/x/web-interface/search/type?search_type=video&keyword=QUERY"

# 公开内容读取（原始文件/页面；curl 可直接取文本）
& C:\Windows\System32\curl.exe -sSL --max-time 60 "https://raw.githubusercontent.com/OWNER/REPO/REF/PATH"

# GitHub 公开搜索（无需账号；REST 限速，勿高频）
& C:\Windows\System32\curl.exe -sS --max-time 30 `
  -H "User-Agent: agent-reach-dsh" -H "Accept: application/vnd.github+json" `
  "https://api.github.com/search/repositories?q=QUERY&per_page=5"

# GitHub 公开仓库信息（阅读）
& C:\Windows\System32\curl.exe -sS --max-time 30 `
  -H "User-Agent: agent-reach-dsh" "https://api.github.com/repos/OWNER/REPO"
```

- 需要把 JSON 解析为标题/链接时，用 venv Python：
  `& C:\Users\19183\.agent-reach-venv\Scripts\python.exe -c "import json,sys; d=json.load(sys.stdin); ..."`（stdin 传 JSON）。
- B站 API 返回的标题含 `<em class="keyword">` 高亮标签，展示前需去掉 HTML 标签。

## 按平台查阅 references

| 需求 | 文档 |
| --- | --- |
| 搜索（Exa/网页/代码） | [references/search.md](references/search.md) |
| 社交（B站/V2EX/Twitter/Reddit/小红书等） | [references/social.md](references/social.md) |
| 招聘（LinkedIn/Boss） | [references/career.md](references/career.md) |
| 开发（GitHub） | [references/dev.md](references/dev.md) |
| 网页/RSS | [references/web.md](references/web.md) |
| 视频/播客 | [references/video.md](references/video.md) |
| 金融（雪球） | [references/finance.md](references/finance.md) |

> references 是上游原文快照（commit 见 `SOURCE.md`），其中部分命令针对 bash/macOS；Windows 下请以上面的绝对路径命令为准，不要把 `bash`/`/tmp` 示例直接照搬。需要登录态/额外安装的渠道在当前环境**不可用**，不要尝试配置。

## 边界与限制

- 不提供写操作、不管理账号、不导入 Cookie/Key、不安装额外渠道（这些需要用户另行授权并另行验证）。
- 本机网络对部分服务受限（Jina/V2EX 超时）；失败时先如实报告 exit/错误，不伪造搜索结果。
- 搜索/读取结果必须附原链接与时间；不要把它当作已验证事实或经营结论。
- 上游工具很多，本机仅验证了 doctor + B站搜索 + 原始网页读取 + GitHub 公开搜索；其余按 doctor 为 off/warn，视为未就绪。
