"""VIZ-104: Blitzfrequenz eines Shutter-/Strobe-Kanals — EINE Quelle fuer die
2D-Live-Ansicht und den 3D-Visualizer.

Bis VIZ-104 stand die Formel in ``ui/views/live_view.py`` (FM-48), und nur die
2D-Ansicht blinkte. Die 3D-Szene bekam vom Strobe nichts mit: dort hiess
„Shutter im Strobe-Bereich" schlicht „hell" (``color_utils.visual_intensity``).

Woher die Frequenz kommt, in dieser Reihenfolge:

1. **Bereichsdaten des Profils.** Nur ein Bereich der Art ``strobe`` blitzt
   (``app_state.shutter_bereich_art``); „offen"/„zu" und alles andere nicht.
   Nennt der Bereichsname eine Frequenz („Strobe 1-25 Hz", „Strobe 10 Hz"),
   gilt diese Spanne. Sonst steigt die Frequenz innerhalb des Bereichs linear
   von :data:`HZ_MIN` auf :data:`HZ_MAX`. Heisst der Bereich erkennbar
   „schnell -> langsam", laeuft die Spanne rueckwaerts.
2. **Ohne Bereichsdaten** die Naeherung der 2D-Ansicht seit FM-48:
   Werte ueber 10 = Strobe, linear :data:`HZ_MIN` .. :data:`HZ_MAX`.

Warum Bereichsdaten Vorrang haben (FM-48): bis 2026-09-28 galt pauschal
„> 10 = Strobe" — damit blinkten Geraete mit OFFENEM Shutter (Spider 14ch
„Offen" 8-15, Hero Spot 90 „Open" 251-255, ZQ02001 „Strobe aus (offen)"
250-255). Die pauschale Regel gilt deshalb nur noch, wo das Profil gar keine
Bereiche nennt.

Das Ergebnis ist eine Naeherung fuer die ANZEIGE. An der DMX-Ausgabe aendert
sich nichts, und Farbe/Dimmer bleiben davon unberuehrt.
"""
from __future__ import annotations

import re

#: Naeherung ohne Frequenzangabe im Profil (Hz am unteren/oberen Bereichsende).
HZ_MIN = 0.5
HZ_MAX = 20.0
#: Ohne Bereichsdaten: Werte bis einschliesslich dieser Schwelle = kein Strobe.
OHNE_BEREICHE_SCHWELLE = 10
#: Obergrenze fuer Frequenzen aus Bereichsnamen (Tippfehler im Profil).
HZ_NAME_MAX = 60.0

_SHUTTER_ATTRS = ("shutter", "strobe")

_ZAHL = r"(\d+(?:[.,]\d+)?)"
_HZ_SPANNE = re.compile(_ZAHL + r"\s*(?:hz)?\s*(?:-|–|—|\.\.+|bis|to)\s*" + _ZAHL + r"\s*hz",
                        re.IGNORECASE)
_HZ_EINZEL = re.compile(_ZAHL + r"\s*hz", re.IGNORECASE)
_RUECKWAERTS = re.compile(
    r"(fast|schnell)\s*(?:-+>?|–|—|→|to|bis|nach|\.\.+)\s*(slow|langsam)", re.IGNORECASE)


def _zahl(text: str) -> float:
    return float(text.replace(",", "."))


def hz_spanne_aus_name(name) -> tuple[float, float] | None:
    """Frequenzspanne ``(von, bis)`` aus einem Bereichsnamen, sonst ``None``.

    „Strobe 1-25 Hz" -> (1.0, 25.0); „Strobe 10 Hz" -> (10.0, 10.0);
    „Strobe fast to slow" -> (HZ_MAX, HZ_MIN). Die Reihenfolge im Namen ist die
    Reihenfolge im Wertebereich (erste Zahl = unteres Bereichsende)."""
    text = str(name or "")
    m = _HZ_SPANNE.search(text)
    if m:
        a, b = _zahl(m.group(1)), _zahl(m.group(2))
    else:
        m = _HZ_EINZEL.search(text)
        if m:
            a = b = _zahl(m.group(1))
        elif _RUECKWAERTS.search(text):
            return (HZ_MAX, HZ_MIN)
        else:
            return None
    if not (0.0 < a <= HZ_NAME_MAX and 0.0 < b <= HZ_NAME_MAX):
        return None
    return (a, b)


def strobe_hz(ch, val) -> float:
    """Blitzfrequenz in Hz fuer den Wert ``val`` des Kanals ``ch``; ``0.0`` =
    kein Strobe (Shutter offen, zu, oder ein Bereich anderer Art)."""
    from src.core.app_state import shutter_bereich_art
    try:
        val = int(val)
    except (TypeError, ValueError):
        return 0.0
    ranges = list(getattr(ch, "ranges", None) or ())
    if ranges:
        for r in ranges:
            try:
                lo, hi = int(r.range_from), int(r.range_to)
            except (TypeError, ValueError):
                continue
            if lo <= val <= hi:
                if shutter_bereich_art(r) != "strobe":
                    return 0.0
                spanne = hz_spanne_aus_name(getattr(r, "name", ""))
                von, bis = spanne if spanne else (HZ_MIN, HZ_MAX)
                return von + (val - lo) / max(1, hi - lo) * (bis - von)
        return 0.0
    if val <= OHNE_BEREICHE_SCHWELLE:
        return 0.0
    return HZ_MIN + (val - (OHNE_BEREICHE_SCHWELLE + 1)) / 244.0 * (HZ_MAX - HZ_MIN)


def _kanaele_nach_schluessel(channels) -> dict:
    """``attr`` / ``attr#N`` -> Kanal, dieselbe Vergabe wie im Visualizer-
    Service (Kopf 0 = ``attr``, das N-te weitere Vorkommen = ``attr#N``)."""
    out: dict = {}
    seen: dict[str, int] = {}
    for ch in channels or ():
        a = getattr(ch, "attribute", None)
        if a not in _SHUTTER_ATTRS:
            continue
        h = seen.get(a, 0)
        seen[a] = h + 1
        out[a if h == 0 else f"{a}#{h}"] = ch
    return out


def strobe_hz_aus_attrs(attrs, channels, sfx: str | None = None) -> float:
    """Blitzfrequenz eines Geraets aus seinen Attribut-Werten (``attrs`` wie im
    Visualizer-Service: ``shutter``, ``strobe``, ``shutter#1`` ...).

    ``sfx=None``: das ganze Geraet — die hoechste Frequenz ALLER Shutter-/
    Strobe-Kanaele (so rechnet auch die 2D-Ansicht). ``sfx=""`` / ``"#1"`` ...:
    nur die Kanaele dieses Kopfes. Geraet ohne Shutter-Kanal -> ``0.0``."""
    if not attrs or not channels:
        return 0.0
    hz = 0.0
    for key, ch in _kanaele_nach_schluessel(channels).items():
        if key not in attrs:
            continue
        if sfx is not None and key.partition("#")[1] + key.partition("#")[2] != sfx:
            continue
        hz = max(hz, strobe_hz(ch, attrs[key]))
    return hz


def hat_kopf_shutter(channels) -> bool:
    """Hat das Geraet mehr als einen Shutter-/Strobe-Kanal derselben Art —
    also einen je Kopf?"""
    return any("#" in k for k in _kanaele_nach_schluessel(channels))
