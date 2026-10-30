"""S6 备份/恢复脚本测试（B-01/B-02/B-03/B-06/R-02 的离线子集；**不联网、不写业务库**）。

全程使用隔离 tmp DB（``tests/api/b2_helpers.new_client``）与 tmp 备份/恢复目录；
业务库仅作为**路径守卫输入**出现（``--business-db`` 指向 tmp 哨兵，不打开真实业务库）。
"""

import hashlib
import json
import pathlib
import shutil
import sqlite3
import sys
import tempfile
import unittest

from tests.api import b2_helpers as b2

ROOT = pathlib.Path(__file__).resolve().parents[2]
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import backup as backup_tool                            # noqa: E402
import restore as restore_tool                          # noqa: E402


def sha256_of(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class BackupRestoreTest(unittest.TestCase):
    def setUp(self):
        self.tmp = pathlib.Path(tempfile.mkdtemp(prefix="bk_"))
        self.client, self.db_path = b2.new_client("bk_src_")
        b2.seed_full(self.client, title="示例-备份恢复")
        self.backup_dir = self.tmp / "backups"

    def make_backup(self, stamp="20261020-120000"):
        return backup_tool.backup(db_path=self.db_path, out_dir=self.backup_dir, stamp=stamp)

    # ---------------------------------------------------------------- B-01 备份
    def test_backup_creates_db_and_manifest(self):
        result = self.make_backup()
        db_path = result["backup_path"]
        manifest_path = result["manifest_path"]
        self.assertEqual(db_path.name, "app-20261020-120000.db")
        self.assertTrue(db_path.is_file() and manifest_path.is_file())
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.assertEqual(manifest["kind"], "sqlite_backup_manifest_v1")
        self.assertEqual(manifest["sha256"], sha256_of(db_path))
        self.assertEqual(manifest["bytes"], db_path.stat().st_size)
        self.assertEqual(manifest["integrity_check"], "ok")
        self.assertEqual(manifest["foreign_key_check"], [])
        self.assertEqual(manifest["schema_version"],
                         backup_tool.build_manifest(db_path)[0]["schema_version"])
        self.assertEqual(manifest["app_max_schema_version"],
                         backup_tool.app_max_schema_version())
        for table in backup_tool.HASH_TABLES:
            self.assertIn(table, manifest["row_hashes"])
            self.assertTrue(manifest["row_hashes"][table]["sha256"])
        for table in backup_tool.COUNT_TABLES:
            self.assertIn(table, manifest["table_counts"])
        # 源库配置里应有种子数据
        self.assertGreaterEqual(manifest["table_counts"]["candidate"], 1)

    def test_backup_refuses_overwrite(self):
        self.make_backup()
        with self.assertRaises(backup_tool.BackupError):
            self.make_backup()                                   # 同名再备份
        self.assertEqual(len(list(self.backup_dir.glob("app-*.db"))), 1)
        err = self._capture(lambda: backup_tool.main(
            ["--db", self.db_path, "--out-dir", str(self.backup_dir), "--stamp", "20261020-120000"]))
        self.assertEqual(err["code"], 2)

    def test_verify_manifest_detects_tampering(self):
        result = self.make_backup()
        manifest = result["manifest"]
        self.assertEqual(backup_tool.verify_manifest(result["backup_path"], manifest), [])
        self.assertEqual(backup_tool.sidecar_files(result["backup_path"]), [])  # 校验不产生旁文件
        tampered = dict(manifest, sha256="0" * 64)
        self.assertTrue(backup_tool.verify_manifest(result["backup_path"], tampered))
        # 篡改清单文件本身 → 校验报问题
        manifest_path = result["manifest_path"]
        manifest_path.write_text(json.dumps(tampered), encoding="utf-8")
        reloaded = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.assertIn("sha256 不一致", backup_tool.verify_manifest(result["backup_path"], reloaded))

    def test_backup_missing_source_rejected(self):
        with self.assertRaises(backup_tool.BackupError):
            backup_tool.backup(db_path=self.tmp / "nope.db", out_dir=self.backup_dir)

    def test_backup_does_not_modify_source_and_adds_no_sidecars(self):
        source = pathlib.Path(self.db_path)
        for leftover in (source.with_name(source.name + "-wal"),
                         source.with_name(source.name + "-shm")):
            leftover.unlink(missing_ok=True)                     # 正常关闭后应无旁文件
        before_sha = sha256_of(source)
        before_counts = b2.counts(self.db_path, "candidate", "demand_signal", "evidence")
        self.make_backup()
        self.assertEqual(sha256_of(source), before_sha)          # 源库文件未被写
        self.assertEqual(b2.counts(self.db_path, "candidate", "demand_signal", "evidence"),
                         before_counts)
        self.assertEqual(backup_tool.sidecar_files(source), [])  # immutable=1：不产生 -wal/-shm

    def test_backup_refuses_source_with_wal_sidecars(self):
        source = pathlib.Path(self.db_path)
        fake_wal = source.with_name(source.name + "-wal")
        fake_wal.write_bytes(b"")
        try:
            with self.assertRaises(backup_tool.BackupError) as ctx:
                self.make_backup()
            self.assertIn("人工确认", str(ctx.exception))
            self.assertEqual(list(self.backup_dir.glob("app-*.db")), [])
        finally:
            fake_wal.unlink(missing_ok=True)

    def test_restore_refuses_backup_with_sidecars(self):
        result = self.make_backup()
        fake_shm = result["backup_path"].with_name(result["backup_path"].name + "-shm")
        fake_shm.write_bytes(b"")
        try:
            target = self.tmp / "restore" / "sidecar" / "app.db"
            with self.assertRaises(restore_tool.RestoreError) as ctx:
                restore_tool.restore(backup_path=result["backup_path"], target=target)
            self.assertIn("人工确认", str(ctx.exception))
            self.assertFalse(target.exists())
        finally:
            fake_shm.unlink(missing_ok=True)

    # ---------------------------------------------------------------- B-02 恢复
    def test_restore_to_isolated_copy_verified(self):
        result = self.make_backup()
        target = self.tmp / "restore" / "run1" / "app.db"
        report = restore_tool.restore(backup_path=result["backup_path"], target=target)
        self.assertTrue(target.is_file())
        self.assertTrue(report["manifest_checked"])
        self.assertEqual(report["sha256"], sha256_of(target))
        self.assertEqual(report["row_hashes"], result["manifest"]["row_hashes"])
        self.assertEqual(report["table_counts"], result["manifest"]["table_counts"])
        self.assertEqual(report["schema_version"], result["manifest"]["schema_version"])
        self.assertEqual(backup_tool.sidecar_files(target), [])      # 恢复副本旁无 -wal/-shm
        conn = sqlite3.connect(str(target))
        try:
            self.assertEqual(conn.execute("PRAGMA integrity_check").fetchone()[0], "ok")
            self.assertEqual(conn.execute("PRAGMA foreign_key_check").fetchall(), [])
            restored = conn.execute("SELECT count(*) FROM candidate").fetchone()[0]
        finally:
            conn.close()
        self.assertEqual(restored, result["manifest"]["table_counts"]["candidate"])

    def test_restore_refuses_existing_target(self):
        result = self.make_backup()
        target = self.tmp / "restore" / "app.db"
        target.parent.mkdir(parents=True)
        target.write_text("existing", encoding="utf-8")
        before = sha256_of(target)
        with self.assertRaises(restore_tool.RestoreError):
            restore_tool.restore(backup_path=result["backup_path"], target=target)
        self.assertEqual(sha256_of(target), before)              # 未覆盖

    def test_restore_refuses_business_db_target(self):
        result = self.make_backup()
        business = self.tmp / "instance" / "app.db"               # 哨兵路径，不打开真实业务库
        with self.assertRaises(restore_tool.RestoreError):
            restore_tool.restore(backup_path=result["backup_path"], target=business,
                                 business_db=business)
        self.assertFalse(business.exists())
        # 位于 instance/ 目录内的其它路径同样拒绝（真实 ROOT/instance 下不落盘）
        guarded = ROOT / "instance" / "restore_test_not_allowed.db"
        with self.assertRaises(restore_tool.RestoreError):
            restore_tool.restore(backup_path=result["backup_path"], target=guarded)
        self.assertFalse(guarded.exists())

    def test_restore_rejects_corrupted_backup(self):
        result = self.make_backup()
        corrupted = self.tmp / "broken.db"
        shutil.copyfile(result["backup_path"], corrupted)
        payload = bytearray(corrupted.read_bytes())
        payload[:16] = b"NOTSQLITE" + payload[7:16]
        corrupted.write_bytes(bytes(payload))
        target = self.tmp / "restore" / "broken" / "app.db"
        err = self._capture(lambda: restore_tool.main(
            ["--backup", str(corrupted), "--target", str(target)]))
        self.assertEqual(err["code"], 2)
        self.assertFalse(target.exists())                          # 无半成品残留

    def test_restore_rejects_manifest_mismatch(self):
        result = self.make_backup()
        manifest = json.loads(result["manifest_path"].read_text(encoding="utf-8"))
        manifest["row_hashes"]["candidate"]["sha256"] = "f" * 64
        bad_manifest = self.tmp / "bad.manifest.json"
        bad_manifest.write_text(json.dumps(manifest), encoding="utf-8")
        target = self.tmp / "restore" / "mismatch" / "app.db"
        err = self._capture(lambda: restore_tool.main(
            ["--backup", str(result["backup_path"]), "--target", str(target),
             "--manifest", str(bad_manifest)]))
        self.assertEqual(err["code"], 2)
        self.assertFalse(target.exists())

    def test_restore_rejects_higher_schema_version(self):
        """R-02：库版本高于应用支持版本 → 恢复层明确拒绝（应用层不拒绝的差距如实保留）。"""
        result = self.make_backup()
        higher = self.tmp / "higher.db"
        shutil.copyfile(result["backup_path"], higher)
        conn = sqlite3.connect(str(higher))
        try:
            version = conn.execute("SELECT MAX(version) FROM schema_migrations").fetchone()[0]
            conn.execute("INSERT INTO schema_migrations(version, name, applied_at) VALUES (?,?,?)",
                         (int(version) + 99, "manual_future.sql", "2026-10-20T00:00:00Z"))
            conn.commit()
        finally:
            conn.close()
        target = self.tmp / "restore" / "higher" / "app.db"
        with self.assertRaises(restore_tool.RestoreError) as ctx:
            restore_tool.restore(backup_path=higher, target=target, manifest=result["manifest_path"])
        self.assertIn("库版本高于应用支持版本", str(ctx.exception))
        self.assertFalse(target.exists())

    # ---------------------------------------------------------------- CLI
    def test_cli_backup_and_restore(self):
        code = backup_tool.main(["--db", self.db_path, "--out-dir", str(self.backup_dir),
                                 "--stamp", "20261020-130000"])
        self.assertEqual(code, 0)
        backup_file = self.backup_dir / "app-20261020-130000.db"
        self.assertTrue(backup_file.is_file())
        target = self.tmp / "restore" / "cli" / "app.db"
        code = restore_tool.main(["--backup", str(backup_file), "--target", str(target)])
        self.assertEqual(code, 0)
        self.assertTrue(target.is_file())

    def _capture(self, fn):
        import contextlib
        import io
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = fn()
        return {"code": code, "stdout": out.getvalue(), "stderr": err.getvalue()}


if __name__ == "__main__":
    unittest.main()
