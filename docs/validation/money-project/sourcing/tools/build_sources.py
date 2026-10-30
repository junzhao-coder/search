#!/usr/bin/env python
"""Build sources.csv from verified GitHub licenses + scoring metadata."""

from __future__ import annotations

import csv
import datetime
import json
import pathlib

BASE = pathlib.Path(__file__).resolve().parents[1]
SCORING = BASE.parent / "scoring"

PUSHED_REF = datetime.datetime(2026, 10, 22, tzinfo=datetime.timezone.utc)


def parse_dt(value: str | None):
    if not value:
        return None
    try:
        return datetime.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def classify_type(name: str) -> str:
    low = name.lower()
    if "prompt" in low or "chatgpt" in low or "n8n" in low:
        return "提示词/自动化模板"
    if "dashboard" in low or "anytype" in low or "design" in low:
        return "设计资产/模板"
    if "resume" in low:
        return "简历模板"
    if "portfolio" in low or "academicpages" in low or "simplefolio" in low:
        return "作品集/站点模板"
    if "blog" in low or "website" in low or "waitlist" in low or "marketing" in low:
        return "站点/Notion 模板"
    return "Notion 模板/开发资源"


def main() -> int:
    checks = json.loads((BASE / "raw" / "license_checks.json").read_text(encoding="utf-8"))
    raw = json.loads((SCORING / "raw" / "github_search.json").read_text(encoding="utf-8"))
    stars_by_name = {item["full_name"]: item.get("stargazers_count") or 0 for item in raw["items"]}
    max_stars = max(stars_by_name.values()) if stars_by_name else 1

    rows = []
    for idx, check in enumerate(checks["results"], 1):
        name = check["full_name"]
        stars = check.get("stars") or stars_by_name.get(name, 0)
        pushed = parse_dt(check.get("pushed_at"))
        days = (PUSHED_REF - pushed).days if pushed else 730
        stability = round(max(0.10, min(0.95, 1 - days / 730)), 2)
        differentiation = round(1 - min(1.0, stars / max_stars), 2) if max_stars else 0.5
        verdict = check["license_verdict"]
        after_sales = {"可商用": "低", "需授权": "中", "禁止或不明": "高"}[verdict]
        effort = "低" if any(word in name.lower() for word in ("template", "dashboard", "assets")) else "中"
        rows.append({
            "source_id": f"gh-{idx:02d}",
            "name": name,
            "type": classify_type(name),
            "repo_or_url": check["html_url"],
            "license_spdx": check["license_spdx"] or "NONE",
            "license_verdict": verdict,
            "cost": "0（公开仓库）" if verdict != "禁止或不明" else "0（代码公开，许可不明）",
            "effort": effort,
            "delivery": "数字下载/仓库",
            "stability": stability,
            "differentiation": differentiation,
            "after_sales_risk": after_sales,
            "evidence_url": check["license_url"],
            "checked_at": checks["checked_at"],
            "license_source": check["license_source"],
            "license_reason": check["license_reason"],
            "license_key_sentence": ((check["license_text_first40"] or "").splitlines() or ["(no LICENSE text)"])[0][:160],
            "stars": stars,
            "pushed_at": check.get("pushed_at"),
        })

    fields = ["source_id", "name", "type", "repo_or_url", "license_spdx", "license_verdict",
              "cost", "effort", "delivery", "stability", "differentiation", "after_sales_risk",
              "evidence_url", "checked_at", "license_source", "license_reason",
              "license_key_sentence", "stars", "pushed_at"]
    with (BASE / "sources.csv").open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)

    summary = {
        "built_at": "2026-10-22T07:31:03Z",
        "rows": len(rows),
        "verdicts": {v: sum(1 for r in rows if r["license_verdict"] == v)
                     for v in ("可商用", "需授权", "禁止或不明")},
        "license_sources": {v: sum(1 for r in rows if r["license_source"] == v)
                            for v in ("api_license", "license_file")},
        "notes": "CC BY/attribution => 需授权; NOASSERTION with CC BY is not unknown; no LICENSE/404 stays 禁止或不明.",
    }
    (BASE / "logs" / "source_build_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8", newline="\n")
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
