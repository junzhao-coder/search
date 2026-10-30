"""XHS skeleton: fixture parsing, risk stop, profile doctor (zero network)."""

from __future__ import annotations

import json
import pathlib
import unittest

from tools.selection import xiaohongshu as xhs

FIXTURES = pathlib.Path(__file__).resolve().parents[1] / "docs" / "validation" / "v9" / "xhs-readiness" / "fixtures"


class XhsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.results = (FIXTURES / "results_page.html").read_text(encoding="utf-8")
        cls.login = (FIXTURES / "login_wall.html").read_text(encoding="utf-8")
        cls.captcha = (FIXTURES / "captcha_page.html").read_text(encoding="utf-8")
        cls.note = json.loads((FIXTURES / "note_comments.json").read_text(encoding="utf-8"))
        cls.real = (FIXTURES / "home_real_structure.html").read_text(encoding="utf-8")

    def test_search_url(self):
        self.assertEqual(xhs.search_url("学习计划"),
                         "https://www.xiaohongshu.com/search_result?keyword=%E5%AD%A6%E4%B9%A0%E8%AE%A1%E5%88%92")

    def test_parse_results_ok(self):
        out = xhs.parse_results(self.results, limit=5)
        self.assertTrue(out["ok"])
        self.assertEqual(out["count"], 3)
        ids = [s["native_id"] for s in out["signals"]]
        self.assertEqual(ids, ["note001", "note002", "note003"])
        self.assertEqual(out["signals"][0]["title"], "求推荐的学习计划模板")
        self.assertIn("学生党想要", out["signals"][0]["quote"])
        self.assertTrue(out["signals"][0]["url"].startswith("https://www.xiaohongshu.com/explore/"))
        self.assertEqual(out["signals"][0]["origin_kind"], "real")
        self.assertTrue(out["signals"][0]["content_hash"])

    def test_parse_real_note_item_structure(self):
        out = xhs.parse_results(self.real, limit=5)
        self.assertTrue(out["ok"])
        self.assertEqual(out["count"], 2)
        self.assertEqual([s["native_id"] for s in out["signals"]], ["real001", "real002"])
        self.assertEqual(out["signals"][0]["title"], "占位标题一")
        self.assertEqual(out["signals"][0]["likes"], "1.2万")
        self.assertTrue(out["signals"][0]["author_hash"])
        self.assertNotIn("占位作者A", str(out["signals"][0]))  # author is hashed only

    def test_parse_search_result_href(self):
        html = ('<section class="note-item"><a href="/explore/abc"></a>'
                '<a class="title" href="/search_result/abc"><span>占位标题</span></a>'
                '<span class="like-wrapper"><span class="count">7</span></span></section>')
        out = xhs.parse_results(html, limit=1)
        self.assertEqual(out["count"], 1)
        self.assertEqual(out["signals"][0]["native_id"], "abc")
        self.assertEqual(out["signals"][0]["title"], "占位标题")

    def test_parse_login_wall_stops(self):
        out = xhs.parse_results(self.login)
        self.assertFalse(out["ok"])
        self.assertTrue(out["stop"])
        self.assertIs(out["retry"], False)
        self.assertIn("risk_marker:", out["stop_reason"])

    def test_parse_captcha_stops(self):
        out = xhs.parse_results(self.captcha)
        self.assertFalse(out["ok"])
        self.assertTrue(out["stop"])
        self.assertIn("risk_marker:", out["stop_reason"])

    def test_parse_replies_fixture(self):
        out = xhs.parse_replies(self.note, limit=10)
        self.assertEqual(out["count"], 3)
        self.assertEqual(out["signals"][0]["parent_native_id"], None)
        self.assertEqual(out["signals"][1]["parent_native_id"], "c1")
        self.assertIn("求一份模板", out["signals"][0]["quote"])
        self.assertEqual(out["signals"][0]["platform"], "xiaohongshu")

    def test_doctor_three_states(self):
        with self.subTest("missing profile"):
            code, info = xhs.doctor(FIXTURES / "no-profile")
            self.assertEqual((code, info["state"], info["exists"]), (2, "waiting_user", False))
        # empty sqlite as "not logged in" profile
        import sqlite3, tempfile, pathlib as pl
        with tempfile.TemporaryDirectory() as d:
            prof = pl.Path(d) / "profile"
            (prof / "Default" / "Network").mkdir(parents=True)
            conn = sqlite3.connect(prof / "Default" / "Network" / "Cookies")
            conn.execute("CREATE TABLE cookies (name TEXT, host_key TEXT)")
            conn.execute("INSERT INTO cookies VALUES ('a1','xiaohongshu.com')")
            conn.commit(); conn.close()
            code, info = xhs.doctor(prof)
            self.assertEqual((code, info["state"]), (2, "waiting_user"))
            self.assertFalse(info["cookies"]["web_session"])
            # ready: web_session present
            conn = sqlite3.connect(prof / "Default" / "Network" / "Cookies")
            conn.execute("INSERT INTO cookies VALUES ('web_session','xiaohongshu.com')")
            conn.commit(); conn.close()
            code, info = xhs.doctor(prof)
            self.assertEqual(code, 0)
            self.assertEqual(info["state"], "ready")
            self.assertTrue(info["cookies"]["web_session"])

    def test_stop_payload_never_retries(self):
        payload = xhs._stop_for("unit")
        self.assertEqual(payload, {"ok": False, "stop": True, "stop_reason": "unit", "retry": False})


if __name__ == "__main__":
    unittest.main()
