"""Real-HTTP end-to-end driver for S2-B2 (run against a live server, see S2_CORE.md §4).

Usage: python tests/api/b2_e2e.py [base_url]
Exercises: health -> import -> gates -> scenario -> draft -> feedback -> detail.
"""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:5081"

FULL_ROW = (
    "title,data_origin,demand_source,demand_url,demand_excerpt,demand_kind,supply_provider,supply_url,"
    "supply_native_id,supply_origin_type,supply_format_version,supply_price,supply_commercial_allowed,"
    "supply_redistribute_allowed,supply_resale_allowed,supply_sample_checked,supply_sample_note,"
    "supply_evidence_url,supply_evidence_excerpt\n"
    "示例-B2端到端,synthetic,xianyu,https://example.com/demand/e2e,求同一类模板,specific_ask,"
    "示例开放模板库,https://example.com/supply/e2e,tpl-e2e,open_repo,v1,0,yes,yes,yes,partial,抽检 2 个文件,"
    "https://example.com/supply/e2e/license,本库素材可用于商业用途并允许转售（示例摘录）\n"
)

COSTS = [
    {"role": "sale_price", "basis": "per_order", "value_kind": "money", "money_minor": 1000},
    {"role": "procurement", "basis": "per_order", "value_kind": "money", "money_minor": 300},
    {"role": "procurement", "basis": "one_time", "value_kind": "money", "money_minor": 0},
    {"role": "procurement", "basis": "recurring", "value_kind": "money", "money_minor": 0, "period": "monthly"},
    {"role": "platform_fee", "basis": "per_order", "value_kind": "rate", "rate_bp": 500},
    {"role": "payment_fee", "basis": "per_order", "value_kind": "rate", "rate_bp": 0},
    {"role": "acquisition", "basis": "per_order", "value_kind": "money", "money_minor": 0},
    {"role": "refund_reserve", "basis": "per_order", "value_kind": "rate", "rate_bp": 0},
    {"role": "other", "basis": "per_order", "value_kind": "money", "money_minor": 0},
    {"role": "manual_labor", "basis": "per_order", "value_kind": "minutes", "minutes": 10, "hourly_rate_minor": 3000},
]


def call(method: str, path: str, body=None, content_type="application/json"):
    data = None
    if body is not None:
        data = body.encode("utf-8") if isinstance(body, str) else json.dumps(body, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(BASE + path, data=data, method=method)
    if data is not None:
        request.add_header("Content-Type", content_type)
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as err:
        return err.code, json.loads(err.read().decode("utf-8"))


def main() -> int:
    out: dict = {}
    status, health = call("GET", "/api/health")
    out["health"] = {"status": status, "schema_version": health.get("schema_version"), "keys": sorted(health.keys())}

    status, imported = call("POST", "/api/imports?format=csv&mode=atomic", FULL_ROW, "text/csv")
    records = [r for row in imported.get("rows", []) for r in row.get("records", [])]
    candidate_id = next(r["id"] for r in records if r["type"] == "candidate")
    supply_id = next(r["id"] for r in records if r["type"] == "supply_offer")
    out["import"] = {"status": status, "batch_status": imported.get("status"), "candidate_id": candidate_id,
                     "supply_id": supply_id}

    _, snapshot = call("GET", f"/api/candidates/{candidate_id}")
    demand_evidence = next(e["id"] for e in snapshot["evidences"] if e["evidence_type"] == "demand")
    clause_evidence = snapshot["supplies"][0]["license_evidence_id"]
    out["before_gates"] = {"derived_status": snapshot["derived_status"], "gates": snapshot["gates"]}

    status, platform_evidence = call("POST", f"/api/candidates/{candidate_id}/evidences",
                                     {"evidence_type": "platform_policy",
                                      "source_url": "https://example.com/platform/policy",
                                      "excerpt": "示例平台规则：虚拟商品需按类目发布", "fact_kind": "fact"})
    out["platform_evidence"] = status

    cost_statuses = []
    for spec in COSTS:
        payload = dict(spec, assumption_note="示例假设：端到端样例", supply_offer_id=supply_id)
        code, body = call("POST", f"/api/candidates/{candidate_id}/cost-items", payload)
        cost_statuses.append(code)
    out["cost_item_writes"] = cost_statuses

    gate_results = {}
    gate_results["demand"] = call("POST", f"/api/candidates/{candidate_id}/gates/demand",
                                  {"status": "verified", "evidence_id": demand_evidence})
    gate_results["supply_distribution"] = call("POST", f"/api/candidates/{candidate_id}/gates/supply_distribution",
                                               {"status": "verified", "supply_offer_id": supply_id,
                                                "evidence_id": clause_evidence})
    gate_results["cost"] = call("POST", f"/api/candidates/{candidate_id}/gates/cost",
                                {"status": "verified", "supply_offer_id": supply_id})
    gate_results["platform_policy"] = call("POST", f"/api/candidates/{candidate_id}/gates/platform_policy",
                                           {"status": "verified", "evidence_id": platform_evidence.get("id"),
                                            "applies_to_platform": "xianyu", "applies_to_version": "v1"})
    out["gate_results"] = {gate: {"status": code, "candidate_status": body.get("candidate_status"),
                                  "seq": body.get("seq"), "expires_at": body.get("expires_at")}
                           for gate, (code, body) in gate_results.items()}

    status, scenario_initial = call("GET", f"/api/candidates/{candidate_id}/scenario?variant=base")
    out["scenario_initial"] = {"status": status, "complete": scenario_initial["complete"],
                               "sale_price_minor": scenario_initial["sale_price_minor"],
                               "known_subtotal_minor": scenario_initial["known_subtotal_minor"],
                               "contribution_per_order_minor": scenario_initial["contribution_per_order_minor"],
                               "net_per_order_minor": scenario_initial["net_per_order_minor"],
                               "unknown_components": scenario_initial["unknown_components"]}

    status, rejected = call("POST", f"/api/candidates/{candidate_id}/gates/platform_policy",
                            {"status": "verified", "evidence_id": platform_evidence.get("id"),
                             "applies_to_platform": "xianyu", "applies_to_version": "v9"})
    out["gate_rejection_demo"] = {"status": status, "code": rejected.get("error", {}).get("code"),
                                  "fields": [d["field"] for d in rejected.get("error", {}).get("details", [])]}

    _, snapshot = call("GET", f"/api/candidates/{candidate_id}")
    platform_cost = next(row["id"] for row in snapshot["cost_items"]
                         if row["role"] == "platform_fee" and row["is_active"])
    status, superseded = call("POST", f"/api/cost-items/{platform_cost}/supersede",
                              {"value_kind": "rate", "rate_bp": 600, "assumption_note": "示例：平台费率更正"})
    _, stale_snapshot = call("GET", f"/api/candidates/{candidate_id}")
    out["downgrade_demo"] = {"status": status, "gate_downgraded": superseded.get("gate_downgraded"),
                             "cost_gate": stale_snapshot["gates"]["cost"],
                             "derived_status": stale_snapshot["derived_status"],
                             "review_kinds": sorted({r["kind"] for r in stale_snapshot["review_items"]
                                                     if r["status"] == "open"})}
    status, restored = call("POST", f"/api/candidates/{candidate_id}/gates/cost",
                            {"status": "verified", "supply_offer_id": supply_id})
    _, blocked = call("GET", f"/api/candidates/{candidate_id}")
    open_review = next((r["id"] for r in blocked["review_items"] if r["status"] == "open"), None)
    resolve_status, resolved = call("POST", f"/api/review-items/{open_review}/resolve",
                                    {"status": "resolved_recheck", "note": "复核后重新核验"})
    _, recovered = call("GET", f"/api/candidates/{candidate_id}")
    out["reverify_after_downgrade"] = {"http": status, "candidate_status": restored.get("candidate_status"),
                                       "seq": restored.get("seq"),
                                       "review_resolve": {"http": resolve_status,
                                                          "status": resolved.get("status")},
                                       "after_resolve": recovered["derived_status"],
                                       "error": restored.get("error", {}).get("details")}

    status, scenario_body = call("GET", f"/api/candidates/{candidate_id}/scenario?variant=base")
    out["scenario_after_correction"] = {"status": status, "complete": scenario_body["complete"],
                                        "known_subtotal_minor": scenario_body["known_subtotal_minor"],
                                        "contribution_per_order_minor": scenario_body["contribution_per_order_minor"],
                                        "net_per_order_minor": scenario_body["net_per_order_minor"],
                                        "unknown_components": scenario_body["unknown_components"]}

    status, draft = call("POST", f"/api/candidates/{candidate_id}/drafts", {"kind": "listing_copy",
                                                                            "method": "template"})
    out["draft"] = {"status": status, "draft_status": draft.get("status"), "template_version": draft.get("template_version"),
                    "has_placeholder": "【待核验" in draft.get("body", "")}

    status, sale = call("POST", f"/api/candidates/{candidate_id}/feedback",
                        {"kind": "sale", "amount_minor": 10000, "order_ref": "ORDER-E2E"})
    out["sale"] = {"status": status, "predicted_net_per_order_minor": sale.get("predicted_net_per_order_minor"),
                   "actual_net_per_order_minor": sale.get("actual_net_per_order_minor")}
    status, rewrite = call("PATCH", f"/api/feedback/{sale.get('id')}", {"predicted_net_per_order_minor": 999})
    out["snapshot_rewrite_attempt"] = {"status": status, "code": rewrite.get("error", {}).get("code")}

    status, final = call("GET", f"/api/candidates/{candidate_id}")
    out["after"] = {"status": status, "derived_status": final["derived_status"], "gates": final["gates"],
                    "cost_items": len(final["cost_items"]), "drafts": len(final["drafts"]),
                    "feedback": len(final["feedback"]), "review_items": len(final["review_items"]),
                    "sale_snapshot": next((f["predicted_net_per_order_minor"] for f in final["feedback"]
                                           if f["kind"] == "sale"), None)}
    print(json.dumps(out, ensure_ascii=False, indent=1))
    ok = (
        out["health"]["status"] == 200
        and out["import"]["status"] == 201
        and out["gate_results"]["platform_policy"]["candidate_status"] == "testable"
        and out["gate_rejection_demo"]["status"] == 422
        and out["downgrade_demo"]["cost_gate"] == "expired"
        and out["downgrade_demo"]["derived_status"] == "stale"
        and out["reverify_after_downgrade"]["after_resolve"] == "testable"
        and out["scenario_initial"]["contribution_per_order_minor"] == 150
        and out["scenario_initial"]["complete"] is True
        and out["scenario_after_correction"]["contribution_per_order_minor"] == 140  # 600bp after the correction
        and out["draft"]["has_placeholder"]
        and out["sale"]["predicted_net_per_order_minor"] == 140
        and out["snapshot_rewrite_attempt"]["status"] == 422
        and out["after"]["derived_status"] == "testable"
    )
    print("E2E_OK" if ok else "E2E_FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
