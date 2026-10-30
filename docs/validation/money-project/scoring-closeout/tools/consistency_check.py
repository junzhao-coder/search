"""Read-only consistency check for seven-dimension scoring artifacts.

Uses stdlib only (ast/csv/json/math). Never writes scores.csv/model.md/scorer.py.
"""

from __future__ import annotations

import ast
import csv
import json
import math
import pathlib
import re
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:  # pragma: no cover
    pass

BASE = pathlib.Path(r"D:\桌面\two\docs\validation\money-project\scoring")
SCORER = BASE / "scorer.py"
MODEL = BASE / "model.md"
SCORES = BASE / "scores.csv"


def weights_from_scorer() -> dict:
    tree = ast.parse(SCORER.read_text(encoding="utf-8"), filename=str(SCORER))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
                isinstance(target, ast.Name) and target.id == "WEIGHTS" for target in node.targets):
            return ast.literal_eval(node.value)
    raise RuntimeError("WEIGHTS assignment not found")


def model_section_35() -> dict:
    text = MODEL.read_text(encoding="utf-8")
    lines = text.splitlines()
    start = next((index for index, line in enumerate(lines) if re.match(r"^###\s+3\.5\b", line)), None)
    if start is None:
        return {"found": False}
    end = next((index for index in range(start + 1, len(lines))
                if re.match(r"^##\s+", lines[index])), len(lines))
    section = "\n".join(lines[start:end])
    return {"found": True, "start_line": start + 1, "end_line": end,
            "has_0_15": "0.15" in section, "has_0_85": "0.85" in section,
            "mentions_sellability": "可售性" in section and "sellability" in section.lower(),
            "section_excerpt": section[:2400]}


def score_rows() -> list[dict]:
    with SCORES.open(encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def main() -> int:
    out = pathlib.Path(sys.argv[sys.argv.index("--out") + 1])
    weights = weights_from_scorer()
    weight_sum = sum(weights.values())
    model = model_section_35()
    rows = score_rows()
    required = {"rank", "total_score", "sellability_raw", "sellability_norm",
                "sellability_weighted", "sellability_reason"}
    missing_columns = sorted(required - set(rows[0].keys() if rows else []))
    norm_values = []
    bad_norm = []
    for row in rows:
        try:
            value = float(row.get("sellability_norm"))
        except (TypeError, ValueError):
            bad_norm.append({"rank": row.get("rank"), "value": row.get("sellability_norm")})
            continue
        norm_values.append(value)
        if not (0.0 <= value <= 1.0):
            bad_norm.append({"rank": row.get("rank"), "value": value})
    ordered = sorted(rows, key=lambda row: int(row["rank"]))
    ranks = [int(row["rank"]) for row in ordered]
    totals = [float(row["total_score"]) for row in ordered]
    inversions = []
    ties = []
    for index in range(len(ordered) - 1):
        if totals[index] < totals[index + 1]:
            inversions.append({"rank": ranks[index], "total": totals[index],
                               "next_rank": ranks[index + 1], "next_total": totals[index + 1]})
        if totals[index] == totals[index + 1] and ordered[index]["item_id"] > ordered[index + 1]["item_id"]:
            ties.append({"rank": ranks[index], "item_id": ordered[index]["item_id"],
                         "next_item_id": ordered[index + 1]["item_id"]})
    weighted_mismatch = []
    for row in rows:
        try:
            if not math.isclose(float(row["sellability_weighted"]),
                                float(weights["sellability"]) * float(row["sellability_norm"]),
                                abs_tol=1e-5):
                weighted_mismatch.append({"rank": row["rank"]})
        except (KeyError, TypeError, ValueError):
            weighted_mismatch.append({"rank": row.get("rank"), "error": "parse"})
    old_six_sum = sum(value for key, value in weights.items() if key != "sellability")
    model_consistent = bool(model.get("found") and model.get("has_0_85")
                            and model.get("mentions_sellability"))
    payload = {
        "generated_at_utc": __import__("datetime").datetime.now(
            __import__("datetime").timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "weights": weights,
        "weight_sum": weight_sum,
        "weight_sum_ok": math.isclose(weight_sum, 1.0, abs_tol=1e-9),
        "old_six_sum": old_six_sum,
        "old_six_sum_ok": math.isclose(old_six_sum, 0.85, abs_tol=1e-9),
        "sellability_weight": weights.get("sellability"),
        "model_3_5": model,
        "model_consistent": model_consistent,
        "model_explicit_0_15": bool(model.get("has_0_15")),
        "scores": {
            "rows": len(rows),
            "required_columns": sorted(required),
            "missing_columns": missing_columns,
            "sellability_norm_count": len(norm_values),
            "sellability_norm_min": min(norm_values) if norm_values else None,
            "sellability_norm_max": max(norm_values) if norm_values else None,
            "sellability_out_of_range": bad_norm,
            "ranks_sequential": ranks == list(range(1, len(ranks) + 1)),
            "rank_total_inversions": inversions,
            "tie_item_id_order_issues": ties,
            "sellability_weighted_mismatch": weighted_mismatch,
        },
        "ok": (math.isclose(weight_sum, 1.0, abs_tol=1e-9)
               and math.isclose(old_six_sum, 0.85, abs_tol=1e-9)
               and model_consistent
               and not missing_columns and not bad_norm and ranks == list(range(1, len(ranks) + 1))
               and not inversions and not ties and not weighted_mismatch),
    }
    out.write_bytes(json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8"))
    print(json.dumps({key: payload[key] for key in
                      ("weight_sum", "weight_sum_ok", "old_six_sum", "old_six_sum_ok",
                       "sellability_weight", "model_consistent", "model_explicit_0_15",
                       "scores", "ok")},
                     ensure_ascii=False, indent=2)[:4000])
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
