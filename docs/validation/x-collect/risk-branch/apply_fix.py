"""Apply RISK_JS/profile/fixture changes to the x_collect tool script.

Run with the x-collect venv. The script backs up nothing itself; before_x_collect.py
in this directory is the pre-change copy.
"""

import pathlib
import sys

TARGET = pathlib.Path(r"C:\Users\19183\.dsh\tools\x-collect\scripts\x_collect.py")
text = TARGET.read_text(encoding="utf-8")

OLD_RISK = '''RISK_JS = r"""
(() => {
  const t = document.body ? document.body.innerText : '';
  return /Something went wrong|Rate limit|rate limit|Verify you are human|captcha|Challenge|尝试过多|出错了/i.test(t);
})()
"""'''

NEW_RISK = '''RISK_JS = r"""
(() => {
  const visible = (el) => {
    if (!el) return false;
    const style = window.getComputedStyle(el);
    if (style.display === 'none' || style.visibility === 'hidden') return false;
    const r = el.getBoundingClientRect();
    return r.width > 0 && r.height > 0;
  };
  const toasts = [...document.querySelectorAll('[role="alert"], [data-testid="toast"]')]
    .filter(visible);
  const toast = toasts.map((el) => el.innerText || '').join(' | ').slice(0, 500);
  const captcha = [...document.querySelectorAll(
    'iframe[src*="captcha" i], iframe[src*="arkose" i], [data-testid*="captcha" i], [id*="captcha" i]'
  )].some(visible);
  const error_page = [...document.querySelectorAll(
    '[data-testid="error-detail"], [data-testid="errorPage"]'
  )].some(visible);
  return {toast: toast, captcha: captcha, error_page: error_page, url: location.href};
})()
"""'''

RISK_FUNC = '''

RISK_TOAST_RE = re.compile(
    r"something went wrong|rate limit|too many requests|verify you are human|challenge required|captcha",
    re.IGNORECASE,
)


def risk_from_signals(signals: dict) -> bool:
    """Pure predicate: structured DOM signals -> risk boolean.

    Normal tweet text is never inspected here; only visible toast/alert text,
    captcha containers, and X error-page containers count.
    """
    if not isinstance(signals, dict):
        return False
    if signals.get("captcha") or signals.get("error_page"):
        return True
    toast = str(signals.get("toast") or "")
    return bool(RISK_TOAST_RE.search(toast))
'''

OLD_SAVE = '''def _save_error(kind: str, url: str, title: str, body: str, log: RunLog) -> str:
    ERRORS.mkdir(parents=True, exist_ok=True)
    path = ERRORS / f"{kind}-{utc().replace(':', '')}.txt"
    text = (f"utc={utc()}\\nkind={kind}\\nurl={url}\\ntitle={title}\\n"
            f"body_excerpt={body[:2000]}\\n")
    path.write_text(text, encoding="utf-8", newline="\\n")
    log.write(f"ERROR_FRAGMENT={path}")
    return str(path)'''

NEW_SAVE = '''def _save_error(kind: str, url: str, title: str, body: str, log: RunLog,
                signals: dict | None = None) -> str:
    ERRORS.mkdir(parents=True, exist_ok=True)
    path = ERRORS / f"{kind}-{utc().replace(':', '')}.txt"
    text = (f"utc={utc()}\\nkind={kind}\\nurl={url}\\ntitle={title}\\n"
            f"body_excerpt={body[:2000]}\\n")
    if signals is not None:
        text += f"signals={json.dumps(signals, ensure_ascii=False)}\\n"
    path.write_text(text, encoding="utf-8", newline="\\n")
    log.write(f"ERROR_FRAGMENT={path}")
    return str(path)'''

OLD_RISK_CHECK = '''    try:
        risk = bool(_decode_cdp(await tab.evaluate(RISK_JS)))
    except Exception:  # noqa: BLE001
        risk = False
    if risk:
        try:
            body = str(_decode_cdp(await tab.evaluate(BODY_JS)) or "")
        except Exception:  # noqa: BLE001
            body = ""
        _save_error(kind, href, title, body, log)
        log.write(f"RISK_CONTROL href={href} title={title!r}")
        return ERROR
    return None'''

NEW_RISK_CHECK = '''    try:
        signals = _decode_cdp(await tab.evaluate(RISK_JS))
        if not isinstance(signals, dict):
            signals = {}
    except Exception:  # noqa: BLE001
        signals = {}
    if risk_from_signals(signals):
        try:
            body = str(_decode_cdp(await tab.evaluate(BODY_JS)) or "")
        except Exception:  # noqa: BLE001
            body = ""
        _save_error(kind, href, title, body, log, signals=signals)
        log.write(f"RISK_CONTROL href={href} title={title!r} signals={json.dumps(signals, ensure_ascii=False)}")
        return ERROR
    return None'''

# Profile plumbing
OLD_START = 'async def _start(headless: bool, log: RunLog):'
NEW_START = 'async def _start(headless: bool, log: RunLog, profile: pathlib.Path | None = None):'
OLD_USERDATA = '        user_data_dir=str(PROFILE),'
NEW_USERDATA = '        user_data_dir=str(profile or PROFILE),'

OLD_COOKIE = 'def _cookie_auth() -> dict:'
NEW_COOKIE = 'def _cookie_auth(profile: pathlib.Path | None = None) -> dict:'
OLD_COOKIEPATH = '    path = PROFILE / "Default" / "Network" / "Cookies"'
NEW_COOKIEPATH = '    path = (profile or PROFILE) / "Default" / "Network" / "Cookies"'

OLD_DOCTOR = 'async def _doctor_once(headed: bool, log: RunLog) -> int:'
NEW_DOCTOR = 'async def _doctor_once(headed: bool, log: RunLog, profile: pathlib.Path | None = None) -> int:'
OLD_DOCTOR_START = '    browser = await _start(headless=not headed, log=log)'
NEW_DOCTOR_START = '    browser = await _start(headless=not headed, log=log, profile=profile)'

OLD_DOCTOR_ASYNC = 'async def doctor_async(headed: bool, log: RunLog) -> int:'
NEW_DOCTOR_ASYNC = 'async def doctor_async(headed: bool, log: RunLog, profile: pathlib.Path | None = None) -> int:'
OLD_DOCTOR_META = '''async def doctor_async(headed: bool, log: RunLog, profile: pathlib.Path | None = None) -> int:
    meta = _cookie_auth()
    log.write(f"COOKIE_CHECK'''
NEW_DOCTOR_META = '''async def doctor_async(headed: bool, log: RunLog, profile: pathlib.Path | None = None) -> int:
    meta = _cookie_auth(profile)
    log.write(f"COOKIE_CHECK'''
OLD_DOCTOR_CALL = '    code = await _doctor_once(headed, log)\n    if code == ERROR and not headed:'
NEW_DOCTOR_CALL = '    code = await _doctor_once(headed, log, profile=profile)\n    if code == ERROR and not headed:'
OLD_DOCTOR_RETRY = '        code = await _doctor_once(True, log)'
NEW_DOCTOR_RETRY = '        code = await _doctor_once(True, log, profile=profile)'

OLD_COLLECT = '''async def _collect_async(kind: str, url: str, limit: int, keyword: str | None,
                         with_replies: bool, interval_min: int, interval_max: int,
                         log: RunLog) -> int:
    meta = _cookie_auth()'''
NEW_COLLECT = '''async def _collect_async(kind: str, url: str, limit: int, keyword: str | None,
                         with_replies: bool, interval_min: int, interval_max: int,
                         log: RunLog, profile: pathlib.Path | None = None,
                         risk_fixture: dict | None = None) -> int:
    meta = _cookie_auth(profile)'''
OLD_COLLECT_START = '    browser = await _start(headless=True, log=log)'
NEW_COLLECT_START = '    browser = await _start(headless=True, log=log, profile=profile)'

FIXTURE_CHECK = '''    if risk_fixture is not None:
        if risk_from_signals(risk_fixture):
            _save_error(kind, f"fixture://{keyword or ''}", "risk-fixture", "", log,
                        signals=risk_fixture)
            log.write(f"RISK_CONTROL_FIXTURE={json.dumps(risk_fixture, ensure_ascii=False)}")
            return ERROR
        log.write("RISK_FIXTURE_NOT_RISK")

'''

replacements = [
    ("import os\nimport pathlib\nimport random\nimport sys", "import os\nimport pathlib\nimport random\nimport re\nimport sys"),
    (OLD_RISK, NEW_RISK),
    ("\n\ndef utc() -> str:", RISK_FUNC + "\n\ndef utc() -> str:"),
    (OLD_SAVE, NEW_SAVE),
    (OLD_RISK_CHECK, NEW_RISK_CHECK),
    (OLD_START, NEW_START),
    (OLD_USERDATA, NEW_USERDATA),
    (OLD_COOKIE, NEW_COOKIE),
    (OLD_COOKIEPATH, NEW_COOKIEPATH),
    (OLD_DOCTOR, NEW_DOCTOR),
    (OLD_DOCTOR_START, NEW_DOCTOR_START),
    (OLD_DOCTOR_ASYNC, NEW_DOCTOR_ASYNC),
    (OLD_DOCTOR_META, NEW_DOCTOR_META),
    (OLD_DOCTOR_CALL, NEW_DOCTOR_CALL),
    (OLD_DOCTOR_RETRY, NEW_DOCTOR_RETRY),
    (OLD_COLLECT, NEW_COLLECT),
    (OLD_COLLECT_START, NEW_COLLECT_START),
]

for old, new in replacements:
    count = text.count(old)
    if count != 1:
        print(f"ABORT: pattern count={count} for {old[:60]!r}")
        sys.exit(1)
    text = text.replace(old, new)

# Insert fixture check right after the cookie check block in _collect_async.
anchor = '''    if not (meta["auth_token"] and meta["ct0"]):
        log.write("SESSION_EXPIRED (no auth cookies in profile; browser not launched)")
        return SESSION_EXPIRED
    DATA.mkdir(parents=True, exist_ok=True)'''
new_anchor = '''    if not (meta["auth_token"] and meta["ct0"]):
        log.write("SESSION_EXPIRED (no auth cookies in profile; browser not launched)")
        return SESSION_EXPIRED
''' + FIXTURE_CHECK + '''    DATA.mkdir(parents=True, exist_ok=True)'''
if text.count(anchor) != 1:
    print("ABORT: collect anchor not unique")
    sys.exit(1)
text = text.replace(anchor, new_anchor)

# CLI: add --profile / --risk-fixture
old_doctor_parser = '''    d = sub.add_parser("doctor", help="check X session in the dedicated profile")
    d.add_argument("--headed", action="store_true", help="run Chrome headed instead of headless")
    d.add_argument("--timeout", type=int, default=90)'''
new_doctor_parser = '''    d = sub.add_parser("doctor", help="check X session in the dedicated profile")
    d.add_argument("--headed", action="store_true", help="run Chrome headed instead of headless")
    d.add_argument("--timeout", type=int, default=90)
    d.add_argument("--profile", help="override user-data-dir (testing only)")'''
old_search_parser = '''    s = sub.add_parser("search", help="collect public tweets from x.com search (read-only)")
    s.add_argument("--keyword", required=True)
    s.add_argument("--limit", type=int, default=20)
    s.add_argument("--interval-min", type=int, default=8)
    s.add_argument("--interval-max", type=int, default=12)'''
new_search_parser = '''    s = sub.add_parser("search", help="collect public tweets from x.com search (read-only)")
    s.add_argument("--keyword", required=True)
    s.add_argument("--limit", type=int, default=20)
    s.add_argument("--interval-min", type=int, default=8)
    s.add_argument("--interval-max", type=int, default=12)
    s.add_argument("--profile", help="override user-data-dir (testing only)")
    s.add_argument("--risk-fixture", help="JSON fixture signals for controlled exit=3 test")'''
old_dispatch_doctor = '''        if args.command == "doctor":
            code = asyncio.run(asyncio.wait_for(doctor_async(args.headed, log), timeout=args.timeout))'''
new_dispatch_doctor = '''        if args.command == "doctor":
            prof = pathlib.Path(args.profile) if args.profile else None
            code = asyncio.run(asyncio.wait_for(doctor_async(args.headed, log, profile=prof), timeout=args.timeout))'''
old_dispatch_search = '''                    url = f"https://x.com/search?q={quote(keyword)}&f=live"
                    code = asyncio.run(asyncio.wait_for(
                        _collect_async("search", url, limit, keyword, False, imin, imax, log),
                        timeout=MAX_SECONDS + 180))'''
new_dispatch_search = '''                    url = f"https://x.com/search?q={quote(keyword)}&f=live"
                    prof = pathlib.Path(args.profile) if args.profile else None
                    fixture = None
                    if args.risk_fixture:
                        fixture = json.loads(pathlib.Path(args.risk_fixture).read_text(encoding="utf-8"))
                    code = asyncio.run(asyncio.wait_for(
                        _collect_async("search", url, limit, keyword, False, imin, imax, log,
                                       profile=prof, risk_fixture=fixture),
                        timeout=MAX_SECONDS + 180))'''

for old, new in [
    (old_doctor_parser, new_doctor_parser),
    (old_search_parser, new_search_parser),
    (old_dispatch_doctor, new_dispatch_doctor),
    (old_dispatch_search, new_dispatch_search),
]:
    if text.count(old) != 1:
        print(f"ABORT cli: pattern count={text.count(old)} for {old[:60]!r}")
        sys.exit(1)
    text = text.replace(old, new)

TARGET.write_text(text, encoding="utf-8", newline="\n")
print("patched", TARGET, "bytes", TARGET.stat().st_size)
