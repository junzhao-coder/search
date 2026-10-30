#!/usr/bin/env python
"""W1: on a read-only production snapshot copy, verify first HTTP candidate add lazily creates the table."""

from __future__ import annotations

import hashlib
import json
import os
import pathlib
import shutil
import sqlite3
import sys
import tempfile

ROOT = pathlib.Path(r"D:\桌面\two")
WB = ROOT / "tools" / "workbench"
OUT = ROOT / "docs" / "validation" / "product-workflow" / "b17-verify"
PROD_DB = WB / "runtime" / "workflow.sqlite3"


def table_state(path: pathlib.Path) -> dict:
    conn = sqlite3.connect(path)
    try:
        exists = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='workorder_supply_candidate'").fetchone()
        count = conn.execute("SELECT COUNT(*) FROM workorder_supply_candidate").fetchone()[0] if exists else None
        workorders = conn.execute("SELECT workorder_id FROM workorder").fetchall()
        return {"table_exists": bool(exists), "candidate_count": count,
                "workorders": [r[0] for r in workorders]}
    finally:
        conn.close()


def main() -> int:
    out = {"utc": "2026-10-24T05:10:00Z", "production_before_sha": hashlib.sha256(PROD_DB.read_bytes()).hexdigest()}
    with tempfile.TemporaryDirectory(prefix="b17_w1_") as td:
        tmp = pathlib.Path(td)
        copy = tmp / "workflow-copy.sqlite3"
        shutil.copy2(PROD_DB, copy)
        out["copy_before"] = table_state(copy)
        os.environ["WORKBENCH_WORKFLOW_DB"] = str(copy)
        os.environ["WORKBENCH_SECRET_FILE"] = str(tmp / "secret")
        sys.path.insert(0, str(WB))
        import app as wb  # noqa: E402
        import workflow as wf  # noqa: E402

        wid = out["copy_before"]["workorders"][0]
        app = wb.create_app()
        app.testing = True
        client = app.test_client()

        def csrf():
            client.get("/worksheet")
            with client.session_transaction() as s:
                return s["csrf"]

        detail = client.get(f"/worksheet/{wid}")
        response = client.post(f"/worksheet/{wid}/supply/candidates",
                               data={"csrf": csrf(), "provider": "W1 lazy init", "source_url": "self:w1",
                                     "kind": "同款", "commercial": "yes", "redistribute": "yes",
                                     "resale": "yes", "license_note": "copy only"})
        out["detail"] = {"status": detail.status_code,
                         "supply_section": "货源候选" in detail.get_data(as_text=True)}
        out["post"] = {"status": response.status_code, "location": response.headers.get("Location")}
        out["copy_after"] = table_state(copy)
    out["production_after_sha"] = hashlib.sha256(PROD_DB.read_bytes()).hexdigest()
    (OUT / "w1_lazy_init.json").write_text(json.dumps(out, ensure_ascii=False, indent=1),
                                           encoding="utf-8", newline="\n")
    print(json.dumps(out, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
