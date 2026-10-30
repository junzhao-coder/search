"""Pure helpers of the V9-9 visible probe (no browser, no network)."""

from __future__ import annotations

import hashlib
import pathlib
import tempfile
import unittest

from tools.selection import db, xhs_probe

HTML = """<html><head>
<meta property="og:title" content="一份学习计划 - 小红书">
<meta property="og:description" content="分享一个可打印的周计划">
<meta property="og:article:author" content="someone">
<meta property="article:published_time" content="2026-10-25T12:00:00Z">
<title>fallback</title></head>
<body><a href="/explore/abc123?x=1">nickname 个人主页</a>
<a href="/user/profile/name123">个人主页</a>
<p>12 赞</p><div class="comment-entry">评论</div></body></html>"""


class XhsProbeTests(unittest.TestCase):
    def test_sanitize_skeleton_removes_text_and_redacts_user(self):
        out = xhs_probe.sanitize_skeleton(HTML)
        self.assertNotIn("nickname", out)
        self.assertNotIn("someone", out)
        self.assertNotIn("个人主页", out)
        self.assertIn("/explore/abc123", out)
        self.assertIn("/user/profile/[redacted]", out)
        self.assertIn("<a", out)

    def test_search_groups_and_url(self):
        self.assertEqual(xhs_probe.search_words("A"), ("求推荐", "有没有", "怎么做"))
        self.assertEqual(xhs_probe.search_words("B"), ("不会用", "怎么选", "踩坑"))
        self.assertIn("keyword=%E6%B1%82%E6%8E%A8%E8%8D%90", xhs_probe.search_url("求推荐"))

    def test_search_parse_and_summary(self):
        html = (pathlib.Path(__file__).resolve().parents[1] / "docs" / "validation" / "v9"
                / "xhs-readiness" / "fixtures" / "results_page.html").read_text(encoding="utf-8")
        parsed = xhs_probe.parse_search_page(html, "求推荐", limit=3)
        self.assertTrue(parsed["ok"])
        self.assertEqual(len(parsed["records"]), 3)
        s = xhs_probe.triage_summary(parsed["records"])
        self.assertEqual(s["counts"], {"demand": 1, "promo": 1, "noise": 1})
        self.assertAlmostEqual(s["demand_rate"], 1 / 3)
        self.assertEqual(xhs_probe.search_page_state("正常页面", parsed["records"]), "ok")

    def test_search_login_wall_stop(self):
        html = (pathlib.Path(__file__).resolve().parents[1] / "docs" / "validation" / "v9"
                / "xhs-readiness" / "fixtures" / "login_wall.html").read_text(encoding="utf-8")
        parsed = xhs_probe.parse_search_page(html, "有没有")
        self.assertFalse(parsed["ok"])
        self.assertIn("risk_marker", parsed["stop"])
        self.assertEqual(xhs_probe.search_page_state("请登录", []), "login_required")
        self.assertEqual(xhs_probe.search_page_state("访问异常", []), "risk")

    def test_quote_evidence_fallback_and_ingest(self):
        html = (pathlib.Path(__file__).resolve().parents[1] / "docs" / "validation" / "v9"
                / "xhs-readiness" / "fixtures" / "results_page.html").read_text(encoding="utf-8")
        records = xhs_probe.parse_search_page(html, "求推荐")["records"]
        quotes = xhs_probe.quote_evidence(records)
        self.assertTrue(quotes)
        self.assertTrue(all(len(q["quote"]) <= 61 for q in quotes))
        old = xhs_probe.ISO_DB
        with tempfile.TemporaryDirectory() as d:
            xhs_probe.ISO_DB = pathlib.Path(d) / "search.sqlite3"
            try:
                out = xhs_probe._ingest_search(records, "xhs-search-test")
                self.assertEqual(out["written"], 1)
                conn = db.init_db(xhs_probe.ISO_DB)
                try:
                    self.assertEqual(conn.execute("SELECT COUNT(*) FROM signals").fetchone()[0], 1)
                finally:
                    conn.close()
            finally:
                xhs_probe.ISO_DB = old

    def test_search_exit_code(self):
        self.assertEqual(xhs_probe.exit_code({"mode": "search", "completed": True,
                                              "stopped": None, "records": [{}]}), 0)
        self.assertEqual(xhs_probe.exit_code({"mode": "search", "completed": True,
                                              "stopped": "risk_marker:captcha",
                                              "records": [{}]}), 5)
        self.assertEqual(xhs_probe.exit_code({"mode": "search", "completed": True,
                                              "stopped": "risk_marker:dom",
                                              "records": []}), 5)
        self.assertEqual(xhs_probe.exit_code({"mode": "search", "completed": True,
                                              "stopped": "search_nav_timeout:TimeoutError",
                                              "records": []}), 6)
        self.assertEqual(xhs_probe.exit_code({"mode": "search", "completed": True,
                                              "stopped": None, "records": []}), 6)
        self.assertEqual(xhs_probe.exit_code({"mode": "search", "completed": False,
                                              "stopped": None, "records": [{}]}), 6)

    def test_like_wrapper_first_count_only(self):
        html = '<span class="like-wrapper"><span class="count">1.2万</span>'                '<span class="count">99</span><span>评论 8</span></span>'
        f = xhs_probe.parse_note_fields(html, "https://www.xiaohongshu.com/explore/a")
        self.assertEqual(f["likes"], "1.2万")
        self.assertIn("like-wrapper.count", f["likes_path"])

    def test_classify_online(self):
        self.assertEqual(xhs_probe.classify_online("请登录", [])[0], "login_required")
        self.assertEqual(xhs_probe.classify_online("请完成安全验证", [])[0], "risk")
        self.assertEqual(xhs_probe.classify_online("首页", ["https://x/explore/a"])[0], "valid")
        self.assertEqual(xhs_probe.classify_online("首页", [])[0], "unknown")

    def test_extract_links(self):
        self.assertEqual(xhs_probe.extract_explore_links(HTML),
                         ["https://www.xiaohongshu.com/explore/abc123"])

    def test_parse_note_fields(self):
        f = xhs_probe.parse_note_fields(HTML, "https://www.xiaohongshu.com/explore/abc123")
        self.assertEqual(f["native_id"], "abc123")
        self.assertEqual(f["title"], "一份学习计划")
        self.assertEqual(f["desc"], "分享一个可打印的周计划")
        self.assertEqual(f["likes"], "12")
        self.assertEqual(f["author_hash"], hashlib.sha256(b"someone").hexdigest()[:12])
        self.assertEqual(f["missing"], [])
        self.assertEqual(f["publish_time"], "2026-10-25T12:00:00Z")
        self.assertTrue(f["comment_entry_present"])
        self.assertTrue(f["complete"])

    def test_error_page_rejected(self):
        err = "<html><head><title>小红书 - 你访问的页面不见了</title></head></html>"
        fields = xhs_probe.parse_note_fields(err, "https://www.xiaohongshu.com/explore/abc")
        self.assertTrue(fields["error_page"])
        self.assertFalse(fields["complete"])
        old = xhs_probe.ISO_DB
        with tempfile.TemporaryDirectory() as d:
            xhs_probe.ISO_DB = pathlib.Path(d) / "first.sqlite3"
            try:
                out = xhs_probe._ingest(fields, "https://www.xiaohongshu.com/explore/abc",
                                        "b" * 64, "first-real-test")
                self.assertEqual(out, {"written": 0, "reason": "error_page"})
                self.assertFalse(xhs_probe.ISO_DB.exists())
            finally:
                xhs_probe.ISO_DB = old

    def test_batch_limit_and_stop(self):
        self.assertEqual(xhs_probe.batch_limit(8, 10), 5)
        self.assertEqual(xhs_probe.batch_limit(8, 20), 8)
        self.assertEqual(xhs_probe.batch_limit(3, 10), 3)
        self.assertTrue(xhs_probe.batch_should_stop("login_required"))
        self.assertTrue(xhs_probe.batch_should_stop("risk"))
        self.assertFalse(xhs_probe.batch_should_stop("error_page"))
        self.assertFalse(xhs_probe.batch_should_stop("note"))

    def test_note_exit_code_completed(self):
        self.assertEqual(xhs_probe.exit_code({"mode": "note-click", "completed": True}), 0)
        self.assertEqual(xhs_probe.exit_code({"mode": "note", "completed": False}), 6)

    def test_classify_note_skips_error_and_login(self):
        err = xhs_probe.parse_note_fields("<title>小红书 - 你访问的页面不见了</title>", "https://www.xiaohongshu.com/explore/e")
        login = xhs_probe.parse_note_fields("<title>请登录</title>", "https://www.xiaohongshu.com/explore/l")
        good = xhs_probe.parse_note_fields(HTML, "https://www.xiaohongshu.com/explore/abc123")
        verdicts = [xhs_probe.classify_note(x) for x in (err, login, good)]
        self.assertEqual(verdicts, ["error_page", "login_required", "note"])
        self.assertEqual(next(i for i, v in enumerate(verdicts) if v == "note"), 2)

    def test_ingest_one_row_into_temp_db(self):
        old = xhs_probe.ISO_DB
        with tempfile.TemporaryDirectory() as d:
            xhs_probe.ISO_DB = pathlib.Path(d) / "first.sqlite3"
            try:
                fields = xhs_probe.parse_note_fields(HTML, "https://www.xiaohongshu.com/explore/abc123")
                out = xhs_probe._ingest(fields, "https://www.xiaohongshu.com/explore/abc123",
                                        "a" * 64, "first-real-test")
                self.assertEqual(out["written"], 1)
                again = xhs_probe._ingest(fields, "https://www.xiaohongshu.com/explore/abc123",
                                          "c" * 64, "first-real-test-2")
                self.assertEqual(again["written"], 0)  # duplicate, still one row
                conn = db.init_db(xhs_probe.ISO_DB)
                try:
                    self.assertEqual(conn.execute("SELECT COUNT(*) FROM signals").fetchone()[0], 1)
                    row = conn.execute("SELECT origin_kind,platform,native_id FROM signals").fetchone()
                    self.assertEqual((row["origin_kind"], row["platform"], row["native_id"]),
                                     ("real", "xiaohongshu", "abc123"))
                finally:
                    conn.close()
            finally:
                xhs_probe.ISO_DB = old


if __name__ == "__main__":
    unittest.main()
