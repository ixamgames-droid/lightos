"""FM-22: Panel-Raster und Lauflicht-Muster — die Rechnung hinter den zwei
Knoepfen im Matrix-Effekt-Tab.

Ausloeser (Robin, 2026-08-05): die Demo-Show fuer den 48-Zonen-Balken liess sich
**nur per Build-Skript** erzeugen. Zwei Dinge fehlten in der UI, beide hier:

**(1) Das Raster.** Ein Matrix-Effekt bekommt sein Raster bisher aus einer
Fixture-Gruppe. Fuer ein Panel heisst das: Gruppen-Tab oeffnen, Raster
vergroessern, Geraet finden, aufteilen, zurueck zum Matrix-Tab — und das nur,
damit am Ende ``cols/rows/fixture_grid/head_grid`` gesetzt sind. ``panel_grid``
rechnet dieselben Zellen direkt aus, ohne den Umweg ueber die Gruppe.

★ Die Rechnung selbst wird NICHT nachgebaut: sie kommt aus
:func:`src.core.pixel_order.place_element` — derselben Quelle, aus der auch
``FixtureGridWidget.place_fixture_block`` (FM-20 Teil 1) und die 3D-Vorschau
schoepfen. Zwei Fassungen derselben Formel waeren genau die Drift-Quelle aus
der FM16E-Lehre.

**(2) Die Muster.** Ein Lauflicht „Spalte fuer Spalte" ist in der UI nur als
Chaser aus 12 einzeln angelegten Szenen baubar — je Szene 4 Zonen von Hand
faerben. Die Matrix-Algorithmen koennen es NICHT ersetzen: sie laufen mit
eigenem Tempo ueber die Flaeche, man sieht einen Verlauf, keine klare Kante.
``pattern_frames`` liefert stattdessen je Schritt genau die Zellen, die leuchten
sollen; ``build_pattern_chaser`` macht daraus Szenen + Chaser.

Bewusst OHNE Qt-Importe: das Raster und die Muster sind reine Geometrie und
muessen headless pruefbar bleiben.
"""
from __future__ import annotations

from src.core.pixel_order import (DEFAULT_PIXEL_ORDER, place_element)

# ── Teil 1: Raster aus einem Geraet ──────────────────────────────────────────


def panel_grid(head_count: int, block_cols: int, *,
               order: str = DEFAULT_PIXEL_ORDER,
               rotation: int = 0, flip: bool = False) -> tuple:
    """``head_count`` Koepfe EINES Geraets -> ``(cols, rows, head_grid)``.

    ``head_grid`` ist row-major und genau ``cols*rows`` lang; jeder Eintrag ist
    der Kopf-Index, der in dieser Zelle sitzt, oder ``None`` fuer eine Luecke.
    Luecken entstehen, wenn ``head_count`` nicht durch ``block_cols`` teilbar
    ist (angebrochene letzte Zeile) — sie bleiben leer statt zu wandern, denn
    ein verschobener Kopf waere am Geraet nicht als Fehler erkennbar.

    ``block_cols`` ist die Breite VOR der Drehung. Bei 90°/270° tauschen Zeilen
    und Spalten die Rollen (aus 12x4 wird 4x12) — die zurueckgegebenen Masse
    kommen deshalb aus ``place_element`` selbst und werden nicht danebenher
    gerechnet.

    Ungueltige Eingaben liefern ``(0, 0, [])`` statt zu werfen: der Aufrufer ist
    eine Dialog-Spinbox, und ein leeres Raster ist dort die ehrliche Antwort.
    """
    try:
        count = int(head_count)
        bcols = int(block_cols)
    except (TypeError, ValueError):
        return 0, 0, []
    if count < 1 or bcols < 1:
        return 0, 0, []

    block_rows = (count + bcols - 1) // bcols
    _r0, _c0, rows, cols = place_element(0, bcols, block_rows,
                                         order, rotation, flip)
    cells: list = [None] * (rows * cols)
    for h in range(count):
        r, c, _nr, _nc = place_element(h, bcols, block_rows,
                                       order, rotation, flip)
        idx = r * cols + c
        if 0 <= idx < len(cells):
            cells[idx] = h
    return cols, rows, cells


def suggested_block_cols(head_count: int) -> int:
    """Vorbelegung fuer die Spaltenzahl: ein TEILER von ``head_count`` nahe der
    Wurzel (48 -> 6, nicht 7).

    Ein Rest waere kein Fehler — die letzte Zeile bliebe kuerzer —, aber bei
    einem Panel ist eine angebrochene Zeile fast immer ein Vertipper. Gleiche
    Regel wie ``FixtureGroupView._ask_block_cols``, damit beide Wege dieselbe
    Zahl vorschlagen.
    """
    try:
        n = int(head_count)
    except (TypeError, ValueError):
        return 1
    if n < 2:
        return max(1, n)
    teiler = [t for t in range(2, n) if n % t == 0]
    return min(teiler, key=lambda t: abs(t - (n ** 0.5)), default=n)


# ── Teil 2: Lauflicht-Muster ueber das Raster ────────────────────────────────

# (Schluessel, Beschriftung) — die Reihenfolge ist die im Auswahlfeld.
PATTERN_DIRECTIONS = (
    ("spalten_lr", "Spalten: links → rechts"),
    ("spalten_rl", "Spalten: rechts → links"),
    ("reihen_ou", "Reihen: oben → unten"),
    ("reihen_uo", "Reihen: unten → oben"),
    ("diagonal_lo", "Diagonal: links oben → rechts unten"),
    ("diagonal_ro", "Diagonal: rechts oben → links unten"),
)
DEFAULT_DIRECTION = "spalten_lr"

_DIRECTION_KEYS = tuple(k for k, _label in PATTERN_DIRECTIONS)


def direction_label(key: str) -> str:
    """Beschriftung zu einem Richtungs-Schluessel (unbekannt -> der Schluessel
    selbst, damit eine Alt-Show nichts Leeres anzeigt)."""
    for k, label in PATTERN_DIRECTIONS:
        if k == key:
            return label
    return str(key)


def _band_index(row: int, col: int, cols: int, rows: int, direction: str) -> int:
    """Welchem „Band" gehoert diese Zelle in dieser Richtung?

    Ein Band ist das, was in EINEM Schritt gemeinsam leuchtet: eine Spalte, eine
    Zeile oder eine Diagonale. Nur hier steht, was „Richtung" geometrisch heisst
    — Schrittzahl und Balkenbreite fallen daraus ab.
    """
    if direction in ("spalten_lr", "spalten_rl"):
        return col
    if direction in ("reihen_ou", "reihen_uo"):
        return row
    if direction == "diagonal_ro":
        return row + (cols - 1 - col)
    return row + col                      # diagonal_lo (und Default)


def band_count(cols: int, rows: int, direction: str) -> int:
    """Wie viele Schritte hat ein voller Durchlauf in dieser Richtung?"""
    c, r = max(0, int(cols)), max(0, int(rows))
    if c < 1 or r < 1:
        return 0
    if direction in ("spalten_lr", "spalten_rl"):
        return c
    if direction in ("reihen_ou", "reihen_uo"):
        return r
    return c + r - 1                      # Diagonalen


def pattern_frames(cols: int, rows: int, direction: str = DEFAULT_DIRECTION,
                   *, width: int = 1) -> list:
    """Ein Schritt je Balkenposition -> Liste von Zell-Indizes (row-major).

    ★ Der Balken laeuft UMLAUFEND (modulo), nicht anlaufend. Damit ist er in
    jedem Schritt gleich breit und die Schleife hat keine Naht — ein Balken, der
    am Rand schmaler wird, sieht am Geraet nach einem Fehler aus. Bei
    ``width=1`` sind beide Lesarten ohnehin identisch; genau dieser Fall ist der
    Referenzaufbau aus ``tools/build_zq06121_demo.py``.

    ``width`` wird auf die Zahl der Baender geklemmt: ein Balken, der breiter
    als die Flaeche ist, wuerde umlaufend jede Zelle mehrfach treffen und damit
    schlicht alles einschalten — das ist kein Lauflicht mehr.

    ``spalten_rl``/``reihen_uo`` sind die zeitlich umgekehrte Vorwaerts-Folge:
    derselbe Balken, nur andersherum laufend — und nicht ein zweiter, der sich
    in der Kante unterscheidet. Die beiden Diagonalen werden NICHT umgekehrt;
    sie sind keine Gegenrichtungen voneinander, sondern die zwei ACHSEN, und ihr
    Band 0 liegt schon in der jeweiligen Startecke (``diagonal_lo`` links oben,
    ``diagonal_ro`` rechts oben). Ein Umkehren haette sie an der falschen Ecke
    starten lassen.
    """
    c, r = max(0, int(cols)), max(0, int(rows))
    n = band_count(c, r, direction)
    if n < 1:
        return []
    w = max(1, min(int(width or 1), n))

    # Zellen je Band einmal einsammeln (statt je Schritt ueber das Raster zu
    # laufen) — bei 48 Zonen x 12 Schritten sonst 576 Durchlaeufe.
    bands: list[list[int]] = [[] for _ in range(n)]
    for rr in range(r):
        for cc in range(c):
            b = _band_index(rr, cc, c, r, direction)
            if 0 <= b < n:
                bands[b].append(rr * c + cc)

    frames = []
    for p in range(n):
        cells: list[int] = []
        for k in range(w):
            cells.extend(bands[(p + k) % n])
        frames.append(sorted(cells))
    if direction in ("spalten_rl", "reihen_uo"):
        frames.reverse()
    return frames


# ── Teil 3: aus Mustern werden Szenen + ein Chaser ───────────────────────────


def cell_channel_values(fx, head, color, *, drive_intensity: bool = True) -> dict:
    """``{kanal_offset_1basiert: wert}`` fuer EINE Zelle.

    Geht denselben Weg wie ``RgbMatrixInstance.write``: Kanaele des Geraets ->
    Projektion auf den Kopf (``channels_for_head``) -> Farbkanaele setzen. Ein
    Kopf-Index ``None`` faerbt das ganze Geraet (Zelle = ganzes Fixture).

    ★ ``drive_intensity`` ist hier Pflicht und keine Kosmetik. Ein Panel hat
    einen eigenen Master-Dimmer (ZQ06121: CH1), und der bleibt sonst auf 0 — das
    Geraet ist dann STOCKDUNKEL, obwohl die Szene korrekte Farbwerte auf alle
    144 Farbkanaele schreibt. Genau so ist es beim ersten Live-Test passiert.
    Deshalb kommen bei Kopf-Zellen auch die GETEILTEN Master-Kanaele mit
    (``shared_master_channels``, FM-17): der Kopf-eigene Dimmer nuetzt nichts,
    solange der gemeinsame davor auf 0 steht.

    Weiss (``color_w``) wird bewusst NICHT bedient. Beim ZQ06121 liegen die acht
    Warmweiss-Segmente auf den Koepfen 1-8, decken physisch aber je anderthalb
    RGB-Spalten ab — ein Lauflicht wuerde acht willkuerliche Zonen zusaetzlich
    weiss faerben. Robin hat am 2026-08-05 ausdruecklich bestaetigt: Weiss soll
    bei Farbeffekten nicht mitlaufen.
    """
    from src.core.app_state import (get_channels_for_patched, channels_for_head,
                                    shared_master_channels, _DIM_INTENSITY_ATTRS)
    try:
        chans = list(get_channels_for_patched(fx))
    except Exception:
        return {}
    if head is None:
        target = chans
    else:
        proj = channels_for_head(chans, int(head))
        target = list(proj.values())
        for attr in list(proj):
            if attr in _DIM_INTENSITY_ATTRS:
                target.extend(shared_master_channels(chans, attr))

    r, g, b = (int(color[0]), int(color[1]), int(color[2]))
    out: dict = {}
    for ch in target:
        attr = (getattr(ch, "attribute", "") or "").lower()
        if attr == "color_r":
            val = r
        elif attr == "color_g":
            val = g
        elif attr == "color_b":
            val = b
        elif attr in _DIM_INTENSITY_ATTRS:
            if not drive_intensity:
                continue
            val = 255
        else:
            continue
        num = getattr(ch, "channel_number", None)
        if num is None:
            continue
        out[int(num)] = max(0, min(255, int(val)))
    return out


def build_pattern_chaser(manager, matrix, frames, *, name: str,
                         color=(255, 255, 255), hold: float = 0.12,
                         patch_cache=None, drive_intensity: bool = True):
    """Baut Szenen + Chaser aus fertigen ``frames`` und haengt sie in ``manager``.

    Ein Schritt je Frame, ``fade_in``/``fade_out`` bewusst 0: das Muster lebt
    von der harten Kante. Wer weiche Uebergaenge will, hat dafuer die
    Matrix-Algorithmen — genau die Unterscheidung, wegen der es diesen Weg
    ueberhaupt gibt.

    Nur die LEUCHTENDEN Zellen bekommen Werte. Die dunklen bleiben ungeschrieben
    statt auf 0 gesetzt zu werden, damit der Chaser eine darunterliegende Ebene
    (Grundlicht, zweiter Effekt) nicht ausknipst — dasselbe Verhalten wie beim
    Referenz-Aufbau.

    Die Schritt-Szenen landen in einem Bibliotheks-Ordner mit dem Namen des
    Musters; der Chaser selbst bleibt in der Wurzel — er ist das, was man
    startet und auf einen Taster zieht.

    Rueckgabe: ``(chaser, szenen)``. Ohne Frames oder ohne zuweisbare Zellen
    wird NICHTS angelegt und ``(None, [])`` zurueckgegeben — ein leerer Chaser
    im Funktionsbaum waere schlimmer als eine Fehlermeldung.
    """
    from src.core.engine.chaser import Chaser, ChaserStep
    from src.core.engine.scene import Scene

    grid = list(getattr(matrix, "fixture_grid", []) or [])
    heads = list(getattr(matrix, "head_grid", []) or [])
    if not frames or not grid:
        return None, []

    if patch_cache is None:
        try:
            from src.core.app_state import get_state
            patch_cache = list(get_state().get_patched_fixtures())
        except Exception:
            patch_cache = []
    by_fid = {}
    for fx in patch_cache or []:
        fid = getattr(fx, "fid", None)
        if fid is not None:
            by_fid[int(fid)] = fx

    # Kanalwerte je Zelle EINMAL aufloesen: dieselbe Zelle taucht in mehreren
    # Schritten auf (Balkenbreite > 1), und die Aufloesung geht ueber den
    # Kanal-Cache des Geraets.
    cache: dict = {}

    def _cell_values(idx):
        """``(fid, {kanal: wert})`` oder ``None``, wenn die Zelle nichts trifft."""
        if idx not in cache:
            cache[idx] = None
            if 0 <= idx < len(grid) and grid[idx] is not None:
                fx = by_fid.get(int(grid[idx]))
                if fx is not None:
                    head = heads[idx] if idx < len(heads) else None
                    vals = cell_channel_values(fx, head, color,
                                               drive_intensity=drive_intensity)
                    if vals:
                        cache[idx] = (int(grid[idx]), vals)
        return cache[idx]

    # ★ Die Schritt-Szenen kommen in einen eigenen Bibliotheks-Ordner. Ein
    # Lauflicht ueber 12 Spalten sind 12 Szenen; lose in der Wurzel machen zwei
    # Muster die Funktionsliste unbenutzbar — und der Assistent soll das Arbeiten
    # erleichtern, nicht das Aufraeumen. Ein "/" im Namen wuerde die Ordner-
    # Hierarchie (FLD-01a, "/"-getrennt) unbeabsichtigt verschachteln.
    ordner = str(name).replace("/", "-")

    szenen = []
    schritte = []
    for i, cells in enumerate(frames):
        sc = Scene(f"{name} · Schritt {i + 1}")
        sc.folder = ordner
        gesetzt = 0
        for idx in cells:
            got = _cell_values(idx)
            if not got:
                continue
            fid, vals = got
            for chan, val in vals.items():
                sc.set_value(fid, chan, val)
                gesetzt += 1
        if gesetzt == 0:
            continue                      # Schritt ohne Geraet -> kein Schritt
        szenen.append(sc)
        schritte.append(sc)

    if not schritte:
        return None, []

    ch = Chaser(name)
    for sc in schritte:
        manager.add(sc)
        ch.steps.append(ChaserStep(function_id=sc.id, fade_in=0.0,
                                   hold=max(0.01, float(hold)), fade_out=0.0))
    manager.add(ch)
    return ch, szenen
