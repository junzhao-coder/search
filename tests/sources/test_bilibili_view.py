"""Bilibili known-object completion: offline replay, mapping, cache and no-network rules."""

from __future__ import annotations

import datetime as _dt
import json
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from app.core.identity import content_hash, url_norm  # noqa: E402
from app.sources.bilibili_view import (  # noqa: E402
    API_URL,
    CANONICAL_URL,
    EXCERPT_MAX,
    BilibiliViewReader,
    resolve_target,
)

FIXTURES = pathlib.Path(__file__).resolve().parents[1] / "fixtures" / "sources"
CST = _dt.timezone(_dt.timedelta(hours=8))
BVID = "BV1us8MzPEmn"
CLOCK_START = 1_760_000_000.0


def _load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


class FakeClock:
    def __init__(self, now: float):
        self.now = now

    def __call__(self) -> float:
        return self.now


class RecordingTransport:
    """Fake transport: records request URLs, returns one canned envelope."""

    def __init__(self, envelope: dict):
        self.calls: list[str] = []
        self.envelope = envelope

    def __call__(self, url: str) -> dict:
        self.calls.append(url)
        return dict(self.envelope)


class BilibiliViewReaderTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ok_fixture = _load("bilibili_view_ok_BV1us8MzPEmn.json")
        cls.failures = _load("bilibili_view_failures.json")
        cls.ok_envelope = cls.ok_fixture["transport"]

    def _reader(self, envelope: dict | None = None, *, now: float = CLOCK_START):
        transport = RecordingTransport(envelope if envelope is not None else self.ok_envelope)
        clock = FakeClock(now)
        return BilibiliViewReader(transport, clock=clock), transport, clock

    def _clone_ok(self) -> dict:
        return json.loads(json.dumps(self.ok_envelope))

    # --- fixtures ---------------------------------------------------------

    def test_fixtures_declare_provenance(self):
        ok_meta = self.ok_fixture["_fixture"]
        self.assertEqual(ok_meta["kind"], "real_excerpt")
        self.assertFalse(ok_meta["is_complete_raw_response"])
        self.assertIn("S3_PROBES", ok_meta["provenance"])
        fail_meta = self.failures["_fixture"]
        self.assertEqual(fail_meta["kind"], "synthetic_failures")
        self.assertFalse(fail_meta["is_real_log"])

    # --- happy path -------------------------------------------------------

    def test_ok_record_uses_contract_fields(self):
        reader, transport, _ = self._reader()
        record = reader.complete(BVID)
        self.assertEqual(record["outcome"], "ok")
        self.assertEqual(record["source_name"], "bilibili")
        self.assertEqual(record["native_id"], BVID)
        self.assertEqual(record["identity_key"], f"n:bilibili:{BVID}")
        self.assertEqual(record["identity_source"], "demand_native_id")
        self.assertEqual(record["title"], "拼多多全域虚拟电商从零到1实操课")
        self.assertTrue(record["excerpt"].startswith("拼多多全域虚拟电商"))
        self.assertEqual(record["signal_kind"], "other")
        self.assertEqual(record["published_at"], "2025-07-24T17:39:41+08:00")
        self.assertEqual(record["original_author"], "有趣知识八分饱")
        self.assertEqual(json.loads(record["engagement_json"])["view"], 5125)
        self.assertEqual(record["unknown_fields"], [])
        self.assertEqual(record["url"], CANONICAL_URL.format(bvid=BVID))
        self.assertEqual(record["url_norm"], "https://www.bilibili.com/video/BV1us8MzPEmn/")
        self.assertEqual(record["content_hash"], content_hash(record["excerpt"], record["title"]))
        self.assertEqual(record["request_url"], API_URL.format(bvid=BVID))
        self.assertEqual(transport.calls, [API_URL.format(bvid=BVID)])

    def test_observed_at_defaults_to_import_time_and_is_not_pubdate(self):
        reader, _, clock = self._reader(now=CLOCK_START)
        record = reader.complete(BVID)
        expected = _dt.datetime.fromtimestamp(clock.now, CST).isoformat(timespec="seconds")
        self.assertEqual(record["observed_at"], expected)
        self.assertEqual(record["observed_at_source"], "import_time")
        self.assertNotEqual(record["observed_at"], record["published_at"])
        self.assertNotIn("observed_at_rejected", record)

    # --- observed_at validation -------------------------------------------

    def test_explicit_observed_at_accepts_z_and_offset(self):
        for stamp in ("2026-10-14T13:05:10Z", "2026-10-14T13:05:10+08:00"):
            with self.subTest(stamp=stamp):
                reader, _, _ = self._reader()
                record = reader.complete(BVID, observed_at=stamp)
                self.assertEqual(record["observed_at"], stamp)
                self.assertEqual(record["observed_at_source"], "source")
                self.assertNotIn("observed_at_rejected", record)

    def test_invalid_observed_at_falls_back_and_is_recorded(self):
        bad_stamps = [
            "2026-10-14 13:05:10",
            "2026-10-14T13:05:10",
            "2026-10-14T13:05+08:00",
            "2026-02-30T00:00:00+08:00",
            "2026-13-01T00:00:00+08:00",
        ]
        for stamp in bad_stamps:
            with self.subTest(stamp=stamp):
                reader, _, clock = self._reader(now=CLOCK_START)
                record = reader.complete(BVID, observed_at=stamp)
                expected = _dt.datetime.fromtimestamp(clock.now, CST).isoformat(timespec="seconds")
                self.assertEqual(record["observed_at"], expected)
                self.assertEqual(record["observed_at_source"], "import_time")
                self.assertEqual(record["observed_at_rejected"], stamp)

    # --- hash semantics ---------------------------------------------------

    def test_stat_change_does_not_change_hash(self):
        reader, _, _ = self._reader()
        first = reader.complete(BVID)["content_hash"]
        changed = self._clone_ok()
        changed["payload"]["data"]["stat"]["view"] = 999999
        other, _, _ = self._reader(envelope=changed)
        self.assertEqual(first, other.complete(BVID)["content_hash"])

    def test_observed_at_change_does_not_change_hash(self):
        reader, _, _ = self._reader()
        first = reader.complete(BVID, observed_at="2026-10-01T00:00:00+08:00")["content_hash"]
        second = reader.complete(BVID, observed_at="2026-10-14T13:05:10+08:00")["content_hash"]
        self.assertEqual(first, second)

    def test_excerpt_change_changes_hash(self):
        reader, _, _ = self._reader()
        first = reader.complete(BVID)["content_hash"]
        changed = self._clone_ok()
        changed["payload"]["data"]["desc"] = "完全不同的正文摘录"
        other, _, _ = self._reader(envelope=changed)
        self.assertNotEqual(first, other.complete(BVID)["content_hash"])

    # --- degraded payloads and type checks --------------------------------

    def test_missing_desc_falls_back_to_title(self):
        envelope = self._clone_ok()
        envelope["payload"]["data"].pop("desc")
        reader, _, _ = self._reader(envelope=envelope)
        record = reader.complete(BVID)
        self.assertEqual(record["outcome"], "ok")
        self.assertEqual(record["excerpt"], record["title"])
        self.assertNotIn("desc_malformed", record["unknown_fields"])

    def test_desc_non_string_falls_back_to_title(self):
        envelope = self._clone_ok()
        envelope["payload"]["data"]["desc"] = ["not", "a", "string"]
        reader, _, _ = self._reader(envelope=envelope)
        record = reader.complete(BVID)
        self.assertEqual(record["outcome"], "ok")
        self.assertEqual(record["excerpt"], record["title"])
        self.assertIn("desc_malformed", record["unknown_fields"])

    def test_title_must_be_nonempty_string(self):
        for bad_title in ("   ", 123, ["标题"], ""):
            with self.subTest(title=repr(bad_title)):
                envelope = self._clone_ok()
                envelope["payload"]["data"]["title"] = bad_title
                reader, transport, _ = self._reader(envelope=envelope)
                record = reader.complete(BVID)
                self.assertEqual(record["outcome"], "failed")
                self.assertIn("missing_title", record["failure_reason"])
                self.assertNotIn("identity_key", record)
                self.assertEqual(len(transport.calls), 1)

    def test_payload_not_dict_fails_cleanly(self):
        envelope = {"http_status": 200, "app_code": 0, "app_message": "OK", "error": None,
                    "payload": "<!DOCTYPE html><html></html>"}
        reader, _, _ = self._reader(envelope=envelope)
        record = reader.complete(BVID)
        self.assertEqual(record["outcome"], "failed")
        self.assertIn("unexpected_response", record["failure_reason"])
        self.assertNotIn("identity_key", record)

    def test_data_not_dict_fails_cleanly(self):
        envelope = self._clone_ok()
        envelope["payload"]["data"] = "<html>"
        reader, _, _ = self._reader(envelope=envelope)
        record = reader.complete(BVID)
        self.assertEqual(record["outcome"], "failed")
        self.assertIn("unexpected_response", record["failure_reason"])

    def test_bvid_mismatch_fails_without_identity(self):
        envelope = self._clone_ok()
        envelope["payload"]["data"]["bvid"] = "BV1xx411c7mD"
        reader, transport, _ = self._reader(envelope=envelope)
        record = reader.complete(BVID)
        self.assertEqual(record["outcome"], "failed")
        self.assertIn("bvid_mismatch", record["failure_reason"])
        self.assertNotIn("identity_key", record)
        self.assertNotIn("url", record)
        self.assertEqual(len(transport.calls), 1)

    def test_missing_bvid_field_fails_without_identity(self):
        envelope = self._clone_ok()
        envelope["payload"]["data"].pop("bvid")
        reader, _, _ = self._reader(envelope=envelope)
        record = reader.complete(BVID)
        self.assertEqual(record["outcome"], "failed")
        self.assertIn("bvid_mismatch", record["failure_reason"])
        self.assertNotIn("identity_key", record)

    def test_owner_malformed_stays_unknown(self):
        envelope = self._clone_ok()
        envelope["payload"]["data"]["owner"] = "有趣知识八分饱"
        reader, _, _ = self._reader(envelope=envelope)
        record = reader.complete(BVID)
        self.assertEqual(record["outcome"], "ok")
        self.assertIsNone(record["original_author"])
        self.assertIn("owner_malformed", record["unknown_fields"])

    def test_owner_name_missing_stays_unknown(self):
        envelope = self._clone_ok()
        envelope["payload"]["data"]["owner"] = {"mid": 1, "name": "   "}
        reader, _, _ = self._reader(envelope=envelope)
        record = reader.complete(BVID)
        self.assertIsNone(record["original_author"])
        self.assertIn("owner_name_missing", record["unknown_fields"])

    def test_pubdate_malformed_variants_stay_unknown(self):
        for bad_value in (True, 1753349981.5, "1753349981"):
            with self.subTest(pubdate=repr(bad_value)):
                envelope = self._clone_ok()
                envelope["payload"]["data"]["pubdate"] = bad_value
                reader, _, _ = self._reader(envelope=envelope)
                record = reader.complete(BVID)
                self.assertEqual(record["outcome"], "ok")
                self.assertIsNone(record["published_at"])
                self.assertIn("pubdate_malformed", record["unknown_fields"])

    def test_pubdate_out_of_range_stays_unknown(self):
        for bad_value in (0, 99999999999999):
            with self.subTest(pubdate=bad_value):
                envelope = self._clone_ok()
                envelope["payload"]["data"]["pubdate"] = bad_value
                reader, _, _ = self._reader(envelope=envelope)
                record = reader.complete(BVID)
                self.assertIsNone(record["published_at"])
                self.assertIn("pubdate_out_of_range", record["unknown_fields"])

    def test_stat_non_dict_yields_empty_engagement(self):
        envelope = self._clone_ok()
        envelope["payload"]["data"]["stat"] = ["not", "a", "dict"]
        reader, _, _ = self._reader(envelope=envelope)
        record = reader.complete(BVID)
        self.assertEqual(json.loads(record["engagement_json"]), {})
        self.assertIn("stat_malformed", record["unknown_fields"])

    def test_long_excerpt_is_truncated_to_limit(self):
        envelope = self._clone_ok()
        envelope["payload"]["data"]["desc"] = "x" * (EXCERPT_MAX + 500)
        reader, _, _ = self._reader(envelope=envelope)
        record = reader.complete(BVID)
        self.assertEqual(len(record["excerpt"]), EXCERPT_MAX)
        self.assertEqual(record["excerpt"], "x" * EXCERPT_MAX)

    # --- failure mapping (frozen caliber) ---------------------------------

    def test_failure_mapping_follows_frozen_caliber(self):
        expected = {
            "rate_limited_412": "rate_limited",
            "login_redirect_200": "blocked_login",
            "login_final_url_only": "blocked_login",
            "login_path_segment": "blocked_login",
            "html_shell": "failed",
            "timeout": "timeout",
            "missing_62002": "failed",
            "cross_origin_redirect": "failed",
            "server_error_500": "failed",
            "http_401_plain": "failed",
            "http_403_plain": "failed",
        }
        for name, outcome in expected.items():
            with self.subTest(case=name):
                reader, transport, _ = self._reader(envelope=self.failures["cases"][name])
                record = reader.complete(BVID)
                self.assertEqual(record["outcome"], outcome)
                self.assertEqual(len(transport.calls), 1)

    def test_login_only_from_explicit_markers(self):
        for name in ("http_401_plain", "http_403_plain"):
            with self.subTest(case=name):
                reader, _, _ = self._reader(envelope=self.failures["cases"][name])
                record = reader.complete(BVID)
                self.assertEqual(record["outcome"], "failed")
                self.assertNotEqual(record["outcome"], "blocked_login")
        reader, _, _ = self._reader(envelope=self.failures["cases"]["login_final_url_only"])
        self.assertIn("final_url_login", reader.complete(BVID)["failure_reason"])

    def test_cross_origin_redirect_is_failed_not_login(self):
        reader, _, _ = self._reader(envelope=self.failures["cases"]["cross_origin_redirect"])
        record = reader.complete(BVID)
        self.assertEqual(record["outcome"], "failed")
        self.assertIn("cross_origin_redirect", record["failure_reason"])
        self.assertNotIn("login", record["failure_reason"])

    def test_html_shell_is_failed(self):
        reader, _, _ = self._reader(envelope=self.failures["cases"]["html_shell"])
        record = reader.complete(BVID)
        self.assertEqual(record["outcome"], "failed")
        self.assertIn("html_shell", record["failure_reason"])

    def test_risk_control_keeps_raw_reason_without_threshold_claim(self):
        reader, _, _ = self._reader(envelope=self.failures["cases"]["rate_limited_412"])
        record = reader.complete(BVID)
        self.assertEqual(record["outcome"], "rate_limited")
        self.assertIn("http=412", record["failure_reason"])
        self.assertIn("app_code=-412", record["failure_reason"])
        self.assertIn("request was banned", record["failure_reason"])
        self.assertNotIn("429", record["failure_reason"])
        self.assertNotIn("阈值", record["failure_reason"])

    def test_unknown_http_stays_none_for_timeout_and_redirect(self):
        for name in ("timeout", "cross_origin_redirect"):
            with self.subTest(case=name):
                reader, _, _ = self._reader(envelope=self.failures["cases"][name])
                self.assertIsNone(reader.complete(BVID)["http_status"])

    def test_invisible_object_62002_maps_to_failed(self):
        reader, _, _ = self._reader(envelope=self.failures["cases"]["missing_62002"])
        record = reader.complete(BVID)
        self.assertEqual(record["outcome"], "failed")
        self.assertEqual(record["app_code"], 62002)

    # --- input trust boundary ---------------------------------------------

    def test_invalid_or_untrusted_targets_never_reach_transport(self):
        bad_targets = [
            "",
            "   ",
            "not-a-bvid",
            "BV123",
            "BV1us8MzPEm",
            "https://b23.tv/BV1us8MzPEmn",
            "https://evil.example/video/BV1us8MzPEmn/",
            "https://www.bilibili.com/watch/BV1us8MzPEmn/",
            "https://user:pass@www.bilibili.com/video/BV1us8MzPEmn/",
            "https://@www.bilibili.com/video/BV1us8MzPEmn/",
            "http://[::1/video/BV1us8MzPEmn",
            "https://www.bilibili.com:8443/video/BV1us8MzPEmn/",
            "https://www.bilibili.com:99999999/video/BV1us8MzPEmn/",
            "https://www.bilibili.com:abc/video/BV1us8MzPEmn/",
            "ftp://www.bilibili.com/video/BV1us8MzPEmn/",
        ]
        for value in bad_targets:
            with self.subTest(target=value):
                reader, transport, _ = self._reader()
                record = reader.complete(value)
                self.assertEqual(record["outcome"], "failed")
                self.assertTrue(record["failure_reason"].startswith("invalid_target"))
                self.assertIsNone(record["http_status"])
                self.assertIsNone(record["app_code"])
                self.assertEqual(record["observed_at_source"], "import_time")
                self.assertEqual(transport.calls, [])

    def test_default_port_is_accepted(self):
        url = f"https://www.bilibili.com:443/video/{BVID}/"
        reader, transport, _ = self._reader()
        record = reader.complete(url)
        self.assertEqual(record["outcome"], "ok")
        self.assertEqual(transport.calls, [API_URL.format(bvid=BVID)])

    def test_resolve_target_returns_bvid_and_original_url(self):
        self.assertEqual(resolve_target(BVID), (BVID, ""))
        url = f"https://www.bilibili.com/video/{BVID}/"
        self.assertEqual(resolve_target(url), (BVID, url))
        no_slash = f"https://www.bilibili.com/video/{BVID}"
        self.assertEqual(resolve_target(no_slash), (BVID, no_slash))

    def test_bilibili_video_url_is_accepted_and_normalised(self):
        raw = f"https://www.bilibili.com/video/{BVID}/?spm=1&vd_source=abc&utm_source=x&fbclid=y"
        reader, transport, _ = self._reader()
        record = reader.complete(raw)
        self.assertEqual(record["outcome"], "ok")
        self.assertEqual(record["url"], raw)
        self.assertEqual(record["url_norm"], url_norm(raw))
        self.assertIn("vd_source=abc", record["url_norm"])
        for dropped in ("spm=1", "utm_source", "fbclid"):
            self.assertNotIn(dropped, record["url_norm"])
        self.assertEqual(record["identity_key"], f"n:bilibili:{BVID}")
        self.assertEqual(transport.calls, [API_URL.format(bvid=BVID)])

    # --- cache and retry policy -------------------------------------------

    def test_cache_shares_content_but_rebuilds_url_per_input(self):
        reader, transport, clock = self._reader()
        bare = reader.complete(BVID)
        url1 = f"https://www.bilibili.com/video/{BVID}/?vd_source=abc&utm_source=x"
        first_url = reader.complete(url1)
        url2 = f"https://m.bilibili.com/video/{BVID}/"
        second_url = reader.complete(url2)

        self.assertEqual(len(transport.calls), 1)
        self.assertEqual(bare["url"], CANONICAL_URL.format(bvid=BVID))
        self.assertEqual(bare["url_norm"], url_norm(CANONICAL_URL.format(bvid=BVID)))
        self.assertEqual(first_url["url"], url1)
        self.assertEqual(first_url["url_norm"], url_norm(url1))
        self.assertEqual(second_url["url"], url2)
        self.assertEqual(second_url["url_norm"], url_norm(url2))
        hashes = {bare["content_hash"], first_url["content_hash"], second_url["content_hash"]}
        self.assertEqual(len(hashes), 1)
        self.assertEqual(bare["content_hash"], content_hash(bare["excerpt"], bare["title"]))
        stamps = {bare["observed_at"], first_url["observed_at"], second_url["observed_at"]}
        self.assertEqual(len(stamps), 1)
        for record in (bare, first_url, second_url):
            self.assertEqual(record["identity_key"], f"n:bilibili:{BVID}")
            self.assertEqual(record["observed_at"], _dt.datetime.fromtimestamp(clock.now, CST).isoformat(timespec="seconds"))

    def test_cache_hit_within_24h_then_refresh(self):
        reader, transport, clock = self._reader()
        reader.complete(BVID)
        self.assertEqual(len(transport.calls), 1)
        clock.now += 86399
        reader.complete(BVID)
        self.assertEqual(len(transport.calls), 1)
        clock.now += 2
        reader.complete(BVID)
        self.assertEqual(len(transport.calls), 2)

    def test_failure_is_not_cached_and_not_retried(self):
        reader, transport, clock = self._reader(envelope=self.failures["cases"]["timeout"])
        reader.complete(BVID)
        self.assertEqual(len(transport.calls), 1)
        clock.now += 10
        reader.complete(BVID)
        self.assertEqual(len(transport.calls), 2)

    # --- third-round rework additions -------------------------------------

    def test_overlong_title_fallback_is_truncated(self):
        for desc in (None, "   "):
            with self.subTest(desc=repr(desc)):
                envelope = self._clone_ok()
                envelope["payload"]["data"]["title"] = "题" * (EXCERPT_MAX + 200)
                if desc is None:
                    envelope["payload"]["data"].pop("desc")
                else:
                    envelope["payload"]["data"]["desc"] = desc
                reader, _, _ = self._reader(envelope=envelope)
                record = reader.complete(BVID)
                self.assertEqual(record["outcome"], "ok")
                self.assertEqual(len(record["excerpt"]), EXCERPT_MAX)
                self.assertEqual(record["excerpt"], "题" * EXCERPT_MAX)

    def test_non_integer_app_codes_fail_without_identity(self):
        variants = []
        envelope = self._clone_ok()
        envelope["app_code"] = False
        variants.append(("app_code=False", envelope))
        envelope = self._clone_ok()
        envelope["app_code"] = None
        envelope["payload"]["code"] = False
        variants.append(("payload.code=False", envelope))
        envelope = self._clone_ok()
        envelope["app_code"] = "0"
        variants.append(("app_code='0'", envelope))
        for name, envelope in variants:
            with self.subTest(case=name):
                reader, transport, _ = self._reader(envelope=envelope)
                record = reader.complete(BVID)
                self.assertEqual(record["outcome"], "failed")
                self.assertIn("unexpected_response", record["failure_reason"])
                self.assertNotIn("identity_key", record)
                self.assertNotIn("url", record)
                self.assertEqual(len(transport.calls), 1)

    def test_login_path_segment_matching(self):
        targets = (
            f"https://www.bilibili.com/video/{BVID}/login",
            "https://www.bilibili.com/users/account/login",
        )
        for final_url in targets:
            with self.subTest(final_url=final_url):
                envelope = self._clone_ok()
                envelope["final_url"] = final_url
                reader, _, _ = self._reader(envelope=envelope)
                record = reader.complete(BVID)
                self.assertEqual(record["outcome"], "blocked_login")
                self.assertIn("final_url_login", record["failure_reason"])

    def test_login_similar_paths_are_not_login(self):
        targets = (
            f"https://www.bilibili.com/video/{BVID}/login-tips",
            f"https://www.bilibili.com/video/{BVID}/loginx",
        )
        for final_url in targets:
            with self.subTest(final_url=final_url):
                envelope = self._clone_ok()
                envelope["final_url"] = final_url
                reader, _, _ = self._reader(envelope=envelope)
                record = reader.complete(BVID)
                self.assertEqual(record["outcome"], "ok")
                self.assertEqual(record["title"], "拼多多全域虚拟电商从零到1实操课")

    def test_unknown_fields_not_shared_between_records(self):
        envelope = self._clone_ok()
        envelope["payload"]["data"]["owner"] = "not-a-dict"
        reader, transport, _ = self._reader(envelope=envelope)
        first = reader.complete(BVID)
        second = reader.complete(BVID)
        self.assertEqual(len(transport.calls), 1)
        self.assertEqual(first["unknown_fields"], ["owner_malformed"])
        self.assertEqual(second["unknown_fields"], ["owner_malformed"])
        self.assertIsNot(first["unknown_fields"], second["unknown_fields"])
        first["unknown_fields"].append("polluted")
        third = reader.complete(BVID)
        self.assertEqual(third["unknown_fields"], ["owner_malformed"])

    def test_module_has_no_network_client(self):
        source = (ROOT / "app" / "sources" / "bilibili_view.py").read_text(encoding="utf-8")
        for forbidden in ("urllib.request", "http.client", "import socket", "import requests", "aiohttp"):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
