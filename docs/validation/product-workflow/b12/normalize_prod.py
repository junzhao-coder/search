"""B12：存量单归一化（方案 a：备份库后改写为标准单号，保留映射表）。

- 备份生产库到 `b12/backup/workflow-<utc>.sqlite3`；
- 把 `wo:c3-prod-20261023` 改写为 `wo:<yyyymmdd>-<8hex>`，同步更新 workorder / workorder_event / workorder_export；
- 写 `b12/id_mapping.json`（old → new，含时间与库 sha），并用真实路由核对列表与详情；
- 只改单号，不动任何字段语义。
"""

from __future__ import annotations

import hashlib
import json
import pathlib
import re
import shutil
import sys
import time
import uuid

ROOT = pathlib.Path(r"D:\桌面\two")
B12 = ROOT / "docs" / "validation" / "product-workflow" / "b12"
BACKUP = B12 / "backup"
WORKBENCH = ROOT / "tools" / "workbench"
PROD_DB = WORKBENCH / "runtime" / "workflow.sqlite3"
OLD = "wo:c3-prod-20261023"
sys.path.insert(0, str(WORKBENCH))


def main() -> int:
    BACKUP.mkdir(parents=True, exist_ok=True)
    out: dict = {"generated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "old": OLD}
    if not PROD_DB.exists():
        out["error"] = "生产库不存在"
        print(json.dumps(out, ensure_ascii=True))
        return 1
    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    backup_path = BACKUP / f"workflow-{stamp}.sqlite3"
    shutil.copy2(PROD_DB, backup_path)
    out["backup"] = str(backup_path)
    out["backup_sha256"] = hashlib.sha256(backup_path.read_bytes()).hexdigest()

    import workflow as wf
    import app as wb

    new_id = f"wo:{time.strftime('%Y%m%d', time.gmtime())}-{uuid.uuid4().hex[:8]}"
    if not re.fullmatch(r"wo:\d{8}-[0-9a-f]{8}", new_id):
        raise SystemExit("generated id invalid")
    conn = wf.connect()
    try:
        wf.init_schema(conn)
        row = conn.execute("SELECT workorder_id FROM workorder WHERE workorder_id=?", (OLD,)).fetchone()
        out["found"] = bool(row)
        if row:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute("UPDATE workorder SET workorder_id=? WHERE workorder_id=?", (new_id, OLD))
            for table in ("workorder_event", "workorder_export"):
                conn.execute(f"UPDATE {table} SET workorder_id=? WHERE workorder_id=?", (new_id, OLD))
            conn.execute("INSERT INTO workorder_event (workorder_id, action, detail, at) VALUES (?,?,?,?)",
                         (new_id, "id_normalize", f"{OLD} -> {new_id}（B12 归一化，备份 {backup_path.name}）",
                          time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())))
            conn.commit()
    finally:
        conn.close()

    app = wb.create_app()
    app.testing = True
    client = app.test_client()
    listing = client.get("/worksheet").get_data(as_text=True)
    detail = client.get(f"/worksheet/{new_id}")
    out.update({"new": new_id, "list_contains_new": new_id in listing, "list_contains_old": OLD in listing,
                "detail_status": detail.status_code, "detail_has_6_1":
                    detail.get_data(as_text=True).count('chip chip-ok">通过') == 6
                    and detail.get_data(as_text=True).count('chip chip-warn">未通过') == 1})
    conn = wf.connect()
    try:
        out["rows"] = {"workorder": conn.execute("SELECT COUNT(*) FROM workorder").fetchone()[0],
                       "workorder_event": conn.execute("SELECT COUNT(*) FROM workorder_event").fetchone()[0],
                       "workorder_export": conn.execute("SELECT COUNT(*) FROM workorder_export").fetchone()[0]}
        out["ids"] = [r[0] for r in conn.execute("SELECT workorder_id FROM workorder").fetchall()]
    finally:
        conn.close()
    out["db_sha256_after"] = hashlib.sha256(PROD_DB.read_bytes()).hexdigest()
    (B12 / "id_mapping.json").write_bytes(json.dumps(out, ensure_ascii=False, indent=1).encode())
    print(json.dumps(out, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
