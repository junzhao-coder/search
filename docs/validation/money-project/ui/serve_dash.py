"""Local dashboard server for screenshots (temp DB, read-only data files)."""

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))

from app import create_app  # noqa: E402

TMP = pathlib.Path(__file__).resolve().parent / "tmp"
TMP.mkdir(parents=True, exist_ok=True)
app = create_app({"db_path": str(TMP / "server.db")})

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5010, debug=False, use_reloader=False)
