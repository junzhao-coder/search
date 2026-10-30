"""只读核验 v2：修正字段名后的数据抽样与许可复核（不改被测文件）。

修正点：
- X 原始记录字段为 tweet_id/likes/retweets/replies（不是 id/public_metrics）
- price_signals 的连接键为 item_id（先看其前缀族）
- 许可复核改读 raw/license_checks.json 与 raw/licenses/*.json 的实际结构
输出：docs/validation/money-project/verify/recompute_and_samples_v2.json（ASCII 安全）
"""

from __future__ import annotations

import csv
import json
import pathlib
import sys

ROOT = pathlib.Path(r"D:\桌面\two")
MP = ROOT / "docs" / "validation" / "money-project"
OUT = MP / "verify" / "recompute_and_samples_v2.json"
V1 = MP / "verify" / "recompute_and_samples.json"


def read_csv(p):
    with p.open(encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def main() -> int:
    out = {"structure": {}, "data_samples": [], "license_checks": [], "github_api_reused": True}
    scores = read_csv(MP / "scoring" / "scores.csv")
    x_raw = [json.loads(l) for l in (MP / "scoring" / "raw" / "x_search.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    price = read_csv(MP / "sourcing" / "price_signals.csv")
    top10 = read_csv(MP / "sourcing" / "opportunity_sourcing_top10.csv")
    sources = read_csv(MP / "sourcing" / "sources.csv")

    out["structure"]["x_raw_keys"] = sorted(x_raw[0].keys())
    out["structure"]["price_header"] = list(price[0].keys())
    out["structure"]["top10_header"] = list(top10[0].keys())
    out["structure"]["price_item_id_prefixes"] = sorted({str(r["item_id"]).split(":")[0] for r in price})[:10]
    out["structure"]["price_item_id_sample"] = [r["item_id"] for r in price[:5]]

    # 抽样 1：X 互动和
    x_row = next(r for r in scores if r["platform"] == "x")
    tid = x_row["item_id"].split(":", 1)[1]
    rec = next((d for d in x_raw if str(d.get("tweet_id")) == tid), None)
    eng = None
    if rec:
        eng = int(rec.get("likes", 0)) + int(rec.get("retweets", 0)) + int(rec.get("replies", 0))
    out["data_samples"].append({"check": "scores.csv.demand_raw == x_raw(likes+retweets+replies)", "item_id": x_row["item_id"],
                                "scores_demand_raw": float(x_row["demand_raw"]), "raw_engagement_sum": eng,
                                "match": eng is not None and abs(eng - float(x_row["demand_raw"])) < 1e-6,
                                "raw_record_found": rec is not None})

    # 抽样 2：行数一致性（scores ↔ items.jsonl ↔ 原始三源）
    items = [json.loads(l) for l in (MP / "scoring" / "items.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    out["data_samples"].append({"check": "rows(scores.csv) == rows(items.jsonl)", "scores": len(scores), "items": len(items),
                                "match": len(scores) == len(items)})

    # 抽样 3：top10 ↔ price_signals 连接（按 item_id 前缀族判断是否应连接）
    top_ids = [r.get("opportunity_id") for r in top10]
    price_ids = {r["item_id"] for r in price}
    exact = [i for i in top_ids if i in price_ids]
    out["data_samples"].append({"check": "top10.opportunity_id ∈ price_signals.item_id ?",
                                "top10_ids_sample": top_ids[:3], "price_ids_sample": list(price_ids)[:3],
                                "exact_hits": len(exact),
                                "interpretation": ("两表 id 族不同（top10 含 x:/bili:/gh: 机会 id，price_signals 为闲鱼 item_id），"
                                                   "0 命中属设计而非缺陷——需人工确认两表是否有其他连接键"),
                                "match": None if not exact else True})

    # 许可复核：按实际结构匹配
    lc_path = MP / "sourcing" / "raw" / "license_checks.json"
    lic_checks = json.loads(lc_path.read_text(encoding="utf-8")) if lc_path.exists() else None
    out["structure"]["license_checks_type"] = type(lic_checks).__name__
    if isinstance(lic_checks, dict):
        out["structure"]["license_checks_keys"] = list(lic_checks)[:10]
    lic_files = sorted(f.name for f in (MP / "sourcing" / "raw" / "licenses").glob("*.json"))
    out["structure"]["license_files"] = lic_files
    for row in sources[:3]:
        name = row["name"]
        fn = name.replace("/", "__") + ".json"
        raw_path = MP / "sourcing" / "raw" / "licenses" / fn
        raw = json.loads(raw_path.read_text(encoding="utf-8")) if raw_path.exists() else None
        spdx = None
        if isinstance(raw, dict):
            lic = raw.get("license")
            spdx = (lic or {}).get("spdx_id") if isinstance(lic, dict) else raw.get("license_spdx")
            if spdx is None:
                spdx = raw.get("spdx_id")
        out["license_checks"].append({"repo": name, "csv_spdx": row["license_spdx"], "csv_verdict": row["license_verdict"],
                                      "csv_source": row.get("license_source"), "raw_file": fn if raw_path.exists() else None,
                                      "raw_spdx": spdx, "key_sentence": row.get("license_key_sentence"),
                                      "match": (str(spdx).upper() == row["license_spdx"].upper()) if spdx else None})
    v1 = json.loads(V1.read_text(encoding="utf-8"))
    out["github_api_reused_from_v1"] = v1.get("github_api")
    OUT.write_bytes(json.dumps(out, ensure_ascii=True, indent=1).encode("utf-8"))
    print(json.dumps(out, ensure_ascii=True, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
