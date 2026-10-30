"""Bilibili collector tests with injected fetch; never touches the network."""

from __future__ import annotations

import json
import pathlib
import tempfile
import unittest

from tools.selection import bilibili, db


def payload(code=0, data=None):
    return json.dumps({"code": code, "message": "OK", "data": data or {}}).encode()


class FakeFetcher:
    def __init__(self, view, reply, sub=None, reply_status=200):
        self.view = view
        self.reply = reply
        self.sub = sub
        self.reply_status = reply_status
        self.urls = []

    def __call__(self, url):
        self.urls.append(url)
        if "/view?" in url:
            return bilibili.FetchResult(200, payload(data=self.view), {}, url)
        if "/reply/reply?" in url:
            return bilibili.FetchResult(200, payload(data=self.sub or {"page": {}, "replies": []}), {}, url)
        return bilibili.FetchResult(self.reply_status, payload(data=self.reply), {}, url)


VIEW = {
    "aid": 540769243, "bvid": "BV11i4y147FS", "title": "test video",
    "videos": 1, "stat": {"reply": 2},
}
REPLY = {
    "page": {"num": 1, "size": 5, "count": 2, "acount": 2},
    "replies": [
        {"rpid": 3000819542, "root": 0, "parent": 0, "like": 7, "rcount": 1,
         "content": {"message": "hello @someone"}, "member": {"mid": 11, "uname": "alice"}},
        {"rpid": 3005231967, "root": 3000819542, "parent": 3000819542, "like": 1, "rcount": 0,
         "content": {"message": "child"}, "member": {"mid": 12, "uname": "bob"}},
    ],
}
SUB = {"page": {"num": 1, "size": 2, "count": 1},
       "replies": [{"rpid": 3009999999, "root": 3000819542, "parent": 3000819542,
                    "content": {"message": "sub"}, "member": {"mid": 13, "uname": "carol"}}]}


class BilibiliTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = pathlib.Path(self.tmp.name) / "selection.sqlite3"
        self.raw = pathlib.Path(self.tmp.name) / "raw"

    def tearDown(self):
        self.tmp.cleanup()

    def test_sort2_first_page_and_sanitized_raw(self):
        fake = FakeFetcher(VIEW, REPLY)
        result = bilibili.collect(db_path=self.db, raw_dir=self.raw, aid=540769243,
                                  budget=3, interval=0, fetch=fake)
        self.assertEqual(result["status"], "complete")
        self.assertEqual(result["new"], 2)
        self.assertEqual(len(fake.urls), 2)
        self.assertIn("sort=2", fake.urls[1])
        self.assertNotIn("pn=2", " ".join(fake.urls))
        conn = db.init_db(self.db)
        rows = conn.execute("SELECT native_id,parent_native_id,origin_kind FROM signals ORDER BY native_id").fetchall()
        conn.close()
        self.assertEqual([(r["native_id"], r["parent_native_id"], r["origin_kind"]) for r in rows],
                         [("3000819542", None, "real"), ("3005231967", "3000819542", "real")])
        raw_text = "\n".join(p.read_text(encoding="utf-8") for p in self.raw.glob("*.json"))
        self.assertNotIn("alice", raw_text)
        self.assertNotIn("bob", raw_text)
        self.assertIn("@u***", raw_text)

    def test_duplicate_run_zero_new(self):
        fake = FakeFetcher(VIEW, REPLY)
        first = bilibili.collect(db_path=self.db, raw_dir=self.raw, aid=540769243,
                                 budget=3, interval=0, fetch=fake)
        second = bilibili.collect(db_path=self.db, raw_dir=self.raw, aid=540769243,
                                  budget=3, interval=0, fetch=fake)
        self.assertEqual(first["new"], 2)
        self.assertEqual(second["new"], 0)
        self.assertEqual(second["duplicate"], 2)

    def test_budget_exhausted_stops_before_comment(self):
        fake = FakeFetcher(VIEW, REPLY)
        result = bilibili.collect(db_path=self.db, raw_dir=self.raw, aid=540769243,
                                  budget=1, interval=0, fetch=fake)
        self.assertEqual(result["status"], "partial")
        self.assertEqual(result["stop_reason"], "budget_exhausted")
        self.assertEqual(len(fake.urls), 1)

    def test_412_stops_without_retry(self):
        fake = FakeFetcher(VIEW, REPLY, reply_status=412)
        result = bilibili.collect(db_path=self.db, raw_dir=self.raw, aid=540769243,
                                  budget=3, interval=0, fetch=fake)
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["stop_reason"], "http_412")
        self.assertEqual(len(fake.urls), 2)

    def test_optional_subreply(self):
        fake = FakeFetcher(VIEW, REPLY, sub=SUB)
        result = bilibili.collect(db_path=self.db, raw_dir=self.raw, aid=540769243,
                                  budget=4, interval=0, include_subreply=True, fetch=fake)
        self.assertEqual(result["status"], "complete")
        self.assertEqual(result["new"], 3)
        self.assertEqual(len(fake.urls), 3)
        self.assertIn("/reply/reply?", fake.urls[2])
        self.assertIn("root=3000819542", fake.urls[2])


if __name__ == "__main__":
    unittest.main()
