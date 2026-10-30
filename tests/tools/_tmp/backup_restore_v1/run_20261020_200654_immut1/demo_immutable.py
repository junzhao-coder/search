import hashlib, json, pathlib, sys
run = pathlib.Path(__file__).resolve().parent
ROOT = pathlib.Path(__file__).resolve().parents[5]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "tools"))
from app import create_app
from tests.api import b2_helpers as b2
import backup, restore
def sha(p): return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()
db = run / "demo" / "source.db"
client = create_app({"db_path": str(db)}).test_client()
b2.seed_full(client, title="示例-S6 immutable 演示")
src = pathlib.Path(db)
for leftover in (src.with_name(src.name + "-wal"), src.with_name(src.name + "-shm")):
    leftover.unlink(missing_ok=True)
before = sha(src)
result = backup.backup(db_path=db, out_dir=run/"backups", stamp="20261020-160000")
target = run / "restore" / "run1" / "app.db"
report = restore.restore(backup_path=result["backup_path"], target=target)
after = sha(src)
summary = {
  "source_sha_unchanged": before == after,
  "source_sidecars_after": [p.name for p in backup.sidecar_files(src)],
  "backup_sidecars_after": [p.name for p in backup.sidecar_files(result["backup_path"])],
  "restore_target_sidecars_after": [p.name for p in backup.sidecar_files(target)],
  "backup": {"path": str(result["backup_path"]), "sha256": result["manifest"]["sha256"],
             "bytes": result["manifest"]["bytes"], "schema_version": result["manifest"]["schema_version"],
             "integrity": result["manifest"]["integrity_check"],
             "row_hashes": {k: v["sha256"] for k, v in result["manifest"]["row_hashes"].items()}},
  "restore": {"manifest_checked": report["manifest_checked"], "schema_version": report["schema_version"],
              "row_hashes_equal": report["row_hashes"] == result["manifest"]["row_hashes"],
              "counts_equal": report["table_counts"] == result["manifest"]["table_counts"]},
}
(run / "20_immutable_demo.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")
print(json.dumps(summary, ensure_ascii=False, indent=1))
