"""Round state machine tests + Bilibili item-level pause/resume (temp DB)."""

from __future__ import annotations

import importlib.util
import json
import os
import pathlib
import sys
import tempfile
import unittest

from tools.selection import bilibili, db, rounds

WORKBENCH = pathlib.Path(__file__).resolve().parents[1] / "tools" / "workbench"
ROOT = pathlib.Path(__file__).resolve().parents[1]

VIEW = {"aid": 1, "bvid": "BV1", "title": "t"}
REPLY = {"page": {"num": 1, "size": 5, "count": 1},
         "replies": [{"rpid": 10, "root": 0, "parent": 0,
                      "content": {"message": "学生 学习计划 Notion 模板 学习笔记"}, "member": {"mid": 1}}]}


def payload(data):
    return json.dumps({"code": 0, "message": "OK", "data": data}).encode()


class Fake:
    def __init__(self):
        self.urls = []

    def __call__(self, url):
        self.urls.append(url)
        if "/view?" in url:
            return bilibili.FetchResult(200, payload(VIEW), {}, url)
        return bilibili.FetchResult(200, payload(REPLY), {}, url)


class RoundStateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = pathlib.Path(self.tmp.name) / "s.sqlite3"
        self.conn = db.init_db(self.db)
        self.raw = pathlib.Path(self.tmp.name) / "raw"

    def tearDown(self):
        self.conn.close()
        self.tmp.cleanup()

    def test_illegal_transitions_and_cancel(self):
        r = rounds.start(self.conn, kind="bilibili", platform="bilibili",
                         budget={"max_requests": 3}, idempotency_key="k1")
        with self.assertRaises(ValueError):
            rounds.transition(self.conn, r["id"], "complete")
        rounds.transition(self.conn, r["id"], "running")
        rounds.transition(self.conn, r["id"], "paused")
        rounds.transition(self.conn, r["id"], "running")
        rounds.transition(self.conn, r["id"], "complete")
        with self.assertRaises(ValueError):
            rounds.transition(self.conn, r["id"], "running")
        r2 = rounds.start(self.conn, kind="bilibili", platform="bilibili",
                          budget={"max_requests": 3}, idempotency_key="k2")
        rounds.transition(self.conn, r2["id"], "running")
        rounds.transition(self.conn, r2["id"], "cancelled")
        self.assertEqual(self.conn.execute("SELECT status FROM rounds WHERE id=?", (r2["id"],)).fetchone()[0], "cancelled")

    def test_start_idempotent(self):
        a = rounds.start(self.conn, kind="bilibili", platform="bilibili",
                         budget={"max_requests": 3}, idempotency_key="same")
        b = rounds.start(self.conn, kind="bilibili", platform="bilibili",
                         budget={"max_requests": 3}, idempotency_key="same")
        self.assertEqual(a["id"], b["id"])
        self.assertTrue(b["reused"])
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM rounds").fetchone()[0], 1)

    def test_round_item_unique_and_mark(self):
        r = rounds.start(self.conn, kind="bilibili", platform="bilibili",
                         budget={"max_requests": 3}, idempotency_key="k")
        rounds.add_item(self.conn, r["id"], "bilibili:1")
        rounds.add_item(self.conn, r["id"], "bilibili:1")
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM round_item").fetchone()[0], 1)
        item = rounds.mark_item(self.conn, r["id"], "bilibili:1", "done")
        self.assertEqual(item["state"], "done")
        self.assertEqual(item["attempts"], 1)
        self.assertEqual(rounds.mark_item(self.conn, r["id"], "bilibili:1", "failed", error="x")["attempts"], 2)
        self.assertEqual(self.conn.execute("SELECT error_count FROM rounds WHERE id=?", (r["id"],)).fetchone()[0], 1)

    def test_pause_resume_round_bilibili(self):
        r = rounds.start(self.conn, kind="bilibili", platform="bilibili",
                         budget={"max_requests": 3}, idempotency_key="realish")
        rounds.transition(self.conn, r["id"], "running")
        rounds.add_item(self.conn, r["id"], "bilibili:view")
        rounds.add_item(self.conn, r["id"], "bilibili:reply")
        fake = Fake()
        # first execution: run until pause after view
        out = bilibili.collect_round(db_path=self.db, round_id=r["id"], raw_dir=self.raw,
                                     aid=1, budget=3, interval=0, fetch=fake, pause_after_items=1)
        self.assertEqual(out["status"], "paused")
        before = self.conn.execute("SELECT COUNT(*) FROM signals").fetchone()[0]
        used = rounds.used_requests(self.conn, r["id"])
        self.assertEqual(before, 0)  # view is not a signal; raw only
        self.assertEqual(used, 1)
        self.assertEqual(self.conn.execute(
            "SELECT state FROM round_item WHERE item_key='bilibili:view'").fetchone()[0], "done")
        # resume from cursor; must not duplicate view, and process reply
        rounds.resume(self.conn, r["id"])
        out2 = bilibili.collect_round(db_path=self.db, round_id=r["id"], raw_dir=self.raw,
                                      aid=1, budget=3, interval=0, fetch=fake)
        self.assertEqual(out2["status"], "complete")
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM signals").fetchone()[0], 1)
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM round_item WHERE state='done'").fetchone()[0], 2)
        self.assertEqual(len(fake.urls), 2)
        self.assertEqual(rounds.used_requests(self.conn, r["id"]), 2)

    def test_pause_atomicity_keeps_cursor(self):
        r = rounds.start(self.conn, kind="bilibili", platform="bilibili",
                         budget={"max_requests": 3}, idempotency_key="pause-atomic")
        rounds.transition(self.conn, r["id"], "running")
        rounds.pause(self.conn, r["id"], cursor={"last_item_key": "bilibili:view"})
        before = self.conn.execute("SELECT cursor_json FROM rounds WHERE id=?", (r["id"],)).fetchone()[0]
        self.assertIn("bilibili:view", before)
        # draft -> pause must fail with no cursor change
        d = rounds.start(self.conn, kind="bilibili", platform="bilibili",
                         budget={"max_requests": 3}, idempotency_key="draft-pause")
        with self.assertRaises(ValueError):
            rounds.pause(self.conn, d["id"], cursor={"last_item_key": "dirty"})
        self.assertIsNone(self.conn.execute("SELECT cursor_json FROM rounds WHERE id=?", (d["id"],)).fetchone()[0])
        # paused -> pause must fail and preserve original cursor
        with self.assertRaises(ValueError):
            rounds.pause(self.conn, r["id"], cursor={"last_item_key": "dirty"})
        after = self.conn.execute("SELECT cursor_json FROM rounds WHERE id=?", (r["id"],)).fetchone()[0]
        self.assertEqual(after, before)

    def test_budget_partial_writes_cursor(self):
        r = rounds.start(self.conn, kind="bilibili", platform="bilibili",
                         budget={"max_requests": 1}, idempotency_key="budget-cursor")
        rounds.transition(self.conn, r["id"], "running")
        fake = Fake()
        out = bilibili.collect_round(db_path=self.db, round_id=r["id"], raw_dir=self.raw,
                                     aid=1, budget=1, interval=0, fetch=fake)
        self.assertEqual(out["status"], "partial")
        row = self.conn.execute("SELECT cursor_json,stats_json FROM rounds WHERE id=?", (r["id"],)).fetchone()
        self.assertIsNotNone(row["cursor_json"])
        cursor = json.loads(row["cursor_json"])
        self.assertEqual(cursor.get("last_item_key"), "bilibili:view")
        self.assertEqual(json.loads(row["stats_json"])["stop_reason"], "budget_exhausted")

    def test_resume_marks_processing_interrupted(self):
        r = rounds.start(self.conn, kind="bilibili", platform="bilibili",
                         budget={"max_requests": 3}, idempotency_key="interrupted")
        rounds.transition(self.conn, r["id"], "running")
        rounds.add_item(self.conn, r["id"], "bilibili:view")
        rounds.mark_item(self.conn, r["id"], "bilibili:view", "processing")
        # simulate process exit after pause: round is paused, item remains processing
        rounds.transition(self.conn, r["id"], "paused")
        out = rounds.resume(self.conn, r["id"])  # mark interrupted + running
        self.assertGreaterEqual(out["interrupted_items"], 1)
        item = self.conn.execute("SELECT state,last_error FROM round_item WHERE round_id=? AND item_key='bilibili:view'", (r["id"],)).fetchone()
        self.assertEqual((item["state"], item["last_error"]), ("failed", "interrupted"))

    def test_budget_partial(self):
        r = rounds.start(self.conn, kind="bilibili", platform="bilibili",
                         budget={"max_requests": 1}, idempotency_key="budget")
        rounds.transition(self.conn, r["id"], "running")
        fake = Fake()
        out = bilibili.collect_round(db_path=self.db, round_id=r["id"], raw_dir=self.raw,
                                     aid=1, budget=1, interval=0, fetch=fake)
        self.assertEqual(out["status"], "partial")
        self.assertEqual(out["stop_reason"], "budget_exhausted")
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM signals").fetchone()[0], 0)
        self.assertEqual(rounds.used_requests(self.conn, r["id"]), 1)


    def test_collect_round_interval_sleeps_and_cancel(self):
        r = rounds.start(self.conn, kind="bilibili", platform="bilibili",
                         budget={"max_requests": 3}, idempotency_key="interval")
        rounds.transition(self.conn, r["id"], "running")
        slept = []
        clock = [0.0]
        def fake_clock():
            return clock[0]
        def fake_sleep(seconds):
            slept.append(seconds)
            clock[0] += seconds
        fake = Fake()
        out = bilibili.collect_round(db_path=self.db, round_id=r["id"], raw_dir=self.raw,
                                     aid=1, budget=3, interval=3, fetch=fake,
                                     sleep=fake_sleep, clock=fake_clock)
        self.assertEqual(out["status"], "complete")
        self.assertEqual(len(fake.urls), 2)
        self.assertEqual(len(slept), 1)
        self.assertGreaterEqual(slept[0], 2.9)
        # cancel before the reply: no reply request, status cancelled
        r2 = rounds.start(self.conn, kind="bilibili", platform="bilibili",
                          budget={"max_requests": 3}, idempotency_key="cancel-mid")
        rounds.transition(self.conn, r2["id"], "running")
        calls = []
        test_conn = self.conn
        class CancelFake:
            def __call__(self, url):
                calls.append(url)
                rounds.cancel(test_conn, r2["id"])
                return bilibili.FetchResult(200, payload(VIEW), {}, url)
        out2 = bilibili.collect_round(db_path=self.db, round_id=r2["id"], raw_dir=self.raw,
                                      aid=1, budget=3, interval=0, fetch=CancelFake())
        self.assertEqual(out2["status"], "cancelled")
        self.assertEqual(len(calls), 1)

    def test_start_idempotency_conflict_budget(self):
        rounds.start(self.conn, kind="bilibili", platform="bilibili",
                     budget={"max_requests": 3, "interval": 3}, idempotency_key="conflict")
        with self.assertRaises(ValueError) as cm:
            rounds.start(self.conn, kind="bilibili", platform="bilibili",
                         budget={"max_requests": 4, "interval": 3}, idempotency_key="conflict")
        self.assertIn("idempotency_conflict", str(cm.exception))

    def test_start_idempotency_conflict_aid(self):
        rounds.start(self.conn, kind="bilibili", platform="bilibili",
                     budget={"max_requests": 3, "aid": 1}, idempotency_key="aid-conflict")
        with self.assertRaises(ValueError) as cm:
            rounds.start(self.conn, kind="bilibili", platform="bilibili",
                         budget={"max_requests": 3, "aid": 2}, idempotency_key="aid-conflict")
        self.assertIn("idempotency_conflict", str(cm.exception))

    def test_start_route_categorizes_and_resume_route_collects(self):
        old_sel = os.environ.get("V9_SELECTION_DB")
        old_wf = os.environ.get("WORKBENCH_WORKFLOW_DB")
        old_bili = bilibili.collect_round
        os.environ["V9_SELECTION_DB"] = str(self.db)
        os.environ["WORKBENCH_WORKFLOW_DB"] = str(pathlib.Path(self.tmp.name) / "wf.sqlite3")
        try:
            sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(WORKBENCH))
            spec = importlib.util.spec_from_file_location("wb_v97", WORKBENCH / "app.py")
            wb = importlib.util.module_from_spec(spec); spec.loader.exec_module(wb)
            fake = Fake()
            def collect(**kw):
                kw.pop("sleep", None)
                kw["fetch"] = fake
                kw["interval"] = 0
                return old_bili(**kw)
            wb.sel_bili.collect_round = collect
            app = wb.create_app(); app.testing = True
            c = app.test_client(); c.get("/leads")
            with c.session_transaction() as s:
                token = s["csrf"]
            r = c.post("/leads/round", data={"csrf": token, "aid": "1", "budget": "3",
                                            "interval": "3", "idempotency_key": "ui-e2e"})
            self.assertEqual(r.status_code, 303)
            from urllib.parse import unquote
            self.assertIn("categories=1", unquote(r.headers["Location"]))
            conn = db.init_db(self.db)
            try:
                self.assertGreaterEqual(conn.execute("SELECT COUNT(*) FROM categories").fetchone()[0], 1)
                self.assertGreaterEqual(conn.execute("SELECT COUNT(*) FROM direction_card").fetchone()[0], 1)
                self.assertGreaterEqual(conn.execute("SELECT COUNT(*) FROM discovery_event").fetchone()[0], 1)
                rid = conn.execute("SELECT id FROM rounds WHERE idempotency_key='ui-e2e'").fetchone()[0]
            finally:
                conn.close()
            # separate paused round with only view done; resume route must fetch reply
            conn = db.init_db(self.db)
            try:
                r2 = rounds.start(conn, kind="bilibili", platform="bilibili",
                                  budget={"max_requests": 3, "interval": 3, "aid": 1, "bvid": None},
                                  idempotency_key="ui-resume")
                rounds.transition(conn, r2["id"], "running")
            finally:
                conn.close()
            first = old_bili(db_path=self.db, round_id=r2["id"], raw_dir=self.raw,
                             aid=1, budget=3, interval=0, fetch=fake, pause_after_items=1)
            self.assertEqual(first["status"], "paused")
            before = len(fake.urls)
            rr = c.post(f"/leads/round/{r2['id']}/resume", data={"csrf": token})
            self.assertEqual(rr.status_code, 303)
            self.assertGreater(len(fake.urls), before)
            conn = db.init_db(self.db)
            try:
                self.assertEqual(conn.execute("SELECT state FROM round_item WHERE round_id=? AND item_key='bilibili:reply'", (r2["id"],)).fetchone()[0], "done")
                used = json.loads(conn.execute("SELECT stats_json FROM rounds WHERE id=?", (r2["id"],)).fetchone()[0])["requests_used"]
                self.assertGreaterEqual(used, 2)
                self.assertEqual(conn.execute("SELECT COUNT(*) FROM signals").fetchone()[0], 1)
                self.assertEqual(conn.execute("SELECT COUNT(*) FROM signals WHERE platform='bilibili' AND native_id='10'").fetchone()[0], 1)
            finally:
                conn.close()
        finally:
            bilibili.collect_round = old_bili
            for key, old in (("V9_SELECTION_DB", old_sel), ("WORKBENCH_WORKFLOW_DB", old_wf)):
                if old is None: os.environ.pop(key, None)
                else: os.environ[key] = old

if __name__ == "__main__":
    unittest.main()
