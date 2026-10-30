# RISK_JS 误报修复与 exit 2/3 受控验证

> 任务：`task-a9e0931179befd52e49d08c52f48c51b`（计划 v5，p4）。范围：`docs/validation/x-collect/risk-branch`。
> 工具 `C:\Users\19183\.dsh\tools\x-collect`；真实 profile 未重登；handle 仍 `@Johnsmathjyjp`。
> 结论：RISK_JS 已改为**结构化信号**（toast/captcha/error page），不再扫描 body 文本；纯函数 fixtures 7/7 通过；exit2（空 profile）与 exit3（fixture 注入）均实测；真实 doctor/search 回归 exit=0。

## 1. risk-fix（RISK_JS 重写）

| 项 | 值 |
| --- | --- |
| 修改前备份 | `before_x_collect.py` sha256=`fcd74b5a7a5d1f6bb471e3e6206f0ed3a100e69ee333f21cf7865718803b0f5c` |
| 修改后（工具当前） | `after_x_collect.py` sha256=`5b1441339537e42317b9c95bfb9dff0dd95dc9bec285a871b30b5c36052b4985` |
| diff | `before_after.diff`（243 行；含 risk JS/纯函数/错误落盘/profile 覆盖参数，未改 handle/登录/user/tweet 逻辑） |

- `RISK_JS` 现在只返回结构化信号：可见 `[role="alert"]`/`[data-testid="toast"]` 文本、验证码容器（`iframe[src*=captcha]`/`arkose`/`[data-testid*=captcha]`/`[id*=captcha]`）、X 错误页容器（`[data-testid="error-detail"]`/`errorPage`）。
- **删除 body 全文正则**（原 `/Challenge/i`）；正常推文含 “challenges/challenge accepted” 不再触发。
- 新增纯函数 `risk_from_signals(signals)`：captcha/error_page → RISK；否则仅检查 toast 文本（`something went wrong|rate limit|too many requests|verify you are human|challenge required|captcha`）。
- `_check_state` 调用纯函数并保存 `signals=` 到 `data/errors/*.txt`；`_save_error` 增加可选 `signals` 参数。
- 新增测试参数：`--profile`（doctor/search，仅覆盖 user-data-dir）、`--risk-fixture`（search，JSON 信号注入）；默认行为不变。
- 未改 handle 读取、登录、user/tweet 结构；profile/risk fixture 仅用于测试。

## 2. fixtures（纯函数回归）

`run_fixtures.py` → `fixtures_results.json`，7/7 通过：

| case | 输入信号 | 期望 | 实际 |
| --- | --- | --- | --- |
| normal_challenges | 正文含 challenges，无 toast | NOT_RISK | NOT_RISK |
| normal_challenge_accepted | 正文含 “Challenge accepted” | NOT_RISK | NOT_RISK |
| normal_toast_other | toast=“Your post was sent.” | NOT_RISK | NOT_RISK |
| risk_toast | toast=“Something went wrong…” | RISK | RISK |
| risk_rate_limit | toast=“Rate limit exceeded…” | RISK | RISK |
| risk_captcha | captcha=true | RISK | RISK |
| risk_error_page | error_page=true | RISK | RISK |

- HTML 片段在 `fixtures/*.html`；`cases.json` 保存对应 signals/期望；`ALL_PASSED=True count=7`。

## 3. exit2（受控空 profile）

临时 profile：`tmp/empty-profile`（空目录，0 文件/0 字节；未复制真实 profile）。

| 命令 | 输出 | exit |
| --- | --- | --- |
| `x_collect.py doctor --profile tmp/empty-profile` | `COOKIE_CHECK exists=False x_rows=0 auth_token=False ct0=False` → `SESSION_EXPIRED (no auth cookies; browser not launched)` | **2** |
| `x_collect.py search --keyword "web scraping" --limit 1 --profile tmp/empty-profile` | `SESSION_EXPIRED (no auth cookies; browser not launched)` | **2** |

- 两次前后 Chrome 进程数 **0**；未打开登录窗口；真实 profile 未触碰。日志 `exit2_doctor.log`、`exit2_search.log`、`doctor-2026-10-22T045523Z.log`、`search-2026-10-22T045524Z.log`。

## 4. exit3（fixture 注入，不访问真实风控页）

命令：

```powershell
x_collect.py search --keyword "web scraping" --limit 1 `
  --risk-fixture docs/validation/x-collect/risk-branch/fixtures/risk_toast.json
```

- 输出：`RISK_CONTROL_FIXTURE={"toast":"Something went wrong...","captcha":false,...}`，`ERROR_FRAGMENT=...search-2026-10-22T045544Z.txt`，**exit=3**。
- 错误文件同时含 `signals={...}`（无 cookie/凭据）；无浏览器启动，未访问真实平台风控页。日志 `exit3_fixture.log`、`search-2026-10-22T045544Z.log`、`exit3_error_fragment.txt`。

## 5. 真实 profile 回归

| 运行 | 命令 | 结果 |
| --- | --- | --- |
| doctor | `x_collect.py doctor` | `LOGGED_IN handle=@Johnsmathjyjp utc=2026-10-22T04:56:00Z`，**exit=0**（`regression_doctor.log`） |
| search | `x_collect.py search --keyword "web scraping" --limit 5 --interval-min 8 --interval-max 8` | **exit=0**，collected=1，duplicates=26，elapsed=40.1s，stop=END，无 RISK_CONTROL（`regression_search.log`） |

- 两轮间隔：doctor 结束 04:56:00Z → search 开始 04:56:32Z，**32s（≥30s）**；总跨度 78s。
- search 仅 1 条新 id（全局 `seen.jsonl` 已有大量 web scraping 结果）；无 HANDLE 变化、无假 RISK。
- 前后 Chrome 进程 0。

## 6. 哈希/清理

`hash_check.json`：

- requirements / CONTRACT / 冻结三 / real_link 全 same；业务库 `e073f828…`（wal/shm=false）。
- `x_collect` before `fcd74b5a…` → after `5b1441…`；diff `before_after.diff`。
- 临时 profile 保留：`tmp/empty-profile`（0 文件/0 字节，无 cookie）便于复测；如不需要可删除该目录。

## 7. 限制

1. RISK 判定依赖 X DOM 的 toast/captcha/error 选择器；页面结构变化会漏判（但不回退到 body 文本猜测）。正常文案中的 “challenge(s)” 不再触发。
2. toast 文本匹配仍是规则；若 X 新增风控文案需补充词表（当前含 something went wrong/rate limit/too many requests/verify/challenge required/captcha）。
3. exit3 为 fixture 注入验证，未真实触发平台 429/验证码；真实风控分支逻辑同 `risk_from_signals`+`_save_error`。
4. `--profile`/`--risk-fixture` 仅测试用；默认真实 profile 行为不变；未改 handle/登录/user/tweet。
5. 真实 search limit5 仅新增 1 条（seen 去重），exit0 已满足回归；未跑 325 业务测试；未发布/点赞/关注/私信；未读 cookie 值。
