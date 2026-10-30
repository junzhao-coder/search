"""B3 就绪检查与导出测试（隔离库 + 隔离来源 fixture）：全缺/部分缺/齐全/伪造 + 版本戳失效。"""

from __future__ import annotations

import csv
import json
import os
import pathlib
import sys
import tempfile
import unittest

WORKBENCH = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(WORKBENCH))

import readiness as rd  # noqa: E402
import workflow as wf  # noqa: E402

SCORE_COLS = ["rank", "item_id", "platform", "title", "url", "author", "published_at", "total_score",
              "demand_raw", "demand_norm", "sellability_norm", "sellability_reason", "margin_low", "margin_high",
              "margin_mid", "margin_assumption", "cost_input", "cost_note", "missing_metrics", "source", "raw_ref"]
ROW = {"rank": "1", "item_id": "x:prod", "platform": "x", "title": "notion study notes template",
       "url": "https://x/1", "author": "@a", "total_score": "0.8", "demand_raw": "1000", "demand_norm": "0.9",
       "sellability_norm": "0.9", "sellability_reason": "含明确售价", "margin_low": "0.7", "margin_high": "0.95",
       "margin_mid": "0.825", "margin_assumption": "假设", "cost_input": "missing", "missing_metrics": "",
       "source": "fixture", "raw_ref": "raw/x.jsonl"}

FULL_EVIDENCE = {
    "selected_supply_id": "sup-mit-1", "supply_version": "v1",
    "supply_license_commercial": "yes", "supply_license_redistribute": "yes", "supply_license_resell": "yes",
    "sample_status": "verified", "sample_ref": "sample://check-1",
    "cost_minor": "500", "cost_known": "yes", "platform_evidence": "policy://xianyu/digital-goods",
    "copy_status": "final", "copy_version": "copy-v1",
    "selling_points": "覆盖求职全流程\n可直接复制使用",
    "price_minor": "990", "delivery_note": "拍下后 1 小时内发网盘链接",
    "aftersales_note": "7 天内答疑，不含二次定制",
    "faq_json": json.dumps([{"q": "能否商用", "a": "许可见许可说明"}], ensure_ascii=False),
}


class ExportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tmp = tempfile.TemporaryDirectory()
        root = pathlib.Path(cls.tmp.name)
        scores = root / "scores.csv"
        with scores.open("w", encoding="utf-8", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=SCORE_COLS)
            writer.writeheader()
            writer.writerow({c: ROW.get(c, "") for c in SCORE_COLS})
        top10 = root / "top10.csv"
        top10.write_text("rank,opportunity_id,reference_max\n1,x:prod,699\n", encoding="utf-8")
        cls.db = root / "workflow.sqlite3"
        cls.secret = root / "secret"
        os.environ["WORKBENCH_WORKFLOW_DB"] = str(cls.db)
        os.environ["WORKBENCH_SECRET_FILE"] = str(cls.secret)
        os.environ["WORKBENCH_SOURCE_FIXTURE"] = f"{scores},{top10}"
        import app as wb
        cls.wb = wb

    @classmethod
    def tearDownClass(cls) -> None:
        for key in ("WORKBENCH_WORKFLOW_DB", "WORKBENCH_SECRET_FILE", "WORKBENCH_SOURCE_FIXTURE"):
            os.environ.pop(key, None)
        cls.tmp.cleanup()

    def setUp(self) -> None:
        if self.db.exists():
            self.db.unlink()
        self.app = self.wb.create_app()
        self.app.testing = True
        self.client = self.app.test_client()
        self.wid = self._create()

    # ---------- helpers ----------
    def _token(self) -> str:
        self.client.get("/worksheet")
        with self.client.session_transaction() as sess:
            return sess["csrf"]

    def _create(self) -> str:
        data = {"csrf": self._token(), "group": "Notion 学习笔记模板", "item_id": "x:prod", "submit_key": "b3",
                "name": "Notion 学习笔记工作单", "use_case": "学习笔记", "deliverable": "Notion 模板",
                "target_platform": "xianyu"}
        resp = self.client.post("/worksheet/new", data=data)
        self.assertEqual(resp.status_code, 303)
        return resp.headers["Location"].rsplit("/", 1)[-1].split("?")[0]

    def _record(self) -> dict:
        conn = wf.connect()
        try:
            return wf.get(conn, self.wid)
        finally:
            conn.close()

    def _evidence(self, payload: dict) -> int:
        rev = self._record()["revision"]
        resp = self.client.post(f"/worksheet/{self.wid}/evidence",
                                data={"csrf": self._token(), "revision": str(rev), **payload})
        return resp.status_code

    def _fill_all(self) -> None:
        self.assertEqual(self._evidence(FULL_EVIDENCE), 303)

    # ---------- ① 全缺：每项阻断 ----------
    def test_all_blocked_initially(self):
        state = rd.readiness(self._record())
        blocked = {c["key"] for c in state["checks"] if not c["ok"]}
        self.assertEqual(blocked, {"supply", "license", "sample", "cost", "platform", "copy"})
        self.assertFalse(state["overall_ready"])
        resp = self.client.get(f"/worksheet/{self.wid}/export?format=md")
        self.assertEqual(resp.status_code, 409)
        body = resp.get_data(as_text=True)
        for token in ("未选货源", "许可三档", "样品", "成本未知", "平台", "文案未定稿"):
            self.assertIn(token, body, token)

    def test_detail_page_shows_checks_and_disabled_buttons(self):
        body = self.client.get(f"/worksheet/{self.wid}").get_data(as_text=True)
        self.assertIn("上架准备检查（服务端判定）", body)
        self.assertIn("未就绪", body)
        self.assertIn('disabled aria-disabled="true"', body)
        self.assertNotIn("导出 Markdown（买家可见）", body)

    # ---------- ② 部分缺：逐项翻绿 ----------
    def test_partial_then_full(self):
        self.assertEqual(self._evidence({"selected_supply_id": "sup-1", "supply_version": "v1"}), 303)
        state = rd.readiness(self._record())
        self.assertTrue(next(c for c in state["checks"] if c["key"] == "supply")["ok"])
        self.assertFalse(state["overall_ready"])

        # 许可只给两档 yes，仍阻断
        self.assertEqual(self._evidence({"supply_license_commercial": "yes",
                                         "supply_license_redistribute": "yes"}), 303)
        state = rd.readiness(self._record())
        self.assertFalse(next(c for c in state["checks"] if c["key"] == "license")["ok"])

        self._fill_all()
        state = rd.readiness(self._record())
        self.assertTrue(state["overall_ready"], state["blockers"])

    # ---------- ③ 伪造就绪被拒 ----------
    def test_forged_ready_rejected_and_state_unchanged(self):
        before = self._record()
        for payload in ({"ready": "1"}, {"status": "ready"}, {"gate_cost": "verified"},
                        {"selected_supply_id": "x", "gate_demand": "verified"}):
            resp = self.client.post(f"/worksheet/{self.wid}/evidence",
                                    data={"csrf": self._token(), "revision": str(before["revision"]), **payload})
            self.assertEqual(resp.status_code, 403, payload)
        after = self._record()
        self.assertEqual(after["revision"], before["revision"])
        self.assertEqual(after["selected_supply_id"], before["selected_supply_id"])
        self.assertFalse(rd.readiness(after)["overall_ready"])

    # ---------- ④ 齐全后导出：白名单 + 无内部字段 ----------
    def test_export_md_and_json_whitelist(self):
        self._fill_all()
        md = self.client.get(f"/worksheet/{self.wid}/export?format=md")
        self.assertEqual(md.status_code, 200)
        self.assertIn("attachment", md.headers["Content-Disposition"])
        self.assertIn("X-WB-Revision", md.headers)
        text = md.get_data(as_text=True)
        for token in ("Notion 学习笔记工作单", "卖点", "内容清单", "格式与兼容", "价格规格", "交付与售后", "FAQ"):
            self.assertIn(token, text, token)
        for internal in ("采购成本", "利润", "打分", "毛利", "raw_ref", "snapshot", "cost_minor"):
            self.assertNotIn(internal, text, internal)

        js = self.client.get(f"/worksheet/{self.wid}/export?format=json")
        self.assertEqual(js.status_code, 200)
        payload = json.loads(js.get_data(as_text=True))
        self.assertEqual(set(payload["buyer_visible_fields"]),
                         {"title", "selling_points", "contents", "format", "price", "delivery", "aftersales", "faq"})
        for internal in ("cost_minor", "supply_note", "raw_ref", "snapshot", "total_score"):
            self.assertNotIn(internal, json.dumps(payload, ensure_ascii=False), internal)
        self.assertEqual(payload["version_stamp"]["revision"], self._record()["revision"])

    def test_export_blocked_when_not_ready_then_ok(self):
        self.assertEqual(self.client.get(f"/worksheet/{self.wid}/export?format=json").status_code, 409)
        self._fill_all()
        self.assertEqual(self.client.get(f"/worksheet/{self.wid}/export?format=json").status_code, 200)

    # ---------- ⑤ 版本戳变化 → 旧导出失效（记录由 POST 产生） ----------
    def test_stamp_invalidates_old_export(self):
        self._fill_all()
        first = self.client.post(f"/worksheet/{self.wid}/export/record",
                                 data={"csrf": self._token(), "format": "json"})
        self.assertEqual(first.status_code, 200)
        self.assertEqual(first.headers.get("X-WB-Recorded"), "true")
        stamp1 = json.loads(first.get_data(as_text=True))["version_stamp"]

        # 改文案版本 → revision 变、stamp 变
        rec = self._record()
        status = self._evidence({"copy_version": "copy-v2"})
        self.assertEqual(status, 303)
        rec2 = self._record()
        self.assertGreater(rec2["revision"], rec["revision"])

        conn = wf.connect()
        try:
            last = rd.last_export(conn, self.wid)
        finally:
            conn.close()
        validity = rd.export_validity(rec2, last)
        self.assertTrue(validity["has_export"])
        self.assertFalse(validity["valid"])
        self.assertIn("失效", validity["reason"])
        self.assertNotEqual(stamp1["stamp_hash"], rd.version_stamp(rec2)["stamp_hash"])

        body = self.client.get(f"/worksheet/{self.wid}").get_data(as_text=True)
        self.assertIn("已失效", body)

        # 重新记录后恢复有效
        second = self.client.post(f"/worksheet/{self.wid}/export/record",
                                  data={"csrf": self._token(), "format": "json"})
        self.assertEqual(second.status_code, 200)
        conn = wf.connect()
        try:
            last2 = rd.last_export(conn, self.wid)
        finally:
            conn.close()
        self.assertTrue(rd.export_validity(self._record(), last2)["valid"])

    # ---------- ⑥ 证据保存的版本与校验 ----------
    def test_evidence_revision_and_validation(self):
        rec = self._record()
        bad = self.client.post(f"/worksheet/{self.wid}/evidence",
                               data={"csrf": self._token(), "revision": "1", "cost_minor": "abc"})
        self.assertEqual(bad.status_code, 400)
        stale = self.client.post(f"/worksheet/{self.wid}/evidence",
                                 data={"csrf": self._token(), "revision": "999", "cost_minor": "100"})
        self.assertEqual(stale.status_code, 409)
        self.assertEqual(self._record()["revision"], rec["revision"])

    # ---------- ⑦ GET 零写（导出前的页面） ----------
    def test_detail_get_zero_write(self):
        before = self._record()
        conn = wf.connect()
        try:
            events_before = conn.execute("SELECT COUNT(*) FROM workorder_event").fetchone()[0]
        finally:
            conn.close()
        self.client.get(f"/worksheet/{self.wid}")
        after = self._record()
        conn = wf.connect()
        try:
            events_after = conn.execute("SELECT COUNT(*) FROM workorder_event").fetchone()[0]
        finally:
            conn.close()
        self.assertEqual(before["revision"], after["revision"])
        self.assertEqual(events_before, events_after)


    # ---------- ⑧ 内部标记自检：业务拒绝 409 ----------
    def test_export_internal_marker_rejected(self):
        self._fill_all()
        # 让卖点里带内部标记「毛利」
        self.assertEqual(self._evidence({"selling_points": "覆盖求职全流程\n毛利很高（内部）"}), 303)
        rec = self._record()
        self.assertTrue(rd.readiness(rec)["overall_ready"])
        with self.assertRaises(wf.Reject) as ctx:
            rd.build_export(rec)
        self.assertEqual(ctx.exception.status, 409)
        self.assertEqual(ctx.exception.code, "export_internal_leak")
        resp = self.client.get(f"/worksheet/{self.wid}/export?format=json")
        self.assertEqual(resp.status_code, 409, "内部标记命中应为 409 业务拒绝，而不是 500")
        self.assertIn("export_internal_leak", resp.get_data(as_text=True))


class GetExportZeroWriteTests(ExportTests):
    """D1 修复：GET 导出零写（两态），导出记录只由 POST 产生。"""

    def _export_state(self):
        import hashlib
        sha = hashlib.sha256(self.db.read_bytes()).hexdigest()
        conn = wf.connect()
        try:
            rows = conn.execute("SELECT COUNT(*) FROM workorder_export").fetchone()[0]
        finally:
            conn.close()
        return sha, int(rows)

    def test_get_export_ready_does_not_write(self):
        self._fill_all()
        before = self._export_state()
        md = self.client.get(f"/worksheet/{self.wid}/export?format=md")
        self.assertEqual(md.status_code, 200)
        self.assertEqual(md.headers.get("X-WB-Recorded"), "false")
        js = self.client.get(f"/worksheet/{self.wid}/export?format=json")
        self.assertEqual(js.status_code, 200)
        self.assertEqual(self._export_state(), before, "GET 导出不得写库（行数与库 sha 均须不变）")

    def test_get_export_not_ready_409_does_not_write(self):
        before = self._export_state()
        resp = self.client.get(f"/worksheet/{self.wid}/export?format=md")
        self.assertEqual(resp.status_code, 409)
        self.assertEqual(self._export_state(), before, "未就绪 409 也不得写库")

    def test_post_record_requires_csrf_and_writes_one_row(self):
        self._fill_all()
        before = self._export_state()
        bad = self.client.post(f"/worksheet/{self.wid}/export/record",
                               data={"csrf": "wrong", "format": "md"})
        self.assertEqual(bad.status_code, 403)
        self.assertEqual(self._export_state(), before, "无 CSRF 不得写入")

        ok = self.client.post(f"/worksheet/{self.wid}/export/record",
                              data={"csrf": self._token(), "format": "md"})
        self.assertEqual(ok.status_code, 200)
        self.assertEqual(ok.headers.get("X-WB-Recorded"), "true")
        sha2, rows2 = self._export_state()
        self.assertEqual(rows2, before[1] + 1)
        self.assertNotEqual(sha2, before[0])

        # 相同版本戳再次记录 → 幂等（不新增行，头 deduplicated=true）
        again = self.client.post(f"/worksheet/{self.wid}/export/record",
                                 data={"csrf": self._token(), "format": "json"})
        self.assertEqual(again.status_code, 200)
        self.assertEqual(again.headers.get("X-WB-Deduplicated"), "true")
        _, rows3 = self._export_state()
        self.assertEqual(rows3, rows2, "同 (revision, copy_version, supply_id, supply_version) 不应新增行")

        # 改文案版本 → 新戳 → 新增 1 行
        self.assertEqual(self._evidence({"copy_version": "copy-v2"}), 303)
        changed = self.client.post(f"/worksheet/{self.wid}/export/record",
                                   data={"csrf": self._token(), "format": "json"})
        self.assertEqual(changed.status_code, 200)
        self.assertEqual(changed.headers.get("X-WB-Deduplicated"), "false")
        _, rows4 = self._export_state()
        self.assertEqual(rows4, rows3 + 1)

    def test_post_record_not_ready_409_and_no_write(self):
        before = self._export_state()
        resp = self.client.post(f"/worksheet/{self.wid}/export/record",
                                data={"csrf": self._token(), "format": "md"})
        self.assertEqual(resp.status_code, 409)
        self.assertEqual(self._export_state(), before)


if __name__ == "__main__":
    unittest.main(verbosity=2)
