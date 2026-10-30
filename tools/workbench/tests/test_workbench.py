"""工作台单测（隔离 fixture）。

关键口径：可售性**只读** scores.csv 的 `sellability_norm`（展示 100×n、理由取 `sellability_reason` 原文）；
分类仅按该列阈值（≥0.8 较强 / ≤0.2 低信号 / 其余不明确 / 缺失或非数值 未评估）。
价格：毛利/百分比不带 ¥；真实标价带 ¥；无法解析的原始价（如 `¥ 1`、`面议`）原样展示，不吞成 —。
"""

from __future__ import annotations

import csv
import hashlib
import pathlib
import sys
import tempfile
import unittest
import urllib.parse

WORKBENCH = pathlib.Path(__file__).resolve().parents[1]
ROOT = WORKBENCH.parents[1]
sys.path.insert(0, str(WORKBENCH))

import app as workbench_app  # noqa: E402

SCORE_COLS = ["rank", "item_id", "platform", "title", "url", "author", "total_score", "demand_raw", "demand_norm",
              "demand_weighted", "competition_norm", "competition_weighted", "margin_low", "margin_high", "margin_mid",
              "margin_weighted", "fulfillment_norm", "fulfillment_weighted", "compliance_norm", "compliance_weighted",
              "replicability_norm", "replicability_weighted", "sellability_raw", "sellability_norm",
              "sellability_weighted", "sellability_reason", "margin_assumption", "cost_input", "cost_note",
              "missing_metrics", "source", "raw_ref"]


def row(rank, item_id, platform, title, total, sell_norm, sell_reason, **kw):
    base = dict(rank=rank, item_id=item_id, platform=platform, title=title, url=f"https://x/{item_id}",
                author="@a", total_score=total, demand_raw=kw.get("demand_raw", 100),
                demand_norm=kw.get("demand_norm", 0.5), demand_weighted=0.15, competition_norm=0.4,
                competition_weighted=0.08, margin_low=kw.get("margin_low", 0.7),
                margin_high=kw.get("margin_high", 0.95), margin_mid=kw.get("margin_mid", 0.825),
                margin_weighted=0.165, fulfillment_norm=kw.get("fulfillment_norm", 0.5),
                fulfillment_weighted=0.05, compliance_norm=kw.get("compliance_norm", 0.5),
                compliance_weighted=0.05, replicability_norm=kw.get("replicability_norm", 0.5),
                replicability_weighted=0.05, sellability_raw="", sellability_norm=sell_norm,
                sellability_weighted=kw.get("sellability_weighted", "0.0"),
                sellability_reason=sell_reason, margin_assumption="假设", cost_input="missing", cost_note="",
                missing_metrics="", source="fixture", raw_ref="raw/x.jsonl")
    return base


SCORES = [
    # ①真实可售 0.05、其余指标很高 → 仍 5 分 / 低信号
    row(1, "x:low-sell", "x", "高指标但可售0.05", 0.95, "0.05", "真实可售极低：缺交付素材",
        demand_norm=0.99, compliance_norm=0.99, fulfillment_norm=0.99, replicability_norm=0.99),
    # ②真实可售 0.85、其余很低 → 仍 85 分 / 较强售卖
    row(2, "x:high-sell", "x", "低指标但可售0.85", 0.30, "0.85", "真实可售高：已有成品与授权",
        demand_norm=0.01, compliance_norm=0.01, fulfillment_norm=0.01, replicability_norm=0.01),
    # ③缺真实可售但其余齐全 → 未评估
    row(3, "bili:no-sell", "bilibili", "缺可售字段", 0.60, "", "", demand_norm=0.8, compliance_norm=0.9,
        fulfillment_norm=0.9, replicability_norm=0.9),
    # 中间值 → 不明确
    row(4, "bili:mid-sell", "bilibili", "中间可售", 0.45, "0.55", "部分可售：需补授权", margin_mid=""),
]
SOURCE_COLS = ["source_id", "name", "type", "repo_or_url", "license_spdx", "license_verdict", "cost", "effort",
               "delivery", "stability", "differentiation", "after_sales_risk", "evidence_url", "checked_at",
               "license_source", "license_reason", "license_key_sentence", "stars", "pushed_at"]
SOURCES = [
    dict(source_id="gh-01", name="ok/repo", type="模板", repo_or_url="https://github.com/ok/repo", license_spdx="MIT",
         license_verdict="可商用", cost="0", effort="低", delivery="数字", stability="0.9", differentiation="0.9",
         after_sales_risk="低", evidence_url="https://github.com/ok/repo", checked_at="2026-10-22T00:00:00Z",
         license_source="api_license", license_reason="permissive", license_key_sentence="MIT License", stars="10",
         pushed_at="2026-10-01T00:00:00Z"),
    dict(source_id="gh-02", name="need/repo", type="模板", repo_or_url="https://github.com/need/repo",
         license_spdx="NOASSERTION", license_verdict="需授权", cost="0", effort="低", delivery="数字",
         stability="0.9", differentiation="0.5", after_sales_risk="中", evidence_url="https://github.com/need/repo",
         checked_at="2026-10-22T00:00:00Z", license_source="license_file", license_reason="attribution",
         license_key_sentence="CC BY", stars="20", pushed_at="2026-10-01T00:00:00Z"),
    dict(source_id="gh-03", name="ban/repo", type="素材", repo_or_url="https://github.com/ban/repo",
         license_spdx="", license_verdict="禁止", cost="0", effort="低", delivery="数字", stability="0.8",
         differentiation="0.2", after_sales_risk="高", evidence_url="", checked_at="", license_source="",
         license_reason="no license", license_key_sentence="", stars="30", pushed_at=""),
    dict(source_id="gh-04", name="unknown/repo", type="素材", repo_or_url="https://github.com/unknown/repo",
         license_spdx="", license_verdict="不明", cost="0", effort="低", delivery="数字", stability="0.7",
         differentiation="0.3", after_sales_risk="中", evidence_url="", checked_at="", license_source="",
         license_reason="", license_key_sentence="", stars="40", pushed_at=""),
]
PRICES = [
    dict(item_id="105", title_snippet="模板A", listed_price="¥ 1", effective_price="1.88", wants="808",
         province="江苏", parse_status="ok"),
    dict(item_id="106", title_snippet="模板B", listed_price="面议", effective_price="", wants="0", province="",
         parse_status="ok"),
]


def write_csv(path: pathlib.Path, cols: list[str], rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=cols)
        writer.writeheader()
        for item in rows:
            writer.writerow({c: item.get(c, "") for c in cols})


class FixtureCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = pathlib.Path(cls.tmp.name)
        mp = cls.root / "docs" / "validation" / "money-project"
        write_csv(mp / "scoring" / "scores.csv", SCORE_COLS, SCORES)
        write_csv(mp / "sourcing" / "sources.csv", SOURCE_COLS, SOURCES)
        write_csv(mp / "sourcing" / "price_signals.csv",
                  ["item_id", "title_snippet", "listed_price", "effective_price", "wants", "province", "parse_status"],
                  PRICES)
        write_csv(mp / "sourcing" / "opportunity_sourcing_top10.csv",
                  ["rank", "opportunity_id", "platform", "title", "price_category", "price_scope",
                   "price_signal_count", "effective_low", "effective_high", "reference_max", "wants_sum",
                   "match_quality"],
                  [dict(rank="1", opportunity_id="x:high-sell", platform="x", title="低指标但可售0.85",
                        price_category="notion", price_scope="all_20_fallback", price_signal_count="20",
                        effective_low="1.0", effective_high="1.88", reference_max="699", wants_sum="808",
                        match_quality="同品类")])
        cls.app = workbench_app.create_app(cls.root)
        cls.app.testing = True
        cls.client = cls.app.test_client()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.tmp.cleanup()

    def get(self, path: str) -> str:
        # 逐条断言默认走 items 视图（聚合视图另有专门用例）
        if path.startswith("/opportunities") and "view=" not in path:
            path += ("&" if "?" in path else "?") + "view=items"
        resp = self.client.get(path)
        self.assertEqual(resp.status_code, 200, path)
        return resp.get_data(as_text=True)

    @staticmethod
    def shown(html_text: str) -> int:
        marker = 'role="status">筛后 <strong>'
        start = html_text.index(marker) + len(marker)
        return int(html_text[start:html_text.index("</strong>", start)])

    # ---------- ① 只读 sellability_norm ----------
    def test_sellability_reads_only_sellability_norm(self):
        body = self.get("/opportunities")
        # ① 0.05 + 其余全高 → 仍 5
        self.assertIn("低信号 5", body)
        self.assertIn("真实可售极低：缺交付素材", body)
        # ② 0.85 + 其余全低 → 仍 85
        self.assertIn("较强售卖 85", body)
        self.assertIn("真实可售高：已有成品与授权", body)
        # ③ 缺列但其余齐全 → 未评估
        self.assertIn("未评估", body)
        self.assertIn("缺少真实可售性字段", body)
        # 中间值
        self.assertIn("不明确 55", body)

    def test_sellability_filter_counts(self):
        expect = {"较强售卖": 1, "低信号": 1, "不明确": 1, "未评估": 1}
        for bucket, count in expect.items():
            body = self.get(f"/opportunities?sell={urllib.parse.quote(bucket)}")
            self.assertEqual(self.shown(body), count, bucket)

    def test_daily_uses_same_sellability_function(self):
        body = self.get("/daily")
        self.assertIn("可售性分布", body)
        for bucket in ("较强售卖 1", "低信号 1", "不明确 1", "未评估 1"):
            self.assertIn(bucket, body)

    def test_evidence_has_seventh_dimension(self):
        body = self.get("/opportunities")
        self.assertIn("可售性", body)
        self.assertIn("sellability_weighted" if False else "可售性 0.0", body)

    # ---------- ② 价格与百分比 ----------
    def test_raw_price_preserved_and_margin_has_no_currency(self):
        opp = self.get("/opportunities")
        # 毛利以百分比进入“选择理由”，不带货币符号；区间仍在
        self.assertTrue(any(f"毛利估算 {p}%" in opp for p in ("82", "83")), "毛利应以百分比呈现")
        self.assertIn("%–95%", opp)
        self.assertNotIn("¥82", opp)
        src = self.get("/sources")
        self.assertIn("¥1.00", src)      # "¥ 1" 安全解析
        self.assertIn("¥1.88", src)
        self.assertIn("面议", src)        # 无法解析 → 原样保留

    # ---------- ③ 排序与筛选保留 ----------
    def test_sort_link_preserves_filters(self):
        body = self.get("/opportunities?q=可售&platform=x&min_score=0.3&sell=较强售卖&sort=score&dir=desc")
        self.assertIn("sort=score&amp;dir=asc", body)
        self.assertIn("min_score=0.3", body)
        self.assertIn("sell=%E8%BE%83%E5%BC%BA%E5%94%AE%E5%8D%96", body)

    def test_sort_direction_flips_rows(self):
        desc = self.get("/opportunities?sort=score&dir=desc")
        asc = self.get("/opportunities?sort=score&dir=asc")
        self.assertIn("高指标但可售0.05", desc.split("<tbody>")[1].split("</tr>")[0])
        self.assertIn("低指标但可售0.85", asc.split("<tbody>")[1].split("</tr>")[0])

    def test_min_score_row_level(self):
        body = self.get("/opportunities?min_score=0.6")
        self.assertEqual(self.shown(body), 2)  # 0.95 与 0.60
        self.assertNotIn("中间可售", body)

    # ---------- ④ 许可三档 ----------
    def test_license_three_tiers(self):
        self.assertEqual(self.shown(self.get("/sources?license=可商用")), 1)
        self.assertEqual(self.shown(self.get("/sources?license=需授权")), 1)
        pending = self.get("/sources?license=待核验")
        self.assertEqual(self.shown(pending), 2)
        self.assertIn("ban/repo", pending)
        self.assertIn("unknown/repo", pending)

    # ---------- 真实 root 冒烟 + 守卫 ----------
    def test_real_root_pages_and_healthz(self):
        app = workbench_app.create_app()
        app.testing = True
        client = app.test_client()
        # B21：根入口改为落到“选品”，其余旧页仍保留
        root = client.get("/")
        self.assertEqual(root.status_code, 302)
        self.assertEqual(root.headers["Location"], "/pick")
        for path in ("/opportunities", "/sources", "/collect", "/daily"):
            self.assertEqual(client.get(path).status_code, 200, path)
        payload = client.get("/healthz").get_json()
        self.assertEqual(payload["status"], "ok")
        self.assertIn("counts", payload)

    def test_no_business_db_write(self):
        db = ROOT / "instance" / "app.db"
        before = hashlib.sha256(db.read_bytes()).hexdigest() if db.exists() else None
        self.get("/pick")          # B21：根入口 302 到 /pick，这里直接验证选品页只读
        after = hashlib.sha256(db.read_bytes()).hexdigest() if db.exists() else None
        self.assertEqual(before, after)


class AnalysisTests(unittest.TestCase):
    """产品分析生成器：确定性规则，四类边界 + 搜索覆盖。"""

    build = staticmethod(workbench_app.build_analysis)

    def test_unclassified_when_no_keyword_or_platform_hint(self):
        info = self.build({"title": "hello world", "platform": "x"})
        self.assertEqual(info["product_type"], "未分类")
        self.assertEqual(info["target_user"], "人群未明确")
        self.assertIn("待确认", info["deliverable"])
        self.assertTrue(info["risks"])

    def test_missing_fields_do_not_invent_numbers(self):
        info = self.build({"title": "resume template", "platform": "x"})
        self.assertEqual(info["product_type"], "求职简历资料")
        self.assertEqual(info["target_user"], "求职者")
        self.assertEqual(info["why"], [])  # 无任何指标 → 不生成理由
        self.assertTrue(any("可售性未评估" in r for r in info["risks"]))
        self.assertNotIn("%", " ".join(info["why"]))  # 不臆造百分比

    def test_low_sellability_becomes_top_risk(self):
        info = self.build({"title": "prompt pack", "platform": "x", "sellability_norm": "0.05",
                           "sellability_reason": "缺少可交付源文件"})
        self.assertEqual(info["product_type"], "提示词或数字包")
        self.assertTrue(info["risks"][0].startswith("可售性仅 5（低信号）"))
        self.assertIn("缺少可交付源文件", info["risks"][0])

    def test_competition_risk_only_below_threshold(self):
        dense = self.build({"title": "portfolio kit", "platform": "github", "competition_norm": "0.49",
                            "sellability_norm": "0.85"})
        self.assertEqual(dense["product_type"], "设计素材")
        self.assertTrue(any("竞争偏密" in r for r in dense["risks"]))
        loose = self.build({"title": "portfolio kit", "platform": "github", "competition_norm": "0.5",
                            "sellability_norm": "0.85"})
        self.assertFalse(any("竞争偏密" in r for r in loose["risks"]))

    def test_why_items_carry_real_numbers_and_deterministic(self):
        row = {"title": "notion dashboard", "platform": "x", "demand_norm": "0.9", "demand_raw": "5968",
               "competition_norm": "0.6", "margin_mid": "0.825", "margin_low": "0.7", "margin_high": "0.95",
               "sellability_norm": "0.85", "sellability_reason": "已有成品", "total_score": "0.800"}
        first = self.build(row, {"count": 20, "effective_min": 1.0, "effective_max": 1.88})
        second = self.build(row, {"count": 20, "effective_min": 1.0, "effective_max": 1.88})
        self.assertEqual(first, second)  # 确定性
        self.assertLessEqual(len(first["why"]), 3)
        self.assertTrue(any("90%" in w for w in first["why"]), first["why"])
        self.assertTrue(any(("82%" in w) or ("83%" in w) for w in first["why"]), first["why"])
        self.assertTrue(any("85" in w for w in first["why"]))
        self.assertIn("demand_norm", first["evidence_fields"])

    def test_search_blob_covers_product_summary(self):
        row = {"title": "how to import notion templates", "platform": "x"}
        info = self.build(row)
        self.assertEqual(info["product_type"], "教学内容")
        blob = workbench_app.search_blob(row, info)
        self.assertIn("教学内容", blob)
        self.assertIn("how to import notion templates", blob)

    def test_opportunities_page_shows_analysis_columns(self):
        app = workbench_app.create_app()
        app.testing = True
        client = app.test_client()
        items = client.get("/opportunities?view=items").get_data(as_text=True)
        for token in ("产品定位", "选择理由", "主要风险", "原始证据", "排序："):
            self.assertIn(token, items, token)
        self.assertIn("不调用模型、不臆造数字", items)
        grouped = client.get("/opportunities").get_data(as_text=True)
        for token in ("机会线索（商品型）", "组内明细", "代表证据", "可复用货源", "近似匹配", "教程与内容"):
            self.assertIn(token, grouped, token)


    def test_notion_is_carrier_not_type(self):
        info = self.build({"title": "notion template for freelancers", "platform": "x"})
        self.assertNotEqual(info["product_type"], "Notion 模板")
        self.assertIn("载体为 Notion 模板", info["positioning"])
        self.assertEqual(info["target_user"], "人群未明确")

    def test_intent_priority_beats_tool_word(self):
        info = self.build({"title": "resume notion template", "platform": "x"})
        self.assertEqual(info["product_type"], "求职简历资料")
        self.assertIn("载体为 Notion 模板", info["positioning"])

    def test_risks_differ_between_rows(self):
        low = self.build({"title": "prompt pack", "platform": "x", "sellability_norm": "0.05",
                          "sellability_reason": "缺源文件", "competition_norm": "0.4"})
        wide = self.build({"title": "prompt pack", "platform": "x", "sellability_norm": "0.85",
                           "competition_norm": "0.9", "margin_mid": "0.8", "margin_low": "0.5",
                           "margin_high": "0.95", "cost_input": "missing"})
        self.assertNotEqual(low["risks"], wide["risks"])
        self.assertLessEqual(len(low["risks"]), 2)
        self.assertLessEqual(len(wide["risks"]), 2)
        self.assertTrue(any("可售性仅 5" in r for r in low["risks"]))
        self.assertTrue(any("毛利低置信" in r for r in wide["risks"]))


    def test_unclassified_uses_commercial_and_demand_tiers(self):
        base = {"title": "notion template", "platform": "x"}
        paid = self.build({**base, "sellability_norm": "0.85", "demand_norm": "0.9"})
        free = self.build({**base, "sellability_norm": "0.05", "demand_norm": "0.1"})
        no_price = self.build({**base, "demand_norm": "0.5"})
        for info in (paid, free, no_price):
            self.assertEqual(info["product_type"], "未分类")
            self.assertIn("品类待确认", info["positioning"])
        self.assertIn("可售（可售性 85）的高需求线索", paid["positioning"])
        self.assertIn("免费引流（可售性 5）的低需求线索", free["positioning"])
        self.assertIn("无价格信号", no_price["positioning"])
        self.assertEqual(paid["commercial_form"], "可售")
        self.assertEqual(paid["demand_tier"], "高")
        self.assertEqual(free["commercial_form"], "免费引流")
        self.assertEqual(free["demand_tier"], "低")
        self.assertEqual(no_price["demand_tier"], "中")
        # 三条不得同一句
        self.assertEqual(len({paid["positioning"], free["positioning"], no_price["positioning"]}), 3)

    def test_pack_maps_to_prompt_or_digital_bundle(self):
        info = self.build({"title": "notion template pack bundle", "platform": "x"})
        self.assertEqual(info["product_type"], "提示词或数字包")
        self.assertEqual(info["target_user"], "内容创作者")

    def test_planner_maps_to_study_or_life_planner(self):
        info = self.build({"title": "notion planner habit tracker 2026", "platform": "x"})
        self.assertEqual(info["product_type"], "学习或生活规划模板")
        self.assertEqual(info["target_user"], "学生")


class GroupTests(unittest.TestCase):
    """聚合：同载体合并、不同品类不合并、未判品类按载体、空数据、组统计、展开条数=count。"""

    build_groups = staticmethod(workbench_app.build_groups)
    build = staticmethod(workbench_app.build_analysis)

    def _groups(self, rows, sources=None):
        analyses = {str(r["item_id"]): self.build(r) for r in rows}
        return self.build_groups(rows, analyses, sources or [])

    def test_same_carrier_merges_into_one_group(self):
        rows = [{"item_id": "a", "title": "notion template", "platform": "x", "total_score": "0.5"},
                {"item_id": "b", "title": "notion dashboard", "platform": "x", "total_score": "0.4"}]
        groups = self._groups(rows)
        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0]["group_key"], "carrier:notion")
        self.assertEqual(groups[0]["group_name"], "Notion 模板（品类待定）")
        self.assertEqual(groups[0]["count"], 2)
        self.assertEqual(sorted(groups[0]["members"]), ["a", "b"])

    def test_different_product_types_do_not_merge(self):
        rows = [{"item_id": "r", "title": "resume notion template", "platform": "x", "total_score": "0.5"},
                {"item_id": "p", "title": "planner habit tracker", "platform": "x", "total_score": "0.4"}]
        groups = self._groups(rows)
        keys = {g["group_key"] for g in groups}
        self.assertEqual(keys, {"type:求职简历资料", "type:学习或生活规划模板"})

    def test_unclassified_without_carrier_uses_unknown_group(self):
        rows = [{"item_id": "u", "title": "hello world", "platform": "x", "total_score": "0.3"}]
        groups = self._groups(rows)
        self.assertEqual(groups[0]["group_key"], "carrier:unknown")
        self.assertEqual(groups[0]["group_name"], "载体未明确（品类待定）")

    def test_empty_rows_produce_no_groups(self):
        self.assertEqual(self._groups([]), [])

    def test_group_stats_are_recomputable(self):
        rows = [
            {"item_id": "a", "title": "notion template", "platform": "x", "total_score": "0.8",
             "demand_raw": "100", "demand_norm": "0.5", "sellability_norm": "0.8",
             "margin_low": "0.6", "margin_high": "0.9", "sellability_reason": "可售"},
            {"item_id": "b", "title": "notion template 2", "platform": "x", "total_score": "0.6",
             "demand_raw": "50", "demand_norm": "0.9", "sellability_norm": "0.4",
             "margin_low": "0.5", "margin_high": "0.7", "sellability_reason": "部分"},
        ]
        group = self._groups(rows)[0]
        self.assertEqual(group["demand_sum"], 150)
        self.assertEqual(group["demand_max_norm"], 0.9)
        self.assertAlmostEqual(group["sellability_mean"], 0.6, places=4)
        self.assertEqual(group["margin_range"], [0.5, 0.9])
        self.assertEqual(len(group["representative_urls"]), 2)  # 只有 2 条成员
        self.assertEqual(group["max_total_score"], 0.8)

    def test_grouped_page_expands_to_member_count(self):
        import re
        app = workbench_app.create_app()
        app.testing = True
        client = app.test_client()
        body = client.get("/opportunities").get_data(as_text=True)
        self.assertIn("机会线索（商品型）", body)
        self.assertIn("展开组内明细", body)
        expand_counts = [int(n) for n in re.findall(r"展开组内明细（(\d+) 条）", body)]
        sample_counts = [int(n) for n in re.findall(r"样本 (\d+) 条（口径：", body)]
        self.assertTrue(expand_counts)
        self.assertEqual(sum(expand_counts), sum(sample_counts))
        self.assertEqual(sum(expand_counts), 25)   # 机会页只剩商品型 25 条
        items_body = client.get("/opportunities?view=items").get_data(as_text=True)
        self.assertIn("按条目", items_body)


class TaxonomyTests(unittest.TestCase):
    """载体 × 用途 分类法：五类命名、禁止笼统词、未归类兜底、守恒。"""

    classify = staticmethod(workbench_app.classify)
    build_categories = staticmethod(workbench_app.build_categories)
    summarize = staticmethod(workbench_app.summarize_conservation)

    def test_five_carrier_use_combinations(self):
        cases = [
            ({"title": "notion job application tracker"}, "Notion 求职投递追踪表"),
            ({"title": "ppt portfolio deck"}, "PPT 模板（作品集）"),
            ({"title": "resume doc template"}, "简历文档模板"),
            ({"title": "netflix 代充 会员"}, "资料代充/代下服务"),
            ({"title": "figma design pack"}, "设计素材包"),
        ]
        for row, expected in cases:
            self.assertEqual(self.classify(row)["category"], expected, row["title"])

    def test_vague_names_are_forbidden(self):
        rows = [{"item_id": "a", "title": "notion job tracker", "platform": "x", "total_score": "0.5"},
                {"item_id": "b", "title": "notion study notes", "platform": "x", "total_score": "0.4"},
                {"item_id": "c", "title": "hello world", "platform": "x", "total_score": "0.3"}]
        analyses = {r["item_id"]: workbench_app.build_analysis(r) for r in rows}
        names = {c["category"] for c in self.build_categories(rows, analyses)}
        for forbidden in ("学习或生活规划模板", "教学内容", "提示词或数字包"):
            self.assertNotIn(forbidden, names)

    def test_unclassified_fallback_with_reason(self):
        info = self.classify({"title": "totally unrelated text"})
        self.assertEqual(info["category"], "未归类（待人工）")
        self.assertTrue(info["unclassified_reason"])

    def test_notion_without_use_goes_to_manual(self):
        info = self.classify({"title": "notion template"})
        self.assertEqual(info["category"], "Notion 其它（待人工）")
        self.assertIn("用途词", info["unclassified_reason"])

    def test_conservation_sums_to_total(self):
        rows = [{"item_id": "a", "title": "notion job tracker", "platform": "x", "total_score": "0.5"},
                {"item_id": "b", "title": "notion template", "platform": "x", "total_score": "0.4"},
                {"item_id": "c", "title": "hello world", "platform": "x", "total_score": "0.3"}]
        analyses = {r["item_id"]: workbench_app.build_analysis(r) for r in rows}
        categories = self.build_categories(rows, analyses)
        summary = self.summarize(categories, len(rows))
        self.assertEqual(summary["total"], 3)
        self.assertEqual(summary["classified"] + summary["pending"], 3)
        self.assertTrue(summary["checked"])

    def test_five_part_analysis_present(self):
        rows = [{"item_id": "a", "title": "notion job tracker", "platform": "x", "total_score": "0.5",
                 "demand_raw": "100", "demand_norm": "0.8", "sellability_norm": "0.9",
                 "margin_low": "0.7", "margin_high": "0.95"}]
        analyses = {"a": workbench_app.build_analysis(rows[0])}
        category = self.build_categories(rows, analyses)[0]
        for key in ("what", "who", "demand_evidence", "competition", "pricing_risk"):
            self.assertTrue(category["analysis"][key], key)
        self.assertIn("需补采集", category["analysis"]["competition"])


    def test_notion29_subset_conserved_in_artifact(self):
        import json
        path = ROOT / "docs" / "validation" / "money-project" / "product-taxonomy" / "categories.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        notion29 = payload["notion29"]
        self.assertEqual(notion29["total"], 29)
        self.assertTrue(notion29["checked"])
        self.assertEqual(sum(notion29["breakdown"].values()), 29)
        self.assertGreaterEqual(len([k for k in notion29["breakdown"] if k.startswith("Notion ") and "其它" not in k]), 1)


    def test_full_text_beats_title_for_use_detection(self):
        row = {"title": "notion template", "platform": "x"}
        bare = self.classify(row)
        self.assertEqual(bare["category"], "Notion 其它（待人工）")
        enriched = self.classify(row, "I built this to track job applications and interviews", "items.raw_summary")
        self.assertEqual(enriched["category"], "Notion 求职投递追踪表")
        self.assertEqual(enriched["text_source"], "items.raw_summary")
        self.assertTrue(enriched["use_hits"])

    def test_full_text_index_covers_all_rows(self):
        import json
        path = ROOT / "docs" / "validation" / "money-project" / "product-taxonomy" / "categories.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        coverage = payload["coverage"]
        self.assertEqual(coverage["items_with_text"], coverage["items_total"])
        self.assertIn("targets", payload)
        self.assertIn("notion_other_platforms", payload["targets"])


    def test_three_content_categories_hit(self):
        cases = [
            ({"title": "Notion模板怎么导入？简单！"}, "Notion 使用教程/导入设置"),
            ({"title": "CARA MENCARI & REKOMENDASI TEMPLATE NOTION"}, "Notion 资源推荐清单"),
            ({"title": "Create a Notion template / Sell it for $14"}, "Notion 教学变现"),
        ]
        for row, expected in cases:
            info = self.classify(row)
            self.assertEqual(info["category"], expected, row["title"])
            self.assertEqual(info["kind"], "内容", row["title"])

    def test_content_not_counted_as_product(self):
        rows = [{"item_id": "a", "title": "notion job tracker", "platform": "x", "total_score": "0.5"},
                {"item_id": "b", "title": "notion 导入教程", "platform": "bilibili", "total_score": "0.4"}]
        analyses = {r["item_id"]: workbench_app.build_analysis(r) for r in rows}
        categories = self.build_categories(rows, analyses)
        summary = self.summarize(categories, len(rows))
        self.assertEqual(summary["product"], 1)
        self.assertEqual(summary["content"], 1)
        self.assertEqual(summary["product"] + summary["content"], 2)

    def test_other_missing_explains_each_pending_row(self):
        import json
        path = ROOT / "docs" / "validation" / "money-project" / "product-taxonomy" / "categories.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        other = [c for c in payload["categories"] if c["category"] == "Notion 其它（待人工）"]
        other_count = sum(c["count"] for c in other)
        missing = payload["other_missing"]
        self.assertEqual(len(missing), other_count)
        for item in missing:
            self.assertTrue(item["missing"].strip())
            self.assertTrue(item["title_snippet"])


    def test_strong_design_words_beat_generic_best_list(self):
        info = self.classify({"title": "best notion portfolio templates list"})
        self.assertEqual(info["category"], "Notion 设计作品集模板")
        self.assertEqual(info["kind"], "商品")
        self.assertIn("Notion 资源推荐清单", info["secondary_tags"])

    def test_pure_list_goes_to_recommendation(self):
        info = self.classify({"title": "notion template 合集 list 盘点"})
        self.assertEqual(info["category"], "Notion 资源推荐清单")
        self.assertEqual(info["kind"], "内容")

    def test_secondary_tags_recorded_on_group(self):
        rows = [{"item_id": "d1", "title": "best notion portfolio templates", "platform": "x", "total_score": "0.6"},
                {"item_id": "d2", "title": "notion design ui kit moodboard", "platform": "x", "total_score": "0.5"}]
        analyses = {r["item_id"]: workbench_app.build_analysis(r) for r in rows}
        categories = self.build_categories(rows, analyses)
        design = next(c for c in categories if c["category"] == "Notion 设计作品集模板")
        self.assertEqual(design["count"], 2)
        self.assertIn("Notion 资源推荐清单", design["hit_words"]["d1"]["secondary_tags"])
        self.assertTrue(design["secondary_top"])


class GroupedViewTests(unittest.TestCase):
    """可售性单位、整行可展开、内容型指引、类型快捷筛选、质量线与漏斗。"""

    @classmethod
    def setUpClass(cls) -> None:
        cls.app = workbench_app.create_app()
        cls.app.testing = True
        cls.client = cls.app.test_client()
        cls.body = cls.client.get("/opportunities").get_data(as_text=True)

    # ---------- ① 单位 ----------
    def test_sellability_header_has_unit_and_tooltip(self):
        self.assertIn("可售性均值（0–100）", self.body)
        self.assertIn("0 = 无售卖信号", self.body)

    # ---------- ② 整行可展开（button + aria-expanded） ----------
    def test_expand_is_button_with_aria_controls(self):
        import re
        self.assertIn('class="row-toggle"', self.body)
        self.assertIn('aria-expanded="false"', self.body)
        pairs = re.findall(r'aria-controls="(g\d+)"', self.body)
        self.assertTrue(pairs)
        for gid in pairs:
            self.assertIn(f'id="{gid}"', self.body)

    # ---------- ③ 内容型指引（已移出到 /content 页） ----------
    def test_content_groups_have_badge_and_guidance(self):
        body = self.client.get("/content").get_data(as_text=True)
        self.assertIn("内容·非商品", body)
        self.assertIn("参考价值：可作选题/导购参考，非自营商品", body)
        self.assertIn("通用判断，非数据结论", body)
        self.assertNotIn("毛利区间", body)
        self.assertNotIn("可售性均值", body)

    # ---------- ④ 类型区分（内容型已独立成页） ----------
    def test_kind_quick_filter_counts(self):
        self.assertIn("教程与内容", self.body)          # 机会页给出跳转
        self.assertIn("/content", self.body)
        self.assertNotIn("只看内容型", self.body)        # 内容型不再混在机会页筛选里

    # ---------- 质量线与漏斗 ----------
    def test_quality_threshold_boundaries(self):
        from views_grouped import meets_quality
        refs = set()
        self.assertTrue(meets_quality({"demand_norm": "0.70"}, refs)[0])      # 边界含
        self.assertFalse(meets_quality({"demand_norm": "0.699"}, refs)[0])    # 差一点
        self.assertTrue(meets_quality({"sellability_norm": "0.80"}, refs)[0])
        self.assertFalse(meets_quality({"sellability_norm": "0.79"}, refs)[0])
        self.assertTrue(meets_quality({"item_id": "x:1"}, {"x:1"})[0])        # 有参考价

    def test_funnel_counts_conserved(self):
        import re
        total = int(re.search(r"采集 <strong>(\d+)</strong>", self.body).group(1))
        products = int(re.search(r"商品 <strong>(\d+)</strong>", self.body).group(1))
        contents = int(re.search(r"教程与内容 <strong>(\d+)</strong>", self.body).group(1))
        pending = int(re.search(r"已剔除 <strong>(\d+)</strong>", self.body).group(1))
        self.assertEqual(total, 60)
        self.assertEqual(products + contents + pending, total)
        self.assertIn(f"已剔除·未归类（{pending} 条", self.body)

    def test_default_scope_keeps_all_classified(self):
        import re
        samples = [int(n) for n in re.findall(r"样本 (\d+) 条（口径：已归类全部）", self.body)]
        kept = [int(n) for n in re.findall(r"样本 (\d+) 条（口径：仅达线）", self.body)]
        self.assertEqual(sum(samples), 25)    # 机会页只剩商品型 25
        self.assertEqual(sum(kept), 0)
        self.assertIn("只看达线（10）", self.body)

    def test_quality_toggle_uses_only_passing_set(self):
        import re
        body = self.client.get("/opportunities?quality=1").get_data(as_text=True)
        kept = [int(n) for n in re.findall(r"样本 (\d+) 条（口径：仅达线）", body)]
        self.assertEqual(sum(kept), 10)          # 商品型达线 10
        self.assertIn("当前口径：仅达线", body)
        total = int(re.search(r"采集 <strong>(\d+)</strong>", body).group(1))
        removed = int(re.search(r"已剔除 <strong>(\d+)</strong>", body).group(1))
        self.assertEqual((total, removed), (60, 22))

    def test_weak_not_double_counted_as_removed(self):
        import re
        weak = int(re.search(r"弱信号 (\d+)）", self.body).group(1))
        removed = int(re.search(r"已剔除 <strong>(\d+)</strong>", self.body).group(1))
        self.assertEqual(removed, 22)            # 已剔除只含未归类
        self.assertEqual(weak, 15)               # 商品型弱信号（内容型弱信号在另页）
        self.assertIn(f"弱信号（{weak} 条商品型，未计入“已剔除”", self.body)

    def test_unclassified_not_in_group_stats(self):
        from views_grouped import split_rows
        with self.app.app_context():
            data = workbench_app.get_data()
        split = split_rows(data["scores"], data)
        names = {r["tax"]["category"] for r in split["kept"]}
        self.assertNotIn("Notion 其它（待人工）", names)
        self.assertNotIn("未归类（待人工）", names)
        self.assertGreater(len(split["pending"]), 0)
        self.assertGreaterEqual(len(split["weak"]), 0)


class ContentPageTests(unittest.TestCase):
    """内容型移出机会页、独立 /content 页、漏斗守恒与字段缺席。"""

    @classmethod
    def setUpClass(cls) -> None:
        cls.app = workbench_app.create_app()
        cls.app.testing = True
        cls.client = cls.app.test_client()
        cls.opp = cls.client.get("/opportunities").get_data(as_text=True)
        cls.content = cls.client.get("/content").get_data(as_text=True)

    def test_opportunities_has_no_content_groups(self):
        # 内容型已移出机会页：不出现内容分组徽章、也不把内容类型作为组名
        self.assertNotIn("内容·非商品", self.opp)
        for name in ("Notion 资源推荐清单", "Notion 使用教程/导入设置", "Notion 教学变现"):
            self.assertNotIn(f'<span class="group-name">{name}</span>', self.opp, name)

    def test_content_page_has_three_groups_totaling_13(self):
        import re
        for name in ("Notion 资源推荐清单", "Notion 使用教程/导入设置", "Notion 教学变现"):
            self.assertIn(name, self.content, name)
        counts = [int(n) for n in re.findall(r'<td class="num">(\d+)</td>', self.content)]
        self.assertEqual(sum(counts), 13)

    def test_content_page_hides_source_and_margin_fields(self):
        self.assertNotIn("可复用货源", self.content)
        self.assertNotIn("毛利区间", self.content)
        self.assertNotIn("可售性均值", self.content)
        self.assertIn("参考价值：可作选题/导购参考，非自营商品", self.content)
        self.assertIn("通用判断，非数据结论", self.content)

    def test_funnel_conservation_25_13_22(self):
        import re
        total = int(re.search(r"采集 <strong>(\d+)</strong>", self.opp).group(1))
        products = int(re.search(r"商品 <strong>(\d+)</strong>", self.opp).group(1))
        contents = int(re.search(r"教程与内容 <strong>(\d+)</strong>", self.opp).group(1))
        pending = int(re.search(r"已剔除 <strong>(\d+)</strong>", self.opp).group(1))
        self.assertEqual((total, products, contents, pending), (60, 25, 13, 22))
        self.assertEqual(products + contents + pending, total)

    def test_default_scope_is_all_classified_products(self):
        import re
        samples = [int(n) for n in re.findall(r"样本 (\d+) 条（口径：已归类全部）", self.opp)]
        self.assertEqual(sum(samples), 25)
        self.assertIn("剩余 22 条未归类（已剔除，可展开复查）", self.opp)

    def test_quality_toggle_on_products_only(self):
        body = self.client.get("/opportunities?quality=1").get_data(as_text=True)
        import re
        kept = [int(n) for n in re.findall(r"样本 (\d+) 条（口径：仅达线）", body)]
        self.assertGreater(len(kept), 0)
        self.assertEqual(sum(kept), 10)      # 商品型达线 10（内容型 6 在另页）
        self.assertIn("当前口径：仅达线", body)

    def test_text_consistency_between_header_and_buttons(self):
        self.assertIn("默认统计<strong>已归类全部</strong>条目（只剔除未归类）", self.opp)
        self.assertIn("达线 = 需求分位≥70% 或 可售性≥80% 或 有参考价", self.opp)
        self.assertIn("已归类全部 = 25 条（含弱信号）", self.opp)
        self.assertIn("只看达线 = 10 条", self.opp)


if __name__ == "__main__":
    unittest.main(verbosity=2)
