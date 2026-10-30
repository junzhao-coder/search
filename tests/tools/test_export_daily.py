"""C 导出脚本测试：只读复用 daily_digest、JSON/CSV 落盘、参数与 instance 拒绝。

全程隔离 tmp DB（``tests/api/b2_helpers.new_client``），**不联网**、不写业务库。
"""

import contextlib
import hashlib
import importlib.util
import io
import json
import pathlib
import tempfile
import unittest

from tests.api import b2_helpers as b2

ROOT = pathlib.Path(__file__).resolve().parents[2]
TOOL_PATH = ROOT / "tools" / "export_daily.py"
AS_OF = "2026-10-20T12:00:00Z"


def load_tool():
    spec = importlib.util.spec_from_file_location("export_daily_tool", TOOL_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


export_daily = load_tool()


def _seed(db_path: str) -> tuple:
    """在给定库上建一条完整候选（复用 b2 夹具，走真实 import API）。"""
    from app import create_app
    client = create_app({"db_path": db_path}).test_client()
    candidate_id, supply_id = b2.seed_full(client, title="示例-导出每日摘要")
    b2.add_default_costs(client, candidate_id, supply_id)
    b2.verify_all_gates(client, candidate_id, supply_id)
    return client, candidate_id, supply_id


def _read_text(path: pathlib.Path) -> str:
    raw = path.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf"), "不应写出 UTF-8 BOM"
    return raw.decode("utf-8")          # 严格 UTF-8；坏字节会抛错


class ExportDailyTest(unittest.TestCase):
    def setUp(self):
        self.out_dir = pathlib.Path(tempfile.mkdtemp(prefix="export_out_")) / "reports"
        self.client, self.db_path = b2.new_client("export_")
        _seed(self.db_path)

    def export(self, **kwargs):
        params = {"db_path": self.db_path, "as_of": AS_OF, "out_dir": self.out_dir}
        params.update(kwargs)
        return export_daily.export(**params)

    # ---------------------------------------------------------------- 落盘
    def test_exports_json_and_csv_utf8(self):
        result = self.export()
        digest = result["digest"]
        date = digest["digest_date"]
        json_path = self.out_dir / f"daily-{date}.json"
        csv_path = self.out_dir / f"daily-{date}.csv"
        self.assertEqual(result["json_path"], json_path)
        self.assertEqual(result["csv_path"], csv_path)
        self.assertTrue(json_path.is_file() and csv_path.is_file())

        text = _read_text(json_path)
        payload = json.loads(text)
        self.assertEqual(payload["kind"], "daily_digest")
        self.assertEqual(payload["as_of"], AS_OF)
        self.assertEqual(payload["digest_date"], date)
        self.assertEqual(payload["daily_limit"], 5)
        self.assertEqual(payload, digest)                     # 文件即 daily_digest 输出
        self.assertIn("每日摘要", text)                        # ensure_ascii=False：中文原文可读
        for pool in ("top", "blocked", "observing", "exploring"):
            self.assertIn(pool, payload)
        self.assertEqual(sorted(payload["counts"]),
                         sorted(["top", "blocked", "observing", "exploring", "omitted",
                                 "insufficient", "excluded"]))

        csv_text = _read_text(csv_path)
        lines = [line for line in csv_text.splitlines() if line]
        self.assertEqual(lines[0].split(","), list(export_daily.CSV_COLUMNS))
        expected_rows = sum(len(digest[pool]) for pool in
                            ("top", "blocked", "observing", "exploring"))
        self.assertEqual(len(lines) - 1, expected_rows)

    def test_as_of_and_limit_are_honored(self):
        result = self.export(limit=2)
        self.assertEqual(result["digest"]["daily_limit"], 2)
        self.assertEqual(result["digest"]["as_of"], AS_OF)
        self.assertEqual(result["digest"]["digest_date"], AS_OF[:10])
        invalid = "2026-10-20 12:00:00"                        # 非 ISO-8601 UTC
        with self.assertRaises(export_daily.ExportError):
            self.export(as_of=invalid)
        with self.assertRaises(export_daily.ExportError):
            self.export(limit=0)

    def test_out_dir_custom_created(self):
        nested = self.out_dir / "a" / "b"
        result = self.export(out_dir=nested)
        self.assertTrue(result["json_path"].is_file())
        self.assertEqual(result["json_path"].parent, nested)

    # ---------------------------------------------------------------- 只读/拒绝
    def test_rejects_instance_out_dir(self):
        inst_out = ROOT / "instance" / "export_daily_out"
        for out_dir in (inst_out, "instance/export_daily_out"):
            with self.assertRaises(export_daily.ExportError):
                self.export(out_dir=out_dir)
            self.assertFalse(inst_out.exists())          # 拒绝：不创建目录、不写文件
        err = io.StringIO()
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(err):
            code = export_daily.main(["--db", self.db_path, "--as-of", AS_OF,
                                      "--out-dir", str(inst_out)])
        self.assertEqual(code, 2)
        self.assertIn("instance", err.getvalue())
        self.assertFalse(inst_out.exists())

    def test_instance_input_is_readonly_allowed(self):
        """输入库允许 instance/app.db：用 tmp 构造 instance 目录并 monkeypatch ROOT 指向，不读真实业务库。"""
        from unittest import mock
        tmp_root = pathlib.Path(tempfile.mkdtemp(prefix="export_instance_"))
        inst = tmp_root / "instance"
        inst.mkdir()
        db = inst / "app.db"
        _seed(str(db))
        before = b2.counts(str(db), "candidate", "demand_signal", "evidence")
        with mock.patch.object(export_daily, "_INSTANCE_DIR", inst), \
             mock.patch.object(export_daily, "DEFAULT_DB", db):
            out = tmp_root / "reports"
            result = export_daily.export(db_path=str(db), as_of=AS_OF, out_dir=out)
            self.assertTrue(result["json_path"].is_file())      # 只读打开成功
            self.assertEqual(b2.counts(str(db), "candidate", "demand_signal", "evidence"),
                             before)                                # 未写库
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(io.StringIO()):
                code = export_daily.main(["--as-of", AS_OF, "--limit", "2",
                                          "--out-dir", str(out / "cli")])
            self.assertEqual(code, 0)                               # 默认 --db 走 patched instance/app.db
            self.assertIn("export_daily: ok", buf.getvalue())

    def test_rejects_missing_database(self):
        missing = pathlib.Path(tempfile.mkdtemp(prefix="export_missing_")) / "nope.db"
        with self.assertRaises(export_daily.ExportError):
            self.export(db_path=missing)
        self.assertFalse(self.out_dir.exists())

    def test_export_is_read_only(self):
        tables = ("candidate", "demand_signal", "evidence", "run_record", "supply_offer")
        before = b2.counts(self.db_path, *tables)
        self.export()
        self.assertEqual(b2.counts(self.db_path, *tables), before)

    # ---------------------------------------------------------------- CLI
    def test_cli_success_writes_files(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            code = export_daily.main(["--db", self.db_path, "--as-of", AS_OF,
                                      "--limit", "2", "--out-dir", str(self.out_dir)])
        self.assertEqual(code, 0)
        self.assertTrue(list(self.out_dir.glob("daily-*.json")))
        self.assertTrue(list(self.out_dir.glob("daily-*.csv")))
        self.assertIn("export_daily: ok", out.getvalue())

    def test_cli_requires_as_of(self):
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as ctx:
                export_daily.main(["--db", self.db_path])
        self.assertEqual(ctx.exception.code, 2)                 # --as-of 必填

    def test_cli_rejects_bad_as_of_and_instance_out_dir(self):
        inst_out = ROOT / "instance" / "export_daily_cli_out"
        for argv in (["--db", self.db_path, "--as-of", "2026/10/20 12:00",
                      "--out-dir", str(self.out_dir)],
                     ["--db", self.db_path, "--as-of", AS_OF, "--out-dir", str(inst_out)]):
            err = io.StringIO()
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(err):
                code = export_daily.main(argv)
            self.assertEqual(code, 2)
            self.assertIn("export_daily:", err.getvalue())
        self.assertFalse(inst_out.exists())

if __name__ == "__main__":
    unittest.main()
