"""真实桌面级可见性检查：本地 fixture + 可见 Chrome + Windows 前台/矩形/整屏截图。

必须用带 nodriver 的解释器（项目 .venv 没有 nodriver）：

    cd D:\\桌面\\two
    C:\\Users\\19183\\.dsh\\tools\\x-collect\\venv\\Scripts\\python.exe -X utf8 `
      docs\\validation\\v10\\browser-rpa\\checks\\desktop_proof_check.py

产物：
- `docs/validation/v10/browser-rpa/logs/desktop-proof-check.json`（逐项 pass/fail + 原始字段）
- `docs/validation/v10/browser-rpa/logs/desktop-proof.png`（**整屏**截图，不是页面截图）

退出码：0 全过；1 有检查失败；2 fixture 缺失。

注意：需要**交互桌面会话**（用户已登录的 Windows 桌面）。服务会话/锁屏下
`GetForegroundWindow` 不可能等于目标窗口，本脚本会如实报
`foreground_not_matched` 并退出 1 —— 这是结论，不是脚本故障。
"""

from __future__ import annotations

import datetime as dt
import json
import pathlib
import sys
import tempfile
import time

REPO = pathlib.Path(__file__).resolve().parents[5]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from tools.selection.rpa import session  # noqa: E402

HERE = REPO / "docs" / "validation" / "v10" / "browser-rpa"
FIXTURE = HERE / "fixtures" / "card-cases.html"
OUT_JSON = HERE / "logs" / "desktop-proof-check.json"
OUT_PNG = HERE / "logs" / "desktop-proof.png"


def main() -> int:
    if not FIXTURE.is_file():
        print(json.dumps({"error": "fixture_missing", "path": str(FIXTURE)}))
        return 2
    checks: list[dict] = []

    def record(name: str, passed: bool, detail="") -> None:
        checks.append({"check": name, "pass": bool(passed), "detail": detail})

    profile = pathlib.Path(tempfile.mkdtemp(prefix="rpa-desktop-"))
    sess = session.VisibleSession(profile, live=False)
    started = nav = proof = None
    try:
        started = sess.start()
        tab, blocked = sess.open_local(FIXTURE.as_uri())
        nav = sess.navigate_stable(tab)
        nonce = f"DSH-RPA-PROOF-{dt.datetime.now().strftime('%H%M%S')}"
        sess.set_title(tab, nonce)
        time.sleep(0.6)                      # 让窗口标题刷新，PID 匹配失败时可按 nonce 兜底
        proof = sess.desktop_proof(screenshot=OUT_PNG, title_hint=nonce)
        record("session_mode_local", started.get("mode") == "local",
               json.dumps(started, ensure_ascii=False))
        record("network_blocked", isinstance(blocked, dict)
               and bool(blocked.get("blocked_patterns")), json.dumps(blocked))
        record("navigation_stable", bool(nav) and not nav.get("escaped")
               and not nav.get("timed_out"), json.dumps(nav, ensure_ascii=False))
        record("desktop_supported", bool(proof.get("supported")), proof.get("platform"))
        record("window_found", proof.get("hwnd") is not None,
               f"hwnd={proof.get('hwnd')} matched_by={proof.get('matched_by')}")
        record("foreground_matched", bool(proof.get("foreground_matched")),
               f"before={proof.get('foreground_before')} "
               f"after={proof.get('foreground_after')} reason={proof.get('reason')}")
        rect = proof.get("window_rect") or {}
        record("window_rect_readable", int(rect.get("width") or 0) > 0
               and int(rect.get("height") or 0) > 0,
               json.dumps(rect, ensure_ascii=False))
        shot = proof.get("desktop_screenshot") or {}
        record("desktop_screenshot_written",
               int(proof.get("desktop_screenshot_bytes") or 0) > 1000,
               json.dumps(shot, ensure_ascii=False))
        screen = proof.get("screen") or {}
        same_size = (int(shot.get("width") or 0) == int(screen.get("width") or -1)
                     and int(shot.get("height") or 0) == int(screen.get("height") or -1))
        record("screenshot_covers_whole_screen", same_size,
               f"shot={shot.get('width')}x{shot.get('height')} "
               f"screen={screen.get('width')}x{screen.get('height')}")
        record("proven_true", bool(proof.get("proven")), proof.get("reason"))
    except Exception as exc:  # noqa: BLE001 - 失败要留证据，不是崩掉
        record("exception", False, f"{type(exc).__name__}:{exc}")
        proof = proof or {}
    finally:
        try:
            sess.close()
        except Exception:  # noqa: BLE001
            pass

    all_pass = all(item["pass"] for item in checks)
    payload = {
        "generated_utc": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "python": sys.executable,
        "cwd": str(pathlib.Path.cwd()),
        "fixture": str(FIXTURE),
        "all_pass": all_pass,
        "checks": checks,
        "desktop": proof,
        "session": started,
        "navigation": nav,
        "screenshot_path": str(OUT_PNG),
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(payload, ensure_ascii=False, indent=1),
                        encoding="utf-8")
    print(json.dumps({"all_pass": all_pass,
                      "failed": [c for c in checks if not c["pass"]],
                      "foreground_matched": (proof or {}).get("foreground_matched"),
                      "window_rect": (proof or {}).get("window_rect"),
                      "desktop_screenshot_bytes": (proof or {}).get("desktop_screenshot_bytes"),
                      "reason": (proof or {}).get("reason"),
                      "out": str(OUT_JSON)}, ensure_ascii=False))
    return 0 if all_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
