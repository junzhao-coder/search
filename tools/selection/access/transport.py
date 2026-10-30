"""Two transports, two very different trust levels.

`PublicHttpTransport` — no profile, no cookies, no account state. It refuses
redirects outright: `urlopen` would otherwise follow a 302 to an unvalidated
host inside a single budget charge, which is exactly the "one charge, many
requests" hole this batch must close. A 3xx comes back as a result and the
command exits non-zero; it is not retried.

`AuthenticatedBrowserTransport` — reuses the dedicated Chrome profile that
`login` wrote, so `search/detail/comments` after a login actually see the
account state. It never reads, exports or logs cookies/localStorage: the page
content is the only thing that leaves the browser. Each navigation is charged
by the caller before it happens, and the landed URL must stay on the target
domain or the run aborts and locks.
"""

from __future__ import annotations

import asyncio
import copy
import json
import pathlib
import time
import urllib.error
import urllib.parse
import urllib.request

from . import diagnostics
from . import records as rec

UA = "two-selection-access/1.0 (+local research)"
REDIRECT_CODES = (301, 302, 303, 307, 308)


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Turn every redirect into an HTTPError instead of following it."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: D102
        return None


def _opener() -> urllib.request.OpenerDirector:
    return urllib.request.build_opener(_NoRedirect)


class RefusedTransport:
    """Default in this batch: no socket is opened, ever.

    `offline = True` is the only exemption from the platform guard: this class
    cannot reach the network, so charging it would be noise. Everything else
    (public-http, browser) must carry a platform ledger.
    """

    mode = "offline"
    offline = True

    def fetch(self, url: str) -> dict:
        return {"status": None, "text": "", "json": None, "url": url,
                "final_url": url, "redirect": None, "error": "network_disabled_offline_batch"}


class PublicHttpTransport:
    """Unauthenticated HTTP. No redirects, no profile, no cookies."""

    mode = "public-http"

    def __init__(self, timeout: float = 20.0) -> None:
        self.timeout = timeout
        self._open = _opener()

    def fetch(self, url: str) -> dict:
        request = urllib.request.Request(url, headers={
            "User-Agent": UA, "Accept": "text/html,application/json;q=0.9,*/*;q=0.8"})
        try:
            with self._open.open(request, timeout=self.timeout) as response:
                body = response.read(2_000_000)
                status = response.status
                final_url = response.geturl()
        except urllib.error.HTTPError as exc:
            body = b""
            try:
                body = exc.read(200_000)
            except Exception:  # noqa: BLE001
                pass
            text = body.decode("utf-8", "replace")
            if exc.code in REDIRECT_CODES:
                return {"status": exc.code, "text": text, "json": None, "url": url,
                        "final_url": exc.headers.get("Location") or url,
                        "redirect": {"code": exc.code,
                                     "location": exc.headers.get("Location")},
                        "error": f"redirect_not_followed:{exc.code}"}
            return {"status": exc.code, "text": text, "json": None, "url": url,
                    "final_url": url, "redirect": None, "error": None}
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            return {"status": None, "text": "", "json": None, "url": url,
                    "final_url": url, "redirect": None,
                    "error": f"transport:{type(exc).__name__}"}
        text = body.decode("utf-8", "replace")
        parsed = None
        stripped = text.lstrip()
        if stripped.startswith("{"):
            try:
                parsed = json.loads(text)
            except json.JSONDecodeError:
                parsed = None
        return {"status": status, "text": text, "json": parsed, "url": url,
                "final_url": final_url, "redirect": None, "error": None}


class BrowserStartFailed(RuntimeError):
    """`uc.start` raised: the browser never launched. Never a risk signal."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def _short_reason(exc: BaseException, limit: int = 120) -> str:
    """One-line, bounded reason so a diagnostic stays readable."""
    text = " ".join(str(exc or "").split())
    return f"{type(exc).__name__}:{text}"[:limit] if text else type(exc).__name__


class AuthenticatedBrowserTransport:
    """Drives the dedicated profile so account state is actually reused.

    `fetch` is called *after* the caller charged the budget. It performs one
    navigation, waits for the document, and returns the rendered HTML. The
    browser is opened lazily on first use and closed by `close()`.

    **One loop only.** A nodriver Browser/connection is bound to the event loop
    that created it: awaiting it from another loop does not raise, it hangs
    forever. So this transport owns a single loop (`self._loop`) and runs both
    the launch and every navigation on it.

    **One total deadline.** Launch, navigation, the readiness wait, the content
    read and the final-URL read all share a single budget of wall-clock time:
    every phase is bounded by the *remaining* time, never by a fresh timeout.
    Three independent `wait_for` calls used to add up to 3x the intended
    budget, and a launch that never returned was unbounded.

    **Readiness is observed, not assumed.** After navigation the transport waits
    for a state it can actually see (readyState + result container / candidate
    links / explicit empty / wall markers) before reading the content, so a
    still-loading SPA is not read as "an empty but complete page". The selectors
    used for that are **assumptions** (no real Zhihu page has been observed in
    this batch) and every diagnostic says so.
    """

    mode = "authenticated-browser"

    def __init__(self, profile, *, headless: bool = True, timeout: float = 60.0,
                 allowed_host_suffix: str = "zhihu.com", browser=None,
                 clock=None, site: SiteProfile | None = None) -> None:
        self.profile = pathlib.Path(profile).expanduser().resolve()
        self.headless = headless
        self.timeout = timeout
        self.allowed_host_suffix = allowed_host_suffix
        self.site = site or ZHIHU_SITE
        self._browser = browser
        self._owns_browser = browser is None
        self._clock = clock
        self._loop = None
        self.navigations: list[str] = []
        self.diagnostics: dict = {}

    # -- lifecycle ---------------------------------------------------------
    def _get_loop(self):
        """The one loop this transport uses for launch and every navigation."""
        if self._loop is None or self._loop.is_closed():
            self._loop = asyncio.new_event_loop()
        return self._loop

    def _ensure_browser(self, deadline: float | None = None):
        if self._browser is not None:
            return self._browser
        from . import browser as browser_mod  # local: nodriver is optional

        info = browser_mod.available()
        if not info["usable"]:
            raise RuntimeError("browser_unavailable")
        import nodriver as uc

        async def _start():
            return await uc.start(**self._launch_kwargs(info))

        loop = self._get_loop()
        remaining = _remaining(deadline)
        try:
            self._browser = loop.run_until_complete(
                asyncio.wait_for(_start(), timeout=remaining))
        except asyncio.TimeoutError as exc:
            raise TimeoutError("browser_start_timeout") from exc
        except Exception as exc:  # noqa: BLE001 - a failed launch is data, not a stack
            # `uc.start` can fail for reasons that have nothing to do with the
            # request (relative profile path, a busy port, a missing browser).
            # It must become a structured result so the ledger can tell a failed
            # launch apart from a failed request.
            raise BrowserStartFailed(_short_reason(exc)) from exc
        return self._browser

    def _launch_kwargs(self, info: dict) -> dict:
        """The exact kwargs handed to `uc.start` (testable without a browser).

        The UA is applied as a Chrome *launch switch* (`--user-agent=`), not via
        `Network.setUserAgentOverride`: the switch is in effect from the very
        first request, so the server-side render decision is made with the
        mobile UA instead of after a desktop-UA load.
        """
        kwargs = {"headless": self.headless, "user_data_dir": str(self.profile),
                  "browser_executable_path": info.get("chrome")}
        if self.site.user_agent:
            kwargs["browser_args"] = [f"--user-agent={self.site.user_agent}"]
        return kwargs

    def close(self) -> None:
        if self._owns_browser and self._browser is not None:
            try:
                self._browser.stop()
            except Exception:  # noqa: BLE001
                pass
            self._browser = None
        if self._loop is not None and not self._loop.is_closed():
            try:
                self._loop.close()
            except Exception:  # noqa: BLE001
                pass
            self._loop = None

    # -- one navigation ----------------------------------------------------
    def fetch(self, url: str) -> dict:
        deadline = _deadline(self.timeout)
        diag: dict = {"requested_url": rec.sanitize_url(url), "phase": "start",
                      "selectors_assumed": list(diagnostics.assumed_selectors(self.site.name))}
        try:
            browser = self._ensure_browser(deadline)
        except BrowserStartFailed as exc:
            # structured, distinguishable from a request failure, never a risk
            error = f"browser_start_failed:{exc.reason}"
            diag.update({"phase": "start", "state": "start_failed", "error": error})
            self.diagnostics = diagnostics.sanitize(diag)
            return {"status": None, "text": "", "json": None, "url": url,
                    "final_url": url, "final_url_known": False, "redirect": None,
                    "error": error, "diagnostics": self.diagnostics}
        except RuntimeError as exc:
            diag.update({"phase": "start", "state": "unavailable", "error": str(exc)})
            self.diagnostics = diagnostics.sanitize(diag)
            return {"status": None, "text": "", "json": None, "url": url,
                    "final_url": url, "final_url_known": False, "redirect": None,
                    "error": str(exc), "diagnostics": self.diagnostics}
        except TimeoutError as exc:
            diag.update({"phase": "start", "state": "unknown", "error": "browser_start_timeout"})
            self.diagnostics = diagnostics.sanitize(diag)
            return {"status": None, "text": "", "json": None, "url": url,
                    "final_url": url, "final_url_known": False, "redirect": None,
                    "error": "browser:TimeoutError", "diagnostics": self.diagnostics}
        try:
            html, final_url, final_known, probe = _navigate(
                browser, url, deadline=deadline, loop=self._get_loop(), site=self.site)
        except TimeoutError as exc:
            diag.update({"phase": "navigate", "state": "unknown", "error": "browser:TimeoutError"})
            self.diagnostics = diagnostics.sanitize(diag)
            return {"status": None, "text": "", "json": None, "url": url,
                    "final_url": url, "final_url_known": False, "redirect": None,
                    "error": "browser:TimeoutError", "diagnostics": self.diagnostics}
        except Exception as exc:  # noqa: BLE001 - a dead tab is a transport error
            diag.update({"phase": "navigate", "state": "unknown",
                         "error": f"browser:{type(exc).__name__}"})
            self.diagnostics = diagnostics.sanitize(diag)
            return {"status": None, "text": "", "json": None, "url": url,
                    "final_url": url, "final_url_known": False, "redirect": None,
                    "error": f"browser:{type(exc).__name__}", "diagnostics": self.diagnostics}

        diag.update({"phase": "read", "html_bytes": len(html or ""), "probe": probe,
                     "probe_level": probe.get("level"),
                     "probe_elapsed_ms": probe.get("timings_ms") or {},
                     "state": probe.get("state") or "ready",
                     "ready_state": probe.get("readyState"),
                     "anchors_total": probe.get("anchors_total"),
                     "anchors_recognized": probe.get("anchors_recognized"),
                     "anchors_rejected": probe.get("anchors_rejected"),
                     "href_shapes": probe.get("shapes") or {},
                     "dom_anchor_count": probe.get("anchorCount"),
                     "render_wait_ms": probe.get("render_wait_ms"),
                     "render_wait_exhausted": probe.get("render_wait_exhausted"),
                     # the normal path must say where we actually landed, not
                     # only the failure path: without this a successful run had
                     # no final_url at all in its diagnostics.
                     "final_url": rec.sanitize_url(final_url) if final_known else None,
                     "final_url_known": bool(final_known)})
        diag["elapsed_ms"] = _elapsed_ms(deadline)
        if probe.get("wall"):
            # a real wall: lock on the original budget, do not keep reading
            diag.update({"state": "risk", "risk": f"text:{probe['wall']}"})
            self.diagnostics = diagnostics.sanitize(diag)
            return {"status": None, "text": "", "json": None, "url": url,
                    "final_url": "", "final_url_known": False, "redirect": None,
                    "error": f"browser:risk:text:{probe['wall']}",
                    "diagnostics": self.diagnostics}
        self.diagnostics = diagnostics.sanitize(diag)
        if not final_known:
            # the landing URL could not be read: say "unknown" instead of
            # pretending the requested URL is where we ended up
            self.diagnostics = diagnostics.sanitize({**self.diagnostics,
                                                     "final_url": None,
                                                     "final_url_known": False,
                                                     "state": "unknown",
                                                     "error": "final_url_unknown"})
        if final_url:
            self.navigations.append(final_url)
        if final_known and not _same_site(final_url, self.allowed_host_suffix):
            self.diagnostics = diagnostics.sanitize({**self.diagnostics,
                                                     "final_url": rec.sanitize_url(final_url),
                                                     "state": "risk"})
            return {"status": None, "text": "", "json": None, "url": url,
                    "final_url": final_url, "final_url_known": True, "redirect": None,
                    "error": f"offsite_redirect:{urllib.parse.urlsplit(final_url).hostname}",
                    "diagnostics": self.diagnostics}
        return {"status": 200, "text": html, "json": None, "url": url,
                "final_url": final_url or url, "final_url_known": final_known,
                "redirect": None, "error": None, "diagnostics": self.diagnostics,
                "probe": probe}


def _remaining(deadline: float | None) -> float:
    """Seconds left on the shared deadline (never a fresh budget)."""
    if deadline is None:
        return 0.0
    left = deadline - time.monotonic()
    if left <= 0:
        raise TimeoutError("deadline_exceeded")
    return left


def _deadline(timeout: float) -> float:
    return time.monotonic() + max(0.05, float(timeout))


def _elapsed_ms(deadline: float | None) -> int:
    if deadline is None:
        return 0
    return int(max(0.0, (_deadline(0) - deadline) * 1000))


#: Per-site knobs for the shared transport. One transport implementation, many
#: sites: the only things a new platform supplies are its link shapes, its
#: container selectors and its wall/empty wording. Anything else (loop, deadline,
#: probe tiers, readiness) stays here so no adapter can quietly re-implement it.
class SiteProfile:
    """What a site contributes to the shared transport."""

    def __init__(self, name: str, *, shape_rules, recognized_keys,
                 result_selectors: str, list_selectors: str,
                 wall_markers, empty_markers, user_agent: str | None = None) -> None:
        self.name = name
        #: (key, JS boolean expression over `href`) -- order matters, first match wins
        self.shape_rules = tuple(shape_rules)
        #: which shape keys count as "recognised content" for readiness
        self.recognized_keys = tuple(recognized_keys)
        self.result_selectors = result_selectors
        self.list_selectors = list_selectors
        self.wall_markers = tuple(wall_markers)
        self.empty_markers = tuple(empty_markers)
        #: browser User-Agent for this site (None = leave Chrome's default).
        #: Zhihu keeps None so its accepted behaviour cannot drift.
        self.user_agent = user_agent

    def with_user_agent(self, user_agent: str | None):
        """A copy with a different UA; the module-level profile stays untouched."""
        clone = copy.copy(self)
        clone.user_agent = user_agent
        return clone

    @property
    def shape_keys(self) -> tuple:
        return tuple(key for key, _expr in self.shape_rules) + ("other",)


#: Zhihu (default): the shapes the existing adapter has always used.
ZHIHU_SITE = SiteProfile(
    "zhihu",
    shape_rules=(
        ("answer", r"/\/question\/\d+\/answer\/\d+\/?$/.test(href)"),
        ("question", r"/\/question\/\d+\/?$/.test(href)"),
        ("article", r"/\/p\/\d+\/?$/.test(href)"),
        ("video", r"/\/zvideo\/\d+\/?$/.test(href)"),
    ),
    recognized_keys=("answer", "question", "article", "video"),
    result_selectors='[class*="Result"],[class*="Search"],[data-zop*="Search"]',
    list_selectors='[class*="List"],[class*="Card"],[class*="Item"]',
    wall_markers=("安全验证", "验证码", "访问异常", "操作频繁", "请求过于频繁",
                  "系统检测到", "请登录后查看", "请先登录", "请登录知乎"),
    empty_markers=("没有找到", "暂无相关", "无搜索结果", "没有更多结果"),
)


#: Observed page state, read from the DOM only (no reload, no retry, no extra
#: API call, no UA change, no mode switch).
#:
#: The probe is **tiered and light first**: one heavy `evaluate` that pulled
#: `document.body.innerText` plus hundreds of hrefs blocked the CDP call on a
#: real page (the run timed out inside `navigate`, before any state was read).
#: So level 1 asks for almost nothing, and the heavier levels only run when the
#: light one succeeded and the page still looks unready.
def _light_js(site: SiteProfile) -> str:
    """Level 1: readyState + anchor count + the **shape histogram** of the hrefs.

    Every anchor seen is classified into one bucket: the site's own content
    shapes first (first rule wins), then the generic fallbacks
    (`other_same_origin` / `other_cross_origin` / `relative_other` / `non_http`).
    That histogram is what tells "13 anchors, none of them a content link" apart
    from "13 content links the parser rejected" — two very different diagnoses.
    """
    init = ", ".join(f"{key}:0" for key in site.shape_keys)
    init = f"{init}, other_same_origin:0, other_cross_origin:0, relative_other:0, non_http:0"
    branches = []
    for index, (key, expr) in enumerate(site.shape_rules):
        keyword = "if" if index == 0 else "else if"
        branches.append(f"    {keyword} ({expr}) shapes.{key}++;")
    branches += [
        "    else if (!href || href.charAt(0) === '#' || /^(javascript|mailto|tel|data):/i.test(href)) shapes.non_http++;",
        "    else if (/^[a-z][a-z0-9+.-]*:/i.test(href) || href.slice(0, 2) === '//') {",
        "      let host = '';",
        "      try { host = new URL(href, document.baseURI).hostname; } catch (e) { host = ''; }",
        "      if (host && host === location.hostname) shapes.other_same_origin++;",
        "      else shapes.other_cross_origin++;",
        "    }",
        "    else shapes.relative_other++;",
    ]
    return "\n".join([
        "(() => {",
        "  const state = document.readyState || '';",
        "  const anchors = document.querySelectorAll('a[href]');",
        f"  const shapes = {{{init}}};",
        "  const limit = Math.min(anchors.length, 600);",
        "  for (let i = 0; i < limit; i++) {",
        "    const href = anchors[i].getAttribute('href') || '';",
        *branches,
        "  }",
        "  return JSON.stringify({level:1, readyState: state, anchorCount: anchors.length,",
        "                         sampled: limit, shapes: shapes});",
        "})()",
    ])


def _medium_js(site: SiteProfile) -> str:
    return "\n".join([
        "(() => {",
        "  const counts = {",
        f"    result: document.querySelectorAll('{site.result_selectors}').length,",
        f"    list: document.querySelectorAll('{site.list_selectors}').length",
        "  };",
        "  return JSON.stringify({level:2, counts: counts});",
        "})()",
    ])


def _text_js(site: SiteProfile) -> str:
    markers = ", ".join(f"'{marker}'" for marker in site.wall_markers)
    empty = "|".join(site.empty_markers)
    return "\n".join([
        "(() => {",
        "  const text = (document.body && document.body.innerText) || '';",
        "  const slice = text.slice(0, 4000);",
        f"  const markers = [{markers}];",
        "  let wall = null;",
        "  for (const m of markers) { if (slice.indexOf(m) >= 0) { wall = m; break; } }",
        f"  const emptyish = /({empty})/.test(slice);",
        "  return JSON.stringify({level:3, wall: wall, emptyish: emptyish, textLen: text.length});",
        "})()",
    ])

#: Back-compat literal: the Zhihu level-1 probe script, built from ZHIHU_SITE
#: (a test asserts this script reads `document.readyState`). Another site never
#: needs it — it passes its own SiteProfile to the transport and the scripts are
#: generated by `_light_js` / `_medium_js` / `_text_js`.
PROBE_LIGHT_JS = _light_js(ZHIHU_SITE)

#: per-level short timeouts (seconds); a level that exceeds its own budget is
#: reported as unknown for that level and the wait stops there.
PROBE_LEVEL_TIMEOUTS = (2.0, 2.0, 4.0)

#: how long a `readyState=complete` page with no recognised anchors may keep
#: hydrating before we call it unknown instead of "an empty page that is done".
RENDER_WAIT_MAX = 5.0


def _parse_probe(raw, level: int) -> dict:
    """Probe payload, or a `legacy` marker when the tab did not answer ours."""
    if isinstance(raw, str):
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            # not our probe script (a stub tab): readiness was not observed
            return {"level": level, "legacy": True}
    elif isinstance(raw, dict):
        payload = dict(raw)
    else:
        payload = {"level": level}
    payload.setdefault("level", level)
    return payload


async def _probe(tab, level: int, deadline: float | None, site: SiteProfile):
    """One tiered probe with its own short timeout -> (payload|None, elapsed_ms).

    `None` means that level timed out; the caller degrades to that level's
    "unknown" instead of failing the whole navigation.
    """
    script = (_light_js(site), _medium_js(site), _text_js(site))[level - 1]
    # never let a probe eat the whole budget: half of what is left stays
    # reserved for the content read, so a stuck probe degrades to "unknown"
    # instead of turning the whole navigation into a hard timeout
    budget = min(PROBE_LEVEL_TIMEOUTS[level - 1], max(0.05, _remaining(deadline) * 0.5))
    started = time.monotonic()
    try:
        raw = await asyncio.wait_for(tab.evaluate(script), timeout=budget)
    except (asyncio.TimeoutError, TimeoutError):
        return None, int((time.monotonic() - started) * 1000)
    return _parse_probe(raw, level), int((time.monotonic() - started) * 1000)


def _navigate(browser, url: str, *, deadline: float | None = None,
              loop=None, site: SiteProfile | None = None) -> tuple[str, str, bool, dict]:
    """One navigation on an already-open browser object (nodriver-shaped).

    Runs on the loop that created `browser`. Launch-free: the caller already
    opened the browser under the same deadline. Every await is bounded by the
    *remaining* deadline, and the readiness wait observes the page instead of
    assuming it is done.
    """
    site = site or ZHIHU_SITE

    async def _run():
        tab = await asyncio.wait_for(browser.get(url), timeout=_remaining(deadline))
        probe = await _wait_ready(tab, deadline, site)
        html = await asyncio.wait_for(tab.get_content(), timeout=_remaining(deadline))
        final, known = "", False
        try:
            value = await asyncio.wait_for(tab.evaluate("location.href"),
                                           timeout=_remaining(deadline))
            final = str(value or "")
            known = bool(final)
        except Exception:  # noqa: BLE001 - URL evidence is best-effort
            final, known = "", False
        return html, final, known, probe

    active = loop if loop is not None else asyncio.new_event_loop()
    try:
        return active.run_until_complete(_run())
    finally:
        if loop is None and not active.is_closed():
            active.close()


async def _wait_ready(tab, deadline: float | None, site: SiteProfile | None = None) -> dict:
    """Wait until the page shows a state we can read, or the deadline is gone.

    Tiered and light first: level 1 (readyState + anchor count + the href shape
    histogram) must succeed before the heavier levels run at all. Each level has
    its own short timeout; a level that times out ends the wait with that level's
    answer ("unknown"), never with an overall failure. The total deadline is
    never reset by a level change.

    **Bounded render wait**: `readyState=complete` with zero recognised anchors
    is the shape of an SPA that has not hydrated yet, so the wait keeps re-reading
    level 1 (cheap) until anchors appear, the render cap (`RENDER_WAIT_MAX`)
    expires, or the deadline goes. It never reports a still-loading page as a
    finished, empty one.
    """
    site = site or ZHIHU_SITE
    probe: dict = {"level": 0, "readyState": "", "anchorCount": 0, "sampled": 0, "shapes": {},
                   "state": "unknown", "timings_ms": {}}
    render_started: float | None = None
    first_pass = True
    while True:
        # -- level 1: light (readyState + anchor count + href shapes) -------
        payload, ms = await _probe(tab, 1, deadline, site)
        probe["timings_ms"]["1"] = ms
        if payload is None:
            probe.update({"level": 1, "state": "unknown", "level_timeout": True})
            return probe
        probe.update(payload)
        if probe.get("legacy"):
            probe["state"] = "ready"
            probe["level"] = 1
            return probe
        shapes = probe.get("shapes") or {}
        histogram = {key: int(shapes.get(key, 0) or 0) for key in
                     (*site.shape_keys, "other_same_origin", "other_cross_origin",
                      "relative_other", "non_http")}
        probe["shapes"] = histogram
        recognized = sum(histogram.get(k, 0) for k in site.recognized_keys)
        # the histogram covers every sampled anchor, so the totals always add up
        probe["anchors_total"] = sum(histogram.values())
        probe["anchors_recognized"] = recognized
        probe["anchors_rejected"] = probe["anchors_total"] - recognized
        if probe.get("readyState") == "complete" and recognized:
            probe.update({"state": "result", "level": 1})
            return probe
        if first_pass:
            # -- level 2: medium (containers) -------------------------------
            first_pass = False
            medium, ms = await _probe(tab, 2, deadline, site)
            probe["timings_ms"]["2"] = ms
            if medium is None:
                probe.update({"level": 2, "state": "unknown", "level_timeout": True})
                return probe
            counts = (medium or {}).get("counts") or {}
            probe["contentish"] = int(counts.get("result") or 0) + int(counts.get("list") or 0)
            if probe.get("readyState") == "complete" and probe["contentish"] \
                    and probe["anchors_total"]:
                probe.update({"state": "ready", "level": 2})
                return probe
            # -- level 3: text markers (wall / empty) -----------------------
            text, ms = await _probe(tab, 3, deadline, site)
            probe["timings_ms"]["3"] = ms
            probe["level"] = 3
            if text is None:
                probe.update({"state": "unknown", "level_timeout": True})
                return probe
            probe.update({k: v for k, v in (text or {}).items()
                          if k in ("wall", "emptyish", "textLen")})
            if probe.get("wall"):
                probe["state"] = "risk"
                return probe
            if probe.get("emptyish"):
                probe["state"] = "empty"
                return probe
            if probe["anchors_total"]:
                # the page finished rendering and has anchors, but none of them
                # match this site's content shapes: that is a *readable page with
                # unknown link shapes*, not a page still loading. Returning here
                # is what makes "13 anchors, 0 recognised" reportable instead of
                # a timeout that tells us nothing.
                probe.update({"state": "ready", "level": 3})
                return probe
        # -- bounded render wait (only level 1 on repeat, it is cheap) ------
        if probe.get("readyState") == "complete":
            now = time.monotonic()
            if render_started is None:
                render_started = now
            probe["render_wait_ms"] = int((now - render_started) * 1000)
            if now - render_started >= RENDER_WAIT_MAX:
                probe.update({"state": "unknown", "render_wait_exhausted": True})
                return probe
        if deadline is not None and time.monotonic() >= deadline:
            probe["state"] = "unknown"
            return probe
        try:
            await asyncio.wait_for(asyncio.sleep(0.25), timeout=_remaining(deadline))
        except (asyncio.TimeoutError, TimeoutError):
            probe["state"] = "unknown"
            return probe


def _same_site(url: str, suffix: str) -> bool:
    host = (urllib.parse.urlsplit(url or "").hostname or "").lower()
    suffix = suffix.lower().lstrip(".")
    return host == suffix or host.endswith("." + suffix)
