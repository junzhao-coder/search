#!/usr/bin/env python
"""B19 independent probe for B18 D2/D3/D4 sync/invalidation, control, recovery."""

from __future__ import annotations

import json
import os
import pathlib
import sqlite3
import sys
import tempfile

ROOT = pathlib.Path(r"D:\桌面\two")
WB = ROOT / "tools" / "workbench"
OUT = ROOT / "docs" / "validation" / "product-workflow" / "b19"
SAMPLE = "docs/validation/product-workflow/b7/sample-study-planner-v1.xlsx"
COPY = {"cost_minor": "500", "cost_known": "yes", "copy_status": "final", "copy_version": "copy-v1",
        "selling_points": "B19 测试", "price_minor": "990", "delivery_note": "站内",
        "aftersales_note": "未定", "faq_json": "[]",
        "platform_evidence": "demo://b19/synthetic-platform-evidence"}


def compact(rec):
    keys = ("selected_supply_id", "supply_version", "supply_license_commercial",
            "supply_license_redistribute", "supply_license_resell", "supply_note",
            "sample_status", "sample_ref", "cost_minor", "cost_known", "platform_evidence",
            "revision", "copy_version")
    return {k: (rec or {}).get(k) for k in keys}


def main() -> int:
    out = {"utc": "2026-10-24T05:35:00Z", "steps": {}}
    with tempfile.TemporaryDirectory(prefix="b19_verify_") as td:
        tmp = pathlib.Path(td)
        os.environ["WORKBENCH_WORKFLOW_DB"] = str(tmp / "workflow.sqlite3")
        os.environ["WORKBENCH_SECRET_FILE"] = str(tmp / "secret")
        sys.path.insert(0, str(WB))
        import app as wb  # noqa: E402
        import readiness as rd  # noqa: E402
        import supply as sup  # noqa: E402
        import workflow as wf  # noqa: E402

        db = tmp / "workflow.sqlite3"
        c0 = wf.connect()
        wf.init_schema(c0)
        c0.close()
        app = wb.create_app()
        app.testing = True
        client = app.test_client()

        def csrf():
            client.get("/worksheet")
            with client.session_transaction() as s:
                return s["csrf"]

        def rec(wid):
            conn = wf.connect()
            try:
                return wf.get(conn, wid)
            finally:
                conn.close()

        def cands(wid):
            conn = wf.connect()
            try:
                return sup.list_candidates(conn, wid, active_only=False)
            finally:
                conn.close()

        def state(wid):
            r = rec(wid)
            conn = wf.connect()
            try:
                last = rd.last_export(conn, wid)
            finally:
                conn.close()
            ready = rd.readiness(r)
            return {"record": compact(r),
                    "readiness": {c["key"]: c["ok"] for c in ready["checks"]},
                    "blockers": ready["blockers"],
                    "validity": rd.export_validity(r, last),
                    "last_export": last,
                    "candidates": [{k: c.get(k) for k in ("id", "provider", "commercial", "redistribute",
                                                           "resale", "is_active", "updated_at")}
                                   for c in cands(wid)]}

        def add(provider):
            payload = {"csrf": csrf(), "provider": provider, "source_url": "self:" + provider,
                       "kind": "同款", "commercial": "yes", "redistribute": "yes", "resale": "yes"}
            rr = client.post(f"/worksheet/{wid}/supply/candidates", data=payload)
            return rr.status_code, [c for c in cands(wid) if c["provider"] == provider][0]

        created = client.post("/worksheet/new", data={
            "csrf": csrf(), "self_made": "1", "submit_key": "b19",
            "name": "B19 绑定测试", "use_case": "测试", "deliverable": "文本",
            "target_platform": "xianyu"})
        wid = created.headers.get("Location", "").rsplit("/", 1)[-1].split("?")[0]
        out["workorder"] = wid
        out["add"] = {}
        _, A = add("A")
        out["add"]["A"] = A["id"]
        _, B = add("B")
        out["add"]["B"] = B["id"]

        # baseline ready
        r = rec(wid)
        out["select_A"] = client.post(f"/worksheet/{wid}/supply/select",
                                      data={"csrf": csrf(), "revision": str(r["revision"]), "candidate_id": A["id"]}).status_code
        r = rec(wid)
        out["sample_A"] = client.post(f"/worksheet/{wid}/sample/check",
                                      data={"csrf": csrf(), "revision": str(r["revision"]), "path": SAMPLE}).status_code
        r = rec(wid)
        out["evidence_A"] = client.post(f"/worksheet/{wid}/evidence",
                                        data={"csrf": csrf(), "revision": str(r["revision"]), **COPY}).status_code
        out["baseline"] = state(wid)
        exp = client.post(f"/worksheet/{wid}/export/record", data={"csrf": csrf(), "format": "json"})
        out["export_baseline"] = {"status": exp.status_code, "dedup": exp.headers.get("X-WB-Deduplicated")}
        out["baseline_after_export"] = state(wid)

        # control: modify/deactivate unselected B -> workorder exact same
        before_control = rec(wid)
        upd = client.post(f"/worksheet/{wid}/supply/candidates/{B['id']}",
                          data={"csrf": csrf(), "resale": "no"})
        deact = client.post(f"/worksheet/{wid}/supply/candidates/{B['id']}/deactivate",
                            data={"csrf": csrf(), "confirm": "1"})
        after_control = rec(wid)
        out["control"] = {"update": upd.status_code, "deactivate": deact.status_code,
                          "record_same": before_control == after_control,
                          "state": state(wid),
                          "get_export": client.get(f"/worksheet/{wid}/export?format=json").status_code}

        # D2: selected A resale yes -> no
        d2 = client.post(f"/worksheet/{wid}/supply/candidates/{A['id']}",
                         data={"csrf": csrf(), "resale": "no"})
        d2state = state(wid)
        get_d2 = client.get(f"/worksheet/{wid}/export?format=json")
        out["D2"] = {"update": d2.status_code, "state": d2state,
                     "get_export": {"status": get_d2.status_code, "bytes": len(get_d2.data)}}

        # D2 recovery: candidate back yes; sync clears sample/cost; sample+evidence -> 7/7
        rec_yes = client.post(f"/worksheet/{wid}/supply/candidates/{A['id']}",
                              data={"csrf": csrf(), "resale": "yes"})
        r = rec(wid)
        sample_again = client.post(f"/worksheet/{wid}/sample/check",
                                   data={"csrf": csrf(), "revision": str(r["revision"]), "path": SAMPLE})
        r = rec(wid)
        ev_again = client.post(f"/worksheet/{wid}/evidence",
                               data={"csrf": csrf(), "revision": str(r["revision"]),
                                     "cost_minor": "500", "cost_known": "yes"})
        out["D2_recovery"] = {"update_yes": rec_yes.status_code, "sample": sample_again.status_code,
                              "evidence": ev_again.status_code, "state": state(wid),
                              "get_export": client.get(f"/worksheet/{wid}/export?format=json").status_code}

        # D3: deactivate selected A
        d3 = client.post(f"/worksheet/{wid}/supply/candidates/{A['id']}/deactivate",
                         data={"csrf": csrf(), "confirm": "1"})
        d3state = state(wid)
        get_d3 = client.get(f"/worksheet/{wid}/export?format=json")
        out["D3"] = {"deactivate": d3.status_code, "state": d3state,
                     "get_export": {"status": get_d3.status_code, "bytes": len(get_d3.data)}}

        # D4: add B2, select replacing A (B was deactivated)
        _, B2 = add("B2")
        r = rec(wid)
        d4 = client.post(f"/worksheet/{wid}/supply/select",
                         data={"csrf": csrf(), "revision": str(r["revision"]), "candidate_id": B2["id"]})
        d4state = state(wid)
        get_d4 = client.get(f"/worksheet/{wid}/export?format=json")
        out["D4"] = {"select": d4.status_code, "state": d4state,
                     "get_export": {"status": get_d4.status_code, "bytes": len(get_d4.data)}}

        # D4 recovery: sample + cost -> 7/7
        r = rec(wid)
        s4 = client.post(f"/worksheet/{wid}/sample/check",
                         data={"csrf": csrf(), "revision": str(r["revision"]), "path": SAMPLE})
        r = rec(wid)
        e4 = client.post(f"/worksheet/{wid}/evidence",
                         data={"csrf": csrf(), "revision": str(r["revision"]),
                               "cost_minor": "500", "cost_known": "yes"})
        out["D4_recovery"] = {"sample": s4.status_code, "evidence": e4.status_code,
                              "state": state(wid),
                              "get_export": client.get(f"/worksheet/{wid}/export?format=json").status_code}

        # final schema/DB
        conn = sqlite3.connect(db)
        try:
            out["db_counts"] = {t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
                                for t in ("workorder", "workorder_supply_candidate", "workorder_event",
                                          "workorder_export")}
        finally:
            conn.close()
    (OUT / "binding_probe.json").write_text(json.dumps(out, ensure_ascii=False, indent=1),
                                             encoding="utf-8", newline="\n")
    print(json.dumps(out, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
