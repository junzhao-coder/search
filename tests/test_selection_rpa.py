"""Browser-RPA：可见卡片提取、本地窗口策略、风险优先、平台守卫、桌面证据（纯离线/本地）。

本文件不需要真实网络：真实浏览器只在 `docs/validation/v10/browser-rpa/checks/` 下跑；
这里用 fake tab / fake session / fake ledger 覆盖守卫顺序与失败分支。
"""

from __future__ import annotations

import contextlib
import io
import json
import pathlib
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

REPO = pathlib.Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from tools.selection.access import codes  # noqa: E402
from tools.selection.access import platform_budget as pb  # noqa: E402
from tools.selection.access import weibo as weibo_mod  # noqa: E402
from tools.selection.rpa import cli, desktop, extract, guard, session  # noqa: E402

COLLECTED = "2026-10-30T04:00:00Z"


def card(**over):
    base = {"container_id": "c1", "id": "4900000000000001",
            "url": "https://m.weibo.cn/status/4900000000000001",
            "text": "周计划模板正文", "title": "周计划模板分享", "time": "3小时前",
            "counts": {"comments": 3, "likes": 45}, "hidden": False}
    base.update(over)
    return base


class ExtractTests(unittest.TestCase):
    def test_card_becomes_record_with_same_container_fields(self):
        parsed = extract.extract_cards([card()], collected_at=COLLECTED)
        record = parsed["records"][0]
        self.assertIsNone(parsed["stop"])
        self.assertEqual(record["native_id"], "4900000000000001")
        self.assertEqual(record["title"], "周计划模板分享")
        self.assertEqual(record["text"], "周计划模板正文")
        self.assertEqual(record["published_at"], "3小时前")
        self.assertEqual(record["comments"], 3)
        self.assertEqual(record["likes"], 45)
        self.assertIsNone(record["voteup"])                      # 转发不冒充赞同
        self.assertEqual(record["field_evidence"]["text"], "dom:card visible text")
        self.assertTrue(record["supported"])
        self.assertTrue(any("assumed" in a for a in parsed["assumptions"]))

    def test_hidden_card_is_rejected(self):
        parsed = extract.extract_cards([card(hidden=True)], collected_at=COLLECTED)
        self.assertEqual(parsed["records"], [])
        self.assertEqual(parsed["diagnostics"]["rejected"], {"hidden": 1})
        self.assertEqual(parsed["stop"], "empty")

    def test_duplicate_id_and_container_are_deduped(self):
        parsed = extract.extract_cards(
            [card(), card(container_id="c2"), card(container_id="c1")],
            collected_at=COLLECTED)
        self.assertEqual(len(parsed["records"]), 1)
        self.assertEqual(parsed["diagnostics"]["rejected"],
                         {"duplicate_id": 1, "duplicate_container": 1})

    def test_nested_cards_same_id_collapse_and_inner_is_skipped(self):
        """Python 规则层：内层卡（同 id）只算一次；不同 id 的平面输入仍各自成记录。

        真实 DOM 的嵌套政策（内层整棵跳过、不串正文）由
        `docs/validation/v10/browser-rpa/checks/card_js_check.py` 在真实浏览器里验证。
        """
        nested_same = [card(), card(container_id="inner")]
        nested_diff = [card(), card(container_id="c9", id="4900000000000002",
                                    url="https://m.weibo.cn/status/4900000000000002")]
        self.assertEqual(len(extract.extract_cards(nested_same,
                                                   collected_at=COLLECTED)["records"]), 1)
        self.assertEqual(len(extract.extract_cards(nested_diff,
                                                   collected_at=COLLECTED)["records"]), 2)

    def test_url_scheme_host_path_and_id_must_all_match(self):
        cases = {
            "bad_scheme": card(url="file:///D:/status/4900000000000001"),
            "foreign_host": card(url="https://evil.example.com/status/4900000000000001"),
            "bad_path": card(url="https://m.weibo.cn/foo/4900000000000001"),
            "url_id_mismatch": card(url="https://m.weibo.cn/status/4900000000000002"),
        }
        for reason, bad in cases.items():
            with self.subTest(reason=reason):
                parsed = extract.extract_cards([bad], collected_at=COLLECTED)
                self.assertEqual(parsed["records"], [])
                self.assertEqual(parsed["diagnostics"]["rejected"], {reason: 1})

    def test_foreign_host_is_rejected(self):
        parsed = extract.extract_cards(
            [card(url="https://evil.example.com/status/4900000000000001")],
            collected_at=COLLECTED)
        self.assertEqual(parsed["records"], [])
        self.assertEqual(parsed["diagnostics"]["rejected"], {"foreign_host": 1})

    def test_missing_keys_bad_id_and_empty_text_are_rejected(self):
        parsed = extract.extract_cards(
            [{"id": "1"}, card(id="abc"), card(text="", title="")],
            collected_at=COLLECTED)
        self.assertEqual(parsed["diagnostics"]["rejected"],
                         {"missing_keys": 1, "bad_id": 1, "no_text": 1})

    def test_empty_input_is_unknown(self):
        parsed = extract.extract_cards([], collected_at=COLLECTED)
        self.assertEqual(parsed["stop"], "unknown")
        self.assertEqual(parsed["records"], [])

    def test_limit_is_respected(self):
        cards = [card(container_id=f"c{i}", id=f"49000000000000{i:02d}",
                      url=f"https://m.weibo.cn/status/49000000000000{i:02d}")
                 for i in range(1, 8)]
        parsed = extract.extract_cards(cards, collected_at=COLLECTED, limit=5)
        self.assertEqual(len(parsed["records"]), 5)

    def test_detail_ok_and_unsupported(self):
        ok = extract.extract_detail(card(), collected_at=COLLECTED)
        self.assertIsNone(ok["stop"])
        self.assertEqual(ok["record"]["source"], "weibo:detail:status")
        bad = extract.extract_detail({"id": "x"}, collected_at=COLLECTED)
        self.assertEqual(bad["stop"], "unsupported")
        none = extract.extract_detail(None, collected_at=COLLECTED)
        self.assertEqual(none["stop"], "unsupported")

    def test_detail_rejects_every_reason_without_record(self):
        cases = {
            "hidden": card(hidden=True),
            "missing_keys": {"id": "4900000000000001"},
            "bad_id": card(id="abc"),
            "bad_scheme": card(url="file:///D:/status/4900000000000001"),
            "foreign_host": card(url="https://evil.example.com/status/4900000000000001"),
            "bad_path": card(url="https://m.weibo.cn/foo/4900000000000001"),
            "url_id_mismatch": card(url="https://m.weibo.cn/status/4900000000000002"),
            "no_text": card(text="", title=""),
        }
        for reason, bad in cases.items():
            with self.subTest(reason=reason):
                parsed = extract.extract_detail(bad, collected_at=COLLECTED)
                self.assertEqual(parsed["stop"], "unsupported")
                self.assertIsNone(parsed["record"])
                self.assertEqual(parsed["diagnostics"]["reason"], reason)


class CliExtractTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = pathlib.Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def _cards(self, payload) -> str:
        path = self.dir / "cards.json"
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        return str(path)

    def test_extract_cards_exit_zero_and_writes_out(self):
        path = self._cards({"cards": [card(), card(container_id="c2",
                                                   id="4900000000000002",
                                                   url="https://m.weibo.cn/status/4900000000000002")]})
        out = str(self.dir / "records.jsonl")
        self.assertEqual(cli.main(["extract", "--cards-json", path, "--out", out]),
                         codes.EXIT_OK)
        rows = [json.loads(line) for line in pathlib.Path(out).read_text(
            encoding="utf-8").splitlines()]
        self.assertEqual(len(rows), 2)

    def test_extract_empty_is_three_and_unknown_is_four(self):
        self.assertEqual(cli.main(["extract", "--cards-json", self._cards({"cards": []})]),
                         codes.EXIT_UNSUPPORTED)
        only_hidden = self._cards({"cards": [card(hidden=True)]})
        self.assertEqual(cli.main(["extract", "--cards-json", only_hidden]),
                         codes.EXIT_EMPTY)

    def test_extract_missing_file_is_input_error(self):
        self.assertEqual(cli.main(["extract", "--cards-json", str(self.dir / "nope.json")]),
                         codes.EXIT_INPUT)

    def test_detail_without_id_is_unsupported(self):
        self.assertEqual(cli.main(["extract", "--cards-json",
                                   self._cards({"cards": [{"id": "x"}]}),
                                   "--kind", "detail"]),
                         codes.EXIT_UNSUPPORTED)


class WindowPolicyTests(unittest.TestCase):
    """window 只能本地：http(s)/外域 file 一律 blocked，不启动浏览器。"""

    def test_http_url_is_blocked(self):
        self.assertEqual(cli.main(["window", "--profile", "x", "--url",
                                   "https://m.weibo.cn/"]), codes.EXIT_BUDGET)

    def test_file_outside_fixtures_is_blocked(self):
        outside = pathlib.Path(tempfile.gettempdir()) / "not-fixture.html"
        outside.write_text("<html></html>", encoding="utf-8")
        try:
            self.assertEqual(cli.main(["window", "--profile", "x", "--url",
                                       outside.as_uri()]), codes.EXIT_BUDGET)
        finally:
            outside.unlink(missing_ok=True)

    def test_about_blank_dry_run_is_ok(self):
        self.assertEqual(cli.main(["window", "--profile", "x", "--dry-run"]),
                         codes.EXIT_OK)

    def test_live_search_without_allow_live_is_blocked(self):
        """没有 --allow-live 就拒绝，且不打开账本、不启动浏览器。"""
        with mock.patch.object(cli, "_open_ledger",
                               side_effect=AssertionError("ledger must not be opened")):
            self.assertEqual(cli.main(["live-search", "--keyword", "kw"]),
                             codes.EXIT_BUDGET)

    def test_cli_has_no_platform_db_override(self):
        with self.assertRaises(SystemExit):
            cli.build_parser().parse_args(
                ["live-search", "--keyword", "kw", "--platform-db", "x.sqlite3"])

    def test_cli_has_no_state_dir_or_ledger_path_flag(self):
        """账本路径固定：换 state-dir 这种入口根本不存在，所以也不可能重置额度/锁。"""
        for flag in ("--state-dir", "--ledger", "--ledger-path"):
            with self.subTest(flag=flag):
                with self.assertRaises(SystemExit):
                    cli.build_parser().parse_args(
                        ["live-search", "--keyword", "kw", flag, "x"])


class FakeTab:
    """duck-typed tab：按脚本返回预置值，用来测导航边界（不启浏览器）。"""

    def __init__(self, values):
        self._values = list(values)
        self._last = None

    async def evaluate(self, script):
        if self._values:
            self._last = self._values.pop(0)
        return self._last


class NavigateBoundaryTests(unittest.TestCase):
    def _session(self):
        return session.VisibleSession("unused-profile")

    def test_redirect_and_completion(self):
        tab = FakeTab(["file:///a.html",
                       json.dumps({"href": "file:///b.html", "ready": "loading"}),
                       json.dumps({"href": "file:///b.html", "ready": "complete"})])
        out = self._session().navigate_stable(tab, attempts=3, interval=0)
        self.assertEqual(out["requested_url"], "file:///a.html")
        self.assertEqual(out["final_url"], "file:///b.html")
        self.assertEqual(out["redirects"], ["file:///b.html"])
        self.assertFalse(out["timed_out"])
        self.assertFalse(out["escaped"])

    def test_escape_to_http_is_flagged(self):
        tab = FakeTab(["file:///a.html",
                       json.dumps({"href": "https://m.weibo.cn/", "ready": "complete"})])
        out = self._session().navigate_stable(tab, attempts=2, interval=0)
        self.assertTrue(out["escaped"])

    def test_timeout_when_never_complete(self):
        tab = FakeTab(["file:///a.html",
                       json.dumps({"href": "file:///a.html", "ready": "loading"}),
                       json.dumps({"href": "file:///a.html", "ready": "loading"})])
        out = self._session().navigate_stable(tab, attempts=2, interval=0)
        self.assertTrue(out["timed_out"])


class LiveSessionModeTests(unittest.TestCase):
    """live/local 的网络策略与入口限制（不启浏览器）。"""

    def test_local_mode_blocks_dns_and_live_mode_does_not(self):
        local = session.VisibleSession("p", live=False).browser_args()
        live = session.VisibleSession("p", live=True, user_agent="UA/1").browser_args()
        self.assertTrue(any("host-resolver-rules" in a for a in local))
        self.assertFalse(any("host-resolver-rules" in a for a in live))
        self.assertIn("--user-agent=UA/1", live)
        self.assertTrue(all("host-resolver-rules" not in a for a in live))

    def test_new_session_carries_timeout_and_user_agent(self):
        """真实参数必须落到 VisibleSession 并进入浏览器启动参数。"""
        sess = cli._new_session("p", live=True, timeout=42.0, user_agent="UA/9")
        self.assertEqual(sess.timeout, 42.0)
        self.assertEqual(sess.user_agent, "UA/9")
        self.assertIn("--user-agent=UA/9", sess.browser_args())

    def test_open_live_requires_live_mode_and_http(self):
        closing = session.VisibleSession("p", live=False)
        closing._browser = object()                      # 只测入口判定，不启浏览器
        with self.assertRaises(session.SessionUnavailable):
            closing.open_live("https://m.weibo.cn/search?containerid=1")
        live = session.VisibleSession("p", live=True)
        live._browser = object()
        with self.assertRaises(session.SessionUnavailable):
            live.open_live("file:///D:/x.html")

    def test_read_page_and_signals_parse_json(self):
        page = {"url": "https://s.weibo.com/weibo?q=x", "ready": "complete",
                "http_status": 200, "text": "x", "text_len": 1}
        tab = FakeTab([json.dumps(page), json.dumps({"host": "weibo.com"})])
        sess = session.VisibleSession("p")
        self.assertEqual(sess.read_page(tab)["http_status"], 200)
        self.assertEqual(sess.read_signals(tab, "js")["host"], "weibo.com")

    def test_wait_ready_times_out_honestly(self):
        tab = FakeTab([json.dumps({"ready": "loading"}), json.dumps({"ready": "loading"})])
        out = session.VisibleSession("p").wait_ready(tab, attempts=2, interval=0)
        self.assertTrue(out["timed_out"])


class StubLedger:
    def __init__(self, *, lock_error=None, result_error=None):
        self.locked_calls, self.result_calls = [], []
        self._lock_error, self._result_error = lock_error, result_error

    def lock(self, reason, *, source="unknown"):
        self.locked_calls.append((reason, source))
        if self._lock_error:
            raise self._lock_error

    def audit(self, batch_id, kind, *, detail="", source="runtime"):
        self.result_calls.append((batch_id, kind, detail, source))
        if self._result_error:
            raise self._result_error


class RiskFirstTests(unittest.TestCase):
    def test_http_status_and_text_markers(self):
        self.assertEqual(guard.risk_reason(http_status=403), "http_403")
        self.assertEqual(guard.risk_reason(http_status=429), "http_429")
        self.assertEqual(guard.risk_reason(text="请完成安全验证"), "text:安全验证")
        self.assertIsNone(guard.risk_reason(text="普通正文，含获取验证码字样"))

    def test_enforce_risk_locks_then_raises(self):
        ledger = StubLedger()
        with self.assertRaises(guard.GuardBlocked) as caught:
            guard.enforce_risk(ledger, text="访问过于频繁", source="test")
        self.assertEqual(caught.exception.stop, "risk:text:访问过于频繁")
        self.assertEqual(ledger.locked_calls, [("text:访问过于频繁", "test")])

    def test_lock_write_failure_is_not_swallowed(self):
        ledger = StubLedger(lock_error=pb.PlatformBudgetError("db_locked"))
        with self.assertRaises(guard.GuardBlocked) as caught:
            guard.lock(ledger, "x")
        self.assertEqual(caught.exception.stop, "lock_write_failed")

    def test_result_write_failure_is_not_swallowed(self):
        ledger = StubLedger(result_error=pb.PlatformBudgetError("db_locked"))
        with self.assertRaises(guard.GuardBlocked) as caught:
            guard.record_result(ledger, "b", "search", "success", source="rpa.search")
        self.assertEqual(caught.exception.stop, "result_write_failed")
        self.assertEqual(ledger.result_calls,
                         [("b", "search_result", "success", "rpa.search")])

    def test_result_kind_must_match_a_known_call_kind(self):
        ledger = StubLedger()
        with self.assertRaises(guard.GuardBlocked) as caught:
            guard.record_result(ledger, "b", "detail", "success", source="rpa.search")
        self.assertEqual(caught.exception.stop, "unknown_result_kind")
        with self.assertRaises(guard.GuardBlocked) as caught:
            guard.record_result(ledger, "b", "search", "maybe", source="rpa.search")
        self.assertEqual(caught.exception.stop, "invalid_outcome")


def _make_source(directory: pathlib.Path, *, locked: bool = False) -> None:
    """A source is a **directory** holding `budget.sqlite3` (canonical_source_path)."""
    directory.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(directory / "budget.sqlite3"))
    con.execute("CREATE TABLE budget (id INTEGER PRIMARY KEY, calls INTEGER, records INTEGER,"
                " locked INTEGER, lock_reason TEXT)")
    con.execute("INSERT INTO budget VALUES (1, 1, 0, ?, ?)",
                (1 if locked else 0, "text:安全验证" if locked else None))
    con.execute("CREATE TABLE ledger (id INTEGER PRIMARY KEY, at REAL, kind TEXT, detail TEXT)")
    con.execute("INSERT INTO ledger(at, kind, detail) VALUES (0, 'charge', '{}')")
    con.commit()
    con.close()


class GuardTests(unittest.TestCase):
    """平台守卫：未授权/已锁/额度用尽都必须 blocked；历史锁会被继承。"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = pathlib.Path(self._tmp.name)
        self.sources, self.manifest = [], []
        for spec in pb.HISTORY_SOURCES:
            directory = self.dir / "src" / spec["source_key"]
            _make_source(directory)
            self.sources.append({**spec, "path": str(directory / "budget.sqlite3")})
            self.manifest.append({**spec, "path": str(directory)})
        self.ledger_path = self.dir / "platform.sqlite3"

    def tearDown(self):
        self._tmp.cleanup()

    def _ledger(self) -> pb.PlatformLedger:
        ledger = pb.PlatformLedger(self.ledger_path, allow_test_manifest=True)
        try:
            ledger.import_snapshot(self.sources, manifest=self.manifest, note="test")
        except Exception:
            ledger.close()
            raise
        return ledger

    def test_unauthorized_batch_is_blocked(self):
        ledger = self._ledger()
        try:
            with self.assertRaises(guard.GuardBlocked) as caught:
                guard.precheck(ledger, None)
            self.assertEqual(caught.exception.stop, "batch_id_required")
            with self.assertRaises(guard.GuardBlocked) as caught:
                guard.precheck(ledger, "nope")
            self.assertEqual(caught.exception.stop, "no_authorized_batch")
        finally:
            ledger.close()

    def test_authorized_batch_allows_exactly_one_charge(self):
        ledger = self._ledger()
        try:
            ledger.authorize_batch("t1", authorized_calls=1, window_seconds=300,
                                   source="test")
            self.assertEqual(guard.precheck(ledger, "t1")["remaining"], 1)
            guard.charge_search(ledger, "t1", "search")
            with self.assertRaises(guard.GuardBlocked) as caught:
                guard.precheck(ledger, "t1")
            self.assertEqual(caught.exception.stop, "calls_exhausted")
        finally:
            ledger.close()

    def test_locked_platform_blocks_even_with_authorized_batch(self):
        ledger = self._ledger()
        try:
            ledger.authorize_batch("t1", authorized_calls=1, window_seconds=300,
                                   source="test")
            ledger.lock("text:安全验证", source="test")
            with self.assertRaises(guard.GuardBlocked) as caught:
                guard.precheck(ledger, "t1")
            self.assertEqual(caught.exception.stop, "platform_locked")
        finally:
            ledger.close()

    def test_locked_history_source_is_inherited_as_platform_lock(self):
        locked_sources, locked_manifest = [], []
        for spec in pb.HISTORY_SOURCES:
            directory = self.dir / "locked_src" / spec["source_key"]
            _make_source(directory, locked=(spec["source_key"] == "probe2"))
            locked_sources.append({**spec, "path": str(directory / "budget.sqlite3")})
            locked_manifest.append({**spec, "path": str(directory)})
        ledger = pb.PlatformLedger(self.dir / "platform2.sqlite3",
                                   allow_test_manifest=True)
        try:
            ledger.import_snapshot(locked_sources, manifest=locked_manifest, note="test")
            ledger.authorize_batch("t2", authorized_calls=1, window_seconds=300,
                                   source="test")
            with self.assertRaises(guard.GuardBlocked) as caught:
                guard.charge_search(ledger, "t2", "search")
            self.assertEqual(caught.exception.stop, "platform:history_locked")
        finally:
            ledger.close()


class RecordedCardJsTests(unittest.TestCase):
    """核对 `checks/card_js_check.py` 在**真实本地浏览器**里跑 CARD_JS 的产物。

    平面 dict 只能验证 Python 规则；真实 DOM 的隐藏文字/导航/作者/嵌套卡是否被排除，
    必须看这份真实产物（缺失时 skip 并说明怎么生成）。
    """

    LOG = REPO / "docs" / "validation" / "v10" / "browser-rpa" / "logs" / "card-js-check.json"

    def setUp(self):
        if not self.LOG.is_file():
            self.skipTest("run docs/validation/v10/browser-rpa/checks/card_js_check.py "
                          "with the x-collect venv first")
        self.payload = json.loads(self.LOG.read_text(encoding="utf-8"))
        self.cards = {str(c["id"]): c for c in self.payload.get("cards") or []}

    def test_recorded_run_passed(self):
        self.assertTrue(self.payload["all_pass"],
                        [c for c in self.payload["checks"] if not c["pass"]])

    def test_hidden_nav_author_and_control_text_absent(self):
        text = " ".join((c.get("text") or "") for c in self.cards.values())
        for marker in ("隐藏正文不该出现", "不可见文字不该出现", "整张卡隐藏不该出现",
                       "站点首页", "站点热搜", "作者昵称不该出现"):
            self.assertNotIn(marker, text)

    def test_nested_card_text_not_bleeding_and_own_counts(self):
        outer = self.cards["4900000000000103"]
        self.assertNotIn("内层卡片正文不该串入外层", outer["text"])
        self.assertEqual(outer["counts"], {"comments": 7, "likes": 8})
        self.assertNotIn("4900000000000104", self.cards)      # 内层卡不单独输出
        self.assertNotIn("4900000000000107", self.cards)      # 整张隐藏卡不输出

    def test_every_card_id_matches_its_url_path(self):
        for native_id, item in self.cards.items():
            self.assertEqual((item["url"] or "").rstrip("/").rsplit("/", 1)[-1], native_id)


# --------------------------------------------------------------------------
# 桌面证据 + 真实登录 / 真实搜索的守卫顺序（全部用 fake，不启浏览器）
# --------------------------------------------------------------------------
class FakeLedger:
    """duck-typed 平台账本：记录调用顺序，按需抛 PlatformBudgetError。"""

    def __init__(self, *, locked=False, lock_reason=None, authorized=True,
                 remaining=2, window_open=True, charge_error=None,
                 reserve_error=None, result_error=None, lock_error=None,
                 timeline=None):
        self.locked_flag, self.lock_reason = locked, lock_reason
        self.authorized, self.remaining = authorized, remaining
        self.window_open = window_open
        self.charge_error, self.reserve_error = charge_error, reserve_error
        self.result_error, self.lock_error = result_error, lock_error
        self.calls: list = []
        self.result_sources: list = []
        self.timeline = timeline if timeline is not None else []
        self.closed = False

    def _note(self, item):
        self.calls.append(item)
        self.timeline.append(item)

    def locked(self):
        return self.locked_flag, self.lock_reason

    def summary(self, batch_id=None):
        return {"batch_id": batch_id, "authorized": self.authorized,
                "remaining": self.remaining, "window_open": self.window_open,
                "used": 2 - self.remaining, "authorized_calls": 2, "seed_used": 0}

    def charge(self, batch_id, kind, *, detail="", source=""):
        self._note(("charge", kind))
        if self.charge_error:
            raise self.charge_error
        return {"batch_id": batch_id, "kind": kind}

    def reserve_records(self, batch_id, count, *, source=""):
        self._note(("reserve", count))
        if self.reserve_error:
            raise self.reserve_error
        return {"reserved": count}

    def audit(self, batch_id, kind, *, detail="", source="runtime"):
        """guard.record_result 走这里：事件名必须是 active_nav_result / search_result。"""
        self._note(("result", kind, detail))
        self.result_sources.append(source)
        if self.result_error:
            raise self.result_error

    def lock(self, reason, *, source=""):
        self._note(("lock", reason))
        if self.lock_error:
            raise self.lock_error

    def close(self):
        self.closed = True


class FakeSession:
    """duck-typed 可见窗口会话：不发网络、不启浏览器。"""

    def __init__(self, *, page=None, desktop=None, cards=None, signals=None,
                 start_error=None, timeline=None):
        self.page = page if page is not None else {
            "url": "https://s.weibo.com/weibo?q=x", "title": "微博搜索",
            "ready": "complete", "http_status": 200, "text": "页面正文",
            "text_len": 4, "visibility": "visible", "timed_out": False}
        self.desktop = desktop if desktop is not None else {
            "supported": True, "proven": True, "reason": None, "hwnd": 1234,
            "foreground_matched": True, "desktop_screenshot_bytes": 0,
            "window_title": "微博搜索 - Google Chrome", "page_title": "微博搜索",
            "window_title_matches_page": True,
            "window_rect": {"left": 0, "top": 0, "right": 800, "bottom": 600,
                            "width": 800, "height": 600}}
        self.cards = cards if cards is not None else [card()]
        self.signals = signals if signals is not None else {"host": "weibo.com"}
        self.start_error = start_error
        self.events: list = []
        self.timeline = timeline if timeline is not None else []

    def _note(self, item):
        self.events.append(item)
        self.timeline.append(item)

    def start(self):
        self._note("session.start")
        if self.start_error:
            raise self.start_error
        return {"mode": "live", "browser_pid": 42}

    def open_live(self, url):
        self._note(("session.open_live", url))
        return object()

    def open_local(self, url):
        self._note(("session.open_local", url))
        return object(), {"blocked_patterns": ["http://*"]}

    def navigate_stable(self, tab, **kwargs):
        self._note("session.navigate_stable")
        return {"requested_url": self.page["url"], "final_url": self.page["url"],
                "redirects": [], "ready_state": "complete", "timed_out": False,
                "escaped": False}

    def evidence(self, tab, screenshot=None):
        self._note("session.evidence")
        return {"geometry": {}, "network_audit": {"external_attempts": 0,
                                                  "external_completed": 0},
                "desktop_visibility_proven": False}

    def read_page(self, tab):
        self._note("session.read_page")
        return dict(self.page)

    def read_signals(self, tab, script):
        self._note("session.read_signals")
        return dict(self.signals)

    def wait_ready(self, tab, **kwargs):
        self._note("session.wait_ready")
        return dict(self.page)

    def dump_cards(self, tab):
        self._note("session.dump_cards")
        return {"cards": list(self.cards)}

    def dump_desktop_cards(self, tab):
        self._note("session.dump_desktop_cards")
        return {"cards": list(self.cards)}

    def set_title(self, tab, title):
        self._note(("session.set_title", title))
        return title

    def desktop_proof(self, *, tab=None, screenshot=None, title_hint=None, wait_s=2.0):
        self._note(("session.desktop_proof", screenshot, title_hint))
        return dict(self.desktop)

    def close(self):
        if not getattr(self, "_closed", False):   # 与真实 VisibleSession 一样幂等
            self._closed = True
            self._note("session.close")


class SessionFactory:
    """记录创建次数与构造参数；未授权时创建次数必须为 0。"""

    def __init__(self, factory):
        self.factory = factory
        self.created: list[bool] = []
        self.kwargs: list[dict] = []

    def __call__(self, profile, *, live, timeout=None, user_agent=None):
        self.created.append(bool(live))
        self.kwargs.append({"profile": profile, "live": bool(live),
                            "timeout": timeout, "user_agent": user_agent})
        return self.factory()


class FakeClock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.now += float(seconds)


def run_cli(argv):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = cli.main(argv)
    lines = [line for line in buf.getvalue().splitlines() if line.strip()]
    return code, (json.loads(lines[-1]) if lines else None)


class LiveSearchGuardTests(unittest.TestCase):
    def test_default_user_agent_is_desktop(self):
        """桌面入口 s.weibo.com 用移动 UA 会被重定向到 m.weibo.cn —— 默认必须是桌面 UA。"""
        args = cli.build_parser().parse_args(["live-search", "--keyword", "k"])
        self.assertIsNone(args.user_agent)

    def test_redirect_to_other_host_is_flagged(self):
        """请求 s.weibo.com 却落到 m.weibo.cn：exit 4 / redirected_elsewhere，不解析记录。"""
        ledger = FakeLedger()
        page = {"url": "https://m.weibo.cn/search", "title": "微博", "ready": "complete",
                "http_status": 200, "text": "", "text_len": 6, "timed_out": False}
        code, payload, _, _ = self._run(ledger, sessions=FakeSession(page=page))
        self.assertEqual(code, codes.EXIT_UNSUPPORTED)
        self.assertEqual(payload["stop"], "redirected_elsewhere")
        self.assertTrue(payload["requested_url"].startswith("https://s.weibo.com/"))
        self.assertTrue(str(payload["final_url"]).startswith("https://m.weibo.cn/"))
        self.assertEqual(payload["records"], [])
    """live-search：守卫全在启动浏览器之前；风险判定在记录构建之前。"""

    def _run(self, ledger, *, sessions=None, argv_extra=(), clock=None):
        session_obj = sessions or FakeSession()
        factory = SessionFactory(lambda: session_obj)
        clock = clock or FakeClock()
        with mock.patch.object(cli, "_open_ledger", return_value=ledger), \
                mock.patch.object(cli, "_new_session", side_effect=factory), \
                mock.patch.object(cli, "_monotonic", side_effect=clock), \
                mock.patch.object(cli, "_sleep", side_effect=clock.sleep):
            code, payload = run_cli(["live-search", "--keyword", "学习计划模板",
                                     "--batch-id", "weibo-rpa-1", "--allow-live",
                                     *argv_extra])
        return code, payload, factory, session_obj

    def test_locked_platform_never_launches_browser(self):
        ledger = FakeLedger(locked=True, lock_reason="text:安全验证")
        code, payload, factory, _ = self._run(ledger)
        self.assertEqual(code, codes.EXIT_BUDGET)
        self.assertEqual(payload["stop"], "blocked:platform_locked")
        self.assertEqual(factory.created, [])
        self.assertEqual([c for c in ledger.calls if c[0] == "charge"], [])

    def test_unauthorized_batch_never_launches_browser(self):
        ledger = FakeLedger(authorized=False)
        code, payload, factory, _ = self._run(ledger)
        self.assertEqual(code, codes.EXIT_BUDGET)
        self.assertEqual(payload["stop"], "blocked:no_authorized_batch")
        self.assertEqual(factory.created, [])

    def test_batch_id_required_never_launches_browser(self):
        ledger = FakeLedger()
        with mock.patch.object(cli, "_open_ledger", return_value=ledger), \
                mock.patch.object(cli, "_new_session",
                                  side_effect=AssertionError("no browser")):
            code, payload = run_cli(["live-search", "--keyword", "kw", "--allow-live"])
        self.assertEqual(code, codes.EXIT_BUDGET)
        self.assertEqual(payload["stop"], "blocked:batch_id_required")

    def test_exhausted_remaining_never_launches_browser(self):
        ledger = FakeLedger(remaining=0)
        code, payload, factory, _ = self._run(ledger)
        self.assertEqual(code, codes.EXIT_BUDGET)
        self.assertEqual(payload["stop"], "blocked:calls_exhausted")
        self.assertEqual(factory.created, [])

    def test_closed_window_never_launches_browser(self):
        ledger = FakeLedger(window_open=False)
        code, payload, factory, _ = self._run(ledger)
        self.assertEqual(code, codes.EXIT_BUDGET)
        self.assertEqual(payload["stop"], "blocked:batch_window_closed")
        self.assertEqual(factory.created, [])

    def test_charge_refusal_never_launches_browser(self):
        ledger = FakeLedger(charge_error=pb.PlatformBudgetError("calls_exhausted", "2/2"))
        code, payload, factory, _ = self._run(ledger)
        self.assertEqual(code, codes.EXIT_BUDGET)
        self.assertEqual(payload["stop"], "blocked:platform:calls_exhausted")
        self.assertEqual(factory.created, [])

    def test_risk_text_locks_and_builds_no_records(self):
        ledger = FakeLedger()
        page = {"url": "https://s.weibo.com/weibo?q=x", "title": "微博", "ready": "complete",
                "http_status": 200, "text": "访问过于频繁，请稍后再试", "text_len": 12,
                "visibility": "visible", "timed_out": False}
        code, payload, _, sess = self._run(ledger, sessions=FakeSession(page=page))
        self.assertEqual(code, codes.EXIT_RISK)
        self.assertEqual(payload["stop"], "risk:text:访问过于频繁")
        self.assertEqual([c for c in ledger.calls if c[0] == "lock"],
                         [("lock", "text:访问过于频繁")])
        self.assertNotIn("session.dump_cards", sess.events)      # 风险先于记录构建
        self.assertEqual(payload["records"], [])
        self.assertEqual([c for c in ledger.calls if c[0] == "result"][-1],
                         ("result", "search_result", "failed"))

    def test_http_403_wins_over_extractable_cards(self):
        ledger = FakeLedger()
        page = {"url": "https://s.weibo.com/weibo?q=x", "title": "微博", "ready": "complete",
                "http_status": 403, "text": "普通页面", "text_len": 4,
                "visibility": "visible", "timed_out": False}
        code, payload, _, sess = self._run(ledger, sessions=FakeSession(page=page))
        self.assertEqual(code, codes.EXIT_RISK)
        self.assertEqual(payload["stop"], "risk:http_403")
        self.assertNotIn("session.dump_cards", sess.events)
        self.assertEqual(payload["records"], [])

    def test_happy_path_order_and_records(self):
        ledger = FakeLedger()
        timeline: list = []
        ledger.timeline = timeline
        sess = FakeSession(timeline=timeline)
        code, payload, factory, _ = self._run(ledger, sessions=sess)
        self.assertEqual(code, codes.EXIT_OK)
        self.assertEqual(factory.created, [True])
        self.assertEqual(payload["count"], 1)
        self.assertEqual(payload["records"][0]["native_id"], "4900000000000001")
        self.assertTrue(payload["desktop_visibility_proven"])
        self.assertTrue(payload["result_persisted"])
        self.assertEqual(payload["result_kind"], "search")
        self.assertEqual(payload["result_source"], "rpa.search")
        self.assertEqual(ledger.result_sources, ["rpa.search"])
        # 固定顺序：预扣 → 启动 → 导航 → 风险(读页面) → 提取 → 预留 → 结果登记
        self.assertEqual(timeline[0], ("charge", "search"))
        self.assertLess(timeline.index(("charge", "search")),
                        timeline.index("session.start"))
        self.assertLess(timeline.index("session.start"),
                        timeline.index("session.wait_ready"))
        self.assertIn(("session.desktop_proof", None, None), timeline)
        self.assertIn("session.dump_desktop_cards", timeline)
        self.assertLess(timeline.index(("session.desktop_proof", None, None)),
                        timeline.index("session.dump_desktop_cards"))
        self.assertLess(timeline.index(("reserve", 1)),
                        timeline.index(("result", "search_result", "success")))
        self.assertEqual(timeline[-1], ("result", "search_result", "success"))
        self.assertIn("session.close", timeline)

    def test_lock_write_failure_is_nonzero(self):
        ledger = FakeLedger(lock_error=pb.PlatformBudgetError("db_locked"))
        page = {"url": "https://s.weibo.com/weibo?q=x", "title": "微博", "ready": "complete",
                "http_status": 200, "text": "请完成安全验证", "text_len": 7,
                "visibility": "visible", "timed_out": False}
        code, payload, _, _ = self._run(ledger, sessions=FakeSession(page=page))
        self.assertEqual(code, codes.EXIT_BUDGET)
        self.assertEqual(payload["stop"], "lock_write_failed:db_locked")
        self.assertNotEqual(payload["exit"], codes.EXIT_OK)

    def test_result_write_failure_is_nonzero(self):
        ledger = FakeLedger(result_error=pb.PlatformBudgetError("db_locked"))
        code, payload, _, _ = self._run(ledger)
        self.assertEqual(code, codes.EXIT_BUDGET)
        self.assertEqual(payload["stop"], "result_write_failed")
        self.assertFalse(payload["result_persisted"])
        self.assertFalse(payload["ok"])

    def test_result_write_failure_drops_records_and_export(self):
        """登记失败：records 必须为空，且不得留下导出文件。"""
        ledger = FakeLedger(result_error=pb.PlatformBudgetError("db_locked"))
        with tempfile.TemporaryDirectory() as tmp:
            out = pathlib.Path(tmp) / "records.jsonl"
            code, payload, _, _ = self._run(ledger, argv_extra=("--out", str(out)))
            self.assertEqual(code, codes.EXIT_BUDGET)
            self.assertEqual(payload["stop"], "result_write_failed")
            self.assertFalse(payload["result_persisted"])
            self.assertEqual(payload["records"], [])
            self.assertEqual(payload["count"], 0)
            self.assertIsNone(payload["output"])
            self.assertFalse(out.exists())

    def test_export_failure_is_nonzero(self):
        """导出异常：用已有目录当输出路径 → EXIT_EXPORT（9），不是 0。"""
        ledger = FakeLedger()
        with tempfile.TemporaryDirectory() as tmp:
            code, payload, _, _ = self._run(ledger, argv_extra=("--out", tmp))
            self.assertEqual(code, codes.EXIT_EXPORT)
            self.assertTrue(str(payload["stop"]).startswith("export_failed:"))
            self.assertIsNone(payload["output"])
            self.assertIsNotNone(payload["export_error"])

    def test_readiness_timeout_is_nonzero_and_skips_records(self):
        """页面从未 complete：非零、不解析、不输出记录。"""
        ledger = FakeLedger()
        page = {"url": "https://s.weibo.com/weibo?q=x", "title": "微博", "ready": "loading",
                "http_status": 200, "text": "加载中", "text_len": 3,
                "visibility": "visible", "timed_out": True}
        sess = FakeSession(page=page)
        code, payload, _, _ = self._run(ledger, sessions=sess)
        self.assertEqual(code, codes.EXIT_TRANSPORT)
        self.assertEqual(payload["stop"], "readiness_timeout")
        self.assertNotIn("session.dump_cards", sess.events)
        self.assertEqual(payload["records"], [])
        self.assertEqual([c for c in ledger.calls if c[0] == "result"][-1],
                         ("result", "search_result", "unknown"))

    def test_live_search_passes_timeout_and_user_agent(self):
        ledger = FakeLedger()
        code, _, factory, _ = self._run(
            ledger, argv_extra=("--timeout", "45", "--user-agent", "UA/9"))
        self.assertEqual(code, codes.EXIT_OK)
        self.assertEqual(factory.kwargs[0]["timeout"], 45.0)
        self.assertEqual(factory.kwargs[0]["user_agent"], "UA/9")
        self.assertTrue(factory.kwargs[0]["live"])

    def test_reserve_refusal_emits_no_records(self):
        ledger = FakeLedger(reserve_error=pb.PlatformBudgetError("records_cap_exceeded", "5+1>5"))
        code, payload, _, _ = self._run(ledger)
        self.assertEqual(code, codes.EXIT_BUDGET)
        self.assertEqual(payload["stop"], "blocked:platform:records_cap_exceeded")
        self.assertEqual(payload["records"], [])

    def test_session_start_failure_settles_and_is_nonzero(self):
        ledger = FakeLedger()
        sess = FakeSession(start_error=session.SessionUnavailable("browser_unavailable"))
        code, payload, _, _ = self._run(ledger, sessions=sess)
        self.assertEqual(code, codes.EXIT_TRANSPORT)
        self.assertEqual(payload["stop"], "browser_unavailable")
        self.assertTrue(payload["browser_started"] is False)
        self.assertEqual([c for c in ledger.calls if c[0] == "result"][-1],
                         ("result", "search_result", "unknown"))
        self.assertEqual(ledger.result_sources[-1], "rpa.search")


class LoginGuardTests(unittest.TestCase):
    """login：precheck → 预扣 active_nav → 启动浏览器；风险即锁；登录态只报页面证据。"""

    def _run(self, ledger, *, sessions=None, clock=None, extra=()):
        session_obj = sessions or FakeSession()
        factory = SessionFactory(lambda: session_obj)
        clock = clock or FakeClock()
        with mock.patch.object(cli, "_open_ledger", return_value=ledger), \
                mock.patch.object(cli, "_new_session", side_effect=factory), \
                mock.patch.object(cli, "_monotonic", side_effect=clock), \
                mock.patch.object(cli, "_sleep", side_effect=clock.sleep), \
                mock.patch.object(cli, "_user_confirmed", return_value=False):
            code, payload = run_cli(["login", "--batch-id", "weibo-rpa-1", *extra])
        return code, payload, factory, session_obj

    def test_unauthorized_never_launches_browser(self):
        ledger = FakeLedger(authorized=False)
        code, payload, factory, _ = self._run(ledger)
        self.assertEqual(code, codes.EXIT_BUDGET)
        self.assertEqual(payload["stop"], "blocked:no_authorized_batch")
        self.assertEqual(factory.created, [])
        self.assertFalse(payload["browser_started"])

    def test_locked_never_launches_browser(self):
        ledger = FakeLedger(locked=True, lock_reason="text:安全验证")
        code, payload, factory, _ = self._run(ledger)
        self.assertEqual(code, codes.EXIT_BUDGET)
        self.assertEqual(payload["stop"], "blocked:platform_locked")
        self.assertEqual(factory.created, [])

    def test_charge_happens_before_browser_and_refusal_blocks(self):
        ledger = FakeLedger(charge_error=pb.PlatformBudgetError("calls_exhausted", "3/3"))
        code, payload, factory, _ = self._run(ledger)
        self.assertEqual(code, codes.EXIT_BUDGET)
        self.assertEqual(payload["stop"], "blocked:platform:calls_exhausted")
        self.assertEqual(factory.created, [])
        self.assertEqual([c for c in ledger.calls if c[0] == "charge"],
                         [("charge", "active_nav")])

    def test_charge_happens_before_browser_start(self):
        """预扣必须早于启动浏览器：先开窗再检查就是绕过守卫。"""
        ledger = FakeLedger()
        timeline: list = []
        ledger.timeline = timeline
        sess = FakeSession(timeline=timeline,
                           signals={"host": "weibo.com", "path": "/", "hasLogout": True})
        code, _, _, _ = self._run(ledger, sessions=sess)
        self.assertEqual(code, codes.EXIT_OK)
        self.assertIn(("charge", "active_nav"), timeline)
        self.assertLess(timeline.index(("charge", "active_nav")),
                        timeline.index("session.start"))

    def test_signed_in_reports_page_evidence_and_exit_zero(self):
        ledger = FakeLedger()
        sess = FakeSession(signals={"host": "weibo.com", "path": "/",
                                    "hasLogout": True})
        code, payload, _, _ = self._run(ledger, sessions=sess)
        self.assertEqual(code, codes.EXIT_OK)
        self.assertEqual(payload["status"], "signed_in")
        self.assertEqual(payload["login_state"]["verdict"], "ok")
        self.assertEqual(payload["login_state"]["evidence"], "page:logout_control")
        self.assertFalse(payload["cookie_values_read"])
        self.assertEqual(payload["result_kind"], "active_nav")
        self.assertEqual(payload["result_source"], "rpa.login")
        self.assertEqual([c for c in ledger.calls if c[0] == "result"][-1],
                         ("result", "active_nav_result", "success"))
        self.assertEqual(ledger.result_sources, ["rpa.login"])
        # 登录页禁止自动截图
        screenshots = [e[1] for e in sess.events
                       if isinstance(e, tuple) and e[0] == "session.desktop_proof"]
        self.assertEqual(screenshots, [None])

    def test_login_start_failure_still_settles_active_nav(self):
        """启动失败也必须结算：已预扣的 active_nav 不能无账。"""
        ledger = FakeLedger()
        sess = FakeSession(start_error=session.SessionUnavailable("browser_unavailable"))
        code, payload, _, _ = self._run(ledger, sessions=sess)
        self.assertEqual(code, codes.EXIT_TRANSPORT)
        self.assertEqual(payload["stop"], "browser_unavailable")
        self.assertEqual([c for c in ledger.calls if c[0] == "result"][-1],
                         ("result", "active_nav_result", "unknown"))
        self.assertEqual(ledger.result_sources, ["rpa.login"])

    def test_no_signed_in_signal_is_unknown_not_ok(self):
        ledger = FakeLedger()
        sess = FakeSession(signals={"host": "weibo.com", "path": "/", "hasLogout": False},
                           page={"url": "https://passport.weibo.com/sso/signin",
                                 "title": "登录", "ready": "complete", "http_status": 200,
                                 "text": "登录", "text_len": 2, "visibility": "visible",
                                 "timed_out": False})
        code, payload, _, _ = self._run(ledger, sessions=sess, extra=("--timeout", "1"))
        self.assertEqual(code, codes.EXIT_LOGIN_TIMEOUT)
        self.assertEqual(payload["status"], "timeout")
        self.assertEqual(payload["login_state"]["verdict"], "unknown")
        self.assertIsNone(payload["login_state"]["evidence"])

    def test_risk_page_locks_and_exits_risk(self):
        ledger = FakeLedger()
        sess = FakeSession(page={"url": "https://passport.weibo.com/sso/signin",
                                 "title": "登录", "ready": "complete", "http_status": 200,
                                 "text": "访问过于频繁，请稍后再试", "text_len": 12,
                                 "visibility": "visible", "timed_out": False})
        code, payload, _, _ = self._run(ledger, sessions=sess)
        self.assertEqual(code, codes.EXIT_RISK)
        self.assertEqual(payload["status"], "risk")
        self.assertEqual([c for c in ledger.calls if c[0] == "lock"],
                         [("lock", "text:访问过于频繁")])

    def test_result_write_failure_on_login_is_nonzero(self):
        ledger = FakeLedger(result_error=pb.PlatformBudgetError("db_locked"))
        sess = FakeSession(signals={"host": "weibo.com", "path": "/", "hasLogout": True})
        code, payload, _, _ = self._run(ledger, sessions=sess)
        self.assertEqual(code, codes.EXIT_BUDGET)
        self.assertEqual(payload["stop"], "result_write_failed")
        self.assertFalse(payload["ok"])


class WindowDesktopProofTests(unittest.TestCase):
    """window --desktop-proof：只对本地 fixture；失败如实 false + reason。"""

    FIXTURE = REPO / "docs" / "validation" / "v10" / "browser-rpa" / "fixtures" / \
        "card-cases.html"

    def _run(self, session_obj, *, extra=()):
        factory = SessionFactory(lambda: session_obj)
        info = {"usable": True, "nodriver": True, "chrome": "chrome.exe",
                "nodriver_version": "test"}
        with mock.patch.object(cli.browser_mod, "available", return_value=info), \
                mock.patch.object(cli, "_new_session", side_effect=factory):
            return run_cli(["window", "--profile", "tmp-profile", "--no-wait",
                            "--url", self.FIXTURE.as_uri(), *extra])

    def test_http_url_is_refused_before_browser_starts(self):
        with mock.patch.object(cli, "_new_session",
                               side_effect=AssertionError("no browser")):
            code, payload = run_cli(["window", "--profile", "p", "--desktop-proof",
                                     "--url", "https://m.weibo.cn/"])
        self.assertEqual(code, codes.EXIT_BUDGET)
        self.assertEqual(payload["stop"], "blocked:non_local_url")

    def test_proven_true_keeps_exit_zero(self):
        sess = FakeSession()
        code, payload = self._run(sess, extra=("--desktop-proof",))
        self.assertEqual(code, codes.EXIT_OK)
        self.assertTrue(payload["desktop_visibility_proven"])
        self.assertTrue(payload["desktop"]["proven"])
        screenshot = [e[1] for e in sess.events
                      if isinstance(e, tuple) and e[0] == "session.desktop_proof"][0]
        self.assertIsNotNone(screenshot)                     # 本地 fixture 必须抓图

    def test_proof_failure_reports_false_with_reason(self):
        failing = {"supported": True, "proven": False, "reason": "foreground_not_matched",
                   "hwnd": 7, "foreground_matched": False, "desktop_screenshot_bytes": 0,
                   "window_rect": {"left": 0, "top": 0, "right": 0, "bottom": 0,
                                   "width": 0, "height": 0}}
        sess = FakeSession(desktop=failing)
        code, payload = self._run(sess, extra=("--desktop-proof",))
        self.assertEqual(code, codes.EXIT_TRANSPORT)
        self.assertFalse(payload["desktop_visibility_proven"])
        self.assertEqual(payload["stop"],
                         "desktop_proof_failed:foreground_not_matched")
        self.assertEqual(payload["desktop"]["reason"], "foreground_not_matched")

    def test_without_flag_no_desktop_evidence_is_claimed(self):
        sess = FakeSession()
        code, payload = self._run(sess)
        self.assertEqual(code, codes.EXIT_OK)
        self.assertFalse(payload["desktop_visibility_proven"])
        self.assertIsNone(payload["desktop"])


class DesktopEvidenceTests(unittest.TestCase):
    """desktop 模块的纯函数 + 失败如实上报（不依赖真实桌面）。"""

    def test_png_bytes_has_valid_signature_and_ihdr(self):
        payload = desktop.png_bytes(2, 1, [bytes([255, 0, 0, 0, 255, 0])])
        self.assertTrue(payload.startswith(b"\x89PNG\r\n\x1a\n"))
        self.assertIn(b"IHDR", payload)
        self.assertIn(b"IEND", payload)
        width = int.from_bytes(payload[16:20], "big")
        height = int.from_bytes(payload[20:24], "big")
        self.assertEqual((width, height), (2, 1))

    def test_png_bytes_roundtrip_through_stdlib_zlib(self):
        import struct
        import zlib
        payload = desktop.png_bytes(1, 1, [bytes([1, 2, 3])])
        start = payload.index(b"IDAT") - 4
        length = struct.unpack(">I", payload[start:start + 4])[0]
        data = payload[start + 8:start + 8 + length]
        self.assertEqual(zlib.decompress(data), b"\x00\x01\x02\x03")

    def test_prove_without_window_reports_false_and_reason(self):
        out = desktop.prove(pid=999999999, title_hint="NO-SUCH-NONCE",
                            screenshot=None, wait_s=0)
        self.assertFalse(out["proven"])
        self.assertIsNotNone(out["reason"])
        self.assertFalse(out["foreground_matched"])
        self.assertEqual(out["desktop_screenshot_bytes"], 0)
        self.assertIn(out["reason"], ("window_not_found", "not_windows",
                                      "winapi_unavailable:not_windows"))

    def test_prove_never_raises_and_never_writes_screenshot_without_window(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = pathlib.Path(tmp) / "shot.png"
            out = desktop.prove(pid=999999999, title_hint=None,
                                screenshot=target, wait_s=0)
            self.assertFalse(out["proven"])
            self.assertFalse(target.exists())

    def test_prove_off_windows_shape(self):
        """跨平台契约：非 Windows 只能是 supported=False + reason，不能抛。"""
        with mock.patch.object(desktop, "IS_WINDOWS", False), \
                mock.patch.object(desktop, "_API", None):
            out = desktop.prove(pid=1, screenshot=None, wait_s=0)
        self.assertFalse(out["supported"])
        self.assertFalse(out["proven"])
        self.assertTrue(str(out["reason"]).startswith("winapi_unavailable"))


class TitleConsistencyTests(unittest.TestCase):
    """窗口标题 vs 页面标题：这是"窗口显示目标页"的可判读前提。"""

    def test_page_title_inside_window_title_is_true(self):
        self.assertTrue(session.title_consistency("登录 - 微博 - Google Chrome", "登录 - 微博"))
        self.assertTrue(session.title_consistency(" 卡片A  - Google Chrome ", "卡片A"))

    def test_blank_new_tab_is_false(self):
        self.assertFalse(session.title_consistency("新标签页 - Google Chrome", "登录 - 微博"))

    def test_missing_titles_are_unknown_not_true(self):
        self.assertIsNone(session.title_consistency(None, "登录 - 微博"))
        self.assertIsNone(session.title_consistency("登录 - 微博 - Google Chrome", None))
        self.assertIsNone(session.title_consistency("", ""))


class _AsyncActivateTab:
    def __init__(self):
        self.calls = 0

    async def activate(self):
        self.calls += 1
        return True


class _NoActivateTab:
    pass


class ActivationTests(unittest.TestCase):
    def test_tab_activate_is_used_first(self):
        tab = _AsyncActivateTab()
        out = session.VisibleSession("unused").activate(tab)
        self.assertTrue(out["activated"])
        self.assertEqual(out["method"], "tab.activate")
        self.assertEqual(tab.calls, 1)

    def test_cdp_fallback_failure_is_recorded_not_raised(self):
        out = session.VisibleSession("unused").activate(_NoActivateTab())
        self.assertFalse(out["activated"])
        self.assertTrue(out["error"])


class _FakePageSession(session.VisibleSession):
    def __init__(self, page_title):
        super().__init__("unused")
        self._page_title = page_title
        self.last_activation = {"activated": True, "method": "tab.activate", "error": None}

    def read_page(self, tab):
        return {"title": self._page_title, "url": "https://passport.weibo.com/sso/signin"}


class DesktopProofFieldsTests(unittest.TestCase):
    def test_proof_carries_page_title_and_match_flag(self):
        from unittest import mock

        sess = _FakePageSession("登录 - 微博")
        with mock.patch("tools.selection.rpa.desktop.prove",
                        return_value={"proven": True, "window_title": "登录 - 微博 - Google Chrome"}):
            proof = sess.desktop_proof(tab=object())
        self.assertEqual(proof["page_title"], "登录 - 微博")
        self.assertTrue(proof["window_title_matches_page"])
        self.assertEqual(proof["activation"]["method"], "tab.activate")

    def test_other_tab_proof_is_false(self):
        from unittest import mock

        sess = _FakePageSession("登录 - 微博")
        with mock.patch("tools.selection.rpa.desktop.prove",
                        return_value={"proven": True, "window_title": "新标签页 - Google Chrome"}):
            proof = sess.desktop_proof(tab=object())
        self.assertFalse(proof["window_title_matches_page"])


class VisibilityGateTests(unittest.TestCase):
    def test_gate_blocks_when_titles_do_not_match(self):
        self.assertEqual(cli._visibility_gate({"window_title_matches_page": False}),
                         "window_showing_other_tab")
        self.assertEqual(cli._visibility_gate({"window_title_matches_page": None}),
                         "window_showing_other_tab")
        self.assertEqual(cli._visibility_gate(None), "window_showing_other_tab")

    def test_gate_passes_only_on_true(self):
        self.assertIsNone(cli._visibility_gate({"window_title_matches_page": True}))

    def test_visibility_exit_code_is_nonzero_and_distinct(self):
        self.assertEqual(cli.EXIT_VISIBILITY, 12)
        self.assertNotIn(cli.EXIT_VISIBILITY, (0, codes.EXIT_OK))


class TopmostAndKeepaliveTests(unittest.TestCase):
    """置顶 + 等待期间只在前台丢失时夺回（不每轮抢焦点）。"""

    def test_topmost_flag_reads_exstyle_bit(self):
        from tools.selection.rpa import desktop as desktop_mod

        self.assertTrue(desktop_mod.topmost_flag(0x00000008))
        self.assertTrue(desktop_mod.topmost_flag(0x00000008 | 0x00000100))
        self.assertFalse(desktop_mod.topmost_flag(0))
        self.assertFalse(desktop_mod.topmost_flag(None))

    def test_start_sets_topmost_and_reports_it(self):
        from unittest import mock
        from tools.selection.rpa import desktop as desktop_mod

        ka = desktop_mod.Keepalive(1234)
        with mock.patch.object(desktop_mod, "set_topmost",
                               return_value={"topmost_set": True}) as patched:
            state = ka.start()
        patched.assert_called_once_with(1234, on=True)
        self.assertTrue(state["topmost_set"])

    def test_tick_does_not_steal_focus_when_already_foreground(self):
        from unittest import mock
        from tools.selection.rpa import desktop as desktop_mod

        ka = desktop_mod.Keepalive(1234, interval=0)
        with mock.patch.object(desktop_mod, "foreground_hwnd", return_value=1234), \
                mock.patch.object(desktop_mod, "force_foreground") as forced, \
                mock.patch.object(desktop_mod, "reassert",
                                  return_value={"was_foreground": True,
                                                "reasserted": False, "error": None}):
            ka.tick(force=True)
        forced.assert_not_called()
        self.assertEqual(ka.reassert_count, 0)
        self.assertEqual(ka.reassert_failures, 0)

    def test_tick_reasserts_when_foreground_lost_and_counts(self):
        from unittest import mock
        from tools.selection.rpa import desktop as desktop_mod

        ka = desktop_mod.Keepalive(1234, interval=0)
        with mock.patch.object(desktop_mod, "reassert",
                               return_value={"was_foreground": False,
                                             "reasserted": True, "error": None}):
            ka.tick(force=True)
        self.assertEqual(ka.reassert_count, 1)
        self.assertEqual(ka.reassert_failures, 0)

    def test_failed_reassert_is_counted_not_silent(self):
        from unittest import mock
        from tools.selection.rpa import desktop as desktop_mod

        ka = desktop_mod.Keepalive(1234, interval=0)
        with mock.patch.object(desktop_mod, "reassert",
                               return_value={"was_foreground": False, "reasserted": False,
                                             "error": "foreground_not_reclaimed"}):
            ka.tick(force=True)
        self.assertEqual(ka.reassert_failures, 1)
        self.assertEqual(ka.last_error, "foreground_not_reclaimed")

    def test_interval_throttles_reassert(self):
        from unittest import mock
        from tools.selection.rpa import desktop as desktop_mod

        ka = desktop_mod.Keepalive(1234, interval=100)
        with mock.patch.object(desktop_mod, "reassert",
                               return_value={"was_foreground": False, "reasserted": True,
                                             "error": None}) as patched:
            ka.tick(force=True)
            ka.tick()                       # 节流窗口内：不再夺回
        self.assertEqual(patched.call_count, 1)
        self.assertEqual(ka.ticks, 1)

    def test_finish_reports_still_foreground_and_clears_topmost(self):
        from unittest import mock
        from tools.selection.rpa import desktop as desktop_mod

        ka = desktop_mod.Keepalive(1234)
        ka.topmost_state = {"topmost_set": True}
        with mock.patch.object(desktop_mod, "foreground_hwnd", return_value=1234), \
                mock.patch.object(desktop_mod, "set_topmost",
                                  return_value={"topmost_set": False}) as patched:
            summary = ka.finish()
        self.assertTrue(summary["still_foreground_at_end"])
        self.assertTrue(summary["topmost_cleared"])
        patched.assert_called_once_with(1234, on=False)

    def test_wait_ready_ticks_keepalive(self):
        class _ReadySession(session.VisibleSession):
            def __init__(self):
                super().__init__("unused")

            def read_page(self, tab):
                return {"ready": "complete", "title": "t"}

        class _KA:
            def __init__(self):
                self.ticks = 0

            def tick(self):
                self.ticks += 1

        ka = _KA()
        out = _ReadySession().wait_ready(object(), attempts=1, interval=0, keepalive=ka)
        self.assertFalse(out["timed_out"])
        self.assertEqual(ka.ticks, 1)

    def test_login_payload_carries_keepalive_summary(self):
        """login 结束必须带 keepalive（reassert_count/still_foreground_at_end）。"""
        import inspect

        source = inspect.getsource(cli.cmd_login)
        self.assertIn("Keepalive", source)
        self.assertIn("keepalive", source)
        self.assertIn("_wait_login", source)


class WindowTitleSettleTests(unittest.TestCase):
    """页面标题先变、OS 窗口标题后变：闸门不能立刻判成"显示错页"（竞态回归）。"""

    def test_already_matched_does_not_wait(self):
        """a) 已匹配：不调用等待，gate 直接放行。"""
        from unittest import mock
        from tools.selection.rpa import desktop as desktop_mod

        desktop = {"window_title": "登录 - 微博 - Google Chrome",
                   "page_title": "登录 - 微博", "window_title_matches_page": True}
        with mock.patch.object(desktop_mod, "wait_title_match") as waited:
            out = cli._settle_window_title(desktop)
        waited.assert_not_called()
        self.assertTrue(out["window_title_matches_page"])
        self.assertIsNone(cli._visibility_gate(out))

    def test_stale_then_match_waits_and_passes(self):
        """b) 窗口标题先是旧值、若干轮后追上：wait 被调用，gate 放行。"""
        from unittest import mock
        from tools.selection.rpa import desktop as desktop_mod

        desktop = {"hwnd": 134016, "window_title": "新标签页 - Google Chrome",
                   "page_title": "登录 - 微博", "window_title_matches_page": False}
        with mock.patch.object(
                desktop_mod, "wait_title_match",
                return_value={"window_title": "登录 - 微博 - Google Chrome",
                              "matched": True, "waited_ms": 220, "polls": 2,
                              "hwnd": 134016}) as waited:
            out = cli._settle_window_title(desktop)
        waited.assert_called_once()
        self.assertEqual(waited.call_args.args[0], 134016)
        self.assertEqual(waited.call_args.args[1], "登录 - 微博")
        self.assertTrue(out["window_title_matches_page"])
        self.assertEqual(out["title_wait"]["waited_ms"], 220)
        self.assertIsNone(cli._visibility_gate(out))

    def test_never_match_is_blocked(self):
        """c) 始终不匹配：gate 仍返回 window_showing_other_tab。"""
        from unittest import mock
        from tools.selection.rpa import desktop as desktop_mod

        desktop = {"hwnd": 1, "window_title": "新标签页 - Google Chrome",
                   "page_title": "登录 - 微博", "window_title_matches_page": False}
        with mock.patch.object(
                desktop_mod, "wait_title_match",
                return_value={"window_title": "新标签页 - Google Chrome",
                              "matched": False, "waited_ms": 3000, "polls": 15,
                              "hwnd": 1}):
            out = cli._settle_window_title(desktop)
        self.assertFalse(out["window_title_matches_page"])
        self.assertEqual(cli._visibility_gate(out), "window_showing_other_tab")

    def test_title_contains_pure_function(self):
        from tools.selection.rpa import desktop as desktop_mod

        self.assertTrue(desktop_mod.title_contains(
            "登录 - 微博 - Google Chrome", "登录 - 微博"))
        self.assertFalse(desktop_mod.title_contains(
            "新标签页 - Google Chrome", "登录 - 微博"))
        self.assertIsNone(desktop_mod.title_contains("", "登录 - 微博"))


class SearchUrlTests(unittest.TestCase):
    """入口默认桌面版（服务端直出卡片），移动版保留为可选。"""

    def test_default_is_desktop_s_weibo(self):
        url = weibo_mod.search_url("学习计划模板")
        self.assertTrue(url.startswith("https://s.weibo.com/weibo?q="))
        self.assertIn("typeall=1", url)
        self.assertIn("suball=1", url)
        self.assertIn("%E5%AD%A6%E4%B9%A0%E8%AE%A1%E5%88%92%E6%A8%A1%E6%9D%BF", url)

    def test_mobile_entry_is_kept(self):
        url = weibo_mod.search_url("学习计划模板", surface="mobile")
        self.assertTrue(url.startswith("https://m.weibo.cn/search?containerid="))


PROBE_ALL_HIT = """<html><head><title>学习计划模板 - 微博搜索</title></head><body>
<div class="card-wrap">
  <div class="card">
    <a class="name" href="https://s.weibo.com/u/1234">作者A</a>
    <p class="txt">这是正文摘要，不会被 probe 输出。</p>
    <div class="from">3小时前 来自 iPhone</div>
    <div class="card-act"><a href="https://s.weibo.com/status/4900000000000001"
        data-id="4900000000000001">详情</a></div>
    <div class="card-comment">评论 3</div>
    <img class="avator" src="x.jpg">
  </div>
</div>
</body></html>"""

PROBE_PARTIAL = """<html><body>
<div class="card"><a href="/status/4900000000000002">只有卡片和一个链接</a></div>
</body></html>"""

PROBE_ZERO = "<html><body><div class='nothing'>没有结果卡片</div></body></html>"

PROBE_CAPTCHA = """<html><body><div class="card">安全验证</div>
<a href="/status/4900000000000003">x</a></body></html>"""


class ProbeSummaryTests(unittest.TestCase):
    """probe 只统计结构，不保留正文；四类 fixture 双向覆盖。"""

    def test_all_selectors_hit(self):
        from tools.selection.rpa import probe as probe_mod

        summary = probe_mod.summarize(PROBE_ALL_HIT, url="https://s.weibo.com/weibo?q=x",
                                      http_status=200, ready="complete")
        counts = summary["counts"]
        for key in ("card_wrap", "card", "p_txt", "a_name", "div_from", "card_act",
                    "status_links", "s_weibo_links", "img_avator", "card_comment"):
            self.assertGreaterEqual(counts[key], 1, key)
        self.assertEqual(summary["status_ids"][0]["href_id"], "4900000000000001")
        self.assertTrue(summary["status_ids"][0]["consistent"])
        self.assertEqual(probe_mod.verdict(summary), (codes.EXIT_OK, None))
        self.assertNotIn("正文摘要", json.dumps(summary, ensure_ascii=False))

    def test_partial_hits_still_count(self):
        from tools.selection.rpa import probe as probe_mod

        summary = probe_mod.summarize(PROBE_PARTIAL, url="https://s.weibo.com/weibo?q=x")
        self.assertEqual(summary["counts"]["card"], 1)
        self.assertEqual(summary["counts"]["status_links"], 1)
        self.assertEqual(summary["counts"]["p_txt"], 0)
        self.assertEqual(probe_mod.verdict(summary)[0], codes.EXIT_OK)

    def test_zero_hits_is_nonzero(self):
        from tools.selection.rpa import probe as probe_mod

        summary = probe_mod.summarize(PROBE_ZERO, url="https://s.weibo.com/weibo?q=x")
        self.assertEqual(summary["cards_total"], 0)
        self.assertEqual(probe_mod.verdict(summary),
                         (codes.EXIT_UNSUPPORTED, "no_cards"))

    def test_captcha_marker_wins_over_cards(self):
        from tools.selection.rpa import probe as probe_mod

        summary = probe_mod.summarize(PROBE_CAPTCHA, url="https://s.weibo.com/weibo?q=x")
        self.assertTrue(summary["wall"]["markers"])
        code, stop = probe_mod.verdict(summary)
        self.assertEqual(code, codes.EXIT_RISK)
        self.assertTrue(str(stop).startswith("risk:text:"))

    def test_data_id_mismatch_is_reported(self):
        from tools.selection.rpa import probe as probe_mod

        html = ('<div class="card"><a href="https://s.weibo.com/status/4900000000000009"'
                ' data-id="4900000000000008">x</a></div>')
        summary = probe_mod.summarize(html, url="https://s.weibo.com/weibo?q=x")
        self.assertFalse(summary["status_ids"][0]["consistent"])


class ProbeCliGuardTests(unittest.TestCase):
    def test_probe_without_batch_is_blocked_before_browser(self):
        from tools.selection.rpa import guard as guard_mod

        class _Ledger:
            def locked(self):
                return False, None

            def close(self):
                pass

        with mock.patch.object(cli, "_open_ledger", return_value=_Ledger()):
            code = cli.main(["probe", "--url", "https://s.weibo.com/weibo?q=x"])
        self.assertEqual(code, codes.EXIT_BUDGET)
        self.assertEqual(guard_mod.GuardBlocked("batch_id_required").stop,
                         "batch_id_required")


class _StubLedger:
    def locked(self):
        return False, None

    def summary(self, batch_id=None):
        return {"batch_id": batch_id, "authorized": True, "remaining": 1, "used": 2,
                "authorized_calls": 3, "seed_used": 2, "window_open": True,
                "records_reserved": 0, "locked": False}

    def charge(self, batch_id, kind, *, detail="", source="runtime"):
        return {"batch_id": batch_id, "kind": kind}

    def audit(self, batch_id, kind, *, detail="", source="runtime"):
        return None

    def lock(self, reason, *, source="unknown"):
        return None

    def close(self):
        return None


class _FakeKeepalive:
    def __init__(self, hwnd, **kwargs):
        self.hwnd = hwnd

    def start(self):
        return {"topmost_set": True, "hwnd": self.hwnd}

    def tick(self, *, force=False):
        return None

    def finish(self):
        return {"ticks": 1, "reassert_count": 0, "reassert_failures": 0,
                "still_foreground_at_end": True, "topmost_cleared": True}


class _ProbeSession:
    """假会话：实现 cmd_probe 真正会调用的全部方法（含 `html`）。"""

    def __init__(self, html_text, opened):
        self._html = html_text
        self.opened = opened

    def start(self):
        return {"mode": "fake"}

    def open_live(self, url):
        self.opened.append(url)
        return object()

    def desktop_proof(self, *, tab=None, screenshot=None):
        return {"proven": True, "hwnd": 4242, "window_title": "probe-smoke - Google Chrome",
                "page_title": "probe-smoke", "window_title_matches_page": True,
                "foreground_matched": True,
                "window_rect": {"width": 800, "height": 600}}

    def wait_ready(self, tab, *, keepalive=None):
        return {"url": "https://s.weibo.com/weibo", "title": "probe-smoke",
                "ready": "complete", "http_status": 200, "text": "",
                "text_len": 10, "timed_out": False}

    def html(self, tab):
        return self._html

    def close(self):
        return None


class ProbeRuntimeTests(unittest.TestCase):
    """真正执行 cmd_probe（不是只查源码字符串）：--keyword 拼 URL、输出 counts、不落正文。"""

    HTML = ('<div class="card-wrap"><div class="card">'
            '<a class="name" href="https://s.weibo.com/u/1">作者</a>'
            '<p class="txt">正文标记-不应出现在输出里</p>'
            '<div class="from">3小时前</div><div class="card-act">'
            '<a href="https://s.weibo.com/status/4900000000000001"'
            ' data-id="4900000000000001">x</a></div>'
            '<div class="card-comment">评论 1</div><img class="avator">'
            '</div></div>')

    def _run(self, argv):
        opened: list[str] = []
        buf = io.StringIO()
        with mock.patch.object(cli, "_open_ledger", return_value=_StubLedger()), \
                mock.patch.object(cli, "_new_session",
                                  lambda *a, **k: _ProbeSession(self.HTML, opened)), \
                mock.patch.object(cli.desktop_mod, "Keepalive", _FakeKeepalive), \
                contextlib.redirect_stdout(buf):
            code = cli.main(argv)
        return code, json.loads(buf.getvalue().strip().splitlines()[-1]), opened

    def test_keyword_builds_url_inside_cli(self):
        code, payload, opened = self._run(
            ["probe", "--keyword", "学习计划模板", "--batch-id", "smoke"])
        self.assertEqual(code, codes.EXIT_OK)
        self.assertEqual(opened, [payload["requested_url"]])
        self.assertIn("s.weibo.com/weibo?q=", payload["requested_url"])
        self.assertIn("%E5%AD%A6%E4%B9%A0%E8%AE%A1%E5%88%92%E6%A8%A1%E6%9D%BF",
                      payload["requested_url"])
        self.assertIn("typeall=1", payload["requested_url"])
        self.assertIn("suball=1", payload["requested_url"])

    def test_runtime_output_has_counts_and_no_body(self):
        code, payload, _opened = self._run(
            ["probe", "--url", "https://s.weibo.com/weibo?q=x", "--batch-id", "smoke"])
        self.assertEqual(code, codes.EXIT_OK)
        counts = payload["summary"]["counts"]
        for key in ("card_wrap", "card", "p_txt", "a_name", "div_from", "card_act",
                    "status_links", "s_weibo_links", "img_avator", "card_comment"):
            self.assertGreaterEqual(counts[key], 1, key)
        self.assertNotIn("正文标记-不应出现在输出里", json.dumps(payload, ensure_ascii=False))
        self.assertIn("requested_url", payload)
        self.assertIn("final_url", payload)

    def test_url_and_keyword_are_exclusive(self):
        code, payload, _opened = self._run(
            ["probe", "--url", "https://x", "--keyword", "k", "--batch-id", "smoke"])
        self.assertEqual(code, codes.EXIT_INPUT)
        self.assertEqual(payload["stop"], "input_error")


class HtmlFetchTests(unittest.TestCase):
    """`session.html(tab)` 是 probe 的数据入口，必须真存在。"""

    def test_html_returns_rendered_document(self):
        class _Tab:
            async def get_content(self):
                return "<html><body><div class='card'>x</div></body></html>"

        out = session.VisibleSession("unused").html(_Tab())
        self.assertIn("class='card'", out)

    def test_visible_session_really_has_html(self):
        self.assertTrue(callable(getattr(session.VisibleSession, "html", None)))


class CountMappingTests(unittest.TestCase):
    """互动字段映射：真实 0 ≠ 未渲染；count_source 与 missing 都要如实带出。"""

    def setUp(self):
        from tools.selection.rpa import extract as _extract

        self.extract_mod = _extract

    def _card(self, mid, counts, meta):
        return {"container_id": mid, "mid": mid, "id": mid, "id_source": "mid",
                "bid": "Naaa" + mid[-3:], "href": f"//weibo.com/11/Naaa{mid[-3:]}",
                "url": f"https://weibo.com/11/Naaa{mid[-3:]}", "author": "作者",
                "text": "正文", "time": "1小时前", "counts": counts,
                "count_meta": meta, "hidden": False}

    def test_zero_is_kept_and_missing_is_not(self):
        card = self._card("4900000000000301", {"reposts": 12, "comments": 0, "likes": 12000},
                          {k: {"source": "position", "unit": None} for k in
                           ("reposts", "comments", "likes")})
        parsed = self.extract_mod.extract_cards([card], collected_at="2026-10-30T00:00:00Z")
        detail = parsed["details"][0]
        self.assertEqual((detail["reposts"], detail["comments"], detail["likes"]),
                         (12, 0, 12000))
        for field in ("reposts", "comments", "likes"):
            self.assertNotIn(field, detail["missing"])

    def test_unrendered_is_null_and_listed_once(self):
        card = self._card("4900000000000304",
                          {"reposts": None, "comments": None, "likes": None},
                          {k: {"source": "absent", "unit": None} for k in
                           ("reposts", "comments", "likes")})
        parsed = self.extract_mod.extract_cards([card], collected_at="2026-10-30T00:00:00Z")
        detail = parsed["details"][0]
        self.assertIsNone(detail["reposts"])
        self.assertIsNone(detail["likes"])
        for field in ("reposts", "comments", "likes"):
            self.assertEqual(detail["missing"].count(field), 1, field)
            self.assertEqual(detail["count_source"][field], "absent")

    def test_count_source_and_unit_surface(self):
        card = self._card("4900000000000302", {"reposts": 5, "comments": 7, "likes": None},
                          {"reposts": {"source": "position", "unit": None},
                           "comments": {"source": "position", "unit": None},
                           "likes": {"source": "absent", "unit": None}})
        detail = self.extract_mod.extract_cards([card], collected_at="2026-10-30T00:00:00Z")["details"][0]
        self.assertEqual(detail["count_source"],
                         {"reposts": "position", "comments": "position", "likes": "absent"})
        self.assertIn("likes", detail["missing"])

    def test_ambiguous_count_is_null_not_guessed(self):
        card = self._card("4900000000000306",
                          {"reposts": None, "comments": 0, "likes": 0},
                          {"reposts": {"source": "ambiguous", "unit": None},
                           "comments": {"source": "position", "unit": None},
                           "likes": {"source": "position", "unit": None}})
        detail = self.extract_mod.extract_cards([card], collected_at="2026-10-30T00:00:00Z")["details"][0]
        self.assertIsNone(detail["reposts"])
        self.assertEqual(detail["count_source"]["reposts"], "ambiguous")
        self.assertIn("reposts", detail["missing"])
        self.assertEqual((detail["comments"], detail["likes"]), (0, 0))


class CardActProfileTests(unittest.TestCase):
    """card-act 结构画像：只出结构，不出正文；四类结构都要能判读。"""

    def setUp(self):
        from tools.selection.rpa import probe as _probe

        self.probe = _probe

    def test_three_numeric_anchors(self):
        html = ('<div class="card-wrap"><div class="card-act">'
                '<a href="//weibo.com/aj/v6/repost/add">转发</a>'
                '<a href="//weibo.com/aj/v6/comment/add">评论</a>'
                '<a href="//weibo.com/attitudes?act=like" class="woo-like-count">12</a>'
                '</div></div>')
        cards = self.probe.summarize_card_act(html)
        self.assertEqual(len(cards), 1)
        card = cards[0]
        self.assertTrue(card["exists"])
        self.assertEqual(card["tags"], {"a": 3})
        self.assertEqual([c["tag"] for c in card["children"]], ["a", "a", "a"])
        self.assertEqual([c["href_shape"] for c in card["children"]],
                         ["repost", "comment", "like"])
        self.assertTrue(all(c["has_href"] for c in card["children"]))
        self.assertEqual([c["text_form"] for c in card["children"]],
                         ["chinese", "chinese", "digits"])
        self.assertEqual([c["has_digit"] for c in card["children"]], [False, False, True])
        self.assertIn("woo-like-count", card["children"][2]["classes"])
        self.assertNotIn("12", json.dumps(card, ensure_ascii=False))

    def test_span_and_em_without_anchor(self):
        html = ('<div class="card-wrap"><div class="card-act">'
                '<span class="line">转发</span><em>1.2万</em></div></div>')
        card = self.probe.summarize_card_act(html)[0]
        self.assertTrue(card["exists"])
        self.assertEqual(card["tags"], {"span": 1, "em": 1})
        self.assertEqual([c["text_form"] for c in card["children"]], ["chinese", "unit"])
        self.assertFalse(any(c["has_href"] for c in card["children"]))
        self.assertEqual([c["href_shape"] for c in card["children"]], ["none", "none"])

    def test_empty_card_act(self):
        html = '<div class="card-wrap"><div class="card-act"></div></div>'
        card = self.probe.summarize_card_act(html)[0]
        self.assertTrue(card["exists"])
        self.assertEqual(card["tags"], {})
        self.assertEqual(card["children"], [])
        self.assertEqual(card["act_text_len"], 0)

    def test_missing_card_act(self):
        html = '<div class="card-wrap"><p class="txt">正文</p></div>'
        card = self.probe.summarize_card_act(html)[0]
        self.assertFalse(card["exists"])
        self.assertEqual(card["tags"], {})
        self.assertEqual(card["children"], [])

    def test_limit_five_cards(self):
        html = "".join(f'<div class="card-wrap"><div class="card-act"><a>1</a></div></div>'
                       for _ in range(7))
        self.assertEqual(len(self.probe.summarize_card_act(html, limit=5)), 5)

    def test_void_elements_do_not_desync_depth(self):
        """`<img>` 等空元素不得让 depth 漂移（否则多张卡会被并成一张）。"""
        html = ("".join('<div class="card-wrap"><img src="a.jpg">'
                        f'<div class="card-act"><ul><li>转发 {i}</li></ul></div></div>'
                        for i in range(3)))
        cards = self.probe.summarize_card_act(html)
        self.assertEqual(len(cards), 3)
        for card in cards:
            self.assertTrue(card["exists"])
            self.assertEqual([c["tag"] for c in card["children"]], ["ul"])
            items = card["children"][0]["items"]
            self.assertEqual([i["tag"] for i in items], ["li"])
            self.assertTrue(items[0]["has_digit"])

    def test_ul_items_drill_down(self):
        """`ul` 下钻一层：li 数量、标签、是否含数字。"""
        html = ('<div class="card-wrap"><div class="card-act"><ul>'
                '<li><a href="//weibo.com/aj/v6/repost/add">转发</a><span>12</span></li>'
                '<li><a href="//weibo.com/aj/v6/comment/add">评论</a></li>'
                '<li><a href="//weibo.com/attitudes?act=like">赞</a></li>'
                '</ul></div></div>')
        ul = self.probe.summarize_card_act(html)[0]["children"][0]
        self.assertEqual(ul["tag"], "ul")
        self.assertEqual(len(ul["items"]), 3)
        self.assertEqual([i["tag"] for i in ul["items"]], ["li", "li", "li"])
        self.assertEqual(ul["tags"], {"other": 3})
        self.assertTrue(ul["items"][0]["has_digit"])
        self.assertFalse(ul["items"][1]["has_digit"])
        self.assertFalse(ul["items"][2]["has_digit"])

    def test_each_card_gets_its_own_act(self):
        html = ('<div class="card-wrap"><div class="card-act"><ul><li>转发</li></ul></div></div>'
                '<div class="card-wrap"><div class="card-act"><ul><li>评论</li></ul></div></div>')
        cards = self.probe.summarize_card_act(html)
        self.assertEqual(len(cards), 2)
        self.assertEqual([len(c["children"]) for c in cards], [1, 1])


class ExportFieldTests(unittest.TestCase):
    """统一导出补齐 reposts/author，且向后兼容旧记录。"""

    def setUp(self):
        from tools.selection.access import records as _rec
        from tools.selection.access import zhihu as _zhihu

        self.rec = _rec
        self.zhihu = _zhihu

    def test_new_record_carries_reposts_and_author(self):
        record = self.rec.make_record(
            values={"native_id": "1", "type": "status", "url": "https://weibo.com/a/1",
                    "text": "正文", "author": "某人", "reposts": 0, "comments": 1,
                    "likes": 2},
            evidence={"native_id": "dom:x", "text": "dom:x", "author": "dom:card a.name",
                      "reposts": "dom:card counts"},
            collected_at="2026-10-30T00:00:00Z", source="weibo:search:status")
        self.assertEqual(record["author"], "某人")
        self.assertEqual(record["reposts"], 0)
        self.assertNotIn("author", record["missing"])
        self.assertNotIn("reposts", record["missing"])       # 0 不是缺失

    def test_legacy_row_without_new_fields_exports(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = pathlib.Path(tmp) / "legacy.jsonl"
            src.write_text(json.dumps({"native_id": "9", "type": "answer",
                                       "url": "https://www.zhihu.com/question/1/answer/9",
                                       "title": "t", "text": "x",
                                       "collected_at": "2026-10-30T00:00:00Z"},
                                      ensure_ascii=False) + "\n", encoding="utf-8")
            out = pathlib.Path(tmp) / "out.jsonl"
            payload = self.zhihu.export(src, out, fmt="jsonl")
            self.assertTrue(payload["ok"])
            written = [json.loads(line) for line in
                       out.read_text(encoding="utf-8").splitlines()]
            self.assertIsNone(written[0]["reposts"])
            self.assertIsNone(written[0]["author"])
            self.assertEqual(list(self.rec.FIELDS)[-3:],
                             ["reposts", "author", "root_comment_id"])

    def test_column_order_is_stable(self):
        self.assertEqual(self.rec.FIELDS[:11],
                         ("native_id", "type", "parent_id", "url", "title", "text",
                          "published_at", "collected_at", "voteup", "comments", "likes"))


class CommentStructureTests(unittest.TestCase):
    """评论结构画像：四类 fixture（多条/子回复/展开按钮/空态/墙）。"""

    def setUp(self):
        from tools.selection.rpa import probe as _probe

        self.probe = _probe

    def test_multiple_comments(self):
        html = ('<div class="comment-item"><a class="name" href="//weibo.com/u/1">甲</a>'
                '<p class="txt">第一条评论正文</p><span>3分钟前</span>'
                '<a class="like">赞 2</a></div>'
                '<div class="comment-item"><a class="name" href="//weibo.com/u/2">乙</a>'
                '<p class="txt">第二条评论正文更长一些</p><span>1小时前</span></div>')
        out = self.probe.summarize_comments(html)
        self.assertEqual(out["items"], 2)
        self.assertEqual(out["author_present"], 2)
        self.assertEqual(out["text_nodes"], {"p": 2})
        self.assertEqual(out["time_nodes"], 2)
        self.assertEqual(out["like_nodes"], 1)
        self.assertFalse(out["empty_state"])
        self.assertNotIn("第一条评论正文", json.dumps(out, ensure_ascii=False))

    def test_child_reply_container(self):
        html = ('<div class="comment-item"><a class="name">甲</a><p class="txt">父评论</p>'
                '<div class="comment-item"><a class="name">乙</a><p class="txt">子回复</p>'
                '</div></div>')
        out = self.probe.summarize_comments(html)
        self.assertGreaterEqual(out["items"], 1)
        self.assertGreaterEqual(out["containers"].get("div.comment-item", 0), 2)

    def test_expand_button(self):
        html = ('<div class="comment-item"><p class="txt">评论</p></div>'
                '<div class="more">展开更多</div>')
        out = self.probe.summarize_comments(html)
        self.assertEqual(out["expand_buttons"], 1)

    def test_empty_state(self):
        out = self.probe.summarize_comments("<div class='comment-list'></div>")
        self.assertEqual(out["items"], 0)
        self.assertTrue(out["empty_state"])

    def test_login_wall(self):
        out = self.probe.summarize_comments("<div>请登录后查看评论</div>")
        self.assertEqual(out["items"], 0)
        self.assertFalse(out["empty_state"])
        self.assertTrue(out["wall_markers"])


class NetworkAuditTests(unittest.TestCase):
    """页面自身请求摘要：只留结构、只留微博域、参数值不落盘。"""

    def setUp(self):
        from tools.selection.rpa import probe as _probe

        self.probe = _probe

    def test_multiple_requests_kept(self):
        entries = [
            {"host": "weibo.com", "path": "/ajax/statuses/buildComments", "method": "get",
             "params": ["is_reload", "id"], "status": 200, "size": 2048,
             "keys": ["ok", "data", "total_number"]},
            {"host": "s.weibo.com", "path": "/ajax/statuses/show", "method": "GET",
             "params": ["id"], "status": 200, "size": 512, "keys": ["id", "text"]},
        ]
        out = self.probe.summarize_network(entries)
        self.assertEqual(out["count"], 2)
        self.assertEqual(out["requests"][0]["method"], "GET")
        self.assertEqual(out["by_path"]["/ajax/statuses/buildComments"], 1)
        self.assertEqual(len(out["comment_like"]), 1)
        self.assertNotIn("2048", json.dumps(out["requests"][0]["params"]))

    def test_non_weibo_filtered(self):
        entries = [{"host": "evil.example.com", "path": "/x", "method": "GET",
                    "params": ["token"], "status": 200, "size": 1, "keys": []},
                   {"host": "weibo.cn", "path": "/comments/hotflow", "method": "GET",
                    "params": ["id", "mid"], "status": 200, "size": 10, "keys": ["data"]}]
        out = self.probe.summarize_network(entries)
        self.assertEqual(out["count"], 1)
        self.assertEqual(out["dropped_non_weibo"], 1)
        self.assertEqual(out["requests"][0]["host"], "weibo.cn")

    def test_non_json_response_does_not_crash(self):
        entries = [{"host": "weibo.com", "path": "/ajax/x", "method": "GET",
                    "params": [], "status": 200, "size": 3, "keys": []}]
        out = self.probe.summarize_network(entries)
        self.assertEqual(out["requests"][0]["keys"], [])

    def test_param_values_never_kept(self):
        entries = [{"host": "weibo.com", "path": "/ajax/statuses/buildComments",
                    "method": "GET", "params": ["id", "is_show_bulletin"],
                    "status": 200, "size": 100, "keys": ["data"]}]
        text = json.dumps(self.probe.summarize_network(entries), ensure_ascii=False)
        self.assertIn("is_show_bulletin", text)
        self.assertNotIn("5358621166144499", text)


class SurfaceVerdictTests(unittest.TestCase):
    """详情页不该再被判成 no_cards：按 surface 分开判定。"""

    def setUp(self):
        from tools.selection.rpa import probe as _probe

        self.probe = _probe

    def test_surface_detection(self):
        self.assertEqual(self.probe.surface_of("https://weibo.com/3271525130/RoB0gpMsP"),
                         "detail")
        self.assertEqual(self.probe.surface_of("https://m.weibo.cn/status/5358621166144499"),
                         "detail")
        self.assertEqual(self.probe.surface_of(
            "https://s.weibo.com/weibo?q=%E5%AD%A6%E4%B9%A0"), "search")

    def test_detail_page_with_text_is_ok(self):
        summary = {"surface": "detail", "text_len": 2355, "cards_total": 0,
                   "wall": {"markers": [], "login_wall": []}}
        self.assertEqual(self.probe.verdict(summary), (codes.EXIT_OK, None))

    def test_detail_page_with_comments_is_ok(self):
        summary = {"surface": "detail", "text_len": 10, "cards_total": 0,
                   "comments": {"items": 3}, "wall": {"markers": [], "login_wall": []}}
        self.assertEqual(self.probe.verdict(summary), (codes.EXIT_OK, None))

    def test_detail_page_empty_is_not_no_cards(self):
        summary = {"surface": "detail", "text_len": 0, "cards_total": 0,
                   "comments": {"items": 0}, "wall": {"markers": [], "login_wall": []}}
        self.assertEqual(self.probe.verdict(summary), (codes.EXIT_EMPTY, "detail_empty"))

    def test_search_page_still_uses_cards(self):
        summary = {"surface": "search", "text_len": 100, "cards_total": 0,
                   "wall": {"markers": [], "login_wall": []}}
        self.assertEqual(self.probe.verdict(summary),
                         (codes.EXIT_UNSUPPORTED, "no_cards"))


class HookOrderTests(unittest.TestCase):
    """钩子必须在导航**之前**注入，否则漏掉加载期请求。"""

    def test_hook_installed_before_navigation(self):
        order: list[str] = []

        class _Tab:
            async def send(self, cmd):
                order.append(str(cmd)[:120])

            async def get(self, url):
                order.append("nav")

        class _Browser:
            async def get(self, url):
                return _Tab()

        sess = session.VisibleSession("unused", live=True)
        sess._browser = _Browser()
        with mock.patch.object(session.VisibleSession, "activate",
                               lambda self, tab: {"activated": True}):
            sess.open_live_hooked("https://weibo.com/1/abc")
        self.assertEqual(order[-1], "nav")                       # 导航在最后
        hook = [i for i, s in enumerate(order)
                if "add_script_to_evaluate_on_new_document" in s]
        self.assertTrue(hook, order)                             # 钩子注入确实发生
        self.assertLess(hook[0], order.index("nav"))             # 且在导航之前

    def test_plain_open_live_has_no_hook(self):
        order: list[str] = []

        class _Tab:
            async def send(self, cmd):
                order.append("hook")

        class _Browser:
            async def get(self, url):
                order.append("nav")
                return _Tab()

        sess = session.VisibleSession("unused", live=True)
        sess._browser = _Browser()
        with mock.patch.object(session.VisibleSession, "activate",
                               lambda self, tab: {"activated": True}):
            sess.open_live("https://weibo.com/1/abc")
        self.assertEqual(order, ["nav"])

    def test_probe_uses_hooked_open_when_auditing(self):
        calls: list[str] = []

        class _Sess(_ProbeSession):
            def open_live(self, url):
                calls.append("plain")
                return object()

            def open_live_hooked(self, url):
                calls.append("hooked")
                return object()

        buf = io.StringIO()
        with mock.patch.object(cli, "_open_ledger", return_value=_StubLedger()), \
                mock.patch.object(cli, "_new_session",
                                  lambda *a, **k: _Sess(ProbeRuntimeTests.HTML, [])), \
                mock.patch.object(cli.desktop_mod, "Keepalive", _FakeKeepalive), \
                contextlib.redirect_stdout(buf):
            cli.main(["probe", "--url", "https://weibo.com/1/abc", "--batch-id", "smoke",
                      "--audit-network"])
        self.assertEqual(calls, ["hooked"])


class SortAndRenderWaitTests(unittest.TestCase):
    """热度排序参数 + 详情页渲染稳定等待。"""

    def test_hot_sort_appends_xsort(self):
        opened: list[str] = []

        class _Sess(_ProbeSession):
            def open_live(self, url):
                opened.append(url)
                return object()

        buf = io.StringIO()
        with mock.patch.object(cli, "_open_ledger", return_value=_StubLedger()), \
                mock.patch.object(cli, "_new_session",
                                  lambda *a, **k: _Sess(ProbeRuntimeTests.HTML, [])), \
                mock.patch.object(cli.desktop_mod, "Keepalive", _FakeKeepalive), \
                contextlib.redirect_stdout(buf):
            cli.main(["live-search", "--keyword", "考研", "--sort", "hot",
                      "--allow-live", "--batch-id", "smoke"])
        self.assertTrue(opened)
        self.assertIn("xsort=hot", opened[0])

    def test_render_wait_stops_when_stable(self):
        pages = [{"text_len": 120}, {"text_len": 620}, {"text_len": 620}]

        class _Tab:
            pass

        sess = session.VisibleSession("unused")
        seq = iter(pages)
        with mock.patch.object(session.VisibleSession, "read_page",
                               lambda self, tab: next(seq, pages[-1])):
            out = sess.wait_render_stable(_Tab(), min_len=500, attempts=5, interval=0.0)
        self.assertTrue(out["stable"])
        self.assertGreaterEqual(out["text_len"], 500)
        self.assertIn("waited_ms", out)

    def test_render_wait_flags_unrendered(self):
        class _Tab:
            pass

        sess = session.VisibleSession("unused")
        with mock.patch.object(session.VisibleSession, "read_page",
                               lambda self, tab: {"text_len": 361}):
            out = sess.wait_render_stable(_Tab(), min_len=500, attempts=3, interval=0.0)
        self.assertFalse(out["stable"])
        self.assertEqual(out["text_len"], 361)


class CommentParseTests(unittest.TestCase):
    """buildComments 响应 -> 统一记录（五类 fixture）。"""

    def setUp(self):
        from tools.selection.rpa import comments as _comments

        self.c = _comments

    def _item(self, cid, text, *, author="甲", likes=0, children=None):
        item = {"id": int(cid) if str(cid).isdigit() else 0, "idstr": str(cid),
                "text_raw": text, "created_at": "Wed Oct 29 16:22:00 +0800 2026",
                "like_counts": likes, "user": {"screen_name": author}}
        if children is not None:
            item["comments"] = children
        return item

    def test_single_page_multiple_comments(self):
        page = {"ok": 1, "total_number": 3, "max_id": 0,
                "data": [self._item("101", "第一条 <a>链接</a>"), self._item("102", "第二条"),
                         self._item("103", "第三条", author="乙", likes=5)]}
        out = self.c.parse_page(page)
        self.assertTrue(out["ok"])
        self.assertEqual(out["page_count"], 3)
        self.assertEqual([r["comment_id"] for r in out["records"]], ["101", "102", "103"])
        self.assertTrue(all(r["parent_id"] is None for r in out["records"]))
        self.assertEqual(out["records"][0]["text"], "第一条 链接")
        self.assertEqual(out["records"][2]["like_counts"], 5)
        self.assertEqual(out["records"][2]["author"], "乙")
        self.assertIsNone(out["max_id"])

    def test_child_replies_keep_parent(self):
        child = self._item("201", "子回复")
        page = {"ok": 1, "total_number": 2, "data": [self._item("200", "父评论", children=[child])]}
        out = self.c.parse_page(page)
        self.assertEqual(out["page_count"], 1)
        self.assertEqual(out["child_count"], 1)
        child_rec = [r for r in out["records"] if r["parent_id"]][0]
        self.assertEqual(child_rec["parent_id"], "200")
        self.assertEqual(child_rec["root_comment_id"], "200")

    def test_more_pages_when_total_exceeds_page(self):
        page = {"ok": 1, "total_number": 147, "max_id": 1234567890,
                "data": [self._item("301", "一")]}
        out = self.c.parse_page(page)
        self.assertEqual(out["total_number"], 147)
        self.assertTrue(out["max_id"])

    def test_no_more_when_max_id_empty(self):
        page = {"ok": 1, "total_number": 1, "max_id": None,
                "data": [self._item("401", "只有一条")]}
        out = self.c.parse_page(page)
        self.assertFalse(out["max_id"])
        merged = self.c.merge_pages([out])
        self.assertEqual(merged["pages"], 1)

    def test_empty_or_error_page(self):
        out = self.c.parse_page({"ok": 0, "data": []})
        self.assertFalse(out["ok"])
        self.assertEqual(out["records"], [])
        self.assertEqual(out["reason"], "ok_false")
        empty = self.c.parse_page({"ok": 1, "data": []})
        self.assertTrue(empty["ok"])
        self.assertEqual(empty["records"], [])

    def test_page_url_params(self):
        url = self.c.page_url("5348595884891806", count=20)
        for needle in ("is_reload=1", "id=5348595884891806", "is_show_bulletin=2",
                       "is_mix=0", "count=20", "fetch_level=0", "locale=zh-CN"):
            self.assertIn(needle, url)
        self.assertNotIn("max_id=", url)
        paged = self.c.page_url("1", count=20, max_id="999")
        self.assertIn("max_id=999", paged)
        self.assertIn("flow=", paged)


class CommentExportMappingTests(unittest.TestCase):
    """评论 -> 统一导出记录（帖子与评论列集合一致、父子可还原）。"""

    def setUp(self):
        from tools.selection.rpa import comments as _comments
        from tools.selection.access import records as _rec

        self.c = _comments
        self.rec = _rec

    def _recs(self, items):
        return self.c.to_records(items, post_url="https://weibo.com/5518250456/RkocskwA6",
                                 collected_at="2026-10-30T08:03:11Z")

    def test_top_level_mapping(self):
        out = self._recs([{"comment_id": "1", "parent_id": None, "author": "甲",
                           "text": "顶层", "published_at": "t", "like_counts": 7,
                           "root_comment_id": "1"}])
        r = out[0]
        self.assertEqual(r["native_id"], "1")
        self.assertEqual(r["type"], "comment")
        self.assertIsNone(r["parent_id"])
        self.assertEqual(r["likes"], 7)
        self.assertEqual(r["author"], "甲")
        self.assertEqual(r["url"], "https://weibo.com/5518250456/RkocskwA6")
        self.assertEqual(r["root_comment_id"], "1")
        self.assertEqual(set(r) - set(self.rec.FIELDS),
                         {"missing", "not_applicable", "supported", "author_redacted",
                          "field_evidence", "source"})

    def test_child_mapping_and_pairing(self):
        out = self._recs([
            {"comment_id": "1", "parent_id": None, "author": "甲", "text": "父",
             "published_at": "t1", "like_counts": 1, "root_comment_id": "1"},
            {"comment_id": "2", "parent_id": "1", "author": "乙", "text": "子",
             "published_at": "t2", "like_counts": 0, "root_comment_id": "1"},
        ])
        by_id = {r["native_id"]: r for r in out}
        self.assertEqual(by_id["2"]["parent_id"], "1")
        self.assertEqual(by_id["2"]["parent_id"], by_id["1"]["native_id"])   # 可还原
        self.assertEqual(by_id["2"]["root_comment_id"], "1")

    def test_zero_likes_not_missing(self):
        out = self._recs([{"comment_id": "3", "parent_id": None, "author": "甲",
                           "text": "x", "published_at": "t", "like_counts": 0}])
        self.assertNotIn("likes", out[0]["missing"])
        self.assertEqual(out[0]["likes"], 0)

    def test_missing_fields_are_listed(self):
        out = self._recs([{"comment_id": "4", "parent_id": None, "text": None,
                           "published_at": None, "like_counts": None}])
        missing = out[0]["missing"]
        for field in ("text", "published_at", "likes", "author"):
            self.assertIn(field, missing)

    def test_columns_match_post_records(self):
        out = self._recs([{"comment_id": "5", "parent_id": None, "text": "x",
                           "published_at": "t", "like_counts": 1}])
        self.assertEqual(set(out[0]) - {"missing", "not_applicable", "supported",
                                        "author_redacted", "field_evidence", "source"},
                         set(self.rec.FIELDS))


class MissingSemanticsTests(unittest.TestCase):
    """「不适用」≠「未读到」：结构性缺项进 not_applicable，不进 missing。"""

    def setUp(self):
        from tools.selection.rpa import comments as _comments
        from tools.selection.access import records as _rec

        self.c = _comments
        self.rec = _rec

    def _mapped(self, item):
        return self.c.to_records([item], post_url="https://weibo.com/1/abc",
                                 collected_at="2026-10-30T08:03:11Z")[0]

    def test_top_level_parent_id_is_not_applicable(self):
        r = self._mapped({"comment_id": "1", "parent_id": None, "author": "甲",
                          "text": "顶层", "published_at": "t", "like_counts": 0})
        self.assertIn("parent_id", r["not_applicable"])
        self.assertNotIn("parent_id", r["missing"])
        self.assertIn("reposts", r["not_applicable"])
        self.assertIn("comments", r["not_applicable"])
        self.assertNotIn("reposts", r["missing"])
        self.assertNotIn("comments", r["missing"])

    def test_child_parent_id_is_never_not_applicable(self):
        r = self._mapped({"comment_id": "2", "parent_id": "1", "author": "乙",
                          "text": "子", "published_at": "t", "like_counts": 1})
        self.assertNotIn("parent_id", r["not_applicable"])
        self.assertNotIn("parent_id", r["missing"])
        self.assertEqual(r["parent_id"], "1")

    def test_really_missing_still_reported(self):
        r = self._mapped({"comment_id": "3", "parent_id": None, "text": None,
                          "published_at": None, "like_counts": None})
        self.assertIn("text", r["missing"])
        self.assertIn("published_at", r["missing"])
        self.assertIn("likes", r["missing"])
        self.assertNotIn("parent_id", r["missing"])

    def test_post_root_comment_is_not_applicable(self):
        card = {"container_id": "9", "mid": "9", "id": "4900000000000009",
                "id_source": "mid", "bid": "Naaa9", "url": "https://weibo.com/1/Naaa9",
                "author": "甲", "text": "正文", "time": "1小时前",
                "counts": {"reposts": 0, "comments": 0, "likes": 0},
                "count_meta": {}, "hidden": False}
        from tools.selection.rpa import extract as _extract

        r = _extract.extract_cards([card], collected_at="2026-10-30T00:00:00Z")["records"][0]
        self.assertIn("root_comment_id", r["not_applicable"])
        self.assertNotIn("root_comment_id", r["missing"])

    def test_legacy_jsonl_without_not_applicable_still_reads(self):
        import json as _json
        import tempfile as _tf

        from tools.selection.access import zhihu as _zhihu

        with _tf.TemporaryDirectory() as tmp:
            src = pathlib.Path(tmp) / "legacy.jsonl"
            src.write_text(_json.dumps({"native_id": "9", "type": "answer",
                                        "url": "https://www.zhihu.com/question/1/answer/9",
                                        "title": "t", "text": "x",
                                        "collected_at": "2026-10-30T00:00:00Z"},
                                       ensure_ascii=False) + "\n", encoding="utf-8")
            out = pathlib.Path(tmp) / "out.jsonl"
            payload = _zhihu.export(src, out, fmt="jsonl")
            self.assertTrue(payload["ok"])
            row = _json.loads(out.read_text(encoding="utf-8").splitlines()[0])
            self.assertTrue(set(row) <= set(self.rec.EXPORT_FIELDS))
            self.assertIn("missing", row)          # 老记录不带 not_applicable 也能读
            self.assertIsNone(row["reposts"])


class StaticSafetyTests(unittest.TestCase):
    RPA = REPO / "tools" / "selection" / "rpa"

    def test_session_never_reads_cookies(self):
        text = (self.RPA / "session.py").read_text(encoding="utf-8")
        self.assertNotIn(".cookies", text)
        self.assertNotIn("cookies()", text)

    def test_session_blocks_external_schemes(self):
        text = (self.RPA / "session.py").read_text(encoding="utf-8")
        for pattern in ('"http://*"', '"https://*"', '"ws://*"', '"wss://*"'):
            self.assertIn(pattern, text)

    def test_rpa_package_never_touches_cookies(self):
        forbidden = ("cookies()", "get_cookies", "getAllCookies", ".cookies",
                     "Network.getAllCookies", "document.cookie")
        for path in sorted(self.RPA.glob("*.py")):
            text = path.read_text(encoding="utf-8")
            for needle in forbidden:
                with self.subTest(file=path.name, needle=needle):
                    self.assertNotIn(needle, text)

    def test_no_ledger_path_override_in_rpa(self):
        text = (self.RPA / "cli.py").read_text(encoding="utf-8")
        self.assertNotIn("--platform-db", text)
        self.assertNotIn("--ledger-path", text)
        self.assertIn("guard_mod.open_guard()", text)


# --------------------------------------------------------------------------
# 登录判定：真实 SIGNED_IN_JS + Node DOM 桩（四类场景，双向覆盖）
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


def run_signed_in_js(host="weibo.com", path="/", text="", counts=None) -> str:
    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = pathlib.Path(tmp)
        (tmpdir / "harness.js").write_text(_DOM_HARNESS, encoding="utf-8")
        (tmpdir / "signals.json").write_text(
            json.dumps({"host": host, "path": path, "text": text,
                        "counts": counts or {}}), encoding="utf-8")
        (tmpdir / "script.js").write_text(weibo_mod.SIGNED_IN_JS, encoding="utf-8")
        proc = subprocess.run([NODE, str(tmpdir / "harness.js"),
                               str(tmpdir / "signals.json"), str(tmpdir / "script.js")],
                              capture_output=True, text=True, encoding="utf-8",
                              timeout=60)
        if proc.returncode != 0:
            raise AssertionError(f"node failed: {proc.stderr[:400]}")
        return proc.stdout


class SignedInDomStubTests(unittest.TestCase):
    """微博登录判定：放宽后仍不能把公开页/登录墙误判成已登录。"""

    def setUp(self):
        self.assertTrue(NODE, "node 必须可用：SIGNED_IN_JS 要真的跑起来，不能跳过")

    def verdict(self, **kwargs) -> str:
        return weibo_mod.classify_signed_in(run_signed_in_js(**kwargs))

    def test_logged_in_home_with_compose_and_own_profile_link(self):
        """已登录首页：发微博按钮 + 自有 /u/ 链接 + 退出文案 → signed_in。"""
        raw = run_signed_in_js(host="weibo.com", path="/",
                               text="首页 我的主页 退出",
                               counts={"/compose": 1, "/u/": 3})
        signals = json.loads(raw)
        self.assertTrue(signals.get("hasComposeBtn"))
        self.assertTrue(signals.get("hasOwnProfileLink"))
        self.assertTrue(signals.get("hasSignout"))
        self.assertEqual(weibo_mod.classify_signed_in(signals), "ok")
        self.assertTrue(weibo_mod.signed_in_verdict(signals))
        self.assertIn(weibo_mod.signed_in_evidence(signals),
                      {"hasSignout", "composeBtn+userLink", "text:退出"})

    def test_logged_out_home_is_unknown(self):
        """未登录首页（只有公开内容）→ 不成立。"""
        self.assertEqual(self.verdict(host="weibo.com", path="/",
                                      text="登录 注册 热门 视频",
                                      counts={"avatar": 4, "/u/": 6}), "unknown")

    def test_passport_page_with_buttons_is_unknown(self):
        """passport 登录页即使有发微博按钮/退出文案 → 不成立。"""
        self.assertEqual(self.verdict(host="passport.weibo.com", path="/sso/signin",
                                      text="退出 我的主页 发微博",
                                      counts={"/compose": 1, "/u/": 5}), "unknown")

    def test_public_page_with_only_user_links_is_unknown(self):
        """公开页只有 /u/ 链接 → 不成立（userLink 单独不能解锁）。"""
        self.assertEqual(self.verdict(host="weibo.com", path="/",
                                      text="热门 话题", counts={"/u/": 20}), "unknown")

    def test_compose_without_user_link_is_unknown(self):
        """只有发布按钮、没有自有主页链接 → 不成立（防公开页误判）。"""
        self.assertEqual(self.verdict(host="weibo.com", path="/",
                                      text="热门", counts={"/compose": 1}), "unknown")

    def test_signin_path_on_business_host_is_unknown(self):
        """weibo.com/signin 即使渲染退出控件也不算登录。"""
        self.assertEqual(self.verdict(host="weibo.com", path="/signin",
                                      text="退出", counts={"/logout": 1}), "unknown")

    def test_blank_page_keeps_the_original_key_contract(self):
        """空白页只吐原有 8 个键（新键仅在为真时出现）。"""
        signals = json.loads(run_signed_in_js(host="weibo.com", path="/"))
        self.assertEqual(set(signals), {"host", "path", "text", "hasLogout",
                                        "hasSettings", "hasCompose",
                                        "avatarCount", "userLinkCount"})


if __name__ == "__main__":
    unittest.main()
