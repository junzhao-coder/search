"""Persistent idempotency (contract §0.7/§1.15/I15): one helper reused by every write endpoint.

Same ``(scope, client_ref)`` + same payload hash -> replay the stored response with
``deduplicated: true``; different payload -> 409. The record is written in the same
transaction as the business write, so a rollback removes it too.
"""

from __future__ import annotations

import hashlib
import json

from .errors import AppError
from .util import now_utc, slug_id


def payload_hash(scope: str, payload: dict) -> str:
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(f"{scope}\n{canonical}".encode("utf-8")).hexdigest()


def replay(conn, scope: str, client_ref: str | None, payload: dict):
    """Return (stored_response, True) when this exact request already ran, else (None, False)."""
    if not client_ref:
        return None, False
    row = conn.execute(
        "SELECT request_hash, response_json FROM idempotency_key WHERE scope=? AND client_ref=?",
        (scope, client_ref),
    ).fetchone()
    if row is None:
        return None, False
    if row["request_hash"] != payload_hash(scope, payload):
        raise AppError("client_ref 已用于不同的请求载荷", code="conflict", status=409)
    return json.loads(row["response_json"]), True


def remember(conn, scope: str, client_ref: str | None, payload: dict, response: dict, record_id: str | None) -> None:
    if not client_ref:
        return
    conn.execute(
        "INSERT INTO idempotency_key(id,scope,client_ref,request_hash,response_json,record_id,created_at)"
        " VALUES (?,?,?,?,?,?,?)",
        (slug_id("ik"), scope, client_ref, payload_hash(scope, payload),
         json.dumps(response, ensure_ascii=False), record_id, now_utc()),
    )


def client_ref_of(args, headers) -> str | None:
    ref = args.get("client_ref") or headers.get("X-Client-Ref") or None
    if ref and len(ref) > 64:
        raise AppError("client_ref 最长 64 字符", code="validation_failed")
    return ref
