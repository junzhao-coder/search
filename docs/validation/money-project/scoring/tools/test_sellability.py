#!/usr/bin/env python
"""Pure unit checks for the sellability rule and weighted total."""

from __future__ import annotations

import copy
import json
import pathlib
import sys
import unittest

BASE = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))
import scorer  # noqa: E402


def item(title: str, platform: str = "x", price=None) -> dict:
    payload = {
        "platform": platform,
        "item_id": "probe",
        "title": title,
        "url": "https://example.test/probe",
        "author": "@probe",
        "published_at": "2026-01-01T00:00:00Z",
        "metrics": {"source": "unit-test", "demand_raw": 1, "demand_basis": "test", "raw": {}},
    }
    if price is not None:
        payload["price"] = price
    return payload


class SellabilityRuleTests(unittest.TestCase):
    def test_free_giveaway_is_low(self):
        profile = scorer.sellability_profile(item("FREE Notion template giveaway for students"))
        self.assertLessEqual(profile["norm"], 0.2)
        self.assertIn("free", profile["reason"])

    def test_free_shipping_and_freedom_are_not_free_giveaway(self):
        self.assertEqual(scorer.sellability_profile(item("Notion template with free shipping"))["norm"], 0.5)
        self.assertEqual(scorer.sellability_profile(item("freedom to organize your notes"))["norm"], 0.5)

    def test_price_and_purchase_is_high(self):
        profile = scorer.sellability_profile(item("Selling for $14 on Gumroad — buy now"))
        self.assertGreaterEqual(profile["norm"], 0.8)
        self.assertTrue(profile["flags"]["price"])
        self.assertTrue(profile["flags"]["purchase"])

    def test_no_signal_is_neutral_and_xianyu_price_is_capped(self):
        self.assertEqual(scorer.sellability_profile(item("a notion template thread"))["norm"], 0.5)
        xy = scorer.sellability_profile(item("AI模板 合集", platform="xianyu", price="¥1"))
        self.assertGreaterEqual(xy["norm"], 0.5)
        self.assertLessEqual(xy["norm"], 0.6)
        self.assertIn("引流价", xy["reason"])

    def test_weighted_total_recomputed(self):
        probe = item("Selling for $14 on Gumroad — buy now")
        row = scorer.score_items([probe])[0]
        field_map = {
            "demand_strength": "demand_norm",
            "competition_sparsity": "competition_norm",
            "gross_margin": "margin_norm",
            "fulfillment_ease": "fulfillment_norm",
            "compliance_safety": "compliance_norm",
            "replicability": "replicability_norm",
            "sellability": "sellability_norm",
        }
        present = [k for k in scorer.WEIGHTS if row.get(field_map[k]) is not None]
        weighted = sum(scorer.WEIGHTS[k] * row[field_map[k]] for k in present)
        denom = sum(scorer.WEIGHTS[k] for k in present)
        self.assertAlmostEqual(row["total_score"], round(weighted / denom, 6), places=6)
        self.assertAlmostEqual(sum(scorer.WEIGHTS.values()), 1.0, places=9)


if __name__ == "__main__":
    unittest.main()
