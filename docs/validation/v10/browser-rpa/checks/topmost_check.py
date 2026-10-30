"""真实本机桌面：置顶 + 被其他最大化窗口遮挡后夺回前台（不访问真实站点）。

场景：
A) 用**真实最大化 Notepad** 盖住 Chrome → `Keepalive.tick(force=True)` 应把 Chrome 夺回前台；
B) `set_topmost(hwnd)` 后回读 `GWL_EXSTYLE`，断言 `WS_EX_TOPMOST` 真的置上；
C) 再把前台切回 Notepad（模拟用户切走）→ 下一次 tick 再夺回，`reassert_count` 递增；
最后 `finish()` 清掉置顶并给出 `still_foreground_at_end`。

用法：
    C:\\Users\\19183\\.dsh\\tools\\x-collect\\venv\\Scripts\\python.exe -X utf8 `
      docs\\validation\\v10\\browser-rpa\\checks\\topmost_check.py
产物：`logs/topmost-check.json`；失败非零。
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes as wintypes
import datetime as dt
import json
import pathlib
import subprocess
import sys
import tempfile
import time
import uuid

REPO = pathlib.Path(__file__).resolve().parents[5]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from tools.selection.rpa import desktop, session  # noqa: E402

HERE = REPO / "docs" / "validation" / "v10" / "browser-rpa"
FIXTURE = HERE / "fixtures" / "card-cases.html"
OUT = HERE / "logs" / "topmost-check.json"


def _find_window_by_class(class_name: str) -> int:
    """EnumWindows 找指定 class 的可见顶层窗口（本机 Notepad 用）。"""
    user32 = ctypes.windll.user32
    found = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def _cb(hwnd, _lparam):
        if not user32.IsWindowVisible(hwnd):
            return True
        buf = ctypes.create_unicode_buffer(256)
        user32.GetClassNameW(hwnd, buf, 256)
        if buf.value == class_name:
            found.append(int(hwnd))
            return False
        return True

    user32.EnumWindows(_cb, 0)
    return found[0] if found else 0


def main() -> int:
    if not FIXTURE.is_file():
        print(json.dumps({"error": "fixture_missing", "path": str(FIXTURE)}))
        return 2
    checks: list[dict] = []

    def record(name: str, passed: bool, detail="") -> None:
        checks.append({"check": name, "pass": bool(passed), "detail": detail})

    nonce = f"RPA-TOPMOST-{uuid.uuid4().hex[:8]}"
    profile = pathlib.Path(tempfile.mkdtemp(prefix="rpa-topmost-"))
    sess = session.VisibleSession(profile, live=False)
    notepad = None
    keepalive = None
    topmost = None
    summary = None
    try:
        sess.start()
        tab, _blocked = sess.open_local(FIXTURE.as_uri())
        sess.set_title(tab, nonce)
        time.sleep(1.0)
        proof = sess.desktop_proof(tab=tab, screenshot=None)
        hwnd = int(proof.get("hwnd") or 0)
        record("window_found", hwnd > 0 and proof.get("proven") is True,
               f"hwnd={hwnd} title={proof.get('window_title')!r}")

        # B) 置顶并回读 exstyle
        topmost = desktop.set_topmost(hwnd, on=True)
        record("topmost_set_via_exstyle", topmost.get("topmost_set") is True,
               json.dumps(topmost, ensure_ascii=False))
        record("exstyle_has_ws_ex_topmost",
               desktop.topmost_flag(topmost.get("exstyle") or 0),
               str(topmost.get("exstyle")))

        # A) 真实最大化 Notepad 盖住 Chrome
        notepad = subprocess.Popen(["notepad.exe"])
        notepad_hwnd = 0
        for _ in range(30):
            notepad_hwnd = _find_window_by_class("Notepad")
            if notepad_hwnd:
                break
            time.sleep(0.2)
        record("cover_window_found", bool(notepad_hwnd), f"notepad_hwnd={notepad_hwnd}")
        if notepad_hwnd:
            desktop.force_foreground(notepad_hwnd)
            time.sleep(0.5)
            covered = desktop.foreground_hwnd() == notepad_hwnd
            record("chrome_covered_by_other_window", covered,
                   f"foreground={desktop.foreground_hwnd()} notepad={notepad_hwnd}")

        keepalive = desktop.Keepalive(hwnd, interval=0)
        keepalive.start()
        first = keepalive.tick(force=True)
        record("reassert_after_cover",
               bool(first and first.get("reasserted")),
               json.dumps(first, ensure_ascii=False))

        # C) 用户切走 → 再夺回
        if notepad_hwnd:
            desktop.force_foreground(notepad_hwnd)
            time.sleep(0.5)
            switched = desktop.foreground_hwnd() == notepad_hwnd
            record("user_switched_away", switched, f"foreground={desktop.foreground_hwnd()}")
        second = keepalive.tick(force=True)
        record("reassert_after_user_switch",
               bool(second and second.get("reasserted")),
               json.dumps(second, ensure_ascii=False))

        summary = keepalive.finish()
        record("reassert_count_ge_2", (summary.get("reassert_count") or 0) >= 2,
               str(summary.get("reassert_count")))
        record("still_foreground_at_end", summary.get("still_foreground_at_end") is True,
               json.dumps(summary, ensure_ascii=False))
        record("topmost_cleared", summary.get("topmost_cleared") is True,
               json.dumps(summary, ensure_ascii=False))
        record("no_reassert_failures", (summary.get("reassert_failures") or 0) == 0,
               str(summary.get("reassert_failures")))
    finally:
        if notepad is not None:
            notepad.terminate()
            try:
                notepad.wait(timeout=5)
            except Exception:  # noqa: BLE001
                notepad.kill()
        sess.close()

    all_pass = all(c["pass"] for c in checks)
    payload = {"generated_utc": dt.datetime.now(dt.timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ"), "all_pass": all_pass, "checks": checks,
        "topmost": topmost, "keepalive": summary, "fixture": str(FIXTURE.relative_to(REPO))}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({"all_pass": all_pass, "failed": [c for c in checks if not c["pass"]],
                      "topmost_set": (topmost or {}).get("topmost_set"),
                      "keepalive": summary, "out": str(OUT)}, ensure_ascii=False))
    return 0 if all_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
