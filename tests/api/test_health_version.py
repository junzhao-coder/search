"""契约 #24：`/api/health` 必须返回"版本与 schema"（版本字段 + schema_version）。"""

import json
import pathlib
import tempfile
import unittest

from app import APP_VERSION, create_app


class HealthVersionTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="health_")
        self.db_path = str(pathlib.Path(self.tmp) / "app.db")
        self.app = create_app({"db_path": self.db_path})
        self.client = self.app.test_client()

    def test_health_returns_version_and_schema(self):
        response = self.client.get("/api/health")
        self.assertEqual(response.status_code, 200)
        body = response.get_json()
        self.assertEqual(sorted(body), ["ok", "schema_version", "time", "version"])
        self.assertIs(body["ok"], True)
        self.assertEqual(body["schema_version"], 2)          # schema_migrations 最大版本
        self.assertEqual(body["version"], APP_VERSION)       # 契约 #24：版本
        self.assertIsInstance(body["version"], str)
        self.assertTrue(body["version"])
        self.assertRegex(body["time"], r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")

    def test_health_has_no_paths_or_secret_fields(self):
        body = self.client.get("/api/health").get_json()
        raw = json.dumps(body, ensure_ascii=False)
        self.assertNotIn(str(self.tmp), raw)                 # 不含绝对路径
        self.assertNotIn("secret", raw.lower())
        self.assertEqual(set(body), {"ok", "schema_version", "time", "version"})

    def test_health_version_matches_package_version(self):
        import app as app_package
        body = self.client.get("/api/health").get_json()
        self.assertEqual(body["version"], app_package.__version__)
        self.assertEqual(app_package.__version__, app_package.APP_VERSION)


if __name__ == "__main__":
    unittest.main()
