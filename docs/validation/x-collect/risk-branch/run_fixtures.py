#!/usr/bin/env python
"""Run structured-signal risk fixtures against x_collect.risk_from_signals."""

import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
TOOL = pathlib.Path(r"C:\Users\19183\.dsh\tools\x-collect\scripts")
sys.path.insert(0, str(TOOL))

import x_collect as xc  # noqa: E402


def main() -> int:
    cases = json.loads((HERE / "fixtures" / "cases.json").read_text(encoding="utf-8"))["cases"]
    results = []
    ok = True
    for case in cases:
        html_path = HERE / "fixtures" / case["html"]
        actual = bool(xc.risk_from_signals(case["signals"]))
        passed = actual == bool(case["expected"])
        ok = ok and passed
        results.append({
            "id": case["id"],
            "html": case["html"],
            "html_exists": html_path.exists(),
            "signals": case["signals"],
            "expected_risk": bool(case["expected"]),
            "actual_risk": actual,
            "passed": passed,
        })
        print(f"{case['id']:<26} expected={case['expected']!s:<5} actual={actual!s:<5} "
              f"html_exists={html_path.exists()}")
    (HERE / "fixtures_results.json").write_text(
        json.dumps({"all_passed": ok, "count": len(results), "results": results},
                   ensure_ascii=False, indent=1),
        encoding="utf-8", newline="\n")
    print(f"ALL_PASSED={ok} count={len(results)}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
