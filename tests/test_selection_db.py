"""Tests for independent selection schema and idempotent upsert."""

from __future__ import annotations

import json
import pathlib
import tempfile
import unittest

from tools.selection import db, models


def make_signal(**overrides):
    signal = {
        "platform": "bilibili", "native_id": "1", "parent_native_id": None,
        "url": "https://www.bilibili.com/video/BV1#reply1", "title": "t",
        "quote": "hello", "lang": "en", "lang_source": "heuristic",
        "listed_price_minor": None, "effective_price_minor": None,
        "reference_price_minor": None, "wants": None,
        "collected_at": "2026-10-25T00:00:00Z", "collected_at_scope": "row",
        "origin_kind": "synthetic", "raw_sha256": "a" * 64,
        "content_hash": "b" * 64, "raw_ref": "raw/x.json", "batch_id": "b1",
    }
    signal.update(overrides)
    return signal


class SelectionDbTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = pathlib.Path(self.tmp.name) / "selection.sqlite3"
        self.conn = db.init_db(self.path)

    def tearDown(self):
        self.conn.close()
        self.tmp.cleanup()

    def test_init_idempotent_and_tables(self):
        self.conn.close()
        self.conn = db.init_db(self.path)
        tables = {r[0] for r in self.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        self.assertTrue({"schema_migrations", "signals", "runs"} <= tables)
        self.assertEqual(self.conn.execute(
            "SELECT MAX(version) FROM schema_migrations").fetchone()[0], models.SCHEMA_VERSION)

    def test_origin_check_and_unique(self):
        sig = make_signal(origin_kind="imported")
        db.upsert_signal(self.conn, sig)
        with self.assertRaises(Exception):
            db.upsert_signal(self.conn, {**sig, "native_id": "2", "origin_kind": "bogus"})
        self.assertEqual(self.conn.execute(
            "SELECT COUNT(*) FROM signals").fetchone()[0], 1)

    def test_upsert_new_duplicate_update(self):
        sig = make_signal()
        self.assertEqual(db.upsert_signal(self.conn, sig)[0], "new")
        self.assertEqual(db.upsert_signal(self.conn, sig)[0], "duplicate")
        changed = {**sig, "content_hash": "c" * 64, "quote": "changed"}
        self.assertEqual(db.upsert_signal(self.conn, changed)[0], "updated")
        row = self.conn.execute("SELECT quote,version,content_hash FROM signals WHERE native_id='1'").fetchone()
        self.assertEqual((row["quote"], row["version"], row["content_hash"]), ("changed", 2, "c" * 64))

    def test_content_hash_stable_and_sensitive(self):
        base = dict(platform="bilibili", native_id="1", quote="q",
                    listed_price_minor=None, effective_price_minor=None, wants=None)
        self.assertEqual(models.content_hash(**base), models.content_hash(**base))
        self.assertNotEqual(models.content_hash(**base),
                            models.content_hash(**{**base, "wants": 2}))

    def test_origin_upgrade_guard_keeps_imported(self):
        from tools.selection import db as dbmod
        s = {
            "platform": "xianyu", "native_id": "9001", "parent_native_id": None, "url": "u",
            "title": "t", "quote": "q", "lang": "zh", "lang_source": "heuristic",
            "listed_price_minor": None, "effective_price_minor": None, "reference_price_minor": None,
            "wants": None, "collected_at": "2026-01-01T00:00:00Z", "collected_at_scope": "row",
            "origin_kind": "imported", "raw_sha256": "a" * 64,
            "content_hash": "same", "raw_ref": "r", "batch_id": "b",
        }
        dbmod.upsert_signal(self.conn, s)
        s2 = {**s, "origin_kind": "real"}
        outcome, _ = dbmod.upsert_signal(self.conn, s2)
        self.assertEqual(outcome, "duplicate")
        row = self.conn.execute("SELECT origin_kind FROM signals WHERE native_id='9001'").fetchone()
        self.assertEqual(row["origin_kind"], "imported")
        self.assertGreaterEqual(dbmod.ORIGIN_GUARD["count"], 1)
        before = dbmod.ORIGIN_GUARD["count"]
        s3 = {**s2, "content_hash": "changed", "quote": "q2"}
        outcome2, _ = dbmod.upsert_signal(self.conn, s3)
        self.assertEqual(outcome2, "updated")
        row2 = self.conn.execute(
            "SELECT origin_kind,last_origin_kind,version FROM signals WHERE native_id='9001'").fetchone()
        self.assertEqual(row2["origin_kind"], "imported")
        self.assertEqual(row2["last_origin_kind"], "real")
        self.assertEqual(row2["version"], 2)
        self.assertEqual(dbmod.ORIGIN_GUARD["count"], before + 1)
        self.assertEqual(dbmod.ORIGIN_GUARD["last"]["reason"],
                         "origin_upgrade_on_change_kept_first_seen")

    def test_runs_and_stats(self):
        run_id, batch = db.start_run(self.conn, kind="test", platform="bilibili",
                                     budget={"max_requests": 2}, raw_dir=self.tmp.name)
        self.assertTrue(batch)
        db.finish_run(self.conn, run_id, status="complete", stop_reason=None,
                      stats={"requests": 2})
        out = db.stats(self.conn)
        self.assertEqual(out["signals"], 0)
        self.assertEqual(out["runs"][0]["status"], "complete")
        self.assertEqual(json.loads(out["runs"][0]["stats_json"])["requests"], 2)


if __name__ == "__main__":
    unittest.main()
