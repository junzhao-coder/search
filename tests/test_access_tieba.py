"""贴吧离线入口测试：doctor 只读、预算预扣与跨实例累计、风险锁、解析导出、unsupported。"""

from __future__ import annotations

import json
import pathlib
import socket
import tempfile
import unittest
from unittest import mock

from tools.selection.access import codes
from tools.selection.access import platform_budget as pb
from tools.selection.access import records as rec
from tools.selection.access import tieba


COLLECTED = "2026-10-30T00:00:00Z"


class TiebaBase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = pathlib.Path(self._tmp.name)
        self.ledger_path = self.dir / "platform_tieba.sqlite3"
        self._ledgers = []

    def tearDown(self):
        for led in self._ledgers:
            try:
                led.close()
            except Exception:
                pass
        self._tmp.cleanup()

    def ledger(self, clock=None):
        led = tieba.open_ledger(self.ledger_path, clock=clock)
        self._ledgers.append(led)
        return led


class DoctorTests(TiebaBase):
    def test_doctor_is_local_and_offline(self):
        with mock.patch.object(socket, "create_connection",
                               side_effect=AssertionError("must not touch network")):
            out = tieba.doctor(self.dir / "missing-profile")
        self.assertEqual(out["network"], "none")
        self.assertFalse(out["profile_exists"])
        self.assertFalse(out["cookie_db_exists"])
        self.assertEqual(out["cookie_count"], 0)
        self.assertTrue(all(v is False for v in out["cookie_names"].values()))
        self.assertNotIn("BDUSS=", json.dumps(out))          # 只有名称布尔
        self.assertEqual(out["site"], "tieba")


class LedgerTests(TiebaBase):
    def test_precharge_and_cross_instance_accumulation(self):
        led = self.ledger()
        led.authorize_batch("b1", authorized_calls=3, window_seconds=300,
                            source="test", note="")
        led.charge("b1", "search", detail="kw")
        summary = led.summary("b1")
        self.assertEqual(summary["used"], 1)
        self.assertEqual(summary["remaining"], 2)
        again = self.ledger()                                 # 新实例，同一文件
        summary2 = again.summary("b1")
        self.assertEqual(summary2["used"], 1)                 # 换进程也不重置
        again.close()

    def test_interval_is_enforced(self):
        led = self.ledger()
        led.authorize_batch("b2", authorized_calls=3, window_seconds=300,
                            source="test")
        led.charge("b2", "search")
        with self.assertRaises(tieba.TiebaBudgetError) as caught:
            led.charge("b2", "search")
        self.assertIn("interval", caught.exception.code)

class RiskLockTests(TiebaBase):
    def test_risk_marker_locks_site(self):
        led = self.ledger()
        led.authorize_batch("b3", authorized_calls=3, window_seconds=300, source="test")
        reason = tieba.risk_reason(text="请完成验证后继续")
        self.assertTrue(reason)
        led.lock(reason, source="test")
        locked, why = led.locked()
        self.assertTrue(locked)
        self.assertEqual(why, reason)
        with self.assertRaises(tieba.TiebaBudgetError):
            led.charge("b3", "search")
    def test_http_status_risk(self):
        self.assertEqual(tieba.risk_reason(http_status=429), "http_429")
        self.assertIsNone(tieba.risk_reason(text="正常的帖子标题"))


class ParseTests(TiebaBase):
    HTML = ('<html><head><title>学习计划吧-百度贴吧</title></head><body>'
            '<a href="/p/1234567890">帖子一</a><a href="/p/8765432109">帖子二</a>'
            '</body></html>')

    def test_search_parses_thread_links(self):
        out = tieba.parse_search_html(self.HTML, collected_at=COLLECTED)
        self.assertEqual(out["stop"], "records")
        self.assertEqual([r["native_id"] for r in out["records"]],
                         ["1234567890", "8765432109"])
        self.assertTrue(all(r["url"].startswith("https://tieba.baidu.com/p/")
                            for r in out["records"]))
        self.assertEqual(out["anchors_total"], 2)

    def test_search_empty_is_explicit(self):
        out = tieba.parse_search_html("<html>没有找到相关内容</html>",
                                      collected_at=COLLECTED)
        self.assertEqual(out["stop"], "empty")
        self.assertEqual(out["records"], [])

    def test_detail_uses_title(self):
        out = tieba.parse_thread_html(self.HTML, "https://tieba.baidu.com/p/1234567890",
                                      collected_at=COLLECTED)
        self.assertIsNone(out["stop"])
        self.assertEqual(out["record"]["native_id"], "1234567890")
        self.assertEqual(out["record"]["title"], "学习计划吧-百度贴吧")

    def test_detail_rejects_foreign_url(self):
        out = tieba.parse_thread_html(self.HTML, "https://evil.example.com/p/1234567890",
                                      collected_at=COLLECTED)
        self.assertEqual(out["stop"], "unsupported_content_url")


class UnsupportedTests(TiebaBase):
    def test_comments_is_explicitly_unsupported_before_charge(self):
        out = tieba.comments("https://tieba.baidu.com/p/1", batch=None)
        self.assertEqual(out["status"], "unsupported")
        self.assertEqual(out["stop"], "unsupported_endpoint")
        self.assertFalse(out["charged"])
        self.assertEqual(out["records"], [])

    def test_login_offline_reports_unknown(self):
        out = tieba.login(self.dir / "profile")
        self.assertEqual(out["status"], "unknown")
        self.assertEqual(out["stop"], "unsupported_offline")
        self.assertEqual(out["network"], "none")


class NotApplicableTests(TiebaBase):
    def test_thread_record_marks_structural_na(self):
        out = tieba.parse_thread_html("<html><title>t</title></html>",
                                      "https://tieba.baidu.com/p/1234567890",
                                      collected_at=COLLECTED)
        record = out["record"]
        for field in ("root_comment_id", "parent_id", "voteup", "reposts"):
            self.assertIn(field, record["not_applicable"])
            self.assertNotIn(field, record["missing"])
        self.assertIn("text", record["missing"])            # 真没读到


class ExportTests(TiebaBase):
    def test_export_keeps_whitelist_only(self):
        src = self.dir / "in.jsonl"
        row = {"native_id": "1", "type": "thread", "url": "https://tieba.baidu.com/p/1",
               "nickname": "SECRET", "cookies": {"BDUSS": "x"}}
        src.write_text(json.dumps(row, ensure_ascii=False) + "\n", encoding="utf-8")
        out = tieba.export(src, self.dir / "out.jsonl")
        self.assertTrue(out["ok"])
        self.assertEqual(out["count"], 1)
        self.assertIn("nickname", out["dropped_keys"])
        self.assertIn("cookies", out["dropped_keys"])
        text = (self.dir / "out.jsonl").read_text(encoding="utf-8")
        self.assertNotIn("SECRET", text)
        written = json.loads(text.splitlines()[0])
        self.assertTrue(set(written) <= set(rec.EXPORT_FIELDS))

    def test_export_columns_include_not_applicable(self):
        self.assertIn("not_applicable", rec.EXPORT_FIELDS)
        self.assertIn("root_comment_id", rec.FIELDS)


class ExitCodeTests(TiebaBase):
    def test_codes_are_reused(self):
        self.assertEqual(tieba.EXIT_OK, codes.EXIT_OK)
        self.assertEqual(codes.EXIT_UNSUPPORTED != codes.EXIT_OK, True)


if __name__ == "__main__":
    unittest.main()
