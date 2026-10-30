"""Category/alias/review/card/event tests; temp DB only."""

from __future__ import annotations

import json
import pathlib
import tempfile
import unittest

from tools.selection import categories, db


def signal(sid, title, quote, platform="xianyu"):
    return {
        "id": sid, "platform": platform, "native_id": str(sid), "title": title,
        "quote": quote, "parent_native_id": None, "url": None,
        "lang": "zh", "lang_source": "heuristic", "listed_price_minor": None,
        "effective_price_minor": None, "reference_price_minor": None, "wants": None,
        "collected_at": "2026-10-25T00:00:00Z", "collected_at_scope": "row",
        "origin_kind": "synthetic", "raw_sha256": "a" * 64, "content_hash": f"h{sid}",
        "raw_ref": "x", "batch_id": "b",
    }


def insert(conn, sid, title, quote, platform="xianyu"):
    s = signal(sid, title, quote, platform)
    conn.execute(
        "INSERT INTO signals(id,platform,native_id,parent_native_id,url,title,quote,lang,lang_source,"
        "listed_price_minor,effective_price_minor,reference_price_minor,wants,collected_at,"
        "collected_at_scope,origin_kind,raw_sha256,content_hash,raw_ref,batch_id,version,created_at,updated_at) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,1,?,?)",
        (sid, s["platform"], s["native_id"], None, None, title, quote, "zh", "heuristic",
         None, None, None, None, s["collected_at"], "row", "synthetic",
         "a" * 64, f"h{sid}", "x", "b", "2026-10-25T00:00:00Z", "2026-10-25T00:00:00Z"))
    conn.commit()


class CategoryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.conn = db.init_db(pathlib.Path(self.tmp.name) / "s.sqlite3")

    def tearDown(self):
        self.conn.close()
        self.tmp.cleanup()

    def test_identity_excludes_platform_title_and_alias_merge(self):
        a = categories.identity_key({"audience": "student", "task": "study_planning",
                                     "deliverable_family": "notion_template", "locale": "zh"})
        b = categories.identity_key({"audience": "student", "task": "study_planning",
                                     "deliverable_family": "notion_template", "locale": "zh"})
        self.assertEqual(a, b)
        insert(self.conn, 1, "学习计划 Notion 模板", "学生 学习计划 notion 模板", "xianyu")
        out = categories.categorize_signal(self.conn, dict(self.conn.execute("SELECT * FROM signals").fetchone()))
        self.assertEqual(out["outcome"], "new")
        self.conn.execute("INSERT INTO category_alias(category_id,alias_norm,created_at,source) VALUES (?,?,?,?)",
                          (out["category_id"], "同义学习计划", "2026-10-25T00:00:00Z", "manual"))
        insert(self.conn, 2, "同义学习计划", "学生 学习计划 notion 模板", "bilibili")
        out2 = categories.categorize_signal(self.conn, dict(self.conn.execute("SELECT * FROM signals WHERE id=2").fetchone()))
        self.assertEqual(out2["outcome"], "update")
        self.assertEqual(out2["category_id"], out["category_id"])

    def test_partial_unknown_combo_goes_review(self):
        # task known + family unknown -> review, no category (strict threshold).
        insert(self.conn, 1, "学生 学习计划", "学生 学习计划 没有交付形态")
        out = categories.categorize_signal(self.conn, dict(self.conn.execute("SELECT * FROM signals").fetchone()))
        self.assertEqual(out["outcome"], "review")
        self.assertEqual(out["fields"]["deliverable_family"], "unknown")
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM categories").fetchone()[0], 0)
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM review_queue").fetchone()[0], 1)

    def test_unknown_fields_go_review_not_merge(self):
        insert(self.conn, 1, "随便", "完全没有关键词")
        out = categories.categorize_signal(self.conn, dict(self.conn.execute("SELECT * FROM signals").fetchone()))
        self.assertEqual(out["outcome"], "review")
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM categories").fetchone()[0], 0)
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM review_queue").fetchone()[0], 1)

    def test_merge_undo_and_exclude_include(self):
        insert(self.conn, 1, "学习计划 Notion 模板", "学生 学习计划 notion 模板")
        insert(self.conn, 2, "客户 Excel 表格", "自由职业 客户 excel 表格")
        c1 = categories.categorize_signal(self.conn, dict(self.conn.execute("SELECT * FROM signals WHERE id=1").fetchone()))
        c2 = categories.categorize_signal(self.conn, dict(self.conn.execute("SELECT * FROM signals WHERE id=2").fetchone()))
        self.assertNotEqual(c1["category_id"], c2["category_id"])
        m = categories.merge(self.conn, c1["category_id"], c2["category_id"])
        row = self.conn.execute("SELECT status,merged_into FROM categories WHERE id=?", (c1["category_id"],)).fetchone()
        self.assertEqual((row["status"], row["merged_into"]), ("merged", c2["category_id"]))
        categories.undo(self.conn, m["event_id"])
        row = self.conn.execute("SELECT status,merged_into FROM categories WHERE id=?", (c1["category_id"],)).fetchone()
        self.assertEqual((row["status"], row["merged_into"]), ("active", None))
        e = categories.exclude(self.conn, c1["category_id"])
        self.assertEqual(self.conn.execute("SELECT status FROM categories WHERE id=?", (c1["category_id"],)).fetchone()[0], "excluded")
        categories.undo(self.conn, e["event_id"])
        self.assertEqual(self.conn.execute("SELECT status FROM categories WHERE id=?", (c1["category_id"],)).fetchone()[0], "active")
        categories.include(self.conn, c1["category_id"])
        self.assertEqual(self.conn.execute("SELECT status FROM categories WHERE id=?", (c1["category_id"],)).fetchone()[0], "active")

    def test_split_event_and_undo(self):
        insert(self.conn, 1, "学习计划 Notion 模板", "学生 学习计划 notion 模板")
        out = categories.categorize_signal(self.conn, dict(self.conn.execute("SELECT * FROM signals").fetchone()))
        split = categories.split(self.conn, out["category_id"], [1], "split child")
        self.assertTrue(split["new_category_id"])
        undo = categories.undo(self.conn, split["event_id"])
        self.assertEqual(undo["undo_of"], split["event_id"])
        self.assertTrue(self.conn.execute("SELECT COUNT(*) FROM discovery_event WHERE kind='undo'").fetchone()[0])

    def test_merge_dual_cards_atomic_and_undo_target_counts(self):
        insert(self.conn, 1, "学习计划 Notion 模板", "学生 学习计划 notion 模板")
        insert(self.conn, 2, "客户 Excel 表格", "自由职业 客户 excel 表格")
        c1 = categories.categorize_signal(self.conn, dict(self.conn.execute("SELECT * FROM signals WHERE id=1").fetchone()))
        c2 = categories.categorize_signal(self.conn, dict(self.conn.execute("SELECT * FROM signals WHERE id=2").fetchone()))
        categories.make_cards(self.conn)
        target_events_before = self.conn.execute("SELECT COUNT(*) FROM discovery_event WHERE category_id=?", (c2["category_id"],)).fetchone()[0]
        target_cards_before = self.conn.execute("SELECT COUNT(*) FROM direction_card WHERE category_id=?", (c2["category_id"],)).fetchone()[0]
        self.assertEqual(target_cards_before, 1)
        merged = categories.merge(self.conn, c1["category_id"], c2["category_id"])
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM direction_card WHERE category_id=?", (c2["category_id"],)).fetchone()[0], 1)
        src_card = self.conn.execute("SELECT status,merged_into FROM direction_card WHERE category_id=?", (c1["category_id"],)).fetchone()
        self.assertEqual((src_card["status"], src_card["merged_into"]), ("merged", c2["category_id"]))
        categories.undo(self.conn, merged["event_id"])
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM discovery_event WHERE category_id=?", (c2["category_id"],)).fetchone()[0], target_events_before)
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM direction_card WHERE category_id=?", (c2["category_id"],)).fetchone()[0], target_cards_before)
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM direction_card WHERE category_id=?", (c1["category_id"],)).fetchone()[0], 1)
        self.assertEqual(self.conn.execute("SELECT status FROM categories WHERE id=?", (c1["category_id"],)).fetchone()[0], "active")

    def test_split_undo_restores_evidence_and_events(self):
        insert(self.conn, 1, "学习计划 Notion 模板", "学生 学习计划 notion 模板")
        insert(self.conn, 2, "学习计划 Notion 模板 新版", "学生 学习计划 notion 模板")
        c1 = categories.categorize_signal(self.conn, dict(self.conn.execute("SELECT * FROM signals WHERE id=1").fetchone()))
        categories.categorize_signal(self.conn, dict(self.conn.execute("SELECT * FROM signals WHERE id=2").fetchone()))
        categories.make_cards(self.conn)
        before = self.conn.execute("SELECT evidence_ids_json FROM direction_card WHERE category_id=?", (c1["category_id"],)).fetchone()[0]
        split = categories.split(self.conn, c1["category_id"], [1])
        after = self.conn.execute("SELECT evidence_ids_json FROM direction_card WHERE category_id=?", (c1["category_id"],)).fetchone()[0]
        self.assertNotEqual(before, after)
        self.assertEqual(self.conn.execute("SELECT category_id FROM discovery_event WHERE signal_id=1 AND kind IN ('new','update')").fetchone()[0], split["new_category_id"])
        categories.undo(self.conn, split["event_id"])
        restored = self.conn.execute("SELECT evidence_ids_json FROM direction_card WHERE category_id=?", (c1["category_id"],)).fetchone()[0]
        self.assertEqual(json.loads(restored), json.loads(before))
        self.assertEqual(self.conn.execute("SELECT category_id FROM discovery_event WHERE signal_id=1 AND kind IN ('new','update')").fetchone()[0], c1["category_id"])

    def test_idempotent_run_and_review_no_duplicate(self):
        insert(self.conn, 1, "学习计划 Notion 模板", "学生 学习计划 notion 模板")
        insert(self.conn, 2, "完全未知", "无关键词")
        r1 = categories.run_categorize(self.conn)
        ev1 = self.conn.execute("SELECT COUNT(*) FROM discovery_event").fetchone()[0]
        r2 = categories.run_categorize(self.conn)
        ev2 = self.conn.execute("SELECT COUNT(*) FROM discovery_event").fetchone()[0]
        self.assertEqual((r1["new"], r1["review"]), (1, 1))
        self.assertEqual((r2["new"], r2["update"], r2["review"], r2["skipped"]), (0, 0, 0, 2))
        self.assertEqual(ev1, ev2)
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM review_queue WHERE status='pending'").fetchone()[0], 1)

    def test_cards_refresh_evidence_and_gaps(self):
        insert(self.conn, 1, "学习计划 Notion 模板", "学生 学习计划 notion 模板")
        c = categories.categorize_signal(self.conn, dict(self.conn.execute("SELECT * FROM signals WHERE id=1").fetchone()))
        categories.make_cards(self.conn)
        first = self.conn.execute("SELECT * FROM direction_card WHERE category_id=?", (c["category_id"],)).fetchone()
        insert(self.conn, 2, "学习计划 Notion 模板 新", "学生 学习计划 notion 模板")
        categories.categorize_signal(self.conn, dict(self.conn.execute("SELECT * FROM signals WHERE id=2").fetchone()))
        cards = categories.make_cards(self.conn)
        self.assertEqual(cards["refreshed"], 1)
        refreshed = self.conn.execute("SELECT * FROM direction_card WHERE category_id=?", (c["category_id"],)).fetchone()
        self.assertNotEqual(first["evidence_ids_json"], refreshed["evidence_ids_json"])
        self.assertEqual(json.loads(refreshed["evidence_ids_json"]), [1, 2])
        self.assertIn("price_unknown", json.loads(refreshed["gaps_json"]))
        # merged tombstone is not revived
        other = categories.split(self.conn, c["category_id"], [1])
        child_card = self.conn.execute("SELECT * FROM direction_card WHERE category_id=?", (other["new_category_id"],)).fetchone()
        self.assertEqual(child_card["status"], "draft")

    def test_excluded_goes_review_and_merged_follows_target(self):
        insert(self.conn, 1, "学习计划 Notion 模板", "学生 学习计划 notion 模板")
        c1 = categories.categorize_signal(self.conn, dict(self.conn.execute("SELECT * FROM signals WHERE id=1").fetchone()))
        categories.exclude(self.conn, c1["category_id"])
        insert(self.conn, 2, "学习计划 Notion 模板 新", "学生 学习计划 notion 模板")
        out = categories.categorize_signal(self.conn, dict(self.conn.execute("SELECT * FROM signals WHERE id=2").fetchone()))
        self.assertEqual(out["outcome"], "review")
        self.assertIn("category_excluded", self.conn.execute("SELECT reason FROM review_queue WHERE signal_id=2").fetchone()[0])
        # separate merge target chain: c3 -> c4; new signal follows to c4
        insert(self.conn, 3, "客户 Excel 表格", "自由职业 客户 excel 表格")
        insert(self.conn, 4, "学习计划 提示词模板", "学生 学习计划 提示词模板")
        c3 = categories.categorize_signal(self.conn, dict(self.conn.execute("SELECT * FROM signals WHERE id=3").fetchone()))
        c4 = categories.categorize_signal(self.conn, dict(self.conn.execute("SELECT * FROM signals WHERE id=4").fetchone()))
        self.assertNotEqual(c3["category_id"], c4["category_id"])
        categories.merge(self.conn, c3["category_id"], c4["category_id"])
        insert(self.conn, 5, "学习计划 提示词模板 新", "学生 学习计划 提示词模板")
        out2 = categories.categorize_signal(self.conn, dict(self.conn.execute("SELECT * FROM signals WHERE id=5").fetchone()))
        self.assertEqual(out2["outcome"], "update")
        self.assertEqual(out2["category_id"], c4["category_id"])

    def test_carrier_normalization_merges_family(self):
        insert(self.conn, 1, "学习计划 Notion 模板", "学生 学习计划 notion 模板")
        insert(self.conn, 2, "学习计划 Excel 表格", "学生 学习计划 excel 表格")
        a = categories.categorize_signal(self.conn, dict(self.conn.execute("SELECT * FROM signals WHERE id=1").fetchone()))
        b = categories.categorize_signal(self.conn, dict(self.conn.execute("SELECT * FROM signals WHERE id=2").fetchone()))
        self.assertEqual(a["category_id"], b["category_id"])
        self.assertTrue(b["carrier_changed"])
        carriers = json.loads(self.conn.execute("SELECT deliverable_carriers FROM categories WHERE id=?", (a["category_id"],)).fetchone()[0])
        self.assertEqual(sorted(carriers), ["excel_template", "notion_template"])

    def test_cards_and_split(self):
        insert(self.conn, 1, "学习计划 Notion 模板", "学生 学习计划 notion 模板")
        insert(self.conn, 2, "客户 Excel 表格", "自由职业 客户 excel 表格")
        for sid in (1, 2):
            categories.categorize_signal(self.conn, dict(self.conn.execute("SELECT * FROM signals WHERE id=?", (sid,)).fetchone()))
        cards = categories.make_cards(self.conn)
        self.assertEqual(cards["created"], 2)
        card = categories.list_cards(self.conn)[0]
        self.assertTrue(json.loads(card["evidence_ids_json"]))
        self.assertIn("price_unknown", json.loads(card["gaps_json"]))
        cat = self.conn.execute("SELECT * FROM categories WHERE id=?", (card["category_id"],)).fetchone()
        out = categories.split(self.conn, cat["id"], [1])
        self.assertTrue(out["new_category_id"])
        self.assertTrue(self.conn.execute("SELECT COUNT(*) FROM discovery_event WHERE kind='split'").fetchone()[0])


if __name__ == "__main__":
    unittest.main()
