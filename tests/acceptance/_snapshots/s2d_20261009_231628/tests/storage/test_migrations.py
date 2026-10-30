"""Storage checks: repeatable initialization, seeds, and the contract's integrity constraints."""

from __future__ import annotations

import pathlib
import sqlite3
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from app.storage.db import connect, ensure_schema, schema_version  # noqa: E402

TMP_ROOT = pathlib.Path(__file__).resolve().parent / "_tmp"


class MigrationTest(unittest.TestCase):
    def setUp(self):
        TMP_ROOT.mkdir(parents=True, exist_ok=True)
        self.tmp = tempfile.mkdtemp(prefix="db_", dir=str(TMP_ROOT))
        self.db_path = str(pathlib.Path(self.tmp) / "app.db")

    def test_schema_applies_and_is_repeatable(self):
        self.assertEqual(ensure_schema(self.db_path), 2)
        self.assertEqual(ensure_schema(self.db_path), 2)  # second run is a no-op
        conn = connect(self.db_path)
        try:
            tables = {r["name"] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            for expected in ("candidate", "demand_signal", "evidence", "supply_offer", "cost_item",
                             "gate_review", "review_item", "import_batch", "import_row_result",
                             "run_record", "idempotency_key", "source", "draft", "feedback"):
                self.assertIn(expected, tables)
            self.assertEqual(schema_version(self.db_path), 2)
        finally:
            conn.close()

    def test_seed_sources_exist(self):
        ensure_schema(self.db_path)
        conn = connect(self.db_path)
        try:
            names = {r["name"] for r in conn.execute("SELECT name FROM source")}
            self.assertEqual(names, {"manual_import", "xianyu", "xiaohongshu", "bilibili"})
            modes = {r["access_mode"] for r in conn.execute("SELECT access_mode FROM source")}
            self.assertEqual(modes, {"manual_import"})
        finally:
            conn.close()

    def test_input_money_must_be_non_negative_and_derived_columns_are_free(self):
        ensure_schema(self.db_path)
        conn = connect(self.db_path)
        try:
            conn.execute("INSERT INTO candidate(id,title,identity_key,identity_source,status,status_reason,"
                         "status_updated_at,title_norm_hash,data_origin,created_at,updated_at) VALUES "
                         "('c_1','t','k','title','pending','derived:pending|gates_incomplete','2026-01-01T00:00:00Z',"
                         "'h','synthetic','2026-01-01T00:00:00Z','2026-01-01T00:00:00Z')")
            with self.assertRaises(sqlite3.IntegrityError):
                conn.execute("INSERT INTO supply_offer(id,candidate_id,provider_name,provider_url,url_norm,origin_type,"
                             "format_version,unit_price_minor,downloadable,commercial_allowed,redistribute_allowed,"
                             "resale_allowed,sample_checked,status,data_origin,created_at,updated_at) VALUES "
                             "('sp_1','c_1','p','u','un','unknown','',-1,'yes','yes','yes','yes','none','candidate',"
                             "'synthetic','2026-01-01T00:00:00Z','2026-01-01T00:00:00Z')")
            # value_kind='minutes' is only allowed for manual_labor
            with self.assertRaises(sqlite3.IntegrityError):
                conn.execute("INSERT INTO cost_item(id,candidate_id,role,basis,value_kind,minutes,variant,currency,"
                             "fact_kind,is_active,data_origin,created_at) VALUES "
                             "('ci_1','c_1','platform_fee','per_order','minutes',5,'base','CNY','fact',1,'synthetic',"
                             "'2026-01-01T00:00:00Z')")
            # sale_price may be NULL (unknown) or money, never another kind
            with self.assertRaises(sqlite3.IntegrityError):
                conn.execute("INSERT INTO cost_item(id,candidate_id,role,basis,value_kind,rate_bp,variant,currency,"
                             "fact_kind,is_active,data_origin,created_at) VALUES "
                             "('ci_2','c_1','sale_price','per_order','rate',500,'base','CNY','fact',1,'synthetic',"
                             "'2026-01-01T00:00:00Z')")
            # unknown rows are legal: all value columns stay NULL
            conn.execute("INSERT INTO cost_item(id,candidate_id,role,basis,value_kind,variant,currency,fact_kind,"
                         "is_active,data_origin,created_at) VALUES "
                         "('ci_3','c_1','payment_fee','per_order',NULL,'base','CNY','assumption',1,'synthetic',"
                         "'2026-01-01T00:00:00Z')")
            # recurring requires a period
            with self.assertRaises(sqlite3.IntegrityError):
                conn.execute("INSERT INTO cost_item(id,candidate_id,role,basis,value_kind,money_minor,variant,currency,"
                             "fact_kind,is_active,data_origin,created_at) VALUES "
                             "('ci_4','c_1','procurement','recurring','money',100,'base','CNY','fact',1,'synthetic',"
                             "'2026-01-01T00:00:00Z')")
        finally:
            conn.close()

    def test_run_record_allows_null_source_and_rejects_source_dash_string(self):
        ensure_schema(self.db_path)
        conn = connect(self.db_path)
        try:
            conn.execute("INSERT INTO run_record(id,run_type,trigger,logical_date,source_id,status,started_at) VALUES "
                         "('r_1','import','manual','2026-01-01',NULL,'ok','2026-01-01T00:00:00Z')")
            with self.assertRaises(sqlite3.IntegrityError):
                conn.execute("INSERT INTO run_record(id,run_type,trigger,logical_date,source_id,status,started_at) VALUES "
                             "('r_2','import','manual','2026-01-01','','ok','2026-01-01T00:00:00Z')")
        finally:
            conn.close()


if __name__ == "__main__":
    unittest.main()
