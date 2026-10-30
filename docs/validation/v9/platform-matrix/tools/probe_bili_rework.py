"""Bilibili-only rework: sort=2 p1/p2 + one subreply probe.

Uses the same sanitized fetch/logging implementation as probe_platforms.py.
No Weibo requests; no login/cookies; consumes at most 3 of the remaining budget.
"""

from __future__ import annotations

import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import probe_platforms as pp  # noqa: E402

OID = pp.BILI_OID


def main() -> int:
    p = pp.Prober()
    p.counts["bilibili"] = 4  # 1 failed view + 3 successful requests already used
    p.counts["weibo"] = 1     # already used; this script never calls Weibo
    first = p.fetch(
        "bilibili", "bili_sort2_p1",
        f"https://api.bilibili.com/x/v2/reply?type=1&oid={OID}&pn=1&ps=5&sort=2",
        accept="application/json",
    )
    if p.stopped["bilibili"] or "skipped" in first:
        print(json.dumps({"stopped": p.stopped["bilibili"], "stage": "sort2_p1"}, ensure_ascii=False))
        return 2
    data = first.get("parsed") or {}
    page1 = ((data.get("data") or {}).get("page") or {}) if isinstance(data, dict) else {}
    replies = ((data.get("data") or {}).get("replies") or []) if isinstance(data, dict) else []
    root = replies[0].get("rpid") if replies and isinstance(replies[0], dict) else None
    print(json.dumps({"stage": "sort2_p1", "page": page1, "replies": len(replies), "root": root},
                     ensure_ascii=False), flush=True)

    if not replies:
        print(json.dumps({"stopped": "no root rpid; subreply not attempted"}, ensure_ascii=False))
        return 2

    second = p.fetch(
        "bilibili", "bili_sort2_p2",
        f"https://api.bilibili.com/x/v2/reply?type=1&oid={OID}&pn=2&ps=5&sort=2",
        accept="application/json",
    )
    if p.stopped["bilibili"] or "skipped" in second:
        print(json.dumps({"stopped": p.stopped["bilibili"], "stage": "sort2_p2"}, ensure_ascii=False))
        return 2
    data2 = second.get("parsed") or {}
    ids1 = {str(r.get("rpid")) for r in replies if isinstance(r, dict) and r.get("rpid")}
    replies2 = ((data2.get("data") or {}).get("replies") or []) if isinstance(data2, dict) else []
    ids2 = {str(r.get("rpid")) for r in replies2 if isinstance(r, dict) and r.get("rpid")}
    page2 = ((data2.get("data") or {}).get("page") or {}) if isinstance(data2, dict) else {}
    print(json.dumps({"stage": "sort2_p2", "page": page2, "replies": len(replies2),
                      "overlap": sorted(ids1 & ids2)}, ensure_ascii=False), flush=True)

    third = p.fetch(
        "bilibili", f"bili_subreply_{root}",
        f"https://api.bilibili.com/x/v2/reply/reply?type=1&oid={OID}&root={root}&pn=1&ps=2",
        accept="application/json",
    )
    (pp.BASE / "raw" / "bili_rework_result.json").write_bytes(
        json.dumps({"generated_utc": pp.utc(), "requests": p.requests,
                    "counts": p.counts, "stopped": p.stopped,
                    "page1": page1, "replies_p1": len(replies), "root": root,
                    "page2": page2, "replies_p2": len(replies2),
                    "overlap": sorted(ids1 & ids2)},
                   ensure_ascii=False, indent=2).encode("utf-8"))
    print(json.dumps({"done": True, "counts": p.counts, "stopped": p.stopped}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
