"""v11：记录数从硬上限改软目标 —— 三平台账本一致性 + 硬护栏不变。"""

from __future__ import annotations

import pathlib
import tempfile
import unittest

from tools.selection.access import douyin
from tools.selection.access import platform_budget as pb
from tools.selection.access import tieba


COLLECTED = "2026-10-30T00:00:00Z"


class _Base(unittest.TestCase):
    """每个子类提供 `make(path)` -> 账本；统一做超额/刚好/不足三档断言。"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = pathlib.Path(self._tmp.name)
        self._ledgers = []

    def tearDown(self):
        for led in self._ledgers:
            try:
                led.close()
            except Exception:
                pass
        self._tmp.cleanup()

    def ledger(self, name="led.sqlite3"):
        led = self.make(self.dir / name)
        self._ledgers.append(led)
        return led

    # 子类实现
    def make(self, path):                      # pragma: no cover - 由子类覆盖
        raise NotImplementedError

    def authorize(self, led, batch_id, *, records_cap=5):
        led.authorize_batch(batch_id, authorized_calls=6, window_seconds=300,
                            source="test", records_cap=records_cap)


class PlatformBudgetSoftCapTests(_Base):
    def make(self, path):
        return pb.PlatformLedger(path, allow_test_manifest=True)

    def test_three_times_target(self):
        led = self.ledger()
        self.authorize(led, "b1", records_cap=5)
        led.reserve_records("b1", 15)
        out = led.reserve_records("b1", 0 + 0) if False else None
        summary = led.summary("b1")
        self.assertEqual(summary["records_reserved"], 15)
        over = led.reserve_records("b1", 1)
        self.assertTrue(over["over_cap"])
        self.assertEqual(over["over_by"], 11)          # 16 - 5

    def test_exactly_target(self):
        led = self.ledger()
        self.authorize(led, "b2", records_cap=5)
        out = led.reserve_records("b2", 5)
        self.assertFalse(out["over_cap"])
        self.assertEqual(out["over_by"], 0)

    def test_below_target(self):
        led = self.ledger()
        self.authorize(led, "b3", records_cap=5)
        out = led.reserve_records("b3", 2)
        self.assertFalse(out["over_cap"])
        self.assertEqual(out["records_used"], 2)

    def test_large_target_accepted(self):
        led = self.ledger()
        batch = led.authorize_batch("b4", authorized_calls=6, window_seconds=300,
                                    source="test", records_cap=500)
        self.assertEqual(batch["records_cap"], 500)
        out = led.reserve_records("b4", 58)
        self.assertFalse(out["over_cap"])


class DouyinSoftCapTests(_Base):
    def make(self, path):
        return douyin.open_ledger(path)

    def authorize(self, led, batch_id, *, records_cap=5):
        led.authorize_batch(batch_id, authorized_calls=6, window_seconds=300,
                            source="test", records_cap=records_cap)

    def test_three_times_target(self):
        led = self.ledger()
        self.authorize(led, "d1", records_cap=5)
        led.reserve_records("d1", 15)
        over = led.reserve_records("d1", 1)
        self.assertTrue(over["over_cap"])
        self.assertEqual(over["over_by"], 11)
        self.assertEqual(over["records_used"], 16)

    def test_exactly_and_below(self):
        led = self.ledger()
        self.authorize(led, "d2", records_cap=5)
        out = led.reserve_records("d2", 5)
        self.assertFalse(out["over_cap"])
        self.assertEqual(out["over_by"], 0)

    def test_large_target_accepted(self):
        led = self.ledger()
        batch = led.authorize_batch("d3", authorized_calls=6, window_seconds=300,
                                    source="test", records_cap=100)
        self.assertEqual(batch["records_cap"], 100)


class TiebaSoftCapTests(_Base):
    def make(self, path):
        return tieba.open_ledger(path)

    def test_three_times_target(self):
        led = self.ledger()
        led.authorize_batch("t1", authorized_calls=6, window_seconds=300,
                            source="test", records_cap=5)
        led.reserve_records("t1", 15)
        over = led.reserve_records("t1", 1)
        self.assertTrue(over["over_cap"])
        self.assertEqual(over["over_by"], 11)
        self.assertEqual(over["records_used"], 16)
        self.assertEqual(over["records_target"], 5)

    def test_exactly_target(self):
        led = self.ledger()
        led.authorize_batch("t2", authorized_calls=6, window_seconds=300,
                            source="test", records_cap=5)
        out = led.reserve_records("t2", 5)
        self.assertFalse(out["over_cap"])
        self.assertEqual(out["over_by"], 0)

    def test_legacy_batch_with_cap_five_is_readable(self):
        led = self.ledger()
        led.authorize_batch("t3", authorized_calls=6, window_seconds=300,
                            source="test", records_cap=5)
        summary = led.summary("t3")
        self.assertEqual(summary["records_cap"], 5)      # 旧语义的列仍可读
        self.assertEqual(summary["used"], 0)


class HardGuardrailsUnchangedTests(unittest.TestCase):
    """记录上限放松，但调用次数/间隔/窗口/风险锁必须仍是硬的。"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = pathlib.Path(self._tmp.name)
        self.now = 1000.0
        self.ledgers = []

    def tearDown(self):
        for led in self.ledgers:
            try:
                led.close()
            except Exception:
                pass
        self._tmp.cleanup()

    def _tieba(self):
        led = tieba.open_ledger(self.dir / "t.sqlite3", clock=lambda: self.now)
        self.ledgers.append(led)
        return led

    def test_calls_limit_is_hard(self):
        led = self._tieba()
        led.authorize_batch("h1", authorized_calls=2, window_seconds=300, source="t")
        led.charge("h1", "search")
        self.now += 20
        led.charge("h1", "search")
        self.now += 20
        with self.assertRaises(tieba.TiebaBudgetError) as caught:
            led.charge("h1", "search")
        self.assertEqual(caught.exception.code, "quota_exceeded")

    def test_interval_is_hard_and_does_not_charge(self):
        led = self._tieba()
        led.authorize_batch("h2", authorized_calls=3, window_seconds=300, source="t")
        led.charge("h2", "search")
        with self.assertRaises(tieba.TiebaBudgetError) as caught:
            led.charge("h2", "search")
        self.assertEqual(caught.exception.code, "interval_not_elapsed")
        self.assertEqual(led.summary("h2")["used"], 1)     # 被拒的不扣费

    def test_window_is_hard(self):
        led = self._tieba()
        led.authorize_batch("h3", authorized_calls=3, window_seconds=60, source="t")
        self.now += 61
        with self.assertRaises(tieba.TiebaBudgetError) as caught:
            led.charge("h3", "search")
        self.assertEqual(caught.exception.code, "window_closed")

    def test_risk_lock_is_hard(self):
        led = self._tieba()
        led.authorize_batch("h4", authorized_calls=3, window_seconds=300, source="t")
        led.lock("text:安全验证", source="test")
        with self.assertRaises(tieba.TiebaBudgetError) as caught:
            led.charge("h4", "search")
        self.assertEqual(caught.exception.code, "site_locked")


if __name__ == "__main__":
    unittest.main()
