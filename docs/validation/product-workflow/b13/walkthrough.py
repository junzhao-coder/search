"""B13 闭环走查（隔离库，真实 HTTP）：版本历史/回滚、导出去重、发布回填与变更提示。"""

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

B13 = pathlib.Path(r"D:\桌面\two\docs\validation\product-workflow\b13")
SHOTS = B13 / "shots"
TMP = pathlib.Path(tempfile.mkdtemp(prefix="b13-walk-"))
DB, SECRET = TMP / "workflow.sqlite3", TMP / "secret"
PORT = 5021
BASE = f"http://127.0.0.1:{PORT}"
PY = pathlib.Path(r"D:\桌面\two\.venv\Scripts\python.exe")
ROOT = pathlib.Path(r"D:\桌面\two")
CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"

EVID = {
    "selected_supply_id": "self:pp-v1", "supply_version": "v1",
    "supply_license_commercial": "yes", "supply_license_redistribute": "yes", "supply_license_resell": "yes",
    "sample_status": "verified", "sample_note": "自测：结构检查通过（非真实打开）",
    "cost_minor": "300", "cost_known": "yes", "platform_evidence": "demo://b13/walkthrough-only",
    "copy_status": "final", "copy_version": "copy-v1", "selling_points": "卖点A\n卖点B",
    "price_minor": "1990", "delivery_note": "站内文件", "aftersales_note": "售后未定",
    "faq_json": json.dumps([{"q": "需要软件吗", "a": "不需要"}], ensure_ascii=False),
}
JS = """
(() => {
  const pick = (sel) => { const el = document.querySelector(sel); if (!el) return null;
    const r = el.getBoundingClientRect();
    return {x:Math.round(r.x+window.scrollX), y:Math.round(r.y+window.scrollY),
            width:Math.round(r.width), height:Math.round(r.height)}; };
  return JSON.stringify({copy: pick('section[aria-labelledby="h-copy"]'),
                         pub: pick('section[aria-labelledby="h-pub"]'),
                         bodyText: document.body.innerText.slice(0, 4000)});
})()
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
            with urllib.request.urlopen(BASE + "/healthz", timeout=2) as r:
                if r.status == 200:
                    return p
        except Exception:
            continue
    raise RuntimeError("no start")


def png_size(p: pathlib.Path):
    b = p.read_bytes()
    return struct.unpack(">II", b[16:24]) if b[:8] == b"\x89PNG\r\n\x1a\n" else (None, None)


def csrf(h: str) -> str:
    return re.search(r'name="csrf" value="([^"]+)"', h).group(1)


def req(opener, method, path, data=None):
    body = urllib.parse.urlencode(data).encode() if data else None
    r = urllib.request.Request(BASE + path, data=body, method=method)
    if body:
        r.add_header("Content-Type", "application/x-www-form-urlencoded")
    try:
        with opener.open(r, timeout=15) as resp:
            return resp.status, resp.read().decode("utf-8", "replace"), dict(resp.headers), resp.geturl()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace"), dict(e.headers), e.geturl()


async def main() -> int:
    SHOTS.mkdir(parents=True, exist_ok=True)
    log = {"generated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "port": PORT,
           "db": str(DB), "ops": []}
    proc = start()
    try:
        op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
        s, page, _, _ = req(op, "GET", "/worksheet/new")
        s, _, _, url = req(op, "POST", "/worksheet/new", {
            "csrf": csrf(page), "self_made": "1", "submit_key": "b13-walk-1",
            "name": "自制提示词包（B13 闭环）", "use_case": "会议纪要", "deliverable": "纯文本 .md（10 条）",
            "target_platform": "xianyu", "fmt": "md", "language": "中文", "version": "v1"})
        wid = url.rsplit("/", 1)[-1].split("?")[0]
        log["workorder_id"] = wid
        log["ops"].append({"op": "POST /worksheet/new", "status": s, "wid": wid,
                           "id_ok": bool(re.fullmatch(r"wo:\d{8}-[0-9a-f]{8}", wid))})

        s, page, _, _ = req(op, "GET", f"/worksheet/{wid}")
        rev = re.search(r'name="revision" value="(\d+)"', page).group(1)
        s, _, _, _ = req(op, "POST", f"/worksheet/{wid}/evidence", {"csrf": csrf(page), "revision": rev, **EVID})
        log["ops"].append({"op": "POST evidence（七项 + demo 平台）", "status": s})

        s, page, _, _ = req(op, "GET", f"/worksheet/{wid}")
        log["ops"].append({"op": "GET detail", "status": s,
                           "ok_chips": page.count('chip chip-ok">通过'),
                           "warn_chips": page.count('chip chip-warn">未通过'),
                           "has_copy_section": "文案版本历史" in page, "has_pub_section": "发布回填" in page})

        s, _, _, _ = req(op, "GET", f"/worksheet/{wid}/export?format=md")
        log["ops"].append({"op": "GET export（预览，零写）", "status": s})

        s1, _, h1, _ = req(op, "POST", f"/worksheet/{wid}/export/record", {"csrf": csrf(page), "format": "md"})
        s2, _, h2, _ = req(op, "POST", f"/worksheet/{wid}/export/record", {"csrf": csrf(page), "format": "md"})
        log["ops"].append({"op": "POST export/record 首次", "status": s1, "dedup": h1.get("X-WB-Deduplicated")})
        log["ops"].append({"op": "POST export/record 重复", "status": s2, "dedup": h2.get("X-WB-Deduplicated")})

        s, page, _, _ = req(op, "GET", f"/worksheet/{wid}")
        s, _, _, _ = req(op, "POST", f"/worksheet/{wid}/publish", {
            "csrf": csrf(page), "status": "已发布", "published_url": "https://example.com/item/b13",
            "published_at": "2026-10-23T14:40:00Z", "sold_count": "0", "platform_note": "走查记录"})
        log["ops"].append({"op": "POST publish（已发布）", "status": s})

        s, page, _, _ = req(op, "GET", f"/worksheet/{wid}")
        rev = re.search(r'name="revision" value="(\d+)"', page).group(1)
        s, _, _, _ = req(op, "POST", f"/worksheet/{wid}/evidence",
                         {"csrf": csrf(page), "revision": rev, "copy_version": "copy-v2",
                          "selling_points": "卖点A\n卖点B\n卖点C（改版）"})
        log["ops"].append({"op": "POST evidence（改文案 → 新版本）", "status": s})

        s, page2, _, _ = req(op, "GET", f"/worksheet/{wid}")
        log["ops"].append({"op": "GET detail（改文案后）", "status": s,
                           "stale": "已失效" in page2, "publish_changed": "发布信息已变更" in page2,
                           "versions": page2.count("回滚到此版本")})

        s3, _, h3, _ = req(op, "POST", f"/worksheet/{wid}/export/record", {"csrf": csrf(page2), "format": "md"})
        log["ops"].append({"op": "POST export/record（新版本戳）", "status": s3, "dedup": h3.get("X-WB-Deduplicated")})

        # 回滚到 v1 → 生成 v3
        s, page3, _, _ = req(op, "GET", f"/worksheet/{wid}")
        rev = re.search(r'name="revision" value="(\d+)"', page3).group(1)
        s, _, _, _ = req(op, "POST", f"/worksheet/{wid}/copy/rollback",
                         {"csrf": csrf(page3), "revision": rev, "version_no": "1"})
        s, page4, _, _ = req(op, "GET", f"/worksheet/{wid}")
        log["ops"].append({"op": "POST copy/rollback v1", "status": s,
                           "rollback_versions": page4.count("rollback:v1")})

        browser = await uc.start(headless=True, browser_executable_path=CHROME,
                                 browser_args=["--hide-scrollbars", "--no-first-run"], sandbox=False)
        shots = {}
        try:
            tab = await browser.get(BASE + f"/worksheet/{wid}")
            await asyncio.sleep(1.5)
            await tab.send(uc.cdp.emulation.set_device_metrics_override(
                width=1440, height=900, device_scale_factor=1, mobile=False, screen_width=1440, screen_height=900))
            await asyncio.sleep(0.5)
            info = json.loads(await tab.evaluate(JS, await_promise=False))
            import base64
            for key, name in (("copy", "desktop_copy_history"), ("pub", "desktop_publish")):
                c = info.get(key)
                if not c:
                    continue
                b64 = await tab.send(uc.cdp.page.capture_screenshot(
                    clip=uc.cdp.page.Viewport(x=c["x"], y=c["y"], width=c["width"],
                                              height=min(c["height"], 1200), scale=1),
                    capture_beyond_viewport=True))
                p = SHOTS / f"{name}.png"
                p.write_bytes(base64.b64decode(b64))
                shots[p.name] = {"width": png_size(p)[0], "height": png_size(p)[1],
                                 "bytes": p.stat().st_size,
                                 "sha256": hashlib.sha256(p.read_bytes()).hexdigest()}
            log["page_text_sample"] = [ln for ln in info.get("bodyText", "").splitlines()
                                       if any(k in ln for k in ("已失效", "发布信息已变更", "文案版本历史", "发布回填",
                                                                "回滚到此版本"))][:8]
        finally:
            try:
                browser.stop()
            except Exception:
                pass
        log["shots"] = shots
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()

    import sqlite3
    conn = sqlite3.connect(DB)
    try:
        log["counts"] = {t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
                         for t in ("workorder_export", "workorder_copy_version", "workorder_publish")}
        log["versions"] = [r[0] for r in conn.execute(
            "SELECT version_no FROM workorder_copy_version ORDER BY version_no").fetchall()]
    finally:
        conn.close()
    log["db_sha256"] = hashlib.sha256(DB.read_bytes()).hexdigest()
    (B13 / "walkthrough.json").write_bytes(json.dumps(log, ensure_ascii=False, indent=1).encode())
    if SECRET.exists():
        SECRET.unlink()
    print(json.dumps({"wid": wid, "ops": [(o["op"], o["status"]) for o in log["ops"]],
                      "counts": log["counts"], "versions": log["versions"], "shots": list(log.get("shots", {}))},
                     ensure_ascii=True))
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
