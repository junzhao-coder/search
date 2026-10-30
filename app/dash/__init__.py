"""Read-only /dash blueprint: four work pages plus overview."""

from __future__ import annotations

import pathlib

from flask import Blueprint, redirect, url_for

ROOT = pathlib.Path(__file__).resolve().parents[2]
bp = Blueprint("dash", __name__, url_prefix="/dash",
               template_folder=str(ROOT / "templates"))

from . import routes  # noqa: E402,F401

__all__ = ["bp"]
