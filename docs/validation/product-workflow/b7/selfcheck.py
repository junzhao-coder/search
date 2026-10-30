"""自检：读取生成的 xlsx，断言结构/公式/无外链/无图片/无宏，并写出 selfcheck.json。

只读生成文件，不改它。
"""

from __future__ import annotations

import json
import pathlib
import time
import zipfile

from openpyxl import load_workbook

B7 = pathlib.Path(r"D:\桌面\two\docs\validation\product-workflow\b7")
XLSX = B7 / "sample-study-planner-v1.xlsx"
OUT = B7 / "selfcheck.json"

EXPECTED_SHEETS = ["使用说明", "课程与考试", "考试倒计时", "周计划", "复习进度"]

checks: list[dict] = []


def check(cid: str, ok: bool, detail: str = "") -> bool:
    checks.append({"id": cid, "ok": bool(ok), "detail": detail})
    print(f"[{'PASS' if ok else 'FAIL'}] {cid} {detail}")
    return bool(ok)


def main() -> int:
    wb = load_workbook(XLSX, data_only=False)
    with zipfile.ZipFile(XLSX) as zf:
        names = zf.namelist()

    check("01-sheet-names-exact", wb.sheetnames == EXPECTED_SHEETS, f"sheets={wb.sheetnames}")
    check("02-sheet-count", len(wb.sheetnames) >= 5, f"count={len(wb.sheetnames)}")

    formulas: list[tuple[str, str, str]] = []
    for ws in wb.worksheets:
        for row in ws.iter_rows():
            for cell in row:
                if isinstance(cell.value, str) and cell.value.startswith("="):
                    formulas.append((ws.title, cell.coordinate, cell.value))
    check("03-formula-count>=10", len(formulas) >= 10, f"formulas={len(formulas)}")

    keys = {
        "TODAY": sum(1 for _s, _c, f in formulas if "TODAY()" in f),
        "COUNTIF": sum(1 for _s, _c, f in formulas if "COUNTIF(" in f),
        "IF": sum(1 for _s, _c, f in formulas if f.startswith("=IF") or "IF(" in f),
        "SUM": sum(1 for _s, _c, f in formulas if "SUM(" in f),
        "COUNTA": sum(1 for _s, _c, f in formulas if "COUNTA(" in f),
        "COUNT": sum(1 for _s, _c, f in formulas if "COUNT(" in f and "COUNTA(" not in f and "COUNTIF(" not in f),
        "AVERAGE": sum(1 for _s, _c, f in formulas if "AVERAGE(" in f),
    }
    check("04-key-functions-present", all(keys[k] > 0 for k in ("TODAY", "COUNTIF", "IF", "SUM", "COUNTA", "AVERAGE")), str(keys))

    ext_attr = list(getattr(wb, "_external_links", []) or [])
    check("05-no-external-links-object", len(ext_attr) == 0, f"_external_links={len(ext_attr)}")
    ext_parts = [n for n in names if "externalLink" in n or n.startswith("xl/externalLinks")]
    check("06-no-external-links-parts", len(ext_parts) == 0, f"parts={ext_parts}")

    img_counts = {ws.title: len(getattr(ws, "_images", []) or []) for ws in wb.worksheets}
    chart_counts = {ws.title: len(getattr(ws, "_charts", []) or []) for ws in wb.worksheets}
    check("07-no-images", all(v == 0 for v in img_counts.values()), f"images={img_counts}")
    check("08-no-charts", all(v == 0 for v in chart_counts.values()), f"charts={chart_counts}")
    drawings = [n for n in names if n.startswith("xl/drawings") or n.startswith("xl/media")]
    check("09-no-drawing-media-parts", len(drawings) == 0, f"parts={drawings}")

    macros = [n for n in names if "vbaProject" in n or n.endswith(".bin")]
    check("10-no-macros", len(macros) == 0, f"macro_parts={macros}")

    cf = {ws.title: len(ws.conditional_formatting._cf_rules) if hasattr(ws.conditional_formatting, "_cf_rules") else 0
          for ws in wb.worksheets}
    total_cf = sum(len(list(ws.conditional_formatting)) for ws in wb.worksheets)
    check("11-conditional-formatting", total_cf >= 3, f"ranges={total_cf}")

    dv_total = sum(len(ws.data_validations.dataValidation) for ws in wb.worksheets)
    check("12-data-validation", dv_total >= 1, f"validations={dv_total}")

    areas = {ws.title: str(ws.print_area) if ws.print_area else None for ws in wb.worksheets}
    check("13-print-areas-set", all(areas.values()), f"areas={areas}")
    week = wb["周计划"]
    check("14-week-a4-portrait", week.page_setup.orientation == "portrait" and str(week.page_setup.paperSize) == "9",
          f"orientation={week.page_setup.orientation} paper={week.page_setup.paperSize}")
    frozen = {ws.title: ws.freeze_panes for ws in wb.worksheets}
    check("15-freeze-first-row", all(frozen[t] for t in ("课程与考试", "考试倒计时", "周计划", "复习进度")), f"frozen={frozen}")

    fonts = sorted({(cell.font.name or "") for ws in wb.worksheets for row in ws.iter_rows() for cell in row
                    if cell.value is not None})
    check("16-fonts-system-only", set(fonts) <= {"宋体", "Calibri", ""}, f"fonts={fonts}")

    size = XLSX.stat().st_size
    check("17-size-reasonable", size < 200_000, f"bytes={size}")

    payload = {
        "utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "file": XLSX.name,
        "bytes": size,
        "sheets": wb.sheetnames,
        "formula_count": len(formulas),
        "functions": keys,
        "formula_samples": [{"sheet": s, "cell": c, "formula": f} for s, c, f in formulas[:12]],
        "external_links": {"_external_links": len(ext_attr), "parts": ext_parts},
        "images": img_counts,
        "charts": chart_counts,
        "drawings_or_media_parts": drawings,
        "macro_parts": macros,
        "conditional_formatting_ranges": total_cf,
        "data_validations": dv_total,
        "print_areas": areas,
        "freeze_panes": frozen,
        "fonts": fonts,
        "checks": checks,
        "failed": [c for c in checks if not c["ok"]],
        "verdict": "PASS" if all(c["ok"] for c in checks) else "FAIL",
    }
    OUT.write_bytes((json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
    print(f"checks={len(checks)} failed={len(payload['failed'])} verdict={payload['verdict']}")
    print(f"wrote {OUT}")
    return 0 if payload["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
