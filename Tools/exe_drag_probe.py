# -*- coding: utf-8 -*-
"""End-to-end resize probe for the RUNNING exe (or source) panel.

Shows the panel, drives a full system drag cycle via real messages
(WM_LBUTTONDOWN at the corner -> real cursor moves -> WM_LBUTTONUP),
then hides the panel again. No foreground needed.
"""
import ctypes
import ctypes.wintypes as wt
import time

u = ctypes.windll.user32
u.SendMessageW.argtypes = [wt.HWND, ctypes.c_uint, wt.WPARAM, wt.LPARAM]
u.SendMessageW.restype = ctypes.c_long
u.PostMessageW.argtypes = [wt.HWND, ctypes.c_uint, wt.WPARAM, wt.LPARAM]


class RECT(ctypes.Structure):
    _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long),
                ("right", ctypes.c_long), ("bottom", ctypes.c_long)]


class POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


def find():
    found = []

    @ctypes.WINFUNCTYPE(ctypes.c_bool, wt.HWND, wt.LPARAM)
    def cb(hwnd, _):
        n = u.GetWindowTextLengthW(hwnd)
        if n:
            buf = ctypes.create_unicode_buffer(n + 1)
            u.GetWindowTextW(hwnd, buf, n + 1)
            if buf.value == "DeepSeek Status":
                found.append(hwnd)
                return False
        return True

    u.EnumWindows(cb, 0)
    return found[0] if found else 0


def rect_of(hwnd):
    r = RECT()
    u.GetWindowRect(hwnd, ctypes.byref(r))
    return r.left, r.top, r.right, r.bottom


hwnd = find()
assert hwnd, "panel not found"
l0, t0, r0, b0 = rect_of(hwnd)
print(f"start rect=({l0},{t0})-({r0},{b0}) size={r0-l0}x{b0-t0}")

u.ShowWindow(hwnd, 5)  # SW_SHOW
time.sleep(0.6)
l1, t1, r1, b1 = rect_of(hwnd)
w, h = r1 - l1, b1 - t1
print(f"shown rect=({l1},{t1})-({r1},{b1}) size={w}x{h}")

# 1) hook alive? (synchronous hit-test, no mouse needed)
ht = u.SendMessageW(hwnd, 0x0084, 0, ((b1 - 3) << 16) | (r1 - 3))
print("NCHITTEST corner ->", ht, "(17 = hook alive)")

# 2) full system drag: NCLBUTTONDOWN(HTBOTTOMRIGHT) -> real cursor moves ->
#    NCLBUTTONUP. (Posting WM_LBUTTONDOWN would be wrong: it bypasses the
#    NCHITTEST->NC translation that a physical press goes through.)
cur0 = POINT()
u.GetCursorPos(ctypes.byref(cur0))
cx, cy = r1 - 3, b1 - 3  # screen point of the corner
u.SetCursorPos(cx, cy)
time.sleep(0.25)
u.PostMessageW(hwnd, 0x00A1, 17, (cy << 16) | cx)
time.sleep(0.6)  # let DefWindowProc enter the modal sizing loop
for i in range(1, 9):
    u.SetCursorPos(cx + i * 10, cy + i * 8)
    time.sleep(0.09)
u.PostMessageW(hwnd, 0x00A2, 17, ((cy + 72) << 16) | (cx + 80))
time.sleep(0.6)
l2, t2, r2, b2 = rect_of(hwnd)
print(f"end   rect=({l2},{t2})-({r2},{b2}) size={r2-l2}x{b2-t2}")
u.SetCursorPos(cur0.x, cur0.y)
u.ShowWindow(hwnd, 0)  # SW_HIDE: restore prior state
dw, dh = (r2 - l2) - w, (b2 - t2) - h
print("RESULT:", "RESIZED (system drag works)" if dw > 20 and dh > 20
      else f"NO-CHANGE (dw={dw} dh={dh})")
