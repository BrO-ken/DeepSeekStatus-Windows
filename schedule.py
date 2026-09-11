# -*- coding: utf-8 -*-
"""
Règle de tarification DeepSeek — source de vérité unique de l'app.

Vérifiée sur la documentation officielle (https://api-docs.deepseek.com/quick_start/pricing,
consulté le 11/09/2026) :
  « Off-peak rates are half of the peak rates. Peak hours are 01:00 - 04:00 and
    06:00 - 10:00 UTC, Monday through Friday (all other hours are off-peak). »

En heure de Pékin (Asia/Shanghai, UTC+8, pas d'heure d'été) c'est identique à :
  lundi–vendredi 09:00–12:00 et 14:00–18:00 → plein tarif ; tout le reste → hors pointe.

Bornes semi-ouvertes : à 09:00 pile on est déjà en plein ; à 12:00 et 18:00 pile,
on est déjà en heures creuses. Le résultat ne dépend jamais du fuseau local.
"""
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

BEIJING = ZoneInfo("Asia/Shanghai")
PEAK = "peak"
OFF = "offPeak"
PEAK_RANGES = ((time(9, 0), time(12, 0)), (time(14, 0), time(18, 0)))


def is_weekday_peak(d: datetime) -> bool:
    """d doit déjà être exprimé en heure de Pékin."""
    if d.weekday() >= 5:  # samedi=5, dimanche=6
        return False
    t = d.time()
    return any(s <= t < e for s, e in PEAK_RANGES)


def period_at(dt: datetime) -> str:
    """Période tarifaire d'un instant (fuseau quelconque, obligatoirement aware)."""
    if dt.tzinfo is None:
        raise ValueError("datetime naive interdit : fournir un fuseau")
    return PEAK if is_weekday_peak(dt.astimezone(BEIJING)) else OFF


def _boundaries(day_date):
    """Les 4 bornes d'une journée de Pékin : 09:00, 12:00, 14:00, 18:00."""
    for s, e in PEAK_RANGES:
        yield datetime.combine(day_date, s, tzinfo=BEIJING)
        yield datetime.combine(day_date, e, tzinfo=BEIJING)


def next_transition(dt: datetime) -> datetime:
    """Prochaine BASCULE (changement de période) strictement après dt.

    Pas simplement la prochaine borne : samedi 09:00 est une borne mais pas
    une bascule (on reste en heures creuses tout le week-end).
    """
    b = dt.astimezone(BEIJING)
    for i in range(9):
        day = (b + timedelta(days=i)).date()
        for bt in sorted(_boundaries(day)):
            if bt > b and is_weekday_peak(bt - timedelta(seconds=1)) != is_weekday_peak(bt):
                return bt.astimezone(dt.tzinfo)
    raise RuntimeError("aucune transition trouvée en 9 jours")


def previous_boundary(dt: datetime) -> datetime:
    """Dernière borne passée (début du bloc en cours)."""
    b = dt.astimezone(BEIJING)
    cands = []
    for i in range(0, 9):
        cands += list(_boundaries((b - timedelta(days=i)).date()))
    cands = [c for c in cands if c <= b]
    return max(cands).astimezone(dt.tzinfo)


def progress(dt: datetime) -> float:
    """Avancement 0..1 dans le bloc tarifaire en cours."""
    prev = previous_boundary(dt)
    nxt = next_transition(dt)
    return max(0.0, min(1.0, (dt - prev) / (nxt - prev)))


def week_matrix() -> list[list[int]]:
    """Semaine type [lundi..dimanche][0..23] → 1 si plein tarif."""
    monday = datetime(2026, 9, 14, 0, 0, tzinfo=BEIJING)  # un lundi quelconque
    out = []
    for wd in range(7):
        row = []
        base = monday + timedelta(days=wd)
        for h in range(24):
            row.append(1 if is_weekday_peak(base.replace(hour=h)) else 0)
        out.append(row)
    return out
