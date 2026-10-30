"""重建浏览器证据：1440×900 精确视口 + 390×844 手机 + 3 次同表头点击 + 真实键盘操作。

输出：interaction_evidence_v2.json、shots_manifest.json、shots/*.jpg
"""

from __future__ import annotations

import asyncio
import hashlib
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
  return JSON.stringify({url: location.href, search: location.search, innerW: window.innerWidth,
    innerH: window.innerHeight, scrollW: de.scrollWidth, overflowX: de.scrollWidth > window.innerWidth + 1,
    rows: document.querySelectorAll('tbody tr').length,
    count: (document.querySelector('.filter-count')||{}).textContent || null,
    firstRow: (document.querySelector('tbody tr')||{}).innerText ? document.querySelector('tbody tr').innerText.replace(/\\s+/g,' ').slice(0,80) : null,
    sortedHref: (document.querySelector('th a.sorted')||{}).getAttribute ? document.querySelector('th a.sorted').getAttribute('href') : null,
    open: document.querySelectorAll('details[open]').length,
    active: document.activeElement ? (document.activeElement.tagName + ':' + (document.activeElement.textContent||'').trim().slice(0,24)) : null,
    navToggleH: (() => { const b=document.querySelector('.nav-toggle'); if(!b) return null; const r=b.getBoundingClientRect(); return {h:Math.round(r.height), w:Math.round(r.width)}; })()
  }); })()
"""


def jpeg_size(path: pathlib.Path):
    data = path.read_bytes()
    i = 2
    while i < len(data) - 9:
        if data[i] != 0xFF:
            i += 1
            continue
        m = data[i + 1]
        if m in (0xC0, 0xC1, 0xC2, 0xC3):
            h, w = struct.unpack(">HH", data[i + 5 : i + 9])
            return w, h
        i += 2 + struct.unpack(">H", data[i + 2 : i + 4])[0]
    return None, None


async def snap(tab, name: str, path) -> dict:
    d = pathlib.Path(path)
    try:
        await tab.save_screenshot(str(d))
    except Exception as exc:
        return {"error": f"{type(exc).__name__}: {exc}"}
    w, h = jpeg_size(d)
    return {"file": d.name, "path": str(d), "width": w, "height": h,
            "bytes": d.stat().st_size, "sha256": hashlib.sha256(d.read_bytes()).hexdigest()}


async def measure(tab) -> dict:
    raw = await tab.evaluate(MEASURE, await_promise=False)
    return json.loads(raw) if isinstance(raw, str) else {}


async def key(tab, key_name: str, code: int) -> None:
    await tab.send(uc.cdp.input_.dispatch_key_event(type_="keyDown", key=key_name, windows_virtual_key_code=code,
                                                    native_virtual_key_code=code))
    await tab.send(uc.cdp.input_.dispatch_key_event(type_="keyUp", key=key_name, windows_virtual_key_code=code,
                                                    native_virtual_key_code=code))


async def main() -> int:
    out = {"desktop": [], "mobile": [], "sort_clicks": [], "keyboard": [], "manifest": {}, "errors": []}
    browser = await uc.start(headless=True, browser_executable_path=CHROME,
                             browser_args=["--hide-scrollbars", "--no-first-run"], sandbox=False)
    try:
        tab = await browser.get(BASE + "/")
        await asyncio.sleep(1.2)
        await tab.send(uc.cdp.emulation.set_device_metrics_override(
            width=1440, height=900, device_scale_factor=1, mobile=False, screen_width=1440, screen_height=900))

        # ---- 桌面 1440×900 ----
        for path, name in (("/", "desktop_index"), ("/opportunities", "desktop_opportunities"),
                           ("/sources", "desktop_sources"), ("/collect", "desktop_collect"),
                           ("/daily", "desktop_daily")):
            await tab.get(BASE + path)
            await asyncio.sleep(1.4)
            data = await measure(tab)
            data["shot"] = await snap(tab, name, SHOTS / f"{name}.jpg")
            out["desktop"].append(data)

        # ---- 3 次同表头点击（保留 q/platform/min_score/sell）----
        start = "/opportunities?q=%E6%A8%A1%E6%9D%BF&platform=x&min_score=0.3&sell=%E8%BE%83%E5%BC%BA%E5%94%AE%E5%8D%96"
        await tab.get(BASE + start)
        await asyncio.sleep(1.4)
        out["sort_clicks"].append({"step": 0, "state": await measure(tab)})
        for step in (1, 2, 3):
            await tab.evaluate("(() => { const a=document.querySelector('th a[href*=\"sort=demand\"]'); "
                               "if(a){a.click(); return true;} return false; })()", await_promise=False)
            await asyncio.sleep(1.5)
            out["sort_clicks"].append({"step": step, "state": await measure(tab)})

        # ---- 键盘：Tab 序列 / Enter 导航 / Enter 筛选 / Space 展开 ----
        await tab.get(BASE + "/")
        await asyncio.sleep(1.2)
        await tab.evaluate("document.body.focus()", await_promise=False)
        for i in range(6):
            await key(tab, "Tab", 9)
            await asyncio.sleep(0.25)
            st = await measure(tab)
            out["keyboard"].append({"step": f"tab{i + 1}", "active": st.get("active")})
        # 聚焦第一个导航链接并 Enter
        await tab.evaluate("(() => { const a=document.querySelector('.sidebar nav a'); a.focus(); return a.textContent.trim(); })()",
                           await_promise=False)
        before = await measure(tab)
        await key(tab, "Enter", 13)
        await asyncio.sleep(1.5)
        after = await measure(tab)
        out["keyboard"].append({"step": "enter_nav", "before_url": before.get("url"), "after_url": after.get("url")})

        # Enter 提交筛选（聚焦关键词框 → 输入 → 聚焦按钮 → Enter）
        await tab.get(BASE + "/opportunities")
        await asyncio.sleep(1.2)
        await tab.evaluate("(() => { const i=document.querySelector('input[name=q]'); i.focus(); i.value='AI'; "
                           "document.querySelector('form.filters button[type=submit]').focus(); return true; })()",
                           await_promise=False)
        await key(tab, "Enter", 13)
        await asyncio.sleep(1.6)
        filtered = await measure(tab)
        out["keyboard"].append({"step": "enter_filter", "url": filtered.get("url"), "count": filtered.get("count")})

        # Space 展开
        await tab.evaluate("(() => { const s=document.querySelector('tbody details summary'); s.focus(); return true; })()",
                           await_promise=False)
        await key(tab, " ", 32)
        await asyncio.sleep(0.8)
        expanded = await measure(tab)
        out["keyboard"].append({"step": "space_expand", "open": expanded.get("open")})
        out["keyboard_shot"] = await snap(tab, "desktop_opportunities_expanded", SHOTS / "desktop_opportunities_expanded.jpg")

        # ---- 手机 390×844 ----
        await tab.send(uc.cdp.emulation.set_device_metrics_override(
            width=390, height=844, device_scale_factor=1, mobile=True, screen_width=390, screen_height=844))
        for path, name in (("/", "mobile_index"), ("/opportunities", "mobile_opportunities"),
                           ("/sources", "mobile_sources")):
            await tab.get(BASE + path)
            await asyncio.sleep(1.4)
            data = await measure(tab)
            data["shot"] = await snap(tab, name, SHOTS / f"{name}.jpg")
            out["mobile"].append(data)

        for f in sorted(SHOTS.glob("*.jpg")):
            w, h = jpeg_size(f)
            out["manifest"][f.name] = {"file": f.name, "path": str(f), "width": w, "height": h,
                                       "bytes": f.stat().st_size,
                                       "sha256": hashlib.sha256(f.read_bytes()).hexdigest(),
                                       "viewport": ("1440x900" if f.name.startswith("desktop_") else "390x844"),
                                       "captured_utc": __import__("datetime").datetime.now(
                                           __import__("datetime").timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}

        # ---- D) 原生 form 对照：同一 rawKeyDown Enter 手法是否提交 ----
        native = {}
        try:
            await tab.send(uc.cdp.emulation.set_device_metrics_override(
                width=1440, height=900, device_scale_factor=1, mobile=False, screen_width=1440, screen_height=900))
            data_url = ("data:text/html,%3Cform%20action%3D%22data%3Atext%2Fhtml%2Cok%22%3E"
                        "%3Cinput%20name%3Dq%20value%3DAI%3E%3Cbutton%20type%3Dsubmit%3Ego%3C%2Fbutton%3E%3C%2Fform%3E")
            await tab.get(data_url)
            await asyncio.sleep(0.8)
            await tab.evaluate("(() => { const b=document.querySelector('button'); b.focus(); return true; })()",
                               await_promise=False)
            before_url = str(await tab.evaluate("location.href", await_promise=False))
            await key(tab, "Enter", 13)
            await asyncio.sleep(1.0)
            after_url = str(await tab.evaluate("location.href", await_promise=False))
            native = {"before": before_url, "after": after_url, "submitted": before_url != after_url}
        except Exception as exc:
            native = {"error": f"{type(exc).__name__}: {exc}"}
        out["native_form_probe"] = native
        out["keyboard_enter_verdict"] = ("CDP 注入限制（原生 form 同样不提交）" if native.get("submitted") is False
                                         else "原生 form 可提交 → 本页存在缺陷" if native.get("submitted")
                                         else "无法判定")

        # ---- C) 自校验：清单必须与磁盘实时 bytes/sha256 完全一致 ----
        mismatches = []
        for name, meta in out["manifest"].items():
            f = SHOTS / name
            live = {"bytes": f.stat().st_size, "sha256": hashlib.sha256(f.read_bytes()).hexdigest()}
            if live["bytes"] != meta["bytes"] or live["sha256"] != meta["sha256"]:
                mismatches.append({"file": name, "manifest": meta, "live": live})
        out["manifest_verification"] = {"checked": len(out["manifest"]), "mismatches": mismatches,
                                        "ok": not mismatches}
        if mismatches:
            out["errors"].append(f"manifest mismatch: {mismatches}")
    except Exception as exc:
        out["errors"].append(f"{type(exc).__name__}: {exc}")
    finally:
        try:
            browser.stop()
        except Exception:
            pass
    (UI / "interaction_evidence_v2.json").write_bytes(json.dumps(out, ensure_ascii=False, indent=1).encode("utf-8"))
    (UI / "shots_manifest.json").write_bytes(json.dumps({"shots": out["manifest"]}, ensure_ascii=False, indent=1).encode("utf-8"))
    print(json.dumps({"desktop": len(out["desktop"]), "mobile": len(out["mobile"]),
                      "clicks": len(out["sort_clicks"]), "keyboard": len(out["keyboard"]),
                      "errors": out["errors"]}, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
