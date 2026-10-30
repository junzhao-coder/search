"""Read-only /dash route and data-loader tests (stdlib unittest)."""

from __future__ import annotations

import csv
import json
import pathlib
import sys
import tempfile
import unittest
ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app import create_app  # noqa: E402
from app.dash.data import load_dashboard_data  # noqa: E402

ROUTES = ("/dash/", "/dash/collect", "/dash/opportunities", "/dash/sources", "/dash/daily")


class DashRouteTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="dash_")
        self.db_path = str(pathlib.Path(self.tmp) / "app.db")
        self.app = create_app({"db_path": self.db_path})
        self.client = self.app.test_client()

    def get(self, route: str):
        resp = self.client.get(route)
        return resp.status_code, resp.headers.get("Content-Type", ""), resp.get_data(as_text=True)

    def test_five_routes_render_html_200(self):
        for route in ROUTES:
            status, content_type, body = self.get(route)
            self.assertEqual(status, 200, route)
            self.assertIn("text/html", content_type, route)
            self.assertIn("数据来源", body, route)
            self.assertIn("文件更新时间", body, route)
            self.assertNotIn("Traceback", body, route)

    def test_overview_shows_counts_and_license_summary(self):
        _, _, body = self.get("/dash/")
        self.assertIn("机会评分行", body)
        self.assertIn("货源条目", body)
        self.assertIn("可商用", body)
        self.assertIn("需授权", body)
        self.assertIn("机会 Top 5", body)

    def test_collect_shows_xianyu_and_file_status(self):
        _, _, body = self.get("/dash/collect")
        self.assertIn("闲鱼采集", body)
        self.assertIn("文件状态", body)
        self.assertIn("已读取", body)

    def test_opportunities_shows_model_rows_and_links(self):
        # Keep the route test independent from live scoring data: the fixture
        # is synthetic and does not assert the current production top item.
        fixture = ROOT / "tests" / "dash" / "_fixtures" / "opportunities_data"
        app = create_app({"db_path": str(pathlib.Path(self.tmp) / "fixture.db"),
                          "DASH_DATA_ROOT": str(fixture)})
        body = app.test_client().get("/dash/opportunities").get_data(as_text=True)
        fixture_scores = fixture / "docs/validation/money-project/scoring/scores.csv"
        with fixture_scores.open(encoding="utf-8", newline="") as fh:
            expected_score = list(csv.DictReader(fh))[0]["total_score"]
        self.assertIn("机会榜", body)
        self.assertIn("fixture opportunity", body)
        self.assertIn(expected_score, body)
        self.assertIn("https://example.test/fixture", body)

    def test_sources_shows_license_rows_and_prices(self):
        _, _, body = self.get("/dash/sources")
        self.assertIn("gh-01", body)
        self.assertIn("需授权", body)
        self.assertIn("price_signals.csv", body)
        self.assertIn("¥1.88", body)
        self.assertIn("价格口径", body)
        self.assertIn("all_20_fallback", body)
        self.assertIn("category_filtered", body)
        self.assertIn("置信度", body)
        self.assertIn("已排除", body)
        self.assertIn("全量回退（20 条）", body)

    def test_daily_is_read_only_summary(self):
        _, _, body = self.get("/dash/daily")
        self.assertIn("每日摘要", body)
        self.assertIn("今日重点", body)
        self.assertIn("不写库", body)

    def test_api_health_unchanged(self):
        payload = self.client.get("/api/health").get_json()
        self.assertEqual(sorted(payload.keys()), ["ok", "schema_version", "time", "version"])

    def test_missing_data_root_degrades_friendly(self):
        empty = pathlib.Path(tempfile.mkdtemp(prefix="dash_missing_"))
        app = create_app({"db_path": str(empty / "app.db"), "DASH_DATA_ROOT": str(empty / "data")})
        client = app.test_client()
        for route in ROUTES:
            resp = client.get(route)
            body = resp.get_data(as_text=True)
            self.assertEqual(resp.status_code, 200, route)
            self.assertTrue("文件缺失" in body or "暂无数据" in body, route)
            self.assertNotIn("Traceback", body, route)

    def test_bad_jsonl_line_is_counted_and_skipped(self):
        root = pathlib.Path(tempfile.mkdtemp(prefix="dash_bad_"))
        data_dir = root / "tools" / "platform-login" / "data"
        data_dir.mkdir(parents=True)
        (data_dir / "xianyu_items.jsonl").write_text(
            json.dumps({"title": "ok", "price": "¥1"}, ensure_ascii=False) + "\n{bad json}\n",
            encoding="utf-8",
        )
        data = load_dashboard_data(root)
        self.assertEqual(data["datasets"]["xianyu"]["count"], 1)
        self.assertEqual(data["datasets"]["xianyu"]["bad_lines"], 1)
        self.assertTrue(any("坏 JSONL" in warning for warning in data["warnings"]))
        self.assertEqual(data["scores"], [])
        self.assertFalse(data["datasets"]["scores"]["exists"])


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
