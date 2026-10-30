"""xhs_collect contract: CDP login gate, post-close recheck, verify classification."""

from __future__ import annotations

import asyncio
import importlib.util
import pathlib
import sqlite3
import sys
import tempfile
import types
import unittest

SCRIPT = pathlib.Path(r"C:\Users\19183\.dsh\tools\xhs-collect\xhs_collect.py")


def load():
    spec = importlib.util.spec_from_file_location("xhs_collect_test", SCRIPT)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


class FakeCookie:
    def __init__(self, name):
        self.name = name


class FakeJar:
    def __init__(self, names):
        self.names = names

    async def get_all(self):
        return [FakeCookie(n) for n in self.names]


class FakeBrowser:
    def __init__(self, names):
        self.cookies = FakeJar(names)
        self.stopped = False
        self.get_calls = 0

    async def get(self, url):
        self.get_calls += 1
        return self

    def stop(self):
        self.stopped = True


class XhsCollectTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.xc = load()

    def _profile(self, with_web=False):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        prof = pathlib.Path(tmp.name) / "profile"
        (prof / "Default" / "Network").mkdir(parents=True)
        conn = sqlite3.connect(prof / "Default" / "Network" / "Cookies")
        conn.execute("CREATE TABLE cookies (name TEXT, host_key TEXT)")
        conn.execute("INSERT INTO cookies VALUES ('a1','xiaohongshu.com')")
        if with_web:
            conn.execute("INSERT INTO cookies VALUES ('web_session','xiaohongshu.com')")
        conn.commit()
        conn.close()
        return prof

    def _run_login(self, names, *, file_has=False, timeout=0.05):
        prof = self._profile(False)
        browser = FakeBrowser(names)
        calls = {}

        async def fake_start(**kwargs):
            calls.update(kwargs)
            return browser

        file_calls = []
        orig_profile = self.xc.PROFILE
        orig_file = self.xc._has_web_session
        self.xc.PROFILE = prof
        self.xc._has_web_session = lambda p: file_calls.append(p) or file_has
        fake_uc = types.ModuleType("nodriver")
        fake_uc.start = fake_start
        old_uc = sys.modules.get("nodriver")
        sys.modules["nodriver"] = fake_uc
        try:
            code = asyncio.run(self.xc.login_async(
                timeout=timeout, poll=0.01, post_close_wait=0))
        finally:
            self.xc.PROFILE = orig_profile
            self.xc._has_web_session = orig_file
            if old_uc is None:
                sys.modules.pop("nodriver", None)
            else:
                sys.modules["nodriver"] = old_uc
        return code, browser, calls, file_calls

    def test_check_profile_states(self):
        missing = self.xc.check_profile(pathlib.Path(tempfile.gettempdir()) / "no-such-xhs")
        self.assertEqual((missing["exists"], missing["state"]), (False, "waiting_user"))
        waiting = self.xc.check_profile(self._profile(False))
        self.assertEqual(waiting["state"], "waiting_user")
        self.assertTrue(waiting["cookies"]["a1"])
        self.assertFalse(waiting["cookies"]["web_session"])
        ready = self.xc.check_profile(self._profile(True))
        self.assertEqual(ready["state"], "ready")
        self.assertTrue(ready["cookies"]["web_session"])

    def test_has_web_session_gate(self):
        self.assertFalse(self.xc._has_web_session(self._profile(False)))
        self.assertTrue(self.xc._has_web_session(self._profile(True)))

    def test_login_browser_cookie_visible_success(self):
        code, browser, calls, file_calls = self._run_login(["a1", "web_session"])
        self.assertEqual(code, 0)
        self.assertTrue(browser.stopped)
        self.assertIs(calls.get("headless"), False)
        self.assertEqual(browser.get_calls, 1)
        self.assertEqual(file_calls, [])  # browser cookie already proved it

    def test_login_file_recheck_after_close_success(self):
        code, browser, calls, file_calls = self._run_login([], file_has=True)
        self.assertEqual(code, 0)
        self.assertTrue(browser.stopped)
        self.assertEqual(len(file_calls), 1)  # the fixed false-negative path

    def test_login_both_absent_timeout_no_retry(self):
        code, browser, calls, file_calls = self._run_login([], file_has=False)
        self.assertEqual(code, 3)
        self.assertTrue(browser.stopped)
        self.assertEqual(len(file_calls), 1)
        self.assertEqual(browser.get_calls, 1)  # no retry / no second navigation


class VerifyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.xc = load()

    def test_verify_valid(self):
        self.assertEqual(self.xc.classify_verify("<html><h1>首页</h1></html>", cookie_present=True),
                         ("valid", 0))

    def test_verify_login_required(self):
        self.assertEqual(self.xc.classify_verify("<html><div>请登录</div></html>", cookie_present=True),
                         ("login_required", 4))

    def test_verify_risk(self):
        self.assertEqual(self.xc.classify_verify("<html>请完成安全验证</html>", cookie_present=True),
                         ("risk", 5))

    def test_verify_unknown_on_error(self):
        self.assertEqual(self.xc.classify_verify("", error="timeout"), ("unknown", 6))


if __name__ == "__main__":
    unittest.main()
