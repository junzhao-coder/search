"""B15：生产库迁移（可复跑、幂等）+ 迁移前后证据。

1) 备份生产库到 b15/backup/（UTC 时间戳）；
2) 直接调用 `workflow.init_schema`（不另写 DDL）两次，证明幂等；
3) 记录前后 sha256 与行数、dedupe_key 唯一索引状态；
4) 用真实路由验证生产单详情两区块可见、GET 导出零写（库 sha 不变）。
"""

from __future__ import annotations

import hashlib
import json
import pathlib
import shutil
import sqlite3
import sys
import time

ROOT = pathlib.Path(r"D:\桌面\two")
B15 = ROOT / "docs" / "validation" / "product-workflow" / "b15"
BACKUP = B15 / "backup"
PROD_DB = ROOT / "tools" / "workbench" / "runtime" / "workflow.sqlite3"
WID = "wo:20261023-88ef9a66"
sys.path.insert(0, str(ROOT / "tools" / "workbench"))


def sha(path: pathlib.Path) -> str | None:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None


def counts(path: pathlib.Path) -> dict:
    conn = sqlite3.connect(path)
    try:
        names = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
        out = {t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
               for t in ("workorder", "workorder_event", "workorder_export",
                         "workorder_copy_version", "workorder_publish") if t in names}
        out["tables"] = sorted(names)
        idx = conn.execute("PRAGMA index_list(workorder_export)").fetchall()
        out["export_indexes"] = [{"name": r[1], "unique": bool(r[2])} for r in idx]
        return out
    finally:
        conn.close()


def main() -> int:
    BACKUP.mkdir(parents=True, exist_ok=True)
    out: dict = {"generated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "db": str(PROD_DB),
                 "workorder": WID}
    if not PROD_DB.exists():
        out["error"] = "生产库不存在"
        print(json.dumps(out, ensure_ascii=True))
        return 1
    ts = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    backup = BACKUP / f"workflow-{ts}.sqlite3"
    shutil.copy2(PROD_DB, backup)
    out["backup"] = {"path": str(backup), "sha256": sha(backup)}
    out["before"] = {"sha256": sha(PROD_DB), "counts": counts(PROD_DB)}

    import workflow as wf

    conn = wf.connect()
    try:
        wf.init_schema(conn)
    finally:
        conn.close()
    out["after_first"] = {"sha256": sha(PROD_DB), "counts": counts(PROD_DB)}

    conn = wf.connect()
    try:
        wf.init_schema(conn)
    finally:
        conn.close()
    out["after_second"] = {"sha256": sha(PROD_DB), "counts": counts(PROD_DB)}
    out["idempotent"] = (out["after_first"]["sha256"] == out["after_second"]["sha256"]
                         and out["after_first"]["counts"] == out["after_second"]["counts"])
    out["rows_preserved"] = (out["before"]["counts"].get("workorder") == out["after_second"]["counts"].get("workorder")
                             and out["before"]["counts"].get("workorder_event")
                             == out["after_second"]["counts"].get("workorder_event"))
    out["created_tables"] = [t for t in ("workorder_copy_version", "workorder_publish")
                             if t in out["after_second"]["counts"]["tables"]]
    out["unique_index"] = [i for i in out["after_second"]["counts"]["export_indexes"]
                           if i["name"] == "idx_export_dedupe_unique"]

    # 真实路由验证
    import app as wb
    app = wb.create_app()
    app.testing = True
    client = app.test_client()
    detail = client.get(f"/worksheet/{WID}")
    html = detail.get_data(as_text=True)
    before_export_sha = sha(PROD_DB)
    exp = client.get(f"/worksheet/{WID}/export?format=md")
    after_export_sha = sha(PROD_DB)
    out["verify"] = {"detail_status": detail.status_code,
                     "has_copy_section": "文案版本历史" in html,
                     "has_publish_section": "发布回填" in html,
                     "export_status": exp.status_code,
                     "export_zero_write": before_export_sha == after_export_sha}
    (B15 / "migration.json").write_bytes(json.dumps(out, ensure_ascii=False, indent=1).encode())
    print(json.dumps({k: out[k] for k in ("backup", "idempotent", "rows_preserved", "created_tables",
                                          "unique_index", "verify")}, ensure_ascii=True))
    return 0 if (out["idempotent"] and out["rows_preserved"] and out["verify"]["export_zero_write"]) else 1


if __name__ == "__main__":
    sys.exit(main())
