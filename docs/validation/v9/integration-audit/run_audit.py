#!/usr/bin/env python
"""V9-5a independent audit: UI round -> cards, resume, dedupe/undo, import.

All databases, secrets and raw output are temp. The only network edge that is
replaced is the Bilibili fetch transport; state machine, categorization and
routes are the real implementation. No production DB is touched.
"""

from __future__ import annotations

import hashlib
import json
import os
import pathlib
import sqlite3
import sys
import tempfile
import time

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[3]  # docs/validation/v9/integration-audit -> repo root
sys.path.insert(0, str(ROOT))

TMP = tempfile.TemporaryDirectory(prefix="v9_audit_")
TMPDIR = pathlib.Path(TMP.name)
os.environ["V9_SELECTION_DB"] = str(TMPDIR / "selection.sqlite3")
os.environ["WORKBENCH_WORKFLOW_DB"] = str(TMPDIR / "workflow.sqlite3")
os.environ["WORKBENCH_SECRET_FILE"] = str(TMPDIR / "secret")
os.environ["APP_DB_PATH"] = str(TMPDIR / "app.db")

from tools.selection import bilibili, categories, db, models, rounds, xianyu  # noqa: E402
import importlib.util
WORKBENCH = ROOT / "tools" / "workbench"
sys.path.insert(0, str(WORKBENCH))
_spec = importlib.util.spec_from_file_location("workbench_audit_app", WORKBENCH / "app.py")
wb = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(wb)

RESULTS = {"env": {k: os.environ[k] for k in ("V9_SELECTION_DB", "WORKBENCH_WORKFLOW_DB",
                                              "WORKBENCH_SECRET_FILE", "APP_DB_PATH")},
           "experiments": []}


def add(eid, title, expected, actual, verdict, refs, evidence=None):
    RESULTS["experiments"].append({
        "id": eid, "title": title, "expected": expected, "actual": actual,
        "verdict": verdict, "code_refs": refs, "evidence": evidence or {},
    })
    print(json.dumps({"id": eid, "verdict": verdict, "actual": actual}, ensure_ascii=False))


def hash_file(p):
    return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()


HASH_FILES = [
    "tools/selection/db.py", "tools/selection/models.py", "tools/selection/categories.py",
    "tools/selection/bilibili.py", "tools/selection/rounds.py", "tools/selection/xianyu.py",
    "tools/selection/cli.py", "tools/workbench/app.py", "tools/workbench/views_leads.py",
    "tests/test_selection_categories.py", "tests/test_selection_rounds_state.py",
    "tests/test_selection_leads.py", "tests/test_selection_db.py",
    "instance/app.db", "CONTRACT.md", "scoring/scores.csv", "sourcing/sources.csv",
]
def hashes():
    return {p: hash_file(ROOT / p) for p in HASH_FILES if (ROOT / p).exists()}


RESULTS["hashes_before"] = hashes()

# ---------------------------------------------------------------- transport stub
VIEW = {"aid": 1, "bvid": "BV1", "title": "synthetic audit video", "videos": 1,
        "stat": {"reply": 2}}
REPLY = {"page": {"num": 1, "size": 5, "count": 2},
         "replies": [
             {"rpid": 101, "root": 0, "parent": 0, "content": {"message": "学生 学习计划 notion 模板"}},
             {"rpid": 102, "root": 0, "parent": 0, "content": {"message": "学生 学习计划 notion 模板 新版"}},
         ]}


def payload(data):
    return json.dumps({"code": 0, "message": "OK", "data": data}).encode()


class FakeFetch:
    def __init__(self, *, cancel_round_id=None, db_path=None):
        self.calls = []
        self.cancel_round_id = cancel_round_id
        self.db_path = db_path

    def __call__(self, url):
        self.calls.append(url)
        if self.cancel_round_id and "/view?" in url:
            c = db.connect(self.db_path)
            try:
                rounds.cancel(c, self.cancel_round_id)
            finally:
                c.close()
        if "/view?" in url:
            return bilibili.FetchResult(200, payload(VIEW), {}, url)
        return bilibili.FetchResult(200, payload(REPLY), {}, url)


# ---------------------------------------------------------------- 1 UI start -> cards
def experiment_ui_start():
    sel = pathlib.Path(os.environ["V9_SELECTION_DB"])
    for p in (sel, pathlib.Path(str(sel) + "-wal"), pathlib.Path(str(sel) + "-shm")):
        try:
            p.unlink()
        except FileNotFoundError:
            pass
    app = wb.create_app()
    app.testing = True
    client = app.test_client()
    client.get("/leads")
    with client.session_transaction() as s:
        token = s["csrf"]
    fake = FakeFetch()
    old_root, old_fetch = wb.ROOT, wb.sel_bili.default_fetch
    wb.ROOT = TMPDIR
    wb.sel_bili.default_fetch = fake
    try:
        r = client.post("/leads/round", data={
            "csrf": token, "aid": "1", "budget": "3", "interval": "3",
            "idempotency_key": "audit-ui-start"})
    finally:
        wb.ROOT, wb.sel_bili.default_fetch = old_root, old_fetch
    conn = db.init_db(sel)
    try:
        ncat = conn.execute("SELECT COUNT(*) FROM categories").fetchone()[0]
        ncard = conn.execute("SELECT COUNT(*) FROM direction_card").fetchone()[0]
        nsig = conn.execute("SELECT COUNT(*) FROM signals").fetchone()[0]
        rnd = dict(conn.execute("SELECT * FROM rounds ORDER BY id DESC LIMIT 1").fetchone())
        ev = conn.execute("SELECT COUNT(*) FROM discovery_event").fetchone()[0]
    finally:
        conn.close()
    actual = {"http": r.status_code, "location": r.headers.get("Location"),
              "fetch_calls": len(fake.calls), "signals": nsig, "categories": ncat,
              "cards": ncard, "events": ev, "round_status": rnd["status"]}
    add("ui_start_cards", "选品页开轮后应能生成方向卡",
        "POST /leads/round 实际请求 2 次；signals=1；categories/card>0",
        actual,
        "FAIL" if ncard == 0 else "PASS",
        ["tools/workbench/app.py:1403-1434（start 只调用 collect_round，无 categorize/make_cards）",
         "tools/selection/categories.py:162-205（categorize/make_cards 仅 CLI 调用）"],
        {"fake_urls": fake.calls})


# ---------------------------------------------------------------- 2 UI resume -> requests
def experiment_ui_resume():
    sel = pathlib.Path(os.environ["V9_SELECTION_DB"])
    for p in (sel, pathlib.Path(str(sel) + "-wal"), pathlib.Path(str(sel) + "-shm")):
        try:
            p.unlink()
        except FileNotFoundError:
            pass
    conn = db.init_db(sel)
    r = rounds.start(conn, kind="bilibili", platform="bilibili",
                     budget={"max_requests": 3}, idempotency_key="audit-resume")
    rounds.transition(conn, r["id"], "running")
    rounds.add_item(conn, r["id"], "bilibili:view")
    rounds.add_item(conn, r["id"], "bilibili:reply")
    conn.close()
    fake = FakeFetch()
    out = bilibili.collect_round(db_path=sel, round_id=r["id"],
                                 raw_dir=TMPDIR / "raw_resume", aid=1, budget=3,
                                 interval=0, fetch=fake, pause_after_items=1)
    before_calls = len(fake.calls)
    app = wb.create_app()
    app.testing = True
    client = app.test_client()
    client.get("/leads")
    with client.session_transaction() as s:
        token = s["csrf"]
    resp = client.post(f"/leads/round/{r['id']}/resume", data={"csrf": token})
    conn = db.init_db(sel)
    try:
        st = dict(conn.execute("SELECT status,stats_json FROM rounds WHERE id=?", (r["id"],)).fetchone())
        items = [dict(x) for x in conn.execute(
            "SELECT item_key,state,last_error FROM round_item WHERE round_id=? ORDER BY id", (r["id"],))]
        nsig = conn.execute("SELECT COUNT(*) FROM signals").fetchone()[0]
    finally:
        conn.close()
    actual = {"first_collect": out.get("status"), "before_calls": before_calls,
              "post": resp.status_code, "after_calls": len(fake.calls),
              "round_status": st["status"], "items": items, "signals": nsig,
              "stats": json.loads(st["stats_json"] or "{}")}
    add("ui_resume_requests", "Continue/Resume should continue actual collection",
        "paused 后 POST resume 触发 reply 请求；requests_used 增加；reply 不再 pending",
        actual,
        "FAIL" if len(fake.calls) == before_calls and st["status"] == "running" else "PASS",
        ["tools/workbench/app.py:1436-1454（resume 只调用 sel_rounds.resume，不调用 collect_round）",
         "tools/selection/rounds.py:105-120（resume 只改状态/interrupted）"],
        {"fake_urls": fake.calls})


# ---------------------------------------------------------------- 3 repeat categorize / card refresh
def make_signal(native, title, quote, platform="xianyu", origin="synthetic"):
    return {
        "platform": platform, "native_id": str(native), "parent_native_id": None,
        "url": f"https://example.test/{platform}/{native}", "title": title, "quote": quote,
        "lang": "zh", "lang_source": "heuristic", "listed_price_minor": None,
        "effective_price_minor": None, "reference_price_minor": None, "wants": None,
        "collected_at": "2026-10-25T00:00:00Z", "collected_at_scope": "row",
        "origin_kind": origin, "raw_sha256": "a" * 64,
        "content_hash": models.content_hash(platform=platform, native_id=str(native), quote=quote,
                                            listed_price_minor=None, effective_price_minor=None,
                                            wants=None),
        "raw_ref": f"temp:{native}", "batch_id": "audit",
    }


def experiment_repeat_cards():
    c = db.init_db(TMPDIR / "cat_repeat.sqlite3")
    try:
        _, s1 = db.upsert_signal(c, make_signal(1, "学习计划 Notion 模板", "学生 学习计划 notion 模板"))
        r1 = categories.run_categorize(c)
        card1 = categories.make_cards(c)
        ev1 = c.execute("SELECT COUNT(*) FROM discovery_event").fetchone()[0]
        _, s2 = db.upsert_signal(c, make_signal(2, "学习计划 Notion 模板 新", "学生 学习计划 notion 模板", "bilibili"))
        r2 = categories.run_categorize(c)
        card2 = categories.make_cards(c)
        ev2 = c.execute("SELECT COUNT(*) FROM discovery_event").fetchone()[0]
        cardrow = dict(c.execute("SELECT evidence_ids_json FROM direction_card LIMIT 1").fetchone())
        r3 = categories.run_categorize(c)
        ev3 = c.execute("SELECT COUNT(*) FROM discovery_event").fetchone()[0]
        # unknown review duplicate
        db.upsert_signal(c, make_signal(3, "完全未知", "无关键词", "xianyu"))
        categories.run_categorize(c)
        categories.run_categorize(c)
        review = c.execute("SELECT COUNT(*) FROM review_queue").fetchone()[0]
        actual = {"run1": r1, "run2": r2, "run3": r3, "card1": card1, "card2": card2,
                  "events_after_first": ev1, "events_after_second": ev2,
                  "events_after_third": ev3, "card_evidence": json.loads(cardrow["evidence_ids_json"]),
                  "review_rows_after_two_runs": review}
    finally:
        c.close()
    add("repeat_categorize_cards", "Repeated categorize should be idempotent and refresh card evidence",
        "第二次/第三次不新增重复事件；同品类新 signal 后卡片 evidence 包含 1,2；review 不重复",
        actual,
        "FAIL" if ev2 > ev1 or ev3 > ev2 or actual["card_evidence"] != [s1, s2] or review > 1 else "PASS",
        ["tools/selection/categories.py:162-175（run_categorize 全表重扫，每次生成 update）",
         "tools/selection/categories.py:178-205（existing card 直接 continue，不补 evidence）"],
        {"signal_ids": [s1, s2]})


# ---------------------------------------------------------------- 4 excluded/merged attribution
def experiment_attribution():
    c = db.init_db(TMPDIR / "cat_attrib.sqlite3")
    try:
        _, sA = db.upsert_signal(c, make_signal(10, "学习计划 Notion 模板", "学生 学习计划 notion 模板"))
        _, sB = db.upsert_signal(c, make_signal(11, "学习计划 Excel 表格", "学生 学习计划 excel 表格"))
        cA = categories.categorize_signal(c, dict(c.execute("SELECT * FROM signals WHERE id=?", (sA,)).fetchone()))
        cB = categories.categorize_signal(c, dict(c.execute("SELECT * FROM signals WHERE id=?", (sB,)).fetchone()))
        categories.exclude(c, cA["category_id"])
        _, sNew = db.upsert_signal(c, make_signal(12, "学习计划 Notion 模板 新", "学生 学习计划 notion 模板", "bilibili"))
        excluded_out = categories.categorize_signal(c, dict(c.execute("SELECT * FROM signals WHERE id=?", (sNew,)).fetchone()))
        excluded_status = c.execute("SELECT status FROM categories WHERE id=?", (cA["category_id"],)).fetchone()[0]
        # separate merge DB
        mdb = db.init_db(TMPDIR / "cat_merged.sqlite3")
        try:
            _, s1 = db.upsert_signal(mdb, make_signal(20, "学习计划 Notion 模板", "学生 学习计划 notion 模板"))
            _, s2 = db.upsert_signal(mdb, make_signal(21, "学习计划 Excel 表格", "学生 学习计划 excel 表格"))
            m1 = categories.categorize_signal(mdb, dict(mdb.execute("SELECT * FROM signals WHERE id=?", (s1,)).fetchone()))
            m2 = categories.categorize_signal(mdb, dict(mdb.execute("SELECT * FROM signals WHERE id=?", (s2,)).fetchone()))
            categories.merge(mdb, m1["category_id"], m2["category_id"])
            _, sNew2 = db.upsert_signal(mdb, make_signal(22, "学习计划 Notion 模板 新", "学生 学习计划 notion 模板", "bilibili"))
            merged_out = categories.categorize_signal(mdb, dict(mdb.execute("SELECT * FROM signals WHERE id=?", (sNew2,)).fetchone()))
            merged_src_status = mdb.execute("SELECT status FROM categories WHERE id=?", (m1["category_id"],)).fetchone()[0]
            merged_tgt_status = mdb.execute("SELECT status FROM categories WHERE id=?", (m2["category_id"],)).fetchone()[0]
        finally:
            mdb.close()
    finally:
        c.close()
    actual = {"excluded": excluded_out, "excluded_status": excluded_status,
              "merged": merged_out, "merged_source_status": merged_src_status,
              "merged_target_status": merged_tgt_status}
    bad = (excluded_out["category_id"] == cA["category_id"] or
           merged_out["category_id"] == m1["category_id"])
    add("merged_excluded_attribution", "Excluded/merged categories must not receive new signals as active",
        "excluded signal 进 review/new，不进 excluded；merged signal 归 target 或 review，不进 source",
        actual, "FAIL" if bad else "PASS",
        ["tools/selection/categories.py:106-126（_category 不检查 status）",
         "tools/selection/categories.py:224-237（merge 只移事件/卡片，不限制后续归类）"])


# ---------------------------------------------------------------- 5 split/undo
def experiment_split_undo():
    c = db.init_db(TMPDIR / "cat_split.sqlite3")
    try:
        _, s1 = db.upsert_signal(c, make_signal(30, "学习计划 Notion 模板 A", "学生 学习计划 notion 模板"))
        _, s2 = db.upsert_signal(c, make_signal(31, "学习计划 Notion 模板 B", "学生 学习计划 notion 模板"))
        first = categories.categorize_signal(c, dict(c.execute("SELECT * FROM signals WHERE id=?", (s1,)).fetchone()))
        second = categories.categorize_signal(c, dict(c.execute("SELECT * FROM signals WHERE id=?", (s2,)).fetchone()))
        categories.make_cards(c)
        before_card = dict(c.execute("SELECT * FROM direction_card WHERE category_id=?", (first["category_id"],)).fetchone())
        sp = categories.split(c, first["category_id"], [s1], "split experiment")
        after_split = {
            "new_category": sp["new_category_id"],
            "categories": [dict(r) for r in c.execute("SELECT id,status,merged_into FROM categories ORDER BY id")],
            "card": dict(c.execute("SELECT * FROM direction_card WHERE category_id=?", (first["category_id"],)).fetchone()),
            "signal1_events": [dict(r) for r in c.execute("SELECT category_id,kind,signal_id FROM discovery_event WHERE signal_id=?", (s1,))],
        }
        undo = categories.undo(c, sp["event_id"])
        after_undo = {
            "undo": undo,
            "categories": [dict(r) for r in c.execute("SELECT id,status,merged_into FROM categories ORDER BY id")],
            "signal1_events": [dict(r) for r in c.execute("SELECT category_id,kind,signal_id FROM discovery_event WHERE signal_id=?", (s1,))],
            "card": dict(c.execute("SELECT * FROM direction_card WHERE category_id=?", (first["category_id"],)).fetchone()),
        }
    finally:
        c.close()
    restored = (after_undo["signal1_events"] and
                all(e["category_id"] == first["category_id"] for e in after_undo["signal1_events"]))
    add("split_undo", "Split undo should restore category/evidence/card relation",
        "undo 后 signal1 事件回到原 category；新 category 不再持有；卡片 evidence 恢复",
        {"before_card": before_card, "split": after_split, "undo": after_undo},
        "PASS" if restored else "FAIL",
        ["tools/selection/categories.py:289-313（split 移动事件，不动卡片 evidence）",
         "tools/selection/categories.py:240-266（undo 只处理 merge/exclude，split 仅追加 undo 事件）"])


# ---------------------------------------------------------------- 6 import bad JSON / budget
def experiment_import():
    src_bad = TMPDIR / "bad.jsonl"
    good = {"href": "https://www.goofish.com/item?id=1001", "title": "t", "price": "¥ 1",
            "raw_text": "学生 学习计划 notion 模板 ¥ 1 .10 5人想要", "platform": "xianyu"}
    bad_line = '{"href": "broken", "title": "bad"'
    src_bad.write_text("\n".join([json.dumps(good, ensure_ascii=False), bad_line,
                                  json.dumps({**good, "href": "https://www.goofish.com/item?id=1002"}, ensure_ascii=False)]) + "\n",
                       encoding="utf-8")
    c = db.init_db(TMPDIR / "import_bad.sqlite3")
    err = None
    try:
        try:
            xianyu.import_file(src_bad, db_path=TMPDIR / "import_bad.sqlite3", max_rows=10)
        except Exception as exc:  # noqa: BLE001
            err = f"{type(exc).__name__}: {exc}"
        nsig = c.execute("SELECT COUNT(*) FROM signals").fetchone()[0]
        run = dict(c.execute("SELECT status,stop_reason FROM runs ORDER BY id DESC LIMIT 1").fetchone())
    finally:
        c.close()
    src_good = TMPDIR / "good.jsonl"
    src_good.write_text("\n".join(json.dumps({**good, "href": f"https://www.goofish.com/item?id={2000+i}"}, ensure_ascii=False) for i in range(3)) + "\n", encoding="utf-8")
    bounded = xianyu.import_file(src_good, db_path=TMPDIR / "import_budget.sqlite3", max_rows=1, max_errors=5)
    actual = {"bad_import_error": err, "bad_signals": nsig, "bad_run": run,
              "max_rows": bounded}
    add("import_bad_json_budget", "Bad JSON should not abort later valid rows; max_rows must bound",
        "坏行记录后继续第三行，status partial，signals=2；max_rows=1 只处理 1 行",
        actual, "FAIL" if (err or nsig != 2 or bounded["rows"] != 1) else "PASS",
        ["tools/selection/xianyu.py:71-83（json.loads 在生成器内、单行 try 外）",
         "tools/selection/xianyu.py:105-133（for 只捕获 _row_to_signal，不能捕获生成器解析异常）"])


# ---------------------------------------------------------------- 7 identity carrier + origin overwrite
def experiment_identity_origin():
    c = db.init_db(TMPDIR / "identity.sqlite3")
    try:
        _, s1 = db.upsert_signal(c, make_signal(40, "学习计划 Notion", "学生 学习计划 notion 模板"))
        _, s2 = db.upsert_signal(c, make_signal(41, "学习计划 Excel", "学生 学习计划 excel 表格", "bilibili"))
        o1 = categories.categorize_signal(c, dict(c.execute("SELECT * FROM signals WHERE id=?", (s1,)).fetchone()))
        o2 = categories.categorize_signal(c, dict(c.execute("SELECT * FROM signals WHERE id=?", (s2,)).fetchone()))
        ncat = c.execute("SELECT COUNT(*) FROM categories").fetchone()[0]
    finally:
        c.close()
    c2 = db.init_db(TMPDIR / "origin.sqlite3")
    try:
        imp = db.upsert_signal(c2, make_signal(50, "导入商品", "学生 学习计划 notion 模板", "xianyu", "imported"))
        same = db.upsert_signal(c2, make_signal(50, "导入商品", "学生 学习计划 notion 模板", "xianyu", "real"))
        changed = db.upsert_signal(c2, make_signal(50, "真实商品更新", "学生 学习计划 notion 模板 新版", "xianyu", "real"))
        row = dict(c2.execute("SELECT origin_kind,version FROM signals WHERE native_id='50'").fetchone())
    finally:
        c2.close()
    actual = {"carrier": {"o1": o1, "o2": o2, "categories": ncat},
              "origin": {"imported": imp, "same_content_real": same,
                         "changed_content_real": changed, "stored": row}}
    add("identity_carrier_origin", "Carrier-only change should not create new category; origin should not silently overwrite",
        "notion→excel 同需求 1 category；同 native_id 的 imported→real 应冲突/保留 provenance",
        actual, "FAIL" if ncat != 1 or row["origin_kind"] != "imported" else "PASS",
        ["tools/selection/categories.py:30-36,58-61（deliverable_family 进 identity）",
         "tools/selection/db.py:45,175-204（platform+native_id 唯一，update 覆盖 origin_kind）"])


# ---------------------------------------------------------------- 8 merge with cards + undo steal
def experiment_merge_cards_undo():
    c = db.init_db(TMPDIR / "merge_cards.sqlite3")
    err = None
    try:
        _, s1 = db.upsert_signal(c, make_signal(60, "学习计划 Notion", "学生 学习计划 notion 模板"))
        _, s2 = db.upsert_signal(c, make_signal(61, "学习计划 Excel", "学生 学习计划 excel 表格"))
        o1 = categories.categorize_signal(c, dict(c.execute("SELECT * FROM signals WHERE id=?", (s1,)).fetchone()))
        o2 = categories.categorize_signal(c, dict(c.execute("SELECT * FROM signals WHERE id=?", (s2,)).fetchone()))
        categories.make_cards(c)
        try:
            categories.merge(c, o1["category_id"], o2["category_id"])
        except Exception as exc:  # noqa: BLE001
            err = f"{type(exc).__name__}: {exc}"
        state = {
            "categories": [dict(r) for r in c.execute("SELECT id,status,merged_into FROM categories ORDER BY id")],
            "cards": [dict(r) for r in c.execute("SELECT category_id FROM direction_card ORDER BY id")],
            "events": c.execute("SELECT COUNT(*) FROM discovery_event").fetchone()[0],
        }
    finally:
        c.close()

    # undo steals target's own event (no cards involved)
    m = db.init_db(TMPDIR / "merge_undo.sqlite3")
    try:
        _, a = db.upsert_signal(m, make_signal(70, "学习计划 Notion", "学生 学习计划 notion 模板"))
        _, b = db.upsert_signal(m, make_signal(71, "学习计划 Excel", "学生 学习计划 excel 表格"))
        ca = categories.categorize_signal(m, dict(m.execute("SELECT * FROM signals WHERE id=?", (a,)).fetchone()))
        cb = categories.categorize_signal(m, dict(m.execute("SELECT * FROM signals WHERE id=?", (b,)).fetchone()))
        before_target_events = m.execute("SELECT COUNT(*) FROM discovery_event WHERE category_id=?", (cb["category_id"],)).fetchone()[0]
        mm = categories.merge(m, ca["category_id"], cb["category_id"])
        after_merge_target_events = m.execute("SELECT COUNT(*) FROM discovery_event WHERE category_id=?", (cb["category_id"],)).fetchone()[0]
        categories.undo(m, mm["event_id"])
        after_undo = {
            "source_events": m.execute("SELECT COUNT(*) FROM discovery_event WHERE category_id=?", (ca["category_id"],)).fetchone()[0],
            "target_events": m.execute("SELECT COUNT(*) FROM discovery_event WHERE category_id=?", (cb["category_id"],)).fetchone()[0],
            "categories": [dict(r) for r in m.execute("SELECT id,status,merged_into FROM categories ORDER BY id")],
        }
    finally:
        m.close()
    actual = {"merge_with_cards_error": err, "merge_with_cards_state": state,
              "undo_before_target_events": before_target_events,
              "undo_after_merge_target_events": after_merge_target_events,
              "undo_after": after_undo}
    bad = bool(err) or after_undo["target_events"] == 0
    add("merge_cards_undo", "Merge with existing cards must be atomic; undo must restore only source relation",
        "两个 category 都有 card 时 merge 不崩溃且可 undo；undo 不搬走 target 原有事件",
        actual, "FAIL" if bad else "PASS",
        ["tools/selection/db.py:93-103（direction_card.category_id UNIQUE）",
         "tools/selection/categories.py:224-237（merge 无 transaction/rollback）",
         "tools/selection/categories.py:245-258（undo 把 target 全部事件/卡片迁回 source）"])


# ---------------------------------------------------------------- 9 cancel/interval/idempotency
def experiment_round_edges():
    sel = TMPDIR / "edges.sqlite3"
    c = db.init_db(sel)
    r = rounds.start(c, kind="bilibili", platform="bilibili",
                     budget={"max_requests": 3}, idempotency_key="edge-cancel")
    rounds.transition(c, r["id"], "running")
    rounds.add_item(c, r["id"], "bilibili:view")
    rounds.add_item(c, r["id"], "bilibili:reply")
    c.close()
    fake = FakeFetch(cancel_round_id=r["id"], db_path=sel)
    err = None
    try:
        out = bilibili.collect_round(db_path=sel, round_id=r["id"], raw_dir=TMPDIR / "raw_cancel",
                                     aid=1, budget=3, interval=0, fetch=fake)
    except Exception as exc:  # noqa: BLE001
        err = f"{type(exc).__name__}: {exc}"
        out = {}
    c = db.init_db(sel)
    try:
        st = dict(c.execute("SELECT status FROM rounds WHERE id=?", (r["id"],)).fetchone())
        items = [dict(x) for x in c.execute("SELECT item_key,state FROM round_item WHERE round_id=? ORDER BY id", (r["id"],))]
        nsig = c.execute("SELECT COUNT(*) FROM signals").fetchone()[0]
    finally:
        c.close()

    # interval ignored: direct measure
    sel2 = TMPDIR / "interval.sqlite3"
    c = db.init_db(sel2)
    r2 = rounds.start(c, kind="bilibili", platform="bilibili",
                      budget={"max_requests": 3}, idempotency_key="edge-interval")
    rounds.transition(c, r2["id"], "running")
    c.close()
    fake2 = FakeFetch()
    t0 = time.monotonic()
    out2 = bilibili.collect_round(db_path=sel2, round_id=r2["id"], raw_dir=TMPDIR / "raw_interval",
                                  aid=1, budget=3, interval=3.0, fetch=fake2)
    elapsed = time.monotonic() - t0

    # idempotency key reused with different budget
    c = db.init_db(TMPDIR / "idem.sqlite3")
    try:
        a = rounds.start(c, kind="bilibili", platform="bilibili", budget={"max_requests": 3},
                         idempotency_key="same-key")
        b = rounds.start(c, kind="bilibili", platform="bilibili", budget={"max_requests": 5},
                         idempotency_key="same-key")
        idem = {"first": a, "second": b}
    finally:
        c.close()
    actual = {"cancel": {"exception": err, "result": out, "round_status": st["status"],
                          "items": items, "signals": nsig, "fetch_calls": len(fake.calls)},
              "interval": {"elapsed_seconds": round(elapsed, 3), "status": out2.get("status"),
                           "fetch_calls": len(fake2.calls)},
              "idempotency": idem}
    add("round_edges", "Cancel must stop loop; interval must sleep; idempotency key must detect conflict",
        "cancel 后不再发 reply；interval=3 至少间隔约 3s；同 key 不同 budget/video 应报冲突",
        actual,
        "FAIL" if (st["status"] == "cancelled" and len(fake.calls) > 1) or elapsed < 1.0 or idem["second"]["reused"] else "PASS",
        ["tools/selection/bilibili.py:284-372（循环只查 paused；无 interval sleep）",
         "tools/selection/rounds.py:44-56（start 仅按 key 复用，不校验参数）"])


# Run all
for fn in (experiment_ui_start, experiment_ui_resume, experiment_repeat_cards,
           experiment_attribution, experiment_split_undo, experiment_import,
           experiment_identity_origin, experiment_merge_cards_undo, experiment_round_edges):
    try:
        fn()
    except Exception as exc:  # noqa: BLE001
        import traceback
        traceback.print_exc()
        add(fn.__name__, fn.__doc__ or fn.__name__, "experiment should complete",
            f"{type(exc).__name__}: {exc}", "ERROR", [])
        print(f"ERROR {fn.__name__}: {exc}")

RESULTS["hashes_after"] = hashes()
RESULTS["hash_same"] = {k: RESULTS["hashes_before"].get(k) == RESULTS["hashes_after"].get(k)
                        for k in RESULTS["hashes_before"]}
SUMMARY = {
    "verdicts": {e["id"]: e["verdict"] for e in RESULTS["experiments"]},
    "fail_count": sum(1 for e in RESULTS["experiments"] if e["verdict"] == "FAIL"),
    "pass_count": sum(1 for e in RESULTS["experiments"] if e["verdict"] == "PASS"),
    "error_count": sum(1 for e in RESULTS["experiments"] if e["verdict"] == "ERROR"),
    "all_hashes_same": all(RESULTS["hash_same"].values()),
}
RESULTS["summary"] = SUMMARY
(HERE / "audit_results.json").write_text(json.dumps(RESULTS, ensure_ascii=False, indent=1),
                                         encoding="utf-8", newline="\n")
print(json.dumps(SUMMARY, ensure_ascii=False, indent=1))
TMP.cleanup()
