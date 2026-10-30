"""只读核验：评分复算 + 数据抽样 + 许可复核 + GitHub API 校验（不修改任何被测文件）。

输出：docs/validation/money-project/verify/recompute_and_samples.json
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
import pathlib
import sys
import urllib.request

ROOT = pathlib.Path(r"D:\桌面\two")
MP = ROOT / "docs" / "validation" / "money-project"
OUT = MP / "verify" / "recompute_and_samples.json"
PRIOR = {"x": 0.60, "bilibili": 0.45, "github": 0.70}
W = {"demand": 0.30, "competition": 0.20, "margin": 0.20, "fulfillment": 0.10, "compliance": 0.10, "replicability": 0.10}
REPOS = ["enescingoz/awesome-n8n-templates", "InlitX/Obsidian-Dashboard-Gallery", "vercel-labs/marketing-team-eve-template"]


def read_csv(p):
    with p.open(encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def f(x, d=0.0):
    try:
        return float(x)
    except (TypeError, ValueError):
        return d


def percentile_within_platform(rows):
    """model.md §3.1：平台内按 log1p(raw) 升序，rank/(n-1)，并列取首个位置。"""
    by = {}
    for r in rows:
        by.setdefault(r["platform"], []).append(r)
    out = {}
    for plat, items in by.items():
        ordered = sorted(items, key=lambda r: math.log1p(f(r["demand_raw"])))
        n = len(ordered)
        i = 0
        while i < n:
            j = i
            while j + 1 < n and f(ordered[j + 1]["demand_raw"]) == f(ordered[i]["demand_raw"]):
                j += 1
            for k in range(i, j + 1):
                out[ordered[k]["item_id"]] = i / (n - 1) if n > 1 else 0.0
            i = j + 1
    return out


def main() -> int:
    scores = read_csv(MP / "scoring" / "scores.csv")
    items_jsonl = [json.loads(l) for l in (MP / "scoring" / "items.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    sources = read_csv(MP / "sourcing" / "sources.csv")
    price = read_csv(MP / "sourcing" / "price_signals.csv")
    top10 = read_csv(MP / "sourcing" / "opportunity_sourcing_top10.csv")
    report = {"generated_utc": __import__("time").strftime("%Y-%m-%dT%H:%M:%SZ", __import__("time").gmtime()),
              "counts": {"scores_rows": len(scores), "items_jsonl_rows": len(items_jsonl),
                         "sources_rows": len(sources), "price_signals_rows": len(price), "top10_rows": len(top10)},
              "score_recompute": [], "data_samples": [], "license_checks": [], "github_api": []}

    # ---------- 评分复算（3 行，跨平台各一） ----------
    pct = percentile_within_platform(scores)
    by_platform = {}
    for r in scores:
        by_platform.setdefault(r["platform"], r)
    picks = [by_platform[p] for p in ("x", "bilibili", "github") if p in by_platform]
    for r in picks:
        got = {
            "demand_norm": pct.get(r["item_id"]),
            "competition_norm": 1 - min(1.0, PRIOR[r["platform"]] + 0.05 * max(0, int(f(r.get("same_author_count", 1), 1)) - 1)),
            "margin_mid": (f(r["margin_low"]) + f(r["margin_high"])) / 2,
            "fulfillment_norm": f(r["fulfillment_raw"]),
            "compliance_norm": f(r["compliance_raw"]),
            "replicability_norm": f(r["replicability_raw"]),
        }
        total = (got["demand_norm"] * W["demand"] + got["competition_norm"] * W["competition"] +
                 got["margin_mid"] * W["margin"] + got["fulfillment_norm"] * W["fulfillment"] +
                 got["compliance_norm"] * W["compliance"] + got["replicability_norm"] * W["replicability"])
        reported = {"demand_norm": f(r["demand_norm"]), "competition_norm": f(r["competition_norm"]),
                    "margin_mid": f(r["margin_mid"]), "fulfillment_norm": f(r["fulfillment_norm"]),
                    "compliance_norm": f(r["compliance_norm"]), "replicability_norm": f(r["replicability_norm"]),
                    "total_score": f(r["total_score"])}
        diffs = {k: round(got[k] - reported[k], 6) for k in ("demand_norm", "competition_norm", "margin_mid",
                                                             "fulfillment_norm", "compliance_norm", "replicability_norm")}
        diffs["total_score"] = round(total - reported["total_score"], 6)
        report["score_recompute"].append({"item_id": r["item_id"], "platform": r["platform"], "rank": r["rank"],
                                          "recomputed": {k: round(v, 6) for k, v in got.items()},
                                          "recomputed_total": round(total, 6), "reported": reported, "diffs": diffs,
                                          "within_tolerance_1e-3": all(abs(v) <= 1e-3 for v in diffs.values())})

    # ---------- 数据抽样（3 条比对） ----------
    raw_x = [json.loads(l) for l in (MP / "scoring" / "raw" / "x_search.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    x_row = next(r for r in scores if r["platform"] == "x")
    x_id = x_row["item_id"].split(":", 1)[1]
    x_raw = next((d for d in raw_x if str(d.get("id")) == x_id), None)
    engage = None
    if x_raw:
        m = x_raw.get("public_metrics") or x_raw.get("metrics") or {}
        engage = (m.get("like_count", 0) or 0) + (m.get("retweet_count", 0) or 0) + (m.get("reply_count", 0) or 0)
    report["data_samples"].append({"check": "scores.csv demand_raw ↔ x_search.jsonl 互动和", "item_id": x_row["item_id"],
                                   "scores_demand_raw": f(x_row["demand_raw"]), "raw_engagement_sum": engage,
                                   "match": engage is not None and abs(engage - f(x_row["demand_raw"])) < 1e-6})
    report["data_samples"].append({"check": "items.jsonl ↔ scores.csv 行数", "items_jsonl": len(items_jsonl),
                                   "scores_csv": len(scores), "match": len(items_jsonl) == len(scores)})
    join = None
    if top10 and price:
        t = top10[0]
        keys = [k for k in t if "id" in k.lower()]
        k0 = keys[0] if keys else None
        if k0:
            hits = [p for p in price if any(str(p.get(kk)) == str(t.get(k0)) for kk in p if "id" in kk.lower())]
            join = {"top10_key": k0, "value": t.get(k0), "price_signals_hits": len(hits)}
    report["data_samples"].append({"check": "opportunity_sourcing_top10.csv ↔ price_signals.csv 连接", "join": join,
                                   "match": bool(join and join.get("price_signals_hits", 0) > 0)})

    # ---------- 许可复核（3 行） ----------
    lic = json.loads((MP / "sourcing" / "raw" / "license_checks.json").read_text(encoding="utf-8")) \
        if (MP / "sourcing" / "raw" / "license_checks.json").exists() else {}
    for row in sources[:3]:
        name = row["name"]
        raw_file = MP / "sourcing" / "raw" / "licenses" / (name.replace("/", "__") + ".json")
        raw_lic = json.loads(raw_file.read_text(encoding="utf-8")) if raw_file.exists() else None
        api_spdx = None
        if isinstance(raw_lic, dict):
            api_spdx = ((raw_lic.get("license") or {}).get("spdx_id") if isinstance(raw_lic.get("license"), dict)
                        else raw_lic.get("license_spdx"))
        report["license_checks"].append({
            "repo": name, "sources_csv_spdx": row["license_spdx"], "sources_csv_verdict": row["license_verdict"],
            "sources_csv_license_source": row.get("license_source"), "raw_license_file": raw_file.name if raw_file.exists() else None,
            "raw_spdx": api_spdx, "match": (api_spdx or "").upper() in {row["license_spdx"].upper(), ""} if api_spdx else None,
            "note": row.get("license_key_sentence"),
        })

    # ---------- GitHub API（3 仓库，无 token） ----------
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({"http": "http://127.0.0.1:10808",
                                                                      "https": "http://127.0.0.1:10808"}))
    for name in REPOS:
        rec = {"repo": name}
        try:
            req = urllib.request.Request(f"https://api.github.com/repos/{name}",
                                         headers={"Accept": "application/vnd.github+json", "User-Agent": "dsh-verify"})
            with opener.open(req, timeout=20) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            rec.update({"status": 200, "spdx": ((data.get("license") or {}) or {}).get("spdx_id"),
                        "stars": data.get("stargazers_count"), "pushed_at": data.get("pushed_at"),
                        "archived": data.get("archived")})
            src = next((s for s in sources if s["name"] == name), None)
            if src:
                rec["sources_csv"] = {"spdx": src["license_spdx"], "stars": src.get("stars"), "pushed_at": src.get("pushed_at")}
                rec["spdx_consistent"] = str(rec["spdx"]).upper() == str(src["license_spdx"]).upper() or \
                                         (rec["spdx"] in (None, "NOASSERTION") and src["license_spdx"] == "NOASSERTION")
                rec["stars_consistent"] = str(rec["stars"]) == str(src.get("stars"))
        except Exception as exc:
            rec.update({"error": f"{type(exc).__name__}: {exc}"})
        report["github_api"].append(rec)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_bytes(json.dumps(report, ensure_ascii=False, indent=1).encode("utf-8"))
    print(json.dumps(report, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
