"""V18 engine-trial tests: fixture, extraction, stop semantics, real Playwright.

The fast tests use a fake driver with a page model, so they need no browser.
The real headed test is opt-in:

    $env:DSH_ENGINE_TRIAL_REAL = "1"
    python -m unittest tests.test_v18_engine_trial.PlaywrightRealTests -v
"""

from __future__ import annotations

import json
import os
import pathlib
import tempfile
import unittest

from tools.selection.engine_trial import collector, engines, extract, fixture


class FakeDriver:
    """A small page model: same IDs and actions as the fixture, no browser."""

    name = "fake"

    def __init__(self, *, fail_on: str | None = None) -> None:
        self.fail_on = fail_on
        self.closed = False
        self.expanded = False
        self.lazy_done = False
        self.scroll_y = 0
        self.scroll_height = 1800
        self.present = []
        self.events = []
        self.thread = {
            "native_id": fixture.THREAD_ID, "title": fixture.THREAD_TITLE,
            "text": fixture.THREAD_BODY, "author": fixture.THREAD_AUTHOR,
            "published_at": fixture.THREAD_TIME, "likes": fixture.THREAD_LIKES,
            "sources": {"text": "fixture"},
        }
        self._add([item["id"] for item in fixture.COMMENTS[:3]])

    def _add(self, ids) -> None:
        for cid in ids:
            if cid not in self.present:
                self.present.append(cid)

    def _comment(self, cid: str, kind: str = "comment", parent=None) -> dict:
        source = next(item for item in [*fixture.COMMENTS, *fixture.LZL]
                      if item["id"] == cid)
        return {"native_id": cid, "kind": kind,
                "parent_id": parent or fixture.THREAD_ID,
                "root_comment_id": fixture.THREAD_ID, "url": "file:///fake",
                "text": source["text"], "author": source["author"],
                "published_at": source["time"], "likes": source["likes"],
                "sources": {"text": "fixture"}}

    def _payload(self) -> dict:
        comments = [self._comment(cid) for cid in self.present]
        if self.expanded:
            comments.extend(self._comment(item["id"], "lzl", item["parent"])
                            for item in fixture.LZL)
        return {"url": "file:///fake", "title": fixture.THREAD_TITLE,
                "ready": "complete", "thread": self.thread,
                "comments": comments,
                "declared_comments": fixture.DECLARED_COMMENTS,
                "events": list(self.events),
                "scroll": {"y": self.scroll_y, "height": self.scroll_height}}

    def start(self):
        return {"engine": "fake", "browser_version": "fake-1"}

    def goto(self, url):
        self.url = url
        return {"url": url, "status": None, "ms": 1.0}

    def evaluate(self, script):
        return json.dumps(self._payload(), ensure_ascii=False)

    def click(self, selector):
        if self.fail_on == "click":
            raise RuntimeError("fake_click_failure")
        if selector == "div.show-more-lzl":
            if self.expanded:
                return {"clicked": False, "reason": "already_expanded"}
            self.expanded = True
            self.events.extend([{"type": "click", "detail": {"id": None,
                                                              "trusted": True}},
                                {"type": "expand", "detail": {"open": True,
                                                               "trusted": True}}])
            return {"clicked": True, "selector": selector}
        if selector == "#load-more":
            self.events.append({"type": "click", "detail": {"id": "load-more",
                                                             "trusted": True}})
            before = len(self.present)
            self._add([item["id"] for item in fixture.COMMENTS[6:]])
            self.scroll_height += 600 if len(self.present) > before else 0
            self.events.append({"type": "load_more",
                                "detail": {"added": len(self.present) - before,
                                           "trusted": True}})
            return {"clicked": True, "selector": selector}
        return {"clicked": False, "reason": "not_found", "selector": selector}

    def wheel(self, dx, dy):
        if self.fail_on == "wheel":
            raise RuntimeError("fake_wheel_failure")
        self.events.append({"type": "wheel", "detail": {"dy": dy,
                                                         "trusted": True}})
        previous = self.scroll_y
        self.scroll_y = min(2400, self.scroll_y + dy)
        if self.scroll_y != previous:
            self.events.append({"type": "scroll", "detail": {"y": self.scroll_y,
                                                              "trusted": True}})
        if not self.lazy_done and self.scroll_y > 200:
            self.lazy_done = True
            before = len(self.present)
            self._add([item["id"] for item in fixture.COMMENTS[3:6]])
            self.scroll_height += 600 if len(self.present) > before else 0
            self.events.append({"type": "lazy_load",
                                "detail": {"added": len(self.present) - before,
                                           "trusted": True}})
        return {"dx": dx, "dy": dy, "via": "fake_wheel"}

    def wait(self, ms):
        return None

    def screenshot(self, path):
        target = pathlib.Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"fake-png")
        return {"path": str(target), "bytes": target.stat().st_size}

    def close(self):
        self.closed = True
        return {"closed": True}

    def environment(self):
        return {"engine": "fake", "version": "fake-1"}


class FixtureTests(unittest.TestCase):
    def test_fixture_contains_thread_comments_likes_times_and_actions(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / "fixture.html"
            info = fixture.build_fixture(path)
            html = path.read_text(encoding="utf-8")
            self.assertIn(fixture.THREAD_BODY, html)
            self.assertIn(f'data-id="{fixture.COMMENTS[0]["id"]}"', html)
            self.assertIn(f'data-id="{fixture.COMMENTS[-1]["id"]}"', html)
            self.assertIn(f'data-id="{fixture.LZL[0]["id"]}"', html)
            self.assertIn("加载更多评论", html)
            self.assertIn("show-more-lzl", html)
            truth = info["ground_truth"]
            self.assertEqual(len(truth["comment_ids"]), 9)
            self.assertEqual(len(truth["lzl_ids"]), 2)
            self.assertEqual(truth["declared_comments"], 12)
            self.assertEqual(truth["thread_likes"], 37)


class ExtractTests(unittest.TestCase):
    def test_normalize_keeps_missing_values_unknown_and_parent_links(self):
        payload = {
            "thread": {"native_id": "900000001", "title": "标题", "text": "正文",
                       "author": "楼主", "published_at": "2026-10-01 12:00",
                       "likes": "37"},
            "comments": [
                {"native_id": "910000001", "kind": "comment",
                 "parent_id": "900000001", "text": "一", "author": "甲",
                 "published_at": "2026-10-01 12:01", "likes": "5"},
                {"native_id": "", "kind": "comment",
                 "parent_id": "900000001", "text": "没有原生 ID", "author": "乙",
                 "published_at": "2026-10-01 12:02", "likes": None},
                {"native_id": "920000001", "kind": "lzl",
                 "parent_id": "910000001", "text": "楼中楼", "author": "丙",
                 "published_at": "2026-10-01 12:03", "likes": 1},
            ],
            "declared_comments": "12",
            "scroll": {"y": 10, "height": 100},
            "events": [],
        }
        state = extract.normalize(payload)
        self.assertEqual(state["thread"]["likes"], 37)
        self.assertEqual(state["declared"], 12)
        self.assertEqual(state["scroll"], {"y": 10, "height": 100})
        self.assertEqual(state["unidentified"], 1)
        self.assertEqual(len(state["records"]), 3)
        unidentified = [record for record in state["records"].values()
                        if record["native_id"] is None][0]
        self.assertIn("native_id", unidentified["missing"])
        self.assertIn("likes", unidentified["missing"])
        self.assertEqual(state["records"]["920000001"]["parent_id"], "910000001")
        self.assertEqual(extract.ids_of(state),
                         ["900000001", "910000001", "920000001"])

    def test_compare_ids_reports_both_directions(self):
        result = extract.compare_ids({"ids": ["1", "2", "3"]},
                                     {"ids": ["2", "3", "4"]})
        self.assertEqual(result["left_only"], ["1"])
        self.assertEqual(result["right_only"], ["4"])
        self.assertEqual(result["common"], ["2", "3"])


class CollectorTests(unittest.TestCase):
    def _config(self):
        return collector.TrialConfig(max_scrolls=6, settle_ms=0)

    def test_collects_all_fixture_ids_and_stops_on_no_growth(self):
        driver = FakeDriver()
        result = collector.run_trial(driver, "file:///fake", config=self._config())
        truth = fixture.ground_truth()
        self.assertEqual(result["stop"], "no_growth")
        self.assertEqual(result["ids"], sorted(truth["ids"]))
        self.assertEqual(result["observed"], 11)
        self.assertEqual(result["comment_count"], 9)
        self.assertEqual(result["lzl_count"], 2)
        self.assertEqual(result["declared"], 12)
        self.assertFalse(result["complete"])
        self.assertTrue(result["partial"])
        self.assertTrue(result["action_evidence"]["ok"], result["action_evidence"])
        self.assertTrue(result["action_evidence"]["checks"]["trusted_input"])
        self.assertGreaterEqual(result["action_evidence"]["trusted"].get("click", 0), 2)
        self.assertGreater(result["scroll"]["y"], result["initial_scroll"]["y"])
        self.assertGreaterEqual(result["scroll"]["height"],
                                result["initial_scroll"]["height"])
        self.assertTrue(driver.closed)
        phases = [entry["phase"] for entry in result["timeline"]]
        self.assertIn("start_done", phases)
        self.assertIn("navigate", phases)
        self.assertIn("expand", phases)
        self.assertIn("load_more", phases)
        self.assertIn("final_read", phases)
        self.assertIn("close", phases)
        for phase in ("start_ms", "navigate_ms", "first_read_ms",
                      "actions_ms", "close_ms", "total_ms"):
            self.assertIsNotNone(result["phases"][phase], phase)
            self.assertGreaterEqual(result["phases"][phase], 0, phase)

    def test_cancel_keeps_partial_records_and_stops(self):
        driver = FakeDriver()
        result = collector.run_trial(
            driver, "file:///fake", config=self._config(),
            should_cancel=lambda: driver.scroll_y >= 700)
        self.assertEqual(result["stop"], "cancelled")
        self.assertGreaterEqual(result["observed"], 3)
        self.assertTrue(driver.closed)
        self.assertIn("取消", result["stop_detail"])

    def test_error_keeps_partial_records_and_stops(self):
        driver = FakeDriver(fail_on="click")
        result = collector.run_trial(driver, "file:///fake", config=self._config())
        self.assertTrue(result["stop"].startswith("error:RuntimeError"))
        self.assertIn("fake_click_failure", result["error"])
        self.assertGreaterEqual(len(result["ids"]), 4)
        self.assertTrue(driver.closed)

    def test_repeated_reads_do_not_duplicate_ids(self):
        result = collector.run_trial(FakeDriver(), "file:///fake",
                                     config=self._config())
        self.assertEqual(len(result["ids"]), len(set(result["ids"])))
        keys = [record["key"] for record in result["records"]]
        self.assertEqual(len(keys), len(set(keys)))


class AvailabilityTests(unittest.TestCase):
    def test_nodriver_availability_is_honest(self):
        info = engines.nodriver_available()
        if info["usable"]:
            self.skipTest("nodriver is installed; real run is out of scope here")
        self.assertFalse(info["usable"])
        self.assertIn(info["reason"], ("nodriver_not_installed", "chrome_not_found"))
        with self.assertRaises(engines.EngineUnavailable) as caught:
            engines.NodriverDriver().start()
        self.assertEqual(caught.exception.reason, "nodriver_unavailable")
        self.assertIn("nodriver", json.dumps(caught.exception.as_dict(),
                                             ensure_ascii=False))

    def test_playwright_availability_matches_this_environment(self):
        info = engines.playwright_available()
        if not info["installed"]:
            self.skipTest("playwright is not installed in this interpreter")
        self.assertIsNotNone(info["version"])
        if info["usable"]:
            self.assertTrue(info["chrome"])
        else:
            self.assertEqual(info["reason"], "chrome_not_found")


@unittest.skipUnless(os.environ.get("DSH_ENGINE_TRIAL_REAL") == "1",
                     "set DSH_ENGINE_TRIAL_REAL=1 to run a headed browser")
class PlaywrightRealTests(unittest.TestCase):
    def test_headed_trial_reads_same_fixture_and_records_real_actions(self):
        info = engines.playwright_available()
        if not info["usable"]:
            self.skipTest(f"playwright unavailable: {info['reason']}")
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / "fixture.html"
            fixture.build_fixture(path)
            driver = engines.PlaywrightDriver(headless=False, channel="chrome",
                                              timeout_ms=15000)
            result = collector.run_trial(
                driver, path.as_uri(),
                config=collector.TrialConfig(max_scrolls=6, settle_ms=200))
        truth = fixture.ground_truth()
        self.assertEqual(result["stop"], "no_growth")
        self.assertEqual(result["ids"], sorted(truth["ids"]))
        self.assertEqual(result["comment_count"], 9)
        self.assertEqual(result["lzl_count"], 2)
        self.assertEqual(result["thread"]["likes"], 37)
        self.assertEqual(result["thread"]["published_at"], fixture.THREAD_TIME)
        self.assertTrue(result["action_evidence"]["ok"], result["action_evidence"])
        self.assertGreater(result["scroll"]["y"], 0)
        self.assertTrue(driver.closed)


@unittest.skipUnless(os.environ.get("DSH_ENGINE_TRIAL_REAL") == "1",
                     "set DSH_ENGINE_TRIAL_REAL=1 to run a headed browser")
class NodriverRealTests(unittest.TestCase):
    def test_headed_trial_reads_same_fixture_and_records_real_actions(self):
        info = engines.nodriver_available()
        if not info["usable"]:
            self.skipTest(f"nodriver unavailable: {info['reason']}")
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / "fixture.html"
            fixture.build_fixture(path)
            driver = engines.NodriverDriver(headless=False, timeout=30)
            result = collector.run_trial(
                driver, path.as_uri(),
                config=collector.TrialConfig(max_scrolls=6, settle_ms=200))
        truth = fixture.ground_truth()
        self.assertEqual(result["stop"], "no_growth")
        self.assertEqual(result["ids"], sorted(truth["ids"]))
        self.assertEqual(result["comment_count"], 9)
        self.assertEqual(result["lzl_count"], 2)
        self.assertEqual(result["thread"]["likes"], 37)
        self.assertEqual(result["thread"]["published_at"], fixture.THREAD_TIME)
        self.assertTrue(result["action_evidence"]["ok"], result["action_evidence"])
        self.assertTrue(result["action_evidence"]["checks"]["trusted_input"])
        self.assertGreater(result["scroll"]["y"], 0)
        self.assertTrue(driver.closed)


if __name__ == "__main__":
    unittest.main()
