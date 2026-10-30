"""CLI exit codes / stop_reason / import budget behavior (temp DB, no network)."""

from __future__ import annotations

import contextlib
import io
import json
import pathlib
import tempfile
import unittest

from tools.selection import bilibili, cli, db, xianyu


def payload(code=0, data=None):
    return json.dumps({"code": code, "message": "OK", "data": data or {}}).encode()


class FakeFetcher:
    def __init__(self, reply_status=200):
        self.reply_status = reply_status
        self.urls = []

    def __call__(self, url):
        self.urls.append(url)
        if "/view?" in url:
            return bilibili.FetchResult(200, payload(data={
                "aid": 1, "bvid": "BV1", "title": "t"}), {}, url)
        if self.reply_status != 200:
            return bilibili.FetchResult(self.reply_status, b"{}", {}, url)
        return bilibili.FetchResult(200, payload(data={
            "page": {"num": 1, "size": 5, "count": 1},
            "replies": [{"rpid": 1, "root": 0, "parent": 0,
                         "content": {"message": "hello"}, "member": {"mid": 1}}]}), {}, url)


class CliTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = pathlib.Path(self.tmp.name) / "selection.sqlite3"
        self.raw = pathlib.Path(self.tmp.name) / "raw"

    def tearDown(self):
        self.tmp.cleanup()

    def test_complete_returns_zero_and_partial_prints_stop_reason(self):
        orig = bilibili.default_fetch
        try:
            bilibili.default_fetch = FakeFetcher()
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                rc = cli.main(["--db", str(self.db), "--raw-dir", str(self.raw),
                               "run", "bilibili", "--aid", "1", "--interval", "0"])
            self.assertEqual(rc, 0)
            self.assertTrue(json.loads(out.getvalue())["ok"])
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                rc = cli.main(["--db", str(self.db), "--raw-dir", str(self.raw),
                               "run", "bilibili", "--aid", "1", "--budget", "1",
                               "--interval", "0"])
            body = json.loads(out.getvalue())
            self.assertEqual(rc, 0)
            self.assertEqual(body["status"], "partial")
            self.assertEqual(body["stop_reason"], "budget_exhausted")
        finally:
            bilibili.default_fetch = orig

    def test_failed_returns_nonzero_and_keeps_error(self):
        orig = bilibili.default_fetch
        try:
            bilibili.default_fetch = FakeFetcher(reply_status=412)
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                rc = cli.main(["--db", str(self.db), "--raw-dir", str(self.raw),
                               "run", "bilibili", "--aid", "1", "--interval", "0"])
            body = json.loads(out.getvalue())
            self.assertEqual(rc, 3)
            self.assertFalse(body["ok"])
            self.assertEqual(body["stop_reason"], "http_412")
        finally:
            bilibili.default_fetch = orig

    def test_import_rows_exceeded(self):
        src = pathlib.Path(self.tmp.name) / "items.jsonl"
        rows = []
        for i in range(21):
            rows.append(json.dumps({
                "href": f"https://www.goofish.com/item?id={i + 1}&categoryId=1",
                "title": "t", "price": "¥ 1", "raw_text": "¥ 1 1人想要",
                "platform": "xianyu"}, ensure_ascii=False))
        src.write_text("\n".join(rows) + "\n", encoding="utf-8")
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            rc = cli.main(["--db", str(self.db), "import", "xianyu", "--path", str(src),
                           "--max-rows", "20"])
        body = json.loads(out.getvalue())
        self.assertEqual(rc, 0)
        self.assertEqual(body["status"], "stopped")
        self.assertEqual(body["stop_reason"], "rows_exceeded")
        self.assertEqual(body["rows"], 20)
        self.assertEqual(body["new"], 20)
        conn = db.init_db(self.db)
        try:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM signals").fetchone()[0], 20)
            self.assertEqual(conn.execute(
                "SELECT raw_dir FROM runs ORDER BY id DESC LIMIT 1").fetchone()[0], None)
        finally:
            conn.close()

    def test_import_errors_exceeded(self):
        src = pathlib.Path(self.tmp.name) / "items.jsonl"
        rows = [json.dumps({"title": "bad"}) for _ in range(3)]
        src.write_text("\n".join(rows) + "\n", encoding="utf-8")
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            rc = cli.main(["--db", str(self.db), "import", "xianyu", "--path", str(src),
                           "--max-errors", "2"])
        body = json.loads(out.getvalue())
        self.assertEqual(rc, 0)
        self.assertEqual(body["status"], "stopped")
        self.assertEqual(body["stop_reason"], "errors_exceeded")
        self.assertEqual(body["rows"], 2)
        self.assertEqual(len(body["errors"]), 2)


if __name__ == "__main__":
    unittest.main()
