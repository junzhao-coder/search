import json, pathlib, sqlite3, sys
run = pathlib.Path(__file__).resolve().parent
ROOT = pathlib.Path(__file__).resolve().parents[5]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "tools"))
from app import create_app
from tests.api import b2_helpers as b2
import backup, restore
db = run / "demo" / "source.db"
client = create_app({"db_path": str(db)}).test_client()
b2.seed_full(client, title="示例-S6备份演示")
before = __import__("hashlib").sha256(db.read_bytes()).hexdigest()
result = backup.backup(db_path=db, out_dir=run/"backups", stamp="20261020-140000")
target = run / "restore" / "run1" / "app.db"
report = restore.restore(backup_path=result["backup_path"], target=target)
after = __import__("hashlib").sha256(db.read_bytes()).hexdigest()
guards = []
for guard_target, label in ((ROOT/"instance"/"app.db", "business_db"),
                            (ROOT/"instance"/"x_restore.db", "instance_dir")):
    try:
        restore.restore(backup_path=result["backup_path"], target=guard_target)
        guards.append([label, "NOT_REJECTED"])
    except restore.RestoreError as exc:
        guards.append([label, "rejected", str(exc)[:80]])
summary = {
  "source_sha_unchanged": before == after,
  "backup": {"path": str(result["backup_path"]), "sha256": result["manifest"]["sha256"],
             "bytes": result["manifest"]["bytes"], "schema_version": result["manifest"]["schema_version"],
             "integrity": result["manifest"]["integrity_check"],
             "counts": result["manifest"]["table_counts"], "row_hashes": result["manifest"]["row_hashes"]},
  "restore": {"target": str(report["target"]), "manifest_checked": report["manifest_checked"],
              "schema_version": report["schema_version"], "sha256": report["sha256"]},
  "guard_checks": guards,
  "restored_equals_backup": report["sha256"] == result["manifest"]["sha256"],
}
(run / "20_demo_backup_restore.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")
print(json.dumps(summary, ensure_ascii=False, indent=1))
