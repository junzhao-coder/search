"""B3：上架准备检查（服务端推导）与人工上架包导出（买家可见字段白名单 + 版本戳）。

设计原则
- **就绪只能由服务端从字段/证据推导**，没有任何“标记完成”的入口；客户端提交 ready/gate
  字段一律在 `workflow.normalize_fields` 被拒。
- 导出内容**只含买家可见字段**：成本、利润、打分、货源内部备注、内部路径一律不出现。
- 每次导出记录版本戳（revision / 文案版本 / 货源 ID+版本 / 生成 UTC / 内容清单）；
  任一维度变化后，旧导出被标记为**失效**（详情页提示需重新检查与导出）。
"""

from __future__ import annotations

import hashlib
import json
import time

import workflow as wf

LICENSE_KEYS = ("supply_license_commercial", "supply_license_redistribute", "supply_license_resell")
LICENSE_LABEL = {
    "supply_license_commercial": "可商用",
    "supply_license_redistribute": "可再分发",
    "supply_license_resell": "可转售",
}
YES = {"yes", "true", "1", "允许", "可"}
NO = {"no", "false", "0", "禁止", "不可"}

EVIDENCE_FIELDS = (
    "selected_supply_id", "supply_version",
    "supply_license_commercial", "supply_license_redistribute", "supply_license_resell",
    "sample_status", "sample_ref", "sample_note", "cost_minor", "cost_known", "platform_evidence",
    "copy_status", "copy_version",
    "selling_points", "price_minor", "delivery_note", "aftersales_note", "faq_json",
)

BUYER_FIELDS = ("title", "selling_points", "contents", "format", "price", "delivery", "aftersales", "faq")

INTERNAL_MARKERS = ("cost", "profit", "margin", "score", "internal", "raw_ref", "snapshot", "supply_note",
                    "成本", "利润", "打分", "毛利", "内部")


def _txt(record: dict, key: str) -> str:
    return str(record.get(key) or "").strip()


def readiness(record: dict) -> dict:
    """逐项检查；只有全部 ok 时 overall_ready 为 True。"""
    checks: list[dict] = []

    def add(key: str, label: str, ok: bool, blocker: str = "") -> None:
        checks.append({"key": key, "label": label, "ok": bool(ok), "blocker": "" if ok else blocker})

    missing_specs = [label for key, label in (("name", "计划商品名"), ("use_case", "具体用途"),
                                              ("deliverable", "拟交付物"), ("target_platform", "目标平台"))
                     if not _txt(record, key)]
    add("specs", "产品规格完整", not missing_specs,
        "缺少：" + "、".join(missing_specs) if missing_specs else "")

    add("supply", "已选货源", bool(_txt(record, "selected_supply_id")),
        "未选货源（selected_supply_id 为空）")

    licenses = {k: _txt(record, k).lower() for k in LICENSE_KEYS}
    bad = [LICENSE_LABEL[k] for k in LICENSE_KEYS if licenses[k] not in YES]
    detail = "、".join(f"{LICENSE_LABEL[k]}={licenses[k] or '未记录'}" for k in LICENSE_KEYS)
    add("license", "许可三档均允许（可商用/可再分发/可转售）", not bad,
        f"未通过：{detail}" if bad else "")

    sample_ok = _txt(record, "sample_status").lower() in ("verified", "已核对", "ok")
    add("sample", "样品或交付入口已核验", sample_ok,
        "未核验样品/交付入口（sample_status 非 verified）" if not sample_ok else "")

    cost_minor = record.get("cost_minor")
    cost_ok = (isinstance(cost_minor, int) and cost_minor > 0) or _txt(record, "cost_known").lower() in YES
    add("cost", "成本已知", cost_ok, "成本未知（cost_minor 未填且 cost_known 非 yes）")

    add("platform", f"目标平台条件有证据（{_txt(record, 'target_platform') or '未填'}）",
        bool(_txt(record, "platform_evidence")), "缺少目标平台条件证据（platform_evidence 为空）")

    copy_ok = _txt(record, "copy_status").lower() in ("final", "定稿") and bool(_txt(record, "copy_version"))
    add("copy", "文案定稿", copy_ok, "文案未定稿（copy_status 非 final 或 copy_version 为空）")

    return {"checks": checks, "overall_ready": all(c["ok"] for c in checks),
            "blockers": [f'{c["label"]}：{c["blocker"]}' for c in checks if not c["ok"]]}


def version_stamp(record: dict) -> dict:
    contents = ["title", "selling_points", "listing_contents", "format", "price", "delivery", "aftersales", "faq"]
    stamp = {
        "workorder_id": _txt(record, "workorder_id"),
        "revision": int(record.get("revision") or 0),
        "copy_version": _txt(record, "copy_version"),
        "supply_id": _txt(record, "selected_supply_id"),
        "supply_version": _txt(record, "supply_version"),
        "generated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "contents": contents,
    }
    stamp["stamp_hash"] = hashlib.sha256(
        json.dumps({k: stamp[k] for k in ("revision", "copy_version", "supply_id", "supply_version", "contents")},
                   ensure_ascii=False, sort_keys=True).encode()).hexdigest()
    return stamp


def _faq(record: dict) -> list[dict]:
    raw = _txt(record, "faq_json")
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return []
    out = []
    for item in data if isinstance(data, list) else []:
        if isinstance(item, dict) and str(item.get("q") or "").strip():
            out.append({"q": str(item.get("q")).strip(), "a": str(item.get("a") or "").strip()})
    return out


def build_export(record: dict) -> dict:
    """买家可见字段白名单（不含成本/利润/打分/内部备注/路径）。"""
    price_minor = record.get("price_minor")
    payload = {
        "title": _txt(record, "name"),
        "selling_points": [p.strip() for p in _txt(record, "selling_points").splitlines() if p.strip()],
        "contents": {"includes": _txt(record, "includes"), "excludes": _txt(record, "excludes")},
        "format": {"fmt": _txt(record, "fmt"), "language": _txt(record, "language"), "version": _txt(record, "version")},
        "price": {"amount_minor": int(price_minor) if isinstance(price_minor, int) else None,
                  "currency": "CNY", "note": "定价建议，最终以卖家填写为准"},
        "delivery": _txt(record, "delivery_note"),
        "aftersales": _txt(record, "aftersales_note"),
        "faq": _faq(record),
    }
    blob = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    leaked = [m for m in INTERNAL_MARKERS if m in blob.lower()]
    if leaked:                       # 白名单自检：出现内部标记即以业务拒绝（409，不是 500）
        raise wf.Reject("export_internal_leak", f"导出内容包含内部字段标记：{', '.join(leaked)}", 409)
    payload["version_stamp"] = version_stamp(record)
    payload["buyer_visible_fields"] = list(BUYER_FIELDS)
    return payload


def to_markdown(payload: dict) -> str:
    stamp = payload["version_stamp"]
    lines = [f"# {payload['title']}", "", f"> 版本戳：revision {stamp['revision']} · 文案 {stamp['copy_version'] or '—'}"
             f" · 货源 {stamp['supply_id'] or '—'}@{stamp['supply_version'] or '—'} · 生成 {stamp['generated_utc']}",
             "", "## 卖点"]
    lines += [f"- {p}" for p in payload["selling_points"]] or ["- （未填写）"]
    lines += ["", "## 内容清单", f"- 包含：{payload['contents']['includes'] or '—'}",
              f"- 不包含：{payload['contents']['excludes'] or '—'}",
              "", "## 格式与兼容",
              f"- 格式：{payload['format']['fmt'] or '—'} · 语言：{payload['format']['language'] or '—'}"
              f" · 版本：{payload['format']['version'] or '—'}",
              "", "## 价格规格"]
    if payload["price"]["amount_minor"] is not None:
        lines.append(f"- 建议售价：¥{payload['price']['amount_minor'] / 100:.2f}（{payload['price']['currency']}）")
    else:
        lines.append("- 建议售价：未填写")
    lines += ["", "## 交付与售后", f"- 交付：{payload['delivery'] or '—'}", f"- 售后：{payload['aftersales'] or '—'}",
              "", "## FAQ"]
    lines += [f"- **{item['q']}**：{item['a'] or '—'}" for item in payload["faq"]] or ["- （未填写）"]
    lines.append("")
    return "\n".join(lines)


# 文案快照字段（买家可见相关；用于版本历史与“同内容不新增”判定）
COPY_FIELDS = ("name", "selling_points", "includes", "excludes", "fmt", "language", "version",
               "price_minor", "delivery_note", "aftersales_note", "faq_json")


def copy_snapshot(record: dict) -> dict:
    return {k: (record.get(k) if k == "price_minor" else (record.get(k) or "")) for k in COPY_FIELDS}


def copy_hash(snapshot: dict) -> str:
    return hashlib.sha256(json.dumps(snapshot, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def list_copy_versions(conn, workorder_id: str) -> list[dict]:
    try:
        rows = conn.execute("""SELECT version_no, content_hash, created_at, created_by, snapshot_json
                               FROM workorder_copy_version WHERE workorder_id=? ORDER BY version_no DESC""",
                            (workorder_id,)).fetchall()
    except Exception:  # noqa: BLE001 只读连接/表不存在
        return []
    out = []
    for row in rows:
        try:
            snap = json.loads(row["snapshot_json"])
        except Exception:  # noqa: BLE001
            snap = {}
        summary = (snap.get("name") or "")[:40]
        out.append({"version_no": row["version_no"], "content_hash": row["content_hash"],
                    "created_at": row["created_at"], "created_by": row["created_by"],
                    "summary": summary, "snapshot": snap})
    return out


def _insert_version(conn, workorder_id: str, snapshot: dict, *, created_by: str, now: str) -> int | None:
    """同内容不新增：与最新版本 content_hash 相同则跳过；返回新增的版本号或 None。"""
    digest = copy_hash(snapshot)
    last = conn.execute("""SELECT version_no, content_hash FROM workorder_copy_version
                           WHERE workorder_id=? ORDER BY version_no DESC LIMIT 1""",
                        (workorder_id,)).fetchone()
    if last and last["content_hash"] == digest:
        return None
    version_no = (last["version_no"] if last else 0) + 1
    conn.execute("""INSERT INTO workorder_copy_version (workorder_id, version_no, snapshot_json, content_hash,
                      created_at, created_by) VALUES (?,?,?,?,?,?)""",
                 (workorder_id, version_no, json.dumps(snapshot, ensure_ascii=False), digest, now, created_by))
    return version_no
def normalize_evidence(payload: dict) -> dict:
    """只接受证据字段；状态类字段必须显式给出值（没有“一键就绪”）。"""
    # selected_supply_id 在 B1 里是禁写字段，B3 起作为“证据”由本函数显式接受；
    # status 属于 B1 的规格编辑通道，证据通道不接受（避免“改状态即就绪”）。
    forbidden = [k for k in tuple(wf.FORBIDDEN_FIELDS) + ("status",)
                 if k != "selected_supply_id" and str(payload.get(k) or "").strip()]
    if forbidden:
        raise wf.Reject("forbidden_field", f"不允许提交：{', '.join(sorted(forbidden))}", 403)
    unknown = [k for k in payload if k not in EVIDENCE_FIELDS]
    if unknown:
        raise wf.Reject("unknown_field", f"未知字段：{', '.join(sorted(unknown))}")
    data: dict = {}
    for key in EVIDENCE_FIELDS:
        if key == "sample_note":
            continue        # 别名：写入 sample_ref 列，避免新增列
        if key in payload:
            raw = payload.get(key)
        elif key == "sample_ref" and "sample_note" in payload:
            raw = payload.get("sample_note")
        else:
            continue        # 未提交的字段不改动（保持原值）
        if key in ("cost_minor", "price_minor"):
            text = str(raw).strip()
            if text == "":
                data[key] = None
                continue
            if not text.isdigit():
                raise wf.Reject("field_invalid", f"{key} 必须是非负整数（分）")
            data[key] = int(text)
            continue
        text = str(raw).strip()
        if key in LICENSE_KEYS:
            low = text.lower()
            if low not in YES and low not in NO and low not in ("", "unknown", "不明"):
                raise wf.Reject("field_invalid", f"{key} 只能是 yes/no/unknown（收到 {text!r}）")
        if key == "sample_status" and text.lower() not in ("", "verified", "pending", "已核对", "未核对"):
            raise wf.Reject("field_invalid", "sample_status 只能是 verified/pending/未核对")
        if key == "copy_status" and text.lower() not in ("", "draft", "final", "草稿", "定稿"):
            raise wf.Reject("field_invalid", "copy_status 只能是 draft/final")
        if key == "faq_json" and text:
            try:
                json.loads(text)
            except json.JSONDecodeError:
                raise wf.Reject("field_invalid", "faq_json 必须是合法 JSON 数组")
        if len(text) > 2000:
            raise wf.Reject("field_too_long", f"{key} 超过 2000 字")
        data[key] = text
    return data


def save_evidence(conn, workorder_id: str, *, revision, payload: dict) -> dict:
    """保存证据字段：revision 乐观锁 + 同事务审计；不改变 status/gates。"""
    wf.init_schema(conn)
    record = wf.get(conn, workorder_id)
    if record is None:
        raise wf.Reject("not_found", "工作单不存在", 404)
    raw_rev = str(revision).strip() if revision is not None else ""
    if not raw_rev.isdigit():
        raise wf.Reject("revision_invalid", f"revision 必须是 ASCII 正整数（收到 {revision!r}）")
    rev = int(raw_rev)
    if rev != int(record["revision"]):
        raise wf.Reject("revision_conflict", f"版本冲突：当前 revision={record['revision']}，提交 {rev}", 409)
    data = normalize_evidence(payload)
    if not data:
        raise wf.Reject("field_required", "没有可保存的证据字段")
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    sets = ", ".join(f'"{k}"=?' for k in data)
    params = list(data.values()) + [now, workorder_id, rev]
    try:
        conn.execute("BEGIN IMMEDIATE")
        cur = conn.execute(f"UPDATE workorder SET {sets}, revision=revision+1, updated_at=? "
                           "WHERE workorder_id=? AND revision=?", params)
        if cur.rowcount != 1:
            conn.rollback()
            raise wf.Reject("revision_conflict", "版本冲突：UPDATE 命中 0 行，本次未写入", 409)
        conn.execute("INSERT INTO workorder_event (workorder_id, action, detail, at) VALUES (?,?,?,?)",
                     (workorder_id, "evidence", f"revision {rev} -> {rev + 1}：{', '.join(sorted(data))}", now))
        fresh = wf.get(conn, workorder_id)
        assert fresh is not None
        new_version = _insert_version(conn, workorder_id, copy_snapshot(fresh), created_by="ui", now=now)
        if new_version:
            conn.execute("INSERT INTO workorder_event (workorder_id, action, detail, at) VALUES (?,?,?,?)",
                         (workorder_id, "copy_version", f"v{new_version}（保存文案）", now))
        conn.commit()
    except wf.Reject:
        raise
    except Exception as exc:  # noqa: BLE001
        conn.rollback()
        raise wf.Reject("update_failed", f"保存失败已回滚：{type(exc).__name__}", 409)
    return wf.get(conn, workorder_id)


# ---------------------------------------------------------------- 导出记录
def record_export(conn, record: dict, payload: dict, fmt: str) -> dict:
    """导出记录：同 (revision, copy_version, supply_id, supply_version) 幂等，不新增行。"""
    wf.init_schema(conn)
    stamp = payload["version_stamp"]
    content_sha = hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
    dedupe_key = f'{stamp["revision"]}|{stamp["copy_version"]}|{stamp["supply_id"]}|{stamp["supply_version"]}'
    existing = conn.execute("SELECT * FROM workorder_export WHERE workorder_id=? AND dedupe_key=? "
                            "ORDER BY id DESC LIMIT 1", (stamp["workorder_id"], dedupe_key)).fetchone()
    if existing:
        return {"stamp": stamp, "content_sha256": existing["content_sha256"], "deduplicated": True,
                "export_id": existing["id"], "created_utc": existing["created_utc"]}
    try:
        cur = conn.execute("""INSERT INTO workorder_export (workorder_id, format, revision, copy_version, supply_id,
                                supply_version, stamp_hash, content_sha256, created_utc, dedupe_key, publish_version)
                              VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                           (stamp["workorder_id"], fmt, stamp["revision"], stamp["copy_version"],
                            stamp["supply_id"], stamp["supply_version"], stamp["stamp_hash"], content_sha,
                            stamp["generated_utc"], dedupe_key,
                            int((publish_info(conn, stamp["workorder_id"]) or {}).get("publish_version") or 0)))
        conn.commit()
    except Exception as exc:  # noqa: BLE001 唯一索引冲突（并发同戳）→ 回查既有行
        if "UNIQUE" not in str(exc).upper() and "IntegrityError" not in type(exc).__name__:
            conn.rollback()
            raise
        conn.rollback()
        row = conn.execute("SELECT * FROM workorder_export WHERE workorder_id=? AND dedupe_key=? "
                           "ORDER BY id DESC LIMIT 1", (stamp["workorder_id"], dedupe_key)).fetchone()
        if row is None:
            raise
        return {"stamp": stamp, "content_sha256": row["content_sha256"], "deduplicated": True,
                "export_id": row["id"], "created_utc": row["created_utc"]}
    return {"stamp": stamp, "content_sha256": content_sha, "deduplicated": False,
            "export_id": cur.lastrowid, "created_utc": stamp["generated_utc"]}


def rollback_copy(conn, workorder_id: str, *, version_no, revision) -> dict:
    """回滚到某版本：内容取旧快照，**生成新版本**（历史不删除）。"""
    wf.init_schema(conn)
    record = wf.get(conn, workorder_id)
    if record is None:
        raise wf.Reject("not_found", "工作单不存在", 404)
    raw_rev = str(revision).strip() if revision is not None else ""
    if not raw_rev.isdigit():
        raise wf.Reject("revision_invalid", f"revision 必须是 ASCII 正整数（收到 {revision!r}）")
    rev = int(raw_rev)
    if rev != int(record["revision"]):
        raise wf.Reject("revision_conflict", f"版本冲突：当前 revision={record['revision']}，提交 {rev}", 409)
    try:
        target = int(str(version_no).strip())
    except (TypeError, ValueError):
        raise wf.Reject("version_invalid", "目标版本号必须是整数")
    row = conn.execute("""SELECT snapshot_json FROM workorder_copy_version
                          WHERE workorder_id=? AND version_no=?""", (workorder_id, target)).fetchone()
    if not row:
        raise wf.Reject("version_not_found", f"版本 v{target} 不存在", 404)
    snap = json.loads(row["snapshot_json"])
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    sets = ", ".join(f'"{k}"=?' for k in COPY_FIELDS)
    params = [snap.get(k) for k in COPY_FIELDS] + [now, workorder_id, rev]
    try:
        conn.execute("BEGIN IMMEDIATE")
        cur = conn.execute(f"UPDATE workorder SET {sets}, revision=revision+1, updated_at=? "
                           "WHERE workorder_id=? AND revision=?", params)
        if cur.rowcount != 1:
            conn.rollback()
            raise wf.Reject("revision_conflict", "版本冲突：UPDATE 命中 0 行，本次未写入", 409)
        fresh = wf.get(conn, workorder_id)
        assert fresh is not None
        new_version = _insert_version(conn, workorder_id, copy_snapshot(fresh),
                                      created_by=f"rollback:v{target}", now=now)
        conn.execute("INSERT INTO workorder_event (workorder_id, action, detail, at) VALUES (?,?,?,?)",
                     (workorder_id, "copy_rollback", f"回滚到 v{target} → 新版本 v{new_version or '(同内容)'}", now))
        conn.commit()
    except wf.Reject:
        raise
    except Exception as exc:  # noqa: BLE001
        conn.rollback()
        raise wf.Reject("update_failed", f"回滚失败已回滚：{type(exc).__name__}", 409)
    return wf.get(conn, workorder_id)


# ---------------------------------------------------------------- 发布回填
PUBLISH_STATUS = ("未发布", "已发布", "已下架")


def publish_info(conn, workorder_id: str) -> dict | None:
    try:
        row = conn.execute("SELECT * FROM workorder_publish WHERE workorder_id=?", (workorder_id,)).fetchone()
    except Exception:  # noqa: BLE001
        return None
    return dict(row) if row else None


def save_publish(conn, workorder_id: str, payload: dict) -> dict:
    """发布回填：状态枚举、URL 仅 http/https、sold_count 非负整数、备注长度限制。"""
    wf.init_schema(conn)
    record = wf.get(conn, workorder_id)
    if record is None:
        raise wf.Reject("not_found", "工作单不存在", 404)
    status = str(payload.get("status") or "").strip()
    if status not in PUBLISH_STATUS:
        raise wf.Reject("publish_status_invalid", f"状态只能是 {'/'.join(PUBLISH_STATUS)}", 400)
    url = str(payload.get("published_url") or "").strip()
    if url:
        from urllib.parse import urlparse
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            raise wf.Reject("publish_url_invalid", "发布链接必须是 http/https 且含域名", 400)
        if len(url) > 500:
            raise wf.Reject("publish_url_invalid", "发布链接过长（>500）", 400)
    sold_raw = str(payload.get("sold_count") or "0").strip() or "0"
    if not sold_raw.isdigit():
        raise wf.Reject("publish_sold_invalid", "sold_count 必须是非负整数", 400)
    note = str(payload.get("platform_note") or "").strip()
    if len(note) > 500:
        raise wf.Reject("publish_note_invalid", "备注超过 500 字", 400)
    published_at = str(payload.get("published_at") or "").strip()[:32]
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    conn.execute("""INSERT INTO workorder_publish (workorder_id, status, published_url, published_at,
                      platform_note, sold_count, publish_version, updated_at) VALUES (?,?,?,?,?,?,1,?)
                    ON CONFLICT(workorder_id) DO UPDATE SET status=excluded.status,
                      published_url=excluded.published_url, published_at=excluded.published_at,
                      platform_note=excluded.platform_note, sold_count=excluded.sold_count,
                      publish_version=workorder_publish.publish_version + 1,
                      updated_at=excluded.updated_at""",
                 (workorder_id, status, url or None, published_at or None, note or None, int(sold_raw), now))
    conn.execute("INSERT INTO workorder_event (workorder_id, action, detail, at) VALUES (?,?,?,?)",
                 (workorder_id, "publish", f"status={status} url={url[:60]} sold={sold_raw}", now))
    conn.commit()
    return publish_info(conn, workorder_id) or {}


def publish_changed(publish: dict | None, last_export: dict | None) -> dict:
    """发布信息是否在最近一次导出之后变更（用 publish_version 与导出记录里的快照版本比较）。"""
    if not publish:
        return {"changed": False, "reason": ""}
    current = int(publish.get("publish_version") or 0)
    if not last_export:
        return {"changed": False, "reason": ""}
    exported = int(last_export.get("publish_version") or 0)
    if current > exported:
        return {"changed": True, "reason": "发布信息已变更，建议重核就绪并重新导出"}
    return {"changed": False, "reason": ""}


def last_export(conn, workorder_id: str) -> dict | None:
    """只读查询上次导出；表不存在时返回 None，不建表（GET 零写）。"""
    try:
        row = conn.execute("SELECT * FROM workorder_export WHERE workorder_id=? ORDER BY id DESC LIMIT 1",
                           (workorder_id,)).fetchone()
    except Exception:  # noqa: BLE001  （表不存在/只读连接）
        return None
    return dict(row) if row else None


def export_validity(record: dict, last: dict | None) -> dict:
    """旧导出是否失效：比较 revision / copy_version / supply_id / supply_version。"""
    if not last:
        return {"has_export": False, "valid": False, "reason": "尚未导出"}
    current = version_stamp(record)
    changed = [label for key, label in (("revision", "工作单版本"), ("copy_version", "文案版本"),
                                        ("supply_id", "货源"), ("supply_version", "货源版本"))
               if str(current[key]) != str(last.get(key))]
    return {"has_export": True, "valid": not changed, "changed": changed,
            "reason": "无变化" if not changed else "已失效，需重新检查并导出：" + "、".join(changed),
            "created_utc": last.get("created_utc"), "format": last.get("format"),
            "content_sha256": last.get("content_sha256")}
