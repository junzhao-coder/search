# 阶段一执行清单（移动 UA，离线）

> 任务 `task-bc5a638c08c9ce79bd6ad444054d7255`（rev2，计划 v10，V10-5 第 3 次探路之前的离线阶段）。
> 守卫：**阶段一测试全绿后才允许进入阶段二**。本文件记录判绿所用的真实命令与结果。

## 1. 实现（一个 UA 字段，未重构启动流程）

| 位置 | 改动 |
| --- | --- |
| `tools/selection/access/transport.py` `SiteProfile.__init__` | 新增 `user_agent: str \| None = None`（默认 None = 不干预 Chrome 默认 UA） |
| `transport.SiteProfile.with_user_agent(ua)` | 新增 3 行：返回**副本**，模块级 profile 不被改写 |
| `transport.AuthenticatedBrowserTransport._launch_kwargs(info)` | 新增：集中生成 `uc.start` 参数；UA 非空时追加 `browser_args=["--user-agent=<UA>"]` |
| `transport._ensure_browser` | `uc.start(**self._launch_kwargs(info))`（唯一调用点） |
| `weibo.MOBILE_UA` | 常量：Android 13 / Pixel 7 / Chrome 124 Mobile Safari |
| `weibo.SITE` | `user_agent=MOBILE_UA` |
| `weibo` CLI | `search/detail/comments` 新增 `--user-agent`，`_make_transport` 用 `SITE.with_user_agent(override)`（不改模块默认） |
| `transport.ZHIHU_SITE` | **保持 `user_agent=None`**，知乎行为零变化 |

### 为什么用 `--user-agent=` 启动开关，而不用 `Network.setUserAgentOverride`

1. **时机**：CDP override 需要先 `Network.enable` 再 `setUserAgentOverride`，通常发生在**首次导航之后**；而移动 UA 的价值在于**第一次请求**就让服务端走移动渲染分支。启动开关在 Chrome 起来时就生效。
2. **改动面**：开关是 `uc.start(browser_args=[...])` 一个参数；CDP 方案要额外拿 tab、发两次 CDP、处理失败回退——按 ponytail 的"一个字段，不重构"要求，开关更小。
3. **一致性**：与"单一 loop、单一 deadline"的既有约束无交互，不引入新的 await 点。

## 2. 测试（真实命令与结果）

### 2.1 新增 UA 测试（`tests/test_access_weibo.py::UaTests`）

| 测试 | 断言 |
| --- | --- |
| `test_only_weibo_carries_a_mobile_user_agent` | `weibo.SITE.user_agent` 非空、含 `Mobile`、等于 `MOBILE_UA`；**`ZHIHU_SITE.user_agent is None`** |
| `test_launch_kwargs_turn_the_ua_into_a_browser_switch` | 微博：`kwargs["browser_args"] == ["--user-agent=<UA>"]`；知乎：`"browser_args" not in kwargs` |
| `test_uc_start_actually_receives_the_mobile_ua` | 用 stub `nodriver` 模块 + stub `browser.available`（**不启真浏览器**）：`uc.start` 收到的 `browser_args` 含移动 UA，`headless=False`、`user_data_dir` 已 resolve、`browser_executable_path` 透传、`close()` 调用 `stop()` |
| `test_cli_override_copies_the_profile_instead_of_mutating_it` | `--user-agent UA-X` → transport.site.user_agent=="UA-X"，且 `weibo.SITE.user_agent` 仍为 `MOBILE_UA` |
| `test_no_override_keeps_the_site_default` | 无覆盖时 `built.site is weibo.SITE` |

```
argv = D:\桌面\two\.venv\Scripts\python.exe -X utf8 -m unittest tests.test_access_weibo.UaTests -q
cwd  = D:\桌面\two
UTC  = 2026-10-27T15:27:1xZ
exit = 0    Ran 5 tests … OK
```

### 2.2 全量回归（知乎 + 预算 + 微博）

```
argv = D:\桌面\two\.venv\Scripts\python.exe -X utf8 -m unittest tests.test_access_budget tests.test_access_zhihu tests.test_access_weibo -q
cwd  = D:\桌面\two
UTC  = 2026-10-27T15:27:1xZ
exit = 0    Ran 163 tests in 12.852s … OK
```

- 其中知乎 96 + 预算 20 + 微博 47（含新增 5 条 UA 测试）= **163**，**全部通过**，知乎无回归。

### 2.3 离线六入口复查（UA 改动后仍全绿）

```
argv = D:\桌面\two\.venv\Scripts\python.exe -X utf8 docs\validation\v10\weibo\offline_checks.py
cwd  = D:\桌面\two
UTC  = 2026-10-27T15:27:23Z → 15:27:26Z
exit = 0    7/7 场景匹配（doctor 0 / login 7 / search 7 / detail 7 / comments 7 / export 0 / budget 0）
```

## 3. 判绿结论

| 检查 | 结果 |
| --- | --- |
| 阶段一测试是否有任何失败 | **无** |
| 知乎行为是否变化 | **无**（`ZHIHU_SITE.user_agent is None`，96 项知乎测试通过） |
| 是否允许进入阶段二 | **允许**（守卫满足） |

阶段二（本批最后一次真实额度）在 `REPORT_PROBE3.md` 记录。
