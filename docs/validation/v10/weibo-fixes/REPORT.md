# weibo-fixes：墙词误锁 + readyState 断言 + 死代码清理 + export 语义统一

- 范围：`tools/selection/access/{weibo.py,transport.py}`、`tests/test_access_weibo.py`、本目录。
- 触发：前一任务 `task-7d6c4516`（独立只读核验，已验收）的三处待处理项。
- **本轮未联网、未启浏览器、未登录、未装依赖、未写业务库/CSV/CONTRACT；未改预算语义与阈值；未放宽任何断言。**
- 结论：四项全部完成，三个模块全量回归 **148 例 rc=0**（weibo 32 / zhihu 96 / budget 20），**知乎侧零行为变化**（96 例数量与结果与改动前一致）。

## 1. 墙词自相矛盾（最高优先，已修）

**问题**：`weibo.py:53-55` 注释明写“deliberately **without** a bare 验证码……treating that as a wall is the exact false-positive class that closed the Zhihu login window after 4 seconds”，但代码里两处都**带着**裸「验证码」。真实页只要渲染“获取验证码 / 短信验证码”（登录页、需登录的详情页），L3 探针就判墙 → `browser:risk:text:验证码` → `_risk_or_error` 判锁 → **整个 state-dir 被持久锁死**。

| | 改动前 | 改动后 |
| --- | --- | --- |
| `RISK_MARKERS` | `weibo.py:56` `("安全验证", "验证码", "captcha", "访问异常", …)` | `weibo.py:59-61` `("安全验证", "captcha", "访问异常", "操作频繁", "访问过于频繁", "请求过于频繁", "系统繁忙", "系统检测到", "账号异常", "访问受限", "登录后查看", "请先登录")` —— **裸「验证码」已删** |
| `SITE.wall_markers` | `weibo.py:74-76` `("安全验证", "验证码", "访问异常", …)` | `weibo.py:77-79` 同样删掉裸「验证码」，其余真墙词原样保留 |
| `LOGIN_WALL_MARKERS` | `weibo.py:59-60`（原本就不含裸「验证码」） | **未改**（验收要求） |

**判据实测（本轮运行时核验，非推测）**：

```
detect_risk("扫码登录 获取验证码 短信验证码") -> None          # 正常文案不再判墙
detect_risk("请完成安全验证")                 -> text:安全验证   # 真墙仍然判墙
'验证码' in RISK_MARKERS      -> False
'验证码' in SITE.wall_markers -> False
'验证码' not in LOGIN_WALL_MARKERS -> True
```

**新增测试**：`tests/test_access_weibo.py:488` `test_wall_markers_exclude_signin_copy`
- 断言两个列表都不含裸「验证码」，且「安全验证/访问异常/操作频繁」仍在；
- 逐词断言 `"获取验证码 短信验证码 密码登录"` 不含**任何**墙词；
- 断言 `detect_risk(signin_copy) is None`、`detect_risk("请完成安全验证") == "text:安全验证"`。

> 保留的旧测试 `test_wall_locks_the_batch`（`:387` 附近）仍然用字面量 `browser:risk:text:验证码` 走锁路径——它验证的是**锁管道**（探针给出前缀 → 必须锁），不依赖墙词表，故仍然有效，未改。

## 2. 微博站点级 readyState 断言（已补）

| 项 | 内容 |
| --- | --- |
| 事实基础 | 探针脚本由 `transport.py:338-358` `_light_js(site)` 生成，其中 `transport.py:347` 读 `document.readyState`；微博侧 `weibo.py:63-80` 只提供 `SiteProfile` 数据，**不含**探针代码，因此继承该修复，但此前**没有任何微博侧断言**（只有 `test_access_zhihu.py:1344`） |
| 新增测试 | `tests/test_access_weibo.py:506` `test_probe_reads_document_ready_state` |
| 断言 | `_light_js(weibo.SITE)` 含 `document.readyState`、**不含** `documentElement.readyState`；并断言 `transport.site.name == "weibo"`、`"detail" in transport.site.recognized_keys`（确认微博确实用**自己的** profile，而不是悄悄退回知乎默认） |

## 3. 死代码清理（先 grep 全仓确认无引用，再删）

删前确认（全仓 grep `tools/selection/access/*.py`、`tests/*.py`、`docs/validation/v10/weibo/*.py`）：

| 符号 | 引用情况 | 处理 |
| --- | --- | --- |
| `PROBE_MEDIUM_JS` | 仅 `transport.py:391` 定义 | **删除** |
| `PROBE_TEXT_JS` | 仅 `transport.py:392` 定义 | **删除** |
| `_navigate_legacy` | 仅 `transport.py:540` 定义，无调用者 | **删除** |
| `readiness_timeout` | 仅 `transport.py:133/138` 赋值，无读取（`weibo.py:433`、`zhihu.py:669`、`test_access_zhihu.py:1200` 命中是**同名 stop 字符串** `"readiness_timeout"`，不是这个参数） | **删除**参数与属性 |
| `PROBE_LIGHT_JS` | `transport.py:390` + `test_access_zhihu.py:1344` | **保留**（有测试引用，且有诊断价值） |

结果：`transport.py` 544 → **463 行**（−81 行）。改动后再次 grep：`_navigate_legacy` / `PROBE_MEDIUM_JS` / `PROBE_TEXT_JS` / `readiness_timeout =` 全部 **(none)**。

**知乎侧零行为变化**：`AuthenticatedBrowserTransport.__init__` 只是少了一个从未被使用的关键字参数（`zhihu._make_transport` 只传 `headless`/`timeout`，未传它）；`PROBE_LIGHT_JS` 常量内容不变（仍由 `_light_js(ZHIHU_SITE)` 生成）。知乎 96 例全绿即为证据。

## 4. export 语义统一（选“以知乎形状为准”，理由见下）

**问题**：`weibo.py:560-587` 与 `zhihu.py:744-783` 逻辑相同但报告形状不同 —— `dropped_keys` 微博是**列表**、知乎是**计数字典**；`unsupported` 微博是**整数**、知乎是**id 列表**。跨平台汇总脚本会静默出错。

**选择**：验收给了两条路。选了**第一条（以知乎形状为准，微博改成一致）**，理由：
1. 先核对过微博测试：`test_export_is_a_whitelist_and_keeps_weibo_source`（`tests/test_access_weibo.py` 旧 L463）**只断言记录内容与脱敏**，没有断言 `dropped_keys`/`unsupported` 的形状 → 统一**不会破坏已过测试**，无需走“保持两边逐字节一致”的兜底方案。
2. 两条路里，只有“统一形状”能真正消除漂移；兜底方案会让漂移永久留在代码里，反而更难发现。
3. 知乎是**已验收**实现，按验收要求不改其行为。

| | 改动前（weibo.py） | 改动后（weibo.py） |
| --- | --- | --- |
| import | `from .zhihu import _charge, _finish, _merge_diagnostics, _risk_or_error` (`:39`) | `from .zhihu import (..., export as export_records)` (`:39-40`) |
| 实现 | `:560-587` 28 行自写（含 `read_records`/`normalize_record`/`write_records`/统计） | `:562-571` 10 行：`return export_records(input_path, output_path, fmt=fmt, collected_at=collected_at)` |
| `dropped_keys` | 列表（去重排序） | **计数字典**（与知乎一致） |
| `unsupported` | 整数计数 | **id 列表**（与知乎一致） |
| 运行时同一性 | — | `weibo.export_records is zhihu.export` → **True** |

**新增测试**：`tests/test_access_weibo.py:519` `test_export_report_shape_matches_zhihu`
- 同一 fixture 分别喂 `weibo.export` 与 `zhihu.export`，断言 `dropped_keys` **完全相等且是 dict**、`unsupported` **完全相等且是 list**；
- 断言 `"cookies" in dropped_keys`、输出里不含 `SECRET`。

## 5. 测试执行清单（真实 argv / cwd / UTC / exit）

执行器：`docs/validation/v10/weibo-fixes/run_tests.py`（subprocess，逐模块记录）；清单文件：`execution_manifest.json`；原始输出：`logs/*.stdout.txt`、`logs/*.stderr.txt`。

| 模块 | argv | cwd | start (UTC) | end (UTC) | exit | 结果 |
| --- | --- | --- | --- | --- | --- | --- |
| `tests.test_access_weibo` | `.venv\Scripts\python.exe -X utf8 -m unittest tests.test_access_weibo -v` | `D:\桌面\two` | 2026-10-27T14:52:00Z | 14:52:01Z | **0** | Ran 32 — OK |
| `tests.test_access_zhihu` | 同上（模块名替换） | `D:\桌面\two` | 2026-10-27T14:52:01Z | 14:52:10Z | **0** | Ran 96 — OK |
| `tests.test_access_budget` | 同上（模块名替换） | `D:\桌面\two` | 2026-10-27T14:52:10Z | 14:52:12Z | **0** | Ran 20 — OK |

合计 **148 例，rc=0**；`network=none`、`browser=none`。改动前基线：weibo 29 / zhihu 96 / budget 20 = 145；新增 3 例（墙词判据、readyState、export 形状）。

## 6. 守卫（核验时实测，均未变）

| 守卫 | 路径 | SHA256 前 16 位 |
| --- | --- | --- |
| app.db | `instance/app.db` | `e073f828cf0f30d6` |
| workflow.sqlite3 | `tools/workbench/runtime/workflow.sqlite3` | `8ae79c58d8ea5c30` |
| CONTRACT.md | `docs/design/CONTRACT.md` | `826c24cc6c995511` |
| scores.csv | `docs/validation/money-project/scoring/scores.csv` | `ab0c3546c3e9e46f` |
| sources.csv | `docs/validation/money-project/sourcing/sources.csv` | `13679b60d2ba1c32` |

## 7. 仍未验证（不因本修复而改变）

1. 微博真实页面结构、登录方式、反爬策略**全部未实测**；`SITE` 的链接形态/容器类名/空词、搜索 URL、comments 字段仍为假设。
2. 墙词调整后，**真实页面上的验证码类型**（滑块/短信/行为验证）是否命中剩余墙词，未知；例如“请完成验证”“滑块验证”这类文案**目前不在**墙词表内——若真实页用这种措辞，会走 `state=unknown/empty` 而不是 `risk`，需要下一批实测再补词。
3. 432/403/429 与访客墙是否真实存在，未知。
4. 本次只跑三个 access 模块，**未做全套仓库回归**。
