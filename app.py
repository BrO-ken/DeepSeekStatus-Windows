# -*- coding: utf-8 -*-
"""
DeepSeek Status pour Windows — adaptation de DeepSeekStatus (macOS, MIT © Zhao Xin).

Baleine dans la zone de notification Windows 11 : indique en permanence si
DeepSeek est en plein tarif ou en heures creuses, avec panneau de détails
(compte à rebours, heatmap hebdomadaire, aperçu, démarrage avec Windows).
"""
from __future__ import annotations

import ctypes
import json
import os
import sys
import threading
import time
import winreg
from datetime import datetime, timezone
from pathlib import Path

import pystray
import webview
from PIL import Image

from schedule import (BEIJING, OFF, PEAK, next_transition, period_at,
                      previous_boundary, progress, week_matrix)

APP_TITLE = "DeepSeek Status"
VERSION = "1.0.0"
MUTEX_NAME = "DeepSeekStatusWin_Mutex"
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
RUN_VAL = "DeepSeekStatusWin"
JOURS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

if getattr(sys, "frozen", False):
    BUNDLE = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    APP_DIR = Path(sys.executable).parent
else:
    BUNDLE = Path(__file__).resolve().parent
    APP_DIR = BUNDLE
ASSETS = BUNDLE / "assets"
WEB_DIR = BUNDLE / "web"

WHALE_PATH = (ASSETS / "whale_path.txt").read_text(encoding="utf-8").strip()

PANEL_W = 372
PANEL_H = 676


# ------------------------------------------------------------------ état partagé
class State:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.preview: str | None = None
        self.launch_at_login = False
        self.panel_visible = False


state = State()
window = None  # créé dans main()


# ----------------------------------------------------------------------- config
def config_file() -> Path:
    base = Path(os.environ.get("LOCALAPPDATA", str(APP_DIR))) / "DeepSeekStatusWin"
    base.mkdir(parents=True, exist_ok=True)
    return base / "config.json"


DEFAULTS = {"preview": None, "launch_at_login": False, "open_panel_on_start": False,
            "panel_w": None, "panel_h": None}


def load_config() -> dict:
    cfg = dict(DEFAULTS)
    try:
        cfg.update(json.loads(config_file().read_text(encoding="utf-8")))
    except Exception:
        pass
    return cfg


def save_config(cfg: dict) -> None:
    config_file().write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")


# ------------------------------------------------------------ instance unique
_mutex_handle = None


def already_running() -> bool:
    global _mutex_handle
    k32 = ctypes.windll.kernel32
    _mutex_handle = k32.CreateMutexW(None, False, MUTEX_NAME)
    return bool(k32.GetLastError() == 183)  # ERROR_ALREADY_EXISTS


# ------------------------------------------------- démarrage avec Windows (HKCU)
def startup_command() -> str:
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}"'
    exe = APP_DIR / "dist" / "DeepSeekStatus.exe"
    if exe.exists():
        return f'"{exe}"'
    pyw = Path(sys.executable).with_name("pythonw.exe")
    return f'"{pyw}" "{APP_DIR / "app.py"}"'


def get_launch_at_login() -> bool:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_READ) as k:
            v, _ = winreg.QueryValueEx(k, RUN_VAL)
            return bool(v)
    except OSError:
        return False


def set_launch_at_login_registry(on: bool) -> None:
    if on:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
            winreg.SetValueEx(k, RUN_VAL, 0, winreg.REG_SZ, startup_command())
    else:
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
                winreg.DeleteValue(k, RUN_VAL)
        except FileNotFoundError:
            pass


# -------------------------------------------------------------- API Win32 utile
class RECT(ctypes.Structure):
    _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long),
                ("right", ctypes.c_long), ("bottom", ctypes.c_long)]


def work_area() -> RECT:
    """Zone de travail (sans barre des tâches). Repli sûr si l'API échoue."""
    r = RECT()
    ok = ctypes.windll.user32.SystemParametersInfoW(0x004F, 0, ctypes.byref(r), 0)
    if not ok or r.right <= r.left or r.bottom <= r.top:
        w = ctypes.windll.user32.GetSystemMetrics(0)   # SM_CXSCREEN
        h = ctypes.windll.user32.GetSystemMetrics(1)   # SM_CYSCREEN
        print(f"[workarea] repli GetSystemMetrics: {w}x{h}", flush=True)
        r = RECT(0, 0, w, max(200, h - 48))
    return r


def find_hwnd(title: str) -> int:
    user32 = ctypes.windll.user32
    found = []

    @ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
    def cb(hwnd, _lparam):
        n = user32.GetWindowTextLengthW(hwnd)
        if n:
            buf = ctypes.create_unicode_buffer(n + 1)
            user32.GetWindowTextW(hwnd, buf, n + 1)
            if buf.value == title:
                found.append(hwnd)
                return False
        return True

    user32.EnumWindows(cb, 0)
    return found[0] if found else 0


def polish_window(hwnd: int) -> None:
    """Coins arrondis + liseré accent (Windows 11). Silencieux sur Windows 10."""
    try:
        dwm = ctypes.windll.dwmapi
        round_pref = ctypes.c_int(2)        # DWMWCP_ROUND
        dwm.DwmSetWindowAttribute(hwnd, 33, ctypes.byref(round_pref), 4)
        border = ctypes.c_uint(0x00FE6B4D)  # COLORREF (BGR) du bleu #4D6BFE
        dwm.DwmSetWindowAttribute(hwnd, 34, ctypes.byref(border), 4)
    except Exception:
        pass


# --------------------------------------------------------------- ouverture/fermeture
def panel_origin() -> tuple[int, int]:
    wa = work_area()
    h = min(PANEL_H, wa.bottom - wa.top - 48)
    return max(0, wa.right - PANEL_W - 12), max(0, wa.bottom - h - 12)


def open_panel(w) -> None:
    x, y = panel_origin()
    w.show()
    # pywebview n'applique resize/move correctement qu'une fois la fenêtre montrée.
    try:
        w.events.shown.wait(5)
    except Exception:
        pass
    w.resize(PANEL_W, PANEL_H)
    w.move(x, y)
    threading.Timer(0.8, _assert_geometry).start()
    state.panel_visible = True


def _assert_geometry() -> None:
    """Ceinture et bretelles : réasserte la géométrie via Win32 natif (pixels physiques)."""
    try:
        hwnd = find_hwnd(APP_TITLE)
        if not hwnd:
            print("[geometry] hwnd introuvable", flush=True)
            return
        try:
            dpi = ctypes.windll.user32.GetDpiForWindow(hwnd)
        except Exception:
            dpi = 96
        s = (dpi or 96) / 96.0
        x, y = panel_origin()
        SWP_NOACTIVATE = 0x0010
        SWP_SHOWWINDOW = 0x0040
        ctypes.windll.user32.SetWindowPos(
            hwnd, -2, int(x * s), int(y * s), int(PANEL_W * s), int(PANEL_H * s),
            SWP_NOACTIVATE | SWP_SHOWWINDOW)
        r = RECT()
        ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(r))
        print(f"[geometry] hwnd={hwnd} rect=({r.left},{r.top})-({r.right},{r.bottom}) dpi={dpi}", flush=True)
        polish_window(hwnd)
    except Exception as e:
        print("[geometry]", repr(e), flush=True)


def toggle_panel(w) -> None:
    if state.panel_visible:
        w.hide()
        state.panel_visible = False
    else:
        open_panel(w)


class POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


def _grip_resize_loop() -> None:
    """Boucle de redimensionnement natif : suit le curseur tant que le bouton
    gauche est enfoncé, puis replace le panneau au bord et persiste la taille.
    (Les mousemove JS ne sont plus délivrés dès que le curseur sort de la
    fenêtre — exactement là où il faut aller pour l'agrandir.)"""
    global PANEL_W, PANEL_H
    user32 = ctypes.windll.user32
    hwnd = find_hwnd(APP_TITLE)
    if not hwnd:
        return
    try:
        dpi = user32.GetDpiForWindow(hwnd)
    except Exception:
        dpi = 96
    s = (dpi or 96) / 96.0
    wa = work_area()
    w_max = max(300, wa.right - wa.left - 20)
    h_max = max(320, int((wa.bottom - wa.top - 24) / s))
    pt = POINT()
    t0 = time.monotonic()
    user32.GetCursorPos(ctypes.byref(pt))
    r = RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(r))
    # The JS bridge takes a moment to start this thread: wait (max 1 s) for
    # the button to actually be down before tracking, so no drag is missed.
    while not (user32.GetAsyncKeyState(0x01) & 0x8000):
        if time.monotonic() - t0 > 1.0:
            print("[resize] bouton jamais pressé", flush=True)
            return
        time.sleep(0.02)
    # Where the cursor grabbed the corner: the corner then tracks the cursor
    # exactly (no snap on grab).
    off_x = pt.x - r.right
    off_y = pt.y - r.bottom
    print("[resize] grip drag start", flush=True)
    while True:
        if not (user32.GetAsyncKeyState(0x01) & 0x8000):  # VK_LBUTTON released
            break
        if time.monotonic() - t0 > 30:  # safety: never loop for more than 30 s
            break
        user32.GetCursorPos(ctypes.byref(pt))
        r = RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(r))
        w = max(300, min(int((pt.x - off_x - r.left) / s),
                         w_max, wa.right - r.left - 12))
        h = max(320, min(int((pt.y - off_y - r.top) / s), h_max,
                         int((wa.bottom - r.top - 12) / s)))
        if w != PANEL_W or h != PANEL_H:
            PANEL_W, PANEL_H = w, h
            user32.SetWindowPos(hwnd, -2, r.left, r.top,
                                int(w * s), int(h * s), 0x0010 | 0x0040)
        time.sleep(0.025)
    x, y = panel_origin()  # re-anchor bottom-right with the new size
    user32.SetWindowPos(hwnd, -2, int(x * s), int(y * s),
                        int(PANEL_W * s), int(PANEL_H * s), 0x0010 | 0x0040)
    cfg = load_config()
    cfg["panel_w"], cfg["panel_h"] = PANEL_W, PANEL_H
    save_config(cfg)
    print(f"[resize] final {PANEL_W}x{PANEL_H}", flush=True)


def resize_panel_to(w, h) -> None:
    """Programmatic resize (tests / API): clamp, keep the bottom-right anchor."""
    global PANEL_W, PANEL_H
    try:
        hwnd = find_hwnd(APP_TITLE)
        if not hwnd:
            print("[resize] hwnd introuvable", flush=True)
            return
        try:
            dpi = ctypes.windll.user32.GetDpiForWindow(hwnd)
        except Exception:
            dpi = 96
        s = (dpi or 96) / 96.0
        wa = work_area()
        w_max = max(300, int(wa.right - wa.left - 20))
        h_max = max(320, int((wa.bottom - wa.top - 24) / s))
        PANEL_W = max(300, min(int(w), w_max))
        PANEL_H = max(320, min(int(h), h_max))
        x, y = panel_origin()
        ctypes.windll.user32.SetWindowPos(
            hwnd, -2, int(x * s), int(y * s), int(PANEL_W * s), int(PANEL_H * s),
            0x0010 | 0x0040)
        print(f"[resize] -> {PANEL_W}x{PANEL_H} @ {x},{y}", flush=True)
    except Exception as e:
        print("[resize] erreur:", repr(e), flush=True)


# ------------------------------------------------------------- API exposée au JS
class Api:
    def close_panel(self):
        if window is not None:
            window.hide()
            state.panel_visible = False
            cfg = load_config()
            cfg["panel_w"], cfg["panel_h"] = PANEL_W, PANEL_H
            save_config(cfg)
        return True

    def begin_resize(self):
        state.grip_calls = getattr(state, "grip_calls", 0) + 1
        print("[api] begin_resize", flush=True)
        # Native drag loop in a worker thread: it follows the real cursor even
        # outside the window, until the left mouse button is released.
        threading.Thread(target=_grip_resize_loop, daemon=True).start()
        return True

    def set_size(self, w, h):
        print(f"[api] set_size({w},{h})", flush=True)
        if window is not None:
            resize_panel_to(w, h)
        return True

    def set_preview(self, mode):
        with state.lock:
            state.preview = (mode or None)
        cfg = load_config()
        cfg["preview"] = state.preview
        save_config(cfg)
        return True

    def set_launch_at_login(self, on):
        on = bool(on)
        set_launch_at_login_registry(on)
        with state.lock:
            state.launch_at_login = on
        cfg = load_config()
        cfg["launch_at_login"] = on
        save_config(cfg)
        return on == get_launch_at_login()


# ----------------------------------------------------------------- état → UI/tray
def build_state(now: datetime) -> dict:
    real = period_at(now)
    nxt = next_transition(now)
    secs = max(0, int((nxt - now).total_seconds()))
    cd = f"{secs // 3600:02d}:{secs % 3600 // 60:02d}:{secs % 60:02d}"
    bj = now.astimezone(BEIJING)
    nbj = nxt.astimezone(BEIJING)
    ddays = (nbj.date() - bj.date()).days
    when = "today" if ddays == 0 else ("tomorrow" if ddays == 1 else JOURS[nbj.weekday()])
    with state.lock:
        preview = state.preview
    shown = preview or real
    is_peak = shown == PEAK
    pct = round(progress(now) * 100)
    off_local = now.astimezone().utcoffset()
    off_bj = now.astimezone(BEIJING).utcoffset()
    return {
        "version": VERSION,
        "period": shown,
        "preview": preview,
        "isPeak": is_peak,
        "chip": (("PREVIEW · " if preview else "")
                 + ("PEAK · ×1.0" if is_peak else "OFF-PEAK · ×0.5")),
        "countdown": cd,
        "nextLabel": ("Next off-peak switch" if real == PEAK
                      else "Next peak switch"),
        "nextAt": f"{when} at {nbj:%H:%M} (Beijing time)",
        "blockPct": pct,
        "beijingClock": f"{bj:%H:%M:%S}",
        "beijingDate": f"{JOURS[bj.weekday()]} {bj:%d/%m}",
        "tzDifferent": off_local != off_bj,
        "week": week_matrix(),
        "curDay": bj.weekday(),
        "curHour": bj.hour,
        "launchAtLogin": state.launch_at_login,
    }


def tray_image(shown_period: str) -> Image.Image:
    name = "whale_peak.png" if shown_period == PEAK else "whale_offpeak.png"
    return Image.open(ASSETS / name)


def tooltip_for(real: str, countdown: str, nbj) -> str:
    lbl = "Peak ×1.0" if real == PEAK else "Off-peak ×0.5"
    return f"DeepSeek — {lbl} · {countdown} until {nbj:%H:%M}"


# --------------------------------------------------------------------- updater 1 Hz
def updater(w, icon, loaded: threading.Event, open_now: bool) -> None:
    loaded.wait(20)
    try:
        w.evaluate_js("window.__setWhale(" + json.dumps(WHALE_PATH) + ")")
    except Exception as e:
        print("[updater] setWhale:", repr(e), flush=True)
    if open_now:
        open_panel(w)
        try:
            geo = w.evaluate_js(
                "window.outerWidth + 'x' + window.outerHeight"
                + " + ' @ ' + window.screenX + ',' + window.screenY")
            print("[panel] géométrie:", geo, flush=True)
        except Exception as e:
            print("[panel] diag:", repr(e), flush=True)
    last_icon_key = None
    selfcheck_done = False
    while True:
        try:
            now = datetime.now(timezone.utc)
            s = build_state(now)
            w.evaluate_js("window.__update(" + json.dumps(s, ensure_ascii=False) + ")")
            if not selfcheck_done and state.panel_visible:
                selfcheck_done = True
                try:
                    js = ("JSON.stringify({"
                          "chip: document.getElementById('chip').textContent,"
                          "countdown: document.getElementById('countdown').textContent,"
                          "nextAt: document.getElementById('nextAt').textContent,"
                          "nextLabel: document.getElementById('nextLabel').textContent,"
                          "meta: document.getElementById('progressMeta').textContent,"
                          "cells: document.querySelectorAll('#weekGrid .cell').length,"
                          "nowCell: document.querySelectorAll('#weekGrid .cell.now').length,"
                          "bannerHidden: document.getElementById('previewBanner').hidden,"
                          "bannerDisplay: getComputedStyle(document.getElementById('previewBanner')).display,"
                          "appClass: document.getElementById('app').className,"
                          "whaleLen: document.getElementById('whalePath').getAttribute('d').length,"
                          "tz: document.getElementById('tzNote').textContent,"
                          "ver: document.getElementById('ver').textContent,"
                          "preview: (window.__state||{}).preview,"
                          "jsVer: window.__APP_JS_VERSION||0,"
                          "grip: !!document.getElementById('grip')})")
                    import re as _re
                    raw = w.evaluate_js(js)
                    d = json.loads(raw)
                    want_banner_hidden = d.get("preview") is None
                    ok = (bool(_re.fullmatch(r"\d{2}:\d{2}:\d{2}", d["countdown"]))
                          and d["cells"] == 168 and d["nowCell"] == 1
                          and d["bannerHidden"] is want_banner_hidden
                          and (d["bannerDisplay"] == "none") == want_banner_hidden
                          and d["whaleLen"] == 1974
                          and (("peak" in d["appClass"].split()) == ("×1.0" in d["chip"]))
                          and (d["chip"].startswith("PREVIEW") == bool(d.get("preview")))
                          and d.get("grip") is True and d.get("jsVer", 0) >= 3)
                    print("[selfcheck]", json.dumps(d, ensure_ascii=False),
                          "=> VERDICT:", "OK" if ok else "ECHEC", flush=True)
                    if ok and "--selftest" in sys.argv:
                        # Test du pont JS→Python : clic réel sur le bouton ✕ de l'UI.
                        w.evaluate_js("document.getElementById('closeBtn').click()")
                        time.sleep(2.0)
                        closed = state.panel_visible is False
                        open_panel(w)
                        time.sleep(1.0)
                        print("[selftest] fermeture via bouton JS :",
                              "OK" if closed else "ECHEC", flush=True)
                        # Test du redimensionnement : direct puis via le pont JS.
                        resize_panel_to(420, 600)
                        time.sleep(0.5)
                        d_ok = (PANEL_W == 420 and PANEL_H == 600)
                        print("[selftest] resize direct :",
                              "OK" if d_ok else f"ECHEC ({PANEL_W}x{PANEL_H})", flush=True)
                        w.evaluate_js("pywebview.api.set_size(440, 640)")
                        time.sleep(1.2)
                        r_ok = (PANEL_W == 440 and PANEL_H == 640)
                        resize_panel_to(372, 676)
                        time.sleep(0.5)
                        print("[selftest] resize via poignée (pont JS) :",
                              "OK" if r_ok else f"ECHEC ({PANEL_W}x{PANEL_H})", flush=True)
                        # Poignée : test du câblage mousedown → API. Les clics
                        # souris synthétiques ne peuvent pas atteindre un
                        # panneau non-topmost depuis cet environnement de test.
                        before = getattr(state, "grip_calls", 0)
                        w.evaluate_js(
                            "document.getElementById('grip').dispatchEvent("
                            "new MouseEvent('mousedown',{bubbles:true,cancelable:true}))")
                        time.sleep(1.8)  # la boucle attend le bouton 1 s puis renonce
                        g_ok = getattr(state, "grip_calls", 0) > before
                        print("[selftest] poignée (câblage mousedown→API) :",
                              "OK" if g_ok else "ECHEC", flush=True)
                        resize_panel_to(372, 676)
                except Exception as e:
                    print("[selfcheck] erreur:", repr(e), flush=True)
            real = period_at(now)
            with state.lock:
                preview = state.preview
            key = (real, preview)
            if key != last_icon_key:
                icon.icon = tray_image(preview or real)
                last_icon_key = key
            icon.title = tooltip_for(real, s["countdown"], next_transition(now).astimezone(BEIJING))
        except Exception as e:
            print("[updater]", repr(e), flush=True)
        time.sleep(1.0)


# ------------------------------------------------------------------- menu du tray
def make_menu():
    def on_show(icon_, item):
        if window is not None:
            open_panel(window)

    def on_quit(icon_, item):
        try:
            icon_.stop()
        finally:
            try:
                if window is not None:
                    window.destroy()
            except Exception:
                pass
            os._exit(0)

    def prev(mode):
        def _a(icon_, item):
            Api().set_preview(mode)
        return _a

    def on_login(icon_, item):
        Api().set_launch_at_login(not state.launch_at_login)

    return pystray.Menu(
        pystray.MenuItem("Show panel", on_show, default=True),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Preview", pystray.Menu(
            pystray.MenuItem("Follow real time", prev(None), radio=True,
                             checked=lambda it: state.preview is None),
            pystray.MenuItem("Peak", prev(PEAK), radio=True,
                             checked=lambda it: state.preview == PEAK),
            pystray.MenuItem("Off-peak", prev(OFF), radio=True,
                             checked=lambda it: state.preview == OFF),
        )),
        pystray.MenuItem("Start with Windows", on_login,
                         checked=lambda it: state.launch_at_login),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Quit", on_quit),
    )


# --------------------------------------------------------------------------- main
def _prepare_boot_page() -> Path:
    """Copy of index.html with cache-busting query strings on css/js, so the
    WebView never serves a stale UI after an update."""
    src = WEB_DIR / "index.html"
    stamp = "+".join(str(int(p.stat().st_mtime)) for p in
                     (src, WEB_DIR / "app.js", WEB_DIR / "style.css"))
    html = (src.read_text(encoding="utf-8")
            .replace('href="style.css"', f'href="style.css?v={stamp}"')
            .replace('src="app.js"', f'src="app.js?v={stamp}"'))
    out = WEB_DIR / "_boot.html"
    out.write_text(html, encoding="utf-8")
    return out


def main() -> None:
    global window, PANEL_H, PANEL_W
    if already_running():
        print("DeepSeek Status tourne déjà (instance unique).")
        return
    cfg = load_config()
    with state.lock:
        state.preview = cfg.get("preview")
        state.launch_at_login = get_launch_at_login()
    if "--preview" in sys.argv:  # aperçu ponctuel (tests), non persisté
        i = sys.argv.index("--preview")
        if i + 1 < len(sys.argv):
            with state.lock:
                state.preview = sys.argv[i + 1] if sys.argv[i + 1] in (PEAK, OFF) else None

    wa = work_area()
    # DPI: pywebview works in logical pixels; the physical window must fit the screen.
    try:
        scale = ctypes.windll.user32.GetDpiForSystem() / 96.0
    except Exception:
        scale = 1.0
    if scale <= 0:
        scale = 1.0
    PANEL_W = max(300, min(int(cfg.get("panel_w") or PANEL_W), int(wa.right - wa.left - 20)))
    PANEL_H = max(320, min(int(cfg.get("panel_h") or PANEL_H), int((wa.bottom - wa.top - 24) / scale)))
    print(f"[dpi] scale={scale} panel={PANEL_W}x{PANEL_H}", flush=True)

    loaded = threading.Event()
    px, py = panel_origin()
    window = webview.create_window(
        APP_TITLE, str(_prepare_boot_page()),
        js_api=Api(), width=PANEL_W, height=PANEL_H, x=px, y=py,
        frameless=True, easy_drag=False, hidden=True,
        background_color="#0B0E17",
    )
    window.events.loaded += lambda: loaded.set()

    now = datetime.now(timezone.utc)
    icon = pystray.Icon("DeepSeekStatus", tray_image(cfg.get("preview") or period_at(now)),
                        APP_TITLE, make_menu())
    threading.Thread(target=icon.run, daemon=True).start()

    open_now = bool(cfg.get("open_panel_on_start")) or ("--show" in sys.argv)
    webview.start(updater, args=(window, icon, loaded, open_now), gui="edgechromium")


if __name__ == "__main__":
    main()
