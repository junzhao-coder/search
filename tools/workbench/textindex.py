"""全文索引（只读）：为每条机会取“最长的可用文本”，供用途判定使用。

来源优先级（同一 item_id 取最长文本）：
  1) `scoring/items.jsonl` 的 `raw_summary`（60/60 行都有，含 B 站简介 / GitHub 描述 / X 正文）
  2) `scoring/raw/x_search.jsonl` 的 `text`（按 tweet_id）
  3) `scoring/raw/bilibili_search.json` 的 `description`/`desc`（按 bvid）
  4) `scoring/raw/github_search.json` 的 `description` + `topics`（按 full_name）
"""

from __future__ import annotations

import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[2]
MP = ROOT / "docs" / "validation" / "money-project"
RAW = MP / "scoring" / "raw"


def _read_jsonl(path: pathlib.Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _read_json(path: pathlib.Path):
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def build_text_index() -> dict[str, dict]:
    """返回 {item_id: {"text": str, "source": str}}。"""
    best: dict[str, dict] = {}

    def offer(item_id: str, text: str, source: str) -> None:
        text = (text or "").strip()
        if not item_id or not text:
            return
        current = best.get(item_id)
        if current is None or len(text) > len(current["text"]):
            best[item_id] = {"text": text, "source": source}

    for row in _read_jsonl(MP / "scoring" / "items.jsonl"):
        offer(str(row.get("item_id") or ""), str(row.get("raw_summary") or ""), "items.raw_summary")

    for row in _read_jsonl(RAW / "x_search.jsonl"):
        offer(f"x:{row.get('tweet_id')}", str(row.get("text") or ""), "raw.x_search.text")

    bili = _read_json(RAW / "bilibili_search.json")
    if isinstance(bili, dict):
        records = ((bili.get("data") or {}).get("result") or []) if isinstance(bili.get("data"), dict) else []
        for rec in records:
            if not isinstance(rec, dict):
                continue
            text = " ".join(str(rec.get(k) or "") for k in ("title", "description", "desc"))
            offer(f"bili:{rec.get('bvid')}", text, "raw.bilibili.description")

    gh = _read_json(RAW / "github_search.json")
    records = gh if isinstance(gh, list) else (gh or {}).get("items") or []
    for rec in records:
        if not isinstance(rec, dict):
            continue
        topics = " ".join(rec.get("topics") or []) if isinstance(rec.get("topics"), list) else ""
        text = " ".join(str(rec.get(k) or "") for k in ("full_name", "description", "name")) + " " + topics
        offer(f"gh:{rec.get('full_name')}", text, "raw.github.description")

    return best


def text_for(item_id: str, index: dict[str, dict] | None = None) -> tuple[str, str]:
    entry = (index or {}).get(str(item_id)) or {}
    return str(entry.get("text") or ""), str(entry.get("source") or "")
