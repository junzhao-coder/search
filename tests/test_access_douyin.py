"""Offline tests for the Douyin adapter: no network, no browser, no real profile."""

from __future__ import annotations

import contextlib
import io
import json
import pathlib
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from tools.selection.access import budget as budget_mod  # noqa: E402
from tools.selection.access import codes  # noqa: E402
from tools.selection.access import douyin  # noqa: E402
from tools.selection.access import transport as transport_mod  # noqa: E402

COLLECTED = "2026-10-29T15:00:00Z"
SEARCH_HTML = (
    '<html><body>'
    '<a href="/video/7000000000000000001">全文</a>'
    '<a href="/video/7000000000000000001">重复</a>'
    '<a href="/video/7000000000000000002">第二条标题</a>'
    '<a href="/user/someone">作者主页</a>'
    '</body></html>'
)


class FakeClock:
    def __init__(self, start: float = 5_000_000.0) -> None:
        self.now = start

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


class FakeTransport:
    """Offline double: returns a canned page and records the URLs it was asked for."""

    def __init__(self, page: dict) -> None:
        self.page = page
        self.urls: list[str] = []

    def fetch(self, url: str) -> dict:
        self.urls.append(url)
        return {**self.page, "url": url, "final_url": url}


class DouyinTestBase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = pathlib.Path(self._tmp.name)
        self.clock = FakeClock()
        self._budgets = []
        self._ledgers = []

    def tearDown(self):
        for batch in self._budgets:
            with contextlib.suppress(Exception):
                batch.close()
        for ledger in self._ledgers:
            with contextlib.suppress(Exception):
                ledger.close()
        self._tmp.cleanup()

    def run_cli(self, argv):
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            code = douyin.main(argv)
        return code, json.loads(buffer.getvalue().strip().splitlines()[-1])

    def budget(self, name="state"):
        batch = budget_mod.open_budget(self.dir / name, clock=self.clock)
        self._budgets.append(batch)
        return batch

    def ledger(self, *, authorized=3, batch_id="d1", name="douyin.sqlite3"):
        led = douyin.DouyinLedger(self.dir / name, clock=self.clock)
        self._ledgers.append(led)
        led.authorize_batch(batch_id, authorized_calls=authorized,
                            window_seconds=300, source="test")
        return led


class DoctorTests(DouyinTestBase):
    def test_doctor_reports_profile_and_never_touches_the_network(self):
        report = douyin.doctor(self.dir / "missing-profile")
        self.assertEqual(report["site"], "douyin")
        self.assertFalse(report["profile_exists"])
        self.assertEqual(report["network"], "none")
        self.assertEqual(report["online"], "unverified")

    def test_doctor_reads_cookie_names_only(self):
        profile = self.dir / "profile" / "Default" / "Network"
        profile.mkdir(parents=True)
        conn = __import__("sqlite3").connect(str(profile / "Cookies"))
        conn.execute("CREATE TABLE cookies (host_key TEXT, name TEXT, value TEXT)")
        conn.execute("INSERT INTO cookies VALUES ('.douyin.com','sessionid','SECRET')")
        conn.commit()
        conn.close()
        report = douyin.doctor(self.dir / "profile")
        self.assertTrue(report["cookie_db_exists"])
        self.assertTrue(report["cookie_names"]["sessionid"])
        self.assertNotIn("SECRET", json.dumps(report))


class OfflineDefaultTests(DouyinTestBase):
    def test_default_transport_is_refused_and_charges_nothing_remote(self):
        transport = douyin._make_transport(type("A", (), {"mode": "offline"})())
        self.assertIsInstance(transport, transport_mod.RefusedTransport)

    def test_search_offline_reports_transport_error_and_keeps_the_charge(self):
        led = self.ledger()
        payload = douyin.run_search(
            "学习计划模板", batch=self.budget(), transport=transport_mod.RefusedTransport(),
            collected_at=COLLECTED, ledger=led, batch_id="d1")
        self.assertEqual(payload["exit"], codes.EXIT_TRANSPORT)
        self.assertEqual(payload["records"], [])
        summary = led.summary("d1")
        self.assertEqual(summary["used"], 1)          # failure still consumed


class LedgerTests(DouyinTestBase):
    def test_charge_is_shared_across_state_dirs_and_restarts(self):
        led = self.ledger(authorized=2)
        led.charge("d1", "search", detail="https://www.douyin.com/search")
        self.clock.advance(20)
        # a second "state dir" is a second ledger object on the same authority
        other = douyin.DouyinLedger(self.dir / "douyin.sqlite3", clock=self.clock)
        self._ledgers.append(other)
        other.charge("d1", "search", detail="https://www.douyin.com/search")
        self.assertEqual(other.summary("d1")["used"], 2)
        self.clock.advance(20)
        with self.assertRaises(douyin.DouyinBudgetError) as caught:
            other.charge("d1", "search")
        self.assertEqual(caught.exception.code, "calls_exhausted")

    def test_interval_and_window_are_enforced(self):
        led = self.ledger(authorized=3)
        led.charge("d1", "search")
        with self.assertRaises(douyin.DouyinBudgetError) as caught:
            led.charge("d1", "search")
        self.assertEqual(caught.exception.code, "interval_not_elapsed")
        self.clock.advance(301)
        with self.assertRaises(douyin.DouyinBudgetError) as caught:
            led.charge("d1", "search")
        self.assertEqual(caught.exception.code, "batch_window_closed")

    def test_risk_lock_survives_a_new_ledger_and_blocks_other_dirs(self):
        led = self.ledger()
        transport = FakeTransport({"status": None, "text": "", "json": None,
                                   "error": "browser:risk:text:安全验证",
                                   "diagnostics": {"state": "risk",
                                                   "risk": "text:安全验证"}})
        payload = douyin.run_search("x", batch=self.budget(), transport=transport,
                                    collected_at=COLLECTED, ledger=led, batch_id="d1")
        self.assertEqual(payload["exit"], codes.EXIT_RISK)
        reopened = douyin.DouyinLedger(self.dir / "douyin.sqlite3", clock=self.clock)
        self._ledgers.append(reopened)
        locked, reason = reopened.locked()
        self.assertTrue(locked)
        self.assertIn("安全验证", str(reason))

    def test_records_target_is_soft(self):
        led = self.ledger()
        led.reserve_records("d1", 3)
        led.reserve_records("d1", 2)
        over = led.reserve_records("d1", 1)
        self.assertTrue(over["over_cap"])
        self.assertEqual(over["over_by"], 1)
        self.assertEqual(over["records_used"], 6)
        self.assertEqual(over["records_target"], 5)


class ParseTests(DouyinTestBase):
    def test_search_parses_and_deduplicates_video_ids(self):
        parsed = douyin.parse_search_html(SEARCH_HTML, collected_at=COLLECTED)
        ids = [r["native_id"] for r in parsed["records"]]
        self.assertEqual(ids, ["7000000000000000001", "7000000000000000002"])
        self.assertEqual(parsed["anchors_total"], 4)
        self.assertEqual(parsed["anchors_recognized"], 2)
        self.assertEqual(parsed["anchors_rejected"], 2)

    def test_generic_anchor_text_is_not_used_as_the_body(self):
        parsed = douyin.parse_search_html(
            '<a href="/video/7000000000000000009">全文</a>', collected_at=COLLECTED)
        record = parsed["records"][0]
        self.assertIsNone(record["title"])
        self.assertIsNone(record["text"])
        self.assertIn("title", record["missing"])

    def test_detail_uses_meta_and_refuses_unknown_pages(self):
        page = ('<html><head><meta property="og:title" content="标题">'
                '<meta property="og:description" content="描述"></head></html>')
        parsed = douyin.parse_detail_html(page, "https://www.douyin.com/video/123456",
                                          collected_at=COLLECTED)
        self.assertEqual(parsed["record"]["title"], "标题")
        self.assertEqual(parsed["record"]["text"], "描述")
        unknown = douyin.parse_detail_html("<html></html>",
                                           "https://www.douyin.com/video/123456",
                                           collected_at=COLLECTED)
        self.assertEqual(unknown["stop"], "unsupported")

    def test_detail_rejects_non_video_urls(self):
        payload = douyin.run_detail("https://www.douyin.com/user/someone",
                                    batch=self.budget(), transport=FakeTransport({}),
                                    collected_at=COLLECTED)
        self.assertEqual(payload["exit"], codes.EXIT_INPUT)


class CommentsTests(DouyinTestBase):
    def test_comments_are_unsupported_and_never_empty_success(self):
        payload = douyin.run_comments("https://www.douyin.com/video/123456",
                                      batch=self.budget(), collected_at=COLLECTED)
        self.assertEqual(payload["exit"], codes.EXIT_UNSUPPORTED)
        self.assertEqual(payload["records"], [])
        self.assertTrue(payload["stop"].startswith("comments_not_supported"))


class ExportTests(DouyinTestBase):
    def test_export_keeps_the_shared_whitelist(self):
        source = self.dir / "in.jsonl"
        source.write_text(json.dumps({
            "native_id": "1", "type": "video", "url": "https://www.douyin.com/video/1",
            "title": "t", "collected_at": COLLECTED, "source": "douyin:search:video",
            "secret": "drop-me"}) + "\n", encoding="utf-8")
        out = self.dir / "out.jsonl"
        payload = douyin.export(source, out)
        self.assertEqual(payload["exit"], codes.EXIT_OK)
        row = json.loads(out.read_text(encoding="utf-8").strip())
        self.assertNotIn("secret", row)


class CliTests(DouyinTestBase):
    def run_cli(self, argv):
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            code = douyin.main(argv)
        return code, json.loads(buffer.getvalue().strip().splitlines()[-1])

    def test_real_network_mode_requires_an_authorized_batch(self):
        argv = ["--state-dir", str(self.dir / "s"), "--batch-id", "nope",
                "--mode", "authenticated-browser", "--profile", str(self.dir / "p"),
                "search", "x"]
        with mock.patch.object(douyin, "open_ledger",
                               lambda: douyin.DouyinLedger(self.dir / "l.sqlite3")):
            code, payload = self.run_cli(argv)
        self.assertEqual(code, codes.EXIT_BUDGET)
        self.assertEqual(payload["stop"], "platform:no_authorized_batch")

    def test_login_is_unsupported_and_charges_nothing(self):
        led = self.ledger()
        payload = douyin.login(self.dir / "p", budget=self.budget(), ledger=led,
                               batch_id="d1")
        self.assertEqual(payload["status"], "unsupported")
        self.assertFalse(payload["signed_in"])
        self.assertEqual(payload["exit"], codes.EXIT_UNSUPPORTED)
        self.assertTrue(payload["stop"].startswith("login_not_supported"))
        self.assertEqual(led.summary("d1")["used"], 0)     # nothing pre-deducted
        self.assertEqual(led.events(5), [])


if __name__ == "__main__":  # pragma: no cover
    unittest.main()


class KeywordLeakTests(DouyinTestBase):
    """Neither ledger nor the returned payload may carry the search keyword."""

    def run_and_scan(self, keyword):
        state = self.dir / f"state-{abs(hash(keyword))}"
        batch = budget_mod.open_budget(state, clock=self.clock)
        led = self.ledger()
        transport = FakeTransport({"status": 200, "text": SEARCH_HTML, "json": None})
        try:
            payload = douyin.run_search(keyword, batch=batch, transport=transport,
                                        collected_at=COLLECTED, ledger=led,
                                        batch_id="d1")
        finally:
            batch.close()
        blob = json.dumps({
            "payload": payload,
            "old_ledger": budget_mod.read_ledger(state, 20),
            "platform": led.events(20),
        }, ensure_ascii=False)
        for form in {keyword, __import__("urllib.parse").parse.quote(keyword)}:
            self.assertNotIn(form, blob)
        return payload

    def test_chinese_keyword_never_leaks(self):
        payload = self.run_and_scan("学习计划模板")
        self.assertEqual(payload["exit"], codes.EXIT_OK)
        self.assertEqual(payload["url"], douyin.SEARCH_PAGE)

    def test_english_keyword_never_leaks(self):
        self.run_and_scan("study plan")


class HostValidationTests(DouyinTestBase):
    def test_off_host_anchors_never_become_records(self):
        html = ('<a href="https://evil.example/video/7000000000000000001">x</a>'
                '<a href="/video/7000000000000000002">ok</a>')
        parsed = douyin.parse_search_html(html, collected_at=COLLECTED)
        self.assertEqual([r["native_id"] for r in parsed["records"]],
                         ["7000000000000000002"])

    def test_detail_rejects_foreign_hosts_before_fetch(self):
        transport = FakeTransport({"status": 200, "text": "x", "json": None})
        payload = douyin.run_detail("https://evil.example/video/123456",
                                    batch=self.budget(), transport=transport,
                                    collected_at=COLLECTED)
        self.assertEqual(payload["exit"], codes.EXIT_INPUT)
        self.assertEqual(transport.urls, [])


class RiskLockTests(DouyinTestBase):
    def test_parse_detail_risk_locks_both_scopes(self):
        led = self.ledger()
        page = "<html><body>安全验证</body></html>"
        payload = douyin.run_detail(
            "https://www.douyin.com/video/123456", batch=self.budget(),
            transport=FakeTransport({"status": 200, "text": page, "json": None}),
            collected_at=COLLECTED, ledger=led, batch_id="d1")
        self.assertEqual(payload["exit"], codes.EXIT_RISK)
        locked, reason = led.locked()
        self.assertTrue(locked)
        self.assertIn("安全验证", str(reason))
        # a fresh instance (restart) still sees the lock
        reopened = douyin.DouyinLedger(self.dir / "douyin.sqlite3", clock=self.clock)
        self._ledgers.append(reopened)
        self.assertTrue(reopened.locked()[0])

    def test_lock_write_failure_is_nonzero(self):
        led = self.ledger()
        page = "<html><body>安全验证</body></html>"
        with mock.patch.object(led, "lock", side_effect=RuntimeError("disk full")):
            payload = douyin.run_detail(
                "https://www.douyin.com/video/123456", batch=self.budget(),
                transport=FakeTransport({"status": 200, "text": page, "json": None}),
                collected_at=COLLECTED, ledger=led, batch_id="d1")
        self.assertEqual(payload["exit"], codes.EXIT_BUDGET)
        self.assertTrue(str(payload["stop"]).startswith("platform:lock_write_failed"))

    def test_settle_failure_is_not_a_success(self):
        led = self.ledger()
        with mock.patch.object(led, "record_result", side_effect=RuntimeError("disk")):
            payload = douyin.run_search(
                "x", batch=self.budget(),
                transport=FakeTransport({"status": 200, "text": SEARCH_HTML,
                                         "json": None}),
                collected_at=COLLECTED, ledger=led, batch_id="d1")
        self.assertEqual(payload["exit"], codes.EXIT_BUDGET)
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["records"], [])


    def test_cli_login_exits_unsupported_without_charging(self):
        led = self.ledger()
        argv = ["--state-dir", str(self.dir / "cli-login"), "--batch-id", "d1",
                "--profile", str(self.dir / "p"), "login", "--timeout", "5"]
        with mock.patch.object(douyin, "open_ledger", lambda: led):
            code, payload = self.run_cli(argv)
        self.assertEqual(code, codes.EXIT_UNSUPPORTED)
        self.assertEqual(payload["status"], "unsupported")
        self.assertEqual(led.summary("d1")["used"], 0)
        self.assertEqual(led.events(5), [])

    def test_cli_search_keyword_never_reaches_the_ledgers(self):
        led = self.ledger()
        state = self.dir / "cli-search"
        argv = ["--state-dir", str(state), "--batch-id", "d1",
                "--profile", str(self.dir / "p"), "search", "学习计划模板"]
        with mock.patch.object(douyin, "open_ledger", lambda: led), \
                mock.patch.object(douyin, "_make_transport",
                                  lambda args: FakeTransport(
                                      {"status": 200, "text": SEARCH_HTML, "json": None})):
            code, payload = self.run_cli(argv)
        self.assertEqual(code, codes.EXIT_OK)
        reopened = douyin.DouyinLedger(self.dir / "douyin.sqlite3", clock=self.clock)
        self._ledgers.append(reopened)
        blob = json.dumps({"payload": payload,
                           "old": budget_mod.read_ledger(state, 20),
                           "platform": reopened.events(20)}, ensure_ascii=False)
        self.assertNotIn("学习计划模板", blob)
        self.assertNotIn(__import__("urllib.parse").parse.quote("学习计划模板"), blob)


class TransportErrorScrubTests(DouyinTestBase):
    """A failing fetch must not leak the keyword through error or diagnostics."""

    def test_error_and_diagnostics_with_the_raw_url_are_scrubbed(self):
        keyword = "学习计划模板"
        state = self.dir / "err-state"
        batch = budget_mod.open_budget(state, clock=self.clock)
        led = self.ledger()
        raw_url = douyin.search_url(keyword)
        transport = FakeTransport({"status": None, "text": "", "json": None,
                                   "error": f"navigate_failed:{raw_url}",
                                   "diagnostics": {"requested_url": raw_url,
                                                   "final_url": raw_url}})
        try:
            payload = douyin.run_search(keyword, batch=batch, transport=transport,
                                        collected_at=COLLECTED, ledger=led,
                                        batch_id="d1")
        finally:
            batch.close()
        reopened = douyin.DouyinLedger(self.dir / "douyin.sqlite3", clock=self.clock)
        self._ledgers.append(reopened)
        blob = json.dumps({"payload": payload,
                           "old": budget_mod.read_ledger(state, 20),
                           "platform": reopened.events(20)}, ensure_ascii=False)
        self.assertNotEqual(payload["exit"], codes.EXIT_OK)
        for form in (keyword, __import__("urllib.parse").parse.quote(keyword)):
            self.assertNotIn(form, blob)
        self.assertIn("transport_error", [row["kind"] for row in
                                          budget_mod.read_ledger(state, 20)])

    def test_fetch_exception_still_settles_unknown(self):
        led = self.ledger()
        transport = FakeTransport({"status": 200, "text": "", "json": None})
        transport.fetch = mock.Mock(side_effect=RuntimeError("tab died"))
        payload = douyin.run_search("study plan", batch=self.budget(),
                                    transport=transport, collected_at=COLLECTED,
                                    ledger=led, batch_id="d1")
        self.assertEqual(payload["exit"], codes.EXIT_TRANSPORT)
        self.assertEqual(payload["records"], [])
        kinds = [row["kind"] for row in led.events(10)]
        self.assertIn("search_result", kinds)
        self.assertEqual(led.summary("d1")["used"], 1)


class DetailSettleTests(DouyinTestBase):
    def test_success_records_a_result(self):
        led = self.ledger()
        page = ('<meta property="og:title" content="标题">'
                '<meta property="og:description" content="描述">')
        payload = douyin.run_detail("https://www.douyin.com/video/123456",
                                    batch=self.budget(),
                                    transport=FakeTransport({"status": 200,
                                                             "text": page, "json": None}),
                                    collected_at=COLLECTED, ledger=led, batch_id="d1")
        self.assertEqual(payload["exit"], codes.EXIT_OK)
        results = [row for row in led.events(10) if row["kind"] == "detail_result"]
        self.assertEqual(results[0]["detail"], "success")

    def test_result_write_failure_is_nonzero_with_no_records(self):
        led = self.ledger()
        page = ('<meta property="og:title" content="标题">'
                '<meta property="og:description" content="描述">')
        with mock.patch.object(led, "record_result", side_effect=RuntimeError("disk")):
            payload = douyin.run_detail(
                "https://www.douyin.com/video/123456", batch=self.budget(),
                transport=FakeTransport({"status": 200, "text": page, "json": None}),
                collected_at=COLLECTED, ledger=led, batch_id="d1")
        self.assertEqual(payload["exit"], codes.EXIT_BUDGET)
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["records"], [])
        self.assertTrue(str(payload["stop"]).startswith("platform:result_write_failed"))


class WallVsDescriptionTests(DouyinTestBase):
    def test_wall_only_in_description_is_ambiguous_not_a_lock(self):
        led = self.ledger()
        page = ('<meta property="og:title" content="我的登录体验">'
                '<meta property="og:description" content="今天遇到了安全验证，记录一下">')
        payload = douyin.run_detail(
            "https://www.douyin.com/video/123456", batch=self.budget(),
            transport=FakeTransport({"status": 200, "text": page, "json": None}),
            collected_at=COLLECTED, ledger=led, batch_id="d1")
        self.assertEqual(payload["exit"], codes.EXIT_UNSUPPORTED)
        self.assertEqual(payload["stop"], "risk_ambiguous")
        self.assertEqual(payload["records"], [])
        self.assertFalse(led.locked()[0])          # ordinary content is not a wall

    def test_wall_in_title_locks_both_scopes(self):
        led = self.ledger()
        page = ('<meta property="og:title" content="安全验证">'
                '<meta property="og:description" content="请完成验证">')
        payload = douyin.run_detail(
            "https://www.douyin.com/video/123456", batch=self.budget(),
            transport=FakeTransport({"status": 200, "text": page, "json": None}),
            collected_at=COLLECTED, ledger=led, batch_id="d1")
        self.assertEqual(payload["exit"], codes.EXIT_RISK)
        locked, reason = led.locked()
        self.assertTrue(locked)
        self.assertIn("安全验证", str(reason))


class DetailExceptionTests(DouyinTestBase):
    """A charged detail call that raises must still settle, non-zero, no records."""

    def test_fetch_exception_settles_unknown_through_the_cli(self):
        led = self.ledger()
        state = self.dir / "detail-cli"
        argv = ["--state-dir", str(state), "--batch-id", "d1",
                "--profile", str(self.dir / "p"),
                "detail", "https://www.douyin.com/video/123456"]
        boom = FakeTransport({"status": 200, "text": "", "json": None})
        boom.fetch = mock.Mock(side_effect=RuntimeError("tab died"))
        with mock.patch.object(douyin, "open_ledger", lambda: led), \
                mock.patch.object(douyin, "_make_transport", lambda args: boom):
            code, payload = self.run_cli(argv)
        self.assertEqual(code, codes.EXIT_TRANSPORT)
        self.assertEqual(payload["records"], [])
        self.assertTrue(payload["stop"].startswith("adapter_exception:"))
        reopened = douyin.DouyinLedger(self.dir / "douyin.sqlite3", clock=self.clock)
        self._ledgers.append(reopened)
        results = [row for row in reopened.events(10) if row["kind"] == "detail_result"]
        self.assertEqual(results[0]["detail"], "unknown")

    def test_exception_plus_result_write_failure_is_nonzero_and_empty(self):
        led = self.ledger()
        boom = FakeTransport({"status": 200, "text": "", "json": None})
        boom.fetch = mock.Mock(side_effect=RuntimeError("tab died"))
        with mock.patch.object(led, "record_result", side_effect=RuntimeError("disk")):
            payload = douyin.run_detail(
                "https://www.douyin.com/video/123456", batch=self.budget(),
                transport=boom, collected_at=COLLECTED, ledger=led, batch_id="d1")
        self.assertEqual(payload["exit"], codes.EXIT_BUDGET)
        self.assertEqual(payload["records"], [])
        self.assertTrue(str(payload["stop"]).startswith("platform:result_write_failed"))


class RiskReasonScrubTests(DouyinTestBase):
    """A risk reason that embeds the search URL must be scrubbed before locking."""

    def check(self, keyword):
        led = self.ledger()
        state = self.dir / f"risk-{abs(hash(keyword))}"
        raw_url = douyin.search_url(keyword)
        transport = FakeTransport({"status": None, "text": "", "json": None,
                                   "error": f"offsite_redirect:{raw_url}",
                                   "diagnostics": {"state": "risk",
                                                   "risk": f"text:offsite_redirect {raw_url}"}})
        batch = budget_mod.open_budget(state, clock=self.clock)
        try:
            payload = douyin.run_search(keyword, batch=batch, transport=transport,
                                        collected_at=COLLECTED, ledger=led,
                                        batch_id="d1")
        finally:
            batch.close()
        reopened = douyin.DouyinLedger(self.dir / "douyin.sqlite3", clock=self.clock)
        self._ledgers.append(reopened)
        locked, reason = reopened.locked()
        blob = json.dumps({"payload": payload, "lock": reason,
                           "old": budget_mod.read_ledger(state, 20),
                           "platform": reopened.events(20)}, ensure_ascii=False)
        for form in (keyword, __import__("urllib.parse").parse.quote(keyword)):
            self.assertNotIn(form, blob)
        return payload, locked

    def test_offsite_redirect_reason_is_scrubbed_chinese(self):
        payload, locked = self.check("学习计划模板")
        self.assertEqual(payload["exit"], codes.EXIT_RISK)
        self.assertTrue(locked)                    # the lock itself still persists

    def test_offsite_redirect_reason_is_scrubbed_english(self):
        self.check("study plan")
