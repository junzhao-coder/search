"""B1 截图（隔离测试库）：工作单列表/详情/编辑（桌面 1440×900）+ 列表（手机 390×844），manifest 自校验。"""

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

B1 = pathlib.Path(r"D:\桌面\two\docs\validation\product-workflow\b1")
SHOTS = B1 / "shots"
# 测试库与密钥放在系统临时目录，跑完即清理；不动生产 runtime/
TMP = pathlib.Path(tempfile.mkdtemp(prefix="b1-shots-"))
DB = TMP / "workflow_e2e.sqlite3"
SECRET = TMP / "secret_e2e"
PORT = 5017
BASE = f"http://127.0.0.1:{PORT}"
PY = pathlib.Path(r"D:\桌面\two\.venv\Scripts\python.exe")
ROOT = pathlib.Path(r"D:\桌面\two")
CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"

MEASURE = """
(() => { const de = document.documentElement;
  return JSON.stringify({url: location.href, innerW: window.innerWidth, innerH: window.innerHeight,
    scrollW: de.scrollWidth, overflowX: de.scrollWidth > window.innerWidth + 1}); })()
"""


def jpeg_size(path: pathlib.Path):
    data = path.read_bytes()
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


def bootstrap_workorder() -> None:
    """库里没有工作单时，用真实表单流程建一条（仅测试库）。"""
    import sqlite3
    if DB.exists():
        conn = sqlite3.connect(DB)
        try:
            has = conn.execute("SELECT COUNT(*) FROM workorder").fetchone()[0]
        except sqlite3.OperationalError:
            has = 0
        finally:
            conn.close()
        if has:
            return
    jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    with opener.open(BASE + "/opportunities", timeout=10) as resp:
        html = resp.read().decode("utf-8", "replace")
    forms = re.findall(r'<form method="post" action="/worksheet/new" class="pick">(.*?)</form>', html, re.S)
    form = dict(re.findall(r'name="([^"]+)" value="([^"]*)"', forms[0]))
    body = urllib.parse.urlencode(form).encode()
    req = urllib.request.Request(BASE + "/worksheet/new", data=body, method="POST")
    req.add_header("Content-Type", "application/x-www-form-urlencoded")
    opener.open(req, timeout=10).read()


async def main() -> int:
    SHOTS.mkdir(parents=True, exist_ok=True)
    proc = start()
    manifest: dict[str, dict] = {}
    metrics: dict[str, dict] = {}
    try:
        bootstrap_workorder()
        import sqlite3
        conn = sqlite3.connect(DB)
        wid = conn.execute("SELECT workorder_id FROM workorder LIMIT 1").fetchone()[0]
        conn.close()
        browser = await uc.start(headless=True, browser_executable_path=CHROME,
                                 browser_args=["--hide-scrollbars", "--no-first-run"], sandbox=False)
        try:
            tab = await browser.get(BASE + "/worksheet")
            await asyncio.sleep(1.2)
            await tab.send(uc.cdp.emulation.set_device_metrics_override(
                width=1440, height=900, device_scale_factor=1, mobile=False, screen_width=1440, screen_height=900))
            await asyncio.sleep(0.8)
            for path, name in (("/worksheet", "desktop_worksheet_list"), (f"/worksheet/{wid}", "desktop_worksheet_detail"),
                               (f"/worksheet/{wid}/edit", "desktop_worksheet_edit")):
                await tab.get(BASE + path)
                await asyncio.sleep(1.2)
                raw = await tab.evaluate(MEASURE, await_promise=False)
                metrics[name] = json.loads(raw) if isinstance(raw, str) else {}
                shot = SHOTS / f"{name}.jpg"
                await tab.save_screenshot(str(shot))
                w, h = jpeg_size(shot)
                manifest[shot.name] = {"file": shot.name, "path": str(shot), "width": w, "height": h,
                                       "bytes": shot.stat().st_size,
                                       "sha256": hashlib.sha256(shot.read_bytes()).hexdigest(),
                                       "viewport": "1440x900"}
            await tab.send(uc.cdp.emulation.set_device_metrics_override(
                width=390, height=844, device_scale_factor=1, mobile=True, screen_width=390, screen_height=844))
            await tab.get(BASE + "/worksheet")
            await asyncio.sleep(1.2)
            raw = await tab.evaluate(MEASURE, await_promise=False)
            metrics["mobile_worksheet_list"] = json.loads(raw) if isinstance(raw, str) else {}
            shot = SHOTS / "mobile_worksheet_list.jpg"
            await tab.save_screenshot(str(shot))
            w, h = jpeg_size(shot)
            manifest[shot.name] = {"file": shot.name, "path": str(shot), "width": w, "height": h,
                                   "bytes": shot.stat().st_size,
                                   "sha256": hashlib.sha256(shot.read_bytes()).hexdigest(), "viewport": "390x844"}
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
        verify.append({"file": name, "ok": live["bytes"] == meta["bytes"] and live["sha256"] == meta["sha256"], **live})
    report = {"base": BASE, "workorder_id": wid, "shots": manifest, "metrics": metrics,
              "verification": {"checked": len(verify), "mismatches": [v for v in verify if not v["ok"]],
                               "ok": all(v["ok"] for v in verify)}}
    (B1 / "shots_manifest.json").write_bytes(json.dumps(report, ensure_ascii=False, indent=1).encode())
    if SECRET.exists():
        SECRET.unlink()          # 清理测试密钥
    print(json.dumps({"shots": list(manifest), "verification": report["verification"]["ok"],
                      "metrics": metrics}, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
