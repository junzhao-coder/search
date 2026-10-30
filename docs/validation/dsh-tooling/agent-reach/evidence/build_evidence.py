"""Build structured evidence for the Agent Reach DSH installation report."""

import hashlib
import json
import pathlib
import re

EV = pathlib.Path(__file__).resolve().parent
WS = EV.parents[4]  # docs/validation/dsh-tooling/agent-reach/evidence -> workspace root


def jload(name):
    return json.loads((EV / name).read_text(encoding="utf-8"))


def sha(p):
    return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()


def strip_tags(text):
    return re.sub(r"<[^>]+>", "", text)


doctor = jload("09_doctor.json")
bili = jload("12_bilibili_search.json")
gh = jload("10_public_search_github.json")
readme = (EV / "14_public_read_raw_readme.md").read_text(encoding="utf-8")

bili_items = []
for item in bili["data"]["result"][:3]:
    bili_items.append({
        "title": strip_tags(item.get("title", "")),
        "bvid": item.get("bvid"),
        "url": item.get("arcurl"),
        "author": item.get("author"),
    })

gh_items = [{"full_name": i["full_name"], "html_url": i["html_url"]}
            for i in gh["items"][:3]]

summary = {
    "recorded_utc": "2026-10-21T13:21Z",
    "cli": {
        "version": (EV / "05b_version.out.txt").read_text(encoding="utf-8").strip(),
        "help_exit_file": "06b_help.out.txt",
        "dryrun_file": "07b_dryrun.out.txt",
    },
    "doctor": {k: {"status": v.get("status"), "active_backend": v.get("active_backend")}
               for k, v in doctor.items()},
    "public_search": {
        "bilibili_api": {
            "exit": 0,
            "code": bili.get("code"),
            "results": bili.get("data", {}).get("numResults"),
            "first": bili_items,
        },
        "github_rest": {
            "exit": 0,
            "total_count": gh.get("total_count"),
            "first": gh_items,
        },
    },
    "public_read": {
        "source": "https://raw.githubusercontent.com/Panniantong/Agent-Reach/94f06c1969dfc1834001269d79d3ad0972d9dee6/README.md",
        "exit": 0,
        "bytes": (EV / "14_public_read_raw_readme.md").stat().st_size,
        "title_line": next((ln for ln in readme.splitlines() if "<h1" in ln), ""),
    },
    "failures": {
        "jina_reader": {"exit": 28, "note": "curl timeout; raw web read used instead"},
        "v2ex": {"exit": 28, "note": "curl timeout; not verified"},
        "skill_tool": {"denied": "Flow 当前角色不允许此工具"},
    },
    "skill": {
        "root": r"C:\Users\19183\.dsh\skills\agent-reach",
        "catalog_discovered": True,
        "note": "session skill catalog 在本步出现了 agent-reach 条目，描述与 SKILL.md 一致；skill 工具加载被 Flow 角色策略拒绝。",
    },
}

(EV / "16_summary.json").write_text(
    json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8", newline="\n")

expected = {
    "requirements.txt": "0AF19A0F1C100E99483B79E7F11B500CCF6A5A1477D8AC4B560C077B2BEA7731",
    "docs/design/CONTRACT.md": "826C24CC6C99551178875BED617E085231BD23998B6A049F396116E1E70FB4F9",
    "app/storage/migrations/0001_init.sql": "9B0493731305C2E3DE3C89A1A16DCC8A53CA5882D014F63333B34E7C872E62BB",
    "app/storage/migrations/0002_draft_feedback.sql": "34D70A1D501BA1AAF2FB93DE1351EA80C470DCAC9E6BC040617B19C5446C3AED",
    "app/sources/wiring.py": "BAFCF3974CBFB3ED4DA99936E5D65D10D6F02C663B6325008255B4EAECC0DA05",
    "app/sources/bilibili_view.py": "B0DC0CED1BC3BE3ECA85116559D5ACAE52F7753DCA1DCBBAC259E573CC73F98E",
    "app/core/importer.py": "A11EAF4D39541AC11459EB1CEBB8586F4922838B96714D7F7F3D2E253CFF51A1",
    "app/sources/real_link.py": "46CBD635B5E70CC2D1B6441BEFDE31E25B8203CAF28D39B772203C43B8F5802C",
    "instance/app.db": "E073F828CF0F30D6206361BBA3A729826BE096BE3308F5A5DC204406DAE4EB85",
}
after = {}
for rel, want in expected.items():
    p = WS / rel
    got = sha(p)
    after[rel] = {"sha256": got.upper(), "matches_baseline": got.upper() == want, "bytes": p.stat().st_size}
after["instance/app.db-wal"] = {"exists": (WS / "instance/app.db-wal").exists()}
after["instance/app.db-shm"] = {"exists": (WS / "instance/app.db-shm").exists()}
after["all_match"] = all(v.get("matches_baseline", True) for v in after.values() if isinstance(v, dict))
(EV / "19_baseline_after.json").write_text(
    json.dumps(after, ensure_ascii=False, indent=1), encoding="utf-8", newline="\n")

bad = []
for p in sorted(EV.glob("*")):
    if p.suffix.lower() in (".txt", ".json", ".md", ".log", ".csv"):
        try:
            p.read_text(encoding="utf-8")
        except Exception as exc:
            bad.append({"file": p.name, "error": repr(exc)})
(EV / "21_utf8_check.txt").write_text(
    "checked=%d bad=%d\n%s\n" % (
        len(list(EV.glob("*"))), len(bad), json.dumps(bad, ensure_ascii=False)),
    encoding="utf-8", newline="\n")

print(json.dumps({"summary": summary["public_search"], "baseline_all_match": after["all_match"],
                  "bad_utf8": bad}, ensure_ascii=False, indent=1))
