#!/usr/bin/env python
"""B6 independent export / write-protection probe (isolated temp DB, no production writes)."""

from __future__ import annotations

import copy
import csv
import json
import os
import pathlib
import sqlite3
import sys
import tempfile

ROOT = pathlib.Path(r"D:\桌面\two")
WORKBENCH = ROOT / "tools" / "workbench"
OUT = ROOT / "docs" / "validation" / "product-workflow" / "b6"
TMP = OUT / "tmp"
TMP.mkdir(parents=True, exist_ok=True)

SCORE_COLS = ["rank", "item_id", "platform", "title", "url", "author", "published_at", "total_score",
              "demand_raw", "demand_norm", "sellability_norm", "sellability_reason", "margin_low", "margin_high",
              "margin_mid", "margin_assumption", "cost_input", "cost_note", "missing_metrics", "source", "raw_ref"]
ROW = {"rank": "1", "item_id": "x:prod", "platform": "x", "title": "notion study notes template",
       "url": "https://x/1", "author": "@a", "total_score": "0.8", "demand_raw": "1000", "demand_norm": "0.9",
       "sellability_norm": "0.9", "sellability_reason": "含明确售价", "margin_low": "0.7", "margin_high": "0.95",
       "margin_mid": "0.825", "margin_assumption": "假设", "cost_input": "missing", "missing_metrics": "",
       "source": "fixture", "raw_ref": "raw/x.jsonl"}
EVIDENCE = {
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
FORBIDDEN = {"cost", "profit", "margin", "score", "internal", "raw_ref", "snapshot", "supply_note"}


def walk(obj):
    keys, strings = set(), []
    if isinstance(obj, dict):
        for k, v in obj.items():
            keys.add(k)
            strings.append(str(k))
            kk, ss = walk(v)
            keys |= kk
            strings += ss
    elif isinstance(obj, list):
        for v in obj:
            kk, ss = walk(v)
            keys |= kk
            strings += ss
    elif isinstance(obj, str):
        strings.append(obj)
    return keys, strings


def main() -> int:
    result = {"utc": "2026-10-23T12:10:00Z", "steps": []}
    with tempfile.TemporaryDirectory(prefix="b6_verify_") as td:
        root = pathlib.Path(td)
        scores = root / "scores.csv"
        with scores.open("w", encoding="utf-8", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=SCORE_COLS, lineterminator="\n")
            w.writeheader()
            w.writerow({c: ROW.get(c, "") for c in SCORE_COLS})
        top10 = root / "top10.csv"
        top10.write_text("rank,opportunity_id,reference_max\n1,x:prod,699\n", encoding="utf-8")
        db = root / "workflow.sqlite3"
        secret = root / "secret"
        os.environ["WORKBENCH_WORKFLOW_DB"] = str(db)
        os.environ["WORKBENCH_SECRET_FILE"] = str(secret)
        os.environ["WORKBENCH_SOURCE_FIXTURE"] = f"{scores},{top10}"

        sys.path.insert(0, str(WORKBENCH))
        import app as wb  # noqa: E402
        import readiness as rd  # noqa: E402
        import workflow as wf  # noqa: E402

        app = wb.create_app()
        app.testing = True
        client = app.test_client()

        def counts():
            conn = sqlite3.connect(db)
            try:
                return {
                    "workorder": conn.execute("SELECT COUNT(*) FROM workorder").fetchone()[0],
                    "export": conn.execute("SELECT COUNT(*) FROM workorder_export").fetchone()[0],
                }
            finally:
                conn.close()

        def csrf():
            client.get("/worksheet")
            with client.session_transaction() as sess:
                return sess["csrf"]

        def current():
            conn = wf.connect()
            try:
                return wf.get(conn, wid)
            finally:
                conn.close()

        # create via real POST
        data = {"csrf": csrf(), "group": "Notion 学习笔记模板", "item_id": "x:prod", "submit_key": "b6",
                "name": "Notion 学习笔记工作单", "use_case": "学习笔记", "deliverable": "Notion 模板",
                "target_platform": "xianyu"}
        resp = client.post("/worksheet/new", data=data)
        wid = resp.headers.get("Location", "").rsplit("/", 1)[-1].split("?")[0]
        result["workorder"] = {"status": resp.status_code, "id": wid}
        before_ready = counts()

        # 1) not ready export => 409, blockers, no export row
        r409 = client.get(f"/worksheet/{wid}/export?format=json")
        result["not_ready"] = {"status": r409.status_code,
                               "has_blocker": "未选货源" in r409.get_data(as_text=True),
                               "counts_before": before_ready, "counts_after": counts()}
        result["not_ready"]["no_export_write"] = result["not_ready"]["counts_before"] == result["not_ready"]["counts_after"]

        # 2) GET detail must be read-only
        before_detail = counts()
        client.get(f"/worksheet/{wid}")
        result["get_detail"] = {"counts_before": before_detail, "counts_after": counts(),
                                "zero_write": before_detail == counts()}

        # 3) fill evidence and ready; export 200
        with sqlite3.connect(db) as conn:
            conn.row_factory = sqlite3.Row
            rec = wf.get(conn, wid)
        rev = rec["revision"]
        payload = {"csrf": csrf(), "revision": str(rev), **EVIDENCE}
        ev = client.post(f"/worksheet/{wid}/evidence", data=payload)
        result["fill_evidence"] = {"status": ev.status_code}
        before_export = counts()
        r200 = client.get(f"/worksheet/{wid}/export?format=json")
        after_export = counts()
        body = r200.get_json(silent=True) or {}
        keys, strings = walk(body)
        stamp = body.get("version_stamp") or {}
        result["ready_export"] = {
            "status": r200.status_code,
            "attachment": r200.headers.get("Content-Disposition", ""),
            "counts_before": before_export,
            "counts_after": after_export,
            "get_export_wrote": after_export["export"] > before_export["export"],
            "stamp_fields": sorted(stamp.keys()),
            "stamp": stamp,
            "buyer_fields": body.get("buyer_visible_fields"),
            "internal_hits": sorted({s.lower() for s in strings if s.lower() in FORBIDDEN}),
            "internal_keys": sorted(keys & FORBIDDEN),
            "has_cost": "cost" in keys,
        }

        # 4) old stamp invalidated by copy_version change
        conn = wf.connect()
        try:
            rec2 = rd.save_evidence(conn, wid, revision=str(stamp.get("revision")),
                                    payload={"copy_version": "copy-v2"})
            last = rd.last_export(conn, wid)
            validity = rd.export_validity(rec2, last)
        finally:
            conn.close()
        result["stamp_invalidation"] = {"has_export": validity.get("has_export"),
                                        "valid": validity.get("valid"),
                                        "changed": validity.get("changed")}

        # 5) abuse / cross-site / invalid revisions
        def evidence(payload, headers=None):
            rec = current()
            return client.post(f"/worksheet/{wid}/evidence",
                               data={"csrf": csrf(), "revision": str(rec["revision"]), **payload},
                               headers=headers or {})

        before_abuse = counts()
        forged = evidence({"ready": "1", "verified": "1", "gate_cost": "1", "status": "verified"})
        after_abuse = counts()
        result["forged_fields"] = {"status": forged.status_code,
                                   "db_unchanged": before_abuse == after_abuse}
        cross = evidence({"copy_version": "evil"}, {"Origin": "http://evil.example"})
        cross_proto = evidence({"copy_version": "evil"}, {"Origin": "https://localhost"})
        result["origin"] = {"cross_site": cross.status_code, "cross_protocol": cross_proto.status_code}
        rev_invalid = []
        for value in ("abc", "1.5", "-1"):
            rec = current()
            rr = client.post(f"/worksheet/{wid}/evidence",
                             data={"csrf": csrf(), "revision": value, "copy_version": "x"})
            rev_invalid.append({"revision": value, "status": rr.status_code})
        result["revision_invalid"] = rev_invalid

        # 6) leak self-check is a business 409, not 500
        rec3 = current()
        bad = copy.deepcopy(rec3)
        bad["selling_points"] = "cost sheet"
        try:
            rd.build_export(bad)
            leak = {"status": "NO_ERROR"}
        except wf.Reject as exc:
            leak = {"status": exc.status, "code": exc.code}
        result["leak_selfcheck"] = leak

        result["db"] = {"counts_final": counts(), "path": str(db)}
    (OUT / "export_probe.json").write_text(json.dumps(result, ensure_ascii=False, indent=1),
                                           encoding="utf-8", newline="\n")
    print(json.dumps(result, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
