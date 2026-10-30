"""Identity rules (contract §4.5): normalization, fingerprints, URL rules, namespaced keys."""

from __future__ import annotations

import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from app.core.identity import (  # noqa: E402
    candidate_identity_key,
    content_hash,
    demand_identity_key,
    normalize,
    title_norm_hash,
    url_norm,
)


class IdentityTest(unittest.TestCase):
    def test_normalize_collapses_and_lowercases_ascii(self):
        self.assertEqual(normalize("  Hello   World  "), "hello world")
        self.assertEqual(normalize("ＡＢＣ　１２３"), "abc 123")
        self.assertEqual(normalize("模板  合集"), "模板 合集")

    def test_title_norm_hash_is_stable(self):
        self.assertEqual(title_norm_hash("A  B"), title_norm_hash("a b"))
        self.assertEqual(len(title_norm_hash("示例")), 32)

    def test_content_hash_changes_with_excerpt(self):
        first = content_hash("求模板", "标题")
        self.assertEqual(first, content_hash("求模板", "标题"))
        self.assertNotEqual(first, content_hash("求模板2", "标题"))

    def test_url_norm_drops_tracking_and_sorts_params(self):
        raw = "HTTPS://Example.COM:443/a/B?b=2&utm_source=x&a=1#frag"
        self.assertEqual(url_norm(raw), "https://example.com/a/B?a=1&b=2")
        self.assertEqual(url_norm("http://example.com:80/x?spm=1&z=9"), "http://example.com/x?z=9")

    def test_identity_keys_are_namespaced(self):
        key, source = demand_identity_key("s_xianyu", "1001", "https://example.com/x")
        self.assertEqual(key, "n:s_xianyu:1001")
        self.assertEqual(source, "demand_native_id")
        url_key, url_source = demand_identity_key("s_bili", None, "https://example.com/x")
        self.assertEqual(url_key, "u:s_bili:https://example.com/x")
        self.assertEqual(url_source, "demand_url")

    def test_candidate_identity_reuses_demand_then_title(self):
        self.assertEqual(candidate_identity_key("n:s_xianyu:1001", "h"), ("n:s_xianyu:1001", "demand_native_id"))
        key, source = candidate_identity_key(None, "hash123")
        self.assertEqual((key, source), ("t:hash123", "title"))

    def test_distinct_sources_same_native_id_are_distinct_candidates(self):
        a, _ = demand_identity_key("s_xianyu", "1001", "")
        b, _ = demand_identity_key("s_bili", "1001", "")
        self.assertNotEqual(a, b)


if __name__ == "__main__":
    unittest.main()
