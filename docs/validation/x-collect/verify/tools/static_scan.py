"""Static read-only/credential checks for x-collect (no values from cookies)."""

from __future__ import annotations

import json
import pathlib
import re
import sqlite3
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:  # pragma: no cover
    pass

SCRIPT = pathlib.Path(r"C:\Users\19183\.dsh\tools\x-collect\scripts\x_collect.py")
TOOL_LOGS = pathlib.Path(r"C:\Users\19183\.dsh\tools\x-collect\logs")
COOKIES = pathlib.Path(r"C:\Users\19183\.dsh\tools\x-collect\profile\Default\Network\Cookies")
ACTION_PATTERNS = {
    "click": r"\.click\s*\(",
    "type": r"\.type\s*\(",
    "send_keys": r"send_keys\s*\(",
    "keyboard": r"(keyboard|dispatch_key|Input\.dispatch)",
    "mouse": r"(\.mouse|mouse_)",
    "like_call": r"\blike\s*\(",
    "retweet_call": r"\bretweet\s*\(",
    "follow_call": r"\bfollow\s*\(",
    "post_call": r"\bpost\s*\(",
    "dm_call": r"\bdm\s*\(",
}
CRED_PATTERNS = {
    "auth_token_value": r"auth_token\s*[:=]\s*(?!True|False|null|\"\"|'')[A-Za-z0-9%._-]{8,}",
    "ct0_value": r"\bct0\s*[:=]\s*(?!True|False|null|\"\"|'')[A-Za-z0-9%._-]{8,}",
    "cookie_header": r"(?i)cookie:\s*\S+",
    "bearer": r"(?i)bearer\s+[A-Za-z0-9._-]{12,}",
}


def cookie_meta() -> dict:
    info = {"path": str(COOKIES), "exists": COOKIES.exists(), "x_rows": 0, "names": [],
            "auth_token_name_present": False, "ct0_name_present": False}
    if not COOKIES.is_file():
        return info
    conn = sqlite3.connect(f"file:{COOKIES.as_posix()}?mode=ro&immutable=1", uri=True, timeout=5.0)
    try:
        rows = conn.execute(
            "SELECT name FROM cookies WHERE host_key LIKE '%x.com%' ORDER BY name").fetchall()
        names = sorted({str(row[0]) for row in rows})
        info["x_rows"] = len(rows)
        info["names"] = names
        info["auth_token_name_present"] = "auth_token" in names
        info["ct0_name_present"] = "ct0" in names
    finally:
        conn.close()
    return info


def main() -> int:
    out = pathlib.Path(sys.argv[sys.argv.index("--out") + 1])
    text = SCRIPT.read_text(encoding="utf-8")
    action_hits = []
    for name, pattern in ACTION_PATTERNS.items():
        for match in re.finditer(pattern, text, flags=re.IGNORECASE):
            line_no = text[:match.start()].count("\n") + 1
            line = text.splitlines()[line_no - 1].strip()
            action_hits.append({"pattern": name, "line": line_no, "text": line[:240]})
    log_hits = []
    log_files = list(sorted(TOOL_LOGS.glob("*.log")))
    if "--verify-logs" in sys.argv:
        verify_logs = pathlib.Path(sys.argv[sys.argv.index("--verify-logs") + 1])
        log_files += list(sorted(verify_logs.glob("*.log")))
    for log in log_files:
        log_text = log.read_text(encoding="utf-8", errors="replace")
        for name, pattern in CRED_PATTERNS.items():
            for match in re.finditer(pattern, log_text, flags=re.IGNORECASE):
                line_no = log_text[:match.start()].count("\n") + 1
                line = log_text.splitlines()[line_no - 1].strip()
                log_hits.append({"file": str(log), "pattern": name, "line": line_no, "text": line[:240]})
    script_hits = []
    for name, pattern in CRED_PATTERNS.items():
        for match in re.finditer(pattern, text, flags=re.IGNORECASE):
            line_no = text[:match.start()].count("\n") + 1
            line = text.splitlines()[line_no - 1].strip()
            script_hits.append({"pattern": name, "line": line_no, "text": line[:240]})
    payload = {
        "script": str(SCRIPT),
        "action_hits": action_hits,
        "action_hits_count": len(action_hits),
        "log_credential_hits": log_hits,
        "script_credential_hits": script_hits,
        "cookie_meta": cookie_meta(),
        "read_only_conclusion": len(action_hits) == 0,
        "logs_clean_conclusion": len(log_hits) == 0,
    }
    out.write_bytes(json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8"))
    print(json.dumps({"action_hits": len(action_hits), "log_credential_hits": len(log_hits),
                      "script_credential_hits": len(script_hits),
                      "cookies": {k: payload["cookie_meta"][k] for k in
                                  ("exists", "x_rows", "auth_token_name_present", "ct0_name_present")}},
                     ensure_ascii=False, indent=2))
    for hit in action_hits[:10]:
        print("ACTION", hit)
    return 0


if __name__ == "__main__":
    sys.exit(main())
