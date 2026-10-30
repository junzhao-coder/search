# 小红书登录操作指引（给用户本人照做）

> 脚本只开一个可见窗口等你扫码；**它不会读也不会填任何账号、密码、验证码**，不会点击、不会截图。
> 成功判定只看专用 profile 里是否出现 cookie 名称 `web_session`（只查名称，不读值）。

## 现在做什么（等策划者告知“现在弹窗”后）

1. 弹出的 Chrome 窗口会打开 `https://www.xiaohongshu.com`（专用 profile，与日常浏览器完全隔离）。
2. 用**你本人**的手机小红书 App 扫码登录（或你自己的任何方式）；**不要**让任何人/任何脚本代填。
3. 登录成功后等脚本自动关窗；它会打印 `LOGIN_OK`。
4. 超时（300 秒未登录）会打印 `LOGIN_TIMEOUT` 并退出（非零），不重试；需要再来一次就说一声。

## 命令（执行者会代跑，无需你操作）

```powershell
C:\Users\19183\.dsh\tools\x-collect\venv\Scripts\python.exe C:\Users\19183\.dsh\tools\xhs-collect\xhs_collect.py login
C:\Users\19183\.dsh\tools\xhs-collect\xhs_collect.py  # doctor 同理（见下）
```

- doctor（登录后验证）：打印 cookie 名称布尔与 `state`；`state=ready` 时 exit 0。
- profile 路径：`C:\Users\19183\.dsh\tools\xhs-collect\profile`（专用，不碰日常 Chrome）。
- 登录成功后 doctor ready 即停；**首采另批派发**，本步不会自动采集。

## 安全边界

- 脚本不读/不打印 cookie 值、密码、验证码；只查名称布尔。
- 不装依赖（复用 x-collect venv 的 nodriver）；不改 x-collect；不写业务库。
- 登录窗口只会在你确认后弹出一次；超时不开第二次。


## 需要重登前先跑 verify（避免无谓扫码）

```powershell
C:\Users\19183\.dsh\tools\xhs-collect\venv\Scripts\python.exe C:\Users\19183\.dsh\tools\xhs-collect\xhs_collect.py verify
```

- `online=valid`（exit 0）：在线登录态可用，不需要重登。
- `online=login_required`（exit 4）：需要你本人重登；不要先扫码，先确认此结果。
- `online=risk`（exit 5）：遇到验证码/风控，停止，不重试。
- `online=unknown`（exit 6）：网络/页面/超时未知，不重试；不要据此判定已登录。
- verify 是 headless 单页只读检查：不截图、不保存正文、不写 signals/业务库、不重试；只输出判定。
