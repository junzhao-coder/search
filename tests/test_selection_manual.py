"""V9-8b manual paste import + triage override (temp DB, workbench test client)."""

from __future__ import annotations

import importlib.util
import os
import pathlib
import sys
import tempfile
import unittest

from urllib.parse import unquote

from tools.selection import db, manual, triage

WORKBENCH = pathlib.Path(__file__).resolve().parents[1] / "tools" / "workbench"
ROOT = pathlib.Path(__file__).resolve().parents[1]


class ManualTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = pathlib.Path(self.tmp.name) / "s.sqlite3"
        self.conn = db.init_db(self.db)

    def tearDown(self):
        self.conn.close()
        self.tmp.cleanup()

    def test_native_id_parse_rules_and_derived(self):
        cases = [
            ("xiaohongshu", "https://www.xiaohongshu.com/explore/abc123", "abc123", "url"),
            ("xiaohongshu", "https://xhslink.com/x?note_id=note9", "note9", "url"),
            ("douyin", "https://www.douyin.com/video/7301234567890", "7301234567890", "url"),
            ("weibo", "https://weibo.com/u/1/status/abcdEFG", "abcdEFG", "url"),
            ("zhihu", "https://www.zhihu.com/question/123456", "123456", "url"),
            ("zhihu", "https://zhuanlan.zhihu.com/p/xyz789", "xyz789", "url"),
            ("tieba", "https://tieba.baidu.com/p/998877", "998877", "url"),
        ]
        for platform, url, expect, source in cases:
            got = manual.parse_native_id(platform, url)
            self.assertEqual(got, (expect, source), (platform, url))
        self.assertIsNone(manual.parse_native_id("weibo", "https://weibo.com/1"))
        sig = manual.build_signal("other", url="", text="今天的想法")
        self.assertEqual(sig["native_id_source"] if "native_id_source" in sig else "derived", "derived")
        sig2 = manual.build_signal("other", url="", text="今天的想法")
        self.assertEqual(sig["native_id"], sig2["native_id"])  # stable derived
        self.assertEqual(len(sig["native_id"]), 16)

    def test_manual_add_and_idempotent(self):
        a = manual.add(self.conn, "xiaohongshu", url="https://www.xiaohongshu.com/explore/abc123",
                       title="求推荐", text="有没有好的学习计划")
        self.assertEqual(a["outcome"], "new")
        self.assertEqual(a["native_id_source"], "url")
        b = manual.add(self.conn, "xiaohongshu", url="https://www.xiaohongshu.com/explore/abc123",
                       title="求推荐", text="有没有好的学习计划")
        self.assertEqual((b["outcome"], b["signal_id"]), ("duplicate", a["signal_id"]))
        row = self.conn.execute("SELECT origin_kind,collected_at_scope FROM signals WHERE id=?",
                                (a["signal_id"],)).fetchone()
        self.assertEqual((row["origin_kind"], row["collected_at_scope"]), ("imported", "batch"))
        tri = self.conn.execute("SELECT label FROM signal_triage WHERE signal_id=?",
                                (a["signal_id"],)).fetchone()
        self.assertEqual(tri["label"], "demand")


class ManualUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = pathlib.Path(cls.tmp.name)
        cls.old = {k: os.environ.get(k) for k in ("V9_SELECTION_DB", "WORKBENCH_WORKFLOW_DB")}
        os.environ["V9_SELECTION_DB"] = str(cls.root / "selection.sqlite3")
        os.environ["WORKBENCH_WORKFLOW_DB"] = str(cls.root / "workflow.sqlite3")
        os.environ["WORKBENCH_SECRET_FILE"] = str(cls.root / "secret")
        sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(WORKBENCH))
        spec = importlib.util.spec_from_file_location("wb_manual_app", WORKBENCH / "app.py")
        wb = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(wb)
        cls.wb = wb

    @classmethod
    def tearDownClass(cls):
        for k, old in cls.old.items():
            if old is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = old
        cls.tmp.cleanup()

    def setUp(self):
        self.app = self.wb.create_app()
        self.app.testing = True
        self.client = self.app.test_client()
        self.client.get("/leads")
        with self.client.session_transaction() as s:
            self.token = s["csrf"]

    def test_form_rendered_and_counts(self):
        r = self.client.get("/leads")
        text = r.get_data(as_text=True)
        self.assertIn('action="/leads/manual"', text)
        self.assertIn("人工导入≠自动采集，分开计数", text)

    def test_manual_post_success_and_counts(self):
        r = self.client.post("/leads/manual", data={
            "csrf": self.token, "platform": "zhihu",
            "url": "https://www.zhihu.com/question/999", "text": "求推荐一个 Notion 模板"})
        self.assertEqual(r.status_code, 303)
        self.assertIn("manual new", unquote(r.headers["Location"]))
        page = self.client.get("/leads")
        self.assertIn("999", page.get_data(as_text=True))
        self.assertIn("zhihu=1", page.get_data(as_text=True))

    def test_manual_missing_fields_303(self):
        r = self.client.post("/leads/manual", data={"csrf": self.token, "platform": "weibo"})
        self.assertEqual(r.status_code, 303)
        self.assertIn("err=", r.headers["Location"])

    def test_manual_csrf_missing_403(self):
        r = self.client.post("/leads/manual", data={"platform": "weibo", "text": "x"})
        self.assertEqual(r.status_code, 403)

    def test_manual_repeat_idempotent(self):
        data = {"csrf": self.token, "platform": "zhihu",
                "url": "https://www.zhihu.com/question/888", "text": "同样的问题"}
        first = self.client.post("/leads/manual", data=data)
        second = self.client.post("/leads/manual", data=data)
        self.assertIn("manual new", unquote(first.headers["Location"]))
        self.assertIn("manual duplicate", unquote(second.headers["Location"]))

    def test_triage_override_survives_refresh(self):
        add = self.client.post("/leads/manual", data={
            "csrf": self.token, "platform": "tieba",
            "url": "https://tieba.baidu.com/p/777", "text": "出模板 接单 优惠"})
        self.assertIn("manual new", unquote(add.headers["Location"]))
        page = self.client.get("/leads")
        self.assertIn('action="/leads/triage/', page.get_data(as_text=True))
        r = self.client.post("/leads/triage/1", data={"csrf": self.token, "label": "demand"})
        self.assertEqual(r.status_code, 303)
        self.assertIn("triage signal 1 -> demand", unquote(r.headers["Location"]))
        conn = db.init_db(pathlib.Path(os.environ["V9_SELECTION_DB"]))
        try:
            row = conn.execute("SELECT label,manual_override FROM signal_triage WHERE signal_id=1").fetchone()
            self.assertEqual((row["label"], row["manual_override"]), ("demand", "demand"))
            counts = triage.refresh(conn)  # store must preserve manual override
            row2 = conn.execute("SELECT label,manual_override FROM signal_triage WHERE signal_id=1").fetchone()
            self.assertEqual((row2["label"], row2["manual_override"]), ("demand", "demand"))
        finally:
            conn.close()


if __name__ == "__main__":
    unittest.main()
