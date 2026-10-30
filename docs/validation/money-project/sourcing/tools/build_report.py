#!/usr/bin/env python
"""Build sourcing/report.md from sources, price signals and Top10 join."""

from __future__ import annotations

import csv
import json
import pathlib

BASE = pathlib.Path(__file__).resolve().parents[1]


def load_csv(name: str) -> list[dict]:
    with (BASE / name).open(encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def main() -> int:
    sources = load_csv("sources.csv")
    prices = load_csv("price_signals.csv")
    join = load_csv("opportunity_sourcing_top10.csv")
    price_summary = json.loads((BASE / "logs" / "price_parse_summary.json").read_text(encoding="utf-8"))
    join_summary = json.loads((BASE / "logs" / "join_summary.json").read_text(encoding="utf-8"))
    fallback_count = sum(1 for r in join if r["price_scope"] == "all_20_fallback")
    confidence = {c: sum(1 for r in join if r["margin_confidence"] == c)
                  for c in ("high", "medium", "low")}
    margin_ranges = sorted({(r["gross_margin_low"], r["gross_margin_high"]) for r in join})

    lines = [
        "# 货源库与机会-货源联动（Notion/数字商品）", "",
        "> 数据来源：已验收 scoring 的 60 条机会样本 + GitHub 公开仓库许可证核验 + "
        "已采集的闲鱼 20 条真实商品（只读）。**不构成法律意见；不用于下单/互动。**", "",
        "## 1. 方法与口径", "",
        "### 许可证",
        "- 优先 GitHub API `license.spdx_id`；若为 `null` 或 `NOASSERTION`，实际读取 `/repos/{owner}/{repo}/license` "
        "并解码 LICENSE 前 40 行，不凭仓库名猜测。",
        "- 三档：**可商用**（MIT/Apache/BSD 等宽松许可）、**需授权（署名/有条件）**（CC BY 需署名；GPL/AGPL/MPL 等带义务）、"
        "**禁止或不明**（无 LICENSE、404 或自定义条款）。",
        "- **CC BY 更正**：gh-01 的 API 标记为 NOASSERTION，但 LICENSE 前 40 行为 CC BY 4.0；"
        "CC BY 允许商用、仅需署名，因此归 **需授权**，不是“禁止或不明”。上一版分类错误，本版已更正。",
        "- 无 LICENSE/404 的仓库才是“禁止或不明”；不能仅凭 NOASSERTION 字段判定，必须看 LICENSE 文本。"
        "MediaCrawler 若 NOASSERTION 且无可识别许可文本，仍按“不明”处理。",
        "",
        "### 价格",
        "- `price` 字段的 **¥1 是引流标价**，不是真实客单价；`effective_price` 合并 raw_text 中的小数后缀"
        "（如 `¥1 .88` → ¥1.88）。",
        "- `reference_price` 是 raw_text 中更高的划线/参考价（如 `¥699`、`¥9.9`），不是成交价。",
        "- `wants` 是“N人想要”的兴趣代理，不是订单/付款人数。",
        "- 小红书 20 条已读取，但 `price=null`，未纳入价格信号；仅作内容参考。",
        "",
        "### 联动",
        "- 机会来自已验收 `scoring/scores.csv` 的 Top10；货源按品类做**最近可复用模板**匹配，"
        "不是同款商品；匹配质量在表中标注“近似匹配”。",
        "- **毛利改为价格信号驱动**：**¥1 标价视为引流价/缺失，已排除，不作 price_low 锚点**；"
        "优先用同品类 `reference_price` 中位数作为价格锚点，无参考价则用同品类 `effective_high`。"
        "全量回退或样本<3 时，用全量篮子并额外放宽 ±0.15。旧 scoring 的 0.7–0.95 只作为无价格信号时的 fallback。",
        "- 成本口径：数字交付边际成本 **¥0.5–3/单**（人民币口径）；不按汇率硬换算，不含退款/支付/流量/客服成本。",
        "- 归一化：`margin = clamp((price - cost) / price, 0, 1)`，直接得到 0–1 的毛利率；"
        "`mid = (low + high) / 2`。不是把绝对毛利金额除以 cap，避免因品类价格量级不同而失真。", "",
        "## 2. 货源表（sources.csv，14 行）", "",
        "| ID | 名称 | 类型 | SPDX | 结论 | 成本 |  effort | 稳定性 | 售后风险 |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for s in sources:
        lines.append(f"| {s['source_id']} | [{s['name']}]({s['repo_or_url']}) | {s['type']} | "
                     f"{s['license_spdx']} | **{s['license_verdict']}** | {s['cost']} | {s['effort']} | "
                     f"{s['stability']} | {s['after_sales_risk']} |")
    lines += ["", "三档分布：**可商用 8 / 需授权 1 / 禁止或不明 5**（详见 `sources.csv`；"
              "`raw/license_checks.json` 与 `raw/licenses/*.json` 保留逐仓库核验证据）。"
              "8 个可商用均为 MIT；1 个需授权为 CC BY 4.0（gh-01，需署名）；"
              "5 个无 LICENSE/404 为不明。", "",
              "### CC BY 更正记录", "",
              "- **gh-01 `enescingoz/awesome-n8n-templates`**：API `license.spdx_id=NOASSERTION`，"
              "但实际 LICENSE 前 40 行为 **Creative Commons Attribution 4.0 International**；"
              "CC BY 允许商业使用、要求署名，故修正为 **需授权**（非“禁止或不明”）。"
              "证据：`raw/licenses/enescingoz__awesome-n8n-templates.json`、`raw/license_checks.json`。",
              "- 其余 5 个无 LICENSE/404 的仓库保持“禁止或不明”：gh-04/06/07/08/09。", "",
              "## 3. 闲鱼价格信号（price_signals.csv，20 行）", "",
              f"- 标价均为 ¥1；合并小数后缀后的有效价：**¥{price_summary['effective_price']['min']:.2f}–"
              f"¥{price_summary['effective_price']['max']:.2f}**（唯一值 "
              f"{', '.join(f'¥{v:.2f}' for v in price_summary['effective_price']['unique'])}）。",
              f"- 划线/参考价仅 **{price_summary['reference_price']['count']}/20** 条："
              f"{', '.join(f'¥{v:.2f}' for v in price_summary['reference_price']['values'])}；"
              "其余无参考价，不能据此推客单价。",
              f"- 想要人数：**{price_summary['wants']['count']}/20** 条有值，范围 "
              f"{price_summary['wants']['min']}–{price_summary['wants']['max']}，合计 {price_summary['wants']['sum']}；"
              "是兴趣代理，不是订单。",
              f"- 解析状态：`{json.dumps(price_summary['status_counts'], ensure_ascii=False)}`。", "",
              "**价格解析失败/部分样例**（完整列表见 `logs/price_parse_summary.json`）：", ""]
    for f in price_summary["failures_or_partial"]:
        lines.append(f"- item `{f['item_id']}`：`{f['status']}`；尾部 `{f['raw_tail'][-70:]}`")
    lines += ["", "> 结论：¥1 为引流价，已排除，不能直接当售价或毛利锚点；有效价仍多为 ¥1.00–¥1.88，"
              "划线价只有 3 条（最高 ¥699 为极值，不作锚点），因此毛利只给价格驱动区间/情景，不给点估计。", "",
              f"join 使用 **{len({r['source_id'] for r in join})} 个不同源码**："
              + "、".join(f"`{sid}`" for sid in sorted({r['source_id'] for r in join})) + "。", "",
              "## 4. 机会-货源联动 Top10", "",
              "| # | 机会 | 分数 | 候选货源 | 许可结论 | 价格口径/样本 | 闲鱼价格信号 | 毛利区间 | 依据/置信度 |",
              "| --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
    for r in join:
        price_text = f"¥{r['effective_low']}–{r['effective_high']}"
        if r["reference_max"]:
            price_text += f"（参考 ¥{r['reference_max']}）"
        if r["price_scope"] == "all_20_fallback":
            price_text += " *全量20条代理*"
        lines.append(f"| {r['rank']} | [{r['title'][:48]}]({r['url']}) | {r['score']} | "
                     f"{r['source_id']} {r['source_name']} | **{r['license_verdict']}** ({r['license_spdx']}) | "
                     f"{r['price_scope']} / {r['price_signal_count']} 条 | "
                     f"{price_text}；{r['wants_sum']} 想要 | {r['gross_margin_low']}–{r['gross_margin_high']} | "
                     f"{r['margin_basis']} / {r['margin_confidence']} |")
    lines += ["", "### Top10 明细（来源/链接/假设）", ""]
    for r in join:
        lines += [
            f"**{r['rank']}. {r['title'][:80]}**",
            f"- 机会证据：[{r['url']}]({r['url']})；平台 {r['platform']}；分数 {r['score']}。",
            f"- 候选货源：`{r['source_id']}` [{r['source_name']}]({r['source_url']})；"
            f"许可证 **{r['license_verdict']}**（{r['license_spdx']}）；核验证据 [license]({r['source_evidence_url']})。",
            f"- 匹配质量：{r['match_quality']}；匹配理由：**{r['match_reason']}**；替代货源：{r['source_alternatives'] or '无'}。",
            f"- 价格信号：{r['price_category']} / {r['price_scope']} / {r['price_signal_count']} 条；"
            f"有效价 ¥{r['effective_low']}–{r['effective_high']}，参考价 {('¥' + r['reference_max']) if r['reference_max'] else '无'}，"
            f"想要合计 {r['wants_sum']}（兴趣代理）。",
            f"- 毛利区间：**{r['gross_margin_low']}–{r['gross_margin_high']}**（mid {r['gross_margin_mid']}；"
            f"依据 `{r['margin_basis']}`；置信度 **{r['margin_confidence']}**）。",
            f"- 计算说明：{r['margin_note']}",
            f"- 假设：{r['assumptions']}", "",
        ]
    unknown = [s for s in sources if s["license_verdict"] == "禁止或不明"]
    conditional = [s for s in sources if s["license_verdict"] == "需授权"]
    commercial = [s for s in sources if s["license_verdict"] == "可商用"]
    lines += ["## 5. 风险与不可商用清单", "",
              f"- 可商用 **{len(commercial)}** 条："
              + "、".join(f"`{s['source_id']}`" for s in commercial) + "（仍需保留版权声明与第三方素材复核）。",
              f"- 需授权（署名/有条件）**{len(conditional)}** 条：" if conditional else "- 需授权：0 条。",]
    for s in conditional:
        lines.append(f"  - `{s['source_id']}` **{s['name']}**：{s['license_reason']}；[证据]({s['evidence_url']})。")
    lines += ["", "以下货源**不能仅凭公开仓库直接商用**（无 LICENSE、404 或自定义条款）：", ""]
    for s in unknown:
        lines.append(f"- `{s['source_id']}` **{s['name']}**：{s['license_verdict']}；"
                     f"SPDX={s['license_spdx']}；原因：{s['license_reason']}；"
                     f"[证据]({s['evidence_url']})。")
    lines += ["", "其他风险：",
              "- 货源匹配是“最近可复用模板”，不是同款/授权内容；不能把 GitHub 模板等同于闲鱼商品的权利。",
              "- 闲鱼 ¥1 为引流价；有效价与划线价都不是成交价；想要人数不是订单；无法据此算真实转化/利润。",
              "- 8 个 MIT 源可复用代码/模板，但仍需保留版权声明、检查第三方字体/图片/商标与 Notion 模板内容权利。",
              "- 样本没有“囤货/重售后”品类；本库只覆盖数字商品/模板/工具，实体货源覆盖不足。",
              "- GitHub API 曾遇共享 IP rate limit，本次仅读取公开 API/LICENSE；未使用 token，未扩大请求。", "",
              "## 6. 假设与限制", "",
              "- **价格**：有效价来自 raw_text 小数后缀合并；17/20 无参考价，3/20 有参考价；不把 ¥1 当 ASP。",
              "- **毛利**：由 price 信号推导，`clamp((price-cost)/price,0,1)`；成本 ¥0.5–3/单；"
              "**¥1 引流标价已排除，不作 price_low**；锚点用 `reference` 中位数，无参考价用 `effective_high`；"
              "`reference_max`（699）只展示、不作锚点。"
              f"本批 10 行有 **{len(margin_ranges)} 组**不同区间；置信度分布 {confidence}。",
              "- **偏差方向**：全量回退把跨品类价格带混在一起并 ±0.15 放宽，可能**抬高**低价值 Notion 教程的毛利"
              "（锚点 9.9 并非 Notion 专属价）；高价值设计机会若只有 3 条参考价、且 699 极值不参与，可能被**低估**。"
              "同品类样本<5 不高于 medium，n≥5 且有参考价才允许 high；全量回退固定 low。",
              "- **不可比**：闲鱼 ¥1 是引流价，effective 是品类篮子代理而非机会自身成交价；"
              "reference 是划线价不是成交价；wants 是兴趣代理；x/bili 内容平台与闲鱼交易平台不可直接比价。",
              "- **许可证**：无 LICENSE/404 或无法识别条款按“禁止或不明”；CC BY 等有条件许可归“需授权（署名/有条件）”；本报告不是法律意见。",
              f"- **来源匹配**：Top10 里 {fallback_count} 条因闲鱼无同品类价格，回退使用全量 20 条数字商品价格带"
              "（表中标 `all_20_fallback`），不能视为 Notion 专属价格。",
              "- **样本**：闲鱼 20、GitHub 14（原 10 + 补充 resume/portfolio/prompt 4）；非概率抽样，不能代表全市场；未下单/互动。", ""]
    (BASE / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"sources": len(sources), "prices": len(prices), "join": len(join),
                      "unknown_sources": len(unknown), "report": str(BASE / "report.md")},
                     ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
