#!/usr/bin/env python
"""Filter x-collect topic search results: engagement + relevance (stdlib only).

Three tiers:
  raw                 all collected rows
  engaged             likes+retweets+replies >= 50 (None -> 0)
  relevant            engaged AND matches the web-scraping semantic whitelist,
                      after dropping clearly irrelevant contexts (reptiles,
                      sewer/pipe/robotic crawlers, kitten rescue).

CSV/top20 use only the third tier. Outputs: filtered JSONL (UTF-8 no BOM),
summary.csv (UTF-8 with BOM for Excel), summary.json, top20.md,
dropped_irrelevant.jsonl (audit).
"""

from __future__ import annotations

import csv
import json
import pathlib
import re

BASE = pathlib.Path(__file__).resolve().parents[1]
RAW = BASE / "raw"
FILTERED = BASE / "filtered"
THRESHOLD = 50
SOURCES = {
    "web scraping": RAW / "top_run1_web_scraping.jsonl",
    "crawler": RAW / "top_run2_crawler.jsonl",
    "爬虫": RAW / "top_run3_pachong.jsonl",
}
SLUGS = {"web scraping": "web_scraping", "crawler": "crawler", "爬虫": "pachong"}

INCLUDE = re.compile(
    r"scrap|scraper|scraping|spider|web\s*crawl|crawling|爬虫|反爬|采集|"
    r"selenium|playwright|puppeteer|beautifulsoup|requests\s*库|数据抓取",
    re.IGNORECASE,
)
EXCLUDE = re.compile(
    r"reptile|爬虫類|爬蟲|爬宠|トカゲ|蜥蜴|pipe\s*crawler|sewer|storm\s*drain|"
    r"kitten\s*rescue|robotic\s*crawler|spider[\s-]?man|marvel|dc\s*comics|"
    r"wall[\s-]?crawler|superhero|comic",
    re.IGNORECASE,
)
CONTEXT = re.compile(
    r"\bwebsite\b|\bhtml\b|\bbrowser\b|\bautomation\b|\bselenium\b|"
    r"\bplaywright\b|\bpuppeteer\b|\bbeautifulsoup\b|\bscrapy\b|"
    r"\bcrawl(?:er|ing|s)?\b|\bspider\b|\bapi\b|\bpython\b|\bproxy\b|"
    r"anti[- ]?bot|web\s+(scrap|crawl|data|spider|page|content|automation)|"
    r"反爬|采集|抓取|爬取|网页|网站|数据|代码|接口|工具|程序",
    re.IGNORECASE,
)


def load_rows(path: pathlib.Path) -> list[dict]:
    rows = []
    if not path.exists():
        return rows
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def engagement(row: dict) -> int:
    total = 0
    for key in ("likes", "retweets", "replies"):
        value = row.get(key)
        if isinstance(value, bool) or not isinstance(value, int):
            continue
        total += value
    return total


def relevance(row: dict) -> bool:
    text = row.get("text") or ""
    if EXCLUDE.search(text):
        return False
    if not INCLUDE.search(text):
        return False
    return bool(CONTEXT.search(text))


def snippet(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()[:120]


def main() -> int:
    FILTERED.mkdir(parents=True, exist_ok=True)
    raw_by_kw: dict[str, list[dict]] = {}
    engaged_by_kw: dict[str, list[dict]] = {}
    relevant_by_kw: dict[str, list[dict]] = {}
    dropped: list[dict] = []
    all_rows: dict[str, dict] = {}
    fetched: list[str] = []

    for keyword, path in SOURCES.items():
        rows = load_rows(path)
        raw_by_kw[keyword] = rows
        engaged, relevant = [], []
        for row in rows:
            row = dict(row)
            row["engagement"] = engagement(row)
            row["keyword"] = keyword
            if row.get("fetched_at"):
                fetched.append(row["fetched_at"])
            if row["engagement"] < THRESHOLD:
                continue
            engaged.append(row)
            if relevance(row):
                relevant.append(row)
            else:
                dropped.append({"tweet_id": row.get("tweet_id"), "url": row.get("url"),
                                "author_handle": row.get("author_handle"),
                                "engagement": row["engagement"],
                                "text": row.get("text")})
        engaged_by_kw[keyword] = engaged
        relevant_by_kw[keyword] = relevant
        relevant = sorted(relevant,
                          key=lambda r: (r["engagement"], r.get("created_at") or ""),
                          reverse=True)
        out = FILTERED / f"filtered_{SLUGS[keyword]}.jsonl"
        out.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in relevant),
                       encoding="utf-8", newline="\n")
        for row in relevant:
            tid = str(row.get("tweet_id"))
            current = all_rows.get(tid)
            if current is None or row["engagement"] > current["engagement"]:
                all_rows[tid] = row

    combined = sorted(all_rows.values(),
                      key=lambda r: (r["engagement"], r.get("created_at") or ""),
                      reverse=True)
    FILTERED.joinpath("filtered_all.jsonl").write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in combined),
        encoding="utf-8", newline="\n")
    FILTERED.joinpath("dropped_irrelevant.jsonl").write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in dropped),
        encoding="utf-8", newline="\n")

    csv_path = FILTERED / "summary.csv"
    with csv_path.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=[
            "engagement", "likes", "retweets", "replies", "author_handle",
            "created_at", "lang", "url", "text_snippet"], lineterminator="\n")
        writer.writeheader()
        for row in combined:
            writer.writerow({
                "engagement": row["engagement"],
                "likes": row.get("likes"),
                "retweets": row.get("retweets"),
                "replies": row.get("replies"),
                "author_handle": row.get("author_handle"),
                "created_at": row.get("created_at"),
                "lang": row.get("lang"),
                "url": row.get("url"),
                "text_snippet": snippet(row.get("text", "")),
            })

    per_keyword = {}
    for keyword in SOURCES:
        raw_n = len(raw_by_kw[keyword])
        eng_n = len(engaged_by_kw[keyword])
        rel_n = len(relevant_by_kw[keyword])
        per_keyword[keyword] = {
            "raw": raw_n,
            "engaged_ge_50": eng_n,
            "relevant": rel_n,
            "dropped_irrelevant": eng_n - rel_n,
            "pass_rate_raw_to_engaged": round(eng_n / raw_n, 4) if raw_n else 0.0,
            "pass_rate_engaged_to_relevant": round(rel_n / eng_n, 4) if eng_n else 0.0,
        }

    # Threshold sensitivity for suggestions only (not used to change output).
    sensitivity = {}
    for t in (50, 30, 20):
        count = 0
        for rows in raw_by_kw.values():
            for row in rows:
                if engagement(row) >= t and relevance(row):
                    count += 1
        sensitivity[str(t)] = count

    total_engaged = sum(len(v) for v in engaged_by_kw.values())
    total_relevant_raw = sum(len(v) for v in relevant_by_kw.values())
    summary = {
        "threshold": THRESHOLD,
        "engagement_formula": "likes + retweets + replies (None -> 0)",
        "relevance": {
            "include_regex": INCLUDE.pattern,
            "exclude_regex": EXCLUDE.pattern,
            "context_regex": CONTEXT.pattern,
            "note": "exclude takes precedence; include AND context required; only engaged rows are checked",
        },
        "dedupe_strategy": "cross-keyword by tweet_id: keep highest engagement; tie -> first seen",
        "sources": {k: str(v.relative_to(BASE)) for k, v in SOURCES.items()},
        "three_tiers": {
            "raw": sum(len(v) for v in raw_by_kw.values()),
            "engaged_ge_50": total_engaged,
            "engaged_and_relevant": len(combined),
            "dropped_irrelevant_raw": len(dropped),
            "deduped_removed": total_relevant_raw - len(combined),
        },
        "per_keyword": per_keyword,
        "threshold_sensitivity_relevant": sensitivity,
        "execution_period": {"start": min(fetched) if fetched else None,
                             "end": max(fetched) if fetched else None},
        "outputs": {
            "filtered_all": str((FILTERED / "filtered_all.jsonl").relative_to(BASE)),
            "dropped_irrelevant": str((FILTERED / "dropped_irrelevant.jsonl").relative_to(BASE)),
            "summary_csv": str(csv_path.relative_to(BASE)),
            "per_keyword": {k: f"filtered/filtered_{SLUGS[k]}.jsonl" for k in SOURCES},
        },
        "limits": {
            "low_yield": "f=top + engagement>=50 + relevance may yield few rows; threshold not lowered.",
            "suggestion": ("若第三档不足 10 条：建议扩大 raw（每词 >60 或更多关键词）、"
                           "阈值下调至 30/20（需用户确认）并扩充同义词/排除词；"
                           f"当前相关计数@50={sensitivity['50']}、@30={sensitivity['30']}、"
                           f"@20={sensitivity['20']}"),
            "attempt_note": "run1 CLI false RISK_CONTROL (/Challenge/i matched tweet text 'challenges'); "
                            "collection used tools/collect_search.py with selector-based risk check; "
                            "original x_collect.py unchanged.",
        },
    }
    (BASE / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8", newline="\n")

    lines = ["# top20（engagement = likes+retweets+replies ≥50 且 relevance 通过）", "",
             f"- 阈值：≥{THRESHOLD}；相关性：网页采集词表 + 排除词（排除优先）",
             f"- 原始：{summary['three_tiers']['raw']} 条；达标：{total_engaged} 条；"
             f"达标且相关（去重后）：{len(combined)} 条", ""]
    if len(combined) < 10:
        lines.append(f"> 注意：第三档仅 {len(combined)} 条（<10）。建议扩大 raw/关键词，"
                     "或在用户确认后下调阈值（@30 相关="
                     f"{sensitivity['30']}，@20 相关={sensitivity['20']}），本文件未擅自降阈值。")
        lines.append("")
    for i, row in enumerate(combined[:20], 1):
        lines.append(f"{i}. **{row['engagement']}** | [{row.get('author_handle')}]({row.get('url')}) "
                     f"| {row.get('created_at')} | {snippet(row.get('text', ''))}")
    (BASE / "top20.md").write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")

    print(json.dumps(summary, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
