"""生成可审计的产品分析画像：docs/validation/money-project/product-analysis/{profiles.json,model.md}。

只读 scoring/scores.csv 与 sourcing/price_signals.csv，调用 tools/workbench/analysis.py 的纯函数。
不联网、不调用模型、不写其它目录。
"""

from __future__ import annotations

import csv
import hashlib
import json
import pathlib
import sys
import time

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))

from analysis import INTENT_META, build_analysis  # noqa: E402
from groups import build_groups  # noqa: E402
from taxonomy import build_categories, summarize_conservation  # noqa: E402
from textindex import build_text_index  # noqa: E402

SCORES = ROOT / "docs" / "validation" / "money-project" / "scoring" / "scores.csv"
PRICES = ROOT / "docs" / "validation" / "money-project" / "sourcing" / "price_signals.csv"
SOURCES = ROOT / "docs" / "validation" / "money-project" / "sourcing" / "sources.csv"
OUT_TAX = ROOT / "docs" / "validation" / "money-project" / "product-taxonomy"
OUT = ROOT / "docs" / "validation" / "money-project" / "product-analysis"


def read_csv(path: pathlib.Path) -> list[dict]:
    with path.open(encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def price_stats(rows: list[dict]) -> dict:
    values = []
    for row in rows:
        try:
            values.append(float(row.get("effective_price")))
        except (TypeError, ValueError):
            continue
    return {"count": len(rows),
            "effective_min": round(min(values), 2) if values else None,
            "effective_max": round(max(values), 2) if values else None}


MODEL_MD = """# 产品分析生成规则（可审计，rev2 意图优先）

> 目的：把原始推文标题转成「产品是什么 / 为什么选它 / 有什么风险」。
> **不调用外部模型、不联网、不臆造数字**；文案只由 `scoring/scores.csv` 的字段确定性拼接。

## 1. 先判生意形态（intent），再判载体

| 优先级 | 生意形态 | 命中意图词（不区分大小写） | 目标人群 | 交付形态 |
| --- | --- | --- | --- | --- |
| 1 | 学习或生活规划模板 | class / course / student / school / study / notes / planner / tracker / habit / goal / budget / meal / workout / travel | 学生 | 学习/生活规划模板（可复制的页面或文档） |
| 2 | 求职简历资料 | cv / resume / job / internship / lamaran / apply / interview | 求职者 | 简历·求职排版与投递资料（可编辑文件） |
| 3 | 设计素材 | portfolio / design / psd / figma / ui kit | 设计师 | 设计素材包（PSD / Figma 源文件） |
| 4 | 提示词或数字包 | prompt / pack / bundle / gumroad / checkout / buy / sell | 内容创作者 | 提示词/数字包（文本库、模板包或下载文件） |
| 5 | 教学内容 | teaching / tutorial / guide / how to / import / setup | 教师 | 图文或视频教程（内容型交付） |
| 6 | 未分类 | 以上都不命中 | **人群未明确** | 待确认（需人工打开原始链接判断） |

**载体不是类型**：`notion` 只在 positioning 末尾追加 `；载体为 Notion 模板（可复制到自己的工作区）`，不参与类型判定。
**未分类条目改用「商业形态 + 需求档」区分**（不得同一句）：
- 商业形态：`可售`（`sellability_norm ≥ 0.8`）/ `免费引流`（`≤ 0.2`）/ `无价格信号`（其余，含字段缺失）
- 需求档：`高`（`demand_norm ≥ 0.7`）/ `中`（`0.4 ≤ x < 0.7`）/ `低`（`< 0.4`）/ `需求未评估`（缺失）
- 句式：`<商业形态>（可售性 NN / 无价格信号）的<需求档>需求线索（需求分位 NN%），品类待确认，需人工打开原始链接判断交付形态` + 载体尾巴；句子内嵌真实数值，保证各行不同。

## 2. 选择理由（最多 3 条，按固定优先级，必须挂真实数值）

优先级：`需求分位 > 可售性 > 毛利 > 竞争稀疏 > 综合评分`；仅在字段存在时生成。

- 需求：`需求位于本平台样本第 X% 分位（平台内百分位，原始需求值 N）` ← `demand_norm` / `demand_raw`
- 可售性：`可售性 NN（较强售卖|低信号|不明确）：<sellability_reason 原文>` ← `sellability_norm` / `sellability_reason`
- 毛利：`毛利估算 X%（，区间 A%–B%）（模型假设；价格信号 N 条样本（有效价 min–max））` ← `margin_mid/low/high` + `price_signals`
- 竞争：`竞争稀疏度 X%（平台供给先验 + 同作者惩罚）` ← `competition_norm`
- 评分：`综合评分 0.xxx（加权合计）` ← `total_score`

## 3. 主要风险（逐行差异化，每行 ≤2 条，仅字段支持时出现）

| 严重度 | 触发条件（严格） | 文案 |
| --- | --- | --- |
| 0.0 | `sellability_norm` 缺失/非数值 | 可售性未评估：缺少 `sellability_norm`，无法判断能否交付 |
| 0.1 | `sellability_norm ≤ 0.2` | 可售性仅 NN（低信号）：`sellability_reason` |
| 1.0 | `margin_assumption` 含 `all 20`/`fallback`/`basket proxy`/`全量回退` | 毛利低置信：使用品类回退价（毛利估算 X%），非该机会自身成交价 |
| 1.1 | `margin_high - margin_low > 0.3` | 毛利低置信：区间宽度 X%（A%–B%），估计范围过宽 |
| 2.0 | `competition_norm < 0.5` | 竞争偏密：稀疏度仅 X%（低于 50% 阈值，同质供给多） |
| 3.0 | `missing_metrics` 非空 | 缺失指标：`missing_metrics` |
| 4.0 | 存在毛利区间且 `cost_input` 为空或 `missing` | 成本缺失：无公开成本输入，毛利 X% 为假设区间而非实测 |
| 9.0 | 以上均不成立 | 数据面未见明显风险项；仍需人工核验原始链接真实性与可交付性 |

文案内嵌该行真实数值，因此不同行不会完全相同。**许可待核验不在本生成器中输出**：`scores.csv` 无逐条 `license_verdict`，`sources.csv` 无与 60 条机会连接的键（`scores.source` 为采集描述），属数据缺口，界面不臆造。

## 4. 硬约束

- 不出现「稳赚 / 已验证需求 / 保证销量」；不显示订单、收益、成交量（数据中不存在）。
- 毛利一律标「模型假设」；可售性一律来自 `sellability_norm` 分档。
- 原始标题、作者、时间、链接、评分构成**只在展开的证据区**。
- 关键词搜索同时匹配产品摘要（意图/人群/载体/理由/风险）与原始标题。

## 5. 复算

```powershell
python tools\\workbench\\gen_profiles.py
```

`profiles.json` 每条含 `evidence_fields[]`，列出该条文案实际用到的 `scores.csv` 列，可逐条对照复核。
"""


TAXONOMY_MD = """# 商品分类法：载体 × 具体用途（可审计）

> 目标：把“Notion 模板 / 教学内容 / 提示词包”这类笼统说法，换成**具体商品类型**（如「Notion 求职投递追踪表」）。
> 纯关键词规则、确定性、可复算；**不调用模型、不编造价格或销量**。

## 1. 载体（先判）

| 载体 | 关键词 |
| --- | --- |
| Notion | notion |
| PPT | ppt / powerpoint / 幻灯片 / 演示文稿 |
| 服务 | 代充 / 代下 / 代购 / 充值 / download service / top up |
| 素材 | psd / figma / ui kit / 素材 / 插画 / icon / design pack |
| 文档 | doc / docx / pdf / 文档 / 表格 / excel / spreadsheet / 简历文档 |
| 其他 | 以上都不命中 |

## 2. 用途（后判，按优先级）

| 用途 | 关键词 |
| --- | --- |
| 求职 | job / apply / interview / lamaran / cv / resume / 求职 / 简历 / 面试 / 投递 |
| 学习 | study / class / lecture / notes / student / school / 学习 / 课堂 / 笔记 |
| 内容创作 | content / creator / edit / social / 选题 / 内容 / 创作 / 社媒 |
| 生活 | budget / meal / workout / habit / goal / travel / planner / tracker / 预算 / 健身 / 旅行 / 习惯 / 计划 / 记账 |
| 设计 | design / portfolio / ui / 设计 / 作品集 |
| 赠送引流 | giveaway / free / 赠送 / 免费 / 福利 |
| 未判定 | 以上都不命中 |

## 3. 商品类型名（载体 × 用途）

| 载体 | 用途 | 商品类型 |
| --- | --- | --- |
| Notion | 求职 | Notion 求职投递追踪表 |
| Notion | 学习 | Notion 学习笔记模板 |
| Notion | 内容创作 | Notion 内容创作选题库 |
| Notion | 生活 | Notion 生活计划（预算/健身/旅行） |
| Notion | 设计 | Notion 设计作品集模板 |
| Notion | 赠送引流 | Notion 赠送引流模板 |
| PPT | 设计 / 求职 / 学习 | PPT 模板（作品集）/（汇报/述职）/（课件） |
| 文档 | 求职 | 简历文档模板 |
| 服务 | 未判定 | 资料代充/代下服务 |
| 素材 | 设计 | 设计素材包 |
| — | 兜底 | Notion 其它（待人工）/ PPT 模板（用途待定）/ 文档模板（用途待定）/ 未归类（待人工） |

**禁止**用“学习或生活规划模板 / 教学内容 / 提示词或数字包”这类笼统词作为组名。

## 4. 每类固定五段分析（组级，全部由真实列推导）

1. **是什么（具体交付物）**：载体 × 用途 组合出的商品类型。
2. **谁买**：取组内评分最高成员的目标人群（`profiles.json.target_user`）。
3. **为什么可能卖得动**：组内条数、`demand_raw` 合计、`demand_norm` 最高分位、`sellability_norm` 均值；**无可比成交价时写明「仅内容信号、无售卖证据」**；有价格信号时注明样本数为 `price_signals`，且**不是该类型自身成交价**。
4. **竞争与差异化**：该类型占全部机会的比例、组内可售（≥0.8）条数；**无竞品计数数据时写「需补采集平台在售数量」**。
5. **定价、毛利与风险**：`margin_low..high` 并集区间（标「模型假设」）、组内高频风险前 2；**无真实成交/订单时写「定价需补采集」**。

## 5. 质量线与默认统计口径（页面默认视图）

- **只统计已归类条目**：`商品型具体品类` + `内容型具体类别`。
- 从默认统计与组表中**剔除**：`Notion 其它（待人工）`、`未归类（待人工）`，以及**信号弱**条目。
- **质量线（可配置，当前取值）**：已归类 且（`demand_norm ≥ 0.70` **或** `sellability_norm ≥ 0.80` **或** 有参考价）。
  - 边界含等号：`0.70` 视为达线，`0.699` 不达线；`0.80` 达线，`0.79` 不达线。
  - 「有参考价」= `opportunity_sourcing_top10.csv` 中该机会的 `reference_max` 非空。
  - 未达线者标为「信号弱」，**不计入组级统计**（条数/需求合计/可售性均值/毛利区间），但在「查看已剔除条目」折叠区保留原链接可复查。
- **漏斗**：采集 60 → 已归类 N（商品 a / 内容 b；其中达线 x · 弱信号 y）→ 已剔除 M（其它 m + 未归类 n），且 `N + M = 60`。
- 组行标注「样本 N 条（已剔除无关/弱信号）」，确保被剔除条目不参与均值。

## 6. 守恒与兜底

- 分类守恒：各具体类型条数之和 + 待人工 = 总条数（脚本输出 `conservation` 字段，测试断言）。
- 只有 Notion 载体但无用途词 → 「Notion 其它（待人工）」，并记录原因。
- 既无载体也无用途词 → 「未归类（待人工）」，原因同时写入 `categories.json.unclassified_reason`。

## 7. 复算

```powershell
python tools\\workbench\\gen_profiles.py     # 生成 profiles.json / groups.json / product-taxonomy/{categories.json,model.md}
```
每条成员保留 `hit_words`（载体命中词 / 用途命中词），即“用途判定依据”。
"""


def main() -> int:
    scores = read_csv(SCORES)
    stats = price_stats(read_csv(PRICES))
    profiles = []
    for row in scores:
        info = build_analysis(row, stats)
        profiles.append({
            "item_id": row.get("item_id"),
            "platform": row.get("platform"),
            "rank": row.get("rank"),
            "product_type": info["product_type"],
            "target_user": info["target_user"],
            "deliverable": info["deliverable"],
            "carrier": info["carrier"],
            "commercial_form": info["commercial_form"],
            "demand_tier": info["demand_tier"],
            "positioning": info["positioning"],
            "why": info["why"],
            "risks": info["risks"],
            "evidence_fields": info["evidence_fields"],
            "raw_title_ref": row.get("raw_ref"),
            "source_url": row.get("url"),
        })
    type_counts: dict[str, int] = {}
    user_counts: dict[str, int] = {}
    risk_variants: dict[str, int] = {}
    for item in profiles:
        type_counts[item["product_type"]] = type_counts.get(item["product_type"], 0) + 1
        user_counts[item["target_user"]] = user_counts.get(item["target_user"], 0) + 1
        key = " | ".join(item["risks"])
        risk_variants[key] = risk_variants.get(key, 0) + 1
    payload = {
        "generated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "source": "docs/validation/money-project/scoring/scores.csv",
        "source_sha256": hashlib.sha256(SCORES.read_bytes()).hexdigest(),
        "price_stats": stats,
        "rules_version": "analysis.py@rev2-intent-first",
        "type_counts": type_counts,
        "target_user_counts": user_counts,
        "risk_variant_count": len(risk_variants),
        "rows": profiles,
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "profiles.json").write_bytes(json.dumps(payload, ensure_ascii=False, indent=1).encode("utf-8"))
    analyses = {item["item_id"]: {"product_type": item["product_type"], "carrier": item["carrier"],
                                 "why": item["why"], "risks": item["risks"]} for item in profiles}
    groups = build_groups(scores, analyses, read_csv(SOURCES))
    (OUT / "groups.json").write_bytes(json.dumps({
        "generated_utc": payload["generated_utc"],
        "source_sha256": payload["source_sha256"],
        "rules_version": payload["rules_version"],
        "group_count": len(groups),
        "groups": groups,
    }, ensure_ascii=False, indent=1).encode("utf-8"))
    (OUT / "model.md").write_bytes(MODEL_MD.encode("utf-8"))

    src_rows = read_csv(SOURCES)
    texts = build_text_index()
    categories = build_categories(scores, analyses, stats, src_rows, texts)
    conservation = summarize_conservation(categories, len(scores))
    # 旧分组里的 29 条「carrier:notion」子集：按用途再拆一次，并给出该子集守恒
    notion29_rows = [row for row in scores
                     if "notion" in str(row.get("title") or "").lower()
                     and (analyses.get(row.get("item_id")) or {}).get("product_type") == "未分类"]
    notion29_cats = build_categories(notion29_rows, analyses, stats, src_rows, texts)
    notion29 = {
        "total": len(notion29_rows),
        "breakdown": {c["category"]: c["count"] for c in notion29_cats},
        "pending": sum(c["count"] for c in notion29_cats
                       if c["category"] in ("Notion 其它（待人工）", "未归类（待人工）")),
        "checked": sum(c["count"] for c in notion29_cats) == len(notion29_rows),
    }
    # 达标评估：Notion 其它 ≤18 且 ≥4 个子类各 ≥2 条
    notion_cats = [c for c in categories if c["carrier"] == "Notion"]
    notion_total = sum(c["count"] for c in notion_cats)
    other_count = sum(c["count"] for c in notion_cats if c["category"] == "Notion 其它（待人工）")
    subcat_ge2 = [c["category"] for c in notion_cats
                  if c["category"] != "Notion 其它（待人工）" and c["count"] >= 2]
    coverage = {
        "items_with_text": sum(1 for row in scores if (texts.get(str(row.get("item_id"))) or {}).get("text")),
        "items_total": len(scores),
    }
    targets = {
        "notion_total": notion_total,
        "notion_other": other_count,
        "notion_other_ratio": round(other_count / notion_total, 4) if notion_total else None,
        "subcats_ge2": subcat_ge2,
        "target_other_le_18": other_count <= 18,
        "target_four_subcats_ge2": len(subcat_ge2) >= 4,
        "met": other_count <= 18 and len(subcat_ge2) >= 4,
    }
    pending_rows = [row for c in categories if c["category"] == "Notion 其它（待人工）"
                    for row in scores if str(row.get("item_id")) in c["members"]]
    targets["notion_other_platforms"] = {p: sum(1 for r in pending_rows if r.get("platform") == p)
                                         for p in sorted({r.get("platform") for r in pending_rows})}
    targets["notion_other_samples"] = [
        {"item_id": r.get("item_id"), "title": str(r.get("title") or "")[:70],
         "text_len": len((texts.get(str(r.get("item_id"))) or {}).get("text") or "")}
        for r in pending_rows[:5]
    ]
    # 逐条缺词说明（其它条目每条一行）
    other_members = {m for c in categories if c["category"] == "Notion 其它（待人工）" for m in c["members"]}
    other_missing = []
    for row in scores:
        if str(row.get("item_id")) not in other_members:
            continue
        other_missing.append({
            "item_id": row.get("item_id"),
            "platform": row.get("platform"),
            "title_snippet": str(row.get("title") or "")[:70],
            "text_len": len((texts.get(str(row.get("item_id"))) or {}).get("text") or ""),
            "missing": "缺用途词（求职/学习/内容/生活/设计/赠送）且未命中内容型词（import/setup/推荐/rekomendasi/变现 等）",
        })
    targets["other_missing_count"] = len(other_missing)
    targets["remaining_needs_manual"] = other_count
    OUT_TAX.mkdir(parents=True, exist_ok=True)
    (OUT_TAX / "categories.json").write_bytes(json.dumps({
        "generated_utc": payload["generated_utc"],
        "source_sha256": payload["source_sha256"],
        "rules_version": "taxonomy.py@rev1-carrier-x-use",
        "conservation": conservation,
        "notion29": notion29,
        "coverage": coverage,
        "targets": targets,
        "other_missing": other_missing,
        "categories": categories,
    }, ensure_ascii=False, indent=1).encode("utf-8"))
    (OUT_TAX / "model.md").write_bytes(TAXONOMY_MD.encode("utf-8"))
    print(json.dumps({"rows": len(profiles), "type_counts": type_counts, "target_user_counts": user_counts,
                      "risk_variants": len(risk_variants), "groups": len(groups),
                      "categories": len(categories),
                      "category_counts": {c["category"]: c["count"] for c in categories},
                      "conservation": conservation,
                      "profiles_sha256": hashlib.sha256((OUT / "profiles.json").read_bytes()).hexdigest()[:16],
                      "groups_sha256": hashlib.sha256((OUT / "groups.json").read_bytes()).hexdigest()[:16],
                      "categories_sha256": hashlib.sha256((OUT_TAX / "categories.json").read_bytes()).hexdigest()[:16],
                      "taxonomy_model_sha256": hashlib.sha256((OUT_TAX / "model.md").read_bytes()).hexdigest()[:16],
                      "model_sha256": hashlib.sha256((OUT / "model.md").read_bytes()).hexdigest()[:16]},
                     ensure_ascii=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
