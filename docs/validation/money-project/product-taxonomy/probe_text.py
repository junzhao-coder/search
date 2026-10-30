"""只读探查：全文可用性与用途词命中（不改任何数据）。"""

from __future__ import annotations

import csv
import json
import pathlib
import re

ROOT = pathlib.Path(r"D:\桌面\two")
MP = ROOT / "docs" / "validation" / "money-project"
RAW = MP / "scoring" / "raw"

WORDS = {
    "求职": ["job", "apply", "interview", "lamaran", "hiring", "resume", "cv"],
    "学习": ["class", "student", "study", "lecture", "notes", "exam", "school"],
    "内容创作": ["content", "creator", "post", "edit", "social", "newsletter"],
    "生活": ["budget", "finance", "expense", "meal", "workout", "habit", "goal", "travel"],
    "设计": ["design", "portfolio", "ui", "moodboard"],
    "赠送引流": ["giveaway", "free", "赠送"],
}

out = {}
scores = list(csv.DictReader((MP / "scoring" / "scores.csv").open(encoding="utf-8-sig", newline="")))
out["scores_rows"] = len(scores)
out["by_platform"] = {}
for r in scores:
    out["by_platform"][r["platform"]] = out["by_platform"].get(r["platform"], 0) + 1

# x 全文
x = [json.loads(l) for l in (RAW / "x_search.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
out["x_rows"] = len(x)
out["x_keys"] = sorted(x[0].keys())
xmap = {str(d.get("tweet_id")): (d.get("text") or "") for d in x}

# bilibili / github
for name in ("bilibili_search.json", "github_search.json"):
    p = RAW / name
    if not p.exists():
        out[name] = "missing"
        continue
    data = json.loads(p.read_text(encoding="utf-8"))
    records = data if isinstance(data, list) else data.get("items") or data.get("results") or []
    out[name] = {"records": len(records), "keys": sorted(records[0].keys()) if records else []}

notion_rows = [r for r in scores if "notion" in (r.get("title") or "").lower()]
out["notion_rows"] = len(notion_rows)
covered = 0
hits_by_use = {k: 0 for k in WORDS}
samples = []
for r in notion_rows:
    tid = r["item_id"].split(":", 1)[1]
    text = xmap.get(tid, "")
    if text.strip():
        covered += 1
    body = ((r.get("title") or "") + " " + text).lower()
    hit_use = None
    for use, words in WORDS.items():
        found = [w for w in words if re.search(rf"\b{re.escape(w)}\b", body) or w in body]
        if found:
            hit_use = (use, found)
            break
    if hit_use:
        hits_by_use[hit_use[0]] += 1
    elif len(samples) < 5:
        samples.append({"id": r["item_id"], "title": (r.get("title") or "")[:60], "text_len": len(text),
                        "text_head": text[:120].replace("\n", " ")})
out["notion_with_text"] = covered
out["notion_use_hits"] = hits_by_use
out["notion_unmatched"] = len(notion_rows) - sum(hits_by_use.values())
out["unmatched_samples"] = samples
print(json.dumps(out, ensure_ascii=False, indent=1))
