#!/usr/bin/env python
"""Join scoring Top10 with Xianyu price signals and verified GitHub sources."""

from __future__ import annotations

import csv
import json
import pathlib
import re

BASE = pathlib.Path(__file__).resolve().parents[1]
SCORING = BASE.parent / "scoring"

# Price-driven gross-margin assumptions. These are CNY per digital unit, not a
# hard FX conversion of the old $0.5-3 model range; the platform prices are CNY
# and mostly ¥1 bait, so a lower-bound delivery/hosting cost is the honest unit.
COST_LOW = 0.5
COST_HIGH = 3.0
FALLBACK_WIDEN = 0.15


def clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


def median(values: list[float]) -> float:
    ordered = sorted(values)
    mid = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[mid]
    return (ordered[mid - 1] + ordered[mid]) / 2.0


def gross_margin(price: float, cost: float) -> float:
    if price <= 0:
        return 0.0
    return clamp01((price - cost) / price)



def load_csv(path: pathlib.Path) -> list[dict]:
    with path.open(encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def price_category(title: str) -> str:
    text = title.lower()
    if re.search(r"resume|简历|作品集|设计|ui|psd|素材|logo|海报|平面|lamaran|job application|求职|面试", text):
        return "design"
    if re.search(r"prompt|提示词|chatgpt|ai|文案", text):
        return "prompt"
    return "notion"


def choose_source(title: str, sources: list[dict], rank: int) -> tuple[dict, list[dict], str, str]:
    cat = price_category(title)
    by_id = {s["source_id"]: s for s in sources}
    if cat == "design":
        if re.search(r"resume|简历|lamaran|job application|求职|面试", title, re.I):
            preferred = ["gh-11", "gh-12", "gh-14", "gh-02"]
            note = "同品类：简历/求职模板源"
            reason = "同品类"
        else:
            preferred = ["gh-12", "gh-14", "gh-02", "gh-05"]
            note = "近似匹配：作品集/设计模板源"
            reason = "近似"
    elif cat == "prompt":
        preferred = ["gh-13", "gh-10", "gh-03"]
        note = "同品类：提示词库源"
        reason = "同品类"
    elif rank == 4:
        preferred = ["gh-03", "gh-10", "gh-02"]
        note = "近似匹配：站点/Notion 模板源（内容教程非直接商品）"
        reason = "近似"
    elif rank == 8:
        preferred = ["gh-12", "gh-14", "gh-03"]
        note = "替代匹配：作品集/站点模板源（教程机会无同款商品）"
        reason = "替代"
    else:
        preferred = ["gh-10", "gh-03", "gh-02"]
        note = "同品类：Notion 模板/站点源"
        reason = "同品类"
    ordered = [by_id[sid] for sid in preferred if sid in by_id]
    ordered += [s for s in sources if s not in ordered]
    commercial = [s for s in ordered if s["license_verdict"] == "可商用"]
    chosen = commercial[0] if commercial else ordered[0]
    alternatives = [s for s in ordered if s["source_id"] != chosen["source_id"]][:2]
    return chosen, alternatives, note, reason


def main() -> int:
    scores = load_csv(SCORING / "scores.csv")
    sources = load_csv(BASE / "sources.csv")
    prices = load_csv(BASE / "price_signals.csv")
    top = [row for row in scores if int(row["rank"]) <= 10]
    top.sort(key=lambda row: int(row["rank"]))
    old_by_rank = {}
    old_path = BASE / "opportunity_sourcing_top10.csv"
    if old_path.exists():
        old_by_rank = {r["rank"]: r for r in load_csv(old_path)}

    rows = []
    for row in top:
        cat = price_category(row["title"])
        if cat == "design":
            selected_prices = [p for p in prices if price_category(p["title_snippet"]) == "design"]
        elif cat == "prompt":
            selected_prices = [p for p in prices if price_category(p["title_snippet"]) == "prompt"]
        else:
            selected_prices = [p for p in prices if price_category(p["title_snippet"]) == "notion"]
        used_fallback = False
        if not selected_prices:
            # No exact Xianyu category (e.g. Notion tutorial); use the full
            # 20-item digital-goods basket as a market proxy, clearly labeled.
            selected_prices = prices
            used_fallback = True
        effective = [float(p["effective_price"]) for p in selected_prices]
        refs = [float(p["reference_price"]) for p in selected_prices if p["reference_price"]]
        wants = [int(p["wants"]) for p in selected_prices if p["wants"]]
        chosen, alternatives, match_note, match_reason = choose_source(
            row["title"], sources, int(row["rank"]))

        fallback = used_fallback or len(selected_prices) < 3
        # ¥1 listings are traffic bait / missing price: do not use effective_low
        # as the revenue floor. Prefer the reference median; without a reference,
        # use the category/all-basket effective_high.
        ref_anchor = median(refs) if refs else None
        anchor = ref_anchor if ref_anchor is not None else (max(effective) if effective else None)

        if anchor is None:
            margin_basis = "model_assumption_fallback"
            margin_confidence = "low"
            margin_low = float(row["margin_low"])
            margin_high = float(row["margin_high"])
            margin_mid = float(row["margin_mid"])
            margin_note = ("No usable Xianyu price signal; retained scoring model "
                           "range as an explicit low-confidence fallback.")
        else:
            margin_low = gross_margin(anchor, COST_HIGH)
            margin_high = gross_margin(anchor, COST_LOW)
            if fallback:
                margin_low = clamp01(margin_low - FALLBACK_WIDEN)
                margin_high = clamp01(margin_high + FALLBACK_WIDEN)
                margin_basis = ("all20_reference_median_widened" if refs
                                else "all20_effective_high_widened")
                margin_confidence = "low"
            elif refs:
                margin_basis = "category_reference_median"
                # n<5 never high; only n>=5 with a reference may be high.
                margin_confidence = "high" if len(selected_prices) >= 5 else "medium"
            else:
                margin_basis = "category_effective_high"
                margin_confidence = "low" if len(selected_prices) < 5 else "medium"
            margin_mid = (margin_low + margin_high) / 2.0
            anchor_name = "reference_median" if refs else "effective_high"
            note_prefix = "all_20 fallback; " if used_fallback else ""
            margin_note = (
                f"已排除 ¥1 引流标价；{note_prefix}price_anchor={anchor_name} ¥{anchor:.2f}; "
                f"cost=¥{COST_LOW:.1f}-{COST_HIGH:.1f}/unit; "
                "margin=clamp((price-cost)/price,0,1); mid=midpoint"
                + ("; widened ±0.15" if fallback else "")
                + (f"; reference_max ¥{max(refs):.2f} not used as anchor (outlier risk)" if refs else "")
                + "."
            )

        assumptions = (
            ("No exact Xianyu Notion category; all 20 digital-goods signals used as basket proxy. "
             if used_fallback else "")
            + "¥1 listings excluded as traffic bait. "
            + (f"Xianyu effective range ¥{min(effective):.2f}-{max(effective):.2f}; "
               if effective else "No usable Xianyu effective price; ")
            + (f"reference median ¥{ref_anchor:.2f} (max ¥{max(refs):.2f}); "
               if refs else "no struck reference; effective_high used as anchor; ")
            + f"price-driven margin {margin_low:.3f}-{margin_high:.3f} via {margin_basis}; "
            + "wants is interest proxy, not paid orders; old model assumption retained only for no-price fallback."
        )
        rows.append({
            "rank": row["rank"],
            "opportunity_id": row["item_id"],
            "platform": row["platform"],
            "title": row["title"],
            "url": row["url"],
            "score": row["total_score"],
            "price_category": cat,
            "price_scope": "all_20_fallback" if used_fallback else "category_filtered",
            "price_signal_count": len(selected_prices),
            "effective_low": min(effective) if effective else "",
            "effective_high": max(effective) if effective else "",
            "reference_max": max(refs) if refs else "",
            "wants_sum": sum(wants) if wants else "",
            "source_id": chosen["source_id"],
            "source_name": chosen["name"],
            "source_url": chosen["repo_or_url"],
            "license_spdx": chosen["license_spdx"],
            "license_verdict": chosen["license_verdict"],
            "source_evidence_url": chosen["evidence_url"],
            "match_quality": match_note,
            "match_reason": match_reason,
            "source_alternatives": " | ".join(f"{s['source_id']}:{s['name']}({s['license_verdict']})"
                                              for s in alternatives),
            "gross_margin_low": f"{margin_low:.3f}",
            "gross_margin_high": f"{margin_high:.3f}",
            "gross_margin_mid": f"{margin_mid:.3f}",
            "margin_basis": margin_basis,
            "margin_confidence": margin_confidence,
            "margin_note": margin_note,
            "assumptions": assumptions,
        })

    fields = ["rank", "opportunity_id", "platform", "title", "url", "score", "price_category",
              "price_scope", "price_signal_count", "effective_low", "effective_high",
              "reference_max", "wants_sum",
              "source_id", "source_name", "source_url", "license_spdx", "license_verdict", "source_evidence_url",
              "match_quality", "match_reason", "source_alternatives", "gross_margin_low", "gross_margin_high",
              "gross_margin_mid", "margin_basis", "margin_confidence", "margin_note", "assumptions"]
    with (BASE / "opportunity_sourcing_top10.csv").open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)

    for r in rows:
        old = old_by_rank.get(r["rank"], {})
        print(
            f"[margin] rank {r['rank']}: "
            f"old {old.get('gross_margin_low', '?')}-{old.get('gross_margin_high', '?')} "
            f"(mid {old.get('gross_margin_mid', '?')}) -> "
            f"new {r['gross_margin_low']}-{r['gross_margin_high']} (mid {r['gross_margin_mid']}) "
            f"| {r['price_scope']} n={r['price_signal_count']} "
            f"| {r['margin_basis']} / {r['margin_confidence']}"
        )

    summary = {
        "rows": len(rows),
        "license_verdicts": {v: sum(1 for r in rows if r["license_verdict"] == v)
                             for v in ("可商用", "需授权", "禁止或不明")},
        "price_categories": {c: sum(1 for r in rows if r["price_category"] == c)
                             for c in ("design", "prompt", "notion")},
        "margin_confidence": {c: sum(1 for r in rows if r["margin_confidence"] == c)
                              for c in ("high", "medium", "low")},
        "margin_basis": {c: sum(1 for r in rows if r["margin_basis"] == c)
                          for c in sorted({r["margin_basis"] for r in rows})},
        "gross_margin_ranges": sorted({(r["gross_margin_low"], r["gross_margin_high"])
                                        for r in rows}),
        "note": "source matching is nearest reusable template, not exact product match; margin is price-driven with CNY unit cost",
    }
    (BASE / "logs" / "join_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8", newline="\n")
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
