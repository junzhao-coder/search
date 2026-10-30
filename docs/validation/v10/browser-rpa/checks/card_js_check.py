"""真实本地浏览器跑 CARD_JS 的行为检查（隔离临时 profile，不触网、不碰真实 profile）。

覆盖退回意见要求的场景：卡内隐藏文字、卡内导航、作者链接、控制文字「全文」、
外域链接卡、嵌套不同 ID 卡、以及 ID 与路径不一致的可能性；核对最终输出。

用法（必须用带 nodriver 的解释器）：
    C:\\Users\\19183\\.dsh\\tools\\x-collect\\venv\\Scripts\\python.exe -X utf8 `
      docs\\validation\\v10\\browser-rpa\\checks\\card_js_check.py
输出：`docs/validation/v10/browser-rpa/logs/card-js-check.json`，失败退出码非零。
"""

from __future__ import annotations

import datetime as dt
import json
import pathlib
import sys
import tempfile

REPO = pathlib.Path(__file__).resolve().parents[5]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from tools.selection.rpa import extract, session  # noqa: E402

HERE = REPO / "docs" / "validation" / "v10" / "browser-rpa"
FIXTURE = HERE / "fixtures" / "card-cases.html"
OUT = HERE / "logs" / "card-js-check.json"

HIDDEN_MARKERS = ("隐藏正文不该出现", "不可见文字不该出现", "整张卡隐藏不该出现")
NAV_MARKERS = ("站点首页", "站点热搜", "首页", "热搜")
AUTHOR_MARKERS = ("作者昵称不该出现",)
CONTROL_MARKERS = ("全文", "展开全文")
INNER_MARKERS = ("内层卡片正文不该串入外层",)


def _fail(checks, name, detail=""):
    checks.append({"check": name, "pass": False, "detail": detail})


def _ok(checks, name, detail=""):
    checks.append({"check": name, "pass": True, "detail": detail})


def main() -> int:
    if not FIXTURE.is_file():
        print(json.dumps({"error": "fixture_missing", "path": str(FIXTURE)}))
        return 2
    checks: list[dict] = []
    profile = pathlib.Path(tempfile.mkdtemp(prefix="rpa-cardjs-"))
    sess = session.VisibleSession(profile)
    try:
        sess.start()
        tab, blocked = sess.open_local(FIXTURE.as_uri())
        nav = sess.navigate_stable(tab)
        audit = sess.audit_network(tab)
        dumped = sess.dump_cards(tab)
    finally:
        sess.close()
    cards = dumped.get("cards") or []
    by_id = {str(c.get("id")): c for c in cards}

    if nav.get("escaped") or nav.get("timed_out"):
        _fail(checks, "navigation_stable", json.dumps(nav, ensure_ascii=False))
    else:
        _ok(checks, "navigation_stable", nav.get("ready_state") or "")

    if audit.get("external_completed"):
        _fail(checks, "no_external_completion", json.dumps(audit, ensure_ascii=False))
    else:
        _ok(checks, "no_external_completion",
            f"attempts={audit.get('external_attempts')} completed=0")

    expected_ids = {"4900000000000101", "4900000000000102",
                    "4900000000000103", "4900000000000105"}
    if set(by_id) != expected_ids:
        _fail(checks, "card_set", f"got={sorted(by_id)} want={sorted(expected_ids)}")
    else:
        _ok(checks, "card_set", ",".join(sorted(by_id)))

    if "4900000000000104" in by_id or "4900000000000107" in by_id:
        _fail(checks, "nested_and_hidden_cards_not_emitted", f"got={sorted(by_id)}")
    else:
        _ok(checks, "nested_and_hidden_cards_not_emitted", "inner/hidden cards skipped")

    for native_id, card in by_id.items():
        path_id = (card.get("url") or "").rstrip("/").rsplit("/", 1)[-1]
        if path_id != native_id:
            _fail(checks, f"id_matches_url[{native_id}]", card.get("url") or "")
    text_a = (by_id.get("4900000000000101") or {}).get("text") or ""
    text_c = (by_id.get("4900000000000103") or {}).get("text") or ""

    for marker in HIDDEN_MARKERS:
        (_fail(checks, f"hidden_text_absent[{marker}]", text_a + text_c)
         if marker in text_a or marker in text_c
         else _ok(checks, f"hidden_text_absent[{marker}]"))
    for marker in NAV_MARKERS + AUTHOR_MARKERS + CONTROL_MARKERS:
        (_fail(checks, f"ui_text_absent[{marker}]", text_a)
         if marker in text_a else _ok(checks, f"ui_text_absent[{marker}]"))
    for marker in INNER_MARKERS:
        (_fail(checks, f"nested_text_absent[{marker}]", text_c)
         if marker in text_c else _ok(checks, f"nested_text_absent[{marker}]"))
    if "卡片A可见正文" in text_a:
        _ok(checks, "outer_text_present[card-a]")
    else:
        _fail(checks, "outer_text_present[card-a]", text_a)
    if "卡片C外层正文" in text_c:
        _ok(checks, "outer_text_present[card-c]")
    else:
        _fail(checks, "outer_text_present[card-c]", text_c)

    counts_c = (by_id.get("4900000000000103") or {}).get("counts") or {}
    if counts_c.get("comments") == 7 and counts_c.get("likes") == 8:
        _ok(checks, "counts_from_own_toolbar[card-c]", json.dumps(counts_c))
    else:
        _fail(checks, "counts_from_own_toolbar[card-c]", json.dumps(counts_c))

    parsed = extract.extract_cards(cards, collected_at=dt.datetime.now(
        dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))
    rejected = parsed["diagnostics"]["rejected"]
    if rejected.get("foreign_host") != 1:
        _fail(checks, "foreign_card_rejected", json.dumps(rejected))
    else:
        _ok(checks, "foreign_card_rejected", json.dumps(rejected))
    if len(parsed["records"]) != 3:
        _fail(checks, "three_records_kept", str(len(parsed["records"])))
    else:
        _ok(checks, "three_records_kept", ",".join(r["native_id"] for r in parsed["records"]))

    all_pass = all(c["pass"] for c in checks)
    payload = {"generated_utc": dt.datetime.now(dt.timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ"), "all_pass": all_pass, "checks": checks,
        "navigation": nav, "network_audit": audit,
        "cards": cards, "extract": {"records": len(parsed["records"]),
                                    "rejected": rejected}}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({"all_pass": all_pass, "failed": [c for c in checks if not c["pass"]],
                      "cards": len(cards), "records": len(parsed["records"]),
                      "rejected": rejected, "out": str(OUT)}, ensure_ascii=False))
    return 0 if all_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
