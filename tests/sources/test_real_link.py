"""S3 real 模式离线测试（fixture transport）：授权/预算/重试/异常/审计/共存/间隔/缓存。

所有用例使用隔离 tmp DB 与假 transport（**不发起真实网络**）；真实受控运行在另一 run 目录单独执行。
"""

import json
import pathlib
import tempfile
import unittest

from app import create_app
from app.core import importer
from app.core.errors import AppError
from app.sources import real_link
from app.storage.db import connect
from tests.api import b2_helpers as b2

FIXTURE = pathlib.Path(__file__).resolve().parents[1] / "fixtures" / "sources" / "bilibili_view_ok_BV1us8MzPEmn.json"
AUTH = {"batch_id": "batch-test-1", "confirmed": True}


def ok_payload(bvid: str = "BV1us8MzPEmn") -> dict:
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))["transport"]
    payload = json.loads(json.dumps(payload))
    inner = payload.get("payload")
    if isinstance(inner, dict):
        inner.setdefault("data", {})["bvid"] = bvid
    payload.setdefault("http_status", 200)
    return payload


class FakeTransport:
    def __init__(self, *, exc=None, fail_bvids=()):
        self.exc = exc
        self.fail_bvids = set(fail_bvids)
        self.calls = []

    def __call__(self, url: str) -> dict:
        self.calls.append(url)
        if self.exc is not None:
            raise self.exc
        bvid = real_link._bvid_from_url(url)
        if bvid in self.fail_bvids:
            return {"http_status": 422, "payload": {"code": -412, "message": "risk"},
                    "error": None}
        return ok_payload(bvid)


class Clock:
    def __init__(self):
        self.now = 1000.0
        self.sleeps = []
        self.jump = {}

    def __call__(self):
        self.now += getattr(self, "tick", 0.0)
        return self.now

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.now += seconds + self.jump.get(seconds, 0.0)


class RealLinkTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="real_")
        self.app = create_app({"db_path": str(pathlib.Path(self.tmp) / "app.db")})
        self.cfg = self.app.config["APP_CFG"]
        self.conn = connect(self.cfg["db_path"])
        self.run_dir = str(pathlib.Path(self.tmp) / "run")

    def tearDown(self):
        self.conn.close()

    def run_batch(self, transport, bvids=("BV1us8MzPEmn",), **kwargs):
        clock = kwargs.pop("clock", None) or Clock()
        kwargs.setdefault("budget", real_link.DEFAULT_BUDGET)
        kwargs.setdefault("interval_seconds", 5.0)
        kwargs.setdefault("timeout_seconds", 600.0)
        kwargs.setdefault("authorization", AUTH)
        kwargs.setdefault("cfg", self.cfg)
        kwargs.setdefault("run_dir", self.run_dir)
        kwargs.setdefault("transport", transport)
        return real_link.run_real_batch(self.conn, bvids, clock=clock, sleep=clock.sleep,
                                        **kwargs), clock

    def audit_lines(self):
        path = pathlib.Path(self.run_dir) / "audit.jsonl"
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]

    # ---------------------------------------------------------------- 授权
    def test_unauthorized_never_touches_network(self):
        for authorization in (None, {}, {"batch_id": "", "confirmed": True},
                              {"batch_id": "b1", "confirmed": False}):
            transport = FakeTransport()
            with self.assertRaises(AppError):
                real_link.run_real_batch(self.conn, ["BV1us8MzPEmn"], authorization=authorization,
                                         run_dir=self.run_dir, cfg=self.cfg, transport=transport)
            self.assertEqual(transport.calls, [])            # 0 次网络请求
        self.assertFalse((pathlib.Path(self.run_dir) / "audit.jsonl").exists())

    def test_invalid_budget_and_interval_rejected(self):
        for kwargs in ({"budget": 21}, {"budget": 0}, {"interval_seconds": 4.9},
                       {"timeout_seconds": 601}):
            transport = FakeTransport()
            with self.assertRaises(AppError):
                real_link.run_real_batch(self.conn, ["BV1us8MzPEmn"], authorization=AUTH,
                                         run_dir=self.run_dir, cfg=self.cfg, transport=transport,
                                         **kwargs)
            self.assertEqual(transport.calls, [])

    # ---------------------------------------------------------------- 预算/重试/间隔
    def test_budget_exhausted_notes_and_stop(self):
        transport = FakeTransport()
        result, _ = self.run_batch(transport, bvids=("BV1us8MzPEmn", "BV1us8MzPEmn"), budget=1)
        self.assertEqual(len(transport.calls), 1)
        self.assertEqual(result["requests"], 1)
        self.assertIn(real_link.BUDGET_EXHAUSTED, result["notes"])
        self.assertEqual(result["stopped_reason"], real_link.BUDGET_EXHAUSTED)

    def test_retry_counts_toward_budget(self):
        transport = FakeTransport(exc=RuntimeError("boom"))   # 异常属可重试（失败类）
        result, clock = self.run_batch(transport, budget=10)
        self.assertEqual(len(transport.calls), 2)                 # 一次请求 + 一次重试
        self.assertEqual(result["requests"], 2)                   # 重试计入预算
        self.assertIn(real_link.RETRY_WAIT_SECONDS, clock.sleeps)  # 2 秒退避
        self.assertEqual(self.audit_lines()[-1]["attempt"], 2)

    def test_successful_import_creates_real_row(self):
        transport = FakeTransport()
        result, clock = self.run_batch(transport, bvids=("BV1us8MzPEmn", "BV1us8MzPEmn"))
        self.assertEqual(result["status"], "ok")
        self.assertEqual(len(transport.calls), 2)                 # 同 bvid 两次：第二次为重放
        self.assertIn(5.0, clock.sleeps)                          # 串行间隔 ≥5s
        rows = b2.query(self.cfg["db_path"], "SELECT data_origin, identity_key FROM demand_signal")
        self.assertEqual({row["data_origin"] for row in rows}, {"real"})
        self.assertIn("n:bilibili:BV1us8MzPEmn", {row["identity_key"] for row in rows})
        run = b2.query(self.cfg["db_path"], "SELECT status, source_id FROM run_record ORDER BY rowid DESC")[0]
        self.assertEqual((run["status"], run["source_id"]), ("ok", "s_bili"))
        lines = self.audit_lines()
        self.assertEqual(len(lines), 2)
        for line in lines:
            self.assertIn("https://api.bilibili.com/x/web-interface/view?bvid=", line["url"])
            self.assertEqual(line["http_status"], 200)
            self.assertEqual(line["outcome"], "ok")

    def test_transport_exception_is_recorded_as_failed_run(self):
        transport = FakeTransport(exc=RuntimeError("boom"))
        result, _ = self.run_batch(transport, budget=2)
        self.assertIn(result["status"], ("failed", "partial"))
        failed = b2.query(self.cfg["db_path"], "SELECT status, error_summary FROM run_record")
        self.assertTrue(any(row["status"] == "failed" for row in failed))
        self.assertIn("transport 异常", json.dumps(failed, ensure_ascii=False))
        self.assertIn("boom", json.dumps(self.audit_lines(), ensure_ascii=False))

    def test_failures_are_not_cached(self):
        transport = FakeTransport(exc=RuntimeError("boom"))
        self.run_batch(transport, budget=3)
        calls_first = len(transport.calls)
        self.assertGreaterEqual(calls_first, 1)
        self.run_batch(transport, budget=3)
        self.assertEqual(len(transport.calls), calls_first * 2)   # 新批次重新请求，不复用失败

    # ---------------------------------------------------------------- 归一化层（本批新增）
    def test_normalize_response_layers(self):
        env = real_link.normalize_response(200, None, json.dumps({"code": 0, "data": {"bvid": "BV1us8MzPEmn"}}).encode())
        self.assertEqual((env["http_status"], env["error"]), (200, None))
        self.assertEqual(env["payload"]["code"], 0)
        self.assertEqual(env["payload"]["data"]["bvid"], "BV1us8MzPEmn")
        html = real_link.normalize_response(200, "text/html", b"<html>challenge</html>")
        self.assertEqual(html, {"http_status": 200, "payload": None, "error": "html_shell"})
        import gzip
        gzipped = gzip.compress(json.dumps({"code": -412, "message": "risk"}).encode())
        env2 = real_link.normalize_response(412, None, gzipped)
        self.assertEqual(env2["http_status"], 412)
        self.assertEqual(env2["payload"]["code"], -412)

    def test_api_url_normalization(self):
        self.assertEqual(real_link.api_url("BV1us8MzPEmn"),
                         "https://api.bilibili.com/x/web-interface/view?bvid=BV1us8MzPEmn")
        self.assertEqual(real_link._bvid_from_url("https://www.bilibili.com/video/BV1us8MzPEmn"),
                         "BV1us8MzPEmn")

    # ---------------------------------------------------------------- 失败路径加固（本批）
    def test_import_failure_never_reports_ok(self):
        from unittest import mock
        with mock.patch.object(real_link, "_build_real_row",
                               side_effect=AppError("boom", code="invalid_field", status=422)):
            result, _ = self.run_batch(FakeTransport())
        self.assertEqual(result["status"], "failed")          # 导入失败不得报 ok
        self.assertEqual(result["imported"], [])
        self.assertTrue(result["failed_imports"])
        rows = b2.query(self.cfg["db_path"], "SELECT status, error_summary FROM run_record")
        self.assertTrue(any(row["status"] == "failed" and "映射/校验失败" in (row["error_summary"] or "")
                            for row in rows))
        terminal = json.loads(pathlib.Path(result["result_path"]).read_text(encoding="utf-8"))
        self.assertEqual(terminal["status"], "failed")
        self.assertTrue(terminal["failed_imports"])

    def test_timeout_after_retry_wait_blocks_request(self):
        clock = Clock()
        clock.jump[real_link.RETRY_WAIT_SECONDS] = 700.0      # 退避等待后已越过总超时
        transport = FakeTransport(exc=RuntimeError("boom"))
        result, _ = self.run_batch(transport, budget=5, timeout_seconds=600.0, clock=clock)
        self.assertEqual(len(transport.calls), 1)             # 等待后过期：不得再请求
        self.assertEqual(result["stopped_reason"], real_link.TIMEOUT_STOP)
        self.assertTrue(result["truncated"])
        rows = b2.query(self.cfg["db_path"], "SELECT status, error_summary FROM run_record")
        self.assertTrue(any(real_link.TIMEOUT_STOP in (row["error_summary"] or "") for row in rows))
        self.assertTrue([line for line in self.audit_lines() if line.get("event") == "truncated"])
        terminal = json.loads(pathlib.Path(result["result_path"]).read_text(encoding="utf-8"))
        self.assertEqual(terminal["stopped_reason"], real_link.TIMEOUT_STOP)

    def test_budget_truncation_records_failed_run(self):
        transport = FakeTransport(exc=RuntimeError("boom"))
        result, _ = self.run_batch(transport, budget=1)       # 首个请求已耗尽预算，重试被截断
        self.assertEqual(len(transport.calls), 1)
        self.assertEqual(result["stopped_reason"], real_link.BUDGET_EXHAUSTED)
        rows = b2.query(self.cfg["db_path"], "SELECT status, error_summary FROM run_record")
        self.assertTrue(any(row["status"] == "failed"
                            and real_link.BUDGET_EXHAUSTED in (row["error_summary"] or "") for row in rows))
        self.assertTrue([line for line in self.audit_lines() if line.get("event") == "truncated"])

    def test_batch_result_file_written(self):
        result, _ = self.run_batch(FakeTransport())
        terminal = json.loads(pathlib.Path(result["result_path"]).read_text(encoding="utf-8"))
        self.assertEqual((terminal["batch_id"], terminal["status"]), ("batch-test-1", "ok"))
        self.assertIsNone(terminal["stopped_reason"])
        self.assertEqual(terminal["imported"], 1)
        self.assertIn("terminal_reason=none", result["notes"])

    # ---------------------------------------------------------------- A: 配置校验（网络前，0 请求）
    def test_cfg_validation_before_network(self):
        for cfg in (None, {}, {"tz_offset_hours": "bad", "max_rows_per_batch": 5000},
                    {"tz_offset_hours": 8}, {"tz_offset_hours": 8, "max_rows_per_batch": 0}):
            transport = FakeTransport()
            with self.assertRaises(AppError) as ctx:
                real_link.run_real_batch(self.conn, ["BV1us8MzPEmn"], authorization=AUTH,
                                         run_dir=self.run_dir, cfg=cfg, transport=transport)
            self.assertEqual(ctx.exception.status, 422)
            self.assertEqual(transport.calls, [])                       # A：transport 0 次
            self.assertFalse((pathlib.Path(self.run_dir) / "audit.jsonl").exists())
            self.assertFalse((pathlib.Path(self.run_dir) / "batch_result.json").exists())

    # ---------------------------------------------------------------- B: deadline / transport timeout
    class _FakeResponse:
        status = 200

        def __init__(self, body: bytes):
            self._body = body

        def read(self, _n=None):
            return self._body

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    def _patched_urlopen(self, body: bytes, timeouts: list):
        def fake(url, timeout=None, **kwargs):
            timeouts.append(timeout)
            return self._FakeResponse(body)
        return fake

    def test_default_transport_timeout_clamped_to_remaining(self):
        from unittest import mock
        raw = json.dumps(ok_payload()["payload"]).encode("utf-8")
        timeouts = []
        with mock.patch.object(real_link.urllib.request, "urlopen",
                               side_effect=self._patched_urlopen(raw, timeouts)):
            result, _ = self.run_batch(None, timeout_seconds=600.0)
        self.assertEqual(result["status"], "ok")
        self.assertEqual(len(timeouts), 1)
        self.assertLessEqual(timeouts[0], 600.0)
        self.assertLessEqual(timeouts[0], 10.0)                         # min(10, remaining)

    def test_remaining_non_positive_never_calls_transport(self):
        from unittest import mock
        clock = Clock()
        clock.tick = 1.0                                                # 每次读时钟前进 1 秒
        raw = json.dumps(ok_payload()["payload"]).encode("utf-8")
        timeouts = []
        with mock.patch.object(real_link.urllib.request, "urlopen",
                               side_effect=self._patched_urlopen(raw, timeouts)):
            result, _ = self.run_batch(None, timeout_seconds=0.5, clock=clock)
        self.assertEqual(timeouts, [])                                  # 剩余<=0：绝不调用
        self.assertEqual(result["stopped_reason"], real_link.TIMEOUT_STOP)
        self.assertEqual(result["summary_counts"]["unrequested"], 1)

    # ---------------------------------------------------------------- C: 停止分类与逐目标对账
    def test_unrequested_target_is_not_failed_run(self):
        transport = FakeTransport()
        result, _ = self.run_batch(transport, bvids=("BV1us8MzPEmn", "BV1GJ411x7h7"), budget=1)
        self.assertEqual(len(transport.calls), 1)
        self.assertEqual(result["summary_counts"], {"attempted": 1, "succeeded": 1,
                                                    "failed": 0, "unrequested": 1})
        self.assertEqual([item["unrequested"] for item in result["target_summary"]], [False, True])
        rows = b2.query(self.cfg["db_path"], "SELECT status FROM run_record")
        self.assertEqual([row["status"] for row in rows], ["ok"])      # 未执行目标不伪造失败 run

    # ---------------------------------------------------------------- 2) 对账不变量
    def assert_reconcile(self, result):
        counts = result["summary_counts"]
        self.assertEqual(counts["attempted"] + counts["unrequested"], len(result["targets"]))
        self.assertEqual(counts["succeeded"] + counts["failed"], counts["attempted"])
        self.assertEqual(counts["succeeded"], len(result["imported"]))

    def test_reconcile_duplicate_bvid_budget_one(self):
        transport = FakeTransport()
        bvids = ("BV1us8MzPEmn",) * 3
        result, _ = self.run_batch(transport, bvids=bvids, budget=1)
        self.assertEqual(len(transport.calls), 1)
        self.assertEqual(result["summary_counts"], {"attempted": 1, "succeeded": 1,
                                                    "failed": 0, "unrequested": 2})
        self.assertEqual([e["index"] for e in result["target_summary"]], [0, 1, 2])
        self.assertEqual([e["unrequested"] for e in result["target_summary"]], [False, True, True])
        self.assert_reconcile(result)

    def test_reconcile_single_target_mapping_failure(self):
        from unittest import mock
        with mock.patch.object(real_link, "_build_real_row",
                               side_effect=AppError("boom", code="invalid_field", status=422)):
            result, _ = self.run_batch(FakeTransport())
        entry = result["target_summary"][0]
        self.assertEqual((entry["attempted"], entry["succeeded"], entry["failed"]), (True, False, True))
        self.assertTrue(entry["error"])
        self.assert_reconcile(result)

    # ---------------------------------------------------------------- 1) D：导入失败/HTTP 非成功/审计写失败
    def test_d_import_sqlite_error_marks_failed(self):
        import sqlite3
        from unittest import mock
        with mock.patch.object(real_link.importer, "handle_import",
                               side_effect=sqlite3.OperationalError("disk I/O error")):
            result, _ = self.run_batch(FakeTransport())
        self.assertEqual(result["status"], "failed")
        self.assertIn("导入SQL异常", json.dumps(result["failed_imports"], ensure_ascii=False))
        b2.query(self.cfg["db_path"], "SELECT 1")
        failed = self._failed_run_records()
        self.assertTrue(any("导入SQL异常" in (row["error_summary"] or "") for row in failed))

    def test_d_non_success_http_code_is_failure(self):
        transport = FakeTransport(fail_bvids=("BV1us8MzPEmn",))
        result, _ = self.run_batch(transport, budget=3)
        self.assertEqual(len(transport.calls), 1)                 # rate_limited 不重试
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["summary_counts"]["failed"], 1)
        self.assertTrue(self._failed_run_records())

    def test_d_mixed_success_and_failure_summary(self):
        transport = FakeTransport(fail_bvids=("BV1GJ411x7h7",))
        result, _ = self.run_batch(transport, bvids=("BV1us8MzPEmn", "BV1GJ411x7h7"), budget=3)
        self.assertEqual(result["status"], "partial")
        self.assertEqual(result["summary_counts"], {"attempted": 2, "succeeded": 1,
                                                    "failed": 1, "unrequested": 0})
        self.assert_reconcile(result)

    def test_d_audit_write_failure_propagates_without_recursive_run(self):
        from unittest import mock
        before = self._failed_run_records()
        with mock.patch.object(real_link, "_audit", side_effect=OSError("audit disk full")):
            with self.assertRaises(OSError):
                self.run_batch(FakeTransport())
        self.assertEqual(self._failed_run_records(), before)      # 不递归重记

    def _failed_run_records(self):
        return [row for row in b2.query(self.cfg["db_path"],
                                        "SELECT status, error_summary FROM run_record")
                if row["status"] == "failed"]

    # ---------------------------------------------------------------- 3) timeout 不抬高下限
    def test_timeout_uses_remaining_without_floor(self):
        from unittest import mock
        raw = json.dumps(ok_payload()["payload"]).encode("utf-8")
        timeouts = []
        with mock.patch.object(real_link.urllib.request, "urlopen",
                               side_effect=self._patched_urlopen(raw, timeouts)):
            result, _ = self.run_batch(None, timeout_seconds=0.2)
        self.assertEqual(result["status"], "ok")
        self.assertEqual(len(timeouts), 1)
        self.assertLessEqual(timeouts[0], 0.2 + 1e-9)   # 浮点误差内不超过 remaining

    def test_remaining_below_threshold_never_calls(self):
        from unittest import mock
        clock = Clock()
        clock.tick = 0.001
        timeouts = []
        with mock.patch.object(real_link.urllib.request, "urlopen",
                               side_effect=self._patched_urlopen(b"{}", timeouts)):
            result, _ = self.run_batch(None, timeout_seconds=0.0005, clock=clock)
        self.assertEqual(timeouts, [])
        self.assertEqual(result["stopped_reason"], real_link.TIMEOUT_STOP)
        self.assert_reconcile(result)

    def test_interval_crossing_deadline_blocks_second_request(self):
        clock = Clock()
        clock.jump[5.0] = 700.0                                    # 5s 间隔等待跨越 600s deadline
        transport = FakeTransport()
        result, _ = self.run_batch(transport, bvids=("BV1us8MzPEmn", "BV1GJ411x7h7"),
                                   budget=3, timeout_seconds=600.0, clock=clock)
        self.assertEqual(len(transport.calls), 1)
        self.assertEqual(result["stopped_reason"], real_link.TIMEOUT_STOP)
        self.assertEqual(result["summary_counts"]["unrequested"], 1)
        self.assert_reconcile(result)

    # ---------------------------------------------------------------- A1/A2/B1/B2 回归（独立复核报告 §3）
    class SequenceTransport:
        def __init__(self, outcomes):
            self.outcomes = list(outcomes)
            self.calls = []

        def __call__(self, url):
            self.calls.append(url)
            bvid = real_link._bvid_from_url(url)
            outcome = self.outcomes.pop(0) if self.outcomes else "ok"
            if outcome == "ok":
                return ok_payload(bvid)
            return {"http_status": 412, "payload": {"code": -412, "message": "risk"}, "error": None}

    def test_a1_index_attribution_middle_failure(self):
        transport = self.SequenceTransport(["ok", "rate_limited", "ok"])
        result, _ = self.run_batch(transport, bvids=("BV1us8MzPEmn",) * 3, budget=3)
        got = [[entry["succeeded"], entry["failed"]] for entry in result["target_summary"]]
        self.assertEqual(got, [[True, False], [False, True], [True, False]])   # 每 index 归属正确
        self.assertEqual(result["summary_counts"],
                         {"attempted": 3, "succeeded": 2, "failed": 1, "unrequested": 0})
        self.assert_reconcile(result)
        self.assertEqual([entry["index"] for entry in result["target_summary"]], [0, 1, 2])

    def test_a2_index_attribution_import_rejected_first(self):
        from unittest import mock
        bvid = "BV1us8MzPEmn"
        original = real_link.importer.handle_import
        calls = {"n": 0}

        def fake(conn, cfg, **kwargs):
            calls["n"] += 1
            if calls["n"] == 1:
                return {"rows": []}, 422, None
            return original(conn, cfg, **kwargs)

        with mock.patch.object(real_link.importer, "handle_import", side_effect=fake):
            result, _ = self.run_batch(FakeTransport(), bvids=(bvid, bvid), budget=3)
        got = [[entry["succeeded"], entry["failed"]] for entry in result["target_summary"]]
        self.assertEqual(got, [[False, True], [True, False]])                  # 位置 0 导入失败、位置 1 成功
        self.assertEqual(result["summary_counts"]["succeeded"], len(result["imported"]))
        self.assert_reconcile(result)

    def test_b1_record_failure_error_not_double_counted(self):
        import sqlite3
        from unittest import mock
        with mock.patch.object(real_link.importer, "handle_import",
                               return_value=({"rows": []}, 422, None)), \
             mock.patch.object(real_link.wiring, "record_failure",
                               side_effect=[sqlite3.OperationalError("audit io"), None]) as recorder:
            with self.assertRaises(sqlite3.OperationalError):
                self.run_batch(FakeTransport())
        self.assertEqual(recorder.call_count, 1)          # 单次调用；异常冒泡、不二次记账
        self.assertEqual(self._failed_run_records(), [])  # 审计写失败：无 run_record

    def test_b2_record_failure_always_raising_bubbles_once(self):
        import sqlite3
        from unittest import mock
        with mock.patch.object(real_link.importer, "handle_import",
                               return_value=({"rows": []}, 422, None)), \
             mock.patch.object(real_link.wiring, "record_failure",
                               side_effect=sqlite3.OperationalError("audit io")) as recorder:
            with self.assertRaises(sqlite3.OperationalError):
                self.run_batch(FakeTransport())
        self.assertEqual(recorder.call_count, 1)          # 不递归、不多次尝试

    # ---------------------------------------------------------------- 真实/合成共存
    def test_real_and_synthetic_coexist(self):
        self.run_batch(FakeTransport())
        body = json.dumps([{"title": "示例-合成共存", "data_origin": "synthetic", "demand_source": "xianyu",
                            "demand_url": "https://example.com/demand/real-syn", "demand_excerpt": "合成摘录",
                            "observed_at": "2026-06-01T08:00:00Z"}], ensure_ascii=False).encode("utf-8")
        payload, code, _ = importer.handle_import(self.conn, self.cfg, fmt="json", body=body,
                                                  filename="syn.json", mode="atomic", format_version=1,
                                                  client_ref=None)
        self.assertEqual(code, 201, payload)
        rows = b2.query(self.cfg["db_path"], "SELECT data_origin FROM demand_signal ORDER BY rowid")
        self.assertEqual({row["data_origin"] for row in rows}, {"real", "synthetic"})


if __name__ == "__main__":
    unittest.main()
