# 真实端到端采集 + /dash 刷新报告

> 任务：`task-0ca037411f7a9b7de7f92486dfc196ae`（计划 v6 B5）。
> 结论：三源串行采集完成（X 30 / 闲鱼 20 / 小红书 20，exit=0）；scoring 与 sourcing 已用新批次重算；`/dash` 已刷新并做轻量视觉打磨；完整 **334 测试 exit=0**。

## 1. collect

| 平台 | 命令 | exit | 条数 | 时间（UTC） | 备注 |
| --- | --- | --- | --- | --- | --- |
| X | `e2e/tools/collect_search.py --keyword "notion template" --limit 30 --interval-min 8 --interval-max 12` | **0** | 30 | 08:42:21–08:44:55 | f=top；批次独立 `x_seen.jsonl`；146.7s；52 duplicates |
| 闲鱼 | `tools/platform-login/login_and_search.py --platforms xianyu --profile profile --wait 45` | **0** | 20 | 08:46:26–08:47:03 | `unb` 登录态检测；页面检测 30 条，脚本只保存 20；无验证码 |
| 小红书 | `tools/platform-login/login_and_search.py --platforms xiaohongshu --profile profiles/xhs --wait 45` | **0** | 20 | 08:48:33–08:49:08 | `web_session` 检测；页面检测 27 条，脚本只保存 20；无验证码 |

- 轮间：X→闲鱼 **91s**、闲鱼→小红书 **90s**（≥60s）；三个 profile 均复用，未重新登录。
- 原始数据：`data/x_search.jsonl`、`data/xianyu_items.jsonl`、`data/xiaohongshu_items.jsonl`；日志 `logs/x_search.log`、`logs/xianyu_run.log`、`logs/xhs_run.log`、`logs/platform_login.log`。控制台原始捕获含 cp936 转码伪影，已不纳入证据；以上述 UTF-8 运行日志和源 JSON 为准。
- 未点击任何互动/下单；x-collect 与 platform-login 脚本未改。

## 2. recompute（批次策略：替换 + 明确复用）

**不静默混用**：本批次替换 X 评分行与闲鱼价格信号；B站/GitHub 行复用已验收 scoring 批次；sources.csv 14 条保持不变。旧文件备份在 `data/previous/`。

- scoring：`items.jsonl` **60 条**（X 30 新批次 + B站 20 + GitHub 10 复用）；`scores.csv` 60 行；`report.md` 重算。Top1 不变（`x:1467843989533442054`, 0.800），Top2 变为 `x:1674662364057317382`（0.790）。
- sourcing：`price_signals.csv` **20 行**（新闲鱼批次）；`opportunity_sourcing_top10.csv` **10 行**，使用 **5 个不同源码**（gh-10/gh-13/gh-11/gh-03/gh-12）；`sources.csv` 不变（14 条，8 可商用/1 需授权/5 不明）。
- 价格：有效价 **¥1.00–1.88**；参考价 **3/20**（9.89/9.9/699）；wants **16/20**（3–2519，合计 8093），仅兴趣代理。
- 哈希/批次：`run_manifest.json`（三源条数/exit/UTC、输入输出 sha256、policy、间隔、编码结论、测试）。

## 3. encoding（乱码结论）

- 对 `data/*.jsonl`、`scoring/items.jsonl+scores.csv`、`sourcing/price_signals.csv+opportunity_sourcing_top10.csv` 逐文件扫描：**U+FFFD = 0**，全部可按 UTF-8 严格解码（`encoding_scan.json`）。
- 5 个 `/dash` 页渲染结果同样 **U+FFFD = 0**。
- 结论：**不是 CSV 读写编码或模板转义问题**。标题中的 `•ଓ.°`、`*̥₊˚‧☆ﾐ` 等是源推文自带的装饰性 Unicode/组合字符，属**源数据字体渲染差异**；按任务要求不修改源数据。已在 dash 样式加入 emoji 字体回退与换行，减少“看起来像乱码”的观感。
- 数据读取仍用 `utf-8-sig`（CSV）与 `utf-8`（JSONL），Jinja 默认转义；未发现可修复的编码 bug。

## 4. ui（只改 dash 模板，克制）

- 字体栈加入 `Segoe UI Emoji / Noto Color Emoji`，表格链接 `word-break`。
- 统一层级：H1 24px、H2 18px、表头 12px/600；主容器 1180px、24px 留白。
- 卡片：左侧 3px 强调线、hover 轻阴影、数字 24px。
- 表格：sticky 表头、斑马纹、hover、行高 1.5、单元格 padding 7/9。
- 徽章：可商用/需授权/不明统一底色、字重、圆角；空状态/错误状态统一虚线/浅底。
- 元信息条改为浅底卡片；新增 640px 以下媒体查询。
- **未改旧页面样式**；只改 `templates/dash/base.html`。

## 5. test / shots

- 命令：`.\.venv\Scripts\python.exe -m unittest discover -s tests -v`
- **exit=0**；`Ran 334 tests in 49.162s` → **OK**（`logs/test.log`）。
- 截图（1440×1400，无头 Chrome，端口 5010，临时 DB，已停止并清理）：
  - before：`shots_before/{overview,collect,opportunities,sources,daily}.png`（旧批次/旧样式）
  - after：`shots_after/{overview,collect,opportunities,sources,daily}.png`（新批次/新样式）
  - 清单/哈希：`shots_manifest.json`
- 典型对比：before Top2 `@worksfess`，after Top2 `@mareidaily`；封面/表格/徽章视觉层级已统一。

## 6. hashes

`hash_check.json`：

- 业务库 `instance/app.db` = `e073f828…`（same）；wal/shm=false。
- CONTRACT `826c24cc…`、requirements、冻结三、real_link 均 same。
- `x_collect` sha `5b1441…`、`login_and_search.py` sha `e27d97…`（未改）。
- 输入/输出哈希见 `run_manifest.json`；旧批次备份在 `data/previous/`。

## 7. limits

1. **混合批次**：X 是新采集；B站/GitHub 复用上一批已验收数据（已在 manifest/report 标注），不是三源全新鲜。
2. 闲鱼/小红书脚本页面检测到 30/27 条，但脚本固定只保存前 20；小红书 `price=null`，未用于价格。
3. 闲鱼 ¥1 为引流价，参考价仅 3/20；wants 是兴趣代理，不是订单；毛利仍为区间估计。
4. X f=top 含历史高互动旧帖；新批次独立 seen 仅用于本批次去重。
5. 视觉修改限于 dash 模板；未做移动端逐页截图回归。
6. 标题装饰性 Unicode 可能因字体显示为方块/组合符，源数据无 U+FFFD；未改源数据。
7. 未发布/点赞/关注/私信/下单；未改 x-collect/platform-login 脚本、业务库、CONTRACT、旧页面样式。
