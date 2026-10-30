"""S4-B3 排序矩阵 R-01…R-16（设计 docs/design/S4_RANKING_SPEC.md v2）。

只验证**只读纯函数** ``app.core.ranking.rank_candidates``：不接 GET、不联网、不加依赖。
每 case 用隔离 tmp DB（``b2_helpers.new_client``）；``as_of`` 固定；零写入用**全部业务表**
全行快照（含时间戳）对比。
"""

import unittest

from app.core import ranking
from app.storage.db import connect
from tests.api import b2_helpers as b2

AS_OF = "2026-10-20T00:00:00Z"
LONG_AGO = "2026-09-10T00:00:00Z"          # 相对 AS_OF 已超 30 天


class RankingTest(unittest.TestCase):
    def setUp(self):
        self.client, self.db_path = b2.new_client("rank_")

    # ---------------------------------------------------------------- helpers
    def rank(self, **kwargs):
        kwargs.setdefault("as_of", AS_OF)
        conn = connect(self.db_path)
        try:
            return ranking.rank_candidates(conn, **kwargs)
        finally:
            conn.close()

    def sql(self, statement: str, params=()):
        conn = connect(self.db_path)
        try:
            conn.execute(statement, params)
        finally:
            conn.close()

    def snapshot(self):
        conn = connect(self.db_path)
        try:
            tables = [row["name"] for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
            return {table: [tuple(dict(row).items()) for row in conn.execute(f"SELECT * FROM {table} ORDER BY rowid")]
                    for table in tables}
        finally:
            conn.close()

    def t1_candidate(self, title: str):
        candidate_id, supply_id = b2.seed_full(self.client, title=title)
        b2.verify_all_gates(self.client, candidate_id, supply_id)
        return candidate_id, supply_id

    def item_of(self, result: dict, candidate_id: str) -> dict:
        return next(item for item in result["items"] if item["candidate_id"] == candidate_id)

    # ---------------------------------------------------------------- R-01
    def test_r01_t1_full_score(self):
        candidate_id, _ = self.t1_candidate("示例-R01满分")
        result = self.rank()
        self.assertEqual(result["pools"]["recommended"], 1)
        item = self.item_of(result, candidate_id)
        self.assertEqual((item["pool"], item["tier"], item["rank"]), ("recommended", "T1", 1))
        self.assertEqual(item["score"], 100)            # 39+15+10+20+8+6+2
        self.assertTrue(item["daily_pick"])
        self.assertIn("四门槛均 verified", item["reasons"])

    # ---------------------------------------------------------------- R-02a
    def test_r02a_tie_break_candidate_id(self):
        first, _ = self.t1_candidate("示例-R02a甲")
        second, _ = self.t1_candidate("示例-R02a乙")
        # 同分同桶且同观察时间（否则 observed_at 会先于 candidate_id 决定次序）
        self.sql("UPDATE demand_signal SET observed_at='2026-10-19T00:00:00Z' WHERE candidate_id IN (?, ?)",
                 (first, second))
        result = self.rank()
        got = [item["candidate_id"] for item in result["items"]]
        self.assertEqual(got, sorted([first, second]))  # 同分同桶 → candidate_id 升序终键
        self.assertEqual({item["score"] for item in result["items"]}, {100})

    # ---------------------------------------------------------------- R-02b
    def test_r02b_manual_minutes_affects_score_and_order(self):
        low, _ = self.t1_candidate("示例-R02b少人工")
        high, _ = self.t1_candidate("示例-R02b多人工")
        self.sql("UPDATE cost_item SET minutes=40 WHERE candidate_id=? AND role='manual_labor'", (high,))
        result = self.rank()
        self.assertEqual(self.item_of(result, low)["score"], 100)
        self.assertEqual(self.item_of(result, high)["score"], 89)      # 分钟档 +2→+1 且人工成本↑使 net 转负（少 +10）
        self.assertEqual(result["items"][0]["candidate_id"], low)

    # ---------------------------------------------------------------- R-03
    def test_r03_t2_via_missing_assumptions_then_t1_with_params(self):
        candidate_id, _ = self.t1_candidate("示例-R03缺假设")
        self.sql("UPDATE cost_item SET money_minor=10000 WHERE candidate_id=? AND role='procurement'"
                 " AND basis='one_time' AND is_active=1", (candidate_id,))
        default = self.rank()
        item = self.item_of(default, candidate_id)
        self.assertEqual(item["tier"], "T2")
        self.assertIsNone(item["inputs_used"]["net_per_order_minor"])  # 未知不是 0
        self.assertTrue(item["daily_pick"])            # T2 仍属推荐池（可入选每日 5 条）
        with_params = self.rank(scenario_params={"amortize_orders": 20})
        t1 = self.item_of(with_params, candidate_id)
        self.assertEqual(t1["tier"], "T1")
        self.assertEqual(t1["inputs_used"]["net_per_order_minor"], 150 - 500)
        self.assertEqual(with_params["scenario_params"]["amortize_orders"], 20)

    # ---------------------------------------------------------------- R-04
    def test_r04_observing_pool(self):
        candidate_id, _ = b2.seed_full(self.client, title="示例-R04观察")
        result = self.rank()
        item = self.item_of(result, candidate_id)
        self.assertEqual(item["pool"], "observing")
        self.assertEqual(item["tier"], "T3")
        self.assertEqual(item["score"], 23)            # 15+8+0（无 verified/无稳定/分钟未知）
        self.assertIn("待补证据", item["reasons"][0])

    # ---------------------------------------------------------------- R-05
    def test_r05_exploring_pool_and_material_gap_penalty(self):
        clean, _ = b2.seed_full(self.client, title="示例-R05对照观察")
        dirty, _ = b2.seed_full(self.client, title="示例-R05许可未知", commercial="unknown")
        result = self.rank()
        exploring = self.item_of(result, dirty)
        self.assertEqual(exploring["pool"], "exploring")
        self.assertEqual(exploring["tier"], "T4")
        self.assertIn("license_unknown", exploring["gaps"])
        self.assertEqual(exploring["score"], 11)       # 5+8+0-2（分钟未知 +0）
        self.assertEqual(self.item_of(result, clean)["score"], 23)
        self.assertEqual(self.item_of(result, clean)["score"] - exploring["score"], 12)

    # ---------------------------------------------------------------- R-06
    def test_r06_blocked_pool_from_invalid_supply(self):
        candidate_id, supply_id = self.t1_candidate("示例-R06失效")
        self.client.patch(f"/api/supplies/{supply_id}", json={"status": "invalid"})
        result = self.rank()
        item = self.item_of(result, candidate_id)
        self.assertEqual((item["pool"], item["tier"], item["rank"]), ("blocked", "B", 1))
        self.assertIsNone(item["score"])
        self.assertTrue(item["reasons"][0].startswith("stale:"))
        self.assertTrue(item["next_action"])
        self.assertFalse(item["daily_pick"])

    # ---------------------------------------------------------------- R-07
    def test_r07_old_observation_loses_freshness_points(self):
        candidate_id, _ = self.t1_candidate("示例-R07旧数据")
        self.sql("UPDATE demand_signal SET observed_at=? WHERE candidate_id=?", (LONG_AGO, candidate_id))
        item = self.item_of(self.rank(), candidate_id)
        self.assertEqual(item["inputs_used"]["observed_at"], LONG_AGO)
        self.assertEqual(item["score"], 92)            # 新鲜 +0（100-8）

    # ---------------------------------------------------------------- R-08
    def test_r08_negative_net_is_shown_without_positive_points(self):
        candidate_id, _ = self.t1_candidate("示例-R08负利润")
        self.sql("UPDATE cost_item SET money_minor=100 WHERE candidate_id=? AND role='sale_price'"
                 " AND is_active=1", (candidate_id,))
        item = self.item_of(self.rank(), candidate_id)
        self.assertEqual(item["tier"], "T1")
        self.assertLess(item["inputs_used"]["net_per_order_minor"], 0)
        self.assertEqual(item["score"], 90)            # 无 net>0 的 +10
        self.assertTrue(any("负利润" in reason for reason in item["reasons"]))

    # ---------------------------------------------------------------- R-09 / R-10
    def test_r09_limit_five_and_omitted_global_rank(self):
        for index in range(6):
            self.t1_candidate(f"示例-R09-{index}")
        result = self.rank()
        self.assertEqual(len(result["items"]), 6)
        self.assertEqual(sum(1 for item in result["items"] if item["daily_pick"]), 5)
        self.assertEqual(len(result["omitted"]), 1)
        self.assertEqual(result["omitted"][0]["rank"], 6)   # 全局连续名次
        self.assertIn("超出每日 5 条上限", result["omitted"][0]["reason"])

    def test_r10_fewer_than_limit_not_padded(self):
        self.t1_candidate("示例-R10甲")
        self.t1_candidate("示例-R10乙")
        result = self.rank()
        self.assertEqual(sum(1 for item in result["items"] if item["daily_pick"]), 2)
        self.assertEqual(result["omitted"], [])

    # ---------------------------------------------------------------- R-11
    def test_r11_manual_override_excluded_from_items(self):
        candidate_id, _ = b2.seed_full(self.client, title="示例-R11探索标记")
        response = self.client.post(f"/api/candidates/{candidate_id}/override",
                                    json={"manual_override": "explore", "override_reason": "示例"})
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        result = self.rank()
        self.assertEqual(result["pools"]["excluded"], 1)
        self.assertEqual(result["items"], [])

    # ---------------------------------------------------------------- R-12
    def test_r12_deterministic_and_zero_write(self):
        self.t1_candidate("示例-R12确定性")
        before = self.snapshot()
        first = self.rank()
        second = self.rank()
        self.assertEqual(first, second)
        self.assertEqual(self.snapshot(), before)       # 全部业务表全行零写入

    # ---------------------------------------------------------------- R-13
    def test_r13_output_shape_and_no_predictions(self):
        self.t1_candidate("示例-R13输出")
        result = self.rank()
        self.assertEqual(result["rank_version"], "rank-v1")
        self.assertEqual(result["as_of"], AS_OF)
        self.assertEqual(result["pool_order"], list(ranking.POOL_ORDER))
        self.assertTrue(result["pending_confirmation"])
        self.assertIn("待用户确认", result["budget_note"])
        for forbidden in ("success_rate", "roi", "probability", "expected_return"):
            self.assertNotIn(forbidden, result)
        self.assertNotIn("成功率", str(result["items"][0]["reasons"]))
        for key in ("rank", "candidate_id", "pool", "tier", "score", "reasons", "gaps",
                    "next_action", "inputs_used"):
            self.assertIn(key, result["items"][0])

    # ---------------------------------------------------------------- R-14
    def test_r14_weights_frozen_for_version(self):
        self.assertEqual(ranking.RANK_VERSION, "rank-v1")
        self.assertEqual(ranking.WEIGHTS["base"], {"T1": 39, "T2": 29, "T3": 15, "T4": 5})
        self.assertEqual(ranking.WEIGHTS["complete"], 15)
        self.assertEqual(ranking.WEIGHTS["net_positive"], 10)
        self.assertEqual(ranking.WEIGHTS["verified_each"], 5)
        self.assertEqual(ranking.WEIGHTS["fresh_7d"], 8)
        self.assertEqual(ranking.WEIGHTS["fresh_30d"], 4)
        self.assertEqual(ranking.WEIGHTS["supply_stable"], 6)
        self.assertEqual(ranking.WEIGHTS["material_gap"], -2)
        with self.assertRaises(ValueError):
            self.rank(rank_version="rank-v2")           # 改权重须实现批 + 升版本

    # ---------------------------------------------------------------- R-15
    def test_r15_stale_from_failed_gate_lands_in_blocked(self):
        candidate_id, _ = self.t1_candidate("示例-R15门槛失败")
        response = self.client.post(f"/api/candidates/{candidate_id}/gates/demand",
                                    json={"status": "failed"})
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        result = self.rank()
        item = self.item_of(result, candidate_id)
        self.assertEqual(item["pool"], "blocked")       # 无 blocking 复核也归 blocked
        self.assertTrue(item["reasons"][0].startswith("stale:"))
        self.assertEqual(result["pools"]["observing"], 0)
        self.assertEqual(result["pools"]["insufficient"], 0)

    # ---------------------------------------------------------------- R-16
    def test_r16_candidate_without_demand_rows_is_insufficient(self):
        conn = connect(self.db_path)
        try:
            columns = conn.execute("PRAGMA table_info(candidate)").fetchall()
            filled = {}
            for column in columns:
                if column["notnull"] and column["dflt_value"] is None and not column["pk"]:
                    filled[column["name"]] = {"title": "示例-R16无需求", "data_origin": "synthetic",
                                              "status": "pending", "created_at": AS_OF,
                                              "updated_at": AS_OF, "identity_source": "title",
                                              "delivery_form": "", "category": "", "use_case": "",
                                              "notes": ""}.get(column["name"], "")
            filled["id"] = "c_r16_no_demand"
            names = ",".join(filled)
            marks = ",".join("?" for _ in filled)
            conn.execute(f"INSERT INTO candidate({names}) VALUES({marks})", tuple(filled.values()))
        finally:
            conn.close()
        result = self.rank()
        self.assertEqual(result["pools"]["insufficient"], 1)
        self.assertNotIn("c_r16_no_demand", [item["candidate_id"] for item in result["items"]])


if __name__ == "__main__":
    unittest.main()
