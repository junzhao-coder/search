"""S4-B1 匹配设计矩阵 M-01…M-12（设计 docs/design/S4_MATCHING_SPEC.md v2）。

只验证**只读纯函数** ``app.core.matching.match_supplies``：不新增接口、不联网、不加依赖。
每个 case 用隔离 tmp DB（``b2_helpers.new_client``）；零写入用 supply_offer / gate_review /
review_item / candidate 四表**全行**快照对比（连续两次调用前后一致）。
"""

import unittest

from app.core import matching
from app.storage.db import connect
from tests.api import b2_helpers as b2

OLD_STAMP = "2026-01-01T00:00:00Z"          # 远早于运行时钟（2026-10），用于 TTL/到期夹具
TABLES = ("supply_offer", "gate_review", "review_item", "candidate")


class MatchingTest(unittest.TestCase):
    def setUp(self):
        self.client, self.db_path = b2.new_client("match_")

    # ---------------------------------------------------------------- helpers
    def match(self, candidate_id: str) -> dict:
        conn = connect(self.db_path)
        try:
            return matching.match_supplies(conn, candidate_id)
        finally:
            conn.close()

    def snapshot(self) -> dict:
        conn = connect(self.db_path)
        try:
            return {table: [dict(row) for row in conn.execute(f"SELECT * FROM {table} ORDER BY rowid")]
                    for table in TABLES}
        finally:
            conn.close()

    def assert_read_only(self, candidate_id: str) -> dict:
        before = self.snapshot()
        first = self.match(candidate_id)
        second = self.match(candidate_id)
        self.assertEqual(first, second)                       # 纯函数：同状态同结果
        self.assertEqual(self.snapshot(), before)             # 四表全行含时间戳逐字节一致
        return first

    def license_evidence_id(self, candidate_id: str) -> str:
        return next(row["license_evidence_id"] for row in b2.detail(self.client, candidate_id)["supplies"])

    def second_supply(self, candidate_id: str) -> str:
        response = self.client.post(f"/api/candidates/{candidate_id}/supplies", json={
            "provider_name": "示例第二货源", "provider_url": "https://example.com/supply/second",
            "sample_checked": "partial", "sample_note": "抽检 2 个文件的结构与占位符",
            "commercial_allowed": "yes", "redistribute_allowed": "yes", "resale_allowed": "yes",
            "license_evidence_url": "https://example.com/supply/second/license",
            "format_version": "v1", "downloadable": "yes",
        })
        self.assertEqual(response.status_code, 201, response.get_data(as_text=True))
        return response.get_json()["id"]

    def reviews(self, candidate_id: str) -> list[dict]:
        return b2.query(self.db_path, "SELECT kind, ref_gate, reason, status, blocking FROM review_item"
                                      " WHERE ref_id=? OR ref_id IN (SELECT id FROM supply_offer WHERE candidate_id=?)"
                                      " ORDER BY created_at, id", (candidate_id, candidate_id))

    def gate_rows(self, candidate_id: str, gate: str) -> list[dict]:
        return b2.query(self.db_path, "SELECT * FROM gate_review WHERE candidate_id=? AND gate=? ORDER BY seq",
                        (candidate_id, gate))

    # ---------------------------------------------------------------- M-01
    def test_m01_full_import_is_needs_review_never_adaptable(self):
        candidate_id, supply_id = b2.seed_full(self.client)
        result = self.assert_read_only(candidate_id)
        self.assertEqual(set(result), {"candidate_id", "current_g2_supply_id", "is_current_g2_valid",
                                       "items", "gaps", "display_note"})
        self.assertIsNone(result["current_g2_supply_id"])                       # 尚无 G2
        self.assertFalse(result["is_current_g2_valid"])
        self.assertIn("g2_not_verified", result["gaps"])
        self.assertIn("dims_text_only", result["gaps"])
        self.assertEqual(len(result["items"]), 1)
        item = result["items"][0]
        self.assertEqual(item["supply_offer_id"], supply_id)
        self.assertEqual(item["dims"]["用途"], "hint_only")                     # 无受控词表
        self.assertEqual(item["level"], "needs_review")                         # 不得 adaptable
        self.assertFalse(item["is_selected_by_g2"])                             # 唯一货源只是数值 fallback
        self.assertIn("S4_MATCHING_SPEC", matching.__doc__)
        self.assertEqual(b2.detail(self.client, candidate_id)["derived_status"], "pending")

    # ---------------------------------------------------------------- M-02
    def test_m02_unknown_license_needs_review_and_g2_still_422(self):
        candidate_id, supply_id = b2.seed_full(self.client, title="示例-M02许可未知", commercial="unknown")
        result = self.assert_read_only(candidate_id)
        item = result["items"][0]
        self.assertIn("license_unknown", result["gaps"])
        self.assertEqual(item["level"], "needs_review")
        self.assertNotIn("name_only_similarity", item["reasons"])               # H1：不做相似度
        response = b2.add_gate(self.client, candidate_id, "supply_distribution", status="verified",
                               supply_offer_id=supply_id, evidence_id=self.license_evidence_id(candidate_id))
        self.assertEqual(response.status_code, 422, response.get_data(as_text=True))
        self.assertEqual(self.match(candidate_id)["items"][0]["level"], "needs_review")

    # ---------------------------------------------------------------- M-03
    def test_m03_supplier_self_claim_does_not_upgrade(self):
        candidate_id, supply_id = b2.seed_full(self.client, title="示例-M03自称可转售", resale="unknown")
        response = self.client.patch(f"/api/supplies/{supply_id}", json={
            "license_summary": "供应商自称：本素材可转售、可商用、授权齐全"})
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        result = self.assert_read_only(candidate_id)
        item = result["items"][0]
        self.assertIn("self_claim_only", item["reasons"])                       # 关键词表 + 许可非 yes
        supply = b2.query(self.db_path, "SELECT resale_allowed, commercial_allowed FROM supply_offer"
                                        " WHERE id=?", (supply_id,))[0]
        self.assertEqual(supply["resale_allowed"], "unknown")                   # 许可字段未被改写
        self.assertEqual(supply["commercial_allowed"], "yes")
        response = b2.add_gate(self.client, candidate_id, "supply_distribution", status="verified",
                               supply_offer_id=supply_id, evidence_id=self.license_evidence_id(candidate_id))
        self.assertEqual(response.status_code, 422)                             # 不升级核验

    # ---------------------------------------------------------------- M-04
    def test_m04_invalid_supply_excluded_and_existing_review_fires(self):
        candidate_id, supply_id = b2.seed_full(self.client, title="示例-M04货源失效")
        b2.verify_all_gates(self.client, candidate_id, supply_id)
        response = self.client.patch(f"/api/supplies/{supply_id}", json={"status": "invalid"})
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        result = self.assert_read_only(candidate_id)
        item = result["items"][0]
        self.assertEqual(item["level"], "excluded")
        self.assertIn("supply_invalid", item["reasons"])
        kinds = [row["kind"] for row in self.reviews(candidate_id)]
        self.assertIn("supply_invalid", kinds)                                  # 既有机制，不是匹配写的
        self.assertEqual(b2.detail(self.client, candidate_id)["derived_status"], "stale")

    # ---------------------------------------------------------------- M-05
    def test_m05_license_change_reflected_as_license_changed(self):
        candidate_id, supply_id = b2.seed_full(self.client, title="示例-M05许可变更")
        created = b2.add_gate(self.client, candidate_id, "supply_distribution", status="verified",
                              supply_offer_id=supply_id, evidence_id=self.license_evidence_id(candidate_id))
        self.assertEqual(created.status_code, 200, created.get_data(as_text=True))
        response = self.client.patch(f"/api/supplies/{supply_id}", json={"resale_allowed": "no"})
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        result = self.assert_read_only(candidate_id)
        item = result["items"][0]
        self.assertIn("license_changed", item["reasons"])
        self.assertEqual(item["dims"]["适用条件"], "not_applicable")             # 明确反证，不是缺口
        self.assertEqual(self.gate_rows(candidate_id, "supply_distribution")[-1]["status"], "expired")

    # ---------------------------------------------------------------- M-06
    def test_m06_supply_price_change_does_not_move_contribution(self):
        candidate_id, supply_id = b2.seed_full(self.client, title="示例-M06价格变化")
        b2.verify_all_gates(self.client, candidate_id, supply_id)
        before = b2.scenario(self.client, candidate_id)
        response = self.client.patch(f"/api/supplies/{supply_id}", json={"unit_price_minor": 5000})
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        result = self.assert_read_only(candidate_id)
        self.assertIn("cost_changed", result["items"][0]["reasons"])
        after = b2.scenario(self.client, candidate_id)
        self.assertEqual(after, before)                                         # 金额只来自 cost_item
        self.assertEqual(after["contribution_per_order_minor"], before["contribution_per_order_minor"])

    # ---------------------------------------------------------------- M-07a
    def test_m07a_supply_ttl_excludes_and_materializes_supply_invalid(self):
        candidate_id, supply_id = b2.seed_full(self.client, title="示例-M07a货源TTL")
        b2.verify_all_gates(self.client, candidate_id, supply_id)
        conn = connect(self.db_path)
        try:
            conn.execute("UPDATE supply_offer SET last_checked_at=? WHERE id=?", (OLD_STAMP, supply_id))
        finally:
            conn.close()
        result = self.assert_read_only(candidate_id)
        item = result["items"][0]
        self.assertEqual(item["level"], "excluded")
        self.assertIn("supply_ttl_expired", item["reasons"])                    # 不是 gate_expired
        response = self.client.post("/api/runs/recompute", json={"candidate_id": candidate_id})
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        ttl_reviews = [row for row in self.reviews(candidate_id) if row["kind"] == "supply_invalid"]
        self.assertTrue(any("TTL" in (row["reason"] or "") for row in ttl_reviews), ttl_reviews)

    # ---------------------------------------------------------------- M-07b
    def test_m07b_gate_ttl_marks_gate_expired(self):
        candidate_id, supply_id = b2.seed_full(self.client, title="示例-M07b门槛TTL")
        b2.verify_all_gates(self.client, candidate_id, supply_id)
        conn = connect(self.db_path)
        try:
            conn.execute("UPDATE gate_review SET expires_at=? WHERE candidate_id=? AND gate='supply_distribution'"
                         " AND status='verified'", (OLD_STAMP, candidate_id))
        finally:
            conn.close()
        result = self.assert_read_only(candidate_id)
        item = result["items"][0]
        self.assertIn("gate_expired", item["reasons"])
        self.assertNotIn("supply_ttl_expired", item["reasons"])
        response = self.client.post("/api/runs/recompute", json={"candidate_id": candidate_id})
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        self.assertIn("gate_expired", [row["kind"] for row in self.reviews(candidate_id)])

    # ---------------------------------------------------------------- M-08
    def test_m08_no_supply_reports_gap_not_zero_demand(self):
        candidate_id = b2.seed_demand_only(self.client, title="示例-M08无货源")
        result = self.assert_read_only(candidate_id)
        self.assertEqual(result["items"], [])
        self.assertIn("no_supply_rows", result["gaps"])
        self.assertIn("g2_not_verified", result["gaps"])
        self.assertNotIn("无需求", result["display_note"])                      # 不写"无需求"
        self.assertEqual(matching.DISPLAY_NOTE, "匹配结果仅供挑选与复核，不构成门槛核验或证据。")
        self.assertEqual(b2.detail(self.client, candidate_id)["derived_status"], "pending")

    # ---------------------------------------------------------------- M-09
    def test_m09_two_supplies_reports_current_g2_and_keeps_selection(self):
        candidate_id, supply_id = b2.seed_full(self.client, title="示例-M09双货源")
        second_id = self.second_supply(candidate_id)
        created = b2.add_gate(self.client, candidate_id, "supply_distribution", status="verified",
                              supply_offer_id=supply_id, evidence_id=self.license_evidence_id(candidate_id))
        self.assertEqual(created.status_code, 200, created.get_data(as_text=True))
        before = b2.scenario(self.client, candidate_id)
        result = self.assert_read_only(candidate_id)
        self.assertEqual(len(result["items"]), 2)
        self.assertEqual(result["current_g2_supply_id"], supply_id)
        self.assertTrue(result["is_current_g2_valid"])
        selected = [item for item in result["items"] if item["is_selected_by_g2"]]
        self.assertEqual([item["supply_offer_id"] for item in selected], [supply_id])
        other = next(item for item in result["items"] if item["supply_offer_id"] == second_id)
        self.assertFalse(other["is_selected_by_g2"])                            # 非"排除"
        self.assertNotEqual(other["level"], "excluded")
        self.assertEqual(b2.scenario(self.client, candidate_id), before)        # 匹配不改选择

    # ---------------------------------------------------------------- M-10
    def test_m10_version_mismatch_is_gap_and_g4_stays_unverified(self):
        candidate_id, supply_id = b2.seed_full(self.client, title="示例-M10版本不一致", version="v1")
        created = b2.add_gate(self.client, candidate_id, "supply_distribution", status="verified",
                              supply_offer_id=supply_id, evidence_id=self.license_evidence_id(candidate_id))
        self.assertEqual(created.status_code, 200, created.get_data(as_text=True))
        unverified = b2.add_gate(self.client, candidate_id, "platform_policy", status="unverified",
                                 applies_to_platform="xianyu", applies_to_version="v2")
        self.assertEqual(unverified.status_code, 200, unverified.get_data(as_text=True))
        result = self.assert_read_only(candidate_id)
        item = result["items"][0]
        self.assertEqual(item["dims"]["内容版本"], "not_applicable")             # 基准行 G4=v2
        self.assertIn("format_unknown", result["gaps"])
        self.assertEqual(b2.detail(self.client, candidate_id)["gates"]["platform_policy"], "unverified")

    # ---------------------------------------------------------------- M-11
    def test_m11_match_is_read_only_on_all_paths(self):
        candidate_id, supply_id = b2.seed_full(self.client, title="示例-M11零写入")
        b2.verify_all_gates(self.client, candidate_id, supply_id)
        self.assert_read_only(candidate_id)
        self.client.patch(f"/api/supplies/{supply_id}", json={"status": "invalid"})
        self.assert_read_only(candidate_id)                                     # 失效路径也不写
        with self.assertRaises(KeyError):
            self.match("c_missing")

    # ---------------------------------------------------------------- M-12
    def test_m12_s4_scenario_unchanged_by_matching(self):
        candidate_id, supply_id = b2.seed_full(self.client, title="示例-M12情景不退化")
        b2.verify_all_gates(self.client, candidate_id, supply_id)
        before = b2.scenario(self.client, candidate_id)
        self.assertEqual(b2.detail(self.client, candidate_id)["derived_status"], "testable")
        self.assert_read_only(candidate_id)
        self.assertEqual(b2.scenario(self.client, candidate_id), before)
        self.assertEqual(b2.detail(self.client, candidate_id)["derived_status"], "testable")


    # ---------------------------------------------------------------- M-13
    def test_m13_g2_switch_expires_old_g4_without_misleading_reason(self):
        """策划返工裁定：G2 变更导致旧 G4 行失效，不得冒充 license_changed/失效类 reason。"""
        candidate_id, first_id = b2.seed_full(self.client, title="示例-M13换货源G4失效")
        b2.verify_all_gates(self.client, candidate_id, first_id)
        self.assertEqual(b2.detail(self.client, candidate_id)["gates"]["platform_policy"], "verified")
        second_id = self.second_supply(candidate_id)
        switched = b2.add_gate(self.client, candidate_id, "supply_distribution", status="verified",
                               supply_offer_id=second_id, evidence_id=self.license_evidence_id(candidate_id))
        self.assertEqual(switched.status_code, 200, switched.get_data(as_text=True))
        # 旧 G4 行（指向 first）因 _follows_current_g2 失效：读时 expired。
        self.assertEqual(b2.detail(self.client, candidate_id)["gates"]["platform_policy"], "expired")
        result = self.assert_read_only(candidate_id)              # 四表快照零写入
        first = next(item for item in result["items"] if item["supply_offer_id"] == first_id)
        self.assertTrue(any(ref["gate"] == "platform_policy" and ref["status"] == "expired"
                            for ref in first["gate_refs"]), first["gate_refs"])
        misleading = {"license_changed", "supply_invalid", "supply_ttl_expired", "cost_changed"}
        self.assertEqual(set(first["reasons"]) & misleading, set())   # 不编造未定义 reason
        # 注：DB 里确实会出现 license_changed/cost_changed 复核——那是 gate 换货源时
        # `gates._downgrade_selectors_for_new_g2` 既有机制物化的，不是匹配写的；
        # 上面的 assert_read_only 已用四表快照证明匹配零写入。
        self.assertEqual(b2.detail(self.client, candidate_id)["gates"]["supply_distribution"], "verified")


if __name__ == "__main__":
    unittest.main()
