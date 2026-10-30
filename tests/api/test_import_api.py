"""End-to-end import/query checks on a clean temp database (stdlib unittest only)."""

from __future__ import annotations

import json
import pathlib
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from app import create_app  # noqa: E402
from app.storage.db import connect  # noqa: E402

TMP_ROOT = pathlib.Path(__file__).resolve().parent / "_tmp"

POSITIVE_CSV = (
    "title,data_origin,category,use_case,sale_price,platform_fee_bp,payment_fee_bp,acquisition_cost,"
    "refund_rate_bp,procurement_unit_cost,procurement_cost,procurement_recurring_cost,procurement_period,"
    "manual_minutes,manual_hourly_rate,other_cost,cost_supply_url,scenario_variant,currency,observed_at,"
    "demand_source,demand_url,demand_excerpt,demand_kind,demand_published_date,supply_provider,supply_url,"
    "supply_native_id,supply_origin_type,supply_format_version,supply_price,supply_commercial_allowed,"
    "supply_redistribute_allowed,supply_resale_allowed,supply_sample_checked,supply_sample_note,"
    "supply_evidence_url,supply_evidence_excerpt\n"
    "示例-周会纪要模板包,synthetic,模板,小团队周会记录,9.90,500,0,0,0,0,0,0,monthly,15,30.00,0,"
    "https://example.com/supply/2001,base,CNY,2026-06-01T08:00:00Z,xianyu,https://example.com/demand/1001,"
    "求一份能直接套用的周会纪要模板,specific_ask,2026-05-20,示例开放模板库,https://example.com/supply/2001,"
    "tpl-2001,open_repo,v1,0,yes,yes,yes,partial,抽样查看了 3 个文件的结构与占位符,"
    "https://example.com/supply/2001/license,本库素材可用于商业用途并允许转售（示例摘录）\n"
)

POSITIVE_JSON = json.dumps(
    [
        {
            "title": "示例-简历模板合集",
            "data_origin": "synthetic",
            "use_case": "应届生投递",
            "sale_price_minor": 1990,
            "platform_fee_bp": 500,
            "payment_fee_bp": 60,
            "acquisition_cost": "0",
            "refund_rate_bp": 200,
            "procurement_unit_cost": "0",
            "manual_minutes": 20,
            "manual_hourly_rate": "30.00",
            "demand_source": "xiaohongshu",
            "demand_url": "https://example.com/demand/1002",
            "demand_excerpt": "有没有可以直接改的简历模板",
            "demand_kind": "want_to_buy",
            "supply_provider": "示例开放素材库",
            "supply_url": "https://example.com/supply/2002",
            "supply_native_id": "tpl-2002",
            "supply_price": "0",
            "supply_commercial_allowed": "yes",
            "supply_redistribute_allowed": "no",
            "supply_resale_allowed": "unknown",
            "supply_sample_checked": "none",
        }
    ],
    ensure_ascii=False,
)

NEGATIVE_CSV = (
    "title,data_origin,observed_at,sale_price,sale_price_minor,demand_url,demand_excerpt,supply_url\n"
    ",synthetic,2026-06-01T08:00:00Z,12.00,,,,\n"
    "示例-金额三位小数,synthetic,2026-06-01T08:00:00Z,12.345,,,,\n"
    "示例-双表示冲突,synthetic,2026-06-01T08:00:00Z,12.00,1300,,,\n"
    "示例-负金额,synthetic,2026-06-01T08:00:00Z,-9.90,,,,\n"
    "示例-时区缺失,synthetic,2026-06-01 08:00:00,9.90,,,,\n"
    "示例-真实行用示例域,real,2026-06-01T08:00:00Z,9.90,,https://example.com/demand/1005,一条求购信息,\n"
    "示例-需求组缺摘录,synthetic,2026-06-01T08:00:00Z,9.90,,https://example.com/demand/1003,,\n"
    "示例-货源组缺许可,synthetic,2026-06-01T08:00:00Z,9.90,,,,https://example.com/supply/2001\n"
    "示例-行宽不一致,synthetic,2026-06-01T08:00:00Z,9.90,,,,,多余值\n"
)

TWO_CHANNELS_CSV = (
    "title,data_origin,demand_source,demand_native_id,demand_url,demand_excerpt\n"
    "示例-渠道A,synthetic,xianyu,1001,https://example.com/demand/a,求模板\n"
    "示例-渠道B,synthetic,bilibili,1001,https://example.com/demand/b,求模板\n"
)

NULL_VS_ZERO_CSV = (
    "title,data_origin,sale_price\n"
    "示例-成本未知,synthetic,\n"
    "示例-成本为零,synthetic,0\n"
)

TITLE_ONLY_CSV = "title,data_origin,category\n示例-仅基础组,synthetic,模板\n"

TABLES = ("candidate", "demand_signal", "evidence", "supply_offer", "cost_item", "import_batch", "run_record")
# Business tables only: a repeated/rejected import may still create a batch and a run record.
BUSINESS = ("candidate", "demand_signal", "evidence", "supply_offer", "cost_item")


class ImportApiTest(unittest.TestCase):
    def setUp(self):
        TMP_ROOT.mkdir(parents=True, exist_ok=True)
        self.tmp = tempfile.mkdtemp(prefix="api_", dir=str(TMP_ROOT))
        self.db_path = str(pathlib.Path(self.tmp) / "app.db")
        self.app = create_app({"db_path": self.db_path})
        self.client = self.app.test_client()

    # ---------------- helpers
    def post_csv(self, text: str, mode: str = "atomic", client_ref: str | None = None):
        url = f"/api/imports?format=csv&mode={mode}"
        headers = {}
        if client_ref:
            url += f"&client_ref={client_ref}"
        return self.client.post(url, data=text.encode("utf-8"), content_type="text/csv", headers=headers)

    def post_json(self, text: str, mode: str = "atomic", client_ref: str | None = None):
        url = f"/api/imports?format=json&mode={mode}"
        if client_ref:
            url += f"&client_ref={client_ref}"
        return self.client.post(url, data=text.encode("utf-8"), content_type="application/json")

    def counts(self, *tables: str) -> dict:
        conn = connect(self.db_path)
        try:
            return {t: conn.execute(f"SELECT COUNT(*) AS n FROM {t}").fetchone()["n"] for t in tables}
        finally:
            conn.close()

    def query(self, sql: str, params=()):
        conn = connect(self.db_path)
        try:
            return [dict(r) for r in conn.execute(sql, params).fetchall()]
        finally:
            conn.close()

    # ---------------- tests
    def test_health_and_empty_start(self):
        health = self.client.get("/api/health")
        self.assertEqual(health.status_code, 200)
        body = health.get_json()
        self.assertTrue(body["ok"])
        self.assertEqual(body["schema_version"], 2)
        self.assertEqual(self.client.get("/api/candidates").get_json()["total"], 0)

    def test_positive_csv_import_counts_and_run_record(self):
        resp = self.post_csv(POSITIVE_CSV)
        self.assertEqual(resp.status_code, 201, resp.get_data(as_text=True))
        payload = resp.get_json()
        self.assertEqual(payload["status"], "committed")
        self.assertEqual(payload["counts"]["created"], 1)
        counts = self.counts(*TABLES)
        self.assertEqual(counts["candidate"], 1)
        self.assertEqual(counts["demand_signal"], 1)
        self.assertEqual(counts["evidence"], 2)  # demand evidence + clause evidence
        self.assertEqual(counts["supply_offer"], 1)
        self.assertEqual(counts["cost_item"], 10)
        runs = self.query("SELECT * FROM run_record")
        self.assertEqual(len(runs), 1)
        self.assertIsNone(runs[0]["source_id"])  # no '' dangling FK value

    def test_detail_exposes_evidence_and_keeps_gates_pending(self):
        self.post_csv(POSITIVE_CSV)
        candidate_id = self.client.get("/api/candidates").get_json()["items"][0]["id"]
        detail = self.client.get(f"/api/candidates/{candidate_id}").get_json()
        self.assertEqual(detail["derived_status"], "pending")
        self.assertEqual(set(detail["gates"].values()), {"unverified"})
        self.assertEqual(len(detail["cost_items"]), 10)
        self.assertEqual(detail["candidate"]["identity_key"].startswith("u:xianyu:"), True)
        labor = [c for c in detail["cost_items"] if c["role"] == "manual_labor"][0]
        self.assertEqual(labor["minutes"], 15)
        self.assertEqual(labor["hourly_rate_minor"], 3000)
        self.assertEqual(labor["money_minor"], None)
        periods = {(c["role"], c["basis"]): c["period"] for c in detail["cost_items"]}
        self.assertEqual(periods[("procurement", "recurring")], "monthly")  # only the recurring row carries a period
        self.assertEqual(periods[("procurement", "per_order")], None)
        self.assertEqual(periods[("sale_price", "per_order")], None)

    def test_reimport_same_file_does_not_proliferate(self):
        self.post_csv(POSITIVE_CSV)
        before = self.counts(*BUSINESS)
        batches_before = self.counts("import_batch")["import_batch"]
        second = self.post_csv(POSITIVE_CSV)
        self.assertEqual(second.status_code, 201)
        payload = second.get_json()
        self.assertEqual(payload["counts"]["duplicate_skipped"], 1)
        self.assertEqual(payload["counts"]["created"], 0)
        self.assertEqual(self.counts(*BUSINESS), before)
        self.assertEqual(self.counts("import_batch")["import_batch"], batches_before + 1)  # new batch only
        self.assertEqual(self.counts("run_record")["run_record"], 2)  # one run record per import

    def test_content_change_adds_version(self):
        self.post_csv(POSITIVE_CSV)
        changed = POSITIVE_CSV.replace("求一份能直接套用的周会纪要模板", "求一份能直接套用的周会纪要模板，最好带示例")
        resp = self.post_csv(changed)
        self.assertEqual(resp.get_json()["counts"]["version_added"], 1)
        signals = self.query("SELECT id, version_no, superseded_by FROM demand_signal ORDER BY version_no")
        self.assertEqual(len(signals), 2)
        self.assertEqual(signals[0]["superseded_by"], signals[1]["id"])
        self.assertEqual(self.counts("candidate")["candidate"], 1)

    def test_cross_channel_same_native_id_stays_two_candidates(self):
        resp = self.post_csv(TWO_CHANNELS_CSV)
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(self.counts("candidate")["candidate"], 2)
        keys = {row["identity_key"] for row in self.query("SELECT identity_key FROM candidate")}
        self.assertEqual(keys, {"n:xianyu:1001", "n:bilibili:1001"})

    def test_json_positive_sample_maps_minor_and_yuan_forms(self):
        resp = self.post_json(POSITIVE_JSON)
        self.assertEqual(resp.status_code, 201, resp.get_data(as_text=True))
        costs = self.query("SELECT role, value_kind, money_minor, rate_bp, minutes, hourly_rate_minor FROM cost_item")
        self.assertEqual(len(costs), 7)
        sale = [c for c in costs if c["role"] == "sale_price"][0]
        self.assertEqual(sale["money_minor"], 1990)  # JSON number allowed for *_minor
        labor = [c for c in costs if c["role"] == "manual_labor"][0]
        self.assertEqual((labor["minutes"], labor["hourly_rate_minor"]), (20, 3000))  # "30.00" 元/时

    def test_negative_rows_are_rejected_atomically_with_reasons(self):
        before = self.counts(*BUSINESS)
        resp = self.post_csv(NEGATIVE_CSV)
        self.assertEqual(resp.status_code, 422)
        payload = resp.get_json()
        self.assertEqual(payload["status"], "rejected")
        self.assertEqual(self.counts(*BUSINESS), before)  # no partial residue in business tables
        batches = self.query("SELECT status FROM import_batch")
        self.assertEqual([b["status"] for b in batches], ["rejected"])  # the batch itself is kept
        batch_id = payload["batch_id"]
        stored = self.client.get(f"/api/imports/{batch_id}").get_json()
        reasons = {r["reason_code"] for r in stored["row_results"]}
        for code in ("V2", "V5", "V21", "V22", "V7", "V4", "V10", "V25"):
            self.assertIn(code, reasons)
        self.assertEqual(stored["batch"]["status"], "rejected")

    def test_validate_mode_writes_nothing(self):
        before = self.counts(*TABLES)
        resp = self.post_csv(POSITIVE_CSV, mode="validate")
        self.assertEqual(resp.status_code, 200)
        payload = resp.get_json()
        self.assertFalse(payload["saved"])
        self.assertEqual(payload["mode"], "validate")
        self.assertEqual(self.counts(*TABLES), before)  # no business rows, no batch, no run

    def test_idempotency_replay_and_conflict(self):
        first = self.post_csv(POSITIVE_CSV, client_ref="demo-1")
        self.assertEqual(first.status_code, 201)
        batches = self.counts("import_batch")["import_batch"]
        replay = self.post_csv(POSITIVE_CSV, client_ref="demo-1")
        self.assertEqual(replay.status_code, 200)
        self.assertTrue(replay.get_json()["deduplicated"])
        self.assertEqual(self.counts("import_batch")["import_batch"], batches)
        conflict = self.post_csv(NEGATIVE_CSV, client_ref="demo-1")
        self.assertEqual(conflict.status_code, 409)

    def test_unknown_cost_and_explicit_zero_are_distinct(self):
        resp = self.post_csv(NULL_VS_ZERO_CSV)
        self.assertEqual(resp.status_code, 201)
        rows = self.query(
            "SELECT c.title, ci.id AS cost_id, ci.money_minor FROM candidate c"
            " LEFT JOIN cost_item ci ON ci.candidate_id = c.id AND ci.role='sale_price'"
        )
        self.assertEqual(len(rows), 2)
        by_title = {r["title"]: r for r in rows}
        self.assertIsNone(by_title["示例-成本未知"]["cost_id"])  # no row at all: 未知
        self.assertEqual(by_title["示例-成本为零"]["money_minor"], 0)  # explicit 0 stays 0

    def test_title_only_row_reuses_candidate(self):
        self.post_csv(TITLE_ONLY_CSV)
        self.post_csv(TITLE_ONLY_CSV)
        self.assertEqual(self.counts("candidate")["candidate"], 1)
        key = self.query("SELECT identity_key FROM candidate")[0]["identity_key"]
        self.assertTrue(key.startswith("t:"))

    def test_sources_and_runs_endpoints(self):
        self.post_csv(POSITIVE_CSV)
        sources = self.client.get("/api/sources").get_json()["items"]
        self.assertEqual(len(sources), 4)
        self.assertEqual({s["access_mode"] for s in sources}, {"manual_import"})
        runs = self.client.get("/api/runs").get_json()["items"]
        self.assertGreaterEqual(len(runs), 1)
        self.assertEqual(runs[0]["run_type"], "import")

    def test_restart_keeps_data(self):
        self.post_csv(POSITIVE_CSV)
        restarted = create_app({"db_path": self.db_path})
        client = restarted.test_client()
        listing = client.get("/api/candidates").get_json()
        self.assertEqual(listing["total"], 1)
        detail = client.get(f"/api/candidates/{listing['items'][0]['id']}").get_json()
        self.assertEqual(len(detail["cost_items"]), 10)

    def test_page_routes_render_pages(self):
        """S2-C: the four page routes now render templates instead of 501 stubs."""
        for route in ("/", "/import", "/ops"):
            resp = self.client.get(route)
            self.assertEqual(resp.status_code, 200, route)
            self.assertIn("text/html", resp.headers.get("Content-Type", ""))
        not_found = self.client.get("/opportunity/c_x")
        self.assertEqual(not_found.status_code, 404)
        self.assertIn("未找到该候选", not_found.get_data(as_text=True))

    def test_oversized_and_malformed_inputs(self):
        self.assertEqual(self.client.post("/api/imports?format=csv&mode=atomic", data=b"", content_type="text/csv").status_code, 400)
        self.assertEqual(
            self.client.post("/api/imports?format=xml&mode=atomic", data=b"a,b\n1,2\n", content_type="text/plain").status_code,
            400,
        )
        self.assertEqual(
            self.client.post("/api/imports?format=json&mode=atomic", data=b"{}", content_type="application/json").status_code,
            400,
        )


    def test_same_content_different_url_creates_suspect_review(self):
        first = (
            "title,data_origin,demand_source,demand_url,demand_excerpt\n"
            "示例-同文,synthetic,xianyu,https://example.com/demand/x1,求同一份模板\n"
        )
        second = (
            "title,data_origin,demand_source,demand_url,demand_excerpt\n"
            "示例-同文,synthetic,xianyu,https://example.com/demand/x2,求同一份模板\n"
        )
        self.post_csv(first)
        payload = self.post_csv(second).get_json()
        self.assertEqual(payload["counts"]["suspect_review"], 1)
        reviews = self.query("SELECT kind, ref_id, ref_id_b, status FROM review_item")
        self.assertEqual(len(reviews), 1)
        self.assertEqual(reviews[0]["kind"], "dup_suspect")
        self.assertLess(reviews[0]["ref_id"], reviews[0]["ref_id_b"])  # order-normalized pair

    def test_same_demand_with_new_cost_row_keeps_sub_records(self):
        self.post_csv(POSITIVE_CSV)
        costs_before = self.counts("cost_item")["cost_item"]
        with_extra_cost = POSITIVE_CSV.rstrip("\n").replace(",0,https://example.com/supply/2001,base",
                                                 ",1.50,https://example.com/supply/2001,base") + "\n"
        payload = self.post_csv(with_extra_cost).get_json()
        self.assertEqual(payload["counts"]["created"], 1)  # sub-records created despite the demand hit
        results = {
            (r["action"], r["record_type"])
            for r in self.query("SELECT action, record_type FROM import_row_result WHERE row_no=1")
        }
        self.assertIn(("duplicate_skipped", "demand_signal"), results)  # V17: demand side skipped
        self.assertEqual(self.counts("cost_item")["cost_item"], costs_before + 1)
        rows = self.query("SELECT money_minor, is_active FROM cost_item WHERE role='other' ORDER BY created_at")
        self.assertEqual([(r["money_minor"], r["is_active"]) for r in rows], [(0, 0), (150, 1)])

    def test_real_and_synthetic_are_isolated(self):
        synthetic = "title,data_origin,demand_source,demand_native_id,demand_url,demand_excerpt\n示例-同键,synthetic,xianyu,2001,https://example.com/d/a,求模板\n"
        real = "title,data_origin,demand_source,demand_native_id,demand_url,demand_excerpt\n示例-同键,real,xianyu,2001,https://real.example.org/d/a,求模板\n"
        self.post_csv(synthetic)
        self.post_csv(real)
        self.assertEqual(self.counts("candidate")["candidate"], 2)
        origins = {r["data_origin"] for r in self.query("SELECT data_origin FROM candidate")}
        self.assertEqual(origins, {"real", "synthetic"})

    def test_non_utf8_body_is_rejected(self):
        resp = self.client.post("/api/imports?format=csv&mode=atomic",
                                data="title,data_origin\n示例,GBK编码\n".encode("gbk"), content_type="text/csv")
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.get_json()["error"]["code"], "encoding_error")
        self.assertEqual(self.counts(*BUSINESS), {t: 0 for t in BUSINESS})

    def test_url_only_supply_keeps_gap_and_observed_at_warning(self):
        csv_text = (
            "title,data_origin,observed_at,supply_provider,supply_url,supply_commercial_allowed,"
            "supply_redistribute_allowed,supply_resale_allowed,supply_evidence_url\n"
            "示例-仅链接货源,synthetic,2026-06-02T00:00:00Z,示例库,https://example.com/supply/9,yes,yes,yes,"
            "https://example.com/supply/9/license\n"
        )
        payload = self.post_csv(csv_text).get_json()
        self.assertEqual(payload["counts"]["created"], 1)
        rows = self.query("SELECT license_evidence_url, license_evidence_id FROM supply_offer")
        self.assertEqual(rows[0]["license_evidence_url"], "https://example.com/supply/9/license")
        self.assertIsNone(rows[0]["license_evidence_id"])  # no excerpt -> no evidence row
        self.assertEqual(self.counts("evidence")["evidence"], 0)
        warnings = [r["reason_code"] for r in self.query("SELECT reason_code FROM import_row_result")]
        self.assertIn("V23", warnings)  # observed_at has no landing field without a demand group

    def test_procurement_bases_are_independent(self):
        csv_text = "title,data_origin,procurement_unit_cost\n示例-仅逐单采购,synthetic,0\n"
        self.post_csv(csv_text)
        candidate_id = self.query("SELECT id FROM candidate")[0]["id"]
        from app.core.state import base_unknown_components  # local import keeps module import light

        conn = connect(self.db_path)
        try:
            unknown = base_unknown_components(conn, candidate_id)
        finally:
            conn.close()
        self.assertIn("procurement.one_time", unknown)
        self.assertIn("procurement.recurring", unknown)
        self.assertIn("other", unknown)
        self.assertNotIn("procurement.per_order", unknown)  # known zero is not unknown

    def test_list_order_is_stable_and_repeatable(self):
        self.post_csv(POSITIVE_CSV)
        first = self.client.get("/api/candidates?sort=default").get_json()["items"]
        second = self.client.get("/api/candidates?sort=default").get_json()["items"]
        self.assertEqual([i["id"] for i in first], [i["id"] for i in second])
        self.assertEqual(first[0]["status"], "pending")

    def test_idempotency_survives_restart(self):
        self.post_csv(POSITIVE_CSV, client_ref="restart-1")
        restarted = create_app({"db_path": self.db_path}).test_client()
        replay = restarted.post(
            "/api/imports?format=csv&mode=atomic&client_ref=restart-1",
            data=POSITIVE_CSV.encode("utf-8"),
            content_type="text/csv",
        )
        self.assertEqual(replay.status_code, 200)
        self.assertTrue(replay.get_json()["deduplicated"])

    def test_recurring_without_period_is_row_rejected(self):
        csv_text = (
            "title,data_origin,procurement_recurring_cost,procurement_period\n"
            "示例-周期缺失,synthetic,12.00,\n"
        )
        before = self.counts(*BUSINESS)
        resp = self.post_csv(csv_text)
        self.assertEqual(resp.status_code, 422)
        self.assertEqual(self.counts(*BUSINESS), before)  # nothing stored, no NULL period row
        reasons = [r["reason_code"] for r in self.query("SELECT reason_code FROM import_row_result")]
        self.assertIn("V16", reasons)

    def test_four_candidate_groups_stay_pending(self):
        csv_text = (
            "title,data_origin,demand_url,demand_excerpt\n"
            "示例-组1,synthetic,https://example.com/demand/g1,求模板一\n"
            "示例-组2,synthetic,https://example.com/demand/g2,求模板二\n"
            "示例-组3,synthetic,https://example.com/demand/g3,求模板三\n"
            "示例-组4,synthetic,https://example.com/demand/g4,求模板四\n"
        )
        resp = self.post_csv(csv_text)
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.get_json()["counts"]["created"], 4)
        for item in self.client.get("/api/candidates").get_json()["items"]:
            detail = self.client.get(f"/api/candidates/{item['id']}").get_json()
            self.assertEqual(detail["derived_status"], "pending")
            self.assertEqual(set(detail["gates"].values()), {"unverified"})
            self.assertTrue(detail["derived_status_reason"].startswith("derived:pending"))

    def test_not_found_contract(self):
        self.assertEqual(self.client.get("/api/candidates/c_missing").status_code, 404)
        self.assertEqual(self.client.get("/api/imports/ib_missing").status_code, 404)
        self.assertEqual(self.client.get("/api/candidates/c_missing").get_json()["error"]["code"], "not_found")


class HistoryHashRevisitTest(unittest.TestCase):
    """A→B→A（旧版本重见）：完整强键历史命中，不得 500、不得新增版本或证据。"""

    def setUp(self):
        TMP_ROOT.mkdir(parents=True, exist_ok=True)
        self.tmp = tempfile.mkdtemp(prefix="api_", dir=str(TMP_ROOT))
        self.db_path = str(pathlib.Path(self.tmp) / "app.db")
        self.app = create_app({"db_path": self.db_path})
        self.client = self.app.test_client()

    # ---------------- helpers
    def post_csv(self, text: str, mode: str = "atomic", client_ref: str | None = None):
        url = f"/api/imports?format=csv&mode={mode}"
        if client_ref:
            url += f"&client_ref={client_ref}"
        return self.client.post(url, data=text.encode("utf-8"), content_type="text/csv")

    def post_json(self, payload, mode: str = "atomic", client_ref: str | None = None):
        url = f"/api/imports?format=json&mode={mode}"
        if client_ref:
            url += f"&client_ref={client_ref}"
        return self.client.post(url, data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                                content_type="application/json")

    def counts(self, *tables: str) -> dict:
        conn = connect(self.db_path)
        try:
            return {t: conn.execute(f"SELECT COUNT(*) AS n FROM {t}").fetchone()["n"] for t in tables}
        finally:
            conn.close()

    def query(self, sql: str, params=()):
        conn = connect(self.db_path)
        try:
            return [dict(r) for r in conn.execute(sql, params).fetchall()]
        finally:
            conn.close()

    def execute(self, sql: str, params=()):
        conn = connect(self.db_path)
        try:
            conn.execute(sql, params)
        finally:
            conn.close()

    @staticmethod
    def _variants() -> tuple[str, str, str]:
        """同一身份（demand_url 不变）下三份不同摘录：A / B / C。"""
        a = POSITIVE_CSV
        b = a.replace("求一份能直接套用的周会纪要模板", "求一份能直接套用的周会纪要模板，最好带示例")
        c = a.replace("求一份能直接套用的周会纪要模板", "求一份能直接套用的周会纪要模板，含季报场景")
        return a, b, c

    @staticmethod
    def _native_row(source: str, native_id: str, excerpt: str, origin: str = "synthetic") -> list[dict]:
        # `real` 行不得用示例域（§0.5），故按 origin 选择 URL 域。
        url = (f"https://www.goofish.com/item/{native_id}" if origin == "real"
               else f"https://example.com/demand/{source}-{native_id}")
        return [{
            "title": f"示例-{source}-{native_id}",
            "data_origin": origin,
            "demand_source": source,
            "demand_native_id": native_id,
            "demand_url": url,
            "demand_excerpt": excerpt,
        }]

    # ---------------- tests
    def test_revisit_url_identity_is_duplicate_not_500(self):
        a, b, _ = self._variants()
        self.assertEqual(self.post_csv(a).status_code, 201)
        self.assertEqual(self.post_csv(b).status_code, 201)
        self.execute("UPDATE demand_signal SET last_seen_at=? WHERE version_no=1", ("2020-01-01T00:00:00Z",))

        third = self.post_csv(a)                       # 旧版本重见（修前：500 / IntegrityError）
        self.assertEqual(third.status_code, 201, third.get_data(as_text=True))
        self.assertEqual(third.get_json()["counts"]["duplicate_skipped"], 1)

        signals = self.query("SELECT id, version_no, superseded_by, last_seen_at FROM demand_signal"
                             " ORDER BY version_no")
        self.assertEqual([s["version_no"] for s in signals], [1, 2])
        self.assertEqual(signals[0]["superseded_by"], signals[1]["id"])   # 版本链不变（A→B）
        self.assertIsNone(signals[1]["superseded_by"])
        self.assertNotEqual(signals[0]["last_seen_at"], "2020-01-01T00:00:00Z")  # 仅刷新旧行
        self.assertEqual(self.counts("candidate")["candidate"], 1)
        self.assertEqual(self.counts("demand_signal")["demand_signal"], 2)
        self.assertEqual(self.counts("evidence")["evidence"], 3)   # 2 条需求派生证据 + 1 条 supply_distribution

    def test_revisit_native_id_json_isolated_by_source_and_origin(self):
        self.post_json(self._native_row("xianyu", "1001", "求模板 A"))
        self.post_json(self._native_row("xianyu", "1001", "求模板 B"))
        third = self.post_json(self._native_row("xianyu", "1001", "求模板 A"))
        self.assertEqual(third.status_code, 201, third.get_data(as_text=True))
        self.assertEqual(self.counts("demand_signal")["demand_signal"], 2)

        self.post_json(self._native_row("bilibili", "1001", "求模板 A"))          # 不同来源 → 独立候选
        self.post_json(self._native_row("xianyu", "1001", "求模板 A", origin="real"))  # 不同 origin → 独立
        keys = {row["identity_key"] for row in self.query("SELECT identity_key FROM candidate")}
        self.assertEqual(keys, {"n:xianyu:1001", "n:bilibili:1001"})
        self.assertEqual(self.counts("demand_signal")["demand_signal"], 4)

    def test_revisit_keeps_invalidated_evidence_invalid(self):
        a, b, _ = self._variants()
        self.post_csv(a)
        self.post_csv(b)
        first = self.query("SELECT id FROM demand_signal ORDER BY version_no LIMIT 1")[0]["id"]
        self.execute("UPDATE evidence SET invalidated_at=?, invalid_reason=? WHERE demand_signal_id=?",
                     ("2026-10-01T00:00:00Z", "示例：证据失效", first))
        before = self.counts("evidence", "gate_review")

        third = self.post_csv(a)
        self.assertEqual(third.status_code, 201, third.get_data(as_text=True))
        self.assertEqual(self.counts("evidence", "gate_review"), before)          # 不新建证据/门槛
        kept = self.query("SELECT invalidated_at, invalid_reason FROM evidence WHERE demand_signal_id=?", (first,))
        self.assertEqual(kept, [{"invalidated_at": "2026-10-01T00:00:00Z", "invalid_reason": "示例：证据失效"}])

    def test_revisit_then_new_content_appends_v3(self):
        a, b, c = self._variants()
        self.post_csv(a)
        self.post_csv(b)
        self.assertEqual(self.post_csv(a).status_code, 201)                       # 重见旧 A
        fourth = self.post_csv(c)                                                 # 全新技术内容
        self.assertEqual(fourth.get_json()["counts"]["version_added"], 1)
        signals = self.query("SELECT id, version_no, superseded_by FROM demand_signal ORDER BY version_no")
        self.assertEqual([s["version_no"] for s in signals], [1, 2, 3])
        self.assertEqual(signals[0]["superseded_by"], signals[1]["id"])            # A→B 不变
        self.assertEqual(signals[1]["superseded_by"], signals[2]["id"])            # B→C
        self.assertIsNone(signals[2]["superseded_by"])
        self.assertEqual(self.counts("candidate")["candidate"], 1)

    def test_revisit_keeps_supply_and_cost_judged_independently(self):
        a, b, _ = self._variants()
        self.post_csv(a)
        self.post_csv(b)
        before_signals = self.counts("demand_signal")["demand_signal"]
        changed = a.replace("9.90,500,0,0,0,0,0,0,monthly", "12.00,500,0,0,0,0,0,0,monthly")  # 仅成本变化
        third = self.post_csv(changed)                                            # 需求同旧 hash，成本仍独立判定
        self.assertEqual(third.status_code, 201, third.get_data(as_text=True))
        self.assertEqual(self.counts("demand_signal")["demand_signal"], before_signals)     # 需求侧未新增
        skipped_types = {(r["record_type"], r["action"]) for r in self.query(
            "SELECT record_type, action FROM import_row_result WHERE action='duplicate_skipped'")}
        self.assertIn(("demand_signal", "duplicate_skipped"), skipped_types)      # 需求侧记重复
        active_sale = self.query("SELECT money_minor FROM cost_item WHERE role='sale_price' AND is_active=1")
        self.assertEqual(active_sale, [{"money_minor": 1200}])                    # 成本变化被处理（V17）

    def test_revisit_keeps_idempotency_and_validate_modes(self):
        a, _, _ = self._variants()
        self.post_csv(a)
        before = self.counts("candidate", "demand_signal", "evidence", "cost_item", "supply_offer")
        replay = self.post_csv(a, client_ref="aba-ref")
        self.assertEqual(replay.status_code, 201)
        again = self.post_csv(a, client_ref="aba-ref")
        self.assertEqual(again.status_code, 200)
        self.assertTrue(again.get_json().get("deduplicated"))
        conflict = self.post_csv(a.replace("示例-周会纪要模板包", "示例-周会纪要模板包2"), client_ref="aba-ref")
        self.assertEqual(conflict.status_code, 409)
        validated = self.post_csv(a, mode="validate")
        self.assertEqual(validated.status_code, 200)
        self.assertFalse(validated.get_json()["saved"])
        after = self.counts("candidate", "demand_signal", "evidence", "cost_item", "supply_offer")
        self.assertEqual(after["demand_signal"], before["demand_signal"] + 0)
        self.assertGreaterEqual(after["candidate"], before["candidate"])


if __name__ == "__main__":
    unittest.main()
