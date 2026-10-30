# V10-3 修复后真实运行（证据纠正版）：未复现挂死，搜索 0 记录、原因未判定

> 任务 `task-b3be4befc53006c538fc2f759eb22e0b`（rev5，计划 v10）。
> 执行时间 2026-10-27 17:55:52–17:55:54 UTC+8（09:55:52–09:55:54Z）。
> **恰好 1 次真实调用**、全新 state-dir `runtime_live3` + 新批次 `zhihu-live-3`；未重试、未换词、未换 mode、未改产品代码、未装依赖、未代填、未读 cookie 值。
> 本版为**证据纠正版**：修正了上一版的编码判定与两处过度断言；原始字节未改动。

## 1. 编码与证据转存（本地转换，未执行采集器）

| 项 | 值 |
| --- | --- |
| 原件 | `live_search_4.out.txt`，604 B，sha256 `ece8fcf2ddb11c57d40d5f4d53ba0cb26ec677073799603abe325240392a7140`（**字节未改动**） |
| BOM | **无**（前 4 字节 `7B 22 62 61`） |
| 源编码 | **gb18030**（GBK 系列） |
| 判定依据 | ①utf-8 strict 解码**失败**（偏移 283 处 0xD7）；②gb18030 解码后是**合法 JSON** 且 `keyword` 精确等于 `学习计划模板`；③big5/cp932/latin-1 等候选被 JSON 结构或 keyword 校验否决。**latin-1 未被采信**（它可解码任意字节，不能作为来源证据） |
| 转换方法 | 以 gb18030 **无 errors=ignore 抑制**解码 → 重新编码为 UTF-8（无 BOM）；原件字节不动 |
| UTF-8 副本 | `live_search_4.out.utf8.txt`，612 B，sha256 `587d92d23bb3f86e035dfc247b2fa323ab4e49c4174e7c66d406a8c062607e94` |
| 判定记录 | `live_search_4.encoding.json`（含各候选的尝试与结论） |
| run 元数据（UTF-8） | `live_search_4.run.json`（argv/cwd/PYTHONPATH/UTC/exit/两种超时是否触发） |
| budget 原件（UTF-8） | `live_search_4.budget.json`（sqlite 只读导出：budget + ledger） |

## 2. 观测事实（白描，不含推断）

| 项 | 值 |
| --- | --- |
| argv | `C:\Users\19183\.dsh\tools\x-collect\venv\Scripts\python.exe -m tools.selection.access.zhihu --state-dir docs\validation\v10\zhihu\runtime_live3 --batch-id zhihu-live-3 --mode authenticated-browser --profile C:\Users\19183\.dsh\tools\zhihu-collect\profile search 学习计划模板 --limit 5` |
| cwd / PYTHONPATH | `D:\桌面\two` / `D:\桌面\two` |
| started_utc / finished_utc | **2026-10-27T09:55:52Z** / **09:55:54Z** |
| elapsed_s（batch 内） | **1.529** |
| **exit** | **3** |
| **stop** | **`empty`** |
| **count / records** | **0 / 0** |
| **parsed_structure** | **`html:links`** |
| risk_reason | 无 |
| final_url | 输出中无该字段（0 记录时未落地） |
| stderr | 0 字节 |
| ledger | 2 条：`charge {kind:"search", detail:"https://www.zhihu.com/search?type=content&q=…"}` + `search_result {count:0, exit:3}` |
| 锁 | `locked=0`、`lock_reason=null` → **锁未命中**（无 403/429/登录墙判定记录） |

## 3. 超时保护：两层均未触发

| 保护 | 是否触发 | 依据 |
| --- | --- | --- |
| 180 秒外部超时（执行侧） | **未触发** | 命令 1.53 秒自行返回 |
| `asyncio.wait_for` 硬超时（transport 内） | **未触发** | 输出是 `stop=empty` 的正常解析路径，不是 `browser:TimeoutError` |

- 因此只能得出：**本次运行未复现此前的挂死**（修复前为 44 分钟挂死、exit=-1、stdout 0 字节；本次 1.53 秒返回并产出完整 JSON）。
- **不能**得出“硬超时机制已被真实触发并验收”——该路径本轮未被走到。

## 4. 原因：未判定（可检验假设）

`parsed_structure=html:links` 只说明进入了 `parse_search_html`；按代码实读，`parse_search_html` 对**任意字符串（含空白）**都返回该标签，且 `_Links` 在形成候选记录**之前**就过滤路径。因此该标签**不证明**搜索结果已就绪，也**不证明**存在任何异形链接。

可检验假设（均未验证）：

| # | 假设 | 可检验方式（需另行派发） |
| --- | --- | --- |
| A | **SPA 未就绪**：`browser.get` 后立即 `get_content`，没有 readyState / 结果渲染等待（`transport.py:207-215`） | 等待 `document.readyState`/结果容器出现后再取 HTML |
| B | **登录墙/空壳未识别**：页面是登录墙或空壳，但未触发既有风控标记 | 保存脱敏快照，离线判定页面实际内容 |
| C | **DOM 链接形态差异**：真实结果的链接形态与 `url_identity` 白名单（`/question/<qid>/answer/<aid>`、`/p/<id>`、`/zvideo/<id>`、`/question/<qid>`）不匹配，而 `_Links` 先过滤，链接总数未知 | 保存脱敏快照后统计链接形态与被过滤数 |
| D | **最终地址未知**：`location.href` 读取失败会回落到输入 url（`transport.py:213-214`），掩盖真实落地域 | 记录跳转链/最终 URL，失败时显式标记 unknown |

- 本轮**未保存页面 HTML**（transport 只返回文本、不落盘），上述任一假设都无法离线验证；补齐需要再发请求或新增“脱敏快照”能力，均超出本轮授权。

## 5. 批次与预算状态（历史累计 ≠ 可直接调用）

- `runtime_live3`：本批 `calls=1`、`calls_max=3`、`records=0`、`locked=0`；批次 300 秒窗口自 `started_at` 起算，本批已用 1.53 秒，**窗口会随时间过期**。
- 因此“剩余 2 次”是**计数意义上的剩余**，**不等于**未来可直接调用的有效预算：窗口过期后同 state-dir 会返回 `budget:time_exhausted`（参见 `LIVE_SEARCH_3.md` 的同类现象）。
- 历史累计：匿名 public-http 一次（403 锁停，`runtime_live`）；authenticated-browser 一次（挂死，`runtime_live2`，已停）；本次一次（`runtime_live3`）。
- 按约束**未换目录重新发请求**。

## 6. 结论

- ✅ 本次运行**未复现挂死**（1.53 秒返回、产出完整 JSON），与修复方向一致；但两层超时保护均未触发，硬超时路径**未获真实验收**。
- ❓ **“登录后知乎搜索是否可读”仍不可判定**：本轮 0 记录，原因未判定（见 §4 假设 A–D），不将知乎搜索判为可用。
- 本任务仅**验收取证**，不改判平台能力。

## 7. 声明

- **只执行 1 次真实调用**、用的是**全新 state-dir**（`runtime_live3`）+ 新批次（`zhihu-live-3`）；未重试、未换关键词、未换 mode、未改产品代码/测试/期望值。
- 编码转换是**本地文件操作**，未执行采集器、未发请求；原 stdout 字节与 sha256 保留。
- 未装依赖、未代填凭据、未读取/输出 cookie 值、未写业务库/CSV/CONTRACT、profile 未入仓库。
