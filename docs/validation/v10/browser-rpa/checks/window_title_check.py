"""真实本地浏览器：窗口标题 = 页面标题（可见性前提）的行为检查。

两段场景：
1. 打开 fixtures 页面 → **激活标签页** → 设置唯一标题 → 断言
   `window_title_matches_page=true`、OS 窗口标题包含该页面标题、gate 放行；
2. 再开一个空白标签（窗口标题变成"新标签页"）→ 不重新激活 → 断言
   `window_title_matches_page=false`、gate 返回 `window_showing_other_tab`。

不访问真实站点、不用真实 profile（隔离临时 profile）、不读 cookie 值、不截图真实页面。

用法：
    C:\\Users\\19183\\.dsh\\tools\\x-collect\\venv\\Scripts\\python.exe -X utf8 `
      docs\\validation\\v10\\browser-rpa\\checks\\window_title_check.py
"""

from __future__ import annotations

import datetime as dt
import json
import pathlib
import sys
import tempfile
import time
import uuid

REPO = pathlib.Path(__file__).resolve().parents[5]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from tools.selection.rpa import cli, session  # noqa: E402

HERE = REPO / "docs" / "validation" / "v10" / "browser-rpa"
FIXTURE = HERE / "fixtures" / "card-cases.html"
OUT = HERE / "logs" / "window-title-check.json"


def main() -> int:
    if not FIXTURE.is_file():
        print(json.dumps({"error": "fixture_missing", "path": str(FIXTURE)}))
        return 2
    checks: list[dict] = []

    def record(name: str, passed: bool, detail="") -> None:
        checks.append({"check": name, "pass": bool(passed), "detail": detail})

    nonce = f"RPA-TITLE-PROOF-{uuid.uuid4().hex[:8]}"
    profile = pathlib.Path(tempfile.mkdtemp(prefix="rpa-title-"))
    sess = session.VisibleSession(profile, live=False)
    first = second = None
    try:
        sess.start()
        tab, _blocked = sess.open_local(FIXTURE.as_uri())
        activation = dict(sess.last_activation or {})
        record("activation_reported", bool(activation.get("activated")),
               json.dumps(activation, ensure_ascii=False))
        sess.set_title(tab, nonce)
        time.sleep(1.2)
        first = sess.desktop_proof(tab=tab, screenshot=None)
        record("window_title_matches_page_true",
               first.get("window_title_matches_page") is True,
               json.dumps({"window_title": first.get("window_title"),
                           "page_title": first.get("page_title")}, ensure_ascii=False))
        record("os_title_contains_page_title",
               nonce in (first.get("window_title") or ""), first.get("window_title") or "")
        record("gate_allows_when_matched", cli._visibility_gate(first) is None,
               str(cli._visibility_gate(first)))

        # 场景 2：导航后另开空白标签 → 窗口显示的不是目标页
        sess._run(sess._browser.get("about:blank"))
        time.sleep(1.2)
        second = sess.desktop_proof(tab=tab, screenshot=None)
        # 判定只要求"不成立"：标题不匹配是 False，读不到页面标题是 None，两者都必须拦。
        record("window_title_not_matching_after_other_tab",
               second.get("window_title_matches_page") is not True,
               json.dumps({"window_title": second.get("window_title"),
                           "page_title": second.get("page_title"),
                           "match": second.get("window_title_matches_page")},
                          ensure_ascii=False))
        record("os_title_no_longer_contains_page_title",
               nonce not in (second.get("window_title") or ""),
               second.get("window_title") or "")
        record("gate_blocks_other_tab",
               cli._visibility_gate(second) == "window_showing_other_tab",
               str(cli._visibility_gate(second)))
    finally:
        sess.close()

    all_pass = all(c["pass"] for c in checks)
    payload = {"generated_utc": dt.datetime.now(dt.timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ"), "all_pass": all_pass, "checks": checks,
        "fixture": str(FIXTURE.relative_to(REPO)), "nonce": nonce,
        "desktop_matched": first, "desktop_other_tab": second,
        "exit_visibility": cli.EXIT_VISIBILITY}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({"all_pass": all_pass, "failed": [c for c in checks if not c["pass"]],
                      "window_title": (first or {}).get("window_title"),
                      "page_title": (first or {}).get("page_title"),
                      "other_tab_title": (second or {}).get("window_title"),
                      "out": str(OUT)}, ensure_ascii=False))
    return 0 if all_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
