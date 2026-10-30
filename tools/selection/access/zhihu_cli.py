"""Thin alias so both entry points work: module and script path.

The real implementation is `tools.selection.access.zhihu`.
"""

from __future__ import annotations

import pathlib
import sys

if __package__ in (None, ""):  # `python tools/selection/access/zhihu_cli.py`
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3]))

from tools.selection.access.zhihu import build_parser, main  # noqa: E402,F401

__all__ = ["build_parser", "main"]

if __name__ == "__main__":
    sys.exit(main())
