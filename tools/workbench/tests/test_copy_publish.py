"""B13 测试：文案版本历史/回滚、导出去重、发布回填与变更提示。"""

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

COLS = ["rank", "item_id", "platform", "title", "url", "author", "published_at", "total_score", "demand_raw",
        "demand_norm", "sellability_norm", "sellability_reason", "margin_low", "margin_high", "margin_mid",
        "margin_assumption", "cost_input", "cost_note", "missing_metrics", "source", "raw_ref"]
EVIDENCE = {
    "selected_supply_id": "self:pp-v1", "supply_version": "v1",
    "supply_license_commercial": "yes", "supply_license_redistribute": "yes", "supply_license_resell": "yes",
    "sample_status": "verified", "sample_note": "自测通过", "cost_minor": "300", "cost_known": "yes",
    "platform_evidence": "demo://b13/test", "copy_status": "final", "copy_version": "copy-v1",
    "selling_points": "卖点A\n卖点B", "price_minor": "1990", "delivery_note": "站内文件",
    "aftersales_note": "售后未定", "faq_json": json.dumps([{"q": "要装软件吗", "a": "不用"}], ensure_ascii=False),
}


class CopyPublishTests(unittest.TestCase):
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
        self.wid = self._create()

    # ---------- helpers ----------
    def token(self) -> str:
        self.client.get("/worksheet")
        with self.client.session_transaction() as s:
            return s["csrf"]

    def _create(self) -> str:
        resp = self.client.post("/worksheet/new", data={
            "csrf": self.token(), "self_made": "1", "submit_key": "b13-1",
            "name": "自制提示词包", "use_case": "会议纪要", "deliverable": "纯文本 .md",
            "target_platform": "xianyu", "fmt": "md", "language": "中文", "version": "v1"})
        return resp.headers["Location"].rsplit("/", 1)[-1].split("?")[0]

    def rec(self) -> dict:
        conn = wf.connect()
        try:
            return wf.get(conn, self.wid)
        finally:
            conn.close()

    def evidence(self, payload: dict) -> int:
        rev = self.rec()["revision"]
        return self.client.post(f"/worksheet/{self.wid}/evidence",
                                data={"csrf": self.token(), "revision": str(rev), **payload}).status_code

    def versions(self) -> list[dict]:
        conn = wf.connect()
        try:
            return rd.list_copy_versions(conn, self.wid)
        finally:
            conn.close()

    # ---------- 版本历史 ----------
    def test_copy_version_created_and_deduplicated(self):
        self.assertEqual(self.evidence(EVIDENCE), 303)
        v1 = self.versions()
        self.assertEqual([v["version_no"] for v in v1], [1])
        # 同内容再保存（只改成本，不动文案字段）→ 不新增版本
        self.assertEqual(self.evidence({"cost_minor": "400"}), 303)
        self.assertEqual(len(self.versions()), 1, "同内容不应新增版本")
        # 改文案 → 新版本
        self.assertEqual(self.evidence({"selling_points": "卖点A\n卖点B\n卖点C"}), 303)
        versions = self.versions()
        self.assertEqual([v["version_no"] for v in versions], [2, 1])
        self.assertNotEqual(versions[0]["content_hash"], versions[1]["content_hash"])

    def test_rollback_creates_new_version(self):
        self.assertEqual(self.evidence(EVIDENCE), 303)
        self.assertEqual(self.evidence({"selling_points": "改过的卖点"}), 303)
        rev = self.rec()["revision"]
        before = len(self.versions())
        resp = self.client.post(f"/worksheet/{self.wid}/copy/rollback",
                                data={"csrf": self.token(), "revision": str(rev), "version_no": "1"})
        self.assertEqual(resp.status_code, 303)
        after = self.versions()
        self.assertEqual(len(after), before + 1)
        self.assertEqual(after[0]["created_by"], "rollback:v1")
        self.assertIn("卖点A", self.rec()["selling_points"])
        self.assertEqual(len(after), 3, "历史不删除，回滚生成新版本")

    def test_rollback_validation(self):
        self.assertEqual(self.evidence(EVIDENCE), 303)
        rev = self.rec()["revision"]
        bad_rev = self.client.post(f"/worksheet/{self.wid}/copy/rollback",
                                   data={"csrf": self.token(), "revision": "999", "version_no": "1"})
        self.assertEqual(bad_rev.status_code, 409)
        missing = self.client.post(f"/worksheet/{self.wid}/copy/rollback",
                                   data={"csrf": self.token(), "revision": str(rev), "version_no": "99"})
        self.assertEqual(missing.status_code, 404)
        no_csrf = self.client.post(f"/worksheet/{self.wid}/copy/rollback",
                                   data={"csrf": "x", "revision": str(rev), "version_no": "1"})
        self.assertEqual(no_csrf.status_code, 403)

    # ---------- 导出幂等 ----------
    def test_export_record_dedup(self):
        self.assertEqual(self.evidence(EVIDENCE), 303)
        first = self.client.post(f"/worksheet/{self.wid}/export/record",
                                 data={"csrf": self.token(), "format": "md"})
        self.assertEqual(first.status_code, 200)
        self.assertEqual(first.headers.get("X-WB-Deduplicated"), "false")
        conn = wf.connect()
        try:
            rows1 = conn.execute("SELECT COUNT(*) FROM workorder_export").fetchone()[0]
        finally:
            conn.close()
        second = self.client.post(f"/worksheet/{self.wid}/export/record",
                                  data={"csrf": self.token(), "format": "md"})
        self.assertEqual(second.status_code, 200)
        self.assertEqual(second.headers.get("X-WB-Deduplicated"), "true")
        conn = wf.connect()
        try:
            rows2 = conn.execute("SELECT COUNT(*) FROM workorder_export").fetchone()[0]
        finally:
            conn.close()
        self.assertEqual(rows1, rows2, "同版本戳重复记录不新增行")
        # 改文案版本后新戳 → 新增
        self.assertEqual(self.evidence({"copy_version": "copy-v2"}), 303)
        third = self.client.post(f"/worksheet/{self.wid}/export/record",
                                 data={"csrf": self.token(), "format": "md"})
        self.assertEqual(third.headers.get("X-WB-Deduplicated"), "false")
        conn = wf.connect()
        try:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM workorder_export").fetchone()[0], rows1 + 1)
        finally:
            conn.close()

    # ---------- 唯一约束 + 并发同戳 ----------
    def test_export_dedupe_unique_index_and_concurrency(self):
        """两连接并发写同戳：唯一索引兜底，最终仅 1 行，另一方返回 deduplicated=true。"""
        self.assertEqual(self.evidence(EVIDENCE), 303)
        conns = [wf.connect(), wf.connect()]
        try:
            conn = conns[0]
            record = wf.get(conn, self.wid)
            payload = rd.build_export(record)
            results = []
            for c in conns:
                results.append(rd.record_export(c, record, payload, "md"))
        finally:
            for c in conns:
                c.close()
        conn = wf.connect()
        try:
            rows = conn.execute("SELECT COUNT(*) FROM workorder_export WHERE workorder_id=?",
                                (self.wid,)).fetchone()[0]
            idx = [r[1] for r in conn.execute("PRAGMA index_list(workorder_export)").fetchall()]
            uniq = conn.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='index' "
                                "AND name='idx_export_dedupe_unique'").fetchone()[0]
        finally:
            conn.close()
        self.assertEqual(rows, 1, "同戳并发写入最终只能 1 行")
        self.assertGreaterEqual(sum(1 for r in results if r["deduplicated"]), 1,
                                "至少一方应返回 deduplicated=true")
        self.assertEqual(uniq, 1, "唯一索引应存在")
        self.assertNotIn("idx_export_dedupe", idx, "旧的非唯一索引应已删除")

    def test_unique_index_allows_multiple_nulls(self):
        """SQLite 唯一索引允许多个 NULL：历史行 dedupe_key 置 NULL 后不互相冲突。"""
        conn = wf.connect()
        try:
            conn.execute("INSERT INTO workorder_export (workorder_id, format, revision, stamp_hash, "
                         "content_sha256, created_utc, dedupe_key) VALUES (?,?,?,?,?,?,NULL)",
                         (self.wid, "md", 1, "h", "c", "2026-01-01T00:00:00Z"))
            conn.execute("INSERT INTO workorder_export (workorder_id, format, revision, stamp_hash, "
                         "content_sha256, created_utc, dedupe_key) VALUES (?,?,?,?,?,?,NULL)",
                         (self.wid, "md", 1, "h2", "c2", "2026-01-01T00:00:01Z"))
            conn.commit()
            n = conn.execute("SELECT COUNT(*) FROM workorder_export WHERE dedupe_key IS NULL").fetchone()[0]
        finally:
            conn.close()
        self.assertEqual(n, 2)

    # ---------- 发布回填 ----------
    def test_publish_change_banner_has_rerecord_button(self):
        self.assertEqual(self.evidence(EVIDENCE), 303)
        self.client.post(f"/worksheet/{self.wid}/export/record", data={"csrf": self.token(), "format": "md"})
        self.client.post(f"/worksheet/{self.wid}/publish", data={
            "csrf": self.token(), "status": "已发布", "published_url": "https://example.com/item/9",
            "sold_count": "0"})
        body = self.client.get(f"/worksheet/{self.wid}").get_data(as_text=True)
        self.assertIn("发布信息已变更", body)
        self.assertIn("重新记录本次导出", body)
        self.assertIn(f'/worksheet/{self.wid}/export/record', body)

    def test_worksheet_evidence_page_points_copy_versions_to_wizard(self):
        self.assertEqual(self.evidence(EVIDENCE), 303)
        body = self.client.get(f"/worksheet/{self.wid}").get_data(as_text=True)
        self.assertIn("本页保存不生成文案版本", body)
        self.assertIn(f'/copy?wo={self.wid}', body)

    def test_publish_validation(self):
        for payload in ({"status": "已上架"}, {"status": "已发布", "published_url": "ftp://x/y"},
                        {"status": "已发布", "published_url": "not-a-url"},
                        {"status": "已发布", "sold_count": "-1"},
                        {"status": "已发布", "sold_count": "abc"}):
            resp = self.client.post(f"/worksheet/{self.wid}/publish",
                                    data={"csrf": self.token(), **payload})
            self.assertEqual(resp.status_code, 400, payload)

    def test_publish_saved_and_change_hint(self):
        self.assertEqual(self.evidence(EVIDENCE), 303)
        ok = self.client.post(f"/worksheet/{self.wid}/publish", data={
            "csrf": self.token(), "status": "已发布", "published_url": "https://example.com/item/1",
            "published_at": "2026-10-23T14:30:00Z", "sold_count": "0", "platform_note": "审核通过"})
        self.assertEqual(ok.status_code, 303)
        conn = wf.connect()
        try:
            pub = rd.publish_info(conn, self.wid)
        finally:
            conn.close()
        self.assertEqual(pub["status"], "已发布")
        self.assertEqual(pub["published_url"], "https://example.com/item/1")
        # 未导出前：不提示
        conn = wf.connect()
        try:
            self.assertFalse(rd.publish_changed(pub, rd.last_export(conn, self.wid))["changed"])
        finally:
            conn.close()
        # 记录导出（时间晚于发布）→ 不提示
        self.client.post(f"/worksheet/{self.wid}/export/record", data={"csrf": self.token(), "format": "md"})
        # 再改发布信息（updated_at 变新）→ 提示重新核验
        self.client.post(f"/worksheet/{self.wid}/publish", data={
            "csrf": self.token(), "status": "已发布", "published_url": "https://example.com/item/2",
            "sold_count": "1"})
        conn = wf.connect()
        try:
            pub2 = rd.publish_info(conn, self.wid)
            last = rd.last_export(conn, self.wid)
        finally:
            conn.close()
        changed = rd.publish_changed(pub2, last)
        self.assertTrue(changed["changed"])
        self.assertIn("重新导出", changed["reason"])
        body = self.client.get(f"/worksheet/{self.wid}").get_data(as_text=True)
        self.assertIn("发布信息已变更", body)

    def test_publish_page_sections(self):
        body = self.client.get(f"/worksheet/{self.wid}").get_data(as_text=True)
        self.assertIn("发布回填", body)
        self.assertIn("文案版本历史", body)

    # ---------- GET 零写 ----------
    def test_detail_get_zero_write(self):
        import hashlib
        self.assertEqual(self.evidence(EVIDENCE), 303)
        before = hashlib.sha256(self.db.read_bytes()).hexdigest()
        for path in ("/worksheet", f"/worksheet/{self.wid}", f"/worksheet/{self.wid}/edit"):
            self.client.get(path)
        self.assertEqual(hashlib.sha256(self.db.read_bytes()).hexdigest(), before)


if __name__ == "__main__":
    unittest.main(verbosity=2)
