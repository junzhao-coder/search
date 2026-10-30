# 修复 doctor handle 读取缺陷

> 任务：`task-96edb124949b8eac8761dc6f4cdc2871`（计划 v5，小目标 goal-87ecc184）。范围：`docs/validation/x-collect`。
> 结论：**handle 读取已改为账号菜单/设置页，不再扫描正文首个 @mention；连续两次 doctor 一致返回 `@Johnsmathjyjp`，exit=0。实际账号与任务给定的 `@xluchuan` 不一致，需用户确认。**

## 1. 修复内容（仅 handle 读取与输出分支）

| 文件 | sha256 |
| --- | --- |
| 修改前备份 `before_x_collect.py` | `efd95bcaf59a3065a352410aa833d4ddc01e24e79ea45d3b362438006da361e4` |
| 修改后 `after_x_collect.py`（= 工具 scripts 当前） | `06ebace18dca4b6223f50162a682abfcc1cb1b24f3d03951214767bd4776d71d` |

- `HANDLE_JS`：只读 `[data-testid="SideNav_AccountSwitcher_Button"]` 的 innerText/aria-label；**删除正文首个 @mention 回退**。
- 新增账号菜单读取：点击账号切换按钮（只读 UI，不点 Log out/Post/Like），读取 `[data-testid="AccountSwitcher_Logout_Button"]` 文本中的 `@handle`（本轮实际为 `Log out @Johnsmathjyjp`）或 `[role="menu"]` 文本；随后点击 body 关闭菜单。
- 新增设置页回退：`https://x.com/settings/account`，读取 `input[name="username"]` 的值或页面文本中的 `@handle`。
- 两者都失败：doctor 输出 **`HANDLE_UNKNOWN` 且 exit 0**，不再猜 handle（不再返回 ERROR 3）。
- 未改 `doctor` 的 cookie 预检/登录检查/headless 逻辑，未改 search/user/tweet 逻辑；diff 见 `before_after.diff`（119 行，仅上述常量/`_handle`/doctor 输出分支）。

## 2. 失败尝试（保留）

第一次修改只加了 settings/account 回退、尚未读取账号菜单时：home 的 account switcher 只有 `aria-label="Account menu"`（无 @handle），settings/account 页面需要密码，结果 `HANDLE_UNKNOWN`、exit 0（无猜测）。日志：`doctor_failed_attempt.log`。
随后加入账号菜单读取（`Log out @handle`）修复。

## 3. 两次独立 doctor

命令：`C:\Users\19183\.dsh\tools\x-collect\venv\Scripts\python.exe C:\Users\19183\.dsh\tools\x-collect\scripts\x_collect.py doctor`

| 运行 | UTC | handle | exit | 耗时 | cookie 检查 |
| --- | --- | --- | --- | --- | --- |
| run1 | `2026-10-22T03:56:28Z` | **`@Johnsmathjyjp`** | **0** | 6.0 s | `x_rows=15 auth_token=True ct0=True` |
| run2 | `2026-10-22T03:56:42Z` | **`@Johnsmathjyjp`** | **0** | 6.0 s | `x_rows=15 auth_token=True ct0=True` |

- 原始日志：`doctor_run1.log`、`doctor_run2.log`；两次 handle 一致，无 HANDLE_UNKNOWN。
- 机制：点击账号菜单 → 读取 `Log out @Johnsmathjyjp` → 返回；不再从正文/时间线抓 @mention（此前 `@5ay9jxad693631`、`@bianokm_momo` 均为时间线 @mention 误读）。

## 4. 账号身份（需确认）

- **实际登录 handle：`@Johnsmathjyjp`**。
- 任务给定/期望：`@xluchuan`。
- **两者不一致**；本轮未做任何账号操作（未登录、未切换、未退出、未改 profile），仅只读打开账号菜单。请策划/用户确认该 profile 是否应登录 `@xluchuan`，或任务给定值是否需更新；在确认前不要把 `@Johnsmathjyjp` 当作目标账号。
- 证据：`summary.json` 的 `actual_equals_expected=false`；账号菜单文本见 run 日志 `HANDLE_SWITCHER_CLICKED`/`LOGGED_IN`。

## 5. Cookie 确认（仅名称/行数，未读值）

- 当前 `Default\Network\Cookies` 中 `.x.com` **15 行**（此前 B2 记录为 14 行；浏览/菜单后新增 1 行，未做清理）。
- `auth_token=True`、`ct0=True`；名称（仅名称）：`__cf_bm, __cuid, _twitter_sess, auth_token, cf_clearance, ct0, g_state, gt, guest_id, guest_id_ads, guest_id_marketing, lang, personalization_id, twid`。
- 未打印/保存任何 cookie 值；未改 profile 登录态。

## 6. 证据

| 文件 | 内容 |
| --- | --- |
| `before_x_collect.py` / `after_x_collect.py` | 修改前后源码（可回滚） |
| `before_after.diff` | 119 行 unified diff |
| `doctor_failed_attempt.log` | 仅 settings 回退时的 HANDLE_UNKNOWN/exit 0（失败尝试） |
| `doctor_run1.log` / `doctor_run2.log` | 两次 doctor 原始输出 |
| `summary.json` | 两次 handle/exit/cookie 布尔/是否等于 @xluchuan |

## 7. 限制

1. 账号菜单读取依赖 `data-testid="SideNav_AccountSwitcher_Button"` 与 `AccountSwitcher_Logout_Button`；X 页面结构变化会使读取失败，届时按设计输出 `HANDLE_UNKNOWN` exit 0（不猜测）。
2. `settings/account` 仅作回退；X 当前该页账号信息需密码确认，通常拿不到 username，回退可能返回 unknown（本轮由账号菜单成功，未依赖设置页）。
3. 读取账号菜单是一次只读 UI 点击（打开/关闭菜单），未点 Log out、未发帖/点赞/关注/私信；未改 search/user/tweet 逻辑。
4. cookie 行数由 14 变 15（新增为浏览产生的非 auth cookie），auth_token/ct0 仍在；未清理/修改 profile。
5. 未跑 325 业务测试（无业务代码变更）；未改 DSH 配置、未重登、未弹窗。
