"""Emit catalog/tool facts and the changed-files inventory."""

import hashlib
import json
import pathlib

EV = pathlib.Path(__file__).resolve().parent
WS = EV.parents[4]
DSH = pathlib.Path(r"C:\Users\19183\.dsh")
SKILL = DSH / "skills" / "agent-reach"
VENV = pathlib.Path(r"C:\Users\19183\.agent-reach-venv")
BACKUP = DSH / "tooling-backups" / "agent-reach"


def sha(p):
    return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()


catalog_note = """DSH skill catalog evidence (2026-10-21, same model step after skill install)
- The session's available-skills catalog now contains an `agent-reach` entry whose description matches
  `C:\\Users\\19183\\.dsh\\skills\\agent-reach\\SKILL.md` frontmatter (read-only internet research/search/read).
- This catalog is the DSH skill discovery surface; the new user-level skill appeared without restarting DSH.
- Direct load attempt: `skill(name="agent-reach")` -> "Flow 当前角色不允许此工具；未知工具及其他代理/脚本通道默认拒绝".
  Loading is therefore NOT verified by this executor; only discovery is verified.
"""
(EV / "17_catalog_and_tool.txt").write_text(catalog_note, encoding="utf-8", newline="\n")

inventory = {
    "recorded_utc": "2026-10-21T13:22Z",
    "created": [],
    "modified": [],
    "not_created": [
        r"C:\Users\19183\.agent-reach",
        r"C:\Users\19183\.dsh\mcp* (MCP registry untouched)",
        "system PATH / proxy / global pip and npm settings",
    ],
}

for p in sorted(SKILL.rglob("*")):
    if p.is_file():
        inventory["created"].append({"path": str(p), "bytes": p.stat().st_size, "sha256": sha(p)})
for p in sorted(BACKUP.rglob("*")):
    if p.is_file():
        inventory["created"].append({"path": str(p), "bytes": p.stat().st_size, "sha256": sha(p)})

venv_marker = VENV / "Scripts" / "agent-reach.exe"
inventory["created"].append({
    "path": str(venv_marker),
    "bytes": venv_marker.stat().st_size if venv_marker.exists() else None,
    "note": "isolated venv (Python 3.12.10); full site-packages tree omitted from inventory",
})
inventory["created"].append({
    "path": str(VENV / "pyvenv.cfg"),
    "bytes": (VENV / "pyvenv.cfg").stat().st_size,
    "sha256": sha(VENV / "pyvenv.cfg"),
})

for p in sorted(EV.parent.rglob("*")):
    if p.is_file():
        inventory["created"].append({"path": str(p), "bytes": p.stat().st_size, "sha256": sha(p)})

inventory["workspace_code_unchanged"] = True
(EV / "20_changed_files.json").write_text(
    json.dumps(inventory, ensure_ascii=False, indent=1), encoding="utf-8", newline="\n")

print(json.dumps({"created_count": len(inventory["created"]),
                  "skill_files": len(list(SKILL.rglob('*'))),
                  "backup_files": len(list(BACKUP.rglob('*')))}, ensure_ascii=False))
