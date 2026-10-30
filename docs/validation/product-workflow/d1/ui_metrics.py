"""D1：界面核对（隔离库、真实 HTTP）：三栏仅三项、继续区块可回到该单、两视口无横向溢出、无/无效 wo 提示。"""

from __future__ import annotations

import asyncio
import http.cookiejar
import json
import os
import pathlib
import re
import subprocess
import sys
import tempfile
import time
import urllib.parse
import urllib.request

import nodriver as uc

D1 = pathlib.Path(r"D:\桌面\two\docs\validation\product-workflow\d1")
TMP = pathlib.Path(tempfile.mkdtemp(prefix="d1-ui-"))
DB, SECRET = TMP / "w.db", TMP / "s"
PORT, BASE = 5026, "http://127.0.0.1:5026"
PY = pathlib.Path(r"D:\桌面\two\.venv\Scripts\python.exe")
ROOT = pathlib.Path(r"D:\桌面\two")
CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
NAME = "[SYNTHETIC] D1 UI 核对单"

MEASURE = """
(() => { const de = document.documentElement;
  return JSON.stringify({innerW: window.innerWidth, innerH: window.innerHeight,
    scrollW: de.scrollWidth, scrollH: de.scrollHeight,
    overflowX: de.scrollWidth > window.innerWidth + 1}); })()
"""


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


async def main() -> int:
    out: dict = {"generated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "port": PORT,
                 "db": str(DB), "pages": {}, "probes": {}}
    proc = start()
    try:
        op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))

        def req(method, path, data=None):
            body = urllib.parse.urlencode(data).encode() if data else None
            r = urllib.request.Request(BASE + path, data=body, method=method)
            if body:
                r.add_header("Content-Type", "application/x-www-form-urlencoded")
            try:
                with op.open(r, timeout=15) as resp:
                    return resp.status, resp.read().decode("utf-8", "replace")
            except urllib.error.HTTPError as e:
                return e.code, e.read().decode("utf-8", "replace")

        _, page = req("GET", "/worksheet/new")
        csrf = re.search(r'name="csrf" value="([^"]+)"', page).group(1)
        req("POST", "/worksheet/new", {"csrf": csrf, "self_made": "1", "submit_key": "d1-ui",
                                       "name": NAME, "use_case": "学习计划", "deliverable": "Excel .xlsx",
                                       "target_platform": "xianyu"})
        _, pick = req("GET", "/pick")
        m = re.search(r'href="/source\?wo=(wo:\d{8}-[0-9a-f]{8})"', pick)
        wid = m.group(1) if m else ""
        out["workorder_id"] = wid
        out["probes"]["continue_block_present"] = "继续已有工作单" in pick
        out["probes"]["continue_links_to_wo"] = bool(wid and f"/source?wo={wid}" in pick and f"/copy?wo={wid}" in pick)
        s_no_wo, body_no_wo = req("GET", "/source")
        out["probes"]["source_no_wo"] = {"status": s_no_wo, "has_hint": ("还没有" in body_no_wo or "请先" in body_no_wo)}
        s_bad, body_bad = req("GET", "/copy?wo=wo:deadbeef")
        out["probes"]["copy_invalid_wo"] = {"status": s_bad, "has_hint": ("不存在" in body_bad or "not_found" in body_bad)}
        s_root, _ = req("GET", "/")
        out["probes"]["root"] = {"status": s_root}

        browser = await uc.start(headless=True, browser_executable_path=CHROME,
                                 browser_args=["--hide-scrollbars", "--no-first-run"], sandbox=False)
        try:
            tab = await browser.get(BASE + "/pick")
            await asyncio.sleep(1.4)
            for label, width, height, mobile in (("desktop", 1440, 900, False), ("mobile", 390, 844, True)):
                await tab.send(uc.cdp.emulation.set_device_metrics_override(
                    width=width, height=height, device_scale_factor=1, mobile=mobile,
                    screen_width=width, screen_height=height))
                await asyncio.sleep(0.4)
                for path in ("/pick", f"/source?wo={wid}", f"/copy?wo={wid}"):
                    await tab.get(BASE + path)
                    await asyncio.sleep(1.1)
                    metrics = json.loads(await tab.evaluate(MEASURE, await_promise=False))
                    labels = await tab.evaluate(
                        "JSON.stringify([...document.querySelectorAll('nav[aria-label=\"主导航\"] "
                        ".nav-label')].map(e => e.textContent.trim()))", await_promise=False)
                    out["pages"][f"{label} {path}"] = {**metrics, "nav_labels": json.loads(labels)}
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
    (D1 / "ui.json").write_bytes(json.dumps(out, ensure_ascii=False, indent=1).encode())
    if SECRET.exists():
        SECRET.unlink()
    print(json.dumps({"wo": out.get("workorder_id"), "probes": out["probes"],
                      "overflow_any": any(p["overflowX"] for p in out["pages"].values())}, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
