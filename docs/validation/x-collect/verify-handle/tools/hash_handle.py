"""Read-only hash baseline/after for x-collect handle verification."""

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
    r"D:\桌面\two\app\sources\bilibili_view.py": ("b0dc0ced1bc3be3eca85116559d5acae52f7753dca1dcbbac259e573cc73f98e", 12866),
    r"D:\桌面\two\app\core\importer.py": ("a11eaf4d39541ac11459eb1cebb8586f4922838b96714d7f7f3d2e253cff51a1", 49011),
    r"D:\桌面\two\app\sources\real_link.py": ("46cbd635b5e70cc2d1b6441befde31e25b8203caf28d39b772203c43b8f5802c", None),
    r"D:\桌面\two\app\storage\migrations\0001_init.sql": ("9b0493731305c2e3de3c89a1a16dcc8a53ca5882d014f63333b34e7c872e62bb", 14102),
    r"D:\桌面\two\app\storage\migrations\0002_draft_feedback.sql": ("34d70a1d501ba1aaf2fb93de1351ea80c470dcac9e6bc040617b19c5446c3aed", 2688),
    r"C:\Users\19183\.dsh\profiles\desktop\cordis.patch.yml": (None, None),
    r"C:\Users\19183\.dsh\tools\x-collect\scripts\x_collect.py": ("06ebace18dca4b6223f50162a682abfcc1cb1b24f3d03951214767bd4776d71d", 29253),
}


def sha(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    label = sys.argv[sys.argv.index("--label") + 1]
    out = pathlib.Path(sys.argv[sys.argv.index("--out") + 1])
    files = {}
    mismatches = []
    for text, (expected, expected_bytes) in EXPECTED.items():
        path = pathlib.Path(text)
        if not path.is_file():
            files[text] = {"exists": False}
            mismatches.append({"path": text, "reason": "missing"})
            continue
        digest = sha(path)
        size = path.stat().st_size
        ok = (expected is None or digest == expected) and (expected_bytes is None or size == expected_bytes)
        files[text] = {"sha256": digest, "bytes": size, "expected_sha256": expected, "ok": ok}
        if not ok:
            mismatches.append({"path": text, "sha256": digest, "expected_sha256": expected,
                               "bytes": size, "expected_bytes": expected_bytes})
    db = pathlib.Path(r"D:\桌面\two\instance\app.db")
    payload = {"label": label, "sampled_at_utc": __import__("datetime").datetime.now(
                   __import__("datetime").timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
               "files": files, "mismatches": mismatches,
               "business_db": {"sha256": sha(db), "bytes": db.stat().st_size,
                               "wal": pathlib.Path(str(db) + "-wal").exists(),
                               "shm": pathlib.Path(str(db) + "-shm").exists()}}
    out.write_bytes(json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8"))
    print(f"label={label} files={len(files)} mismatches={len(mismatches)} "
          f"business={payload['business_db']['sha256'][:16]} wal={payload['business_db']['wal']} "
          f"shm={payload['business_db']['shm']}")
    for item in mismatches:
        print("MISMATCH", json.dumps(item, ensure_ascii=False))
    return 0 if not mismatches else 1


if __name__ == "__main__":
    sys.exit(main())
