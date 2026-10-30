"""Read-only environment/dependency probe for the two DSH tool environments.

Usage: python dep_probe.py <env-label>
Prints JSON: python version/executable, metadata versions, module paths, PEP610 direct_url,
site-packages, and whether the module import succeeds. Does NOT install/upgrade anything.
"""

from __future__ import annotations

import importlib
import importlib.metadata as md
import json
import pathlib
import platform
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:  # pragma: no cover
    pass


def dist_info(name: str) -> dict:
    try:
        dist = md.distribution(name)
    except md.PackageNotFoundError:
        return {"installed": False}
    info = {"installed": True, "version": dist.version}
    try:
        info["direct_url"] = json.loads(dist.read_text("direct_url.json") or "null")
    except Exception as exc:  # noqa: BLE001
        info["direct_url_error"] = f"{type(exc).__name__}: {exc}"
    try:
        files = list(dist.files or [])
        info["file_count"] = len(files)
        info["location"] = str(dist.locate_file(""))
    except Exception as exc:  # noqa: BLE001
        info["location_error"] = f"{type(exc).__name__}: {exc}"
    return info


def module_info(name: str) -> dict:
    try:
        module = importlib.import_module(name)
    except Exception as exc:  # noqa: BLE001
        return {"imported": False, "error": f"{type(exc).__name__}: {exc}"}
    return {"imported": True, "file": str(pathlib.Path(getattr(module, "__file__", "")).resolve()),
            "version_attr": getattr(module, "__version__", None)}


def main() -> int:
    label = sys.argv[1] if len(sys.argv) > 1 else "env"
    distributions = ["agent-reach", "stealth-browser-mcp", "fastmcp", "nodriver", "mcp", "pydantic",
                     "flask", "requests"]
    modules = ["agent_reach"] if label == "agent-reach" else ["fastmcp", "nodriver", "mcp", "server"]
    payload = {
        "label": label,
        "python": {"version": platform.python_version(), "executable": sys.executable,
                   "prefix": sys.prefix, "base_prefix": sys.base_prefix,
                   "in_venv": sys.prefix != sys.base_prefix},
        "platform": platform.platform(),
        "distributions": {name: dist_info(name) for name in distributions},
        "modules": {name: module_info(name) for name in modules},
        "sys_path": [path for path in sys.path if path],
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
