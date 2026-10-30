# 微博接入独立核验（weibo-review）

- 核验对象：`tools/selection/access/weibo.py`（730 行）、`tests/test_access_weibo.py`（29 例）、`docs/validation/v10/weibo/`
- 核验者：非实现者。**只读核验 + 离线测试**；未改任何产品代码/测试/期望值；未联网、未开浏览器、未登录、未装依赖。
- 时间：2026-10-27T14:43:43Z（测试起）→ 14:43:45Z（测试止），cwd=`D:\桌面\two`。

## 0. 总结论

| 验收项 | 判定 |
| --- | --- |
| 1) 只读独立核验、逐条给证据行号 | 通过（见 §1–§4） |
| 2) 五个已修缺陷未被重新引入 | **a/b/c/d 通过；e 通过但微博侧无断言**（见 §1） |
| 3) 复用真实性（无 budget/diagnostics 副本） | 通过；但 `export` / 诊断落盘有**重复实现**（见 §2，存疑·轻） |
| 4) 入口与边界（子命令/非零退出/零网络） | 通过；实测 **7 个子命令**（文档写“六个”，见 §3） |
| 5) 陷阱抽取 + 下批诊断字段 | 交付（见 §5、§6） |
| 6) 守卫生效 | 通过（5 哈希全对，见 §7） |
| 7) 零真实请求 | 通过（见 §3.4） |

**新发现 1 个需要处理的问题**（不在五个缺陷之列）：`weibo.py` 的墙词集合里**包含裸 “验证码”**，与它上面注释声称的“故意不含裸验证码”自相矛盾；一旦真实页面把 “获取验证码” 这类正常文案渲染出来，探针会把它判成墙并**持久锁死批次**（见 §4.1）。

## 1. 五个已修缺陷逐条核验

### a) async 未 await —— **通过**

| 证据 | 说明 |
| --- | --- |
| `weibo.py:224` `return asyncio.run(browser_mod.wait_for_login(...))` | 假浏览器路径：协程被完整跑到结束 |
| `weibo.py:243-246` `await browser.get(LOGIN_URL)` / `return await browser_mod.wait_for_login(...)` | 真窗口路径：两处均 await |
| `weibo.py:253` `return asyncio.run(_run())` | 启动 + 导航 + 登录轮询在同一个 `_run()` 里 |
| `transport.py:446/448/451` | `browser.get` / `tab.get_content` / `tab.evaluate` 三处全部 await |
| `browser.py:206` `if inspect.isawaitable(result): return await result` | 同步/异步混合的 evaluate 都被统一 await |
| 测试侧 | `tests/test_access_weibo.py:96,108,195` 的 fake 均为 `async def evaluate/get/get_content`，**没有**用同步方法掩盖真实签名 |

### b) 跨事件循环 —— **通过**

| 证据 | 说明 |
| --- | --- |
| `transport.py:150-154` `_get_loop()` 复用 `self._loop`（`new_event_loop` 只在这里） | 单 loop 唯一出口 |
| `transport.py:171-175` 启动用 `loop.run_until_complete(...)`，`loop = self._get_loop()` | 启动与导航同一 loop |
| `transport.py:214-215` `_navigate(..., loop=self._get_loop())` | 导航显式复用同一 loop |
| `weibo.py` 全文 | **没有任何** `asyncio.new_event_loop` / 第二次 loop 去 await 已建连接 |
| 提示（非缺陷） | `transport.py:459` 的 `else asyncio.new_event_loop()` 只在 `loop=None`（legacy 路径）时触发；`_navigate_legacy`（`transport.py:540`）当前**无调用者**，见 §4.3 |

### c) 单一递减 deadline + 硬超时 —— **通过**

| 证据 | 说明 |
| --- | --- |
| `transport.py:277` `_deadline(timeout)` / `transport.py:267` `_remaining(deadline)` | 一个总预算、按剩余递减 |
| `transport.py:174-175` `wait_for(_start(), timeout=remaining)` | **启动**阶段也有界（原知乎缺陷之一） |
| `transport.py:446` `wait_for(browser.get(url), timeout=_remaining(deadline))` | 导航有界 |
| `transport.py:448` `wait_for(tab.get_content(), ...)` | 内容读取有界 |
| `transport.py:451-452` `wait_for(tab.evaluate("location.href"), ...)` | 最终 URL 读取有界 |
| `transport.py:425` `budget = min(PROBE_LEVEL_TIMEOUTS[level-1], max(0.05, _remaining(deadline) * 0.5))` | 每级探针只吃**剩余一半**，不重置总预算 |
| `weibo.py:612` `--timeout` 默认 60.0；`weibo.py:636` 传入 transport | CLI 与传输层一致 |

### d) 风险持久锁 —— **通过**

| 证据 | 说明 |
| --- | --- |
| `transport.py:240` `"error": f"browser:risk:text:{probe['wall']}"` | 探针看到墙 → 该前缀 |
| `zhihu.py:623`（`_risk_or_error` 内）`if text.startswith(RISK_ERROR_PREFIX): return text, True` | 该前缀**等同 403/429**，返回锁定语义 |
| `weibo.py:39` `from .zhihu import ... _risk_or_error` | 微博**复用**同一判定，未另写一份 |
| `weibo.py:408-413 / 460-465 / 510-515` | search/detail/comments 三路都 `batch.lock(reason, source=...)`，并在返回里带 `diagnostics` |
| `weibo.py:474-478` | 详情页解析出 `risk:` 时同样 `batch.lock(stop, source="detail")` |
| `weibo.py:259/337-339/350/401` 测试 | `browser:risk:text:验证码` → 锁；锁后下一次搜索被拒；登录墙 → 锁；详情墙 → 锁 |

### e) readyState —— **通过（继承），但微博侧无断言**

| 证据 | 说明 |
| --- | --- |
| `transport.py:347` `const state = document.readyState \|\| '';` | 读的是 `document.readyState`（正确属性） |
| `transport.py:338-358` `_light_js(site)` 由站点 profile 生成 | 微博没有自己的探针脚本，**继承**共享实现 |
| `weibo.py:63-78` `SITE = transport_mod.SiteProfile(...)` | 只提供链接形态/选择器/墙词，无探针代码 |
| 缺口 | `tests/test_access_weibo.py` **没有**任何 `readyState` 断言（只有 `test_access_zhihu.py:1344` 那条）；建议补一条站点级断言，防以后有人给微博单独写探针时把属性写错 |

## 2. 复用真实性

**真的复用（通过）**

- `weibo.py:34-38`：`from . import budget as budget_mod / codes / diagnostics as diag_mod / records as rec / transport as transport_mod`。
- `weibo.py:39`：`from .zhihu import _charge, _finish, _merge_diagnostics, _risk_or_error` —— 编排、诊断合并、风险判定全部复用，**没有第二套**。
- `weibo.py:63`：`SiteProfile` 是 `transport_mod` 提供的**数据扩展点**（`transport.py:291-309`），探针脚本由 `_light_js/_medium_js/_text_js`（`transport.py:338-386`）按 profile 生成 —— 一份传输实现、多站点。
- 预算：`weibo.py:403/455/505/672` 全部走 `budget_mod`，无本地计数/本地限速。
- 诊断白名单：`weibo.py:719` 走 `diag_mod.sanitize`，未自建白名单。

**重复实现（存疑·轻，未列为“重写引擎”）**

| 位置 | 与谁重复 | 差异风险 |
| --- | --- | --- |
| `weibo.py:560-587` `export()` | `zhihu.py:744-783` `export()` | 返回结构漂移：`dropped_keys` 微博是**列表**、知乎是**计数字典**；`unsupported` 微博是**整数**、知乎是**id 列表**。两平台导出报告不可比，属**语义漂移**，建议合并成一个共享函数 |
| `weibo.py:548-554` `budget_mod_error()` | `zhihu.py:_attempt()` | 3 行等价逻辑，两份 |
| `weibo.py:717-726` `_write_diagnostics()` | `zhihu.py:_write_diagnostics()` | 两份近似实现（微博多了 `parse_state` 默认值） |

其余未发现把 budget 或 diagnostics **整份抄写**的情况；`SiteProfile` 的出现说明实现者主动把“平台差异”和“机制”分开了，这是对的。

## 3. 入口与边界

### 3.1 子命令（实测 `--help` 全部 exit=0）

`doctor` / `login` / `search` / `detail` / `comments` / `export` / `budget` —— **实际 7 个**（`weibo.py:600-625`）。实现报告写“六个子命令”（`docs/validation/v10/weibo/REPORT.md:22`），与代码不符；按功能看应是 7 个（若把 `budget` 视为调试命令则 6 个）。**建议改文档措辞，不改代码。**

### 3.2 非零退出边界（本次实测，全新临时 state-dir）

| 命令 | exit | 含义 |
| --- | --- | --- |
| `--mode offline search 测试` | **7** | `network_disabled_offline_batch` → 传输错误，非空成功 |
| `--mode offline detail https://weibo.com/1` | **8** | 主机不在白名单（`weibo.cn`）→ `url_not_allowed` |
| `--mode offline comments https://m.weibo.cn/detail/1234567890` | **6** | 同批 interval 未到 → `budget:interval_not_elapsed`（预算拒绝，先于网络） |
| `doctor`（无 profile） | **0** | 本地只读，`network="none"`、`online="unverified"` |

### 3.3 doctor 零网络（通过）

`weibo.py:176-203`：只读 profile 目录 + cookie **名**（`SELECT DISTINCT name ... host_key LIKE '%weibo%'`），返回 `network: "none"`、`online: "unverified"`，注释与实现一致（“Never launches a browser”）。

### 3.4 零真实请求（通过）

- 默认模式 offline → `RefusedTransport`（`weibo.py:632-640`）；`public-http` 需显式 `--mode`，`authenticated-browser` 需显式 + 会先扣预算。
- `tests/test_access_weibo.py` 仅用 `FakeTransport`/假浏览器，**无** `socket`/`requests`/`urllib` 网络调用（grep 无命中）；29 例 0.82s 跑完。
- `docs/validation/v10/weibo/offline_checks.py:34-42` 明确断言 offline 拒绝 socket（exit 7）。
- 文档声明零真实请求（`REPORT.md:5`），与本次核验一致。

## 4. 新发现（三个，均不影响五缺陷判定）

### 4.1 墙词集合含裸“验证码”，与注释自相矛盾 → **建议修**

- `weibo.py:53-55` 注释：“wall wording. Deliberately **without** a bare `验证码`: sign-in pages show `获取验证码` as normal copy…”
- 但 `weibo.py:56` `RISK_MARKERS = ("安全验证", "验证码", ...)` **含**裸“验证码”；`weibo.py:74-76` `SITE.wall_markers` 同样**含**裸“验证码”。
- 后果：真实页面只要渲染出“获取验证码/短信验证码”字样（登录页、需登录的详情页），L3 探针 `wall` 命中 → `browser:risk:text:验证码` → `_risk_or_error` → **持久锁死整个 state-dir 批次**。这与知乎那次“登录页文案误锁”的错误同类。
- 注意：`LOGIN_WALL_MARKERS`（`weibo.py:59-60`）**确实**排除了裸“验证码”，所以注释描述的其实是登录用的那组；真正的问题在 `RISK_MARKERS` 与 `SITE.wall_markers`。
- 建议（本轮不改码）：把 `RISK_MARKERS`/`SITE.wall_markers` 里的裸“验证码”换成更具体的“请完成验证/安全验证/滑块验证”等，或仅在 `readyState=complete && 无内容锚点` 时才允许“验证码”单独成立。

### 4.2 `export()` 语义漂移（见 §2 表）

同一份导出在本仓两个平台给出**不同形状**的报告字段，后续若写跨平台汇总脚本会静默出错。建议合并为一个共享 `export()`，微博只传 `source` 前缀。

### 4.3 死代码 / 死开关（ponytail 视角，建议清理）

| 位置 | 现状 |
| --- | --- |
| `transport.py:540-544` `_navigate_legacy` | 全仓**无调用者**（仅定义） |
| `transport.py:133,138` `readiness_timeout` | 赋值后**没有任何逻辑读取**（`weibo.py:433`/`zhihu.py:669` 命中是同名 **stop 字符串**，不是这个参数） |
| `transport.py:391-392` `PROBE_MEDIUM_JS`/`PROBE_TEXT_JS` | 仅作知乎兼容字面量定义，无其它引用（`PROBE_LIGHT_JS` 被 `test_access_zhihu.py:1344` 使用） |

这几项是“可删的复杂度”，不影响缺陷判定；但既然这套底座要给微博/抖音/贴吧复用，建议在下一个平台接入前清掉，避免别人误用 legacy 路径自建 loop。

## 5. 陷阱清单：微博侧“仍未验证”的假设

来自 `docs/validation/v10/weibo/RESEARCH.md`（L104-108）+ 本次代码核对，逐项列出：

1. **页面结构**：`SITE.shape_rules`（`weibo.py:65-70`）的四种链接形态（`/detail/<id>`、`/status/<id>`、`/<uid>/<bid>`、`/<uid>`）与容器类名（`class*="card"/"feed"/"m-panel"`，`weibo.py:72-73`）**全部 assumed**，从未对真实移动站核对。
2. **搜索 URL**：`containerid=100103type=1&q=…`（`weibo.py:120-123`）来自公开文档，未实测。
3. **评论接口**：`/comments/hotflow?id=&mid=&max_id_type=0`（`weibo.py:126-128`）与字段名 `data.data[].id/text/created_at/like_count`（`weibo.py:359-369`）**假设**。
4. **登录方式**：`passport.weibo.com/sso/signin`（`weibo.py:43`）、cookie 名 `SUB/SUBP/SUHB/SCL/SSOLoginState/_T_WM/XSRF-TOKEN`（`weibo.py:47`）、`SIGNED_IN_JS` 文案（`weibo.py:81-87`：退出/我的主页/发微博/账号设置）**未验证**；扫码 vs 短信登录未知。
5. **反爬策略**：432/403/429、访客墙、验证码类型（滑块/短信）、频控窗口、是否需要移动 UA **全部未知**；V9 旧结论“访客墙”既不能确认也不能否认。
6. **标识体系**：`/<uid>/<bid>` 的 bid 与 `/detail/<mid>` 的 mid 可能不是同一体系（`REPORT.md:108` 已标记），会影响 detail/comments 的 `native_id` 一致性。
7. **墙词误锁**（本次新发现，见 §4.1）：真实页面出现“获取验证码”等正常文案会锁批次。

## 6. 下一批真实验证必须带的诊断字段

**现有白名单已具备**（`diagnostics.py` ALLOWED_KEYS + transport 填充）：

`requested_url`、`final_url`、`final_url_known`、`ready_state`、`phase`、`elapsed_ms`、`html_bytes`、
`probe_level`、`probe_elapsed_ms`（`{"1":ms,"2":ms,"3":ms}`）、`anchors_total`、`anchors_recognized`、`anchors_rejected`、`href_shapes`、`query_key_counts`、`state`、`parse_state`、`risk`、`selectors_assumed`、`error`。

**判读顺序**（与知乎线同一套）：

1. `phase=navigate` + `browser:TimeoutError` → 连 `get` 都没回来（知乎线就是这个现象）。
2. `probe_level=1` + `level_timeout=true` → 轻探针本身被卡，问题不在探针过重。
3. `probe_level=2/3` + `level_timeout=true` → 重探针被卡，继续拆小。
4. `state=result` 但 `count=0` → 才轮到解析/链接形态假设。
5. `state=risk` + `risk=text:<marker>` → 立刻停手，别在同一 state-dir 重试（会 `batch_locked`）。

**建议显式新增的诊断字段**（当前白名单没有，真实验证会需要；新增时必须仍不含正文/账号信息）：

| 字段 | 为什么需要 |
| --- | --- |
| `http_status` | 微博的 432/418/403 是重要信号；现在传输层只给 200 或 None，`_risk_or_error` 只能靠 403/429 文本推断 |
| `wall_source`（`probe` / `parse`） | 区分“探针看到墙”与“解析器看到墙”，避免像 §4.1 那样把误锁归因错 |
| `console_error_count`（只计数，不留文本） | 知乎线卡在 CDP 求值不返回，微博若出现同样现象，需要区分“页面报错”与“求值阻塞” |
| `profile_reused`（bool） | 判断这次跑的是新 profile 还是登录过的 profile（会话复用是微博可读性的关键变量） |

**另外必须带**：`--diagnostics-dir`（落最小骨架）、`--timeout 60`、全新 `--state-dir`、原 profile 只读。

## 7. 守卫与测试运行记录

### 守卫哈希（核验时实测，全部与预期一致）

| 守卫 | 路径 | SHA256 前 16 位 | 预期 | 判定 |
| --- | --- | --- | --- | --- |
| app.db | `instance/app.db` | `e073f828cf0f30d6` | `e073f828` | ✓ |
| workflow.sqlite3 | `tools/workbench/runtime/workflow.sqlite3` | `8ae79c58d8ea5c30` | `8ae79c58` | ✓ |
| CONTRACT.md | `docs/design/CONTRACT.md` | `826c24cc6c995511` | `826c24cc` | ✓ |
| scores.csv | `docs/validation/money-project/scoring/scores.csv` | `ab0c3546c3e9e46f` | `ab0c3546` | ✓ |
| sources.csv | `docs/validation/money-project/sourcing/sources.csv` | `13679b60d2ba1c32` | `13679b60` | ✓ |

> 说明：`workflow.sqlite3` 与 `CONTRACT.md` 不在仓库根，分别在 `tools/workbench/runtime/` 与 `docs/design/`；文档里若写“根目录”应更正。

日志/文档里未发现真实 cookie 值或 token：`offline_checks.py:57,63` 出现的是**反例 fixture**（`token=SECRET`、`SECRET_COOKIE`、`nickname: someone`），用来验证导出脱敏，不是真实凭据。

### 测试（真实 argv / cwd / UTC / exit）

`execution_manifest.json` 记录的那次（`run_tests.py` 内 subprocess）：

```
argv   : D:\桌面\two\.venv\Scripts\python.exe -X utf8 -m unittest tests.test_access_weibo -v
cwd    : D:\桌面\two
start  : 2026-10-27T14:48:44Z
end    : 2026-10-27T14:48:45Z
exit   : 0
result : Ran 29 tests in 0.929s — OK        (network=none, browser=none)
```

先前手工那次同命令：`2026-10-27T14:43:43Z → 14:43:45Z`，**exit 0 / Ran 29 tests in 0.821s — OK**（两次一致）。

产品文件 mtime 仍为 22:31–22:39（实现者时间），本次核验（22:48）**没有触碰任何产品文件**。

### 本次核验执行的只读命令（摘要）

- `weibo <cmd> --help` × 7 → 全部 exit=0
- `--mode offline search/detail/comments`（全新临时 state-dir）→ exit 7 / 8 / 6
- `doctor`（无 profile）→ exit 0，`network="none"`
- 只读 grep：浏览器调用点、`new_event_loop`、`document.readyState`、`browser:risk`、`ALLOWED_KEYS`、死代码引用

## 8. 给策划者的一句话

微博接入在**机制层**是干净的：五个缺陷一个都没被重新引入，复用是真复用（`SiteProfile` 数据扩展点 + 共享 `_risk_or_error`/`budget`/`diagnostics`），默认路径零网络、非零退出、守卫未被触碰。**唯一需要在下批真实验证前处理的是 §4.1 的裸“验证码”墙词**——它不是五个缺陷的回归，但在真实页面上会造成“误锁死批次”，正好是知乎线吃过的那类亏。
