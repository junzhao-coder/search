"""Xianyu JSONL/CSV → imported signals (read-only source, independent DB)."""

from __future__ import annotations

import csv
import json
import pathlib
import re
import urllib.parse

from . import db, models, triage


def native_id_from_href(href: str) -> str | None:
    try:
        query = urllib.parse.parse_qs(urllib.parse.urlsplit(href).query)
        value = (query.get("id") or [None])[0]
        if value and str(value).isdigit():
            return str(value)
    except Exception:
        pass
    match = re.search(r"[?&]id=(\d+)", href or "")
    return match.group(1) if match else None


def _prices(raw: str) -> list[int]:
    out = []
    for whole, frac in re.findall(r"[\u00a5\uffe5]\s*(\d+)(?:\s*\.\s*(\d{1,2}))?", raw or ""):
        out.append(int(whole) * 100 + int((frac or "00").ljust(2, "0")))
    return out


def _wants(raw: str) -> int | None:
    match = re.search(r"(\d+)\s*人想要", raw or "")
    return int(match.group(1)) if match else None


def _row_to_signal(row: dict, *, collected_at: str, batch_id: str, raw_sha256: str,
                   raw_ref: str) -> dict:
    href = str(row.get("href") or "").strip()
    platform = str(row.get("platform") or "").strip()
    if platform != "xianyu":
        raise ValueError("platform_must_be_xianyu")
    native_id = native_id_from_href(href)
    if not native_id:
        raise ValueError("native_id_unparseable")
    title = str(row.get("title") or "").strip()
    quote = str(row.get("raw_text") or "").strip()
    if not quote:
        raise ValueError("raw_text_missing")
    listed = models.minor_from_yuan(row.get("price") or "")
    prices = _prices(quote)
    effective = prices[0] if prices else listed
    reference = prices[1] if len(prices) > 1 else None
    lang, lang_source = models.lang_of(quote)
    signal = {
        "platform": "xianyu", "native_id": native_id, "parent_native_id": None,
        "url": href, "title": title or None, "quote": quote, "lang": lang,
        "lang_source": lang_source, "listed_price_minor": listed,
        "effective_price_minor": effective, "reference_price_minor": reference,
        "wants": _wants(quote), "collected_at": collected_at,
        "collected_at_scope": "batch", "origin_kind": "imported",
        "raw_sha256": raw_sha256, "raw_ref": raw_ref, "batch_id": batch_id,
    }
    signal["content_hash"] = models.content_hash(
        platform=signal["platform"], native_id=signal["native_id"], quote=quote,
        listed_price_minor=listed, effective_price_minor=effective, wants=signal["wants"])
    return signal


def _read_rows(path: pathlib.Path):
    """Yield (line_no, raw_bytes, row_or_exception); parse errors do not abort iteration."""
    suffix = path.suffix.lower()
    if suffix == ".jsonl":
        for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip():
                continue
            raw = line.encode("utf-8")
            try:
                yield line_no, raw, json.loads(line)
            except Exception as exc:  # noqa: BLE001 - bad row is data, not a batch failure
                yield line_no, raw, exc
    elif suffix == ".csv":
        text = path.read_text(encoding="utf-8-sig")
        for line_no, row in enumerate(csv.DictReader(text.splitlines()), 2):
            yield line_no, json.dumps(row, ensure_ascii=False).encode("utf-8"), row
    else:
        raise ValueError("unsupported_format")


def import_file(path: str | pathlib.Path, *, db_path: str | pathlib.Path,
                collected_at: str | None = None, batch_id: str | None = None,
                max_rows: int = 5000, max_errors: int = 100) -> dict:
    source = pathlib.Path(path)
    if not source.exists():
        raise FileNotFoundError(source)
    conn = db.init_db(db_path)
    run_id, batch = db.start_run(
        conn, kind="xianyu_import", platform="xianyu",
        budget={"max_rows": max_rows, "max_errors": max_errors},
        raw_dir=None)
    if batch_id:
        # caller-provided label is used for signal batch_id, while runs keeps its own audit id
        batch = batch_id
    collected = collected_at or models.utc_now()
    stats = {"rows": 0, "ok_rows": 0, "bad_rows": 0, "new": 0, "updated": 0, "duplicate": 0,
             "errors": [], "wants_missing": 0, "wants_sum": 0, "reference_present": 0,
             "batch_id": batch, "origin_kind": "imported", "stop_reason": None}
    stopped = False
    try:
        for line_no, raw_bytes, row in _read_rows(source):
            if stats["rows"] >= max_rows:
                stats["stop_reason"] = "rows_exceeded"
                stopped = True
                break
            stats["rows"] += 1
            if isinstance(row, Exception):
                stats["bad_rows"] += 1
                stats["errors"].append({"line": line_no, "reason": str(row)})
                if len(stats["errors"]) >= max_errors:
                    stats["stop_reason"] = "errors_exceeded"
                    stopped = True
                    break
                continue
            try:
                if not isinstance(row, dict):
                    raise ValueError("row_not_object")
                signal = _row_to_signal(
                    row, collected_at=collected, batch_id=batch,
                    raw_sha256=models.sha256_bytes(raw_bytes),
                    raw_ref=f"{source}#L{line_no}")
                outcome, sid = db.upsert_signal(conn, signal)
                stats[outcome] += 1
                stats["ok_rows"] += 1
                triage.store(conn, int(sid), (signal.get("title") or "") + " " + (signal.get("quote") or ""))
                if signal["wants"] is None:
                    stats["wants_missing"] += 1
                else:
                    stats["wants_sum"] += signal["wants"]
                if signal["reference_price_minor"] is not None:
                    stats["reference_present"] += 1
            except Exception as exc:  # noqa: BLE001 - bad rows are reported, not fatal
                stats["bad_rows"] += 1
                stats["errors"].append({"line": line_no, "reason": str(exc)})
                if len(stats["errors"]) >= max_errors:
                    stats["stop_reason"] = "errors_exceeded"
                    stopped = True
                    break
        status = "stopped" if stopped else ("complete" if not stats["errors"] else "partial")
        db.finish_run(conn, run_id, status=status, stop_reason=stats["stop_reason"], stats=stats)
        return {**stats, "run_id": run_id, "status": status, "db": str(db_path)}
    except Exception as exc:
        db.finish_run(conn, run_id, status="failed", stop_reason=str(exc), stats=stats)
        raise
    finally:
        conn.close()
