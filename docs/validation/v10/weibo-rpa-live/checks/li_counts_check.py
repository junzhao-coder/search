"""互动字段（ul>li 位置解析）六类 fixture 的真实浏览器检查（local 模式、封网）。

- a：三项都有非零数字（`转发 12 / 评论 3 / 赞 45`）
- b：全 0（三个 li 只有标签）
- c：只有赞非零（`转发 / 评论 / 1`，模拟真实页）
- d：items 只有 2 个（likes 缺失 → null + missing）
- e：带单位（`1.2万` → 12000，unit=万）
- f：一个 li 含多个数字（`转发 12 13` → ambiguous，不猜，null）

用法：
    C:\\Users\\19183\\.dsh\\tools\\x-collect\\venv\\Scripts\\python.exe -X utf8 `
      docs\\validation\\v10\\weibo-rpa-live\\checks\\li_counts_check.py
产物：`logs/li-counts-check.json`；失败非零。
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
FIX = HERE / "checks" / "fixtures"
OUT = HERE / "logs" / "li-counts-check.json"

EXPECT = {
    "li-a.html": {"r": 12, "c": 3, "l": 45,
                  "src": {"reposts": "position", "comments": "position", "likes": "position"},
                  "unit": {}, "missing": []},
    "li-b.html": {"r": 0, "c": 0, "l": 0,
                  "src": {"reposts": "position", "comments": "position", "likes": "position"},
                  "unit": {}, "missing": []},
    "li-c.html": {"r": 0, "c": 0, "l": 1,
                  "src": {"reposts": "position", "comments": "position", "likes": "position"},
                  "unit": {}, "missing": []},
    "li-d.html": {"r": 7, "c": 2, "l": None,
                  "src": {"reposts": "position", "comments": "position", "likes": "absent"},
                  "unit": {}, "missing": ["likes"]},
    "li-e.html": {"r": 12000, "c": 0, "l": 0,
                  "src": {"reposts": "position", "comments": "position", "likes": "position"},
                  "unit": {"reposts": "万"}, "missing": []},
    "li-f.html": {"r": None, "c": 0, "l": 0,
                  "src": {"reposts": "ambiguous", "comments": "position", "likes": "position"},
                  "unit": {}, "missing": ["reposts"]},
}


def main() -> int:
    checks: list[dict] = []

    def record(name: str, passed: bool, detail="") -> None:
        checks.append({"check": name, "pass": bool(passed), "detail": detail})

    profile = pathlib.Path(tempfile.mkdtemp(prefix="rpa-li-counts-"))
    sess = session.VisibleSession(profile, live=False)
    observed: dict[str, dict] = {}
    try:
        sess.start()
        for name, want in EXPECT.items():
            path = FIX / name
            if not path.is_file():
                record(f"{name}:fixture", False, str(path))
                continue
            tab, _blocked = sess.open_local(path.as_uri())
            dumped = sess.dump_desktop_cards(tab)
            parsed = extract.extract_cards(dumped.get("cards") or [],
                                           collected_at=dt.datetime.now(
                                               dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                                           limit=5)
            details = parsed.get("details") or []
            got = details[0] if details else {}
            observed[name] = {"cards": dumped.get("cards"), "details": details,
                              "rejected": parsed.get("diagnostics", {}).get("rejected")}
            record(f"{name}:one_record", len(details) == 1,
                   json.dumps(parsed.get("diagnostics", {}).get("rejected") or {}))
            for field, key in (("reposts", "r"), ("comments", "c"), ("likes", "l")):
                record(f"{name}:{field}", got.get(field) == want[key],
                       f"got={got.get(field)} want={want[key]}")
            for field, want_src in want["src"].items():
                got_src = (got.get("count_source") or {}).get(field)
                record(f"{name}:{field}:source", got_src == want_src,
                       f"got={got_src} want={want_src}")
            for field, want_unit in want["unit"].items():
                got_unit = (got.get("count_unit") or {}).get(field)
                record(f"{name}:{field}:unit", got_unit == want_unit,
                       f"got={got_unit} want={want_unit}")
            got_missing = [m for m in (got.get("missing") or [])
                           if m in ("reposts", "comments", "likes")]
            record(f"{name}:missing", sorted(got_missing) == sorted(want["missing"]),
                   f"got={got_missing} want={want['missing']}")
    finally:
        sess.close()

    all_pass = all(c["pass"] for c in checks)
    payload = {"generated_utc": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
               "all_pass": all_pass, "checks": checks, "observed": observed}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    summary = {name: {k: (obs["details"][0].get(k) if obs["details"] else None)
                      for k in ("reposts", "comments", "likes", "count_source",
                                "count_unit", "missing")}
               for name, obs in observed.items()}
    print(json.dumps({"all_pass": all_pass,
                      "failed": [c for c in checks if not c["pass"]],
                      "observed": summary, "out": str(OUT)}, ensure_ascii=False))
    return 0 if all_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
