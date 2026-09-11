"""Finds the PROClient window and captures the battle-log / menu regions."""
import ctypes

import mss
import win32gui
import win32process
from PIL import Image

# Regions as fractions of the client area, measured on the default layout
REGIONS = {
    "log": (0.000, 0.560, 0.400, 1.000),      # Battle Log panel (bottom-left)
    "menu": (0.780, 0.100, 1.000, 0.620),     # move / switch menu (right side)
    "foe_zone": (0.180, 0.130, 0.880, 0.400),  # opponent nameplate + HP bar area
    "my_zone": (0.400, 0.540, 0.980, 0.860),   # my active's nameplate + HP bar
    "party": (0.000, 0.030, 0.150, 0.700),     # my party panel (left edge)
}


def _process_exe(hwnd):
    """Executable path of the window's owning process, or None if unqueryable."""
    try:
        _, pid = win32process.GetWindowThreadProcessId(hwnd)
    except Exception:
        return None
    try:
        k32 = ctypes.windll.kernel32
        handle = k32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
        if not handle:
            return None
        try:
            buf = ctypes.create_unicode_buffer(512)
            size = ctypes.c_ulong(512)
            if k32.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size)):
                return buf.value
        finally:
            k32.CloseHandle(handle)
    except Exception:
        return None
    return None


def find_pro_hwnd():
    """Title match + process verification.

    Many windows can contain 'proclient' in their title (a file-explorer folder,
    a browser tab, a chat) - reading those pixels poisons every OCR read. A
    candidate is only accepted when its owning process is actually
    PROClient.exe; when the process can't be queried we fall back to the
    title-only match (old behavior) rather than refusing the real game."""
    found = []

    def cb(hwnd, _):
        if not win32gui.IsWindowVisible(hwnd):
            return
        title = (win32gui.GetWindowText(hwnd) or "").lower()
        if "proclient" not in title:
            return
        exe = _process_exe(hwnd)
        if exe is not None and not exe.lower().endswith("proclient.exe"):
            return   # confirmed impostor (explorer/browser/chat with a matching title)
        found.append(hwnd)

    win32gui.EnumWindows(cb, None)
    return found[0] if found else None


def client_rect(hwnd):
    l, t, r, b = win32gui.GetClientRect(hwnd)
    x, y = win32gui.ClientToScreen(hwnd, (0, 0))
    return x, y, x + r, y + b


def grab_regions(hwnd, regions=REGIONS):
    """Returns {name: PIL.Image} for the requested regions, or {} if window is gone."""
    try:
        x0, y0, x1, y1 = client_rect(hwnd)
    except win32gui.error:
        return {}
    w, h = x1 - x0, y1 - y0
    if w <= 0 or h <= 0:
        return {}
    out = {}
    with mss.mss() as sct:
        for name, (fx0, fy0, fx1, fy1) in regions.items():
            box = {
                "left": int(x0 + fx0 * w),
                "top": int(y0 + fy0 * h),
                "width": max(8, int((fx1 - fx0) * w)),
                "height": max(8, int((fy1 - fy0) * h)),
            }
            shot = sct.grab(box)
            out[name] = Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")
    return out
