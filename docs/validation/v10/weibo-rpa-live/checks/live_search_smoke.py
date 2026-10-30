"""live-search 的离线端到端自检：本地 fixture + 真实 Chrome（local 模式、封网）。

作用：在动真实账本之前，确认 `live-search` 全链路（argv→守卫→扣费→导航→桌面证据/标题闸门→
wait_ready→风险→`dump_desktop_cards`→extract→reserve→settle）能在桌面结构上产出记录。

断言：exit=0、records 数正确、`records_detail` 非空且含 id_source/author/text_len/互动、
`rejected` 分类正确（foreign_host / bad_id）、`requested_url` 存在、正文不含导航文字。

用法：
    C:\\Users\\19183\\.dsh\\tools\\x-collect\\venv\\Scripts\\python.exe -X utf8 `
      docs\\validation\\v10\\weibo-rpa-live\\checks\\live_search_smoke.py
产物：`logs/live-search-smoke.json`；失败非零。
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
FIXTURE = HERE / "checks" / "fixtures" / "desktop-cards.html"
OUT = HERE / "logs" / "live-search-smoke.json"
NAV_MARKERS = ("首页", "登录")


class _StubLedger:
    def __init__(self):
        self.calls = []

    def locked(self):
        return False, None

    def summary(self, batch_id=None):
        return {"batch_id": batch_id, "authorized": True, "remaining": 1, "used": 2,
                "authorized_calls": 3, "seed_used": 2, "window_open": True,
                "records_reserved": 0, "locked": False}

    def charge(self, batch_id, kind, *, detail="", source="runtime"):
        self.calls.append(("charge", kind))
        return {"batch_id": batch_id, "kind": kind}

    def reserve_records(self, batch_id, count, *, source="runtime"):
        self.calls.append(("reserve", count))
        return {"batch_id": batch_id, "reserved": count}

    def audit(self, batch_id, kind, *, detail="", source="runtime"):
        self.calls.append(("audit", kind, detail))
        return None

    def lock(self, reason, *, source="unknown"):
        self.calls.append(("lock", reason))
        return None

    def close(self):
        return None


class _FakeKeepalive:
    def __init__(self, hwnd, **kwargs):
        self.hwnd = hwnd

    def start(self):
        return {"topmost_set": True, "hwnd": self.hwnd}

    def tick(self, *, force=False):
        return None

    def finish(self):
        return {"ticks": 1, "reassert_count": 0, "reassert_failures": 0,
                "still_foreground_at_end": True, "topmost_cleared": True}


class _LocalLiveSession(session.VisibleSession):
    """真实会话（local 模式、封网），只把 open_live 指到桌面版 fixture。"""

    def __init__(self, fixture_uri: str, **kwargs):
        super().__init__(**kwargs)
        self._fixture_uri = fixture_uri
        self.opened: list[str] = []

    def open_live(self, url):
        self.opened.append(url)
        tab, _blocked = self.open_local(self._fixture_uri)
        return tab

    def wait_ready(self, tab, *, attempts=20, interval=0.5, keepalive=None):
        return {"url": self._fixture_uri, "title": "desktop-cards", "ready": "complete",
                "http_status": 200, "text": "", "text_len": 100, "timed_out": False}


def main() -> int:
    if not FIXTURE.is_file():
        print(json.dumps({"error": "fixture_missing", "path": str(FIXTURE)}))
        return 2
    profile = pathlib.Path(tempfile.mkdtemp(prefix="rpa-live-smoke-"))
    fixture_uri = FIXTURE.as_uri()
    created: list[_LocalLiveSession] = []
    ledger = _StubLedger()

    def _factory(profile_arg, *, live, timeout=None, user_agent=None):
        sess = _LocalLiveSession(fixture_uri, profile=profile, live=False,
                                 timeout=timeout or 60.0, user_agent=user_agent)
        created.append(sess)
        return sess

    buf = io.StringIO()
    original = (cli._open_ledger, cli._new_session, cli.desktop_mod.Keepalive)
    cli._open_ledger = lambda: ledger
    cli._new_session = _factory
    cli.desktop_mod.Keepalive = _FakeKeepalive
    try:
        with contextlib.redirect_stdout(buf):
            code = cli.main(["live-search", "--keyword", "学习计划模板", "--allow-live",
                             "--batch-id", "smoke", "--limit", "5",
                             "--out", str(HERE / "logs" / "live-search-smoke.jsonl")])
    finally:
        cli._open_ledger, cli._new_session, cli.desktop_mod.Keepalive = original

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
    details = payload.get("records_detail") or []
    rejected = payload.get("rejected") or {}
    checks = []

    def record(name: str, passed: bool, detail="") -> None:
        checks.append({"check": name, "pass": bool(passed), "detail": detail})

    record("default_user_agent_is_none",
           cli.build_parser().parse_args(["live-search", "--keyword", "k"]).user_agent is None)
    record("exit_zero", code == 0, str(code))
    record("records_two", payload.get("count") == 2, str(payload.get("count")))
    record("records_detail_nonempty", len(details) == 2, json.dumps(len(details)))
    record("id_source_present",
           {d.get("id_source") for d in details} == {"mid", "bid"},
           json.dumps([d.get("id_source") for d in details]))
    record("author_present", all(d.get("author") for d in details),
           json.dumps([d.get("author") for d in details]))
    record("interaction_present",
           any(d.get("reposts") is not None for d in details)
           and any(d.get("comments") is not None for d in details)
           and any(d.get("likes") is not None for d in details),
           json.dumps([(d.get("reposts"), d.get("comments"), d.get("likes")) for d in details]))
    record("rejected_classification",
           rejected.get("foreign_host") == 1 and rejected.get("bad_id") == 1,
           json.dumps(rejected))
    record("requested_url_present", bool(payload.get("requested_url")),
           str(payload.get("requested_url")))
    text = " ".join((r.get("text") or "") for r in payload.get("records") or [])
    record("no_nav_text", all(marker not in text for marker in NAV_MARKERS), text)

    all_pass = all(c["pass"] for c in checks)
    out = {"generated_utc": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
           "all_pass": all_pass, "checks": checks, "exit": code,
           "requested_url": payload.get("requested_url"),
           "final_url": payload.get("final_url"),
           "count": payload.get("count"), "details": details, "rejected": rejected,
           "stdout": raw}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({"all_pass": all_pass,
                      "failed": [c for c in checks if not c["pass"]],
                      "exit": code, "count": payload.get("count"),
                      "details": details, "rejected": rejected, "out": str(OUT)},
                     ensure_ascii=False))
    return 0 if all_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
