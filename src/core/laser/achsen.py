"""LAS-30: Laser-Achsen je gepatchtem Geraet umkehren/tauschen.

Gegenstueck zu ``invert_pan``/``invert_tilt``/``swap_pan_tilt`` (Moving Heads,
``app_state.apply_pan_tilt_orientation``) fuer die Laser-Positionsachsen
``laser_x``/``laser_y``. Ein Laser haengt mal kopfueber unter der Traverse, mal
steht er auf dem Boden — dieselbe Programmierung soll in beiden Faellen in
dieselbe Richtung fahren. Die Flags am Geraet heissen ``invert_laser_x``,
``invert_laser_y`` und ``swap_laser_xy``.

Wirkt in DERSELBEN Ausgabestufe wie die Pan/Tilt-Flags: ``apply_pan_tilt_
orientation`` ruft :func:`apply_laser_orientation` mit auf (Programmer-Flush,
Render-Pfad, EFX, Layer-Effekte), ``unapply_pan_tilt_orientation`` nimmt sie
fuer den 3D-Payload wieder zurueck.

Achsen-Konvention — Umkehren ist NICHT immer ``255 - v``
--------------------------------------------------------
Was „umkehren" heisst, haengt daran, wie das Profil die Achse beschreibt
(``ChannelRange``-Bereiche des Kanals):

``linear``
    Keine Bereiche oder EIN Bereich ueber die ganze Achse (FB4:
    „-100 bis +100 % (128 = Mitte)"). Umkehr = ``255 - v`` (bzw. ``lo+hi-v``).
    Ein Profil ohne jede Beschreibung faellt hierher — der Patch-Dialog sagt das.

``zwei_richtungen``
    Ein „Mitte"-Bereich am ANFANG und genau zwei Richtungsbereiche danach
    (Laserworld EL-400RGB MK2: 0-10 Mitte, 11-127 eine Richtung, 128-255 die
    andere; am Geraet gemessen X 80 = rechts, X 200 = links). Umkehr = die
    Auslenkung bleibt, die Richtung wechselt: ein Wert im ersten Richtungs-
    bereich wird anteilig in den zweiten abgebildet und umgekehrt
    (``80`` -> ``~199``). Der Mitte-Bereich bleibt unveraendert. ``255 - v``
    waere hier falsch: aus „Mitte" (5) wuerde 250 = fast ganz links.

``zwei_richtungen`` mit Mitte IN der Mitte
    (links … Mitte … rechts): die Seiten werden gegenlaeufig getauscht (aussen
    bleibt aussen), der Mitte-Bereich in sich gespiegelt.

``statisch``
    Erster Bereich = feste Position, alles darueber = Eigenbewegung des
    Geraets (EHAHO L2600: 0-127 „Position statisch", 128-255 Wellen/Laeufe —
    dieselbe Regel wie ``visualizer_service._laser_statisch``). Gespiegelt wird
    NUR innerhalb des statischen Bereichs (``lo+hi-v``); Eigenbewegungs-Werte
    bleiben unberuehrt, sonst wuerde aus einer Position ein Programm.

Laser-Sicherheit: hier werden ausschliesslich ``laser_x``/``laser_y`` (je Kopf)
angefasst — Shutter/Aus-Werte, NOT-AUS und Blackout sind davon nicht beruehrt.
"""
from __future__ import annotations

import re

ACHSEN = ("laser_x", "laser_y")
FLAGS = ("invert_laser_x", "invert_laser_y", "swap_laser_xy")

_MITTE = re.compile(r"mitte|center|centre|zentr", re.IGNORECASE)


def hat_flags(fx) -> bool:
    return any(bool(getattr(fx, f, False)) for f in FLAGS)


def _bereiche(channel) -> list[tuple[int, int, str]]:
    out = []
    for rg in (getattr(channel, "ranges", None) or ()) if channel is not None else ():
        try:
            lo, hi = int(rg.range_from), int(rg.range_to)
        except (TypeError, ValueError):
            continue
        if hi < lo:
            lo, hi = hi, lo
        name = getattr(rg, "name", None) or getattr(rg, "label", "") or ""
        out.append((max(0, lo), min(255, hi), str(name)))
    out.sort()
    return out


def achsen_plan(channel) -> tuple:
    """Wie die Achse dieses Kanals umgekehrt wird (siehe Modul-Doc).

    ``("linear", lo, hi)`` · ``("statisch", lo, hi)`` ·
    ``("zwei", mitte, r1, r2)`` (Mitte vorn) · ``("seiten", r1, mitte, r2)``.
    """
    rgs = _bereiche(channel)
    if not rgs:
        return ("linear", 0, 255)
    lo_all, hi_all = rgs[0][0], max(r[1] for r in rgs)
    if len(rgs) == 1:
        return ("linear", 0, 255) if (lo_all, hi_all) == (0, 255) else ("statisch", lo_all, hi_all)
    mitten = [r for r in rgs if _MITTE.search(r[2])]
    if len(mitten) == 1 and len(rgs) == 3:
        m = mitten[0]
        rest = [(r[0], r[1]) for r in rgs if r is not m]
        if rgs[0] is m:
            return ("zwei", (m[0], m[1]), rest[0], rest[1])
        if rgs[1] is m:
            return ("seiten", rest[0], (m[0], m[1]), rest[1])
    if mitten and rgs[0] is mitten[0]:
        # Mitte vorn, aber keine zwei eindeutigen Richtungen: nicht raten.
        return ("linear", 0, 255)
    return ("statisch", rgs[0][0], rgs[0][1])


def _anteilig(v: int, von: tuple[int, int], nach: tuple[int, int]) -> int:
    a1, b1 = von
    a2, b2 = nach
    if b1 <= a1:
        return a2
    return a2 + int(round((v - a1) * (b2 - a2) / (b1 - a1)))


def spiegel(v: int, plan: tuple) -> int:
    """Wert ``v`` nach ``plan`` umkehren (Involution bis auf +-1 Rundung bei
    ungleich breiten Richtungsbereichen)."""
    art = plan[0]
    if art == "linear":
        return plan[1] + plan[2] - v
    if art == "statisch":
        lo, hi = plan[1], plan[2]
        return lo + hi - v if lo <= v <= hi else v
    if art == "zwei":
        _m, r1, r2 = plan[1], plan[2], plan[3]
        if r1[0] <= v <= r1[1]:
            return _anteilig(v, r1, r2)
        if r2[0] <= v <= r2[1]:
            return _anteilig(v, r2, r1)
        return v
    if art == "seiten":
        r1, m, r2 = plan[1], plan[2], plan[3]
        if r1[0] <= v <= r1[1]:   # aussen bleibt aussen: gegenlaeufig
            return _anteilig(r1[1] - (v - r1[0]), r1, r2)
        if r2[0] <= v <= r2[1]:
            return _anteilig(r2[1] - (v - r2[0]), r2, r1)
        if m[0] <= v <= m[1]:
            return m[0] + m[1] - v
        return v
    return 255 - v


def _kanaele_je_kopf(channels) -> dict[str, object]:
    """``{"laser_x": ch, "laser_x#1": ch, …}`` in Kanal-Reihenfolge (X-6)."""
    out: dict[str, object] = {}
    seen: dict[str, int] = {}
    for ch in channels or ():
        a = getattr(ch, "attribute", None)
        if a not in ACHSEN:
            continue
        n = seen.get(a, 0)
        seen[a] = n + 1
        out[a if n == 0 else f"{a}#{n}"] = ch
    return out


def _koepfe(attrs) -> list[str]:
    suffixe = set()
    for k in attrs:
        for basis in ACHSEN:
            if k == basis:
                suffixe.add("")
            elif k.startswith(basis + "#"):
                suffixe.add(k[len(basis):])
    return sorted(suffixe, key=lambda s: (s != "", s))


def _kanaele(fx, channels):
    if channels is not None:
        return channels
    try:
        from src.core.app_state import get_channels_for_patched
        return get_channels_for_patched(fx)
    except Exception:
        return ()


def _invertiere(out: dict, key: str, kanaele: dict) -> None:
    if key not in out:
        return
    try:
        v = max(0, min(255, int(out[key])))
    except (TypeError, ValueError):
        out.pop(key, None)   # kaputter Wert darf den Render-Takt nicht stoppen
        return
    out[key] = max(0, min(255, spiegel(v, achsen_plan(kanaele.get(key)))))


def _tausche(out: dict, k: str) -> None:
    a, b = f"laser_x{k}", f"laser_y{k}"
    va, vb = out.get(a), out.get(b)
    if va is None and vb is None:
        return
    if vb is not None:
        out[a] = vb
    else:
        out.pop(a, None)
    if va is not None:
        out[b] = va
    else:
        out.pop(b, None)


def apply_laser_orientation(fx, attrs: dict, channels=None) -> dict:
    """MODELL-Wert -> DRAHT-Wert: erst Tausch, dann Umkehr je Achse.

    Ohne gesetzte Flag oder ohne ``laser_x``/``laser_y`` in der Schicht kommt
    das Original zurueck (kein Overhead im Render-Takt), sonst ein NEUES dict.
    ``channels`` = Kanal-Objekte des Geraets (Bereiche fuer die Achsen-
    Konvention); ``None`` laedt sie gecacht ueber ``get_channels_for_patched``.
    """
    if not hat_flags(fx):
        return attrs
    koepfe = _koepfe(attrs)
    if not koepfe:
        return attrs
    inv_x = bool(getattr(fx, "invert_laser_x", False))
    inv_y = bool(getattr(fx, "invert_laser_y", False))
    swap = bool(getattr(fx, "swap_laser_xy", False))
    kanaele = _kanaele_je_kopf(_kanaele(fx, channels)) if (inv_x or inv_y) else {}
    out = dict(attrs)
    for k in koepfe:
        if swap:
            _tausche(out, k)
        if inv_x:
            _invertiere(out, f"laser_x{k}", kanaele)
        if inv_y:
            _invertiere(out, f"laser_y{k}", kanaele)
    return out


def unapply_laser_orientation(fx, attrs: dict, channels=None) -> dict:
    """DRAHT-Wert -> MODELL-Wert (fuer den 3D-Payload): exakte Umkehr-
    Reihenfolge — erst Umkehr, dann Tausch."""
    if not hat_flags(fx):
        return attrs
    koepfe = _koepfe(attrs)
    if not koepfe:
        return attrs
    inv_x = bool(getattr(fx, "invert_laser_x", False))
    inv_y = bool(getattr(fx, "invert_laser_y", False))
    swap = bool(getattr(fx, "swap_laser_xy", False))
    kanaele = _kanaele_je_kopf(_kanaele(fx, channels)) if (inv_x or inv_y) else {}
    out = dict(attrs)
    for k in koepfe:
        if inv_x:
            _invertiere(out, f"laser_x{k}", kanaele)
        if inv_y:
            _invertiere(out, f"laser_y{k}", kanaele)
        if swap:
            _tausche(out, k)
    return out


def profil_beschreibung(channels) -> str:
    """Kurztext fuer den Patch-Dialog: wie dieses Profil umgekehrt wird."""
    k = _kanaele_je_kopf(channels)
    if not k:
        return "Profil ohne laser_x/laser_y — die Optionen wirken hier nicht."
    arten = {achsen_plan(ch)[0] for ch in k.values()}
    if arten == {"linear"} and not any(_bereiche(ch) for ch in k.values()):
        return ("Profil beschreibt die Achsen nicht (keine Bereiche): Umkehr "
                "linear (255 − Wert). Bitte am Gerät prüfen.")
    namen = {"linear": "linear (255 − Wert)",
             "statisch": "nur im Positionsbereich gespiegelt",
             "zwei": "Mitte bleibt, Richtungsbereiche getauscht",
             "seiten": "Seiten um die Mitte getauscht"}
    return "Umkehr: " + ", ".join(namen.get(a, a) for a in sorted(arten)) + "."
