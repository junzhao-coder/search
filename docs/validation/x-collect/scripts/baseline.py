"""Baseline / after hash capture for x-collect (no SQL, file hashes only)."""

import hashlib
import json
import os
import pathlib
import sys
import time

WS = pathlib.Path(r"D:\桌面\two")
DSH_HOME = pathlib.Path(r"C:\Users\19183\.dsh")
DSH_CORE = pathlib.Path(r"C:\Users\19183\AppData\Local\Programs\DeepSeek Harness\resources\app\dsh")
CHROME = pathlib.Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe")
TOOL = DSH_HOME / "tools" / "x-collect"
OUT = WS / "docs" / "validation" / "x-collect" / "login"


def sha(p):
    h = hashlib.sha256()
    with open(p, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def file_entry(p):
    return {"path": str(p), "exists": p.exists(),
            "bytes": p.stat().st_size if p.exists() else None,
            "sha256": sha(p) if p.exists() else None}


def tree_manifest(root):
    files = []
    if not root.exists():
        return {"root": str(root), "exists": False, "files": [], "tree_sha256": None}
    for p in sorted(root.rglob("*")):
        if p.is_file():
            files.append({"rel": str(p.relative_to(root)), "bytes": p.stat().st_size,
                          "sha256": sha(p)})
    h = hashlib.sha256()
    for f in files:
        h.update(f["rel"].encode("utf-8"))
        h.update(f["sha256"].encode("ascii"))
        h.update(str(f["bytes"]).encode("ascii"))
    return {"root": str(root), "exists": True, "file_count": len(files),
            "files": files, "tree_sha256": h.hexdigest()}


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "before"
    OUT.mkdir(parents=True, exist_ok=True)
    files = {
        "requirements": WS / "requirements.txt",
        "contract": WS / "docs" / "design" / "CONTRACT.md",
        "wiring": WS / "app" / "sources" / "wiring.py",
        "bilibili_view": WS / "app" / "sources" / "bilibili_view.py",
        "importer": WS / "app" / "core" / "importer.py",
        "real_link": WS / "app" / "sources" / "real_link.py",
        "migration_0001": WS / "app" / "storage" / "migrations" / "0001_init.sql",
        "migration_0002": WS / "app" / "storage" / "migrations" / "0002_draft_feedback.sql",
        "business_db": WS / "instance" / "app.db",
    }
    data = {
        "mode": mode,
        "recorded_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "cwd": os.getcwd(),
        "paths": {
            "dsh_home": str(DSH_HOME),
            "dsh_core": str(DSH_CORE),
            "chrome": str(CHROME),
            "tool": str(TOOL),
            "python": sys.executable,
        },
        "files": {k: file_entry(v) for k, v in files.items()},
        "dsh_core_package_json": file_entry(DSH_CORE / "package.json"),
        "dsh_mcp_client": tree_manifest(DSH_CORE / "node_modules" / "@deepseek-ai" / "dsh-mcp-client"),
        "tool_dir": {
            "root": str(TOOL),
            "exists": TOOL.exists(),
            "entries": sorted([p.name for p in TOOL.iterdir()]) if TOOL.exists() else [],
            "venv_file_count": sum(1 for p in (TOOL / "venv").rglob("*") if p.is_file())
            if (TOOL / "venv").exists() else 0,
            "venv_bytes": sum(p.stat().st_size for p in (TOOL / "venv").rglob("*") if p.is_file())
            if (TOOL / "venv").exists() else 0,
            "profile_file_count": sum(1 for p in (TOOL / "profile").rglob("*") if p.is_file())
            if (TOOL / "profile").exists() else 0,
        },
        "business_db_sidecars": {
            "wal": (WS / "instance" / "app.db-wal").exists(),
            "shm": (WS / "instance" / "app.db-shm").exists(),
        },
        "dsh_profiles_touched": False,
        "daily_chrome_touched": False,
    }
    if CHROME.exists():
        data["paths"]["chrome_bytes"] = CHROME.stat().st_size
        data["paths"]["chrome_mtime_utc"] = time.strftime(
            "%Y-%m-%dT%H:%M:%SZ", time.gmtime(CHROME.stat().st_mtime))
    out = OUT / f"{mode}.json"
    out.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8", newline="\n")
    print(f"{mode}: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
