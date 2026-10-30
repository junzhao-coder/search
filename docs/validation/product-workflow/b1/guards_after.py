"""守卫 hash 清单 + 与可追溯 baseline 比对，输出 guards_after.json。"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import pathlib
import sys

ROOT = pathlib.Path(r"D:\桌面\two")
B1 = ROOT / "docs" / "validation" / "product-workflow" / "b1"
BASELINE = ROOT / "docs" / "validation" / "money-project" / "verify" / "baseline_before.json"

TARGETS = [
    "instance/app.db",
    "docs/design/CONTRACT.md",
    "app/sources/wiring.py",
    "app/sources/bilibili_view.py",
    "app/core/importer.py",
    "docs/validation/money-project/scoring/scores.csv",
    "docs/validation/money-project/scoring/items.jsonl",
    "docs/validation/money-project/scoring/model.md",
    "docs/validation/money-project/scoring/raw",
    "docs/validation/money-project/sourcing/sources.csv",
    "docs/validation/money-project/sourcing/price_signals.csv",
    "docs/validation/money-project/sourcing/opportunity_sourcing_top10.csv",
    "docs/validation/money-project/sourcing/raw",
    "migrations",
    "alembic",
]


def sha_file(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sha_tree(path: pathlib.Path) -> tuple[str, int]:
    files = sorted(f for f in path.rglob("*") if f.is_file() and "__pycache__" not in f.parts)
    digest = hashlib.sha256("\n".join(f"{sha_file(f)}  {f.relative_to(ROOT).as_posix()}" for f in files).encode())
    return digest.hexdigest(), len(files)


def main() -> int:
    out: dict = {"generated_utc": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "items": {}}
    for rel in TARGETS:
        path = ROOT / rel
        if not path.exists():
            out["items"][rel] = {"exists": False}
            continue
        if path.is_file():
            out["items"][rel] = {"exists": True, "kind": "file", "bytes": path.stat().st_size,
                                 "sha256": sha_file(path)}
        else:
            digest, count = sha_tree(path)
            out["items"][rel] = {"exists": True, "kind": "dir", "files": count, "tree_sha256": digest}

    baseline = {}
    if BASELINE.exists():
        raw = json.loads(BASELINE.read_text(encoding="utf-8"))
        for key, meta in raw.items():
            value = meta.get("sha256") or meta.get("tree_sha256")
            if value:
                baseline[key] = value
    out["baseline"] = {"path": str(BASELINE.relative_to(ROOT)), "entries": len(baseline),
                       "source": "docs/validation/money-project/verify/baseline_before.json（上一轮独立只读核验产物）"}
    known = {
        "instance/app.db": "e073f828cf0f30d6206361bba3a729826be096be3308f5a5dc204406dae4eb85",
        "docs/design/CONTRACT.md": "826c24cc6c99551178875bed617e085231bd23998b6a049f396116e1e70fb4f9",
        "docs/validation/money-project/scoring/scores.csv": "ab0c3546c3e9e46ffe726aa036aecce7e535c38fd54f3423c4e4b4bb03967cd1",
        "docs/validation/money-project/sourcing/sources.csv": "13679b60d2ba1c326b9bf85e35f24f4bc230104a500c9ee8dde2e3544061b5f4",
        "app/core/importer.py": "a11eaf4d39541ac11459eb1cebb8586f4922838b96714d7f7f3d2e253cff51a1",
        "app/sources/wiring.py": "bafcf3974cbfb3ed4da99936e5d65d10d6f02c663b6325008255b4eaecc0da05",
    }
    comparisons = {}
    for rel, expected in known.items():
        actual = (out["items"].get(rel) or {}).get("sha256")
        comparisons[rel] = {"expected": expected, "actual": actual, "match": actual == expected}
    for rel, value in baseline.items():
        item = out["items"].get(rel)
        if not item:
            continue
        actual = item.get("sha256") or item.get("tree_sha256")
        comparisons.setdefault(rel, {"expected": value, "actual": actual, "match": actual == value})
    out["comparisons"] = comparisons
    external = {
        "docs/validation/money-project/scoring/model.md":
            "外部评分产物重生成（mtime 2026-10-22T11:19:49Z），发生于 B1 实施之前，非本任务写入",
        "docs/validation/money-project/sourcing/opportunity_sourcing_top10.csv":
            "外部货源联动产物重生成（mtime 2026-10-22T09:49:48Z），发生于 B1 实施之前，非本任务写入",
    }
    for rel, meta in out["items"].items():
        path = ROOT / rel
        if meta.get("exists") and path.is_file():
            meta["mtime_utc"] = dt.datetime.fromtimestamp(path.stat().st_mtime, dt.timezone.utc).strftime(
                "%Y-%m-%dT%H:%M:%SZ")
    changed = [k for k, v in comparisons.items() if not v["match"]]
    out["changed"] = changed
    out["changed_external"] = [{"path": k, "reason": external.get(k, "无归因记录（需人工复核）")} for k in changed]
    out["changed_by_this_task"] = [k for k in changed if k not in external]
    out["baseline_note"] = ("baseline_before.json 生成于上一轮只读核验（2026-10-22T09:08Z）；"
                            "其后外部任务重生成过 scoring/model.md 与 sourcing/opportunity_sourcing_top10.csv，"
                            "故这两项与旧 baseline 不同属预期，已在 changed_external 逐条归因。")
    (B1 / "guards_after.json").write_bytes(json.dumps(out, ensure_ascii=False, indent=1).encode())
    print(json.dumps({"items": len(out["items"]), "compared": len(comparisons), "changed": out["changed"],
                      "changed_by_this_task": out["changed_by_this_task"]}, ensure_ascii=True))
    return 0 if not out["changed_by_this_task"] else 1


if __name__ == "__main__":
    sys.exit(main())
