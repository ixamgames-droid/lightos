"""FM-64: Abstrahlwinkel eines Fixture-Profils (voller Winkel in Grad).

Ein Profil kann seinen Abstrahlwinkel laut Datenblatt tragen — fest (ein
Wert) oder, bei Geraeten mit Zoom, als Spanne ``min`` .. ``max``. Gespeichert
wird er als zwei Zahlen (``FixtureProfile.beam_angle_min``/``_max``), in der
Bibliotheksdatei als Feld ``abstrahlwinkel`` (Zahl oder ``[min, max]``).

``(0, 0)`` heisst **keine Angabe** — dann leitet der 3D-Visualizer den Kegel
wie bisher aus Geraetetyp und Zoom ab. Diese Regel steht nur hier, damit
Editor, Generator, Datenbank, Bibliotheksformat und Visualizer dieselbe Zahl
meinen.

Reine Funktionen ohne Qt/DB — Kern der Tests.
"""
from __future__ import annotations

#: kleinster/groesster erlaubter voller Winkel in Grad. 170 wie beim
#: Laserwinkel (LAS-32): darueber ist ein Kegel kein Kegel mehr.
WINKEL_MIN = 1.0
WINKEL_MAX = 170.0

#: Name des Felds in der Bibliotheksdatei.
FELD = "abstrahlwinkel"


def _zahl(v) -> float:
    if isinstance(v, bool):
        return 0.0
    try:
        f = float(v)
    except (TypeError, ValueError):
        return 0.0
    if f != f or f in (float("inf"), float("-inf")):
        return 0.0
    return f


def normalisiere(wmin, wmax=None) -> tuple[float, float]:
    """``(min, max)`` in Grad, bereinigt; ``(0.0, 0.0)`` = keine Angabe.

    * Fehlt ``max`` (oder ist <= 0), ist der Winkel fest: ``max = min``.
    * Fehlt nur ``min``, gilt dasselbe andersherum.
    * Vertauschte Werte werden getauscht, alles auf ``WINKEL_MIN`` ..
      ``WINKEL_MAX`` geklemmt und auf eine Nachkommastelle gerundet.
    """
    a, b = _zahl(wmin), _zahl(wmax)
    if a <= 0 and b <= 0:
        return (0.0, 0.0)
    if a <= 0:
        a = b
    if b <= 0:
        b = a
    if a > b:
        a, b = b, a
    a = round(min(WINKEL_MAX, max(WINKEL_MIN, a)), 1)
    b = round(min(WINKEL_MAX, max(WINKEL_MIN, b)), 1)
    return (a, b)


def hat_angabe(wmin, wmax=None) -> bool:
    return normalisiere(wmin, wmax) != (0.0, 0.0)


def aus_profil(prof) -> tuple[float, float]:
    """Winkel eines ``FixtureProfile`` (fehlende Spalten = keine Angabe)."""
    return normalisiere(getattr(prof, "beam_angle_min", 0),
                        getattr(prof, "beam_angle_max", 0))


def zu_daten(wmin, wmax=None):
    """Wert fuer das Bibliotheksfeld: Zahl (fest), ``[min, max]`` (Zoom)
    oder ``None`` (keine Angabe — Feld weglassen)."""
    a, b = normalisiere(wmin, wmax)
    if (a, b) == (0.0, 0.0):
        return None

    def _k(x):
        return int(x) if float(x).is_integer() else x
    return _k(a) if a == b else [_k(a), _k(b)]


def aus_daten(wert) -> tuple[float, float]:
    """Bibliotheksfeld -> ``(min, max)``; fehlend/ungueltig = keine Angabe."""
    if wert is None:
        return (0.0, 0.0)
    if isinstance(wert, (list, tuple)):
        if len(wert) != 2:
            return (0.0, 0.0)
        return normalisiere(wert[0], wert[1])
    return normalisiere(wert)


def pruefe_wert(wert) -> bool:
    """Ist ``wert`` ein gueltiges Bibliotheksfeld? (Zahl oder ``[min, max]``,
    je ``WINKEL_MIN`` .. ``WINKEL_MAX``, min <= max)."""
    def _ok(v):
        return (isinstance(v, (int, float)) and not isinstance(v, bool)
                and WINKEL_MIN <= v <= WINKEL_MAX)
    if isinstance(wert, list):
        return len(wert) == 2 and all(_ok(v) for v in wert) and wert[0] <= wert[1]
    return _ok(wert)


def text(wmin, wmax=None) -> str:
    """Kurze Anzeige: ``"25°"``, ``"8–40° (Zoom)"`` oder ``""``."""
    a, b = normalisiere(wmin, wmax)
    if (a, b) == (0.0, 0.0):
        return ""

    def _f(x):
        return f"{x:g}"
    return f"{_f(a)}°" if a == b else f"{_f(a)}–{_f(b)}° (Zoom)"


# ── VIZ-111: Laufrichtung des Zoom-Kanals ───────────────────────────────────
#
# DMX sagt nicht, in welche Richtung ein Zoom-Kanal laeuft. Der verbreitete
# Fall (und die Annahme des 3D-Visualizers) ist „0 = eng, 255 = weit“. Ein
# Profil kann die Umkehr angeben („0 = weit, 255 = eng“); gespeichert als
# ``FixtureProfile.zoom_inverted``, in der Bibliotheksdatei als Feld
# ``zoom_umgekehrt`` (nur ``true``; fehlt = normale Laufrichtung). Die Angabe
# betrifft NUR das Bild im 3D — an der DMX-Ausgabe aendert sie nichts.

#: Name des Felds in der Bibliotheksdatei.
FELD_ZOOM_UMGEKEHRT = "zoom_umgekehrt"


def zoom_umgekehrt_aus_profil(prof) -> bool:
    """Laufrichtung eines ``FixtureProfile`` (fehlende Spalte = normal)."""
    return bool(getattr(prof, "zoom_inverted", False) or False)


def zoom_umgekehrt_aus_daten(wert) -> bool:
    """Bibliotheksfeld -> bool; nur ein echtes ``true`` zaehlt."""
    return wert is True


def pruefe_zoom_umgekehrt(wert) -> bool:
    """Ist ``wert`` ein gueltiges Feld ``zoom_umgekehrt``? (``true``/``false``)"""
    return isinstance(wert, bool)
