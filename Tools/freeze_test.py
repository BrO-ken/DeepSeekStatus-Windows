# -*- coding: utf-8 -*-
"""Reproduce the frozen-clock scenario: open -> close (API) -> 30 s hidden ->
show again -> the countdown must be live. Also asserts the app log has no
runaway '_call' thread exceptions."""
import ctypes
import ctypes.wintypes as wt
import hashlib
import time

import sys
sys.path.insert(0, r"C:\Users\Administrator\Desktop\DeepSeek Status\DeepSeekStatusWin")

u = ctypes.windll.user32
u.SendMessageW.argtypes = [wt.HWND, ctypes.c_uint, wt.WPARAM, wt.LPARAM]
u.SendMessageW.restype = ctypes.c_long
u.PostMessageW.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_void_p, ctypes.c_void_p]


def find(visible_only):
    out = []

    @ctypes.WINFUNCTYPE(ctypes.c_bool, wt.HWND, wt.LPARAM)
    def cb(hwnd, _):
        n = u.GetWindowTextLengthW(hwnd)
        if n:
            b = ctypes.create_unicode_buffer(n + 1)
            u.GetWindowTextW(hwnd, b, n + 1)
            if b.value == "DeepSeek Status" and (not visible_only or u.IsWindowVisible(hwnd)):
                out.append(hwnd)
        return True

    u.EnumWindows(cb, 0)
    return out[0] if out else 0


def grab(tag):
    import subprocess
    subprocess.run([r"C:\Users\Administrator\Desktop\DeepSeek Status\DeepSeekStatusWin\venv\Scripts\python.exe",
                    r"C:\Users\Administrator\Desktop\DeepSeek Status\DeepSeekStatusWin\Tools\capture_window.py",
                    rf"C:\Users\Administrator\Desktop\DeepSeek Status\DeepSeekStatusWin\_{tag}.png"],
                   capture_output=True)
    return hashlib.sha256(open(rf"C:\Users\Administrator\Desktop\DeepSeek Status\DeepSeekStatusWin\_{tag}.png", "rb").read()).hexdigest()[:16]


hwnd = find(True)
if not hwnd:
    hwnd = find(False)
    assert hwnd, "window must exist at least"
    u.ShowWindow(hwnd, 5)  # tray-style open for the test
    time.sleep(3)
    hwnd = find(True)
assert hwnd, "panel must be visible at start"
h1 = grab("f1"); time.sleep(3); h2 = grab("f2")
print("ouvert  : ", "VIT" if h1 != h2 else "FIGE <<<<", h1, h2)

# close via the ✕ button inside the page (real API path, sets panel_visible False)
# (pywebview hides through window.hide(); emulate with Win32 too)
u.ShowWindow(hwnd, 0)  # SW_HIDE
print("cache   : 30 s...")
time.sleep(30)

u.ShowWindow(hwnd, 5)  # SW_SHOW like the tray click
time.sleep(3)  # visibilitychange -> tick resume
h3 = grab("f3"); time.sleep(3); h4 = grab("f4")
print("revient :", "VIT" if h3 != h4 else "FIGE <<<<", h3, h4)

log = open(r"C:\Users\Administrator\Desktop\DeepSeek Status\DeepSeekStatusWin\_run.log",
           encoding="utf-8", errors="ignore").read()
print("lignes 'Exception in thread':", log.count("Exception in thread"))
print("RESULT:", "PASS" if (h1 != h2 and h3 != h4 and log.count("Exception in thread") == 0) else "FAIL")
