"""只读 cookie **元数据**（名称/主机/时间戳/是否持久），绝不读取或打印值。

用于回答"weibo-rpa-4 的登录是否落地"：如果 SUB/SUBP/SSOLoginState 的
`creation_utc` 落在登录窗口内，说明这些会话 cookie 是那次登录写入的。

用法：
    C:\\Users\\19183\\.dsh\\tools\\x-collect\\venv\\Scripts\\python.exe -X utf8 `
      docs\\validation\\v10\\weibo-rpa-live\\checks\\cookie_metadata.py
输出：同目录上一级 `logs/cookie-metadata.log`（JSON 行）。
"""

from __future__ import annotations

import datetime as dt
import json
import pathlib
import sqlite3

PROFILE = pathlib.Path(r"C:\Users\19183\.dsh\tools\weibo-collect\profile")
DB = PROFILE / "Default" / "Network" / "Cookies"
OUT = pathlib.Path(__file__).resolve().parents[1] / "logs" / "cookie-metadata.log"
EPOCH = dt.datetime(1601, 1, 1, tzinfo=dt.timezone.utc)


def _t(microseconds) -> str | None:
    try:
        return (EPOCH + dt.timedelta(microseconds=int(microseconds))).strftime(
            "%Y-%m-%dT%H:%M:%SZ")
    except (TypeError, ValueError, OverflowError):
        return None


def main() -> int:
    if not DB.is_file():
        print(json.dumps({"error": "cookie_db_missing", "path": str(DB)}))
        return 2
    con = sqlite3.connect(DB.as_uri() + "?mode=ro&immutable=1", uri=True, timeout=5.0)
    con.row_factory = sqlite3.Row
    try:
        rows = con.execute(
            "SELECT name, host_key, creation_utc, last_access_utc, expires_utc,"
            " is_persistent FROM cookies WHERE host_key LIKE '%weibo%'"
            " ORDER BY creation_utc DESC").fetchall()
    finally:
        con.close()
    out = [{"name": r["name"], "host": r["host_key"],
            "created_utc": _t(r["creation_utc"]),
            "last_access_utc": _t(r["last_access_utc"]),
            "expires_utc": _t(r["expires_utc"]),
            "persistent": bool(r["is_persistent"])} for r in rows]
    payload = {"profile": str(PROFILE), "profile_exists": PROFILE.is_dir(),
               "cookie_db": str(DB), "cookie_count": len(out),
               "values_read": False, "cookies": out}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({"cookie_count": len(out), "values_read": False,
                      "cookies": [{k: c[k] for k in ("name", "host", "created_utc")}
                                  for c in out]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
