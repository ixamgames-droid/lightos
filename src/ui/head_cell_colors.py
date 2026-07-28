"""EINE Quelle fuer die Kopf-/Geraete-Farbsprache der Rasterzellen.

FM-HEADLAYOUT Slice 4 fuehrte „**Farbton je Geraet, Helligkeit je Kopf**" im
Fixture-Gruppen-Editor ein; der Matrix-Editor zeigte dieselben Zellen weiter ohne
jede Zuordnung. Damit beide Ansichten NICHT auseinanderdriften, liegt die Palette
und die Farbfunktion hier — nicht in einer der beiden Views.

Regel aus Slice 4, die auch hier gilt: **Legende und gerendertes Element nie aus
zwei Farbquellen speisen.** Wer eine neue Flaeche baut, die Kopf-/Geraete-Zellen
zeigt, importiert ``fixture_cell_color`` und definiert KEINE eigene Palette.

Bewusst ein UI-Modul (liefert ``QColor``) und kein ``core``-Leaf — es haengt an
Qt, aber an keinem Widget-Zustand: die Funktion ist rein und headless testbar.
"""
from __future__ import annotations

from PySide6.QtGui import QColor

# Bewusst dunkle, kraeftige Basistoene (dunkles UI, weisse Schrift muss lesbar
# bleiben) mit deutlich unterschiedlichem Farbton — nicht nur Helligkeit, damit
# sie auch bei Rot-Gruen-Schwaeche unterscheidbar bleiben.
FIXTURE_CELL_COLORS = (
    "#0978FF",   # Blau (bisheriger Standardton -> Ein-Geraet-Gruppen sehen aus wie vorher)
    "#22a06b",   # Gruen
    "#c2410c",   # Orange-Rot
    "#7c3aed",   # Violett
    "#0e7490",   # Petrol
    "#a16207",   # Ocker
    "#be185d",   # Magenta
    "#4d7c0f",   # Oliv
)

# Rueckwaerts-Alias: der frueher private Name aus fixture_group_view.
_FIXTURE_CELL_COLORS = FIXTURE_CELL_COLORS


def fixture_cell_color(fid, head, fid_order) -> QColor:
    """Zellfarbe fuer ``fid``/``head``: **Farbton je Geraet, Helligkeit je Kopf.**

    * ``fid_order`` = Basis-fids in Raster-Reihenfolge (``base_fids_in_grid_order``).
      Der Farb-Index ist die POSITION darin, nicht der fid selbst — so bekommen
      die Geraete EINER Gruppe garantiert unterschiedliche Toene (genau der Zweck),
      statt dass z. B. fid 1 und fid 9 bei ``fid % 8`` denselben Ton erwischen.
    * Koepfe desselben Geraets teilen den Farbton und werden nur **aufgehellt**
      (K1 dunkel -> Kn heller) — dadurch ist die Kopf-REIHENFOLGE ablesbar und die
      Zugehoerigkeit bleibt trotzdem sofort sichtbar.
    * Ein Geraet ohne Kopf-Zelle (ganzes Fixture) behaelt den Basiston; eine
      Ein-Geraet-Gruppe sieht damit aus wie vor Slice 4 (kein Bruch mit Gewohnheit).

    Reine Funktion (nur Qt-Farbe, kein Widget-Zustand) -> headless testbar."""
    try:
        idx = list(fid_order).index(fid)
    except (ValueError, TypeError):
        idx = 0
    base = QColor(FIXTURE_CELL_COLORS[idx % len(FIXTURE_CELL_COLORS)])
    if head is None:
        return base
    # Helligkeits-Rampe je Kopf: HSL-Lightness in kleinen Schritten anheben,
    # geklemmt, damit weisse Schrift lesbar bleibt (max. ~62 % Lightness).
    h, s, light, a = base.getHsl()
    light = min(int(light + 26 * max(0, int(head))), 158)
    out = QColor()
    out.setHsl(h, s, light, a)
    return out
