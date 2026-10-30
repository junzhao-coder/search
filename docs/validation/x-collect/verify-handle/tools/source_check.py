"""Read-only source/scope/cookie checks for the handle fix."""

from __future__ import annotations

import difflib
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
BEFORE = pathlib.Path(r"D:\桌面\two\docs\validation\x-collect\fix-handle\before_x_collect.py")
COOKIES = pathlib.Path(r"C:\Users\19183\.dsh\tools\x-collect\profile\Default\Network\Cookies")


def block(text: str, name: str) -> dict:
    match = re.search(rf'{name} = r"""(.*?)"""', text, re.S)
    if not match:
        return {"found": False}
    start_line = text[:match.start()].count("\n") + 1
    body = match.group(1)
    return {"found": True, "start_line": start_line,
            "end_line": text[:match.end()].count("\n") + 1,
            "body": body,
            "has_document_body": "document.body" in body,
            "has_body_innertext": "innerText" in body and "document.body" in body,
            "has_at_regex": bool(re.search(r"match\(/.*@", body))}


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
    before = BEFORE.read_text(encoding="utf-8")
    blocks = {name: block(text, name) for name in
              ("HANDLE_JS", "SETTINGS_HANDLE_JS", "CLICK_SWITCHER_JS", "MENU_HANDLE_JS")}
    # changed line ranges (independent diff of before vs current)
    diff = list(difflib.unified_diff(before.splitlines(), text.splitlines(), lineterm="", n=1))
    changed = [line for line in diff if line.startswith(("+", "-")) and not line.startswith(("+++", "---"))]
    # locate _handle/doctor code excerpts
    handle_def = re.search(r"async def _handle\(.*?\n(?=def |async def |\Z)", text, re.S)
    handle_excerpt = handle_def.group(0) if handle_def else ""
    handle_lines = text[:handle_def.start()].count("\n") + 1 if handle_def else None
    residual = []
    for name, info in blocks.items():
        if info.get("found") and info.get("has_body_innertext") and info.get("has_at_regex"):
            residual.append(name)
    payload = {
        "script": str(SCRIPT),
        "script_sha256": __import__("hashlib").sha256(SCRIPT.read_bytes()).hexdigest(),
        "before_sha256": __import__("hashlib").sha256(BEFORE.read_bytes()).hexdigest(),
        "blocks": blocks,
        "changed_line_count": len(changed),
        "changed_lines_sample": changed[:30],
        "handle_def_start_line": handle_lines,
        "handle_sequence_has_switcher_click": "CLICK_SWITCHER_JS" in handle_excerpt,
        "handle_sequence_has_menu": "MENU_HANDLE_JS" in handle_excerpt,
        "handle_sequence_has_settings": "SETTINGS_HANDLE_JS" in handle_excerpt,
        "handle_sequence_has_document_body": "document.body" in handle_excerpt,
        "handle_sequence_excerpt": handle_excerpt[:2400],
        "residual_body_fallbacks": residual,
        "HANDLE_JS_clean": blocks["HANDLE_JS"].get("found") and not blocks["HANDLE_JS"].get("has_body_innertext"),
        "cookie_meta": cookie_meta(),
    }
    out.write_bytes(json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8"))
    print(json.dumps({k: payload[k] for k in ("script_sha256", "before_sha256", "changed_line_count",
                                             "residual_body_fallbacks", "HANDLE_JS_clean",
                                             "handle_sequence_has_switcher_click", "handle_sequence_has_menu",
                                             "handle_sequence_has_settings",
                                             "cookie_meta")}, ensure_ascii=False, indent=2)[:2400])
    for name, info in blocks.items():
        print(name, {k: info.get(k) for k in ("found", "start_line", "end_line", "has_document_body",
                                             "has_body_innertext", "has_at_regex")})
    return 0


if __name__ == "__main__":
    sys.exit(main())
