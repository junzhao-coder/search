"""桌面级可见性证据（Windows，仅标准库 ctypes，无新依赖）。

回应用户投诉「并没有看到有页面弹出」：PID、页面截图、`document.visibilityState`
都不能证明窗口真的出现在桌面上。本模块只做四件事，并把每一步结果如实返回：

1. 按浏览器进程 PID（其次按调用方给的一次性标题 nonce）找到 Chrome 顶层窗口
   （class `Chrome_WidgetWin_1`，必须可见且有标题）；
2. `ShowWindow(SW_RESTORE)` → `SetWindowPos(HWND_TOP)` → `SetForegroundWindow`，
   若仍未置前再用 `AttachThreadInput` + `BringWindowToTop` 重试一次；
3. 读 `GetForegroundWindow()`，判定它是否**等于**目标 hwnd（`foreground_matched`）；
4. 读窗口矩形（优先 DWM 扩展边框），并对**整屏**做 GDI 抓图写成 PNG。

边界（写进返回值，不靠口头承诺）：
- `proven=False` 时必有 `reason`；PID 命中或页面截图都不算桌面可见；
- 调用方传 `screenshot=None` 就不抓图（真实登录页禁止自动截图）；
- 没有交互桌面（服务会话/会话被锁）时 `GetForegroundWindow` 与抓图会失败，
  如实报 `foreground_not_matched` / `desktop_screenshot_failed`，不重试、不冒充。
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes as wintypes
import pathlib
import struct
import sys
import time
import zlib

IS_WINDOWS = sys.platform.startswith("win")

#: 只有这个 class 才是 Chrome 的顶层浏览器窗口（其余是消息窗口/隐藏宿主）。
CHROME_CLASS = "Chrome_WidgetWin_1"

SW_RESTORE = 9
HWND_TOP = 0
HWND_TOPMOST = -1
HWND_NOTOPMOST = -2
GWL_EXSTYLE = -20
WS_EX_TOPMOST = 0x00000008
SWP_NOSIZE = 0x0001
SWP_NOMOVE = 0x0002
SWP_NOACTIVATE = 0x0010
SWP_SHOWWINDOW = 0x0040
ASFW_ANY = 0xFFFFFFFF
SRCCOPY = 0x00CC0020
DWMWA_EXTENDED_FRAME_BOUNDS = 9

SM_XVIRTUALSCREEN, SM_YVIRTUALSCREEN = 76, 77
SM_CXVIRTUALSCREEN, SM_CYVIRTUALSCREEN = 78, 79
SM_CXSCREEN, SM_CYSCREEN = 0, 1

NOTE = ("桌面级证据=前台窗口匹配+窗口矩形+(可选)整屏截图；"
        "它证明窗口在桌面被置前，不证明人眼已经看到")

_API = None


class _RECT(ctypes.Structure):
    _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long),
                ("right", ctypes.c_long), ("bottom", ctypes.c_long)]


class _BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [("biSize", ctypes.c_uint32), ("biWidth", ctypes.c_int32),
                ("biHeight", ctypes.c_int32), ("biPlanes", ctypes.c_uint16),
                ("biBitCount", ctypes.c_uint16), ("biCompression", ctypes.c_uint32),
                ("biSizeImage", ctypes.c_uint32), ("biXPelsPerMeter", ctypes.c_int32),
                ("biYPelsPerMeter", ctypes.c_int32), ("biClrUsed", ctypes.c_uint32),
                ("biClrImportant", ctypes.c_uint32)]


class _BITMAPINFO(ctypes.Structure):
    _fields_ = [("bmiHeader", _BITMAPINFOHEADER), ("bmiColors", ctypes.c_uint32 * 3)]


class _WinAPI:
    """Lazy WinDLL bundle with explicit signatures (64-bit handles are pointers)."""

    def __init__(self) -> None:
        self.user32 = ctypes.WinDLL("user32", use_last_error=True)
        self.gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)
        self.kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        try:
            self.dwmapi = ctypes.WinDLL("dwmapi", use_last_error=True)
        except OSError:                     # very old Windows: rect falls back to GDI
            self.dwmapi = None
        u, g, k = self.user32, self.gdi32, self.kernel32
        u.GetForegroundWindow.restype = wintypes.HWND
        u.SetForegroundWindow.argtypes = [wintypes.HWND]
        u.SetForegroundWindow.restype = wintypes.BOOL
        u.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
        u.ShowWindow.restype = wintypes.BOOL
        u.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int,
                                   ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                   ctypes.c_uint]
        u.SetWindowPos.restype = wintypes.BOOL
        u.IsWindowVisible.argtypes = [wintypes.HWND]
        u.IsWindowVisible.restype = wintypes.BOOL
        u.GetWindowTextW.argtypes = [wintypes.HWND, ctypes.c_wchar_p, ctypes.c_int]
        u.GetWindowTextW.restype = ctypes.c_int
        u.GetClassNameW.argtypes = [wintypes.HWND, ctypes.c_wchar_p, ctypes.c_int]
        u.GetClassNameW.restype = ctypes.c_int
        u.GetWindowThreadProcessId.argtypes = [wintypes.HWND,
                                               ctypes.POINTER(wintypes.DWORD)]
        u.GetWindowThreadProcessId.restype = wintypes.DWORD
        u.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(_RECT)]
        u.GetWindowRect.restype = wintypes.BOOL
        u.AttachThreadInput.argtypes = [wintypes.DWORD, wintypes.DWORD, wintypes.BOOL]
        u.AttachThreadInput.restype = wintypes.BOOL
        u.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
        u.GetWindowLongW.restype = ctypes.c_long
        u.BringWindowToTop.argtypes = [wintypes.HWND]
        u.SetFocus.argtypes = [wintypes.HWND]
        u.AllowSetForegroundWindow.argtypes = [wintypes.DWORD]
        u.keybd_event.argtypes = [wintypes.BYTE, wintypes.BYTE, wintypes.DWORD,
                                  ctypes.c_size_t]
        u.keybd_event.restype = None
        u.GetSystemMetrics.argtypes = [ctypes.c_int]
        u.GetDC.argtypes = [wintypes.HWND]
        u.GetDC.restype = ctypes.c_void_p
        u.ReleaseDC.argtypes = [wintypes.HWND, ctypes.c_void_p]
        g.CreateCompatibleDC.argtypes = [ctypes.c_void_p]
        g.CreateCompatibleDC.restype = ctypes.c_void_p
        g.CreateCompatibleBitmap.argtypes = [ctypes.c_void_p, ctypes.c_int,
                                             ctypes.c_int]
        g.CreateCompatibleBitmap.restype = ctypes.c_void_p
        g.SelectObject.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        g.SelectObject.restype = ctypes.c_void_p
        g.BitBlt.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int,
                             ctypes.c_int, ctypes.c_int, ctypes.c_void_p,
                             ctypes.c_int, ctypes.c_int, ctypes.c_uint]
        g.BitBlt.restype = wintypes.BOOL
        g.GetDIBits.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint,
                                ctypes.c_uint, ctypes.c_void_p, ctypes.c_void_p,
                                ctypes.c_uint]
        g.GetDIBits.restype = ctypes.c_int
        g.DeleteObject.argtypes = [ctypes.c_void_p]
        g.DeleteDC.argtypes = [ctypes.c_void_p]
        k.GetCurrentThreadId.restype = wintypes.DWORD
        if self.dwmapi is not None:
            self.dwmapi.DwmGetWindowAttribute.argtypes = [
                wintypes.HWND, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD]
            self.dwmapi.DwmGetWindowAttribute.restype = ctypes.c_long


def api() -> _WinAPI:
    """Build (once) the WinDLL bundle; raises OSError off-Windows."""
    global _API
    if _API is None:
        if not IS_WINDOWS:
            raise OSError("not_windows")
        _API = _WinAPI()
    return _API


def _set_dpi_aware() -> bool:
    """物理像素坐标/截图尺寸一致的前提；失败只影响尺寸换算，不影响判定。"""
    if not IS_WINDOWS:
        return False
    try:
        shcore = ctypes.WinDLL("shcore", use_last_error=True)
        if shcore.SetProcessDpiAwareness(2) == 0:      # per-monitor aware
            return True
    except Exception:  # noqa: BLE001 - pre-8.1 or already set by the host
        pass
    try:
        return bool(ctypes.windll.user32.SetProcessDPIAware())
    except Exception:  # noqa: BLE001
        return False


def _read_text(fn, hwnd, size: int) -> str:
    buf = ctypes.create_unicode_buffer(size)
    fn(wintypes.HWND(hwnd), buf, size)
    return buf.value or ""


def window_rect(hwnd: int) -> dict:
    """DWM 扩展边框优先（阴影不算进窗口），回退 `GetWindowRect`。"""
    winapi = api()
    rect = _RECT()
    source = None
    if winapi.dwmapi is not None:
        try:
            hr = winapi.dwmapi.DwmGetWindowAttribute(
                wintypes.HWND(hwnd), DWMWA_EXTENDED_FRAME_BOUNDS,
                ctypes.byref(rect), ctypes.sizeof(rect))
            if hr == 0 and rect.right > rect.left and rect.bottom > rect.top:
                source = "dwm_extended_frame_bounds"
        except Exception:  # noqa: BLE001 - a failed DWM query is not fatal
            pass
    if source is None:
        rect = _RECT()
        if winapi.user32.GetWindowRect(wintypes.HWND(hwnd), ctypes.byref(rect)):
            source = "get_window_rect"
    return {"left": int(rect.left), "top": int(rect.top), "right": int(rect.right),
            "bottom": int(rect.bottom), "width": max(0, int(rect.right - rect.left)),
            "height": max(0, int(rect.bottom - rect.top)), "source": source}


def list_chrome_windows() -> list[dict]:
    """Visible top-level Chrome windows: hwnd/pid/title/class/rect."""
    winapi = api()
    found: list[dict] = []
    proto = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def _callback(hwnd, _lparam):  # noqa: ANN001 - ctypes signature
        try:
            if not winapi.user32.IsWindowVisible(hwnd):
                return True
            class_name = _read_text(winapi.user32.GetClassNameW, hwnd, 256)
            if class_name != CHROME_CLASS:
                return True
            title = _read_text(winapi.user32.GetWindowTextW, hwnd, 512)
            if not title:
                return True
            pid = wintypes.DWORD(0)
            winapi.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            found.append({"hwnd": int(hwnd or 0), "pid": int(pid.value),
                          "title": title, "class_name": class_name,
                          "rect": window_rect(hwnd)})
        except Exception:  # noqa: BLE001 - one odd window must not break the scan
            return True
        return True

    winapi.user32.EnumWindows(proto(_callback), 0)
    return found


def _area(window: dict) -> int:
    rect = window.get("rect") or {}
    return int(rect.get("width") or 0) * int(rect.get("height") or 0)


def _pick(candidates: list[dict], *, pid: int | None, title_hint: str | None):
    """PID 命中优先；给了 nonce 才允许跨进程按标题兜底（nonce 由调用方生成）。"""
    if pid is not None:
        pool = [c for c in candidates if c["pid"] == int(pid)]
        if pool:
            if title_hint:
                titled = [c for c in pool
                          if title_hint.lower() in (c["title"] or "").lower()]
                if titled:
                    return {**titled[0], "matched_by": "pid+title"}
            return {**max(pool, key=_area), "matched_by": "pid"}
    if title_hint:
        titled = [c for c in candidates
                  if title_hint.lower() in (c["title"] or "").lower()]
        if titled:
            return {**titled[0], "matched_by": "title"}
    # 没有 PID 命中、也没有 nonce 时宁可不猜：挑最大的会抢到用户日常 Chrome
    return None


def force_foreground(hwnd: int) -> list[str]:
    """尽力把窗口置前；返回尝试序列（成败由调用方用 GetForegroundWindow 判定）。"""
    winapi = api()
    attempts: list[str] = []
    handle = wintypes.HWND(hwnd)
    try:
        winapi.user32.AllowSetForegroundWindow(ASFW_ANY)
        attempts.append("allow_set_foreground_window")
    except Exception:  # noqa: BLE001
        attempts.append("allow_set_foreground_window_failed")
    try:
        winapi.user32.ShowWindow(handle, SW_RESTORE)
        attempts.append("show_window_restore")
    except Exception:  # noqa: BLE001
        attempts.append("show_window_restore_failed")
    try:
        winapi.user32.SetWindowPos(handle, wintypes.HWND(HWND_TOP), 0, 0, 0, 0,
                                   SWP_NOMOVE | SWP_NOSIZE | SWP_SHOWWINDOW)
        attempts.append("set_window_pos_top")
    except Exception:  # noqa: BLE001
        attempts.append("set_window_pos_top_failed")
    try:
        ok = bool(winapi.user32.SetForegroundWindow(handle))
    except Exception:  # noqa: BLE001
        ok = False
    attempts.append(f"set_foreground_window:{int(ok)}")
    if int(winapi.user32.GetForegroundWindow() or 0) == int(hwnd):
        return attempts
    foreground = winapi.user32.GetForegroundWindow()
    current = int(winapi.kernel32.GetCurrentThreadId())
    target_thread = int(winapi.user32.GetWindowThreadProcessId(foreground, None)) \
        if foreground else 0
    attached = False
    if target_thread and target_thread != current:
        attached = bool(winapi.user32.AttachThreadInput(current, target_thread, True))
        attempts.append(f"attach_thread_input:{int(attached)}")
    try:
        winapi.user32.BringWindowToTop(handle)
        winapi.user32.SetForegroundWindow(handle)
        winapi.user32.SetFocus(handle)
        attempts.append("retry_bring_to_top_set_focus")
    except Exception:  # noqa: BLE001
        attempts.append("retry_failed")
    finally:
        if attached:
            winapi.user32.AttachThreadInput(current, target_thread, False)
    if int(winapi.user32.GetForegroundWindow() or 0) == int(hwnd):
        return attempts
    # 最后一招：合成一次 Alt 键事件，让本进程成为"最后输入"的持有者（前台锁真正检查的东西）
    try:
        winapi.user32.keybd_event(0x12, 0, 0, 0)              # Alt down
        winapi.user32.keybd_event(0x12, 0, 0x0002, 0)         # Alt up
        winapi.user32.SetForegroundWindow(handle)
        attempts.append("alt_key_then_set_foreground")
    except Exception:  # noqa: BLE001
        attempts.append("alt_key_attempt_failed")
    return attempts


def topmost_flag(exstyle: int) -> bool:
    """纯函数：从 GWL_EXSTYLE 判断 WS_EX_TOPMOST 是否真的置上。"""
    return bool(int(exstyle or 0) & WS_EX_TOPMOST)


def exstyle(hwnd: int) -> int:
    return int(api().user32.GetWindowLongW(wintypes.HWND(hwnd), GWL_EXSTYLE) or 0)


def set_topmost(hwnd: int, *, on: bool = True) -> dict:
    """SetWindowPos(HWND_TOPMOST/NOTOPMOST, SWP_NOMOVE|SWP_NOSIZE|SWP_NOACTIVATE)。

    置上后**回读** GWL_EXSTYLE 核对 WS_EX_TOPMOST，返回 `topmost_set`；
    失败只记录，不抛（调用方决定是否停）。
    """
    out: dict = {"hwnd": int(hwnd), "requested": bool(on), "topmost_set": False,
                 "exstyle": None, "error": None}
    if not IS_WINDOWS:
        out["error"] = "not_windows"
        return out
    try:
        winapi = api()
        handle = wintypes.HWND(hwnd)
        target = wintypes.HWND(HWND_TOPMOST if on else HWND_NOTOPMOST)
        ok = bool(winapi.user32.SetWindowPos(
            handle, target, 0, 0, 0, 0,
            SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE | SWP_SHOWWINDOW))
        style = exstyle(hwnd)
        out.update(exstyle=style, topmost_set=topmost_flag(style))
        if not ok:
            out["error"] = "set_window_pos_returned_false"
    except Exception as exc:  # noqa: BLE001
        out["error"] = f"{type(exc).__name__}"
    return out


def foreground_hwnd() -> int:
    if not IS_WINDOWS:
        return 0
    try:
        return int(api().user32.GetForegroundWindow() or 0)
    except Exception:  # noqa: BLE001
        return 0


def reassert(hwnd: int, *, topmost: bool = False) -> dict:
    """仅当前台不是目标窗口时才夺回；返回本次是否真的重新置前。"""
    out: dict = {"hwnd": int(hwnd), "was_foreground": False, "reasserted": False,
                 "foreground_after": None, "attempts": [], "error": None}
    current = foreground_hwnd()
    out["was_foreground"] = current == int(hwnd)
    if out["was_foreground"]:
        out["foreground_after"] = current
        return out
    try:
        if topmost:
            set_topmost(hwnd, on=True)
        out["attempts"] = force_foreground(hwnd)
    except Exception as exc:  # noqa: BLE001
        out["error"] = f"{type(exc).__name__}"
    out["foreground_after"] = foreground_hwnd()
    out["reasserted"] = out["foreground_after"] == int(hwnd)
    if not out["reasserted"] and out["error"] is None:
        out["error"] = "foreground_not_reclaimed"
    return out


class Keepalive:
    """等待扫码期间维持置顶 + 只在前台丢失时夺回（不每轮抢焦点）。"""

    def __init__(self, hwnd: int, *, topmost: bool = True, interval: float = 2.0) -> None:
        self.hwnd = int(hwnd)
        self.topmost = bool(topmost)
        self.interval = float(interval)
        self.ticks = 0
        self.reassert_count = 0
        self.reassert_failures = 0
        self.last_error: str | None = None
        self.topmost_state: dict | None = None
        self._last_tick = 0.0

    def start(self) -> dict:
        self.topmost_state = set_topmost(self.hwnd, on=self.topmost) if self.topmost \
            else {"topmost_set": None, "requested": False}
        return dict(self.topmost_state)

    def tick(self, *, force: bool = False) -> dict | None:
        """按 interval 节流；前台已是目标窗口时不做任何抢占。"""
        now = time.monotonic()
        if not force and (now - self._last_tick) < self.interval:
            return None
        self._last_tick = now
        self.ticks += 1
        result = reassert(self.hwnd, topmost=self.topmost)
        if result["reasserted"]:
            self.reassert_count += 1
        elif not result["was_foreground"]:
            self.reassert_failures += 1
            self.last_error = result.get("error")
        return result

    def finish(self) -> dict:
        still = foreground_hwnd() == self.hwnd
        cleared = None
        if self.topmost:
            cleared = set_topmost(self.hwnd, on=False)
        return {"ticks": self.ticks, "reassert_count": self.reassert_count,
                "reassert_failures": self.reassert_failures,
                "still_foreground_at_end": still,
                "topmost_state": self.topmost_state,
                "topmost_cleared": bool((cleared or {}).get("topmost_set") is False),
                "last_error": self.last_error}


def wait_title_match(hwnd: int, page_title, *, attempts: int = 15,
                     interval: float = 0.2) -> dict:
    """等 OS 窗口标题追上页面标题（Chrome 是异步更新窗口标题的）。

    只读轮询，不抢焦点；返回 `{window_title, matched, waited_ms, polls}`。
    这是为了消除"页面标题已变、窗口标题还停在上一页"的竞态误判。
    """
    started = time.monotonic()
    polls = 0
    window_title = ""
    matched = None
    for _ in range(max(1, int(attempts))):
        polls += 1
        try:
            window_title = _read_text(api().user32.GetWindowTextW, int(hwnd), 512)
        except Exception:  # noqa: BLE001
            window_title = ""
        matched = title_contains(window_title, page_title)
        if matched is True:
            break
        time.sleep(interval)
    return {"hwnd": int(hwnd), "window_title": window_title, "matched": matched,
            "polls": polls,
            "waited_ms": int((time.monotonic() - started) * 1000)}


def title_contains(window_title, page_title) -> bool | None:
    """纯函数：页面标题是否为窗口标题子串（任一为空 → None）。"""
    window = " ".join(str(window_title or "").split())
    page = " ".join(str(page_title or "").split())
    if not window or not page:
        return None
    return page in window


def screen_rect() -> dict:
    """整个虚拟桌面（多显示器时是所有屏幕的并集）。"""
    winapi = api()
    get = winapi.user32.GetSystemMetrics
    width, height = int(get(SM_CXVIRTUALSCREEN)), int(get(SM_CYVIRTUALSCREEN))
    if width > 0 and height > 0:
        return {"x": int(get(SM_XVIRTUALSCREEN)), "y": int(get(SM_YVIRTUALSCREEN)),
                "width": width, "height": height, "source": "virtual_screen"}
    return {"x": 0, "y": 0, "width": int(get(SM_CXSCREEN)),
            "height": int(get(SM_CYSCREEN)), "source": "primary_screen"}


def png_bytes(width: int, height: int, rows: list[bytes]) -> bytes:
    """Minimal RGB8 PNG writer: one filter byte per row, zlib, no dependencies."""
    raw = bytearray()
    for row in rows:
        raw.append(0)
        raw.extend(row)

    def _chunk(tag: bytes, data: bytes) -> bytes:
        return (struct.pack(">I", len(data)) + tag + data
                + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))

    header = struct.pack(">IIBBBBB", int(width), int(height), 8, 2, 0, 0, 0)
    return (b"\x89PNG\r\n\x1a\n" + _chunk(b"IHDR", header)
            + _chunk(b"IDAT", zlib.compress(bytes(raw), 6)) + _chunk(b"IEND", b""))


def capture_screen(path) -> dict:
    """GDI 抓整屏写成 PNG；返回 path/bytes/width/height，失败抛异常由调用方记录。"""
    winapi = api()
    _set_dpi_aware()
    screen = screen_rect()
    width, height = int(screen["width"]), int(screen["height"])
    if width <= 0 or height <= 0:
        raise OSError(f"empty_screen:{width}x{height}")
    screen_dc = winapi.user32.GetDC(None)
    if not screen_dc:
        raise OSError("get_dc_failed")
    mem_dc = bitmap = previous = None
    try:
        mem_dc = winapi.gdi32.CreateCompatibleDC(ctypes.c_void_p(screen_dc))
        bitmap = winapi.gdi32.CreateCompatibleBitmap(ctypes.c_void_p(screen_dc),
                                                     width, height)
        if not mem_dc or not bitmap:
            raise OSError("gdi_object_failed")
        previous = winapi.gdi32.SelectObject(ctypes.c_void_p(mem_dc),
                                             ctypes.c_void_p(bitmap))
        if not winapi.gdi32.BitBlt(ctypes.c_void_p(mem_dc), 0, 0, width, height,
                                   ctypes.c_void_p(screen_dc), int(screen["x"]),
                                   int(screen["y"]), SRCCOPY):
            raise OSError("bitblt_failed")
        # GetDIBits 要求位图未被选进任何 DC：抓完立刻选回原对象
        if previous:
            winapi.gdi32.SelectObject(ctypes.c_void_p(mem_dc),
                                      ctypes.c_void_p(previous))
            previous = None
        info = _BITMAPINFO()
        info.bmiHeader.biSize = ctypes.sizeof(_BITMAPINFOHEADER)
        info.bmiHeader.biWidth = width
        info.bmiHeader.biHeight = -height          # top-down rows
        info.bmiHeader.biPlanes = 1
        info.bmiHeader.biBitCount = 32
        info.bmiHeader.biCompression = 0
        buffer = ctypes.create_string_buffer(width * height * 4)
        lines = winapi.gdi32.GetDIBits(ctypes.c_void_p(mem_dc),
                                       ctypes.c_void_p(bitmap), 0, height, buffer,
                                       ctypes.byref(info), 0)
        if int(lines) != height:
            raise OSError(f"get_dibits_failed:{lines}")
        data = buffer.raw
        stride = width * 4
        rows: list[bytes] = []
        for index in range(height):
            base = index * stride
            rgb = bytearray(width * 3)
            rgb[0::3] = data[base:base + stride:4]          # B -> R slot
            rgb[1::3] = data[base + 1:base + stride:4]      # G -> G slot
            rgb[2::3] = data[base + 2:base + stride:4]      # R -> B slot
            rows.append(bytes(rgb))
        payload = png_bytes(width, height, rows)
        target = pathlib.Path(path).expanduser()
        if target.parent and not target.parent.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(payload)
        return {"path": str(target), "bytes": len(payload), "width": width,
                "height": height, "mode": "rgb8_png", "captured": True}
    finally:
        if previous and mem_dc:
            winapi.gdi32.SelectObject(ctypes.c_void_p(mem_dc),
                                      ctypes.c_void_p(previous))
        if bitmap:
            winapi.gdi32.DeleteObject(ctypes.c_void_p(bitmap))
        if mem_dc:
            winapi.gdi32.DeleteDC(ctypes.c_void_p(mem_dc))
        winapi.user32.ReleaseDC(None, ctypes.c_void_p(screen_dc))


def prove(*, pid: int | None = None, title_hint: str | None = None,
          screenshot=None, wait_s: float = 2.0) -> dict:
    """完整桌面证据；任何一步失败都 `proven=False` + `reason`，绝不抛给调用方。"""
    out = {"supported": False, "proven": False, "reason": None, "platform": sys.platform,
           "hwnd": None, "pid": pid, "matched_by": None, "window_title": None,
           "class_name": None, "candidate_count": 0,
           "foreground_before": None, "foreground_after": None,
           "foreground_matched": False, "attempts": [],
           "window_rect": None, "rect_source": None, "dpi_aware": False,
           "screen": None, "desktop_screenshot": None,
           "desktop_screenshot_bytes": 0, "note": NOTE}
    try:
        winapi = api()
    except OSError as exc:
        out["reason"] = f"winapi_unavailable:{exc}"
        return out
    out["supported"] = True
    out["dpi_aware"] = _set_dpi_aware()
    out["screen"] = screen_rect()

    deadline = time.monotonic() + max(0.0, float(wait_s))
    candidates: list[dict] = []
    match = None
    while True:
        candidates = list_chrome_windows()
        match = _pick(candidates, pid=pid, title_hint=title_hint)
        if match is not None or time.monotonic() >= deadline:
            break
        time.sleep(0.2)
    out["candidate_count"] = len(candidates)
    if match is None:
        out["reason"] = "window_not_found"
        out["candidates"] = [{"hwnd": c["hwnd"], "pid": c["pid"], "title": c["title"]}
                             for c in candidates[:5]]
        return out

    hwnd = int(match["hwnd"])
    out.update({"hwnd": hwnd, "pid": match["pid"], "matched_by": match["matched_by"],
                "window_title": match["title"], "class_name": match["class_name"]})
    try:
        out["foreground_before"] = int(winapi.user32.GetForegroundWindow() or 0)
    except Exception:  # noqa: BLE001
        out["foreground_before"] = None
    out["attempts"] = force_foreground(hwnd)
    try:
        out["foreground_after"] = int(winapi.user32.GetForegroundWindow() or 0)
    except Exception:  # noqa: BLE001
        out["foreground_after"] = None
    out["foreground_matched"] = out["foreground_after"] == hwnd
    rect = window_rect(hwnd)
    out["window_rect"] = {key: rect[key] for key in
                          ("left", "top", "right", "bottom", "width", "height")}
    out["rect_source"] = rect["source"]

    if screenshot is not None:
        time.sleep(0.25)          # 让 DWM 把置前后的画面真正合成到桌面
        try:
            shot = capture_screen(screenshot)
            out["desktop_screenshot"] = shot
            out["desktop_screenshot_bytes"] = int(shot.get("bytes") or 0)
        except Exception as exc:  # noqa: BLE001 - evidence failure is reported, not raised
            out["desktop_screenshot"] = {"path": str(screenshot),
                                         "error": f"{type(exc).__name__}:{exc}"}

    if not out["foreground_matched"]:
        out["reason"] = "foreground_not_matched"
    elif not out["window_rect"] or out["window_rect"]["width"] <= 0:
        out["reason"] = "window_rect_unreadable"
    elif screenshot is not None and out["desktop_screenshot_bytes"] <= 0:
        out["reason"] = "desktop_screenshot_failed"
    else:
        out["reason"] = None
    out["proven"] = out["reason"] is None
    return out
