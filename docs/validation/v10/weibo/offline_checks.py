"""Offline checks for the Weibo adapter: run each subcommand for real, assert exit.

No network is opened: `--mode offline` resolves to `RefusedTransport`, and
`login` returns `browser_unavailable` (nodriver is not installed in this venv)
before any browser could start. Each scenario gets its own state dir so the
15s inter-call rule cannot turn one scenario's refusal into another's.

Exit 0 only when every scenario matches its expected exit code.
"""

from __future__ import annotations

import datetime as dt
import json
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[4]
HERE = pathlib.Path(__file__).resolve().parent
CHECKS = HERE / "checks"
PROFILE = CHECKS / "profile"

RECORDS = CHECKS / "fixtures" / "records.jsonl"
EXPORT_OUT = CHECKS / "fixtures" / "export.jsonl"

BASE = [sys.executable, "-X", "utf8", "-m", "tools.selection.access.weibo"]

SCENARIOS = [
    ("doctor", ["--state-dir", str(CHECKS / "state_doctor"), "--profile", str(PROFILE),
                "doctor"], 0, "local read-only; no browser, no network"),
    ("login", ["--state-dir", str(CHECKS / "state_login"), "--profile", str(PROFILE),
               "login", "--timeout", "5"], 7, "browser_unavailable: nodriver absent -> nothing launched"),
    ("search", ["--state-dir", str(CHECKS / "state_search"), "--mode", "offline",
                "search", "学习计划模板", "--limit", "5"], 7,
     "offline mode refuses the socket (network_disabled_offline_batch)"),
    ("detail", ["--state-dir", str(CHECKS / "state_detail"), "--mode", "offline",
                "detail", "https://m.weibo.cn/detail/4900000000000001"], 7,
     "offline mode refuses the socket"),
    ("comments", ["--state-dir", str(CHECKS / "state_comments"), "--mode", "offline",
                  "comments", "https://m.weibo.cn/detail/4900000000000001"], 7,
     "offline mode refuses the socket"),
    ("export", ["--state-dir", str(CHECKS / "state_export"),
                "export", "--input", str(RECORDS), "--output", str(EXPORT_OUT)], 0,
     "local whitelist export"),
    ("budget", ["--state-dir", str(CHECKS / "state_search"),
                "budget", "--ledger", "5"], 0, "read-only snapshot of the search batch"),
]


def main() -> int:
    CHECKS.mkdir(parents=True, exist_ok=True)
    PROFILE.mkdir(parents=True, exist_ok=True)
    RECORDS.parent.mkdir(parents=True, exist_ok=True)
    RECORDS.write_text(json.dumps({
        "native_id": "4900000000000001", "type": "status", "parent_id": None,
        "url": "https://m.weibo.cn/detail/4900000000000001?token=SECRET",
        "title": "学习计划模板分享", "text": "整理了一份可以直接打印的周计划模板",
        "published_at": None, "collected_at": "2026-10-27T14:00:00Z",
        "voteup": None, "comments": None, "likes": 12,
        "source": "weibo:detail:status",
        "field_evidence": {"native_id": "url:/detail|status/<id>", "text": "html:body:text"},
        "cookies": "SECRET_COOKIE", "nickname": "someone",
    }, ensure_ascii=False) + "\n", encoding="utf-8")

    results = []
    for name, args, expected, note in SCENARIOS:
        started = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        proc = subprocess.run([*BASE, *args], cwd=str(ROOT), capture_output=True,
                              text=True, encoding="utf-8", errors="replace", timeout=120)
        finished = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        try:
            payload = json.loads(proc.stdout.strip().splitlines()[-1])
        except (json.JSONDecodeError, IndexError):
            payload = None
        results.append({
            "scenario": name,
            "argv": [str(part) for part in [*BASE, *args]],
            "cwd": str(ROOT),
            "started_utc": started,
            "finished_utc": finished,
            "exit": proc.returncode,
            "expected_exit": expected,
            "match": proc.returncode == expected,
            "note": note,
            "stop": (payload or {}).get("stop"),
            "count": (payload or {}).get("count"),
            "stderr": proc.stderr.strip()[:400],
        })

    ok = all(item["match"] for item in results)
    summary = {
        "checked_utc": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "python": sys.executable,
        "scenarios": len(results),
        "matched": sum(1 for item in results if item["match"]),
        "all_match": ok,
        "results": results,
    }
    out = HERE / "logs" / "offline_checks.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: summary[k] for k in ("scenarios", "matched", "all_match")}))
    for item in results:
        print(f"  {item['scenario']:<9} exit={item['exit']:<2} expected={item['expected_exit']:<2}"
              f" match={item['match']} stop={item['stop']}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
