"""Rule-based category ledger, direction cards and review queue (stdlib only)."""

from __future__ import annotations

import difflib
import hashlib
import json
import re

from . import db, models

UNKNOWN = "unknown"

AUDIENCE_RULES = (
    ("student", ("学生", "同学", "考研", "四六级", "考试", "期末", "高考", "大学", "学习")),
    ("designer", ("设计师", "设计", "平面", "简历", "作品集", "PSD", "UI")),
    ("creator", ("自媒体", "创作者", "博主", "文案", "写作", "视频", "运营")),
    ("small_business", ("商家", "店主", "店铺", "电商", "经营", "客服")),
    ("freelancer", ("自由职业", "客户", "CRM", "接单")),
)
TASK_RULES = (
    ("exam_countdown", ("考试", "倒计时", "期末")),
    ("client_management", ("客户", "CRM", "自由职业", "接单")),
    ("study_planning", ("学习计划", "复习", "周计划", "笔记", "notion", "学习笔记")),
    ("resume_portfolio", ("简历", "作品集", "面试", "排版")),
    ("prompt_generation", ("提示词", "prompt", "AI绘画", "出图", "生图", "提示词模板")),
    ("design_assets", ("设计素材", "矢量", "logo", "图标", "模板", "PSD", "AI文件")),
    ("content_creation", ("文案", "写作", "短视频", "脚本", "内容")),
)
FAMILY_RULES = (
    ("notion_template", ("notion", "学习笔记模板", "template")),
    ("excel_template", ("excel", "xlsx", "表格", "学习计划表", "预算表")),
    ("prompt_pack", ("提示词", "prompt")),
    ("design_asset_pack", ("设计素材", "矢量", "PSD", "AI文件", "logo", "图标")),
    ("pdf_guide", ("pdf", "教程", "指南", "文档")),
)
LOCALE_RULES = (("zh", ("\u4e00", "\u9fff")), ("en", ("a", "z")))


def _match(text: str, rules) -> str:
    lowered = (text or "").lower()
    for label, words in rules:
        if any(str(w).lower() in lowered for w in words):
            return label
    return UNKNOWN


def infer(text: str) -> dict:
    return {
        "audience": _match(text, AUDIENCE_RULES),
        "task": _match(text, TASK_RULES),
        "deliverable_family": _match(text, FAMILY_RULES),
        "locale": "zh" if any("\u4e00" <= ch <= "\u9fff" for ch in text or "") else (
            "en" if re.search(r"[A-Za-z]", text or "") else UNKNOWN),
    }


def coarse_family(family: str) -> str:
    return models.FAMILY_NORM.get(family or UNKNOWN, family or UNKNOWN)


def identity_key(fields: dict) -> str:
    payload = {k: str(fields.get(k) or UNKNOWN) for k in
               ("audience", "task", "deliverable_family", "locale")}
    payload["deliverable_family"] = coarse_family(payload["deliverable_family"])
    return hashlib.sha256(models.canonical_json(payload).encode("utf-8")).hexdigest()


def _norm_alias(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().lower())


def _category(conn, identity):
    return conn.execute("SELECT * FROM categories WHERE identity_key=?", (identity,)).fetchone()


def _alias_category(conn, alias):
    """Alias lookup only; aliases are inserted manually (no auto-learning)."""
    row = conn.execute(
        "SELECT c.* FROM category_alias a JOIN categories c ON c.id=a.category_id "
        "WHERE a.alias_norm=? ORDER BY a.id LIMIT 1", (_norm_alias(alias),)).fetchone()
    return row


def _resolve_active(conn, category):
    """Follow merged_into recursively; return (category, excluded?) or (None, False)."""
    seen = set()
    row = category
    while row is not None and row["id"] not in seen:
        seen.add(row["id"])
        if row["status"] == "excluded":
            return row, True
        if row["status"] == "merged" and row["merged_into"]:
            row = conn.execute("SELECT * FROM categories WHERE id=?", (row["merged_into"],)).fetchone()
            continue
        if row["status"] == "active":
            return row, False
        break
    return None, False


def _review(conn, signal_id, reason, candidate_id=None):
    existing = conn.execute(
        "SELECT id FROM review_queue WHERE signal_id=? AND status='pending'", (signal_id,)).fetchone()
    if existing:
        return int(existing["id"]), False
    cur = conn.execute(
        "INSERT INTO review_queue(signal_id,reason,candidate_category_id,status,created_at) "
        "VALUES (?,?,?,'pending',?)",
        (signal_id, reason, candidate_id, models.utc_now()))
    conn.commit()
    return int(cur.lastrowid), True


def _event(conn, category_id, kind, signal_id, before=None, after=None, undo_of=None):
    cur = conn.execute(
        "INSERT INTO discovery_event(category_id,kind,signal_id,before_json,after_json,at,undo_of) "
        "VALUES (?,?,?,?,?,?,?)",
        (category_id, kind, signal_id,
         json.dumps(before, ensure_ascii=False) if before is not None else None,
         json.dumps(after, ensure_ascii=False) if after is not None else None,
         models.utc_now(), undo_of))
    conn.commit()
    return int(cur.lastrowid)


def _hits(text: str) -> dict:
    lowered = (text or "").lower()
    hits = {}
    for name, rules in (("audience", AUDIENCE_RULES), ("task", TASK_RULES),
                        ("deliverable_family", FAMILY_RULES)):
        matched = []
        for label, words in rules:
            for word in words:
                if str(word).lower() in lowered:
                    matched.append(f"{label}:{word}")
        hits[name] = matched[:8]
    return hits


def categorize_signal(conn, signal: dict, *, candidate_hint: bool = True,
                      explain: bool = False) -> dict:
    """Return outcome: new/update/review; never auto-merges similarity-only."""
    text = " ".join(str(signal.get(k) or "") for k in ("title", "quote"))
    fields = infer(text)
    key = identity_key(fields)
    detail = {"signal_id": int(signal["id"]), "fields": fields, "hits": _hits(text)} if explain else None
    row = _category(conn, key)
    alias = _alias_category(conn, text[:80])
    signal_id = int(signal["id"])
    fine_family = fields["deliverable_family"]
    coarse = coarse_family(fine_family)
    fields["deliverable_family"] = coarse
    carrier = fine_family

    if row is not None:
        target, excluded = _resolve_active(conn, row)
        if excluded:
            rid, _ = _review(conn, signal_id, "category_excluded: hit excluded category", int(row["id"]))
            return {"outcome": "review", "category_id": None, "review_id": rid,
                    "candidate_category_id": int(row["id"]),
                    "identity_key": key, "fields": fields,
                    **({"explain": detail} if explain else {})}
        if target is None:
            rid, _ = _review(conn, signal_id, "category_merged_without_target", int(row["id"]))
            return {"outcome": "review", "category_id": None, "review_id": rid,
                    "candidate_category_id": int(row["id"]),
                    "identity_key": key, "fields": fields,
                    **({"explain": detail} if explain else {})}
        carriers = []
        try:
            carriers = json.loads(target["deliverable_carriers"] or "[]")
        except Exception:
            carriers = []
        changed = carrier not in carriers
        if changed:
            carriers.append(carrier)
            new_label = target["canonical_label"]
            if carrier not in (new_label or ""):
                new_label = f'{target["canonical_label"]} · {carrier}'
            conn.execute(
                "UPDATE categories SET deliverable_carriers=?,canonical_label=? WHERE id=?",
                (json.dumps(carriers, ensure_ascii=False), new_label, target["id"]))
            conn.commit()
        _event(conn, int(target["id"]), "update", signal_id,
               before={"identity_key": target["identity_key"]},
               after={"signal_id": signal_id, "carrier": carrier, "carrier_changed": changed,
                      "deliverable_carriers": carriers})
        return {"outcome": "update", "category_id": int(target["id"]), "identity_key": target["identity_key"],
                "fields": fields, "carrier": carrier, "carrier_changed": changed,
                **({"explain": detail} if explain else {})}
    if alias is not None:
        target, excluded = _resolve_active(conn, alias)
        if excluded or target is None:
            rid, _ = _review(conn, signal_id, "alias_category_not_active", int(alias["id"]))
            return {"outcome": "review", "category_id": None, "review_id": rid,
                    "candidate_category_id": int(alias["id"]),
                    "identity_key": key, "fields": fields,
                    **({"explain": detail} if explain else {})}
        _event(conn, int(target["id"]), "update", signal_id,
               before={"alias": _norm_alias(text[:80])}, after={"signal_id": signal_id})
        return {"outcome": "update", "category_id": int(target["id"]), "identity_key": target["identity_key"],
                "fields": fields, **({"explain": detail} if explain else {})}

    # No exact key/alias. If fields are not unknown, create a new category (field difference is proof).
    # strict proof: task + deliverable_family known; audience or locale known.
    task_ok = fields["task"] != UNKNOWN and fields["deliverable_family"] != UNKNOWN
    context_ok = fields["audience"] != UNKNOWN or fields["locale"] != UNKNOWN
    if task_ok and context_ok:
        label = f'{fields["audience"]}/{fields["task"]}/{coarse}'
        cur = conn.execute(
            "INSERT INTO categories(identity_key,audience,task,deliverable_family,locale,"
            "canonical_label,status,deliverable_carriers,created_at) VALUES (?,?,?,?,?,?,'active',?,?)",
            (key, fields["audience"], fields["task"], coarse,
             fields["locale"], label, json.dumps([carrier], ensure_ascii=False), models.utc_now()))
        cid = int(cur.lastrowid)
        conn.commit()
        _event(conn, cid, "new", signal_id, before=None,
               after={"fields": fields, "carriers": [carrier]})
        return {"outcome": "new", "category_id": cid, "identity_key": key, "fields": fields,
                "carrier": carrier, **({"explain": detail} if explain else {})}

    # Not enough fields to prove identity: similarity only -> review, never merge.
    candidates = []
    if candidate_hint:
        for cat in conn.execute("SELECT * FROM categories WHERE status='active'").fetchall():
            ratio = difflib.SequenceMatcher(None, text[:120], cat["canonical_label"]).ratio()
            if ratio >= 0.35:
                candidates.append((ratio, int(cat["id"])))
    candidates.sort(reverse=True)
    cid = candidates[0][1] if candidates else None
    rid, _ = _review(conn, signal_id, "fields_unknown_or_similarity_only", cid)
    return {"outcome": "review", "category_id": cid, "review_id": rid,
            "identity_key": key, "fields": fields,
            **({"explain": detail} if explain else {})}


def run_categorize(conn, *, explain: bool = False) -> dict:
    """Idempotent pass: only signals with no event and no pending review are processed."""
    stats = {"signals": 0, "new": 0, "update": 0, "review": 0, "skipped": 0, "categories": 0}
    if explain:
        stats["details"] = []
    rows = conn.execute(
        "SELECT s.* FROM signals s WHERE NOT EXISTS "
        "(SELECT 1 FROM discovery_event e WHERE e.signal_id=s.id) "
        "AND NOT EXISTS (SELECT 1 FROM review_queue r WHERE r.signal_id=s.id AND r.status='pending') "
        "ORDER BY s.id").fetchall()
    for signal in rows:
        stats["signals"] += 1
        out = categorize_signal(conn, dict(signal), explain=explain)
        stats[out["outcome"]] += 1
        if explain:
            stats["details"].append({**out.get("explain", {}), "outcome": out["outcome"],
                                     "category_id": out.get("category_id")})
    stats["skipped"] = conn.execute("SELECT COUNT(*) FROM signals").fetchone()[0] - stats["signals"]
    stats["categories"] = conn.execute(
        "SELECT COUNT(*) FROM categories WHERE status='active'").fetchone()[0]
    return stats


def _gaps_for(conn, category_id):
    signals = conn.execute(
        "SELECT * FROM signals WHERE id IN (SELECT DISTINCT signal_id FROM discovery_event "
        "WHERE category_id=? AND signal_id IS NOT NULL) ORDER BY id", (category_id,)).fetchall()
    gaps = []
    if not signals:
        return signals, ["no_evidence"]
    if all(s["listed_price_minor"] is None for s in signals):
        gaps.append("price_unknown")
    if all(s["wants"] is None for s in signals):
        gaps.append("wants_unknown")
    if not any(s["platform"] != "xianyu" for s in signals):
        gaps.append("comments_or_second_platform_unknown")
    return signals, gaps


def make_cards(conn) -> dict:
    """Create or refresh active cards; never revive a merged tombstone."""
    created = 0
    refreshed = 0
    for cat in conn.execute("SELECT * FROM categories WHERE status='active' ORDER BY id").fetchall():
        signals, gaps = _gaps_for(conn, cat["id"])
        if not signals:
            continue
        evidence = [int(s["id"]) for s in signals]
        existing = conn.execute("SELECT * FROM direction_card WHERE category_id=?", (cat["id"],)).fetchone()
        if existing:
            if existing["status"] == "merged":
                continue
            conn.execute(
                "UPDATE direction_card SET audience=?,task=?,deliverable=?,evidence_ids_json=?,gaps_json=? WHERE id=?",
                (cat["audience"], cat["task"], cat["deliverable_family"],
                 json.dumps(evidence), json.dumps(gaps), existing["id"]))
            refreshed += 1
        else:
            conn.execute(
                "INSERT INTO direction_card(category_id,audience,task,deliverable,evidence_ids_json,"
                "gaps_json,status,created_at) VALUES (?,?,?,?,?,?,'draft',?)",
                (cat["id"], cat["audience"], cat["task"], cat["deliverable_family"],
                 json.dumps(evidence), json.dumps(gaps), models.utc_now()))
            created += 1
    conn.commit()
    return {"created": created, "refreshed": refreshed,
            "cards": conn.execute("SELECT COUNT(*) FROM direction_card").fetchone()[0]}


def list_cards(conn) -> list[dict]:
    return [dict(r) for r in conn.execute(
        "SELECT id,category_id,audience,task,deliverable,evidence_ids_json,gaps_json,status,created_at "
        "FROM direction_card ORDER BY id")]


def list_ledger(conn) -> list[dict]:
    rows = []
    for cat in conn.execute("SELECT * FROM categories ORDER BY id").fetchall():
        events = [dict(e) for e in conn.execute(
            "SELECT id,kind,signal_id,at,undo_of FROM discovery_event WHERE category_id=? ORDER BY id",
            (cat["id"],))]
        rows.append({**dict(cat), "events": events})
    return rows


def merge(conn, source_id: int, target_id: int, *, reason: str = "manual_merge") -> dict:
    src = conn.execute("SELECT * FROM categories WHERE id=?", (source_id,)).fetchone()
    dst = conn.execute("SELECT * FROM categories WHERE id=?", (target_id,)).fetchone()
    if src is None or dst is None or source_id == target_id:
        raise ValueError("merge_requires_two_existing_distinct_categories")
    source_events = [int(r[0]) for r in conn.execute(
        "SELECT id FROM discovery_event WHERE category_id=?", (source_id,))]
    source_aliases = [int(r[0]) for r in conn.execute(
        "SELECT id FROM category_alias WHERE category_id=?", (source_id,))]
    source_cards = [dict(r) for r in conn.execute(
        "SELECT * FROM direction_card WHERE category_id=?", (source_id,))]
    target_cards = conn.execute(
        "SELECT COUNT(*) FROM direction_card WHERE category_id=?", (target_id,)).fetchone()[0]
    before = {"source": dict(src), "target": dict(dst),
              "source_event_ids": source_events, "source_alias_ids": source_aliases,
              "source_cards": source_cards, "target_card_count": target_cards}
    try:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute("UPDATE categories SET status='merged',merged_into=? WHERE id=?",
                     (target_id, source_id))
        if source_events:
            q = ",".join("?" for _ in source_events)
            conn.execute(f"UPDATE discovery_event SET category_id=?,origin_category_id=? "
                         f"WHERE id IN ({q})", (target_id, source_id, *source_events))
        if source_aliases:
            q = ",".join("?" for _ in source_aliases)
            conn.execute(f"UPDATE category_alias SET category_id=? WHERE id IN ({q})",
                         (target_id, *source_aliases))
        if source_cards:
            for card in source_cards:
                if target_cards:
                    # keep both; source card becomes a merged tombstone (not hard-deleted)
                    conn.execute("UPDATE direction_card SET status='merged',merged_into=? WHERE id=?",
                                 (target_id, card["id"]))
                else:
                    conn.execute("UPDATE direction_card SET category_id=? WHERE id=?",
                                 (target_id, card["id"]))
        cur = conn.execute(
            "INSERT INTO discovery_event(category_id,kind,signal_id,before_json,after_json,at) "
            "VALUES (?, 'merge', NULL, ?, ?, ?)",
            (source_id, json.dumps(before, ensure_ascii=False),
             json.dumps({"merged_into": target_id, "reason": reason}, ensure_ascii=False),
             models.utc_now()))
        event_id = int(cur.lastrowid)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return {"event_id": event_id, "source_id": source_id, "target_id": target_id,
            "source_card_count": len(source_cards), "target_card_count": target_cards}


def undo(conn, event_id: int) -> dict:
    event = conn.execute("SELECT * FROM discovery_event WHERE id=?", (event_id,)).fetchone()
    if event is None:
        raise ValueError("event_not_found")
    before = json.loads(event["before_json"] or "{}")
    try:
        conn.execute("BEGIN IMMEDIATE")
        if event["kind"] == "merge":
            source = before.get("source") or {}
            sid = source.get("id")
            if sid:
                conn.execute("UPDATE categories SET status=?,merged_into=? WHERE id=?",
                             (source.get("status", "active"), source.get("merged_into"), sid))
                ids = before.get("source_event_ids") or []
                if ids:
                    q = ",".join("?" for _ in ids)
                    conn.execute(f"UPDATE discovery_event SET category_id=?,origin_category_id=NULL "
                                 f"WHERE id IN ({q})", (sid, *ids))
                aids = before.get("source_alias_ids") or []
                if aids:
                    q = ",".join("?" for _ in aids)
                    conn.execute(f"UPDATE category_alias SET category_id=? WHERE id IN ({q})",
                                 (sid, *aids))
                # cards explicitly recorded as source's own; move back and restore status
                for card in before.get("source_cards") or []:
                    conn.execute("UPDATE direction_card SET category_id=?,status=?,merged_into=? WHERE id=?",
                                 (sid, card.get("status", "draft"), None, card["id"]))
        elif event["kind"] == "exclude":
            cid = (before.get("category") or {}).get("id")
            if cid:
                conn.execute("UPDATE categories SET status='active' WHERE id=?", (cid,))
        elif event["kind"] == "split":
            source = before.get("category") or {}
            sid = source.get("id")
            moved = before.get("moved_events") or []
            for move in moved:
                conn.execute("UPDATE discovery_event SET category_id=? WHERE id=?",
                             (move["from"], move["event_id"]))
            if sid:
                card = conn.execute("SELECT * FROM direction_card WHERE category_id=? AND status<>'merged'",
                                     (sid,)).fetchone()
                if card:
                    old = before.get("source_card_evidence")
                    if old is not None:
                        conn.execute("UPDATE direction_card SET evidence_ids_json=? WHERE id=?",
                                     (json.dumps(old), card["id"]))
            child = before.get("new_category_id")
            if child:
                child_card = conn.execute("SELECT * FROM direction_card WHERE category_id=?", (child,)).fetchone()
                if child_card:
                    try:
                        ev = json.loads(child_card["evidence_ids_json"] or "[]")
                    except Exception:
                        ev = []
                    moved_ids = {m["signal_id"] for m in moved}
                    ev = [x for x in ev if x not in moved_ids]
                    conn.execute("UPDATE direction_card SET evidence_ids_json=?,status='merged',merged_into=? WHERE id=?",
                                 (json.dumps(ev), sid, child_card["id"]))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    undo_id = _event(conn, event["category_id"], "undo", event["signal_id"],
                     before={"undo_of": event_id}, after=before, undo_of=event_id)
    return {"undo_event_id": undo_id, "undo_of": event_id}


def exclude(conn, category_id: int, reason: str = "manual_exclude") -> dict:
    cat = conn.execute("SELECT * FROM categories WHERE id=?", (category_id,)).fetchone()
    if cat is None:
        raise ValueError("category_not_found")
    conn.execute("UPDATE categories SET status='excluded' WHERE id=?", (category_id,))
    conn.commit()
    return {"event_id": _event(conn, category_id, "exclude", None, before={"category": dict(cat)},
                               after={"status": "excluded", "reason": reason})}


def include(conn, category_id: int, reason: str = "manual_include") -> dict:
    cat = conn.execute("SELECT * FROM categories WHERE id=?", (category_id,)).fetchone()
    if cat is None:
        raise ValueError("category_not_found")
    conn.execute("UPDATE categories SET status='active',merged_into=NULL WHERE id=?", (category_id,))
    conn.commit()
    return {"event_id": _event(conn, category_id, "include", None, before={"category": dict(cat)},
                               after={"status": "active", "reason": reason})}


def split(conn, category_id: int, signal_ids: list[int], label: str | None = None) -> dict:
    cat = conn.execute("SELECT * FROM categories WHERE id=?", (category_id,)).fetchone()
    if cat is None:
        raise ValueError("category_not_found")
    ids = [int(x) for x in signal_ids]
    fields = {"audience": cat["audience"], "task": cat["task"],
              "deliverable_family": cat["deliverable_family"], "locale": cat["locale"]}
    new_key = identity_key({**fields, "task": fields["task"] + "#split"})
    moved = []
    for sid in ids:
        for ev in conn.execute("SELECT id,category_id FROM discovery_event WHERE signal_id=? AND category_id=?",
                               (sid, category_id)).fetchall():
            moved.append({"signal_id": sid, "event_id": int(ev["id"]), "from": int(ev["category_id"])})
    source_card = conn.execute(
        "SELECT * FROM direction_card WHERE category_id=? AND status<>'merged'", (category_id,)).fetchone()
    old_evidence = None
    if source_card:
        try:
            old_evidence = json.loads(source_card["evidence_ids_json"] or "[]")
        except Exception:
            old_evidence = []
    try:
        conn.execute("BEGIN IMMEDIATE")
        cur = conn.execute(
            "INSERT INTO categories(identity_key,audience,task,deliverable_family,locale,canonical_label,"
            "status,created_at) VALUES (?,?,?,?,?,?,'active',?)",
            (new_key, fields["audience"], fields["task"] + "#split", fields["deliverable_family"],
             fields["locale"], label or (cat["canonical_label"] + " / split"), models.utc_now()))
        new_id = int(cur.lastrowid)
        for move in moved:
            conn.execute("UPDATE discovery_event SET category_id=? WHERE id=?", (new_id, move["event_id"]))
        if source_card:
            kept = [x for x in old_evidence if x not in set(ids)] if old_evidence is not None else []
            conn.execute("UPDATE direction_card SET evidence_ids_json=? WHERE id=?",
                         (json.dumps(kept), source_card["id"]))
        # child card with moved evidence (draft; no fabrication of fields)
        if moved:
            conn.execute(
                "INSERT INTO direction_card(category_id,audience,task,deliverable,evidence_ids_json,"
                "gaps_json,status,created_at) VALUES (?,?,?,?,?,'[]','draft',?)",
                (new_id, cat["audience"], cat["task"] + "#split", cat["deliverable_family"],
                 json.dumps(sorted({m["signal_id"] for m in moved})), models.utc_now()))
        cur = conn.execute(
            "INSERT INTO discovery_event(category_id,kind,signal_id,before_json,after_json,at) "
            "VALUES (?, 'split', NULL, ?, ?, ?)",
            (category_id, json.dumps({"category": dict(cat), "signal_ids": ids,
                                      "moved_events": moved, "source_card_evidence": old_evidence,
                                      "new_category_id": new_id}, ensure_ascii=False),
             json.dumps({"new_category_id": new_id}, ensure_ascii=False), models.utc_now()))
        event_id = int(cur.lastrowid)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return {"event_id": event_id, "new_category_id": new_id, "moved_events": moved}
