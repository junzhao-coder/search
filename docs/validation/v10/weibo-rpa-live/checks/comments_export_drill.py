"""评论导出演练：用已落盘的 `comments-rpa21.jsonl`（5 行真实数据）跑一次映射 + 导出。

不触网、不入库、不改任何业务数据；只读日志、写 `logs/comments-export-rpa21.jsonl`。

用法：
    C:\\Users\\19183\\.dsh\\tools\\x-collect\\venv\\Scripts\\python.exe -X utf8 `
      docs\\validation\\v10\\weibo-rpa-live\\checks\\comments_export_drill.py
"""

from __future__ import annotations

import datetime as dt
import json
import pathlib
import sys

REPO = pathlib.Path(__file__).resolve().parents[5]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from tools.selection.access import records as rec  # noqa: E402
from tools.selection.rpa import comments as comments_mod  # noqa: E402

HERE = pathlib.Path(__file__).resolve().parents[1]
SRC = HERE / "logs" / "comments-rpa21.jsonl"
OUT = HERE / "logs" / "comments-export-rpa21.jsonl"
POST_URL = "https://weibo.com/5518250456/RkocskwA6"
COLLECTED = "2026-10-30T08:03:11Z"


def main() -> int:
    if not SRC.is_file():
        print(json.dumps({"error": "source_missing", "path": str(SRC)}, ensure_ascii=False))
        return 2
    raw = [json.loads(line) for line in SRC.read_text(encoding="utf-8").splitlines() if line.strip()]
    mapped = comments_mod.to_records(raw, post_url=POST_URL, collected_at=COLLECTED)
    written = rec.write_records(mapped, OUT)
    out_rows = [json.loads(line) for line in
                pathlib.Path(written).read_text(encoding="utf-8").splitlines() if line.strip()]
    ids = {r["native_id"] for r in out_rows}
    pairs = []
    for row in out_rows:
        if row["parent_id"] is None:
            pairs.append({"child": row["native_id"], "parent": None,
                          "resolved": True, "root": row.get("root_comment_id")})
        else:
            pairs.append({"child": row["native_id"], "parent": row["parent_id"],
                          "resolved": row["parent_id"] in ids,
                          "root": row.get("root_comment_id")})
    columns_ok = all(set(r) - {"missing", "not_applicable", "supported",
                              "author_redacted", "field_evidence", "source"} == set(rec.FIELDS)
                     for r in out_rows)
    top_level_missing_clean = all(
        "parent_id" not in r["missing"] and "parent_id" in r["not_applicable"]
        for r in out_rows if r["parent_id"] is None)
    zero_likes_ok = all(("likes" not in r["missing"]) for r in out_rows
                        if r["likes"] == 0)
    payload = {
        "generated_utc": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": str(SRC), "output": written, "rows": len(out_rows),
        "columns": list(rec.FIELDS), "columns_consistent": columns_ok,
        "pairs": pairs, "all_parents_resolved": all(p["resolved"] for p in pairs),
        "zero_likes_not_missing": zero_likes_ok,
        "top_level_missing_clean": top_level_missing_clean,
        "sample": [{k: r.get(k) for k in ("native_id", "type", "parent_id",
                                          "root_comment_id", "author", "likes",
                                          "published_at", "url", "missing")}
                   for r in out_rows],
    }
    (HERE / "logs" / "comments-export-rpa21.check.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({k: payload[k] for k in ("rows", "columns_consistent",
                                              "all_parents_resolved",
                                              "zero_likes_not_missing",
                                              "top_level_missing_clean", "output")},
                     ensure_ascii=False))
    ok = (columns_ok and payload["all_parents_resolved"] and zero_likes_ok
          and top_level_missing_clean)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
