"""Two-round synthetic category-count test (temp DB)."""

from __future__ import annotations

import pathlib
import tempfile
import unittest

from tools.selection import categories, db
from tests.test_selection_categories import insert


class RoundTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.conn = db.init_db(pathlib.Path(self.tmp.name) / "s.sqlite3")

    def tearDown(self):
        self.conn.close()
        self.tmp.cleanup()

    def _run(self, sid, title, quote, platform="xianyu"):
        insert(self.conn, sid, title, quote, platform)
        return categories.categorize_signal(
            self.conn, dict(self.conn.execute("SELECT * FROM signals WHERE id=?", (sid,)).fetchone()))

    def test_two_round_counts(self):
        # round 1: 6 rows -> 3 categories (notion vs excel are same coarse template only
        # when audience/task are equal; use a different task for the third category)
        self._run(1, "学习计划 Notion 模板", "学生 学习计划 notion 模板", "xianyu")
        self._run(2, "学习计划 Notion 模板", "学生 学习计划 notion 模板", "xianyu")  # duplicate
        c_excel = self._run(3, "客户 Excel 表格", "自由职业 客户 excel 表格", "bilibili")
        self._run(4, "AI 提示词模板", "创作者 提示词 模板", "xianyu")
        self._run(5, "AI 提示词模板", "创作者 提示词 模板", "bilibili")  # cross-platform duplicate
        self._run(6, "随便", "没有关键词", "xianyu")  # review
        cats1 = self.conn.execute("SELECT COUNT(*) FROM categories").fetchone()[0]
        review1 = self.conn.execute("SELECT COUNT(*) FROM review_queue WHERE status='pending'").fetchone()[0]
        self.assertEqual((cats1, review1), (3, 1))
        # round 2: 8 rows: old update, excluded review, new task/family, review
        self._run(7, "客户 Excel 表格 新版", "自由职业 客户 excel 表格", "xianyu")  # update
        self._run(8, "自由职业客户 CRM", "自由职业 客户 管理 excel 表格", "xianyu")  # same coarse category
        self._run(9, "设计素材包", "设计师 设计素材 矢量 PSD", "xianyu")  # new family/task
        categories.exclude(self.conn, c_excel["category_id"])
        self._run(10, "客户 Excel 表格 排除后", "自由职业 客户 excel 表格", "xianyu")  # excluded -> review
        self._run(11, "客户 Excel 表格 新证据", "自由职业 客户 excel 表格", "bilibili")  # excluded -> review
        self._run(12, "学生考试倒计时 Excel", "学生 考试 倒计时 excel 表格", "xianyu")  # new task
        self._run(13, "未知", "完全无关键词", "xianyu")  # review
        self._run(14, "设计师简历作品集 PSD", "设计师 简历 作品集 PSD", "xianyu")  # new task/family
        cats2 = self.conn.execute("SELECT COUNT(*) FROM categories").fetchone()[0]
        review2 = self.conn.execute("SELECT COUNT(*) FROM review_queue WHERE status='pending'").fetchone()[0]
        self.assertEqual(cats2, 6)
        self.assertEqual(review2, 4)
        # no hard delete: all signals remain; duplicate #2 has no event
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM signals").fetchone()[0], 14)
        signal_events = self.conn.execute("SELECT COUNT(*) FROM discovery_event WHERE signal_id IS NOT NULL").fetchone()[0]
        self.assertEqual(signal_events, 10)
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM discovery_event WHERE kind='exclude'").fetchone()[0], 1)
        # excluded category stays excluded and its new signals are reviews, not updates
        self.assertEqual(self.conn.execute("SELECT status FROM categories WHERE id=?", (c_excel["category_id"],)).fetchone()[0], "excluded")
        self.assertEqual(self.conn.execute("SELECT category_id FROM discovery_event WHERE signal_id=10").fetchone(), None)

if __name__ == "__main__":
    unittest.main()
