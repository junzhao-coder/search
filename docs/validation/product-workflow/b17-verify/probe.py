#!/usr/bin/env python
"""B17-B independent probe for B16 supply candidates and sample check."""

from __future__ import annotations

import hashlib
import json
import os
import pathlib
import sqlite3
import sys
import tempfile

ROOT = pathlib.Path(r"D:\桌面\two")
WORKBENCH = ROOT / "tools" / "workbench"
OUT = ROOT / "docs" / "validation" / "product-workflow" / "b17-verify"
SAMPLE = ROOT / "docs" / "validation" / "product-workflow" / "b7" / "sample-study-planner-v1.xlsx"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    out = {"utc": "2026-10-24T04:55:00Z", "sample_sha_before": sha(SAMPLE), "steps": {}}
    with tempfile.TemporaryDirectory(prefix="b17_verify_") as td:
        tmp = pathlib.Path(td)
        os.environ["WORKBENCH_WORKFLOW_DB"] = str(tmp / "workflow.sqlite3")
        os.environ["WORKBENCH_SECRET_FILE"] = str(tmp / "secret")
        sys.path.insert(0, str(WORKBENCH))
        import app as wb  # noqa: E402
        import samplecheck as sc  # noqa: E402
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

        def current(wid):
            conn = wf.connect()
            try:
                return wf.get(conn, wid)
            finally:
                conn.close()

        def counts():
            conn = sqlite3.connect(db)
            try:
                return {t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
                        for t in ("workorder", "workorder_event", "workorder_supply_candidate")}
            finally:
                conn.close()

        created = client.post("/worksheet/new", data={
            "csrf": csrf(), "self_made": "1", "submit_key": "b17",
            "name": "B17 自制提示词包", "use_case": "会议纪要", "deliverable": "纯文本 .md",
            "target_platform": "xianyu", "fmt": "md"})
        wid = created.headers.get("Location", "").rsplit("/", 1)[-1].split("?")[0]
        out["steps"]["create"] = {"status": created.status_code, "id": wid}

        detail = client.get(f"/worksheet/{wid}")
        body = detail.get_data(as_text=True)
        out["steps"]["sections"] = {"status": detail.status_code,
                                    "supply": "货源候选" in body, "sample": "样品自检（本地文件）" in body}

        def add(provider, **kw):
            payload = {"csrf": csrf(), "provider": provider, "source_url": "self:pp-v1",
                       "kind": "同款", "commercial": "yes", "redistribute": "yes", "resale": "yes",
                       "license_note": "作者自持", "price_minor": "0"}
            payload.update(kw)
            return client.post(f"/worksheet/{wid}/supply/candidates", data=payload)

        r1, r2 = add("第一来源"), add("第二来源")
        out["steps"]["candidate_add"] = {"first": r1.status_code, "second": r2.status_code}
        conn = wf.connect()
        try:
            cands = sup.list_candidates(conn, wid)
        finally:
            conn.close()
        out["steps"]["candidate_count"] = len(cands)

        c1, c2 = cands[0], cands[1]
        upd = client.post(f"/worksheet/{wid}/supply/candidates/{c1['id']}",
                          data={"csrf": csrf(), "kind": "替代", "conclusion": "可用"})
        conn = wf.connect()
        try:
            c1u = sup.get_candidate(conn, wid, c1["id"])
        finally:
            conn.close()
        out["steps"]["candidate_update"] = {"status": upd.status_code,
                                            "kind": c1u["kind"], "conclusion": c1u["conclusion"]}

        # select first, then replace
        rec = current(wid)
        s1 = client.post(f"/worksheet/{wid}/supply/select",
                         data={"csrf": csrf(), "revision": str(rec["revision"]), "candidate_id": c1["id"]})
        rec = current(wid)
        s1state = {"status": s1.status_code, "selected": rec["selected_supply_id"],
                   "version": rec["supply_version"], "license": [rec["supply_license_commercial"],
                                                                   rec["supply_license_redistribute"],
                                                                   rec["supply_license_resell"]],
                   "note": rec["supply_note"],
                   "readiness": {c["key"]: c["ok"] for c in __import__("readiness").readiness(rec)["checks"]}}
        s2 = client.post(f"/worksheet/{wid}/supply/select",
                         data={"csrf": csrf(), "revision": str(rec["revision"]), "candidate_id": c2["id"]})
        rec = current(wid)
        conn = wf.connect()
        try:
            events = [dict(r) for r in conn.execute(
                "SELECT action,detail FROM workorder_event WHERE workorder_id=? ORDER BY id", (wid,)).fetchall()]
        finally:
            conn.close()
        out["steps"]["select"] = {"first": s1state, "second_status": s2.status_code,
                                  "selected": rec["selected_supply_id"],
                                  "events": events}

        # deactivate third candidate: no confirm => 400, confirm => soft delete
        add("待停用")
        conn = wf.connect()
        try:
            c3 = [c for c in sup.list_candidates(conn, wid) if c["provider"] == "待停用"][0]
        finally:
            conn.close()
        d0 = client.post(f"/worksheet/{wid}/supply/candidates/{c3['id']}/deactivate",
                         data={"csrf": csrf(), "confirm": "0"})
        d1 = client.post(f"/worksheet/{wid}/supply/candidates/{c3['id']}/deactivate",
                         data={"csrf": csrf(), "confirm": "1"})
        conn = wf.connect()
        try:
            c3after = sup.get_candidate(conn, wid, c3["id"])
            active = len(sup.list_candidates(conn, wid))
        finally:
            conn.close()
        out["steps"]["deactivate"] = {"no_confirm": d0.status_code, "confirm": d1.status_code,
                                      "is_active": c3after["is_active"], "active_count": active}

        # JSON import: 2 valid, 1 bad, 1 non-object
        payload = json.dumps([
            {"provider": "A 站", "source_url": "https://a.example/x", "kind": "同款",
             "commercial": "yes", "redistribute": "yes", "resale": "yes", "price": {"amount": 990}},
            {"provider": "B 站", "kind": "未知类型"},
            {"provider": "C 站", "kind": "替代", "native_id": "x-1", "unknown_field": 1},
            "not-an-object",
        ], ensure_ascii=False)
        imp = client.post(f"/worksheet/{wid}/supply/import", data={"csrf": csrf(), "payload": payload})
        conn = wf.connect()
        try:
            icount = len(sup.list_candidates(conn, wid))
        finally:
            conn.close()
        out["steps"]["import"] = {"status": imp.status_code, "active_count": icount}

        # CSRF / origin
        bad = client.post(f"/worksheet/{wid}/supply/candidates", data={"provider": "x"})
        cross = client.post(f"/worksheet/{wid}/supply/candidates",
                            data={"csrf": csrf(), "provider": "x", "source_url": "self:x"},
                            headers={"Origin": "http://evil.example"})
        out["steps"]["guards"] = {"no_csrf": bad.status_code, "cross_origin": cross.status_code}

        # sample check success
        rec = current(wid)
        ok = client.post(f"/worksheet/{wid}/sample/check",
                         data={"csrf": csrf(), "revision": str(rec["revision"]),
                               "path": "docs/validation/product-workflow/b7/sample-study-planner-v1.xlsx"})
        rec_ok = current(wid)
        out["steps"]["sample_ok"] = {"status": ok.status_code, "sample_status": rec_ok["sample_status"],
                                     "ref_has_path": "sample-study-planner-v1.xlsx" in (rec_ok["sample_ref"] or ""),
                                     "ref_has_checks": "sheets" in (rec_ok["sample_ref"] or ""),
                                     "sha_after": sha(SAMPLE)}

        # failures; state must stay verified + same ref
        before_fail = {"status": rec_ok["sample_status"], "ref": rec_ok["sample_ref"], "rev": rec_ok["revision"]}
        fails = []
        for path in ("../etc/passwd", str(ROOT / "instance" / "app.db"),
                     "docs/../instance/app.db", "docs/validation/product-workflow/b7/00_build.log",
                     "docs/not-exists.xlsx", "C:\\Windows\\win.ini"):
            rr = client.post(f"/worksheet/{wid}/sample/check",
                             data={"csrf": csrf(), "revision": str(before_fail["rev"]), "path": path})
            fails.append({"path": path, "status": rr.status_code})
        over = OUT / "tmp" / "oversize.xlsx"
        over.parent.mkdir(parents=True, exist_ok=True)
        over.write_bytes(b"0" * (20 * 1024 * 1024 + 1))
        over_rel = str(over.relative_to(ROOT)).replace("\\", "/")
        r_over = client.post(f"/worksheet/{wid}/sample/check",
                             data={"csrf": csrf(), "revision": str(before_fail["rev"]), "path": over_rel})
        fails.append({"path": over_rel, "status": r_over.status_code})
        over.unlink(missing_ok=True)
        rec_fail = current(wid)
        out["steps"]["sample_fail"] = {"fails": fails,
                                       "state_same": (rec_fail["sample_status"] == before_fail["status"]
                                                      and rec_fail["sample_ref"] == before_fail["ref"]
                                                      and rec_fail["revision"] == before_fail["rev"])}

        # absolute in-root check (pure function, no state)
        abs_ok = sc.check_path(str(SAMPLE))
        out["steps"]["absolute_in_root"] = {"ok": abs_ok["ok"], "path": abs_ok.get("path"),
                                            "checks": len(abs_ok.get("checks") or [])}

        out["steps"]["final"] = {"counts": counts(), "selected": current(wid)["selected_supply_id"]}
    out["sample_sha_after"] = sha(SAMPLE)
    (OUT / "probe.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8", newline="\n")
    print(json.dumps(out, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
