"""D 槽位复跑工具共用的守卫实现（单一来源，freeze/acceptance/attempt 共用）。

批准根固定在本 workspace 的 tests/acceptance：
- 快照根默认 tests/acceptance/_snapshots；env 覆盖（S2D_SNAPSHOT_ROOT）只允许落在
  tests/acceptance/_tmp 之下（隔离哨兵），否则拒绝——env 不能扩批准根。
- RUN_ID 必须是单段安全名（[A-Za-z0-9_-]{1,48}）；拒绝绝对路径、路径分隔符与 `..`；
  解析后（含既有链接）必须正好落在批准根的下一层。
- 目录一律独占创建；工具不删除、不覆盖既有快照/DB/日志。
"""

from __future__ import annotations

import hashlib
import os
import random
import re
import socket
import string
import subprocess
import sys
import time
from pathlib import Path

ACC_ROOT = Path(__file__).resolve().parent          # 固定批准根：tests/acceptance
TMP_ROOT = ACC_ROOT / "_tmp"
SAFE_ID = re.compile(r"^[A-Za-z0-9_-]{1,48}$")
INCLUDE_DIRS = ["app", "tests/core", "tests/storage", "tests/api", "tests/ui"]
INCLUDE_FILES = [
    "requirements.txt",
    "tests/__init__.py",
    "docs/design/CONTRACT.md",
    "docs/design/ACCEPTANCE.md",
    "docs/design/S2_CORE.md",
    "docs/design/S2_RUNTIME.md",
]
EXCLUDE_PARTS = {"__pycache__", "_tmp", ".venv", "instance", "_snapshots", ".pytest_cache"}


class GuardError(Exception):
    """守卫拒绝（非法名称/越界路径/清单不符/已存在），调用方应非零退出。"""


def safe_id(value: str) -> str:
    """校验并返回**规范化**后的单段安全名（调用方必须使用返回值拼接）。"""
    text = (value or "").strip()
    if (not SAFE_ID.fullmatch(text) or os.path.isabs(text) or "/" in text or "\\" in text
            or ".." in text or text != Path(text).name):
        raise GuardError(
            f"非法 RUN_ID：{value!r}（只允许单段 [A-Za-z0-9_-]{{1,48}}；禁止绝对路径/路径分隔符/..）")
    return text


def resolve_under(root: Path, name: str) -> Path:
    """批准根下一层目录；用 safe_id 的规范化返回值拼接，解析后（含链接）再核对。"""
    normalized = safe_id(name)
    approved = root.resolve()
    target = (root / normalized).resolve()
    if target.parent != approved:
        raise GuardError(f"解析后路径越出批准根：{target}（批准根={approved}）")
    return target


def _approved_override(value: str | None, default: Path) -> Path:
    if not value:
        return default
    candidate = Path(value).resolve()
    if candidate != TMP_ROOT.resolve() and TMP_ROOT.resolve() not in candidate.parents:
        raise GuardError(f"env 覆盖越出隔离区（只允许 tests/acceptance/_tmp 之下）：{candidate}")
    return candidate


def snapshot_root() -> Path:
    root = _approved_override(os.environ.get("S2D_SNAPSHOT_ROOT"), ACC_ROOT / "_snapshots").resolve()
    if root != ACC_ROOT.resolve() and ACC_ROOT.resolve() not in root.parents:
        raise GuardError(f"快照根解析后越出批准根：{root}（批准根={ACC_ROOT.resolve()}，含链接同样核对）")
    return root


def pointer_path() -> Path:
    path = _approved_override(os.environ.get("S2D_POINTER"), TMP_ROOT / "attempts" / "CURRENT_SNAPSHOT.txt").resolve()
    if TMP_ROOT.resolve() not in path.parents:
        raise GuardError(f"pointer 解析后越出隔离区：{path}（只允许 tests/acceptance/_tmp 之下，含链接同样核对）")
    return path


def exclusive_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=False)  # 已存在 → FileExistsError，绝不覆盖
    return path


def new_attempt_name(prefix: str = "attempt") -> str:
    return f"{prefix}_" + time.strftime("%Y%m%d_%H%M%S") + "_" + "".join(
        random.choice(string.ascii_lowercase + string.digits) for _ in range(4))


def attempt_dir(root: Path, name: str | None = None) -> Path:
    return exclusive_dir(resolve_under(root, name or new_attempt_name()))


def collect(root: Path) -> list[str]:
    rels: set[str] = set()
    for rel_dir in INCLUDE_DIRS:
        base = root / rel_dir
        if not base.exists():
            continue
        for path in base.rglob("*"):
            if path.is_file() and not (set(path.relative_to(root).parts) & EXCLUDE_PARTS):
                rels.add(str(path.relative_to(root)).replace("\\", "/"))
    for rel_file in INCLUDE_FILES:
        if (root / rel_file).exists():
            rels.add(rel_file)
    return sorted(rels)


def manifest(root: Path, rels: list[str] | None = None) -> tuple[list[str], str]:
    lines = []
    for rel in (rels if rels is not None else collect(root)):
        digest = hashlib.sha256((root / rel).read_bytes()).hexdigest()
        lines.append(f"{digest}  {rel}")
    return lines, hashlib.sha256("\n".join(lines).encode("utf-8")).hexdigest()


def port_free(port: int) -> bool:
    """独占 bind 探测端口是否可用（不用 connect 语义）。

    connect_ex 在「监听方 backlog 已满」时会超时返回非 0，从而把已占用端口误判为空闲；
    改为尝试独占绑定：能绑上才算空闲。Windows 使用 SO_EXCLUSIVEADDRUSE（不设 REUSE），
    因此他人已绑定/监听时必定失败；本函数只探测，不结束任何进程。
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        exclusive = getattr(socket, "SO_EXCLUSIVEADDRUSE", None)
        if exclusive is not None:
            try:
                sock.setsockopt(socket.SOL_SOCKET, exclusive, 1)
            except OSError:
                pass
        try:
            sock.bind(("127.0.0.1", port))
        except OSError:
            return False
        return True


def read_pointer(path: Path) -> str:
    if not path.exists():
        raise GuardError(f"指针文件不存在：{path}（先运行 freeze_snapshot.py）")
    return safe_id(path.read_text(encoding="utf-8"))


def write_pointer(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(safe_id(value) + "\n", encoding="utf-8")


def probe_app(snapshot: Path) -> str:
    env = {**os.environ, "PYTHONPATH": "", "PYTHONUTF8": "1", "PYTHONDONTWRITEBYTECODE": "1"}
    proc = subprocess.run([sys.executable, "-c", "import app;print(app.__file__)"], cwd=str(snapshot),
                          capture_output=True, text=True, errors="replace", env=env)
    if proc.returncode != 0:
        raise GuardError(f"来源探针失败（exit={proc.returncode}）：{proc.stderr.strip()[:160]}")
    return proc.stdout.strip()


def preflight(snapshot: Path, manifest_file: Path) -> str:
    """清单完整一致 + 来源合法；任何问题抛 GuardError（调用方据此非零退出）。"""
    if not snapshot.is_dir():
        raise GuardError(f"快照目录不存在：{snapshot}")
    if not manifest_file.exists():
        raise GuardError(f"清单文件不存在：{manifest_file}")
    lines = [l for l in manifest_file.read_text(encoding="utf-8").splitlines() if l.strip()]
    if not lines:
        raise GuardError(f"清单为空：{manifest_file}")
    entries: dict[str, str] = {}
    for line in lines:
        digest, rel = line.split("  ", 1)
        pure = Path(rel)
        if pure.is_absolute() or ".." in pure.parts:
            raise GuardError(f"清单含越界/绝对路径：{rel}")
        if rel in entries:                                    # 重复条目必须拒绝（不静默覆盖）
            raise GuardError(f"清单含重复条目：{rel}（条目数 {len(lines)}，唯一 {len(entries)}）")
        entries[rel] = digest
    actual = set(collect(snapshot))
    if set(entries) != actual:
        raise GuardError(f"清单条目与快照实际文件集合不一致："
                         f"仅清单有={sorted(set(entries) - actual)[:3]} 仅快照有={sorted(actual - set(entries))[:3]}")
    snap_resolved = snapshot.resolve()
    for rel, digest in entries.items():
        target = (snapshot / rel).resolve()                   # 逐文件 resolve 后仍须在 snapshot 内
        if snap_resolved not in target.parents:
            raise GuardError(f"清单条目解析后越出快照：{rel} -> {target}")
        if not target.is_file():
            raise GuardError(f"清单条目不是文件：{rel}")
        if hashlib.sha256(target.read_bytes()).hexdigest() != digest:
            raise GuardError(f"清单哈希不符：{rel}")
    provenance = probe_app(snapshot)
    prov_path = Path(provenance).resolve()
    if snap_resolved not in prov_path.parents:              # 用解析后的 Path 判断，不用字符串前缀
        raise GuardError(f"来源不在快照内：{provenance}（快照={snap_resolved}）")
    return provenance
