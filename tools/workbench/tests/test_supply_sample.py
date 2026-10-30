"""B16 测试：货源候选（增/改/停用/导入）、采用与替换、样品自检（路径/扩展名/失败不改状态）。"""

from __future__ import annotations

import json
import os
import pathlib
import sys
import tempfile
import unittest

WORKBENCH = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(WORKBENCH))

import samplecheck as sc  # noqa: E402
import supply as sup  # noqa: E402
import workflow as wf  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[2]
SAMPLE_XLSX = "docs/validation/product-workflow/b7/sample-study-planner-v1.xlsx"


class SupplySampleTests(unittest.TestCase):
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

    def _token(self) -> str:
        self.client.get("/worksheet")
        with self.client.session_transaction() as s:
            return s["csrf"]

    def _create(self) -> str:
        resp = self.client.post("/worksheet/new", data={
            "csrf": self._token(), "self_made": "1", "submit_key": "b16-1",
            "name": "自制提示词包", "use_case": "会议纪要", "deliverable": "纯文本 .md",
            "target_platform": "xianyu", "fmt": "md"})
        return resp.headers["Location"].rsplit("/", 1)[-1].split("?")[0]

    def _rec(self) -> dict:
        conn = wf.connect()
        try:
            return wf.get(conn, self.wid)
        finally:
            conn.close()

    def _add(self, **override) -> dict:
        conn = wf.connect()
        try:
            payload = {"provider": "自制素材", "source_url": "self:pp-v1", "kind": "同款",
                       "commercial": "yes", "redistribute": "yes", "resale": "no",
                       "license_note": "作者自持", "price_minor": "0"}
            payload.update(override)
            return sup.add(conn, self.wid, payload)
        finally:
            conn.close()

    # ---------- 候选 ----------
    def test_add_and_list(self):
        cand = self._add()
        self.assertRegex(cand["id"], r"^sc:[0-9a-f]{8}$")
        conn = wf.connect()
        try:
            items = sup.list_candidates(conn, self.wid)
        finally:
            conn.close()
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["provider"], "自制素材")
        self.assertEqual(items[0]["is_active"], 1)

    def test_update_and_validation(self):
        cand = self._add()
        conn = wf.connect()
        try:
            updated = sup.update_candidate(conn, self.wid, cand["id"], {"conclusion": "可用", "kind": "替代"})
            self.assertEqual(updated["conclusion"], "可用")
            self.assertEqual(updated["kind"], "替代")
            with self.assertRaises(wf.Reject):
                sup.update_candidate(conn, self.wid, cand["id"], {"kind": "乱填"})
            with self.assertRaises(wf.Reject):
                sup.add(conn, self.wid, {"provider": "", "kind": "同款"})
        finally:
            conn.close()

    def test_deactivate_requires_confirm_and_soft_deletes(self):
        cand = self._add()
        conn = wf.connect()
        try:
            with self.assertRaises(wf.Reject) as ctx:
                sup.deactivate(conn, self.wid, cand["id"], confirm="0")
            self.assertEqual(ctx.exception.status, 400)
            sup.deactivate(conn, self.wid, cand["id"], confirm="1")
            self.assertEqual(sup.list_candidates(conn, self.wid), [])
            all_rows = sup.list_candidates(conn, self.wid, active_only=False)
            self.assertEqual(len(all_rows), 1)
            self.assertEqual(all_rows[0]["is_active"], 0)
        finally:
            conn.close()

    def test_import_json_with_skipped(self):
        payload = json.dumps([
            {"provider": "A 站", "source_url": "https://a.example/x", "kind": "同款",
             "commercial": "yes", "redistribute": "yes", "resale": "yes", "price": {"amount": 990, "currency": "CNY"}},
            {"provider": "B 站", "kind": "未知类型"},
            {"provider": "C 站", "kind": "替代", "native_id": "x-1", "unknown_field": 1},
            "not-an-object",
        ], ensure_ascii=False)
        conn = wf.connect()
        try:
            result = sup.import_json(conn, self.wid, payload)
            count = len(sup.list_candidates(conn, self.wid))
        finally:
            conn.close()
        self.assertEqual(result["imported"], 2)
        self.assertGreaterEqual(len(result["skipped"]), 2)
        self.assertEqual(count, 2)

    # ---------- 采用/替换 ----------
    def test_select_and_replace_events(self):
        first = self._add()
        second = self._add(provider="第二来源", commercial="yes", redistribute="yes", resale="yes")
        conn = wf.connect()
        try:
            rec = sup.select_candidate(conn, self.wid, first["id"], revision=1)
        finally:
            conn.close()
        self.assertEqual(rec["selected_supply_id"], first["id"])
        self.assertTrue(rec["supply_version"])
        self.assertEqual(rec["supply_license_resell"], "no")
        conn = wf.connect()
        try:
            rec2 = sup.select_candidate(conn, self.wid, second["id"], revision=rec["revision"])
            actions = [r["action"] for r in conn.execute(
                "SELECT action FROM workorder_event WHERE workorder_id=? ORDER BY id", (self.wid,)).fetchall()]
        finally:
            conn.close()
        self.assertEqual(rec2["selected_supply_id"], second["id"])
        self.assertIn("supply_select", actions)
        self.assertIn("supply_replace", actions)

    def test_select_requires_valid_revision(self):
        cand = self._add()
        conn = wf.connect()
        try:
            with self.assertRaises(wf.Reject) as ctx:
                sup.select_candidate(conn, self.wid, cand["id"], revision="abc")
            self.assertEqual(ctx.exception.status, 400)
            with self.assertRaises(wf.Reject) as ctx2:
                sup.select_candidate(conn, self.wid, cand["id"], revision="99")
            self.assertEqual(ctx2.exception.status, 409)
        finally:
            conn.close()

    # ---------- 样品自检 ----------
    def test_sample_check_passes_on_b7_sample(self):
        resp = self.client.post(f"/worksheet/{self.wid}/sample/check",
                                data={"csrf": self._token(), "revision": "1", "path": SAMPLE_XLSX})
        self.assertEqual(resp.status_code, 303)
        rec = self._rec()
        self.assertEqual(rec["sample_status"], "verified")
        self.assertIn("sample-study-planner-v1.xlsx", rec["sample_ref"])
        self.assertIn("sheets", rec["sample_ref"])

    def test_sample_check_rejects_escapes_and_wrong_ext(self):
        for path in ("../etc/passwd", "C:\\Windows\\win.ini", "docs/../instance/app.db",
                     "docs/validation/product-workflow/b7/00_build.log", "docs/not-exists.xlsx"):
            resp = self.client.post(f"/worksheet/{self.wid}/sample/check",
                                    data={"csrf": self._token(), "revision": "1", "path": path})
            self.assertEqual(resp.status_code, 400, path)
        self.assertIsNone(self._rec()["sample_status"])
        self.assertEqual(self._rec()["revision"], 1, "失败不应改 revision")

    def test_sample_check_failure_keeps_state(self):
        # 先标记 verified 再换坏文件：坏路径不改状态
        self.client.post(f"/worksheet/{self.wid}/sample/check",
                         data={"csrf": self._token(), "revision": "1", "path": SAMPLE_XLSX})
        rec = self._rec()
        bad = self.client.post(f"/worksheet/{self.wid}/sample/check",
                               data={"csrf": self._token(), "revision": str(rec["revision"]),
                                     "path": "docs/not-a-file.xlsx"})
        self.assertEqual(bad.status_code, 400)
        self.assertEqual(self._rec()["sample_status"], "verified")
        self.assertEqual(self._rec()["sample_ref"], rec["sample_ref"])

    def test_md_file_check(self):
        target = ROOT / "docs" / "validation" / "product-workflow" / "b7" / "usage.md"
        result = sc.check_path(str(target.relative_to(ROOT)))
        self.assertTrue(result["ok"], result)
        self.assertTrue(any(c["item"] == "行数" for c in result["checks"]))

    def test_detail_page_sections(self):
        body = self.client.get(f"/worksheet/{self.wid}").get_data(as_text=True)
        self.assertIn("货源候选", body)
        self.assertIn("样品自检（本地文件）", body)


if __name__ == "__main__":
    unittest.main(verbosity=2)
