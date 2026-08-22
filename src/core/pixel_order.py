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


# ── ORIENT (2026-08-05): wie das Panel HAENGT, zusaetzlich zur Nummerierung ───
#
# `pixel_cell` oben beantwortet: „in welcher Reihenfolge legt das GERAET seine
# Pixel auf DMX". Das ist eine Eigenschaft des Modells bzw. seines Flip-Schalters.
# Offen blieb die zweite, davon UNABHAENGIGE Frage: „wie ist das Panel MONTIERT".
#
# ★ Warum das nicht dasselbe ist und deshalb NICHT in `pixel_order` gehoert:
# ein Panel kann in Schlangenlinien zaehlen UND hochkant haengen. Beides in ein
# Feld zu pressen hiesse, eine der beiden Aussagen zu verlieren.
#
# ★★ Und warum `mirrored` allein nicht reicht: `pixel_cell` aendert
# AUSSCHLIESSLICH die Spalte, nie die Zeile. Damit ist
#   - 180° (Zeilen- UND Spaltenumkehr) gar nicht ausdrueckbar — genau der Fall
#     „Pixel Dir = invert", den das Stairville-Panel im Geraetemenue anbietet,
#   - 90°/270° erst recht nicht, denn dort tauschen Zeilen und Spalten die
#     Rollen und das RASTER selbst aendert seine Form.
#
# Deshalb gibt `place_element` das resultierende (rows, cols) MIT zurueck. Ohne
# das rechnet es jeder Aufrufer wieder selbst — und dann laeuft es auseinander.

ELEMENT_ROTATIONS = (0, 90, 180, 270)
DEFAULT_ELEMENT_ROTATION = 0


def normalize_element_rotation(value) -> int:
    """Beliebige Eingabe -> 0/90/180/270. Nie werfen: der Wert kommt aus
    Show-Dateien und aus der DB (dieselbe Politik wie normalize_pixel_order)."""
    try:
        v = int(round(float(value or 0))) % 360
    except (TypeError, ValueError):
        return DEFAULT_ELEMENT_ROTATION
    return v if v in ELEMENT_ROTATIONS else DEFAULT_ELEMENT_ROTATION


def rotate_cell(row: int, col: int, rows: int, cols: int,
                rotation: int = 0, flip: bool = False) -> tuple:
    """``(zeile, spalte)`` im gedrehten Raster + dessen neue ``(rows, cols)``.

    Rueckgabe: ``(zeile, spalte, rows_neu, cols_neu)``.

    Die Drehung ist im Uhrzeigersinn und beschreibt, wie das Geraet HAENGT.
    ``flip`` spiegelt danach waagerecht (Panel um die Hochachse verbaut).

    Bei 90°/270° tauschen Zeilen und Spalten die Rollen — aus einem 4x12 wird
    ein 12x4. Genau deshalb reicht es nicht, nur die Position umzurechnen.
    """
    r, c = int(row), int(col)
    nr, nc = max(1, int(rows or 1)), max(1, int(cols or 1))
    rot = normalize_element_rotation(rotation)
    if rot == 90:
        r, c, nr, nc = c, nr - 1 - r, nc, nr
    elif rot == 180:
        r, c = nr - 1 - r, nc - 1 - c
    elif rot == 270:
        r, c, nr, nc = nc - 1 - c, r, nc, nr
    if flip:
        c = nc - 1 - c
    return r, c, nr, nc


def place_element(index: int, cols: int, rows: int,
                  order: str = DEFAULT_PIXEL_ORDER,
                  rotation: int = 0, flip: bool = False) -> tuple:
    """DMX-Index -> endgueltige ``(zeile, spalte, rows, cols)`` im Raster.

    Verbindet die zwei unabhaengigen Fragen in DIESER Reihenfolge:
      1. `pixel_cell` — wie das Geraet nummeriert (Werkszustand/Flip-Schalter),
      2. `rotate_cell` — wie es haengt.

    Die Reihenfolge ist nicht beliebig: die Nummerierung ist eine Aussage ueber
    das UNGEDREHTE Geraet. Erst drehen und dann die Schlangenlinie anwenden
    haette die Schlange ueber die falsche Achse laufen lassen.

    Ohne Drehung und ohne Spiegelung ist das Ergebnis elementweise identisch zu
    ``pixel_cell`` — Bestandsgeraete verhalten sich unveraendert.
    """
    nc = max(1, int(cols or 1))
    nr = max(1, int(rows or 1))
    r, c = pixel_cell(index, nc, order)
    return rotate_cell(r, c, nr, nc, rotation, flip)


# ── FM-14 / VIZ-53: der RING eines Pixel-Kopfes ──────────────────────────────
#
# Ein Pixel-Moving-Head (Robe Spiider) ist EIN Kopf, dessen Lichtquelle in
# Waben-/Ring-Segmente zerlegt ist — kein Raster. Die Plaetze rechnet deshalb
# nicht ``pixel_cell``, sondern die zwei Funktionen unten.
#
# ★ Sie sind die PYTHON-Fassung von ``ringSegmente``/``wabenPlatz`` aus
# ``scene_src/fixtures/pixel_order.js`` — dieselbe Spiegelung wie
# ``pixel_cell`` <-> ``pixelCell`` weiter oben, und aus demselben Grund: das
# 3D-Modell und das 3D-Top-Down-Icon leben in JS, die 2D-Live-View
# (``live_view.FixtureRenderer``) in Python. Zwei Fassungen, die still
# auseinanderlaufen, waeren genau der 2D/3D-Riss, den VIZ-51/52 fuer die
# Panel-Reihenfolge geschlossen haben. ``test_viz53_pixel_head_2d.py`` haelt
# beide Fassungen ZAHL FUER ZAHL gegeneinander — durch echtes Ausfuehren des
# JS-Moduls in QtWebEngine, nicht ueber den Quelltext.
#
# Aus dem Spiider-Manual (S. 15) abgelesen und fuer BEIDE Ringe gueltig:
#   Ring k: 6k Plaetze, Winkelschritt 60°/k, Startwinkel 270° - Schritt/2,
#   danach im Uhrzeigersinn einmal herum.
# ``x`` zeigt nach RECHTS, ``y`` nach OBEN (Ansicht von vorn auf die Linse).

import math as _math


def _abrunden(wert) -> int:
    """``Math.floor(wert || 0)`` — nie werfen (die Zahl kommt aus Show-Dateien,
    aus der DB und aus der Kanalzaehlung eines beliebigen Profils)."""
    try:
        return int(_math.floor(float(wert or 0)))
    except (TypeError, ValueError):
        return 0


def ring_segmente(n_baenke, basis_baenke) -> tuple:
    """``(basis, anzahl)`` — welche Farb-Baenke werden zu Ring-Segmenten?

    ``basis_baenke`` ist die Zahl der FUEHRENDEN Baenke, die KEIN Ring-Pixel
    sind (``app_state.pixel_ring_base_banks`` leitet sie aus dem Kanal-Layout
    ab). Segment ``i`` haengt an Bank ``i + basis``.

    Ohne Bank-Angabe EIN Segment — ein Pixel-Kopf ohne Kopfzahl ist eine
    unvollstaendige Nutzlast, kein Geraet ohne Pixel. Der Versatz darf nie ALLE
    Baenke wegnehmen: ein Ring ohne Segment waere ein Pixel-Kopf, der als
    gewoehnlicher Moving Head dasteht. Gekappt wird NICHTS (CDX-56).
    """
    baenke = max(1, _abrunden(n_baenke))
    basis = min(max(0, _abrunden(basis_baenke)), baenke - 1)
    return basis, baenke - basis


def waben_plaetze(ring) -> int:
    """Wie viele Plaetze fassen die Ringe 0..k? (1, 7, 19, 37, …)"""
    k = max(0, _abrunden(ring))
    return 1 + 3 * k * (k + 1)


def waben_platz(index) -> tuple:
    """Segmentindex (0 = Mitte) -> ``(ring, x, y)`` in Ring-Einheiten."""
    i = max(0, _abrunden(index))
    if i == 0:
        return 0, 0.0, 0.0
    k = 1
    while i >= waben_plaetze(k):
        k += 1
    j = i - waben_plaetze(k - 1)          # Platz innerhalb des Rings
    schritt = (_math.pi / 3) / k          # 60°/k
    # 270° = -PI/2 (unten); MINUS j*Schritt = im Uhrzeigersinn.
    winkel = -_math.pi / 2 - schritt / 2 - j * schritt
    return k, k * _math.cos(winkel), k * _math.sin(winkel)
