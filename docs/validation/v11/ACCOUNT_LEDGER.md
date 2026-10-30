# 跨平台账号台账（v11，2026-10-30）

- 口径：**只写 cookie 名称与 true/false，绝不写值**；`online` 一律 `unverified`（doctor 是零网络只读；2026-10-30 的登录窗口有网络，但没有做任何业务在线验证）。
- 数据来源：本批本地调用各平台 `doctor()`（纯只读：profile 目录 + cookie 表名 + 浏览器查找），零网络；抖音/知乎另有 2026-10-30 本人扫码登录运行记录（`LOGIN_RUN_2026-10-30.md`）。
- 「待用户本人登录」= 需要用户在自己的窗口里扫码/输密码，agent 不代填。

## 1. 四平台台账

| 平台 | profile 路径 | 存在 | cookie DB | cookie 数 | cookie 名称（布尔） | 在线本人状态 | 已验证能力 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 微博 | `C:\Users\19183\.dsh\tools\weibo-collect\profile` | ✅ | ✅ | 9 | `SUB=true, SUBP=true, SUHB=false, SCL=false, SSOLoginState=true, _T_WM=false, XSRF-TOKEN=true` | **unverified**（本批零网络）；历史批次 weibo-rpa-13/19/21 有登录态实测 | 登录、桌面搜索、正文、互动数、评论（含第 2 页）、统一导出 |
| 知乎 | `C:\Users\19183\.dsh\tools\zhihu-collect\profile` | ✅ | ✅ | 24 | `z_c0=true, d_c0=true, _xsrf=true, __zse_ck=true, q_c1=true, SESSIONID=true` | **已登录（2026-10-30 本人扫码）**：`z_c0=true`（登录前 false、21 个 cookie）；运行记录见 `LOGIN_RUN_2026-10-30.md` | doctor（只读）、可见窗口登录（z_c0 判据）、export；search 匿名 403、comments unsupported |
| 抖音 | `C:\Users\19183\.dsh\tools\douyin-collect\profile`（**v11 起移出仓库**；旧值 `docs/validation/v10/douyin-access/profile` 已废弃） | ✅ | ✅ | 3 | `sessionid=true, sid_tt=true, uid_tt=true` | **已登录（2026-10-30 本人扫码）**：会话 cookie 名称出现；`profile_in_repo=false`；运行记录见 `LOGIN_RUN_2026-10-30.md` | 可见窗口登录（本轮实现，`--window` 才开窗）、doctor、六入口离线可用；comments 显式 unsupported |
| 百度贴吧 | `C:\Users\19183\.dsh\tools\tieba-collect\profile`（**v11 起移出仓库**；旧值 `docs/validation/v10/tieba/profile` 已废弃） | ❌ | ❌ | 0 | `BDUSS=false, STOKEN=false, BAIDUID=false, PTOKEN=false, SAID=false` | **待用户本人登录**（profile 尚未创建） | 六入口离线可用；comments 显式 unsupported；零真实访问 |

## 2. 读法与红线

1. **只有名称与布尔**：本台账不含任何 cookie 值、token 值或凭据；`doctor()` 也只统计名称。
2. `online` 全部 `unverified`：本批没有联网，历史在线证据按批次号可查（微博 rpa-13/19/21）。
3. **抖音 profile 已创建并登录**（2026-10-30 本人扫码，`sessionid/sid_tt/uid_tt` 名称出现）；**贴吧 profile 仍不存在**（不是"登录失败"，是从没建过，首次使用要先跑一次可见窗口登录）。
4. 知乎 `z_c0` 于 **2026-10-30 由 false 变 true**（本人扫码，cookie 数 21→24）：之前的"未完整登录态"已解除。
5. **profile 一律在仓库外**（v11 起）：四个平台的默认 profile 都在 `~/.dsh/tools/*-collect/profile`；`doctor()` 会返回 `profile_in_repo` 并在命中时给 `warning`，`login()` 直接 `rejected/profile_inside_repo`（不启动窗口）。详见 `PROFILE_OUTSIDE_REPO.md`。

## 3. 复现命令（本地只读，零网络）

```powershell
C:\Users\19183\.dsh\tools\x-collect\venv\Scripts\python.exe -X utf8 -c @"
import sys; sys.path.insert(0, r'D:\桌面\two')
from tools.selection.access import weibo, zhihu, douyin, tieba
for m in (weibo, zhihu, douyin, tieba):
    d = m.doctor()
    print(m.__name__, d.get('profile'), d.get('profile_exists'),
          d.get('cookie_count'), d.get('cookie_names'), d.get('network'))
"@
```

预期：`network='none'`，且**不出现任何 cookie 值**。
