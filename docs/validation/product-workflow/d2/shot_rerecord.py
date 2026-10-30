"""D2：截图（详情页“重新记录本次导出”按钮 + 文案版本提示），隔离库真机拍摄。"""

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

D2 = pathlib.Path(r"D:\桌面\two\docs\validation\product-workflow\d2")
SHOTS = D2 / "shots"
SHOTS.mkdir(parents=True, exist_ok=True)
TMP = pathlib.Path(tempfile.mkdtemp(prefix="d2-shot-"))
DB, SECRET = TMP / "w.db", TMP / "s"
PORT, BASE = 5028, "http://127.0.0.1:5028"
PY = pathlib.Path(r"D:\桌面\two\.venv\Scripts\python.exe")
ROOT = pathlib.Path(r"D:\桌面\two")
CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"


def start():
    env = dict(os.environ)
    env.update({"WORKBENCH_WORKFLOW_DB": str(DB), "WORKBENCH_SECRET_FILE": str(SECRET),
                "PYTHONUTF8": "1", "PYTHONDONTWRITEBYTECODE": "1"})
    p = subprocess.Popen([str(PY), "-X", "utf8", "tools/workbench/run.py", "--port", str(PORT), "--no-browser"],
                         cwd=str(ROOT), env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(60):
        time.sleep(0.3)
        try:
            with urllib.request.urlopen(BASE + "/healthz", timeout=2):
                return p
        except Exception:
            continue
    raise RuntimeError("no start")


def jpeg_size(p):
    b = p.read_bytes()
    i = 2
    while i < len(b) - 9:
        if b[i] != 0xFF:
            i += 1
            continue
        m = b[i + 1]
        if m in (0xC0, 0xC1, 0xC2, 0xC3):
            h, w = struct.unpack(">HH", b[i + 5 : i + 9])
            return w, h
        i += 2 + struct.unpack(">H", b[i + 2 : i + 4])[0]
    return None, None


JS = """
(() => { const el=[...document.querySelectorAll('#h-pub')][0]
   ? document.querySelector('section[aria-labelledby="h-pub"]') : null;
  if (!el) return JSON.stringify({found:false});
  const r = el.getBoundingClientRect();
  return JSON.stringify({found:true, clip:{x:Math.round(r.x+window.scrollX), y:Math.round(r.y+window.scrollY),
    width:Math.round(r.width), height:Math.round(r.height), scale:1},
    hasRerecord: !!el.querySelector('button') && el.innerText.includes('重新记录本次导出')}); })()
"""


async def main() -> int:
    out = {"generated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "shots": {}}
    proc = start()
    try:
        op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))

        def req(method, path, data=None):
            body = urllib.parse.urlencode(data).encode() if data else None
            r = urllib.request.Request(BASE + path, data=body, method=method)
            if body:
                r.add_header("Content-Type", "application/x-www-form-urlencoded")
            with op.open(r, timeout=15) as resp:
                return resp.status, resp.read().decode("utf-8", "replace")

        _, page = req("GET", "/worksheet/new")
        csrf = re.search(r'name="csrf" value="([^"]+)"', page).group(1)
        req("POST", "/worksheet/new", {"csrf": csrf, "self_made": "1", "submit_key": "d2-shot",
                                       "name": "[SYNTHETIC] D2 截图单", "use_case": "测试",
                                       "deliverable": "文本", "target_platform": "xianyu"})
        _, pick = req("GET", "/pick")
        wid = re.search(r'href="/source\?wo=(wo:\d{8}-[0-9a-f]{8})"', pick).group(1)
        out["workorder_id"] = wid

        # 造出“有导出记录 + 发布已变更”的状态
        _, page = req("GET", f"/worksheet/{wid}")
        csrf = re.search(r'name="csrf" value="([^"]+)"', page).group(1)
        rev = re.search(r'name="revision" value="(\d+)"', page).group(1)
        req("POST", f"/worksheet/{wid}/supply/candidates",
            {"csrf": csrf, "provider": "SELF", "source_url": "self:d2", "kind": "同款",
             "commercial": "yes", "redistribute": "yes", "resale": "yes"})
        _, page = req("GET", f"/worksheet/{wid}")
        cid = re.search(r'name="candidate_id" value="(sc:[0-9a-f]{8})"', page).group(1)
        req("POST", f"/worksheet/{wid}/supply/select",
            {"csrf": csrf, "revision": re.search(r'name="revision" value="(\d+)"', page).group(1), "candidate_id": cid})
        _, page = req("GET", f"/worksheet/{wid}")
        req("POST", f"/worksheet/{wid}/evidence", {
            "csrf": csrf, "revision": re.search(r'name="revision" value="(\d+)"', page).group(1),
            "sample_status": "verified", "sample_note": "自测", "cost_minor": "300", "cost_known": "yes",
            "platform_evidence": "synthetic://d2/shot", "copy_status": "final", "copy_version": "copy-d2",
            "selling_points": "A", "price_minor": "1990", "delivery_note": "站内", "aftersales_note": "未定",
            "faq_json": "[]"})
        _, page = req("GET", f"/worksheet/{wid}")
        req("POST", f"/worksheet/{wid}/export/record",
            {"csrf": csrf, "format": "md"})
        req("POST", f"/worksheet/{wid}/publish",
            {"csrf": csrf, "status": "已发布", "published_url": "https://example.invalid/d2",
             "published_at": "2026-10-24T22:10:00Z", "sold_count": "0"})

        browser = await uc.start(headless=True, browser_executable_path=CHROME,
                                 browser_args=["--hide-scrollbars", "--no-first-run"], sandbox=False)
        try:
            tab = await browser.get(BASE + f"/worksheet/{wid}")
            await asyncio.sleep(1.6)
            await tab.send(uc.cdp.emulation.set_device_metrics_override(
                width=1440, height=900, device_scale_factor=1, mobile=False, screen_width=1440, screen_height=900))
            info = json.loads(await tab.evaluate(JS, await_promise=False))
            import base64
            if info.get("found"):
                c = info["clip"]
                b64 = await tab.send(uc.cdp.page.capture_screenshot(
                    clip=uc.cdp.page.Viewport(x=c["x"], y=c["y"], width=c["width"],
                                              height=min(c["height"], 900), scale=1),
                    capture_beyond_viewport=True))
                p = SHOTS / "worksheet_publish_rerecord.png"
                p.write_bytes(base64.b64decode(b64))
                blob = p.read_bytes()
                out["shots"][p.name] = {"width": struct.unpack(">II", blob[16:24])[0],
                                        "height": struct.unpack(">II", blob[16:24])[1],
                                        "bytes": p.stat().st_size, "format": "png",
                                        "openable": blob[:8] == b"\x89PNG\r\n\x1a\n",
                                        "sha256": hashlib.sha256(blob).hexdigest(),
                                        "has_rerecord_button": info.get("hasRerecord")}
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
    (D2 / "shots_manifest.json").write_bytes(json.dumps(out, ensure_ascii=False, indent=1).encode())
    if SECRET.exists():
        SECRET.unlink()
    print(json.dumps({"wo": out.get("workorder_id"), "shots": list(out["shots"])}, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
