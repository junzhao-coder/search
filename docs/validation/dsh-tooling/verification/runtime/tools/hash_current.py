"""Independent current-hash recomputation for DSH tooling + business baseline files (read-only)."""

from __future__ import annotations

import hashlib
import json
import pathlib
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:  # pragma: no cover
    pass

EXPECTED = {
    r"D:\桌面\two\instance\app.db": ("e073f828cf0f30d6206361bba3a729826be096be3308f5a5dc204406dae4eb85", 241664),
    r"D:\桌面\two\requirements.txt": ("0af19a0f1c100e99483b79e7f11b500ccf6a5a1477d8ac4b560c077b2bea7731", 179),
    r"D:\桌面\two\docs\design\CONTRACT.md": ("826c24cc6c99551178875bed617e085231bd23998b6a049f396116e1e70fb4f9", 74839),
    r"D:\桌面\two\app\sources\wiring.py": ("bafcf3974cbfb3ed4da99936e5d65d10d6f02c663b6325008255b4eaecc0da05", 8402),
    r"D:\桌面\two\app\core\importer.py": ("a11eaf4d39541ac11459eb1cebb8586f4922838b96714d7f7f3d2e253cff51a1", 49011),
    r"D:\桌面\two\app\sources\bilibili_view.py": ("b0dc0ced1bc3be3eca85116559d5acae52f7753dca1dcbbac259e573cc73f98e", 12866),
    r"D:\桌面\two\app\sources\real_link.py": ("46cbd635b5e70cc2d1b6441befde31e25b8203caf28d39b772203c43b8f5802c", None),
    r"D:\桌面\two\app\storage\migrations\0001_init.sql": ("9b0493731305c2e3de3c89a1a16dcc8a53ca5882d014f63333b34e7c872e62bb", 14102),
    r"D:\桌面\two\app\storage\migrations\0002_draft_feedback.sql": ("34d70a1d501ba1aaf2fb93de1351ea80c470dcac9e6bc040617b19c5446c3aed", 2688),
    r"C:\Users\19183\.dsh\profiles\desktop\package.json": ("10424b6b3ce5609fef0aeb63f6d55da740a6c5a4b4a1f6f569879b9dcdccac5c", 832),
    r"C:\Users\19183\.dsh\profiles\desktop\cordis.patch.yml": ("fda036e9aec82a7e07054df16e0ec425c0276ce6b6107e158239198fdb13c355", 10899),
    r"C:\Users\19183\AppData\Local\Programs\DeepSeek Harness\resources\app\dsh\package.json": ("b67a65b9719272b2eb54093b63c121d05907da062a1393e8c9f871e1cd18f94e", 17100),
    r"C:\Users\19183\AppData\Local\Programs\DeepSeek Harness\resources\app\dsh\node_modules\@deepseek-ai\dsh-mcp-client\lib\index.js": ("758d8fc473b700b5d351158d06ce9f9e92c16e8b25497b08bb7bd2122a87f5dd", 35041),
}
AGENT_SKILL_EXPECTED = {
    "DSH-INSTALL-NOTES.md": ("9373ebfc423597a986ba227c301fa08815c3b944e426a8cd57721c2add9c945c", 6000),
    "LICENSE": ("e94c131ac1c2f78cfd8f7e69da354c0ff58e4e54071697703d56856c036de402", 1067),
    "SKILL.md": ("1bb7eae7322220f89299d683f9ce7caac8d2800ad5ee898d353010e5dfcd3fa9", 6316),
    "SOURCE.md": ("6b134cdc7d16ffbf317cc45e08ae1da4c16970508e5c604fcdf7ebec3ecd2ce0", 1679),
    "references/career.md": ("ade444ac499e55f02c84bd663253a28cebc1eefc7f56c7248dc6792841fbe53e", 9249),
    "references/dev.md": ("f6f91107557eacf1d28a023d597eb5a61353a8a6ede286c3c0a4888d274df9fe", 1383),
    "references/finance.md": ("c0cf89af1119d81890f6797ff9e8154a00ee08c17141e7d18c1b09658a916551", 1474),
    "references/install.md": ("269dfa9308f0adf06d9efe22591fd60a48af785b2c4921302ff2d6726ee579f5", 22167),
    "references/README.md": ("7b723bcd4e5992c37ad1c25c3a2badd89c723a105b787fde9d1aa19a215f7ff7", 22830),
    "references/search.md": ("23bfc54a3b85847ac7c1e12d6dbb0913d6fa3bb89a706d79e2b36396a8a8ef5d", 1066),
    "references/social.md": ("e2e6451eb931effd4f63ea407fbb109bea1e98de34bd703c52753ad0cc7025b3", 10521),
    "references/video.md": ("167ce732382c664eea63b884685dc085caa27cd69820138f7eeb91b0162efac8", 5515),
    "references/web.md": ("b238fc897975a693d7bb262600ca2ea69cd13a4892e870d346dbe375c880b303", 1087),
}


def sha(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    out_path = pathlib.Path(sys.argv[sys.argv.index("--out") + 1])
    files = {}
    mismatches = []
    for path_text, (expected_sha, expected_bytes) in EXPECTED.items():
        path = pathlib.Path(path_text)
        if not path.is_file():
            files[path_text] = {"exists": False}
            mismatches.append({"path": path_text, "reason": "missing"})
            continue
        sha_value = sha(path)
        bytes_value = path.stat().st_size
        ok = sha_value == expected_sha and (expected_bytes is None or bytes_value == expected_bytes)
        files[path_text] = {"exists": True, "sha256": sha_value, "bytes": bytes_value,
                            "expected_sha256": expected_sha, "expected_bytes": expected_bytes, "ok": ok}
        if not ok:
            mismatches.append({"path": path_text, "sha256": sha_value, "expected": expected_sha,
                               "bytes": bytes_value, "expected_bytes": expected_bytes})
    skill_root = pathlib.Path(r"C:\Users\19183\.dsh\skills\agent-reach")
    skill_files = {}
    for rel, (expected_sha, expected_bytes) in AGENT_SKILL_EXPECTED.items():
        path = skill_root / rel
        if not path.is_file():
            skill_files[rel] = {"exists": False}
            mismatches.append({"path": f"agent-reach-skill/{rel}", "reason": "missing"})
            continue
        sha_value = sha(path)
        ok = sha_value == expected_sha and path.stat().st_size == expected_bytes
        skill_files[rel] = {"sha256": sha_value, "bytes": path.stat().st_size, "ok": ok}
        if not ok:
            mismatches.append({"path": f"agent-reach-skill/{rel}", "sha256": sha_value,
                               "expected": expected_sha, "bytes": path.stat().st_size,
                               "expected_bytes": expected_bytes})
    stealth_skill_root = pathlib.Path(r"C:\Users\19183\.dsh\skills\stealth-browser-mcp")
    stealth_skill = {}
    if stealth_skill_root.is_dir():
        for path in sorted(p for p in stealth_skill_root.rglob("*") if p.is_file()):
            rel = path.relative_to(stealth_skill_root).as_posix()
            stealth_skill[rel] = {"sha256": sha(path), "bytes": path.stat().st_size}
    stealth_repo = pathlib.Path(r"C:\Users\19183\.dsh\tools\stealth-browser-mcp\repo")
    stealth_repo_files = {}
    for rel in ("pyproject.toml", "src/server.py", "LICENSE"):
        path = stealth_repo / rel
        if path.is_file():
            stealth_repo_files[rel] = {"sha256": sha(path), "bytes": path.stat().st_size}
    business = pathlib.Path(r"D:\桌面\two\instance\app.db")
    import re as _re
    pyproject_text = (stealth_repo / "pyproject.toml").read_text(encoding="utf-8")
    version_match = _re.search(r'(?m)^version\s*=\s*"([^"]+)"', pyproject_text)
    payload = {
        "sampled_at_utc": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "files": files,
        "agent_reach_skill": {"root": str(skill_root), "file_count": len(skill_files), "files": skill_files},
        "stealth_skill": {"root": str(stealth_skill_root), "file_count": len(stealth_skill), "files": stealth_skill},
        "stealth_repo_key_files": stealth_repo_files,
        "stealth_pyproject_version": version_match.group(1) if version_match else None,
        "business_db": {"sha256": sha(business), "bytes": business.stat().st_size,
                        "wal": pathlib.Path(str(business) + "-wal").exists(),
                        "shm": pathlib.Path(str(business) + "-shm").exists()},
        "mismatches": mismatches,
        "all_expected_ok": not mismatches,
    }
    out_path.write_bytes(json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8"))
    print(f"files={len(files)} agent_skill={len(skill_files)} stealth_skill={len(stealth_skill)} "
          f"mismatches={len(mismatches)} all_ok={payload['all_expected_ok']}")
    for item in mismatches:
        print("MISMATCH", json.dumps(item, ensure_ascii=False))
    print("business", payload["business_db"])
    print("stealth_repo", stealth_repo_files)
    return 0 if payload["all_expected_ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
