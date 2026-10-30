"""B20：三步向导测试（路由/参数校验/选品建单/找货源确定/写介绍保存与导出守卫）。"""

from __future__ import annotations

import json
import os
import pathlib
import re
import sys
import tempfile
import unittest

WORKBENCH = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(WORKBENCH))

import readiness as rd  # noqa: E402
import supply as sup  # noqa: E402
import workflow as wf  # noqa: E402

SAMPLE = "docs/validation/product-workflow/b7/sample-study-planner-v1.xlsx"


class WizardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tmp = tempfile.TemporaryDirectory()
        root = pathlib.Path(cls.tmp.name)
        cls.db = root / "w.db"
        os.environ["WORKBENCH_WORKFLOW_DB"] = str(cls.db)
        os.environ["WORKBENCH_SECRET_FILE"] = str(root / "s")
        import app as wb
        cls.wb = wb

    @classmethod
    def tearDownClass(cls) -> None:
        for k in ("WORKBENCH_WORKFLOW_DB", "WORKBENCH_SECRET_FILE"):
            os.environ.pop(k, None)
        cls.tmp.cleanup()

    def setUp(self) -> None:
        if self.db.exists():
            self.db.unlink()
        self.app = self.wb.create_app()
        self.app.testing = True
        self.client = self.app.test_client()

    def _token(self) -> str:
        self.client.get("/pick")
        with self.client.session_transaction() as s:
            return s["csrf"]

    def _self_made(self) -> str:
        resp = self.client.post("/worksheet/new", data={
            "csrf": self._token(), "self_made": "1", "submit_key": "b20-1",
            "name": "自制提示词包", "use_case": "会议纪要", "deliverable": "纯文本 .md",
            "target_platform": "xianyu", "fmt": "md"})
        return resp.headers["Location"].rsplit("/", 1)[-1].split("?")[0]

    def _rec(self, wid: str) -> dict:
        conn = wf.connect()
        try:
            return wf.get(conn, wid)
        finally:
            conn.close()

    # ---------- 路由与参数 ----------
    def test_pick_renders_with_wizard_bar(self):
        body = self.client.get("/pick").get_data(as_text=True)
        for label in ("选品", "找货源", "写文案"):
            self.assertIn(label, body)
        self.assertIn('aria-current="step"', body)

    def test_pick_filter_keeps_state(self):
        body = self.client.get("/pick?q=笔记&platform=x").get_data(as_text=True)
        self.assertIn('value="笔记"', body)
        self.assertIn('value="x" selected', body.replace('selected=', 'selected='))

    def test_pick_invalid_param_notice(self):
        body = self.client.get("/pick?err=invalid").get_data(as_text=True)
        self.assertIn("参数无效", body)

    # ---------- 选品页数据与准入（rev8） ----------
    def test_pick_excludes_content_and_marks_pending(self):
        body = self.client.get("/pick").get_data(as_text=True)
        titles = re.findall(r'<td class="cell-title">([^<]+)', body)
        for content_name in ("资源推荐清单", "使用教程", "教学变现"):
            self.assertFalse(any(content_name in t for t in titles), content_name)
        self.assertIn("教程与内容", body)          # 页脚指向内容页
        if "待人工" in body:
            self.assertTrue("需先人工确认品类" in body or "待人工确认" in body)
            for seg in body.split("<tr>"):
                if "需先人工确认品类" in seg:
                    self.assertNotIn("选这个", seg, "待人工行不应有建单按钮")

    def test_pick_sellability_and_sparsity_are_honest(self):
        body = self.client.get("/pick").get_data(as_text=True)
        self.assertIn("未评估", body)
        self.assertIn("competition_norm", body)
        self.assertIn("1=竞争者最少", body)
        self.assertIn("数据快照", body)
        self.assertIn("样本量", body)
        self.assertIn("competition_norm 均值", body)

    def test_pick_pending_row_has_no_button(self):
        app = self.wb.create_app()
        app.testing = True
        client = app.test_client()
        html = client.get("/pick").get_data(as_text=True)
        rows = html.split("<tr>")
        for seg in rows:
            if "需先人工确认品类" in seg:
                self.assertNotIn("选这个", seg)

    # ---------- rev10：两列取值来自真实字段 ----------
    def test_pick_sellability_numeric(self):
        html = self.client.get("/pick").get_data(as_text=True)
        cells = re.findall(r'<td class="num" title="([^"]*)">(\d\.\d{2})（n=(\d+)）</td>', html)
        self.assertTrue(cells, "至少一个组的可售性应为数值")
        values = [float(v) for _t, v, _n in cells]
        self.assertTrue(all(0.0 <= v <= 1.0 for v in values), values)
        # 与 build_categories 的 sellability_mean 对照（±0.01）
        with self.app.app_context():
            data = self.wb.get_data()
            price_stats = data.get("price_stats") or {}
            rows, _state = self.wb.filter_opportunities(data.get("scores") or [], {}, price_stats)
            analyses = {str(r.get("item_id") or ""): self.wb.build_analysis(r, price_stats) for r in rows}
            groups = self.wb.build_categories(rows, analyses, price_stats, data.get("sources") or [],
                                              self.wb.build_text_index())
        expected = [g["sellability_mean"] for g in groups
                    if g.get("sellability_mean") is not None and g.get("category") not in self.wb.taxonomy.CONTENT_NAMES]
        self.assertTrue(expected)
        self.assertTrue(any(abs(v - float(e)) <= 0.01 for v in values for e in expected),
                        f"页面值 {values[:5]} 与组级均值 {expected[:5]} 无匹配")

    def test_pick_sellability_n_never_zero_and_same_scale(self):
        html = self.client.get("/pick").get_data(as_text=True)
        pairs = []
        for seg in html.split("<tr>")[1:]:
            count_m = re.search(r'<td class="num">(\d+)</td>', seg)
            sell_m = re.search(r'<td class="num" title="[^"]*">(\d\.\d{2})（n=(\d+)）</td>', seg)
            if count_m and sell_m:
                pairs.append((int(count_m.group(1)), int(sell_m.group(2))))
        self.assertTrue(pairs, "至少应有一个可售性单元格带 n")
        for count, n in pairs:
            self.assertGreaterEqual(n, 1, f"有数值时 n 不得为 0（count={count}）")
            self.assertLessEqual(n, count, f"n 不应超过条数（count={count}, n={n}）")
            self.assertGreaterEqual(n, max(1, count // 2), f"n 应与条数同量级（count={count}, n={n}）")

    def test_pick_competition_numeric(self):
        html = self.client.get("/pick").get_data(as_text=True)
        cells = re.findall(r'<td class="num" title="([^"]*competition_norm[^"]*)">(\d\.\d{2})（n=(\d+)）</td>', html)
        self.assertGreaterEqual(len(cells), 3, "至少 3 行应有 competition_norm 均值")
        values = [float(v) for _t, v, _n in cells]
        self.assertTrue(all(0.0 <= v <= 1.0 for v in values), values)
        self.assertFalse(all(v == 0 for v in values), "不接受整列 0")
        self.assertIn("1=竞争者最少", html)

    def test_source_and_copy_without_wo_show_guidance(self):
        """D3：无 wo 不再是 400，而是 200 引导页（可点可达）。"""
        for path in ("/source", "/copy"):
            resp = self.client.get(path)
            self.assertEqual(resp.status_code, 200, path)
            body = resp.get_data(as_text=True)
            self.assertIn("还没有选中商品", body)
            self.assertIn('href="/pick"', body)
            self.assertIn("从最近工作单继续", body)

    def test_guidance_page_lists_recent_orders_with_buttons(self):
        wid = self._self_made()
        body = self.client.get("/source").get_data(as_text=True)
        self.assertIn(f'/source?wo={wid}', body)
        self.assertIn(f'/copy?wo={wid}', body)
        self.assertIn("继续找货源", body)
        self.assertIn("继续写文案", body)
        body2 = self.client.get("/copy").get_data(as_text=True)
        self.assertIn("写文案", body2)

    def test_invalid_wo_404(self):
        self.assertEqual(self.client.get("/source?wo=wo:nope").status_code, 404)
        self.assertEqual(self.client.get("/copy?wo=wo:nope").status_code, 404)

    # ---------- 找货源 ----------
    def test_source_shows_summary_and_blocks_confirm(self):
        wid = self._self_made()
        body = self.client.get(f"/source?wo={wid}").get_data(as_text=True)
        self.assertIn("自制提示词包", body)
        self.assertIn("未采用任何货源前不能确定上架商品", body)
        self.assertIn("disabled", body)
        resp = self.client.post(f"/worksheet/{wid}/source/confirm",
                                data={"csrf": self._token(), "revision": "1"})
        self.assertEqual(resp.status_code, 303)
        self.assertIn("err=no_supply", resp.headers["Location"])

    def test_source_confirm_after_select(self):
        wid = self._self_made()
        conn = wf.connect()
        try:
            cand = sup.add(conn, wid, {"provider": "自制", "source_url": "self:x", "kind": "同款",
                                       "commercial": "yes", "redistribute": "yes", "resale": "yes"})
            sup.select_candidate(conn, wid, cand["id"], revision=self._rec(wid)["revision"])
        finally:
            conn.close()
        body = self.client.get(f"/source?wo={wid}").get_data(as_text=True)
        self.assertIn("已采用", body)
        resp = self.client.post(f"/worksheet/{wid}/source/confirm",
                                data={"csrf": self._token(), "revision": "1"})
        self.assertEqual(resp.status_code, 303)
        self.assertIn(f"/copy?wo={wid}", resp.headers["Location"])

    # ---------- 写介绍 ----------
    def test_copy_page_saves_version_and_blocks_export(self):
        wid = self._self_made()
        body = self.client.get(f"/copy?wo={wid}").get_data(as_text=True)
        self.assertIn("七项就绪", body)
        self.assertIn("导出（未就绪）", body)
        rev = self._rec(wid)["revision"]
        resp = self.client.post(f"/worksheet/{wid}/copy/save", data={
            "csrf": self._token(), "revision": str(rev), "name": "自制提示词包（改）",
            "selling_points": "卖点A\n卖点B", "price_minor": "1990", "copy_version": "copy-v1",
            "copy_status": "final", "faq_json": "[]"})
        self.assertEqual(resp.status_code, 303)
        conn = wf.connect()
        try:
            versions = rd.list_copy_versions(conn, wid)
        finally:
            conn.close()
        self.assertEqual([v["version_no"] for v in versions], [1])
        self.assertEqual(self.client.get(f"/worksheet/{wid}/export?format=md").status_code, 409)

    def test_copy_ready_shows_export_links(self):
        wid = self._self_made()
        conn = wf.connect()
        try:
            cand = sup.add(conn, wid, {"provider": "自制", "source_url": "self:x", "kind": "同款",
                                       "commercial": "yes", "redistribute": "yes", "resale": "yes"})
            sup.select_candidate(conn, wid, cand["id"], revision=self._rec(wid)["revision"])
        finally:
            conn.close()
        self.client.post(f"/worksheet/{wid}/sample/check",
                         data={"csrf": self._token(), "revision": str(self._rec(wid)["revision"]), "path": SAMPLE})
        self.client.post(f"/worksheet/{wid}/copy/save", data={
            "csrf": self._token(), "revision": str(self._rec(wid)["revision"]),
            "cost_minor": "300", "cost_known": "yes", "platform_evidence": "demo://b20/test",
            "copy_status": "final", "copy_version": "copy-v1", "selling_points": "A", "price_minor": "1990",
            "delivery_note": "站内", "aftersales_note": "未定", "faq_json": "[]"})
        self.assertTrue(rd.readiness(self._rec(wid))["overall_ready"])
        body = self.client.get(f"/copy?wo={wid}").get_data(as_text=True)
        self.assertIn("导出 Markdown", body)
        self.assertIn("记录本次导出", body)
        self.assertEqual(self.client.get(f"/worksheet/{wid}/export?format=json").status_code, 200)

    def test_copy_page_has_publish_guidance(self):
        wid = self._self_made()
        body = self.client.get(f"/copy?wo={wid}").get_data(as_text=True)
        self.assertIn("发布回填", body)
        self.assertIn("PUBLISH-CARD.md", body)
        self.assertIn("FEEDBACK-CARD.md", body)
        self.assertIn("系统不代发、不登录、不改平台设置", body)
        self.assertIn(f'/worksheet/{wid}#h-pub', body)

    def test_copy_page_has_platform_evidence_hint(self):
        wid = self._self_made()
        body = self.client.get(f"/copy?wo={wid}").get_data(as_text=True)
        self.assertIn('name="platform_evidence"', body)
        self.assertIn("未核对前请保持为空，导出会被阻止", body)
        self.assertIn("不代表平台已批准", body)
        self.assertIn("PLATFORM-CHECKLIST.md", body)

    def test_old_routes_still_work(self):
        root = self.client.get("/")
        self.assertEqual(root.status_code, 302)
        self.assertEqual(root.headers["Location"], "/pick")
        for path in ("/opportunities", "/content", "/worksheet", "/worksheet/new"):
            self.assertIn(self.client.get(path).status_code, (200,), path)


class NavTests(WizardTests):
    """B21：主侧栏严格 3 项（选品/找货源/写文案），工作单上下文在切换中保留。"""

    OLD_LABELS = ("总览", "机会线索", "教程与内容", "商品工作单", "货源与价格", "采集来源", "每日快照", "选品向导")

    def _nav_html(self, path: str) -> str:
        html = self.client.get(path).get_data(as_text=True)
        m = re.search(r'<nav aria-label="主导航">(.*?)</nav>', html, re.S)
        self.assertIsNotNone(m, f"{path} 缺少主导航")
        return m.group(1)

    def test_main_nav_exactly_three_items(self):
        nav = self._nav_html("/pick")
        labels = re.findall(r'class="nav-label[^"]*"[^>]*>([^<]+)<', nav)
        self.assertEqual(labels, ["选品", "找货源", "写文案"])
        for old in self.OLD_LABELS:
            self.assertNotIn(old, nav, f"主导航不应出现旧栏目：{old}")

    def test_root_redirects_to_pick(self):
        resp = self.client.get("/")
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.headers["Location"], "/pick")
        self.assertIn("选品", self.client.get("/pick").get_data(as_text=True))

    def test_nav_preserves_wo_across_steps(self):
        wid = self._self_made()
        for path in (f"/source?wo={wid}", f"/copy?wo={wid}"):
            nav = self._nav_html(path)
            for key in ("/pick", "/source", "/copy"):
                self.assertIn(f'href="{key}?wo={wid}"', nav, f"{path} 的 {key} 链接应带 wo")

    def test_nav_clickable_without_wo(self):
        """D3：无当前单时三项仍是可点链接（不再 aria-disabled）。"""
        nav = self._nav_html("/pick")
        self.assertIn('href="/source"', nav)
        self.assertIn('href="/copy"', nav)
        self.assertNotIn("aria-disabled", nav)

    def test_aria_current_and_mobile_toggle(self):
        nav = self._nav_html("/pick")
        self.assertIn('aria-current="page"', nav)
        html = self.client.get("/pick").get_data(as_text=True)
        self.assertIn('aria-controls="sidebar"', html)
        self.assertEqual(html.count('<nav aria-label="主导航">'), 1, "移动端复用同一侧栏，不应出现第二个主导航")

    def test_old_pages_keep_working_without_nav_entries(self):
        for path in ("/opportunities", "/content", "/worksheet", "/sources", "/collect", "/daily"):
            resp = self.client.get(path)
            self.assertEqual(resp.status_code, 200, path)
            nav = self._nav_html(path)
            for old in self.OLD_LABELS:
                self.assertNotIn(old, nav, f"{path} 主导航不应出现旧栏目：{old}")


class ContinueWorkorderTests(WizardTests):
    """B22：/pick 顶部“继续已有工作单”区块（只读列表 + 带 wo 跳转）。"""

    def test_lists_recent_two_orders_with_links(self):
        wid1 = self._self_made()
        self.client.post("/worksheet/new", data={
            "csrf": self._token(), "self_made": "1", "submit_key": "b22-2",
            "name": "第二条示例单", "use_case": "测试", "deliverable": "文本", "target_platform": "xianyu"})
        html = self.client.get("/pick").get_data(as_text=True)
        self.assertIn("继续已有工作单", html)
        self.assertIn(f'href="/source?wo={wid1}"', html)
        self.assertIn(f'href="/copy?wo={wid1}"', html)
        self.assertIn("第二条示例单", html)
        self.assertEqual(html.count("继续找货源"), 2)
        self.assertEqual(html.count("继续写文案"), 2)
        self.assertRegex(html, r'\d/7')

    def test_empty_state_when_no_orders(self):
        html = self.client.get("/pick").get_data(as_text=True)
        self.assertIn("还没有工作单，先在上面选一个商品", html)

    def test_nav_still_three_items_and_wo_kept_after_continue(self):
        wid = self._self_made()
        nav = re.search(r'<nav aria-label="主导航">(.*?)</nav>', self.client.get("/pick").get_data(as_text=True), re.S).group(1)
        self.assertEqual(re.findall(r'class="nav-label[^"]*"[^>]*>([^<]+)<', nav), ["选品", "找货源", "写文案"])
        for path in (f"/source?wo={wid}", f"/copy?wo={wid}"):
            self.assertEqual(self.client.get(path).status_code, 200, path)
            nav2 = re.search(r'<nav aria-label="主导航">(.*?)</nav>',
                             self.client.get(path).get_data(as_text=True), re.S).group(1)
            self.assertIn(f'?wo={wid}', nav2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
