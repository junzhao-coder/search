"""S5 每日摘要聚合测试（设计 S4_RANKING_SPEC v2 §6/§8；只读、隔离 DB）。

覆盖：top 与 ranking 一致、limit 截断、blocked 独立且置顶、空库空摘要、as_of 必填与确定性、
全表零写入、仅推荐池进 top、digest_date/结构键、pools/omitted 透传。
"""

import unittest

from app.core import daily, ranking
from app.storage.db import connect
from tests.api import b2_helpers as b2

AS_OF = "2026-10-20T00:00:00Z"


class DailyDigestTest(unittest.TestCase):
    def setUp(self):
        self.client, self.db_path = b2.new_client("daily_")

    # ---------------------------------------------------------------- helpers
    def digest(self, **kwargs):
        kwargs.setdefault("as_of", AS_OF)
        # 既有测试全部用 synthetic 夹具；按契约默认 real-only 后，helper 显式纳入合成，
        # 以继续覆盖聚合语义（HTTP 端点默认 real-only 由 tests/api/test_daily_endpoint.py 覆盖）。
        kwargs.setdefault("include_synthetic", True)
        conn = connect(self.db_path)
        try:
            return daily.daily_digest(conn, **kwargs)
        finally:
            conn.close()

    def ranked(self, **kwargs):
        kwargs.setdefault("as_of", AS_OF)
        kwargs.setdefault("include_synthetic", True)
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

    def insert_candidate_without_demand(self, candidate_id: str) -> None:
        conn = connect(self.db_path)
        try:
            filled = {}
            for column in conn.execute("PRAGMA table_info(candidate)").fetchall():
                if column["notnull"] and column["dflt_value"] is None and not column["pk"]:
                    filled[column["name"]] = {"title": "示例-无需求", "data_origin": "synthetic",
                                              "status": "pending", "created_at": AS_OF,
                                              "updated_at": AS_OF, "identity_source": "title",
                                              "delivery_form": "", "category": "", "use_case": "",
                                              "notes": ""}.get(column["name"], "")
            filled["id"] = candidate_id
            names = ",".join(filled)
            marks = ",".join("?" for _ in filled)
            conn.execute(f"INSERT INTO candidate({names}) VALUES({marks})", tuple(filled.values()))
        finally:
            conn.close()

    # ---------------------------------------------------------------- cases
    def test_full_digest_matches_ranking_and_truncates_top(self):
        recommended = [self.t1_candidate(f"示例-D-{index}")[0] for index in range(6)]
        blocked_id, blocked_supply = self.t1_candidate("示例-D-需处理")
        self.client.patch(f"/api/supplies/{blocked_supply}", json={"status": "invalid"})
        observing_id, _ = b2.seed_full(self.client, title="示例-D-观察")
        exploring_id, _ = b2.seed_full(self.client, title="示例-D-探索", commercial="unknown")
        self.insert_candidate_without_demand("c_d_insufficient")
        excluded_id, _ = b2.seed_full(self.client, title="示例-D-排除")
        self.client.post(f"/api/candidates/{excluded_id}/override",
                         json={"manual_override": "explore", "override_reason": "示例"})

        digest = self.digest(limit=5)
        ranked = self.ranked(limit=5)

        self.assertEqual(digest["kind"], "daily_digest")
        self.assertEqual(digest["as_of"], AS_OF)
        self.assertEqual(digest["digest_date"], "2026-10-20")
        self.assertEqual(digest["rank_version"], ranked["rank_version"])
        self.assertEqual(digest["source"], "ranking.rank_candidates")
        self.assertEqual(digest["pools"], ranked["pools"])
        self.assertEqual(digest["omitted"], ranked["omitted"])
        self.assertEqual(digest["daily_limit"], 5)
        # top 恰 5 条且与 ranking 的 daily_pick 推荐项一致（含次序与 rank 字段）
        expected_top = [item for item in ranked["items"]
                        if item["pool"] == "recommended" and item["daily_pick"]]
        self.assertEqual([item["candidate_id"] for item in digest["top"]],
                         [item["candidate_id"] for item in expected_top])
        self.assertEqual([item["rank"] for item in digest["top"]], [item["rank"] for item in expected_top])
        self.assertEqual(len(digest["top"]), 5)
        # 仅推荐池进 top
        top_ids = {item["candidate_id"] for item in digest["top"]}
        self.assertTrue(top_ids.issubset(set(recommended)))
        self.assertNotIn(observing_id, top_ids)
        self.assertNotIn(exploring_id, top_ids)
        self.assertNotIn(blocked_id, top_ids)
        # blocked 独立列出（含 stale 原因与 next_action），且 ranking 中置顶
        self.assertEqual([item["candidate_id"] for item in digest["blocked"]], [blocked_id])
        self.assertTrue(digest["blocked"][0]["reasons"][0].startswith("stale:"))
        self.assertTrue(digest["blocked"][0]["next_action"])
        self.assertEqual(ranked["items"][0]["pool"], "blocked")
        # 观察/探索/insufficient/excluded 计数
        self.assertEqual([item["candidate_id"] for item in digest["observing"]], [observing_id])
        self.assertEqual([item["candidate_id"] for item in digest["exploring"]], [exploring_id])
        self.assertEqual(digest["counts"], {"top": 5, "blocked": 1, "observing": 1, "exploring": 1,
                                            "omitted": len(ranked["omitted"]), "insufficient": 1,
                                            "excluded": 1})
        self.assertEqual(len(digest["omitted"]), 1)                # 6 推荐 → 第 6 条 omitted
        self.assertTrue(digest["pending_confirmation"])
        self.assertIn("不凑数", digest["display_note"])
        self.assertIn("不是收益", digest["display_note"])

    def test_limit_is_passed_through(self):
        for index in range(3):
            self.t1_candidate(f"示例-DL-{index}")
        digest = self.digest(limit=2)
        ranked = self.ranked(limit=2)
        self.assertEqual(len(digest["top"]), 2)
        self.assertEqual([item["candidate_id"] for item in digest["top"]],
                         [item["candidate_id"] for item in ranked["items"] if item["daily_pick"]])
        self.assertEqual(len(digest["omitted"]), 1)

    def test_empty_database_returns_empty_digest(self):
        digest = self.digest()
        self.assertEqual(digest["top"], [])
        self.assertEqual(digest["blocked"], [])
        self.assertEqual(digest["observing"], [])
        self.assertEqual(digest["exploring"], [])
        self.assertEqual(digest["omitted"], [])
        self.assertEqual(digest["pools"], {"excluded": 0, "blocked": 0, "recommended": 0,
                                           "observing": 0, "exploring": 0, "insufficient": 0})
        self.assertEqual(digest["counts"]["top"], 0)

    def test_as_of_required_and_deterministic(self):
        self.t1_candidate("示例-DA-确定性")
        with self.assertRaises(TypeError):
            conn = connect(self.db_path)
            try:
                daily.daily_digest(conn)                            # as_of 必填
            finally:
                conn.close()
        with self.assertRaises(ValueError):
            self.digest(as_of="not-a-timestamp")
        self.assertEqual(self.digest(), self.digest())              # 同 as_of 逐字段一致

    def test_zero_write(self):
        self.t1_candidate("示例-DW-零写入")
        before = self.snapshot()
        self.digest()
        self.assertEqual(self.snapshot(), before)                   # 全部业务表全行零写入


if __name__ == "__main__":
    unittest.main()
