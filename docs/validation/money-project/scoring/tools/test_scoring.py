#!/usr/bin/env python
"""Small deterministic checks for scorer.py (stdlib only)."""

import copy
import json
import pathlib
import sys

BASE = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))
import scorer  # noqa: E402


def main() -> int:
    items = [json.loads(line) for line in (BASE / "items.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    rows = scorer.score_items(items)
    assert len(rows) == len(items) == 60
    assert [row["rank"] for row in rows] == list(range(1, len(items) + 1))
    assert all(rows[i]["total_score"] >= rows[i + 1]["total_score"] for i in range(len(rows) - 1))

    probe = copy.deepcopy(items[0])
    probe["metrics"] = {"source": "unit-test", "demand_raw": None, "demand_basis": "missing", "raw": {}}
    missing_row = scorer.score_items([probe])[0]
    assert missing_row["demand_norm"] is None
    assert "demand_strength" in missing_row["missing_metrics"]
    assert abs(missing_row["weight_coverage"] - 0.745) < 1e-9
    assert "sellability_norm" in missing_row and 0.0 <= missing_row["sellability_norm"] <= 1.0
    print("OK items=60 ranks=1..60 sorted=True missing_demand_coverage=0.745")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
