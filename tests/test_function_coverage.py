"""Abdeckungs-Rechnung: welche Geraete schreibt eine Funktion?

Entstanden fuer BUG-FBW (David 2026-08-01: „Alles Weiß macht nicht alles
weiß").

Seit Slice 2 deckt „Alles Weiß" selbst alle gepatchten Geraete ab; die Rechnung
hier entscheidet, welche Geraete eine GEBUNDENE Funktion schon bedient — die
laesst der Override dann in Ruhe, damit ein bewusst eingestellter Weiss-Look
erhalten bleibt (``VCButton`` ALL_WHITE → ``AppState.set_all_white``).

**Die Regel, an der alles haengt: im Zweifel ``None``.** Eine geratene Abdeckung
waere schlimmer als gar keine — der Override wuerde dann Geraete auslassen, die
in Wahrheit niemand bedient. ``None`` heisst „nicht bestimmbar", und der
Aufrufer deckt dann sicherheitshalber ALLES ab.
"""
from __future__ import annotations

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from src.core.engine.function_coverage import (coverage_of_bindings,  # noqa: E402
                                               covered_fixture_ids)
from src.core.engine.scene import Scene                             # noqa: E402


class _Sammlung:
    """Minimal-Sammlung — deckt die ``function_ids``-Form ab."""
    def __init__(self, ids):
        self.function_ids = list(ids)


class _Schritt:
    def __init__(self, fid):
        self.function_id = fid


class _Chaser:
    def __init__(self, ids):
        self.steps = [_Schritt(i) for i in ids]


class _Matrix:
    """Ein Effekt, dessen Ziele erst zur Laufzeit entstehen — nicht bestimmbar."""


class RechnungTest(unittest.TestCase):
    """Die Abdeckungs-Rechnung, ohne Qt und ohne AppState."""

    def _szene(self, fids, sid=1) -> Scene:
        sc = Scene("weiss", sid)
        for fid in fids:
            sc.set_value(fid, 1, 255)
        return sc

    def test_szene_nennt_ihre_geraete(self):
        self.assertEqual(covered_fixture_ids(self._szene([3, 7, 3]), lambda _: None),
                         {3, 7})

    def test_leere_szene_deckt_nichts_ab_ist_aber_bestimmbar(self):
        """Wichtige Unterscheidung: leere Menge ≠ ``None``. Eine leere Szene ist
        eine sichere Aussage („deckt nichts ab"), kein Unwissen."""
        self.assertEqual(covered_fixture_ids(self._szene([]), lambda _: None), set())

    def test_sammlung_vereinigt_ihre_mitglieder(self):
        katalog = {1: self._szene([1, 2], 1), 2: self._szene([2, 5], 2)}
        self.assertEqual(
            covered_fixture_ids(_Sammlung([1, 2]), katalog.get), {1, 2, 5})

    def test_chaser_vereinigt_seine_schritte(self):
        katalog = {1: self._szene([4], 1), 2: self._szene([9], 2)}
        self.assertEqual(covered_fixture_ids(_Chaser([1, 2]), katalog.get), {4, 9})

    def test_unbekannter_typ_ist_None_und_nicht_leer(self):
        """Die Regel, an der alles haengt: im Zweifel ``None``. „Leer" wuerde als
        „deckt nichts ab" gelesen und eine falsche Warnung erzeugen."""
        self.assertIsNone(covered_fixture_ids(_Matrix(), lambda _: None))

    def test_ein_unbekanntes_mitglied_macht_die_ganze_sammlung_unbestimmbar(self):
        katalog = {1: self._szene([1], 1), 2: _Matrix()}
        self.assertIsNone(covered_fixture_ids(_Sammlung([1, 2]), katalog.get))

    def test_zyklus_haengt_sich_nicht_auf(self):
        """Sammlung A enthaelt B enthaelt A — ohne Tiefenbegrenzung endlos."""
        katalog = {}
        katalog[1] = _Sammlung([2])
        katalog[2] = _Sammlung([1])
        self.assertIsNone(covered_fixture_ids(katalog[1], katalog.get))

    def test_ohne_bindung_ist_die_abdeckung_leer_nicht_unbekannt(self):
        """Daran haengt „nicht belegt": keine Bindung ist eine sichere Aussage."""
        self.assertEqual(coverage_of_bindings([], lambda _: None), set())


if __name__ == "__main__":
    unittest.main()
