"""Zhihu adapter: URL rules, parsers, budget integration, login states, export.

No browser, no network: transports are fakes, the login flow runs against a
fake browser, and every state dir is temporary.
"""

from __future__ import annotations

import asyncio
import inspect
import json
import pathlib
import re
import sys
import tempfile
import unittest

REPO = pathlib.Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from tools.selection.access import browser as browser_mod  # noqa: E402
from tools.selection.access import budget as budget_mod  # noqa: E402
from tools.selection.access import records as rec  # noqa: E402
from tools.selection.access import transport as transport_mod  # noqa: E402
from tools.selection.access import zhihu  # noqa: E402

COLLECTED = "2026-10-27T04:00:00Z"

SEARCH_JSON = {
    "data": [
        {"type": "search_result", "object": {
            "type": "answer", "id": 111, "content": "<p>求一个能直接用的周计划模板</p>",
            "created_time": 1700000000, "voteup_count": "1.2万", "comment_count": 34,
            "question": {"id": 900, "name": "有哪些好用的学习计划模板？"}}},
        {"type": "search_result", "object": {
            "type": "article", "id": 222, "title": "我的备考节奏",
            "content": "每天两小时", "created": 1700000100,
            "voteup_count": 12, "comment_count": 3}},
        {"type": "search_result", "object": {"type": "unknown_kind", "id": 333}},
    ],
    "paging": {"is_end": True},
}

COMMENTS_JSON = {
    "data": [
        {"id": "c1", "content": "<p>同求，蹲一个</p>", "created_time": 1700000200,
         "vote_count": 5, "child_comment_count": 2},
        {"id": "c2", "content": "我整理过一份", "created_time": 1700000300,
         "vote_count": 0, "child_comment_count": 0},
    ],
    "paging": {"is_end": False, "next": "off-2"},
}

COMMENTS_JSON_4 = {
    "data": [
        {"id": f"c{n}", "content": f"评论{n}", "created_time": 1700000200 + n,
         "vote_count": n, "child_comment_count": 0} for n in range(1, 5)
    ],
    "paging": {"is_end": True},
}

DETAIL_HTML = """<html><head>
<meta property="og:title" content="有哪些好用的学习计划模板？ - 知乎">
<meta property="og:description" content="求一个能直接用的周计划模板，可打印">
<meta property="article:published_time" content="2026-10-20T08:00:00Z">
<title>fallback</title></head>
<body><div>1,234 赞同 · 56 条评论</div></body></html>"""

LOGIN_HTML = """<html><head><meta property="og:title" content="知乎 - 有问题，就会有答案">
<title>知乎</title></head><body><div>请登录后查看</div><a href="/signin">登录</a></body></html>"""
# wall pages carry no og:description; that absence is the primary wall signal
RISK_HTML = """<html><head><title>知乎</title></head>
<body><div>当前环境异常，请完成安全验证</div></body></html>"""
RISK_WITH_META_HTML = """<html><head><title>知乎</title>
<meta property="og:title" content="安全验证"></head>
<body><div>请完成安全验证</div></body></html>"""

SEARCH_HTML = """<html><body>
<a href="/question/900/answer/111">有哪些好用的学习计划模板？</a>
<a href="/question/900/answer/111">重复链接</a>
<a href="/p/222">我的备考节奏</a>
<a href="https://www.zhihu.com/question/901">纯问题</a>
<a href="/people/someone">人物页</a>
</body></html>"""


class FakeTransport:
    def __init__(self, response: dict) -> None:
        self.response = response
        self.urls: list[str] = []

    def fetch(self, url: str) -> dict:
        self.urls.append(url)
        return {"final_url": url, "redirect": None, **self.response, "url": url}


class FakeClock:
    def __init__(self, start: float = 5_000_000.0) -> None:
        self.now = start

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


class FakeBrowser:
    """Stands in for a nodriver browser during login polling.

    Each call to `wait_for_login` reads three snippets per poll (href, the
    signed-in probe, the visible text). The fake serves the step that matches
    the snippet, so a test can script "still on /signin, not signed in" and let
    the injected clock run the timeout out.
    """

    def __init__(self, steps: list[dict]) -> None:
        self.steps = steps
        self.index = 0
        self.evaluated: list[str] = []

    async def evaluate(self, script: str):
        self.evaluated.append(script)
        step = self.steps[min(self.index, len(self.steps) - 1)]
        if "location.href" in script:
            return step.get("url", "")
        if "querySelector" in script or "AppHeader" in script:
            return step.get("signed_in", False)
        return step.get("text", "")


class ZhihuTestBase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = pathlib.Path(self._tmp.name)
        self.clock = FakeClock()

    def tearDown(self):
        self._tmp.cleanup()

    def budget(self, **kwargs):
        kwargs.setdefault("clock", self.clock)
        return budget_mod.open_budget(self.dir, **kwargs)


class UrlRuleTests(unittest.TestCase):
    def test_only_zhihu_hosts_are_allowed(self):
        self.assertTrue(zhihu.allowed_url("https://www.zhihu.com/question/1"))
        self.assertTrue(zhihu.allowed_url("https://zhuanlan.zhihu.com/p/1"))
        self.assertFalse(zhihu.allowed_url("https://zhihu.com.evil.test/q/1"))
        self.assertFalse(zhihu.allowed_url("https://example.com/?next=zhihu.com"))
        self.assertFalse(zhihu.allowed_url("file:///etc/passwd"))
        with self.assertRaises(ValueError):
            zhihu.require_url("https://evil.test/question/1")

    def test_sanitize_url_drops_tokens_but_keeps_search_term(self):
        dirty = ("https://www.zhihu.com/question/1/answer/2"
                 "?utm_source=x&token=SECRET#frag")
        self.assertEqual(rec.sanitize_url(dirty), "https://www.zhihu.com/question/1/answer/2")
        search = "https://www.zhihu.com/search?type=content&q=周计划&cookie=SECRET"
        self.assertEqual(rec.sanitize_url(search),
                         "https://www.zhihu.com/search?q=%E5%91%A8%E8%AE%A1%E5%88%92")

    def test_url_identity(self):
        answer = zhihu.url_identity("https://www.zhihu.com/question/900/answer/111")
        self.assertEqual((answer["type"], answer["native_id"], answer["parent_id"]),
                         ("answer", "111", "900"))
        article = zhihu.url_identity("https://zhuanlan.zhihu.com/p/222")
        self.assertEqual((article["type"], article["native_id"]), ("article", "222"))
        self.assertIsNone(zhihu.url_identity("https://www.zhihu.com/people/x")["native_id"])


class ParserTests(unittest.TestCase):
    def test_search_json_keeps_identity_parent_and_counts(self):
        parsed = zhihu.parse_search(SEARCH_JSON, collected_at=COLLECTED, limit=5)
        self.assertEqual(parsed["structure"], "json:search_v3")
        self.assertEqual(parsed["unknown_objects"], 1)
        self.assertEqual(parsed["stop"], "unknown_objects")  # usable, not clean
        answer, article = parsed["records"]
        self.assertEqual(answer["native_id"], "111")
        self.assertEqual(answer["type"], "answer")
        self.assertEqual(answer["parent_id"], "900")
        self.assertEqual(answer["title"], "有哪些好用的学习计划模板？")
        self.assertEqual(answer["text"], "求一个能直接用的周计划模板")
        self.assertEqual(answer["published_at"], "2023-11-14T22:13:20Z")
        self.assertEqual(answer["voteup"], 12000)
        self.assertEqual(answer["comments"], 34)
        self.assertIsNone(answer["likes"])
        self.assertEqual(answer["field_evidence"]["parent_id"], "json:object.question.id")
        self.assertEqual(article["type"], "article")
        self.assertTrue(article["supported"])

    def test_search_html_fallback_dedupes_and_skips_unknown(self):
        parsed = zhihu.parse_search_html(SEARCH_HTML, collected_at=COLLECTED, limit=5)
        ids = [r["native_id"] for r in parsed["records"]]
        self.assertEqual(ids, ["111", "222", "901"])
        first = parsed["records"][0]
        self.assertEqual(first["field_evidence"]["title"], "html:a[text]")
        self.assertIsNone(first["text"])
        self.assertIn("text", first["missing"])

    def test_search_unsupported_shape_is_not_an_empty_success(self):
        self.assertEqual(zhihu.parse_search({"nope": 1}, collected_at=COLLECTED)["stop"],
                         "unsupported")
        self.assertEqual(zhihu.parse_search([], collected_at=COLLECTED)["stop"],
                         "unsupported")
        self.assertEqual(zhihu.parse_search({"data": []}, collected_at=COLLECTED)["stop"],
                         "empty")

    def test_detail_meta_and_heuristics(self):
        parsed = zhihu.parse_detail(DETAIL_HTML, "https://www.zhihu.com/question/900/answer/111",
                                    collected_at=COLLECTED)
        record = parsed["record"]
        self.assertIsNone(parsed["stop"])
        self.assertEqual(record["native_id"], "111")
        self.assertEqual(record["parent_id"], "900")
        self.assertEqual(record["title"], "有哪些好用的学习计划模板？")
        self.assertEqual(record["published_at"], "2026-10-20T08:00:00Z")
        self.assertEqual(record["voteup"], 1234)
        self.assertEqual(record["comments"], 56)
        self.assertIn("heuristic", record["field_evidence"]["voteup"])

    def test_detail_body_mentioning_captcha_with_description_does_not_lock(self):
        html = """<html><head><meta property="og:title" content="知乎老是弹验证码怎么办 - 知乎">
        <meta property="og:description" content="分享几个减少验证码的做法"></head>
        <body><div>正文：验证码、安全验证、访问异常都遇到过</div></body></html>"""
        parsed = zhihu.parse_detail(html, "https://www.zhihu.com/question/1/answer/2",
                                    collected_at=COLLECTED)
        self.assertIsNone(parsed["stop"])
        self.assertIsNotNone(parsed["record"])

    def test_detail_title_containing_captcha_but_with_content_is_content(self):
        # a real question *about* captchas must not be read as a captcha page
        html = """<html><head><title>知乎老是弹验证码怎么办 - 知乎</title>
        <meta property="og:description" content="正常回答内容"></head>
        <body><div>正文</div></body></html>"""
        parsed = zhihu.parse_detail(html, "https://www.zhihu.com/question/1/answer/2",
                                    collected_at=COLLECTED)
        self.assertIsNone(parsed["stop"])

    def test_detail_wall_without_description_still_locks(self):
        html = """<html><head><title>知乎</title></head>
        <body><div>当前环境异常，请完成安全验证</div></body></html>"""
        parsed = zhihu.parse_detail(html, "https://www.zhihu.com/question/1/answer/2",
                                    collected_at=COLLECTED)
        self.assertEqual(parsed["stop"], "text:安全验证")

    def test_detail_wall_identified_by_meta_title_alone(self):
        parsed = zhihu.parse_detail(RISK_WITH_META_HTML,
                                    "https://www.zhihu.com/question/1/answer/2",
                                    collected_at=COLLECTED)
        self.assertEqual(parsed["stop"], "text:安全验证")

    def test_detail_login_wall_and_risk(self):
        wall = zhihu.parse_detail(LOGIN_HTML, "https://www.zhihu.com/question/1/answer/2",
                                  collected_at=COLLECTED)
        self.assertEqual(wall["stop"], "text:请登录后查看")
        self.assertIsNone(wall["record"])
        risk = zhihu.parse_detail(RISK_HTML, "https://www.zhihu.com/question/1/answer/2",
                                  collected_at=COLLECTED)
        self.assertEqual(risk["stop"], "text:安全验证")

    def test_detail_plain_login_link_is_not_a_wall(self):
        html = """<html><head><meta property="og:title" content="问题 - 知乎">
        <meta property="og:description" content="正常回答摘要"></head>
        <body><a href="/signin">登录</a></body></html>"""
        parsed = zhihu.parse_detail(html, "https://www.zhihu.com/question/1/answer/2",
                                    collected_at=COLLECTED)
        self.assertIsNone(parsed["stop"])

    def test_comments_keep_parent_chain(self):
        parsed = zhihu.parse_comments(COMMENTS_JSON, content_id="111",
                                      collected_at=COLLECTED, limit=5)
        self.assertEqual(len(parsed["records"]), 2)
        comment = parsed["records"][0]
        self.assertEqual(comment["type"], "comment")
        self.assertEqual(comment["parent_id"], "111")
        self.assertEqual(comment["text"], "同求，蹲一个")
        self.assertEqual(comment["likes"], 5)
        self.assertEqual(comment["comments"], 2)
        self.assertFalse(parsed["is_end"])
        self.assertEqual(parsed["next_offset"], "off-2")

        child = zhihu.parse_comments(COMMENTS_JSON, content_id="111",
                                     collected_at=COLLECTED, parent_id="c1")
        self.assertEqual(child["records"][0]["parent_id"], "c1")
        self.assertEqual(child["records"][0]["field_evidence"]["parent_id"], "input:parent_id")

    def test_comments_unsupported(self):
        self.assertEqual(zhihu.parse_comments("not json", content_id="1",
                                              collected_at=COLLECTED)["stop"], "unsupported")
        self.assertEqual(zhihu.parse_comments({"data": []}, content_id="1",
                                              collected_at=COLLECTED)["stop"], "empty")

    def test_record_without_evidence_is_unsupported(self):
        record = rec.make_record(
            values={"native_id": "1", "type": "answer", "title": None, "text": None},
            evidence={}, collected_at=COLLECTED, source="test")
        self.assertFalse(record["supported"])
        self.assertIn("title", record["missing"])


class CommandTests(ZhihuTestBase):
    def test_search_charges_budget_then_parses(self):
        budget = self.budget()
        transport = FakeTransport({"status": 200, "text": "", "json": SEARCH_JSON})
        payload = zhihu.run_search("周计划", batch=budget, transport=transport,
                                   collected_at=COLLECTED, limit=5)
        budget.close()
        # one unusable object in the fixture: records kept, exit is partial
        self.assertEqual(payload["exit"], zhihu.EXIT_PARTIAL)
        self.assertEqual(payload["count"], 2)
        self.assertEqual(payload["batch"]["calls"], 1)
        self.assertEqual(payload["batch"]["records"], 2)
        self.assertEqual(transport.urls, [zhihu.search_url("周计划")])

    def test_clean_search_exits_zero(self):
        clean = {"data": [SEARCH_JSON["data"][0]], "paging": {"is_end": True}}
        budget = self.budget()
        payload = zhihu.run_search("周计划", batch=budget,
                                   transport=FakeTransport({"status": 200, "text": "",
                                                            "json": clean}),
                                   collected_at=COLLECTED)
        budget.close()
        self.assertEqual(payload["exit"], zhihu.EXIT_OK)
        self.assertEqual(payload["count"], 1)
        self.assertIsNone(payload["stop"])

    def test_api_error_field_locks_batch(self):
        budget = self.budget()
        payload = zhihu.run_search("x", batch=budget,
                                   transport=FakeTransport({"status": 200, "text": "",
                                                            "json": {"error": {"code": 1}}}),
                                   collected_at=COLLECTED)
        budget.close()
        self.assertEqual(payload["exit"], zhihu.EXIT_RISK)
        self.assertEqual(payload["stop"], "api_error")
        self.assertTrue(payload["batch"]["locked"])

    def test_content_mentioning_captcha_in_json_does_not_lock(self):
        payload = {
            "data": [{"object": {
                "type": "answer", "id": 7,
                "content": "<p>知乎老是弹验证码怎么办？</p>",
                "created_time": 1700000000, "voteup_count": 1, "comment_count": 0,
                "question": {"id": 8, "name": "验证码问题"}}}],
            "paging": {"is_end": True},
        }
        budget = self.budget()
        result = zhihu.run_search("x", batch=budget,
                                  transport=FakeTransport({"status": 200, "text": "",
                                                           "json": payload}),
                                  collected_at=COLLECTED)
        budget.close()
        self.assertEqual(result["exit"], zhihu.EXIT_OK)
        self.assertFalse(result["batch"]["locked"])

    def test_offline_refused_transport_is_not_success(self):
        budget = self.budget()
        payload = zhihu.run_search("周计划", batch=budget,
                                   transport=transport_mod.RefusedTransport(),
                                   collected_at=COLLECTED)
        budget.close()
        self.assertEqual(payload["exit"], zhihu.EXIT_TRANSPORT)
        self.assertEqual(payload["batch"]["calls"], 1)  # failed call still charged
        self.assertEqual(payload["count"], 0)

    def test_risk_locks_budget_and_next_run_refuses(self):
        budget = self.budget()
        payload = zhihu.run_detail("https://www.zhihu.com/question/1/answer/2", batch=budget,
                                   transport=FakeTransport({"status": 200, "text": RISK_HTML}),
                                   collected_at=COLLECTED)
        self.assertEqual(payload["exit"], zhihu.EXIT_RISK)
        self.assertEqual(payload["batch"]["lock_source"], "detail")
        budget.close()

        with self.assertRaises(budget_mod.BudgetError) as caught:
            self.budget()  # restart: same locked budget
        self.assertEqual(caught.exception.code, "batch_locked")

    def test_http_403_locks_the_batch(self):
        budget = self.budget()
        payload = zhihu.run_comments("https://www.zhihu.com/question/900/answer/111",
                                     batch=budget,
                                     transport=FakeTransport({"status": 403, "text": ""}),
                                     collected_at=COLLECTED)
        budget.close()
        self.assertEqual(payload["exit"], zhihu.EXIT_RISK)
        self.assertEqual(payload["stop"], "http_403")
        self.assertTrue(payload["batch"]["locked"])
        with self.assertRaises(budget_mod.BudgetError):
            self.budget()

    def test_transport_error_does_not_lock(self):
        budget = self.budget()
        payload = zhihu.run_search("x", batch=budget,
                                   transport=FakeTransport({"status": None, "text": "",
                                                            "error": "transport:URLError"}),
                                   collected_at=COLLECTED)
        self.clock.advance(budget_mod.MIN_INTERVAL)
        timeout = zhihu.run_detail("https://www.zhihu.com/question/1/answer/2", batch=budget,
                                   transport=FakeTransport({"status": None, "text": "",
                                                            "error": "transport:TimeoutError"}),
                                   collected_at=COLLECTED)
        budget.close()
        self.assertEqual(payload["exit"], zhihu.EXIT_TRANSPORT)
        self.assertFalse(payload["batch"]["locked"])
        self.assertEqual(payload["batch"]["calls"], 1)
        self.assertEqual(timeout["exit"], zhihu.EXIT_TRANSPORT)
        self.assertEqual(timeout["stop"], "transport:TimeoutError")
        self.assertFalse(timeout["batch"]["locked"])
        self.assertEqual(timeout["batch"]["calls"], 2)

    def test_offsite_redirect_locks_the_batch(self):
        budget = self.budget()
        payload = zhihu.run_detail("https://www.zhihu.com/question/1/answer/2", batch=budget,
                                   transport=FakeTransport(
                                       {"status": None, "text": "", "error":
                                        "offsite_redirect:evil.test",
                                        "final_url": "https://evil.test/x"}),
                                   collected_at=COLLECTED)
        budget.close()
        self.assertEqual(payload["exit"], zhihu.EXIT_RISK)
        self.assertEqual(payload["stop"], "offsite_redirect:evil.test")
        self.assertTrue(payload["batch"]["locked"])

    def test_charge_write_failure_sends_no_request(self):
        budget = self.budget()
        budget._conn.execute("PRAGMA query_only=ON")  # break the ledger write path
        transport = FakeTransport({"status": 200, "json": SEARCH_JSON})
        payload = zhihu.run_search("x", batch=budget, transport=transport,
                                   collected_at=COLLECTED)
        budget._conn.execute("PRAGMA query_only=OFF")
        calls = budget.snapshot()["calls"]
        budget.close()
        self.assertEqual(payload["exit"], zhihu.EXIT_BUDGET)
        self.assertEqual(payload["stop"], "budget:budget_write_failed")
        self.assertEqual(transport.urls, [])  # nothing was sent
        self.assertEqual(calls, 0)

    def test_budget_exhausted_before_second_call(self):
        budget = self.budget()
        zhihu.run_search("a", batch=budget,
                         transport=FakeTransport({"status": 200, "json": SEARCH_JSON}),
                         collected_at=COLLECTED)
        second = zhihu.run_search("b", batch=budget,
                                  transport=FakeTransport({"status": 200, "json": SEARCH_JSON}),
                                  collected_at=COLLECTED)
        budget.close()
        self.assertEqual(second["exit"], zhihu.EXIT_BUDGET)
        self.assertEqual(second["stop"], "budget:interval_not_elapsed")
        self.assertEqual(second["batch"]["calls"], 1)

    def test_records_cap_blocks_extra_records(self):
        budget = self.budget()
        zhihu.run_search("a", batch=budget,
                         transport=FakeTransport({"status": 200, "json": SEARCH_JSON}),
                         collected_at=COLLECTED)
        self.clock.advance(budget_mod.MIN_INTERVAL)
        payload = zhihu.run_comments("https://www.zhihu.com/question/900/answer/111",
                                     batch=budget,
                                     transport=FakeTransport({"status": 200,
                                                              "json": COMMENTS_JSON_4}),
                                     collected_at=COLLECTED)
        budget.close()
        # v11：记录数是软目标，超目标也照常输出记录（不再 budget:records_exhausted）
        self.assertNotEqual(payload["stop"], "budget:records_exhausted")
        self.assertGreaterEqual(payload["batch"]["records"], 2)
        self.assertEqual(payload["batch"]["calls"], 2)  # the call itself was charged

    def test_comments_requires_content_url(self):
        budget = self.budget()
        payload = zhihu.run_comments("https://www.zhihu.com/question/900", batch=budget,
                                     transport=FakeTransport({"status": 200,
                                                              "json": COMMENTS_JSON}),
                                     collected_at=COLLECTED)
        budget.close()
        self.assertEqual(payload["exit"], zhihu.EXIT_INPUT)
        self.assertEqual(payload["batch"]["calls"], 0)  # refused before charging

    def test_empty_search_exits_nonzero(self):
        budget = self.budget()
        payload = zhihu.run_search("空", batch=budget,
                                   transport=FakeTransport({"status": 200, "text": "",
                                                            "json": {"data": []}}),
                                   collected_at=COLLECTED)
        budget.close()
        self.assertEqual(payload["exit"], zhihu.EXIT_EMPTY)

    def test_unknown_shape_exits_unsupported(self):
        budget = self.budget()
        payload = zhihu.run_search("未知", batch=budget,
                                   transport=FakeTransport({"status": 200,
                                                            "json": {"weird": True}}),
                                   collected_at=COLLECTED)
        budget.close()
        self.assertEqual(payload["exit"], zhihu.EXIT_UNSUPPORTED)


class LoginTests(ZhihuTestBase):
    """Login branches, all against a fake browser. No real window is opened."""

    def test_signed_in_returns_ok_without_using_call_budget(self):
        budget = self.budget()
        fake = FakeBrowser([{"url": "https://www.zhihu.com/",
                             "signed_in": True, "text": "消息 私信 我的主页"}])
        result = asyncio.run(browser_mod.wait_for_login(
            fake, profile=self.dir, budget=budget, clock=self.clock, timeout=30))
        snapshot = budget.snapshot()
        budget.close()
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["exit"], 0)
        self.assertEqual(snapshot["calls"], 0)  # login did not eat the data budget
        self.assertEqual(snapshot["polls"], 1)

    def test_timeout_is_not_success(self):
        budget = self.budget()
        fake = FakeBrowser([{"url": "https://www.zhihu.com/signin", "signed_in": False,
                             "text": "扫码登录"}])
        result = asyncio.run(browser_mod.wait_for_login(
            fake, profile=self.dir, budget=budget, clock=self.clock, timeout=10))
        budget.close()
        self.assertEqual(result["status"], "timeout")
        self.assertEqual(result["exit"], zhihu.EXIT_LOGIN_TIMEOUT)
        self.assertNotEqual(result["exit"], 0)

    def test_poll_quota_covers_full_window(self):
        # 300s at 3s poll must not hit the quota before the window ends
        self.assertGreaterEqual(budget_mod.polls_for_window(300, 3.0), 100)
        self.assertEqual(budget_mod.MAX_POLLS, 120)

    def test_poll_limit_is_its_own_nonzero_exit(self):
        budget = self.budget()
        fake = FakeBrowser([{"url": "https://www.zhihu.com/signin", "signed_in": False}])
        result = asyncio.run(browser_mod.wait_for_login(
            fake, profile=self.dir, budget=budget, clock=self.clock, timeout=300,
            max_polls=2))
        budget.close()
        self.assertEqual(result["stop_reason"], "poll_limit")
        self.assertEqual(result["exit"], zhihu.EXIT_LOGIN_POLL_LIMIT)
        self.assertEqual(result["polls"], 2)

    def test_risk_during_login_locks_budget(self):
        budget = self.budget()
        fake = FakeBrowser([{"url": "https://www.zhihu.com/signin", "signed_in": False,
                             "text": "请完成安全验证"}])
        result = asyncio.run(browser_mod.wait_for_login(
            fake, profile=self.dir, budget=budget, clock=self.clock, timeout=30))
        self.assertEqual(result["status"], "risk")
        self.assertEqual(result["exit"], zhihu.EXIT_RISK)
        locked = budget.snapshot()
        budget.close()
        self.assertTrue(locked["locked"])
        self.assertEqual(locked["lock_source"], "login")
        with self.assertRaises(budget_mod.BudgetError):
            self.budget()

    def test_locked_budget_refuses_login(self):
        budget = self.budget()
        budget.lock("text:安全验证", source="detail")
        budget.close()
        with self.assertRaises(budget_mod.BudgetError) as caught:
            self.budget(batch_id="login-attempt")
        self.assertEqual(caught.exception.code, "batch_locked")

    def test_final_url_is_sanitized(self):
        budget = self.budget()
        fake = FakeBrowser([{"url": "https://www.zhihu.com/?token=SECRET&x=1",
                             "signed_in": True}])
        result = asyncio.run(browser_mod.wait_for_login(
            fake, profile=self.dir, budget=budget, clock=self.clock, timeout=30))
        budget.close()
        self.assertEqual(result["final_url"], "https://www.zhihu.com/")
        self.assertNotIn("SECRET", json.dumps(result))

    def test_fake_evaluate_is_async_like_nodriver(self):
        self.assertTrue(inspect.iscoroutinefunction(FakeBrowser.evaluate))

    def test_wait_for_login_is_async(self):
        self.assertTrue(inspect.iscoroutinefunction(browser_mod.wait_for_login))

    def test_eval_awaits_coroutine_and_sync_values(self):
        class AsyncEval:
            async def evaluate(self, script):
                return "https://www.zhihu.com/"

        class SyncEval:
            def evaluate(self, script):
                return "https://www.zhihu.com/"

        self.assertEqual(asyncio.run(browser_mod._eval(AsyncEval(), "location.href")),
                         "https://www.zhihu.com/")
        self.assertEqual(asyncio.run(browser_mod._eval(SyncEval(), "location.href")),
                         "https://www.zhihu.com/")

    def test_signin_copy_is_not_a_wall(self):
        # /signin legitimately shows "获取验证码 / 短信验证码"
        text = "扫码登录 获取验证码 短信验证码 密码登录"
        self.assertIsNone(zhihu.detect_login_wall(text))
        fake = FakeBrowser([{"url": "https://www.zhihu.com/signin", "signed_in": False,
                             "text": text}])
        budget = self.budget()
        result = asyncio.run(browser_mod.wait_for_login(
            fake, profile=self.dir, budget=budget, clock=self.clock, timeout=10,
            max_polls=2))
        budget.close()
        # not risk: the window is allowed to stay open (poll_limit/timeout both fine)
        self.assertNotEqual(result["status"], "risk")
        self.assertIsNone(result["risk_reason"])
        self.assertNotEqual(result["exit"], zhihu.EXIT_RISK)

    def test_real_wall_still_locks_login(self):
        self.assertEqual(zhihu.detect_login_wall("请完成安全验证"), "text:安全验证")
        self.assertEqual(zhihu.detect_login_wall("访问异常，请稍后再试"), "text:访问异常")
        fake = FakeBrowser([{"url": "https://www.zhihu.com/signin", "signed_in": False,
                             "text": "访问异常"}])
        budget = self.budget()
        result = asyncio.run(browser_mod.wait_for_login(
            fake, profile=self.dir, budget=budget, clock=self.clock, timeout=10))
        self.assertEqual(result["status"], "risk")
        self.assertEqual(result["risk_reason"], "text:访问异常")
        locked = budget.snapshot()
        budget.close()
        self.assertTrue(locked["locked"])
        self.assertEqual(locked["lock_source"], "login")

    def test_signed_in_wins_over_captcha_copy(self):
        fake = FakeBrowser([{"url": "https://www.zhihu.com/", "signed_in": True,
                             "text": "验证码 安全验证"}])
        budget = self.budget()
        result = asyncio.run(browser_mod.wait_for_login(
            fake, profile=self.dir, budget=budget, clock=self.clock, timeout=10))
        budget.close()
        self.assertEqual(result["status"], "ok")
        self.assertIsNone(result["risk_reason"])
        self.assertEqual(result["exit"], 0)

    def test_detect_risk_unchanged_for_non_login(self):
        self.assertEqual(zhihu.detect_risk("获取验证码"), "text:验证码")
        self.assertEqual(zhihu.detect_risk("请登录后查看"), "text:请登录后查看")
        self.assertIsNone(zhihu.detect_risk("普通的回答正文"))

    def test_unknown_browser_is_not_success(self):
        self.assertEqual(browser_mod.classify_login_page(
            url="https://www.zhihu.com/signin", signed_in=False,
            risk_reason=None, still_waiting=False), "unknown")


class TransportTests(unittest.TestCase):
    def test_public_http_refuses_to_follow_redirects(self):
        """A 302 must come back as a result, never be followed inside one charge."""
        handler = transport_mod._NoRedirect()
        self.assertIsNone(handler.redirect_request(
            None, None, 302, "Found", {}, "https://evil.test/x"))

    def test_offline_transport_never_reports_success(self):
        result = transport_mod.RefusedTransport().fetch("https://www.zhihu.com/")
        self.assertIsNone(result["status"])
        self.assertEqual(result["error"], "network_disabled_offline_batch")

    def test_same_site_check(self):
        self.assertTrue(transport_mod._same_site("https://www.zhihu.com/x", "zhihu.com"))
        self.assertTrue(transport_mod._same_site("https://zhuanlan.zhihu.com/p/1",
                                                 "zhihu.com"))
        self.assertFalse(transport_mod._same_site("https://evil.test/", "zhihu.com"))
        self.assertFalse(transport_mod._same_site("https://zhihu.com.evil.test/",
                                                  "zhihu.com"))

    def test_authenticated_transport_blocks_offsite_landing(self):
        class FakeTab:
            async def get_content(self):
                return "<html>ok</html>"

            async def evaluate(self, script):
                return "https://evil.test/steal"

        class FakeBrowserObj:
            async def get(self, url):
                return FakeTab()

        transport = transport_mod.AuthenticatedBrowserTransport(
            "/tmp/profile", browser=FakeBrowserObj())
        result = transport.fetch("https://www.zhihu.com/question/1")
        self.assertIsNone(result["status"])
        self.assertTrue(result["error"].startswith("offsite_redirect:"))

    def test_authenticated_transport_uses_one_loop(self):
        """Launch and navigation must run on the same event loop."""
        seen = {}

        class FakeBrowserObj:
            async def get(self, url):
                seen["nav_loop"] = asyncio.get_running_loop()
                return FakeTab()

        class FakeTab:
            async def get_content(self):
                return "<html>ok</html>"

            async def evaluate(self, script):
                return "https://www.zhihu.com/question/1"

        transport = transport_mod.AuthenticatedBrowserTransport(
            "/tmp/profile", browser=FakeBrowserObj())
        # the transport's own loop is what _navigate runs on
        transport.fetch("https://www.zhihu.com/question/1")
        self.assertIs(seen["nav_loop"], transport._loop)

    def test_authenticated_transport_times_out_instead_of_hanging(self):
        """A never-returning get must raise TimeoutError, not hang forever."""
        import time

        class HangingBrowser:
            async def get(self, url):
                await asyncio.sleep(3600)

        transport = transport_mod.AuthenticatedBrowserTransport(
            "/tmp/profile", browser=HangingBrowser(), timeout=0.2)
        started = time.monotonic()
        result = transport.fetch("https://www.zhihu.com/question/1")
        elapsed = time.monotonic() - started
        self.assertEqual(result["error"], "browser:TimeoutError")
        self.assertIsNone(result["status"])
        self.assertLess(elapsed, 5.0)

    def test_authenticated_transport_returns_html_when_on_site(self):
        class FakeTab:
            async def get_content(self):
                return "<html><body>content</body></html>"

            async def evaluate(self, script):
                return "https://www.zhihu.com/question/1"

        class FakeBrowserObj:
            async def get(self, url):
                return FakeTab()

        transport = transport_mod.AuthenticatedBrowserTransport(
            "/tmp/profile", browser=FakeBrowserObj())
        result = transport.fetch("https://www.zhihu.com/question/1")
        self.assertEqual(result["status"], 200)
        self.assertIn("content", result["text"])
        self.assertIsNone(result["error"])


class ExportTests(ZhihuTestBase):
    def test_export_is_a_whitelist_and_drops_nested_secrets(self):
        source = self.dir / "records.jsonl"
        rows = [
            {"native_id": "111", "type": "answer", "parent_id": "900",
             "url": "https://www.zhihu.com/question/900/answer/111?utm_source=x&token=SECRET",
             "title": "问题", "text": "正文", "published_at": COLLECTED,
             "collected_at": COLLECTED, "voteup": 3, "comments": 1, "likes": None,
             "author": "某人", "nickname": "某人", "cookies": {"z_c0": "SECRET"},
             "password": "hunter2", "credentials": {"token": "SECRET"},
             "field_evidence": {"native_id": "json:object.id"}},
            {"native_id": "222", "type": "article", "url": "https://zhuanlan.zhihu.com/p/222",
             "title": None, "text": None, "user_nickname": "另一个",
             "profile": {"email": "a@b.c"}},
        ]
        source.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n",
                          encoding="utf-8")
        out = self.dir / "export" / "out.jsonl"
        payload = zhihu.export(source, out, fmt="jsonl")
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["count"], 2)
        self.assertIn("cookies", payload["dropped_keys"])
        self.assertIn("password", payload["dropped_keys"])
        self.assertIn("credentials", payload["dropped_keys"])
        self.assertIn("nickname", payload["dropped_keys"])
        self.assertEqual(payload["url_query_stripped"], 1)
        self.assertEqual(payload["unsupported"], ["222"])

        text = out.read_text(encoding="utf-8")
        written = [json.loads(line) for line in text.splitlines()]
        # recursive scan: no secret may survive anywhere in the output
        for banned in ("SECRET", "hunter2", "cookies", "password", "nickname",
                       "credentials", "profile", "a@b.c"):
            self.assertNotIn(banned, text)
        # `author` 现在是白名单字段（统一导出补齐）；`nickname` 仍被丢弃
        self.assertEqual(written[0]["author"], "某人")
        self.assertNotIn("nickname", written[0])
        self.assertEqual(set(written[0]) <= set(rec.EXPORT_FIELDS), True)
        self.assertEqual(written[0]["url"],
                         "https://www.zhihu.com/question/900/answer/111")
        self.assertIsNone(written[1]["title"])

    def test_export_rejects_unknown_evidence_and_source(self):
        source = self.dir / "records.jsonl"
        rows = [{"native_id": "1", "url": "https://www.zhihu.com/p/1", "title": "t",
                 "source": "https://evil.test/leak",
                 "field_evidence": {"native_id": "cookie:z_c0=SECRET",
                                    "title": "json:object.title"}}]
        source.write_text(json.dumps(rows[0], ensure_ascii=False) + "\n", encoding="utf-8")
        payload = zhihu.export(source, self.dir / "out.jsonl")
        record = payload["records"][0]
        self.assertEqual(record["source"], "redacted")
        self.assertIsNone(record["field_evidence"]["native_id"])
        self.assertTrue(record["evidence_rejected"])
        self.assertEqual(record["field_evidence"]["title"], "json:object.title")
        self.assertNotIn("SECRET", json.dumps(payload))

    def test_export_reads_json_array_too(self):
        source = self.dir / "records.json"
        source.write_text(json.dumps([{"native_id": "1", "url": "https://www.zhihu.com/p/1"}],
                                     ensure_ascii=False), encoding="utf-8")
        payload = zhihu.export(source, self.dir / "out.json", fmt="json")
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["count"], 1)
        self.assertTrue(pathlib.Path(payload["output"]).is_file())

    def test_export_missing_input_is_nonzero(self):
        payload = zhihu.export(self.dir / "missing.jsonl")
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["exit"], zhihu.EXIT_EXPORT)

    def test_cli_missing_input_file_exits_8_and_charges_nothing(self):
        state = self.dir / "state"
        code = zhihu.main(["--state-dir", str(state), "search", "x",
                           "--input", str(self.dir / "nope.json")])
        self.assertEqual(code, zhihu.EXIT_INPUT)
        snapshot = budget_mod.peek(state)
        self.assertEqual(snapshot["calls"], 0)


class DoctorTests(ZhihuTestBase):
    def test_doctor_without_profile_is_waiting_not_online(self):
        payload = zhihu.doctor(self.dir / "no_profile")
        self.assertFalse(payload["profile_exists"])
        self.assertEqual(payload["online"], "unverified")
        self.assertEqual(payload["network"], "none")

    def test_doctor_reads_cookie_names_only(self):
        import sqlite3

        profile = self.dir / "profile"
        network = profile / "Default" / "Network"
        network.mkdir(parents=True)
        cookies = network / "Cookies"
        conn = sqlite3.connect(str(cookies))
        conn.execute("CREATE TABLE cookies(name TEXT, host_key TEXT, value TEXT)")
        conn.execute("INSERT INTO cookies VALUES ('z_c0','.zhihu.com','SECRETVALUE')")
        conn.execute("INSERT INTO cookies VALUES ('other','.example.com','SECRETVALUE')")
        conn.commit()
        conn.close()

        payload = zhihu.doctor(profile)
        self.assertTrue(payload["cookie_db_exists"])
        self.assertEqual(payload["cookie_names"]["z_c0"], True)
        self.assertEqual(payload["cookie_names"]["d_c0"], False)
        self.assertEqual(payload["cookie_count"], 1)
        self.assertEqual(payload["online"], "unverified")  # names are not a session
        self.assertNotIn("SECRETVALUE", json.dumps(payload))

    def test_doctor_never_claims_online_from_cookie_presence(self):
        payload = zhihu.doctor(self.dir / "absent")
        self.assertNotIn(payload["online"], ("online", "valid", "ready"))

    def test_doctor_does_not_create_a_missing_cookie_db(self):
        profile = self.dir / "empty_profile"
        (profile / "Default" / "Network").mkdir(parents=True)
        payload = zhihu.doctor(profile)
        self.assertFalse(payload["cookie_db_exists"])
        self.assertFalse((profile / "Default" / "Network" / "Cookies").exists())


class FakeTab:
    """A nodriver-shaped tab driven by a scripted list of page states.

    Each readiness cycle consumes the next state (level 1 advances it, levels
    2/3 reuse it), so a test can script "loading first, then results" and the
    transport must observe the change. `hang_levels` makes a given tier hang,
    which is how the degradation paths are exercised.
    """

    def __init__(self, states, *, final_url="https://www.zhihu.com/search?type=content&q=x",
                 hang_get=False, hang_content=False, final_url_fails=False,
                 hang_levels=()) -> None:
        self.states = list(states)
        self.index = 0
        self.current = self.states[0]
        self.final_url = final_url
        self.hang_get = hang_get
        self.hang_content = hang_content
        self.final_url_fails = final_url_fails
        self.hang_levels = {int(x) for x in hang_levels}
        self.evaluated = 0
        self.levels_seen: list[int] = []

    def _advance(self):
        self.current = self.states[min(self.index, len(self.states) - 1)]
        if self.index < len(self.states) - 1:
            self.index += 1
        return self.current

    async def evaluate(self, script: str):
        self.evaluated += 1
        if "location.href" in script:
            if self.final_url_fails:
                raise RuntimeError("evaluate_failed")
            return self.final_url
        if "level:1" in script:
            level = 1
        elif "level:2" in script:
            level = 2
        elif "level:3" in script:
            level = 3
        else:
            level = 1
        self.levels_seen.append(level)
        if level in self.hang_levels:
            await asyncio.sleep(3600)
        state = self._advance() if level == 1 else self.current
        return json.dumps(state.get(f"level{level}", {}), ensure_ascii=False)

    async def get_content(self):
        if self.hang_content:
            await asyncio.sleep(3600)
        return self.states[-1].get("html", "")


class FakePageBrowser:
    def __init__(self, tab: FakeTab) -> None:
        self._tab = tab
        self.navigated = 0

    async def get(self, url: str):
        self.navigated += 1
        if getattr(self._tab, "hang_get", False):
            await asyncio.sleep(3600)
        return self._tab


def _page_state(ready="complete", anchors=None, wall=None, emptyish=False, contentish=0, html=""):
    """One logical page state, expanded into the three probe-tier payloads."""
    hrefs = list(anchors or [])
    shapes = {"answer": 0, "question": 0, "article": 0, "video": 0, "other": 0}
    for href in hrefs[:20]:
        path = href.split("?")[0]
        if re.search(r"/question/\d+/answer/\d+/?$", path):
            shapes["answer"] += 1
        elif re.search(r"/question/\d+/?$", path):
            shapes["question"] += 1
        elif re.search(r"/p/\d+/?$", path):
            shapes["article"] += 1
        elif re.search(r"/zvideo/\d+/?$", path):
            shapes["video"] += 1
        else:
            shapes["other"] += 1
    return {"level1": {"level": 1, "readyState": ready, "anchorCount": len(hrefs),
                       "sampled": min(len(hrefs), 20), "shapes": shapes},
            "level2": {"level": 2, "counts": {"result": contentish, "list": 0}},
            "level3": {"level": 3, "wall": wall, "emptyish": bool(emptyish), "textLen": 0},
            "html": html}


RESULT_ANCHORS = ["/question/900/answer/111", "/p/222", "/people/someone", "#top"]
EMPTY_PAGE_ANCHORS = ["/search", "/static/logo.png"]


class ReadinessAndDeadlineTests(ZhihuTestBase):
    """One total deadline, observed readiness, redacted diagnostics. No browser."""

    def _transport(self, browser, **kwargs):
        return transport_mod.AuthenticatedBrowserTransport(
            self.dir / "profile", browser=browser, **kwargs)

    def test_loading_then_result_is_observed(self):
        tab = FakeTab([_page_state(ready="loading"),
                       _page_state(anchors=RESULT_ANCHORS, contentish=3,
                                   html="<html><body>ok</body></html>")])
        result = self._transport(FakePageBrowser(tab), timeout=5.0).fetch(
            "https://www.zhihu.com/search?type=content&q=x")
        self.assertEqual(result["status"], 200)
        self.assertEqual(result["probe"]["state"], "result")
        self.assertEqual(result["probe"]["level"], 1)
        self.assertGreaterEqual(tab.evaluated, 2)
        self.assertEqual(result["probe"]["anchors_recognized"], 2)
        self.assertEqual(result["probe"]["anchors_rejected"], 2)

    def test_light_probe_success_then_heavier_levels_run(self):
        """Level 1 says "not ready" -> levels 2 and 3 must run before giving up."""
        tab = FakeTab([_page_state(ready="loading")])
        result = self._transport(FakePageBrowser(tab), timeout=0.9).fetch(
            "https://www.zhihu.com/search?q=x")
        self.assertIn(2, tab.levels_seen)
        self.assertIn(3, tab.levels_seen)
        self.assertEqual(result["diagnostics"]["state"], "unknown")

    def test_light_probe_timeout_degrades_to_unknown(self):
        """A stuck light probe is one level's unknown, not a whole-call failure."""
        tab = FakeTab([_page_state(anchors=RESULT_ANCHORS,
                                   html="<html><body>x</body></html>")],
                      hang_levels=(1,))
        result = self._transport(FakePageBrowser(tab), timeout=1.0).fetch(
            "https://www.zhihu.com/search?q=x")
        self.assertEqual(result["status"], 200)  # content was still read
        probe = result["probe"]
        self.assertEqual(probe["state"], "unknown")
        self.assertEqual(probe["level"], 1)
        self.assertTrue(probe["level_timeout"])
        self.assertEqual(result["diagnostics"]["probe_level"], 1)

    def test_heavier_probe_timeout_degrades_to_unknown(self):
        tab = FakeTab([_page_state(ready="loading", html="<html></html>")],
                      hang_levels=(2,))
        result = self._transport(FakePageBrowser(tab), timeout=1.2).fetch(
            "https://www.zhihu.com/search?q=x")
        self.assertEqual(result["status"], 200)
        self.assertEqual(result["probe"]["state"], "unknown")
        self.assertEqual(result["probe"]["level"], 2)
        self.assertTrue(result["probe"]["level_timeout"])

    def test_probe_timings_and_level_are_in_diagnostics(self):
        tab = FakeTab([_page_state(anchors=RESULT_ANCHORS)])
        result = self._transport(FakePageBrowser(tab), timeout=5.0).fetch(
            "https://www.zhihu.com/search?q=x")
        diag = result["diagnostics"]
        self.assertIn("probe_level", diag)
        self.assertIn("probe_elapsed_ms", diag)
        self.assertIn("1", diag["probe_elapsed_ms"])
        self.assertIsInstance(diag["probe_elapsed_ms"]["1"], int)

    def test_default_timeout_is_60_seconds(self):
        transport = transport_mod.AuthenticatedBrowserTransport(self.dir / "profile")
        self.assertEqual(transport.timeout, 60.0)
        self.assertEqual(transport_mod.AuthenticatedBrowserTransport(
            self.dir / "profile", timeout=5.0).timeout, 5.0)

    def test_stuck_light_probe_stops_without_resetting_deadline(self):
        """A stuck tier ends the wait at that tier, inside the one budget."""
        import time

        tab = FakeTab([_page_state(anchors=RESULT_ANCHORS)], hang_levels=(1, 2, 3))
        started = time.monotonic()
        result = self._transport(FakePageBrowser(tab), timeout=1.2).fetch(
            "https://www.zhihu.com/search?q=x")
        elapsed = time.monotonic() - started
        self.assertLess(elapsed, 2.0, "tiers must share the one deadline")
        self.assertEqual(result["probe"]["state"], "unknown")
        self.assertEqual(result["probe"]["level"], 1)

    def test_cli_timeout_and_diagnostics_dir_reach_the_transport(self):
        args = zhihu.build_parser().parse_args(["search", "x", "--timeout", "60",
                                               "--diagnostics-dir", str(self.dir / "diag")])
        self.assertEqual(args.timeout, 60.0)
        self.assertEqual(args.diagnostics_dir, str(self.dir / "diag"))
        default = zhihu.build_parser().parse_args(["search", "x"])
        self.assertEqual(default.timeout, 60.0)

    def test_explicit_empty_result_is_not_unknown(self):
        tab = FakeTab([_page_state(anchors=EMPTY_PAGE_ANCHORS, emptyish=True,
                                   html="<html><body>没有找到</body></html>")])
        result = self._transport(FakePageBrowser(tab), timeout=5.0).fetch(
            "https://www.zhihu.com/search?q=x")
        self.assertEqual(result["status"], 200)
        self.assertEqual(result["probe"]["state"], "empty")

    def test_always_loading_times_out_as_unknown(self):
        tab = FakeTab([_page_state(ready="loading")])
        result = self._transport(FakePageBrowser(tab), timeout=1.0).fetch(
            "https://www.zhihu.com/search?q=x")
        self.assertIsNone(result["status"])
        self.assertEqual(result["error"], "browser:TimeoutError")
        self.assertEqual(result["diagnostics"]["state"], "unknown")
        self.assertFalse(result["final_url_known"])

    def test_login_wall_is_reported_as_risk(self):
        tab = FakeTab([_page_state(anchors=["/signin"], wall="安全验证")])
        result = self._transport(FakePageBrowser(tab), timeout=5.0).fetch(
            "https://www.zhihu.com/search?q=x")
        self.assertIsNone(result["status"])
        self.assertIn("risk", result["error"])
        self.assertEqual(result["diagnostics"]["state"], "risk")

    def test_final_url_read_failure_is_unknown_not_input_url(self):
        tab = FakeTab([_page_state(anchors=RESULT_ANCHORS)], final_url_fails=True)
        result = self._transport(FakePageBrowser(tab), timeout=5.0).fetch(
            "https://www.zhihu.com/search?q=x")
        self.assertEqual(result["status"], 200)
        self.assertFalse(result["final_url_known"])
        self.assertIsNone(result["diagnostics"].get("final_url"))
        self.assertEqual(result["diagnostics"]["state"], "unknown")

    def test_hanging_get_content_is_bounded(self):
        tab = FakeTab([_page_state(anchors=RESULT_ANCHORS)], hang_content=True)
        result = self._transport(FakePageBrowser(tab), timeout=1.0).fetch(
            "https://www.zhihu.com/search?q=x")
        self.assertIsNone(result["status"])
        self.assertIn("TimeoutError", result["error"])

    def test_hanging_get_is_bounded(self):
        tab = FakeTab([_page_state(anchors=RESULT_ANCHORS)], hang_get=True)
        result = self._transport(FakePageBrowser(tab), timeout=1.0).fetch(
            "https://www.zhihu.com/search?q=x")
        self.assertIsNone(result["status"])
        self.assertIn("TimeoutError", result["error"])

    def test_total_deadline_is_not_reset_per_phase(self):
        """Phases share one budget: a 0.6s budget cannot take longer than that."""
        import time

        class SlowTab(FakeTab):
            async def get(self, url):
                await asyncio.sleep(0.4)
                return self

            async def get_content(self):
                await asyncio.sleep(0.4)
                return "<html></html>"

        browser = FakePageBrowser(SlowTab([_page_state(ready="loading", anchors=[])]))
        started = time.monotonic()
        result = self._transport(browser, timeout=0.6).fetch("https://www.zhihu.com/search?q=x")
        elapsed = time.monotonic() - started
        self.assertIsNone(result["status"])
        self.assertLess(elapsed, 1.4, "phases must share one deadline")
        self.assertIn("TimeoutError", result["error"])


class DiagnosticRedactionTests(ZhihuTestBase):
    def test_diagnostic_keys_are_whitelisted(self):
        from tools.selection.access import diagnostics as diag_mod
        cleaned = diag_mod.sanitize({"requested_url": "https://www.zhihu.com/search?q=x",
                                     "secret": "SECRET", "nickname": "某人",
                                     "cookies": "z_c0=SECRET", "html": "<html>SECRET</html>",
                                     "anchors_total": 3})
        self.assertNotIn("secret", cleaned)
        self.assertNotIn("nickname", cleaned)
        self.assertNotIn("cookies", cleaned)
        self.assertNotIn("html", cleaned)
        self.assertEqual(cleaned["anchors_total"], 3)

    def test_href_shapes_do_not_leak_urls(self):
        from tools.selection.access import diagnostics as diag_mod
        shapes = diag_mod.count_href_shapes(
            ["https://www.zhihu.com/question/900/answer/111?token=SECRET",
             "https://www.zhihu.com/p/222", "https://evil.test/x",
             "/people/someone", "javascript:void(0)"])
        self.assertEqual(shapes["recognized"], 2)
        self.assertEqual(shapes["rejected"], 3)
        self.assertNotIn("SECRET", json.dumps(shapes))
        self.assertEqual(shapes["shapes"]["answer"], 1)
        self.assertEqual(shapes["shapes"]["other_cross_origin"], 1)

    def test_query_keys_are_counted_not_valued(self):
        from tools.selection.access import diagnostics as diag_mod
        counts = diag_mod.query_key_counts(
            ["https://www.zhihu.com/question/1/answer/2?token=SECRET&token=OTHER&x=1"])
        self.assertEqual(counts, {"token": 2, "x": 1})
        self.assertNotIn("SECRET", json.dumps(counts))

    def test_empty_html_is_not_reported_as_readable_links(self):
        parsed = zhihu.parse_search_html("", collected_at=COLLECTED)
        self.assertNotEqual(parsed["structure"], "html:links")
        self.assertEqual(parsed["anchors_total"], 0)
        self.assertEqual(parsed["web_state"], "empty_document")

    def test_anchors_that_do_not_match_report_unknown(self):
        html = '<html><body><a href="/people/x">人</a><a href="/tag/y">标签</a></body></html>'
        parsed = zhihu.parse_search_html(html, collected_at=COLLECTED)
        self.assertEqual(parsed["stop"], "unknown")
        self.assertEqual(parsed["structure"], "html:unknown")
        self.assertEqual(parsed["anchors_total"], 2)
        self.assertEqual(parsed["anchors_recognized"], 0)
        self.assertEqual(parsed["anchors_rejected"], 2)

    def test_zero_records_still_carry_diagnostics(self):
        class T:
            def fetch(self, url):
                return {"status": 200, "text": "", "json": None, "url": url, "final_url": url,
                        "final_url_known": True, "redirect": None, "error": None,
                        "diagnostics": {"requested_url": "https://www.zhihu.com/search?q=x",
                                        "final_url": "https://www.zhihu.com/search?q=x",
                                        "final_url_known": True, "ready_state": "complete",
                                        "state": "empty", "anchors_total": 4,
                                        "anchors_recognized": 0, "anchors_rejected": 4}}
        batch = budget_mod.open_budget(self.dir)
        payload = zhihu.run_search("x", batch=batch, transport=T(), collected_at=COLLECTED)
        batch.close()
        self.assertEqual(payload["count"], 0)
        self.assertEqual(payload["diagnostics"]["anchors_total"], 4)
        self.assertEqual(payload["diagnostics"]["anchors_rejected"], 4)
        self.assertNotIn("triage", payload)
        self.assertNotIn("categories", payload)

    def test_unreadable_page_is_not_reported_as_empty_success(self):
        class T:
            def fetch(self, url):
                return {"status": 200, "text": "<html></html>", "json": None, "url": url,
                        "final_url": url, "final_url_known": False, "redirect": None,
                        "error": None,
                        "diagnostics": {"requested_url": "https://www.zhihu.com/search?q=x",
                                        "final_url_known": False, "state": "unknown",
                                        "ready_state": "loading"}}
        batch = budget_mod.open_budget(self.dir)
        payload = zhihu.run_search("x", batch=batch, transport=T(), collected_at=COLLECTED)
        batch.close()
        self.assertNotEqual(payload["exit"], zhihu.EXIT_OK)
        self.assertNotEqual(payload["exit"], zhihu.EXIT_EMPTY)
        self.assertEqual(payload["stop"], "readiness_timeout")
        self.assertEqual(payload["diagnostics"]["state"], "unknown")


class VisibleWindowFlagTests(ZhihuTestBase):
    """`--visible` is opt-in: without it nothing changes, with it headless=False."""

    COMMANDS = (["search", "x"],
                ["detail", "https://www.zhihu.com/question/1"],
                ["comments", "https://www.zhihu.com/question/1/answer/2"])

    def _parse(self, argv):
        return zhihu.build_parser().parse_args(["--mode", "authenticated-browser", *argv])

    def test_default_construction_is_headless(self):
        args = self._parse(["search", "x"])
        self.assertFalse(args.visible)
        transport = zhihu._make_transport(args)
        try:
            self.assertTrue(transport.headless)
            self.assertEqual(transport.timeout, 60.0)
        finally:
            transport.close()

    def test_default_visible_is_false_for_every_command(self):
        for command in self.COMMANDS:
            self.assertFalse(self._parse(command).visible, command[0])

    def test_visible_flag_reaches_transport_for_every_command(self):
        for command in self.COMMANDS:
            args = self._parse([*command, "--visible"])
            self.assertTrue(args.visible, command[0])
            transport = zhihu._make_transport(args)
            try:
                self.assertFalse(transport.headless, command[0])
            finally:
                transport.close()

    def test_visible_does_not_touch_other_modes(self):
        args = zhihu.build_parser().parse_args(["--mode", "offline", "search", "x"])
        self.assertIsInstance(zhihu._make_transport(args), transport_mod.RefusedTransport)


class ErrorTransport:
    """Transport that only reports an error (as the browser transport does)."""

    def __init__(self, error: str, **extra) -> None:
        self.error = error
        self.extra = extra
        self.urls: list[str] = []

    def fetch(self, url: str) -> dict:
        self.urls.append(url)
        return {"status": None, "text": "", "json": None, "url": url, "final_url": url,
                "final_url_known": False, "redirect": None, "error": self.error,
                "diagnostics": {"state": "risk", "phase": "read"}, **self.extra}


class RiskLockTests(ZhihuTestBase):
    """A wall the transport saw must lock the batch, not just exit non-zero."""

    def test_captcha_wall_locks_the_batch(self):
        budget = self.budget()
        payload = zhihu.run_search("x", batch=budget,
                                   transport=ErrorTransport("browser:risk:text:验证码"),
                                   collected_at=COLLECTED)
        snapshot = budget.snapshot()
        budget.close()
        self.assertEqual(payload["exit"], zhihu.EXIT_RISK)
        self.assertIn("验证码", payload["stop"])
        self.assertTrue(snapshot["locked"])
        self.assertEqual(snapshot["lock_source"], "search")
        self.assertIn("验证码", snapshot["lock_reason"])

    def test_other_wall_markers_lock_too(self):
        for index, marker in enumerate(("安全验证", "访问异常", "操作频繁", "请求过于频繁")):
            # one fresh state dir per marker: a locked budget refuses reopening
            budget = budget_mod.open_budget(self.dir / f"wall-{index}", clock=self.clock)
            payload = zhihu.run_search("x", batch=budget,
                                       transport=ErrorTransport(f"browser:risk:text:{marker}"),
                                       collected_at=COLLECTED)
            snapshot = budget.snapshot()
            budget.close()
            self.assertEqual(payload["exit"], zhihu.EXIT_RISK, marker)
            self.assertTrue(snapshot["locked"], marker)
            self.assertIn(marker, snapshot["lock_reason"], marker)

    def test_lock_survives_restart_and_blocks_the_next_command(self):
        budget = self.budget()
        zhihu.run_search("x", batch=budget,
                         transport=ErrorTransport("browser:risk:text:验证码"),
                         collected_at=COLLECTED)
        budget.close()
        # same state dir, new batch object: the lock is persisted
        with self.assertRaises(budget_mod.BudgetError) as caught:
            self.budget()
        self.assertEqual(caught.exception.code, "batch_locked")

    def test_locked_batch_sends_no_second_request(self):
        budget = self.budget()
        zhihu.run_search("x", batch=budget,
                         transport=ErrorTransport("browser:risk:text:验证码"),
                         collected_at=COLLECTED)
        self.clock.advance(budget_mod.MIN_INTERVAL)
        second = ErrorTransport("browser:risk:text:验证码")
        payload = zhihu.run_search("y", batch=budget, transport=second,
                                   collected_at=COLLECTED)
        snapshot = budget.snapshot()
        budget.close()
        self.assertEqual(payload["exit"], zhihu.EXIT_BUDGET)
        self.assertEqual(payload["stop"], "budget:batch_locked")
        self.assertEqual(second.urls, [])  # refused before any request
        self.assertEqual(snapshot["calls"], 1)

    def test_detail_and_comments_paths_lock_as_well(self):
        budget = self.budget()
        detail = zhihu.run_detail("https://www.zhihu.com/question/1/answer/2", batch=budget,
                                  transport=ErrorTransport("browser:risk:text:安全验证"),
                                  collected_at=COLLECTED)
        snapshot = budget.snapshot()
        budget.close()
        self.assertEqual(detail["exit"], zhihu.EXIT_RISK)
        self.assertTrue(snapshot["locked"])
        self.assertEqual(snapshot["lock_source"], "detail")

    def test_non_risk_errors_still_do_not_lock(self):
        budget = self.budget()
        payload = zhihu.run_search("x", batch=budget,
                                   transport=ErrorTransport("browser:TimeoutError"),
                                   collected_at=COLLECTED)
        snapshot = budget.snapshot()
        budget.close()
        self.assertEqual(payload["exit"], zhihu.EXIT_TRANSPORT)
        self.assertFalse(snapshot["locked"])

    def test_offsite_redirect_lock_unchanged(self):
        self.assertEqual(zhihu._risk_or_error({"error": "offsite_redirect:evil.test"}),
                         ("offsite_redirect:evil.test", True))
        self.assertEqual(zhihu._risk_or_error({"error": "browser:TimeoutError"}),
                         ("browser:TimeoutError", False))
        self.assertEqual(zhihu._risk_or_error({"error": "browser:risk:text:验证码"}),
                         ("browser:risk:text:验证码", True))

    def test_probe_reads_document_ready_state(self):
        script = transport_mod.PROBE_LIGHT_JS
        self.assertIn("document.readyState", script)
        self.assertNotIn("documentElement.readyState", script)


if __name__ == "__main__":
    unittest.main()
