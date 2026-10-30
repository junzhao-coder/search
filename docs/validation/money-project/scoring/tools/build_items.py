#!/usr/bin/env python
"""Build unified items.jsonl from X, Bilibili and GitHub raw JSON."""

from __future__ import annotations

import datetime
import html
import json
import pathlib
import re

BASE = pathlib.Path(__file__).resolve().parents[1]
RAW = BASE / "raw"
X_RAW = RAW / "x_search.jsonl"
BILI_RAW = RAW / "bilibili_search.json"
GITHUB_RAW = RAW / "github_search.json"
OUT = BASE / "items.jsonl"
TAG = re.compile(r"<[^>]+>")


def clean(text: str) -> str:
    return html.unescape(TAG.sub("", text or "")).strip()


def iso_from_epoch(value) -> str | None:
    try:
        return datetime.datetime.fromtimestamp(int(value), datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    except Exception:  # noqa: BLE001
        return None


def snippet(text: str, n: int = 120) -> str:
    return re.sub(r"\s+", " ", clean(text))[:n]


def x_items() -> list[dict]:
    rows = [json.loads(line) for line in X_RAW.read_text(encoding="utf-8").splitlines() if line.strip()]
    items = []
    for row in rows:
        raw = {
            "tweet_id": row.get("tweet_id"),
            "author_handle": row.get("author_handle"),
            "created_at": row.get("created_at"),
            "lang": row.get("lang"),
            "replies": row.get("replies"),
            "retweets": row.get("retweets"),
            "likes": row.get("likes"),
            "views": row.get("views"),
        }
        engagement = sum(int(row.get(k) or 0) for k in ("likes", "retweets", "replies"))
        items.append({
            "platform": "x",
            "item_id": f"x:{row['tweet_id']}",
            "title": snippet(row.get("text")),
            "url": row.get("url"),
            "author": f"@{row.get('author_handle')}",
            "published_at": row.get("created_at"),
            "metrics": {
                "source": "x.com search f=top keyword=notion template",
                "demand_raw": engagement,
                "demand_basis": "likes + retweets + replies",
                "cost_input": "missing",
                "cost_note": "no public seller cost input; margin is an interval estimate",
                "raw": raw,
            },
            "collected_at": row.get("fetched_at"),
            "raw_ref": "raw/x_search.jsonl",
            "raw_summary": {k: raw[k] for k in ("tweet_id", "author_handle", "created_at", "likes", "retweets", "replies")},
        })
    return items


def bili_items() -> list[dict]:
    data = json.loads(BILI_RAW.read_text(encoding="utf-8"))
    items = []
    for row in data["data"]["result"]:
        raw = {
            "bvid": row.get("bvid"),
            "aid": row.get("aid"),
            "author": row.get("author"),
            "play": row.get("play"),
            "like": row.get("like"),
            "favorites": row.get("favorites"),
            "danmaku": row.get("danmaku"),
            "review": row.get("review"),
            "pubdate": row.get("pubdate"),
            "duration": row.get("duration"),
            "tag": row.get("tag"),
        }
        items.append({
            "platform": "bilibili",
            "item_id": f"bili:{row['bvid']}",
            "title": snippet(clean(row.get("title"))),
            "url": f"https://www.bilibili.com/video/{row['bvid']}",
            "author": row.get("author"),
            "published_at": iso_from_epoch(row.get("pubdate")),
            "metrics": {
                "source": "api.bilibili.com search/type video keyword=notion template",
                "demand_raw": int(row.get("play") or 0),
                "demand_basis": "play count",
                "cost_input": "missing",
                "cost_note": "no public seller cost input; margin is an interval estimate",
                "raw": raw,
            },
            "collected_at": "2026-10-22T07:01:30Z",
            "raw_ref": "raw/bilibili_search.json",
            "raw_summary": {k: raw[k] for k in ("bvid", "author", "play", "like", "favorites", "pubdate")},
        })
    return items


def github_items() -> list[dict]:
    data = json.loads(GITHUB_RAW.read_text(encoding="utf-8"))
    items = []
    for row in data["items"]:
        lic = row.get("license") or {}
        raw = {
            "full_name": row.get("full_name"),
            "stargazers_count": row.get("stargazers_count"),
            "forks_count": row.get("forks_count"),
            "open_issues_count": row.get("open_issues_count"),
            "license": lic.get("spdx_id"),
            "license_name": lic.get("name"),
            "pushed_at": row.get("pushed_at"),
            "created_at": row.get("created_at"),
            "language": row.get("language"),
            "topics": row.get("topics") or [],
        }
        items.append({
            "platform": "github",
            "item_id": f"gh:{row['full_name']}",
            "title": snippet(row.get("full_name")),
            "url": row.get("html_url"),
            "author": (row.get("owner") or {}).get("login"),
            "published_at": row.get("created_at"),
            "metrics": {
                "source": "api.github.com search/repositories q=notion template sort=stars",
                "demand_raw": int(row.get("stargazers_count") or 0),
                "demand_basis": "stargazers_count",
                "cost_input": "missing",
                "cost_note": "no public seller cost input; margin is an interval estimate",
                "raw": raw,
            },
            "collected_at": "2026-10-22T07:02:37Z",
            "raw_ref": "raw/github_search.json",
            "raw_summary": {k: raw[k] for k in ("full_name", "stargazers_count", "forks_count", "license", "pushed_at")},
        })
    return items


def main() -> int:
    items = x_items() + bili_items() + github_items()
    items.sort(key=lambda r: (r["platform"], r["item_id"]))
    OUT.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in items),
                   encoding="utf-8", newline="\n")
    counts = {}
    for item in items:
        counts[item["platform"]] = counts.get(item["platform"], 0) + 1
    print(json.dumps({"total": len(items), "counts": counts, "out": str(OUT)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
