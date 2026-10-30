"""Xianyu JSONL/CSV imported-signal tests; temp DB only."""

from __future__ import annotations

import json
import pathlib
import tempfile
import unittest

from tools.selection import db, xianyu


def row(item_id="1052243348747", raw_text="¥ 1 .88 12人想要 ¥9.9", title="t"):
    return {
        "href": f"https://www.goofish.com/item?id={item_id}&categoryId=1",
        "title": title, "price": "¥ 1", "raw_text": raw_text, "platform": "xianyu",
    }


class XianyuTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = pathlib.Path(self.tmp.name) / "selection.sqlite3"
        self.source = pathlib.Path(self.tmp.name) / "items.jsonl"

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, rows):
        self.source.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n",
                               encoding="utf-8")

    def test_import_effective_wants_origin_and_bad_row(self):
        self.write([row(), row(item_id="2", raw_text="¥ 1 3人想要"), {"title": "bad"}])
        out = xianyu.import_file(self.source, db_path=self.db,
                                 collected_at="2026-10-22T08:46:35Z")
        self.assertEqual((out["rows"], out["new"], len(out["errors"])), (3, 2, 1))
        self.assertEqual(out["wants_sum"], 15)
        self.assertEqual(out["wants_missing"], 0)
        self.assertEqual(out["reference_present"], 1)
        conn = db.init_db(self.db)
        row1 = conn.execute("SELECT * FROM signals WHERE native_id='1052243348747'").fetchone()
        self.assertEqual(row1["origin_kind"], "imported")
        self.assertEqual(row1["effective_price_minor"], 188)
        self.assertEqual(row1["listed_price_minor"], 100)
        self.assertEqual(row1["wants"], 12)
        self.assertEqual(row1["lang_source"], "heuristic")
        self.assertEqual(row1["collected_at_scope"], "batch")
        self.assertTrue(row1["content_hash"])
        conn.close()

    def test_reimport_duplicate_then_update(self):
        self.write([row()])
        first = xianyu.import_file(self.source, db_path=self.db,
                                   collected_at="2026-10-22T08:46:35Z")
        second = xianyu.import_file(self.source, db_path=self.db,
                                    collected_at="2026-10-22T08:46:35Z")
        self.assertEqual((first["new"], second["new"], second["duplicate"]), (1, 0, 1))
        self.write([row(raw_text="¥ 1 .10 99人想要")])
        third = xianyu.import_file(self.source, db_path=self.db,
                                   collected_at="2026-10-22T08:46:35Z")
        self.assertEqual((third["new"], third["updated"]), (0, 1))
        conn = db.init_db(self.db)
        row1 = conn.execute("SELECT * FROM signals WHERE native_id='1052243348747'").fetchone()
        self.assertEqual((row1["effective_price_minor"], row1["wants"], row1["version"]), (110, 99, 2))
        conn.close()

    def test_bad_json_line_continues_partial(self):
        good = json.dumps(row(), ensure_ascii=False)
        self.source.write_text(good + "\n{bad json\n" + json.dumps(row(item_id="2"), ensure_ascii=False) + "\n",
                               encoding="utf-8")
        out = xianyu.import_file(self.source, db_path=self.db)
        self.assertEqual((out["rows"], out["ok_rows"], out["bad_rows"], len(out["errors"])), (3, 2, 1, 1))
        self.assertEqual(out["new"], 2)
        self.assertEqual(out["status"], "partial")

    def test_bad_json_max_errors_stops(self):
        self.source.write_text("{bad1\n{bad2\n", encoding="utf-8")
        out = xianyu.import_file(self.source, db_path=self.db, max_errors=1)
        self.assertEqual(out["stop_reason"], "errors_exceeded")
        self.assertEqual(out["status"], "stopped")
        self.assertEqual(out["bad_rows"], 1)

    def test_csv_and_missing_wants(self):
        csv_path = pathlib.Path(self.tmp.name) / "items.csv"
        csv_path.write_text(
            "href,title,price,raw_text,platform\n"
            "https://www.goofish.com/item?id=777&categoryId=1,t,¥ 1,no wants here,xianyu\n",
            encoding="utf-8")
        out = xianyu.import_file(csv_path, db_path=self.db)
        self.assertEqual((out["new"], out["wants_missing"]), (1, 1))
        conn = db.init_db(self.db)
        row1 = conn.execute("SELECT * FROM signals WHERE native_id='777'").fetchone()
        self.assertIsNone(row1["wants"])
        self.assertEqual(row1["effective_price_minor"], 100)
        conn.close()

    def test_unparseable_native_id_rejected(self):
        self.write([{**row(), "href": "https://www.goofish.com/item?categoryId=1"}])
        out = xianyu.import_file(self.source, db_path=self.db)
        self.assertEqual(out["new"], 0)
        self.assertEqual(len(out["errors"]), 1)
        self.assertIn("native_id", out["errors"][0]["reason"])


if __name__ == "__main__":
    unittest.main()
