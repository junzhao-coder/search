"""B16 全流程走查（隔离库，真实 HTTP）：候选×2 → 采用 1 条 → b7 样品自检 → 成本/文案 → 6/1 → demo 平台 → 导出。"""

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

B16 = pathlib.Path(r"D:\桌面\two\docs\validation\product-workflow\b16")
SHOTS = B16 / "shots"
TMP = pathlib.Path(tempfile.mkdtemp(prefix="b16-walk-"))
DB, SECRET = TMP / "w.db", TMP / "s"
PORT, BASE = 5023, "http://127.0.0.1:5023"
PY = pathlib.Path(r"D:\桌面\two\.venv\Scripts\python.exe")
ROOT = pathlib.Path(r"D:\桌面\two")
CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
SAMPLE = "docs/validation/product-workflow/b7/sample-study-planner-v1.xlsx"
JS = """
(() => { const g=(s)=>{const e=document.querySelector(s); if(!e) return null; const r=e.getBoundingClientRect();
  return {x:Math.round(r.x+window.scrollX),y:Math.round(r.y+window.scrollY),w:Math.round(r.width),h:Math.round(r.height)};};
  return JSON.stringify({sup:g('section[aria-labelledby="h-supply"]'), smp:g('section[aria-labelledby="h-sample"]'),
    ok:(document.body.innerHTML.match(/chip chip-ok">通过/g)||[]).length,
    warn:(document.body.innerHTML.match(/chip chip-warn">未通过/g)||[]).length}); })()
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


def png_size(p):
    b = p.read_bytes()
    return struct.unpack(">II", b[16:24]) if b[:8] == b"\x89PNG\r\n\x1a\n" else (None, None)


def csrf(h):
    return re.search(r'name="csrf" value="([^"]+)"', h).group(1)


def rev_of(h):
    m = re.search(r'name="revision" value="(\d+)"', h)
    return m.group(1) if m else "1"


def req(op, method, path, data=None):
    body = urllib.parse.urlencode(data).encode() if data else None
    r = urllib.request.Request(BASE + path, data=body, method=method)
    if body:
        r.add_header("Content-Type", "application/x-www-form-urlencoded")
    try:
        with op.open(r, timeout=15) as resp:
            return resp.status, resp.read().decode("utf-8", "replace"), dict(resp.headers), resp.geturl()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace"), dict(e.headers), e.geturl()


async def main() -> int:
    SHOTS.mkdir(parents=True, exist_ok=True)
    log = {"generated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "port": PORT, "db": str(DB),
           "ops": []}
    proc = start()
    try:
        op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
        _, page, _, _ = req(op, "GET", "/worksheet/new")
        _, _, _, url = req(op, "POST", "/worksheet/new", {
            "csrf": csrf(page), "self_made": "1", "submit_key": "b16-walk",
            "name": "自制提示词包（B16 走查）", "use_case": "会议纪要", "deliverable": "纯文本 .md",
            "target_platform": "xianyu", "fmt": "md"})
        wid = url.rsplit("/", 1)[-1].split("?")[0]
        log["workorder_id"] = wid
        log["ops"].append({"op": "POST /worksheet/new", "status": 200, "wid": wid,
                           "id_ok": bool(re.fullmatch(r"wo:\d{8}-[0-9a-f]{8}", wid))})

        for i, kind in enumerate(("同款", "替代"), start=1):
            s, page, _, _ = req(op, "GET", f"/worksheet/{wid}")
            s, _, _, _ = req(op, "POST", f"/worksheet/{wid}/supply/candidates", {
                "csrf": csrf(page), "provider": f"来源{i}", "source_url": f"self:pp-source-{i}",
                "kind": kind, "commercial": "yes", "redistribute": "yes", "resale": "yes",
                "license_note": "作者自持", "price_minor": "0", "note": "走查候选"})
            log["ops"].append({"op": f"POST 新增候选 {i}", "status": s})

        s, page, _, _ = req(op, "GET", f"/worksheet/{wid}")
        cids = re.findall(r'name="candidate_id" value="(sc:[0-9a-f]{8})"', page)
        log["candidates"] = cids
        s, _, _, _ = req(op, "POST", f"/worksheet/{wid}/supply/select",
                         {"csrf": csrf(page), "revision": rev_of(page), "candidate_id": cids[0]})
        rec_page = req(op, "GET", f"/worksheet/{wid}")[1]
        log["ops"].append({"op": "POST 采用第 1 条候选", "status": s,
                           "selected_shown": cids[0] in rec_page})

        s, page, _, _ = req(op, "GET", f"/worksheet/{wid}")
        s, _, _, _ = req(op, "POST", f"/worksheet/{wid}/sample/check",
                         {"csrf": csrf(page), "revision": rev_of(page), "path": SAMPLE})
        log["ops"].append({"op": "POST 样品自检（b7 xlsx）", "status": s})

        s, page, _, _ = req(op, "GET", f"/worksheet/{wid}")
        s, _, _, _ = req(op, "POST", f"/worksheet/{wid}/evidence", {
            "csrf": csrf(page), "revision": rev_of(page),
            "cost_minor": "300", "cost_known": "yes", "copy_status": "final", "copy_version": "copy-v1",
            "selling_points": "卖点A\n卖点B", "price_minor": "1990", "delivery_note": "站内文件",
            "aftersales_note": "售后未定", "faq_json": "[]"})
        s, page, _, _ = req(op, "GET", f"/worksheet/{wid}")
        log["ops"].append({"op": "POST 成本与文案", "status": s,
                           "ok": page.count('chip chip-ok">通过'), "warn": page.count('chip chip-warn">未通过')})
        log["blocked_export"] = req(op, "GET", f"/worksheet/{wid}/export?format=md")[0]

        s, _, _, _ = req(op, "POST", f"/worksheet/{wid}/evidence", {
            "csrf": csrf(page), "revision": rev_of(page),
            "platform_evidence": "demo://b16/walkthrough-only"})
        s2, body, _, _ = req(op, "GET", f"/worksheet/{wid}/export?format=json")
        payload = json.loads(body) if s2 == 200 else {}
        log["ops"].append({"op": "POST demo 平台 + GET 导出", "status": f"{s}/{s2}",
                           "buyer_fields": payload.get("buyer_visible_fields"),
                           "no_internal": all(k not in json.dumps(payload) for k in
                                              ("cost_minor", "supply_note", "raw_ref", "snapshot"))})

        browser = await uc.start(headless=True, browser_executable_path=CHROME,
                                 browser_args=["--hide-scrollbars", "--no-first-run"], sandbox=False)
        shots = {}
        try:
            tab = await browser.get(BASE + f"/worksheet/{wid}")
            await asyncio.sleep(1.6)
            await tab.send(uc.cdp.emulation.set_device_metrics_override(
                width=1440, height=900, device_scale_factor=1, mobile=False, screen_width=1440, screen_height=900))
            await asyncio.sleep(0.5)
            info = json.loads(await tab.evaluate(JS, await_promise=False))
            import base64
            for key, name in (("sup", "desktop_supply_candidates"), ("smp", "desktop_sample_check")):
                c = info.get(key)
                if not c:
                    continue
                b64 = await tab.send(uc.cdp.page.capture_screenshot(
                    clip=uc.cdp.page.Viewport(x=c["x"], y=c["y"], width=c["w"], height=min(c["h"], 1400), scale=1),
                    capture_beyond_viewport=True))
                p = SHOTS / f"{name}.png"
                p.write_bytes(base64.b64decode(b64))
                shots[p.name] = {"width": png_size(p)[0], "height": png_size(p)[1], "bytes": p.stat().st_size,
                                 "sha256": hashlib.sha256(p.read_bytes()).hexdigest()}
            log["page_state"] = {"ok": info.get("ok"), "warn": info.get("warn")}
            await tab.send(uc.cdp.emulation.set_device_metrics_override(
                width=390, height=844, device_scale_factor=1, mobile=True, screen_width=390, screen_height=844))
            await tab.get(BASE + f"/worksheet/{wid}")
            await asyncio.sleep(1.2)
            info_m = json.loads(await tab.evaluate(JS, await_promise=False))
            c = info_m.get("sup")
            if c:
                b64 = await tab.send(uc.cdp.page.capture_screenshot(
                    clip=uc.cdp.page.Viewport(x=c["x"], y=c["y"], width=c["w"], height=min(c["h"], 1400), scale=1),
                    capture_beyond_viewport=True))
                p = SHOTS / "mobile_supply_candidates.png"
                p.write_bytes(base64.b64decode(b64))
                shots[p.name] = {"width": png_size(p)[0], "height": png_size(p)[1], "bytes": p.stat().st_size,
                                 "sha256": hashlib.sha256(p.read_bytes()).hexdigest()}
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
                         for t in ("workorder_supply_candidate", "workorder_event")}
        row = conn.execute("SELECT selected_supply_id, sample_status, supply_version FROM workorder").fetchone()
        log["record"] = {"selected_supply_id": row[0], "sample_status": row[1], "supply_version": row[2]}
    finally:
        conn.close()
    log["db_sha256"] = hashlib.sha256(DB.read_bytes()).hexdigest()
    (B16 / "walkthrough.json").write_bytes(json.dumps(log, ensure_ascii=False, indent=1).encode())
    if SECRET.exists():
        SECRET.unlink()
    print(json.dumps({"wid": wid, "ops": [(o["op"], str(o["status"])) for o in log["ops"]],
                      "record": log["record"], "counts": log["counts"], "blocked_export": log["blocked_export"],
                      "shots": list(log.get("shots", {}))}, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
