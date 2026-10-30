#!/usr/bin/env python
"""B17-B focused binding probe: selected-candidate changes and old evidence reuse."""

from __future__ import annotations

import json
import os
import pathlib
import sqlite3
import sys
import tempfile

ROOT = pathlib.Path(r"D:\桌面\two")
WB = ROOT / "tools" / "workbench"
OUT = ROOT / "docs" / "validation" / "product-workflow" / "b17-verify"
SAMPLE = "docs/validation/product-workflow/b7/sample-study-planner-v1.xlsx"

EVIDENCE = {
    "cost_minor": "500", "cost_known": "yes",
    "platform_evidence": "demo://b17/synthetic-platform-evidence",
    "copy_status": "final", "copy_version": "copy-v1",
    "selling_points": "会议纪要模板\n可直接复制",
    "price_minor": "990", "delivery_note": "拍下后发网盘链接",
    "aftersales_note": "7 天内答疑", "faq_json": json.dumps([{"q": "格式", "a": "Markdown"}], ensure_ascii=False),
}


def compact_record(r: dict | None) -> dict:
    keys = ("selected_supply_id", "supply_version", "supply_license_commercial",
            "supply_license_redistribute", "supply_license_resell", "supply_note",
            "sample_status", "sample_ref", "cost_minor", "cost_known", "platform_evidence",
            "revision", "copy_version")
    return {k: (r or {}).get(k) for k in keys}


def main() -> int:
    out = {"utc": "2026-10-24T05:05:00Z", "steps": {}}
    with tempfile.TemporaryDirectory(prefix="b17_bind_") as td:
        tmp = pathlib.Path(td)
        os.environ["WORKBENCH_WORKFLOW_DB"] = str(tmp / "workflow.sqlite3")
        os.environ["WORKBENCH_SECRET_FILE"] = str(tmp / "secret")
        sys.path.insert(0, str(WB))
        import app as wb  # noqa: E402
        import readiness as rd  # noqa: E402
        import supply as sup  # noqa: E402
        import workflow as wf  # noqa: E402

        db = tmp / "workflow.sqlite3"
        conn0 = wf.connect()
        wf.init_schema(conn0)
        conn0.close()
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

        def state(wid):
            conn = wf.connect()
            try:
                r = wf.get(conn, wid)
                cands = sup.list_candidates(conn, wid, active_only=False)
                last = rd.last_export(conn, wid)
            finally:
                conn.close()
            ready = rd.readiness(r)
            return {
                "record": compact_record(r),
                "readiness": {c["key"]: c["ok"] for c in ready["checks"]},
                "blockers": ready["blockers"],
                "last_export": last,
                "validity": rd.export_validity(r, last),
                "candidates": [{k: c.get(k) for k in ("id", "provider", "source_url", "commercial",
                                                       "redistribute", "resale", "price_minor", "is_active",
                                                       "created_at", "updated_at")}
                               for c in cands],
            }

        def add(provider, license_yes=True):
            payload = {"csrf": csrf(), "provider": provider, "source_url": "self:" + provider,
                       "kind": "同款", "commercial": "yes" if license_yes else "no",
                       "redistribute": "yes" if license_yes else "no",
                       "resale": "yes" if license_yes else "no",
                       "license_note": "test", "price_minor": "100"}
            r = client.post(f"/worksheet/{wid}/supply/candidates", data=payload)
            conn = wf.connect()
            try:
                cand = [c for c in sup.list_candidates(conn, wid, active_only=False)
                        if c["provider"] == provider][0]
            finally:
                conn.close()
            return r.status_code, cand

        created = client.post("/worksheet/new", data={
            "csrf": csrf(), "self_made": "1", "submit_key": "b17-bind",
            "name": "B17 绑定测试", "use_case": "会议纪要", "deliverable": "Markdown",
            "target_platform": "xianyu", "fmt": "md"})
        wid = created.headers.get("Location", "").rsplit("/", 1)[-1].split("?")[0]
        out["workorder"] = wid

        a_status, A = add("A")
        c_status, C = add("C")
        out["add"] = {"A": [a_status, A["id"]], "C": [c_status, C["id"]]}

        r = rec(wid)
        sel = client.post(f"/worksheet/{wid}/supply/select",
                          data={"csrf": csrf(), "revision": str(r["revision"]), "candidate_id": A["id"]})
        r = rec(wid)
        sample = client.post(f"/worksheet/{wid}/sample/check",
                             data={"csrf": csrf(), "revision": str(r["revision"]), "path": SAMPLE})
        r = rec(wid)
        ev = client.post(f"/worksheet/{wid}/evidence",
                         data={"csrf": csrf(), "revision": str(r["revision"]), **EVIDENCE})
        baseline = state(wid)
        exp = client.post(f"/worksheet/{wid}/export/record", data={"csrf": csrf(), "format": "json"})
        out["baseline"] = {"select_A": sel.status_code, "sample": sample.status_code, "evidence": ev.status_code,
                           "export_record": {"status": exp.status_code, "dedup": exp.headers.get("X-WB-Deduplicated")},
                           "state": state(wid), "pre_export_state": baseline}

        # Control: modify unselected C; workorder/readiness/old export must not change.
        c_before = state(wid)
        c_update = client.post(f"/worksheet/{wid}/supply/candidates/{C['id']}",
                               data={"csrf": csrf(), "commercial": "no", "price_minor": "111"})
        c_after = state(wid)
        out["control_unselected"] = {"update_status": c_update.status_code,
                                     "same_record": c_before["record"] == c_after["record"],
                                     "same_readiness": c_before["readiness"] == c_after["readiness"],
                                     "same_validity": c_before["validity"] == c_after["validity"],
                                     "candidate": [c for c in c_after["candidates"] if c["id"] == C["id"]][0]}

        # (a) modify selected A: license yes->no and source/price change.
        a_update = client.post(f"/worksheet/{wid}/supply/candidates/{A['id']}",
                               data={"csrf": csrf(), "commercial": "no", "source_url": "self:A-v2",
                                     "price_minor": "222"})
        a_state = state(wid)
        get_a = client.get(f"/worksheet/{wid}/export?format=json")
        out["a_modified_selected"] = {"update_status": a_update.status_code,
                                      "candidate": [c for c in a_state["candidates"] if c["id"] == A["id"]][0],
                                      "state": a_state, "get_export": {"status": get_a.status_code,
                                                                        "bytes": len(get_a.data)}}

        # (b) deactivate selected A.
        a_deact = client.post(f"/worksheet/{wid}/supply/candidates/{A['id']}/deactivate",
                              data={"csrf": csrf(), "confirm": "1"})
        b_state = state(wid)
        get_b = client.get(f"/worksheet/{wid}/export?format=json")
        out["b_deactivated_selected"] = {"deactivate_status": a_deact.status_code,
                                         "candidate_active": [c["is_active"] for c in b_state["candidates"]
                                                              if c["id"] == A["id"]][0],
                                         "state": b_state, "get_export": {"status": get_b.status_code,
                                                                           "bytes": len(get_b.data)}}

        # (c) add B (all yes) and replace A with B.
        b_add_status, B = add("B")
        r = rec(wid)
        sel_b = client.post(f"/worksheet/{wid}/supply/select",
                            data={"csrf": csrf(), "revision": str(r["revision"]), "candidate_id": B["id"]})
        cstate = state(wid)
        get_c = client.get(f"/worksheet/{wid}/export?format=json")
        out["c_replaced_by_B"] = {"add_status": b_add_status, "B_id": B["id"],
                                  "select_status": sel_b.status_code,
                                  "state": cstate,
                                  "get_export": {"status": get_c.status_code, "bytes": len(get_c.data)},
                                  "sample_cost_preserved": (cstate["record"]["sample_ref"]
                                                            == out["baseline"]["state"]["record"]["sample_ref"]
                                                            and cstate["record"]["cost_minor"]
                                                            == out["baseline"]["state"]["record"]["cost_minor"])}
        # final candidate table
        conn = wf.connect()
        try:
            out["final_candidates"] = [dict(r) for r in conn.execute(
                "SELECT id,provider,commercial,is_active,created_at,updated_at FROM workorder_supply_candidate "
                "WHERE workorder_id=? ORDER BY id", (wid,)).fetchall()]
        finally:
            conn.close()
    (OUT / "binding_probe.json").write_text(json.dumps(out, ensure_ascii=False, indent=1),
                                             encoding="utf-8", newline="\n")
    print(json.dumps(out, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
