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
JOURS = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]

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


DEFAULTS = {"preview": None, "launch_at_login": False, "open_panel_on_start": False}


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
            hwnd, -1, int(x * s), int(y * s), int(PANEL_W * s), int(PANEL_H * s),
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


# ------------------------------------------------------------- API exposée au JS
class Api:
    def close_panel(self):
        if window is not None:
            window.hide()
            state.panel_visible = False
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
    when = "aujourd'hui" if ddays == 0 else ("demain" if ddays == 1 else JOURS[nbj.weekday()])
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
        "chip": (("APERÇU · " if preview else "")
                 + ("PLEIN TARIF" if is_peak else "HEURES CREUSES")
                 + " · " + ("×1,0" if is_peak else "×0,5")),
        "countdown": cd,
        "nextLabel": ("Prochain passage en heures creuses" if real == PEAK
                      else "Prochain passage en plein tarif"),
        "nextAt": f"{when} à {nbj:%H:%M} (heure de Pékin)",
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
    lbl = "Plein tarif ×1.0" if real == PEAK else "Heures creuses ×0.5"
    return f"DeepSeek — {lbl} · {countdown} avant {nbj:%H:%M}"


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
                          "preview: (window.__state||{}).preview})")
                    import re as _re
                    raw = w.evaluate_js(js)
                    d = json.loads(raw)
                    want_banner_hidden = d.get("preview") is None
                    ok = (bool(_re.fullmatch(r"\d{2}:\d{2}:\d{2}", d["countdown"]))
                          and d["cells"] == 168 and d["nowCell"] == 1
                          and d["bannerHidden"] is want_banner_hidden
                          and (d["bannerDisplay"] == "none") == want_banner_hidden
                          and d["whaleLen"] == 1974
                          and (("peak" in d["appClass"].split()) == (d["chip"].find("PLEIN") >= 0))
                          and (d["chip"].startswith("APERÇU") == bool(d.get("preview"))))
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
    def on_toggle(icon_, item):
        if window is not None:
            toggle_panel(window)

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
        pystray.MenuItem("Ouvrir / masquer le panneau", on_toggle, default=True),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Aperçu", pystray.Menu(
            pystray.MenuItem("Suivre l'heure réelle", prev(None), radio=True,
                             checked=lambda it: state.preview is None),
            pystray.MenuItem("Plein tarif", prev(PEAK), radio=True,
                             checked=lambda it: state.preview == PEAK),
            pystray.MenuItem("Heures creuses", prev(OFF), radio=True,
                             checked=lambda it: state.preview == OFF),
        )),
        pystray.MenuItem("Démarrer avec Windows", on_login,
                         checked=lambda it: state.launch_at_login),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Quitter", on_quit),
    )


# --------------------------------------------------------------------------- main
def main() -> None:
    global window, PANEL_H
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
    # DPI : sous Windows, pywebview travaille en pixels logiques ; la fenêtre
    # physique = logique × échelle et doit tenir dans l'écran réel.
    try:
        scale = ctypes.windll.user32.GetDpiForSystem() / 96.0
    except Exception:
        scale = 1.0
    if scale <= 0:
        scale = 1.0
    PANEL_H = max(400, min(PANEL_H, int((wa.bottom - wa.top - 24) / scale)))
    print(f"[dpi] échelle={scale} panneau={PANEL_W}x{PANEL_H}", flush=True)

    loaded = threading.Event()
    px, py = panel_origin()
    window = webview.create_window(
        APP_TITLE, str(WEB_DIR / "index.html"),
        js_api=Api(), width=PANEL_W, height=PANEL_H, x=px, y=py,
        frameless=True, on_top=True, hidden=True,
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
