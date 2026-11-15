"""UI-127: Rechenteil des VC-Raum-Pads — den Raum antippen statt Pan/Tilt.

Ohne Qt, damit die Regeln einzeln pruefbar sind. Das Widget
(``src/ui/virtualconsole/vc_raumpad.py``) fragt hier:

* :func:`raum_masse` — wie gross ist der Raum in der Draufsicht? Dieselbe Regel
  wie die Raum-Huelle des 3D-Visualizers (``scene_src/scene/room_shell.js``,
  VIZ-14): Ausdehnung der platzierten Geraete plus 4 m Rand, mindestens 12 m,
  hoechstens 80 m; Hoehe = hoechster Standort plus 4 m, 5..20 m. Eine feste
  Groesse wuerde bei grossen Rigs mitten durch das Rig schneiden.
* :func:`bewegung` — ist das Geraet ein Moving Head (bzw. eine Mover-Bar mit
  N Koepfen)? Dieselbe Unterscheidung wie das Zielen-Werkzeug im Visualizer
  (``VisualizerBridge._mover_bar_heads`` / ``_is_moving_head``): Spider ohne
  Pixel-Kopf kippen nur und gelten NICHT als Moving Head.
* :func:`ziel_werte` — welche Programmer-Werte bekommt ein Kopf fuer einen
  Raumpunkt? Exakt die Rechnung von ``VisualizerBridge._aim_values``:
  ``aim_pan_tilt`` (8 Bit) ohne Feinkanal, ``aim_pan_tilt_16`` auf Grob + Fein
  mit Feinkanal, Nullpunkt inkl. Einmess-Versatz (``einmessen.aim_kw``).
  Anders als dort wird ``*_fine`` NICHT auf 0 gesetzt, wenn das Geraet keinen
  Feinkanal hat — das Pad soll beim Freigeben genau das zuruecknehmen, was es
  geschrieben hat, und ein Schluessel ohne Kanal ist dabei nur Ballast.

Koordinaten wie im Visualizer: ``x`` rechts, ``y`` hoch, ``z`` Richtung
Publikum (Meter). In der Draufsicht des Pads ist oben die Rueckwand (kleines
``z``) und unten das Publikum (grosses ``z``) — wie in der Live View.
"""
from __future__ import annotations

from dataclasses import dataclass

from .aim import aim_pan_tilt, aim_pan_tilt_16
from .coords import normalize_rotation
from .einmessen import aim_kw

#: Regeln der Raum-Huelle (``room_shell.js``) — bei Aenderung beide anpassen.
RAND_M = 4.0
MIN_BREITE = 12.0
MAX_BREITE = 80.0
MIN_HOEHE = 5.0
MAX_HOEHE = 20.0


@dataclass(frozen=True)
class RaumMasse:
    """Draufsicht des Raums in Metern: x von ``x0`` bis ``x1``, z von ``z0``
    (Rueckwand) bis ``z1`` (Publikum), Hoehe ``hoehe``."""
    x0: float
    x1: float
    z0: float
    z1: float
    hoehe: float

    @property
    def breite(self) -> float:
        return self.x1 - self.x0

    @property
    def tiefe(self) -> float:
        return self.z1 - self.z0

    def klemme(self, x: float, z: float) -> tuple[float, float]:
        """Punkt auf den Raum begrenzen."""
        return (min(max(float(x), self.x0), self.x1),
                min(max(float(z), self.z0), self.z1))


def _pos3(p):
    try:
        return (float(p[0]), float(p[1]), float(p[2]))
    except (TypeError, ValueError, IndexError):
        return None


def raum_masse(positionen) -> RaumMasse:
    """Raum aus den Standorten ``{fid: (x, y, z)}`` (bzw. einer Liste davon)."""
    werte = positionen.values() if hasattr(positionen, "values") else positionen
    pts = [p for p in (_pos3(v) for v in (werte or ())) if p is not None]
    if pts:
        min_x = min(p[0] for p in pts); max_x = max(p[0] for p in pts)
        min_z = min(p[2] for p in pts); max_z = max(p[2] for p in pts)
        max_y = max(0.0, max(p[1] for p in pts))
    else:
        min_x = max_x = min_z = max_z = max_y = 0.0
    breite = min(MAX_BREITE, max(MIN_BREITE, (max_x - min_x) + 2 * RAND_M))
    tiefe = min(MAX_BREITE, max(MIN_BREITE, (max_z - min_z) + 2 * RAND_M))
    hoehe = min(MAX_HOEHE, max(MIN_HOEHE, max_y + RAND_M))
    mx, mz = (min_x + max_x) / 2.0, (min_z + max_z) / 2.0
    return RaumMasse(mx - breite / 2.0, mx + breite / 2.0,
                     mz - tiefe / 2.0, mz + tiefe / 2.0, hoehe)


def _attrs(kanaele) -> list[str]:
    return [(getattr(c, "attribute", "") or "") for c in (kanaele or ())]


def bewegung(f, kanaele) -> int:
    """Wie viele Bewegungskoepfe steuert das Pad an diesem Geraet? 0 = keiner
    (kein Pan/Tilt, oder ein Spider, der nur kippt). 1 = Moving Head, N >= 2 =
    Mover-Bar mit N Koepfen (je eigener Pan + Tilt)."""
    attrs = _attrs(kanaele)
    pans, tilts = attrs.count("pan"), attrs.count("tilt")
    if pans >= 2 and tilts >= 2:
        return min(pans, tilts)
    if pans < 1 or tilts < 1:
        return 0
    try:
        from src.core.app_state import is_spider_fixture, viz_model_for
        if is_spider_fixture(f) and viz_model_for(f) != "pixel_head":
            return 0
    except Exception:
        pass
    return 1


def ziel_werte(f, kanaele, pos, rot, ziel) -> list[tuple[str, int | None, int]]:
    """``[(attribut, kopf, wert), ...]`` fuer einen Kopf an ``pos`` (Montage
    ``rot``), der auf ``ziel`` (x, y, z) zeigen soll. ``kopf`` ist ``None``
    (ganzes Geraet) oder 0..N-1 bei einer Mover-Bar. Leer, wenn das Geraet
    kein Bewegungskopf ist.

    MODELL-Werte wie beim Zielen im Visualizer: ``invert_pan``/``invert_tilt``/
    ``swap_pan_tilt`` dreht ausschliesslich die Ausgabestufe (VIZ-55)."""
    n = bewegung(f, kanaele)
    if n < 1:
        return []
    attrs = _attrs(kanaele)
    rot = normalize_rotation(rot)
    kw = aim_kw(f)
    grob8 = aim_pan_tilt(pos, ziel, rot, **kw)
    fein16 = aim_pan_tilt_16(pos, ziel, rot, **kw)
    werte: list[tuple[str, int]] = []
    for achse, a8, a16 in (("pan", grob8[0], fein16[0]), ("tilt", grob8[1], fein16[1])):
        if attrs.count(f"{achse}_fine") >= n:
            werte += [(achse, a16 >> 8), (f"{achse}_fine", a16 & 0xFF)]
        else:
            werte.append((achse, a8))
    koepfe = [None] if n == 1 else list(range(n))
    return [(attr, kopf, wert) for kopf in koepfe for attr, wert in werte]
