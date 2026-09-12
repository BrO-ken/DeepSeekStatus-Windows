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
u.SetWindowPos.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int,
                           ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_uint]
u.SetWindowPos.restype = ctypes.c_int
u.GetWindowRect.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
u.GetWindowRect.restype = ctypes.c_int
u.SetCursorPos.argtypes = [ctypes.c_int, ctypes.c_int]
u.SendMessageW.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_void_p, ctypes.c_void_p]
u.SendMessageW.restype = ctypes.c_long
u.PostMessageW.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_void_p, ctypes.c_void_p]
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

# 2) REAL physical drag (the exact user gesture): TOPMOST first so the press
#    truly lands on the panel, then physical DOWN / slow moves / physical UP.
#    (Message-posted button events were proven unable to drive the system
#    sizing loop; only a physical press works.)
u.ShowWindow(hwnd, 5)  # SW_SHOW (already shown, harmless)
u.SetWindowPos(hwnd, -1, 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0040)  # TOPMOST
time.sleep(0.4)
ex = u.GetWindowLongW(hwnd, -20)
print("topmost effectif:", bool(ex & 0x8), flush=True)
l1, t1, r1, b1 = rect_of(hwnd)
w, h = r1 - l1, b1 - t1
cur0 = POINT()
u.GetCursorPos(ctypes.byref(cur0))
# drag INWARD (shrink): plenty of room, unambiguous verdict
cx, cy = r1 - 20, b1 - 16  # on the visible grip glyph
u.SetCursorPos(cx, cy)
time.sleep(0.3)
u.mouse_event(0x0002, 0, 0, 0, 0)
time.sleep(0.5)
for i in range(1, 9):
    u.SetCursorPos(cx - i * 10, cy - i * 8)
    time.sleep(0.12)
u.mouse_event(0x0004, 0, 0, 0, 0)
time.sleep(0.6)
l2, t2, r2, b2 = rect_of(hwnd)
print(f"end   rect=({l2},{t2})-({r2},{b2}) size={r2-l2}x{b2-t2}")
u.SetCursorPos(cur0.x, cur0.y)
u.SetWindowPos(hwnd, -1, 0, 0, 0, 0, 0x0001 | 0x0002)  # stay topmost (usable panel)
u.ShowWindow(hwnd, 0)  # SW_HIDE: restore prior state
dw, dh = (r2 - l2) - w, (b2 - t2) - h
print("RESULT:", "RESIZED (physical drag works)" if abs(dw) > 20 and abs(dh) > 20
      else f"NO-CHANGE (dw={dw} dh={dh})")
# restore the pre-test size so the user finds their panel unchanged
# (keep TOPMOST: the app now maintains it while visible)
u.SetWindowPos(hwnd, -1, l1, t1, w, h, 0x0010 | 0x0040)
time.sleep(0.3)
print("restored:", rect_of(hwnd))
