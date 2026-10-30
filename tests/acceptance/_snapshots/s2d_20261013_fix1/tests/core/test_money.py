"""Money rules (contract §0.3): integer minor units, half-up rounding, no floats."""

from __future__ import annotations

import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from app.core.money import apply_rate, format_minor, labor_minor, minor_int, yuan_to_minor  # noqa: E402


class MoneyTest(unittest.TestCase):
    def test_yuan_to_minor_exact(self):
        self.assertEqual(yuan_to_minor("9.90"), 990)
        self.assertEqual(yuan_to_minor("0"), 0)
        self.assertEqual(yuan_to_minor("33.33"), 3333)

    def test_yuan_rejects_bad_shapes(self):
        for bad in ("12.345", "-9.90", "1,000", "¥9.9", "1e2", "", "abc"):
            with self.assertRaises(ValueError, msg=bad):
                yuan_to_minor(bad)

    def test_minor_int_rejects_bool_and_negative(self):
        self.assertEqual(minor_int(0), 0)
        self.assertEqual(minor_int("1500"), 1500)
        with self.assertRaises(ValueError):
            minor_int(True)
        with self.assertRaises(ValueError):
            minor_int(-1)
        with self.assertRaises(ValueError):
            minor_int(1.5)

    def test_rate_rounding_half_up(self):
        # 9.90 元 × 500bp = 50 分；33.33 元 × 500bp = 167 分（½ 分向上）
        self.assertEqual(apply_rate(990, 500), 50)
        self.assertEqual(apply_rate(3333, 500), 167)

    def test_labor_rounding(self):
        # 15 分钟 × 3000 分/时 = 750 分
        self.assertEqual(labor_minor(15, 3000), 750)
        self.assertEqual(labor_minor(10, 3000), 500)

    def test_unknown_vs_zero_display(self):
        self.assertEqual(format_minor(None), "未知")
        self.assertEqual(format_minor(0), "¥0.00")
        self.assertEqual(format_minor(190), "¥1.90")

    def test_derived_negative_is_not_produced_by_inputs(self):
        with self.assertRaises(ValueError):
            apply_rate(-1, 500)
        with self.assertRaises(ValueError):
            labor_minor(-1, 3000)


if __name__ == "__main__":
    unittest.main()
