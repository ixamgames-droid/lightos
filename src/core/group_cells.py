"""EINE Quelle fuer das Parsen von ``FixtureGroup.positions_json``-Zellwerten.

Eine Rasterzelle einer Fixture-Gruppe haelt ENTWEDER ein ganzes Fixture (``fid``,
int oder str) ODER — seit FM-16 (Pro-Kopf-Matrix) — eine **Kopf-Zelle**
``"fid:head"`` (aus ``AppState.create_head_matrix_group`` / ``merge_head_matrix_
groups``). Historisch parsten mehrere Resolver den Zellwert je fuer sich per
``int(v)`` — das wirft bei ``"5:2"`` (``ValueError``) und liess die Kopf-Zelle
**still fallen**: eine Kopf-Matrix-Gruppe erschien so mit ``(0)`` Geraeten und
selektierte nichts (FM16E-HEADCOUNT). Dieses Modul buendelt das Parsen an EINER
Stelle, damit die Views nicht auseinanderdriften. Bewusst OHNE Projekt-Imports
(Leaf-Modul) — jeder Resolver (Core ``app_state`` UND UI) darf es zyklenfrei
importieren.
"""
from __future__ import annotations


def parse_group_cell(value) -> tuple:
    """Zellwert -> ``(fid, head)``. Ein reiner Zahlwert (``5`` / ``"5"``) = GANZES
    Fixture -> ``(5, None)``; ``"5:2"`` = KOPF 2 des Fixtures 5 -> ``(5, 2)``.
    Unparsbar -> ``(None, None)``. Rueckwaertskompatibel (Alt-Gruppen = reine fids
    laden unveraendert). Byte-gleich zu den frueheren ``rgb_matrix._parse_cell`` /
    ``fixture_group_view._split_cell`` (die jetzt hierher delegieren)."""
    try:
        s = str(value)
        if ":" in s:
            fid_s, head_s = s.split(":", 1)
            head = int(head_s)
            # FM-45: ein NEGATIVER Kopfindex ist keine Kopf-Zelle, sondern eine
            # kaputte. Vorher kam "1:-1" als Kopf -1 durch und wurde ueberall wie
            # ein echter Kopf behandelt; im Renderer lieferte er die GETEILTEN
            # Kanaele, also den Master-Dimmer des ganzen Geraets (gemessen).
            # Unparsbar heisst hier wie sonst: die Zelle faellt weg. Bewusst
            # NICHT auf "(fid, None)" abbilden - das waere die stille
            # Befoerderung einer kaputten Kopf-Zelle zum GANZEN Geraet, also
            # genau in die gefaehrliche Richtung.
            if head < 0:
                return None, None
            return int(fid_s), head
        return int(s), None
    except Exception:
        return None, None


# ── FM-41: die ACHSE einer Zelle ────────────────────────────────────────────
# Ein Geraet kann mehrere Emitter-Saetze haben, die NICHT dasselbe Raster
# bilden. Robins ZQ06121 traegt 48 RGB-Zonen (4x12) UND 8 eigene
# Warmweiss-Segmente, die mittig zwischen Reihe 2 und 3 sitzen und je
# anderthalb RGB-Spalten abdecken — „die beiden Raster fallen also NICHT
# zusammen", sagt die Bibliothek selbst.
#
# Bis 2026-09-03 kannte das Zellformat nur EINEN Kopfindex, und der adressierte
# alle Achsen zugleich: `channels_for_head(chans, 3)` lieferte gemessen
# `color_r = CH12 'Zone 4 Rot'` UND `color_w = CH150 'Weiss-Zone 4'`. Die
# Zellen K1..K8 fuhren also acht willkuerliche Weiss-Segmente mit, K9..K48
# hatten gar keins. Das ist der „Zuordnungs-Salat" aus der Rig-Meldung.
#
# ★ Die Entscheidung des Betreibers (03.09.2026): ein solches Geraet soll beim
# Gruppenbauen ZWEI ansprechbare Saetze zeigen — „einmal die RGB-Variante und
# einmal die, die nur weiss kann" — damit man eine Gruppe nur aus Weiss, nur
# aus RGB oder aus beidem bauen kann. Ausdrueckliche Auflage: **generisch aus
# den Kanaelen abgeleitet, kein Geraete-Sonderfall.**
ACHSE_FARBE = "rgb"
ACHSE_WEISS = "w"

# Achse -> Attribut, dessen Vorkommen die Koepfe DIESER Achse zaehlen.
ACHSEN_ATTRIBUT = {ACHSE_FARBE: "color_r", ACHSE_WEISS: "color_w"}

# Zellwert-Praefix je Achse. Die Farb-Achse hat KEINEN — `"5:2"` bleibt exakt
# wie bisher, damit jede bestehende Gruppe und jede gespeicherte Show
# unveraendert laedt.
_ACHSEN_PRAEFIX = {ACHSE_WEISS: "w"}


def zelle_fuer(fid: int, achse: str | None = None, index: int | None = None) -> str:
    """``(fid, achse, index)`` -> Zellwert. Gegenstueck zu :func:`parse_zelle`.

    EINE Stelle, an der ein Zellwert entsteht — sonst steht in einem Jahr das
    zweite ``f"{fid}:w{n}"`` im Baum und die beiden laufen auseinander.
    """
    if achse is None or index is None:
        return str(int(fid))
    if achse == ACHSE_FARBE:
        return f"{int(fid)}:{int(index)}"
    praefix = _ACHSEN_PRAEFIX.get(achse)
    if praefix is None:
        raise ValueError(f"unbekannte Achse: {achse!r}")
    return f"{int(fid)}:{praefix}{int(index)}"


def parse_zelle(value) -> tuple:
    """Zellwert -> ``(fid, achse, index)``. Die achsen-bewusste Lesung.

    * ``5`` / ``"5"``   -> ``(5, None, None)``   — ganzes Geraet
    * ``"5:2"``         -> ``(5, "rgb", 2)``     — Farb-Kopf 2
    * ``"5:w3"``        -> ``(5, "w", 3)``       — Weiss-Segment 3
    * unparsbar         -> ``(None, None, None)``

    ★★ **:func:`parse_group_cell` bleibt daneben bestehen und ist bewusst
    VERLUSTBEHAFTET:** fuer ``"5:w3"`` liefert es ``(None, None)``, also „diese
    Zelle kenne ich nicht" — und ausdruecklich NICHT ``(5, None)``. Das waere
    die stille Befoerderung eines Weiss-Segments zum GANZEN Geraet, also genau
    in die gefaehrliche Richtung (dieselbe Ueberlegung wie bei FM-45s negativem
    Kopfindex). Gemessen haengen 61 Aufrufstellen in 12 Dateien an dem
    2-Tupel-Vertrag; sie duerfen unveraendert bleiben und sehen eine Weiss-Zelle
    schlicht nicht, statt sie falsch zu sehen.

    Negativer Index ist unparsbar — dieselbe Regel wie fuer Kopf-Zellen (FM-45).
    """
    try:
        s = str(value)
        if ":" not in s:
            return int(s), None, None
        fid_s, rest = s.split(":", 1)
        fid = int(fid_s)
        for achse, praefix in _ACHSEN_PRAEFIX.items():
            if rest.startswith(praefix):
                index = int(rest[len(praefix):])
                return (fid, achse, index) if index >= 0 else (None, None, None)
        index = int(rest)
        return (fid, ACHSE_FARBE, index) if index >= 0 else (None, None, None)
    except Exception:
        return None, None, None


def achsen_zellen(cells, achse: str) -> list:
    """Aus einer Zell-Liste die Indizes je Geraet fuer GENAU EINE Achse.

    ``["1", "1:0", "1:w3", "2:w0"]``, Achse ``"w"`` -> ``{1: {3}, 2: {0}}``.
    Ganz-Geraet-Zellen (``"1"``) zaehlen fuer KEINE Achse — sie meinen das
    ganze Geraet und damit alles.
    """
    out: dict[int, set] = {}
    for c in cells or []:
        fid, a, index = parse_zelle(c)
        if fid is None or a != achse or index is None:
            continue
        out.setdefault(fid, set()).add(int(index))
    return out


def head_restrictions(cells) -> dict:
    """Zell-Liste -> ``{fid: {head, ...}}``: auf WELCHE Koepfe eine Auswahl bzw.
    ein Gruppen-Raster ein Geraet einschraenkt (FM-HEADLAYOUT A4).

    ``["1", "2:0", "2:3"]`` -> ``{2: {0, 3}}``. Enthalten sind NUR Geraete, deren
    Zellen ausschliesslich Kopf-Zellen sind: taucht dasselbe Geraet auch als
    GANZE Zelle (``"2"``) auf, gewinnt das ganze Geraet und faellt hier raus —
    dieselbe Vorrang-Regel wie ``AppState.set_selected_cells`` ("die groebere
    Aussage ist die sichere: alle Koepfe"). Ein leeres Ergebnis heisst also
    ausdruecklich „keine Kopf-Einschraenkung" (= Bestandsverhalten), NICHT
    „nichts gewaehlt".

    ★ Die Vorrang-Regel ist hier BEWUSST die umgekehrte wie in
    ``drop_whole_cells_with_heads`` (FM-32), wo beim Zusammenlegen die KOPF-Zellen
    gewinnen: dort geht es um den Raster-INHALT, und die groebere Zelle nimmt
    Information weg; hier um eine AUSWAHL, wo die groebere Aussage („alle Koepfe")
    die sichere ist. Wer eine der beiden Stellen anfasst, muss die andere mitlesen
    — das ist kein Fluechtigkeitsfehler.

    EINE Quelle fuer Auswahl-Zellen (``get_selected_cells``) UND Gruppen-
    Rasterzellen (``positions_json``), damit „Nur Auswahl" und „Feste Gruppe"
    beim VC-Submaster nicht auseinanderdriften."""
    heads: dict[int, set] = {}
    whole: set = set()
    for c in cells or []:
        fid, head = parse_group_cell(c)
        if fid is None:
            continue
        if head is None:
            whole.add(fid)
        else:
            heads.setdefault(fid, set()).add(int(head))
    return {f: hs for f, hs in heads.items() if hs and f not in whole}


def drop_whole_cells_with_heads(cells: dict) -> dict:
    """Raster-Zellen -> dieselben Zellen OHNE die GANZ-Zellen der Geraete, die im
    selben Raster auch KOPFWEISE liegen (FM-32). Eingabe/Ausgabe: eine beliebig
    geschluesselte Map ``{zelle: fid|"fid:head"}`` (``(col,row)``-Tupel wie im
    Gruppen-Editor oder ``"col,row"``-Strings wie im ``positions_json``).

    **Die Regel: die feinere Form gewinnt.** Ein Geraet, das zugleich als ganzes
    UND kopfweise im Raster steht, wird von zwei Zellen gleichzeitig gefahren —
    die Ganz-Zelle faerbt ALLE Koepfe uniform, die Kopf-Zellen jeden einzeln. Wer
    von beiden am Ende auf DMX steht, entscheidet die Schreib-Reihenfolge
    (``RgbMatrixInstance.write`` laeuft row-major ueber das Raster), also die
    Stapelreihenfolge beim Zusammenlegen — am selben Geraetepaar gemessen einmal
    vier verschiedene Pixelwerte, einmal vier gleiche. Das ist kein Zustand, den
    der Nutzer gewaehlt hat.

    Verworfen wird die GANZ-Zelle, weil die Kopf-Zellen alles koennen, was sie
    kann (alle Koepfe dieselbe Farbe), umgekehrt aber nicht — und weil das
    Zusammenlegen genau dafuer da ist, aus Kopf-Matrizen EINE groessere Matrix zu
    machen: liesse man die Ganz-Zelle gewinnen, verloere das Raster dabei die
    Aufloesung, fuer die es gebaut wurde (gemessen: 24 belegte Zellen -> 21, die
    vier Bar-Pixel auf einen uniformen Wert).

    ★ Bewusst die UMGEKEHRTE Vorrangregel wie ``head_restrictions``: dort geht es
    um eine AUSWAHL, und „auch als Ganzes gewaehlt" heisst „nicht auf Koepfe
    einschraenken" — die groebere Aussage ist die sichere. Hier geht es um den
    Raster-INHALT, und dort ist die groebere Zelle die, die Information wegnimmt.

    Nicht betroffen: Zellwerte, die kein Geraet nennen (bleiben unveraendert), und
    Geraete, die nur in EINER Form vorkommen — ein Raster ohne Ueberschneidung
    kommt unveraendert zurueck."""
    quelle = cells or {}
    mit_koepfen = set()
    for value in quelle.values():
        fid, head = parse_group_cell(value)
        if fid is not None and head is not None:
            mit_koepfen.add(fid)
    if not mit_koepfen:
        return dict(quelle)
    out = {}
    for key, value in quelle.items():
        fid, head = parse_group_cell(value)
        if head is None and fid is not None and fid in mit_koepfen:
            continue                      # Ganz-Zelle weicht den Kopf-Zellen
        out[key] = value
    return out


def base_fids_in_grid_order(positions: dict) -> list[int]:
    """Basis-fids einer ``positions_json``-Map (``{"col,row": fid|"fid:head"}``) in
    **Raster-Reihenfolge** (Zeile, dann Spalte), **dedupliziert**.

    Kopf-Zellen ``"fid:head"`` tragen zum Basis-fid bei (ein Multi-Head-Fixture
    mit N Kopf-Zellen ist EIN Geraet -> erscheint EINMAL). EINE Quelle fuer alle
    Gruppen-fid-Resolver (``app_state``-Kern + Programmer-/EFX-/VC-Views), damit
    Kopf-Matrizen ihre Geraete zeigen statt ``(0)`` (FM16E-HEADCOUNT). Reihenfolge
    ist fuer Fan/Chase relevant (Geraete in Raster-Platzierungsreihenfolge)."""
    items: list[tuple] = []
    for key, value in (positions or {}).items():
        try:
            c_str, r_str = str(key).split(",")
            c, r = int(c_str), int(r_str)
        except (TypeError, ValueError):
            continue
        fid, _head = parse_group_cell(value)
        if fid is not None:
            items.append((r, c, fid))
    items.sort()
    out: list[int] = []
    for _r, _c, fid in items:
        if fid not in out:
            out.append(fid)
    return out


def base_fids_in_cells(cells) -> list[int]:
    """Basis-fids einer BEREITS geordneten Zell-Liste, dedupliziert und in
    Reihenfolge. Gegenstueck zu ``base_fids_in_grid_order`` fuer Aufrufer, die die
    Zellen schon in der Hand haben — so braucht „Geraete UND Koepfe einer Gruppe"
    nur EINE Gruppen-Abfrage statt zweier (der VC-Submaster loest das bei jeder
    Fader-Bewegung auf)."""
    out: list[int] = []
    for c in cells or []:
        fid, _head = parse_group_cell(c)
        if fid is not None and fid not in out:
            out.append(fid)
    return out


def cells_in_grid_order(positions: dict) -> list[str]:
    """Wie ``base_fids_in_grid_order``, aber mit der FEINEN Aufloesung: die
    normalisierten Zellwerte (``"fid"`` bzw. ``"fid:head"``) in Raster-Reihenfolge
    (Zeile, dann Spalte), dedupliziert.

    Fuer Konsumenten, die die Kopf-Information brauchen (VC-Submaster pro Kopf,
    FM-HEADLAYOUT A4) — ``base_fids_in_grid_order`` wirft sie bewusst weg, weil
    ein Multi-Head-Geraet dort EIN Geraet ist."""
    items: list[tuple] = []
    for key, value in (positions or {}).items():
        try:
            c_str, r_str = str(key).split(",")
            c, r = int(c_str), int(r_str)
        except (TypeError, ValueError):
            continue
        fid, head = parse_group_cell(value)
        if fid is not None:
            items.append((r, c, f"{fid}" if head is None else f"{fid}:{head}"))
    items.sort()
    out: list[str] = []
    for _r, _c, cell in items:
        if cell not in out:
            out.append(cell)
    return out
