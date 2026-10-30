"""Weibo adapter: six commands, zero network.

Every transport here is a fake. The point of the suite is that the Weibo
adapter *reuses* the shared base (transport / budget / records / diagnostics)
and that its own rules fail closed: a wall locks, an unreadable page is not
"empty", an unsupported URL is not a success.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import pathlib
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import types
import unittest
from unittest import mock
from unittest import mock

REPO = pathlib.Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from tools.selection.access import browser as browser_mod  # noqa: E402
from tools.selection.access import budget as budget_mod  # noqa: E402
from tools.selection.access import codes  # noqa: E402
from tools.selection.access import diagnostics as diag_mod  # noqa: E402
from tools.selection.access import platform_budget as platform_mod  # noqa: E402
from tools.selection.access import records as rec  # noqa: E402
from tools.selection.access import transport as transport_mod  # noqa: E402
from tools.selection.access import weibo  # noqa: E402
from tools.selection.access import zhihu as zhihu_mod  # noqa: E402

COLLECTED = "2026-10-27T14:00:00Z"

SEARCH_HTML = """<html><body>
<a href="/detail/4900000000000001">学习计划模板分享</a>
<a href="/detail/4900000000000001">重复链接</a>
<a href="https://m.weibo.cn/status/4900000000000002">第二个</a>
<a href="/u/1234567">某人的主页</a>
</body></html>"""

UNKNOWN_HTML = """<html><body>
<a href="/people/someone">人物页</a><a href="/login">登录</a>
</body></html>"""

DETAIL_HTML = """<html><head>
<meta property="og:title" content="学习计划模板分享 - 微博">
<meta property="og:description" content="整理了一份可以直接打印的周计划模板">
<title>fallback</title></head><body><div>转发 3 · 评论 5 · 赞 12</div></body></html>"""

WALL_HTML = """<html><head><title>微博</title></head>
<body><div>访问过于频繁，请稍后再试</div></body></html>"""

COMMENTS_JSON = {
    "ok": 1,
    "data": {
        "data": [
            {"id": "c1", "text": "<span>同求</span>", "created_at": "Mon Oct 27 10:00:00 +0800 2026",
             "like_count": 4},
            {"id": "c2", "text": "我整理过一份", "created_at": "Mon Oct 27 11:00:00 +0800 2026",
             "like_count": 0},
        ],
        "max_id": 123456789,
    },
}


class FakeTransport:
    def __init__(self, response: dict) -> None:
        self.response = response
        self.urls: list[str] = []

    def fetch(self, url: str) -> dict:
        self.urls.append(url)
        return {"url": url, "final_url": url, "final_url_known": True,
                "redirect": None, **self.response}


class FakeClock:
    def __init__(self, start: float = 5_000_000.0) -> None:
        self.now = start

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


class FakeBrowser:
    """Serves the three snippets `wait_for_login` reads, per scripted step."""

    def __init__(self, steps: list[dict]) -> None:
        self.steps = steps
        self.index = 0
        self.evaluated: list[str] = []

    async def evaluate(self, script: str):
        self.evaluated.append(script)
        step = self.steps[min(self.index, len(self.steps) - 1)]
        self.index += 1
        if "location.href" in script:
            return step.get("url", "")
        if "hasLogout" in script:  # the Weibo signal collector (JSON, not a bool)
            if "signals" in step:
                return json.dumps(step["signals"])
            return json.dumps({"host": "weibo.com", "path": "/",
                               "hasLogout": bool(step.get("signed_in")),
                               "text": step.get("text", "")})
        return step.get("text", "")


class BrokenBrowser:
    async def evaluate(self, script: str):
        raise RuntimeError("tab_died")


class WeiboTestBase(unittest.TestCase):
    """Shared helpers: every metered call gets an isolated temp platform ledger."""

    def metered(self, calls: int = 10, seed: int = 0, batch: str = "t1"):
        led = getattr(self, "_plat", None)
        if led is None:
            led = platform_mod.PlatformLedger(self.dir / "platform.sqlite3",
                                              clock=self.clock,
                                              allow_test_manifest=True)
            import_isolated_snapshot(led, self.dir, self.clock)
            led.authorize_batch(batch, authorized_calls=calls, window_seconds=300,
                                source="test:isolated", seed_used=seed)
            self._plat = led
            self._pbatch = batch
        return led

    def rs(self, *args, **kwargs):
        kwargs.setdefault("platform", self.metered())
        kwargs.setdefault("batch_id", getattr(self, "_pbatch", "t1"))
        return weibo.run_search(*args, **kwargs)

    def rd(self, *args, **kwargs):
        kwargs.setdefault("platform", self.metered())
        kwargs.setdefault("batch_id", getattr(self, "_pbatch", "t1"))
        return weibo.run_detail(*args, **kwargs)

    def rc(self, *args, **kwargs):
        kwargs.setdefault("platform", self.metered())
        kwargs.setdefault("batch_id", getattr(self, "_pbatch", "t1"))
        return weibo.run_comments(*args, **kwargs)

    def lg(self, *args, **kwargs):
        kwargs.setdefault("platform", self.metered())
        kwargs.setdefault("batch_id", getattr(self, "_pbatch", "t1"))
        return weibo.login(*args, **kwargs)

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = pathlib.Path(self._tmp.name)
        self.clock = FakeClock()
        self._budgets: list = []

    def tearDown(self):
        for batch in self._budgets:
            try:
                batch.close()
            except Exception:  # noqa: BLE001 - already closed
                pass
        led = getattr(self, "_plat", None)
        if led is not None:
            try:
                led.close()
            except Exception:  # noqa: BLE001 - already closed
                pass
            self._plat = None
        self._tmp.cleanup()

    def budget(self, **kwargs):
        kwargs.setdefault("clock", self.clock)
        batch = budget_mod.open_budget(self.dir, **kwargs)
        self._budgets.append(batch)
        return batch


# --------------------------------------------------------------------------
# the adapter really reuses the shared base
# --------------------------------------------------------------------------
class ReuseTests(unittest.TestCase):
    def test_site_profile_is_data_not_a_second_transport(self):
        self.assertEqual(transport_mod.ZHIHU_SITE.name, "zhihu")
        self.assertEqual(weibo.SITE.name, "weibo")
        self.assertNotEqual(transport_mod.ZHIHU_SITE.shape_keys, weibo.SITE.shape_keys)
        light = transport_mod._light_js(weibo.SITE)
        self.assertIn("shapes.detail++", light)
        self.assertNotIn("question", light)

    def test_transport_defaults_to_zhihu_and_accepts_weibo(self):
        default = transport_mod.AuthenticatedBrowserTransport("/tmp/x")
        self.assertIs(default.site, transport_mod.ZHIHU_SITE)
        weib = transport_mod.AuthenticatedBrowserTransport(
            "/tmp/x", allowed_host_suffix=weibo.ALLOWED_HOST, site=weibo.SITE)
        self.assertIs(weib.site, weibo.SITE)

    def test_diagnostics_are_site_aware(self):
        hrefs = ["/detail/1234567890123456", "/u/1234567", "https://weibo.com/1/abc",
                 "https://evil.test/people/x"]
        weib = diag_mod.count_href_shapes(hrefs, site="weibo")
        self.assertEqual(weib["recognized"], 1)          # only the /detail/ id
        self.assertEqual(weib["total"], 4)
        zhih = diag_mod.count_href_shapes(["/question/1/answer/2"], site="zhihu")
        self.assertEqual(zhih["recognized"], 1)
        self.assertIn("/detail/<id>", diag_mod.assumed_selectors("weibo")[1])

    def test_source_tags_unknown_survives_only_for_known_sites(self):
        self.assertEqual(rec.clean_source("weibo:detail:status"), "weibo:detail:status")
        self.assertEqual(rec.clean_source("zhihu:detail:answer"), "zhihu:detail:answer")
        self.assertEqual(rec.clean_source("weibo:evil"), "redacted")
        self.assertEqual(rec.clean_source("evil:detail:status"), "redacted")

    def test_login_markers_are_weibo_specific_and_not_the_zhihu_ones(self):
        self.assertNotIn("知乎", weibo.SIGNED_IN_JS)
        # the collector reports account-specific controls; the decision is Python
        self.assertIn("hasLogout", weibo.SIGNED_IN_JS)
        self.assertIn("hasSettings", weibo.SIGNED_IN_JS)
        self.assertEqual(weibo.STRONG_SIGNALS, ("hasLogout",))
        # a bare "验证码" must never be a login wall: sign-in pages say 获取验证码
        self.assertNotIn("验证码", weibo.LOGIN_WALL_MARKERS)
        self.assertIn("访问过于频繁", weibo.LOGIN_WALL_MARKERS)

    def test_diagnostics_skeleton_is_whitelisted_and_names_the_phase(self):
        with tempfile.TemporaryDirectory() as tmp:
            payload = {"command": "search", "stop": "empty",
                       "diagnostics": {"phase": "read", "html_bytes": 12,
                                       "nickname": "someone", "cookies": "SECRET",
                                       "href_shapes": {"detail": 2}, "final_url": None}}
            weibo._write_diagnostics(tmp, payload)
            files = list(pathlib.Path(tmp).glob("search-*.json"))
            self.assertEqual(len(files), 1)
            written = json.loads(files[0].read_text(encoding="utf-8"))
            self.assertEqual(written["phase"], "read")
            self.assertEqual(written["parse_state"], "empty")
            dumped = json.dumps(written)
            self.assertNotIn("SECRET", dumped)
            self.assertNotIn("nickname", dumped)
            self.assertNotIn("cookies", dumped)

    def test_transport_reports_navigate_phase_when_get_hangs(self):
        class HangingBrowser:
            async def get(self, url):
                await asyncio.sleep(3600)

        transport = transport_mod.AuthenticatedBrowserTransport(
            "/tmp/x", browser=HangingBrowser(), timeout=0.3,
            allowed_host_suffix=weibo.ALLOWED_HOST, site=weibo.SITE)
        result = transport.fetch("https://m.weibo.cn/search?containerid=x")
        self.assertEqual(result["error"], "browser:TimeoutError")
        self.assertEqual(result["diagnostics"]["phase"], "navigate")
        self.assertEqual(result["diagnostics"]["state"], "unknown")


# --------------------------------------------------------------------------
# doctor (local only)
# --------------------------------------------------------------------------
class DoctorTests(WeiboTestBase):
    def _profile(self, names=("SUB", "SUBP"), values=("SECRET_SUB", "SECRET_SUBP")):
        profile = self.dir / "profile"
        network = profile / "Default" / "Network"
        network.mkdir(parents=True)
        conn = sqlite3.connect(network / "Cookies")
        conn.execute("CREATE TABLE cookies (host_key TEXT, name TEXT, value TEXT)")
        for name, value in zip(names, values):
            conn.execute("INSERT INTO cookies VALUES (?,?,?)",
                         (".weibo.com", name, value))
        conn.execute("INSERT INTO cookies VALUES (?,?,?)", (".zhihu.com", "z_c0", "SECRET_Z"))
        conn.commit()
        conn.close()
        return profile

    def test_doctor_reads_names_only_and_never_touches_network(self):
        profile = self._profile()
        out = weibo.doctor(profile)
        self.assertTrue(out["profile_exists"])
        self.assertTrue(out["cookie_db_exists"])
        self.assertEqual(out["network"], "none")
        self.assertEqual(out["online"], "unverified")
        self.assertTrue(out["cookie_names"]["SUB"])
        self.assertTrue(out["cookie_names"]["SUBP"])
        self.assertFalse(out["cookie_names"]["SCL"])
        self.assertEqual(out["cookie_count"], 2)      # zhihu cookie not counted
        self.assertNotIn("SECRET", json.dumps(out))   # values never leave

    def test_doctor_without_profile_is_not_an_error(self):
        out = weibo.doctor(self.dir / "missing")
        self.assertFalse(out["profile_exists"])
        self.assertFalse(out["cookie_db_exists"])
        self.assertEqual(out["cookie_names"], {})
        self.assertEqual(out["network"], "none")


# --------------------------------------------------------------------------
# login: the five states, on Weibo markers
# --------------------------------------------------------------------------
class LoginTests(WeiboTestBase):
    def test_signed_in_is_ok_without_spending_a_call(self):
        fake = FakeBrowser([{"url": "https://m.weibo.cn/", "signed_in": True}])
        result = self.lg(self.dir / "p", budget=self.budget(), clock=self.clock,
                             timeout=30, browser=fake)
        snapshot = self.budget().snapshot()
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["exit"], codes.EXIT_OK)
        self.assertEqual(snapshot["calls"], 0)   # login never eats the data budget

    def test_wall_is_risk_and_locks(self):
        fake = FakeBrowser([{"url": "https://passport.weibo.com/sso/signin",
                             "signed_in": False, "text": "访问过于频繁"}])
        result = self.lg(self.dir / "p", budget=self.budget(), clock=self.clock,
                             timeout=30, browser=fake)
        self.assertEqual(result["status"], "risk")
        self.assertEqual(result["risk_reason"], "text:访问过于频繁")
        self.assertEqual(result["exit"], codes.EXIT_RISK)

    def test_signin_copy_is_not_a_wall(self):
        fake = FakeBrowser([{"url": "https://passport.weibo.com/sso/signin",
                             "signed_in": False, "text": "获取验证码 短信验证码 密码登录"}])
        result = self.lg(self.dir / "p", budget=self.budget(), clock=self.clock,
                             timeout=10, browser=fake)
        self.assertNotEqual(result["status"], "risk")
        self.assertIsNone(result["risk_reason"])

    def test_timeout_and_poll_limit_are_different_nonzero_exits(self):
        fake = FakeBrowser([{"url": "https://m.weibo.cn/", "signed_in": False}])
        timed = asyncio.run(browser_mod.wait_for_login(
            fake, profile=self.dir, budget=self.budget(), clock=self.clock, timeout=6,
            signed_in_js=weibo.SIGNED_IN_JS, wall_markers=weibo.LOGIN_WALL_MARKERS,
            signed_in_verdict=weibo.signed_in_verdict))
        self.assertEqual(timed["status"], "timeout")
        self.assertEqual(timed["exit"], codes.EXIT_LOGIN_TIMEOUT)

        fake2 = FakeBrowser([{"url": "https://m.weibo.cn/", "signed_in": False}])
        limited = asyncio.run(browser_mod.wait_for_login(
            fake2, profile=self.dir, budget=self.budget(batch_id="b2"), clock=self.clock,
            timeout=300, max_polls=2,
            signed_in_js=weibo.SIGNED_IN_JS, wall_markers=weibo.LOGIN_WALL_MARKERS,
            signed_in_verdict=weibo.signed_in_verdict))
        self.assertEqual(limited["status"], "poll_limit")
        self.assertEqual(limited["exit"], codes.EXIT_LOGIN_POLL_LIMIT)

    def test_dead_tab_is_unknown_not_success(self):
        result = self.lg(self.dir / "p", budget=self.budget(), clock=self.clock,
                             timeout=10, browser=BrokenBrowser())
        self.assertEqual(result["status"], "unknown")
        self.assertEqual(result["exit"], codes.EXIT_LOGIN_UNKNOWN)


# --------------------------------------------------------------------------
# search: empty vs unknown vs wall must be different answers
# --------------------------------------------------------------------------
class SearchTests(WeiboTestBase):
    def test_html_links_become_status_records(self):
        transport = FakeTransport({"status": 200, "text": SEARCH_HTML, "json": None,
                                   "diagnostics": {"state": "result"}})
        payload = self.rs("学习计划模板", batch=self.budget(), transport=transport,
                                   collected_at=COLLECTED, limit=5)
        self.assertEqual(payload["exit"], codes.EXIT_OK)
        self.assertEqual(payload["count"], 2)                    # duplicate collapsed
        self.assertEqual([r["native_id"] for r in payload["records"]],
                         ["4900000000000001", "4900000000000002"])
        first = payload["records"][0]
        self.assertEqual(first["type"], "status")
        self.assertEqual(first["source"], "weibo:search:status")
        self.assertEqual(first["url"], "https://m.weibo.cn/detail/4900000000000001")
        self.assertTrue(first["field_evidence"]["native_id"].startswith("url:"))
        self.assertIn("text", first["missing"])                  # listing has no body

    def test_empty_document_is_empty_not_success(self):
        transport = FakeTransport({"status": 200, "text": "", "json": None,
                                   "diagnostics": {"state": "empty"}})
        payload = self.rs("学习计划模板", batch=self.budget(), transport=transport,
                                   collected_at=COLLECTED)
        self.assertEqual(payload["exit"], codes.EXIT_EMPTY)
        self.assertEqual(payload["stop"], "empty")
        self.assertEqual(payload["count"], 0)

    def test_unrecognized_anchors_are_unsupported_not_empty(self):
        transport = FakeTransport({"status": 200, "text": UNKNOWN_HTML, "json": None,
                                   "diagnostics": {"state": "result"}})
        payload = self.rs("学习计划模板", batch=self.budget(), transport=transport,
                                   collected_at=COLLECTED)
        self.assertEqual(payload["exit"], codes.EXIT_UNSUPPORTED)
        self.assertEqual(payload["stop"], "unknown")
        self.assertEqual(payload["diagnostics"]["web_state"], "no_recognized_anchors")

    def test_wall_locks_the_batch(self):
        transport = FakeTransport({"status": None, "text": "", "json": None,
                                   "error": "browser:risk:text:验证码",
                                   "diagnostics": {"state": "risk", "risk": "text:验证码"}})
        batch = self.budget()
        payload = self.rs("学习计划模板", batch=batch, transport=transport,
                                   collected_at=COLLECTED)
        self.assertEqual(payload["exit"], codes.EXIT_RISK)
        locked = batch.snapshot()
        self.assertTrue(locked["locked"])
        self.assertEqual(locked["lock_source"], "search")
        self.assertIn("验证码", locked["lock_reason"])

    def test_locked_batch_refuses_the_next_search(self):
        batch = self.budget()
        batch.lock("text:安全验证", source="detail")
        batch.close()
        # a locked batch refuses to even open again: logging in / searching is
        # not a way around a lock
        with self.assertRaises(budget_mod.BudgetError) as caught:
            self.budget(batch_id="again")
        self.assertEqual(caught.exception.code, "batch_locked")

    def test_search_charges_one_call_before_fetching(self):
        batch = self.budget()
        self.rs("学习计划模板", batch=batch,
                         transport=FakeTransport({"status": 200, "text": SEARCH_HTML,
                                                  "json": None}),
                         collected_at=COLLECTED)
        snapshot = batch.snapshot()
        self.assertEqual(snapshot["calls"], 1)
        self.assertEqual(snapshot["records"], 2)

    def test_budget_refusal_happens_before_the_transport_is_touched(self):
        batch = self.budget(max_calls=1)
        batch.charge("search", "first")           # spend the only allowed call
        transport = FakeTransport({"status": 200, "text": SEARCH_HTML, "json": None})
        payload = self.rs("学习计划模板", batch=batch, transport=transport,
                                   collected_at=COLLECTED)
        self.assertEqual(payload["exit"], codes.EXIT_BUDGET)
        self.assertEqual(payload["stop"], "budget:calls_exhausted")
        self.assertEqual(transport.urls, [])      # charged first, fetched never


# --------------------------------------------------------------------------
# detail / comments: parent relationships
# --------------------------------------------------------------------------
class DetailAndCommentsTests(WeiboTestBase):
    def test_detail_returns_one_status_record(self):
        url = "https://m.weibo.cn/detail/4900000000000001"
        payload = self.rd(
            url, batch=self.budget(),
            transport=FakeTransport({"status": 200, "text": DETAIL_HTML, "json": None,
                                     "diagnostics": {"state": "ready"}}),
            collected_at=COLLECTED)
        self.assertEqual(payload["exit"], codes.EXIT_OK)
        record = payload["records"][0]
        self.assertEqual(record["type"], "status")
        self.assertEqual(record["native_id"], "4900000000000001")
        self.assertIsNone(record["parent_id"])
        self.assertEqual(record["title"], "学习计划模板分享 - 微博")
        self.assertTrue(record["text"].startswith("整理了一份"))
        self.assertEqual(record["field_evidence"]["text"], "html:meta[og:description]")

    def test_detail_on_a_wall_page_locks(self):
        url = "https://m.weibo.cn/detail/4900000000000001"
        batch = self.budget()
        payload = self.rd(
            url, batch=batch,
            transport=FakeTransport({"status": 200, "text": WALL_HTML, "json": None,
                                     "diagnostics": {"state": "ready"}}),
            collected_at=COLLECTED)
        self.assertEqual(payload["exit"], codes.EXIT_RISK)
        self.assertTrue(payload["stop"].startswith("risk:"))
        self.assertTrue(batch.snapshot()["locked"])

    def test_detail_rejects_profile_url_without_spending_a_call(self):
        batch = self.budget()
        payload = self.rd("https://m.weibo.cn/u/1234567", batch=batch,
                                   transport=FakeTransport({"status": 200, "text": "",
                                                            "json": None}),
                                   collected_at=COLLECTED)
        self.assertEqual(payload["exit"], codes.EXIT_INPUT)
        self.assertEqual(payload["stop"], "unsupported_content_url")
        self.assertEqual(batch.snapshot()["calls"], 0)

    def test_comments_carry_parent_id_and_paging(self):
        url = "https://m.weibo.cn/detail/4900000000000001"
        payload = self.rc(
            url, batch=self.budget(),
            transport=FakeTransport({"status": 200, "text": json.dumps(COMMENTS_JSON),
                                     "json": COMMENTS_JSON,
                                     "diagnostics": {"state": "ready"}}),
            collected_at=COLLECTED)
        self.assertEqual(payload["exit"], codes.EXIT_OK)
        self.assertEqual(payload["count"], 2)
        first = payload["records"][0]
        self.assertEqual(first["type"], "comment")
        self.assertEqual(first["parent_id"], "4900000000000001")
        self.assertEqual(first["native_id"], "c1")
        self.assertEqual(first["likes"], 4)
        self.assertEqual(first["field_evidence"]["parent_id"], "input:url")
        self.assertEqual(payload["next_offset"], 123456789)

    def test_comments_on_profile_url_are_input_errors(self):
        payload = self.rc("https://m.weibo.cn/u/1234567", batch=self.budget(),
                                     transport=FakeTransport({"status": 200, "text": "",
                                                              "json": None}),
                                     collected_at=COLLECTED)
        self.assertEqual(payload["exit"], codes.EXIT_INPUT)
        self.assertEqual(payload["stop"], "unsupported_content_url")

    def test_comments_json_without_data_is_unsupported(self):
        payload = self.rc(
            "https://m.weibo.cn/detail/4900000000000001", batch=self.budget(),
            transport=FakeTransport({"status": 200, "text": "{}", "json": {},
                                     "diagnostics": {"state": "ready"}}),
            collected_at=COLLECTED)
        self.assertEqual(payload["exit"], codes.EXIT_UNSUPPORTED)
        self.assertEqual(payload["stop"], "unsupported")


# --------------------------------------------------------------------------
# export: same whitelist as the other adapter
# --------------------------------------------------------------------------
class ExportTests(WeiboTestBase):
    def test_export_is_a_whitelist_and_keeps_weibo_source(self):
        source = self.dir / "records.jsonl"
        source.write_text(json.dumps({
            "native_id": "4900000000000001", "type": "status", "parent_id": None,
            "url": "https://m.weibo.cn/detail/4900000000000001?token=SECRET",
            "title": "标题", "text": "正文", "published_at": None,
            "collected_at": COLLECTED, "voteup": None, "comments": None, "likes": 12,
            "source": "weibo:detail:status",
            "field_evidence": {"native_id": "url:/detail|status/<id>", "text": "html:body:text"},
            "cookies": "SECRET_COOKIE", "nickname": "someone",
        }, ensure_ascii=False) + "\n", encoding="utf-8")
        out = source.with_name("export.jsonl")
        payload = weibo.export(source, out)
        self.assertEqual(payload["exit"], codes.EXIT_OK)
        rows = rec.read_records(out)
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["source"], "weibo:detail:status")
        self.assertEqual(row["url"], "https://m.weibo.cn/detail/4900000000000001")
        self.assertTrue(row["supported"])
        dumped = json.dumps(row)
        self.assertNotIn("SECRET", dumped)
        self.assertNotIn("cookies", dumped)
        self.assertNotIn("nickname", dumped)

    def test_wall_markers_exclude_signin_copy(self):
        """The sign-in page's own "获取验证码 / 短信验证码" is never a wall.

        A bare 验证码 in the risk/site marker lists locked a whole state-dir on
        normal sign-in copy; only real wall wording may stay.
        """
        self.assertNotIn("验证码", weibo.RISK_MARKERS)
        self.assertNotIn("验证码", weibo.SITE.wall_markers)
        for marker in ("安全验证", "访问异常", "操作频繁"):
            self.assertIn(marker, weibo.RISK_MARKERS)
            self.assertIn(marker, weibo.SITE.wall_markers)
        signin_copy = "扫码登录 获取验证码 短信验证码 密码登录"
        for marker in tuple(weibo.RISK_MARKERS) + tuple(weibo.SITE.wall_markers):
            self.assertNotIn(marker, signin_copy)
        self.assertIsNone(weibo.detect_risk(signin_copy))
        # a real wall still trips
        self.assertEqual(weibo.detect_risk("请完成安全验证"), "text:安全验证")

    def test_probe_reads_document_ready_state(self):
        """The Weibo probe must read document.readyState, not documentElement's."""
        script = transport_mod._light_js(weibo.SITE)
        self.assertIn("document.readyState", script)
        self.assertNotIn("documentElement.readyState", script)
        transport = transport_mod.AuthenticatedBrowserTransport(
            self.dir / "profile", site=weibo.SITE, timeout=5.0)
        try:
            self.assertEqual(transport.site.name, "weibo")
            self.assertIn("detail", transport.site.recognized_keys)
        finally:
            transport.close()

    def test_export_report_shape_matches_zhihu(self):
        """One exporter: the Weibo report must have the accepted Zhihu shape."""
        from tools.selection.access import zhihu as zhihu_mod

        source = self.dir / "records2.jsonl"
        source.write_text(json.dumps({
            "native_id": "1", "type": "status", "url": "https://m.weibo.cn/detail/1?token=S",
            "title": "t", "text": "x", "source": "weibo:detail:status",
            "field_evidence": {"native_id": "url:/detail|status/<id>"},
            "cookies": "SECRET_COOKIE", "nickname": "someone"}, ensure_ascii=False) + "\n",
            encoding="utf-8")
        ours = weibo.export(source, self.dir / "wb.jsonl")
        theirs = zhihu_mod.export(source, self.dir / "zh.jsonl")
        self.assertEqual(ours["dropped_keys"], theirs["dropped_keys"])
        self.assertIsInstance(ours["dropped_keys"], dict)          # counts, not a list
        self.assertIn("cookies", ours["dropped_keys"])
        self.assertEqual(ours["unsupported"], theirs["unsupported"])
        self.assertIsInstance(ours["unsupported"], list)           # ids, not an int
        self.assertNotIn("SECRET", json.dumps(ours, ensure_ascii=False))

    def test_export_of_missing_file_is_a_nonzero_exit(self):
        payload = weibo.export(self.dir / "nope.jsonl")
        self.assertEqual(payload["exit"], codes.EXIT_EXPORT)
        self.assertFalse(payload["ok"])


class _StubNodriver:
    """A `nodriver` module stand-in so launch paths can be tested offline."""

    def __init__(self, *, raises=None) -> None:
        self.calls: list[dict] = []
        self._raises = raises

    async def start(self, **kwargs):
        self.calls.append(kwargs)
        if self._raises is not None:
            raise self._raises
        return _StubLoginBrowser()


class _StubLoginBrowser:
    """Just enough browser for `browser.wait_for_login` to reach 'signed in'."""

    def __init__(self) -> None:
        self.stopped = False

    async def evaluate(self, script: str):
        if "location.href" in script:
            return "https://weibo.com/"
        if "hasLogout" in script:      # weibo signal collector: real JSON payload
            return json.dumps({"host": "weibo.com", "path": "/", "hasLogout": True,
                               "hasSettings": True, "hasCompose": True,
                               "avatarCount": 1, "userLinkCount": 1, "text": "首页"})
        return True

    async def get(self, url: str):
        return self

    def stop(self) -> None:
        self.stopped = True


@contextlib.contextmanager
def _stub_nodriver(stub):
    with mock.patch.dict(sys.modules, {"nodriver": stub}):
        yield stub


class StartFailureTests(WeiboTestBase):
    """A failed launch is structured data + a ledger row, never a bare stack."""

    def test_relative_profile_becomes_absolute(self):
        transport = transport_mod.AuthenticatedBrowserTransport(
            "docs/validation/v10/weibo-startfix/relative-profile", timeout=5.0)
        try:
            self.assertTrue(transport.profile.is_absolute())
            self.assertEqual(transport.profile,
                             pathlib.Path("docs/validation/v10/weibo-startfix/relative-profile").resolve())
        finally:
            transport.close()

    def test_absolute_profile_is_unchanged(self):
        absolute = self.dir / "abs-profile"
        transport = transport_mod.AuthenticatedBrowserTransport(str(absolute), timeout=5.0)
        try:
            self.assertEqual(transport.profile, absolute.resolve())
            self.assertTrue(transport.profile.is_absolute())
        finally:
            transport.close()

    def test_failed_launch_is_structured_and_not_a_risk(self):
        stub = _StubNodriver(raises=Exception("Failed to connect to browser"))
        with _stub_nodriver(stub), mock.patch.object(
                browser_mod, "available", lambda: {"usable": True, "chrome": "chrome.exe"}):
            transport = transport_mod.AuthenticatedBrowserTransport(
                "docs/validation/v10/weibo-startfix/rel", timeout=5.0)
            result = transport.fetch("https://m.weibo.cn/search?containerid=x")
            transport.close()
        self.assertIsNone(result["status"])
        self.assertTrue(result["error"].startswith("browser_start_failed:"))
        self.assertIn("Failed to connect", result["error"])
        self.assertEqual(result["diagnostics"]["state"], "start_failed")
        self.assertEqual(result["diagnostics"]["phase"], "start")
        self.assertEqual(len(stub.calls), 1)
        # the launch got an absolute user_data_dir even though we passed a relative one
        self.assertTrue(pathlib.Path(stub.calls[0]["user_data_dir"]).is_absolute())

    def test_failed_launch_exits_nonzero_without_locking_and_is_in_the_ledger(self):
        stub = _StubNodriver(raises=RuntimeError("Failed to connect to browser"))
        state = self.dir / "state"
        budget = budget_mod.open_budget(state, clock=self.clock)
        with _stub_nodriver(stub), mock.patch.object(
                browser_mod, "available", lambda: {"usable": True, "chrome": "chrome.exe"}):
            transport = transport_mod.AuthenticatedBrowserTransport(
                str(self.dir / "profile"), timeout=5.0)
            payload = self.rs("x", batch=budget, transport=transport,
                                       collected_at=COLLECTED)
            transport.close()
        snapshot = budget.snapshot()
        ledger = budget_mod.read_ledger(state, 20)
        budget.close()
        self.assertEqual(payload["exit"], weibo.EXIT_TRANSPORT)
        self.assertNotEqual(payload["exit"], 0)
        self.assertFalse(snapshot["locked"])              # a launch failure is not a wall
        self.assertIn("browser_start_failed", payload["stop"])
        kinds = [row.get("kind") for row in ledger]
        details = " ".join(str(row.get("detail") or "") for row in ledger)
        self.assertIn("transport_error", kinds)           # distinguishable in the ledger
        self.assertIn("browser_start_failed", details)

    def test_login_path_passes_an_absolute_user_data_dir(self):
        for module in (weibo, zhihu_mod):
            stub = _StubNodriver()
            relative = f"docs/validation/v10/weibo-startfix/login-{module.__name__}"
            budget = budget_mod.open_budget(self.dir / f"login-{module.__name__}",
                                            clock=self.clock)
            try:
                with _stub_nodriver(stub):
                    result = module._login_with_real_browser(
                        relative, budget=budget, clock=self.clock, timeout=2,
                        headless=True, info={"chrome": "chrome.exe"})
            finally:
                budget.close()
            self.assertEqual(result["status"], "ok", module.__name__)
            self.assertTrue(pathlib.Path(stub.calls[0]["user_data_dir"]).is_absolute(),
                            module.__name__)


class _ProbeTab:
    """Scripted tab for the three observation gaps (one state per level-1 cycle)."""

    def __init__(self, states, *, final_url="https://m.weibo.cn/search?containerid=x",
                 html="<html><body><a href='/detail/1'>x</a></body></html>") -> None:
        self.states = list(states)
        self.index = 0
        self.current = self.states[0]
        self.final_url = final_url
        self.html = html
        self.levels: list[int] = []

    def _advance(self):
        self.current = self.states[min(self.index, len(self.states) - 1)]
        if self.index < len(self.states) - 1:
            self.index += 1
        return self.current

    async def evaluate(self, script: str):
        if "location.href" in script:
            return self.final_url
        level = 1 if "level:1" in script else 2 if "level:2" in script else 3
        self.levels.append(level)
        state = self._advance() if level == 1 else self.current
        return json.dumps(state.get(f"level{level}", {}), ensure_ascii=False)

    async def get_content(self):
        return self.html


class _ProbeBrowser:
    def __init__(self, tab) -> None:
        self._tab = tab

    async def get(self, url: str):
        return self._tab


def _probe_page(*, ready="complete", shapes=None, contentish=0, wall=None,
                empty=False, html=""):
    hist = {"detail": 0, "status": 0, "post": 0, "profile": 0, "other": 0,
            "other_same_origin": 0, "other_cross_origin": 0, "relative_other": 0,
            "non_http": 0}
    hist.update(shapes or {})
    total = sum(int(v) for v in hist.values())
    return {"level1": {"level": 1, "readyState": ready, "anchorCount": total,
                       "sampled": total, "shapes": hist},
            "level2": {"level": 2, "counts": {"result": contentish, "list": 0}},
            "level3": {"level": 3, "wall": wall, "emptyish": empty, "textLen": 0},
            "html": html}


class ObservationGapTests(WeiboTestBase):
    """The three gaps from probe run #2: final_url, href_shapes, bounded render."""

    def _transport(self, browser, **kwargs):
        kwargs.setdefault("timeout", 5.0)
        return transport_mod.AuthenticatedBrowserTransport(
            self.dir / "profile", browser=browser, allowed_host_suffix="weibo.cn",
            site=weibo.SITE, **kwargs)

    def test_normal_path_reports_final_url_and_known(self):
        tab = _ProbeTab([_probe_page(shapes={"detail": 1}, contentish=2)])
        result = self._transport(_ProbeBrowser(tab)).fetch(
            "https://m.weibo.cn/search?containerid=x")
        self.assertEqual(result["status"], 200)
        self.assertTrue(result["final_url"])
        self.assertTrue(result["final_url_known"])
        self.assertTrue(result["diagnostics"]["final_url"])
        self.assertIs(result["diagnostics"]["final_url_known"], True)

    def test_rejected_anchor_shapes_are_a_filled_histogram(self):
        shapes = {"profile": 1, "other_same_origin": 3, "other_cross_origin": 2,
                  "relative_other": 6, "non_http": 1}          # 13 anchors, 0 content
        tab = _ProbeTab([_probe_page(shapes=shapes)])
        result = self._transport(_ProbeBrowser(tab)).fetch(
            "https://m.weibo.cn/search?containerid=x")
        diag = result["diagnostics"]
        nonzero = {k: v for k, v in diag["href_shapes"].items() if v}
        self.assertEqual(nonzero, shapes)
        self.assertEqual(diag["anchors_total"], 13)
        self.assertEqual(diag["anchors_recognized"], 0)
        self.assertEqual(diag["anchors_rejected"], 13)
        self.assertEqual(sum(diag["href_shapes"].values()), diag["anchors_total"])
        # the script really classifies into those fallback buckets
        script = transport_mod._light_js(weibo.SITE)
        for bucket in ("other_same_origin", "other_cross_origin", "relative_other",
                       "non_http"):
            self.assertIn(bucket, script)

    def test_shell_then_anchors_is_read(self):
        tab = _ProbeTab([_probe_page(), _probe_page(shapes={"detail": 2}, contentish=4)])
        result = self._transport(_ProbeBrowser(tab)).fetch(
            "https://m.weibo.cn/search?containerid=x")
        self.assertEqual(result["status"], 200)
        self.assertEqual(result["probe"]["state"], "result")
        self.assertEqual(result["diagnostics"]["anchors_recognized"], 2)
        # level 1 was re-read (cheap) instead of trusting the first empty shell
        self.assertGreaterEqual(tab.levels.count(1), 2)

    def test_shell_that_never_renders_is_unknown_not_empty(self):
        import time

        tab = _ProbeTab([_probe_page()])
        started = time.monotonic()
        with mock.patch.object(transport_mod, "RENDER_WAIT_MAX", 0.3):
            result = self._transport(_ProbeBrowser(tab)).fetch(
                "https://m.weibo.cn/search?containerid=x")
        elapsed = time.monotonic() - started
        self.assertLess(elapsed, 3.0, "render wait must stay bounded")
        self.assertEqual(result["probe"]["state"], "unknown")
        self.assertTrue(result["probe"].get("render_wait_exhausted"))
        self.assertEqual(result["diagnostics"]["state"], "unknown")
        self.assertEqual(result["diagnostics"]["anchors_total"], 0)

    def test_render_wait_keeps_the_one_deadline(self):
        """A shell page cannot extend the budget: it ends unknown, not 'empty'."""
        import time

        tab = _ProbeTab([_probe_page()])
        started = time.monotonic()
        with mock.patch.object(transport_mod, "RENDER_WAIT_MAX", 10.0):
            transport = self._transport(_ProbeBrowser(tab), timeout=0.8)
            result = transport.fetch("https://m.weibo.cn/search?containerid=x")
            elapsed = time.monotonic() - started
            self.assertLess(elapsed, 2.0, "the render wait never resets the budget")
            self.assertEqual(result["diagnostics"]["state"], "unknown")
            probe_state = (result.get("probe") or {}).get("state")
            self.assertNotEqual(probe_state, "result")
            self.assertNotEqual(probe_state, "empty")
            # and the caller must not read that as a finished, empty search.
            # A fresh shell tab with NO content links keeps this deterministic:
            # the previous tab could be read before its deadline and yield a
            # record, which is a different (timing) path than the one under test.
            shell = _ProbeTab([_probe_page()], html="")
            shell_transport = self._transport(_ProbeBrowser(shell), timeout=0.8)
            budget = budget_mod.open_budget(self.dir / "state-shell", clock=self.clock)
            payload = self.rs("x", batch=budget, transport=shell_transport,
                                       collected_at=COLLECTED)
            budget.close()
        self.assertNotEqual(payload["exit"], 0)
        self.assertNotEqual(payload["exit"], weibo.EXIT_EMPTY)
        # "unknown" either way: the render wait ran out, or the budget did
        self.assertIn(payload["stop"], ("readiness_timeout", "browser:TimeoutError"))


class UaTests(unittest.TestCase):
    """Phase one: the mobile UA must exist for weibo, be applied at launch, and
    leave Zhihu exactly as it was. No browser is started for any of these."""

    def test_only_weibo_carries_a_mobile_user_agent(self):
        self.assertTrue(weibo.SITE.user_agent)
        self.assertIn("Mobile", weibo.SITE.user_agent)
        self.assertEqual(weibo.SITE.user_agent, weibo.MOBILE_UA)
        self.assertIsNone(transport_mod.ZHIHU_SITE.user_agent)

    def test_launch_kwargs_turn_the_ua_into_a_browser_switch(self):
        weib = transport_mod.AuthenticatedBrowserTransport("/tmp/x", site=weibo.SITE)
        kwargs = weib._launch_kwargs({"chrome": "chrome.exe"})
        self.assertEqual(kwargs["browser_args"],
                         [f"--user-agent={weibo.SITE.user_agent}"])
        self.assertEqual(kwargs["headless"], True)
        zhihu = transport_mod.AuthenticatedBrowserTransport("/tmp/x")
        self.assertNotIn("browser_args", zhihu._launch_kwargs({"chrome": "chrome.exe"}))

    def test_uc_start_actually_receives_the_mobile_ua(self):
        captured: dict = {}

        class FakeBrowser:
            def stop(self):
                captured["stopped"] = True

        async def fake_start(**kwargs):
            captured.update(kwargs)
            return FakeBrowser()

        fake_nodriver = types.ModuleType("nodriver")
        fake_nodriver.start = fake_start
        with mock.patch.dict(sys.modules, {"nodriver": fake_nodriver}):
            with mock.patch.object(browser_mod, "available",
                                   return_value={"usable": True, "chrome": "chrome.exe"}):
                transport = transport_mod.AuthenticatedBrowserTransport(
                    "/tmp/profile", headless=False, site=weibo.SITE)
                # real callers always pass the shared deadline; a None deadline
                # means "no time left" by design
                import time as _time
                transport._ensure_browser(deadline=_time.monotonic() + 5)
                transport.close()
        self.assertEqual(captured["browser_args"],
                         [f"--user-agent={weibo.SITE.user_agent}"])
        self.assertTrue(captured["user_data_dir"].endswith("profile"))
        self.assertFalse(captured["headless"])
        self.assertTrue(captured.get("stopped"))
        self.assertEqual(captured["browser_executable_path"], "chrome.exe")

    def test_cli_override_copies_the_profile_instead_of_mutating_it(self):
        args = types.SimpleNamespace(mode="authenticated-browser", profile="p",
                                     visible=False, timeout=5, user_agent="UA-X")
        built = weibo._make_transport(args)
        self.assertEqual(built.site.user_agent, "UA-X")
        self.assertEqual(weibo.SITE.user_agent, weibo.MOBILE_UA)  # module default intact

    def test_no_override_keeps_the_site_default(self):
        args = types.SimpleNamespace(mode="authenticated-browser", profile="p",
                                     visible=False, timeout=5, user_agent=None)
        built = weibo._make_transport(args)
        self.assertIs(built.site, weibo.SITE)


# --------------------------------------------------------------------------
# login detector: the REAL SIGNED_IN_JS is executed (Node + minimal DOM stub)
# --------------------------------------------------------------------------
NODE = shutil.which("node")

_DOM_HARNESS = r"""
const fs = require('fs');
const sig = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
const counts = sig.counts || {};
const match = (sel) => {
  for (const key of Object.keys(counts)) { if (sel.includes(key)) return counts[key]; }
  return 0;
};
global.location = { hostname: sig.host || '', pathname: sig.path || '' };
global.document = {
  body: { innerText: sig.text || '' },
  querySelector: (sel) => (match(sel) > 0 ? {} : null),
  querySelectorAll: (sel) => new Array(match(sel)).fill({}),
};
const script = fs.readFileSync(process.argv[3], 'utf8');
process.stdout.write(String(eval(script)));
"""


def run_signed_in_js(host="weibo.com", path="/", text="", counts=None):
    """Execute the shipped SIGNED_IN_JS against a DOM stub, return its JSON."""
    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = pathlib.Path(tmp)
        (tmpdir / "harness.js").write_text(_DOM_HARNESS, encoding="utf-8")
        (tmpdir / "signals.json").write_text(
            json.dumps({"host": host, "path": path, "text": text,
                        "counts": counts or {}}), encoding="utf-8")
        (tmpdir / "script.js").write_text(weibo.SIGNED_IN_JS, encoding="utf-8")
        proc = subprocess.run([NODE, str(tmpdir / "harness.js"),
                               str(tmpdir / "signals.json"), str(tmpdir / "script.js")],
                              capture_output=True, text=True, encoding="utf-8", timeout=60)
        if proc.returncode != 0:
            raise AssertionError(f"node failed: {proc.stderr[:400]}")
        return proc.stdout


@unittest.skipUnless(NODE, "node is not installed")
class SignedInJsTests(unittest.TestCase):
    """The JS predicate itself, executed for real against a DOM stub."""

    def verdict(self, **kwargs):
        return weibo.classify_signed_in(run_signed_in_js(**kwargs))

    def test_public_feed_with_avatars_userlinks_and_message_is_unknown(self):
        raw = run_signed_in_js(host="weibo.com", path="/",
                               text="首页 消息 关注 粉丝 热门",
                               counts={"avatar": 6, "/u/": 12})
        signals = json.loads(raw)
        self.assertGreaterEqual(signals["avatarCount"], 6)     # the stub really fed it
        self.assertGreaterEqual(signals["userLinkCount"], 12)
        self.assertEqual(weibo.classify_signed_in(signals), "unknown")
        self.assertFalse(weibo.signed_in_verdict(signals))

    def test_login_form_with_weak_signals_is_unknown(self):
        raw = run_signed_in_js(host="passport.weibo.com", path="/sso/signin",
                               text="登录 注册 消息 发微博",
                               counts={"avatar": 3, "/u/": 5, "/logout": 1})
        self.assertEqual(weibo.classify_signed_in(raw), "unknown")

    def test_non_weibo_tab_with_account_controls_is_unknown(self):
        raw = run_signed_in_js(host="example.com", path="/",
                               counts={"/logout": 1, "/setting": 1})
        self.assertEqual(weibo.classify_signed_in(raw), "unknown")

    def test_explicit_account_controls_are_ok(self):
        raw = run_signed_in_js(host="weibo.com", path="/",
                               text="首页 消息", counts={"/logout": 1})
        self.assertEqual(weibo.classify_signed_in(raw), "ok")
        self.assertTrue(weibo.signed_in_verdict(raw))

    def test_settings_link_alone_is_unknown(self):
        # a generic /setting entry also appears on logged-out pages
        raw = run_signed_in_js(host="weibo.com", path="/home", counts={"/setting": 1})
        self.assertEqual(weibo.classify_signed_in(raw), "unknown")

    def test_account_link_alone_is_unknown(self):
        raw = run_signed_in_js(host="weibo.com", path="/", counts={"/account/": 1})
        self.assertEqual(weibo.classify_signed_in(raw), "unknown")

    def test_settings_plus_account_still_unknown(self):
        raw = run_signed_in_js(host="weibo.com", path="/",
                               counts={"/setting": 1, "/account/": 1})
        self.assertEqual(weibo.classify_signed_in(raw), "unknown")

    def test_node_is_available_so_js_tests_never_skip_silently(self):
        self.assertTrue(NODE, "node is required: the JS predicate must really run")

    def test_passport_negation_beats_any_control(self):
        raw = run_signed_in_js(host="passport.weibo.com", path="/sso/signin",
                               counts={"/logout": 1, "/setting": 1})
        self.assertEqual(weibo.classify_signed_in(raw), "unknown")

    def test_signin_path_on_the_business_host_is_unknown(self):
        raw = run_signed_in_js(host="weibo.com", path="/signin",
                               counts={"/logout": 1})
        self.assertEqual(weibo.classify_signed_in(raw), "unknown")

    def test_empty_text_with_only_public_user_links_is_unknown(self):
        raw = run_signed_in_js(host="weibo.com", path="/", text="",
                               counts={"/u/": 20, "avatar": 4})
        signals = json.loads(raw)
        self.assertEqual(signals["text"], "")
        self.assertEqual(weibo.classify_signed_in(signals), "unknown")

    def test_lone_message_word_is_unknown(self):
        raw = run_signed_in_js(host="weibo.com", path="/", text="消息")
        self.assertEqual(weibo.classify_signed_in(raw), "unknown")

    def test_js_emits_only_whitelisted_signal_keys(self):
        signals = json.loads(run_signed_in_js(host="weibo.com", path="/"))
        self.assertEqual(set(signals), {"host", "path", "text", "hasLogout",
                                        "hasSettings", "hasCompose",
                                        "avatarCount", "userLinkCount"})


# --------------------------------------------------------------------------
# polling control flow (NOT a DOM test: the tab is scripted)
# --------------------------------------------------------------------------
class ScriptedTab:
    """A tab that answers the three snippets the login loop reads.

    This is a *control-flow* stand-in, not a DOM: the signed-in probe returns a
    canned signal payload, so these tests say nothing about the real predicate.
    """

    def __init__(self, *, url="", signals=None, text=""):
        self.url = url
        self.signals = signals
        self.text = text
        self.calls = 0

    async def evaluate(self, script):
        self.calls += 1
        if "location.href" in script:
            return self.url
        if "hasLogout" in script:            # the weibo signal collector
            return json.dumps(self.signals or {})
        return self.text


class TabbedBrowser:
    """Main tab plus extra tabs, so the poll can fall back to a newer one."""

    def __init__(self, main, others=()):
        self.main_tab = main
        self.tabs = [main, *others]

    async def evaluate(self, script):     # behaves like the main tab
        return await self.main_tab.evaluate(script)


SIGNED = {"host": "weibo.com", "path": "/", "hasLogout": True, "hasSettings": False,
          "hasCompose": False, "avatarCount": 1, "userLinkCount": 1, "text": "首页"}


class LoginPollingTests(WeiboTestBase):
    """Control flow only: ok / not ok / tab fallback / dead tab / same-tab evidence."""

    def poll(self, browser, timeout=10, max_polls=None):
        return asyncio.run(browser_mod.wait_for_login(
            browser, profile=self.dir, budget=self.budget(), clock=self.clock,
            timeout=timeout, max_polls=max_polls,
            signed_in_js=weibo.SIGNED_IN_JS, wall_markers=weibo.LOGIN_WALL_MARKERS,
            signed_in_verdict=weibo.signed_in_verdict, risk_wins=True))

    def test_account_control_tab_is_ok(self):
        tab = ScriptedTab(url="https://weibo.com/", signals=SIGNED, text="首页 消息")
        result = self.poll(tab)
        self.assertEqual(result["status"], "ok")
        self.assertTrue(result["signed_in"])

    def test_weak_signal_tab_is_not_ok(self):
        weak = {"host": "weibo.com", "path": "/", "avatarCount": 9,
                "userLinkCount": 9, "text": "消息"}
        tab = ScriptedTab(url="https://weibo.com/", signals=weak, text="消息")
        result = self.poll(tab, timeout=3)
        self.assertNotEqual(result["status"], "ok")
        self.assertFalse(result["signed_in"])

    def test_login_landing_in_a_later_tab_is_detected(self):
        blank = ScriptedTab(url="about:blank", signals={}, text="")
        landed = ScriptedTab(url="https://weibo.com/", signals=SIGNED, text="首页")
        result = self.poll(TabbedBrowser(blank, [landed]))
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["final_url"], "https://weibo.com/")
        self.assertGreaterEqual(landed.calls, 1)

    def test_evidence_url_and_text_come_from_the_same_tab(self):
        # main tab has text but no controls; later tab has the controls AND its url
        main = ScriptedTab(url="https://weibo.com/feed", signals={}, text="公开信息流")
        landed = ScriptedTab(url="https://weibo.com/home", signals=SIGNED, text="首页")
        result = self.poll(TabbedBrowser(main, [landed]))
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["final_url"], "https://weibo.com/home")

    def test_later_tab_wall_beats_the_first_normal_tab(self):
        normal = ScriptedTab(url="https://weibo.com/feed", signals={},
                             text="公开信息流 首页")
        wall = ScriptedTab(url="https://weibo.com/verify", signals=SIGNED,
                           text="请完成安全验证")
        result = self.poll(TabbedBrowser(normal, [wall]))
        self.assertEqual(result["status"], "risk")
        self.assertIn("安全验证", result["risk_reason"])
        self.assertEqual(result["risk_url"], "https://weibo.com/verify")
        self.assertFalse(result["signed_in"])

    def test_wall_on_the_first_tab_also_wins(self):
        wall = ScriptedTab(url="https://weibo.com/wall", signals={}, text="访问过于频繁")
        other = ScriptedTab(url="https://weibo.com/home", signals=SIGNED, text="首页")
        result = self.poll(TabbedBrowser(wall, [other]))
        self.assertEqual(result["status"], "risk")
        self.assertEqual(result["risk_url"], "https://weibo.com/wall")

    def test_risk_and_signed_together_are_risk(self):
        signed_and_wall = ScriptedTab(url="https://weibo.com/home", signals=SIGNED,
                                      text="首页 请完成安全验证")
        result = self.poll(signed_and_wall)
        self.assertEqual(result["status"], "risk")
        self.assertFalse(result["signed_in"])

    def test_dead_tab_is_unknown_not_timeout(self):
        class Broken:
            async def evaluate(self, script):
                raise RuntimeError("tab_died")

        result = self.poll(Broken(), timeout=10)
        self.assertEqual(result["status"], "unknown")
        self.assertEqual(result["stop_reason"], "browser_error:RuntimeError")


class SessionCheckEntryTests(unittest.TestCase):
    """`login --check-session` must navigate weibo.com and nothing else."""

    def _run(self, check_session):
        visited = []

        class FakeBrowser:
            async def get(self, url):
                visited.append(url)
                return None

            def stop(self):
                visited.append("stopped")

        async def fake_start(**kwargs):
            return FakeBrowser()

        async def fake_wait(*args, **kwargs):
            return {"status": "unknown", "exit": 13, "polls": 0,
                    "stop_reason": "unknown", "signed_in": False}

        fake_nodriver = types.ModuleType("nodriver")
        fake_nodriver.start = fake_start
        with mock.patch.dict(sys.modules, {"nodriver": fake_nodriver}):
            with mock.patch.object(browser_mod, "wait_for_login", fake_wait):
                payload = weibo._login_with_real_browser(
                    self.profile, budget=_NullBudget(), clock=lambda: 0.0,
                    timeout=5, headless=False, info={"chrome": "chrome.exe"},
                    check_session=check_session)
        return visited, payload

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.profile = self._tmp.name

    def tearDown(self):
        self._tmp.cleanup()

    def test_check_session_navigates_the_business_home_only(self):
        visited, payload = self._run(True)
        self.assertEqual(visited[0], weibo.SESSION_CHECK_URL)
        self.assertEqual(visited[0], "https://weibo.com/")
        self.assertIn("stopped", visited)          # browser always closed

    def test_default_login_still_navigates_the_signin_page(self):
        visited, _payload = self._run(False)
        self.assertEqual(visited[0], weibo.LOGIN_URL)
        self.assertNotEqual(visited[0], weibo.SESSION_CHECK_URL)


class _NullBudget:
    """Just enough budget surface for the login helper (no I/O)."""

    max_polls = 120

    def charge_poll(self, detail=""):
        return {}

    def lock(self, reason, source="unknown"):
        return None


if __name__ == "__main__":
    unittest.main()


def import_isolated_snapshot(ledger, base_dir, clock):
    """Give a temp ledger a snapshot built from an independent test manifest.

    Every key gets its own temp source file: a snapshot that points two keys at
    one path is refused by the gate, so the fixture must be honest about it.
    """
    base = pathlib.Path(base_dir) / "history"
    sources, manifest = [], []
    for spec in platform_mod.HISTORY_SOURCES:
        folder = base / spec["source_key"]
        seed = budget_mod.open_budget(folder, clock=clock)
        seed.close()
        manifest.append({"source_key": spec["source_key"], "path": str(folder),
                         "classification": spec["classification"],
                         "may_be_absent": False, "reason": ""})
        sources.append({"source_key": spec["source_key"],
                        "path": str(folder / "budget.sqlite3"),
                        "classification": spec["classification"],
                        "note": "test fixture"})
    return ledger.import_snapshot(sources, note="isolated test snapshot",
                                  manifest=manifest)


class PlatformGuardTests(WeiboTestBase):
    """Every real navigation is charged before it happens, and a spent batch or a
    platform lock refuses *before* anything touches the network."""

    def setUp(self):
        super().setUp()
        self.platform_path = self.dir / "platform.sqlite3"
        self.pclock = FakeClock()
        self.ledger = platform_mod.PlatformLedger(self.platform_path,
                                                  clock=self.pclock,
                                                  allow_test_manifest=True)
        import_isolated_snapshot(self.ledger, self.dir, self.pclock)

    def tearDown(self):
        self.ledger.close()
        super().tearDown()

    def authorize(self, batch="b1", calls=2):
        self.ledger.authorize_batch(batch, authorized_calls=calls, window_seconds=300,
                                    source="test:user-decision")

    def test_login_charges_before_the_browser_navigates(self):
        self.authorize(calls=2)
        seen = {}

        def fake_real(profile, *, budget, clock, timeout, headless, info,
                      check_session=False):
            seen["used_at_navigation"] = self.ledger.summary("b1")["used"]
            return {"status": "ok", "exit": 0, "polls": 1, "signed_in": True}

        with mock.patch.object(weibo, "_login_with_real_browser", fake_real), \
                mock.patch.object(browser_mod, "available",
                                  return_value={"usable": True, "chrome": "chrome.exe"}):
            payload = weibo.login(self.dir / "p", budget=self.budget(), clock=self.clock,
                                  timeout=5, platform=self.ledger, batch_id="b1")
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(seen["used_at_navigation"], 1)      # charged first, then get()
        self.assertEqual(self.ledger.summary("b1")["used"], 1)

    def test_login_refuses_when_the_batch_is_spent_and_never_navigates(self):
        self.authorize(calls=1)
        self.ledger.charge("b1", "active_nav")
        self.pclock.advance(20)                      # past the platform interval
        called = mock.Mock()
        with mock.patch.object(weibo, "_login_with_real_browser", called), \
                mock.patch.object(browser_mod, "available",
                                  return_value={"usable": True, "chrome": "chrome.exe"}):
            payload = weibo.login(self.dir / "p", budget=self.budget(), clock=self.clock,
                                  timeout=5, platform=self.ledger, batch_id="b1")
        self.assertEqual(payload["exit"], codes.EXIT_BUDGET)
        self.assertEqual(payload["stop"], "platform:calls_exhausted")
        self.assertFalse(called.called)                      # no browser.get at all

    def test_platform_lock_blocks_login(self):
        self.authorize(calls=2)
        self.ledger.lock("text:安全验证", source="weibo.search")
        called = mock.Mock()
        with mock.patch.object(weibo, "_login_with_real_browser", called), \
                mock.patch.object(browser_mod, "available",
                                  return_value={"usable": True, "chrome": "chrome.exe"}):
            payload = weibo.login(self.dir / "p", budget=self.budget(), clock=self.clock,
                                  timeout=5, platform=self.ledger, batch_id="b1")
        self.assertEqual(payload["exit"], codes.EXIT_BUDGET)
        self.assertTrue(payload["stop"].startswith("platform:platform_locked"))
        self.assertFalse(called.called)

    def test_search_charges_platform_before_fetching(self):
        self.authorize(calls=1)
        transport = FakeTransport({"status": 200, "text": SEARCH_HTML, "json": None})
        first = weibo.run_search("学习计划模板", batch=self.budget(), transport=transport,
                                 collected_at=COLLECTED, platform=self.ledger,
                                 batch_id="b1")
        self.assertEqual(first["exit"], codes.EXIT_OK)
        self.assertEqual(len(transport.urls), 1)
        self.pclock.advance(20)                      # past the platform interval
        self.assertEqual(self.ledger.summary("b1")["used"], 1)
        # a different state dir must NOT help: the platform ledger is the cap
        other_state = budget_mod.open_budget(self.dir / "other-state", clock=self.clock)
        try:
            second = weibo.run_search("学习计划模板", batch=other_state,
                                      transport=transport, collected_at=COLLECTED,
                                      platform=self.ledger, batch_id="b1")
        finally:
            other_state.close()
        self.assertEqual(second["exit"], codes.EXIT_BUDGET)
        self.assertEqual(second["stop"], "platform:calls_exhausted")
        self.assertEqual(len(transport.urls), 1)             # no second fetch

    def test_cli_denies_an_unauthorized_batch_even_with_a_new_state_dir(self):
        import contextlib
        import io
        import os

        state_dir = self.dir / "brand-new-state-dir"      # never existed before
        argv = ["--state-dir", str(state_dir), "--batch-id", "not-authorized",
                "--mode", "authenticated-browser", "--profile", str(self.dir / "p"),
                "search", "学习计划模板", "--limit", "5"]
        boom = mock.Mock(side_effect=AssertionError("transport must not be built"))
        with mock.patch.object(weibo, "_open_guard", lambda: self.ledger), \
                mock.patch.object(weibo, "_make_transport", boom), \
                contextlib.redirect_stdout(io.StringIO()):
            code = weibo.main(argv)
        self.assertEqual(code, codes.EXIT_BUDGET)
        self.assertFalse(boom.called)


class PlatformGuardStrictTests(WeiboTestBase):
    """Production paths cannot run unmetered; risk locks persist or the run stops."""

    def setUp(self):
        super().setUp()
        self.pclock = FakeClock()
        self.ledger = platform_mod.PlatformLedger(self.dir / "platform.sqlite3",
                                                  clock=self.pclock,
                                                  allow_test_manifest=True)
        import_isolated_snapshot(self.ledger, self.dir, self.pclock)
        self.ledger.authorize_batch("b1", authorized_calls=3, window_seconds=300,
                                    source="test:user-decision")

    def tearDown(self):
        self.ledger.close()
        super().tearDown()

    def real_transport(self):
        tab = _ProbeTab([_probe_page()])
        return transport_mod.AuthenticatedBrowserTransport(
            self.dir / "profile", browser=_ProbeBrowser(tab),
            allowed_host_suffix="weibo.cn", site=weibo.SITE, timeout=1.0)

    def test_direct_search_without_guard_is_refused_before_any_fetch(self):
        transport = self.real_transport()
        fetched = mock.Mock(side_effect=AssertionError("no fetch without a guard"))
        with mock.patch.object(transport, "fetch", fetched):
            payload = weibo.run_search("x", batch=self.budget(), transport=transport,
                                       collected_at=COLLECTED)
        self.assertEqual(payload["exit"], codes.EXIT_BUDGET)
        self.assertEqual(payload["stop"], "platform:guard_required")
        self.assertFalse(fetched.called)

    def test_login_without_guard_is_refused_and_never_launches(self):
        launched = mock.Mock()
        with mock.patch.object(weibo, "_login_with_real_browser", launched), \
                mock.patch.object(browser_mod, "available",
                                  return_value={"usable": True, "chrome": "chrome.exe"}):
            payload = weibo.login(self.dir / "p", budget=self.budget(),
                                  clock=self.clock, timeout=5)
        self.assertEqual(payload["exit"], codes.EXIT_BUDGET)
        self.assertEqual(payload["stop"], "platform:guard_required")
        self.assertFalse(launched.called)

    def test_lock_write_failure_stops_the_run(self):
        transport = FakeTransport({"status": None, "text": "", "json": None,
                                   "error": "browser:risk:text:安全验证",
                                   "diagnostics": {"state": "risk", "risk": "text:安全验证"}})
        with mock.patch.object(self.ledger, "lock", side_effect=RuntimeError("disk full")):
            payload = weibo.run_search("x", batch=self.budget(), transport=transport,
                                       collected_at=COLLECTED, platform=self.ledger,
                                       batch_id="b1")
        self.assertEqual(payload["exit"], codes.EXIT_BUDGET)
        self.assertEqual(payload["stop"], "platform:lock_write_failed")

    def test_lock_survives_a_changed_state_dir_for_login(self):
        self.ledger.lock("text:安全验证", source="weibo.search")
        launched = mock.Mock()
        with mock.patch.object(weibo, "_login_with_real_browser", launched), \
                mock.patch.object(browser_mod, "available",
                                  return_value={"usable": True, "chrome": "chrome.exe"}):
            payload = weibo.login(self.dir / "p", budget=self.budget(),
                                  clock=self.clock, timeout=5,
                                  platform=self.ledger, batch_id="b1")
        self.assertEqual(payload["exit"], codes.EXIT_BUDGET)
        self.assertTrue(payload["stop"].startswith("platform:platform_locked"))
        self.assertFalse(launched.called)

    def test_persistent_events_carry_no_keyword_query_or_token(self):
        transport = FakeTransport({"status": 200, "text": SEARCH_HTML, "json": None})
        weibo.run_search("秘密关键词", batch=self.budget(), transport=transport,
                         collected_at=COLLECTED, platform=self.ledger, batch_id="b1")
        rows = self.ledger.events(10)
        blob = json.dumps(rows, ensure_ascii=False)
        self.assertNotIn("秘密关键词", blob)
        self.assertNotIn("token", blob.lower())
        self.assertNotIn("?", blob)
        for row in rows:
            if row["kind"] == "search":
                self.assertTrue(row["detail"].startswith("https://"))
                self.assertNotIn("?", row["detail"])

    def test_outcome_is_recorded_and_the_call_is_not_refunded(self):
        transport = FakeTransport({"status": None, "text": "", "json": None,
                                   "error": "browser:risk:text:安全验证",
                                   "diagnostics": {"state": "risk", "risk": "text:安全验证"}})
        payload = weibo.run_search("x", batch=self.budget(), transport=transport,
                                   collected_at=COLLECTED, platform=self.ledger,
                                   batch_id="b1")
        self.assertEqual(payload["exit"], codes.EXIT_RISK)
        summary = self.ledger.summary("b1")
        self.assertEqual(summary["used"], 1)                 # no refund
        kinds = [row["kind"] for row in self.ledger.events(10)]
        self.assertIn("search_result", kinds)
        result = next(row for row in self.ledger.events(10)
                      if row["kind"] == "search_result")
        self.assertTrue(result["detail"].startswith("failed"))


    def test_records_cap_is_shared_by_two_state_dirs_and_never_over_emits(self):
        html = ("<html><body>"
                "<a href='/detail/1'>1</a><a href='/detail/2'>2</a>"
                "<a href='/detail/3'>3</a></body></html>")
        first = FakeTransport({"status": 200, "text": html, "json": None})
        one = weibo.run_search("x", batch=self.budget(), transport=first,
                               collected_at=COLLECTED, platform=self.ledger,
                               batch_id="b1")
        self.assertEqual(one["exit"], codes.EXIT_OK)
        self.assertEqual(len(one["records"]), 3)
        self.pclock.advance(20)
        # a different state dir, same platform batch: the cap is shared
        other_state = budget_mod.open_budget(self.dir / "other", clock=self.clock)
        try:
            second = weibo.run_search("x", batch=other_state, transport=first,
                                      collected_at=COLLECTED, platform=self.ledger,
                                      batch_id="b1")
        finally:
            other_state.close()
        # v11：软目标——第二次照常写记录，只是账本回报 over_cap
        self.assertEqual(second["exit"], codes.EXIT_OK)
        self.assertEqual(len(second["records"]), 3)
        self.assertEqual(self.ledger.summary("b1")["records_reserved"], 6)

    def test_result_write_failure_is_not_silent(self):
        transport = FakeTransport({"status": 200, "text": SEARCH_HTML, "json": None})
        with mock.patch.object(self.ledger, "record_result",
                               side_effect=RuntimeError("disk full")):
            payload = weibo.run_search("x", batch=self.budget(), transport=transport,
                                       collected_at=COLLECTED, platform=self.ledger,
                                       batch_id="b1")
        self.assertTrue(str(payload["stop"]).startswith("platform:result_write_failed"))

    def test_public_http_without_a_ledger_is_refused(self):
        fetched = mock.Mock(side_effect=AssertionError("no network without a guard"))
        transport = transport_mod.PublicHttpTransport()
        with mock.patch.object(transport, "fetch", fetched):
            payload = weibo.run_search("x", batch=self.budget(), transport=transport,
                                       collected_at=COLLECTED)
        self.assertEqual(payload["exit"], codes.EXIT_BUDGET)
        self.assertEqual(payload["stop"], "platform:guard_required")
        self.assertFalse(fetched.called)

    def test_login_browser_unavailable_still_records_its_outcome(self):
        with mock.patch.object(browser_mod, "available",
                               return_value={"usable": False, "reason": "no chrome"}):
            payload = weibo.login(self.dir / "p", budget=self.budget(),
                                  clock=self.clock, timeout=5,
                                  platform=self.ledger, batch_id="b1")
        self.assertEqual(payload["status"], "unavailable")
        kinds = [row["kind"] for row in self.ledger.events(10)]
        self.assertIn("active_nav_result", kinds)        # settled, not dropped
        self.assertEqual(self.ledger.summary("b1")["used"], 1)


    def test_settle_failure_clears_records_and_exits_nonzero(self):
        transport = FakeTransport({"status": 200, "text": SEARCH_HTML, "json": None})
        with mock.patch.object(self.ledger, "record_result",
                               side_effect=RuntimeError("disk full")):
            payload = weibo.run_search("x", batch=self.budget(), transport=transport,
                                       collected_at=COLLECTED, platform=self.ledger,
                                       batch_id="b1")
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["exit"], codes.EXIT_BUDGET)
        self.assertEqual(payload["records"], [])
        self.assertFalse(payload["result_persisted"])
        self.assertTrue(str(payload["stop"]).startswith("platform:result_write_failed"))

    def test_fetch_exception_settles_unknown_and_fails_closed(self):
        transport = FakeTransport({"status": 200, "text": SEARCH_HTML, "json": None})
        transport.fetch = mock.Mock(side_effect=RuntimeError("tab died"))
        payload = weibo.run_search("x", batch=self.budget(), transport=transport,
                                   collected_at=COLLECTED, platform=self.ledger,
                                   batch_id="b1")
        self.assertFalse(payload["ok"])
        self.assertNotEqual(payload["exit"], codes.EXIT_OK)
        self.assertEqual(payload["records"], [])
        self.assertTrue(payload["stop"].startswith("adapter_exception:"))
        kinds = [row["kind"] for row in self.ledger.events(10)]
        self.assertIn("search_result", kinds)          # charged call still settled
        self.assertEqual(self.ledger.summary("b1")["used"], 1)

    def test_detail_parse_risk_locks_the_platform_across_state_dirs(self):
        wall_html = "<html><body>安全验证</body></html>"
        transport = FakeTransport({"status": 200, "text": wall_html, "json": None})
        payload = weibo.run_detail("https://m.weibo.cn/detail/1", batch=self.budget(),
                                   transport=transport, collected_at=COLLECTED,
                                   platform=self.ledger, batch_id="b1")
        self.assertEqual(payload["exit"], codes.EXIT_RISK)
        locked, reason = self.ledger.locked()
        self.assertTrue(locked)                        # parse-level risk persisted
        self.assertIn("安全验证", str(reason))
        # another state dir must still be refused
        other = budget_mod.open_budget(self.dir / "other", clock=self.clock)
        try:
            again = weibo.run_search("x", batch=other, transport=transport,
                                     collected_at=COLLECTED, platform=self.ledger,
                                     batch_id="b1")
        finally:
            other.close()
        self.assertEqual(again["exit"], codes.EXIT_BUDGET)
        self.assertTrue(str(again["stop"]).startswith("platform:platform_locked"))

    def test_run_search_carries_soft_target_fields(self):
        """v11：run_search 的返回体也带 records_target/used/over_cap/over_by（与 CLI 同源）。"""
        html = ("<html><body>"
                "<a href='/detail/1'>1</a><a href='/detail/2'>2</a></body></html>")
        out = weibo.run_search("x", batch=self.budget(),
                               transport=FakeTransport({"status": 200, "text": html,
                                                        "json": None}),
                               collected_at=COLLECTED, platform=self.ledger,
                               batch_id="b1")
        for field in ("records_target", "records_used", "over_cap", "over_by"):
            self.assertIn(field, out)
        snap = self.budget().snapshot()
        self.assertEqual(out["records_target"], int(snap["records_max"]))
        self.assertEqual(out["records_used"], int(snap["records"]))
        self.assertFalse(out["over_cap"])
        self.assertEqual(out["over_by"], 0)

    def test_records_cap_above_five_is_accepted_as_soft_target(self):
        """v11：记录数是软目标——大于 5 也照常授权，只是记账时回报 over_cap。"""
        batch = self.ledger.authorize_batch("cap6", authorized_calls=3,
                                            window_seconds=300, source="u",
                                            records_cap=6)
        self.assertEqual(batch["records_cap"], 6)

    def test_seed_from_unaudited_source_is_refused(self):
        with self.assertRaises(platform_mod.PlatformBudgetError) as caught:
            self.ledger.authorize_batch("bad", authorized_calls=3, window_seconds=300,
                                        source="u", seed_from=("not-a-source",))
        self.assertEqual(caught.exception.code, "seed_source_unaudited")


    def test_login_settle_failure_returns_nonzero_through_the_cli(self):
        import contextlib
        import io

        argv = ["--state-dir", str(self.dir / "cli-state"), "--batch-id", "b1",
                "--profile", str(self.dir / "p"), "login", "--timeout", "5"]
        buffer = io.StringIO()
        with mock.patch.object(weibo, "_open_guard", lambda: self.ledger), \
                mock.patch.object(browser_mod, "available",
                                  return_value={"usable": False, "reason": "no chrome"}), \
                mock.patch.object(self.ledger, "record_result",
                                  side_effect=RuntimeError("disk full")), \
                contextlib.redirect_stdout(buffer):
            code = weibo.main(argv)
        self.assertEqual(code, codes.EXIT_BUDGET)          # the real CLI exit
        payload = json.loads(buffer.getvalue().strip().splitlines()[-1])
        self.assertEqual(payload["status"], "unknown")
        self.assertFalse(payload["signed_in"])
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["exit"], codes.EXIT_BUDGET)
        self.assertFalse(payload["result_persisted"])
        self.assertTrue(payload["stop"].startswith("platform:result_write_failed"))

    def test_both_ledgers_and_payload_carry_no_sensitive_values(self):
        keyword = "秘密关键词ABC"
        secret = "TOKEN_SECRET123"
        state = self.dir / "leak-state"
        batch = budget_mod.open_budget(state, clock=self.clock)
        transport = FakeTransport({"status": 200, "text": SEARCH_HTML, "json": None})
        try:
            payload = weibo.run_search(keyword, batch=batch, transport=transport,
                                       collected_at=COLLECTED, platform=self.ledger,
                                       batch_id="b1")
            self.clock.advance(16)                     # past the 15 s interval
            self.pclock.advance(16)                    # platform ledger interval too
            comments = weibo.run_comments(
                f"https://m.weibo.cn/detail/1?token={secret}", batch=batch,
                transport=transport, collected_at=COLLECTED, platform=self.ledger,
                batch_id="b1")
        finally:
            batch.close()
        # 1) the old state-dir ledger
        old_rows = budget_mod.read_ledger(state, 50)
        # 2) the platform ledger
        platform_rows = self.ledger.events(50)
        # 3) the returned payloads
        blob = json.dumps([payload, comments, old_rows, platform_rows], ensure_ascii=False)
        self.assertNotIn(keyword, blob)
        self.assertNotIn(secret, blob)
        self.assertNotIn("q=", blob)
        self.assertNotIn("token=", blob)
