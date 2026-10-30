"""Shared fixtures for the S2-B2 endpoint tests (sample domains only; isolated temp DBs)."""

from __future__ import annotations

import hashlib
import pathlib
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app import create_app  # noqa: E402
from app.storage.db import connect  # noqa: E402

TMP_ROOT = pathlib.Path(__file__).resolve().parent / "_tmp"

DEMAND_ONLY_HEADER = "title,data_origin,demand_source,demand_url,demand_excerpt,demand_kind"
FULL_HEADER = (
    "title,data_origin,demand_source,demand_url,demand_excerpt,demand_kind,supply_provider,supply_url,"
    "supply_native_id,supply_origin_type,supply_format_version,supply_price,supply_commercial_allowed,"
    "supply_redistribute_allowed,supply_resale_allowed,supply_sample_checked,supply_sample_note,"
    "supply_evidence_url,supply_evidence_excerpt"
)


def slug(text: str) -> str:
    return hashlib.md5(text.encode("utf-8")).hexdigest()[:8]


def new_client(prefix: str = "b2_") -> tuple:
    TMP_ROOT.mkdir(parents=True, exist_ok=True)
    tmp = tempfile.mkdtemp(prefix=prefix, dir=str(TMP_ROOT))
    db_path = str(pathlib.Path(tmp) / "app.db")
    return create_app({"db_path": db_path}).test_client(), db_path


def post_csv(client, text: str, mode: str = "atomic", client_ref: str | None = None):
    url = f"/api/imports?format=csv&mode={mode}"
    if client_ref:
        url += f"&client_ref={client_ref}"
    return client.post(url, data=text.encode("utf-8"), content_type="text/csv")


def seed_demand_only(client, title: str = "示例-B2需求", *, kind: str = "specific_ask") -> str:
    token = slug(title)
    csv_text = (
        f"{DEMAND_ONLY_HEADER}\n"
        f"{title},synthetic,xianyu,https://example.com/demand/{token},求一份可直接套用的模板,{kind}\n"
    )
    payload = post_csv(client, csv_text).get_json()
    return next(r["id"] for row in payload["rows"] for r in row["records"] if r["type"] == "candidate")


def seed_full(client, title: str = "示例-B2完整", *, resale: str = "yes", commercial: str = "yes",
              sample_checked: str = "partial", sample_note: str = "抽检 2 个文件", supply_price: str = "0",
              version: str = "v1") -> tuple[str, str]:
    token = slug(title)
    csv_text = (
        f"{FULL_HEADER}\n"
        f"{title},synthetic,xianyu,https://example.com/demand/{token},求同一类模板,specific_ask,"
        f"示例开放模板库,https://example.com/supply/{token},tpl-{token},open_repo,{version},{supply_price},"
        f"{commercial},yes,{resale},{sample_checked},{sample_note},https://example.com/supply/{token}/license,"
        f"本库素材可用于商业用途并允许转售（示例摘录）\n"
    )
    payload = post_csv(client, csv_text).get_json()
    records = [r for row in payload["rows"] for r in row["records"]]
    candidate_id = next(r["id"] for r in records if r["type"] == "candidate")
    supply_id = next(r["id"] for r in records if r["type"] == "supply_offer")
    return candidate_id, supply_id


def detail(client, candidate_id: str) -> dict:
    return client.get(f"/api/candidates/{candidate_id}").get_json()


def costs_of(client, candidate_id: str) -> dict:
    return {(row["role"], row["basis"]): row for row in detail(client, candidate_id)["cost_items"] if row["is_active"]}


def add_cost(client, candidate_id: str, **payload):
    return client.post(f"/api/candidates/{candidate_id}/cost-items", json=payload)


def add_gate(client, candidate_id: str, gate: str, **payload):
    return client.post(f"/api/candidates/{candidate_id}/gates/{gate}", json=payload)


def scenario(client, candidate_id: str, variant: str = "base") -> dict:
    return client.get(f"/api/candidates/{candidate_id}/scenario?variant={variant}").get_json()


def counts(db_path: str, *tables: str) -> dict:
    conn = connect(db_path)
    try:
        return {t: conn.execute(f"SELECT COUNT(*) AS n FROM {t}").fetchone()["n"] for t in tables}
    finally:
        conn.close()


def query(db_path: str, sql: str, params=()) -> list[dict]:
    conn = connect(db_path)
    try:
        return [dict(r) for r in conn.execute(sql, params).fetchall()]
    finally:
        conn.close()


DEFAULT_COSTS = (
    {"role": "sale_price", "basis": "per_order", "value_kind": "money", "money_minor": 1000},
    {"role": "procurement", "basis": "per_order", "value_kind": "money", "money_minor": 300},
    {"role": "procurement", "basis": "one_time", "value_kind": "money", "money_minor": 0},
    {"role": "procurement", "basis": "recurring", "value_kind": "money", "money_minor": 0, "period": "monthly"},
    {"role": "platform_fee", "basis": "per_order", "value_kind": "rate", "rate_bp": 500},
    {"role": "payment_fee", "basis": "per_order", "value_kind": "rate", "rate_bp": 0},
    {"role": "acquisition", "basis": "per_order", "value_kind": "money", "money_minor": 0},
    {"role": "refund_reserve", "basis": "per_order", "value_kind": "rate", "rate_bp": 0},
    {"role": "other", "basis": "per_order", "value_kind": "money", "money_minor": 0},
    {"role": "manual_labor", "basis": "per_order", "value_kind": "minutes", "minutes": 10,
     "hourly_rate_minor": 3000},
)


def add_default_costs(client, candidate_id: str, supply_id: str | None = None, specs=DEFAULT_COSTS) -> None:
    for spec in specs:
        payload = dict(spec)
        payload.setdefault("assumption_note", "示例假设：本行依据教学样例")
        if supply_id:
            payload.setdefault("supply_offer_id", supply_id)
        response = add_cost(client, candidate_id, **payload)
        assert response.status_code in (200, 201), response.get_data(as_text=True)


def verify_all_gates(client, candidate_id: str, supply_id: str, *, version: str = "v1") -> dict:
    """Drive a candidate to ``testable``: grounded costs bound to the supply + G1..G4."""
    add_default_costs(client, candidate_id, supply_id)
    existing_demand_evidence = next(
        (e["id"] for e in detail(client, candidate_id)["evidences"] if e["evidence_type"] == "demand"), None
    )
    if existing_demand_evidence:
        demand_evidence_id = existing_demand_evidence  # derived from the imported signal (1:1 unique)
    else:
        created = client.post(
            f"/api/candidates/{candidate_id}/evidences",
            json={"evidence_type": "demand", "source_url": "https://example.com/demand/extra",
                  "excerpt": "用户明确求助：需要可套用的模板", "fact_kind": "fact"},
        )
        assert created.status_code == 201, created.get_data(as_text=True)
        demand_evidence_id = created.get_json()["id"]
    platform_evidence = client.post(
        f"/api/candidates/{candidate_id}/evidences",
        json={"evidence_type": "platform_policy", "source_url": "https://example.com/platform/policy",
              "excerpt": "示例平台规则：虚拟商品需按类目发布", "fact_kind": "fact"},
    )
    assert platform_evidence.status_code == 201, platform_evidence.get_data(as_text=True)
    clause_evidence_id = next(
        (row["license_evidence_id"] for row in detail(client, candidate_id)["supplies"]), None
    )
    responses = {
        "demand": add_gate(client, candidate_id, "demand", status="verified",
                           evidence_id=demand_evidence_id),
        "supply_distribution": add_gate(client, candidate_id, "supply_distribution", status="verified",
                                        supply_offer_id=supply_id, evidence_id=clause_evidence_id),
        "cost": add_gate(client, candidate_id, "cost", status="verified", supply_offer_id=supply_id),
        "platform_policy": add_gate(client, candidate_id, "platform_policy", status="verified",
                                    evidence_id=platform_evidence.get_json()["id"],
                                    applies_to_platform="xianyu", applies_to_version=version),
    }
    return responses

