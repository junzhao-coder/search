"""只读探查 2：items.jsonl 与 bilibili/github 原始结构、平台样本键。"""

from __future__ import annotations

import json
import pathlib

ROOT = pathlib.Path(r"D:\桌面\two")
MP = ROOT / "docs" / "validation" / "money-project"
RAW = MP / "scoring" / "raw"
out = {}

items_path = MP / "scoring" / "items.jsonl"
if items_path.exists():
    items = [json.loads(l) for l in items_path.read_text(encoding="utf-8").splitlines() if l.strip()]
    out["items_rows"] = len(items)
    out["items_keys"] = sorted(items[0].keys())
    out["items_sample"] = {k: str(items[0][k])[:80] for k in list(items[0])[:14]}
    text_fields = [k for k in items[0] if any(t in k.lower() for t in ("text", "desc", "title", "summary", "body", "content"))]
    out["items_text_like_fields"] = text_fields
    notion = [i for i in items if "notion" in str(i.get("title", "")).lower()]
    out["items_notion_rows"] = len(notion)
    if text_fields:
        covered = sum(1 for i in notion if any(str(i.get(f) or "").strip() for f in text_fields if f != "title"))
        out["items_notion_with_extra_text"] = covered

p = RAW / "bilibili_search.json"
if p.exists():
    data = json.loads(p.read_text(encoding="utf-8"))
    out["bili_type"] = type(data).__name__
    if isinstance(data, dict):
        out["bili_top_keys"] = list(data)[:12]
        for key in ("data", "items", "results", "list"):
            if key in data and isinstance(data[key], (list, dict)):
                node = data[key]
                out["bili_node_type"] = type(node).__name__
                if isinstance(node, list) and node:
                    out["bili_record_keys"] = sorted(node[0].keys())[:30]
                    out["bili_records"] = len(node)
                elif isinstance(node, dict):
                    out["bili_node_keys"] = list(node)[:12]
                    inner = node.get("result") or node.get("list") or []
                    if isinstance(inner, list) and inner:
                        out["bili_record_keys"] = sorted(inner[0].keys())[:30]
                        out["bili_records"] = len(inner)

for name in ("xianyu_items.jsonl", "xiaohongshu_items.jsonl"):
    q = ROOT / "tools" / "platform-login" / "data" / name
    if q.exists():
        rows = [json.loads(l) for l in q.read_text(encoding="utf-8").splitlines() if l.strip()]
        out[name] = {"rows": len(rows), "keys": sorted(rows[0].keys())}

print(json.dumps(out, ensure_ascii=False, indent=1))
