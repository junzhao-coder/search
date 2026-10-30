# 小红书采集器迁移记录（V9 迁移，用户要求：只迁移不测试）

> 用户原话：**“只需要迁移不需要测试”**。
> 本批**零执行**：未运行脚本、未 `--help`、未 `py_compile`、未开浏览器、未发请求、未写数据库、未安装依赖、未提交 git。
> 迁移来源是**另一个会话**的现有成果，不是本项目实测；不得据此宣称本项目已验收。

## 1. 源会话与源位置

| 项 | 值 |
| --- | --- |
| 源会话 | `session-025f9305-30c7-44e2-b3d9-7eaf7edb1984` |
| 源脚本 | `D:\桌面\破甲\crawler\xhs_collect.py`（39,281 B，SHA256 `BBAB14DBBD1665BDF2FFDE407FD0F5972DF9AE1EA14679E0E10DBEB570E6DF09`） |
| 源 profile | `D:\桌面\破甲\profiles\xhs_main`（Chrome user-data-dir，含 `Default/` 等） |
| 源数据库 | `D:\桌面\破甲\crawler\xhs_data.db`（73,728 B；表 `notes/users/comments/runs/sqlite_sequence`） |
| 源会话摘要 | `C:\Users\19183\.dsh\storages\session_projcache\sessions\session-025f9305-30c7-44e2-b3d9-7eaf7edb1984.json`（末尾记录登录后推荐流 50 条 + 300012 限制；**未在本项目复核**） |

## 2. 新入口（本项目）

| 项 | 值 |
| --- | --- |
| 脚本 | `tools/selection/vendor_xhs/xhs_collect.py`（39,281 B，SHA256 与源**完全一致**） |
| 复制方式 | 原样 `Copy-Item`，**无任何代码改动**（`Compare-Object` = IDENTICAL） |
| 依赖 | 仅标准库 + `websockets.sync.client`（源 `import` 仅 12 项，无本地模块 import） |

## 3. 原资产复用参数（保留原处，不复制、不改）

脚本默认值由源文件位置推导，迁移后默认路径会指向本项目，**必须显式传参**才能复用原 profile/DB：

```powershell
# 顶层参数放在子命令之前（实读 main:1005-1045）
C:\Users\19183\.dsh\tools\x-collect\venv\Scripts\python.exe `
  tools\selection\vendor_xhs\xhs_collect.py `
  --profile "D:\桌面\破甲\profiles\xhs_main" `
  --db "D:\桌面\破甲\crawler\xhs_data.db" `
  check
```

- 默认 `--profile` = `<脚本上两级>/profiles/xhs_main` → 迁移后为 `tools/selection/profiles/xhs_main`（不存在，不要用）。
- 默认 `--db` = `<脚本上两级>/crawler/xhs_data.db` → 迁移后为 `tools/selection/crawler/xhs_data.db`（不存在，不要用）。
- 因此**所有命令都要显式 `--profile` + `--db`**；原资产留在 `D:\桌面\破甲\...` 不动。

## 4. 已安装解释器/依赖位置（只读确定，未执行）

| 项 | 路径 | 状态 |
| --- | --- | --- |
| 推荐解释器 | `C:\Users\19183\.dsh\tools\x-collect\venv\Scripts\python.exe` | 存在 |
| `websockets` 包 | `C:\Users\19183\.dsh\tools\x-collect\venv\Lib\site-packages\websockets` | 存在 |
| 系统 Python | `C:\Users\19183\AppData\Local\Programs\Python\Python312\python.exe` | 存在，但**无 websockets** |
| `xhs-collect` venv | `C:\Users\19183\.dsh\tools\xhs-collect\venv\Scripts\python.exe` | 不存在 |

- 结论：用 **x-collect venv** 运行；本批未安装任何包。

## 5. 支持的子命令（实读 main:1005-1045）

| 子命令 | 关键参数 | 说明 |
| --- | --- | --- |
| `login` | — | 有头 Chrome 扫码登录，profile 落盘 |
| `check` | — | 检查登录态 |
| `explore` | `--pages`（默认 3）、`--channel` | 推荐流/频道 |
| `note` | `--ids`、`--from-db`、`--limit`（默认 50） | 笔记详情 |
| `user` | `--ids`（必填）、`--xsec` | 用户页 |
| `search` | `--kw`（必填）、`--pages`（默认 2） | 搜索 |
| `stats` | — | 统计 |

顶层参数（**必须放子命令前**）：`--db`、`--profile`、`--proxy`、`--headed`、`--interval`、`--session-max`、`--daily-max`。

- **没有 `fill` 子命令**（源文件头部 docstring 过时，以 main 实读为准）。
- 安全默认（源码 `SAFE`）：`min_interval=10.0s`、`session_max=150`、`daily_max=600`、`quiet 01:00–07:00`。

## 6. 未迁移内容（有意排除）

- 账号池/多账号：`xhs_pool.py`、`xhs_phone.py`、`xhs_smscode_eval.py`
- 代理/压测/风控旁支：`xhs_ipcheck.py`、`xhs_ip_attr.py`、`xhs_limit_probe.py`、`xhs_rate_limit.py`、`xhs_risk.py`、`xhs_shield_probe.py`、`xhs_sig_probe.py`、`xhs_sizing.py`、`xhs_sim_source.py`、`xhs_recover_probe.py`、`xhs_diag.py`、`xhs_common_probe.py`、`xhs_login_probe.py`、`xhs_probe.py`、`spider.py`
- 数据/缓存：`xhs_data.db`、`_t.db`、`demo.jsonl`、`__pycache__`、`_proxytest` 等临时目录
- 理由：`xhs_collect.py` 自包含；其余属旁支，用户只要求迁移采集器本体。

## 7. 未验证 / 限制（用户要求不测试）

- **未运行、未 `--help`、未 `py_compile`、未发请求、未开浏览器、未写 DB、未装依赖、未提交 git**。
- 脚本在本项目的可运行性、CLI 行为、登录态、300012 限流表现均**未验证**。
- 源会话摘要的“推荐流 50 条 / 300012 限制”是**另一会话的记录**，本项目未复核。
- 默认路径已错位，必须显式 `--profile/--db`；未做代码修改来“修正默认值”（保持源文件字节一致，便于追溯）。
