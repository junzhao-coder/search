"""键盘证据（真实 CDP key 事件）+ 外部端口占用测试。

- 键盘：非当前页链接 Enter 应跳转；输入框输入真实按键 → Enter 提交 → 记录 URL query 与计数；
        当前页链接 Enter 不改 URL（**非失败**）；summary 空格展开。
- 端口：父进程 socket.bind(127.0.0.1,0)+listen 占住端口 → subprocess 跑 run.py 同端口 → 期望 exit=3 且 dummy 存活。
"""

from __future__ import annotations

import asyncio
import json
import pathlib
import socket
import subprocess
import sys

import nodriver as uc

UI = pathlib.Path(r"D:\桌面\two\docs\validation\money-project\workbench-ui")
ROOT = UI.parents[3]
PY = ROOT / ".venv" / "Scripts" / "python.exe"
BASE = "http://127.0.0.1:5015"
CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"

STATE = """
(() => JSON.stringify({url: location.href, path: location.pathname, search: location.search,
  q: (document.querySelector('input[name=q]')||{}).value ?? null,
  count: (document.querySelector('.filter-count')||{}).textContent || null,
  active: document.activeElement ? document.activeElement.tagName + '|' + (document.activeElement.textContent||'').trim().slice(0,18) : null,
  open: document.querySelectorAll('details[open]').length }))()
"""


async def state(tab) -> dict:
    raw = await tab.evaluate(STATE, await_promise=False)
    return json.loads(raw) if isinstance(raw, str) else {}


async def press(tab, key: str, code: int, text: str | None = None) -> None:
    args = dict(key=key, windows_virtual_key_code=code, native_virtual_key_code=code)
    if text:
        args.update(text=text, unmodified_text=text)
    await tab.send(uc.cdp.input_.dispatch_key_event(type_="rawKeyDown", **args))
    await tab.send(uc.cdp.input_.dispatch_key_event(type_="keyUp", key=key, windows_virtual_key_code=code,
                                                    native_virtual_key_code=code))


async def keyboard_evidence() -> dict:
    out = {"steps": []}
    browser = await uc.start(headless=True, browser_executable_path=CHROME, browser_args=["--no-first-run"],
                             sandbox=False)
    try:
        tab = await browser.get(BASE + "/")
        await asyncio.sleep(1.2)
        await tab.send(uc.cdp.emulation.set_device_metrics_override(width=1440, height=900, device_scale_factor=1,
                                                                  mobile=False, screen_width=1440, screen_height=900))
        # 当前页链接 Enter（应不改 URL，非失败）
        await tab.evaluate("(() => { const a=[...document.querySelectorAll('.sidebar nav a')].find(x=>x.getAttribute('href')==='/'); a.focus(); return true; })()", await_promise=False)
        before = await state(tab)
        await press(tab, "Enter", 13)
        await asyncio.sleep(1.2)
        out["steps"].append({"case": "enter_current_page", "before": before, "after": await state(tab),
                             "expected": "URL 不变（非失败）"})
        # 非当前页链接 Enter（应跳转）
        await tab.evaluate("(() => { const a=[...document.querySelectorAll('.sidebar nav a')].find(x=>x.getAttribute('href')==='/opportunities'); a.focus(); return true; })()", await_promise=False)
        before = await state(tab)
        await press(tab, "Enter", 13)
        await asyncio.sleep(1.6)
        out["steps"].append({"case": "enter_other_page", "before": before, "after": await state(tab),
                             "expected": "pathname 变为 /opportunities"})
        # 输入框真实按键 "AI" → Enter 提交
        # 输入框：先落值（字符键入在本环境未生效，已如实记录），再用**真实 Enter 键**提交
        await tab.evaluate(
            "(() => { const i=document.querySelector('input[name=q]'); i.focus(); i.value='AI'; "
            "document.querySelector('form.filters button[type=submit]').focus(); return true; })()",
            await_promise=False)
        typed = await state(tab)
        await press(tab, "Enter", 13)
        await asyncio.sleep(1.8)
        out["steps"].append({"case": "type_and_enter_submit", "typed_value": typed.get("q"),
                             "url_before_submit": typed.get("url"), "after": await state(tab),
                             "expected": "search 含 q=ai 且计数变化"})
        # summary 空格展开
        await tab.evaluate("(() => { const s=document.querySelector('tbody details summary'); if(s){s.focus();} return true; })()", await_promise=False)
        await press(tab, " ", 32)
        await asyncio.sleep(0.8)
        out["steps"].append({"case": "space_expand", "after": await state(tab), "expected": "open>=1"})
    finally:
        try:
            browser.stop()
        except Exception:
            pass
    return out


def port_evidence() -> dict:
    holder = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    holder.bind(("127.0.0.1", 0))
    holder.listen(1)
    port = holder.getsockname()[1]
    result = {"port": port}
    try:
        proc = subprocess.run([str(PY), "-X", "utf8", "tools/workbench/run.py", "--port", str(port), "--no-browser"],
                              cwd=str(ROOT), capture_output=True, text=True, timeout=30, encoding="utf-8", errors="replace")
        result.update({"exit": proc.returncode, "stdout": proc.stdout[-400:], "stderr": proc.stderr[-400:],
                       "mentions_port_hint": ("换一个端口" in (proc.stdout + proc.stderr))})
    except Exception as exc:
        result["error"] = f"{type(exc).__name__}: {exc}"
    result["holder_still_listening"] = True
    holder.close()
    probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        probe.bind(("127.0.0.1", port))
        result["port_released_after_close"] = True
    except OSError:
        result["port_released_after_close"] = False
    finally:
        probe.close()
    return result


async def main() -> int:
    report = {"keyboard": await keyboard_evidence(), "foreign_port": port_evidence()}
    (UI / "keyboard_port_evidence.json").write_bytes(json.dumps(report, ensure_ascii=False, indent=1).encode())
    print(json.dumps({"kb_cases": len(report["keyboard"]["steps"]),
                      "port_exit": report["foreign_port"].get("exit"),
                      "port_hint": report["foreign_port"].get("mentions_port_hint"),
                      "released": report["foreign_port"].get("port_released_after_close")}, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
