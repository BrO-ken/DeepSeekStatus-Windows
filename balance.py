# -*- coding: utf-8 -*-
"""DeepSeek account balance for the tray app.

Port of the balance feature from owenzhao/DeepSeekStatus (macOS):
- API key lives in the Windows Credential Manager (the system's encrypted
  vault = the macOS Keychain equivalent) — never in config.json,
- one endpoint only: GET https://api.deepseek.com/user/balance
  (Authorization: Bearer <key>). The query itself costs nothing.
- auto refresh every 5 min; stale data is refreshed when the panel opens,
- responses carry a token: a reply from an older key/refresh is discarded
  instead of overwriting the new state.
With no key saved, no request is ever made.
"""
import json
import threading
import time
import urllib.error
import urllib.request

ENDPOINT = "https://api.deepseek.com/user/balance"
REFRESH_INTERVAL = 300.0
TIMEOUT = 15


# ------------------------------------------------------- Windows credential store
# keyring's WinVault backend = Credential Manager, encrypted per Windows user.
import keyring

_SERVICE = "DeepSeekSta…_key"


def save_api_key(key: str) -> bool:
    try:
        keyring.set_password(_SERVICE, "default", key)
        return True
    except Exception:
        return False


def load_api_key():
    try:
        return keyring.get_password(_SERVICE, "default")
    except Exception:
        return None


def delete_api_key() -> bool:
    try:
        keyring.delete_password(_SERVICE, "default")
    except Exception:
        pass
    return load_api_key() is None               # absent == deleted


# -------------------------------------------------------------------- API client
class BalanceError(Exception):
    def __init__(self, code: str, status=None):
        super().__init__(code)
        self.code = code
        self.status = status

    @property
    def message(self) -> str:
        if self.code == "unauthorized":
            return "API key invalid or expired — replace it."
        if self.code == "http":
            return f"DeepSeek returned an error (HTTP {self.status})."
        if self.code == "network":
            return "Couldn't reach DeepSeek (offline?)."
        return "DeepSeek returned an unexpected response."

    @property
    def suggests_replacing_key(self) -> bool:
        return self.code == "unauthorized"


def fetch_balance(api_key: str) -> dict:
    """One GET; raises BalanceError. Costs nothing to call."""
    req = urllib.request.Request(ENDPOINT, headers={
        "Authorization": f"Bearer {api_key}",
        "Accept": "application/json",
    })
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raise BalanceError("unauthorized" if e.code in (401, 403) else "http",
                           status=e.code)
    except BalanceError:
        raise
    except Exception:
        raise BalanceError("network")
    if "balance_infos" not in data:
        raise BalanceError("decoding")
    infos = []
    for i in data.get("balance_infos", []):
        cur = str(i.get("currency", "?"))
        infos.append({
            "currency": cur,
            "symbol": "$" if cur.upper() == "USD" else "¥",
            "total": str(i.get("total_balance", "0")),
            "granted": str(i.get("granted_balance", "0")),
            "toppedUp": str(i.get("topped_up_balance", "0")),
        })
    return {"isAvailable": bool(data.get("is_available")), "infos": infos}


# --------------------------------------------------------------------- the store
class BalanceStore:
    """State + refresh policy, thread-safe, no UI knowledge."""

    def __init__(self, fetch=None, clock=time.monotonic):
        self._fetch = fetch or fetch_balance
        self._clock = clock
        self._lock = threading.Lock()
        self._key = None
        self._state = "noKey"        # noKey | loading | ok | error
        self._data = None            # fetch_balance result
        self._error = None           # BalanceError
        self._last_ok = 0.0          # monotonic of last success
        self._seq = 0                # race token
        self._refreshing = False

    def start(self) -> None:
        key = load_api_key()
        with self._lock:
            self._key = key
            if key:
                self._state = "loading"
                go = True
            else:
                go = False
        if go:
            self._spawn_refresh()

    # ---- actions -----------------------------------------------------------
    def set_key(self, key: str) -> bool:
        key = (key or "").strip()
        if not key:
            return False
        if not save_api_key(key):
            return False
        with self._lock:
            self._key = key
            self._seq += 1
            self._state = "loading"
            self._error = None
        self._spawn_refresh()
        return True

    def remove_key(self) -> None:
        delete_api_key()
        with self._lock:
            self._key = None
            self._seq += 1
            self._state = "noKey"
            self._data = None
            self._error = None
            self._last_ok = 0.0

    def refresh(self) -> None:
        with self._lock:
            if self._key and not self._refreshing:
                self._spawn_refresh_locked()

    def refresh_if_stale(self) -> None:
        with self._lock:
            if not self._key or self._refreshing:
                return
            if self._clock() - self._last_ok >= REFRESH_INTERVAL:
                self._spawn_refresh_locked()

    def tick(self) -> None:
        """Called at 1 Hz by the updater: 5-minute auto refresh."""
        self.refresh_if_stale()

    # ---- view --------------------------------------------------------------
    def snapshot(self) -> dict:
        with self._lock:
            out = {"hasKey": bool(self._key), "state": self._state,
                   "isAvailable": None, "infos": [], "lastOk": None,
                   "error": None, "suggestsRekey": False}
            if self._data:
                out["isAvailable"] = self._data["isAvailable"]
                out["infos"] = self._data["infos"]
            if self._error:
                out["error"] = self._error.message
                out["suggestsRekey"] = self._error.suggests_replacing_key
            if self._last_ok:
                wall = time.time() - (time.monotonic() - self._last_ok)
                out["lastOk"] = time.strftime("%H:%M", time.localtime(wall))
            return out

    # ---- internals ---------------------------------------------------------
    def _spawn_refresh(self) -> None:
        with self._lock:
            self._spawn_refresh_locked()

    def _spawn_refresh_locked(self) -> None:
        self._refreshing = True
        if self._state == "noKey":
            self._state = "loading"
        seq = self._seq + 1
        self._seq = seq
        key = self._key
        threading.Thread(target=self._do_fetch, args=(seq, key),
                         daemon=True).start()

    def _do_fetch(self, seq: int, key) -> None:
        try:
            if not key:
                raise BalanceError("decoding")
            data = self._fetch(key)
            with self._lock:
                if seq != self._seq or key != self._key:
                    return                      # superseded: drop it
                self._data = data
                self._state = "ok"
                self._error = None
                self._last_ok = self._clock()
        except BalanceError as e:
            with self._lock:
                if seq != self._seq or key != self._key:
                    return
                self._state = "error"
                self._error = e
        except Exception:
            with self._lock:
                if seq != self._seq or key != self._key:
                    return
                self._state = "error"
                self._error = BalanceError("network")
        finally:
            with self._lock:
                if seq == self._seq:
                    self._refreshing = False
