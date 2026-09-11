# -*- coding: utf-8 -*-
"""Capture la fenêtre « DeepSeek Status » via PrintWindow (Win32) + info de géométrie."""
import ctypes
import ctypes.wintypes as wt
import sys
from pathlib import Path

user32 = ctypes.windll.user32
TITLE = "DeepSeek Status"


def find() -> int:
    found = []

    @ctypes.WINFUNCTYPE(ctypes.c_bool, wt.HWND, wt.LPARAM)
    def cb(hwnd, _lp):
        n = user32.GetWindowTextLengthW(hwnd)
        if n:
            buf = ctypes.create_unicode_buffer(n + 1)
            user32.GetWindowTextW(hwnd, buf, n + 1)
            if buf.value == TITLE:
                found.append(hwnd)
                return False
        return True

    user32.EnumWindows(cb, 0)
    return found[0] if found else 0


hwnd = find()
if not hwnd:
    print("RESULT: window not found")
    sys.exit(1)

rect = wt.RECT()
user32.GetWindowRect(hwnd, ctypes.byref(rect))


class PT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


class RC(ctypes.Structure):
    _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long),
                ("right", ctypes.c_long), ("bottom", ctypes.c_long)]


class WINDOWPLACEMENT(ctypes.Structure):
    _fields_ = [("length", ctypes.c_uint), ("flags", ctypes.c_uint),
                ("showCmd", ctypes.c_uint), ("ptMinPosition", PT),
                ("ptMaxPosition", PT), ("rcNormalPosition", RC)]


placement = WINDOWPLACEMENT()
placement.length = ctypes.sizeof(placement)
user32.GetWindowPlacement(hwnd, ctypes.byref(placement))
print(f"RESULT: rect=({rect.left},{rect.top})-({rect.right},{rect.bottom}) "
      f"size={rect.right - rect.left}x{rect.bottom - rect.top} "
      f"showcmd={placement.showCmd} (1=normal 2=minimise 3=maximise)")

if len(sys.argv) > 1:
    from PIL import Image
    w, h = rect.right - rect.left, rect.bottom - rect.top
    hdc = user32.GetWindowDC(hwnd)
    mem = ctypes.windll.gdi32.CreateCompatibleDC(hdc)
    bmp = ctypes.windll.gdi32.CreateCompatibleBitmap(hdc, w, h)
    ctypes.windll.gdi32.SelectObject(mem, bmp)
    ok = user32.PrintWindow(hwnd, mem, 2)  # 2 = PW_RENDERFULLCONTENT
    class BMPINFOHEADER(ctypes.Structure):
        _fields_ = [("biSize", ctypes.c_uint32), ("biWidth", ctypes.c_int32),
                    ("biHeight", ctypes.c_int32), ("biPlanes", ctypes.c_uint16),
                    ("biBitCount", ctypes.c_uint16), ("biCompression", ctypes.c_uint32),
                    ("biSizeImage", ctypes.c_uint32), ("biXPelsPerMeter", ctypes.c_int32),
                    ("biYPelsPerMeter", ctypes.c_int32), ("biClrUsed", ctypes.c_uint32),
                    ("biClrImportant", ctypes.c_uint32)]
    bi = BMPINFOHEADER(ctypes.sizeof(BMPINFOHEADER), w, -h, 1, 32, 0, 0, 0, 0, 0, 0)
    buf = ctypes.create_string_buffer(w * h * 4)
    ctypes.windll.gdi32.GetDIBits(mem, bmp, 0, h, buf, ctypes.byref(bi), 0)
    img = Image.frombuffer("RGBA", (w, h), buf.raw, "raw", "BGRA", 0, 1)
    img.save(sys.argv[1])
    print(f"RESULT: printwindow ok={ok} -> {sys.argv[1]}")
