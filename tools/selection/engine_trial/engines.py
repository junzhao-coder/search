"""Two thin engine adapters over the same page contract.

Playwright is the primary engine and is verified in this environment.  The
nodriver adapter reuses the project's existing Chrome/nodriver assumptions but
cannot be executed here because `nodriver` is not installed in any available
Python; its availability result says so instead of pretending a browser ran.

Both adapters expose the same small surface (`start`, `goto`, `evaluate`,
`click`, `wheel`, `wait`, `screenshot`, `close`, `environment`).  The collector
never imports either package itself.
"""

from __future__ import annotations

import asyncio
import importlib.metadata
import inspect
import json
import pathlib
import re
import shutil
import sys
import tempfile
import time

from tools.selection.access import browser as browser_mod

BROWSER_ARGS = ["--no-first-run", "--no-default-browser-check",
                "--disable-background-networking"]


class EngineUnavailable(RuntimeError):
    """The adapter exists, but this environment cannot run it."""

    def __init__(self, reason: str, detail=None) -> None:
        super().__init__(reason)
        self.reason = reason
        self.detail = detail or {}

    def as_dict(self) -> dict:
        return {"reason": self.reason, **self.detail}


def _chrome_path() -> str | None:
    return browser_mod.available().get("chrome")


def _version(package: str) -> str | None:
    try:
        return importlib.metadata.version(package)
    except Exception:  # noqa: BLE001 - a missing distribution is a normal state
        return None


def playwright_available() -> dict:
    chrome = _chrome_path()
    try:
        import playwright  # noqa: F401
        installed = True
        detail = None
    except Exception as exc:  # noqa: BLE001
        installed = False
        detail = f"{type(exc).__name__}:{exc}"
    version = _version("playwright")
    reason = None
    if not installed:
        reason = "playwright_not_installed"
    elif not chrome:
        reason = "chrome_not_found"
    return {"engine": "playwright", "installed": installed, "version": version,
            "chrome": chrome, "usable": bool(installed and chrome),
            "reason": reason, "detail": detail,
            "repro": f'{sys.executable} -c "import playwright"'}


def nodriver_available() -> dict:
    info = browser_mod.available()
    reason = None
    detail = None
    if not info.get("nodriver"):
        reason = "nodriver_not_installed"
        try:
            import nodriver  # noqa: F401
        except Exception as exc:  # noqa: BLE001 - keep the exact import failure
            detail = f"{type(exc).__name__}: {exc}"
    elif not info.get("chrome"):
        reason = "chrome_not_found"
    return {"engine": "nodriver", "installed": bool(info.get("nodriver")),
            "version": info.get("nodriver_version"), "chrome": info.get("chrome"),
            "usable": bool(info.get("usable")), "reason": reason,
            "detail": detail,
            "repro": f'{sys.executable} -c "import nodriver"'}


def availability(engine: str) -> dict:
    if engine == "playwright":
        return playwright_available()
    if engine == "nodriver":
        return nodriver_available()
    raise ValueError(f"unknown engine: {engine}")


class PlaywrightDriver:
    name = "playwright"

    def __init__(self, *, headless: bool = False, channel: str = "chrome",
                 timeout_ms: int = 15000, profile=None) -> None:
        self.headless = bool(headless)
        self.channel = channel
        self.timeout_ms = int(timeout_ms)
        self.profile = profile
        self._owns_profile = profile is None
        self._pw = None
        self._context = None
        self._page = None
        self._profile_path: pathlib.Path | None = None
        self._browser_version = None
        self._closed = False

    @property
    def closed(self) -> bool:
        return self._closed

    def start(self) -> dict:
        from playwright.sync_api import sync_playwright

        self._pw = sync_playwright().start()
        self._profile_path = pathlib.Path(
            self.profile or tempfile.mkdtemp(prefix="dsh-engine-trial-pw-"))
        self._profile_path.mkdir(parents=True, exist_ok=True)
        try:
            self._context = self._pw.chromium.launch_persistent_context(
                user_data_dir=str(self._profile_path), headless=self.headless,
                channel=self.channel, viewport={"width": 1280, "height": 720},
                args=BROWSER_ARGS, timeout=self.timeout_ms)
        except Exception:
            try:
                self._pw.stop()
            finally:
                self._pw = None
            if self._owns_profile and self._profile_path is not None:
                shutil.rmtree(self._profile_path, ignore_errors=True)
            raise
        self._page = (self._context.pages[0] if self._context.pages
                      else self._context.new_page())
        self._page.set_default_timeout(self.timeout_ms)
        try:
            self._browser_version = self._context.browser.version
        except Exception:  # noqa: BLE001 - version is evidence, not a precondition
            self._browser_version = None
        return {"engine": "playwright", "browser_version": self._browser_version,
                "channel": self.channel, "headless": self.headless,
                "profile": str(self._profile_path)}

    def goto(self, url: str) -> dict:
        started = time.perf_counter()
        response = self._page.goto(url, wait_until="load", timeout=self.timeout_ms)
        self._page.wait_for_function("document.readyState === 'complete'",
                                     timeout=self.timeout_ms)
        self._page.wait_for_selector(".image-text, .pb-comment-item",
                                     state="visible", timeout=self.timeout_ms)
        return {"url": self._page.url,
                "status": getattr(response, "status", None) if response else None,
                "ms": round((time.perf_counter() - started) * 1000, 1)}

    def evaluate(self, script: str):
        return self._page.evaluate(script)

    def click(self, selector: str) -> dict:
        locator = self._page.locator(selector).first
        if locator.count() == 0:
            return {"clicked": False, "reason": "not_found", "selector": selector}
        locator.scroll_into_view_if_needed(timeout=self.timeout_ms)
        box = locator.bounding_box()
        locator.click(timeout=self.timeout_ms)
        return {"clicked": True, "selector": selector, "box": box,
                "via": "playwright_locator_click"}

    def wheel(self, dx: int, dy: int) -> dict:
        # Synthetic CDP input; it does not move the Windows pointer.
        self._page.mouse.move(640, 360)
        self._page.mouse.wheel(dx, dy)
        return {"dx": dx, "dy": dy, "via": "playwright_mouse_wheel"}

    def wait(self, ms: int) -> None:
        self._page.wait_for_timeout(int(ms))

    def screenshot(self, path) -> dict:
        target = pathlib.Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        self._page.screenshot(path=str(target), full_page=False)
        return {"path": str(target), "bytes": target.stat().st_size}

    def close(self) -> dict:
        out = {"closed": False, "profile_removed": False, "errors": []}
        if self._context is not None:
            try:
                self._context.close()
                out["closed"] = True
            except Exception as exc:  # noqa: BLE001
                out["errors"].append(f"context:{type(exc).__name__}:{exc}")
            finally:
                self._context = None
                self._page = None
        if self._pw is not None:
            try:
                self._pw.stop()
            except Exception as exc:  # noqa: BLE001
                out["errors"].append(f"playwright:{type(exc).__name__}:{exc}")
            finally:
                self._pw = None
        if self._owns_profile and self._profile_path is not None:
            shutil.rmtree(self._profile_path, ignore_errors=True)
            out["profile_removed"] = not self._profile_path.exists()
        self._closed = True
        return out

    def environment(self) -> dict:
        return {"engine": "playwright", "playwright_version": _version("playwright"),
                "browser_version": self._browser_version, "channel": self.channel,
                "headless": self.headless,
                "profile": str(self._profile_path) if self._profile_path else None,
                "chrome": _chrome_path()}


class NodriverDriver:
    """Backup adapter.  Implemented against nodriver's documented helpers.

    This path is unverified in this environment: `nodriver` is not installed.
    `start()` raises `EngineUnavailable` with the exact import failure instead
    of launching some other browser and calling it nodriver.
    """

    name = "nodriver"

    def __init__(self, *, headless: bool = False, timeout: float = 30.0,
                 profile=None) -> None:
        self.headless = bool(headless)
        self.timeout = float(timeout)
        self.profile = profile
        self._owns_profile = profile is None
        self._loop = None
        self._browser = None
        self._tab = None
        self._profile_path: pathlib.Path | None = None
        self._closed = False

    @property
    def closed(self) -> bool:
        return self._closed

    def _run(self, coro):
        return self._loop.run_until_complete(asyncio.wait_for(coro, timeout=self.timeout))

    def start(self) -> dict:
        info = nodriver_available()
        if not info["usable"]:
            raise EngineUnavailable("nodriver_unavailable", info)
        import nodriver as uc

        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        self._profile_path = pathlib.Path(
            self.profile or tempfile.mkdtemp(prefix="dsh-engine-trial-nd-"))
        self._profile_path.mkdir(parents=True, exist_ok=True)
        self._browser = self._run(uc.start(
            headless=self.headless, user_data_dir=str(self._profile_path),
            browser_executable_path=info["chrome"], browser_args=BROWSER_ARGS))
        self._tab = getattr(self._browser, "main_tab", None)
        if self._tab is None:
            self._tab = self._run(self._browser.get("about:blank"))

        async def _configure_viewport():
            from nodriver import cdp

            # Match Playwright's 1280x720 CSS viewport so scrollHeight /
            # scrollY are comparable instead of depending on window chrome.
            await self._tab.send(cdp.emulation.set_device_metrics_override(
                width=1280, height=720, device_scale_factor=1, mobile=False))

        self._run(_configure_viewport())
        return {"engine": "nodriver", "version": info["version"],
                "chrome": info["chrome"], "headless": self.headless,
                "profile": str(self._profile_path)}

    def goto(self, url: str) -> dict:
        started = time.perf_counter()
        self._run(self._tab.get(url))
        for _ in range(60):
            if str(self.evaluate("document.readyState")) == "complete":
                break
            time.sleep(0.1)
        return {"url": str(self.evaluate("location.href")), "status": None,
                "ms": round((time.perf_counter() - started) * 1000, 1)}

    def evaluate(self, script: str):
        return self._run(self._tab.evaluate(script))

    def click(self, selector: str) -> dict:
        async def go():
            element = await self._tab.select(selector, timeout=self.timeout)
            if element is None:
                return {"clicked": False, "reason": "not_found", "selector": selector}
            # Scroll, let a scroll-triggered layout change settle, measure, and
            # only then send real mousePressed/mouseReleased.  A single
            # scroll+measure was observed to click stale coordinates when the
            # lazy-load handler moved #load-more during the same tick.
            scroll_js = (
                "(() => { const el = document.querySelector(" + json.dumps(selector) + ");"
                " if (!el) return false;"
                " el.scrollIntoView({block: 'center', inline: 'center'});"
                " return true; })()"
            )
            measure_js = (
                "(() => { const el = document.querySelector(" + json.dumps(selector) + ");"
                " if (!el) return null;"
                " const r = el.getBoundingClientRect();"
                " const x = r.left + r.width / 2, y = r.top + r.height / 2;"
                " const hit = document.elementFromPoint(x, y);"
                " return JSON.stringify({x: x, y: y, left: r.left, top: r.top,"
                " width: r.width, height: r.height,"
                " hit_ok: !!(hit && (hit === el || el.contains(hit))),"
                " hit: hit ? (hit.tagName + '#' + (hit.id || '')) : null});"
                " })()"
            )
            last_box = None
            for _ in range(3):
                if not await self._tab.evaluate(scroll_js):
                    return {"clicked": False, "reason": "not_found",
                            "selector": selector}
                # Wait for the layout to settle instead of a fixed sleep:
                # a scroll can trigger the fixture's lazy-load handler, which
                # moves #load-more while the browser is still laying out.
                for _ in range(10):
                    await asyncio.sleep(0.02)
                    raw = await self._tab.evaluate(measure_js)
                    box = json.loads(raw) if isinstance(raw, str) and raw else None
                    if (not isinstance(box, dict) or not box.get("width")
                            or not box.get("height")):
                        return {"clicked": False, "reason": "no_rect",
                                "selector": selector}
                    last_box = box
                    if (box.get("hit_ok") and 0 <= float(box["y"]) <= 720
                            and 0 <= float(box["x"]) <= 1280):
                        await self._tab.mouse_click(float(box["x"]), float(box["y"]))
                        return {"clicked": True, "selector": selector, "box": box,
                                "via": "nodriver_cdp_mouse_click"}
            return {"clicked": False, "reason": "not_hittable",
                    "selector": selector, "box": last_box}

        return self._run(go())

    def wheel(self, dx: int, dy: int) -> dict:
        async def go():
            from nodriver import cdp

            # Same pixel delta as Playwright's page.mouse.wheel: CDP
            # Input.dispatchMouseEvent(mouseWheel).  Tab.scroll_down() takes a
            # percentage of the window, so it is not comparable here.
            await self._tab.send(cdp.input_.dispatch_mouse_event(
                "mouseWheel", x=640, y=360, delta_x=dx, delta_y=dy,
                pointer_type="mouse"))
            return {"dx": dx, "dy": dy, "via": "nodriver_cdp_mouse_wheel",
                    "scrolled": True}

        return self._run(go())

    def wait(self, ms: int) -> None:
        time.sleep(max(0, int(ms)) / 1000.0)

    def screenshot(self, path) -> dict:
        target = pathlib.Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        self._run(self._tab.save_screenshot(str(target), format="png"))
        return {"path": str(target), "bytes": target.stat().st_size}

    def close(self) -> dict:
        out = {"closed": False, "profile_removed": False, "errors": []}
        if self._browser is not None:
            try:
                process = getattr(self._browser, "_process", None)

                async def _shutdown():
                    try:
                        await self._browser.aclose()
                    finally:
                        self._browser.stop()
                    # Browser.stop() terminates the process but does not wait
                    # for its asyncio transport; close it here so interpreter
                    # shutdown cannot print "I/O operation on closed pipe".
                    if process is not None:
                        try:
                            await asyncio.wait_for(process.wait(), timeout=5)
                        except Exception:  # noqa: BLE001
                            pass
                        transport = getattr(process, "_transport", None)
                        if transport is not None:
                            transport.close()

                self._run(_shutdown())
                out["closed"] = True
            except Exception as exc:  # noqa: BLE001
                out["errors"].append(f"browser:{type(exc).__name__}:{exc}")
            finally:
                self._browser = None
                self._tab = None
        if self._loop is not None:
            try:
                browser_mod._reclaim(self._loop)  # reuse the project's pipe cleanup
            except Exception:  # noqa: BLE001
                pass
            try:
                self._loop.close()
            except Exception:  # noqa: BLE001
                pass
            self._loop = None
        if self._owns_profile and self._profile_path is not None:
            shutil.rmtree(self._profile_path, ignore_errors=True)
            out["profile_removed"] = not self._profile_path.exists()
        self._closed = True
        return out

    def environment(self) -> dict:
        info = nodriver_available()
        browser_version = None
        try:
            user_agent = str(self.evaluate("navigator.userAgent") or "")
            match = re.search(r"Chrome/([0-9.]+)", user_agent)
            browser_version = match.group(1) if match else None
        except Exception:  # noqa: BLE001 - version is evidence, not a precondition
            browser_version = None
        return {"engine": "nodriver", "version": info["version"],
                "browser_version": browser_version, "chrome": info["chrome"],
                "headless": self.headless,
                "profile": str(self._profile_path) if self._profile_path else None}
