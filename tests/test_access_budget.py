"""State-dir budget: one budget per dir, no way to reset it by renaming.

Covers the rework items: an explicit batch id is a label (not an escape hatch),
a lock survives restarts and relabels, polls have their own quota, and a
failed write never lets a request out.
"""

from __future__ import annotations

import pathlib
import sys
import threading
import time
import tempfile
import unittest

REPO = pathlib.Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from tools.selection.access import budget as budget_mod  # noqa: E402
from tools.selection.access import platform_budget as platform_mod  # noqa: E402


class FakeClock:
    def __init__(self, start: float = 1_000_000.0) -> None:
        self.now = start

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


class BudgetTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = pathlib.Path(self._tmp.name)
        self.clock = FakeClock()

    def tearDown(self):
        self._tmp.cleanup()

    def open(self, **kwargs):
        kwargs.setdefault("clock", self.clock)
        return budget_mod.open_budget(self.dir, **kwargs)

    # -- one budget per state dir -----------------------------------------
    def test_counters_survive_reopen(self):
        first = self.open()
        label = first.batch_id
        first.charge("search")
        first.close()

        second = self.open()  # plain restart, no flags
        self.assertEqual(second.batch_id, label)
        self.assertEqual(second.snapshot()["calls"], 1)
        second.close()

    def test_three_calls_then_refused(self):
        budget = self.open()
        for index in range(budget_mod.MAX_CALLS):
            budget.charge("search", f"call{index}")
            self.clock.advance(budget_mod.MIN_INTERVAL)
        before = budget.snapshot()
        with self.assertRaises(budget_mod.BudgetError) as caught:
            budget.charge("search")
        self.assertEqual(caught.exception.code, "calls_exhausted")
        self.assertEqual(budget.snapshot()["calls"], before["calls"])
        budget.close()

    def test_interval_enforced(self):
        budget = self.open()
        budget.charge("search")
        with self.assertRaises(budget_mod.BudgetError) as caught:
            budget.charge("detail")
        self.assertEqual(caught.exception.code, "interval_not_elapsed")
        self.assertEqual(budget.snapshot()["calls"], 1)
        self.clock.advance(budget_mod.MIN_INTERVAL)
        budget.charge("detail")
        self.assertEqual(budget.snapshot()["calls"], 2)
        budget.close()

    def test_window_blocks_after_max_seconds(self):
        budget = self.open()
        self.clock.advance(budget_mod.MAX_SECONDS + 1)
        with self.assertRaises(budget_mod.BudgetError) as caught:
            budget.charge("search")
        self.assertEqual(caught.exception.code, "time_exhausted")
        budget.close()

    def test_failed_call_is_not_refunded(self):
        budget = self.open()
        budget.charge("search")
        budget.note("transport_error", "transport:URLError")
        self.clock.advance(budget_mod.MIN_INTERVAL)
        budget.charge("search")
        self.assertEqual(budget.snapshot()["calls"], 2)
        budget.close()

    def test_records_target_is_soft(self):
        """v11：状态预算的记录数也是软目标——超目标不报错，只回报 over_cap。"""
        budget = self.open()
        budget.reserve_records(4)
        over = budget.reserve_records(2)
        self.assertTrue(over["over_cap"])
        self.assertEqual(over["over_by"], 1)
        budget.reserve_records(1)
        self.assertEqual(budget.snapshot()["records"], 7)
        budget.close()

    # -- A) no way to reset by renaming ------------------------------------
    def test_explicit_batch_id_only_relabels(self):
        first = self.open()
        first.charge("search")
        self.clock.advance(budget_mod.MIN_INTERVAL)
        first.close()

        renamed = self.open(batch_id="a-completely-different-id")
        self.assertEqual(renamed.batch_id, "a-completely-different-id")
        # the counter did NOT reset with the new name
        self.assertEqual(renamed.snapshot()["calls"], 1)
        renamed.charge("search")
        self.assertEqual(renamed.snapshot()["calls"], 2)
        renamed.close()

    def test_relabel_does_not_reset_records_or_window(self):
        first = self.open()
        first.reserve_records(3)
        self.clock.advance(budget_mod.MAX_SECONDS + 1)
        first.close()

        renamed = self.open(batch_id="fresh-looking-id")
        self.assertEqual(renamed.snapshot()["records"], 3)
        with self.assertRaises(budget_mod.BudgetError) as caught:
            renamed.charge("search")  # the 300s window is state-dir wide too
        self.assertEqual(caught.exception.code, "time_exhausted")
        renamed.close()

    def test_exhausted_calls_cannot_be_revived_by_new_id(self):
        budget = self.open()
        for index in range(budget_mod.MAX_CALLS):
            budget.charge("search", f"call{index}")
            self.clock.advance(budget_mod.MIN_INTERVAL)
        budget.close()

        other = self.open(batch_id="yet-another-id")
        with self.assertRaises(budget_mod.BudgetError) as caught:
            other.charge("search")
        self.assertEqual(caught.exception.code, "calls_exhausted")
        other.close()

    def test_lock_survives_restart_and_any_relabel(self):
        budget = self.open()
        budget.charge("search")
        budget.lock("text:安全验证", source="detail")
        budget.close()

        with self.assertRaises(budget_mod.BudgetError) as plain:
            self.open()
        self.assertEqual(plain.exception.code, "batch_locked")
        self.assertEqual(plain.exception.detail, "text:安全验证")

        with self.assertRaises(budget_mod.BudgetError) as renamed:
            self.open(batch_id="brand-new-id")
        self.assertEqual(renamed.exception.code, "batch_locked")

        peeked = budget_mod.peek(self.dir)
        self.assertTrue(peeked["locked"])
        self.assertEqual(peeked["lock_reason"], "text:安全验证")
        self.assertEqual(peeked["lock_source"], "detail")

    def test_locked_budget_keeps_its_counters_visible(self):
        budget = self.open()
        budget.charge("search")
        budget.lock("http_429", source="comments")
        budget.close()
        peeked = budget_mod.peek(self.dir)
        self.assertEqual(peeked["calls"], 1)
        self.assertEqual(peeked["lock_source"], "comments")

    def test_charge_after_lock_in_same_instance(self):
        budget = self.open()
        budget.lock("http_429")
        with self.assertRaises(budget_mod.BudgetError) as caught:
            budget.charge("search")
        self.assertEqual(caught.exception.code, "batch_locked")
        budget.close()

    # -- login polls are a separate quota ----------------------------------
    def test_polls_do_not_touch_the_call_counter(self):
        budget = self.open()
        for _ in range(budget_mod.MAX_POLLS):
            budget.charge_poll("login")
        snapshot = budget.snapshot()
        self.assertEqual(snapshot["polls"], budget_mod.MAX_POLLS)
        self.assertEqual(snapshot["calls"], 0)  # 10 polls did not eat the 3 calls
        budget.charge("search")  # data budget still intact
        self.assertEqual(budget.snapshot()["calls"], 1)
        budget.close()

    def test_poll_quota_exhausts(self):
        budget = self.open()
        for _ in range(budget_mod.MAX_POLLS):
            budget.charge_poll("login")
        with self.assertRaises(budget_mod.BudgetError) as caught:
            budget.charge_poll("login")
        self.assertEqual(caught.exception.code, "polls_exhausted")
        budget.close()

    def test_poll_is_refused_when_locked(self):
        budget = self.open()
        budget.lock("text:验证码", source="login")
        with self.assertRaises(budget_mod.BudgetError) as caught:
            budget.charge_poll("login")
        self.assertEqual(caught.exception.code, "batch_locked")
        budget.close()

    def test_login_cannot_relabel_around_a_lock(self):
        budget = self.open()
        budget.lock("text:请登录后查看", source="login")
        budget.close()
        with self.assertRaises(budget_mod.BudgetError):
            self.open(batch_id="login-attempt")

    # -- write failure means no network -----------------------------------
    def test_unwritable_state_dir_refuses_before_any_call(self):
        blocked = self.dir / "file_not_dir"
        blocked.write_text("x", encoding="utf-8")
        with self.assertRaises(budget_mod.BudgetError) as caught:
            budget_mod.open_budget(blocked, clock=self.clock)
        self.assertEqual(caught.exception.code, "budget_write_failed")

    def test_charge_failure_rolls_back_the_counter(self):
        budget = self.open()
        budget._conn.execute("PRAGMA query_only=ON")  # simulate a broken write path
        with self.assertRaises(budget_mod.BudgetError) as caught:
            budget.charge("search")
        self.assertEqual(caught.exception.code, "budget_write_failed")
        budget._conn.execute("PRAGMA query_only=OFF")
        self.assertEqual(budget.snapshot()["calls"], 0)
        budget.close()

    def test_ledger_records_charge_and_lock(self):
        budget = self.open()
        budget.charge("search", "https://www.zhihu.com/search?q=x")
        budget.lock("text:安全验证", source="search")
        budget.close()
        rows = budget_mod.read_ledger(self.dir, 20)
        kinds = [row["kind"] for row in rows]
        self.assertIn("charge", kinds)
        self.assertIn("lock", kinds)

    def test_relabel_writes_a_ledger_line(self):
        budget = self.open()
        budget.close()
        renamed = self.open(batch_id="second-label")
        renamed.close()
        rows = budget_mod.read_ledger(self.dir, 20)
        self.assertIn("relabel", [row["kind"] for row in rows])


if __name__ == "__main__":
    unittest.main()


def build_test_manifest(base_dir, clock, *, create=True):
    """Nine distinct temp sources plus the manifest that declares them."""
    base = pathlib.Path(base_dir) / "history"
    sources, manifest = [], []
    for spec in platform_mod.HISTORY_SOURCES:
        folder = base / spec["source_key"]
        if create:
            seed = budget_mod.open_budget(folder, clock=clock)
            seed.close()
        manifest.append({"source_key": spec["source_key"], "path": str(folder),
                         "classification": spec["classification"],
                         "may_be_absent": False, "reason": ""})
        sources.append({"source_key": spec["source_key"],
                        "path": str(folder / "budget.sqlite3"),
                        "classification": spec["classification"],
                        "note": "test fixture"})
    return sources, manifest


def satisfy_gate(ledger, base_dir, clock):
    """Give a temp ledger a snapshot built from an independent test manifest."""
    sources, manifest = build_test_manifest(base_dir, clock)
    return ledger.import_snapshot(sources, note="isolated test snapshot",
                                  manifest=manifest)


class PlatformLedgerTests(unittest.TestCase):
    """Site-scoped authority: caps, locks, provenance, concurrency, fail-closed."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = pathlib.Path(self._tmp.name)
        self.path = self.dir / "platform.sqlite3"

    def tearDown(self):
        self._tmp.cleanup()

    def ledger(self, **kwargs):
        led = platform_mod.PlatformLedger(self.path, allow_test_manifest=True, **kwargs)
        satisfy_gate(led, self.dir, kwargs.get("clock", time.time))
        return led

    def test_authorization_is_explicit_and_conflicts_are_refused(self):
        with self.ledger() as led:
            led.authorize_batch("b1", authorized_calls=3, window_seconds=300,
                                source="user-decision:2026-10-29", note="approved")
            same = led.authorize_batch("b1", authorized_calls=3, window_seconds=300,
                                       source="user-decision:2026-10-29")
            self.assertEqual(same["authorized_calls"], 3)
            with self.assertRaises(platform_mod.PlatformBudgetError) as caught:
                led.authorize_batch("b1", authorized_calls=9, window_seconds=300,
                                    source="sneaky")
            self.assertEqual(caught.exception.code, "batch_conflict")

    def test_charge_caps_at_the_authorized_number(self):
        clock = FakeClock()
        with self.ledger(clock=clock) as led:
            led.authorize_batch("b1", authorized_calls=2, window_seconds=300, source="u")
            self.assertEqual(led.charge("b1", "active_nav")["remaining"], 1)
            clock.advance(16)                       # the platform interval is 15 s
            self.assertEqual(led.charge("b1", "search")["remaining"], 0)
            clock.advance(16)                       # past the interval, cap is the blocker
            with self.assertRaises(platform_mod.PlatformBudgetError) as caught:
                led.charge("b1", "search")
            self.assertEqual(caught.exception.code, "calls_exhausted")
            self.assertEqual(led.summary("b1")["history_total_calls"], 2)

    def test_window_close_keeps_history_and_never_reopens(self):
        clock = FakeClock()
        with self.ledger(clock=clock) as led:
            led.authorize_batch("b1", authorized_calls=2, window_seconds=10, source="u")
            led.charge("b1", "active_nav")
            clock.advance(30)                       # past the window
            with self.assertRaises(platform_mod.PlatformBudgetError) as caught:
                led.charge("b1", "search")
            self.assertEqual(caught.exception.code, "batch_window_closed")
            summary = led.summary("b1")
            self.assertFalse(summary["window_open"])
            self.assertEqual(summary["history_total_calls"], 1)   # history kept
            self.assertEqual(len(led.events()), 1)

    def test_lock_survives_restart_and_a_new_state_dir(self):
        with self.ledger() as led:
            led.authorize_batch("b1", authorized_calls=3, window_seconds=300, source="u")
            led.lock("text:安全验证", source="weibo.login")
        # "restart" = brand new object on the same file; a new state dir changes
        # nothing because the authority is not keyed by state dir
        with platform_mod.PlatformLedger(self.path, allow_test_manifest=True) as reopened:
            locked, reason = reopened.locked()
            self.assertTrue(locked)
            self.assertIn("安全验证", reason)
            with self.assertRaises(platform_mod.PlatformBudgetError) as caught:
                reopened.charge("b1", "search")
            self.assertEqual(caught.exception.code, "platform_locked")

    def test_unreadable_ledger_fails_closed(self):
        led = self.ledger()
        real_conn = led._conn
        try:
            class Broken:
                def execute(self, *args, **kwargs):
                    import sqlite3 as _s
                    raise _s.OperationalError("disk gone")
            led._conn = Broken()
            locked, reason = led.locked()
            self.assertTrue(locked)
            self.assertTrue(str(reason).startswith("ledger_unavailable"))
        finally:
            led._conn = real_conn          # restore so close() can release the file
            led.close()

    def test_import_is_idempotent_and_never_counts(self):
        clock = FakeClock()
        sources, manifest = build_test_manifest(self.dir, clock)
        with platform_mod.PlatformLedger(self.path, clock=clock,
                                         allow_test_manifest=True) as led:
            first = led.import_snapshot(sources, manifest=manifest)
            self.assertEqual(first["status"], "recorded")
            again = led.import_snapshot(sources, manifest=manifest)
            self.assertEqual(again["status"], "unchanged")
            history = led.history_summary()
            self.assertEqual(history["pre_deducted_calls"], 0)   # fixture sources are empty
            # provenance adds no *new* events, but it is part of full history
            self.assertEqual(led.summary()["history_total_new_events"], 0)

    def test_concurrent_charges_never_exceed_the_cap(self):
        clock = FakeClock()
        with self.ledger(clock=clock) as led:
            led.authorize_batch("b1", authorized_calls=5, window_seconds=300, source="u")
            for _ in range(4):                       # 4 of 5 already used
                led.charge("b1", "search")
                clock.advance(16)
        ok, refused = [], []

        def worker():
            try:
                with platform_mod.PlatformLedger(self.path, clock=clock, allow_test_manifest=True) as own:
                    own.charge("b1", "search")
                ok.append(1)
            except platform_mod.PlatformBudgetError as exc:
                refused.append(exc.code)

        threads = [threading.Thread(target=worker) for _ in range(12)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(len(ok), 1)                 # exactly the last free slot
        self.assertTrue(refused)
        with platform_mod.PlatformLedger(self.path, clock=clock, allow_test_manifest=True) as check:
            self.assertEqual(check.summary("b1")["used"], 5)   # never above the cap


REPO = pathlib.Path(__file__).resolve().parents[1]
V10 = REPO / "docs" / "validation" / "v10"


def real_history_sources():
    """The audited pre-ledger sources (read-only; never written by tests)."""
    def src(rel, key, cls, note=""):
        return {"source_key": key, "path": str(V10 / rel / "budget.sqlite3"),
                "classification": cls, "note": note}

    out = [src(f"weibo-probe/state-probe{i}", f"probe{i}", "pre_deducted",
               "probe1: launch failure, no request observed" if i == 1 else "")
           for i in (1, 2, 3)]
    out += [src("weibo-login/state-login", "login-window-1", "uncharged_navigation",
                "active nav never charged; timestamp unknown"),
            src("weibo-verify/state-login", "login-window-2", "uncharged_navigation",
                "active nav never charged; timestamp unknown")]
    out += [src(f"weibo/checks/state_{name}", f"offline-{name}", "offline_check",
                "offline transport: no network")
            for name in ("login", "search", "detail", "comments")]
    return out


class PlatformHistoryGateTests(unittest.TestCase):
    """Importing history is a gate: real sources, or fail closed."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = pathlib.Path(self._tmp.name)
        self.path = self.dir / "platform.sqlite3"
        self.clock = FakeClock()

    def tearDown(self):
        self._tmp.cleanup()

    def ledger(self):
        return platform_mod.PlatformLedger(self.path, clock=self.clock,
                                           allow_test_manifest=True)

    def test_snapshot_classifies_the_real_history_without_counting_it(self):
        with self.ledger() as led:
            result = led.import_snapshot(real_history_sources(),
                                         note="audited 2026-10-29, read-only")
            self.assertEqual(result["status"], "recorded")
            history = led.history_summary()
            self.assertTrue(history["imported"])
            self.assertEqual(history["pre_deducted_calls"], 3)      # probe1-3
            self.assertEqual(history["offline_checks"], 4)          # 4 offline dirs
            self.assertEqual(history["uncharged_navigations"], 2)   # two logins
            self.assertEqual(led.summary()["history_total_new_events"], 0)
            self.assertGreaterEqual(led.summary()["history_total_calls"], 6)
            again = led.import_snapshot(real_history_sources())
            self.assertEqual(again["status"], "unchanged")

    def test_missing_source_fails_closed(self):
        sources, manifest = build_test_manifest(self.dir, self.clock)
        missing = pathlib.Path(manifest[0]["path"]) / "budget.sqlite3"
        missing.unlink()
        with self.ledger() as led:
            with self.assertRaises(platform_mod.PlatformBudgetError) as caught:
                led.import_snapshot(sources, manifest=manifest)
            self.assertEqual(caught.exception.code, "history_source_missing")
            self.assertFalse(led.history_summary()["imported"])

    def test_corrupt_source_fails_closed(self):
        sources, manifest = build_test_manifest(self.dir, self.clock)
        bad = pathlib.Path(manifest[0]["path"]) / "budget.sqlite3"
        bad.write_bytes(b"not a database at all")
        with self.ledger() as led:
            with self.assertRaises(platform_mod.PlatformBudgetError) as caught:
                led.import_snapshot(sources, manifest=manifest)
            self.assertEqual(caught.exception.code, "history_source_unreadable")

    def test_wal_sidecar_is_treated_as_uncertain(self):
        sources, manifest = build_test_manifest(self.dir, self.clock)
        sidecar = pathlib.Path(str(pathlib.Path(manifest[0]["path"])
                                   / "budget.sqlite3") + "-wal")
        sidecar.write_bytes(b"pending frames")
        with self.ledger() as led:
            with self.assertRaises(platform_mod.PlatformBudgetError) as caught:
                led.import_snapshot(sources, manifest=manifest)
            self.assertEqual(caught.exception.code, "history_wal_uncertain")

    def test_snapshot_may_not_point_two_keys_at_one_source(self):
        sources, manifest = build_test_manifest(self.dir, self.clock)
        manifest[1]["path"] = manifest[0]["path"]        # same canonical path
        with self.ledger() as led:
            with self.assertRaises(platform_mod.PlatformBudgetError) as caught:
                led.import_snapshot(sources, manifest=manifest)
            self.assertEqual(caught.exception.code,
                             "history_manifest_duplicate_path")


class PlatformGateBehaviourTests(unittest.TestCase):
    """The gate is enforced inside charge: history, change, locks, seeds."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = pathlib.Path(self._tmp.name)
        self.path = self.dir / "platform.sqlite3"
        self.clock = FakeClock()
        self.sources, self.manifest = build_test_manifest(self.dir, self.clock)

    def tearDown(self):
        self._tmp.cleanup()

    def ledger(self, **kwargs):
        led = platform_mod.PlatformLedger(self.path, clock=self.clock,
                                          allow_test_manifest=True, **kwargs)
        led.import_snapshot(self.sources, manifest=self.manifest)
        return led

    def folder(self, key="probe1"):
        return pathlib.Path(next(m["path"] for m in self.manifest
                                 if m["source_key"] == key))

    def mutate(self, key="probe1", *, lock=False, reason="text:安全验证"):
        batch = budget_mod.open_budget(self.folder(key), clock=self.clock)
        try:
            self.clock.advance(16)
            batch.charge("search", "https://m.weibo.cn/search")
            if lock:
                batch.lock(reason, source="search")
        finally:
            batch.close()

    def test_charge_refuses_without_an_imported_snapshot(self):
        with platform_mod.PlatformLedger(self.path, clock=self.clock,
                                         allow_test_manifest=True) as led:
            led.authorize_batch("b1", authorized_calls=3, window_seconds=300, source="u")
            with self.assertRaises(platform_mod.PlatformBudgetError) as caught:
                led.charge("b1", "search")
            self.assertEqual(caught.exception.code, "history_gate_unsatisfied")

    def test_charge_refuses_after_a_source_changes(self):
        with self.ledger() as led:
            led.authorize_batch("b1", authorized_calls=3, window_seconds=300, source="u")
            led.charge("b1", "search")
            self.clock.advance(20)
            self.mutate("probe1")                    # the real source changed
            with self.assertRaises(platform_mod.PlatformBudgetError) as caught:
                led.charge("b1", "search")
            self.assertEqual(caught.exception.code, "history_source_changed")

    def test_locked_source_is_inherited_and_blocks_the_charge(self):
        with self.ledger() as led:
            led.authorize_batch("b1", authorized_calls=3, window_seconds=300, source="u")
            self.mutate("probe1", lock=True)         # source becomes locked
            with self.assertRaises(platform_mod.PlatformBudgetError) as caught:
                led.charge("b1", "search")
            self.assertEqual(caught.exception.code, "history_locked")
            locked, reason = led.locked()
            self.assertTrue(locked)                  # persisted atomically
            self.assertIn("安全验证", str(reason))
            self.assertEqual(led.summary("b1")["used"], 0)

    def test_wal_appearing_after_the_import_blocks_the_charge(self):
        with self.ledger() as led:
            led.authorize_batch("b1", authorized_calls=3, window_seconds=300, source="u")
            sidecar = pathlib.Path(str(self.folder("probe2") / "budget.sqlite3") + "-wal")
            sidecar.write_bytes(b"pending frames")
            with self.assertRaises(platform_mod.PlatformBudgetError) as caught:
                led.charge("b1", "search")
            self.assertEqual(caught.exception.code, "history_wal_uncertain")

    def test_two_occurred_logins_force_remaining_one(self):
        with self.ledger() as led:
            led.authorize_batch("weibo-verify-1", authorized_calls=3, window_seconds=300,
                                source="user-decision",
                                seed_from=("login-window-1", "login-window-2"))
            summary = led.summary("weibo-verify-1")
            self.assertEqual(summary["used"], 2)        # derived from the audit
            self.assertEqual(summary["remaining"], 1)   # enforced, not narrated
            led.charge("weibo-verify-1", "search")
            self.assertEqual(led.summary("weibo-verify-1")["remaining"], 0)
            self.clock.advance(20)
            with self.assertRaises(platform_mod.PlatformBudgetError) as caught:
                led.charge("weibo-verify-1", "search")
            self.assertEqual(caught.exception.code, "calls_exhausted")

    def test_seeded_usage_is_not_filtered_by_the_window(self):
        with self.ledger() as led:
            led.authorize_batch("b1", authorized_calls=3, window_seconds=300, source="u",
                                seed_from=("login-window-1", "login-window-2"))
            self.clock.advance(301)
            summary = led.summary("b1")
            self.assertEqual(summary["used"], 2)        # seed survives the window
            self.assertFalse(summary["window_open"])
            with self.assertRaises(platform_mod.PlatformBudgetError) as caught:
                led.charge("b1", "search")
            self.assertEqual(caught.exception.code, "batch_window_closed")

    def test_history_total_counts_seeded_and_imported_activity(self):
        with self.ledger() as led:
            led.authorize_batch("b1", authorized_calls=5, window_seconds=300, source="u",
                                seed_from=("login-window-1", "login-window-2"))
            total = led.summary()["history_total_calls"]
            self.assertGreaterEqual(total, 2)


class PlatformLimitsTests(unittest.TestCase):
    """15 s interval / 5 records / 300 s window, shared by every state dir."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = pathlib.Path(self._tmp.name)
        self.path = self.dir / "platform.sqlite3"
        self.clock = FakeClock()
        gate = platform_mod.PlatformLedger(self.path, clock=self.clock,
                                           allow_test_manifest=True)
        satisfy_gate(gate, self.dir, self.clock)
        gate.close()

    def tearDown(self):
        self._tmp.cleanup()

    def test_interval_is_enforced_across_two_state_dirs(self):
        with platform_mod.PlatformLedger(self.path, clock=self.clock, allow_test_manifest=True) as led:
            led.authorize_batch("b1", authorized_calls=3, window_seconds=300, source="u")
            led.charge("b1", "search", detail="/search")
        # a second "state dir" = a second ledger object on the same authority
        with platform_mod.PlatformLedger(self.path, clock=self.clock, allow_test_manifest=True) as other:
            with self.assertRaises(platform_mod.PlatformBudgetError) as caught:
                other.charge("b1", "search", detail="/search")
            self.assertEqual(caught.exception.code, "interval_not_elapsed")
            self.clock.advance(16)
            other.charge("b1", "search", detail="/search")
            self.assertEqual(other.summary("b1")["used"], 2)

    def test_records_cap_is_shared_and_soft(self):
        """v11：目标 5 条，但写第 6 条不再报错，只回报 over_cap/over_by。"""
        with platform_mod.PlatformLedger(self.path, clock=self.clock, allow_test_manifest=True) as led:
            led.authorize_batch("b1", authorized_calls=3, window_seconds=300, source="u")
            led.reserve_records("b1", 3)
            led.reserve_records("b1", 2)
            over = led.reserve_records("b1", 1)
            self.assertEqual(over["records_target"], 5)
            self.assertEqual(over["records_used"], 6)
            self.assertTrue(over["over_cap"])
            self.assertEqual(over["over_by"], 1)
            self.assertEqual(led.summary("b1")["records_reserved"], 6)

    def test_window_and_started_at_survive_a_restart(self):
        with platform_mod.PlatformLedger(self.path, clock=self.clock, allow_test_manifest=True) as led:
            led.authorize_batch("b1", authorized_calls=2, window_seconds=300, source="u")
            started = led.summary("b1")["started_at"]
        self.clock.advance(301)
        with platform_mod.PlatformLedger(self.path, clock=self.clock, allow_test_manifest=True) as reopened:
            summary = reopened.summary("b1")
            self.assertEqual(summary["started_at"], started)   # not refreshed
            self.assertFalse(summary["window_open"])
            with self.assertRaises(platform_mod.PlatformBudgetError) as caught:
                reopened.charge("b1", "search")
            self.assertEqual(caught.exception.code, "batch_window_closed")

    def test_lock_check_lives_inside_the_charge_transaction(self):
        import inspect

        source = inspect.getsource(platform_mod.PlatformLedger.charge)
        self.assertNotIn("self.locked()", source)      # no pre-transaction peek
        self.assertIn("BEGIN IMMEDIATE", source)
        self.assertLess(source.index("BEGIN IMMEDIATE"),
                        source.index("_lock_inside_txn"))


class PlatformDeclarationTests(unittest.TestCase):
    """The stored manifest must match the fixed declaration, and production
    batches must bind the two logins that already happened."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = pathlib.Path(self._tmp.name)
        self.path = self.dir / "platform.sqlite3"
        self.clock = FakeClock()

    def tearDown(self):
        self._tmp.cleanup()

    def test_production_batch_must_bind_the_two_logins(self):
        with platform_mod.PlatformLedger(self.path, clock=self.clock) as led:
            led.import_snapshot(real_history_sources(),
                                note="audited real snapshot, read-only")
            with self.assertRaises(platform_mod.PlatformBudgetError) as caught:
                led.authorize_batch("weibo-verify-1", authorized_calls=3,
                                    window_seconds=300, source="user-decision")
            self.assertEqual(caught.exception.code, "seed_association_incomplete")
            row = led.authorize_batch(
                "weibo-verify-1", authorized_calls=3, window_seconds=300,
                source="user-decision",
                seed_from=("login-window-1", "login-window-2"))
            self.assertEqual(row["seed_used"], 2)
            self.assertEqual(led.summary("weibo-verify-1")["remaining"], 1)

    def test_disguised_classification_is_refused(self):
        sources, manifest = build_test_manifest(self.dir, self.clock)
        manifest[0]["classification"] = "uncharged_navigation"   # disguise
        with platform_mod.PlatformLedger(self.path, clock=self.clock,
                                         allow_test_manifest=True) as led:
            led.import_snapshot(sources, manifest=manifest)
            led.authorize_batch("b1", authorized_calls=3, window_seconds=300, source="u")
            with self.assertRaises(platform_mod.PlatformBudgetError) as caught:
                led.charge("b1", "search")
            self.assertEqual(caught.exception.code, "history_manifest_invalid")

    def test_missing_or_extra_key_is_refused(self):
        sources, manifest = build_test_manifest(self.dir, self.clock)
        with platform_mod.PlatformLedger(self.path, clock=self.clock,
                                         allow_test_manifest=True) as led:
            dropped = manifest[:-1]
            led.import_snapshot(sources[:-1], manifest=dropped)
            led.authorize_batch("b1", authorized_calls=3, window_seconds=300, source="u")
            with self.assertRaises(platform_mod.PlatformBudgetError) as caught:
                led.charge("b1", "search")
            self.assertEqual(caught.exception.code, "history_manifest_invalid")
            self.assertIn("missing", caught.exception.detail)

    def test_duplicate_key_is_refused(self):
        sources, manifest = build_test_manifest(self.dir, self.clock)
        manifest[1]["source_key"] = manifest[0]["source_key"]
        with platform_mod.PlatformLedger(self.path, clock=self.clock,
                                         allow_test_manifest=True) as led:
            with self.assertRaises(platform_mod.PlatformBudgetError) as caught:
                led.import_snapshot(sources, manifest=manifest)
            self.assertIn(caught.exception.code,
                          ("history_manifest_duplicate_path", "history_spec_invalid",
                           "history_manifest_invalid", "history_source_undeclared"))
