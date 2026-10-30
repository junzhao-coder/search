"""B12 测试：自制商品 UI 建单、单号格式、证据录入、越级拒绝、GET 零写。"""

from __future__ import annotations

import csv
import hashlib
import json
import os
import pathlib
import re
import sys
import tempfile
import unittest

WORKBENCH = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(WORKBENCH))

import readiness as rd  # noqa: E402
import workflow as wf  # noqa: E402

COLS = ["rank", "item_id", "platform", "title", "url", "author", "published_at", "total_score", "demand_raw",
        "demand_norm", "sellability_norm", "sellability_reason", "margin_low", "margin_high", "margin_mid",
        "margin_assumption", "cost_input", "cost_note", "missing_metrics", "source", "raw_ref"]
EVIDENCE = {
    "selected_supply_id": "self:demo", "supply_version": "v1",
    "supply_license_commercial": "yes", "supply_license_redistribute": "yes", "supply_license_resell": "yes",
    "sample_status": "verified", "sample_note": "自测通过（结构自检，非真实打开）",
    "cost_minor": "500", "cost_known": "yes",
    "copy_status": "final", "copy_version": "copy-v1", "selling_points": "第一条卖点\n第二条卖点",
    "price_minor": "990", "delivery_note": "站内文件", "aftersales_note": "售后未定",
    "faq_json": json.dumps([{"q": "需要什么软件", "a": "任意文本编辑器"}], ensure_ascii=False),
}


class SelfMadeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tmp = tempfile.TemporaryDirectory()
        root = pathlib.Path(cls.tmp.name)
        with (root / "scores.csv").open("w", encoding="utf-8", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=COLS)
            w.writeheader()
            w.writerow({c: ("1" if c == "rank" else "x:p" if c == "item_id" else "notion notes" if c == "title" else "")
                        for c in COLS})
        (root / "top10.csv").write_text("rank,opportunity_id,reference_max\n1,x:p,699\n", encoding="utf-8")
        cls.db = root / "w.db"
        os.environ["WORKBENCH_WORKFLOW_DB"] = str(cls.db)
        os.environ["WORKBENCH_SECRET_FILE"] = str(root / "s")
        os.environ["WORKBENCH_SOURCE_FIXTURE"] = f"{root}/scores.csv,{root}/top10.csv"
        import app as wb
        cls.wb = wb

    @classmethod
    def tearDownClass(cls) -> None:
        for k in ("WORKBENCH_WORKFLOW_DB", "WORKBENCH_SECRET_FILE", "WORKBENCH_SOURCE_FIXTURE"):
            os.environ.pop(k, None)
        cls.tmp.cleanup()

    def setUp(self) -> None:
        if self.db.exists():
            self.db.unlink()
        self.app = self.wb.create_app()
        self.app.testing = True
        self.client = self.app.test_client()

    # ---------- helpers ----------
    def token(self) -> str:
        self.client.get("/worksheet")
        with self.client.session_transaction() as s:
            return s["csrf"]

    def create(self, *, key="sk-1", **override):
        data = {"csrf": self.token(), "self_made": "1", "submit_key": key,
                "name": "自制提示词包", "use_case": "会议纪要", "deliverable": "纯文本 .md（10 条）",
                "target_platform": "xianyu", "fmt": "md", "language": "中文", "version": "v1"}
        data.update(override)
        return self.client.post("/worksheet/new", data=data)

    def wid(self) -> str:
        conn = wf.connect()
        try:
            return wf.list_all(conn)[0]["workorder_id"]
        finally:
            conn.close()

    # ---------- 建单 ----------
    def test_new_form_page(self):
        html = self.client.get("/worksheet/new").get_data(as_text=True)
        self.assertIn("新建自制商品", html)
        for name in ("name", "use_case", "deliverable", "target_platform", "submit_key", "self_made"):
            self.assertIn(f'name="{name}"', html, name)

    def test_create_self_made_and_id_format(self):
        resp = self.create()
        self.assertEqual(resp.status_code, 303)
        wid = self.wid()
        self.assertRegex(wid, r"^wo:\d{8}-[0-9a-f]{8}$")
        conn = wf.connect()
        try:
            rec = wf.get(conn, wid)
        finally:
            conn.close()
        self.assertEqual(rec["source_group"], "自制商品")
        self.assertTrue(rec["source_item_id"].startswith("self:"))
        self.assertTrue(rec["snapshot"]["self_made"])
        self.assertEqual(rec["snapshot"]["note"], "自制商品，无采集来源")

    def test_required_missing_rejected(self):
        for field in ("name", "use_case", "deliverable"):
            resp = self.create(**{field: ""})
            self.assertEqual(resp.status_code, 400, resp.get_data(as_text=True)[:200])

    def test_idempotent(self):
        self.create(key="dup")
        resp = self.create(key="dup")
        self.assertEqual(resp.status_code, 303)
        self.assertIn("deduplicated=1", resp.headers["Location"])
        conn = wf.connect()
        try:
            self.assertEqual(len(wf.list_all(conn)), 1)
        finally:
            conn.close()

    def test_self_prefix_enforced(self):
        resp = self.create(item_id="x:not-self")
        self.assertEqual(resp.status_code, 400)
        self.assertIn("source_invalid", self.client.get("/worksheet/new").get_data(as_text=True) + resp.get_data(as_text=True))

    # ---------- 证据 ----------
    def test_seven_evidence_via_ui(self):
        self.create()
        wid = self.wid()
        conn = wf.connect()
        try:
            rev = wf.get(conn, wid)["revision"]
        finally:
            conn.close()
        resp = self.client.post(f"/worksheet/{wid}/evidence",
                                data={"csrf": self.token(), "revision": str(rev), **EVIDENCE})
        self.assertEqual(resp.status_code, 303)
        conn = wf.connect()
        try:
            rec = wf.get(conn, wid)
        finally:
            conn.close()
        state = rd.readiness(rec)
        passed = {c["key"] for c in state["checks"] if c["ok"]}
        self.assertEqual(passed, {"specs", "supply", "license", "sample", "cost", "copy"})
        self.assertEqual([c["key"] for c in state["checks"] if not c["ok"]], ["platform"])
        self.assertEqual(rec["sample_ref"], EVIDENCE["sample_note"])   # 别名写入
        self.assertEqual(self.client.get(f"/worksheet/{wid}/export?format=md").status_code, 409)

    def test_revision_conflict_and_rollback(self):
        self.create()
        wid = self.wid()
        bad = self.client.post(f"/worksheet/{wid}/evidence",
                               data={"csrf": self.token(), "revision": "999", "cost_minor": "100"})
        self.assertEqual(bad.status_code, 409)
        invalid = self.client.post(f"/worksheet/{wid}/evidence",
                                   data={"csrf": self.token(), "revision": "1", "cost_minor": "abc"})
        self.assertEqual(invalid.status_code, 400)
        conn = wf.connect()
        try:
            self.assertEqual(wf.get(conn, wid)["revision"], 1)
        finally:
            conn.close()

    def test_forged_ready_403(self):
        self.create()
        wid = self.wid()
        for payload in ({"status": "ready"}, {"ready": "1"}, {"gate_cost": "verified"}):
            resp = self.client.post(f"/worksheet/{wid}/evidence",
                                    data={"csrf": self.token(), "revision": "1", **payload})
            self.assertEqual(resp.status_code, 403, payload)

    def test_demo_platform_enables_export(self):
        self.create()
        wid = self.wid()
        data = {**EVIDENCE, "platform_evidence": "demo://b12/walkthrough-only"}
        resp = self.client.post(f"/worksheet/{wid}/evidence",
                                data={"csrf": self.token(), "revision": "1", **data})
        self.assertEqual(resp.status_code, 303)
        out = self.client.get(f"/worksheet/{wid}/export?format=json")
        self.assertEqual(out.status_code, 200)
        payload = json.loads(out.get_data(as_text=True))
        self.assertEqual(set(payload["buyer_visible_fields"]),
                         {"title", "selling_points", "contents", "format", "price", "delivery", "aftersales", "faq"})
        self.assertNotIn("cost", json.dumps(payload, ensure_ascii=False).lower().split("buyer_visible_fields")[0])

    def test_get_zero_write(self):
        self.create()
        wid = self.wid()
        before = hashlib.sha256(self.db.read_bytes()).hexdigest()
        for path in ("/worksheet", f"/worksheet/{wid}", f"/worksheet/{wid}/edit", "/worksheet/new"):
            self.client.get(path)
        self.assertEqual(hashlib.sha256(self.db.read_bytes()).hexdigest(), before)


if __name__ == "__main__":
    unittest.main(verbosity=2)
