"""离线测试：v18 单帖采集的隔离存储（不联网、不跑真实平台）。

覆盖：同 ID 不同平台、无 ID 内容、未知 vs 0、父级三态、时间组、文本三态、
冲突回滚、run target、续跑/停止历史、应用标识与 schema 识别、v1 迁移、
23 列兼容映射、可运行入口。运行：

    .venv\\Scripts\\python.exe -m unittest tests.test_v18_storage -v
"""

from __future__ import annotations

import csv
import hashlib
import json
import sqlite3
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path

from tools.selection.access import records as rec
from tools.selection.access import tieba
from tools.selection.storage import compat, store
from tools.selection.storage.__main__ import main as cli_main

TID = "11066015202"

#: 上一版（v1）的 schema 原文，用来构造"旧版已生成的库"做迁移验证。
LEGACY_V1_SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
  run_id TEXT PRIMARY KEY,
  platform TEXT NOT NULL,
  target_native_id TEXT,
  started_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  stop_reason TEXT,
  complete INTEGER NOT NULL DEFAULT 0 CHECK (complete IN (0, 1)),
  declared_count INTEGER,
  note TEXT
);

CREATE TABLE IF NOT EXISTS items (
  item_id INTEGER PRIMARY KEY AUTOINCREMENT,
  platform TEXT NOT NULL,
  kind TEXT NOT NULL CHECK (kind IN ('post', 'comment')),
  native_id TEXT,
  id_verified INTEGER NOT NULL CHECK (id_verified IN (0, 1)),
  parent_native_id TEXT,
  parent_kind TEXT CHECK (parent_kind IS NULL OR parent_kind IN ('post', 'comment')),
  post_native_id TEXT,
  url TEXT,
  title TEXT,
  text TEXT,
  text_truncated INTEGER CHECK (text_truncated IS NULL OR text_truncated IN (0, 1)),
  author TEXT,
  likes INTEGER,
  comments_count INTEGER,
  published_at_raw TEXT,
  published_at TEXT,
  published_at_precision TEXT,
  collected_at TEXT NOT NULL,
  last_seen_at TEXT NOT NULL,
  first_run_id TEXT REFERENCES runs(run_id),
  last_run_id TEXT REFERENCES runs(run_id),
  needs_recheck INTEGER NOT NULL DEFAULT 0 CHECK (needs_recheck IN (0, 1)),
  source TEXT,
  evidence_json TEXT,
  not_applicable_json TEXT,
  CHECK (id_verified = (native_id IS NOT NULL)),
  CHECK (kind <> 'comment' OR post_native_id IS NOT NULL)
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_items_identity
  ON items(platform, kind, native_id) WHERE native_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS ix_items_thread ON items(platform, post_native_id);
CREATE INDEX IF NOT EXISTS ix_items_parent ON items(platform, parent_native_id);
"""


def make_post(native_id=TID, **extra):
    values = {"platform": "tieba", "kind": store.POST, "native_id": native_id}
    values.update(extra)
    return store.Item(**values)


def make_comment(native_id, *, platform="tieba", post_id=TID,
                 parent_known=True, **extra):
    values = {"platform": platform, "kind": store.COMMENT,
              "native_id": native_id, "post_native_id": post_id,
              "parent_known": parent_known}
    values.update(extra)
    return store.Item(**values)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def make_v1_db(path: Path, *, extra_sql: str = "") -> None:
    con = sqlite3.connect(str(path))
    con.executescript(LEGACY_V1_SCHEMA)
    if extra_sql:
        con.executescript(extra_sql)
    con.execute("PRAGMA user_version=1")
    con.execute(
        "INSERT INTO runs(run_id, platform, target_native_id, started_at, updated_at,"
        " stop_reason, complete, declared_count, note) VALUES (?,?,?,?,?,?,?,?,?)",
        ("legacy-run", "tieba", TID, "2026-11-01T00:00:00Z",
         "2026-11-01T01:00:00Z", "cancelled", 0, 63, "旧运行"))
    con.execute(
        "INSERT INTO items(platform, kind, native_id, id_verified, parent_native_id,"
        " parent_kind, post_native_id, text, collected_at, last_seen_at,"
        " needs_recheck) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        ("tieba", "comment", "1001", 1, TID, "post", TID, "旧评论",
         "2026-11-01T00:00:00Z", "2026-11-01T00:00:00Z", 0))
    con.commit()
    con.close()


class StorageCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.db = Path(self._tmp.name) / "store.sqlite3"
        self.box = store.Storage(self.db)

    def tearDown(self):
        self.box.close()
        self._tmp.cleanup()


class IdentityTests(StorageCase):
    def test_same_native_id_on_different_platforms_is_two_rows(self):
        self.box.save([make_post(),
                       store.Item(platform="bilibili", kind=store.POST,
                                  native_id=TID)])
        self.assertEqual(self.box.counts()["items"], 2)
        self.assertEqual(self.box.get("tieba", store.POST, TID)["platform"], "tieba")
        self.assertEqual(self.box.get("bilibili", store.POST, TID)["platform"],
                         "bilibili")

    def test_same_identity_is_idempotent_and_keeps_first_seen(self):
        run = self.box.begin_run("tieba", target_native_id=TID)
        self.box.save([make_post(text="v1", likes=None,
                                 collected_at="2026-11-01T00:00:00Z")], run_id=run)
        saved = self.box.save([make_post(text="v2", likes=7,
                                         collected_at="2026-11-02T00:00:00Z")],
                              run_id=run)
        self.assertEqual((saved["inserted"], saved["updated"]), (0, 1))
        self.assertEqual(self.box.counts()["items"], 1)
        row = self.box.get("tieba", store.POST, TID)
        self.assertEqual(row["text"], "v2")
        self.assertEqual(row["likes"], 7)
        self.assertEqual(row["collected_at"], "2026-11-01T00:00:00Z")
        self.assertEqual(row["last_seen_at"], "2026-11-02T00:00:00Z")

    def test_post_and_comment_with_same_native_id_do_not_collide(self):
        self.box.save([make_post("777"), make_comment("777", post_id="777")])
        self.assertEqual(self.box.counts()["items"], 2)


class NoIdTests(StorageCase):
    def test_no_id_content_is_kept_without_fake_id(self):
        item = store.Item(platform="tieba", kind=store.COMMENT, native_id=None,
                          post_native_id=TID, parent_known=False,
                          text="楼中楼没有稳定 ID",
                          url=tieba.THREAD_URL.format(tid=TID))
        saved = self.box.save([item])
        self.assertEqual(saved["without_native_id"], 1)
        row = self.box.items(platform="tieba")[0]
        self.assertIsNone(row["native_id"])
        self.assertFalse(row["id_verified"])
        self.assertTrue(row["needs_recheck"])
        self.assertEqual(row["text"], "楼中楼没有稳定 ID")

    def test_no_id_observations_are_never_merged(self):
        item = store.Item(platform="tieba", kind=store.COMMENT, native_id=None,
                          post_native_id=TID, parent_known=False,
                          text="同文本也不合并")
        first = self.box.save([item])
        second = self.box.save([item])
        self.assertEqual((first["without_native_id"],
                          second["without_native_id"]), (1, 1))
        rows = self.box.items(platform="tieba")
        self.assertEqual(len(rows), 2)
        self.assertTrue(all(row["native_id"] is None for row in rows))
        self.assertEqual(self.box.counts()["without_native_id"], 2)

    def test_no_id_row_does_not_claim_support_in_compat_export(self):
        self.box.save([store.Item(platform="tieba", kind=store.COMMENT,
                                  native_id=None, post_native_id=TID,
                                  parent_known=False, text="待回查")])
        out = Path(self._tmp.name) / "no_id.csv"
        compat.export_compat(self.box, out, platform="tieba")
        with out.open(encoding="utf-8", newline="") as handle:
            row = next(csv.DictReader(handle))
        self.assertEqual(row["native_id"], "")
        self.assertEqual(row["supported"], "false")
        self.assertIn("native_id", row["missing"].split(";"))
        self.assertEqual(row["text"], "待回查")


class ParentTests(StorageCase):
    def test_unknown_parent_is_not_defaulted_to_post(self):
        item = make_comment("1001", parent_known=False, text="父评论未知")
        self.assertFalse(item.parent_known)
        self.assertIsNone(item.parent_native_id)
        self.assertIsNone(item.parent_kind)
        self.assertTrue(item.needs_recheck)
        self.box.save([make_post(), item])
        row = self.box.get("tieba", store.COMMENT, "1001")
        self.assertFalse(row["parent_known"])
        self.assertIsNone(row["parent_native_id"])
        self.assertIsNone(row["parent_kind"])
        self.assertTrue(row["needs_recheck"])
        self.assertEqual(row["post_native_id"], TID)
        self.assertEqual(self.box.children("tieba", TID), [])   # 不冒充直接子评论
        self.assertEqual([r["native_id"] for r in self.box.thread("tieba", TID)],
                         [TID, "1001"])

    def test_known_top_level_is_explicit(self):
        item = make_comment("1001")
        self.assertTrue(item.parent_known)
        self.assertEqual(item.parent_native_id, TID)
        self.assertEqual(item.parent_kind, store.POST)
        self.assertFalse(item.needs_recheck)

    def test_known_nested_parent(self):
        item = make_comment("1002", parent_native_id="1001",
                            parent_kind=store.COMMENT)
        self.assertTrue(item.parent_known)
        self.assertEqual(item.parent_kind, store.COMMENT)

    def test_unknown_parent_upgrades_to_known(self):
        self.box.save([make_comment("1001", parent_known=False)])
        self.box.save([make_comment("1001", parent_native_id="1000",
                                    parent_kind=store.COMMENT)])
        row = self.box.get("tieba", store.COMMENT, "1001")
        self.assertTrue(row["parent_known"])
        self.assertEqual(row["parent_native_id"], "1000")
        self.assertEqual(row["parent_kind"], store.COMMENT)
        self.assertFalse(row["needs_recheck"])

    def test_unknown_parent_does_not_downgrade_known(self):
        self.box.save([make_comment("1001")])
        self.box.save([make_comment("1001", parent_known=False)])
        row = self.box.get("tieba", store.COMMENT, "1001")
        self.assertTrue(row["parent_known"])
        self.assertEqual(row["parent_native_id"], TID)
        self.assertFalse(row["needs_recheck"])

    def test_parent_conflict_rolls_back(self):
        self.box.save([make_comment("1001", parent_native_id="1000",
                                    parent_kind=store.COMMENT)])
        with self.assertRaises(ValueError) as ctx:
            self.box.save([make_post(),
                           make_comment("1001", parent_native_id="1003",
                                        parent_kind=store.COMMENT)])
        self.assertIn("parent_conflict", str(ctx.exception))
        self.assertEqual(self.box.counts()["items"], 1)      # 帖子也没有写进去
        row = self.box.get("tieba", store.COMMENT, "1001")
        self.assertEqual(row["parent_native_id"], "1000")

    def test_post_conflict_rolls_back(self):
        self.box.save([make_comment("1001")])
        with self.assertRaises(ValueError) as ctx:
            self.box.save([make_post("777"),
                           make_comment("1001", post_id="999")])
        self.assertIn("post_conflict", str(ctx.exception))
        self.assertEqual(self.box.counts()["items"], 1)
        self.assertEqual(self.box.get("tieba", store.COMMENT, "1001")["post_native_id"],
                         TID)

    def test_unknown_parent_with_parent_id_is_rejected(self):
        with self.assertRaises(ValueError):
            make_comment("1001", parent_known=False, parent_native_id="1000")

    def test_parent_kind_must_match_the_parent(self):
        with self.assertRaises(ValueError):
            make_comment("1002", parent_native_id="1001", parent_kind=store.POST)
        with self.assertRaises(ValueError):
            make_comment("1002", parent_native_id=TID, parent_kind=store.COMMENT)

    def test_comment_requires_post_attribution(self):
        with self.assertRaises(ValueError):
            store.Item(platform="tieba", kind=store.COMMENT, native_id="1")

    def test_post_cannot_have_a_parent(self):
        with self.assertRaises(ValueError):
            store.Item(platform="tieba", kind=store.POST, native_id=TID,
                       parent_native_id=TID)


class TimeGroupTests(StorageCase):
    def test_new_raw_does_not_pair_with_old_normalized(self):
        self.box.save([make_comment(
            "1", published_at_raw="昨天", published_at="2026-11-01T08:00:00Z",
            published_at_precision="relative")])
        self.box.save([make_comment("1", published_at_raw="今天")])
        row = self.box.get("tieba", store.COMMENT, "1")
        self.assertEqual(row["published_at_raw"], "今天")
        self.assertIsNone(row["published_at"])
        self.assertIsNone(row["published_at_precision"])

    def test_same_raw_keeps_old_normalized(self):
        self.box.save([make_comment(
            "1", published_at_raw="10-31 12:34",
            published_at="2026-10-31T04:34:00Z",
            published_at_precision="minute")])
        self.box.save([make_comment("1", published_at_raw="10-31 12:34")])
        row = self.box.get("tieba", store.COMMENT, "1")
        self.assertEqual(row["published_at"], "2026-10-31T04:34:00Z")
        self.assertEqual(row["published_at_precision"], "minute")

    def test_full_triple_replaces(self):
        self.box.save([make_comment(
            "1", published_at_raw="昨天", published_at="2026-11-01T08:00:00Z",
            published_at_precision="relative")])
        self.box.save([make_comment(
            "1", published_at_raw="今天 09:15", published_at="2026-11-02T09:15:00Z",
            published_at_precision="minute")])
        row = self.box.get("tieba", store.COMMENT, "1")
        self.assertEqual(row["published_at_raw"], "今天 09:15")
        self.assertEqual(row["published_at"], "2026-11-02T09:15:00Z")
        self.assertEqual(row["published_at_precision"], "minute")

    def test_new_normalized_without_raw_clears_mismatched_raw(self):
        self.box.save([make_comment(
            "1", published_at_raw="昨天", published_at="2026-11-01T08:00:00Z",
            published_at_precision="relative")])
        self.box.save([make_comment("1", published_at="2026-11-02T09:15:00Z",
                                    published_at_precision="minute")])
        row = self.box.get("tieba", store.COMMENT, "1")
        self.assertIsNone(row["published_at_raw"])
        self.assertEqual(row["published_at"], "2026-11-02T09:15:00Z")

    def test_precision_without_normalized_is_rejected(self):
        with self.assertRaises(ValueError):
            make_comment("1", published_at_raw="10-31",
                         published_at_precision="day")


class TextTriStateTests(StorageCase):
    def test_truncated_snippet_does_not_replace_full_body(self):
        """现实例子：详情页拿全正文后，搜索摘要的截断文本不能覆盖它。"""
        self.box.save([make_comment("1", text="完整正文" * 20, text_truncated=False)])
        self.box.save([make_comment("1", text="完整正文…", text_truncated=True)])
        row = self.box.get("tieba", store.COMMENT, "1")
        self.assertEqual(row["text"], "完整正文" * 20)
        self.assertFalse(row["text_truncated"])

    def test_full_text_replaces_truncated(self):
        self.box.save([make_comment("1", text="短…", text_truncated=True)])
        self.box.save([make_comment("1", text="完整正文", text_truncated=False)])
        row = self.box.get("tieba", store.COMMENT, "1")
        self.assertEqual(row["text"], "完整正文")
        self.assertFalse(row["text_truncated"])

    def test_unknown_old_is_not_replaced_by_truncated(self):
        self.box.save([make_comment("1", text="旧文本")])          # 完整性未知
        self.box.save([make_comment("1", text="截断…", text_truncated=True)])
        row = self.box.get("tieba", store.COMMENT, "1")
        self.assertEqual(row["text"], "旧文本")
        self.assertIsNone(row["text_truncated"])

    def test_same_text_keeps_known_full_flag(self):
        self.box.save([make_comment("1", text="正文", text_truncated=False)])
        self.box.save([make_comment("1", text="正文")])
        row = self.box.get("tieba", store.COMMENT, "1")
        self.assertEqual(row["text"], "正文")
        self.assertFalse(row["text_truncated"])

    def test_unknown_flag_is_recorded_when_text_changes(self):
        self.box.save([make_comment("1", text="正文", text_truncated=False)])
        self.box.save([make_comment("1", text="正文（改）")])
        row = self.box.get("tieba", store.COMMENT, "1")
        self.assertEqual(row["text"], "正文（改）")
        self.assertIsNone(row["text_truncated"])

    def test_realistic_detail_then_search_then_detail(self):
        self.box.save([make_comment("1", text="完整正文", text_truncated=False)])
        self.box.save([make_comment("1", text="完整…", text_truncated=True)])
        self.box.save([make_comment("1", text="完整正文", text_truncated=False)])
        row = self.box.get("tieba", store.COMMENT, "1")
        self.assertEqual(row["text"], "完整正文")
        self.assertFalse(row["text_truncated"])

    def test_missing_body_then_truncated_then_full_chain(self):
        """现实链：新建缺正文 → 搜索摘要（截断）→ 详情页完整正文。"""
        self.box.save([make_comment("1")])                  # 还没有正文
        self.assertIsNone(self.box.get("tieba", store.COMMENT, "1")["text"])

        self.box.save([make_comment("1", text="摘要…", text_truncated=True)])
        row = self.box.get("tieba", store.COMMENT, "1")
        self.assertEqual(row["text"], "摘要…")             # 唯一可得的正文必须保留
        self.assertTrue(row["text_truncated"])

        truncated_csv = Path(self._tmp.name) / "truncated.csv"
        compat.export_compat(self.box, truncated_csv, platform="tieba")
        with truncated_csv.open(encoding="utf-8", newline="") as handle:
            exported = next(csv.DictReader(handle))
        self.assertEqual(exported["text"], "摘要…")
        self.assertEqual(exported["text_truncated"], "true")
        self.assertNotIn("text", exported["missing"].split(";"))

        self.box.save([make_comment("1", text="完整正文", text_truncated=False)])
        row = self.box.get("tieba", store.COMMENT, "1")
        self.assertEqual(row["text"], "完整正文")
        self.assertFalse(row["text_truncated"])

        full_csv = Path(self._tmp.name) / "full_body.csv"
        compat.export_compat(self.box, full_csv, platform="tieba")
        with full_csv.open(encoding="utf-8", newline="") as handle:
            exported = next(csv.DictReader(handle))
        self.assertEqual(exported["text"], "完整正文")
        self.assertEqual(exported["text_truncated"], "false")

    def test_same_text_completeness_upgrades_from_unknown(self):
        self.box.save([make_comment("1", text="正文")])     # 完整性未知
        self.box.save([make_comment("1", text="正文", text_truncated=True)])
        row = self.box.get("tieba", store.COMMENT, "1")
        self.assertEqual(row["text"], "正文")
        self.assertTrue(row["text_truncated"])              # 未知 -> 已知截断
        self.box.save([make_comment("1", text="正文", text_truncated=False)])
        row = self.box.get("tieba", store.COMMENT, "1")
        self.assertFalse(row["text_truncated"])             # 已知截断 -> 已知完整

    def test_same_text_known_full_is_not_downgraded(self):
        self.box.save([make_comment("1", text="正文", text_truncated=False)])
        self.box.save([make_comment("1", text="正文", text_truncated=True)])
        row = self.box.get("tieba", store.COMMENT, "1")
        self.assertFalse(row["text_truncated"])

    def test_truncated_flag_requires_text(self):
        with self.assertRaises(ValueError):
            make_comment("1", text=None, text_truncated=True)


class NotApplicableTests(StorageCase):
    @staticmethod
    def legacy_comment(**extra):
        values = {"native_id": "1001", "type": "comment", "parent_id": TID,
                  "root_comment_id": TID, "text": "评论", "author": "用户A",
                  "comments": 2, "url": tieba.THREAD_URL.format(tid=TID)}
        values.update(extra)
        return rec.make_record(
            values=values,
            evidence={"native_id": "json:post_list[].id",
                      "type": "constant:comment",
                      "url": "input:thread_url"},
            collected_at="2026-11-02T00:00:00Z", source="tieba:page_pc",
            not_applicable=("title", "voteup", "reposts"))

    def _export(self, name="compat.csv"):
        out = Path(self._tmp.name) / name
        compat.export_compat(self.box, out, platform="tieba")
        with out.open(encoding="utf-8", newline="") as handle:
            return next(csv.DictReader(handle))

    def test_not_applicable_dropped_when_value_arrives(self):
        legacy = self.legacy_comment(likes=None)
        legacy["not_applicable"] = ["title", "voteup", "reposts", "likes"]
        self.box.save([compat.item_from_record(legacy, platform="tieba")])
        self.box.save([make_comment("1001", likes=0, text="评论")])
        row = self._export()
        self.assertEqual(row["likes"], "0")
        self.assertNotIn("likes", row["not_applicable"].split(";"))
        self.assertNotIn("likes", row["missing"].split(";"))
        self.assertEqual(row["text"], "评论")
        self.assertEqual(row["author"], "用户A")

    def test_not_applicable_kept_when_value_still_unknown(self):
        legacy = self.legacy_comment(likes=None)
        legacy["not_applicable"] = ["title", "voteup", "reposts", "likes"]
        self.box.save([compat.item_from_record(legacy, platform="tieba")])
        self.box.save([make_comment("1001", text="评论")])
        row = self._export()
        self.assertEqual(row["likes"], "")
        self.assertIn("likes", row["not_applicable"].split(";"))
        self.assertNotIn("likes", row["missing"].split(";"))

    def test_unknown_then_zero_is_neither_missing_nor_na(self):
        self.box.save([compat.item_from_record(self.legacy_comment(likes=None),
                                               platform="tieba")])
        self.box.save([make_comment("1001", likes=0, text="评论")])
        row = self._export()
        self.assertEqual(row["likes"], "0")
        self.assertNotIn("likes", row["missing"].split(";"))
        self.assertNotIn("likes", row["not_applicable"].split(";"))

    def test_other_fields_survive_na_cleanup(self):
        self.box.save([compat.item_from_record(self.legacy_comment(likes=None),
                                               platform="tieba")])
        self.box.save([make_comment("1001", likes=5, text="评论（改）",
                                    author="用户B")])
        row = self._export()
        self.assertEqual(row["text"], "评论（改）")
        self.assertEqual(row["author"], "用户B")
        self.assertEqual(row["comments"], "2")
        self.assertEqual(row["root_comment_id"], TID)
        self.assertEqual(row["likes"], "5")

    def test_full_export_also_cleans_not_applicable(self):
        legacy = self.legacy_comment(likes=None)
        legacy["not_applicable"] = ["title", "voteup", "reposts", "likes"]
        self.box.save([compat.item_from_record(legacy, platform="tieba")])
        self.box.save([make_comment("1001", likes=0, text="评论")])
        out = Path(self._tmp.name) / "full.jsonl"
        compat.export_items(self.box, out, platform="tieba")
        stored = json.loads(out.read_text(encoding="utf-8").splitlines()[0])
        self.assertEqual(stored["likes"], 0)
        self.assertNotIn("likes", stored["not_applicable"])


class RecheckTests(StorageCase):
    def test_explicit_recheck_survives_ordinary_recollect(self):
        self.box.save([make_comment("1001", recheck=True)])
        row = self.box.get("tieba", store.COMMENT, "1001")
        self.assertTrue(row["needs_recheck"])
        self.assertTrue(row["recheck_explicit"])
        self.box.save([make_comment("1001")])               # 普通重采
        row = self.box.get("tieba", store.COMMENT, "1001")
        self.assertTrue(row["needs_recheck"])
        self.assertTrue(row["recheck_explicit"])

    def test_explicit_recheck_survives_parent_upgrade(self):
        self.box.save([make_comment("1001", parent_known=False, recheck=True)])
        self.box.save([make_comment("1001", parent_native_id="1000",
                                    parent_kind=store.COMMENT)])
        row = self.box.get("tieba", store.COMMENT, "1001")
        self.assertTrue(row["parent_known"])
        self.assertTrue(row["needs_recheck"])               # 显式复核仍在
        self.assertTrue(row["recheck_explicit"])

    def test_auto_recheck_clears_on_parent_upgrade(self):
        self.box.save([make_comment("1001", parent_known=False)])
        row = self.box.get("tieba", store.COMMENT, "1001")
        self.assertTrue(row["needs_recheck"])
        self.assertFalse(row["recheck_explicit"])
        self.box.save([make_comment("1001", parent_native_id="1000",
                                    parent_kind=store.COMMENT)])
        row = self.box.get("tieba", store.COMMENT, "1001")
        self.assertFalse(row["needs_recheck"])              # 自动原因已解除
        self.assertFalse(row["recheck_explicit"])

    def test_no_id_recheck_is_automatic(self):
        self.box.save([store.Item(platform="tieba", kind=store.COMMENT,
                                  native_id=None, post_native_id=TID,
                                  parent_known=False, text="无 ID")])
        row = self.box.items()[0]
        self.assertTrue(row["needs_recheck"])
        self.assertFalse(row["recheck_explicit"])


class EvidenceMergeTests(StorageCase):
    def _comment(self, native_id="1001"):
        return self.box.get("tieba", store.COMMENT, native_id)

    def _export(self, name="evidence.csv"):
        out = Path(self._tmp.name) / name
        compat.export_compat(self.box, out, platform="tieba")
        with out.open(encoding="utf-8", newline="") as handle:
            return next(csv.DictReader(handle))

    def test_rejected_summary_keeps_detail_evidence(self):
        self.box.save([make_comment(
            "1001", text="完整正文", text_truncated=False,
            evidence={"text": "html:span.pb-text-wrapper[detail]"})])
        self.box.save([make_comment(
            "1001", text="摘要…", text_truncated=True,
            evidence={"text": "html:.search-snippet"})])
        row = self._comment()
        self.assertEqual(row["text"], "完整正文")
        self.assertEqual(row["evidence"]["text"],
                         "html:span.pb-text-wrapper[detail]")
        exported = self._export()
        self.assertEqual(exported["text"], "完整正文")
        self.assertEqual(json.loads(exported["field_evidence"])["text"],
                         "html:span.pb-text-wrapper[detail]")

    def test_missing_body_then_summary_then_full_evidence_follows_value(self):
        self.box.save([make_comment("1001")])                  # 还没有正文
        self.box.save([make_comment(
            "1001", text="摘要…", text_truncated=True,
            evidence={"text": "html:.search-snippet"})])
        row = self._comment()
        self.assertEqual(row["text"], "摘要…")
        self.assertEqual(row["evidence"]["text"], "html:.search-snippet")
        self.box.save([make_comment(
            "1001", text="完整正文", text_truncated=False,
            evidence={"text": "html:span.pb-text-wrapper[detail]"})])
        row = self._comment()
        self.assertEqual(row["text"], "完整正文")
        self.assertEqual(row["evidence"]["text"],
                         "html:span.pb-text-wrapper[detail]")

    def test_time_group_evidence_cleared_when_group_replaced(self):
        self.box.save([make_comment(
            "1001", published_at_raw="昨天",
            published_at="2026-11-01T08:00:00Z",
            published_at_precision="relative",
            evidence={"published_at": "html:old-time"})])
        self.box.save([make_comment("1001", published_at_raw="今天")])
        row = self._comment()
        self.assertEqual(row["published_at_raw"], "今天")
        self.assertIsNone(row["published_at"])
        self.assertIsNone(row["evidence"].get("published_at"))
        self.box.save([make_comment(
            "1001", published_at_raw="今天 09:15",
            published_at="2026-11-02T09:15:00Z",
            published_at_precision="minute",
            evidence={"published_at": "json:time"})])
        self.assertEqual(self._comment()["evidence"]["published_at"], "json:time")

    def test_likes_evidence_follows_value(self):
        self.box.save([make_comment("1001", likes=5,
                                    evidence={"likes": "json:agree"})])
        self.box.save([make_comment("1001", likes=0)])
        row = self._comment()
        self.assertEqual(row["likes"], 0)
        self.assertIsNone(row["evidence"].get("likes"))
        self.box.save([make_comment("1001", likes=0,
                                    evidence={"likes": "json:agree2"})])
        self.assertEqual(self._comment()["evidence"]["likes"], "json:agree2")

    def test_same_value_keeps_old_evidence(self):
        self.box.save([make_comment("1001", text="正文",
                                    evidence={"text": "html:detail"})])
        self.box.save([make_comment("1001", text="正文",
                                    evidence={"text": "html:other"})])
        self.assertEqual(self._comment()["evidence"]["text"], "html:detail")

    def test_title_evidence_follows_value_on_posts(self):
        self.box.save([make_post(title="旧标题",
                                 evidence={"title": "html:old-title"})])
        self.box.save([make_post(title="新标题")])
        self.assertIsNone(self.box.get("tieba", store.POST, TID)["evidence"].get(
            "title"))
        self.box.save([make_post(title="新标题",
                                 evidence={"title": "html:new-title"})])
        self.assertEqual(self.box.get("tieba", store.POST, TID)["evidence"]["title"],
                         "html:new-title")


class UnknownVsZeroTests(StorageCase):
    def test_unknown_likes_stay_null_and_zero_stays_zero(self):
        self.box.save([make_comment("1", likes=None), make_comment("2", likes=0)])
        rows = {row["native_id"]: row for row in self.box.items(platform="tieba")}
        self.assertIsNone(rows["1"]["likes"])
        self.assertEqual(rows["2"]["likes"], 0)

    def test_unknown_is_not_exported_as_zero(self):
        self.box.save([make_comment("1", likes=None), make_comment("2", likes=0)])
        out = Path(self._tmp.name) / "likes.csv"
        compat.export_compat(self.box, out, platform="tieba")
        with out.open(encoding="utf-8", newline="") as handle:
            rows = {row["native_id"]: row for row in csv.DictReader(handle)}
        self.assertEqual(rows["1"]["likes"], "")
        self.assertEqual(rows["2"]["likes"], "0")
        self.assertIn("likes", rows["1"]["missing"].split(";"))

    def test_published_time_keeps_raw_normalized_and_precision(self):
        self.box.save([make_comment(
            "1", published_at_raw="10-31 12:34",
            published_at="2026-10-31T04:34:00Z", published_at_precision="minute")])
        row = self.box.items(platform="tieba")[0]
        self.assertEqual(row["published_at_raw"], "10-31 12:34")
        self.assertEqual(row["published_at"], "2026-10-31T04:34:00Z")
        self.assertEqual(row["published_at_precision"], "minute")
        full = Path(self._tmp.name) / "full.jsonl"
        compat.export_items(self.box, full, platform="tieba")
        stored = json.loads(full.read_text(encoding="utf-8").splitlines()[0])
        self.assertEqual(stored["published_at_precision"], "minute")
        self.assertEqual(stored["published_at_raw"], "10-31 12:34")
        compat_csv = Path(self._tmp.name) / "compat.csv"
        compat.export_compat(self.box, compat_csv, platform="tieba")
        with compat_csv.open(encoding="utf-8", newline="") as handle:
            exported = next(csv.DictReader(handle))
        self.assertEqual(exported["published_at"], "2026-10-31T04:34:00Z")

    def test_bad_precision_is_rejected(self):
        with self.assertRaises(ValueError):
            make_comment("1", published_at="2026-11-02T00:00:00Z",
                         published_at_precision="banana")


class RunStateTests(StorageCase):
    def test_resume_clears_complete_and_keeps_stop_history(self):
        run = self.box.begin_run("tieba", target_native_id=TID)
        self.box.save([make_post()], run_id=run)
        finished = self.box.finish_run(run, stop_reason=store.STOP_CANCELLED)
        self.assertFalse(finished["complete"])
        self.assertFalse(finished["pending"])
        self.assertEqual(len(finished["stop_history"]), 1)

        self.box.begin_run("tieba", run_id=run)
        summary = self.box.run_summary(run)
        self.assertTrue(summary["pending"])
        self.assertFalse(summary["complete"])            # 运行中不显示已完成
        self.assertEqual(summary["resumes"], 1)
        self.assertEqual(summary["previous_stop_reason"], store.STOP_CANCELLED)
        self.assertEqual(len(summary["stop_history"]), 1)

        done = self.box.finish_run(run, stop_reason=store.STOP_END, complete=True)
        self.assertTrue(done["complete"])
        self.assertEqual(len(done["stop_history"]), 2)

    def test_interrupted_run_is_pending_not_complete(self):
        run = self.box.begin_run("tieba", target_native_id=TID)
        self.box.save([make_post()], run_id=run)
        self.box.close()
        self.box = store.Storage(self.db)
        summary = self.box.run_summary(run)
        self.assertTrue(summary["pending"])
        self.assertFalse(summary["complete"])
        self.assertIsNone(summary["stop_reason"])
        self.assertEqual(summary["items_first_seen"], 1)

    def test_complete_requires_end_signal(self):
        run = self.box.begin_run("tieba", target_native_id=TID)
        with self.assertRaises(ValueError):
            self.box.finish_run(run, stop_reason=store.STOP_CANCELLED,
                                complete=True)
        summary = self.box.run_summary(run)
        self.assertIsNone(summary["stop_reason"])
        self.assertEqual(summary["stop_history"], [])

    def test_unknown_stop_reason_is_rejected(self):
        run = self.box.begin_run("tieba", target_native_id=TID)
        with self.assertRaises(ValueError):
            self.box.finish_run(run, stop_reason="done")

    def test_restart_resumes_without_duplicates(self):
        run = self.box.begin_run("tieba", target_native_id=TID)
        self.box.save([make_post(text="正文"), make_comment("1001", text="c1")],
                      run_id=run)
        self.box.close()
        self.box = store.Storage(self.db)
        self.assertEqual(self.box.begin_run("tieba", run_id=run), run)
        saved = self.box.save([make_post(text="正文"),
                               make_comment("1001", text="c1"),
                               make_comment("1002")], run_id=run)
        self.assertEqual((saved["inserted"], saved["updated"]), (1, 2))
        finished = self.box.finish_run(run, stop_reason=store.STOP_END,
                                       complete=True, declared_count=3)
        self.assertEqual(finished["thread_items"], 3)
        self.assertEqual(finished["declared_count"], 3)

    def test_same_run_id_rejects_other_platform_or_target(self):
        run = self.box.begin_run("tieba", target_native_id=TID)
        with self.assertRaises(ValueError):
            self.box.begin_run("bilibili", run_id=run)
        with self.assertRaises(ValueError):
            self.box.begin_run("tieba", run_id=run, target_native_id="999")


class RunTargetTests(StorageCase):
    def test_run_target_derived_from_batch(self):
        run = self.box.begin_run("tieba")
        self.box.save([make_comment("1001")], run_id=run)
        self.assertEqual(self.box.run_summary(run)["target_native_id"], TID)
        with self.assertRaises(ValueError):
            self.box.save([make_comment("2001", post_id="999")], run_id=run)

    def test_run_target_conflict_in_batch(self):
        run = self.box.begin_run("tieba")
        with self.assertRaises(ValueError) as ctx:
            self.box.save([make_comment("1001"),
                           make_comment("2001", post_id="999")], run_id=run)
        self.assertIn("run_target_conflict", str(ctx.exception))
        self.assertEqual(self.box.counts()["items"], 0)
        self.assertIsNone(self.box.run_summary(run)["target_native_id"])

    def test_run_target_mismatch_rolls_back(self):
        run = self.box.begin_run("tieba", target_native_id=TID)
        with self.assertRaises(ValueError) as ctx:
            self.box.save([make_comment("1001"),
                           make_comment("2001", post_id="999")], run_id=run)
        self.assertIn("run_target_mismatch", str(ctx.exception))
        self.assertEqual(self.box.counts()["items"], 0)

    def test_two_runs_do_not_cross_posts(self):
        run_a = self.box.begin_run("tieba", target_native_id="111")
        run_b = self.box.begin_run("tieba", target_native_id="222")
        self.box.save([make_comment("1001", post_id="111")], run_id=run_a)
        self.box.save([make_comment("2001", post_id="222")], run_id=run_b)
        with self.assertRaises(ValueError):
            self.box.save([make_comment("3001", post_id="222")], run_id=run_a)
        self.assertEqual([r["native_id"] for r in self.box.thread("tieba", "111")],
                         ["1001"])
        self.assertEqual([r["native_id"] for r in self.box.thread("tieba", "222")],
                         ["2001"])

    def test_derived_target_rolls_back_on_conflict(self):
        self.box.save([make_comment("1001", parent_native_id="1000",
                                    parent_kind=store.COMMENT)])
        run = self.box.begin_run("tieba")            # 目标未知，等本批证据补
        with self.assertRaises(ValueError) as ctx:
            self.box.save([make_comment("1002"),
                           make_comment("1001", parent_native_id="1003",
                                        parent_kind=store.COMMENT)], run_id=run)
        self.assertIn("parent_conflict", str(ctx.exception))
        self.assertIsNone(self.box.run_summary(run)["target_native_id"])
        self.assertEqual(self.box.counts()["items"], 1)   # 只保留冲突前已有的行


class CompatTests(StorageCase):
    def test_legacy_tieba_comment_round_trips_through_23_columns(self):
        payload = {"post_list": [{"id": 1001, "content": "第一条评论",
                                  "author_id": 7, "time": 1762000000,
                                  "agree": {"agree_num": 5},
                                  "sub_post_number": 2, "floor": 1}],
                   "user_list": [{"id": 7, "name_show": "用户A"}],
                   "page": {"current_page": 1, "total_page": 1, "has_more": 0}}
        legacy = tieba.parse_comments_api(payload, TID, collected_at=(
            "2026-11-02T00:00:00Z"))["records"][0]
        item = compat.item_from_record(legacy, platform="tieba")
        self.assertTrue(item.parent_known)
        self.box.save([item])
        row = self.box.items(platform="tieba")[0]
        self.assertEqual(compat.record_from_row(row), rec.normalize_record(legacy))

    def test_legacy_thread_record_round_trips_through_23_columns(self):
        legacy = rec.make_record(
            values={"native_id": TID, "type": "thread",
                    "url": tieba.THREAD_URL.format(tid=TID), "title": "标题",
                    "text": "正文", "published_at": "10-31 12:34",
                    "comments": 63, "author": "楼主"},
            evidence={"native_id": "url:/p/<tid>", "type": "constant:thread",
                      "url": "input:thread_url", "title": "html:span.pb-title",
                      "text": "html:span.pb-text-wrapper",
                      "published_at": "html:div.image-text span.post-num",
                      "comments": "html:a#tab-全部回复",
                      "author": "html:div.image-text a.head-name"},
            collected_at="2026-11-02T00:00:00Z", source="tieba:detail",
            not_applicable=("root_comment_id", "parent_id", "voteup", "reposts"))
        self.box.save([compat.item_from_record(legacy, platform="tieba")])
        row = self.box.items(platform="tieba")[0]
        self.assertEqual(compat.record_from_row(row), rec.normalize_record(legacy))

    def test_legacy_parent_equals_thread_is_top_level(self):
        legacy = rec.make_record(
            values={"native_id": "1001", "type": "comment", "parent_id": TID,
                    "root_comment_id": TID, "text": "评论"},
            evidence={"native_id": "json:post_list[].id",
                      "type": "constant:comment"},
            collected_at="2026-11-02T00:00:00Z", source="tieba:page_pc",
            not_applicable=("title", "voteup", "reposts"))
        item = compat.item_from_record(legacy, platform="tieba")
        self.assertTrue(item.parent_known)
        self.assertEqual(item.parent_native_id, TID)
        self.assertEqual(item.parent_kind, store.POST)

    def test_legacy_missing_parent_is_unknown(self):
        legacy = rec.make_record(
            values={"native_id": "1001", "type": "comment",
                    "root_comment_id": TID, "text": "评论"},
            evidence={"native_id": "json:post_list[].id",
                      "type": "constant:comment"},
            collected_at="2026-11-02T00:00:00Z", source="tieba:page_pc",
            not_applicable=("title", "voteup", "reposts"))
        item = compat.item_from_record(legacy, platform="tieba")
        self.assertFalse(item.parent_known)
        self.assertIsNone(item.parent_native_id)
        self.assertTrue(item.needs_recheck)
        self.box.save([item])
        exported = compat.record_from_row(self.box.items()[0])
        self.assertIsNone(exported["parent_id"])
        self.assertIn("parent_id", exported["missing"])
        self.assertEqual(exported["root_comment_id"], TID)

    def test_legacy_comment_without_post_attribution_is_rejected(self):
        with self.assertRaises(ValueError):
            compat.item_from_record({"type": "comment", "native_id": "1",
                                     "text": "x"}, platform="tieba")

    def test_numeric_legacy_ids_are_kept_as_text(self):
        legacy = {"type": "comment", "native_id": 1001,
                  "parent_id": 11066015202, "root_comment_id": 11066015202,
                  "text": "数字 ID"}
        item = compat.item_from_record(legacy, platform="tieba")
        self.assertEqual(item.native_id, "1001")
        self.assertEqual(item.post_native_id, "11066015202")
        self.assertEqual(item.parent_native_id, "11066015202")

    def test_compat_csv_has_exactly_the_legacy_23_columns(self):
        self.box.save([make_post(), make_comment("1001")])
        out = Path(self._tmp.name) / "tieba.csv"
        result = compat.export_compat(self.box, out, platform="tieba")
        self.assertEqual(result["columns"], 23)
        with out.open(encoding="utf-8", newline="") as handle:
            reader = csv.reader(handle)
            header = next(reader)
            rows = list(reader)
        self.assertEqual(header, list(rec.EXPORT_FIELDS))
        self.assertEqual(len(header), 23)
        self.assertEqual(len(rows), 2)

    def test_compat_export_is_platform_scoped(self):
        self.box.save([make_post(),
                       store.Item(platform="bilibili", kind=store.POST,
                                  native_id=TID)])
        out = Path(self._tmp.name) / "tieba.csv"
        self.assertEqual(compat.export_compat(self.box, out,
                                              platform="tieba")["count"], 1)

    def test_compat_export_requires_platform(self):
        with self.assertRaises(ValueError):
            compat.export_compat(self.box, Path(self._tmp.name) / "x.csv",
                                 platform="")

    def test_full_export_keeps_storage_only_fields(self):
        self.box.save([make_comment("1", likes=None, published_at_raw="昨天",
                                    published_at="2026-11-01T00:00:00Z",
                                    published_at_precision="relative")])
        out = Path(self._tmp.name) / "full.jsonl"
        compat.export_items(self.box, out, platform="tieba")
        stored = json.loads(out.read_text(encoding="utf-8").splitlines()[0])
        self.assertEqual(stored["platform"], "tieba")
        self.assertIsNone(stored["likes"])
        self.assertTrue(stored["id_verified"])
        self.assertTrue(stored["parent_known"])
        self.assertFalse(stored["recheck_explicit"])
        self.assertFalse(stored["needs_recheck"])
        self.assertEqual(stored["published_at_precision"], "relative")
        self.assertEqual(stored["parent_kind"], "post")


class IsolationTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def _expect_reject(self, path: Path, message: str) -> None:
        with self.assertRaises(RuntimeError) as ctx:
            store.Storage(path)
        self.assertIn(message, str(ctx.exception))

    def _sidecars(self, path: Path) -> list:
        return sorted(p.name for p in self.root.iterdir()
                      if p.name != path.name and p.name.startswith(path.name))

    def test_empty_file_creates_store_and_stamps_identity(self):
        path = self.root / "empty.sqlite3"
        path.write_bytes(b"")
        with store.Storage(path) as box:
            self.assertEqual(box.counts()["items"], 0)
        con = sqlite3.connect(str(path))
        try:
            self.assertEqual(con.execute("PRAGMA application_id").fetchone()[0],
                             store.APPLICATION_ID)
            self.assertEqual(con.execute("PRAGMA user_version").fetchone()[0],
                             store.SCHEMA_VERSION)
        finally:
            con.close()
        with store.Storage(path) as box:          # 自身重开可用
            self.assertEqual(box.counts()["items"], 0)

    def test_reopening_own_store_keeps_identity(self):
        path = self.root / "own.sqlite3"
        with store.Storage(path) as box:
            box.save([make_post()])
        with store.Storage(path) as box:
            self.assertEqual(box.counts()["items"], 1)
        con = sqlite3.connect(str(path))
        try:
            self.assertEqual(con.execute("PRAGMA application_id").fetchone()[0],
                             store.APPLICATION_ID)
            self.assertEqual(con.execute("PRAGMA user_version").fetchone()[0],
                             store.SCHEMA_VERSION)
        finally:
            con.close()

    def test_foreign_db_rejected_unchanged(self):
        path = self.root / "platform_tieba.sqlite3"
        con = sqlite3.connect(str(path))
        con.execute("CREATE TABLE locks(site TEXT PRIMARY KEY, reason TEXT)")
        con.execute("PRAGMA user_version=1")
        con.commit()
        con.close()
        before = digest(path)
        self._expect_reject(path, "not_a_v18_store")
        self.assertEqual(digest(path), before)
        self.assertEqual(self._sidecars(path), [])
        con = sqlite3.connect(str(path))
        try:
            names = {row[0] for row in con.execute(
                "SELECT name FROM sqlite_master WHERE type='table'")}
            mode = con.execute("PRAGMA journal_mode").fetchone()[0].lower()
        finally:
            con.close()
        self.assertEqual(names, {"locks"})
        self.assertNotEqual(mode, "wal")

    def test_same_name_tables_wrong_columns_rejected_unchanged(self):
        path = self.root / "sames.sqlite3"
        con = sqlite3.connect(str(path))
        con.execute("CREATE TABLE runs(x TEXT)")
        con.execute("CREATE TABLE items(y TEXT)")
        con.execute("PRAGMA user_version=1")
        con.commit()
        con.close()
        before = digest(path)
        self._expect_reject(path, "not_a_v18_store")
        self.assertEqual(digest(path), before)
        self.assertEqual(self._sidecars(path), [])

    def test_views_only_db_rejected_unchanged(self):
        path = self.root / "view.sqlite3"
        con = sqlite3.connect(str(path))
        con.execute("CREATE VIEW v AS SELECT 1 AS x")
        con.execute("PRAGMA user_version=1")
        con.commit()
        con.close()
        before = digest(path)
        self._expect_reject(path, "not_a_v18_store")
        self.assertEqual(digest(path), before)

    def test_garbage_file_rejected_unchanged(self):
        path = self.root / "garbage.sqlite3"
        path.write_bytes(b"not a database at all")
        before = digest(path)
        self._expect_reject(path, "not_a_v18_store")
        self.assertEqual(digest(path), before)

    def test_wrong_application_id_rejected_unchanged(self):
        path = self.root / "own.sqlite3"
        with store.Storage(path) as box:
            box.save([make_post()])
        con = sqlite3.connect(str(path))
        con.execute("PRAGMA application_id=12345")
        con.commit()
        con.close()
        before = digest(path)
        self._expect_reject(path, "not_a_v18_store")
        self.assertEqual(digest(path), before)

    def test_future_schema_version_rejected_unchanged(self):
        path = self.root / "own.sqlite3"
        with store.Storage(path) as box:
            box.save([make_post()])
        con = sqlite3.connect(str(path))
        con.execute("PRAGMA user_version=99")
        con.commit()
        con.close()
        before = digest(path)
        self._expect_reject(path, "schema_version_mismatch:99")
        self.assertEqual(digest(path), before)

    def test_legacy_v1_store_is_migrated_with_history(self):
        path = self.root / "legacy.sqlite3"
        make_v1_db(path)
        with store.Storage(path) as box:
            self.assertEqual(box.counts()["items"], 1)
            row = box.items()[0]
            self.assertEqual(row["text"], "旧评论")
            self.assertTrue(row["parent_known"])       # 旧语义：父级都是已知
            self.assertFalse(row["recheck_explicit"])
            summary = box.run_summary("legacy-run")
            self.assertEqual(summary["previous_stop_reason"], "cancelled")
            self.assertEqual(len(summary["stop_history"]), 1)
            self.assertEqual(summary["stop_history"][0]["at"],
                             "2026-11-01T01:00:00Z")
        con = sqlite3.connect(str(path))
        try:
            self.assertEqual(con.execute("PRAGMA application_id").fetchone()[0],
                             store.APPLICATION_ID)
            self.assertEqual(con.execute("PRAGMA user_version").fetchone()[0],
                             store.SCHEMA_VERSION)
        finally:
            con.close()
        with store.Storage(path) as box:               # 迁移后再开可用
            self.assertEqual(box.counts()["items"], 1)

    def test_legacy_v2_store_is_migrated(self):
        path = self.root / "legacy_v2.sqlite3"
        with store.Storage(path) as box:
            box.save([make_comment("1001", parent_known=False)])
            box.save([make_comment("1002")])
        con = sqlite3.connect(str(path))
        con.execute("UPDATE items SET needs_recheck=1 WHERE native_id='1002'")
        con.execute("ALTER TABLE items DROP COLUMN recheck_explicit")
        con.execute("PRAGMA user_version=2")
        con.commit()
        con.close()
        with store.Storage(path) as box:
            rows = {row["native_id"]: row for row in box.items()}
            # 父级未知：自动复核保留，但不冒充显式
            self.assertTrue(rows["1001"]["needs_recheck"])
            self.assertFalse(rows["1001"]["recheck_explicit"])
            # 旧库里无法由身份/父级解释的 1：迁移为显式复核
            self.assertTrue(rows["1002"]["needs_recheck"])
            self.assertTrue(rows["1002"]["recheck_explicit"])
        con = sqlite3.connect(str(path))
        try:
            self.assertEqual(con.execute("PRAGMA user_version").fetchone()[0],
                             store.SCHEMA_VERSION)
        finally:
            con.close()

    def test_legacy_v1_with_extra_table_rejected_unchanged(self):
        path = self.root / "legacy_extra.sqlite3"
        make_v1_db(path, extra_sql="CREATE TABLE notes(x TEXT);")
        before = digest(path)
        self._expect_reject(path, "not_a_v18_store")
        self.assertEqual(digest(path), before)

    def test_legacy_v1_with_wrong_columns_rejected_unchanged(self):
        path = self.root / "legacy_bad.sqlite3"
        make_v1_db(path)
        con = sqlite3.connect(str(path))
        con.execute("ALTER TABLE items ADD COLUMN extra TEXT")
        con.commit()
        con.close()
        before = digest(path)
        self._expect_reject(path, "not_a_v18_store")
        self.assertEqual(digest(path), before)


class CliTests(unittest.TestCase):
    def test_ingest_export_stats_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            record = rec.make_record(
                values={"native_id": "1001", "type": "comment",
                        "parent_id": TID, "url": tieba.THREAD_URL.format(tid=TID),
                        "text": "命令行导入", "likes": 0,
                        "published_at": "10-31 12:34",
                        "root_comment_id": TID},
                evidence={"native_id": "json:post_list[].id",
                          "type": "constant:comment",
                          "url": "input:thread_url"},
                collected_at="2026-11-02T00:00:00Z", source="tieba:page_pc",
                not_applicable=("title", "voteup", "reposts"))
            records = root / "records.jsonl"
            records.write_text(json.dumps(record, ensure_ascii=False) + "\n",
                               encoding="utf-8")
            db = root / "cli.sqlite3"
            out = root / "cli.csv"
            with redirect_stdout(StringIO()) as captured:
                self.assertEqual(cli_main([
                    "ingest", "--db", str(db), "--platform", "tieba",
                    "--records", str(records), "--target", TID,
                    "--stop", "cancelled"]), 0)
            self.assertIn("cancelled", captured.getvalue())
            with redirect_stdout(StringIO()):
                self.assertEqual(cli_main([
                    "export", "--db", str(db), "--platform", "tieba",
                    "--out", str(out)]), 0)
            with out.open(encoding="utf-8", newline="") as handle:
                header = next(csv.reader(handle))
            self.assertEqual(header, list(rec.EXPORT_FIELDS))
            with redirect_stdout(StringIO()):
                self.assertEqual(cli_main(["stats", "--db", str(db)]), 0)

    def test_cli_ingest_accepts_utf8_bom_records_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            records = root / "bom.jsonl"
            records.write_text(json.dumps({
                "native_id": "1001", "type": "comment", "parent_id": TID,
                "root_comment_id": TID, "text": "带 BOM"}) + "\n",
                encoding="utf-8-sig")
            db = root / "bom.sqlite3"
            with redirect_stdout(StringIO()):
                self.assertEqual(cli_main([
                    "ingest", "--db", str(db), "--platform", "tieba",
                    "--records", str(records)]), 0)
            with store.Storage(db) as box:
                self.assertEqual(box.counts()["items"], 1)
                self.assertEqual(box.run_summary(
                    box.runs()[0]["run_id"])["target_native_id"], TID)

    def test_cli_rejects_complete_without_end_signal(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            records = root / "records.jsonl"
            records.write_text(json.dumps({
                "native_id": "1001", "type": "comment", "parent_id": TID,
                "root_comment_id": TID, "text": "x"}) + "\n", encoding="utf-8")
            with redirect_stderr(StringIO()) as captured:
                code = cli_main(["ingest", "--db", str(root / "x.sqlite3"),
                                 "--platform", "tieba", "--records",
                                 str(records), "--stop", "cancelled",
                                 "--complete"])
            self.assertEqual(code, 2)
            self.assertIn("complete_requires_end_signal", captured.getvalue())


if __name__ == "__main__":
    unittest.main()
