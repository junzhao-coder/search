"""截图与清单（不依赖 DSH）：桌面 1440×900、展开态、手机 390×844，并自校验 manifest。

用法：
  <x-collect venv python> shot_check.py --base http://127.0.0.1:5016 --out ../../docs/.../shots
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import pathlib
import struct
import sys

import nodriver as uc

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


async def snap(tab, path: pathlib.Path) -> dict:
    await tab.save_screenshot(str(path))
    w, h = jpeg_size(path)
    return {"file": path.name, "path": str(path), "width": w, "height": h,
            "bytes": path.stat().st_size, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


async def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:5016")
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)
    out_dir = pathlib.Path(args.out).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    base = args.base.rstrip("/")
    manifest: dict[str, dict] = {}
    browser = await uc.start(headless=True, browser_executable_path=CHROME,
                             browser_args=["--hide-scrollbars", "--no-first-run"], sandbox=False)
    try:
        tab = await browser.get(base + "/opportunities")
        await asyncio.sleep(1.5)
        await tab.send(uc.cdp.emulation.set_device_metrics_override(
            width=1440, height=900, device_scale_factor=1, mobile=False,
            screen_width=1440, screen_height=900))
        await asyncio.sleep(1.0)
        manifest["desktop_grouped.jpg"] = await snap(tab, out_dir / "desktop_grouped.jpg")

        # 教程与内容页
        await tab.get(base + "/content")
        await asyncio.sleep(1.2)
        manifest["desktop_content.jpg"] = await snap(tab, out_dir / "desktop_content.jpg")

        await tab.get(base + "/opportunities")
        await asyncio.sleep(1.2)

        # 展开第一组（点击整行按钮）
        await tab.evaluate("(() => { const b=document.querySelector('.row-toggle'); if(b){b.click();} return true; })()",
                           await_promise=False)
        await asyncio.sleep(1.0)
        state = await tab.evaluate(
            "(() => { const b=document.querySelector('.row-toggle'); const id=b && b.getAttribute('aria-controls');"
            " const p=id && document.getElementById(id); return JSON.stringify({expanded: b && b.getAttribute('aria-expanded'),"
            " hidden: p ? p.hidden : null, text: b ? b.textContent.trim() : null}); })()", await_promise=False)
        manifest["desktop_grouped_expanded.jpg"] = await snap(tab, out_dir / "desktop_grouped_expanded.jpg")

        await tab.send(uc.cdp.emulation.set_device_metrics_override(
            width=390, height=844, device_scale_factor=1, mobile=True, screen_width=390, screen_height=844))
        await tab.get(base + "/opportunities")
        await asyncio.sleep(1.5)
        manifest["mobile_grouped.jpg"] = await snap(tab, out_dir / "mobile_grouped.jpg")
        overflow = await tab.evaluate(
            "(() => JSON.stringify({innerW: window.innerWidth, scrollW: document.documentElement.scrollWidth}))()",
            await_promise=False)
    finally:
        try:
            browser.stop()
        except Exception:
            pass

    report = {"base": base, "shots": manifest, "expand_state": json.loads(state) if isinstance(state, str) else state,
              "mobile_metrics": json.loads(overflow) if isinstance(overflow, str) else overflow}
    verify = []
    for name, meta in manifest.items():
        path = out_dir / name
        live = {"bytes": path.stat().st_size, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
        verify.append({"file": name, "ok": live["bytes"] == meta["bytes"] and live["sha256"] == meta["sha256"], **live})
    report["verification"] = {"checked": len(verify), "mismatches": [v for v in verify if not v["ok"]],
                              "ok": all(v["ok"] for v in verify)}
    (out_dir.parent / "shots_manifest.json").write_bytes(json.dumps(report, ensure_ascii=False, indent=1).encode())
    print(json.dumps({"shots": list(manifest), "verification": report["verification"]["ok"],
                      "expand": report["expand_state"], "mobile": report["mobile_metrics"]}, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
