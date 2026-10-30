"""窄屏重测（CDP 全参数）+ 截图落 .jpg（nodriver 实际输出 JPEG）+ JPEG 尺寸解析。"""

from __future__ import annotations

import asyncio
import json
import pathlib
import struct
import sys

import nodriver as uc

UI = pathlib.Path(r"D:\桌面\two\docs\validation\money-project\workbench-ui")
SHOTS = UI / "shots"
BASE = "http://127.0.0.1:5015"
CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"

MEASURE = """
(() => { const de = document.documentElement;
  return JSON.stringify({url: location.href, innerWidth: window.innerWidth, innerHeight: window.innerHeight,
    scrollWidth: de.scrollWidth, scrollHeight: de.scrollHeight, overflowX: de.scrollWidth > window.innerWidth + 1,
    widest: (() => { let w=0, tag=''; for (const el of document.querySelectorAll('body *')) { const r = el.getBoundingClientRect();
        if (r.right > w) { w = r.right; tag = el.tagName + '.' + (el.className || '').toString().slice(0,24) + '#' + (el.id||''); } }
        return {right: Math.round(w), tag: tag}; })(),
    rows: document.querySelectorAll('tbody tr').length,
    navCollapsed: document.body.classList.contains('nav-collapsed')}); })()
"""


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
        seg_len = struct.unpack(">H", data[i + 2 : i + 4])[0]
        i += 2 + seg_len
    return None, None


async def main() -> int:
    out = {"mobile": [], "shots": {}, "errors": [], "viewport": {"width": 390, "height": 844}}
    browser = await uc.start(headless=True, browser_executable_path=CHROME,
                             browser_args=["--hide-scrollbars", "--no-first-run"], sandbox=False)
    try:
        tab = await browser.get(BASE + "/")
        await asyncio.sleep(1.0)
        try:
            await tab.send(uc.cdp.emulation.set_device_metrics_override(
                width=390, height=844, device_scale_factor=1, mobile=True,
                screen_width=390, screen_height=844, position_x=0, position_y=0))
        except Exception as exc:
            out["errors"].append(f"override: {type(exc).__name__}: {exc}")
        await asyncio.sleep(1.0)
        for path, name in (("/", "mobile_index"), ("/opportunities", "mobile_opportunities"),
                           ("/sources", "mobile_sources")):
            await tab.get(BASE + path)
            await asyncio.sleep(1.5)
            raw = await tab.evaluate(MEASURE, await_promise=False)
            data = json.loads(raw) if isinstance(raw, str) else {}
            shot = SHOTS / f"{name}.jpg"
            try:
                await tab.save_screenshot(str(shot))
                data["screenshot"] = str(shot)
            except Exception as exc:
                data["screenshot_error"] = f"{type(exc).__name__}: {exc}"
            out["mobile"].append(data)
    except Exception as exc:
        out["errors"].append(f"{type(exc).__name__}: {exc}")
    finally:
        try:
            browser.stop()
        except Exception:
            pass
    # 桌面截图也改名为 .jpg（内容是 JPEG）
    for f in sorted(SHOTS.glob("desktop_*.png")):
        target = f.with_suffix(".jpg")
        if not target.exists():
            f.rename(target)
    for f in sorted(SHOTS.glob("mobile_*.png")):
        target = f.with_suffix(".jpg")
        if not target.exists():
            f.rename(target)
    for f in sorted(SHOTS.glob("*.jpg")):
        w, h = jpeg_size(f)
        out["shots"][f.name] = {"format": "jpeg", "width": w, "height": h, "bytes": f.stat().st_size}
    (UI / "mobile_evidence.json").write_bytes(json.dumps(out, ensure_ascii=False, indent=1).encode("utf-8"))
    print(json.dumps({k: out[k] for k in ("mobile", "errors")}, ensure_ascii=True, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
