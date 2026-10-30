"""B16：货源候选管理（新增/编辑/停用/JSON 导入）与“采用为选定货源”。

候选 id 形如 `sc:<8hex>`；停用为软删除（is_active=0）。采用写 selected_supply_id / supply_version /
三项许可 / supply_note，并记 workorder_event（首次 supply_select，替换 supply_replace 并记录旧值）。
"""

from __future__ import annotations

import json
import re
import time
import uuid

import workflow as wf

KINDS = ("同款", "替代", "不匹配")
LICENSE_VALUES = {"yes", "no", "unknown", "允许", "禁止", "不明"}
CAND_COLUMNS = ("provider", "source_url", "kind", "commercial", "redistribute", "resale", "license_note",
                "price_minor", "currency", "sample_status", "note", "conclusion")

FIELD_ALIASES = {
    "provider": ("provider", "vendor", "seller"),
    "source_url": ("source_url", "url", "link"),
    "kind": ("kind", "match", "match_kind"),
    "commercial": ("commercial", "license_commercial"),
    "redistribute": ("redistribute", "license_redistribute"),
    "resale": ("resale", "resale_allowed", "license_resale"),
    "license_note": ("license_note", "license_scope", "license_verdict"),
    "price_minor": ("price_minor",),
    "currency": ("currency",),
    "sample_status": ("sample_status",),
    "note": ("note", "fit_note", "remark"),
    "conclusion": ("conclusion", "verdict"),
}


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _text(value, limit: int = 500) -> str:
    return str(value or "").strip()[:limit]


def _license(value) -> str:
    low = str(value or "").strip().lower()
    if low in ("yes", "true", "1", "允许", "可"):
        return "yes"
    if low in ("no", "false", "0", "禁止", "不可"):
        return "no"
    if low in ("", "unknown", "不明"):
        return "unknown"
    raise wf.Reject("candidate_invalid", f"许可值只能是 yes/no/unknown（收到 {value!r}）")


def normalize_candidate(payload: dict) -> dict:
    data: dict = {}
    provider = _text(payload.get("provider"), 120)
    if not provider:
        raise wf.Reject("candidate_invalid", "provider 必填")
    data["provider"] = provider
    url = _text(payload.get("source_url"), 500)
    if url:
        from urllib.parse import urlparse
        if urlparse(url).scheme not in ("http", "https", "self"):
            raise wf.Reject("candidate_invalid", "source_url 必须是 http/https/self 链接")
    data["source_url"] = url
    kind = _text(payload.get("kind"), 20) or "替代"
    if kind not in KINDS:
        raise wf.Reject("candidate_invalid", f"kind 只能是 {'/'.join(KINDS)}")
    data["kind"] = kind
    for key in ("commercial", "redistribute", "resale"):
        data[key] = _license(payload.get(key))
    data["license_note"] = _text(payload.get("license_note"), 300)
    price_raw = str(payload.get("price_minor") or "").strip()
    if price_raw:
        digits = re.sub(r"[^0-9]", "", price_raw)
        data["price_minor"] = int(digits) if digits else None
    else:
        data["price_minor"] = None
    data["currency"] = _text(payload.get("currency"), 8) or "CNY"
    data["sample_status"] = _text(payload.get("sample_status"), 20)
    data["note"] = _text(payload.get("note"), 300)
    data["conclusion"] = _text(payload.get("conclusion"), 20)
    return data


def list_candidates(conn, workorder_id: str, *, active_only: bool = True) -> list[dict]:
    try:
        sql = "SELECT * FROM workorder_supply_candidate WHERE workorder_id=?"
        if active_only:
            sql += " AND is_active=1"
        rows = conn.execute(sql + " ORDER BY created_at DESC, id", (workorder_id,)).fetchall()
    except Exception:  # noqa: BLE001
        return []
    return [dict(r) for r in rows]


def get_candidate(conn, workorder_id: str, candidate_id: str) -> dict | None:
    row = conn.execute("SELECT * FROM workorder_supply_candidate WHERE workorder_id=? AND id=?",
                       (workorder_id, candidate_id)).fetchone()
    return dict(row) if row else None


def add(conn, workorder_id: str, payload: dict) -> dict:
    wf.init_schema(conn)
    if wf.get(conn, workorder_id) is None:
        raise wf.Reject("not_found", "工作单不存在", 404)
    data = normalize_candidate(payload)
    cid = f"sc:{uuid.uuid4().hex[:8]}"
    now = _now()
    conn.execute("""INSERT INTO workorder_supply_candidate
        (id, workorder_id, provider, source_url, kind, commercial, redistribute, resale, license_note,
         price_minor, currency, sample_status, note, conclusion, is_active, created_at, updated_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,1,?,?)""",
                 (cid, workorder_id, data["provider"], data["source_url"], data["kind"], data["commercial"],
                  data["redistribute"], data["resale"], data["license_note"], data["price_minor"],
                  data["currency"], data["sample_status"], data["note"], data["conclusion"], now, now))
    conn.execute("INSERT INTO workorder_event (workorder_id, action, detail, at) VALUES (?,?,?,?)",
                 (workorder_id, "supply_candidate_add", f"{cid} {data['provider'][:40]}", now))
    conn.commit()
    return get_candidate(conn, workorder_id, cid) or {}


def _invalidate_sample_cost(conn, workorder_id: str, now: str) -> None:
    """货源变动后旧样品与成本证据不再可信：清空并要求重做。"""
    conn.execute("""UPDATE workorder SET sample_status=NULL, sample_ref=NULL,
                    cost_known='no', cost_minor=NULL WHERE workorder_id=?""", (workorder_id,))


def _sync_selected(conn, workorder_id: str, candidate: dict, *, event: str, detail: str) -> None:
    """已选候选变化 → 同步许可/版本/备注，并使样品与成本失效（revision+1，同事务）。"""
    now = _now()
    _invalidate_sample_cost(conn, workorder_id, now)
    conn.execute("""UPDATE workorder SET supply_version=?, supply_license_commercial=?,
                    supply_license_redistribute=?, supply_license_resell=?, supply_note=?,
                    revision=revision+1, updated_at=? WHERE workorder_id=?""",
                 (candidate.get("updated_at") or "", candidate["commercial"], candidate["redistribute"],
                  candidate["resale"], f'{candidate["provider"]} {candidate.get("source_url") or ""}'.strip(),
                  now, workorder_id))
    conn.execute("INSERT INTO workorder_event (workorder_id, action, detail, at) VALUES (?,?,?,?)",
                 (workorder_id, event, detail, now))


def update_candidate(conn, workorder_id: str, candidate_id: str, payload: dict) -> dict:
    wf.init_schema(conn)
    row = get_candidate(conn, workorder_id, candidate_id)
    if row is None:
        raise wf.Reject("not_found", "候选不存在", 404)
    merged = {k: (payload.get(k) if k in payload else row.get(k)) for k in CAND_COLUMNS}
    data = normalize_candidate(merged)
    now = _now()
    try:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute("""UPDATE workorder_supply_candidate SET provider=?, source_url=?, kind=?, commercial=?,
            redistribute=?, resale=?, license_note=?, price_minor=?, currency=?, sample_status=?, note=?,
            conclusion=?, updated_at=? WHERE workorder_id=? AND id=?""",
                     (data["provider"], data["source_url"], data["kind"], data["commercial"], data["redistribute"],
                      data["resale"], data["license_note"], data["price_minor"], data["currency"],
                      data["sample_status"], data["note"], data["conclusion"], now, workorder_id, candidate_id))
        conn.execute("INSERT INTO workorder_event (workorder_id, action, detail, at) VALUES (?,?,?,?)",
                     (workorder_id, "supply_candidate_update", candidate_id, now))
        record = wf.get(conn, workorder_id)
        if record and record.get("selected_supply_id") == candidate_id:
            fresh = get_candidate(conn, workorder_id, candidate_id) or {}
            _sync_selected(conn, workorder_id, fresh, event="supply_sync",
                           detail=f"{candidate_id} 许可 {row['commercial']}/{row['redistribute']}/{row['resale']}"
                                  f" -> {data['commercial']}/{data['redistribute']}/{data['resale']}；样品与成本已失效")
        conn.commit()
    except wf.Reject:
        raise
    except Exception as exc:  # noqa: BLE001
        conn.rollback()
        raise wf.Reject("update_failed", f"更新失败已回滚：{type(exc).__name__}", 409)
    return get_candidate(conn, workorder_id, candidate_id) or {}


def deactivate(conn, workorder_id: str, candidate_id: str, *, confirm: str) -> dict:
    wf.init_schema(conn)
    if str(confirm) != "1":
        raise wf.Reject("confirm_required", "停用是软删除，需要二次确认（confirm=1）", 400)
    row = get_candidate(conn, workorder_id, candidate_id)
    if row is None:
        raise wf.Reject("not_found", "候选不存在", 404)
    now = _now()
    try:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute("UPDATE workorder_supply_candidate SET is_active=0, updated_at=? WHERE workorder_id=? AND id=?",
                     (now, workorder_id, candidate_id))
        conn.execute("INSERT INTO workorder_event (workorder_id, action, detail, at) VALUES (?,?,?,?)",
                     (workorder_id, "supply_candidate_deactivate", candidate_id, now))
        record = wf.get(conn, workorder_id)
        if record and record.get("selected_supply_id") == candidate_id:
            _invalidate_sample_cost(conn, workorder_id, now)
            conn.execute("""UPDATE workorder SET selected_supply_id=NULL, supply_license_commercial='unknown',
                            supply_license_redistribute='unknown', supply_license_resell='unknown',
                            revision=revision+1, updated_at=? WHERE workorder_id=?""", (now, workorder_id))
            conn.execute("INSERT INTO workorder_event (workorder_id, action, detail, at) VALUES (?,?,?,?)",
                         (workorder_id, "supply_deactivate_selected",
                          f"{candidate_id} 已停用 → 货源清空、许可 unknown、样品与成本失效", now))
        conn.commit()
    except wf.Reject:
        raise
    except Exception as exc:  # noqa: BLE001
        conn.rollback()
        raise wf.Reject("update_failed", f"停用失败已回滚：{type(exc).__name__}", 409)
    return get_candidate(conn, workorder_id, candidate_id) or {}


def import_json(conn, workorder_id: str, text: str) -> dict:
    """粘贴 JSON 数组导入；字段名兼容 b2/candidates.json（未知字段忽略并计入 skipped）。"""
    wf.init_schema(conn)
    if wf.get(conn, workorder_id) is None:
        raise wf.Reject("not_found", "工作单不存在", 404)
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise wf.Reject("import_invalid", f"JSON 解析失败：{exc.msg}", 400)
    if not isinstance(data, list):
        raise wf.Reject("import_invalid", "需要 JSON 数组", 400)
    imported, skipped = 0, []
    for index, item in enumerate(data):
        if not isinstance(item, dict):
            skipped.append({"index": index, "reason": "not_object"})
            continue
        mapped: dict = {}
        for target, aliases in FIELD_ALIASES.items():
            for alias in aliases:
                if alias in item and item[alias] not in (None, ""):
                    mapped[target] = item[alias]
                    break
        price = item.get("price")
        if isinstance(price, dict) and price.get("amount") is not None:
            mapped.setdefault("price_minor", price.get("amount"))
            mapped.setdefault("currency", price.get("currency") or "CNY")
        unknown = [k for k in item if k not in {a for aliases in FIELD_ALIASES.values() for a in aliases}
                   and k not in ("price", "native_id", "license_verdict")]
        try:
            add(conn, workorder_id, mapped)
            imported += 1
            if unknown:
                skipped.append({"index": index, "ignored_fields": unknown})
        except wf.Reject as exc:
            skipped.append({"index": index, "reason": exc.message})
    return {"imported": imported, "skipped": skipped, "total": len(data)}


def select_candidate(conn, workorder_id: str, candidate_id: str, *, revision) -> dict:
    """采用为选定货源：CSRF 由路由保证；这里做 revision 乐观锁与事件记录。"""
    wf.init_schema(conn)
    record = wf.get(conn, workorder_id)
    if record is None:
        raise wf.Reject("not_found", "工作单不存在", 404)
    raw = str(revision).strip() if revision is not None else ""
    if not raw.isdigit():
        raise wf.Reject("revision_invalid", f"revision 必须是 ASCII 正整数（收到 {revision!r}）")
    rev = int(raw)
    if rev != int(record["revision"]):
        raise wf.Reject("revision_conflict", f"版本冲突：当前 revision={record['revision']}，提交 {rev}", 409)
    row = get_candidate(conn, workorder_id, candidate_id)
    if row is None or not row["is_active"]:
        raise wf.Reject("not_found", "候选不存在或已停用", 404)
    old = record.get("selected_supply_id")
    version = (row.get("created_at") or "")[:19].replace("-", "").replace(":", "") or "v1"
    note = f'{row["provider"]} {row.get("source_url") or ""}'.strip()
    now = _now()
    try:
        conn.execute("BEGIN IMMEDIATE")
        if old and old != candidate_id:
            _invalidate_sample_cost(conn, workorder_id, now)     # 换源：旧样品/成本作废
        cur = conn.execute("""UPDATE workorder SET selected_supply_id=?, supply_version=?,
            supply_license_commercial=?, supply_license_redistribute=?, supply_license_resell=?,
            supply_note=?, revision=revision+1, updated_at=? WHERE workorder_id=? AND revision=?""",
                           (candidate_id, version, row["commercial"], row["redistribute"], row["resale"],
                            note, now, workorder_id, rev))
        if cur.rowcount != 1:
            conn.rollback()
            raise wf.Reject("revision_conflict", "版本冲突：UPDATE 命中 0 行，本次未写入", 409)
        action = "supply_replace" if old else "supply_select"
        detail = (f"{candidate_id}" if not old
                  else f"{old} -> {candidate_id}；旧样品与成本已失效，需重新自检与重填")
        conn.execute("INSERT INTO workorder_event (workorder_id, action, detail, at) VALUES (?,?,?,?)",
                     (workorder_id, action, detail, now))
        conn.commit()
    except wf.Reject:
        raise
    except Exception as exc:  # noqa: BLE001
        conn.rollback()
        raise wf.Reject("update_failed", f"采用失败已回滚：{type(exc).__name__}", 409)
    return wf.get(conn, workorder_id) or {}
