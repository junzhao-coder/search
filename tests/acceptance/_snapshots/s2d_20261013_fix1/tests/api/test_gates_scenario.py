"""S2-B2: gate admission (§3.5), scenario (§5.5), downgrades (§3.4) and recompute (#21)."""

from __future__ import annotations

import datetime as _dt
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tests.api.b2_helpers import (
    DEFAULT_COSTS,
    FULL_HEADER,
    add_cost,
    add_default_costs,
    add_gate,
    counts,
    detail,
    new_client,
    post_csv,
    query,
    scenario,
    seed_demand_only,
    seed_full,
    slug,
    verify_all_gates,
)

GATE_TABLES = ("gate_review", "review_item", "cost_item", "supply_offer")


def changed_price_csv(price: str = "5.00") -> str:
    """The full sample row re-imported with a different supply price (same demand identity)."""
    token = slug("示例-B2完整")
    return (
        f"{FULL_HEADER}\n"
        f"示例-B2完整,synthetic,xianyu,https://example.com/demand/{token},求同一类模板,specific_ask,"
        f"示例开放模板库,https://example.com/supply/{token},tpl-{token},open_repo,v1,{price},yes,yes,yes,"
        f"partial,抽检 2 个文件,https://example.com/supply/{token}/license,"
        f"本库素材可用于商业用途并允许转售（示例摘录）\n"
    )


def _plus_days(stamp: str, days: int) -> str:
    base = _dt.datetime.strptime(stamp, "%Y-%m-%dT%H:%M:%SZ")
    return (base + _dt.timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")


def _demand_evidence_id(client, candidate_id: str) -> str:
    return next(e["id"] for e in detail(client, candidate_id)["evidences"] if e["evidence_type"] == "demand")


def _clause_evidence_id(client, candidate_id: str) -> str:
    return next(s["license_evidence_id"] for s in detail(client, candidate_id)["supplies"])


class GateAdmissionTest(unittest.TestCase):
    def setUp(self):
        self.client, self.db_path = new_client("gate_")

    def test_demand_gate_requires_signal_derived_evidence(self):
        cid = seed_demand_only(self.client)
        missing = add_gate(self.client, cid, "demand", status="verified")
        self.assertEqual(missing.status_code, 422)
        self.assertIn("evidence_id", {d["field"] for d in missing.get_json()["error"]["details"]})
        evidence_id = _demand_evidence_id(self.client, cid)
        ok = add_gate(self.client, cid, "demand", status="verified", evidence_id=evidence_id)
        self.assertEqual(ok.status_code, 200, ok.get_data(as_text=True))
        body = ok.get_json()
        self.assertEqual((body["seq"], body["verified_by"], body["candidate_status"]), (1, "user", "pending"))
        self.assertEqual(body["expires_at"], _plus_days(body["verified_at"], 90))  # demand TTL

    def test_seller_promo_cannot_pass_demand_gate(self):
        cid = seed_demand_only(self.client, "示例-卖家宣传", kind="seller_promo")
        evidence_id = _demand_evidence_id(self.client, cid)
        refused = add_gate(self.client, cid, "demand", status="verified", evidence_id=evidence_id)
        self.assertEqual(refused.status_code, 422)
        reasons = " ".join(d["reason"] for d in refused.get_json()["error"]["details"])
        self.assertIn("卖家宣传", reasons)

    def test_supply_gate_rejects_licence_and_sample_gaps(self):
        cases = [
            ({"resale": "no"}, "resale_allowed", True),
            ({"commercial": "no"}, "commercial_allowed", True),
            ({"sample_checked": "none", "sample_note": ""}, "sample_checked", False),
        ]
        for overrides, expected_field, expects_exception_hint in cases:
            with self.subTest(field=expected_field):
                cid, supply_id = seed_full(self.client, f"示例-许可{expected_field}", **overrides)
                response = add_gate(self.client, cid, "supply_distribution", status="verified",
                                    supply_offer_id=supply_id)
                self.assertEqual(response.status_code, 422)
                details = response.get_json()["error"]["details"]
                self.assertIn(expected_field, {d["field"] for d in details})
                if expects_exception_hint:
                    # no/unknown licence values point at the §3.5 G2 exception path (scope note + clause excerpt)
                    self.assertIn("license_scope_note", " ".join(d["reason"] for d in details))

    def test_cost_gate_rejects_unknown_roles_and_ungrounded_rows(self):
        cid, supply_id = seed_full(self.client)
        bare = add_gate(self.client, cid, "cost", status="verified", supply_offer_id=supply_id)
        self.assertEqual(bare.status_code, 422)
        fields = {d["field"] for d in bare.get_json()["error"]["details"]}
        self.assertTrue({"sale_price", "payment_fee", "manual_labor"} <= fields)
        add_default_costs(self.client, cid, supply_id)
        add_gate(self.client, cid, "supply_distribution", status="verified", supply_offer_id=supply_id)
        ok = add_gate(self.client, cid, "cost", status="verified", supply_offer_id=supply_id)
        self.assertEqual(ok.status_code, 200, ok.get_data(as_text=True))

    def test_cost_gate_requires_grounding_for_imported_rows(self):
        cid, supply_id = seed_full(self.client)
        # imported rows default to assumption without a note -> not grounded
        add_cost(self.client, cid, role="sale_price", basis="per_order", value_kind="money", money_minor=1000,
                 supply_offer_id=supply_id)
        add_gate(self.client, cid, "supply_distribution", status="verified", supply_offer_id=supply_id)
        response = add_gate(self.client, cid, "cost", status="verified", supply_offer_id=supply_id)
        details = response.get_json()["error"]["details"]
        self.assertIn("assumption_note", " ".join(d["reason"] for d in details))

    def test_platform_gate_version_must_match_selected_supply(self):
        cid, supply_id = seed_full(self.client)
        add_gate(self.client, cid, "supply_distribution", status="verified", supply_offer_id=supply_id)
        evidence = self.client.post(
            f"/api/candidates/{cid}/evidences",
            json={"evidence_type": "platform_policy", "source_url": "https://example.com/policy",
                  "excerpt": "示例平台规则摘录", "fact_kind": "fact"},
        ).get_json()
        bad = add_gate(self.client, cid, "platform_policy", status="verified", evidence_id=evidence["id"],
                       applies_to_platform="xianyu", applies_to_version="v2")
        self.assertEqual(bad.status_code, 422)
        self.assertIn("applies_to_version", {d["field"] for d in bad.get_json()["error"]["details"]})
        other_platform = add_gate(self.client, cid, "platform_policy", status="verified", evidence_id=evidence["id"],
                                  applies_to_platform="other-platform", applies_to_version="v1")
        self.assertEqual(other_platform.status_code, 422)
        self.assertIn("applies_to_platform", {d["field"] for d in other_platform.get_json()["error"]["details"]})
        good = add_gate(self.client, cid, "platform_policy", status="verified", evidence_id=evidence["id"],
                        applies_to_platform="xianyu", applies_to_version="v1")
        self.assertEqual(good.status_code, 200)

    def test_four_gates_make_candidate_testable_with_ttls(self):
        cid, supply_id = seed_full(self.client)
        responses = verify_all_gates(self.client, cid, supply_id)
        for gate, response in responses.items():
            self.assertEqual(response.status_code, 200, f"{gate}: {response.get_data(as_text=True)}")
        self.assertEqual(responses["platform_policy"].get_json()["candidate_status"], "testable")
        ttl = {"demand": 90, "supply_distribution": 30, "cost": 30, "platform_policy": 180}
        for gate, days in ttl.items():
            body = responses[gate].get_json()
            self.assertEqual(body["expires_at"], _plus_days(body["verified_at"], days), gate)
        snapshot = detail(self.client, cid)
        self.assertEqual(snapshot["derived_status"], "testable")
        self.assertEqual(set(snapshot["gates"].values()), {"verified"})

    def test_gate_write_idempotency_and_override(self):
        cid = seed_demand_only(self.client)
        evidence_id = _demand_evidence_id(self.client, cid)
        url = f"/api/candidates/{cid}/gates/demand?client_ref=gate-1"
        payload = {"status": "verified", "evidence_id": evidence_id}
        first = self.client.post(url, json=payload)
        self.assertEqual(first.status_code, 200)
        replay = self.client.post(url, json=payload)
        self.assertEqual(replay.status_code, 200)
        self.assertTrue(replay.get_json()["deduplicated"])
        self.assertEqual(counts(self.db_path, "gate_review")["gate_review"], 1)
        conflict = self.client.post(url, json={"status": "failed"})
        self.assertEqual(conflict.status_code, 409)

        without_reason = self.client.post(f"/api/candidates/{cid}/override", json={"manual_override": "explore"})
        self.assertEqual(without_reason.status_code, 422)
        overridden = self.client.post(f"/api/candidates/{cid}/override",
                                      json={"manual_override": "explore", "override_reason": "弱证据但潜力高"})
        self.assertEqual(overridden.get_json()["candidate_status"], "explore")
        archived = self.client.post(f"/api/candidates/{cid}/override",
                                    json={"manual_override": "archived", "override_reason": "重复线索"})
        self.assertEqual(archived.get_json()["candidate_status"], "archived")


class ScenarioTest(unittest.TestCase):
    def setUp(self):
        self.client, self.db_path = new_client("scn_")

    def test_example_a_all_known(self):
        cid, supply_id = seed_full(self.client)
        add_default_costs(self.client, cid, supply_id)
        body = scenario(self.client, cid)
        self.assertEqual(body["sale_price_minor"], 1000)
        self.assertEqual(body["known_subtotal_minor"], 850)
        self.assertEqual(body["per_order"]["platform_fee_minor"], 50)   # 500bp × 1000
        self.assertEqual(body["per_order"]["manual_labor_minor"], 500)  # 10 min × 3000/h
        self.assertEqual(body["contribution_per_order_minor"], 150)
        self.assertTrue(body["complete"])
        self.assertEqual(body["net_per_order_minor"], 150)
        self.assertIsNone(body["amortize_orders"])
        self.assertEqual(body["unknown_components"], [])

    def test_buyout_nulls_net_and_reports_gap(self):
        cid, supply_id = seed_full(self.client)
        add_default_costs(self.client, cid, supply_id)
        superseded = add_cost(self.client, cid, role="procurement", basis="one_time", value_kind="money",
                              money_minor=10000, supply_offer_id=supply_id,
                              assumption_note="示例：一次性买断 100 元")
        self.assertEqual(superseded.status_code, 201, superseded.get_data(as_text=True))
        body = scenario(self.client, cid)
        self.assertEqual(body["one_time_total_minor"], 10000)
        self.assertEqual(body["fixed_cost_gap_minor"], 10000)
        self.assertFalse(body["complete"])
        self.assertIsNone(body["net_per_order_minor"])
        self.assertEqual(body["contribution_per_order_minor"], 150)  # per-order part unchanged
        self.assertIn("缺口单列", " ".join(body["explanation"]))

    def test_unknown_components_never_inferred_as_zero(self):
        cid = seed_demand_only(self.client)
        add_cost(self.client, cid, role="sale_price", basis="per_order", value_kind="money", money_minor=1000,
                 assumption_note="示例售价")
        add_cost(self.client, cid, role="procurement", basis="per_order", value_kind="money", money_minor=0,
                 assumption_note="示例：现成免费货源，逐单 0")
        body = scenario(self.client, cid)
        self.assertIsNone(body["contribution_per_order_minor"])
        self.assertIsNone(body["net_per_order_minor"])
        self.assertFalse(body["complete"])
        for expected in ("payment_fee", "acquisition", "manual_labor", "procurement.one_time", "procurement.recurring",
                         "other"):
            self.assertIn(expected, body["unknown_components"])
        self.assertEqual(body["known_subtotal_minor"], 0)  # known zero still counts as known

    def test_sale_price_never_joins_cost_sum(self):
        cid, supply_id = seed_full(self.client)
        add_default_costs(self.client, cid, supply_id)
        body = scenario(self.client, cid)
        self.assertEqual(body["known_subtotal_minor"], 850)  # sale price 1000 excluded
        self.assertIn("不参与成本求和", " ".join(body["explanation"]))


class DowngradeTest(unittest.TestCase):
    def setUp(self):
        self.client, self.db_path = new_client("dwn_")

    def _testable(self) -> tuple[str, str]:
        cid, supply_id = seed_full(self.client)
        verify_all_gates(self.client, cid, supply_id)
        self.assertEqual(detail(self.client, cid)["derived_status"], "testable")
        return cid, supply_id

    def test_same_second_supersede_downgrades_cost_gate(self):
        cid, supply_id = self._testable()
        platform_cost = next(row for row in detail(self.client, cid)["cost_items"]
                             if row["role"] == "platform_fee" and row["is_active"])
        response = self.client.post(f"/api/cost-items/{platform_cost['id']}/supersede",
                                    json={"value_kind": "rate", "rate_bp": 600,
                                          "assumption_note": "更正平台费率"})
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        self.assertTrue(response.get_json()["gate_downgraded"])
        snapshot = detail(self.client, cid)
        self.assertEqual(snapshot["gates"]["cost"], "expired")
        self.assertEqual(snapshot["derived_status"], "stale")
        reviews = [r for r in snapshot["review_items"] if r["kind"] == "cost_changed"]
        self.assertTrue(reviews and reviews[0]["ref_gate"] == "cost")
        # other cost rows stay active and do not prevent the downgrade
        active = [row for row in snapshot["cost_items"] if row["is_active"]]
        self.assertEqual(len(active), 10)
        # dismissing the review does not restore the verified row
        resolve = self.client.post(f"/api/reviews/{reviews[0]['id']}/resolve", json={"status": "dismissed"})
        if resolve.status_code == 404:  # route name guard
            resolve = self.client.post(f"/api/review-items/{reviews[0]['id']}/resolve", json={"status": "dismissed"})
        self.assertEqual(resolve.status_code, 200, resolve.get_data(as_text=True))
        after = detail(self.client, cid)
        self.assertEqual(after["gates"]["cost"], "expired")
        self.assertEqual(after["derived_status"], "stale")
        # only a fresh verified verification restores testable
        again = add_gate(self.client, cid, "cost", status="verified", supply_offer_id=supply_id)
        self.assertEqual(again.status_code, 200, again.get_data(as_text=True))
        self.assertEqual(again.get_json()["candidate_status"], "testable")

    def test_import_price_change_downgrades_without_new_cost_row(self):
        cid, supply_id = self._testable()
        before = counts(self.db_path, "cost_item", "gate_review")
        changed = post_csv(self.client, changed_price_csv())
        self.assertEqual(changed.status_code, 201, changed.get_data(as_text=True))
        after = counts(self.db_path, "cost_item", "gate_review")
        self.assertEqual(after["cost_item"], before["cost_item"])  # no new cost row
        self.assertGreater(after["gate_review"], before["gate_review"])  # downgrade row appended
        snapshot = detail(self.client, cid)
        self.assertEqual(snapshot["gates"]["cost"], "expired")
        self.assertEqual(snapshot["derived_status"], "stale")

    def test_validate_mode_never_materializes_downgrade(self):
        cid, supply_id = self._testable()
        before = counts(self.db_path, *GATE_TABLES, "import_batch")
        response = post_csv(self.client, changed_price_csv(), mode="validate")
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.get_json()["saved"])
        self.assertEqual(counts(self.db_path, *GATE_TABLES, "import_batch"), before)
        self.assertEqual(detail(self.client, cid)["gates"]["cost"], "verified")

    def test_atomic_rollback_undoes_downgrade(self):
        cid, supply_id = self._testable()
        before = counts(self.db_path, *GATE_TABLES)
        batches_before = counts(self.db_path, "import_batch")["import_batch"]
        broken = changed_price_csv() + "示例-坏行,synthetic\n"  # second row fails validation
        response = post_csv(self.client, broken, mode="atomic")
        self.assertEqual(response.status_code, 422)
        self.assertEqual(counts(self.db_path, *GATE_TABLES), before)  # no downgrade, no price change
        self.assertEqual(counts(self.db_path, "import_batch")["import_batch"], batches_before + 1)
        rejected = query(self.db_path, "SELECT status FROM import_batch ORDER BY rowid DESC LIMIT 1")
        self.assertEqual(rejected[0]["status"], "rejected")  # batch + row reasons are kept by design
        snapshot = detail(self.client, cid)
        self.assertEqual(snapshot["gates"]["cost"], "verified")
        self.assertEqual(snapshot["derived_status"], "testable")
        supplies = query(self.db_path, "SELECT unit_price_minor FROM supply_offer")
        self.assertEqual(supplies[0]["unit_price_minor"], 0)

    def test_supply_ttl_and_recompute_are_idempotent(self):
        cid, supply_id = self._testable()
        stale_stamp = (_dt.datetime.utcnow() - _dt.timedelta(days=40)).strftime("%Y-%m-%dT%H:%M:%SZ")
        patch = self.client.patch(f"/api/supplies/{supply_id}", json={"last_checked_at": stale_stamp})
        self.assertEqual(patch.status_code, 200, patch.get_data(as_text=True))
        before = counts(self.db_path, *GATE_TABLES)
        snapshot = detail(self.client, cid)  # read-only: no materialization
        self.assertEqual(snapshot["gates"]["supply_distribution"], "expired")
        self.assertEqual(snapshot["derived_status"], "stale")
        self.assertEqual(counts(self.db_path, *GATE_TABLES), before)
        first = self.client.post("/api/runs/recompute", json={"candidate_id": cid})
        self.assertEqual(first.status_code, 200)
        self.assertGreaterEqual(first.get_json()["downgraded"], 1)
        materialized = counts(self.db_path, *GATE_TABLES)
        self.assertGreater(materialized["gate_review"], before["gate_review"])
        second = self.client.post("/api/runs/recompute", json={"candidate_id": cid})
        self.assertEqual(second.get_json()["downgraded"], 0)
        self.assertEqual(counts(self.db_path, *GATE_TABLES), materialized)
        reviews = [r for r in detail(self.client, cid)["review_items"] if r["kind"] == "supply_invalid"]
        self.assertTrue(reviews)

    def test_blocking_review_on_subrecord_makes_candidate_stale(self):
        cid, supply_id = self._testable()
        evidence_id = _clause_evidence_id(self.client, cid)
        response = self.client.post(f"/api/evidences/{evidence_id}/invalidate",
                                    json={"invalid_reason": "条款页已变更"})
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        snapshot = detail(self.client, cid)
        self.assertEqual(snapshot["gates"]["supply_distribution"], "expired")
        self.assertEqual(snapshot["derived_status"], "stale")
        review_ids = [r["id"] for r in snapshot["review_items"] if r["kind"] == "evidence_expired"]
        self.assertTrue(review_ids)
        resolve = self.client.post(f"/api/review-items/{review_ids[0]}/resolve",
                                   json={"status": "dismissed"})
        self.assertEqual(resolve.status_code, 200)
        still = detail(self.client, cid)
        self.assertEqual(still["gates"]["supply_distribution"], "expired")  # dismissal never restores verified
        self.assertEqual(still["derived_status"], "stale")

    def test_override_archived_from_stale(self):
        cid, supply_id = self._testable()
        response = self.client.post(f"/api/candidates/{cid}/override",
                                    json={"manual_override": "archived", "override_reason": "样例归档"})
        self.assertEqual(response.get_json()["candidate_status"], "archived")


class ContractRowsTest(unittest.TestCase):
    """Decisive checks for the contract's own sample rows (S2-03/16/18/19/20/22)."""

    def setUp(self):
        self.client, self.db_path = new_client("rows_")

    def test_example_scenario_190_and_g3_needs_grounding(self):
        from tests.api.test_import_api import POSITIVE_CSV

        payload = post_csv(self.client, POSITIVE_CSV).get_json()
        candidate_id = next(r["id"] for row in payload["rows"] for r in row["records"] if r["type"] == "candidate")
        body = scenario(self.client, candidate_id)
        self.assertEqual(body["sale_price_minor"], 990)
        self.assertEqual(body["known_subtotal_minor"], 800)   # 0+50+0+0+0+0+750
        self.assertEqual(body["contribution_per_order_minor"], 190)
        self.assertTrue(body["complete"])
        supplies = detail(self.client, candidate_id)["supplies"]
        self.assertEqual(len(supplies), 1)
        costs = [c for c in detail(self.client, candidate_id)["cost_items"] if c["is_active"]]
        self.assertEqual(len(costs), 10)
        self.assertTrue(all(c["supply_offer_id"] == supplies[0]["id"] for c in costs))
        refused = add_gate(self.client, candidate_id, "cost", status="verified",
                           supply_offer_id=supplies[0]["id"])
        self.assertEqual(refused.status_code, 422)  # imported rows are assumption without a note

    def test_expiry_by_evidence_expires_and_resequences(self):
        cid, supply_id = seed_full(self.client)
        add_gate(self.client, cid, "supply_distribution", status="verified", supply_offer_id=supply_id)
        soon = (_dt.datetime.utcnow() + _dt.timedelta(days=6)).strftime("%Y-%m-%dT%H:%M:%SZ")
        evidence = self.client.post(
            f"/api/candidates/{cid}/evidences",
            json={"evidence_type": "platform_policy", "source_url": "https://example.com/policy/soon",
                  "excerpt": "示例：即将到期的平台规则摘录", "fact_kind": "fact", "expires_at": soon},
        ).get_json()
        first = add_gate(self.client, cid, "platform_policy", status="verified",
                         evidence_id=evidence["id"], applies_to_platform="xianyu",
                         applies_to_version="v1")
        self.assertEqual(first.status_code, 200, first.get_data(as_text=True))
        body = first.get_json()
        self.assertEqual(body["expires_at"], soon)  # min(evidence.expires_at, TTL)
        # 过期判定：把核验行的 expires_at 推到过去（fixture），读取必须按 §3.3 报 expired 且零写入
        past = (_dt.datetime.utcnow() - _dt.timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
        _exec(self.db_path, "UPDATE gate_review SET expires_at=? WHERE id=?", (past, body["id"]))
        before = counts(self.db_path, "gate_review", "review_item")
        self.assertEqual(detail(self.client, cid)["gates"]["platform_policy"], "expired")
        detail(self.client, cid)  # a second read must not write
        self.assertEqual(counts(self.db_path, "gate_review", "review_item"), before)
        recompute = self.client.post("/api/runs/recompute", json={"candidate_id": cid}).get_json()
        self.assertGreaterEqual(recompute["downgraded"], 1)
        materialized = counts(self.db_path, "gate_review", "review_item")
        self.assertGreater(materialized["gate_review"], before["gate_review"])
        fresh_evidence = self.client.post(
            f"/api/candidates/{cid}/evidences",
            json={"evidence_type": "platform_policy", "source_url": "https://example.com/policy/new",
                  "excerpt": "示例：最新平台规则摘录", "fact_kind": "fact"},
        ).get_json()
        again = add_gate(self.client, cid, "platform_policy", status="verified",
                         evidence_id=fresh_evidence["id"], applies_to_platform="xianyu",
                         applies_to_version="v1")
        self.assertEqual(again.get_json()["seq"], body["seq"] + 2)  # 1 verified -> 2 materialized expire -> 3 recheck
        self.assertEqual(detail(self.client, cid)["gates"]["platform_policy"], "verified")

    def test_supply_ttl_degrades_supply_and_cost_gates(self):
        cid, supply_id = seed_full(self.client)
        verify_all_gates(self.client, cid, supply_id)
        stale = (_dt.datetime.utcnow() - _dt.timedelta(days=40)).strftime("%Y-%m-%dT%H:%M:%SZ")
        self.client.patch(f"/api/supplies/{supply_id}", json={"last_checked_at": stale})
        snapshot = detail(self.client, cid)
        self.assertEqual(snapshot["gates"]["supply_distribution"], "expired")
        self.assertEqual(snapshot["gates"]["cost"], "expired")  # cost row referenced the same supply
        self.assertEqual(snapshot["derived_status"], "stale")
        self.client.post("/api/runs/recompute", json={"candidate_id": cid})
        kinds = {r["kind"] for r in detail(self.client, cid)["review_items"] if r["status"] == "open"}
        self.assertIn("supply_invalid", kinds)

    def test_loss_snapshot_and_negative_derived_value(self):
        """S2-19②: sale 10.00 with 12.00 per-order cost -> contribution -200, snapshot saveable."""
        cid, supply_id = seed_full(self.client)
        add_default_costs(self.client, cid, supply_id, specs=(
            {"role": "sale_price", "basis": "per_order", "value_kind": "money", "money_minor": 1000},
            {"role": "procurement", "basis": "per_order", "value_kind": "money", "money_minor": 1200},
            {"role": "procurement", "basis": "one_time", "value_kind": "money", "money_minor": 0},
            {"role": "procurement", "basis": "recurring", "value_kind": "money", "money_minor": 0,
             "period": "monthly"},
            {"role": "platform_fee", "basis": "per_order", "value_kind": "rate", "rate_bp": 0},
            {"role": "payment_fee", "basis": "per_order", "value_kind": "rate", "rate_bp": 0},
            {"role": "acquisition", "basis": "per_order", "value_kind": "money", "money_minor": 0},
            {"role": "refund_reserve", "basis": "per_order", "value_kind": "rate", "rate_bp": 0},
            {"role": "other", "basis": "per_order", "value_kind": "money", "money_minor": 0},
            {"role": "manual_labor", "basis": "per_order", "value_kind": "minutes", "minutes": 0,
             "hourly_rate_minor": 3000},
        ))
        body = scenario(self.client, cid)
        self.assertEqual(body["contribution_per_order_minor"], -200)  # 1000 - 1200
        self.assertEqual(body["net_per_order_minor"], -200)
        sale = self.client.post(f"/api/candidates/{cid}/feedback",
                                json={"kind": "sale", "amount_minor": 10000})
        self.assertEqual(sale.get_json()["predicted_net_per_order_minor"], -200)
        stored = query(self.db_path, "SELECT predicted_net_per_order_minor FROM feedback WHERE id=?",
                       (sale.get_json()["id"],))
        self.assertEqual(stored[0]["predicted_net_per_order_minor"], -200)  # negative derived value is legal

    def test_contribution_800_case(self):
        cid, supply_id = seed_full(self.client)
        add_default_costs(self.client, cid, supply_id, specs=(
            {"role": "sale_price", "basis": "per_order", "value_kind": "money", "money_minor": 1000},
            {"role": "procurement", "basis": "per_order", "value_kind": "money", "money_minor": 200},
            {"role": "procurement", "basis": "one_time", "value_kind": "money", "money_minor": 0},
            {"role": "procurement", "basis": "recurring", "value_kind": "money", "money_minor": 0,
             "period": "monthly"},
            {"role": "platform_fee", "basis": "per_order", "value_kind": "rate", "rate_bp": 0},
            {"role": "payment_fee", "basis": "per_order", "value_kind": "rate", "rate_bp": 0},
            {"role": "acquisition", "basis": "per_order", "value_kind": "money", "money_minor": 0},
            {"role": "refund_reserve", "basis": "per_order", "value_kind": "rate", "rate_bp": 0},
            {"role": "other", "basis": "per_order", "value_kind": "money", "money_minor": 0},
            {"role": "manual_labor", "basis": "per_order", "value_kind": "minutes", "minutes": 0,
             "hourly_rate_minor": 3000},
        ))
        body = scenario(self.client, cid)
        self.assertEqual(body["contribution_per_order_minor"], 800)
        self.assertEqual(body["net_per_order_minor"], 800)
        self.assertTrue(body["complete"])

    def test_no_purchase_or_payment_endpoints(self):
        cid, supply_id = seed_full(self.client)
        for path in (f"/api/candidates/{cid}/purchase", f"/api/candidates/{cid}/pay",
                     f"/api/supplies/{supply_id}/buy"):
            with self.subTest(path=path):
                self.assertEqual(self.client.post(path, json={}).status_code, 404)


def _exec(db_path: str, sql: str, params=()) -> None:
    """Fixture-only direct write (used to age evidence/validity inside the isolated test DB)."""
    import sqlite3

    conn = sqlite3.connect(db_path)
    try:
        conn.execute(sql, params)
        conn.commit()
    finally:
        conn.close()


def _add_supply(client, candidate_id: str, *, version: str = "v2", token: str = "alt",
                provider: str = "示例备用货源"):
    """Second supply on the same candidate, for the §3.5 'follows the current G2' checks."""
    return client.post(
        f"/api/candidates/{candidate_id}/supplies",
        json={"provider_name": provider, "provider_url": f"https://example.com/supply/{token}",
              "origin_type": "open_repo", "format_version": version, "unit_price_minor": 0,
              "commercial_allowed": "yes", "redistribute_allowed": "yes", "resale_allowed": "yes",
              "sample_checked": "partial", "sample_note": "抽检 2 个文件"},
    )


def _cost_specs(period: str | None = None, amount: int | None = None) -> tuple[dict, ...]:
    """完整成本集：per_order 全部已知 + 一条指定周期的 recurring 行（amount=None 表示缺行）。"""
    specs = [
        {"role": "sale_price", "basis": "per_order", "value_kind": "money", "money_minor": 1000},
        {"role": "procurement", "basis": "per_order", "value_kind": "money", "money_minor": 300},
        {"role": "procurement", "basis": "one_time", "value_kind": "money", "money_minor": 0},
        {"role": "platform_fee", "basis": "per_order", "value_kind": "rate", "rate_bp": 500},
        {"role": "payment_fee", "basis": "per_order", "value_kind": "rate", "rate_bp": 0},
        {"role": "acquisition", "basis": "per_order", "value_kind": "money", "money_minor": 0},
        {"role": "refund_reserve", "basis": "per_order", "value_kind": "rate", "rate_bp": 0},
        {"role": "other", "basis": "per_order", "value_kind": "money", "money_minor": 0},
        {"role": "manual_labor", "basis": "per_order", "value_kind": "minutes", "minutes": 10,
         "hourly_rate_minor": 3000},
    ]
    if period is not None and amount is not None:
        specs.append({"role": "procurement", "basis": "recurring", "value_kind": "money",
                      "money_minor": amount, "period": period})
    return tuple(specs)


class PeriodCostBoundaryTest(unittest.TestCase):
    """A) §5.5-2/4: 非月度周期成本不得被判为 complete，也不得输出伪月额。"""

    def setUp(self):
        self.client, self.db_path = new_client("period_")

    def _scenario(self, period: str | None = None, amount: int | None = None):
        cid, supply_id = seed_full(self.client)
        add_default_costs(self.client, cid, supply_id, specs=_cost_specs(period, amount))
        return cid, scenario(self.client, cid)

    def test_quarterly_positive_keeps_contribution_but_not_complete(self):
        cid, body = self._scenario("quarterly", 10000)
        self.assertEqual(body["contribution_per_order_minor"], 150)   # 逐单部分仍可算
        self.assertFalse(body["complete"])
        self.assertIsNone(body["net_per_order_minor"])
        self.assertIsNone(body["recurring_monthly_total_minor"])      # 不输出伪月额
        self.assertEqual(body["fixed_cost_gap_minor"], 10000)         # 单一周期：缺口即原金额
        self.assertEqual(body["recurring_detail"],
                         [{"role": "procurement", "period": "quarterly", "money_minor": 10000}])
        self.assertIn("非月度周期", " ".join(body["explanation"]))
        sale = self.client.post(f"/api/candidates/{cid}/feedback",
                                json={"kind": "sale", "amount_minor": 10000})
        self.assertIsNone(sale.get_json()["predicted_net_per_order_minor"])  # 同一规则 → 不完整为 NULL

    def test_yearly_positive_is_not_complete(self):
        cid, body = self._scenario("yearly", 12000)
        self.assertFalse(body["complete"])
        self.assertIsNone(body["net_per_order_minor"])
        self.assertIsNone(body["recurring_monthly_total_minor"])
        self.assertEqual(body["recurring_detail"][0]["period"], "yearly")
        self.assertEqual(body["recurring_detail"][0]["money_minor"], 12000)

    def test_monthly_positive_sets_monthly_total_and_gap(self):
        cid, body = self._scenario("monthly", 100)
        self.assertFalse(body["complete"])
        self.assertIsNone(body["net_per_order_minor"])
        self.assertEqual(body["recurring_monthly_total_minor"], 100)
        self.assertEqual(body["fixed_cost_gap_minor"], 100)

    def test_non_monthly_explicit_zero_is_complete(self):
        cid, body = self._scenario("quarterly", 0)
        self.assertTrue(body["complete"])                             # 显式已知 0 → 可完整
        self.assertEqual(body["net_per_order_minor"], 150)
        self.assertIsNone(body["recurring_monthly_total_minor"])      # 非 monthly → 月额字段仍为 null
        self.assertIsNone(body["fixed_cost_gap_minor"])
        self.assertEqual([row["money_minor"] for row in body["recurring_detail"]], [0])

    def test_monthly_explicit_zero_is_complete_with_zero_total(self):
        cid, body = self._scenario("monthly", 0)
        self.assertTrue(body["complete"])
        self.assertEqual(body["recurring_monthly_total_minor"], 0)    # 已知 0 与未知必须区分
        self.assertIsNone(body["fixed_cost_gap_minor"])

    def test_missing_recurring_row_stays_unknown(self):
        cid, body = self._scenario()
        self.assertFalse(body["complete"])
        self.assertIn("procurement.recurring", body["unknown_components"])
        self.assertIsNone(body["recurring_monthly_total_minor"])


class GateEvidenceContextTest(unittest.TestCase):
    """B) G2 默认条款证据必须真实落库并参与 TTL min；失效证据不得产生有效 verified。"""

    def setUp(self):
        self.client, self.db_path = new_client("gctx_")

    def test_g2_default_clause_evidence_is_persisted_and_used_for_ttl(self):
        cid, supply_id = seed_full(self.client)
        clause_id = next(s["license_evidence_id"] for s in detail(self.client, cid)["supplies"])
        short = (_dt.datetime.utcnow() + _dt.timedelta(days=5)).strftime("%Y-%m-%dT%H:%M:%SZ")
        _exec(self.db_path, "UPDATE evidence SET expires_at=? WHERE id=?", (short, clause_id))

        response = add_gate(self.client, cid, "supply_distribution", status="verified",
                            supply_offer_id=supply_id)                 # 省略 evidence_id
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        body = response.get_json()
        self.assertEqual(body["evidence_id"], clause_id)               # 默认关联出现在响应
        self.assertEqual(body["expires_at"], short)                    # TTL = min(证据有效期, 30 天)
        stored = query(self.db_path, "SELECT evidence_id, expires_at FROM gate_review "
                                     "WHERE candidate_id=? AND gate='supply_distribution' ORDER BY seq DESC LIMIT 1",
                       (cid,))
        self.assertEqual(stored[0]["evidence_id"], clause_id)          # 且真实落库
        self.assertEqual(stored[0]["expires_at"], short)

        before = counts(self.db_path, "gate_review", "review_item")
        invalidated = self.client.post(f"/api/evidences/{clause_id}/invalidate",
                                       json={"invalid_reason": "条款页已变更"})
        self.assertEqual(invalidated.status_code, 200, invalidated.get_data(as_text=True))
        # 关联现在真实存在于核验行上，因此失效即触发 §3.4 同事务降级（无需等 recompute）
        materialized = counts(self.db_path, "gate_review", "review_item")
        self.assertGreater(materialized["gate_review"], before["gate_review"])
        self.assertEqual(query(self.db_path, "SELECT status FROM gate_review WHERE candidate_id=?"
                                            " AND gate='supply_distribution' ORDER BY seq DESC LIMIT 1",
                               (cid,))[0]["status"], "expired")
        before = counts(self.db_path, "gate_review", "review_item")
        self.assertEqual(detail(self.client, cid)["gates"]["supply_distribution"], "expired")
        detail(self.client, cid)                                       # 第二次读同样零写入
        self.assertEqual(counts(self.db_path, "gate_review", "review_item"), before)
        recompute = self.client.post("/api/runs/recompute", json={"candidate_id": cid}).get_json()
        self.assertEqual(recompute["downgraded"], 0)                   # 已物化：重复运行幂等
        self.assertEqual(counts(self.db_path, "gate_review", "review_item"), before)

    def test_explicit_evidence_path_is_the_control(self):
        cid, supply_id = seed_full(self.client)
        short = (_dt.datetime.utcnow() + _dt.timedelta(days=2)).strftime("%Y-%m-%dT%H:%M:%SZ")
        explicit = self.client.post(
            f"/api/candidates/{cid}/evidences",
            json={"evidence_type": "supply_distribution", "source_url": "https://example.com/supply/alt/license",
                  "excerpt": "本库素材可用于商业用途（示例摘录）", "fact_kind": "fact", "expires_at": short},
        ).get_json()
        response = add_gate(self.client, cid, "supply_distribution", status="verified",
                            supply_offer_id=supply_id, evidence_id=explicit["id"])
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        self.assertEqual(response.get_json()["evidence_id"], explicit["id"])
        self.assertEqual(response.get_json()["expires_at"], short)

    def test_invalidated_evidence_cannot_produce_verified(self):
        cid = seed_demand_only(self.client)
        evidence_id = _demand_evidence_id(self.client, cid)
        self.client.post(f"/api/evidences/{evidence_id}/invalidate", json={"invalid_reason": "来源已删除"})
        before = counts(self.db_path, "gate_review", "review_item")
        refused = add_gate(self.client, cid, "demand", status="verified", evidence_id=evidence_id)
        self.assertEqual(refused.status_code, 422)
        self.assertIn("失效", " ".join(d["reason"] for d in refused.get_json()["error"]["details"]))
        self.assertEqual(counts(self.db_path, "gate_review", "review_item"), before)  # 失败写不落半行

    def test_expired_evidence_cannot_produce_verified(self):
        cid, supply_id = seed_full(self.client)
        past = (_dt.datetime.utcnow() - _dt.timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
        evidence = self.client.post(
            f"/api/candidates/{cid}/evidences",
            json={"evidence_type": "platform_policy", "source_url": "https://example.com/policy/old",
                  "excerpt": "示例：已过期的平台规则", "fact_kind": "fact", "expires_at": past},
        ).get_json()
        add_gate(self.client, cid, "supply_distribution", status="verified", supply_offer_id=supply_id)
        refused = add_gate(self.client, cid, "platform_policy", status="verified", evidence_id=evidence["id"],
                           applies_to_platform="xianyu", applies_to_version="v1")
        self.assertEqual(refused.status_code, 422)
        self.assertIn("过期", " ".join(d["reason"] for d in refused.get_json()["error"]["details"]))

    def test_failed_gate_write_leaves_no_partial_row(self):
        cid, supply_id = seed_full(self.client)
        before = counts(self.db_path, "gate_review", "review_item", "candidate")
        status_before = query(self.db_path, "SELECT status, status_reason FROM candidate WHERE id=?", (cid,))
        refused = add_gate(self.client, cid, "cost", status="verified", supply_offer_id=supply_id)
        self.assertEqual(refused.status_code, 422)
        self.assertEqual(counts(self.db_path, "gate_review", "review_item", "candidate"), before)
        self.assertEqual(query(self.db_path, "SELECT status, status_reason FROM candidate WHERE id=?", (cid,)),
                         status_before)


class GateSelectionBoundaryTest(unittest.TestCase):
    """C) G3/G4 遵从当前 G2 选择；历史 verified 不冒充当前选择；估算不升级门槛。"""

    def setUp(self):
        self.client, self.db_path = new_client("gsel_")

    def _two_supplies(self):
        cid, supply_a = seed_full(self.client)
        created = _add_supply(self.client, cid)
        self.assertEqual(created.status_code, 201, created.get_data(as_text=True))
        return cid, supply_a, created.get_json()["id"]

    def test_cost_gate_cannot_be_switched_to_another_supply(self):
        cid, supply_a, supply_b = self._two_supplies()
        add_default_costs(self.client, cid, supply_a)
        add_gate(self.client, cid, "supply_distribution", status="verified", supply_offer_id=supply_a)
        switched = add_gate(self.client, cid, "cost", status="verified", supply_offer_id=supply_b)
        self.assertEqual(switched.status_code, 422)
        details = switched.get_json()["error"]["details"]
        self.assertIn("supply_offer_id", {d["field"] for d in details})
        self.assertIn("不一致", " ".join(d["reason"] for d in details))
        self.assertEqual(counts(self.db_path, "gate_review")["gate_review"], 1)  # 未落半行
        ok = add_gate(self.client, cid, "cost", status="verified", supply_offer_id=supply_a)
        self.assertEqual(ok.status_code, 200, ok.get_data(as_text=True))

    def test_cross_candidate_supply_is_rejected(self):
        cid, supply_a, _ = self._two_supplies()
        other_cid, other_supply = seed_full(self.client, "示例-另一候选")
        add_default_costs(self.client, cid, supply_a)
        add_gate(self.client, cid, "supply_distribution", status="verified", supply_offer_id=supply_a)
        refused = add_gate(self.client, cid, "cost", status="verified", supply_offer_id=other_supply)
        self.assertEqual(refused.status_code, 422)
        self.assertIn("不属于本候选", " ".join(d["reason"] for d in refused.get_json()["error"]["details"]))

    def test_g3_requires_a_currently_verified_g2(self):
        cid, supply_id = seed_full(self.client)
        add_default_costs(self.client, cid, supply_id)
        refused = add_gate(self.client, cid, "cost", status="verified", supply_offer_id=supply_id)
        self.assertEqual(refused.status_code, 422)
        self.assertIn("G2", " ".join(d["reason"] for d in refused.get_json()["error"]["details"]))
        add_gate(self.client, cid, "supply_distribution", status="verified", supply_offer_id=supply_id)
        ok = add_gate(self.client, cid, "cost", status="verified", supply_offer_id=supply_id)
        self.assertEqual(ok.status_code, 200, ok.get_data(as_text=True))

    def test_expired_g2_history_is_not_the_current_selection(self):
        cid, supply_a, supply_b = self._two_supplies()
        add_default_costs(self.client, cid, supply_a)
        add_gate(self.client, cid, "supply_distribution", status="verified", supply_offer_id=supply_a)
        clause_id = query(self.db_path, "SELECT evidence_id FROM gate_review WHERE candidate_id=?"
                                         " AND gate='supply_distribution' ORDER BY seq DESC LIMIT 1", (cid,))[0]["evidence_id"]
        self.client.post(f"/api/evidences/{clause_id}/invalidate", json={"invalid_reason": "条款页已变更"})
        snapshot = detail(self.client, cid)
        self.assertEqual(snapshot["gates"]["supply_distribution"], "expired")
        refused = add_gate(self.client, cid, "cost", status="verified", supply_offer_id=supply_a)
        self.assertEqual(refused.status_code, 422)                     # 旧 verified 不再作为基准
        body = scenario(self.client, cid)
        self.assertIsNone(body["selected_supply_id"])                  # 两个有效货源：不猜选定
        self.assertIn("procurement.per_order", body["unknown_components"])

    def test_platform_version_follows_the_current_g2(self):
        cid, supply_a, supply_b = self._two_supplies()
        add_gate(self.client, cid, "supply_distribution", status="verified", supply_offer_id=supply_a)
        evidence = self.client.post(
            f"/api/candidates/{cid}/evidences",
            json={"evidence_type": "platform_policy", "source_url": "https://example.com/policy/v2",
                  "excerpt": "示例：某平台 v2 规则摘录", "fact_kind": "fact"},
        ).get_json()
        switched = add_gate(self.client, cid, "platform_policy", status="verified", evidence_id=evidence["id"],
                            applies_to_platform="xianyu", applies_to_version="v2", supply_offer_id=supply_b)
        self.assertEqual(switched.status_code, 422)
        reasons = " ".join(d["reason"] for d in switched.get_json()["error"]["details"])
        self.assertTrue("不一致" in reasons or "版本" in reasons)
        follow = add_gate(self.client, cid, "platform_policy", status="verified", evidence_id=evidence["id"],
                          applies_to_platform="xianyu", applies_to_version="v1", supply_offer_id=supply_a)
        self.assertEqual(follow.status_code, 200, follow.get_data(as_text=True))


def _platform_evidence(client, candidate_id: str, *, version: str = "v1", token: str = "p"):
    return client.post(
        f"/api/candidates/{candidate_id}/evidences",
        json={"evidence_type": "platform_policy", "source_url": f"https://example.com/policy/{token}",
              "excerpt": f"示例平台规则摘录（{version}）", "fact_kind": "fact"},
    ).get_json()


def _resolve_open_reviews(client) -> int:
    listed = client.get("/api/review-items?status=open").get_json()
    items = listed.get("items", listed if isinstance(listed, list) else [])
    for item in items:
        response = client.post(f"/api/review-items/{item['id']}/resolve", json={"status": "resolved_recheck"})
        assert response.status_code == 200, response.get_data(as_text=True)
    return len(items)


class SelectionSwitchTest(unittest.TestCase):
    """P1（D 已复现）：已核验 A 切到 B 后，旧 G3/G4 不得继续让候选 testable。

    依据 §3.5：G3/G4 跟**当前** G2 所选货源；G2 选择变更须在同一写事务物化必要降级；
    读时按当前有效 G2（含版本）判定，不自动回填旧 NULL 行、不猜历史。
    """

    def setUp(self):
        self.client, self.db_path = new_client("switch_")

    def _verified_on_a(self):
        cid, supply_a = seed_full(self.client)
        responses = verify_all_gates(self.client, cid, supply_a)
        for gate, response in responses.items():
            self.assertEqual(response.status_code, 200, f"{gate}: {response.get_data(as_text=True)}")
        self.assertEqual(detail(self.client, cid)["derived_status"], "testable")
        return cid, supply_a

    def _switch_to_b(self, cid: str) -> str:
        created = _add_supply(self.client, cid, version="v2", token="b", provider="示例B货源")
        self.assertEqual(created.status_code, 201, created.get_data(as_text=True))
        supply_b = created.get_json()["id"]
        evidence = self.client.post(
            f"/api/candidates/{cid}/evidences",
            json={"evidence_type": "supply_distribution", "source_url": "https://example.com/supply/b/license",
                  "excerpt": "B 库素材允许商业用途与转售（示例摘录）", "fact_kind": "fact"},
        ).get_json()
        switched = add_gate(self.client, cid, "supply_distribution", status="verified",
                            supply_offer_id=supply_b, evidence_id=evidence["id"])
        self.assertEqual(switched.status_code, 200, switched.get_data(as_text=True))
        return supply_b

    def test_verified_rows_store_the_supply_actually_used(self):
        cid, supply_a = self._verified_on_a()
        stored = query(self.db_path, "SELECT gate, supply_offer_id FROM gate_review WHERE candidate_id=?"
                                     " AND status='verified'", (cid,))
        by_gate = {row["gate"]: row["supply_offer_id"] for row in stored}
        self.assertEqual(by_gate["cost"], supply_a)             # 省略 supply 时也须持久化实际供给
        self.assertEqual(by_gate["platform_policy"], supply_a)
        # 显式省略 supply 的 G3 路径（新写入口）：落库即当前 G2 供给
        again = add_gate(self.client, cid, "cost", status="verified")
        self.assertEqual(again.status_code, 200, again.get_data(as_text=True))
        self.assertEqual(again.get_json()["supply_offer_id"], supply_a)
        latest = query(self.db_path, "SELECT supply_offer_id FROM gate_review WHERE candidate_id=?"
                                     " AND gate='cost' ORDER BY seq DESC LIMIT 1", (cid,))
        self.assertEqual(latest[0]["supply_offer_id"], supply_a)

    def test_switch_to_other_supply_invalidates_old_rows(self):
        cid, supply_a = self._verified_on_a()
        before = counts(self.db_path, "gate_review", "review_item")
        supply_b = self._switch_to_b(cid)
        materialized = counts(self.db_path, "gate_review", "review_item")
        self.assertGreaterEqual(materialized["gate_review"] - before["gate_review"], 3)  # B 行 + 两条降级
        self.assertGreaterEqual(materialized["review_item"] - before["review_item"], 2)
        self.assertEqual(query(self.db_path, "SELECT status FROM gate_review WHERE candidate_id=?"
                                            " AND gate='cost' ORDER BY seq DESC LIMIT 1", (cid,))[0]["status"],
                         "expired")
        self.assertEqual(query(self.db_path, "SELECT status FROM gate_review WHERE candidate_id=?"
                                            " AND gate='platform_policy' ORDER BY seq DESC LIMIT 1", (cid,))[0]["status"],
                         "expired")

        snapshot = detail(self.client, cid)
        self.assertNotEqual(snapshot["derived_status"], "testable")   # P1 的反面：不得再 testable
        self.assertEqual(snapshot["derived_status"], "stale")
        self.assertEqual(snapshot["gates"]["cost"], "expired")
        self.assertEqual(snapshot["gates"]["platform_policy"], "expired")
        self.assertEqual(snapshot["gates"]["supply_distribution"], "verified")

        body = scenario(self.client, cid)
        self.assertEqual(body["selected_supply_id"], supply_b)
        self.assertIsNone(body["contribution_per_order_minor"])       # 不能借 A 的已知成本
        self.assertIn("procurement.per_order", body["unknown_components"])

        reads = counts(self.db_path, "gate_review", "review_item")
        detail(self.client, cid)
        detail(self.client, cid)
        self.assertEqual(counts(self.db_path, "gate_review", "review_item"), reads)   # GET 零写
        self.client.post("/api/runs/recompute", json={"candidate_id": cid})
        again = self.client.post("/api/runs/recompute", json={"candidate_id": cid}).get_json()
        self.assertEqual(again["downgraded"], 0)                       # 已物化 → 幂等

    def test_recovery_after_switch_needs_user_reverification(self):
        cid, supply_a = self._verified_on_a()
        supply_b = self._switch_to_b(cid)
        # 真实恢复路径：B 的成本与 A **完全同值**，仅改绑定货源（不靠改假金额绕过）
        add_default_costs(self.client, cid, supply_b)
        cost_again = add_gate(self.client, cid, "cost", status="verified")
        self.assertEqual(cost_again.status_code, 200, cost_again.get_data(as_text=True))
        self.assertEqual(cost_again.get_json()["supply_offer_id"], supply_b)
        g4 = add_gate(self.client, cid, "platform_policy", status="verified",
                      evidence_id=_platform_evidence(self.client, cid, version="v2", token="b")["id"],
                      applies_to_platform="xianyu", applies_to_version="v2")
        self.assertEqual(g4.status_code, 200, g4.get_data(as_text=True))
        self.assertNotEqual(detail(self.client, cid)["derived_status"], "testable")   # 复核项未处理
        self.assertGreaterEqual(_resolve_open_reviews(self.client), 1)
        self.assertEqual(detail(self.client, cid)["derived_status"], "testable")

    def test_legacy_null_supply_rows_are_conservatively_expired(self):
        cid, supply_a = self._verified_on_a()
        _exec(self.db_path, "UPDATE gate_review SET supply_offer_id=NULL WHERE candidate_id=?"
                            " AND gate='cost' AND status='verified'", (cid,))
        before = counts(self.db_path, "gate_review", "review_item")
        snapshot = detail(self.client, cid)
        self.assertEqual(snapshot["gates"]["cost"], "expired")         # 保守失效，不猜历史供给
        self.assertEqual(snapshot["derived_status"], "stale")
        detail(self.client, cid)
        self.assertEqual(counts(self.db_path, "gate_review", "review_item"), before)   # 不回填、不写库
        recompute = self.client.post("/api/runs/recompute", json={"candidate_id": cid}).get_json()
        self.assertEqual(recompute["candidates"], 1)
        self.assertEqual(detail(self.client, cid)["derived_status"], "stale")          # 状态口径与 GET 一致
        # 收尾要求：recompute 必须真正物化该降级（不再锁定“不物化”的残留），第二次才幂等
        self.assertGreaterEqual(recompute["downgraded"], 1)
        self.assertEqual(query(self.db_path, "SELECT status FROM gate_review WHERE candidate_id=?"
                                            " AND gate='cost' ORDER BY seq DESC LIMIT 1", (cid,))[0]["status"],
                         "expired")
        materialized = counts(self.db_path, "gate_review", "review_item")
        rows_before = query(self.db_path, "SELECT id, seq, status, created_at FROM gate_review"
                                          " WHERE candidate_id=? ORDER BY seq", (cid,))
        second = self.client.post("/api/runs/recompute", json={"candidate_id": cid}).get_json()
        self.assertEqual(second["downgraded"], 0)                                       # 幂等
        self.assertEqual(counts(self.db_path, "gate_review", "review_item"), materialized)
        self.assertEqual(query(self.db_path, "SELECT id, seq, status, created_at FROM gate_review"
                                            " WHERE candidate_id=? ORDER BY seq", (cid,)), rows_before)
        open_kinds = {row["kind"] for row in query(self.db_path, "SELECT kind FROM review_item"
                                                                 " WHERE status='open'")}
        self.assertTrue(open_kinds)                                                     # 阻断复核项已建

    def test_same_supply_g2_replay_keeps_other_gates(self):
        cid, supply_a = self._verified_on_a()
        before = counts(self.db_path, "review_item")
        again = add_gate(self.client, cid, "supply_distribution", status="verified", supply_offer_id=supply_a)
        self.assertEqual(again.status_code, 200, again.get_data(as_text=True))
        self.assertEqual(again.get_json()["candidate_status"], "testable")
        snapshot = detail(self.client, cid)
        self.assertEqual(snapshot["gates"]["cost"], "verified")        # 同语义重放不反复降级
        self.assertEqual(snapshot["gates"]["platform_policy"], "verified")
        self.assertEqual(counts(self.db_path, "review_item"), before)  # 不新增复核项

    def test_g2_invalidation_does_not_fall_back_to_old_verified(self):
        cid, supply_a = self._verified_on_a()
        clause = query(self.db_path, "SELECT evidence_id FROM gate_review WHERE candidate_id=?"
                                     " AND gate='supply_distribution' ORDER BY seq DESC LIMIT 1", (cid,))[0]["evidence_id"]
        self.client.post(f"/api/evidences/{clause}/invalidate", json={"invalid_reason": "条款页已变更"})
        snapshot = detail(self.client, cid)
        self.assertEqual(snapshot["gates"]["supply_distribution"], "expired")
        self.assertEqual(snapshot["gates"]["cost"], "expired")
        self.assertEqual(snapshot["gates"]["platform_policy"], "expired")
        self.assertNotEqual(snapshot["derived_status"], "testable")

    def test_failed_g2_does_not_fall_back(self):
        cid, supply_a = self._verified_on_a()
        failed = add_gate(self.client, cid, "supply_distribution", status="failed")
        self.assertEqual(failed.status_code, 200, failed.get_data(as_text=True))
        snapshot = detail(self.client, cid)
        self.assertEqual(snapshot["gates"]["supply_distribution"], "failed")
        self.assertEqual(snapshot["gates"]["cost"], "expired")
        self.assertEqual(snapshot["gates"]["platform_policy"], "expired")

    def test_version_change_requires_g4_reverification(self):
        cid, supply_a = self._verified_on_a()
        patched = self.client.patch(f"/api/supplies/{supply_a}", json={"format_version": "v2"})
        self.assertEqual(patched.status_code, 200, patched.get_data(as_text=True))
        self.assertNotEqual(detail(self.client, cid)["derived_status"], "testable")
        re_g2 = add_gate(self.client, cid, "supply_distribution", status="verified", supply_offer_id=supply_a)
        self.assertEqual(re_g2.status_code, 200, re_g2.get_data(as_text=True))
        snapshot = detail(self.client, cid)
        self.assertEqual(snapshot["gates"]["supply_distribution"], "verified")
        self.assertEqual(snapshot["gates"]["platform_policy"], "expired")   # 版本已变：G4 必须重核
        self.assertNotEqual(snapshot["derived_status"], "testable")         # 不得直接 testable
        g4 = add_gate(self.client, cid, "platform_policy", status="verified",
                      evidence_id=_platform_evidence(self.client, cid, version="v2", token="v2")["id"],
                      applies_to_platform="xianyu", applies_to_version="v2")
        self.assertEqual(g4.status_code, 200, g4.get_data(as_text=True))
        _resolve_open_reviews(self.client)
        self.assertEqual(detail(self.client, cid)["derived_status"], "testable")

    def test_star_version_keeps_applying_after_version_change(self):
        cid, supply_a = seed_full(self.client)
        add_default_costs(self.client, cid, supply_a)
        demand_evidence = next(e["id"] for e in detail(self.client, cid)["evidences"]
                               if e["evidence_type"] == "demand")
        add_gate(self.client, cid, "demand", status="verified", evidence_id=demand_evidence)
        add_gate(self.client, cid, "supply_distribution", status="verified", supply_offer_id=supply_a)
        star = add_gate(self.client, cid, "platform_policy", status="verified",
                        evidence_id=_platform_evidence(self.client, cid)["id"],
                        applies_to_platform="xianyu", applies_to_version="*")
        self.assertEqual(star.status_code, 200, star.get_data(as_text=True))
        add_gate(self.client, cid, "cost", status="verified")
        self.client.patch(f"/api/supplies/{supply_a}", json={"format_version": "v9"})
        add_gate(self.client, cid, "supply_distribution", status="verified", supply_offer_id=supply_a)
        snapshot = detail(self.client, cid)
        self.assertEqual(snapshot["gates"]["platform_policy"], "verified")   # 明确适用 * 保持有效
        _resolve_open_reviews(self.client)
        self.assertEqual(detail(self.client, cid)["derived_status"], "testable")

    def test_mismatching_and_cross_candidate_supplies_still_refused(self):
        cid, supply_a = self._verified_on_a()
        supply_b = _add_supply(self.client, cid, version="v2", token="b2", provider="示例B2货源")
        self.assertEqual(supply_b.status_code, 201, supply_b.get_data(as_text=True))
        supply_b_id = supply_b.get_json()["id"]
        other_cid, other_supply = seed_full(self.client, "示例-切换另一候选")
        for gate, extra in (("cost", {}),
                            ("platform_policy", {"evidence_id": _platform_evidence(self.client, cid, token="x")["id"],
                                                 "applies_to_platform": "xianyu", "applies_to_version": "v1"})):
            with self.subTest(gate=gate, case="mismatch"):
                refused = add_gate(self.client, cid, gate, status="verified",
                                   supply_offer_id=supply_b_id, **extra)
                self.assertEqual(refused.status_code, 422)
                self.assertIn("不一致", " ".join(d["reason"] for d in refused.get_json()["error"]["details"]))
            with self.subTest(gate=gate, case="cross-candidate"):
                refused = add_gate(self.client, cid, gate, status="verified",
                                   supply_offer_id=other_supply, **extra)
                self.assertEqual(refused.status_code, 422)
                self.assertIn("不属于本候选", " ".join(d["reason"] for d in refused.get_json()["error"]["details"]))
        self.assertEqual(other_cid != cid, True)


class CostRebindingTest(unittest.TestCase):
    """同值改绑（`_same` 语义比较）与 G3 成本完整性口径。"""

    def setUp(self):
        self.client, self.db_path = new_client("rebind_")

    def _verified_on_a(self):
        cid, supply_a = seed_full(self.client)
        verify_all_gates(self.client, cid, supply_a)
        self.assertEqual(detail(self.client, cid)["derived_status"], "testable")
        return cid, supply_a

    def _add_supply_b(self, cid: str) -> str:
        created = _add_supply(self.client, cid, version="v2", token="rb", provider="示例改绑货源B")
        self.assertEqual(created.status_code, 201, created.get_data(as_text=True))
        return created.get_json()["id"]

    def test_same_values_can_be_rebound_to_another_supply(self):
        cid, supply_a = self._verified_on_a()
        supply_b = self._add_supply_b(cid)
        before_rows = query(self.db_path, "SELECT id, role, basis FROM cost_item WHERE candidate_id=?"
                                          " AND is_active=1", (cid,))
        add_default_costs(self.client, cid, supply_b)          # 值与 A 完全相同，只有供给不同
        active = query(self.db_path, "SELECT id, role, basis, supply_offer_id, supersedes_id FROM cost_item"
                                     " WHERE candidate_id=? AND is_active=1", (cid,))
        self.assertEqual(len(active), len(before_rows))                        # 每个 (role,basis) 仍恰好一条活跃
        self.assertTrue(all(row["supply_offer_id"] == supply_b for row in active))   # 全部确指 B
        self.assertTrue(all(row["supersedes_id"] for row in active))           # supersedes_id 正确
        old_ids = {row["id"] for row in before_rows}
        self.assertEqual({row["supersedes_id"] for row in active}, old_ids)
        self.assertEqual(query(self.db_path, "SELECT COUNT(*) AS n FROM cost_item WHERE candidate_id=?"
                                            " AND is_active=0", (cid,))[0]["n"], len(old_ids))
        # 同语义重放不增殖：行数、降级行、复核项都不再变化
        stable = counts(self.db_path, "cost_item", "gate_review", "review_item")
        add_default_costs(self.client, cid, supply_b)
        self.assertEqual(counts(self.db_path, "cost_item", "gate_review", "review_item"), stable)
        # 同一条 (role,basis) 用 supersede 入口改绑也生效
        sale_row = next(row for row in active if row["role"] == "sale_price")
        superseded = self.client.post(f"/api/cost-items/{sale_row['id']}/supersede",
                                      json={"value_kind": "money", "money_minor": 1000,
                                            "supply_offer_id": supply_a, "assumption_note": "示例假设：本行依据教学样例"})
        self.assertEqual(superseded.status_code, 200, superseded.get_data(as_text=True))
        rebound = query(self.db_path, "SELECT supply_offer_id, is_active FROM cost_item WHERE id=?",
                        (superseded.get_json()["id"],))[0]
        self.assertEqual(rebound["supply_offer_id"], supply_a)                 # 回到 A
        self.assertEqual(rebound["is_active"], 1)

    def test_evidence_and_fact_kind_changes_are_semantic(self):
        cid, supply_a = self._verified_on_a()
        evidence = self.client.post(
            f"/api/candidates/{cid}/evidences",
            json={"evidence_type": "platform_policy", "source_url": "https://example.com/policy/basis",
                  "excerpt": "示例：作为成本依据的摘录", "fact_kind": "fact"},
        ).get_json()
        before = counts(self.db_path, "cost_item")["cost_item"]
        response = add_cost(self.client, cid, role="sale_price", basis="per_order", value_kind="money",
                            money_minor=1000, supply_offer_id=supply_a, fact_kind="fact",
                            source_evidence_id=evidence["id"], assumption_note="示例假设：本行依据教学样例")
        self.assertEqual(response.status_code, 201, response.get_data(as_text=True))
        self.assertGreater(counts(self.db_path, "cost_item")["cost_item"], before)   # 依据变化 → 新行
        active = query(self.db_path, "SELECT fact_kind, source_evidence_id FROM cost_item WHERE candidate_id=?"
                                     " AND role='sale_price' AND is_active=1", (cid,))[0]
        self.assertEqual((active["fact_kind"], active["source_evidence_id"]), ("fact", evidence["id"]))
        stable = counts(self.db_path, "cost_item")
        add_cost(self.client, cid, role="sale_price", basis="per_order", value_kind="money", money_minor=1000,
                 supply_offer_id=supply_a, fact_kind="fact", source_evidence_id=evidence["id"],
                 assumption_note="示例假设：本行依据教学样例")
        self.assertEqual(counts(self.db_path, "cost_item"), stable)                  # 真同语义重放不增行

    def test_partial_rebinding_cannot_fake_g3_completeness(self):
        """静态疑点实测：只把三档采购改绑 B、其余成本仍属 A 时，G3 不得凭 A 的已知值通过。"""
        cid, supply_a = self._verified_on_a()
        supply_b = self._add_supply_b(cid)
        add_gate(self.client, cid, "supply_distribution", status="verified", supply_offer_id=supply_b,
                 evidence_id=self.client.post(
                     f"/api/candidates/{cid}/evidences",
                     json={"evidence_type": "supply_distribution",
                           "source_url": "https://example.com/supply/rb/license",
                           "excerpt": "改绑货源 B 允许商业用途与转售（示例摘录）",
                           "fact_kind": "fact"}).get_json()["id"])
        for spec in (spec for spec in DEFAULT_COSTS if spec["role"] == "procurement"):
            payload = dict(spec)
            payload.setdefault("assumption_note", "示例假设：本行依据教学样例")
            payload["supply_offer_id"] = supply_b
            response = add_cost(self.client, cid, **payload)
            self.assertIn(response.status_code, (200, 201), response.get_data(as_text=True))
        body = scenario(self.client, cid)
        self.assertIsNone(body["contribution_per_order_minor"])      # 情景：B 的成本集不完整
        self.assertIn("platform_fee", body["unknown_components"])
        refused = add_gate(self.client, cid, "cost", status="verified")   # 省略 supply → 当前 G2 = B
        self.assertEqual(refused.status_code, 422, refused.get_data(as_text=True))
        reasons = " ".join(d["reason"] for d in refused.get_json()["error"]["details"])
        self.assertIn("platform_fee", reasons)                       # G3 用同一选择规则，不拿 A 的已知值凑完整
        self.assertIn("manual_labor", reasons)


class RecomputeMaterializationTest(unittest.TestCase):
    """当前 G2 失效/版本变化的 recompute 物化与幂等（reviews._degrade_reason 复用 state 规则）。"""

    def setUp(self):
        self.client, self.db_path = new_client("mat_")

    def _testable(self):
        cid, supply_a = seed_full(self.client)
        verify_all_gates(self.client, cid, supply_a)
        self.assertEqual(detail(self.client, cid)["derived_status"], "testable")
        return cid, supply_a

    def test_recompute_materializes_version_change_for_cost_and_platform(self):
        cid, supply_a = self._testable()
        patched = self.client.patch(f"/api/supplies/{supply_a}", json={"format_version": "v2"})
        self.assertEqual(patched.status_code, 200, patched.get_data(as_text=True))
        before = counts(self.db_path, "gate_review", "review_item")
        first = self.client.post("/api/runs/recompute", json={"candidate_id": cid}).get_json()
        self.assertGreaterEqual(first["downgraded"], 2)             # cost + platform_policy 均已物化
        for gate in ("cost", "platform_policy"):
            self.assertEqual(query(self.db_path, "SELECT status FROM gate_review WHERE candidate_id=?"
                                                f" AND gate='{gate}' ORDER BY seq DESC LIMIT 1", (cid,))[0]["status"],
                             "expired")
            self.assertEqual(query(self.db_path, "SELECT verified_by FROM gate_review WHERE candidate_id=?"
                                                f" AND gate='{gate}' ORDER BY seq DESC LIMIT 1", (cid,))[0]["verified_by"],
                             "system_rule")
        self.assertGreater(counts(self.db_path, "review_item")["review_item"], before["review_item"])
        after_first = counts(self.db_path, "gate_review", "review_item")
        rows = query(self.db_path, "SELECT id, seq, status, created_at FROM gate_review WHERE candidate_id=?"
                                  " ORDER BY seq", (cid,))
        second = self.client.post("/api/runs/recompute", json={"candidate_id": cid}).get_json()
        self.assertEqual(second["downgraded"], 0)
        self.assertEqual(counts(self.db_path, "gate_review", "review_item"), after_first)
        self.assertEqual(query(self.db_path, "SELECT id, seq, status, created_at FROM gate_review"
                                            " WHERE candidate_id=? ORDER BY seq", (cid,)), rows)
        self.assertEqual(detail(self.client, cid)["derived_status"], "stale")

    def test_recompute_materializes_failed_g2(self):
        cid, supply_a = self._testable()
        failed = add_gate(self.client, cid, "supply_distribution", status="failed")
        self.assertEqual(failed.status_code, 200, failed.get_data(as_text=True))
        first = self.client.post("/api/runs/recompute", json={"candidate_id": cid}).get_json()
        self.assertGreaterEqual(first["downgraded"], 2)
        snapshot = detail(self.client, cid)
        self.assertEqual(snapshot["gates"]["supply_distribution"], "failed")
        self.assertEqual(snapshot["gates"]["cost"], "expired")
        self.assertEqual(snapshot["gates"]["platform_policy"], "expired")
        second = self.client.post("/api/runs/recompute", json={"candidate_id": cid}).get_json()
        self.assertEqual(second["downgraded"], 0)

    def test_resolve_does_not_resurrect_downgraded_rows(self):
        cid, supply_a = self._testable()
        self.client.patch(f"/api/supplies/{supply_a}", json={"format_version": "v2"})
        self.client.post("/api/runs/recompute", json={"candidate_id": cid})
        resolved = _resolve_open_reviews(self.client)
        self.assertGreaterEqual(resolved, 1)
        snapshot = detail(self.client, cid)
        self.assertNotEqual(snapshot["gates"]["cost"], "verified")     # 处理复核不使失效行回生
        self.assertNotEqual(snapshot["derived_status"], "testable")


if __name__ == "__main__":
    unittest.main()
