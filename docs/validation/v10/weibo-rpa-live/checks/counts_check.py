"""互动字段（转发/评论/赞）四类 fixture 的真实浏览器检查（local 模式、封网）。

覆盖验收四类：
- a：三值齐全且含一个真实 0（`12 / 0 / 1.2万` → 12 / 0 / 12000，unit=万，source=position）
- b：只渲染 1–2 个（`5` + `评论 7` → reposts=5 position、comments=7 type、likes=null）
- c：三个全为 0（`0 / 0 / 0` → 0/0/0，全部 position，不能变成 null）
- d：完全未渲染（没有 `div.card-act` → 三值 null，source=absent，missing 含三项）

用法：
    C:\\Users\\19183\\.dsh\\tools\\x-collect\\venv\\Scripts\\python.exe -X utf8 `
      docs\\validation\\v10\\weibo-rpa-live\\checks\\counts_check.py
产物：`logs/counts-check.json`；失败非零。
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
OUT = HERE / "logs" / "counts-check.json"

EXPECT = {
    "counts-a.html": {"mid": "4900000000000301", "reposts": 12, "comments": 0, "likes": 12000,
                      "source": {"reposts": "position", "comments": "position",
                                 "likes": "position"},
                      "unit": {"likes": "万"}, "missing": []},
    "counts-b.html": {"mid": "4900000000000302", "reposts": 5, "comments": 7, "likes": None,
                      "source": {"reposts": "position", "comments": "position",
                                 "likes": "absent"},
                      "unit": {}, "missing": ["likes"]},
    "counts-c.html": {"mid": "4900000000000303", "reposts": 0, "comments": 0, "likes": 0,
                      "source": {"reposts": "position", "comments": "position",
                                 "likes": "position"},
                      "unit": {}, "missing": []},
    "counts-d.html": {"mid": "4900000000000304", "reposts": None, "comments": None,
                      "likes": None,
                      "source": {"reposts": "absent", "comments": "absent",
                                 "likes": "absent"},
                      "unit": {}, "missing": ["reposts", "comments", "likes"]},
}


def main() -> int:
    checks: list[dict] = []

    def record(name: str, passed: bool, detail="") -> None:
        checks.append({"check": name, "pass": bool(passed), "detail": detail})

    profile = pathlib.Path(tempfile.mkdtemp(prefix="rpa-counts-"))
    sess = session.VisibleSession(profile, live=False)
    observed: dict[str, dict] = {}
    try:
        sess.start()
        for name, want in EXPECT.items():
            path = FIX / name
            if not path.is_file():
                record(f"{name}:fixture_exists", False, str(path))
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
            for field in ("reposts", "comments", "likes"):
                record(f"{name}:{field}", got.get(field) == want[field],
                       f"got={got.get(field)} want={want[field]}")
            for field, want_src in want["source"].items():
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
