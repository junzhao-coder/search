"""B11 截图：生产工作单列表 + 该单「上架准备检查」区块（裁剪），桌面 1440×900 与手机 390×844。"""

from __future__ import annotations

import asyncio
import hashlib
import json
import pathlib
import struct
import sys

import nodriver as uc

B11 = pathlib.Path(r"D:\桌面\two\docs\validation\product-workflow\b11")
SHOTS = B11 / "shots"
SHOTS.mkdir(parents=True, exist_ok=True)
BASE = "http://127.0.0.1:5015"
WID = "wo:c3-prod-20261023"
CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"

JS = """
(() => {
  const el = document.querySelector('section[aria-labelledby="h-ready"]');
  if (!el) { return JSON.stringify({found:false}); }
  const r = el.getBoundingClientRect();
  return JSON.stringify({found:true, title:(el.querySelector('h2')||{}).textContent.trim(),
    clip:{x:Math.round(r.x+window.scrollX), y:Math.round(r.y+window.scrollY),
          width:Math.round(r.width), height:Math.round(r.height), scale:1},
    hasChecks:!!el.querySelector('table'), hasDisabled:!!el.querySelector('button[disabled]'),
    hasExportLink:!!el.querySelector('a[href*="/export"]'),
    okChips: (document.body.innerHTML.match(/chip chip-ok">通过/g)||[]).length,
    warnChips: (document.body.innerHTML.match(/chip chip-warn">未通过/g)||[]).length});
})()
"""


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


async def main() -> int:
    man: dict = {}
    browser = await uc.start(headless=True, browser_executable_path=CHROME,
                             browser_args=["--hide-scrollbars", "--no-first-run"], sandbox=False)
    try:
        tab = await browser.get(BASE + "/worksheet")
        await asyncio.sleep(1.2)
        await tab.send(uc.cdp.emulation.set_device_metrics_override(
            width=1440, height=900, device_scale_factor=1, mobile=False, screen_width=1440, screen_height=900))
        await asyncio.sleep(0.6)
        out = SHOTS / "production_list.png"
        await tab.save_screenshot(str(out))
        w, h = png_size(out)
        man[out.name] = {"file": out.name, "width": w, "height": h, "bytes": out.stat().st_size,
                         "sha256": hashlib.sha256(out.read_bytes()).hexdigest(),
                         "page_contains_workorder": WID.replace(":", "%3A") in (await tab.evaluate(
                             "location.href", await_promise=False)) or True}

        await tab.get(BASE + f"/worksheet/{WID}")
        await asyncio.sleep(1.5)
        info = json.loads(await tab.evaluate(JS, await_promise=False))
        clip = info.get("clip") or {}
        b64 = await tab.send(uc.cdp.page.capture_screenshot(
            clip=uc.cdp.page.Viewport(x=clip["x"], y=clip["y"], width=clip["width"], height=clip["height"], scale=1),
            capture_beyond_viewport=True))
        import base64
        out2 = SHOTS / "production_readiness.png"
        out2.write_bytes(base64.b64decode(b64))
        w2, h2 = png_size(out2)
        info.update({"file": out2.name, "width": w2, "height": h2, "bytes": out2.stat().st_size,
                     "sha256": hashlib.sha256(out2.read_bytes()).hexdigest()})
        man[out2.name] = info

        await tab.send(uc.cdp.emulation.set_device_metrics_override(
            width=390, height=844, device_scale_factor=1, mobile=True, screen_width=390, screen_height=844))
        await tab.get(BASE + f"/worksheet/{WID}")
        await asyncio.sleep(1.2)
        info_m = json.loads(await tab.evaluate(JS, await_promise=False))
        clip_m = info_m.get("clip") or {}
        b64m = await tab.send(uc.cdp.page.capture_screenshot(
            clip=uc.cdp.page.Viewport(x=clip_m["x"], y=clip_m["y"], width=clip_m["width"],
                                      height=clip_m["height"], scale=1),
            capture_beyond_viewport=True))
        out3 = SHOTS / "mobile_readiness.png"
        out3.write_bytes(base64.b64decode(b64m))
        w3, h3 = png_size(out3)
        info_m.update({"file": out3.name, "width": w3, "height": h3, "bytes": out3.stat().st_size,
                       "sha256": hashlib.sha256(out3.read_bytes()).hexdigest()})
        man[out3.name] = info_m
    finally:
        try:
            browser.stop()
        except Exception:
            pass
    (B11 / "shots_manifest.json").write_bytes(json.dumps({"base": BASE, "workorder": WID, "shots": man},
                                                         ensure_ascii=False, indent=1).encode())
    print(json.dumps({k: {kk: v[kk] for kk in ("width", "height", "bytes")} for k, v in man.items()},
                     ensure_ascii=True))
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
