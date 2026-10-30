"""Routes for the read-only dashboard."""

from __future__ import annotations

from flask import current_app, redirect, render_template, url_for

from . import bp
from .data import load_dashboard_data

NAV = [
    ("overview", "总览", "dash.index"),
    ("collect", "采集", "dash.collect"),
    ("opportunities", "机会", "dash.opportunities"),
    ("sources", "货源", "dash.sources"),
    ("daily", "每日摘要", "dash.daily"),
]


def _data():
    root = current_app.config.get("DASH_DATA_ROOT")
    return load_dashboard_data(root)


def _context(active: str, data: dict) -> dict:
    return {
        "active": active,
        "nav": NAV,
        "generated_at": data["generated_at"],
        "warnings": data["warnings"],
        "datasets": data["datasets"],
        "counts": data["counts"],
    }


@bp.get("")
def dash_root():
    return redirect(url_for("dash.index"))


@bp.get("/")
def index():
    data = _data()
    return render_template("dash/index.html", **_context("overview", data),
                           scores=data["scores"][:5], sources=data["sources"][:5],
                           join=data["join"][:5], price_stats=data["price_stats"],
                           verdicts=data["license_verdicts"], top20=data["top20"])


@bp.get("/collect")
def collect():
    data = _data()
    return render_template("dash/collect.html", **_context("collect", data),
                           xianyu=data["xianyu"][:12], xiaohongshu=data["xiaohongshu"][:12],
                           top20=data["top20"][:20], topic_summary=data["topic_summary"])


@bp.get("/opportunities")
def opportunities():
    data = _data()
    return render_template("dash/opportunities.html", **_context("opportunities", data),
                           scores=data["scores"])


@bp.get("/sources")
def sources():
    data = _data()
    return render_template("dash/sources.html", **_context("sources", data),
                           sources=data["sources"], prices=data["prices"], join=data["join"],
                           verdicts=data["license_verdicts"], price_stats=data["price_stats"])


@bp.get("/daily")
def daily():
    data = _data()
    return render_template("dash/daily.html", **_context("daily", data),
                           scores=data["scores"][:5], sources=data["sources"],
                           join=data["join"][:5], price_stats=data["price_stats"],
                           verdicts=data["license_verdicts"])
