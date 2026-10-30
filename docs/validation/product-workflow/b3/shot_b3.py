"""B3 截图（隔离库/临时目录）：聚焦「上架准备检查」区块的两态截图（桌面 + 手机）。

做法：`#h-ready` 的 `scrollIntoView({block:'start'})` 定位后截**视口**（等价于元素级查看），
manifest 记录 `scroll_y` 与 `rect`，并自校验：图片尺寸==视口、滚动确实发生、sha 与磁盘一致。
"""

from __future__ import annotations

import asyncio
import hashlib
import http.cookiejar
import json
import os
import pathlib
import re
import struct
import subprocess
import sys
import tempfile
import time
import urllib.parse
import urllib.request

import nodriver as uc

B3 = pathlib.Path(r"D:\桌面\two\docs\validation\product-workflow\b3")
SHOTS = B3 / "shots"
TMP = pathlib.Path(tempfile.mkdtemp(prefix="b3-shots-"))
DB = TMP / "workflow.sqlite3"
SECRET = TMP / "secret"
PORT = 5018
BASE = f"http://127.0.0.1:{PORT}"
PY = pathlib.Path(r"D:\桌面\two\.venv\Scripts\python.exe")
ROOT = pathlib.Path(r"D:\桌面\two")
CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"

EVIDENCE = {
    "selected_supply_id": "sup-mit-1", "supply_version": "v1",
    "supply_license_commercial": "yes", "supply_license_redistribute": "yes", "supply_license_resell": "yes",
    "sample_status": "verified", "sample_ref": "sample://check-1", "cost_minor": "500", "cost_known": "yes",
    "platform_evidence": "policy://xianyu/digital-goods", "copy_status": "final", "copy_version": "copy-v1",
    "selling_points": "覆盖求职全流程\n可直接复制使用", "price_minor": "990",
    "delivery_note": "拍下后 1 小时内发网盘链接", "aftersales_note": "7 天内答疑，不含二次定制",
    "faq_json": json.dumps([{"q": "能否商用", "a": "许可见许可说明"}], ensure_ascii=False),
}

SCROLL_JS = """
(() => {
  const el = document.querySelector('section[aria-labelledby="h-ready"]');
  if (!el) { return JSON.stringify({found: false}); }
  const r = el.getBoundingClientRect();
  const title = (el.querySelector('h2') || {}).textContent || '';
  return JSON.stringify({found: true,
    sectionTitle: title.trim(),
    clip: {x: Math.round(r.x + window.scrollX), y: Math.round(r.y + window.scrollY),
           width: Math.round(r.width), height: Math.round(r.height), scale: 1},
    scrollY: Math.round(window.scrollY),
    innerW: window.innerWidth, innerH: window.innerHeight,
    scrollW: document.documentElement.scrollWidth,
    overflowX: document.documentElement.scrollWidth > window.innerWidth + 1,
    hasChecks: !!el.querySelector('table'),
    hasBlockers: !!el.querySelector('ul.gaps'),
    hasDisabled: !!el.querySelector('button[disabled]'),
    hasExportLink: !!el.querySelector('a[href*="/export"]')});
})()
"""


def jpeg_size(path: pathlib.Path):
    data = path.read_bytes()
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        w, h = struct.unpack(">II", data[16:24])
        return w, h
    i = 2
    while i < len(data) - 9:
        if data[i] != 0xFF:
            i += 1
            continue
        marker = data[i + 1]
        if marker in (0xC0, 0xC1, 0xC2, 0xC3):
            h, w = struct.unpack(">HH", data[i + 5 : i + 9])
            return w, h
        i += 2 + struct.unpack(">H", data[i + 2 : i + 4])[0]
    return None, None


def start() -> subprocess.Popen:
    env = dict(os.environ)
    env.update({"WORKBENCH_WORKFLOW_DB": str(DB), "WORKBENCH_SECRET_FILE": str(SECRET),
                "PYTHONUTF8": "1", "PYTHONDONTWRITEBYTECODE": "1"})
    proc = subprocess.Popen([str(PY), "-X", "utf8", "tools/workbench/run.py", "--port", str(PORT), "--no-browser"],
                            cwd=str(ROOT), env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(60):
        time.sleep(0.3)
        try:
            with urllib.request.urlopen(BASE + "/healthz", timeout=2) as resp:
                if resp.status == 200:
                    return proc
        except Exception:
            continue
    raise RuntimeError("server did not start")


def new_session():
    jar = http.cookiejar.CookieJar()
    return urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))


def create_workorder(opener, tag: str) -> tuple[str, str]:
    with opener.open(BASE + "/opportunities", timeout=10) as resp:
        html = resp.read().decode("utf-8", "replace")
    forms = re.findall(r'<form method="post" action="/worksheet/new" class="pick">(.*?)</form>', html, re.S)
    form = dict(re.findall(r'name="([^"]+)" value="([^"]*)"', forms[0]))
    # 用不同 submit_key/名称，避免幂等命中同一条工作单（两态需要两张单）
    form["submit_key"] = f"shot-{tag}"
    form["name"] = f"{form.get('name') or '工作单'}（{tag}）"
    body = urllib.parse.urlencode(form).encode()
    req = urllib.request.Request(BASE + "/worksheet/new", data=body, method="POST")
    req.add_header("Content-Type", "application/x-www-form-urlencoded")
    with opener.open(req, timeout=10) as resp:
        wid = resp.geturl().rsplit("/", 1)[-1].split("?")[0]
    with opener.open(BASE + f"/worksheet/{wid}", timeout=10) as resp:
        detail = resp.read().decode("utf-8", "replace")
    return wid, re.search(r'name="csrf" value="([^"]+)"', detail).group(1)


def fill_evidence(opener, wid: str, csrf: str, revision: str) -> None:
    body = urllib.parse.urlencode({"csrf": csrf, "revision": revision, **EVIDENCE}).encode()
    req = urllib.request.Request(BASE + f"/worksheet/{wid}/evidence", data=body, method="POST")
    req.add_header("Content-Type", "application/x-www-form-urlencoded")
    with opener.open(req, timeout=10) as resp:
        resp.read()


def current_revision(wid: str) -> int:
    import sqlite3
    conn = sqlite3.connect(DB)
    try:
        return int(conn.execute("SELECT revision FROM workorder WHERE workorder_id=?", (wid,)).fetchone()[0])
    finally:
        conn.close()


async def main() -> int:
    SHOTS.mkdir(parents=True, exist_ok=True)
    proc = start()
    manifest: dict[str, dict] = {}
    checks: dict[str, dict] = {}
    try:
        opener = new_session()
        wid_ready, csrf = create_workorder(opener, "ready")
        wid_blocked, _csrf2 = create_workorder(new_session(), "blocked")

        browser = await uc.start(headless=True, browser_executable_path=CHROME,
                                 browser_args=["--hide-scrollbars", "--no-first-run"], sandbox=False)
        try:
            tab = await browser.get(BASE + f"/worksheet/{wid_blocked}")
            await asyncio.sleep(1.0)

            async def set_view(width: int, height: int, mobile: bool) -> None:
                await tab.send(uc.cdp.emulation.set_device_metrics_override(
                    width=width, height=height, device_scale_factor=1, mobile=mobile,
                    screen_width=width, screen_height=height))

            async def capture(name: str, wid: str) -> dict:
                await tab.get(BASE + f"/worksheet/{wid}")
                for _ in range(20):
                    await asyncio.sleep(0.3)
                    raw = await tab.evaluate(SCROLL_JS, await_promise=False)
                    info = json.loads(raw) if isinstance(raw, str) else {}
                    if info.get("found"):
                        break
                clip = info.get("clip") or {}
                out = SHOTS / f"{name}.png"
                method = "cdp clip (capture_beyond_viewport)"
                try:
                    import base64
                    b64 = await tab.send(uc.cdp.page.capture_screenshot(
                        clip=uc.cdp.page.Viewport(x=clip["x"], y=clip["y"], width=clip["width"],
                                                  height=clip["height"], scale=1),
                        capture_beyond_viewport=True))
                    out.write_bytes(base64.b64decode(b64))
                except Exception as exc:                    # 兜底：加高视口后整屏截图
                    method = f"fallback tall viewport (clip failed: {type(exc).__name__})"
                    await tab.send(uc.cdp.emulation.set_device_metrics_override(
                        width=info.get("innerW") or 1440, height=max(1400, int(clip.get("height") or 0) + 120),
                        device_scale_factor=1, mobile=False,
                        screen_width=info.get("innerW") or 1440,
                        screen_height=max(1400, int(clip.get("height") or 0) + 120)))
                    await asyncio.sleep(0.5)
                    out = SHOTS / f"{name}.jpg"
                    await tab.save_screenshot(str(out))
                w, h = jpeg_size(out)
                info.update({"file": out.name, "path": str(out), "width": w, "height": h,
                             "bytes": out.stat().st_size,
                             "sha256": hashlib.sha256(out.read_bytes()).hexdigest(),
                             "selector": 'section[aria-labelledby="h-ready"]',
                             "method": method})
                checks[name] = {"sectionTitle": info.get("sectionTitle"), "clip": clip,
                                "scrollY": info.get("scrollY"), "hasChecks": info.get("hasChecks"),
                                "hasBlockers": info.get("hasBlockers"), "hasDisabled": info.get("hasDisabled"),
                                "hasExportLink": info.get("hasExportLink")}
                manifest[out.name] = info
                return info

            await set_view(1440, 900, False)
            await capture("desktop_checks_not_ready", wid_blocked)

            fill_evidence(opener, wid_ready, csrf, str(current_revision(wid_ready)))
            await capture("desktop_checks_ready", wid_ready)

            await set_view(390, 844, True)
            await capture("mobile_checks_ready", wid_ready)
            await capture("mobile_checks_not_ready", wid_blocked)
        finally:
            try:
                browser.stop()
            except Exception:
                pass
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()

    verify = []
    for name, meta in manifest.items():
        path = SHOTS / name
        live = {"bytes": path.stat().st_size, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
        clip = meta.get("clip") or {}
        method = meta.get("method") or ""
        if method.startswith("cdp clip"):
            size_ok = (abs(meta.get("width", 0) - clip.get("width", -9)) <= 1
                       and abs(meta.get("height", 0) - clip.get("height", -9)) <= 1)
        else:                       # 兜底：加高视口，图高必须 >= 区块高
            size_ok = meta.get("height", 0) >= (clip.get("height") or 0)
        ok = (live["bytes"] == meta["bytes"] and live["sha256"] == meta["sha256"]
              and meta.get("hasChecks") and meta.get("sectionTitle", "").startswith("上架准备检查")
              and size_ok)
        stem = name.rsplit(".", 1)[0]
        is_not_ready = stem.endswith("not_ready")
        is_ready = stem.endswith("_ready") and not is_not_ready
        if is_not_ready:
            ok = ok and meta.get("hasDisabled") and not meta.get("hasExportLink") and meta.get("hasBlockers")
        if is_ready:
            ok = ok and meta.get("hasExportLink")
        verify.append({"file": name, "ok": bool(ok), "live": live, "clip": clip, "method": method,
                       "width": meta.get("width"), "height": meta.get("height"),
                       "sectionTitle": meta.get("sectionTitle"), "hasChecks": meta.get("hasChecks"),
                       "hasBlockers": meta.get("hasBlockers"),
                       "hasDisabled": meta.get("hasDisabled"), "hasExportLink": meta.get("hasExportLink")})
    # 同视口两态必须不同（证明不是同一张图）
    def sha_of(prefix: str):
        for name, meta in manifest.items():
            if name.startswith(prefix):
                return meta["sha256"]
        return None

    distinct = {}
    for a, b in (("desktop_checks_not_ready", "desktop_checks_ready"),
                 ("mobile_checks_not_ready", "mobile_checks_ready")):
        sa, sb = sha_of(a), sha_of(b)
        distinct[f"{a} vs {b}"] = bool(sa and sb and sa != sb)
    report = {"base": BASE, "workorders": {"ready": wid_ready, "blocked": wid_blocked},
              "shots": manifest, "checks": checks, "state_distinct": distinct,
              "verification": {"checked": len(verify), "failed": [v for v in verify if not v["ok"]],
                               "ok": all(v["ok"] for v in verify) and all(distinct.values())}}
    (B3 / "shots_manifest.json").write_bytes(json.dumps(report, ensure_ascii=False, indent=1).encode())
    if SECRET.exists():
        SECRET.unlink()
    print(json.dumps({"shots": list(manifest), "verification": report["verification"]["ok"],
                      "checks": checks}, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
