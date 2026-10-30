"""Ingest V2EX/GitHub read-only signals into an isolated selection DB, then categorize/cards."""

from __future__ import annotations

import pathlib

from . import categories, db, github, models, triage, v2ex


def ingest(signals: list[dict], db_path) -> dict:
    conn = db.init_db(db_path)
    stats = {"new": 0, "updated": 0, "duplicate": 0, "errors": []}
    try:
        for sig in signals:
            try:
                outcome, sid = db.upsert_signal(conn, sig)
                stats[outcome] += 1
                triage.store(conn, int(sid), (sig.get("title") or "") + " " + (sig.get("quote") or ""))
            except Exception as exc:  # noqa: BLE001
                stats["errors"].append({"native_id": sig.get("native_id"), "reason": str(exc)})
        cat = categories.run_categorize(conn)
        cards = categories.make_cards(conn)
        return {**stats, "categorize": cat, "cards": cards, "db": str(db_path)}
    finally:
        conn.close()
