"""B22：/pick 顶部“继续已有工作单”截图（隔离库造 2 条示例单，桌面 1440×900）。"""

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

B22 = pathlib.Path(r"D:\桌面\two\docs\validation\product-workflow\b22")
SHOTS = B22 / "shots"
TMP = pathlib.Path(tempfile.mkdtemp(prefix="b22-shots-"))
DB, SECRET = TMP / "w.db", TMP / "s"
PORT, BASE = 5026, "http://127.0.0.1:5026"
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

        ids = []
        for i, (name, use) in enumerate((("示例单 A：学习计划 Excel", "学习计划"), ("示例单 B：自制提示词包", "会议纪要")), 1):
            _, page, _ = req("GET", "/worksheet/new")
            csrf = re.search(r'name="csrf" value="([^"]+)"', page).group(1)
            _, _, url = req("POST", "/worksheet/new", {
                "csrf": csrf, "self_made": "1", "submit_key": f"b22-shot-{i}",
                "name": name, "use_case": use, "deliverable": "纯文本 .md", "target_platform": "xianyu"})
            ids.append(url.rsplit("/", 1)[-1].split("?")[0])
        out["workorder_ids"] = ids

        browser = await uc.start(headless=True, browser_executable_path=CHROME,
                                 browser_args=["--hide-scrollbars", "--no-first-run"], sandbox=False)
        try:
            tab = await browser.get(BASE + "/pick")
            await asyncio.sleep(1.5)
            await tab.send(uc.cdp.emulation.set_device_metrics_override(
                width=1440, height=900, device_scale_factor=1, mobile=False, screen_width=1440, screen_height=900))
            await asyncio.sleep(0.6)
            p = SHOTS / "pick_continue_block.jpg"
            await tab.save_screenshot(str(p))
            w, h = size(p)
            blob = p.read_bytes()
            out["shots"][p.name] = {"width": w, "height": h, "bytes": p.stat().st_size, "url": "/pick",
                                    "format": "jpeg",
                                    "openable": blob[:3] == b"\xff\xd8\xff" and blob.rstrip().endswith(b"\xff\xd9"),
                                    "sha256": hashlib.sha256(blob).hexdigest()}
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
    (B22 / "shots_manifest.json").write_bytes(json.dumps(out, ensure_ascii=False, indent=1).encode())
    if SECRET.exists():
        SECRET.unlink()
    print(json.dumps({"ids": out.get("workorder_ids"), "shots": list(out["shots"])}, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
