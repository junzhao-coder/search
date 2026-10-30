#!/usr/bin/env python
"""B14 independent probe: B12/B13 rollback, dedupe, publish, isolation."""

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
OUT = ROOT / "docs" / "validation" / "product-workflow" / "b14"
OUT.mkdir(parents=True, exist_ok=True)

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
COPY_FIELDS = ("name", "selling_points", "includes", "excludes", "fmt", "language", "version",
               "price_minor", "delivery_note", "aftersales_note", "faq_json")
SUPPLY_GROUP = ("selected_supply_id", "supply_version", "supply_license_commercial",
                "supply_license_redistribute", "supply_license_resell", "sample_status", "sample_ref",
                "cost_minor", "cost_known", "platform_evidence")


def dbcount(db):
    conn = sqlite3.connect(db)
    try:
        return {t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
                for t in ("workorder", "workorder_event", "workorder_export",
                          "workorder_copy_version", "workorder_publish")}
    finally:
        conn.close()


def main() -> int:
    result = {"utc": "2026-10-23T14:45:00Z", "production": {}, "steps": {}}
    prod = ROOT / "tools" / "workbench" / "runtime" / "workflow.sqlite3"
    result["production"]["before_sha"] = __import__("hashlib").sha256(prod.read_bytes()).hexdigest() if prod.exists() else None
    if prod.exists():
        conn = sqlite3.connect(f"file:{prod}?mode=ro", uri=True)
        try:
            result["production"]["before_counts"] = {}
            result["production"]["table_errors"] = {}
            for t in ("workorder", "workorder_export", "workorder_copy_version", "workorder_publish"):
                try:
                    result["production"]["before_counts"][t] = conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
                except sqlite3.Error as exc:
                    result["production"]["before_counts"][t] = None
                    result["production"]["table_errors"][t] = str(exc)
            result["production"]["ids"] = [r[0] for r in conn.execute("SELECT workorder_id FROM workorder").fetchall()]
        except sqlite3.Error as exc:
            result["production"]["read_error"] = str(exc)
        finally:
            conn.close()

    with tempfile.TemporaryDirectory(prefix="b14_verify_") as td:
        tmp = pathlib.Path(td)
        scores = tmp / "scores.csv"
        with scores.open("w", encoding="utf-8", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=SCORE_COLS, lineterminator="\n")
            w.writeheader()
            w.writerow({c: ROW.get(c, "") for c in SCORE_COLS})
        top10 = tmp / "top10.csv"
        top10.write_text("rank,opportunity_id,reference_max\n1,x:prod,699\n", encoding="utf-8")
        db = tmp / "workflow.sqlite3"
        secret = tmp / "secret"
        os.environ["WORKBENCH_WORKFLOW_DB"] = str(db)
        os.environ["WORKBENCH_SECRET_FILE"] = str(secret)
        os.environ["WORKBENCH_SOURCE_FIXTURE"] = f"{scores},{top10}"

        sys.path.insert(0, str(WORKBENCH))
        import app as wb  # noqa: E402
        import readiness as rd  # noqa: E402
        import workflow as wf  # noqa: E402

        # Isolated schema only; production path is never imported by app.
        conn0 = wf.connect()
        wf.init_schema(conn0)
        conn0.close()

        app = wb.create_app()
        app.testing = True
        client = app.test_client()

        def csrf():
            client.get("/worksheet")
            with client.session_transaction() as sess:
                return sess["csrf"]

        def current(wid):
            conn = wf.connect()
            try:
                return wf.get(conn, wid)
            finally:
                conn.close()

        def rows(wid):
            conn = wf.connect()
            try:
                return {
                    "record": wf.get(conn, wid),
                    "versions": rd.list_copy_versions(conn, wid),
                    "last": rd.last_export(conn, wid),
                    "publish": rd.publish_info(conn, wid),
                }
            finally:
                conn.close()

        # GET /worksheet/new must be zero-write
        before_new = dbcount(db)
        new_page = client.get("/worksheet/new")
        result["steps"]["new_page"] = {"status": new_page.status_code,
                                       "zero_write": before_new == dbcount(db)}

        # create standard workorder
        create_data = {"csrf": csrf(), "group": "Notion 学习笔记模板", "item_id": "x:prod",
                       "submit_key": "b14", "name": "B14 工作单", "use_case": "学习笔记",
                       "deliverable": "Notion 模板", "target_platform": "xianyu"}
        created = client.post("/worksheet/new", data=create_data)
        wid = created.headers.get("Location", "").rsplit("/", 1)[-1].split("?")[0]
        result["steps"]["create"] = {"status": created.status_code, "id": wid}

        before_ready = dbcount(db)
        not_ready = client.get(f"/worksheet/{wid}/export?format=json")
        result["steps"]["not_ready_export"] = {
            "status": not_ready.status_code,
            "blocker": "未选货源" in not_ready.get_data(as_text=True),
            "counts_before": before_ready, "counts_after": dbcount(db),
        }

        # evidence -> ready
        rec = current(wid)
        ev = client.post(f"/worksheet/{wid}/evidence",
                         data={"csrf": csrf(), "revision": str(rec["revision"]), **EVIDENCE})
        result["steps"]["evidence"] = {"status": ev.status_code, "counts": dbcount(db)}

        # GET export must be zero-write; POST record first/second dedup
        before_get = dbcount(db)
        get1 = client.get(f"/worksheet/{wid}/export?format=json")
        after_get = dbcount(db)
        result["steps"]["ready_get"] = {"status": get1.status_code,
                                        "counts_before": before_get, "counts_after": after_get,
                                        "zero_write": before_get == after_get}
        before_rec = dbcount(db)
        post1 = client.post(f"/worksheet/{wid}/export/record", data={"csrf": csrf(), "format": "json"})
        after1 = dbcount(db)
        post2 = client.post(f"/worksheet/{wid}/export/record", data={"csrf": csrf(), "format": "json"})
        after2 = dbcount(db)
        result["steps"]["dedupe"] = {
            "first": {"status": post1.status_code, "dedup": post1.headers.get("X-WB-Deduplicated"),
                      "before": before_rec, "after": after1},
            "second": {"status": post2.status_code, "dedup": post2.headers.get("X-WB-Deduplicated"),
                       "after": after2, "row_unchanged": after1["workorder_export"] == after2["workorder_export"]},
        }

        # change copy -> stale old stamp
        rec = current(wid)
        ev2 = client.post(f"/worksheet/{wid}/evidence",
                          data={"csrf": csrf(), "revision": str(rec["revision"]),
                                "copy_version": "copy-v2", "selling_points": "改后的卖点"})
        state2 = rows(wid)
        validity = rd.export_validity(state2["record"], state2["last"])
        result["steps"]["copy_change"] = {
            "status": ev2.status_code, "versions": [v["version_no"] for v in state2["versions"]],
            "valid": validity["valid"], "changed": validity.get("changed"),
        }
        # record a new stamp (new revision/copy) -> new row
        post3 = client.post(f"/worksheet/{wid}/export/record", data={"csrf": csrf(), "format": "json"})
        result["steps"]["new_stamp"] = {"status": post3.status_code,
                                        "dedup": post3.headers.get("X-WB-Deduplicated"),
                                        "counts": dbcount(db),
                                        "dedupe_key": None}
        conn = wf.connect()
        try:
            row = conn.execute("SELECT dedupe_key FROM workorder_export WHERE workorder_id=? ORDER BY id DESC LIMIT 1",
                               (wid,)).fetchone()
            result["steps"]["new_stamp"]["dedupe_key"] = row["dedupe_key"] if row else None
        finally:
            conn.close()

        # rollback to v1; capture five field groups before/after
        rec = current(wid)
        before_fields = {k: rec.get(k) for k in SUPPLY_GROUP + COPY_FIELDS}
        rollback = client.post(f"/worksheet/{wid}/copy/rollback",
                               data={"csrf": csrf(), "revision": str(rec["revision"]), "version_no": "1"})
        after = current(wid)
        after_fields = {k: after.get(k) for k in SUPPLY_GROUP + COPY_FIELDS}
        versions = rows(wid)["versions"]
        result["steps"]["rollback"] = {
            "status": rollback.status_code,
            "supply_unchanged": {k: before_fields[k] == after_fields[k] for k in SUPPLY_GROUP},
            "copy_changed": {k: before_fields[k] != after_fields[k] for k in COPY_FIELDS},
            "versions": [v["version_no"] for v in versions],
            "newest_created_by": versions[0]["created_by"] if versions else None,
            "snapshot_keys": sorted(versions[0]["snapshot"].keys()) if versions else [],
        }

        # publish invalid + valid
        rec = current(wid)
        rev = str(rec["revision"])
        invalids = []
        for payload in ({"status": "已上架"}, {"status": "已发布", "published_url": "ftp://x/y"},
                        {"status": "已发布", "published_url": "https://example.com/x", "sold_count": "-1"},
                        {"status": "已发布", "published_url": "https://example.com/x", "sold_count": "1.5"}):
            rr = client.post(f"/worksheet/{wid}/publish",
                             data={"csrf": csrf(), "revision": rev, **payload})
            invalids.append({"payload": payload, "status": rr.status_code})
        ok = client.post(f"/worksheet/{wid}/publish",
                         data={"csrf": csrf(), "revision": rev, "status": "已发布",
                               "published_url": "https://example.com/item/1",
                               "published_at": "2026-10-23T14:30:00Z", "sold_count": "0",
                               "platform_note": "审核通过"})
        state = rows(wid)
        result["steps"]["publish"] = {
            "invalids": invalids, "valid_status": ok.status_code,
            "publish": state["publish"],
            "changed_after_publish": rd.publish_changed(state["publish"], state["last"]),
        }

        # abuse / csrf / origin / revision
        rec = current(wid)
        forged = client.post(f"/worksheet/{wid}/evidence",
                             data={"csrf": csrf(), "revision": str(rec["revision"]),
                                   "ready": "1", "verified": "1", "gate_cost": "1", "status": "verified"})
        no_csrf = client.post(f"/worksheet/{wid}/export/record", data={"format": "json"})
        cross = client.post(f"/worksheet/{wid}/publish",
                            data={"csrf": csrf(), "status": "未发布"},
                            headers={"Origin": "http://evil.example"})
        cross2 = client.post(f"/worksheet/{wid}/copy/rollback",
                             data={"csrf": csrf(), "revision": str(current(wid)["revision"]), "version_no": "1"},
                             headers={"Origin": "https://localhost"})
        rev_bad = []
        for value in ("abc", "1.5", "-1"):
            rr = client.post(f"/worksheet/{wid}/evidence",
                             data={"csrf": csrf(), "revision": value, "copy_version": "x"})
            rev_bad.append({"revision": value, "status": rr.status_code})
        result["steps"]["abuse"] = {"forged": forged.status_code, "no_csrf": no_csrf.status_code,
                                    "cross_origin": cross.status_code, "cross_protocol": cross2.status_code,
                                    "bad_revisions": rev_bad}

        result["steps"]["counts_final"] = dbcount(db)
        # close any app caches? no
    if prod.exists():
        import hashlib
        result["production"]["after_sha"] = hashlib.sha256(prod.read_bytes()).hexdigest()
    (OUT / "probe.json").write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8", newline="\n")
    print(json.dumps(result, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
