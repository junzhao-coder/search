"""B15：生产单页面截图（迁移后两区块可见）+ 重复记录 dedup 实测（隔离库）。"""

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

B15 = pathlib.Path(r"D:\桌面\two\docs\validation\product-workflow\b15")
SHOTS = B15 / "shots"
SHOTS.mkdir(parents=True, exist_ok=True)
PROD = "http://127.0.0.1:5015"
WID = "wo:20261023-88ef9a66"
CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
PY = pathlib.Path(r"D:\桌面\two\.venv\Scripts\python.exe")
ROOT = pathlib.Path(r"D:\桌面\two")

JS = """
(() => {
  const g = (sel) => { const el = document.querySelector(sel); if (!el) return null;
    const r = el.getBoundingClientRect();
    return {x:Math.round(r.x+window.scrollX), y:Math.round(r.y+window.scrollY),
            w:Math.round(r.width), h:Math.round(r.height)}; };
  return JSON.stringify({copy:g('section[aria-labelledby=\"h-copy\"]'), pub:g('section[aria-labelledby=\"h-pub\"]'),
    text:document.body.innerText});
})()
"""

EVID = {
    "selected_supply_id": "self:pp-v1", "supply_version": "v1",
    "supply_license_commercial": "yes", "supply_license_redistribute": "yes", "supply_license_resell": "yes",
    "sample_status": "verified", "sample_note": "自测", "cost_minor": "300", "cost_known": "yes",
    "platform_evidence": "demo://b15/dedupe", "copy_status": "final", "copy_version": "copy-v1",
    "selling_points": "A", "price_minor": "1990", "delivery_note": "站内", "aftersales_note": "未定",
    "faq_json": "[]",
}


def png_size(p: pathlib.Path):
    b = p.read_bytes()
    return struct.unpack(">II", b[16:24]) if b[:8] == b"\x89PNG\r\n\x1a\n" else (None, None)


def csrf(h: str) -> str:
    return re.search(r'name="csrf" value="([^"]+)"', h).group(1)


def req(opener, method, base, path, data=None):
    body = urllib.parse.urlencode(data).encode() if data else None
    r = urllib.request.Request(base + path, data=body, method=method)
    if body:
        r.add_header("Content-Type", "application/x-www-form-urlencoded")
    try:
        with opener.open(r, timeout=15) as resp:
            return resp.status, resp.read().decode("utf-8", "replace"), dict(resp.headers), resp.geturl()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace"), dict(e.headers), e.geturl()


async def main() -> int:
    out: dict = {"generated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    # 1) 生产单截图（5015）
    browser = await uc.start(headless=True, browser_executable_path=CHROME,
                             browser_args=["--hide-scrollbars", "--no-first-run"], sandbox=False)
    shots = {}
    try:
        tab = await browser.get(f"{PROD}/worksheet/{WID}")
        await asyncio.sleep(1.6)
        await tab.send(uc.cdp.emulation.set_device_metrics_override(
            width=1440, height=900, device_scale_factor=1, mobile=False, screen_width=1440, screen_height=900))
        await asyncio.sleep(0.5)
        info = json.loads(await tab.evaluate(JS, await_promise=False))
        import base64
        for key, name in (("copy", "prod_copy_history"), ("pub", "prod_publish")):
            c = info.get(key)
            if not c:
                continue
            b64 = await tab.send(uc.cdp.page.capture_screenshot(
                clip=uc.cdp.page.Viewport(x=c["x"], y=c["y"], width=c["w"], height=min(c["h"], 1200), scale=1),
                capture_beyond_viewport=True))
            p = SHOTS / f"{name}.png"
            p.write_bytes(base64.b64decode(b64))
            shots[p.name] = {"width": png_size(p)[0], "height": png_size(p)[1],
                             "bytes": p.stat().st_size, "sha256": hashlib.sha256(p.read_bytes()).hexdigest()}
        out["prod_page"] = {"has_copy": "文案版本历史" in info["text"], "has_publish": "发布回填" in info["text"],
                            "text_sample": [ln for ln in info["text"].splitlines()
                                            if any(k in ln for k in ("文案版本历史", "发布回填", "上次导出"))][:5]}
    finally:
        try:
            browser.stop()
        except Exception:
            pass

    # 2) 隔离库：重复记录 dedup 实测（HTTP）
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="b15-dedup-"))
    db, secret = tmp / "w.db", tmp / "s"
    env = dict(os.environ)
    env.update({"WORKBENCH_WORKFLOW_DB": str(db), "WORKBENCH_SECRET_FILE": str(secret),
                "PYTHONUTF8": "1", "PYTHONDONTWRITEBYTECODE": "1"})
    port = 5022
    base = f"http://127.0.0.1:{port}"
    proc = subprocess.Popen([str(PY), "-X", "utf8", "tools/workbench/run.py", "--port", str(port), "--no-browser"],
                            cwd=str(ROOT), env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(60):
            time.sleep(0.3)
            try:
                with urllib.request.urlopen(base + "/healthz", timeout=2):
                    break
            except Exception:
                continue
        op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
        _, page, _, _ = req(op, "GET", base, "/worksheet/new")
        _, _, _, url = req(op, "POST", base, "/worksheet/new", {
            "csrf": csrf(page), "self_made": "1", "submit_key": "b15-dedup",
            "name": "去重实测单", "use_case": "测试", "deliverable": "文本", "target_platform": "xianyu"})
        wid = url.rsplit("/", 1)[-1].split("?")[0]
        _, page, _, _ = req(op, "GET", base, f"/worksheet/{wid}")
        rev = re.search(r'name="revision" value="(\d+)"', page).group(1)
        req(op, "POST", base, f"/worksheet/{wid}/evidence", {"csrf": csrf(page), "revision": rev, **EVID})
        s1, _, h1, _ = req(op, "POST", base, f"/worksheet/{wid}/export/record", {"csrf": csrf(page), "format": "md"})
        s2, _, h2, _ = req(op, "POST", base, f"/worksheet/{wid}/export/record", {"csrf": csrf(page), "format": "md"})
        with __import__("sqlite3").connect(db) as conn:
            rows = conn.execute("SELECT COUNT(*) FROM workorder_export").fetchone()[0]
            idx = [r[1] for r in conn.execute("PRAGMA index_list(workorder_export)").fetchall()]
        out["dedupe"] = {"first": {"status": s1, "dedup": h1.get("X-WB-Deduplicated")},
                         "second": {"status": s2, "dedup": h2.get("X-WB-Deduplicated")},
                         "rows": rows, "indexes": idx}
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
        if secret.exists():
            secret.unlink()
    out["shots"] = shots
    (B15 / "walkthrough.json").write_bytes(json.dumps(out, ensure_ascii=False, indent=1).encode())
    print(json.dumps({k: out[k] for k in ("prod_page", "dedupe", "shots")}, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
