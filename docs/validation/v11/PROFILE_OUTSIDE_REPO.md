# 默认 profile 移出仓库 + 路径防呆（v11，2026-10-30）

- 目标：真实登录前先堵住「登录态落进仓库」这个缺陷。
- 结论：抖音/贴吧默认 profile 已改到仓库外（与微博/知乎同构），并加了**仓库内路径检测**——`doctor()` 报警、`login()` 直接拒绝；`.gitignore` 已覆盖。

## 1. 路径变更

| 平台 | 旧默认（仓库内） | 新默认（仓库外） | 定义位置 |
| --- | --- | --- | --- |
| 抖音 | `docs/validation/v10/douyin-access/profile` | `C:\Users\19183\.dsh\tools\douyin-collect\profile` | `access/douyin.py::DEFAULT_PROFILE`（`Path.home()/".dsh"/"tools"/"douyin-collect"/"profile"`） |
| 百度贴吧 | `docs/validation/v10/tieba/profile` | `C:\Users\19183\.dsh\tools\tieba-collect\profile` | `access/tieba.py::DEFAULT_PROFILE` |
| 微博（参照） | — | `~/.dsh/tools/weibo-collect/profile` | 一直是仓库外 |
| 知乎（参照） | — | `C:\Users\19183\.dsh\tools\zhihu-collect\profile` | 一直是仓库外 |

抖音 CLI 的 `--profile` 默认值取自 `DEFAULT_PROFILE`，因此随之一致（`douyin.py:720`）。

## 2. 防呆（新增）

1. `REPO_ROOT = Path(__file__).resolve().parents[3]`（模块内自算，不依赖 cwd）。
2. `profile_in_repo(profile)`：`expanduser().resolve()` 后判断是否位于仓库根之下（解析失败按"不在仓库内"处理，不抛异常）。
3. `doctor()`：返回体新增 `profile_in_repo` 与 `repo_root`；命中时追加 `warning`：
   `profile_inside_repo：登录态会写进仓库，禁止使用；请改用 DEFAULT_PROFILE 或仓库外的 --profile`。
4. `login()`：命中直接 **`status=rejected / stop=profile_inside_repo`**，**不启动窗口、不扣费**（抖音连 `budget` 都不会被用）。

实测（本批，本地只读、零网络）：

```
douyin default_in_repo= False profile= C:\Users\19183\.dsh\tools\douyin-collect\profile
  doctor.profile_in_repo= False warning= None
  in-repo doctor: True  profile_inside_repo：登录态会写进仓库，禁…
```

## 3. 仓库残留清理（本批实际动作）

`.gitignore` 新增：

```
**/profile/
**/Cookies
**/Cookies-journal
```

同时**删除了 10 个历史遗留的 cookie 数据库文件**（只删数据文件，不动证据文档）：

```
docs/validation/money-project/feasibility/profile/Default/Network/Cookies(+journal)
docs/validation/v10/weibo-login/profile/Default/Network/Cookies(+journal)
docs/validation/v10/weibo-probe/profile_empty{,2,3}/Default/Network/Cookies(+journal)
```

删除后复核：`docs/` 下 `Cookies*` 文件数 **0**；`docs/validation/v10/douyin-access/profile` 与 `docs/validation/v10/tieba/profile` 均**不存在**。

## 4. 历史 profile 目录：**已移出仓库**（2026-10-30 二次返工）

| 原路径 | 文件数 | 体积 | 新位置 |
| --- | --- | --- | --- |
| `docs/validation/money-project/feasibility/profile` | 1029 | 132.55 MB | `~/.dsh/tools/_legacy/feasibility-profile/` |
| `docs/validation/v10/weibo-login/profile` | 1076 | 155.93 MB | `~/.dsh/tools/_legacy/weibo-login-profile/` |
| `docs/validation/v10/weibo-probe/profile_empty` | 158 | 8.89 MB | `~/.dsh/tools/_legacy/weibo-probe-profiles/empty/` |
| `docs/validation/v10/weibo-probe/profile_empty2` | 351 | 21.43 MB | `~/.dsh/tools/_legacy/weibo-probe-profiles/empty2/` |
| `docs/validation/v10/weibo-probe/profile_empty3` | 824 | 71.03 MB | `~/.dsh/tools/_legacy/weibo-probe-profiles/empty3/` |
| `docs/validation/v10/weibo/checks/profile`（0 文件空目录） | 0 | 0 | 已删（唯一授权删除项） |

- 处置原则：**移出，不删除**；合计 **4038 个文件 / 390.83 MB** 离开仓库树（数字为扫描时点，详见 `PROFILE_INVENTORY.md`）。
- `tools/platform-login/{profile,profiles/xhs}` **有意保留原地**（闲鱼/小红书现有登录态，多份报告与脚本依赖），由 `.gitignore` 兜住。
- 仓库树内 `docs/**/profile*` 已**全部清零**。

## 5. 测试

新增 `tests/test_profile_guard.py`（**12 例**）：默认 profile 不在仓库内（抖音/贴吧各一）、默认值在 `~/.dsh/tools/*-collect`、`doctor` 命中报 `profile_in_repo=true` + `warning`、默认 profile 无 `warning`、`login` 被拒且**浏览器 stub 零调用**、贴吧仓库外仍走 `unsupported_offline`、`.gitignore` 覆盖 `**/profile/` 与 `**/Cookies`、`docs/` 下无 Cookies 数据库、旧默认目录不存在。

八套全量 = **489 tests OK**，无跳过。

## 6. 零网络证据

| 项 | 值 |
| --- | --- |
| 新建 profile | **无**（没跑 doctor 之外的任何东西，未创建目录） |
| `platform_douyin.sqlite3` / `platform_tieba.sqlite3` | **不存在** |
| `platform_weibo.sqlite3` | mtime 仍 `2026-10-30 16:03:11` |
| 残留 Chrome | `leftover_chrome=0` |
| 守卫五哈希 | 未变（见批次报告） |
