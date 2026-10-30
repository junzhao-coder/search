"""三入口 CLI 负例（单表逐案：before → run → after → assert；自身 scope）。

- 镜像保留完整子树（含 app/docs/tests），入口脚本与源逐字节一致 → ROOT/批准根语义与真实一致。
- 坏 root/pointer 目标用**镜像内、ACC 之外**的合成目录，绝不触碰真实工作树。
- 每案断言：exit≠0 + 提示关键字 + 镜像整树零变化（不排除 _tmp）。
- 合法首次冻结与重复拒绝分两个独立窗口。
- 结果写 UTF-8 的 guard_cases.json / guard_cases.log。

用法：& .\\.venv\\Scripts\\python.exe -X utf8 tests\\acceptance\\run_guard_negatives.py
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import socket
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _guard as guard  # noqa: E402

ACC = Path(__file__).resolve().parent
ROOT = ACC.parents[1]
ATTEMPTS = ACC / "_tmp" / "attempts"
ENTRANCES = ["_guard.py", "freeze_snapshot.py", "run_s2_acceptance.py", "run_s2_attempt.py"]
results: list[dict] = []


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def state(root: Path) -> dict:
    """文件哈希 + 目录标记（目录标记用于断言“非法输入不新建空目录”）。"""
    acc = {}
    for path in sorted(root.rglob("*")):
        if "__pycache__" in path.parts:
            continue
        rel = str(path.relative_to(root)).replace("\\", "/")
        if path.is_dir():
            acc[rel + "/"] = "DIR"
        elif path.is_file():
            acc[rel] = sha(path)
    return acc


def diff(before: dict, after: dict) -> list[str]:
    return sorted(k for k in set(before) | set(after) if before.get(k) != after.get(k))


def check(cid: str, ok: bool, detail: str) -> None:
    results.append({"id": cid, "ok": bool(ok), "detail": detail})
    print(f"[{'PASS' if ok else 'FAIL'}] {cid}: {detail}", flush=True)


def run(script: Path, argv: list[str], env_extra: dict, drop: tuple[str, ...] = ()) -> subprocess.CompletedProcess:
    env = {k: v for k, v in os.environ.items() if k not in drop}
    env.update({"PYTHONUTF8": "1", "PYTHONDONTWRITEBYTECODE": "1", **env_extra})
    return subprocess.run([sys.executable, "-X", "utf8", str(script), *argv], cwd=str(ROOT),
                          capture_output=True, text=True, encoding="utf-8", errors="replace", env=env, timeout=240)


def main() -> int:
    attempt = guard.attempt_dir(ATTEMPTS, guard.new_attempt_name("guard"))
    mirror = attempt / "mirror"
    source_snap = ACC / "_snapshots" / os.environ.get("S2D_MIRROR_SOURCE", "s2d_20261013_fix1")
    for rel in ("app", "docs/design", "tests/core", "tests/storage", "tests/api", "tests/ui",
                "requirements.txt", "tests/__init__.py"):
        src = source_snap / rel
        if src.exists():
            dst = mirror / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(src, dst) if src.is_dir() else shutil.copy2(src, dst)
    scripts = mirror / "tests" / "acceptance"
    scripts.mkdir(parents=True, exist_ok=True)
    for name in ENTRANCES:                                 # 先复制，再逐个真比 digest（copy2 返回路径不能当布尔用）
        shutil.copy2(ACC / name, scripts / name)
    digests = {name: (sha(ACC / name), sha(scripts / name)) for name in ENTRANCES}
    mirror_ok = all(src == dst for src, dst in digests.values())
    check("MIRROR-HASH", mirror_ok,
          f"镜像保留完整子树（镜像 ROOT={mirror}），源快照={source_snap.name}；4 个精确哈希="
          f"{ {n: d[1][:12] for n, d in digests.items()} }；不符即在此退出、不执行任何镜像用例")
    if not mirror_ok:
        (attempt / "guard_cases.json").write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
        return 1
    probe_file = scripts / "run_s2_attempt.py"             # 自证：篡改后该比对必须失败，还原后必须一致
    original = probe_file.read_bytes()
    probe_file.write_bytes(original + b"\n# tamper\n")
    detects = sha(probe_file) != sha(ACC / "run_s2_attempt.py")
    probe_file.write_bytes(original)
    restored = sha(probe_file) == sha(ACC / "run_s2_attempt.py")
    check("MIRROR-HASH-SELFTEST", detects and restored,
          f"expected 篡改检测=True 且还原后一致=True；actual detects={detects} restored={restored}")

    # 哨兵与合成越界目标：全部在镜像内、ACC（tests/acceptance）之外
    sentinel = scripts / "_tmp" / "guard_snapshots"
    sentinel.mkdir(parents=True)
    snap = sentinel / "snapA"
    (snap / "app").mkdir(parents=True)
    (snap / "app" / "__init__.py").write_text("", encoding="utf-8")
    digest = sha(snap / "app" / "__init__.py")
    for extra in ("snapEmpty", "snapDup", "snapOut"):
        (sentinel / extra / "app").mkdir(parents=True)
        (sentinel / extra / "app" / "__init__.py").write_text("", encoding="utf-8")
    (sentinel / "snapA.manifest.sha256").write_text(f"{digest}  app/__init__.py\n", encoding="utf-8")
    (sentinel / "snapEmpty.manifest.sha256").write_text("", encoding="utf-8")
    (sentinel / "snapDup.manifest.sha256").write_text(
        f"{digest}  app/__init__.py\n{digest}  app/__init__.py\n", encoding="utf-8")
    (sentinel / "snapOut.manifest.sha256").write_text(f"{digest}  ../../instance/app.db\n", encoding="utf-8")
    bad_pointer = sentinel / "bad_pointer.txt"
    bad_pointer.write_text("../evil\n", encoding="utf-8")
    outside = mirror / "outside_acc"                      # 镜像内、ACC 之外（批准根之外）的合成目标
    (outside / "snaps").mkdir(parents=True)
    (outside / "p.txt").write_text("x\n", encoding="utf-8")
    busy_port = 5299

    base = {"S2D_SNAPSHOT_ROOT": str(sentinel), "S2D_POINTER": str(sentinel / "pointer.txt")}
    freeze, acceptance, attempt_cli = (scripts / "freeze_snapshot.py", scripts / "run_s2_acceptance.py",
                                       scripts / "run_s2_attempt.py")

    # 窗口 1：合法首次冻结（哨兵根下只应新增该快照/清单/指针）
    before = state(mirror)
    legal = run(freeze, ["guard_legal"], base)
    added = diff(before, state(mirror))
    check("WINDOW1-legal-freeze", legal.returncode == 0 and bool(added)
          and all(a.startswith("tests/acceptance/_tmp/guard_snapshots/") for a in added),
          f"expected exit=0 且新增仅限哨兵根（实际相对路径前缀 tests/acceptance/_tmp/guard_snapshots/）；"
          f"actual exit={legal.returncode} 新增={added[:3]}（共 {len(added)}）")

    # 窗口 2：重复拒绝（窗口 1 之后状态必须逐字节不变）
    before = state(mirror)
    dup = run(freeze, ["guard_legal"], base)
    check("WINDOW2-duplicate-reject", dup.returncode != 0 and "已存在" in (dup.stdout + dup.stderr)
          and not diff(before, state(mirror)),
          f"expected exit≠0「已存在」且零变化；actual exit={dup.returncode}")

    table = [
        ("CLI-illegal-id-separator", freeze, ["a/b"], base, (), "非法 RUN_ID"),
        ("CLI-illegal-id-absolute", freeze, [str(outside / "evil")], base, (), "非法 RUN_ID"),
        ("CLI-acceptance-root-out-of-scope", acceptance, [],
         {**base, "S2D_SNAPSHOT_ROOT": str(outside / "snaps")}, (), "越出"),
        ("CLI-freeze-root-out-of-scope", freeze, ["guard_badroot"],
         {**base, "S2D_SNAPSHOT_ROOT": str(outside / "snaps")}, (), "越出"),
        ("CLI-freeze-pointer-out-of-scope", freeze, ["guard_badptr"],
         {**base, "S2D_POINTER": str(outside / "p.txt")}, (), "越出"),
        ("CLI-illegal-pointer", acceptance, [],
         {**base, "S2D_POINTER": str(bad_pointer)}, ("S2D_SNAPSHOT_ID",), "非法 RUN_ID"),
        ("CLI-manifest-empty", acceptance, [], {**base, "S2D_SNAPSHOT_ID": "snapEmpty"}, (), "清单为空"),
        ("CLI-manifest-duplicate", acceptance, [], {**base, "S2D_SNAPSHOT_ID": "snapDup"}, (), "重复条目"),
        ("CLI-manifest-out-of-root", acceptance, [], {**base, "S2D_SNAPSHOT_ID": "snapOut"}, (), "越界"),
        ("CLI-attempt-illegal-id", attempt_cli, [], {**base, "S2D_RUN_ID": "a/b"}, (), "非法 RUN_ID"),
        ("CLI-attempt-root-out-of-scope", attempt_cli, [],
         {**base, "S2D_SNAPSHOT_ROOT": str(outside / "snaps"), "S2D_RUN_ID": "guard_ok"}, (), "越出"),
        ("CLI-attempt-pointer-out-of-scope", attempt_cli, [],
         {**base, "S2D_POINTER": str(outside / "p2.txt"), "S2D_RUN_ID": "guard_ok"}, ("S2D_SNAPSHOT_ID",), "越出"),
    ]
    with socket.socket() as hold:                          # 占用端口在两案执行期间保持
        hold.bind(("127.0.0.1", busy_port))
        hold.listen(1)
        table += [
            ("CLI-acceptance-port-busy", acceptance, [],
             {**base, "S2D_SNAPSHOT_ID": "snapA", "S2D_PORT": str(busy_port)}, (), "被占用"),
            ("CLI-attempt-port-busy", attempt_cli, [],
             {**base, "S2D_SNAPSHOT_ID": "snapA", "S2D_RUN_ID": "guard_ok", "S2D_ATTEMPT_PORT": str(busy_port)}, (),
             "被占用"),
        ]
        for cid, script, argv, env_extra, drop, keyword in table:
            before = state(mirror)
            proc = run(script, argv, env_extra, drop=drop)
            changed = diff(before, state(mirror))
            out = proc.stdout + proc.stderr
            check(cid, proc.returncode != 0 and keyword in out and not changed,
                  f"expected exit≠0 + 含「{keyword}」+ 镜像整树零变化；actual exit={proc.returncode} "
                  f"变化={changed[:3]} 末行={out.strip().splitlines()[-1][:80] if out.strip() else ''}")

    (attempt / "guard_cases.json").write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    (attempt / "guard_cases.log").write_text(
        "\n".join(f"[{'PASS' if r['ok'] else 'FAIL'}] {r['id']}: {r['detail']}" for r in results) + "\n", encoding="utf-8")
    fails = [r["id"] for r in results if not r["ok"]]
    print(f"合计 {len(results)} 项：PASS {sum(1 for r in results if r['ok'])} / FAIL {len(fails)}；"
          f"证据={attempt.name}/guard_cases.json", flush=True)
    return 0 if not fails else 1


if __name__ == "__main__":
    sys.exit(main())
