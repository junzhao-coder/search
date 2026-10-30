"""V9-4 /leads page + controlled round actions (temp selection DB, no network)."""

from __future__ import annotations

import importlib.util
import json
import os
import pathlib
import sys
import tempfile
import unittest

WORKBENCH = pathlib.Path(__file__).resolve().parents[1] / "tools" / "workbench"
ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(WORKBENCH))


class LeadsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = pathlib.Path(cls.tmp.name)
        cls.old_db = os.environ.get("V9_SELECTION_DB")
        cls.old_wf = os.environ.get("WORKBENCH_WORKFLOW_DB")
        os.environ["V9_SELECTION_DB"] = str(cls.root / "selection.sqlite3")
        os.environ["WORKBENCH_WORKFLOW_DB"] = str(cls.root / "workflow.sqlite3")
        os.environ["WORKBENCH_SECRET_FILE"] = str(cls.root / "secret")
        spec = importlib.util.spec_from_file_location("workbench_leads_app", WORKBENCH / "app.py")
        wb = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(wb)
        cls.wb = wb

    @classmethod
    def tearDownClass(cls):
        for key, old in (("V9_SELECTION_DB", cls.old_db),
                         ("WORKBENCH_WORKFLOW_DB", cls.old_wf)):
            if old is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = old
        cls.tmp.cleanup()

    def setUp(self):
        db = pathlib.Path(os.environ["V9_SELECTION_DB"])
        if db.exists():
            db.unlink()
        self.app = self.wb.create_app()
        self.app.testing = True
        self.client = self.app.test_client()

    def token(self):
        self.client.get("/leads")
        with self.client.session_transaction() as s:
            return s["csrf"]

    def test_get_empty_state(self):
        r = self.client.get("/leads")
        self.assertEqual(r.status_code, 200)
        text = r.get_data(as_text=True)
        self.assertIn("规则推断，不是市场结论", text)
        self.assertIn("库不存在", text)
        self.assertIn('action="/leads/round"', text)

    def test_get_with_data_and_pick_link(self):
        from tools.selection import db
        conn = db.init_db(pathlib.Path(os.environ["V9_SELECTION_DB"]))
        conn.execute("INSERT INTO signals(platform,native_id,title,quote,lang,lang_source,collected_at,"
                     "collected_at_scope,origin_kind,raw_sha256,content_hash,raw_ref,batch_id,created_at,updated_at) "
                     "VALUES ('xianyu','1','t','q','zh','heuristic','2026-01-01T00:00:00Z','batch','imported',"
                     "'a','b','x','b','2026-01-01T00:00:00Z','2026-01-01T00:00:00Z')")
        conn.commit()
        conn.close()
        r = self.client.get("/leads")
        text = r.get_data(as_text=True)
        self.assertIn("xianyu=1", text)
        self.assertIn("signals <strong>1</strong>", text)
        pick = self.client.get("/pick")
        self.assertIn('href="/leads"', pick.get_data(as_text=True))

    def test_post_start_success_stub(self):
        calls = []
        orig = self.wb.sel_bili.collect_round
        self.wb.sel_bili.collect_round = lambda **kw: calls.append(kw) or {
            "status": "complete", "requests_used": 2, "round_id": kw["round_id"]}
        try:
            r = self.client.post("/leads/round", data={
                "csrf": self.token(), "aid": "1", "budget": "3", "interval": "3",
                "idempotency_key": "ui-test"})
            self.assertEqual(r.status_code, 303)
            self.assertIn("/leads?", r.headers["Location"])
            self.assertEqual(len(calls), 1)
            self.assertEqual(calls[0]["budget"], 3)
            self.assertEqual(calls[0]["interval"], 3.0)
        finally:
            self.wb.sel_bili.collect_round = orig

    def test_post_csrf_missing_rejected(self):
        r = self.client.post("/leads/round", data={"aid": "1"})
        self.assertEqual(r.status_code, 403)

    def test_post_invalid_transition_303(self):
        from tools.selection import db, rounds
        path = pathlib.Path(os.environ["V9_SELECTION_DB"])
        conn = db.init_db(path)
        r = rounds.start(conn, kind="bilibili", platform="bilibili",
                         budget={"max_requests": 3}, idempotency_key="paused")
        rounds.transition(conn, r["id"], "running")
        rounds.pause(conn, r["id"])
        conn.close()
        resp = self.client.post(f"/leads/round/{r['id']}/pause", data={"csrf": self.token()})
        self.assertEqual(resp.status_code, 303)
        self.assertIn("err=", resp.headers["Location"])


if __name__ == "__main__":
    unittest.main()
