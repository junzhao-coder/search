"""Browser seam: nodriver when installed, otherwise an honest "unavailable".

The login flow is a **pure function over an injected browser object**, so the
ok / timeout / unknown / risk branches can be tested with a fake and no real
window. This batch never launches a real browser.

Login state is decided by what the page shows (an account menu / signed-in
marker), never by cookie names: a cookie row only proves a cookie row exists.
"""

from __future__ import annotations

import asyncio
import inspect
import pathlib
import shutil

from .codes import (EXIT_LOGIN_POLL_LIMIT, EXIT_LOGIN_TIMEOUT, EXIT_LOGIN_UNKNOWN,
                    EXIT_OK, EXIT_RISK)
from .budget import polls_for_window

CHROME_CANDIDATES = (
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    r"C:\Users\19183\AppData\Local\Google\Chrome\Application\chrome.exe",
)

#: page evidence that a real signed-in session is present.
SIGNED_IN_JS = r"""
(() => {
  const sel = [
    '[data-zop*="currentUser"]',
    '.AppHeader-profileAvatar',
    '.AppHeaderUserInfo',
    '[class*="Avatar"][class*="AppHeader"]',
    '#Popover1-toggle'
  ];
  for (const s of sel) { if (document.querySelector(s)) return true; }
  const nav = document.querySelector('.AppHeader');
  if (nav && /消息|私信|我的主页|创作中心/.test(nav.innerText || '')) return true;
  return false;
})()
"""

SIGNIN_URL_MARKERS = ("/signin", "/login")


def available() -> dict:
    try:
        import nodriver  # noqa: F401
        has_nodriver, version = True, getattr(nodriver, "__version__", "unknown")
    except Exception:  # noqa: BLE001 - absence is a normal state here
        has_nodriver, version = False, None
    chrome = next((p for p in CHROME_CANDIDATES if pathlib.Path(p).is_file()), None)
    if chrome is None:
        found = shutil.which("chrome") or shutil.which("chrome.exe")
        chrome = found
    return {"nodriver": has_nodriver, "nodriver_version": version, "chrome": chrome,
            "usable": bool(has_nodriver and chrome)}


def classify_login_page(*, url: str, signed_in: bool, risk_reason: str | None,
                        still_waiting: bool) -> str:
    """Pure decision: ok | risk | timeout | unknown.

    `unknown` means the window opened but neither a signed-in marker nor a
    risk marker was ever seen — that is NOT success and must exit non-zero.
    `timeout` means we waited the whole window without evidence.
    """
    if risk_reason:
        return "risk"
    if signed_in:
        return "ok"
    return "timeout" if still_waiting else "unknown"


async def wait_for_login(browser, *, profile, budget, clock, timeout: float = 300.0,
                         poll: float = 3.0, max_polls: int | None = None,
                         signed_in_js: str | None = None,
                         wall_markers=None, signed_in_verdict=None,
                         risk_wins: bool = False) -> dict:
    """Poll the login page until a real session appears, risk hits, or time runs out.

    Every poll charges the **poll** quota (not the active-call quota), and a
    locked budget refuses here like anywhere else: logging in is not a way
    around a lock.

    `signed_in_js` / `wall_markers` let another adapter reuse this whole loop
    with its own page wording instead of writing a second login waiter. Zhihu
    stays the default so existing behaviour is unchanged.
    """
    from . import records as rec

    started = clock()
    polls = 0
    signed_in_seen = False
    last_url = ""
    risk_reason = None
    risk_url_seen = ""
    stop_reason = None
    # Poll quota covers the whole window by construction, so a normal login can
    # never be cut short by the quota; an explicit max_polls still wins (tests).
    limit = max_polls if max_polls is not None else max(
        budget.max_polls, polls_for_window(timeout, poll))

    while True:
        elapsed = clock() - started
        if elapsed >= timeout:
            stop_reason = "timeout"
            break
        if polls >= limit:
            stop_reason = "poll_limit"
            break
        try:
            budget.charge_poll(f"login elapsed={elapsed:.0f}s")
        except Exception as exc:  # noqa: BLE001 - BudgetError or write failure
            code = getattr(exc, "code", "")
            if code == "polls_exhausted":
                # Quota spent but the window still has time: keep the window
                # open for the user instead of closing it early.
                await _sleep(clock, poll)
                continue
            return {"status": "locked" if code == "batch_locked" else "budget_error",
                    "exit": 6, "detail": code or type(exc).__name__,
                    "polls": polls, "final_url": rec.sanitize_url(last_url)}
        polls += 1

        try:
            url, signed_in, risk_text, tab_risk, risk_url = await _poll_login_state(
                browser, signed_in_js or SIGNED_IN_JS, verdict=signed_in_verdict,
                wall_of=(lambda text: scan_markers(text, wall_markers))
                if wall_markers is not None else _login_wall_of)
        except Exception as exc:  # noqa: BLE001 - tab died mid-wait
            stop_reason = f"browser_error:{type(exc).__name__}"
            break

        last_url = url or last_url
        # Weibo passes risk_wins=True: a wall seen on any tab ends the wait even
        # if another tab looked signed in. Zhihu keeps the old order, where a
        # real session is not killed by "验证码" copy on the login page.
        if tab_risk and (risk_wins or not signed_in):
            risk_reason = tab_risk
            risk_url_seen = risk_url or url
            break
        if signed_in:
            signed_in_seen = True
            stop_reason = "signed_in"
            break
        if tab_risk:
            risk_reason = tab_risk
            risk_url_seen = risk_url or url
            break
        await _sleep(clock, poll)

    verdict = classify_login_page(url=last_url, signed_in=signed_in_seen,
                                  risk_reason=risk_reason,
                                  still_waiting=stop_reason in ("timeout", "poll_limit"))
    if verdict == "risk":
        budget.lock(risk_reason, source="login")
    if verdict == "ok":
        status, exit_code = "ok", EXIT_OK
    elif verdict == "risk":
        status, exit_code = "risk", EXIT_RISK
    elif stop_reason == "poll_limit":
        status, exit_code = "poll_limit", EXIT_LOGIN_POLL_LIMIT
    elif stop_reason == "timeout":
        status, exit_code = "timeout", EXIT_LOGIN_TIMEOUT
    else:
        status, exit_code = "unknown", EXIT_LOGIN_UNKNOWN
    return {"status": status, "exit": exit_code, "polls": polls,
            "stop_reason": stop_reason, "risk_reason": risk_reason,
            "risk_url": rec.sanitize_url(risk_url_seen) if risk_url_seen else None,
            "signed_in": signed_in_seen,
            "final_url": rec.sanitize_url(last_url),
            "elapsed_s": round(clock() - started, 3)}


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


async def _poll_login_state(browser, signed_in_js: str, verdict=None,
                            wall_of=None) -> tuple[str, bool, str, str | None, str]:
    """Read every readable candidate tab; risk wins over signed-in.

    Returns `(url, signed, text, risk_reason, risk_url)` where url/text/risk all
    come from the SAME tab. A wall seen on any tab is returned as the result even
    if another tab looks signed in: choosing a friendlier tab to dodge a wall we
    already saw would be a bypass, not a login.

    `wall_of` is the caller's wall scanner (weibo passes its own markers; zhihu
    keeps the default). Without it, no risk is reported.
    """
    first_url, first_text = "", ""
    signed_hit = None          # (url, text)
    risk_hit = None            # (reason, url)
    last_exc = None
    read_any = False
    for tab in _login_candidates(browser):
        try:
            tab_url = str(await _eval(tab, "location.href") or "")
            raw = await _eval(tab, signed_in_js)
            tab_signed = bool(verdict(raw)) if verdict is not None else bool(raw)
            tab_text = str(await _eval(
                tab, "document.body ? document.body.innerText : ''") or "")
        except Exception as exc:  # noqa: BLE001 - one dead tab must not end the wait
            last_exc = exc
            continue
        read_any = True
        if tab_text and not first_text:
            first_url, first_text = tab_url, tab_text
        reason = wall_of(tab_text) if wall_of is not None else None
        if reason and risk_hit is None:
            # remember the FIRST wall with its own url; keep scanning so a later
            # tab cannot silently outvote it, then return risk before anything else
            risk_hit = (reason, tab_url)
        if tab_signed and signed_hit is None:
            signed_hit = (tab_url, tab_text)
    if not read_any and last_exc is not None:
        # every candidate failed: that is a dead browser, not a patient user,
        # so let the caller report "unknown" instead of waiting out the window
        raise last_exc
    reason, risk_url = risk_hit if risk_hit is not None else (None, "")
    if signed_hit is not None:
        url, text = signed_hit
        # both facts are returned; `wait_for_login` applies the precedence
        # (weibo: risk wins; zhihu: a real session is not killed by "验证码" copy)
        return url, True, text, reason, risk_url
    if risk_hit is not None:
        return risk_url, False, first_text, reason, risk_url
    return first_url, False, first_text, None, ""


def scan_markers(text: str, markers) -> str | None:
    """First configured marker found in `text`, as `text:<marker>`; else None."""
    lowered = " ".join(str(text or "").split()).lower()
    for marker in markers:
        if marker.lower() in lowered:
            return f"text:{marker}"
    return None


def _login_wall_of(text: str) -> str | None:
    """Login-page wall scan; normal sign-in copy ("获取验证码") is not a wall."""
    from .zhihu import detect_login_wall
    return detect_login_wall(text[:4000])


def _risk_of(text: str) -> str | None:
    from .zhihu import detect_risk
    return detect_risk(text[:4000])


async def _eval(browser, script: str):
    """Run one JS snippet on a nodriver-like browser (or a sync fake).

    nodriver exposes ``evaluate`` on a Tab, not on the Browser object; the
    Browser has ``main_tab``. Every result is awaited when awaitable, and a
    plain fake returning a value directly still works.
    """
    target = browser if hasattr(browser, "evaluate") else None
    if target is None:
        target = getattr(browser, "tab", None)
    if target is None:
        target = getattr(browser, "main_tab", None)
    if target is None or not hasattr(target, "evaluate"):
        raise RuntimeError("browser_has_no_evaluate")
    result = target.evaluate(script)
    if inspect.isawaitable(result):
        return await result
    return result


async def _sleep(clock, seconds: float) -> None:
    """Sleep via the injected clock when it can advance itself, else real sleep."""
    advance = getattr(clock, "advance", None)
    if callable(advance):
        advance(seconds)
        return
    await asyncio.sleep(seconds)
