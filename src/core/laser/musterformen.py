"""LAS-33: Schemazeichnung eines Laser-Musters — Form -> Polylinien, ohne Qt.

:func:`form_polylinien` macht aus einem Muster-Eintrag des Geraeteprofils
(``form``, ``anzahl``, ``stil``, bei eigenen Formen ``linien`` — siehe
:mod:`src.core.laser.profilangaben`) eine Liste von :class:`Linie`. Die
Koordinaten sind normiert: x von -1 (links) bis 1 (rechts), y von -1 (unten)
bis 1 (oben). Wer zeichnet (``src/ui/widgets/laser_musterbild.py``), spiegelt
y selbst.

Es ist ein SCHEMA: die Zeichnung zeigt, welches Muster gemeint ist, nicht wie
es am Geraet genau aussieht.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from .profilangaben import ANZAHL_BEDEUTUNG, ANZAHL_MAX, EIGENE_FORM, FORMEN

R = 0.82            # Aussenradius der Grundformen
_KREIS_PUNKTE = 48


@dataclass(frozen=True)
class Linie:
    """Ein Linienzug. ``art``: ``linie`` (Strich), ``punkte`` (jeder Punkt ein
    einzelner Laserpunkt) oder ``flaeche`` (geschlossen und gefuellt)."""
    punkte: tuple[tuple[float, float], ...]
    geschlossen: bool = False
    art: str = "linie"


def _kreis(cx: float, cy: float, r: float, n: int = _KREIS_PUNKTE):
    return tuple((cx + r * math.cos(2 * math.pi * i / n),
                  cy + r * math.sin(2 * math.pi * i / n)) for i in range(n))


def _vieleck(n: int, r: float = R, start_grad: float = 90.0):
    return tuple((r * math.cos(math.radians(start_grad) + 2 * math.pi * i / n),
                  r * math.sin(math.radians(start_grad) + 2 * math.pi * i / n))
                 for i in range(n))


def _parallele(n: int, waagerecht: bool) -> list[Linie]:
    out = []
    for i in range(n):
        v = 0.0 if n == 1 else -0.6 + 1.2 * i / (n - 1)
        a, b = ((-R, v), (R, v)) if waagerecht else ((v, -R), (v, R))
        out.append(Linie((a, b)))
    return out


def _stern(zacken: int):
    zacken = max(3, zacken)
    innen = R * (0.42 if zacken >= 5 else 0.3)
    return tuple(
        ((R if i % 2 == 0 else innen)
         * math.cos(math.pi / 2 + math.pi * i / zacken),
         (R if i % 2 == 0 else innen)
         * math.sin(math.pi / 2 + math.pi * i / zacken))
        for i in range(2 * zacken))


def _mehrere_kreise(n: int) -> list[Linie]:
    if n == 1:
        return [Linie(_kreis(0, 0, R * 0.6), True)]
    # Auf einem Ring; der Radius der kleinen Kreise so, dass sich Nachbarn
    # nicht beruehren. Vier Kreise stehen damit als 2 x 2.
    ring = 0.5 if n > 2 else 0.45
    r = min(0.34, 0.8 * ring * math.sin(math.pi / n))
    dreh = math.pi / n if n % 2 == 0 and n > 2 else (0.0 if n == 2 else math.pi / 2)
    return [Linie(_kreis(ring * math.cos(dreh + 2 * math.pi * i / n),
                         ring * math.sin(dreh + 2 * math.pi * i / n), r, 32), True)
            for i in range(n)]


def _laenge(punkte, geschlossen: bool) -> float:
    paare = list(zip(punkte, punkte[1:]))
    if geschlossen and len(punkte) > 1:
        paare.append((punkte[-1], punkte[0]))
    return sum(math.dist(a, b) for a, b in paare)


def punkte_entlang(linie: Linie, anzahl: int | None = None) -> Linie:
    """Eine Linie als gleichmaessig verteilte Einzelpunkte (``art="punkte"``).
    Ohne ``anzahl`` ein Punkt je ~0,3 Einheiten Weg, mindestens drei."""
    p = list(linie.punkte)
    if len(p) < 2:
        return Linie(tuple(p), False, "punkte")
    strecke = p + [p[0]] if linie.geschlossen else p
    gesamt = _laenge(p, linie.geschlossen)
    if gesamt <= 0:
        return Linie((p[0],), False, "punkte")
    n = anzahl or max(3, int(round(gesamt / 0.3)))
    schritte = n if linie.geschlossen else max(1, n - 1)
    out = []
    for i in range(n):
        ziel = gesamt * i / schritte
        weg = 0.0
        for a, b in zip(strecke, strecke[1:]):
            d = math.dist(a, b)
            if weg + d >= ziel - 1e-9 and d > 0:
                t = (ziel - weg) / d
                out.append((a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1])))
                break
            weg += d
        else:
            out.append(strecke[-1])
    return Linie(tuple(out), False, "punkte")


def _feld(muster, name, vorgabe=None):
    if isinstance(muster, dict):
        return muster.get(name, vorgabe)
    return getattr(muster, name, vorgabe)


def anzahl_fuer(form: str, anzahl=None) -> int | None:
    """Die wirksame ``anzahl`` einer Form: die Angabe, sonst der Standard der
    Form; ``None``, wenn die Form keine Zahl kennt."""
    if form not in ANZAHL_BEDEUTUNG:
        return None
    try:
        n = int(anzahl)
    except (TypeError, ValueError):
        n = ANZAHL_BEDEUTUNG[form][1]
    return max(1, min(ANZAHL_MAX, n))


def _grundform(form: str, n: int | None, linien) -> list[Linie]:
    if form == "kreis":
        return [Linie(_kreis(0, 0, R), True)]
    if form == "linie_waagerecht":
        return _parallele(n, True)
    if form == "linie_senkrecht":
        return _parallele(n, False)
    if form == "dreieck":
        return [Linie(_vieleck(3), True)]
    if form == "quadrat":
        return [Linie(_vieleck(4, R, 45.0), True)]
    if form == "stern":
        return [Linie(_stern(n), True)]
    if form == "punkte_kreis":
        return [Linie(_kreis(0, 0, R, n) if n > 1 else ((0.0, 0.0),), False,
                      "punkte")]
    if form == "punkte_linie":
        return [Linie(tuple(((0.0 if n == 1 else -R + 2 * R * i / (n - 1)), 0.0)
                            for i in range(n)), False, "punkte")]
    if form == "welle":
        schritte = 24 * n
        return [Linie(tuple((-R + 2 * R * i / schritte,
                             0.5 * math.sin(2 * math.pi * n * i / schritte))
                            for i in range(schritte + 1)))]
    if form == "kreuz":
        return [Linie(((-R, 0.0), (R, 0.0))), Linie(((0.0, -R), (0.0, R)))]
    if form == "spirale":
        schritte = 32 * n
        return [Linie(tuple(
            (R * (i / schritte) * math.cos(2 * math.pi * n * i / schritte),
             R * (i / schritte) * math.sin(2 * math.pi * n * i / schritte))
            for i in range(schritte + 1)))]
    if form == "mehrere_kreise":
        return _mehrere_kreise(n)
    if form == EIGENE_FORM:
        out = []
        for l in linien or ():
            try:
                punkte = tuple((max(-1.0, min(1.0, float(p[0]))),
                                max(-1.0, min(1.0, float(p[1]))))
                               for p in l.get("punkte", ()))
            except (AttributeError, TypeError, ValueError, IndexError):
                continue
            if not punkte:
                continue
            einzeln = len(punkte) == 1
            out.append(Linie(punkte, bool(l.get("geschlossen")) and len(punkte) > 2,
                             "punkte" if einzeln else "linie"))
        return out
    return []


def form_polylinien(muster) -> list[Linie]:
    """Die Schemazeichnung eines Musters als Linienzuege.

    ``muster`` ist ein Eintrag der Musterliste — als ``dict`` oder als
    :class:`~src.core.laser.profilangaben.Muster`. Eine unbekannte Form oder
    eine eigene Form ohne Punkte ergibt eine leere Liste (nichts zu zeichnen),
    nie einen Fehler."""
    form = _feld(muster, "form", "")
    if form not in FORMEN:
        return []
    linien = _grundform(form, anzahl_fuer(form, _feld(muster, "anzahl")),
                        _feld(muster, "linien", ()))
    stil = _feld(muster, "stil", "linie") or "linie"
    if stil == "gepunktet":
        return [l if l.art == "punkte" else punkte_entlang(l) for l in linien]
    if stil == "gefuellt":
        return [Linie(l.punkte, True, "flaeche")
                if l.geschlossen and l.art == "linie" else l for l in linien]
    return linien
