"""CONTRACT #19：``GET /api/summary/daily?date=`` 只读读路径测试。

覆盖：空库 200、date 参数矩阵、include_synthetic 语义（默认 real-only / =1 纳入合成）、
与 ``daily_digest`` 逐字段一致、幂等、零写入、兼容性（删除 /api/daily、仅 GET、路由数）。
全程隔离 tmp DB、不联网、不写业务库。
"""

import json
import unittest

from app.core import importer
from app.core.daily import daily_digest
from app.storage.db import connect
from tests.api import b2_helpers as b2

DATE = "2026-10-20"
AS_OF = f"{DATE}T00:00:00Z"
_DIGEST_KEYS = {"kind", "as_of", "digest_date", "rank_version", "daily_limit",
                "scenario_params", "budget_minutes", "pools", "top", "blocked",
                "observing", "exploring", "omitted", "counts", "pending_confirmation",
                "budget_note", "display_note", "source"}
_TABLES = ("candidate", "demand_signal", "evidence", "supply_offer", "cost_item",
           "gate_review", "review_item", "run_record", "import_batch")


class SummaryDailyTest(unittest.TestCase):
    def setUp(self):
        self.client, self.db_path = b2.new_client("summary_daily_")

    def get(self, query: str):
        return self.client.get(f"/api/summary/daily?{query}")

    def digest(self, **kwargs):
        conn = connect(self.db_path)
        try:
            return daily_digest(conn, as_of=AS_OF, limit=5, **kwargs)
        finally:
            conn.close()

    def seed_synthetic_full(self, title: str = "示例-合成-每日摘要"):
        candidate_id, supply_id = b2.seed_full(self.client, title=title)
        b2.add_default_costs(self.client, candidate_id, supply_id)
        b2.verify_all_gates(self.client, candidate_id, supply_id)
        return candidate_id

    def seed_real_minimal(self):
        """通过真实导入 API 建一个 ``data_origin='real'`` 候选（不联网）。"""
        cfg = self.client.application.config["APP_CFG"]
        body = json.dumps([{
            "title": "示例-真实来源需求",
            "data_origin": "real",
            "demand_source": "bilibili",
            "demand_native_id": "BV1us8MzPEmn",
            "demand_url": "https://www.bilibili.com/video/BV1us8MzPEmn",
            "demand_excerpt": "真实来源示例摘录",
        }], ensure_ascii=False).encode("utf-8")
        conn = connect(self.db_path)
        try:
            payload, code, _ = importer.handle_import(
                conn, cfg, fmt="json", body=body, filename="real_seed.json",
                mode="atomic", format_version=1, client_ref=None)
        finally:
            conn.close()
        self.assertIn(code, (200, 201), payload)
        return payload

    def assert_error(self, query: str, field: str):
        response = self.get(query)
        self.assertEqual(response.status_code, 422, f"{query} -> {response.status_code}")
        body = response.get_json()
        self.assertEqual(body["error"]["code"], "invalid_field")
        self.assertTrue(any(item.get("field") == field
                            for item in body["error"].get("details") or []))

    # ---------------------------------------------------------------- 空库与结构
    def test_empty_db_returns_200(self):
        response = self.get(f"date={DATE}")
        self.assertEqual(response.status_code, 200)
        body = response.get_json()
        self.assertEqual(set(body), _DIGEST_KEYS)
        self.assertEqual(body["kind"], "daily_digest")
        self.assertEqual(body["as_of"], AS_OF)
        self.assertEqual(body["digest_date"], DATE)
        self.assertEqual(body["daily_limit"], 5)                 # CONTRACT #19：≤5
        self.assertEqual(body["top"], [])

    # ---------------------------------------------------------------- date 矩阵
    def test_date_required_and_validated(self):
        self.assert_error("", "date")
        for bad in ("2026-10-20T12:00:00Z", "2026-10-20 12:00:00", "20261020",
                    "2026-13-01", "2026-02-30", "not-a-date"):
            self.assert_error(f"date={bad}", "date")

    # ---------------------------------------------------------------- include_synthetic
    def test_include_synthetic_matrix(self):
        self.seed_synthetic_full()
        default = self.get(f"date={DATE}").get_json()            # 缺省：real-only
        explicit_zero = self.get(f"date={DATE}&include_synthetic=0").get_json()
        with_synthetic = self.get(f"date={DATE}&include_synthetic=1").get_json()
        self.assertEqual(default, explicit_zero)
        self.assertEqual(default["counts"]["top"], 0)            # 合成候选被排除
        self.assertGreaterEqual(with_synthetic["counts"]["top"], 1)
        for bad in ("2", "yes", "", "01", "true"):
            self.assert_error(f"date={DATE}&include_synthetic={bad}", "include_synthetic")

    def test_default_is_real_only_but_includes_real_data(self):
        self.seed_synthetic_full(title="示例-合成-仅合成")
        self.seed_real_minimal()                                 # real 候选（缺成本/门槛→仍在池中）
        body = self.get(f"date={DATE}").get_json()
        pools_total = sum(body["pools"].values())
        self.assertGreaterEqual(pools_total, 1)                  # real 候选被统计
        self.assertEqual(body["counts"]["top"], 0)               # synthetic 不进入推荐池
        with_synthetic = self.get(f"date={DATE}&include_synthetic=1").get_json()
        self.assertGreaterEqual(with_synthetic["counts"]["top"], 1)

    # ---------------------------------------------------------------- 结构一致/幂等
    def test_matches_daily_digest_directly(self):
        self.seed_synthetic_full()
        for query, kwargs in ((f"date={DATE}", {"include_synthetic": False}),
                              (f"date={DATE}&include_synthetic=1", {"include_synthetic": True})):
            body = self.get(query).get_json()
            self.assertEqual(body, self.digest(**kwargs))

    def test_same_query_is_deterministic(self):
        self.seed_synthetic_full()
        first = self.get(f"date={DATE}&include_synthetic=1").get_data()
        second = self.get(f"date={DATE}&include_synthetic=1").get_data()
        self.assertEqual(first, second)

    # ---------------------------------------------------------------- 只读/兼容
    def test_zero_write(self):
        self.seed_synthetic_full()
        before = b2.counts(self.db_path, *_TABLES)
        self.get(f"date={DATE}")
        self.get(f"date={DATE}&include_synthetic=1")
        self.assert_error(f"date={DATE}&include_synthetic=9", "include_synthetic")
        self.assertEqual(b2.counts(self.db_path, *_TABLES), before)

    def test_compatibility_routes(self):
        health = self.client.get("/api/health")
        self.assertEqual(health.status_code, 200)
        self.assertEqual(sorted(health.get_json()), ["ok", "schema_version", "time", "version"])
        self.assertEqual(self.client.get("/api/candidates").status_code, 200)
        self.assertEqual(self.client.post(f"/api/summary/daily?date={DATE}").status_code, 405)
        self.assertEqual(self.client.get(f"/api/daily?date={DATE}").status_code, 404)  # 已删除
        rules = sorted(str(rule) for rule in self.client.application.url_map.iter_rules()
                       if str(rule).startswith("/api/"))
        self.assertIn("/api/summary/daily", rules)
        self.assertNotIn("/api/daily", rules)
        self.assertEqual(len(rules), 24)                         # 23 + summary/daily - daily
        # The legacy four pages are unchanged; /dash is a separate read-only namespace.
        pages = [r for r in self.client.application.url_map.iter_rules()
                 if not str(r).startswith("/api/") and not str(r).startswith("/static")
                 and not str(r).startswith("/dash")]
        self.assertEqual(len(pages), 4)


if __name__ == "__main__":
    unittest.main()
