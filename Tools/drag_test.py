# -*- coding: utf-8 -*-
"""Real end-to-end grip drag test: foreground the panel (AttachThreadInput),
drive the physical mouse onto the grip, drag, release, report sizes."""
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
u.SetForegroundWindow.argtypes = [ctypes.c_void_p]
k32 = ctypes.windll.kernel32
k32.GetCurrentThreadId.argtypes = []
u.AttachThreadInput.argtypes = [ctypes.c_uint, ctypes.c_uint, ctypes.c_int]
TITLE = "DeepSeek Status"


def find():
    found = []

    @ctypes.WINFUNCTYPE(ctypes.c_bool, wt.HWND, wt.LPARAM)
    def cb(hwnd, _):
        n = u.GetWindowTextLengthW(hwnd)
        if n:
            buf = ctypes.create_unicode_buffer(n + 1)
            u.GetWindowTextW(hwnd, buf, n + 1)
            if buf.value == TITLE and u.IsWindowVisible(hwnd):
                found.append(hwnd)
                return False
        return True

    u.EnumWindows(cb, 0)
    return found[0] if found else 0


class RECT(ctypes.Structure):
    _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long),
                ("right", ctypes.c_long), ("bottom", ctypes.c_long)]


class POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


hwnd = find()
assert hwnd, "panel not visible"
tid = u.GetWindowThreadProcessId(hwnd, None)
me = k32.GetCurrentThreadId()
print("hwnd:", hwnd, "panel_tid:", tid, "my_tid:", me)
u.AttachThreadInput(me, tid, True)
fore_before = u.GetForegroundWindow()
print("foreground before:", fore_before)
ok = u.SetForegroundWindow(hwnd)
time.sleep(0.5)
print("setforeground:", ok, "foreground now:", u.GetForegroundWindow())

r = RECT()
u.GetWindowRect(hwnd, ctypes.byref(r))
w0, h0 = r.right - r.left, r.bottom - r.top
print(f"start rect=({r.left},{r.top})-({r.right},{r.bottom}) size={w0}x{h0}")

pt0 = POINT()
u.GetCursorPos(ctypes.byref(pt0))
# Native sizing border: press the actual corner edge (not the ◢ span inside).
gx, gy = r.right - 3, r.bottom - 3
u.SetCursorPos(gx, gy)
time.sleep(0.3)
u.mouse_event(0x0002, 0, 0, 0, 0)  # down
time.sleep(0.4)  # let Windows start the native drag
for i in range(1, 11):
    u.SetCursorPos(gx + i * 8, gy + i * 6)
    time.sleep(0.08)
u.mouse_event(0x0004, 0, 0, 0, 0)  # up
time.sleep(0.8)

r2 = RECT()
u.GetWindowRect(hwnd, ctypes.byref(r2))
print(f"end   rect=({r2.left},{r2.top})-({r2.right},{r2.bottom}) size={r2.right-r2.left}x{r2.bottom-r2.top}")
u.SetCursorPos(pt0.x, pt0.y)
u.AttachThreadInput(me, tid, False)
moved_only = (r2.right - r2.left == w0 and r2.bottom - r2.top == h0
              and (r2.left != r.left or r2.top != r.top))
print("RESULT:", "MOVED-ONLY (bug reproduced)" if moved_only else
      ("RESIZED" if (r2.right - r2.left != w0 or r2.bottom - r2.top != h0) else "NO-CHANGE"))
