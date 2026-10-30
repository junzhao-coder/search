"""桌面版卡片提取的离线端到端检查：本地 fixture + 真实 Chrome（local 模式、封网）。

覆盖：`div.card-wrap[mid]`、两段 `p.txt`、`a.name`、`div.from`、`div.card-act` 的互动数字、
无 mid 时回退 `//weibo.com/<uid>/<bid>`（`id_source=bid`）、隐藏卡片、跨域卡片、无 id 卡片。

用法：
    C:\\Users\\19183\\.dsh\\tools\\x-collect\\venv\\Scripts\\python.exe -X utf8 `
      docs\\validation\\v10\\weibo-rpa-live\\checks\\desktop_extract_check.py
产物：`logs/desktop-extract-check.json`；失败非零。
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

HERE = pathlib.Path(__file__).resolve().parents[1]
FIXTURE = HERE / "checks" / "fixtures" / "desktop-cards.html"
OUT = HERE / "logs" / "desktop-extract-check.json"
NAV_MARKERS = ("首页", "登录")


def main() -> int:
    if not FIXTURE.is_file():
        print(json.dumps({"error": "fixture_missing", "path": str(FIXTURE)}))
        return 2
    checks: list[dict] = []

    def record(name: str, passed: bool, detail="") -> None:
        checks.append({"check": name, "pass": bool(passed), "detail": detail})

    profile = pathlib.Path(tempfile.mkdtemp(prefix="rpa-desktop-extract-"))
    sess = session.VisibleSession(profile, live=False)
    try:
        sess.start()
        tab, _blocked = sess.open_local(FIXTURE.as_uri())
        dumped = sess.dump_desktop_cards(tab)
    finally:
        sess.close()

    cards = dumped.get("cards") or []
    record("cards_dumped", len(cards) == 4,
           json.dumps([{k: c.get(k) for k in ("id", "id_source")} for c in cards],
                      ensure_ascii=False))
    parsed = extract.extract_cards(cards, collected_at=dt.datetime.now(
        dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), limit=5)
    records = parsed["records"]
    details = parsed.get("details") or []
    rejected = parsed.get("diagnostics", {}).get("rejected") or {}
    by_id = {r["native_id"]: r for r in records}
    detail_by_id = {d["native_id"]: d for d in details}

    record("two_records_kept", len(records) == 2,
           json.dumps(sorted(by_id), ensure_ascii=False))
    record("foreign_rejected", rejected.get("foreign_host") == 1, json.dumps(rejected))
    record("no_id_rejected", rejected.get("bad_id") == 1, json.dumps(rejected))
    record("hidden_card_not_dumped",
           all(c.get("id") != "4900000000000203" for c in cards),
           json.dumps([c.get("id") for c in cards], ensure_ascii=False))

    first = by_id.get("4900000000000201")
    record("mid_id_source", bool(first) and detail_by_id.get("4900000000000201", {}).get(
        "id_source") == "mid", str(detail_by_id.get("4900000000000201")))
    record("p_txt_joined", bool(first) and first["text"] == "第一段正文-甲 第二段正文-甲",
           (first or {}).get("text") or "")
    record("author_from_name", detail_by_id.get("4900000000000201", {}).get("author") == "作者甲",
           str(detail_by_id.get("4900000000000201", {}).get("author")))
    record("time_from_div_from",
           bool(first) and (first.get("published_at") or "").startswith("3小时前"),
           str((first or {}).get("published_at")))
    record("counts_from_card_act",
           detail_by_id.get("4900000000000201", {}).get("reposts") == 12
           and first is not None and first["comments"] == 3 and first["likes"] == 45,
           json.dumps(detail_by_id.get("4900000000000201", {}), ensure_ascii=False))
    bid_card = by_id.get("Ndef202")
    record("bid_fallback", bool(bid_card) and detail_by_id.get("Ndef202", {}).get(
        "id_source") == "bid", str(detail_by_id.get("Ndef202")))
    record("bid_url_https", bool(bid_card) and (bid_card.get("url") or "").startswith("https://"),
           (bid_card or {}).get("url") or "")
    text_all = " ".join((r.get("text") or "") for r in records)
    record("no_nav_text", all(marker not in text_all for marker in NAV_MARKERS), text_all)
    record("no_hidden_text", "隐藏卡片正文-不该出现" not in text_all, text_all)

    all_pass = all(c["pass"] for c in checks)
    payload = {"generated_utc": dt.datetime.now(dt.timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ"), "all_pass": all_pass, "checks": checks,
        "cards": cards, "records": records, "details": details,
        "rejected": rejected}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({"all_pass": all_pass, "failed": [c for c in checks if not c["pass"]],
                      "records": len(records), "rejected": rejected,
                      "ids": sorted(by_id), "out": str(OUT)}, ensure_ascii=False))
    return 0 if all_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
