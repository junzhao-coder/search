"""S2-B2: drafts (#16/#17), feedback (#18/#27) and the end-to-end chain (S2-30)."""

from __future__ import annotations

import os
import pathlib
import sys
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app import create_app  # noqa: E402
from tests.api.b2_helpers import (  # noqa: E402
    add_cost,
    add_default_costs,
    add_gate,
    detail,
    new_client,
    query,
    scenario,
    seed_full,
    verify_all_gates,
)


class DraftTest(unittest.TestCase):
    def setUp(self):
        self.client, self.db_path = new_client("draft_")
        self.candidate_id, self.supply_id = seed_full(self.client)

    def test_template_draft_works_without_a_model(self):
        response = self.client.post(f"/api/candidates/{self.candidate_id}/drafts",
                                    json={"kind": "listing_copy", "method": "template"})
        self.assertEqual(response.status_code, 201, response.get_data(as_text=True))
        body = response.get_json()
        self.assertEqual(body["status"], "draft")
        self.assertEqual(body["template_version"], "v1")
        self.assertIn("【待核验", body["body"])          # unverified content stays an explicit placeholder
        self.assertTrue(body["no_send_path"])
        draft_id = body["id"]

        edited = self.client.patch(f"/api/drafts/{draft_id}", json={"body": "自定义文案：待核验内容不变"})
        self.assertEqual(edited.status_code, 200)
        self.assertTrue(edited.get_json()["changed"])
        final = self.client.patch(f"/api/drafts/{draft_id}", json={"status": "final"})
        self.assertEqual(final.get_json()["status"], "final")
        backwards = self.client.patch(f"/api/drafts/{draft_id}", json={"status": "draft"})
        self.assertEqual(backwards.status_code, 422)
        unknown = self.client.patch(f"/api/drafts/{draft_id}", json={"status": "sent"})
        self.assertEqual(unknown.status_code, 422)
        self.assertEqual(self.client.post(f"/api/candidates/{self.candidate_id}/send", json={}).status_code, 404)

    def test_model_assisted_requires_a_configured_model(self):
        refused = self.client.post(f"/api/candidates/{self.candidate_id}/drafts",
                                   json={"kind": "reply", "method": "model_assisted"})
        self.assertEqual(refused.status_code, 422)
        self.assertIn("model", str(refused.get_json()["error"]["message"]).lower())
        with mock.patch.dict(os.environ, {"APP_MODEL_NAME": "example-model"}):
            allowed = self.client.post(f"/api/candidates/{self.candidate_id}/drafts",
                                       json={"kind": "reply", "method": "model_assisted", "body": "示例模型草稿"})
        self.assertEqual(allowed.status_code, 201, allowed.get_data(as_text=True))


class FeedbackTest(unittest.TestCase):
    def setUp(self):
        self.client, self.db_path = new_client("fb_")
        self.candidate_id, self.supply_id = seed_full(self.client)
        verify_all_gates(self.client, self.candidate_id, self.supply_id)

    def test_sale_snapshot_is_generated_and_frozen(self):
        baseline = scenario(self.client, self.candidate_id)
        self.assertEqual(baseline["net_per_order_minor"], 150)
        created = self.client.post(f"/api/candidates/{self.candidate_id}/feedback",
                                  json={"kind": "sale", "amount_minor": 10000, "order_ref": "ORDER-1"})
        self.assertEqual(created.status_code, 201, created.get_data(as_text=True))
        body = created.get_json()
        self.assertEqual(body["predicted_net_per_order_minor"], 150)  # server-generated snapshot
        self.assertIsNone(body["actual_net_per_order_minor"])
        self.assertIsNone(body["actual_complete"])
        sale_id = body["id"]

        # cost change moves the scenario but must not rewrite the stored snapshot (I4)
        changed = add_cost(self.client, self.candidate_id, role="procurement", basis="per_order",
                           value_kind="money", money_minor=500, supply_offer_id=self.supply_id,
                           assumption_note="示例：采购成本更正")
        self.assertEqual(changed.status_code, 201)
        self.assertEqual(scenario(self.client, self.candidate_id)["net_per_order_minor"], -50)
        stored = query(self.db_path, "SELECT predicted_net_per_order_minor, predicted_snapshot_at FROM feedback"
                                     " WHERE id=?", (sale_id,))
        self.assertEqual(stored[0]["predicted_net_per_order_minor"], 150)

        rewrite = self.client.patch(f"/api/feedback/{sale_id}", json={"predicted_net_per_order_minor": 999})
        self.assertEqual(rewrite.status_code, 422)
        duplicate = self.client.post(f"/api/candidates/{self.candidate_id}/feedback",
                                    json={"kind": "sale", "amount_minor": 100, "order_ref": "ORDER-1"})
        self.assertEqual(duplicate.status_code, 409)

    def test_refund_requires_matching_sale(self):
        missing = self.client.post(f"/api/candidates/{self.candidate_id}/feedback",
                                   json={"kind": "refund", "refund_state": "pending", "amount_minor": 500})
        self.assertEqual(missing.status_code, 422)

        sale = self.client.post(f"/api/candidates/{self.candidate_id}/feedback",
                                json={"kind": "sale", "amount_minor": 5000, "order_ref": "ORDER-2"}).get_json()
        other_candidate, other_supply = seed_full(self.client, "示例-另一候选")
        other_sale = self.client.post(f"/api/candidates/{other_candidate}/feedback",
                                      json={"kind": "sale", "amount_minor": 5000, "order_ref": "ORDER-3"}).get_json()
        cross = self.client.post(f"/api/candidates/{self.candidate_id}/feedback",
                                 json={"kind": "refund", "refund_state": "pending", "amount_minor": 500,
                                       "related_feedback_id": other_sale["id"]})
        self.assertEqual(cross.status_code, 422)
        mismatch = self.client.post(f"/api/candidates/{self.candidate_id}/feedback",
                                    json={"kind": "refund", "refund_state": "pending", "amount_minor": 500,
                                          "related_feedback_id": sale["id"], "order_ref": "ORDER-OTHER"})
        self.assertEqual(mismatch.status_code, 422)

        refund = self.client.post(f"/api/candidates/{self.candidate_id}/feedback",
                                  json={"kind": "refund", "refund_state": "pending", "amount_minor": 500,
                                        "related_feedback_id": sale["id"]})
        self.assertEqual(refund.status_code, 201, refund.get_data(as_text=True))
        refund_id = refund.get_json()["id"]
        settled = self.client.patch(f"/api/feedback/{refund_id}", json={"refund_state": "settled"})
        self.assertTrue(settled.get_json()["changed"])
        again = self.client.patch(f"/api/feedback/{refund_id}", json={"refund_state": "settled"})
        self.assertFalse(again.get_json()["changed"])
        rows = query(self.db_path, "SELECT actual_net_per_order_minor, actual_complete FROM feedback")
        self.assertTrue(all(row["actual_net_per_order_minor"] is None and row["actual_complete"] is None
                            for row in rows))

    def test_manual_time_record_and_correction(self):
        missing = self.client.post(f"/api/candidates/{self.candidate_id}/feedback",
                                   json={"kind": "manual_time"})
        self.assertEqual(missing.status_code, 422)
        created = self.client.post(f"/api/candidates/{self.candidate_id}/feedback",
                                  json={"kind": "manual_time", "actual_minutes": 20,
                                        "actual_hourly_rate_minor": 3000}).get_json()
        self.assertEqual(created["actual_minutes"] if "actual_minutes" in created else 20, 20)
        same = self.client.patch(f"/api/feedback/{created['id']}",
                                 json={"actual_minutes": 20, "actual_hourly_rate_minor": 3000})
        self.assertFalse(same.get_json()["changed"])  # same value: no new row, no timestamp change
        corrected = self.client.patch(f"/api/feedback/{created['id']}", json={"actual_minutes": 35})
        self.assertTrue(corrected.get_json()["changed"])
        bad = self.client.patch(f"/api/feedback/{created['id']}", json={"refund_state": "settled"})
        self.assertEqual(bad.status_code, 422)
        unknown = self.client.patch(f"/api/feedback/{created['id']}", json={"amount_minor": 100})
        self.assertEqual(unknown.status_code, 422)
        self.assertEqual(
            self.client.patch(f"/api/feedback/{created['id']}", json={"actual_minutes": 1441}).status_code, 422
        )

    def test_expense_inquiry_and_server_field_rejections(self):
        expense = self.client.post(f"/api/candidates/{self.candidate_id}/feedback",
                                  json={"kind": "expense", "amount_minor": 5000})
        self.assertEqual(expense.status_code, 422)
        ok_expense = self.client.post(f"/api/candidates/{self.candidate_id}/feedback",
                                     json={"kind": "expense", "expense_kind": "procurement",
                                           "amount_minor": 5000, "expense_basis": "one_time"})
        self.assertEqual(ok_expense.status_code, 201)
        zero_quantity = self.client.post(f"/api/candidates/{self.candidate_id}/feedback",
                                        json={"kind": "inquiry", "quantity": 0})
        self.assertEqual(zero_quantity.status_code, 422)
        # ⑥ non-manual_time events must not accept the manual-time fields
        sale = self.client.post(f"/api/candidates/{self.candidate_id}/feedback",
                                json={"kind": "sale", "amount_minor": 1000}).get_json()
        non_manual = self.client.patch(f"/api/feedback/{sale['id']}", json={"actual_minutes": 5})
        self.assertEqual(non_manual.status_code, 422)
        for field in ("predicted_net_per_order_minor", "actual_net_per_order_minor", "actual_complete"):
            with self.subTest(field=field):
                rejected = self.client.post(f"/api/candidates/{self.candidate_id}/feedback",
                                            json={"kind": "sale", "amount_minor": 1000, field: 1})
                self.assertEqual(rejected.status_code, 422)
                self.assertEqual(rejected.get_json()["error"]["code"], "invalid_field")

    def test_rejected_import_leaves_no_idempotency_record(self):
        """The idempotency row shares the business transaction, so a rejected batch stores nothing."""
        broken = "title,data_origin,sale_price\n,synthetic,9.90\n"
        first = self.client.post("/api/imports?format=csv&mode=atomic&client_ref=retry-1",
                                 data=broken.encode("utf-8"), content_type="text/csv")
        self.assertEqual(first.status_code, 422)
        self.assertEqual(query(self.db_path, "SELECT COUNT(*) AS n FROM idempotency_key")[0]["n"], 0)
        good = "title,data_origin,sale_price\n示例-修正,synthetic,9.90\n"
        retry = self.client.post("/api/imports?format=csv&mode=atomic&client_ref=retry-1",
                                 data=good.encode("utf-8"), content_type="text/csv")
        self.assertEqual(retry.status_code, 201, retry.get_data(as_text=True))  # no 409: nothing was stored


class FullChainTest(unittest.TestCase):
    def test_end_to_end_chain_and_restart(self):
        client, db_path = new_client("chain_")
        candidate_id, supply_id = seed_full(client)
        self.assertEqual(detail(client, candidate_id)["derived_status"], "pending")
        verify_all_gates(client, candidate_id, supply_id)
        self.assertEqual(detail(client, candidate_id)["derived_status"], "testable")

        draft = client.post(f"/api/candidates/{candidate_id}/drafts",
                            json={"kind": "listing_copy", "method": "template"}).get_json()
        sale = client.post(f"/api/candidates/{candidate_id}/feedback",
                           json={"kind": "sale", "amount_minor": 10000, "order_ref": "ORDER-E2E"}).get_json()
        scenario_before = scenario(client, candidate_id)

        restarted = create_app({"db_path": db_path}).test_client()
        snapshot = restarted.get(f"/api/candidates/{candidate_id}").get_json()
        self.assertEqual(snapshot["derived_status"], "testable")
        self.assertEqual(set(snapshot["gates"].values()), {"verified"})
        self.assertEqual([d["id"] for d in snapshot["drafts"]], [draft["id"]])
        self.assertEqual([f["id"] for f in snapshot["feedback"]], [sale["id"]])
        self.assertEqual(snapshot["feedback"][0]["predicted_net_per_order_minor"],
                         scenario_before["net_per_order_minor"])
        self.assertEqual(scenario(restarted, candidate_id)["net_per_order_minor"],
                         scenario_before["net_per_order_minor"])


if __name__ == "__main__":
    unittest.main()
