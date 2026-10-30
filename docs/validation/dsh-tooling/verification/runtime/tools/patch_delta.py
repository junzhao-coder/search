"""Non-destructive review of the cordis.patch.yml append-only delta (no other config printed)."""

from __future__ import annotations

import hashlib
import json
import pathlib
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:  # pragma: no cover
    pass

CURRENT = pathlib.Path(r"C:\Users\19183\.dsh\profiles\desktop\cordis.patch.yml")
def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def normalize(data: bytes) -> bytes:
    return data.replace(b"\r\n", b"\n").replace(b"\r", b"\n")


def main() -> int:
    backup = pathlib.Path(sys.argv[sys.argv.index("--backup") + 1])
    out_path = pathlib.Path(sys.argv[sys.argv.index("--out") + 1])
    current_bytes = CURRENT.read_bytes()
    backup_bytes = backup.read_bytes()
    current_text = normalize(current_bytes)
    backup_text = normalize(backup_bytes)
    byte_prefix = current_bytes.startswith(backup_bytes)
    # normalized prefix: tolerate line-ending normalisation only
    normalized_prefix = current_text.startswith(backup_text)
    common = 0
    limit = min(len(current_bytes), len(backup_bytes))
    while common < limit and current_bytes[common] == backup_bytes[common]:
        common += 1
    current_lines = current_text.decode("utf-8").splitlines()
    backup_lines = backup_text.decode("utf-8").splitlines()
    line_prefix = current_lines[:len(backup_lines)] == backup_lines
    added_lines = current_lines[len(backup_lines):]
    added_text = "\n".join(added_lines) + "\n"
    block = {"serverName": None, "transport": None, "command": None, "args": [], "cwd": None,
             "env_keys": [], "name": None, "failOnStartupError": None}
    for line in added_lines:
        stripped = line.strip()
        if stripped.startswith("serverName:"):
            block["serverName"] = stripped.split(":", 1)[1].strip()
        elif stripped.startswith("transport:"):
            block["transport"] = stripped.split(":", 1)[1].strip()
        elif stripped.startswith("name:") and block["name"] is None:
            block["name"] = stripped.split(":", 1)[1].strip().strip('"')
        elif stripped.startswith("failOnStartupError:"):
            block["failOnStartupError"] = stripped.split(":", 1)[1].strip()
        elif stripped.startswith("command:"):
            block["command"] = stripped.split(":", 1)[1].strip().strip('"')
        elif stripped.startswith("cwd:"):
            block["cwd"] = stripped.split(":", 1)[1].strip().strip('"')
        elif stripped.startswith("- ") and block["args"] is not None and "args" not in stripped:
            pass
    # parse the added YAML block's key fields without printing the rest of the file
    in_added = False
    mode = None
    for line in added_lines:
        if "- insert:" in line:
            in_added = True
            mode = None
            continue
        if not in_added:
            continue
        stripped = line.strip()
        if stripped.startswith("args:"):
            block["args"] = []
            mode = "args"
            continue
        if stripped.startswith("env:"):
            block["env_keys"] = []
            mode = "env"
            continue
        if stripped.startswith("failOnStartupError:"):
            mode = None
        if mode == "args" and stripped.startswith("- "):
            block["args"].append(stripped[2:].strip().strip('"'))
        elif mode == "env" and ":" in stripped and not stripped.startswith("-"):
            block["env_keys"].append(stripped.split(":", 1)[0].strip())
    insert_count = sum(1 for line in added_lines if "- insert:" in line)
    added_ids = [line.strip().split("id:", 1)[1].strip() for line in added_lines
                 if line.strip().startswith("- id:")]
    expected_current_sha = "fda036e9aec82a7e07054df16e0ec425c0276ce6b6107e158239198fdb13c355"
    expected_backup_sha = "7fe6843373d8ae1e772d0db38f08b2a360b19966aa5b073e03f7f1af3fadefde"
    payload = {
        "sampled_at_utc": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "current": {"path": str(CURRENT), "bytes": len(current_bytes), "sha256": sha(current_bytes),
                    "lines": len(current_lines), "expected_sha256": expected_current_sha,
                    "sha_matches": sha(current_bytes) == expected_current_sha},
        "backup": {"path": str(backup), "bytes": len(backup_bytes), "sha256": sha(backup_bytes),
                   "lines": len(backup_lines), "expected_sha256": expected_backup_sha,
                   "sha_matches": sha(backup_bytes) == expected_backup_sha},
        "prefix": {"byte_prefix_equal": byte_prefix, "normalized_text_prefix_equal": normalized_prefix,
                   "line_prefix_equal": line_prefix, "common_bytes": common},
        "delta": {"added_lines": len(added_lines), "insert_blocks": insert_count, "added_ids": added_ids,
                  "added_block_sha256": sha(added_text.encode("utf-8")), "added_text": added_text,
                  "block_fields": block},
        "verdict": {
            "append_only": line_prefix and normalized_prefix,
            "only_one_insert_block": insert_count == 1,
            "added_id_is_stealth": added_ids == ["stealth-browser-mcp"],
            "block_contract_ok": block["name"] == "@deepseek-ai/dsh-mcp-client"
                                   and block["transport"] == "stdio"
                                   and block["failOnStartupError"] == "true"
                                   and bool(block["args"]) and bool(block["cwd"]),
            "rollback_by_suffix_delete_restores_backup": line_prefix,
            "actual_rollback_performed": False,
        },
    }
    payload["ok"] = (payload["verdict"]["append_only"] and payload["verdict"]["only_one_insert_block"]
                     and payload["verdict"]["added_id_is_stealth"] and payload["verdict"]["block_contract_ok"]
                     and payload["current"]["sha_matches"] and payload["backup"]["sha_matches"])
    out_path.write_bytes(json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8"))
    print(json.dumps({key: payload[key] for key in ("current", "backup", "prefix", "verdict", "ok")},
                     ensure_ascii=False, indent=2))
    print("added_block_sha256", payload["delta"]["added_block_sha256"])
    print("added_lines", payload["delta"]["added_lines"])
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
