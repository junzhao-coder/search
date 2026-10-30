"""B24：/copy 页“发布回填”区与发布卡指引截图（对线上 5015 只读拍摄）。"""

from __future__ import annotations

import asyncio
import hashlib
import json
import pathlib
import struct
import sys
import time

import nodriver as uc

B24 = pathlib.Path(r"D:\桌面\two\docs\validation\product-workflow\b24")
SHOTS = B24 / "shots"
SHOTS.mkdir(parents=True, exist_ok=True)
URL = "http://127.0.0.1:5015/copy?wo=wo:20261023-88ef9a66"
CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"


def jpeg_size(path: pathlib.Path):
    data = path.read_bytes()
    i = 2
    while i < len(data) - 9:
        if data[i] != 0xFF:
            i += 1
            continue
        marker = data[i + 1]
        if marker in (0xC0, 0xC1, 0xC2, 0xC3):
            h, w = struct.unpack(">HH", data[i + 5 : i + 9])
            return w, h
        i += 2 + struct.unpack(">H", data[i + 2 : i + 4])[0]
    return None, None


async def main() -> int:
    browser = await uc.start(headless=True, browser_executable_path=CHROME,
                             browser_args=["--hide-scrollbars", "--no-first-run"], sandbox=False)
    out: dict = {"generated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "url": URL, "shots": {}}
    try:
        tab = await browser.get(URL)
        await asyncio.sleep(1.6)
        await tab.send(uc.cdp.emulation.set_device_metrics_override(
            width=1440, height=900, device_scale_factor=1, mobile=False, screen_width=1440, screen_height=900))
        await asyncio.sleep(0.6)
        await tab.evaluate("(() => { const hs=[...document.querySelectorAll('h3')];"
                           " const h = hs.find(x => x.textContent.includes('发布回填'));"
                           " if (h) h.scrollIntoView({block:'center'}); })()")
        await asyncio.sleep(0.7)
        p = SHOTS / "copy_publish_guide.jpg"
        await tab.save_screenshot(str(p))
        w, h = jpeg_size(p)
        blob = p.read_bytes()
        visible = await tab.evaluate("document.body.innerText.includes('PUBLISH-CARD.md')", await_promise=False)
        out["shots"][p.name] = {"width": w, "height": h, "bytes": p.stat().st_size, "format": "jpeg",
                                "openable": blob[:3] == b"\xff\xd8\xff" and blob.rstrip().endswith(b"\xff\xd9"),
                                "sha256": hashlib.sha256(blob).hexdigest(),
                                "guide_visible_in_dom": bool(visible)}
    finally:
        try:
            browser.stop()
        except Exception:
            pass
    (B24 / "shots_manifest.json").write_bytes(json.dumps(out, ensure_ascii=False, indent=1).encode())
    print(json.dumps({"shots": list(out["shots"])}, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
