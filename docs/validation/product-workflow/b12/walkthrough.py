"""B12 界面全流程走查（隔离库 + 真实 HTTP + 截图）：新建自制商品 → 逐项录证据 → 6/1 → 409 → demo 平台 → 200。

记录“操作序列 + 每步响应码 + 详情页文案”，并截图（桌面新建表单/详情 6-1/可导出，手机详情）。
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

B12 = pathlib.Path(r"D:\桌面\two\docs\validation\product-workflow\b12")
SHOTS = B12 / "shots"
TMP = pathlib.Path(tempfile.mkdtemp(prefix="b12-walk-"))
DB, SECRET = TMP / "workflow.sqlite3", TMP / "secret"
PORT = 5020
BASE = f"http://127.0.0.1:{PORT}"
PY = pathlib.Path(r"D:\桌面\two\.venv\Scripts\python.exe")
ROOT = pathlib.Path(r"D:\桌面\two")
CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"

STEPS = [
    ("supply", {"selected_supply_id": "self:prompt-pack-v1", "supply_version": "v1"}),
    ("license", {"supply_license_commercial": "yes", "supply_license_redistribute": "yes",
                 "supply_license_resell": "yes"}),
    ("sample", {"sample_status": "verified", "sample_note": "自测：结构检查通过（非真实打开）"}),
    ("cost", {"cost_minor": "300", "cost_known": "yes"}),
    ("copy", {"copy_status": "final", "copy_version": "copy-v1", "selling_points": "第一条卖点\n第二条卖点",
              "price_minor": "1990", "delivery_note": "站内文件交付", "aftersales_note": "售后未定",
              "faq_json": json.dumps([{"q": "需要什么软件", "a": "任意文本编辑器"}], ensure_ascii=False)}),
]


def start() -> subprocess.Popen:
    env = dict(os.environ)
    env.update({"WORKBENCH_WORKFLOW_DB": str(DB), "WORKBENCH_SECRET_FILE": str(SECRET),
                "PYTHONUTF8": "1", "PYTHONDONTWRITEBYTECODE": "1"})
    proc = subprocess.Popen([str(PY), "-X", "utf8", "tools/workbench/run.py", "--port", str(PORT), "--no-browser"],
                            cwd=str(ROOT), env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(60):
        time.sleep(0.3)
        try:
            with urllib.request.urlopen(BASE + "/healthz", timeout=2) as r:
                if r.status == 200:
                    return proc
        except Exception:
            continue
    raise RuntimeError("server did not start")


def png_size(p: pathlib.Path):
    b = p.read_bytes()
    if b[:8] == b"\x89PNG\r\n\x1a\n":
        w, h = struct.unpack(">II", b[16:24])
        return w, h
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
(() => {
  const el = document.querySelector('section[aria-labelledby="h-ready"]');
  if (!el) { const f = document.querySelector('form'); return JSON.stringify({found:false,
    clip:{x:0,y:0,width:Math.min(document.documentElement.scrollWidth,1440),height:Math.min(900,innerHeight),scale:1}}); }
  const r = el.getBoundingClientRect();
  return JSON.stringify({found:true, clip:{x:Math.round(r.x+window.scrollX), y:Math.round(r.y+window.scrollY),
    width:Math.round(r.width), height:Math.round(r.height), scale:1},
    ok:(document.body.innerHTML.match(/chip chip-ok">通过/g)||[]).length,
    warn:(document.body.innerHTML.match(/chip chip-warn">未通过/g)||[]).length,
    hasExportLink: !!el.querySelector('a[href*="/export"]')});
})()
"""


def get(opener, path):
    try:
        with opener.open(BASE + path, timeout=15) as r:
            return r.status, r.read().decode("utf-8", "replace"), r.geturl()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace"), e.geturl()


def post(opener, path, data):
    body = urllib.parse.urlencode(data).encode()
    req = urllib.request.Request(BASE + path, data=body, method="POST")
    req.add_header("Content-Type", "application/x-www-form-urlencoded")
    try:
        with opener.open(req, timeout=15) as r:
            return r.status, r.read().decode("utf-8", "replace"), r.geturl()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace"), e.geturl()


def csrf_of(html: str) -> str:
    return re.search(r'name="csrf" value="([^"]+)"', html).group(1)


async def main() -> int:
    SHOTS.mkdir(parents=True, exist_ok=True)
    log: dict = {"generated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "port": PORT,
                 "db": str(DB), "ops": []}
    proc = start()
    try:
        opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
        s, html, _ = get(opener, "/worksheet/new")
        log["ops"].append({"op": "GET /worksheet/new", "status": s, "has_form": "新建自制商品" in html})
        s, _, url = post(opener, "/worksheet/new", {
            "csrf": csrf_of(html), "self_made": "1", "submit_key": "walk-selfmade-1",
            "name": "自制提示词包（走查）", "use_case": "会议纪要/周报", "deliverable": "纯文本 .md（10 条）",
            "target_platform": "xianyu", "fmt": "md", "language": "中文", "version": "v1"})
        wid = url.rsplit("/", 1)[-1].split("?")[0]
        log["workorder_id"] = wid
        log["ops"].append({"op": "POST /worksheet/new (self_made=1)", "status": s, "wid": wid,
                           "id_format_ok": bool(re.fullmatch(r"wo:\d{8}-[0-9a-f]{8}", wid))})

        for name, payload in STEPS:
            s0, page, _ = get(opener, f"/worksheet/{wid}")
            rev = re.search(r'name="revision" value="(\d+)"', page).group(1)
            s1, body, _ = post(opener, f"/worksheet/{wid}/evidence",
                               {"csrf": csrf_of(page), "revision": rev, **payload})
            s2, page2, _ = get(opener, f"/worksheet/{wid}")
            log["ops"].append({"op": f"POST evidence[{name}]", "status": s1, "revision_used": rev,
                               "ok_chips": page2.count('chip chip-ok">通过'),
                               "warn_chips": page2.count('chip chip-warn">未通过')})

        s3, blocked, _ = get(opener, f"/worksheet/{wid}/export?format=md")
        log["ops"].append({"op": "GET export (platform 空)", "status": s3,
                           "mentions_platform": "缺少目标平台条件证据" in blocked})

        s4, page, _ = get(opener, f"/worksheet/{wid}")
        rev = re.search(r'name="revision" value="(\d+)"', page).group(1)
        s5, _, _ = post(opener, f"/worksheet/{wid}/evidence",
                        {"csrf": csrf_of(page), "revision": rev,
                         "platform_evidence": "demo://b12/walkthrough-only"})
        s6, ok_json, _ = get(opener, f"/worksheet/{wid}/export?format=json")
        payload = json.loads(ok_json) if s6 == 200 else {}
        s7, page3, _ = get(opener, f"/worksheet/{wid}")
        s8 = None
        if s6 == 200:
            s8, _, _ = post(opener, f"/worksheet/{wid}/export/record",
                            {"csrf": csrf_of(page3), "format": "json"})
        log["ops"].append({"op": "POST evidence[platform demo]", "status": s5})
        log["ops"].append({"op": "GET export (demo 平台)", "status": s6,
                           "buyer_fields": payload.get("buyer_visible_fields"),
                           "seller_fields_absent": all(k not in json.dumps(payload) for k in
                                                       ("cost_minor", "supply_note", "raw_ref", "snapshot"))})
        log["ops"].append({"op": "POST export/record", "status": s8})

        # 另建一单只填 5 类证据（platform 留空）用于「6 通过 / 1 未通过」截图
        s9, page_new, _ = get(opener, "/worksheet/new")
        _, _, url2 = post(opener, "/worksheet/new", {
            "csrf": csrf_of(page_new), "self_made": "1", "submit_key": "walk-selfmade-2",
            "name": "自制提示词包（走查-未就绪）", "use_case": "会议纪要", "deliverable": "纯文本 .md（10 条）",
            "target_platform": "xianyu", "fmt": "md", "language": "中文", "version": "v1"})
        wid2 = url2.rsplit("/", 1)[-1].split("?")[0]
        for _name, payload in STEPS:
            _, page_i, _ = get(opener, f"/worksheet/{wid2}")
            rev_i = re.search(r'name="revision" value="(\d+)"', page_i).group(1)
            post(opener, f"/worksheet/{wid2}/evidence", {"csrf": csrf_of(page_i), "revision": rev_i, **payload})
        log["workorder_blocked"] = wid2

        # 截图
        browser = await uc.start(headless=True, browser_executable_path=CHROME,
                                 browser_args=["--hide-scrollbars", "--no-first-run"], sandbox=False)
        try:
            tab = await browser.get(BASE + "/worksheet/new")
            await asyncio.sleep(1.2)
            await tab.send(uc.cdp.emulation.set_device_metrics_override(
                width=1440, height=900, device_scale_factor=1, mobile=False, screen_width=1440, screen_height=900))
            await asyncio.sleep(0.5)
            out = SHOTS / "desktop_new_form.png"
            await tab.save_screenshot(str(out))
            shots = {out.name: {"width": png_size(out)[0], "height": png_size(out)[1],
                                "bytes": out.stat().st_size,
                                "sha256": hashlib.sha256(out.read_bytes()).hexdigest()}}

            async def shoot(name: str, wid_target: str, mobile: bool) -> None:
                if mobile:
                    await tab.send(uc.cdp.emulation.set_device_metrics_override(
                        width=390, height=844, device_scale_factor=1, mobile=True,
                        screen_width=390, screen_height=844))
                else:
                    await tab.send(uc.cdp.emulation.set_device_metrics_override(
                        width=1440, height=900, device_scale_factor=1, mobile=False,
                        screen_width=1440, screen_height=900))
                await tab.get(BASE + f"/worksheet/{wid_target}")
                await asyncio.sleep(1.4)
                info = json.loads(await tab.evaluate(JS, await_promise=False))
                clip = info["clip"]
                b64 = await tab.send(uc.cdp.page.capture_screenshot(
                    clip=uc.cdp.page.Viewport(x=clip["x"], y=clip["y"], width=clip["width"],
                                              height=clip["height"], scale=1),
                    capture_beyond_viewport=True))
                import base64
                p = SHOTS / f"{name}.png"
                p.write_bytes(base64.b64decode(b64))
                shots[p.name] = {"width": png_size(p)[0], "height": png_size(p)[1], "bytes": p.stat().st_size,
                                 "sha256": hashlib.sha256(p.read_bytes()).hexdigest(),
                                 "ok": info.get("ok"), "warn": info.get("warn"),
                                 "hasExportLink": info.get("hasExportLink")}

            await shoot("desktop_detail_6_1", wid2, mobile=False)
            await shoot("desktop_detail_ready", wid, mobile=False)
            await shoot("mobile_detail_ready", wid, mobile=True)
            log["shots"] = shots
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
    log["db_sha256"] = hashlib.sha256(DB.read_bytes()).hexdigest() if DB.exists() else None
    (B12 / "walkthrough.json").write_bytes(json.dumps(log, ensure_ascii=False, indent=1).encode())
    if SECRET.exists():
        SECRET.unlink()
    print(json.dumps({"wid": log["workorder_id"], "statuses": [o["status"] for o in log["ops"]],
                      "shots": list(log.get("shots", {}))}, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
