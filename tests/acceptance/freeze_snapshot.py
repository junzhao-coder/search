"""冻结只读快照（第二批：真实入口守卫版）。

- RUN_ID：命令行参数或随机后缀；必须是单段安全名，解析后须落在 _snapshots/ 下一层。
- 目录独占创建：已存在即失败，**不删除、不覆盖**既有快照/清单/指针。
- 清单/来源校验失败时非零退出，不写指针。
- probe 与后续服务一律 PYTHONDONTWRITEBYTECODE，避免在快照内生成副产物。

用法：
    & .\\.venv\\Scripts\\python.exe -X utf8 tests\\acceptance\\freeze_snapshot.py [RUN_ID]
"""

from __future__ import annotations

import json
import os
import random
import shutil
import string
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _guard as guard  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
ACC = ROOT / "tests" / "acceptance"
# 根与指针一律经 guard 解析（env 覆盖只允许 tests/acceptance/_tmp 之下），不直接信任 env


def main(argv: list[str]) -> int:
    run_id = argv[1] if len(argv) > 1 else "s2d_" + time.strftime("%Y%m%d_%H%M%S") + "_" + \
        "".join(random.choice(string.ascii_lowercase + string.digits) for _ in range(4))
    try:
        snap_root = guard.snapshot_root()                   # 批准根 + 链接核对（env 不能扩根）
        pointer = guard.pointer_path()                      # 指针同样经守卫解析
        snapshot = guard.resolve_under(snap_root, run_id)   # 非法/越界在此拒绝
        if snapshot.exists():
            raise guard.GuardError(f"快照已存在，拒绝覆盖：{snapshot}")
        manifest_file = snap_root / f"{run_id}.manifest.sha256"
        if manifest_file.exists():
            raise guard.GuardError(f"清单已存在，拒绝覆盖：{manifest_file}")
        rels = guard.collect(ROOT)
        if not rels:
            raise guard.GuardError("实时树未采集到任何文件，拒绝创建空快照")
        _, live_before = guard.manifest(ROOT, rels)
        guard.exclusive_dir(snapshot)                        # 独占创建
    except guard.GuardError as exc:
        print(f"[FAIL] {exc}")
        return 1
    except FileExistsError:
        print(f"[FAIL] 目录已存在，拒绝覆盖：{snapshot}")
        return 1

    for rel in rels:
        dst = snapshot / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / rel, dst)

    snap_lines, snap_hash = guard.manifest(snapshot)
    _, live_after = guard.manifest(ROOT, rels)
    ok = live_before == live_after == snap_hash and guard.collect(snapshot) == rels
    if not ok:                                            # 先拒哈希不符，再 probe
        print(f"[FAIL] 一致性校验失败（probe 之前）：live_before={live_before} "
              f"live_after={live_after} snap={snap_hash}")
        return 1
    try:
        provenance = guard.probe_app(snapshot)
    except guard.GuardError as exc:
        print(f"[FAIL] {exc}")
        return 1
    if snapshot.resolve() not in Path(provenance).resolve().parents:   # 解析 Path 判定，不用 startswith
        print(f"[FAIL] 来源不在快照内：{provenance}")
        return 1
    manifest_file.write_text("\n".join(snap_lines) + "\n", encoding="utf-8")
    guard.write_pointer(pointer, run_id)
    print(json.dumps({
        "run_id": run_id, "snapshot": str(snapshot), "files": len(snap_lines),
        "tree_hash": snap_hash, "live_unchanged": live_before == live_after,
        "provenance": provenance, "manifest": str(manifest_file),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
