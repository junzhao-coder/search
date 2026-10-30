"""Screenshot /leads at two independent viewports; read-only local page."""
import asyncio, json, pathlib, sys
import nodriver as uc
import nodriver.cdp.emulation as emu
SHOTS = pathlib.Path(__file__).resolve().parents[1] / "shots"
SHOTS.mkdir(parents=True, exist_ok=True)

async def shot(name, w, h):
    browser = await uc.start(headless=True,
        browser_executable_path=r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        browser_args=[f"--window-size={w},{h}", "--force-device-scale-factor=1", "--hide-scrollbars"])
    try:
        tab = await browser.get("http://127.0.0.1:5015/leads")
        await tab.send(emu.set_device_metrics_override(width=w, height=h, device_scale_factor=1, mobile=(w < 600)))
        await asyncio.sleep(1.0)
        metrics = await tab.evaluate("JSON.stringify({iw:innerWidth, ih:innerHeight, sw:document.documentElement.scrollWidth, sh:document.documentElement.scrollHeight, overflowX:document.documentElement.scrollWidth>innerWidth})")
        await tab.save_screenshot(str(SHOTS / f"{name}.png"))
        return {"name": name, "requested": [w, h], "metrics": json.loads(metrics)}
    finally:
        browser.stop()

async def main():
    out = []
    for name, w, h in (("leads_1440x900",1440,900),("leads_390x844",390,844)):
        out.append(await shot(name,w,h))
    print(json.dumps(out,ensure_ascii=False))
    return 0
if __name__=="__main__":
    sys.exit(asyncio.run(main()))
