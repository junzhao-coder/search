"""S2-C page checks (stdlib unittest + Flask test_client, temp DB per test)."""

from __future__ import annotations

import json
import pathlib
import re
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from app import create_app  # noqa: E402
from app.storage.db import connect  # noqa: E402

TMP_ROOT = pathlib.Path(__file__).resolve().parent / "_tmp"

POSITIVE_CSV = (
    "title,data_origin,category,use_case,sale_price,platform_fee_bp,demand_source,demand_url,demand_excerpt\n"
    "示例-周会纪要模板包,synthetic,模板,小团队周会记录,9.90,500,xianyu,"
    "https://example.com/demand/ui-1,求一份能直接套用的周会纪要模板\n"
)

SCRIPT_TITLE_CSV = (
    "title,data_origin,sale_price,demand_source,demand_url,demand_excerpt\n"
    '"<script>alert(1)</script>",synthetic,9.90,xianyu,https://example.com/demand/ui-2,'
    "需要这份模板\n"
)

NULL_VS_ZERO_CSV = (
    "title,data_origin,sale_price,demand_source,demand_url,demand_excerpt\n"
    "示例-成本未知,synthetic,,xianyu,https://example.com/demand/ui-3,求模板甲\n"
    "示例-成本为零,synthetic,0,xianyu,https://example.com/demand/ui-4,求模板乙\n"
)


class PageTests(unittest.TestCase):
    def setUp(self):
        TMP_ROOT.mkdir(parents=True, exist_ok=True)
        self.tmp = tempfile.mkdtemp(prefix="ui_", dir=str(TMP_ROOT))
        self.db_path = str(pathlib.Path(self.tmp) / "app.db")
        self.app = create_app({"db_path": self.db_path})
        self.client = self.app.test_client()

    # ---------------- helpers
    def page(self, route: str) -> tuple[int, str]:
        resp = self.client.get(route)
        return resp.status_code, resp.get_data(as_text=True)

    def import_csv(self, content: str):
        return self.client.post(
            "/api/imports?format=csv&mode=atomic", data=content.encode("utf-8"), content_type="text/csv"
        )

    def candidate_ids(self) -> dict[str, str]:
        listing = self.client.get("/api/candidates?page_size=100").get_json()
        return {row["title"]: row["id"] for row in listing["items"]}

    # ---------------- 1) empty database
    def test_empty_database_pages_open_with_states_and_no_501(self):
        for route in ("/", "/import", "/ops"):
            status, body = self.page(route)
            self.assertEqual(status, 200, route)
            self.assertIn("text/html", self.client.get(route).headers.get("Content-Type", ""))

        _, home = self.page("/")
        # Three client-side states are declared (loading / empty / failure) instead of faking data.
        self.assertIn('id="pool-loading"', home)
        self.assertIn("加载中", home)
        self.assertIn('id="pool-empty"', home)
        self.assertIn("暂无候选", home)
        self.assertIn('id="pool-error"', home)
        self.assertIn("role=\"alert\"", home)

        _, ops = self.page("/ops")
        self.assertIn("暂无运行记录", ops)
        self.assertIn("待 S5", ops)
        self.assertIn("待 S6", ops)

        _, import_page = self.page("/import")
        self.assertIn("人工导入", import_page)
        self.assertIn("未保存", import_page)

    # ---------------- 2) import → list → detail
    def test_import_then_list_and_detail_render_key_fields(self):
        resp = self.import_csv(POSITIVE_CSV)
        self.assertEqual(resp.status_code, 201)
        payload = resp.get_json()
        self.assertEqual(payload["status"], "committed")

        candidate_id = self.candidate_ids()["示例-周会纪要模板包"]
        status, body = self.page(f"/opportunity/{candidate_id}")
        self.assertEqual(status, 200)
        self.assertIn("示例-周会纪要模板包", body)
        self.assertIn("求一份能直接套用的周会纪要模板", body)
        self.assertIn("四项入池门槛", body)
        self.assertIn("未核验", body)
        self.assertIn("成本与利润情景", body)
        self.assertIn("固定成本缺口", body)
        self.assertIn("暂无草稿", body)
        self.assertIn("暂无反馈记录", body)

        batch = self.client.get(f"/api/imports/{payload['batch_id']}")
        self.assertEqual(batch.status_code, 200)
        self.assertTrue(batch.get_json()["row_results"])

    # ---------------- 3) script title stays text (S2-33 evidence)
    def test_script_title_is_rendered_as_text_without_script_node(self):
        resp = self.import_csv(SCRIPT_TITLE_CSV)
        self.assertEqual(resp.status_code, 201)
        candidate_id = self.candidate_ids()["<script>alert(1)</script>"]
        status, body = self.page(f"/opportunity/{candidate_id}")
        self.assertEqual(status, 200)
        self.assertNotIn("<script>alert(1)</script>", body)
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", body)
        self.assertEqual(body.count("<script"), 1)  # only our own ui.js tag

    # ---------------- 4) unknown vs explicit zero
    def test_unknown_cost_shows_unknown_and_explicit_zero_shows_zero(self):
        self.assertEqual(self.import_csv(NULL_VS_ZERO_CSV).status_code, 201)
        ids = self.candidate_ids()
        _, unknown_page = self.page(f"/opportunity/{ids['示例-成本未知']}")
        self.assertIn("未知", unknown_page)
        self.assertIn("不输出净值", unknown_page)
        _, zero_page = self.page(f"/opportunity/{ids['示例-成本为零']}")
        self.assertIn("¥0.00", zero_page)
        self.assertIn("未知", zero_page)  # remaining roles stay unknown, not zero

    # ---------------- 5) missing candidate → honest 404 page
    def test_missing_candidate_renders_not_found_page(self):
        status, body = self.page("/opportunity/c_missing")
        self.assertEqual(status, 404)
        self.assertIn("未找到该候选", body)

    # ---------------- 6) no send / publish / purchase controls
    def test_pages_expose_no_send_publish_or_purchase_controls(self):
        verbs = ("发送", "发布", "采购", "付款", "下单", "上架")
        for route in ("/", "/import", "/ops"):
            _, body = self.page(route)
            for label in re.findall(r"<button[^>]*>(.*?)</button>", body, re.S):
                for verb in verbs:
                    self.assertNotIn(verb, label, f"{route} 出现动作按钮：{label}")
            self.assertNotIn("/send", body, route)
            self.assertNotIn("/publish", body, route)

    # ---------------- 7) pages are wired to the frozen API only
    def test_pages_use_frozen_api_endpoints_via_static_assets(self):
        _, home = self.page("/")
        self.assertIn("/static/ui.js", home)
        self.assertIn("/static/style.css", home)

        script_resp = self.client.get("/static/ui.js")
        self.assertEqual(script_resp.status_code, 200)
        script = script_resp.get_data(as_text=True)
        for endpoint in (
            "/api/candidates",
            "/api/sources",
            "/api/runs",
            "/api/imports",
            "/drafts",
            "/feedback",
            "/review-items",
        ):
            self.assertIn(endpoint, script, endpoint)
        self.assertNotIn(".innerHTML", script)  # user data only via textContent
        self.assertNotIn("insertAdjacentHTML", script)
        self.assertNotIn("|safe", script)

        css_resp = self.client.get("/static/style.css")
        self.assertEqual(css_resp.status_code, 200)
        self.assertIn("badge-status-pending", css_resp.get_data(as_text=True))


    # ---------------- 8) import page: confirm gated + three-state source display
    def test_import_page_gates_confirm_and_shows_source_three_states(self):
        conn = connect(self.db_path)
        try:
            for source_id, name, verified in (("s_no", "未核验来源", "no"), ("s_unknown", "待核实来源", "unknown")):
                conn.execute(
                    "INSERT INTO source(id,name,channel,access_mode,access_verified,enabled,created_at,updated_at)"
                    " VALUES (?,?,?,?,?,'1','2026-01-01T00:00:00Z','2026-01-01T00:00:00Z')",
                    (source_id, name, "xianyu", "manual_import", verified),
                )
        finally:
            conn.close()

        status, body = self.page("/import")
        self.assertEqual(status, 200)
        self.assertIn('<button type="button" id="import-commit" disabled>', body)  # preview-first gate
        self.assertIn('id="import-hint"', body)
        self.assertIn("<td>否</td>", body)      # access_verified='no'
        self.assertIn("<td>未知</td>", body)    # access_verified='unknown'
        # Only the four seeded 'yes' rows may render as 是: no/unknown never read as truthy.
        self.assertEqual(body.count("<td>是</td>"), 4)

    # ---------------- 9) home pagination controls
    def test_home_exposes_pagination_controls(self):
        _, body = self.page("/")
        for element_id in ("pool-prev", "pool-next", "pool-page"):
            self.assertIn(f'id="{element_id}"', body)

    # ---------------- 11) feedback region: stable table + addressable empty state
    def test_detail_feedback_region_keeps_stable_tbody_and_toggles_empty_state(self):
        self.assertEqual(self.import_csv(POSITIVE_CSV).status_code, 201)
        candidate_id = self.candidate_ids()["示例-周会纪要模板包"]

        status, empty_body = self.page(f"/opportunity/{candidate_id}")
        self.assertEqual(status, 200)
        self.assertIn('id="feedback-table"', empty_body)
        self.assertIn('id="feedback-rows"', empty_body)   # tbody 始终存在：首次反馈前也可寻址
        self.assertIn('id="feedback-empty"', empty_body)
        self.assertIn('<table class="table" id="feedback-table" hidden>', empty_body)
        self.assertIn('<p id="feedback-empty" class="state state-empty">', empty_body)  # 初始空态可见
        self.assertIn("暂无反馈记录", empty_body)

        sale = self.client.post(
            f"/api/candidates/{candidate_id}/feedback", json={"kind": "sale", "amount_minor": 990}
        )
        self.assertEqual(sale.status_code, 201, sale.get_data(as_text=True))

        _, filled_body = self.page(f"/opportunity/{candidate_id}")
        self.assertNotIn('<table class="table" id="feedback-table" hidden>', filled_body)   # 表格可见
        self.assertIn('<p id="feedback-empty" class="state state-empty" hidden>', filled_body)  # 空态撤销
        self.assertIn("<td>sale</td>", filled_body)
        self.assertIn("¥9.90", filled_body)

    # ---------------- 12) API contract untouched by page work
    def test_page_work_does_not_change_api_contract(self):
        health = self.client.get("/api/health").get_json()
        self.assertEqual(sorted(health.keys()), ["ok", "schema_version", "time", "version"])
        self.assertEqual(self.client.get("/api/candidates").get_json()["total"], 0)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
