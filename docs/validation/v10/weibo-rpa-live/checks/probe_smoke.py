"""probe 的离线端到端冒烟：本地 fixture + **真实 Chrome** + 封网，走完 `cli.main`。

为什么必须有这一步：上一轮 `cmd_probe` 调了当时不存在的 `session.html`，静态断言只查源码
字符串抓不到；这条冒烟会在**花真实额度之前**把同样的 AttributeError 抓出来。

做法：
- 真实 `VisibleSession(live=False)`（local 模式：DNS 全不解析 + CDP 封 http/https/ws/wss）；
- 把 `open_live()` 重定向到 `open_local(fixture)`，其余（start/desktop_proof/wait_ready/html）全是真代码；
- stub 账本只实现 precheck/charge/record_result/lock，不碰真实账本；
- 跑 `cli.main(["probe", "--url", fixture, "--batch-id", "smoke"])`，断言：
  exit=0、10 个 counts ≥1、stdout 不含正文标记、`requested_url` 存在。

用法：
    C:\\Users\\19183\\.dsh\\tools\\x-collect\\venv\\Scripts\\python.exe -X utf8 `
      docs\\validation\\v10\\weibo-rpa-live\\checks\\probe_smoke.py
产物：`logs/probe-smoke.json`（含完整 stdout）；失败非零。
"""

from __future__ import annotations

import contextlib
import datetime as dt
import io
import json
import pathlib
import sys
import tempfile

REPO = pathlib.Path(__file__).resolve().parents[5]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from tools.selection.rpa import cli, session  # noqa: E402

HERE = pathlib.Path(__file__).resolve().parents[1]
FIXTURE = HERE / "checks" / "fixtures" / "probe-all.html"
OUT = HERE / "logs" / "probe-smoke.json"
BODY_MARKER = "正文标记-不应出现在输出里"
COUNT_KEYS = ("card_wrap", "card", "p_txt", "a_name", "div_from", "card_act",
              "status_links", "s_weibo_links", "img_avator", "card_comment")


class _StubLedger:
    """只满足 cmd_probe 的调用面；绝不写真实账本。"""

    def locked(self):
        return False, None

    def summary(self, batch_id=None):
        return {"batch_id": batch_id, "authorized": True, "remaining": 1,
                "used": 2, "authorized_calls": 3, "seed_used": 2,
                "window_open": True, "records_reserved": 0, "locked": False}

    def charge(self, batch_id, kind, *, detail="", source="runtime"):
        return {"batch_id": batch_id, "kind": kind}

    def record_result(self, batch_id, kind, outcome, *, detail="", source="runtime"):
        return None

    def audit(self, batch_id, kind, *, detail="", source="runtime"):
        """`guard.record_result` 实际写的是 `audit()`；stub 必须实现。"""
        return None

    def lock(self, reason, *, source="unknown"):
        return None

    def close(self):
        return None


class _LocalSession(session.VisibleSession):
    """真实会话，只把 open_live 指到本地 fixture（local 模式，封网）。"""

    def __init__(self, fixture_uri: str, **kwargs):
        super().__init__(**kwargs)
        self._fixture_uri = fixture_uri
        self.opened: list[str] = []

    def open_live(self, url):                      # noqa: D401 - 冒烟专用重定向
        self.opened.append(url)
        tab, _blocked = self.open_local(self._fixture_uri)
        return tab


def main() -> int:
    if not FIXTURE.is_file():
        print(json.dumps({"error": "fixture_missing", "path": str(FIXTURE)}))
        return 2
    profile = pathlib.Path(tempfile.mkdtemp(prefix="rpa-probe-smoke-"))
    fixture_uri = FIXTURE.as_uri()
    created: list[_LocalSession] = []

    def _factory(profile_arg, *, live, timeout=None, user_agent=None):
        sess = _LocalSession(fixture_uri, profile=profile, live=False, timeout=timeout or 60.0)
        created.append(sess)
        return sess

    buf = io.StringIO()
    original_ledger, original_factory = cli._open_ledger, cli._new_session
    cli._open_ledger = lambda: _StubLedger()
    cli._new_session = _factory
    try:
        with contextlib.redirect_stdout(buf):
            code = cli.main(["probe", "--url", fixture_uri, "--batch-id", "smoke",
                             "--out", str(HERE / "logs" / "probe-smoke-summary.json")])
    finally:
        cli._open_ledger, cli._new_session = original_ledger, original_factory

    raw = buf.getvalue().strip()
    payload = {}
    for line in reversed(raw.splitlines()):
        line = line.strip()
        if line.startswith("{"):
            try:
                payload = json.loads(line)
                break
            except ValueError:
                continue
    summary = payload.get("summary") or {}
    counts = summary.get("counts") or {}
    checks = []

    def record(name: str, passed: bool, detail="") -> None:
        checks.append({"check": name, "pass": bool(passed), "detail": detail})

    record("exit_zero", code == 0, str(code))
    missing = [key for key in COUNT_KEYS if int(counts.get(key) or 0) < 1]
    record("all_ten_selectors_hit", not missing, json.dumps(counts, ensure_ascii=False))
    record("no_body_text_in_stdout", BODY_MARKER not in raw, "")
    record("requested_url_present", bool(payload.get("requested_url")),
           str(payload.get("requested_url")))
    record("html_fetch_used", bool(summary.get("text_len")), str(summary.get("text_len")))

    all_pass = all(c["pass"] for c in checks)
    out = {"generated_utc": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
           "all_pass": all_pass, "checks": checks, "exit": code,
           "requested_url": payload.get("requested_url"),
           "final_url": payload.get("final_url"),
           "summary": summary, "stdout": raw}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({"all_pass": all_pass,
                      "failed": [c for c in checks if not c["pass"]],
                      "exit": code, "counts": counts,
                      "requested_url": payload.get("requested_url"),
                      "final_url": payload.get("final_url"),
                      "out": str(OUT)}, ensure_ascii=False))
    return 0 if all_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
