"""S3 offline wiring tests — design matrix S3W-01..S3W-21 (docs/design/S3_WIRING_SPEC.md §8).

No network: the reader transport is an offline fixture (real excerpt + synthetic failure samples).
The adapter module is not modified; wiring only maps records into the existing import pipeline.
"""

from __future__ import annotations

import copy
import datetime as dt
import json
import pathlib
import sqlite3
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app import create_app  # noqa: E402
from app.core import importer  # noqa: E402
from app.core.errors import AppError  # noqa: E402
from app.sources import wiring  # noqa: E402
from app.sources.bilibili_view import BilibiliViewReader  # noqa: E402
from app.storage.db import connect  # noqa: E402

TMP_ROOT = pathlib.Path(__file__).resolve().parent / "_tmp"
FIXTURE_DIR = ROOT / "tests" / "fixtures" / "sources"
OK_TRANSPORT = json.loads((FIXTURE_DIR / "bilibili_view_ok_BV1us8MzPEmn.json").read_text(encoding="utf-8"))["transport"]
FAILURES = json.loads((FIXTURE_DIR / "bilibili_view_failures.json").read_text(encoding="utf-8"))["cases"]
BVID = "BV1us8MzPEmn"
VALID_AT = "2026-06-01T08:00:00Z"
FIXED_CLOCK = 1780000000.0          # 固定时钟：回退时间戳确定性，便于断言"未被 DB now 覆盖"
FALLBACK_STAMP = dt.datetime.fromtimestamp(FIXED_CLOCK, dt.timezone(dt.timedelta(hours=8))) \
    .isoformat(timespec="seconds")
FORBIDDEN_IMPORTS = ("import requests", "import http.client", "from http.client", "urllib.request")


def reader(payload=None, *, clock=None, case=None):
    calls: list[str] = []

    def transport(url: str):
        calls.append(url)
        if case is not None:
            return copy.deepcopy(FAILURES[case])
        return copy.deepcopy(payload if payload is not None else OK_TRANSPORT)

    instance = BilibiliViewReader(transport, clock=(clock or (lambda: FIXED_CLOCK)))
    return instance, calls


def changed(**data_overrides):
    payload = copy.deepcopy(OK_TRANSPORT)
    payload["payload"]["data"].update(data_overrides)
    return payload


class WiringOfflineTest(unittest.TestCase):
    def setUp(self):
        TMP_ROOT.mkdir(parents=True, exist_ok=True)
        self.tmp = tempfile.mkdtemp(prefix="wire_", dir=str(TMP_ROOT))
        self.db_path = str(pathlib.Path(self.tmp) / "app.db")
        self.app = create_app({"db_path": self.db_path})
        self.client = self.app.test_client()
        self.cfg = self.app.config["APP_CFG"]

    # ---------------- helpers
    def complete(self, *, payload=None, clock=None, case=None, observed_at=VALID_AT, target=BVID):
        instance, calls = reader(payload, clock=clock, case=case)
        conn = connect(self.db_path)
        try:
            result = wiring.complete_known_object(conn, self.cfg, reader=instance, target=target,
                                                  observed_at=observed_at)
        finally:
            conn.close()
        return result, calls

    def counts(self, *tables: str) -> dict:
        conn = connect(self.db_path)
        try:
            return {t: conn.execute(f"SELECT COUNT(*) AS n FROM {t}").fetchone()["n"] for t in tables}
        finally:
            conn.close()

    def query(self, sql: str, params=()):
        conn = connect(self.db_path)
        try:
            return [dict(r) for r in conn.execute(sql, params).fetchall()]
        finally:
            conn.close()

    def execute(self, sql: str, params=()):
        conn = connect(self.db_path)
        try:
            conn.execute(sql, params)
        finally:
            conn.close()

    def single_import(self):
        result, _ = self.complete()
        self.assertTrue(result["ok"], result)
        return self.query("SELECT id FROM candidate")[0]["id"]

    # ---------------- S3W-01 / 02 / 03 / 04
    def test_s3w01_success_mapping_evidence_and_run(self):
        result, calls = self.complete()
        self.assertTrue(result["ok"], result)
        self.assertEqual(len(calls), 1)
        self.assertEqual(result["counts"], {"created": 1, "duplicate_skipped": 0, "version_added": 0,
                                            "suspect_review": 0, "rejected": 0, "warning": 0})
        candidate = self.query("SELECT id, title, status, identity_key, data_origin FROM candidate")[0]
        self.assertEqual(candidate["status"], "pending")
        self.assertEqual(candidate["identity_key"], f"n:bilibili:{BVID}")
        self.assertEqual(candidate["data_origin"], "synthetic")
        signal = self.query("SELECT version_no, observed_at, observed_at_source, content_hash, signal_kind,"
                            " url, superseded_by FROM demand_signal")[0]
        self.assertEqual(signal["version_no"], 1)
        self.assertEqual(signal["observed_at"], VALID_AT)
        self.assertEqual(signal["observed_at_source"], "source")
        self.assertEqual(signal["signal_kind"], "other")
        self.assertIsNone(signal["superseded_by"])
        self.assertEqual(self.counts("evidence", "import_batch")["evidence"], 1)
        # 干净成功不得产生任何 stray/元数据告警（D 复验缺陷：适配器键被误判为“非需求字段”）
        self.assertEqual(self.query("SELECT COUNT(*) AS n FROM import_row_result WHERE action='warning'")[0]["n"], 0)
        run = self.query("SELECT run_type, source_id, status, items_found, items_new, items_dup"
                         " FROM run_record")[0]
        self.assertEqual(run, {"run_type": "import", "source_id": "s_bili", "status": "ok",
                               "items_found": 1, "items_new": 1, "items_dup": 0})

    def test_s3w02_replay_is_duplicate_and_refreshes_last_seen(self):
        self.single_import()
        self.execute("UPDATE demand_signal SET last_seen_at=?", ("2020-01-01T00:00:00Z",))
        before = self.counts("candidate", "demand_signal", "evidence")
        result, _ = self.complete()
        self.assertTrue(result["ok"])
        self.assertEqual(result["counts"]["duplicate_skipped"], 1)
        self.assertEqual(self.counts("candidate", "demand_signal", "evidence"), before)
        self.assertNotEqual(self.query("SELECT last_seen_at FROM demand_signal")[0]["last_seen_at"],
                            "2020-01-01T00:00:00Z")

    def test_s3w03_content_change_adds_version_with_faithful_counts(self):
        self.single_import()
        result, _ = self.complete(payload=changed(desc="新的第二版摘要内容，用于版本判定"))
        self.assertTrue(result["ok"], result)
        self.assertEqual(result["counts"]["version_added"], 1)
        rows = self.query("SELECT id, version_no, superseded_by FROM demand_signal ORDER BY version_no")
        self.assertEqual([r["version_no"] for r in rows], [1, 2])
        self.assertEqual(rows[0]["superseded_by"], rows[1]["id"])
        self.assertEqual(self.query("SELECT rows_version_added, rows_created FROM import_batch"
                                    " ORDER BY rowid DESC")[0],
                         {"rows_version_added": 1, "rows_created": 0})
        self.assertEqual(self.query("SELECT items_new FROM run_record ORDER BY rowid DESC")[0]["items_new"], 0)

    def test_s3w04_stat_only_change_stays_duplicate(self):
        self.single_import()
        before = self.counts("demand_signal")
        result, _ = self.complete(payload=changed(stat={"view": 999999, "like": 51}))
        self.assertTrue(result["ok"])
        self.assertEqual(result["counts"]["duplicate_skipped"], 1)
        self.assertEqual(self.counts("demand_signal"), before)

    # ---------------- S3W-05 观察时间保真
    def test_s3w05_illegal_observed_at_keeps_adapter_fallback_stamp(self):
        result, _ = self.complete(observed_at="2026-06-01 08:00:00")          # 无时区 → 非法
        self.assertTrue(result["ok"], result)
        signal = self.query("SELECT observed_at, observed_at_source FROM demand_signal")[0]
        self.assertEqual(signal["observed_at_source"], "import_time")
        self.assertEqual(signal["observed_at"], FALLBACK_STAMP)               # 适配器时间戳，不是 DB now
        warnings = self.query("SELECT reason_code, reason_detail FROM import_row_result"
                              " WHERE action='warning'")
        self.assertIn(("S3_OBSERVED_AT_REJECTED", "观察时间原值被拒：2026-06-01 08:00:00"),
                      [(w["reason_code"], w["reason_detail"]) for w in warnings])

    # ---------------- S3W-06 / 07 / 08 失败与拒绝
    def test_s3w06_rate_limited_failure_writes_no_business_row(self):
        result, _ = self.complete(case="rate_limited_412")
        self.assertFalse(result["ok"])
        self.assertEqual(self.counts("candidate", "demand_signal", "evidence", "import_batch"),
                         {"candidate": 0, "demand_signal": 0, "evidence": 0, "import_batch": 0})
        run = self.query("SELECT status, items_found, items_new, items_dup, error_summary, notes"
                         " FROM run_record")[0]
        self.assertEqual(run["status"], "failed")
        self.assertEqual((run["items_found"], run["items_new"], run["items_dup"]), (0, 0, 0))
        self.assertIn("http=412", run["error_summary"])
        self.assertIn("技术默认值", run["notes"])
        self.assertIn("不代表已观测的零需求", run["notes"])

    def test_s3w07_login_timeout_and_html_shell_fail_without_rows(self):
        for case in ("login_redirect_200", "timeout", "html_shell", "missing_62002"):
            with self.subTest(case=case):
                result, _ = self.complete(case=case)
                self.assertFalse(result["ok"])
        self.assertEqual(self.counts("candidate", "demand_signal", "evidence", "import_batch"),
                         {"candidate": 0, "demand_signal": 0, "evidence": 0, "import_batch": 0})
        self.assertEqual(self.counts("run_record")["run_record"], 4)

    def test_s3w08_long_title_is_refused_without_truncation(self):
        long_title = "长" * 301
        result, _ = self.complete(payload=changed(title=long_title))
        self.assertFalse(result["ok"])
        self.assertIn("title_too_long", result["reason"])
        self.assertEqual(self.counts("candidate", "demand_signal")["candidate"], 0)
        self.assertEqual(self.query("SELECT COUNT(*) AS n FROM candidate WHERE title=?", (long_title,))[0]["n"], 0)
        self.assertEqual(self.query("SELECT length(title) AS n FROM candidate")[0]["n"] if
                         self.counts("candidate")["candidate"] else 0, 0)

    # ---------------- S3W-09 / 10 URL 两阶段
    def test_s3w09_synthetic_url_is_example_domain_only(self):
        self.single_import()
        signal = self.query("SELECT url, url_norm, data_origin FROM demand_signal")[0]
        self.assertEqual(signal["url"], f"https://example.org/bilibili/video/{BVID}")
        self.assertTrue(signal["url_norm"].startswith("https://example.org/"))
        self.assertNotIn("bilibili.com", signal["url"])
        self.assertNotIn("bilibili.com", signal["url_norm"])
        self.assertEqual(signal["data_origin"], "synthetic")

    def test_s3w10_validation_layer_rejects_real_url_for_synthetic_row(self):
        row = {"title": "示例-违规URL", "data_origin": "synthetic", "demand_source": "bilibili",
               "demand_native_id": BVID, "demand_url": f"https://www.bilibili.com/video/{BVID}/",
               "demand_excerpt": "摘录"}
        conn = connect(self.db_path)
        try:
            payload, status, _ = importer.handle_import(
                conn, self.cfg, fmt="json", body=json.dumps([row]).encode("utf-8"), filename="x.json",
                mode="atomic", format_version=1, client_ref=None, run_source_id="s_bili")
        finally:
            conn.close()
        self.assertEqual(status, 422)
        self.assertEqual(payload["status"], "rejected")
        self.assertEqual(self.counts("candidate")["candidate"], 0)
        self.assertGreaterEqual(self.counts("import_batch")["import_batch"], 1)   # 批次与行原因保留

    # ---------------- S3W-11 低层导入的来源/origin 隔离（不开放 wiring 可变 source）
    def test_s3w11_origin_and_source_isolation_is_import_level(self):
        def row(source, origin, url):
            return {"title": f"示例-{source}", "data_origin": origin, "demand_source": source,
                    "demand_native_id": "1001", "demand_url": url, "demand_excerpt": "求模板"}
        rows = [row("xianyu", "synthetic", "https://example.com/demand/a"),
                row("bilibili", "synthetic", "https://example.com/demand/b"),
                row("xianyu", "real", "https://www.goofish.com/item/1001")]
        conn = connect(self.db_path)
        try:
            progress, status, _ = importer.handle_import(
                conn, self.cfg, fmt="json", body=json.dumps(rows, ensure_ascii=False).encode("utf-8"),
                filename="x.json", mode="atomic", format_version=1, client_ref=None)
        finally:
            conn.close()
        self.assertEqual(status, 201, progress)
        self.assertEqual(self.counts("candidate")["candidate"], 3)
        self.assertEqual(self.counts("demand_signal")["demand_signal"], 3)
        self.assertEqual(sorted(r["data_origin"] for r in self.query("SELECT data_origin FROM candidate")),
                         ["real", "synthetic", "synthetic"])

    # ---------------- S3W-12 / 13 追溯与状态
    def test_s3w12_detail_and_sources_endpoint_unchanged(self):
        candidate_id = self.single_import()
        detail = self.client.get(f"/api/candidates/{candidate_id}").get_json()
        signal = detail["demand_signals"][0]
        self.assertEqual(signal["observed_at_source"], "source")
        self.assertTrue(signal["content_hash"])
        self.assertEqual(signal["version_no"], 1)
        sources = {row["name"]: row for row in self.client.get("/api/sources").get_json()["items"]}
        for name in ("manual_import", "xianyu", "xiaohongshu", "bilibili"):
            self.assertEqual(sources[name]["access_mode"], "manual_import")
            self.assertEqual(sources[name]["access_verified"], "yes")
            self.assertIsNone(sources[name]["last_success_at"])

    def test_s3w13_new_candidate_pending_and_override_untouched(self):
        """状态语义：沿用既有派生/override，不新增门槛；已核验 testable 的保持由联合门槛套件覆盖。"""
        candidate_id = self.single_import()
        self.assertEqual(self.query("SELECT status FROM candidate")[0]["status"], "pending")
        gates_before = self.counts("gate_review")["gate_review"]
        self.execute("UPDATE candidate SET manual_override='archived', override_reason='示例', override_at=?"
                     " WHERE id=?", (VALID_AT, candidate_id))
        self.complete(payload=changed(desc="第二版用于触发一次成功导入"))
        state = self.query("SELECT status, manual_override FROM candidate")[0]
        self.assertEqual(state["manual_override"], "archived")                 # 人工标记不被覆盖
        self.assertEqual(state["status"], "archived")                          # 既有派生尊重 override
        self.assertEqual(self.counts("gate_review")["gate_review"], gates_before)   # 门槛零新增

    # ---------------- S3W-14 / 15 网络与默认路径
    def test_s3w14_no_network_and_no_http_client_in_modules(self):
        result, calls = self.complete()
        self.assertTrue(result["ok"])
        self.assertEqual(len(calls), 1)                                     # 仅注入的假 transport
        self.assertTrue(calls[0].startswith("https://api.bilibili.com/x/web-interface/view"))
        _, invalid_calls = self.complete(target="https://evil.example.com/video/" + BVID)
        self.assertEqual(invalid_calls, [])                                 # 非法目标不打网络
        for module in (pathlib.Path(wiring.__file__), pathlib.Path(importer.__file__).parent / ".." / "sources"
                       / "bilibili_view.py"):
            text = pathlib.Path(module).resolve().read_text(encoding="utf-8")
            for token in FORBIDDEN_IMPORTS:
                self.assertNotIn(token, text, f"{module} 不应引入 HTTP 客户端")

    def test_s3w15_default_import_path_is_unaffected(self):
        from tests.api.b2_helpers import DEFAULT_COSTS  # noqa: F401  (仅证明公共路径可正常导入)

        row = {"title": "示例-默认路径", "data_origin": "synthetic", "demand_source": "bilibili",
               "demand_native_id": "BV1default001", "demand_url": "https://example.com/demand/default",
               "demand_excerpt": "摘录", "observed_at": VALID_AT}
        conn = connect(self.db_path)
        try:
            _, status, _ = importer.handle_import(
                conn, self.cfg, fmt="json", body=json.dumps([row], ensure_ascii=False).encode("utf-8"),
                filename="plain.json", mode="atomic", format_version=1, client_ref=None)
        finally:
            conn.close()
        self.assertEqual(status, 201)
        signal = self.query("SELECT observed_at, observed_at_source FROM demand_signal")[0]
        self.assertEqual((signal["observed_at"], signal["observed_at_source"]), (VALID_AT, "source"))
        self.assertEqual(self.query("SELECT COUNT(*) AS n FROM import_row_result WHERE action='warning'")[0]["n"], 0)
        self.assertEqual(self.query("SELECT source_id FROM run_record")[0]["source_id"], None)   # 缺省仍 NULL

    # ---------------- S3W-16 S4 联合回归
    def test_s3w16_s4_default_and_explicit_assumption_still_work(self):
        from tests.api.b2_helpers import add_default_costs, seed_full

        result, _ = self.complete()
        self.assertTrue(result["ok"])
        candidate_id, supply_id = seed_full(self.client, "示例-S4联合回归")
        specs = (
            {"role": "sale_price", "basis": "per_order", "value_kind": "money", "money_minor": 1000},
            {"role": "procurement", "basis": "per_order", "value_kind": "money", "money_minor": 300},
            {"role": "procurement", "basis": "one_time", "value_kind": "money", "money_minor": 0},
            {"role": "platform_fee", "basis": "per_order", "value_kind": "rate", "rate_bp": 500},
            {"role": "payment_fee", "basis": "per_order", "value_kind": "rate", "rate_bp": 0},
            {"role": "acquisition", "basis": "per_order", "value_kind": "money", "money_minor": 0},
            {"role": "refund_reserve", "basis": "per_order", "value_kind": "rate", "rate_bp": 0},
            {"role": "other", "basis": "per_order", "value_kind": "money", "money_minor": 0},
            {"role": "manual_labor", "basis": "per_order", "value_kind": "minutes", "minutes": 10,
             "hourly_rate_minor": 3000},
            {"role": "procurement", "basis": "recurring", "value_kind": "money", "money_minor": 10001,
             "period": "quarterly"},
        )
        add_default_costs(self.client, candidate_id, supply_id, specs=specs)
        default = self.client.get(f"/api/candidates/{candidate_id}/scenario?variant=base").get_json()
        self.assertIsNone(default["amortize_orders"])
        self.assertFalse(default["normalized_periods"])
        self.assertEqual(default["one_time_per_order_minor"], 0)                # 显式零 → 0（已验收口径）
        self.assertIsNone(default["recurring_per_order_minor"])
        self.assertIsNone(default["net_per_order_minor"])                       # 默认路径不完整 → 不输出净值
        body = self.client.get(f"/api/candidates/{candidate_id}/scenario?variant=base"
                               f"&normalize_periods=1&monthly_orders=4").get_json()
        self.assertEqual(body["contribution_per_order_minor"], 150)
        self.assertEqual(body["recurring_monthly_total_minor"], 3334)
        self.assertEqual(body["recurring_per_order_minor"], 833)                # 由 a 取整，非 R/M=834
        self.assertEqual(body["net_per_order_minor"], 150 - 833)

    # ---------------- S3W-17 ABA 经接线
    def test_s3w17_revisit_through_wiring_keeps_chain(self):
        self.complete()
        self.complete(payload=changed(desc="B 版摘要"))
        before = self.counts("demand_signal", "evidence")
        result, _ = self.complete()
        self.assertTrue(result["ok"], result)
        self.assertEqual(result["counts"]["duplicate_skipped"], 1)
        self.assertEqual(self.counts("demand_signal", "evidence"), before)
        rows = self.query("SELECT version_no, superseded_by FROM demand_signal ORDER BY version_no")
        self.assertEqual([r["version_no"] for r in rows], [1, 2])
        self.assertEqual(rows[0]["superseded_by"], self.query("SELECT id FROM demand_signal WHERE version_no=2")[0]["id"])
        self.assertIsNone(rows[1]["superseded_by"])

    # ---------------- S3W-18 越权字段（互补可判别：干净无告警 / 越权有且点名）
    def test_s3w18_external_supply_cost_gate_keys_are_dropped(self):
        payload = copy.deepcopy(OK_TRANSPORT)
        instance = BilibiliViewReader(lambda url: payload)
        clean = instance.complete(BVID, observed_at=VALID_AT)
        _, clean_warnings = wiring.build_row(clean)
        self.assertEqual([code for code, _ in clean_warnings], [])          # 干净成功：零 stray 告警

        violation = dict(clean, supply_url="https://example.com/supply/x", supply_price=0,
                         procurement_unit_cost="0", gate_cost=True)
        row, warnings = wiring.build_row(violation)
        for key in ("supply_url", "supply_price", "procurement_unit_cost", "gate_cost"):
            self.assertNotIn(key, row)                                      # 不透传
        self.assertEqual([code for code, _ in warnings], ["S3_UNKNOWN_FIELDS"])
        named = warnings[0][1].split("：", 1)[1].split(",")
        self.assertEqual(sorted(named), ["gate_cost", "procurement_unit_cost", "supply_price", "supply_url"])
        self.assertEqual(self.counts("supply_offer", "cost_item", "gate_review"),
                         {"supply_offer": 0, "cost_item": 0, "gate_review": 0})

    # ---------------- S3W-19 内部参数规则
    def test_s3w19_internal_parameter_rules(self):
        base_row = {"title": "示例-内部参数", "data_origin": "synthetic", "demand_source": "bilibili",
                    "demand_native_id": "BV1internal01", "demand_url": "https://example.com/demand/i",
                    "demand_excerpt": "摘录"}
        two_rows = json.dumps([base_row, dict(base_row, title="示例-内部参数2")]).encode("utf-8")
        one_row = json.dumps([base_row]).encode("utf-8")
        cases = [
            (two_rows, {"observed_at": VALID_AT, "observed_at_source": "source"}),
            (one_row, {"observed_at": VALID_AT, "observed_at_source": "other"}),
            (one_row, {"observed_at": "2026-06-01 08:00:00", "observed_at_source": "import_time"}),
            (one_row, {"observed_at": VALID_AT, "observed_at_source": "source", "extra": 1}),
            (one_row, {"observed_at_source": "source"}),
            (one_row, {"observed_at": VALID_AT, "observed_at_source": "source"}),   # 行内 observed_at 为空 → 不一致
        ]
        conn = connect(self.db_path)
        try:
            for body, hint in cases:
                with self.subTest(hint=sorted(hint)):
                    with self.assertRaises(AppError):
                        importer.handle_import(conn, self.cfg, fmt="json", body=body, filename="i.json",
                                               mode="atomic", format_version=1, client_ref=None,
                                               internal_observation=hint)
            with self.assertRaises(AppError):
                importer.handle_import(conn, self.cfg, fmt="json", body=one_row, filename="i.json",
                                       mode="validate", format_version=1, client_ref=None,
                                       run_source_id="s_not_registered")
            final_row = dict(base_row, demand_native_id="BV1internal02")
            payload, status, _ = importer.handle_import(
                conn, self.cfg, fmt="json", body=json.dumps([final_row]).encode("utf-8"), filename="i.json",
                mode="atomic", format_version=1, client_ref=None, run_source_id="s_bili",
                internal_observation={"observed_at": FALLBACK_STAMP, "observed_at_source": "import_time",
                                      "warnings": [("S3_TEST", "示例警告")]})
        finally:
            conn.close()
        self.assertEqual(status, 201, payload)
        signal = self.query("SELECT observed_at, observed_at_source FROM demand_signal WHERE native_id=?",
                            ("BV1internal02",))[0]
        self.assertEqual(signal, {"observed_at": FALLBACK_STAMP, "observed_at_source": "import_time"})
        self.assertEqual(self.query("SELECT source_id FROM run_record")[0]["source_id"], "s_bili")
        self.assertIn("S3_TEST", [w["reason_code"] for w in
                                  self.query("SELECT reason_code FROM import_row_result WHERE action='warning'")])

    # ---------------- S3W-20 / 21 失败审计与计数
    def test_s3w20_failure_audit_matrix(self):
        # (b2) 映射后行违规 → importer 422（批次保留） + wiring 补失败 run
        original = wiring.build_row
        wiring.build_row = lambda record, **kw: ({"title": "示例-b2", "data_origin": "synthetic",
                                                  "demand_source": "bilibili", "demand_native_id": "BV1b2000001",
                                                  "demand_url": f"https://www.bilibili.com/video/{BVID}/",
                                                  "demand_excerpt": "摘录", "observed_at": VALID_AT}, [])
        try:
            result, _ = self.complete()
        finally:
            wiring.build_row = original
        self.assertFalse(result["ok"])
        self.assertGreaterEqual(self.counts("import_batch")["import_batch"], 1)   # rejected batch 保留
        self.assertEqual(self.counts("candidate")["candidate"], 0)
        self.assertEqual(self.query("SELECT COUNT(*) AS n FROM run_record WHERE status='failed'")[0]["n"], 1)

        # (c) SQL 异常 → 批内全部回滚 + 另事务失败 run
        original_process = importer.process_row

        def boom(*args, **kwargs):
            raise sqlite3.IntegrityError("模拟唯一冲突")

        importer.process_row = boom
        try:
            result, _ = self.complete()
        finally:
            importer.process_row = original_process
        self.assertFalse(result["ok"])
        self.assertEqual(self.counts("candidate", "demand_signal", "evidence")["candidate"], 0)
        self.assertEqual(self.counts("import_batch")["import_batch"], 1)          # 仍只有上一步的批次
        self.assertEqual(self.query("SELECT COUNT(*) AS n FROM run_record WHERE status='failed'")[0]["n"], 2)

    def test_s3w21_missing_bvid_and_unknown_target_are_audited_without_rows(self):
        result, calls = self.complete(target="not-a-bvid")
        self.assertFalse(result["ok"])
        self.assertEqual(calls, [])
        self.assertEqual(self.counts("candidate", "demand_signal", "import_batch"),
                         {"candidate": 0, "demand_signal": 0, "import_batch": 0})
        self.assertEqual(self.query("SELECT COUNT(*) AS n FROM run_record WHERE status='failed'")[0]["n"], 1)


if __name__ == "__main__":
    unittest.main()
