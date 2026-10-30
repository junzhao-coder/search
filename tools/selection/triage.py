"""Rule-only demand/promo/noise triage. Does not affect identity or dedupe."""

from __future__ import annotations

import json
from . import models

DEMAND_WORDS = ("求", "问", "求助", "有没有", "想要", "推荐", "怎么做", "不会")
# Strong commercial signals win over generic "想要"/"问"; this keeps promo out of demand.
PROMO_WORDS = ("出", "售", "接单", "代做", "推广", "优惠", "私我", "加v", "自营",
               "自动发货", "秒发", "拍下", "网盘", "标价", "发货", "素材", "合集", "源文件", "价格")


def explain(text: str) -> dict:
    lowered = (text or "").lower()
    demand_hits = [w for w in DEMAND_WORDS if w.lower() in lowered]
    promo_hits = [w for w in PROMO_WORDS if w.lower() in lowered]
    if promo_hits:
        # any strong commercial signal wins: a promotional post must not be counted as demand
        label = "promo"
    elif demand_hits:
        label = "demand"
    else:
        label = "noise"
    return {"label": label, "demand_hits": demand_hits, "promo_hits": promo_hits}


def classify(text: str) -> str:
    return explain(text)["label"]


RULE_VERSION = "triage-v1"


def store(conn, signal_id: int, text: str, *, native_id_source: str | None = None,
          note: str | None = None) -> dict:
    """Persist one triage label; reusable by adapters and manual imports.

    An existing manual_override label is authoritative: only hits/rule are refreshed.
    """
    e = explain(text)
    existing = conn.execute(
        "SELECT label,manual_override FROM signal_triage WHERE signal_id=?", (signal_id,)).fetchone()
    label = e["label"]
    if existing and existing["manual_override"]:
        label = existing["manual_override"]
    conn.execute(
        "INSERT INTO signal_triage(signal_id,label,demand_hits_json,promo_hits_json,rule_version,at,"
        "manual_override,native_id_source,note) VALUES (?,?,?,?,?,?,?,?,?) "
        "ON CONFLICT(signal_id) DO UPDATE SET "
        "label=excluded.label,demand_hits_json=excluded.demand_hits_json,"
        "promo_hits_json=excluded.promo_hits_json,rule_version=excluded.rule_version,at=excluded.at,"
        "native_id_source=COALESCE(NULLIF(excluded.native_id_source,''),signal_triage.native_id_source),"
        "note=COALESCE(NULLIF(excluded.note,''),signal_triage.note)",
        (signal_id, label, json.dumps(e["demand_hits"], ensure_ascii=False),
         json.dumps(e["promo_hits"], ensure_ascii=False), RULE_VERSION, models.utc_now(),
         None, native_id_source, note))
    conn.commit()
    row = conn.execute(
        "SELECT label,manual_override,native_id_source,note FROM signal_triage WHERE signal_id=?",
        (signal_id,)).fetchone()
    return {"signal_id": signal_id, "label": label, "effective_label": row["label"],
            "manual_override": row["manual_override"], "native_id_source": row["native_id_source"],
            "note": row["note"], "demand_hits": e["demand_hits"], "promo_hits": e["promo_hits"],
            "rule_version": RULE_VERSION}


def set_override(conn, signal_id: int, label: str) -> dict:
    """Human re-triage; a marker only, never changes identity/category/dedupe."""
    if label not in ("demand", "promo", "noise"):
        raise ValueError("invalid_triage_label")
    row = conn.execute("SELECT demand_hits_json,promo_hits_json,rule_version,at FROM signal_triage WHERE signal_id=?",
                       (signal_id,)).fetchone()
    if row is None:
        raise ValueError("triage_row_not_found")
    conn.execute("UPDATE signal_triage SET label=?,manual_override=? WHERE id=? AND 0", (label, label, signal_id))
    conn.execute("UPDATE signal_triage SET label=?,manual_override=? WHERE signal_id=?",
                 (label, label, signal_id))
    conn.commit()
    return {"signal_id": signal_id, "label": label, "manual_override": label}


def backfill(conn) -> dict:
    """Classify every signal that has no triage row (or all with refresh=True)."""
    rows = conn.execute(
        "SELECT s.id,s.title,s.quote FROM signals s WHERE NOT EXISTS "
        "(SELECT 1 FROM signal_triage t WHERE t.signal_id=s.id) ORDER BY s.id").fetchall()
    counts = {"demand": 0, "promo": 0, "noise": 0}
    for r in rows:
        out = store(conn, int(r["id"]), (r["title"] or "") + " " + (r["quote"] or ""))
        counts[out["label"]] += 1
    return {"processed": len(rows), **counts}


def refresh(conn) -> dict:
    """Re-run rules for all rows; manual_override labels are preserved by store()."""
    rows = conn.execute("SELECT s.id,s.title,s.quote FROM signals s ORDER BY s.id").fetchall()
    counts = {"demand": 0, "promo": 0, "noise": 0}
    for r in rows:
        out = store(conn, int(r["id"]), (r["title"] or "") + " " + (r["quote"] or ""))
        counts[out["label"]] += 1
    return {"processed": len(rows), **counts}
