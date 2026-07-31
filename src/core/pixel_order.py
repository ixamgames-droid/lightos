"""EINE Quelle fuer die Pixel-Reihenfolge eines Matrix-Panels
(``PatchedFixture.pixel_order``).

FM-13: Ein Panel adressiert seine Pixel ueber die DMX-Kanal-Reihenfolge — WO
diese Pixel physisch sitzen, sagt das Profil aber nicht. Gemessen an der **ADJ
Dotz Matrix** (Manual S. 12): im Werkszustand („Pixel Flip: Standard")
nummeriert sie in **Schlangenlinien** ::

     1  2  3  4
     8  7  6  5
     9 10 11 12
    16 15 14 13

``buildMatrixPanel`` legt die Pixel dagegen zeilenweise an. Eine horizontale
Lauflicht-Figur laeuft auf so einem Panel deshalb im **Zickzack** — im 3D sieht
sie richtig aus, am echten Geraet nicht. Beim **Stairville Pixel Panel 144**
dokumentiert das Manual ueberhaupt keine Anordnung.

Deshalb ist die Reihenfolge eine Eigenschaft des GEPATCHTEN GERAETS, nicht des
Profils: dasselbe Modell kann am Geraet umgestellt sein („Flip 1..4"), und ein
Umsortieren im Profil waere fuer die jeweils anderen Stellungen wieder falsch.

* ``"rowwise"``   – zeilenweise, links→rechts, oben→unten (DEFAULT = Bestands-
  verhalten; Alt-Shows rendern damit byte-genau wie bisher).
* ``"serpentine"`` – Schlangenlinien: jede zweite Zeile laeuft rueckwaerts
  (Werkszustand der Dotz Matrix).
* ``"mirrored"``  – zeilenweise, aber jede Zeile rechts→links (Panel um die
  Hochachse gedreht verbaut).

Bewusst ein **Leaf-Modul OHNE Projekt-Importe** — dieselbe Begruendung wie bei
``core.head_mode``: Show-Persistenz, Live-Schreibpfad und das Spalten-Modell
muessen es zyklenfrei importieren koennen, und Tests stubben ``models`` aus.

Die JS-Seite hat dieselbe Regel in ``scene_src/fixtures/pixel_order.js``; die
Tests halten beide Fassungen gegeneinander (eine zweite Regel, die still
auseinanderlaeuft, waere genau die Drift-Quelle aus der FM16E-Lehre).
"""
from __future__ import annotations

PIXEL_ORDERS = ("rowwise", "serpentine", "mirrored")
DEFAULT_PIXEL_ORDER = "rowwise"

PIXEL_ORDER_LABELS = {
    "rowwise": "Zeilenweise (links→rechts)",
    "serpentine": "Schlangenlinien (jede 2. Zeile rückwärts)",
    "mirrored": "Gespiegelt (rechts→links)",
}


def normalize_pixel_order(value) -> str:
    """Beliebige Eingabe -> gueltiger Wert. Unbekanntes faellt auf den Default
    zurueck (nie werfen: der Wert kommt aus Show-Dateien und aus der DB)."""
    v = str(value or "").strip().lower()
    return v if v in PIXEL_ORDERS else DEFAULT_PIXEL_ORDER


def pixel_cell(index: int, cols: int, order: str = DEFAULT_PIXEL_ORDER) -> tuple:
    """DMX-Pixelindex -> ``(zeile, spalte)`` im sichtbaren Raster.

    ``index`` ist 0-basiert und die Reihenfolge, in der das Geraet seine Pixel
    auf DMX legt; die Rueckgabe ist die Position, an der dieses Pixel WIRKLICH
    sitzt. Genau diese Umrechnung fehlte bisher — der Renderer nahm implizit an,
    beides sei dasselbe.
    """
    cols = max(1, int(cols or 1))
    i = max(0, int(index or 0))
    row, col = divmod(i, cols)
    o = normalize_pixel_order(order)
    if o == "serpentine" and row % 2 == 1:
        col = cols - 1 - col
    elif o == "mirrored":
        col = cols - 1 - col
    return row, col
