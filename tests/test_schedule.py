# -*- coding: utf-8 -*-
"""Vérifications de la règle horaire — 27 cas limites, à la manière du projet macOS.

Source de la règle : https://api-docs.deepseek.com/quick_start/pricing
« Peak hours are 01:00 - 04:00 and 06:00 - 10:00 UTC, Monday through Friday ».
"""
import sys
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from schedule import (BEIJING, OFF, PEAK, next_transition, period_at,
                      progress, week_matrix)

UTC = timezone.utc
_ok = 0


def check(name, cond):
    global _ok
    print(("✅" if cond else "❌") + " " + name)
    assert cond, name
    _ok += 1


def bj(day, h, m=0):
    return datetime(2026, 9, day, h, m, tzinfo=BEIJING)


# --- bornes semi-ouvertes, lundi 14/09/2026
check("lun 08:59 → creux", period_at(bj(14, 8, 59)) == OFF)
check("lun 09:00 pile → plein", period_at(bj(14, 9, 0)) == PEAK)
check("lun 11:59 → plein", period_at(bj(14, 11, 59)) == PEAK)
check("lun 12:00 pile → creux", period_at(bj(14, 12)) == OFF)
check("lun 13:59 → creux", period_at(bj(14, 13, 59)) == OFF)
check("lun 14:00 pile → plein", period_at(bj(14, 14)) == PEAK)
check("lun 17:59 → plein", period_at(bj(14, 17, 59)) == PEAK)
check("lun 18:00 pile → creux", period_at(bj(14, 18)) == OFF)

# --- week-end
check("sam 12/09 12:00 → creux", period_at(bj(12, 12)) == OFF)
check("dim 13/09 23:00 → creux", period_at(bj(13, 23)) == OFF)

# --- transitions
check("ven 11/09 18:00 → prochaine bascule = lun 14/09 09:00",
      next_transition(bj(11, 18, 0)) == bj(14, 9, 0))
check("lun 09:00 pile → prochaine bascule = 12:00 (bornes semi-ouvertes)",
      next_transition(bj(14, 9, 0)) == bj(14, 12))

# --- décompte
now = datetime(2026, 9, 14, 11, 59, 30, tzinfo=BEIJING)
check("11:59:30 → 30 s restantes",
      int((next_transition(now) - now).total_seconds()) == 30)

# --- indépendance du fuseau local : même instant vu de UTC / New York / Tokyo
inst = datetime(2026, 9, 14, 1, 30, tzinfo=UTC)  # = lundi 09:30 à Pékin
check("indépendance fuseaux (UTC / New York / Tokyo) → plein",
      period_at(inst)
      == period_at(inst.astimezone(ZoneInfo("America/New_York")))
      == period_at(inst.astimezone(ZoneInfo("Asia/Tokyo")))
      == PEAK)

# --- règle officielle en UTC, lundi entier : plein = 01–04 h et 06–10 h
for h in range(24):
    t = datetime(2026, 9, 14, h, 30, tzinfo=UTC)
    official = (1 <= h < 4) or (6 <= h < 10)
    check(f"UTC lundi {h:02d}:30 → {'plein' if official else 'creux'} (règle officielle)",
          (period_at(t) == PEAK) == official)

# --- semaine type
wm = week_matrix()
check("semaine type : lundi 9-11 h plein", all(wm[0][h] == 1 for h in (9, 10, 11)))
check("semaine type : lundi 12 h creux", wm[0][12] == 0)
check("semaine type : samedi/dimanche tout creux", not any(any(r) for r in wm[5:7]))

# --- progression dans le bloc
p = progress(datetime(2026, 9, 14, 10, 30, tzinfo=BEIJING))  # bloc 9→12 h
check("lun 10:30 → 50 % du bloc écoulé", abs(p - 0.5) < 1e-9)

print(f"\n{_ok} vérifications, toutes réussies ✅")
