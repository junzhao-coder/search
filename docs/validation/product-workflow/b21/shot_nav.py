"""B21：新侧栏截图（选品/选源/起草介绍桌面各一张 + 手机展开菜单一张，隔离库）。"""

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

B21 = pathlib.Path(r"D:\桌面\two\docs\validation\product-workflow\b21")
SHOTS = B21 / "shots"
TMP = pathlib.Path(tempfile.mkdtemp(prefix="b21-shots-"))
DB, SECRET = TMP / "w.db", TMP / "s"
PORT, BASE = 5025, "http://127.0.0.1:5025"
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


def size(p):
    b = p.read_bytes()
    if b[:8] == b"\x89PNG\r\n\x1a\n":
        return struct.unpack(">II", b[16:24])[0], struct.unpack(">II", b[16:24])[1]
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


async def main() -> int:
    SHOTS.mkdir(parents=True, exist_ok=True)
    out = {"generated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "port": PORT, "shots": {}}
    proc = start()
    try:
        jar = http.cookiejar.CookieJar()
        op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))

        def req(method, path, data=None):
            body = urllib.parse.urlencode(data).encode() if data else None
            r = urllib.request.Request(BASE + path, data=body, method=method)
            if body:
                r.add_header("Content-Type", "application/x-www-form-urlencoded")
            with op.open(r, timeout=15) as resp:
                return resp.status, resp.read().decode("utf-8", "replace"), resp.geturl()

        _, page, _ = req("GET", "/worksheet/new")
        csrf = re.search(r'name="csrf" value="([^"]+)"', page).group(1)
        _, _, url = req("POST", "/worksheet/new", {
            "csrf": csrf, "self_made": "1", "submit_key": "b21-shot",
            "name": "示例：自制提示词包（B21 导航截图）", "use_case": "会议纪要", "deliverable": "纯文本 .md",
            "target_platform": "xianyu", "fmt": "md"})
        wid = url.rsplit("/", 1)[-1].split("?")[0]
        _, page, _ = req("GET", f"/source?wo={wid}")
        csrf = re.search(r'name="csrf" value="([^"]+)"', page).group(1)
        req("POST", f"/worksheet/{wid}/supply/candidates", {
            "csrf": csrf, "provider": "自制（作者自持）", "source_url": "self:pp-v1", "kind": "同款",
            "commercial": "yes", "redistribute": "yes", "resale": "yes", "license_note": "作者权利声明"})
        _, page, _ = req("GET", f"/source?wo={wid}")
        cid = re.search(r'name="candidate_id" value="(sc:[0-9a-f]{8})"', page).group(1)
        rev = re.search(r'name="revision" value="(\d+)"', page).group(1)
        req("POST", f"/worksheet/{wid}/supply/select", {"csrf": csrf, "revision": rev, "candidate_id": cid})
        out["workorder_id"] = wid

        browser = await uc.start(headless=True, browser_executable_path=CHROME,
                                 browser_args=["--hide-scrollbars", "--no-first-run"], sandbox=False)
        try:
            tab = await browser.get(BASE + "/pick")
            await asyncio.sleep(1.4)
            await tab.send(uc.cdp.emulation.set_device_metrics_override(
                width=1440, height=900, device_scale_factor=1, mobile=False, screen_width=1440, screen_height=900))
            for name, path in (("nav_pick_desktop", f"/pick?wo={wid}"),
                               ("nav_source_desktop", f"/source?wo={wid}"),
                               ("nav_copy_desktop", f"/copy?wo={wid}")):
                await tab.get(BASE + path)
                await asyncio.sleep(1.3)
                p = SHOTS / f"{name}.jpg"
                await tab.save_screenshot(str(p))
                w, h = size(p)
                blob = p.read_bytes()
                out["shots"][p.name] = {"width": w, "height": h, "bytes": p.stat().st_size, "url": path,
                                        "format": "jpeg", "openable": blob[:3] == b"\xff\xd8\xff" and blob.rstrip().endswith(b"\xff\xd9"),
                                        "sha256": hashlib.sha256(blob).hexdigest()}

            # 手机：打开菜单后截图
            await tab.send(uc.cdp.emulation.set_device_metrics_override(
                width=390, height=844, device_scale_factor=1, mobile=True, screen_width=390, screen_height=844))
            await tab.get(BASE + f"/pick?wo={wid}")
            await asyncio.sleep(1.2)
            await tab.evaluate("document.querySelector('.nav-toggle')?.click()")
            await asyncio.sleep(0.8)
            expanded = await tab.evaluate("document.querySelector('.nav-toggle')?.getAttribute('aria-expanded')",
                                          await_promise=False)
            p = SHOTS / "nav_mobile_menu.jpg"
            await tab.save_screenshot(str(p))
            w, h = size(p)
            blob = p.read_bytes()
            out["shots"][p.name] = {"width": w, "height": h, "bytes": p.stat().st_size,
                                    "url": f"/pick?wo={wid}（菜单展开）", "format": "jpeg",
                                    "openable": blob[:3] == b"\xff\xd8\xff" and blob.rstrip().endswith(b"\xff\xd9"),
                                    "sha256": hashlib.sha256(blob).hexdigest(),
                                    "menu_expanded": str(expanded)}
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
    (B21 / "shots_manifest.json").write_bytes(json.dumps(out, ensure_ascii=False, indent=1).encode())
    if SECRET.exists():
        SECRET.unlink()
    print(json.dumps({"wid": out.get("workorder_id"), "shots": list(out["shots"])}, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
