"""CONTRACT L767：库 schema 版本高于代码支持版本时，**启动必须拒绝**。

覆盖：新库正常启动 / 同版本幂等 / 高版本拒绝（create_app 与 ensure_schema 两层）/ 拒绝后库内容不变。
"""

import pathlib
import sqlite3
import tempfile
import unittest

from app import create_app
from app.storage import db as db_module


class SchemaVersionGuardTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="schemaguard_")
        self.db_path = str(pathlib.Path(self.tmp) / "app.db")

    def _insert_future_version(self, version: int = 99) -> None:
        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute("INSERT INTO schema_migrations(version, name, applied_at) VALUES (?,?,?)",
                         (version, "future_manual.sql", "2026-10-20T00:00:00Z"))
            conn.commit()
        finally:
            conn.close()

    def test_fresh_database_boots(self):
        create_app({"db_path": self.db_path})
        self.assertEqual(db_module.schema_version(self.db_path), 2)
        self.assertEqual(db_module.app_schema_version(), 2)

    def test_same_version_is_idempotent(self):
        create_app({"db_path": self.db_path})
        create_app({"db_path": self.db_path})                 # 二次启动不报错、不重复迁移
        conn = sqlite3.connect(self.db_path)
        try:
            versions = [row[0] for row in conn.execute(
                "SELECT version FROM schema_migrations ORDER BY version")]
        finally:
            conn.close()
        self.assertEqual(versions, [1, 2])

    def test_higher_version_refuses_startup(self):
        create_app({"db_path": self.db_path})
        self._insert_future_version(99)
        with self.assertRaises(db_module.SchemaVersionError) as ctx:
            create_app({"db_path": self.db_path})
        message = str(ctx.exception)
        self.assertIn("库版本高于代码支持版本", message)
        self.assertIn("99", message)
        self.assertIn("2", message)
        # 拒绝后数据库未被改动（仍为 2 + 99，未新增迁移、未写业务表）
        self.assertEqual(db_module.schema_version(self.db_path), 99)
        conn = sqlite3.connect(self.db_path)
        try:
            self.assertEqual(conn.execute("SELECT version FROM schema_migrations ORDER BY version").fetchall(),
                             [(1,), (2,), (99,)])
        finally:
            conn.close()

    def test_refused_startup_does_not_write_business_tables(self):
        create_app({"db_path": self.db_path})
        self._insert_future_version(99)
        before = db_module.connect(self.db_path)
        try:
            counts = {table: before.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
                      for table in ("candidate", "demand_signal", "evidence", "run_record")}
        finally:
            before.close()
        with self.assertRaises(db_module.SchemaVersionError):
            create_app({"db_path": self.db_path})
        after = db_module.connect(self.db_path)
        try:
            self.assertEqual({table: after.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
                              for table in ("candidate", "demand_signal", "evidence", "run_record")},
                             counts)
        finally:
            after.close()

    def test_ensure_schema_directly_refuses_higher_version(self):
        create_app({"db_path": self.db_path})
        self._insert_future_version(3)
        with self.assertRaises(db_module.SchemaVersionError):
            db_module.ensure_schema(self.db_path)
        self.assertEqual(db_module.schema_version(self.db_path), 3)

    def test_lower_version_gets_upgraded(self):
        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute("CREATE TABLE schema_migrations ("
                         " version INTEGER PRIMARY KEY, name TEXT NOT NULL, applied_at TEXT NOT NULL)")
            conn.execute("INSERT INTO schema_migrations VALUES (1, '0001_init.sql', '2026-10-20T00:00:00Z')")
            conn.commit()
        finally:
            conn.close()
        create_app({"db_path": self.db_path})                 # 缺 0002 → 升序补齐后启动
        self.assertEqual(db_module.schema_version(self.db_path), 2)


if __name__ == "__main__":
    unittest.main()
