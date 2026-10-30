# 待应用补丁：微博登录判定器（多信号 + tab 重取）

> 状态：**未应用**。原因：本任务 `scope = ["docs/validation/v10/weibo-login"]`，写入 `tools/selection/access/*` 与 `tests/*` 被 Flow 拒绝（"写入超出正在执行任务的授权文件范围"）。
> 需要策划者用**新 scope**（含 `tools/selection/access`、`tests/test_access_weibo.py`）重新 dispatch，或明确授权后再应用。
> 本文件只放在允许目录内，作为可直接照抄的补丁稿。

---

## 补丁 1：`tools/selection/access/browser.py` —— 每次 poll 重取候选 tab

### 1.1 在 `def scan_markers(...)` 之前新增两个函数

```python
def _login_candidates(browser) -> list:
    """Tabs worth reading on this poll: the browser/main tab first, then any
    other tab newest-first.

    A login redirect can land in a *new* tab; reading only the first
    `main_tab` then reports "nothing" forever. Fakes without `tabs` simply
    yield one candidate, so existing behaviour is unchanged.
    """
    out = [browser]
    try:
        tabs = list(getattr(browser, "tabs", None) or [])
    except TypeError:
        tabs = []
    main = getattr(browser, "main_tab", None)
    for tab in reversed(tabs):
        if tab is main or tab is browser or not hasattr(tab, "evaluate"):
            continue
        out.append(tab)
    return out


async def _poll_login_state(browser, signed_in_js: str) -> tuple[str, bool, str]:
    """Read url / signed-in / visible text, trying every candidate tab.

    Returns as soon as a candidate reports signed-in. Falls back to the first
    non-empty text so a blank main tab does not hide a logged-in one.
    """
    url, text, signed = "", "", False
    for tab in _login_candidates(browser):
        try:
            tab_url = str(await _eval(tab, "location.href") or "")
            tab_signed = bool(await _eval(tab, signed_in_js))
            tab_text = str(await _eval(
                tab, "document.body ? document.body.innerText : ''") or "")
        except Exception:  # noqa: BLE001 - one dead tab must not end the wait
            continue
        if tab_url and not url:
            url = tab_url
        if tab_text and not text:
            text = tab_text
        if tab_signed:
            return tab_url or url, True, tab_text or text
    return url, signed, text
```

### 1.2 `wait_for_login` 循环体内，把三次 `_eval` 换成一次多 tab 读取

替换前（当前 `browser.py:126-133`）：

```python
        try:
            url = str(await _eval(browser, "location.href") or "")
            signed_in = bool(await _eval(browser, signed_in_js or SIGNED_IN_JS))
            risk_text = str(await _eval(browser, "document.body ? document.body.innerText : ''")
                            or "")
        except Exception as exc:  # noqa: BLE001 - tab died mid-wait
            stop_reason = f"browser_error:{type(exc).__name__}"
            break
```

替换后：

```python
        try:
            url, signed_in, risk_text = await _poll_login_state(
                browser, signed_in_js or SIGNED_IN_JS)
        except Exception as exc:  # noqa: BLE001 - tab died mid-wait
            stop_reason = f"browser_error:{type(exc).__name__}"
            break
```

> 其余逻辑（signed_in 优先于墙词、poll 配额、五态、锁）**一律不动**。

---

## 补丁 2：`tools/selection/access/weibo.py` —— 多信号 `SIGNED_IN_JS`

替换现有的：

```python
SIGNED_IN_JS = r"""
(() => {
  const t = (document.body && document.body.innerText) || '';
  if (/退出|我的主页|发微博|账号设置/.test(t)) return true;
  return false;
})()
"""
```

为：

```python
#: Any ONE signal is enough, so a future redesign only has to keep one of them:
#: a user-link, one of five nav words, or an avatar on weibo.com. Passport/login
#: pages are explicitly excluded so the sign-in page never counts as "signed in".
SIGNED_IN_JS = r"""
(() => {
  const host = location.hostname || '';
  const path = location.pathname || '';
  if (/passport|login|signin/i.test(host)) return false;
  if (/\/signin|\/login/i.test(path)) return false;
  const text = (document.body && document.body.innerText) || '';
  if (/我的主页|发微博|退出|账号设置|消息/.test(text)) return true;
  const avatar = document.querySelector(
    'img[src*="avatar"],[class*="avatar"],[class*="Avatar"]');
  if (avatar && /(^|\.)weibo\.com$/.test(host)) return true;
  if (document.querySelector('a[href*="/u/"]')) return true;
  return false;
})()
"""
```

> 知乎 `SIGNED_IN_JS` **不动**（`browser.py` 里的默认值），知乎行为零变化。

---

## 补丁 3：`tests/test_access_weibo.py` —— 判定器测试 a–d

在文件末尾 `if __name__ == "__main__":` 之前追加：

```python
class ScriptedTab:
    """A tab that answers the three snippets the login loop reads."""

    def __init__(self, *, url="", signed=False, text=""):
        self.url = url
        self.signed = signed
        self.text = text
        self.calls = 0

    async def evaluate(self, script):
        self.calls += 1
        if "location.href" in script:
            return self.url
        if "我的主页" in script:          # the weibo signed-in probe
            return self.signed
        return self.text


class TabbedBrowser:
    """Main tab plus extra tabs, so the poll can fall back to a newer one."""

    def __init__(self, main, others=()):
        self.main_tab = main
        self.tabs = [main, *others]

    async def evaluate(self, script):     # behaves like the main tab
        return await self.main_tab.evaluate(script)


class LoginDetectorTests(WeiboTestBase):
    """a) signed-in DOM -> ok; b) signed-out -> not ok; c) empty text but a
    user link -> ok; d) the login landed in a *later* tab -> ok."""

    def test_js_declares_every_signal_and_excludes_the_signin_page(self):
        js = weibo.SIGNED_IN_JS
        self.assertIn('a[href*="/u/"]', js)             # signal 1
        self.assertIn("我的主页", js)                     # signal 2
        self.assertIn("发微博", js)
        self.assertIn("退出", js)
        self.assertIn("账号设置", js)
        self.assertIn("消息", js)
        self.assertIn("avatar", js)                      # signal 3
        self.assertIn("passport|login|signin", js)        # the exclusion

    def test_signed_in_page_is_ok(self):
        tab = ScriptedTab(url="https://weibo.com/", signed=True, text="首页 消息 我的主页")
        result = asyncio.run(browser_mod.wait_for_login(
            tab, profile=self.dir, budget=self.budget(), clock=self.clock, timeout=10,
            signed_in_js=weibo.SIGNED_IN_JS, wall_markers=weibo.LOGIN_WALL_MARKERS))
        self.assertEqual(result["status"], "ok")
        self.assertTrue(result["signed_in"])
        self.assertEqual(result["exit"], codes.EXIT_OK)

    def test_signed_out_page_is_not_ok(self):
        tab = ScriptedTab(url="https://weibo.com/", signed=False, text="登录 注册")
        result = asyncio.run(browser_mod.wait_for_login(
            tab, profile=self.dir, budget=self.budget(), clock=self.clock, timeout=3,
            signed_in_js=weibo.SIGNED_IN_JS, wall_markers=weibo.LOGIN_WALL_MARKERS))
        self.assertNotEqual(result["status"], "ok")
        self.assertFalse(result["signed_in"])

    def test_empty_text_with_a_user_link_still_counts_as_signed_in(self):
        # the selector hit is what the browser reports; text is empty on purpose
        tab = ScriptedTab(url="https://weibo.com/", signed=True, text="")
        result = asyncio.run(browser_mod.wait_for_login(
            tab, profile=self.dir, budget=self.budget(), clock=self.clock, timeout=10,
            signed_in_js=weibo.SIGNED_IN_JS, wall_markers=weibo.LOGIN_WALL_MARKERS))
        self.assertEqual(result["status"], "ok")

    def test_login_landing_in_a_later_tab_is_detected(self):
        blank = ScriptedTab(url="about:blank", signed=False, text="")
        landed = ScriptedTab(url="https://weibo.com/", signed=True, text="首页 消息")
        browser = TabbedBrowser(blank, [landed])
        result = asyncio.run(browser_mod.wait_for_login(
            browser, profile=self.dir, budget=self.budget(), clock=self.clock, timeout=10,
            signed_in_js=weibo.SIGNED_IN_JS, wall_markers=weibo.LOGIN_WALL_MARKERS))
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["final_url"], "https://weibo.com/")
        self.assertGreaterEqual(landed.calls, 1)          # the later tab was read
```

> 测试 a–d 与验收原文一一对应；第 4 条正是"首 tab 空、后续 tab 有登录态"的场景。

---

## 应用后的验收命令（阶段一）

```
D:\桌面\two\.venv\Scripts\python.exe -X utf8 -m unittest \
  tests.test_access_weibo tests.test_access_zhihu tests.test_access_budget -q
```
**必须 exit 0**；不绿则停，不许开窗。
