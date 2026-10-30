"""B18：货源变更传导（D2/D3/D4）与控制组（未选中候选不受影响）+ 恢复路径。"""

from __future__ import annotations

import json
import os
import pathlib
import sys
import tempfile
import unittest

WORKBENCH = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(WORKBENCH))

import readiness as rd  # noqa: E402
import supply as sup  # noqa: E402
import workflow as wf  # noqa: E402

SAMPLE = "docs/validation/product-workflow/b7/sample-study-planner-v1.xlsx"
COPY = {"cost_minor": "300", "cost_known": "yes", "copy_status": "final", "copy_version": "copy-v1",
        "selling_points": "A", "price_minor": "1990", "delivery_note": "站内", "aftersales_note": "未定",
        "faq_json": "[]", "platform_evidence": "demo://b18/test"}


class BindingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tmp = tempfile.TemporaryDirectory()
        root = pathlib.Path(cls.tmp.name)
        cls.db = root / "w.db"
        os.environ["WORKBENCH_WORKFLOW_DB"] = str(cls.db)
        os.environ["WORKBENCH_SECRET_FILE"] = str(root / "s")
        import app as wb
        cls.wb = wb

    @classmethod
    def tearDownClass(cls) -> None:
        for k in ("WORKBENCH_WORKFLOW_DB", "WORKBENCH_SECRET_FILE"):
            os.environ.pop(k, None)
        cls.tmp.cleanup()

    def setUp(self) -> None:
        if self.db.exists():
            self.db.unlink()
        self.app = self.wb.create_app()
        self.app.testing = True
        self.client = self.app.test_client()
        self.wid = self._create()
        self.a = self._add("来源A", commercial="yes")
        self.b = self._add("来源B", commercial="yes")

    # ---------- helpers ----------
    def _token(self) -> str:
        self.client.get("/worksheet")
        with self.client.session_transaction() as s:
            return s["csrf"]

    def _create(self) -> str:
        resp = self.client.post("/worksheet/new", data={
            "csrf": self._token(), "self_made": "1", "submit_key": "b18-1",
            "name": "B18 传导测试", "use_case": "测试", "deliverable": "文本", "target_platform": "xianyu"})
        return resp.headers["Location"].rsplit("/", 1)[-1].split("?")[0]

    def _add(self, provider: str, **override) -> dict:
        conn = wf.connect()
        try:
            payload = {"provider": provider, "source_url": "self:x", "kind": "同款", "commercial": "yes",
                       "redistribute": "yes", "resale": "yes", "license_note": "自持"}
            payload.update(override)
            return sup.add(conn, self.wid, payload)
        finally:
            conn.close()

    def _rec(self) -> dict:
        conn = wf.connect()
        try:
            return wf.get(conn, self.wid)
        finally:
            conn.close()

    def _ready(self) -> dict:
        return rd.readiness(self._rec())

    def _make_ready(self) -> None:
        """采用 A → 样品自检 → 填成本/文案/平台 → 期望 7/7。"""
        conn = wf.connect()
        try:
            sup.select_candidate(conn, self.wid, self.a["id"], revision=self._rec()["revision"])
        finally:
            conn.close()
        self.client.post(f"/worksheet/{self.wid}/sample/check",
                         data={"csrf": self._token(), "revision": str(self._rec()["revision"]), "path": SAMPLE})
        self.client.post(f"/worksheet/{self.wid}/evidence",
                         data={"csrf": self._token(), "revision": str(self._rec()["revision"]), **COPY})
        self.assertTrue(self._ready()["overall_ready"], self._ready()["blockers"])

    def _update_candidate(self, cid: str, payload: dict) -> None:
        conn = wf.connect()
        try:
            sup.update_candidate(conn, self.wid, cid, payload)
        finally:
            conn.close()

    def _export_status(self) -> int:
        return self.client.get(f"/worksheet/{self.wid}/export?format=json").status_code

    # ---------- D2：改已选候选许可 ----------
    def test_d2_license_change_syncs_and_invalidates(self):
        self._make_ready()
        first_export = self.client.post(f"/worksheet/{self.wid}/export/record",
                                        data={"csrf": self._token(), "format": "md"})
        self.assertEqual(first_export.status_code, 200)
        self.assertEqual(self._export_status(), 200)

        self._update_candidate(self.a["id"], {"resale": "no"})
        rec = self._rec()
        self.assertEqual(rec["supply_license_resell"], "no")
        state = self._ready()
        self.assertFalse(next(c for c in state["checks"] if c["key"] == "license")["ok"])
        self.assertFalse(next(c for c in state["checks"] if c["key"] == "sample")["ok"])
        self.assertFalse(next(c for c in state["checks"] if c["key"] == "cost")["ok"])
        self.assertFalse(state["overall_ready"])
        self.assertEqual(self._export_status(), 409)
        conn = wf.connect()
        try:
            last = rd.last_export(conn, self.wid)
        finally:
            conn.close()
        self.assertFalse(rd.export_validity(rec, last)["valid"], "旧导出应失效")

    # ---------- D3：停用已选候选 ----------
    def test_d3_deactivate_selected_clears_supply(self):
        self._make_ready()
        conn = wf.connect()
        try:
            sup.deactivate(conn, self.wid, self.a["id"], confirm="1")
        finally:
            conn.close()
        rec = self._rec()
        self.assertIsNone(rec["selected_supply_id"])
        self.assertEqual(rec["supply_license_commercial"], "unknown")
        state = self._ready()
        self.assertFalse(next(c for c in state["checks"] if c["key"] == "supply")["ok"])
        self.assertFalse(state["overall_ready"])
        self.assertEqual(self._export_status(), 409)

    # ---------- D4：换源 ----------
    def test_d4_replace_requires_new_sample_and_cost(self):
        self._make_ready()
        before = self._rec()
        self.assertIsNotNone(before["sample_ref"])
        conn = wf.connect()
        try:
            sup.select_candidate(conn, self.wid, self.b["id"], revision=before["revision"])
        finally:
            conn.close()
        rec = self._rec()
        self.assertEqual(rec["selected_supply_id"], self.b["id"])
        self.assertIsNone(rec["sample_ref"])
        self.assertIsNone(rec["sample_status"])
        self.assertIsNone(rec["cost_minor"])
        self.assertEqual(rec["cost_known"], "no")
        state = self._ready()
        self.assertFalse(state["overall_ready"], "换源后不得仍 7/7")
        for key in ("sample", "cost"):
            self.assertFalse(next(c for c in state["checks"] if c["key"] == key)["ok"], key)
        self.assertEqual(self._export_status(), 409)

    # ---------- 控制组：改/停未选中候选 ----------
    def test_control_unselected_candidate_changes_nothing(self):
        self._make_ready()
        before = self._rec()
        self._update_candidate(self.b["id"], {"resale": "no"})
        self.assertEqual(self._rec(), before)
        conn = wf.connect()
        try:
            sup.deactivate(conn, self.wid, self.b["id"], confirm="1")
        finally:
            conn.close()
        self.assertEqual(self._rec(), before)
        self.assertTrue(self._ready()["overall_ready"])
        self.assertEqual(self._export_status(), 200)

    # ---------- 恢复路径 ----------
    def test_recovery_after_invalidation(self):
        self._make_ready()
        self._update_candidate(self.a["id"], {"commercial": "yes"})     # 变更 → 失效
        self.assertFalse(self._ready()["overall_ready"])
        self.client.post(f"/worksheet/{self.wid}/sample/check",
                         data={"csrf": self._token(), "revision": str(self._rec()["revision"]), "path": SAMPLE})
        self.client.post(f"/worksheet/{self.wid}/evidence",
                         data={"csrf": self._token(), "revision": str(self._rec()["revision"]),
                               "cost_minor": "300", "cost_known": "yes"})
        self.assertTrue(self._ready()["overall_ready"], self._ready()["blockers"])

    # ---------- D1：旧区块文案 ----------
    def test_d1_legacy_block_labelled_as_snapshot(self):
        body = self.client.get(f"/worksheet/{self.wid}").get_data(as_text=True)
        self.assertIn("来源快照与历史阶段（非当前状态）", body)
        self.assertIn("不代表当前状态", body)
        self.assertIn("上架准备检查（服务端判定）", body)


if __name__ == "__main__":
    unittest.main(verbosity=2)
