"""V2EX/GitHub read-only adapters + triage + end-to-end (temp DB, stub fetch)."""

from __future__ import annotations

import json
import pathlib
import tempfile
import unittest

from tools.selection import db, github, new_sources, triage, v2ex


def v2_payload():
    return [{"id": 101, "title": "求一个 Notion 学习计划模板", "content": "<p>有没有推荐的？学生党不会做</p>",
             "url": "https://www.v2ex.com/t/101"},
            {"id": 102, "title": "出 Notion 模板 接单", "content": "代做 私我 优惠", "url": "https://www.v2ex.com/t/102"}]


def gh_payload():
    return {"items": [
        {"number": 7, "title": "How to build a study planner template?",
         "body": "I want a template; how to do it", "html_url": "https://github.com/acme/repo/issues/7",
         "repository_url": "https://api.github.com/repos/acme/repo"},
        {"number": 8, "title": "Selling notion templates", "body": "DM me, promo discount",
         "html_url": "https://github.com/acme/repo/issues/8",
         "repository_url": "https://api.github.com/repos/acme/repo"},
    ]}


class Fake:
    def __init__(self, body, status=200):
        self.body = body
        self.status = status

    def __call__(self, url):
        return v2ex.FetchResult(self.status, self.body, {}, url)


class SourceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = pathlib.Path(self.tmp.name)
        self.db = self.dir / "s.sqlite3"

    def tearDown(self):
        self.tmp.cleanup()

    def test_v2ex_parse_and_fetch_summary(self):
        raw = json.dumps(v2_payload(), ensure_ascii=False).encode()
        out = v2ex.fetch(node_name="notion", limit=2, raw_dir=self.dir / "raw",
                         fetch=Fake(raw))
        self.assertEqual((out["status"], out["items"], len(out["signals"])), (200, 2, 2))
        self.assertEqual(out["signals"][0]["platform"], "v2ex")
        self.assertEqual(out["signals"][0]["native_id"], "101")
        self.assertTrue(out["signals"][0]["quote"].startswith("有没有推荐"))
        self.assertLessEqual(len(out["signals"][0]["quote"]), 201)
        self.assertTrue(out["raw_path"].endswith(".json"))
        # missing fields skipped, malformed payload errors without throw
        bad = v2ex.fetch(node_name="notion", limit=2, raw_dir=self.dir / "raw",
                         fetch=Fake(json.dumps([{"title": "no id"}]).encode()))
        self.assertEqual(bad["items"], 0)
        broken = v2ex.fetch(node_name="notion", limit=2, raw_dir=self.dir / "raw",
                            fetch=Fake(b"not-json"))
        self.assertEqual(broken["stop_reason"], "invalid_json")

    def test_github_parse_and_http_stop(self):
        raw = json.dumps(gh_payload(), ensure_ascii=False).encode()
        out = github.fetch(query="notion", limit=2, raw_dir=self.dir / "raw", fetch=Fake(raw))
        self.assertEqual((out["items"], out["signals"][0]["native_id"]), (2, "acme/repo#7"))
        self.assertIn("template", out["signals"][0]["quote"])
        stop = github.fetch(query="notion", limit=2, raw_dir=self.dir / "raw",
                            fetch=Fake(b"{}", status=429))
        self.assertEqual(stop["stop_reason"], "http_429")
        self.assertEqual(stop["requests"], 1)

    def test_triage_three_classes(self):
        self.assertEqual(triage.classify("求一个模板，有没有推荐"), "demand")
        self.assertEqual(triage.classify("出模板 接单 私我 优惠"), "promo")
        self.assertEqual(triage.classify("今天天气不错"), "noise")
        # promo wins ties; demand not inflated
        self.assertEqual(triage.classify("求 出 接单"), "promo")

    def test_end_to_end_stub_ingest_categorize_cards(self):
        raw_v = json.dumps(v2_payload(), ensure_ascii=False).encode()
        raw_g = json.dumps(gh_payload(), ensure_ascii=False).encode()
        v = v2ex.fetch(node_name="notion", limit=2, raw_dir=self.dir / "raw", fetch=Fake(raw_v))
        g = github.fetch(query="notion", limit=2, raw_dir=self.dir / "raw", fetch=Fake(raw_g))
        result = new_sources.ingest(v["signals"] + g["signals"], self.db)
        self.assertGreaterEqual(result["categorize"]["categories"], 1)
        self.assertGreaterEqual(result["cards"]["cards"], 1)
        conn = db.init_db(self.db)
        try:
            platforms = {r[0] for r in conn.execute("SELECT DISTINCT platform FROM signals")}
            self.assertEqual(platforms, {"v2ex", "github"})
            tri = conn.execute("SELECT COUNT(*) FROM signal_triage").fetchone()[0]
            self.assertEqual(tri, 4)
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM signal_triage WHERE label='demand'").fetchone()[0] >= 1, True)
        finally:
            conn.close()


if __name__ == "__main__":
    unittest.main()
