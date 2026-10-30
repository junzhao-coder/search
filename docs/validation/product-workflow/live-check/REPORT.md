# 5015 线上版本核对（live-check）

时间：2026-10-24T14:14Z 前后（本机 22:14）· 只读检查，未重启、未写数据。

## 结论

**在线，且是最新版本（D2 之后重启的进程）。**
`http://127.0.0.1:5015/` → `/healthz` **200**，`app_id=workbench-opportunity/1`；
监听进程 **99804**（父 **96704**），**启动时间 21:42:19**，晚于最后一次代码改动（`views_worksheet.py` 21:39:47），因此该进程加载的是最新代码。

## 1. 进程与健康

| 项 | 值 |
| --- | --- |
| 监听 | `127.0.0.1:5015`（仅本机），`LISTENING` 1 条 |
| 监听 PID | **99804** |
| 父 PID | **96704** |
| 子进程命令行 | `"…\.dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe" -X utf8 tools\workbench\run.py --port 5015 --no-browser` |
| 父进程命令行 | `"D:\桌面\two\.venv\Scripts\python.exe" -X utf8 tools\workbench\run.py --port 5015 --no-browser` |
| 启动时间 | 2026-10-24 **21:42:19** |
| `/healthz` | **200**，`app_id=workbench-opportunity/1`，含 `counts` 与 `generated_at=2026-10-22T11:21:59Z` |
| 启动日志 | `tools\workbench\runtime\workbench-5015.log`（横幅记录 PID 99804、地址、停止方式） |

## 2. 最新版本特征核对（线上实测）

| 特征 | 检查点 | 结果 |
| --- | --- | --- |
| 三栏导航只有 3 项 | `/pick` 主导航 | **`NAV=选品,选源,起草介绍`**；旧栏目（总览/机会线索/教程与内容/商品工作单/货源与价格/采集来源/每日快照）**均不出现**（`OLD_NAV=False`） |
| `/pick` 继续已有工作单 | `/pick` 区块 | **存在**（`CONTINUE_BLOCK=True`），且含生产单 `wo:20261023-88ef9a66` 的跳转链接 |
| `/copy` 有 `platform_evidence` 字段 + 取证提示 | `/copy?wo=…` | **`PLATFORM_FIELD=True`、`HINT=True`**（“不代表平台已批准”在页面） |
| `/copy` 发布回填指引 | `/copy?wo=…` | **`PUB_GUIDE=True`**（指向 `PUBLISH-CARD.md`）、**`NOAUTO=True`**（“系统不代发”） |
| `/worksheet` 文案版本提示 | `/worksheet/wo:…` | **200**，`COPY_VERSION_HINT=True`（“本页保存不生成文案版本”）、`COPY_LINK=True`（链到 `/copy?wo=…`） |
| `/source` 货源候选区块 | `/source?wo=…` | **200**，`SUPPLY_BLOCK=True` |
| 发布变更横幅「重新记录本次导出」 | 代码 + 隔离库截图 | 模板在已部署代码中（`RERECORD_TEMPLATE=True`）；生产单当前 **`PUBLISH_CHANGED=False`**（该单既无导出记录也无发布回填），故线上**不出现**该横幅——属预期状态，不是旧版本。按钮的实拍证据见 `d2/shots/worksheet_publish_rerecord.png`（隔离库造出变更态，sha `526c1ecae280…`） |

## 3. 代码与进程时间对照（证明不是旧进程）

| 文件 | 最后修改 | 说明 |
| --- | --- | --- |
| `views_worksheet.py` | 2026-10-24 **21:39:47** | D2：文案版本提示 + 重记按钮（最新改动） |
| `app.py` | 2026-10-24 20:27:54 | B22/B23：继续区块、platform 字段 |
| `views_wizard.py` | 2026-10-24 20:27:54 | B21/B24：三栏与发布指引 |
| 进程启动 | 2026-10-24 **21:42:19** | **晚于**上述全部改动 → 已加载最新代码 |

## 4. 如何刷新（如果你改了代码或想强制重载）

当前是**普通 Flask 进程，没有开启自动重载**（`--no-browser`，未设 debug/relaunch），所以**改代码后必须重启进程**：

```powershell
# 1) 只停本工具（按命令行精确匹配，不会误杀 DSH 或其它 python）
Get-CimInstance Win32_Process -Filter "Name='python.exe'" | Where-Object {
  $_.CommandLine -match 'tools\\workbench\\run\.py' -and $_.CommandLine -match '--port\s+5015' } |
  ForEach-Object { Stop-Process -Id $_.ProcessId -Force }

# 2) 分离启动（Shell 返回后仍存活）
Start-Process -FilePath "D:\桌面\two\.venv\Scripts\python.exe" `
  -ArgumentList '-X','utf8','tools\workbench\run.py','--port','5015','--no-browser' `
  -WorkingDirectory "D:\桌面\two" `
  -RedirectStandardOutput "D:\桌面\two\tools\workbench\runtime\workbench-5015.log" `
  -RedirectStandardError  "D:\桌面\two\tools\workbench\runtime\workbench-5015.err.log" `
  -WindowStyle Hidden

# 3) 等 2–3 秒后核对
(Invoke-WebRequest -UseBasicParsing http://127.0.0.1:5015/healthz).Content
```

- 想省事也可以双击 `start_workbench.cmd`，但那是**前台窗口**，关窗口即停。
- **浏览器刷新**：服务若未重启，直接 `Ctrl+F5` 即可（静态 CSS 有缓存，硬刷可避免旧样式）。
- 若页面报 `ERR_CONNECTION_REFUSED`：说明进程没了（电脑重启/终端关闭），按上面第 2 步重启即可；数据都在 `tools/workbench/runtime/workflow.sqlite3`，不会丢。

## 5. 本轮没有做的事

未重启服务、未改代码/数据、未写生产库；未登录平台、未采购、未发布。
`instance/app.db`、`CONTRACT.md`、`scores.csv`、`sources.csv` 未改动（本轮未触任何写操作）。
