"""Minimal Flask entry point (S2-B1).

Stdlib-first: sqlite3, csv, json, decimal, hashlib, uuid, unittest.
The only third-party import is Flask itself.
"""

from __future__ import annotations

from flask import Flask, jsonify

from . import api
from .core.config import load_config
from .core.errors import AppError
from .storage import db as db_module


def create_app(overrides: dict | None = None) -> Flask:
    cfg = load_config(overrides)
    app = Flask(__name__)
    app.config["APP_CFG"] = cfg
    # Request size bound (contract: request/field/text boundary validation).
    app.config["MAX_CONTENT_LENGTH"] = cfg["max_body_bytes"]
    app.json.ensure_ascii = False

    db_module.ensure_schema(cfg["db_path"])
    db_module.init_app(app)
    app.register_blueprint(api.bp)
    app.register_blueprint(api.pages)
    _register_error_handlers(app)
    return app


def _register_error_handlers(app: Flask) -> None:
    @app.errorhandler(AppError)
    def _app_error(err: AppError):
        return (
            jsonify({"error": {"code": err.code, "message": err.message, "details": err.details}}),
            err.status,
        )

    @app.errorhandler(404)
    def _not_found(_err):
        return jsonify({"error": {"code": "not_found", "message": "路径不存在", "details": []}}), 404

    @app.errorhandler(405)
    def _method_not_allowed(_err):
        return (
            jsonify({"error": {"code": "invalid_state", "message": "方法不允许", "details": []}}),
            405,
        )

    @app.errorhandler(413)
    def _too_large(_err):
        return (
            jsonify(
                {
                    "error": {
                        "code": "validation_failed",
                        "message": "请求体超过允许大小",
                        "details": [{"field": "body", "reason": "超出 APP_MAX_BODY_BYTES"}],
                    }
                }
            ),
            413,
        )

    @app.errorhandler(Exception)
    def _unhandled(err: Exception):  # pragma: no cover - defensive
        return (
            jsonify(
                {
                    "error": {
                        "code": "internal_error",
                        "message": f"内部错误：{type(err).__name__}",
                        "details": [],
                    }
                }
            ),
            500,
        )
