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
            return int(fid_s), int(head_s)
        return int(s), None
    except Exception:
        return None, None


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
