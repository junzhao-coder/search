"""一周复盘：读 feedback-log.csv，算 4 个数字并给一条建议（纯标准库、只读）。

口径与 docs/validation/product-workflow/b24/FEEDBACK-CARD.md 一致：
  询单转化率 = 成交 ÷ 询单
  单件净利   = 单件到手 − 采购成本 − 售后摊销
  折算时薪   = 单件净利 ÷ (人工耗时分钟 ÷ 60)
  退款率     = 退款 ÷ 成交

用法：
  python review.py feedback-log.csv            # 人类可读摘要
  python review.py feedback-log.csv --json     # 结构化输出
  python review.py feedback-log.csv --cost 5 --aftersales 1 --min-conv 20 --min-hourly 30 --max-refund 20

退出码：0＝全部行可解析；2＝存在非数字行（仍会打印已解析结果摘要）。
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

# ---------------------------------------------------------------- 可调阈值与常量
THRESHOLD_MIN_CONVERSION_PCT = 20.0   # 询单转化率低于此值 → 详情/价格没说服力
THRESHOLD_MIN_HOURLY_CNY = 30.0       # 折算时薪低于此值 → 提价或标准化交付
THRESHOLD_MAX_REFUND_PCT = 20.0       # 退款率高于此值 → 先修描述与交付

DEFAULT_COST_PER_UNIT = 0.0           # 采购成本（元/件）：CSV 未提供，默认 0 并注明
DEFAULT_AFTERSALES_PER_UNIT = 0.0     # 售后摊销（元/件）：CSV 未提供，默认 0 并注明

NA_TOKENS = {"", "na", "n/a", "n.a.", "-", "--", "none", "null", "nan", "无"}

FIELDS = ["日期", "单号", "渠道", "曝光", "询单", "成交", "退款",
          "实际售价", "到手", "人工耗时分钟", "交付方式", "备注"]
NUMERIC_OPTIONAL = ["曝光", "实际售价", "到手"]
NUMERIC_REQUIRED = ["询单", "成交", "退款", "人工耗时分钟"]

# 英文/常见别名 → 中文列名（表头会自动映射；README 有完整映射表）
HEADER_ALIASES = {
    "date": "日期", "day": "日期",
    "workorder_id": "单号", "workorder": "单号", "wo": "单号", "order_id": "单号",
    "channel": "渠道", "platform": "渠道",
    "impressions": "曝光", "views": "曝光",
    "inquiries": "询单", "leads": "询单",
    "orders": "成交", "sales": "成交", "sold": "成交",
    "refunds": "退款",
    "actual_price_cny": "实际售价", "actual_price": "实际售价", "price": "实际售价",
    "net_received_cny": "到手", "net_received": "到手", "received": "到手",
    "manual_minutes": "人工耗时分钟", "minutes": "人工耗时分钟", "labor_minutes": "人工耗时分钟",
    "delivery": "交付方式",
    "note": "备注", "notes": "备注", "remark": "备注",
}
HEADER_EXAMPLE = "日期,单号,渠道,曝光,询单,成交,退款,实际售价,到手,人工耗时分钟,交付方式,备注"

INSUFFICIENT = "样本不足，保留观察期"
LABEL_CONTINUE = "继续"
LABEL_PRICE_UP = "提价"
LABEL_CHANGE_ITEM = "换品"
LABEL_FIX_DESC = "修描述"


def is_na(value) -> bool:
    return str(value if value is not None else "").strip().lower() in NA_TOKENS


def parse_number(raw, field: str, line_no: int, errors: list) -> float | None:
    """解析数值：na/空 → None（跳过）；非数字 → 记录错误并返回 None。"""
    if is_na(raw):
        return None
    text = str(raw).strip().replace(",", "").replace("，", "")
    try:
        return float(text)
    except (TypeError, ValueError):
        errors.append({"line": line_no, "field": field, "value": str(raw), "error": "不是数字，也不是 na"})
        return None


def parse_rows(path: Path):
    """读 CSV：自动把英文/别名单映射为中文列名；缺列时给出可复制的修正建议。"""
    rows, errors = [], []
    header_info: dict = {"detected": [], "mapped": {}, "missing": []}
    with path.open(encoding="utf-8-sig", newline="") as fh:
        raw_rows = list(csv.reader(fh))
    if not raw_rows:
        errors.append({"line": 1, "field": "header", "value": "", "error": "文件为空（缺少表头）"})
        return rows, errors, header_info
    detected = [h.strip() for h in raw_rows[0]]
    mapped = {h: HEADER_ALIASES.get(h.strip().lower(), h.strip()) for h in detected}
    header_info = {"detected": detected, "mapped": {k: v for k, v in mapped.items() if k != v}, "missing": []}
    normalized = [mapped[h] for h in detected]
    missing = [f for f in FIELDS if f not in normalized]
    header_info["missing"] = missing
    if missing:
        errors.append({"line": 1, "field": ",".join(missing), "value": "",
                       "error": "表头缺字段",
                       "detected_header": detected,
                       "expected_header": FIELDS,
                       "suggestion": f"改成这行表头即可：{HEADER_EXAMPLE}（英文表头也支持，映射见 README）"})
    for line_no, values in enumerate(raw_rows[1:], start=2):
        if not any((v or "").strip() for v in values):
            continue
        raw = {normalized[i]: (values[i] if i < len(values) else "") for i in range(len(normalized))}
        item = {"line": line_no, "日期": raw.get("日期", ""), "单号": raw.get("单号", ""), "渠道": raw.get("渠道", "")}
        for field in NUMERIC_OPTIONAL + NUMERIC_REQUIRED:
            item[field] = parse_number(raw.get(field), field, line_no, errors)
        item["交付方式"] = raw.get("交付方式", "")
        item["备注"] = raw.get("备注", "")
        item["_raw"] = raw
        rows.append(item)
    return rows, errors, header_info


def aggregate(rows: list) -> dict:
    def total(field):
        vals = [r[field] for r in rows if r.get(field) is not None]
        return sum(vals) if vals else None

    return {
        "行数": len(rows),
        "询单合计": total("询单"),
        "成交合计": total("成交"),
        "退款合计": total("退款"),
        "到手合计": total("到手"),
        "耗时合计分钟": total("人工耗时分钟"),
    }


def compute_metrics(totals: dict, cost_per_unit: float, aftersales_per_unit: float) -> dict:
    inquiries = totals["询单合计"]
    orders = totals["成交合计"]
    refunds = totals["退款合计"]
    gross = totals["到手合计"]
    minutes = totals["耗时合计分钟"]

    conversion = (orders / inquiries * 100.0) if (inquiries and orders is not None and inquiries > 0) else None
    unit_gross = (gross / orders) if (gross is not None and orders and orders > 0) else None
    unit_net = (unit_gross - cost_per_unit - aftersales_per_unit) if unit_gross is not None else None
    hourly = (unit_net / (minutes / 60.0)) if (unit_net is not None and minutes and minutes > 0) else None
    refund_rate = (refunds / orders * 100.0) if (refunds is not None and orders and orders > 0) else None

    return {
        "询单转化率%": round(conversion, 2) if conversion is not None else None,
        "单件到手元": round(unit_gross, 2) if unit_gross is not None else None,
        "单件净利元": round(unit_net, 2) if unit_net is not None else None,
        "折算时薪元": round(hourly, 2) if hourly is not None else None,
        "退款率%": round(refund_rate, 2) if refund_rate is not None else None,
    }


def recommend(totals: dict, metrics: dict, thresholds: dict) -> dict:
    orders = totals["成交合计"]
    minutes = totals["耗时合计分钟"]
    conversion = metrics["询单转化率%"]
    unit_net = metrics["单件净利元"]
    hourly = metrics["折算时薪元"]
    refund_rate = metrics["退款率%"]
    all_none = all(metrics[k] is None for k in ("询单转化率%", "单件净利元", "折算时薪元", "退款率%"))

    if not orders or orders <= 0 or not minutes or minutes <= 0 or all_none:
        return {"label": INSUFFICIENT, "reasons": [
            f"成交={orders if orders is not None else 'na'}，人工耗时={minutes if minutes is not None else 'na'}，"
            f"或四指标全为 na —— 样本不足，先保留观察期（建议至少 7 天）再判断。"]}

    if unit_net is not None and unit_net <= 0:
        return {"label": LABEL_CHANGE_ITEM, "reasons": [
            f"单件净利 {unit_net} 元 ≤ 0：先换品或换货源，别再投入改文案与降价。"]}

    if refund_rate is not None and refund_rate > thresholds["max_refund"]:
        return {"label": LABEL_FIX_DESC, "reasons": [
            f"退款率 {refund_rate}% > {thresholds['max_refund']}%：先修描述与交付（写清包含/不包含、交付方式与售后），不要靠降价掩盖。"]}

    if conversion is not None and conversion < thresholds["min_conv"]:
        return {"label": LABEL_FIX_DESC, "reasons": [
            f"询单转化率 {conversion}% < {thresholds['min_conv']}%（且询单>0）：买家问了但没下单，先改详情与价格说明。"]}

    if hourly is not None and hourly < thresholds["min_hourly"] and (unit_net is not None and unit_net > 0):
        return {"label": LABEL_PRICE_UP, "reasons": [
            f"折算时薪 {hourly} 元 < {thresholds['min_hourly']} 元/小时，但单件净利仍为正：提价，或把交付标准化（模板化/自助化）来压缩耗时。"]}

    return {"label": LABEL_CONTINUE, "reasons": ["四项指标都没触发阈值：维持当前做法，继续记录下一个观察期。"]}


def build_result(csv_path: Path, rows, errors, cost, aftersales, thresholds) -> dict:
    totals = aggregate(rows)
    metrics = compute_metrics(totals, cost, aftersales)
    rec = recommend(totals, metrics, thresholds)
    return {
        "csv": str(csv_path),
        "rows_parsed": len(rows),
        "rows_total": len(rows) + len({e["line"] for e in errors if e["line"] > 1}),
        "assumptions": {
            "采购成本元每件": cost,
            "售后摊销元每件": aftersales,
            "采购与摊销来源": "CSV 无这两列，用命令参数（缺省 0）",
            "单件到手口径": "到手合计 ÷ 成交合计",
            "时薪口径": "单件净利 ÷ (人工耗时分钟 ÷ 60)",
            "阈值": thresholds,
        },
        "totals": totals,
        "metrics": metrics,
        "recommendation": rec,
        "errors": errors,
    }


def print_human(result: dict) -> None:
    m, t, rec = result["metrics"], result["totals"], result["recommendation"]
    a = result["assumptions"]
    fmt = lambda v, unit="": ("na" if v is None else f"{v}{unit}")
    print("=== 一周复盘（4 个数字） ===")
    print(f"读入：{result['csv']}  行数：{result['rows_parsed']}（无法解析的行：{len({e['line'] for e in result['errors'] if e['line'] > 1})}）")
    print(f"合计：询单 {fmt(t['询单合计'])} / 成交 {fmt(t['成交合计'])} / 退款 {fmt(t['退款合计'])} / "
          f"到手 {fmt(t['到手合计'], ' 元')} / 耗时 {fmt(t['耗时合计分钟'], ' 分钟')}")
    print("--- 4 个指标 ---")
    print(f"1) 询单转化率      {fmt(m['询单转化率%'], ' %')}   = 成交 ÷ 询单")
    print(f"2) 单件净利        {fmt(m['单件净利元'], ' 元')}   = 单件到手 {fmt(m['单件到手元'], ' 元')} − 采购 {a['采购成本元每件']} − 售后摊销 {a['售后摊销元每件']}")
    print(f"3) 折算时薪        {fmt(m['折算时薪元'], ' 元/小时')} = 单件净利 ÷ (人工耗时 ÷ 60)")
    print(f"4) 退款率          {fmt(m['退款率%'], ' %')}   = 退款 ÷ 成交")
    print("--- 建议（四选一） ---")
    print(f"【{rec['label']}】")
    for reason in rec["reasons"]:
        print(f"  依据：{reason}")
    print("--- 假设与阈值（可改） ---")
    print(f"  采购成本 {a['采购成本元每件']} 元/件、售后摊销 {a['售后摊销元每件']} 元/件（{a['采购与摊销来源']}）")
    print(f"  阈值：转化率 <{a['阈值']['min_conv']}%、时薪 <{a['阈值']['min_hourly']} 元/小时、退款率 >{a['阈值']['max_refund']}%"
          f"（脚本顶部常量或命令行参数可调）")
    if result["errors"]:
        print("--- 解析错误（这些行未计入） ---")
        for e in result["errors"]:
            print(f"  第 {e['line']} 行 字段「{e['field']}」值「{e['value']}」：{e['error']}")
            if e.get("detected_header"):
                print(f"    检测到的表头：{','.join(e['detected_header'])}")
                print(f"    期望的表头（可直接复制）：{HEADER_EXAMPLE}")
                print(f"    修正建议：{e.get('suggestion', '')}")
    mapped = (result.get("header") or {}).get("mapped") or {}
    if mapped:
        pairs = "；".join(f"{k}→{v}" for k, v in mapped.items())
        print(f"--- 表头别名已自动映射：{pairs} ---")
    print("退出码：0＝全部行可解析；2＝存在表头缺列或非数字行（仍会打印已解析结果摘要）。")
    print("提示：以上是按你填的数据做的机械建议，不等于平台结论，也不代表收益或审核结果。")


def main(argv: list | None = None) -> int:
    ap = argparse.ArgumentParser(description="一周复盘：算 4 个数字并给一条建议（只读 CSV）")
    ap.add_argument("csv", help="feedback-log.csv 路径")
    ap.add_argument("--json", action="store_true", help="输出结构化 JSON")
    ap.add_argument("--cost", type=float, default=DEFAULT_COST_PER_UNIT, help="采购成本（元/件），默认 0")
    ap.add_argument("--aftersales", type=float, default=DEFAULT_AFTERSALES_PER_UNIT, help="售后摊销（元/件），默认 0")
    ap.add_argument("--min-conv", type=float, default=THRESHOLD_MIN_CONVERSION_PCT, help="转化率阈值（%%），默认 20")
    ap.add_argument("--min-hourly", type=float, default=THRESHOLD_MIN_HOURLY_CNY, help="时薪阈值（元/小时），默认 30")
    ap.add_argument("--max-refund", type=float, default=THRESHOLD_MAX_REFUND_PCT, help="退款率阈值（%%），默认 20")
    args = ap.parse_args(argv)

    path = Path(args.csv)
    if not path.is_file():
        payload = {"csv": str(path), "error": f"文件不存在：{path}", "metrics": None,
                   "recommendation": {"label": INSUFFICIENT, "reasons": ["CSV 文件不存在，无法复盘"]}, "errors": [
                       {"line": 0, "field": "csv", "value": str(path), "error": "文件不存在"}]}
        print(json.dumps(payload, ensure_ascii=False, indent=2) if args.json else payload["error"], file=sys.stdout)
        return 2

    thresholds = {"min_conv": args.min_conv, "min_hourly": args.min_hourly, "max_refund": args.max_refund}
    rows, errors, header_info = parse_rows(path)
    result = build_result(path, rows, errors, args.cost, args.aftersales, thresholds)
    result["header"] = header_info

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print_human(result)
    return 2 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
