"""Final consistency check for the Agent Reach install report."""

import hashlib
import json
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[1]  # agent-reach dir
EV = ROOT / "evidence"


def sha(p):
    return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()


files = []
bom = []
crlf = []
bad = []
for p in sorted(ROOT.rglob("*")):
    if not p.is_file():
        continue
    raw = p.read_bytes()
    info = {"path": str(p.relative_to(ROOT)), "bytes": len(raw), "sha256": sha(p)}
    if p.suffix.lower() in (".md", ".json", ".txt", ".log", ".csv", ".py"):
        try:
            text = raw.decode("utf-8")
        except Exception as exc:
            bad.append({"file": info["path"], "error": repr(exc)})
            text = ""
        if raw.startswith(b"\xef\xbb\xbf"):
            bom.append(info["path"])
        if b"\r\n" in raw:
            crlf.append(info["path"])
        info["lines"] = len(text.splitlines())
    files.append(info)

report = (ROOT / "INSTALLATION.md").read_text(encoding="utf-8")
links = re.findall(r"\]\(([^)]+)\)", report)
missing = []
for link in links:
    if link.startswith("http"):
        continue
    target = (ROOT / link.split("#")[0]).resolve()
    if not target.exists():
        missing.append(link)

skill_root = pathlib.Path(r"C:\Users\19183\.dsh\skills\agent-reach")
skill_files = sorted(str(p) for p in skill_root.rglob("*") if p.is_file())
skill_ok = (skill_root / "SKILL.md").exists() and len(skill_files) >= 13

baseline = json.loads((EV / "19_baseline_after.json").read_text(encoding="utf-8"))
result = {
    "report_lines": len(report.splitlines()),
    "report_sha256": sha(ROOT / "INSTALLATION.md"),
    "file_count": len(files),
    "utf8_bad": bad,
    "bom_files": bom,
    "crlf_files": crlf,
    "missing_links": missing,
    "skill_root_files": len(skill_files),
    "skill_ok": skill_ok,
    "workspace_baseline_all_match": baseline.get("all_match"),
    "business_db_sha256": baseline.get("instance/app.db", {}).get("sha256"),
    "business_wal": baseline.get("instance/app.db-wal", {}).get("exists"),
    "business_shm": baseline.get("instance/app.db-shm", {}).get("exists"),
}
(EV / "23_final_check.json").write_text(
    json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8", newline="\n")
print(json.dumps(result, ensure_ascii=False, indent=1))
