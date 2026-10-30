"""Run the local app: ``.venv/Scripts/python -m app`` (127.0.0.1 only, no debug/reload)."""

from __future__ import annotations

from . import create_app
from .core.config import load_config


def main() -> None:
    cfg = load_config()
    app = create_app(cfg)
    app.run(
        host=cfg["host"],
        port=cfg["port"],
        debug=False,
        use_reloader=False,
        threaded=True,
    )


if __name__ == "__main__":
    main()
