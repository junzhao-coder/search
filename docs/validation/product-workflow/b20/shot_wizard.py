"""B20：向导截图（/pick /source /copy 桌面 1440×900 + 手机 390×844，隔离库）。"""

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

B20 = pathlib.Path(r"D:\桌面\two\docs\validation\product-workflow\b20")
SHOTS = B20 / "shots"
TMP = pathlib.Path(tempfile.mkdtemp(prefix="b20-shots-"))
DB, SECRET = TMP / "w.db", TMP / "s"
PORT, BASE = 5024, "http://127.0.0.1:5024"
PY = pathlib.Path(r"D:\桌面\two\.venv\Scripts\python.exe")
ROOT = pathlib.Path(r"D:\桌面\two")
CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
SAMPLE = "docs/validation/product-workflow/b7/sample-study-planner-v1.xlsx"


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


def jpeg(p):
    b = p.read_bytes()
    if b[:8] == b"\x89PNG\r\n\x1a\n":
        return struct.unpack(">II", b[16:24])
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
            "csrf": csrf, "self_made": "1", "submit_key": "b20-shot",
            "name": "示例：自制提示词包（向导截图）", "use_case": "会议纪要", "deliverable": "纯文本 .md（10 条）",
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
        _, page, _ = req("GET", f"/copy?wo={wid}")
        csrf = re.search(r'name="csrf" value="([^"]+)"', page).group(1)
        rev = re.search(r'name="revision" value="(\d+)"', page).group(1)
        req("POST", f"/worksheet/{wid}/sample/check", {"csrf": csrf, "revision": rev, "path": SAMPLE})
        out["workorder_id"] = wid

        browser = await uc.start(headless=True, browser_executable_path=CHROME,
                                 browser_args=["--hide-scrollbars", "--no-first-run"], sandbox=False)
        try:
            tab = await browser.get(BASE + "/pick")
            await asyncio.sleep(1.4)
            await tab.send(uc.cdp.emulation.set_device_metrics_override(
                width=1440, height=900, device_scale_factor=1, mobile=False, screen_width=1440, screen_height=900))
            for name, path, mobile in (("pick_desktop", "/pick", False),
                                       ("source_desktop", f"/source?wo={wid}", False),
                                       ("copy_desktop", f"/copy?wo={wid}", False),
                                       ("pick_mobile", "/pick", True),
                                       ("copy_mobile", f"/copy?wo={wid}", True)):
                if mobile:
                    await tab.send(uc.cdp.emulation.set_device_metrics_override(
                        width=390, height=844, device_scale_factor=1, mobile=True,
                        screen_width=390, screen_height=844))
                await tab.get(BASE + path)
                await asyncio.sleep(1.3)
                p = SHOTS / f"{name}.jpg"       # save_screenshot 输出 JPEG，扩展名保持一致
                await tab.save_screenshot(str(p))
                w, h = jpeg(p)
                blob = p.read_bytes()
                fmt = ("jpeg" if blob[:3] == b"\xff\xd8\xff"
                       else "png" if blob[:8] == b"\x89PNG\r\n\x1a\n" else "unknown")
                openable = bool(fmt == "jpeg" and blob.rstrip().endswith(b"\xff\xd9"))
                out["shots"][p.name] = {"width": w, "height": h, "bytes": p.stat().st_size,
                                        "format": fmt, "openable": openable,
                                        "sha256": hashlib.sha256(blob).hexdigest(), "url": path,
                                        "check": "JPEG SOI/EOI 头尾校验" if fmt == "jpeg" else "PNG 头校验"}
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
    (B20 / "shots_manifest.json").write_bytes(json.dumps(out, ensure_ascii=False, indent=1).encode())
    if SECRET.exists():
        SECRET.unlink()
    print(json.dumps({"wid": out.get("workorder_id"), "shots": list(out["shots"])}, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
