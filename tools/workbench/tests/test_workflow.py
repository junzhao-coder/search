"""B1 商品工作单测试：独立库、服务端校验、幂等/版本、CSRF/同源、持久化、缺项与门槛。"""

from __future__ import annotations

import os
import pathlib
import sys
import tempfile
import unittest

WORKBENCH = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(WORKBENCH))

import workflow as wf  # noqa: E402


def _pick(kind: str) -> tuple[str, str]:
    """从真实数据里找一个指定 kind 的条目，返回 (category, item_id)。"""
    rows, _refs = wf.load_sources()
    for item_id, row in rows.items():
        k, category = wf.classify_group(row)
        if k == kind and category not in ("Notion 其它（待人工）", "未归类（待人工）"):
            return category, item_id
    raise AssertionError(f"no item of kind {kind}")


def _pick_unclassified() -> tuple[str, str]:
    rows, _refs = wf.load_sources()
    for item_id, row in rows.items():
        _k, category = wf.classify_group(row)
        if category in ("Notion 其它（待人工）", "未归类（待人工）"):
            return category, item_id
    raise AssertionError("no unclassified item")


class WorkflowTestBase(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tmp = tempfile.TemporaryDirectory()
        cls.db = pathlib.Path(cls.tmp.name) / "workflow.sqlite3"
        cls.secret = pathlib.Path(cls.tmp.name) / "secret_key"
        os.environ["WORKBENCH_WORKFLOW_DB"] = str(cls.db)
        os.environ["WORKBENCH_SECRET_FILE"] = str(cls.secret)
        import app as wb
        cls.wb = wb

    @classmethod
    def tearDownClass(cls) -> None:
        os.environ.pop("WORKBENCH_WORKFLOW_DB", None)
        os.environ.pop("WORKBENCH_SECRET_FILE", None)
        cls.tmp.cleanup()

    def setUp(self) -> None:
        if self.db.exists():
            self.db.unlink()
        self.app = self.wb.create_app()
        self.app.testing = True
        self.client = self.app.test_client()
        self.category, self.item_id = _pick("商品")

    # ---------- helpers ----------
    def token(self) -> str:
        self.client.get("/worksheet")
        with self.client.session_transaction() as sess:
            return sess["csrf"]

    def create(self, *, key="k1", category=None, item_id=None, **overrides):
        data = {
            "csrf": self.token(), "group": category or self.category, "item_id": item_id or self.item_id,
            "submit_key": key, "name": "Notion 学习笔记工作单", "use_case": "学习笔记整理",
            "target_buyer": "学生", "deliverable": "Notion 页面模板", "fmt": "Notion",
            "language": "中文", "version": "v1", "includes": "模板本体", "excludes": "不含素材",
            "target_platform": "xianyu",
        }
        data.update(overrides)
        return self.client.post("/worksheet/new", data=data)

    def count(self) -> int:
        conn = wf.connect()
        try:
            return len(wf.list_all(conn))
        finally:
            conn.close()

    # ---------- 1. 建单与来源校验 ----------
    def test_create_from_real_product(self):
        resp = self.create()
        self.assertEqual(resp.status_code, 303)
        conn = wf.connect()
        try:
            records = wf.list_all(conn)
        finally:
            conn.close()
        self.assertEqual(len(records), 1)
        rec = records[0]
        self.assertTrue(rec["workorder_id"].startswith("wo:"))
        self.assertEqual(rec["source_item_id"], self.item_id)
        self.assertEqual(rec["source_group"], self.category)
        self.assertEqual(rec["selected_supply_id"], None)
        self.assertEqual(rec["status"], "pending_supply")
        for gate in wf.GATES:
            self.assertEqual(rec[f"gate_{gate}"], "unverified")
        self.assertEqual(rec["snapshot"]["item_id"], self.item_id)

    def test_rejects_content_and_unclassified_and_missing(self):
        content_cat, content_id = _pick("内容")
        resp = self.create(key="k2", category=content_cat, item_id=content_id)
        self.assertEqual(resp.status_code, 400)
        self.assertIn("source_not_product", resp.get_data(as_text=True))

        none_cat, none_id = _pick_unclassified()
        resp = self.create(key="k3", category=none_cat, item_id=none_id)
        self.assertEqual(resp.status_code, 400)
        self.assertIn("source_unclassified", resp.get_data(as_text=True))

        resp = self.create(key="k4", category=self.category, item_id="x:does-not-exist")
        self.assertEqual(resp.status_code, 400)
        self.assertIn("source_not_found", resp.get_data(as_text=True))
        self.assertEqual(self.count(), 0)

    # ---------- 2. 幂等与冲突 ----------
    def test_idempotent_same_key_same_payload(self):
        self.create(key="dup")
        resp = self.create(key="dup")
        self.assertEqual(resp.status_code, 303)
        self.assertIn("deduplicated=1", resp.headers["Location"])
        self.assertEqual(self.count(), 1)

    def test_same_key_different_payload_conflicts(self):
        self.create(key="dup2")
        resp = self.create(key="dup2", name="改过的名字")
        self.assertEqual(resp.status_code, 409)
        self.assertEqual(self.count(), 1)
        conn = wf.connect()
        try:
            rec = wf.list_all(conn)[0]
        finally:
            conn.close()
        self.assertEqual(rec["name"], "Notion 学习笔记工作单")   # 原记录未被覆盖

    def test_missing_submit_key_rejected(self):
        resp = self.create(key="")
        self.assertEqual(resp.status_code, 400)
        self.assertIn("submit_key_invalid", resp.get_data(as_text=True))

    # ---------- 3. 编辑 / 版本冲突 / 校验回滚 ----------
    def _first_id(self) -> str:
        conn = wf.connect()
        try:
            return wf.list_all(conn)[0]["workorder_id"]
        finally:
            conn.close()

    def test_edit_updates_and_bumps_revision(self):
        self.create(key="e1")
        wid = self._first_id()
        resp = self.client.post(f"/worksheet/{wid}/edit", data={
            "csrf": self.token(), "revision": "1", "name": "改名后的工作单", "use_case": "学习笔记",
            "deliverable": "Notion 模板", "target_platform": "xianyu", "status": "in_review"})
        self.assertEqual(resp.status_code, 303)
        conn = wf.connect()
        try:
            rec = wf.get(conn, wid)
        finally:
            conn.close()
        self.assertEqual(rec["name"], "改名后的工作单")
        self.assertEqual(rec["revision"], 2)
        self.assertEqual(rec["status"], "in_review")

    def test_stale_revision_conflicts_without_data_loss(self):
        self.create(key="e2")
        wid = self._first_id()
        self.client.post(f"/worksheet/{wid}/edit", data={
            "csrf": self.token(), "revision": "1", "name": "第一次改名", "use_case": "学习笔记",
            "deliverable": "Notion 模板", "target_platform": "xianyu"})
        resp = self.client.post(f"/worksheet/{wid}/edit", data={
            "csrf": self.token(), "revision": "1", "name": "过期改名", "use_case": "学习笔记",
            "deliverable": "Notion 模板", "target_platform": "xianyu"})
        self.assertEqual(resp.status_code, 409)
        conn = wf.connect()
        try:
            rec = wf.get(conn, wid)
        finally:
            conn.close()
        self.assertEqual(rec["name"], "第一次改名")
        self.assertEqual(rec["revision"], 2)

    def test_validation_failure_keeps_record(self):
        self.create(key="e3")
        wid = self._first_id()
        for bad in ({"name": ""}, {"target_platform": "taobao"}, {"name": "x" * 200}):
            payload = {"csrf": self.token(), "revision": "1", "name": "合法名", "use_case": "用途",
                       "deliverable": "交付物", "target_platform": "xianyu", **bad}
            resp = self.client.post(f"/worksheet/{wid}/edit", data=payload)
            self.assertIn(resp.status_code, (400, 403), bad)
        conn = wf.connect()
        try:
            rec = wf.get(conn, wid)
        finally:
            conn.close()
        self.assertEqual(rec["name"], "Notion 学习笔记工作单")
        self.assertEqual(rec["revision"], 1)

    # ---------- 4. 越级与伪造 ----------
    def test_rejects_ready_verified_and_forged_fields(self):
        for payload in ({"status": "verified"}, {"status": "ready"},
                        {"selected_supply_id": "sup-1"}, {"gate_cost": "verified"}, {"snapshot": "{}"}):
            resp = self.create(key=f"f-{list(payload)[0]}", **payload)
            self.assertEqual(resp.status_code, 403, payload)
        self.assertEqual(self.count(), 0)

    def test_edit_cannot_escalate_status(self):
        self.create(key="esc")
        wid = self._first_id()
        resp = self.client.post(f"/worksheet/{wid}/edit", data={
            "csrf": self.token(), "revision": "1", "name": "名字", "use_case": "用途",
            "deliverable": "交付物", "target_platform": "xianyu", "status": "ready"})
        self.assertEqual(resp.status_code, 403)
        conn = wf.connect()
        try:
            rec = wf.get(conn, wid)
        finally:
            conn.close()
        self.assertEqual(rec["status"], "pending_supply")

    # ---------- 5. CSRF / 同源 / GET 零写 ----------
    def test_csrf_required_and_origin_checked(self):
        resp = self.create(key="c1", csrf="wrong")
        self.assertEqual(resp.status_code, 403)
        token = self.token()
        resp = self.client.post("/worksheet/new", data={
            "csrf": token, "group": self.category, "item_id": self.item_id, "submit_key": "c2",
            "name": "n", "use_case": "u", "deliverable": "d", "target_platform": "xianyu"},
            headers={"Origin": "https://evil.example"})
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(self.count(), 0)

    def test_get_requests_do_not_write_workorder(self):
        """GET 零写：记录/事件快照 + 文件 sha256 前后严格相等。"""
        import hashlib
        self.create(key="g1")

        def snapshot() -> tuple[str, int, int]:
            sha = hashlib.sha256(self.db.read_bytes()).hexdigest()
            conn = wf.connect()
            try:
                wo = conn.execute("SELECT * FROM workorder ORDER BY workorder_id").fetchall()
                ev = conn.execute("SELECT * FROM workorder_event ORDER BY id").fetchall()
            finally:
                conn.close()
            return sha, len([dict(r) for r in wo]), len([dict(r) for r in ev])

        before = snapshot()
        for path in ("/worksheet", "/", "/opportunities", "/content", "/healthz"):
            self.client.get(path)
        after = snapshot()
        self.assertEqual(before, after, "GET 改变了工作单/事件或库文件内容")

    def test_get_does_not_create_db_file(self):
        if self.db.exists():
            self.db.unlink()
        for path in ("/worksheet", "/opportunities", "/content", "/healthz"):
            self.assertIn(self.client.get(path).status_code, (200, 404))
        root = self.client.get("/")            # B21：根入口 302 到 /pick
        self.assertEqual(root.status_code, 302)
        self.assertEqual(root.headers["Location"], "/pick")
        self.assertFalse(self.db.exists(), "GET 不应创建工作单库文件")
        self.assertEqual(self.count(), 0)

    def test_missing_workorder_404(self):
        self.assertEqual(self.client.get("/worksheet/wo:missing").status_code, 404)

    # ---------- 6. 持久化（新实例/新连接） ----------
    def test_persists_across_new_app_instance(self):
        self.create(key="p1")
        wid = self._first_id()
        # 新 app 实例 + 新连接（模拟重启后重新打开库）
        app2 = self.wb.create_app()
        app2.testing = True
        client2 = app2.test_client()
        body = client2.get(f"/worksheet/{wid}").get_data(as_text=True)
        self.assertIn("Notion 学习笔记工作单", body)
        conn = wf.connect()
        try:
            self.assertIsNotNone(wf.get(conn, wid))
        finally:
            conn.close()

    # ---------- 7. 缺项与阶段 ----------
    def test_gaps_and_stages(self):
        self.create(key="gap")
        conn = wf.connect()
        try:
            rec = wf.list_all(conn)[0]
        finally:
            conn.close()
        _rows, refs = wf.load_sources()
        gaps = wf.derive_gaps(rec["snapshot"], refs)
        joined = " ".join(gaps)
        self.assertIn("四门槛均未核验", joined)
        self.assertIn("未选定货源", joined)
        self.assertIn("未验货（B2 待实现）", joined)
        self.assertIn("未生成上架包（B5 待实现）", joined)
        stages = wf.stages_state(rec)
        self.assertEqual([s["state"] for s in stages], ["done", "pending", "pending", "pending", "pending", "pending"])


class AtomicAndRejectTests(unittest.TestCase):
    """隔离来源 fixture：原子更新/并发、revision 校验、CSRF 与同源拒绝、GET 零写。"""

    SCORE_COLS = ["rank", "item_id", "platform", "title", "url", "author", "published_at", "total_score",
                  "demand_raw", "demand_norm", "sellability_norm", "sellability_reason", "margin_low", "margin_high",
                  "margin_mid", "margin_assumption", "cost_input", "cost_note", "missing_metrics", "source", "raw_ref"]
    ROWS = [
        {"rank": "1", "item_id": "x:prod-notes", "platform": "x", "title": "notion study notes template",
         "url": "https://x/1", "author": "@a", "total_score": "0.8", "demand_raw": "1000", "demand_norm": "0.9",
         "sellability_norm": "0.9", "sellability_reason": "含明确售价", "margin_low": "0.7", "margin_high": "0.95",
         "margin_mid": "0.825", "margin_assumption": "假设", "cost_input": "missing", "missing_metrics": "",
         "source": "fixture", "raw_ref": "raw/x.jsonl"},
        {"rank": "2", "item_id": "x:content-tut", "platform": "x", "title": "how to import notion template",
         "url": "https://x/2", "author": "@b", "total_score": "0.5", "demand_raw": "500", "demand_norm": "0.5",
         "sellability_norm": "0.5", "sellability_reason": "", "margin_low": "", "margin_high": "", "margin_mid": "",
         "margin_assumption": "", "cost_input": "", "missing_metrics": "", "source": "fixture", "raw_ref": ""},
        {"rank": "3", "item_id": "x:unclassified", "platform": "x", "title": "notion template",
         "url": "https://x/3", "author": "@c", "total_score": "0.4", "demand_raw": "300", "demand_norm": "0.3",
         "sellability_norm": "0.4", "sellability_reason": "", "margin_low": "", "margin_high": "", "margin_mid": "",
         "margin_assumption": "", "cost_input": "", "missing_metrics": "", "source": "fixture", "raw_ref": ""},
    ]

    @classmethod
    def setUpClass(cls) -> None:
        import csv
        cls.tmp = tempfile.TemporaryDirectory()
        root = pathlib.Path(cls.tmp.name)
        scores = root / "scores.csv"
        with scores.open("w", encoding="utf-8", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=cls.SCORE_COLS)
            writer.writeheader()
            for row in cls.ROWS:
                writer.writerow({c: row.get(c, "") for c in cls.SCORE_COLS})
        top10 = root / "top10.csv"
        top10.write_text("rank,opportunity_id,reference_max\n1,x:prod-notes,699\n", encoding="utf-8")
        cls.db = root / "workflow.sqlite3"
        cls.secret = root / "secret_key"
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

    def _token(self) -> str:
        self.client.get("/worksheet")
        with self.client.session_transaction() as sess:
            return sess["csrf"]

    def _create(self, key="k", item="x:prod-notes", group="Notion 学习笔记模板", **extra):
        data = {"csrf": self._token(), "group": group, "item_id": item, "submit_key": key,
                "name": "工作单", "use_case": "学习笔记", "deliverable": "Notion 模板",
                "target_platform": "xianyu", **extra}
        return self.client.post("/worksheet/new", data=data)

    def _wid(self) -> str:
        conn = wf.connect()
        try:
            return wf.list_all(conn)[0]["workorder_id"]
        finally:
            conn.close()

    def _events(self) -> list[dict]:
        conn = wf.connect()
        try:
            return [dict(r) for r in conn.execute("SELECT * FROM workorder_event ORDER BY id").fetchall()]
        finally:
            conn.close()

    # ---------- 原子性与并发 ----------
    def test_atomic_update_rowcount_and_no_false_audit(self):
        import sqlite3
        self._create()
        wid = self._wid()
        conn_a, conn_b = wf.connect(), wf.connect()
        try:
            rec_a = wf.get(conn_a, wid)          # A 预读 revision=1
            wf.update(conn_b, wid, revision=1, payload={"name": "B 的改名", "use_case": "学习笔记",
                                                        "deliverable": "Notion 模板", "target_platform": "xianyu"})
            with self.assertRaises(wf.Reject) as ctx:
                wf.update(conn_a, wid, revision=rec_a["revision"], payload={
                    "name": "A 的过期改名", "use_case": "学习笔记", "deliverable": "Notion 模板",
                    "target_platform": "xianyu"})
        finally:
            conn_a.close()
            conn_b.close()
        self.assertEqual(ctx.exception.status, 409)
        conn = wf.connect()
        try:
            rec = wf.get(conn, wid)
        finally:
            conn.close()
        self.assertEqual(rec["name"], "B 的改名")     # A 未覆盖
        self.assertEqual(rec["revision"], 2)
        updates = [e for e in self._events() if e["action"] == "update"]
        self.assertEqual(len(updates), 1, "失败路径不应写入成功审计")

    def test_atomic_update_zero_rows_after_prefetch(self):
        """受控用例：patch wf.update 内部首次 wf.get 返回旧快照（库已是 rev2）→ UPDATE 命中 0 行。"""
        import hashlib
        from unittest import mock
        self._create()
        wid = self._wid()
        conn = wf.connect()
        try:
            wf.update(conn, wid, revision=1, payload={"name": "B 的改名", "use_case": "u", "deliverable": "d",
                                                      "target_platform": "xianyu"})
            real_row = wf.get(conn, wid)
            self.assertEqual(real_row["revision"], 2)
            stale = dict(real_row)
            stale["revision"] = 1                       # 旧快照：预检会放行
            stale["name"] = "A 的过期改名"
            events_before = conn.execute("SELECT COUNT(*) FROM workorder_event").fetchone()[0]
            sha_before = hashlib.sha256(self.db.read_bytes()).hexdigest()
            calls = {"n": 0}
            real_get = wf.get

            def fake_get(connection, workorder_id):
                calls["n"] += 1
                return stale if calls["n"] == 1 else real_get(connection, workorder_id)

            with mock.patch.object(wf, "get", fake_get):
                with self.assertRaises(wf.Reject) as ctx:
                    wf.update(conn, wid, revision=1, payload={"name": "A 的过期改名", "use_case": "u",
                                                              "deliverable": "d", "target_platform": "xianyu"})
            self.assertEqual(ctx.exception.status, 409)
            self.assertIn("UPDATE 命中 0 行", ctx.exception.message)
            self.assertFalse(conn.in_transaction, "回滚后不应残留事务")
            after = real_get(conn, wid)
            self.assertEqual(after["name"], "B 的改名")
            self.assertEqual(after["revision"], 2)
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM workorder_event").fetchone()[0],
                             events_before, "冲突路径不应新增审计")
            self.assertEqual(hashlib.sha256(self.db.read_bytes()).hexdigest(), sha_before, "库文件不应变化")
        finally:
            conn.close()

    # ---------- revision 参数校验 ----------
    def test_revision_invalid_returns_4xx(self):
        self._create()
        wid = self._wid()
        for bad in ("abc", "", "1.5", "-1", "0", "1e3", "９", " " * 3):
            resp = self.client.post(f"/worksheet/{wid}/edit", data={
                "csrf": self._token(), "revision": bad, "name": "名字", "use_case": "用途",
                "deliverable": "交付物", "target_platform": "xianyu"})
            self.assertEqual(resp.status_code, 400, bad)
            self.assertIn("revision_invalid", resp.get_data(as_text=True), bad)
        conn = wf.connect()
        try:
            rec = wf.get(conn, wid)
        finally:
            conn.close()
        self.assertEqual(rec["revision"], 1)

    # ---------- CSRF（Unicode/坏值）与同源 ----------
    def test_unicode_and_bad_csrf_are_403_not_500(self):
        token = self._token()
        for bad in ("日本語トークン", "🙂" * 3, "x" * 200, token + "\u0000"):
            resp = self.client.post("/worksheet/new", data={
                "csrf": bad, "group": "Notion 学习笔记模板", "item_id": "x:prod-notes", "submit_key": "u1",
                "name": "n", "use_case": "u", "deliverable": "d", "target_platform": "xianyu"})
            self.assertEqual(resp.status_code, 403, bad)

    def test_origin_rejects_null_file_relative_malformed_and_foreign(self):
        token = self._token()
        base = {"csrf": token, "group": "Notion 学习笔记模板", "item_id": "x:prod-notes", "submit_key": "o1",
                "name": "n", "use_case": "u", "deliverable": "d", "target_platform": "xianyu"}
        for origin in ("null", "file://x", "//evil.example", "http://", "http://evil.example",
                       "https://evil.example/path", "chrome-extension://abc", "ftp://127.0.0.1"):
            resp = self.client.post("/worksheet/new", data=base, headers={"Origin": origin})
            self.assertEqual(resp.status_code, 403, origin)
        ok = self.client.post("/worksheet/new", data=base, headers={"Origin": "http://localhost"})
        self.assertEqual(ok.status_code, 303)

    def test_origin_scheme_must_match_host_url(self):
        """服务是 http 时，同 host 但 https 的 Origin/Referer 必须 403；同源 http 成功。"""
        base = {"group": "Notion 学习笔记模板", "item_id": "x:prod-notes", "submit_key": "s1",
                "name": "n", "use_case": "u", "deliverable": "d", "target_platform": "xianyu"}
        token = self._token()
        for header in ({"Origin": "https://localhost"}, {"Referer": "https://localhost/opportunities"}):
            resp = self.client.post("/worksheet/new", data={**base, "csrf": token}, headers=header)
            self.assertEqual(resp.status_code, 403, header)
        ok = self.client.post("/worksheet/new", data={**base, "csrf": token},
                              headers={"Origin": "http://localhost"})
        self.assertEqual(ok.status_code, 303)

    def test_sequential_conflict_two_connections(self):
        """顺序冲突（A 预读 → B 提交 → A 过期）；**非多线程并发压测**。"""
        self._create("seq")
        wid = self._wid()
        conn_a, conn_b = wf.connect(), wf.connect()
        try:
            rec_a = wf.get(conn_a, wid)
            wf.update(conn_b, wid, revision=1, payload={"name": "B 的改名", "use_case": "u", "deliverable": "d",
                                                        "target_platform": "xianyu"})
            with self.assertRaises(wf.Reject) as ctx:
                wf.update(conn_a, wid, revision=rec_a["revision"], payload={
                    "name": "A 的过期改名", "use_case": "u", "deliverable": "d", "target_platform": "xianyu"})
        finally:
            conn_a.close()
            conn_b.close()
        self.assertEqual(ctx.exception.status, 409)
        conn = wf.connect()
        try:
            rec = wf.get(conn, wid)
        finally:
            conn.close()
        self.assertEqual((rec["name"], rec["revision"]), ("B 的改名", 2))

    def test_referer_checked_too(self):
        token = self._token()
        base = {"csrf": token, "group": "Notion 学习笔记模板", "item_id": "x:prod-notes", "submit_key": "r1",
                "name": "n", "use_case": "u", "deliverable": "d", "target_platform": "xianyu"}
        bad = self.client.post("/worksheet/new", data=base, headers={"Referer": "https://evil.example/x"})
        self.assertEqual(bad.status_code, 403)

    # ---------- fixture 来源校验 ----------
    def test_fixture_source_rejections(self):
        self.assertEqual(self._create("c1", item="x:content-tut", group="Notion 使用教程/导入设置").status_code, 400)
        self.assertEqual(self._create("c2", item="x:unclassified", group="Notion 其它（待人工）").status_code, 400)
        self.assertEqual(self._create("c3", item="x:nope", group="Notion 学习笔记模板").status_code, 400)
        self.assertEqual(self._create("c4", item="x:prod-notes", group="错的分组").status_code, 400)

    # ---------- GET 零写（严格 + 不存在时不建库） ----------
    def test_get_zero_write_strict(self):
        import hashlib
        self._create("z1")
        sha_before = hashlib.sha256(self.db.read_bytes()).hexdigest()
        events_before = self._events()
        for path in ("/worksheet", "/", "/opportunities", "/content", "/healthz"):
            self.client.get(path)
        self.assertEqual(hashlib.sha256(self.db.read_bytes()).hexdigest(), sha_before)
        self.assertEqual(self._events(), events_before)

    def test_get_does_not_create_db(self):
        if self.db.exists():
            self.db.unlink()
        for path in ("/worksheet", "/healthz"):
            self.client.get(path)
        self.assertFalse(self.db.exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
