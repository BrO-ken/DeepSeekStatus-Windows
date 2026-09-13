# -*- coding: utf-8 -*-
"""Balance store tests — offline: the fetcher is mocked, the real API is
never called, and the dummy key lives only in the Windows Credential
Manager for the seconds of the test (removed at the end)."""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import balance
from balance import BalanceStore, BalanceError

_ok = 0


def check(name, cond):
    global _ok
    print(("✅" if cond else "❌") + " " + name)
    assert cond, name
    _ok += 1


class FakeClock:
    def __init__(self): self.t = 1000.0
    def __call__(self): return self.t


def make_store(fetch):
    clock = FakeClock()
    return BalanceStore(fetch=fetch, clock=clock), clock


# ---- parse logic on a sample response shape -----------------------------
def fake_ok(key):
    """Mimics fetch_balance's PARSED return contract."""
    return {"isAvailable": True, "infos": [
        {"currency": "USD", "symbol": "$", "total": "12.34",
         "granted": "1.00", "toppedUp": "11.34"}]}


def wait(store, pred, dur=2.0):
    end = time.time() + dur
    while time.time() < end:
        if pred(store.snapshot()):
            return True
        time.sleep(0.02)
    return False


_orig_save = balance.save_api_key
balance.save_api_key = lambda k: True          # avoid touching the vault here
s, clk = make_store(fake_ok)
snap = s.snapshot()
check("départ sans clé: state=noKey, hasKey=False",
      snap["state"] == "noKey" and snap["hasKey"] is False)
check("pas de données sans clé", snap["infos"] == [] and snap["lastOk"] is None)

# fetch_balance parsing itself: monkey-patch urlopen
class Resp:
    def __init__(self, data): self._d = data
    def read(self): return self._d
    def __enter__(self): return self
    def __exit__(self, *a): return False

import io, json as _json
class FakeUrllib:
    def __init__(self, payload=None, err=None): self.payload, self.err = payload, err
    def __call__(self, req, timeout=None):
        if self.err: raise self.err
        return Resp(_json.dumps(self.payload).encode())

urllib_request = __import__("urllib.request", fromlist=["urlopen"])
RAW_OK = {"is_available": True, "balance_infos": [
    {"currency": "USD", "total_balance": "12.34",
     "granted_balance": "1.00", "topped_up_balance": "11.34"}]}
orig = urllib_request.urlopen
urllib_request.urlopen = FakeUrllib(RAW_OK)
data = balance.fetch_balance("sk-fake")
check("parsing USD -> $ + totaux", data["isAvailable"] is True
      and data["infos"][0]["symbol"] == "$" and data["infos"][0]["total"] == "12.34")
urllib_request.urlopen = FakeUrllib({"is_available": True, "balance_infos": [
    {"currency": "CNY", "total_balance": "110.00",
     "granted_balance": "10.00", "topped_up_balance": "100.00"}]})
data = balance.fetch_balance("sk-fake")
check("parsing CNY -> ¥ + granted/topped-up", data["infos"][0]["symbol"] == "¥"
      and data["infos"][0]["granted"] == "10.00")
urllib_request.urlopen = orig

# 401 -> unauthorized
def boom401(req, timeout=None):
    raise __import__("urllib.error", fromlist=["HTTPError"]).HTTPError(
        "u", 401, "nope", None, io.BytesIO(b""))
urllib_request.urlopen = boom401
try:
    balance.fetch_balance("sk-fake"); check("401 -> unauthorized", False)
except BalanceError as e:
    check("401 -> unauthorized + suggere remplacement",
          e.code == "unauthorized" and e.suggests_replacing_key)
urllib_request.urlopen = orig

# ---- store flow ----------------------------------------------------------
s, clk = make_store(fake_ok)
s._key = "sk-test"
with s._lock: s._state = "loading"
s.refresh()
check("refresh -> ok + lastOk rempli", wait(s, lambda d: d["state"] == "ok")
      and s.snapshot()["lastOk"] is not None)

def boom(key):
    raise BalanceError("network")
s2, _ = make_store(boom)
s2._key = "sk-x"
with s2._lock: s2._state = "loading"
s2.refresh()
check("refresh -> erreur reseau", wait(s2, lambda d: d["state"] == "error")
      and "reach" in s2.snapshot()["error"])

# race token: an old in-flight result must not overwrite a newer key
gate = {"release": False}
def slow_ok(key):
    while not gate["release"]:
        time.sleep(0.02)
    return fake_ok(key)
s3, _ = make_store(slow_ok)
s3._key = "old"
with s3._lock: s3._state = "loading"
s3.refresh()                     # seq N with "old"
time.sleep(0.1)
s3._key = "new"
with s3._lock:
    s3._seq += 1                 # simulate set_key invalidating the flight
    s3._state = "loading"
gate["release"] = True
time.sleep(0.3)                  # old fetch finishes late
snap = s3.snapshot()
check("reponse pelee apres changement de cle -> ignoree",
      snap["state"] == "loading")   # not "ok": stale result was dropped

# refresh_if_stale only fires when stale
hits = []
def counting(key):
    hits.append(1)
    return fake_ok(key)
s4, clk4 = make_store(counting)
s4._key = "sk"
s4.refresh_if_stale()
check("refresh_if_stale declenche quand jamais rafraichi", len(hits) == 1)
deadline = time.time() + 2
while time.time() < deadline and s4.snapshot()["state"] != "ok":
    time.sleep(0.05)
with s4._lock:
    clk4.t = s4._last_ok + 10    # fake clock 10 s after success: fresh
s4.refresh_if_stale()
check("refresh_if_stale muet si recemment rafraichi", len(hits) == 1)
with s4._lock:
    clk4.t = s4._last_ok + 301   # simulate 5 min passing
s4.refresh_if_stale()
check("refresh_if_stale rejoue apres 5 min", len(hits) == 2)

# real credential vault round-trip (dummy, deleted at the end)
balance.save_api_key = _orig_save
check("Credential Manager: round-trip save/load/delete",
      balance.save_api_key("sk-dummy-123")
      and balance.load_api_key() == "sk-dummy-123"
      and balance.delete_api_key()
      and balance.load_api_key() is None)

print(f"\n{_ok} verifications solde, toutes reussies")
