"""Offline S3 wiring: one accepted reader record → the existing import pipeline.

Design: ``docs/design/S3_WIRING_SPEC.md`` (§2 call chain, §3 whitelist mapping, §4 failure audit).
Scope: no HTTP client, no network, no endpoint, no timer; the transport is injected by the caller
(the accepted ``BilibiliViewReader``). All validation/dedup/version/transaction work stays in
``app/core/importer.py`` — nothing is re-implemented here.
"""

from __future__ import annotations

import json
import sqlite3

from ..core import importer
from ..core.errors import AppError
from ..core.util import now_utc, slug_id, today_local

SOURCE_NAME = "bilibili"
SOURCE_ID = "s_bili"                       # registered seed row in 0001_init.sql
EXAMPLE_URL = "https://example.org/bilibili/video/{bvid}"
TITLE_MAX = 300
SYNTHETIC_ORIGINS = {"synthetic"}
# Keys the accepted adapter may return and that this module either maps or deliberately consumes
# (mapped: title/excerpt/bvid/published_at/original_author/engagement_json/signal_kind/observed_at*;
#  surfaced in warnings: unknown_fields/observed_at_rejected; audit-only: outcome/failure_reason/
#  http_status/app_code/request_url; recomputed by the importer: content_hash/identity_key/
#  identity_source/url/url_norm; constants: source_name/native_id). Anything outside this set is a
#  foreign key (e.g. supply_*/cost/gate_*) and is dropped with a warning.
_RECORD_KEYS = {
    "bvid", "native_id", "source_name", "title", "excerpt", "signal_kind", "published_at",
    "original_author", "engagement_json", "content_hash", "outcome", "failure_reason",
    "observed_at", "observed_at_source", "observed_at_rejected", "unknown_fields",
    "http_status", "app_code", "request_url", "identity_key", "identity_source", "url", "url_norm",
}
_META_WARNING = "S3_UNKNOWN_FIELDS"
_OBSERVED_WARNING = "S3_OBSERVED_AT_REJECTED"


class WiringReject(Exception):
    """Contract-level refusal of one record (never written; reported through the failure run)."""

    def __init__(self, code: str, reason: str):
        super().__init__(f"{code}: {reason}")
        self.code = code
        self.reason = reason


def _refuse(code: str, reason: str):
    raise WiringReject(code, reason)


def build_row(record: dict, *, data_origin: str = "synthetic") -> tuple[dict, list[tuple[str, str]]]:
    """Map one reader record to a whitelisted import row plus same-row warnings.

    Returns ``(row, warnings)``; raises :class:`WiringReject` for contract refusals. Only base +
    demand columns are produced — any supply/cost/gate key on the record is dropped with a warning.
    """
    if data_origin not in SYNTHETIC_ORIGINS:
        _refuse("origin_not_allowed", "本批只允许 synthetic 入口（真实网络与 real 写入需另批授权）")
    warnings: list[tuple[str, str]] = []
    if record.get("outcome") != "ok":
        _refuse("not_ok_record", f"读取未成功：{record.get('outcome')}")
    strays = sorted(set(record) - _RECORD_KEYS)
    if strays:
        warnings.append((_META_WARNING, "记录含非需求字段，已丢弃：" + ",".join(strays)))
    bvid = record.get("bvid")
    if not isinstance(bvid, str) or not bvid or bvid != record.get("native_id"):
        _refuse("invalid_bvid", "缺少可用 bvid/native_id")
    title = record.get("title")
    if not isinstance(title, str) or not title.strip():
        _refuse("missing_title", "缺少标题")
    title = title.strip()
    if len(title) > TITLE_MAX:
        _refuse("title_too_long", f"标题长度 {len(title)} 超过 {TITLE_MAX}（拒绝，不截断）")
    excerpt = record.get("excerpt")
    if not isinstance(excerpt, str) or not excerpt.strip():
        _refuse("missing_excerpt", "缺少摘录")
    excerpt = excerpt.strip()
    fingerprint = importer.content_hash(excerpt, title)
    if record.get("content_hash") and record["content_hash"] != fingerprint:
        _refuse("hash_mismatch", "重算 content_hash 与适配器不一致")
    row = {
        "title": title,
        "data_origin": data_origin,
        "demand_source": SOURCE_NAME,
        "demand_native_id": bvid,
        "demand_url": EXAMPLE_URL.format(bvid=bvid),          # 示例域存储 URL（原 bili URL 只作来源文本）
        "demand_excerpt": excerpt,
        "demand_kind": record.get("signal_kind") or "other",
    }
    if record.get("observed_at_source") == "source":
        row["observed_at"] = record.get("observed_at")        # 合法源时间走公共列；回退时间走内部 hint
    if record.get("published_at"):
        row["demand_published_at"] = record["published_at"]
    if record.get("original_author"):
        row["demand_original_author"] = record["original_author"]
    if record.get("engagement_json"):
        row["demand_engagement"] = record["engagement_json"]
    for field in record.get("unknown_fields") or []:
        warnings.append((_META_WARNING, str(field)))
    if record.get("observed_at_rejected"):
        warnings.append((_OBSERVED_WARNING, f"观察时间原值被拒：{record['observed_at_rejected']}"))
    return row, warnings


def record_failure(conn, cfg: dict, record: dict, *, reason: str, status: str = "failed",
                   source_id: str | None = SOURCE_ID) -> dict:
    """Write one audit ``run_record`` for a failed completion (its own transaction, no business row).

    The three count columns are omitted on purpose: the schema default is 0 and the note states that
    this technical zero is not an observed "no demand" result. A failure to write this audit row
    propagates — it is never swallowed and never recursed into.
    """
    run_id = slug_id("r")
    stamp = now_utc()
    bvid = record.get("bvid") or "-"
    note = ("s3:completion failure; 未成功取得可计数结果；"
            "items_found/items_new/items_dup=0 为失败运行的技术默认值，不代表已观测的零需求")
    conn.execute("BEGIN")
    try:
        conn.execute(
            "INSERT INTO run_record(id,run_type,trigger,logical_date,source_id,status,started_at,finished_at,"
            "error_summary,notes) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (run_id, "import", "manual", today_local(cfg["tz_offset_hours"]), source_id, status,
             stamp, stamp, reason, f"{note}; bvid={bvid}"),
        )
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
    return {"ok": False, "status": status, "run_id": run_id, "reason": reason}


def complete_known_object(conn, cfg: dict, *, reader, target, observed_at: str | None = None,
                          data_origin: str = "synthetic") -> dict:
    """Complete one known object offline and land it through the existing import pipeline.

    The caller must not be inside a transaction: ``handle_import`` owns its transaction.
    """
    record = reader.complete(target, observed_at=observed_at)
    if record.get("outcome") != "ok":
        return record_failure(conn, cfg, record,
                              reason=f"{record.get('outcome')}: {record.get('failure_reason')}")
    try:
        row, warnings = build_row(record, data_origin=data_origin)
    except WiringReject as refusal:
        return record_failure(conn, cfg, record, reason=f"{refusal.code}: {refusal.reason}")
    hint = {
        "observed_at": record.get("observed_at"),
        "observed_at_source": record.get("observed_at_source"),
        "warnings": warnings,
    }
    body = json.dumps([row], ensure_ascii=False).encode("utf-8")
    try:
        payload, http_status, deduplicated = importer.handle_import(
            conn, cfg, fmt="json", body=body, filename=f"s3:{SOURCE_NAME}:{record['bvid']}.json",
            mode="atomic", format_version=1, client_ref=None, run_source_id=SOURCE_ID,
            internal_observation=hint,
        )
    except (sqlite3.Error, AppError) as exc:
        return record_failure(conn, cfg, record, reason=f"{type(exc).__name__}: {exc}")
    if http_status == 422:                      # atomic 致命路径：批次/行结果保留，但无 run_record
        return record_failure(conn, cfg, record,
                              reason=f"validation_failed: {json.dumps(payload.get('counts'), ensure_ascii=False)}")
    return {"ok": True, "http_status": http_status, "deduplicated": deduplicated,
            "batch_id": payload.get("batch_id"), "counts": payload.get("counts"), "row": row}
