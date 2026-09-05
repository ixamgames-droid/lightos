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


def fixture_cell_color(fid, head, fid_order, achse=None) -> QColor:
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

    ★★ FM-41: ``achse`` unterscheidet die beiden Saetze eines Geraets. Die
    Farb-Zonen behalten Ton und Rampe unveraendert (``achse=None`` oder
    ``"rgb"`` ist byte-gleich zu vorher). Weiss-Segmente bekommen **denselben
    Geraeteton, aber stark entsaettigt** — sie gehoeren sichtbar zum selben
    Geraet und sind trotzdem nicht mit einer Farb-Zone zu verwechseln. Das
    Entsaettigen ist hier auch semantisch richtig: es IST das Weiss.

    ⚠️ Ohne diese Unterscheidung war eine Weiss-Zelle gemessen im Ton des
    ERSTEN Geraets gemalt — ``fid=None`` fiel unten auf ``idx = 0`` zurueck. Sie
    sah damit aus wie ein fremdes Geraet, und zwar ausgerechnet auf der Flaeche,
    auf der man die Zugehoerigkeit ablesen soll.

    Reine Funktion (nur Qt-Farbe, kein Widget-Zustand) -> headless testbar."""
    try:
        idx = list(fid_order).index(fid)
    except (ValueError, TypeError):
        idx = 0
    base = QColor(FIXTURE_CELL_COLORS[idx % len(FIXTURE_CELL_COLORS)])
    if achse == "w":
        # Geraeteton behalten, Saettigung stark zurueck, Helligkeit je Segment
        # leicht anheben — dieselbe Rampen-IDEE wie bei den Koepfen, damit die
        # Reihenfolge ablesbar bleibt, aber in einem klar anderen Register.
        h, s, light, a = base.getHsl()
        out = QColor()
        out.setHsl(h, int(s * 0.25),
                   min(int(light + 30 + 16 * max(0, int(head or 0))), 190), a)
        return out
    if head is None:
        return base
    # Helligkeits-Rampe je Kopf: HSL-Lightness in kleinen Schritten anheben,
    # geklemmt, damit weisse Schrift lesbar bleibt (max. ~62 % Lightness).
    h, s, light, a = base.getHsl()
    light = min(int(light + 26 * max(0, int(head))), 158)
    out = QColor()
    out.setHsl(h, s, light, a)
    return out


def head_counts(cells) -> dict[int, int]:
    """UI-52: **wie viele VERSCHIEDENE Koepfe** je Geraet im Raster liegen.

    ``cells`` = Folge von ``(fid, head)`` je Rasterzelle; ``head is None`` =
    Zelle des GANZEN Geraets (zaehlt nicht als Kopf-Zelle).

    Beide Legenden („Farbe → Gerät" im Fixture-Gruppen-Editor und im
    Matrix-Editor) schlossen die Zahl frueher aus dem hoechsten Kopf-Index:
    ``heads[fid] = max(heads.get(fid, 0), head + 1)``. Das ist nur dann die Zahl
    der Zellen, wenn die Koepfe **luecken los ab 0** liegen — was nur der
    Streifen aus ``place_fixture_heads``/``create_head_matrix_group`` tut. Sobald
    eine Zelle fehlt (Rechtsklick → „Zelle entfernen"; Ring-Raster eines Robin
    Spiiders, dessen 19 Pixel als Koepfe 1..19 liegen, weil Kopf 0 die Grundfarbe
    des Geraets ist), zaehlte die Formel entfernte bzw. nie platzierte Koepfe mit.

    Bewusst HIER und nicht in einer der beiden Views: die Formel stand zweimal im
    Code und war zweimal falsch — dieselbe Drift, gegen die dieses Modul schon
    fuer die Farben angelegt wurde. Ein Set statt eines Zaehlers haelt die Zahl
    auch dann richtig, wenn derselbe Kopf zweimal im Raster steht.

    Reine Funktion -> headless testbar."""
    sets: dict[int, set[int]] = {}
    for fid, head in cells:
        if fid is None or head is None:
            continue
        try:
            sets.setdefault(int(fid), set()).add(int(head))
        except (TypeError, ValueError):
            continue
    return {fid: len(heads) for fid, heads in sets.items()}


def head_count_suffix(n) -> str:
    """Der Zusatz hinter dem Geraetenamen in der Legende — ``""`` ohne Kopf-Zelle.

    UI-52: **auch EINE Kopf-Zelle bekommt den Zusatz** (in der Einzahl). Vorher
    galt die Schwelle ``n > 1``; zusammen mit der alten ``max(head)+1``-Formel
    fiel das nie auf, weil eine einzelne Kopf-Zelle mit Index > 0 faelschlich
    eine groessere Zahl meldete. Mit der richtigen Zaehlung waere der Eintrag
    sonst von einer GANZ-Geraete-Zelle nicht mehr zu unterscheiden — genau die
    Unterscheidung, fuer die es die Legende gibt."""
    try:
        n = int(n or 0)
    except (TypeError, ValueError):
        return ""
    if n < 1:
        return ""
    return " (1 Kopf)" if n == 1 else f" ({n} Köpfe)"
