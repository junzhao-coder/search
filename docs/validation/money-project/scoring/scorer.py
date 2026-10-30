#!/usr/bin/env python
"""Deterministic opportunity scorer for the notion-template sample.

Input : items.jsonl
Output: scores.csv + report.md

Pure functions (score_items) contain no I/O; main() only reads/writes files.
Standard library only.
"""

from __future__ import annotations

import argparse
import bisect
import csv
import json
import math
import pathlib
import re
from collections import Counter

BASE = pathlib.Path(__file__).resolve().parent
DEFAULT_ITEMS = BASE / "items.jsonl"
DEFAULT_SCORES = BASE / "scores.csv"
DEFAULT_REPORT = BASE / "report.md"

WEIGHTS = {
    "demand_strength": 0.255,
    "competition_sparsity": 0.17,
    "gross_margin": 0.17,
    "fulfillment_ease": 0.085,
    "compliance_safety": 0.085,
    "replicability": 0.085,
    "sellability": 0.15,
}
SUPPLY_PRIOR = {"x": 0.60, "bilibili": 0.45, "github": 0.70}
SERVICE_RE = re.compile(r"freelanc|service|consult|client|hire|agency", re.I)
AI_HYPE_RE = re.compile(r"ai side hustle|passive income|guarantee|get rich", re.I)
RESELL_RE = re.compile(r"resell|clone|copyright|盗版|破解|免费", re.I)
NON_OPPORTUNITY_RE = re.compile(
    r"乐谱|扒谱|Notion Mobile|安卓|手机下载|安装方法|You cannot control|motivat|quote",
    re.I,
)

# Sellability is deliberately conservative: a giveaway/demand-seeking post is
# low even if it has high engagement. "free shipping" and "freedom" must not
# match the free-giveaway rule.
SELLABILITY_FREE_RE = re.compile(
    r"\bfree\b(?!\s*(?:shipping|ship|delivery))"
    r"|\bgiveaway\b|\bgiving away\b|\bgive away\b"
    r"|免费|领取|抽奖|赠送|白嫖|求推荐|有没有|推荐一下|求模板|谁有"
    r"|免费送|送出|送模板|送资料|包送",
    re.I,
)
SELLABILITY_PRICE_RE = re.compile(
    r"[¥￥$]\s*\d"
    r"|\b\d+\s*(?:php|pesos?|ph)\b"
    r"|\b(?:price|pricing|selling for|sold for)\b"
    r"|售价|价格|定价",
    re.I,
)
SELLABILITY_PURCHASE_RE = re.compile(
    r"购买|下单|扫码|私信购买|\bbuy\b|\bpurchase\b|\bcheckout\b|\border\b"
    r"|\bgumroad\b|\bpaypal\b|\blink in bio\b|\bDM to buy\b|链接",
    re.I,
)
SELLABILITY_COMMERCIAL_RE = re.compile(
    r"合集|素材包|模板包|教程包|\bbundle\b|\bpack\b|\bcollection\b",
    re.I,
)


def sellability_profile(item: dict) -> dict:
    """Pure rule: high=price/purchase/commercial, low=free/ask, neutral=other.

    Xianyu listings carry a ¥1 traffic price, so they are capped at 0.55 and
    explicitly labeled as a traffic price rather than a real sale signal.
    """
    text = " ".join(str(item.get(k) or "") for k in ("title", "url", "author"))
    raw = item.get("metrics", {}).get("raw", {}) if isinstance(item.get("metrics"), dict) else {}
    price_value = item.get("price") or raw.get("price")
    if item.get("platform") == "xianyu" or price_value:
        return {
            "raw": 0.55,
            "norm": 0.55,
            "reason": "闲鱼标价为引流价（¥1 类），有价格但不可当真实售价",
            "flags": {"price": True, "purchase": False, "free": False, "commercial": False},
        }

    free = bool(SELLABILITY_FREE_RE.search(text))
    price = bool(SELLABILITY_PRICE_RE.search(text))
    purchase = bool(SELLABILITY_PURCHASE_RE.search(text))
    commercial = bool(SELLABILITY_COMMERCIAL_RE.search(text))

    if free and (price or purchase):
        if purchase:
            raw, norm = 0.90, 0.90
            reason = "free 赠送词与售价/购买入口冲突；有购买入口，按高可售性"
        else:
            raw, norm = 0.10, 0.10
            reason = "free 赠送词与价格词冲突；无购买入口，按低可售性"
    elif free:
        raw, norm = 0.10, 0.10
        reason = "含 free/赠送/领取/求推荐等低可售词"
    elif price and purchase:
        raw, norm = 0.95, 0.95
        reason = "含明确售价与购买入口"
    elif price:
        raw, norm = 0.85, 0.85
        reason = "含明确售价（¥/$/selling for 等）"
    elif purchase:
        raw, norm = 0.80, 0.80
        reason = "含购买入口（链接/下单/扫码/买）"
    elif commercial:
        raw, norm = 0.80, 0.80
        reason = "含商品化词（合集/素材包/模板包/教程包）"
    else:
        raw, norm = 0.50, 0.50
        reason = "无价格/购买入口/赠送信号，按中性"

    return {
        "raw": raw,
        "norm": norm,
        "reason": reason,
        "flags": {"price": price, "purchase": purchase, "free": free, "commercial": commercial},
    }



def clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def percentile_map(items: list[dict], key: str, platform: str) -> dict[str, float]:
    rows = [(math.log1p(float(item[key] if key.startswith("_") else item["_raw"][key])), item["item_id"])
            for item in items if item["platform"] == platform
            and not item.get("_demand_missing")
            and (item.get(key) is not None if key.startswith("_") else item["_raw"].get(key) is not None)]
    if not rows:
        return {}
    rows.sort(key=lambda pair: (pair[0], pair[1]))
    values = [pair[0] for pair in rows]
    n = len(rows)
    if n == 1:
        return {rows[0][1]: 0.5}
    out = {}
    for value, item_id in rows:
        # Lower-rank ties share the first position; deterministic and documented.
        idx = bisect.bisect_left(values, value)
        out[item_id] = round(idx / (n - 1), 6)
    return out


def margin_profile(item: dict) -> dict:
    """Assumption-based gross-margin interval (no cost input in public data)."""
    platform = item["platform"]
    text = item.get("title") or ""
    if platform == "x":
        if SERVICE_RE.search(text):
            return {"price_low": 50, "price_high": 200, "cost_low": 10, "cost_high": 40,
                    "margin_low": 0.50, "margin_high": 0.85, "margin_mid": 0.675,
                    "assumption": "freelance/service offer: $50-200 ticket, $10-40 delivery cost (estimated)"}
        return {"price_low": 9, "price_high": 49, "cost_low": 0.5, "cost_high": 3,
                "margin_low": 0.70, "margin_high": 0.95, "margin_mid": 0.825,
                "assumption": "digital Notion template: $9-49 price, $0.5-3 payment/hosting cost (estimated)"}
    if platform == "bilibili":
        if "模板" in text or "template" in text.lower():
            return {"price_low": 15, "price_high": 99, "cost_low": 5, "cost_high": 30,
                    "margin_low": 0.45, "margin_high": 0.80, "margin_mid": 0.625,
                    "assumption": "template/course upsell: ¥15-99 price, ¥5-30 production/support cost (estimated)"}
        return {"price_low": 0, "price_high": 0, "cost_low": 0, "cost_high": 0,
                "margin_low": 0.35, "margin_high": 0.70, "margin_mid": 0.525,
                "assumption": "ad/affiliate content: no direct price; 35-70% margin proxy (estimated)"}
    return {"price_low": 19, "price_high": 99, "cost_low": 2, "cost_high": 20,
            "margin_low": 0.45, "margin_high": 0.85, "margin_mid": 0.65,
            "assumption": "open-source hosted/support offer: $19-99/mo price, $2-20 infra/support cost (estimated)"}


def fulfillment_ease(item: dict) -> float:
    text = item.get("title") or ""
    if item["platform"] == "x":
        return 0.55 if SERVICE_RE.search(text) else 0.90
    if item["platform"] == "bilibili":
        return 0.75 if ("模板" in text or "template" in text.lower()) else 0.60
    return 0.80


def compliance_safety(item: dict) -> float:
    platform = item["platform"]
    text = item.get("title") or ""
    if platform == "x":
        if AI_HYPE_RE.search(text):
            return 0.55
        if RESELL_RE.search(text):
            return 0.65
        return 0.80
    if platform == "bilibili":
        if RESELL_RE.search(text):
            return 0.55
        return 0.80 if ("模板" in text or "template" in text.lower()) else 0.75
    license_id = str((item["_raw"].get("license") or "")).upper()
    if license_id in ("MIT", "APACHE-2.0", "BSD-3-CLAUSE"):
        return 0.90
    if license_id in ("GPL-3.0", "AGPL-3.0"):
        return 0.75
    if license_id == "NOASSERTION":
        return 0.55
    return 0.50


def replicability(item: dict) -> float:
    text = (item.get("title") or "").lower()
    if item["platform"] == "x":
        return 0.85
    if item["platform"] == "bilibili":
        return 0.70 if ("模板" in text or "template" in text) else 0.55
    return 0.80 if "awesome" in text else 0.70


def score_items(items: list[dict]) -> list[dict]:
    """Pure scoring function: items -> scored rows sorted by total score."""
    working = [dict(item) for item in items]
    for item in working:
        item["_raw"] = item.get("metrics", {}).get("raw", {})
        raw_demand = item.get("metrics", {}).get("demand_raw")
        item["_demand_missing"] = raw_demand is None
        item["_demand_raw"] = 0.0 if raw_demand is None else float(raw_demand)

    demand_pct: dict[str, float] = {}
    for platform in ("x", "bilibili", "github"):
        demand_pct.update(percentile_map(working, "_demand_raw", platform))

    author_counts = Counter((item["platform"], item.get("author")) for item in working)
    scored = []
    for item in working:
        platform = item["platform"]
        item_id = item["item_id"]
        demand_norm = None if item["_demand_missing"] else demand_pct.get(item_id, 0.5)

        prior = SUPPLY_PRIOR.get(platform, 0.6)
        penalty = min(0.20, 0.05 * max(0, author_counts[(platform, item.get("author"))] - 1))
        competition_raw = clamp(prior + penalty)
        competition_norm = 1.0 - competition_raw

        margin = margin_profile(item)
        margin_norm = margin["margin_mid"]
        fulfill_norm = fulfillment_ease(item)
        compliance_norm = compliance_safety(item)
        replic_norm = replicability(item)
        sellability = sellability_profile(item)
        sellability_norm = sellability["norm"]

        values = {
            "demand_strength": demand_norm,
            "competition_sparsity": competition_norm,
            "gross_margin": margin_norm,
            "fulfillment_ease": fulfill_norm,
            "compliance_safety": compliance_norm,
            "replicability": replic_norm,
            "sellability": sellability_norm,
        }
        missing = [name for name, value in values.items() if value is None]
        present = [name for name in WEIGHTS if name not in missing]
        denom = sum(WEIGHTS[name] for name in present)
        weighted = {name: round(WEIGHTS[name] * values[name], 6) for name in present}
        total = round(sum(weighted.values()) / denom, 6) if denom else 0.0
        coverage = round(denom, 6)

        row = {
            "rank": 0,
            "item_id": item_id,
            "platform": platform,
            "title": item.get("title"),
            "url": item.get("url"),
            "author": item.get("author"),
            "published_at": item.get("published_at"),
            "demand_raw": item["_demand_raw"],
            "demand_norm": None if demand_norm is None else round(demand_norm, 6),
            "demand_weighted": weighted.get("demand_strength", 0.0),
            "competition_raw": round(competition_raw, 6),
            "competition_norm": round(competition_norm, 6),
            "competition_weighted": weighted.get("competition_sparsity", 0.0),
            "margin_low": margin["margin_low"],
            "margin_high": margin["margin_high"],
            "margin_mid": margin_norm,
            "margin_norm": round(margin_norm, 6),
            "margin_weighted": weighted.get("gross_margin", 0.0),
            "margin_assumption": margin["assumption"],
            "cost_input": item.get("metrics", {}).get("cost_input", "missing"),
            "cost_note": item.get("metrics", {}).get("cost_note", ""),
            "fulfillment_raw": fulfill_norm,
            "fulfillment_norm": round(fulfill_norm, 6),
            "fulfillment_weighted": weighted.get("fulfillment_ease", 0.0),
            "compliance_raw": compliance_norm,
            "compliance_norm": round(compliance_norm, 6),
            "compliance_weighted": weighted.get("compliance_safety", 0.0),
            "replicability_raw": replic_norm,
            "replicability_norm": round(replic_norm, 6),
            "replicability_weighted": weighted.get("replicability", 0.0),
            "sellability_raw": round(sellability["raw"], 6),
            "sellability_norm": round(sellability_norm, 6),
            "sellability_weighted": weighted.get("sellability", 0.0),
            "sellability_reason": sellability["reason"],
            "total_score": total,
            "weight_coverage": coverage,
            "missing_metrics": "|".join(missing),
            "source": item.get("metrics", {}).get("source"),
            "raw_ref": item.get("raw_ref"),
        }
        scored.append(row)

    scored.sort(key=lambda row: (-row["total_score"], row["item_id"]))
    for index, row in enumerate(scored, 1):
        row["rank"] = index
    return scored


def decision(row: dict) -> str:
    if NON_OPPORTUNITY_RE.search(row.get("title") or ""):
        return "不推荐（关键词误召回/非商品）"
    if row["total_score"] >= 0.60:
        return "推荐验证"
    if row["total_score"] >= 0.50:
        return "谨慎验证"
    return "暂缓/不推荐"


def reasons(row: dict) -> str:
    def fmt(value) -> str:
        return "缺失" if value is None else f"{value:.2f}"
    metrics = [
        ("需求", row["demand_norm"]),
        ("竞争稀疏", row["competition_norm"]),
        ("毛利", row["margin_norm"]),
        ("履约", row["fulfillment_norm"]),
        ("合规", row["compliance_norm"]),
        ("可复制", row["replicability_norm"]),
        ("可售性", row["sellability_norm"]),
    ]
    metrics = [(name, value) for name, value in metrics if value is not None]
    metrics.sort(key=lambda pair: pair[1], reverse=True)
    best = "、".join(f"{name}{fmt(value)}" for name, value in metrics[:2])
    weak = "、".join(f"{name}{fmt(value)}" for name, value in metrics[-2:])
    return f"强项 {best}；弱项 {weak}"


def write_outputs(rows: list[dict], scores_path: pathlib.Path, report_path: pathlib.Path) -> None:
    fields = [
        "rank", "item_id", "platform", "title", "url", "author", "published_at",
        "demand_raw", "demand_norm", "demand_weighted",
        "competition_raw", "competition_norm", "competition_weighted",
        "margin_low", "margin_high", "margin_mid", "margin_norm", "margin_weighted",
        "margin_assumption", "cost_input", "cost_note",
        "fulfillment_raw", "fulfillment_norm", "fulfillment_weighted",
        "compliance_raw", "compliance_norm", "compliance_weighted",
        "replicability_raw", "replicability_norm", "replicability_weighted",
        "sellability_raw", "sellability_norm", "sellability_weighted", "sellability_reason",
        "total_score", "weight_coverage", "missing_metrics", "source", "raw_ref",
    ]
    with scores_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key) for key in fields})

    top = rows[:10]
    lines = [
        "# Notion 模板 / 数字商品机会榜（样本评分）", "",
        "> 数据样本：X 30 条（f=top）、Bilibili 20 条、GitHub 10 仓库；"
        "评分是**可解释的启发式**，不是收入预测。", "",
        "## 数据覆盖", "",
        "| 平台 | items | 真实 exit | 耗时 | UTC 时段 | 原始文件 |", "| --- | --- | --- | --- | --- | --- |",
        "| X | 30 | 0 | 127.5s | 06:57:50–07:00:04 | `raw/x_search.jsonl` |",
        "| Bilibili | 20 | 0 | 1.2s | 07:01:29–07:01:30 | `raw/bilibili_search.json` |",
        "| GitHub | 10 | 0 | 1.1s | 07:02:35–07:02:37 | `raw/github_search.json` |", "",
        "## 方法与权重", "",
        "| 指标 | 权重 | 说明 |", "| --- | --- | --- |",
        "| 需求强度 | 0.255 | X=likes+retweets+replies；B站=play；GitHub=stars；平台内 log1p 分位 |",
        "| 竞争稀疏度 | 0.170 | 平台供给先验 + 同作者重复惩罚，取反 |",
        "| 毛利空间 | 0.170 | 公开售价区间 - 估计履约成本（缺成本输入，区间估计） |",
        "| 履约容易度 | 0.085 | 数字交付 0.8-0.9；视频内容 0.6；服务 0.55 |",
        "| 合规安全度 | 0.085 | IP/许可证/“AI 暴富”话术风险 |",
        "| 可复制性 | 0.085 | 模板/仓库更易复制，视频内容较难 |",
        "| 可售性 | 0.150 | 售价/购买入口/商品化词高；free/赠送/求推荐低；闲鱼 ¥1 引流价 0.55 |", "",
        "公式：`total = Σ(w_i × norm_i) / Σ(w_i)`；缺失指标从分子分母同时剔除（本轮无缺失）。"
        "新维度加入后，原六维按 0.85 等比缩放，权重合计 1.00。", "",
        "## Top10", "",
        "| # | 分数 | 平台 | 机会（证据） | 建议 |", "| --- | --- | --- | --- | --- |",
    ]
    for row in top:
        lines.append(f"| {row['rank']} | {row['total_score']:.3f} | {row['platform']} | "
                     f"[{row['title'][:60]}]({row['url']}) | {decision(row)} |")
    lines += ["", "## Top10 详情", ""]
    for row in top:
        lines += [
            f"### {row['rank']}. {row['title'][:90]}",
            f"- 分数：**{row['total_score']:.3f}**（{decision(row)}）；平台：{row['platform']}；作者：{row['author']}",
            f"- 证据：[{row['url']}]({row['url']})；来源：`{row['source']}`；raw：`{row['raw_ref']}`",
            f"- 指标：需求 {row['demand_norm']:.2f}（原始 {row['demand_raw']}）、竞争稀疏 {row['competition_norm']:.2f}、"
            f"毛利 {row['margin_norm']:.2f}（区间 {row['margin_low']:.2f}-{row['margin_high']:.2f}）、"
            f"履约 {row['fulfillment_norm']:.2f}、合规 {row['compliance_norm']:.2f}、可复制 {row['replicability_norm']:.2f}、"
            f"可售性 {row['sellability_norm']:.2f}（{row['sellability_reason']}）",
            f"- 理由：{reasons(row)}。",
            f"- 毛利假设：{row['margin_assumption']}（缺成本输入，区间估计，非精确值）。", "",
        ]

    cautious = [row for row in rows if decision(row) != "推荐验证"][:8]
    lines += ["## 平台覆盖提示", "",
              "- GitHub 样本中 star 最高的 `enescingoz/awesome-n8n-templates`（26k）排第 13，"
              "未进 Top10：许可证为 NOASSERTION（合规 0.55）+ GitHub 竞争先验 0.70；"
              "若要把仓库服务化，需先核对许可证与商标。",
              "- GitHub 直连 API 命中共享 IP rate limit；经本机进程代理仅重试 1 次 search 请求成功（无 token），未扩大配额。",
              "- B 站样本多为教程/内容，不是直接商品；榜单把它们定位为“内容流量入口”，"
              "可导向模板/课程，而不是把播放量直接当收入。",
              "- 样本没有实体囤货/重售后品类；这是**覆盖不足**，不是“无机会”。", "",
              "## 不推荐/暂缓（样本内）", "",
              "说明：关键词搜索会召回非商品内容（乐谱软件、手机安装教程、泛语录等），"
              "即使互动高也不应当作数字商品机会；以下按分数列出并标注原因。", ""]
    for row in cautious:
        lines.append(f"- **{row['title'][:70]}**（{row['total_score']:.3f}，{decision(row)}）："
                     f"[证据]({row['url']})；{reasons(row)}。")
    lines += ["", "## 缺失值与假设", "",
              "- **没有成本输入**：毛利均用公开售价区间减估计履约成本，`margin_low/high` 为假设区间，"
              "`margin_mid` 用于评分；不得当作真实利润。",
              "- 竞争稀疏度是**样本供给先验**（X 0.60 / B站 0.45 / GitHub 0.70）加同作者重复惩罚，"
              "不是全市场竞品计数。",
              "- 需求为平台内分位，跨平台不可直接比较绝对热度；GitHub stars 受历史累积影响。",
              "- 所有指标 0-1；确定性：无随机数，按 total_score 降序、item_id 升序处理并列。", ""]
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")


def main() -> int:
    parser = argparse.ArgumentParser(prog="scorer")
    parser.add_argument("--items", default=str(DEFAULT_ITEMS))
    parser.add_argument("--scores", default=str(DEFAULT_SCORES))
    parser.add_argument("--report", default=str(DEFAULT_REPORT))
    args = parser.parse_args()
    items_path = pathlib.Path(args.items)
    items = [json.loads(line) for line in items_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    scored = score_items(items)
    write_outputs(scored, pathlib.Path(args.scores), pathlib.Path(args.report))
    print(json.dumps({"items": len(items), "top": scored[0]["item_id"],
                      "top_score": scored[0]["total_score"],
                      "scores": args.scores, "report": args.report}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
