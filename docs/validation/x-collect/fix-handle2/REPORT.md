# 删除 SETTINGS_HANDLE_JS 正文回退（fix-handle2）

> 任务：`task-0c789eb143761c566554e75aaf6a2bd2`（计划 v5）。范围：`docs/validation/x-collect`。
> 结论：**已删除 `SETTINGS_HANDLE_JS` 的 `document.body.innerText` + `/@.../` 回退；仅保留 `input[name="username"]`。两次 doctor 仍一致返回 `@Johnsmathjyjp`、exit=0。**

## 1. fix

修改前 `before_x_collect.py` sha256=`06ebace18dca4b6223f50162a682abfcc1cb1b24f3d03951214767bd4776d71d`
修改后 `after_x_collect.py`（= 工具当前 scripts）sha256=`fcd74b5a7a5d1f6bb471e3e6206f0ed3a100e69ee333f21cf7865718803b0f5c`

`before_after.diff`（13 行，单一 hunk）：

```diff
@@ -53,9 +53,7 @@
   const input = document.querySelector('input[name="username"]');
   if (input && input.value) return input.value.replace(/^@/, '');
-  const text = document.body ? document.body.innerText : '';
-  const m = text.match(/@([A-Za-z0-9_]{1,20})/);
-  return m ? m[1] : null;
+  return null;
 })()
```

- 现 `SETTINGS_HANDLE_JS` 只读 `input[name="username"]`；取不到返回 `null`，由既有 `HANDLE_UNKNOWN` 分支处理（exit 0，不猜）。
- 未改 `HANDLE_JS`、`CLICK_SWITCHER_JS`/`MENU_HANDLE_JS`、`_handle` 其他分支、doctor cookie 预检/登录逻辑、search/user/tweet；未新增点击动作（账号菜单点击为上一批已接受的只读交互）。

## 2. doctor run1 / run2

命令（同一 profile、headless）：

```powershell
C:\Users\19183\.dsh\tools\x-collect\venv\Scripts\python.exe `
  C:\Users\19183\.dsh\tools\x-collect\scripts\x_collect.py doctor
```

| 运行 | UTC | handle | exit（脚本日志） | 耗时 | cookie 检查 |
| --- | --- | --- | --- | --- | --- |
| run1 | `2026-10-22T04:08:00Z` | **`@Johnsmathjyjp`** | **0** | 6.0 s | `x_rows=15 auth_token=True ct0=True` |
| run2 | `2026-10-22T04:08:07Z` | **`@Johnsmathjyjp`** | **0** | 6.0 s | `x_rows=15 auth_token=True ct0=True` |

- 原始日志：`doctor_run1.log`、`doctor_run2.log`（均含 `HANDLE_SWITCHER_CLICKED`、`LOGGED_IN handle=@Johnsmathjyjp`、`EXIT=0`）。
- run2 的 PowerShell 管道截断曾使 `$LASTEXITCODE` 显示 `-1`，但脚本日志明确 `EXIT=0`；run1 管道退出码为 0。两次 handle 一致，说明删除回退未造成退化。

## 3. 账号身份

- 实际 handle 仍为 **`@Johnsmathjyjp`**；与任务此前给定的 `@xluchuan` 不一致（上一批 fix-handle 已记录并提请确认）。
- 本次未登录/切换/退出账号、未改 profile；仅做 handle 读取修复与 doctor 复验。

## 4. 证据/限制

- 证据：`before_x_collect.py`、`after_x_collect.py`、`before_after.diff`、`doctor_run1.log`、`doctor_run2.log`、`summary.json`、本文件；UTF-8 无 BOM，无 cookie 值。
- 限制：
  1. `SETTINGS_HANDLE_JS` 现在只认 `input[name="username"]`；X 若改用 contenteditable/其他选择器，settings 回退会返回 null（按设计 HANDLE_UNKNOWN exit 0，不扫描正文）。本轮账号菜单路径成功，未依赖 settings。
  2. `settings/account` 当前需要密码才能看账号信息，实际回退通常不可用；这是既有设计限制，不是本次引入。
  3. 账号菜单 `data-testid` 结构变化仍可能导致 HANDLE_UNKNOWN（exit 0）。
  4. 未跑 325 业务测试（无业务代码变更）；未改 DSH 配置/日常 Chrome；未发布/点赞/关注/私信。
