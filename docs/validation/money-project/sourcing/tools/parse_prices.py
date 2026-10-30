#!/usr/bin/env python
"""Parse Xianyu price signals: listed price, effective price, struck reference, wants."""

from __future__ import annotations

import csv
import datetime
import json
import pathlib
import re
from urllib.parse import parse_qs, urlparse

BASE = pathlib.Path(__file__).resolve().parents[1]
SOURCE = pathlib.Path(r"D:\桌面\two\tools\platform-login\data\xianyu_items.jsonl")
OUT = BASE / "price_signals.csv"
SUMMARY = BASE / "logs" / "price_parse_summary.json"
PROVINCES = ("北京", "上海", "天津", "重庆", "河北", "山西", "辽宁", "吉林", "黑龙江",
             "江苏", "浙江", "安徽", "福建", "江西", "山东", "河南", "湖北", "湖南",
             "广东", "海南", "四川", "贵州", "云南", "陕西", "甘肃", "青海", "内蒙古",
             "广西", "西藏", "宁夏", "新疆", "香港", "澳门", "台湾")
PARSED_AT = "2026-10-22T08:50:30Z"  # fixed for deterministic re-runs


def utc() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def money(text: str) -> float | None:
    match = re.search(r"¥\s*(\d+(?:\.\d+)?)", text)
    return float(match.group(1)) if match else None


def parse_row(row: dict, index: int) -> dict:
    raw = row.get("raw_text") or ""
    tail = raw[-360:]
    listed = money(row.get("price") or "") or money(tail) or 0.0

    # "¥ 1 .88 ¥699" means displayed 1.88 with a struck 699; "¥ 1 ¥9.9" means 1 / 9.9.
    frac = re.search(r"¥\s*1\s+\.(\d{2})", tail)
    effective = 1.0 + int(frac.group(1)) / 100 if frac else listed

    tokens = [float(x) for x in re.findall(r"¥\s*(\d+(?:\.\d+)?)", tail)]
    refs = [x for x in tokens if x > effective + 0.01]
    reference = max(refs) if refs else None

    wants_match = re.search(r"(\d+)\s*人想要", tail)
    wants = int(wants_match.group(1)) if wants_match else None

    province = next((p for p in PROVINCES if p in tail), "")
    delivery = "发货极快" if "发货极快" in tail else ("回复超快" if "回复超快" in tail else "")
    status = []
    if frac:
        status.append("fraction_merged")
    if reference:
        status.append("reference_found")
    else:
        status.append("reference_missing")
    if wants is None:
        status.append("wants_missing")
    if not frac and effective == listed:
        status.append("list_price_only")

    qs = parse_qs(urlparse(row.get("href") or "").query)
    item_id = (qs.get("id") or [str(index)])[0]
    return {
        "item_id": item_id,
        "title_snippet": re.sub(r"\s+", " ", row.get("title") or "")[:120],
        "listed_price": round(listed, 2),
        "effective_price": round(effective, 2),
        "reference_price": "" if reference is None else round(reference, 2),
        "wants": "" if wants is None else wants,
        "province": province,
        "delivery": delivery,
        "parse_status": "|".join(status),
        "price_assumption": ("¥1 is bait; effective uses fractional suffix when present; "
                             "reference is a struck/other higher price, not a transaction price"),
        "raw_price_tail": tail[-120:],
        "source_url": row.get("href"),
        "collected_at": PARSED_AT,
    }


def main() -> int:
    rows = [json.loads(line) for line in SOURCE.read_text(encoding="utf-8").splitlines() if line.strip()]
    parsed = [parse_row(row, i) for i, row in enumerate(rows, 1)]
    fields = ["item_id", "title_snippet", "listed_price", "effective_price", "reference_price",
              "wants", "province", "delivery", "parse_status", "price_assumption",
              "raw_price_tail", "source_url", "collected_at"]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(parsed)
    effective = [r["effective_price"] for r in parsed]
    refs = [r["reference_price"] for r in parsed if r["reference_price"] != ""]
    wants = [r["wants"] for r in parsed if r["wants"] != ""]
    summary = {
        "parsed_at": PARSED_AT,
        "input_rows": len(rows),
        "output_rows": len(parsed),
        "effective_price": {"min": min(effective), "max": max(effective),
                            "unique": sorted(set(effective))},
        "reference_price": {"count": len(refs), "values": sorted(set(refs))},
        "wants": {"count": len(wants), "min": min(wants) if wants else None,
                  "max": max(wants) if wants else None,
                  "sum": sum(wants) if wants else 0},
        "status_counts": {s: sum(1 for r in parsed if s in r["parse_status"])
                          for s in ("fraction_merged", "reference_found", "reference_missing",
                                    "wants_missing", "list_price_only")},
        "failures_or_partial": [
            {"item_id": r["item_id"], "status": r["parse_status"],
             "raw_tail": r["raw_price_tail"]}
            for r in parsed if "reference_missing" in r["parse_status"]
        ][:5],
        "assumptions": [
            "listed ¥1 is a traffic-bait price, not a realized ASP",
            "effective price merges the fractional suffix in raw text when present",
            "reference price is a struck/higher price, not a transaction price",
            "wants count is an interest proxy, not paid orders",
        ],
    }
    SUMMARY.parent.mkdir(parents=True, exist_ok=True)
    SUMMARY.write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8", newline="\n")
    print(json.dumps(summary, ensure_ascii=True, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
