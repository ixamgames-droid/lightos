"""FM-38: Geraet loeschen + Undo (und Hinzufuegen + Undo + Redo) holt die
Kopf-Matrix-Gruppe FELDWEISE zurueck — und sie steuert danach das RICHTIGE Geraet.

Vorher erzeugte das Undo die Werks-Gruppe neu (Name, Raster, Mitglieder weg).
Ein erster Entwurf (07.09., nicht gemergt) stellte die Gruppe VOR dem Geraet
wieder her und hielt ihre alte id — gemessen: nach Loeschen des Geraets mit der
hoechsten fid, einem XML-Import (belegt diese fid) und Ctrl+Z steuerte die
Gruppe des Nutzers das FREMDE Geraet. Darum gilt hier: Ziel pruefen
(``group_fids_by_name``), nicht nur Felder.

Echter Weg: AppState mit Show-DB, add/remove_fixture, echter Undo-Stack. Nur die
Kanal-Aufloesung ist ersetzt (vier RGBW-Baenke = Mehrkopf-Geraet).
"""
from __future__ import annotations

import json
import os
import tempfile
import unittest
from types import SimpleNamespace as NS

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import src.core.app_state as A                                      # noqa: E402
from sqlalchemy import select                                        # noqa: E402
from sqlalchemy.orm import Session                                   # noqa: E402
from src.core.database.models import FixtureGroup, PatchedFixture   # noqa: E402
from src.core.undo import get_undo_stack                             # noqa: E402


def _rgbw_baenke(n):
    chans, num = [], 1
    for _h in range(n):
        for attr in ("color_r", "color_g", "color_b", "color_w"):
            chans.append(NS(attribute=attr, channel_number=num, default_value=0))
            num += 1
    return chans


class _Basis(unittest.TestCase):

    def setUp(self):
        self._orig = A.get_channels_for_patched
        A.get_channels_for_patched = lambda fx: _rgbw_baenke(4)
        self.addCleanup(setattr, A, "get_channels_for_patched", self._orig)
        self.state = A.AppState()
        fd, pfad = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        self.state.open_show(pfad)
        self.stack = get_undo_stack()
        self.stack.clear()
        self.addCleanup(self.stack.clear)
        self.hinweise = []
        self.state.subscribe(lambda ev, d: ev == "hinweis" and self.hinweise.append(d))

    def _patch(self, fid, label, address, undoable=True):
        self.state.add_fixture(PatchedFixture(
            fid=fid, label=label, fixture_profile_id=1, mode_name="Standard",
            universe=1, address=address, channel_count=16,
            fixture_type="moving_head"), undoable=undoable)

    def _gruppen(self):
        with Session(self.state._show_engine) as s:
            return {g.name: (g.cols, g.rows, g.folder)
                    for g in s.execute(select(FixtureGroup)).scalars().all()}

    def _pflegen(self, fid, name, cols=2, rows=2):
        gid = self.state.find_head_matrix_group(fid, dedicated=True)
        self.assertIsNotNone(gid, "VORBEDINGUNG: Auto-Kopf-Gruppe")
        with Session(self.state._show_engine) as s:
            g = s.get(FixtureGroup, gid)
            g.name, g.cols, g.rows = name, cols, rows
            g.positions_json = json.dumps(
                {f"{i % cols},{i // cols}": f"{fid}:{i}" for i in range(4)})
            s.commit()

    def _drei(self):
        for fid, label, addr in ((5, "HydraA", 1), (9, "HydraB", 33), (12, "HydraC", 65)):
            self._patch(fid, label, addr)


class LoeschenUndUndoTest(_Basis):

    def test_gepflegte_gruppe_kommt_zurueck_und_zielt_richtig(self):
        self._drei()
        self._pflegen(9, "Bühne Links")
        self.state.remove_fixture(9, undoable=True)
        self.assertNotIn("Bühne Links", self._gruppen())
        self.stack.undo()
        g = self._gruppen()
        self.assertEqual((2, 2, "Multi-Head"), g.get("Bühne Links"))
        self.assertNotIn("HydraB · Köpfe", g, "keine zweite Werks-Gruppe")
        self.assertEqual([9], self.state.group_fids_by_name("Bühne Links"))

    def test_fremdes_geraet_auf_der_alten_nummer_wird_nicht_gesteuert(self):
        """Der gemessene Regressionsweg des ersten Entwurfs."""
        self._drei()
        self._pflegen(12, "Fronttruss")
        self.state.remove_fixture(12, undoable=True)
        # XML-Import: legt ein Fremdgeraet auf fid 12, OHNE Undo-Eintrag
        self._patch(12, "Fremd", 97, undoable=False)
        self.stack.undo()
        neu = [f.fid for f in self.state.get_patched_fixtures() if f.label == "HydraC"]
        self.assertEqual(1, len(neu))
        self.assertNotEqual(12, neu[0], "fid-Guard hat HydraC umnummeriert")
        self.assertEqual(neu, self.state.group_fids_by_name("Fronttruss"),
                         "die Gruppe des Nutzers steuert HydraC, nicht das Fremdgeraet")
        self.assertNotIn("HydraC · Köpfe", self._gruppen())

    def test_zwei_eigene_gruppen_desselben_geraets(self):
        """Mehr als eine geloeschte Gruppe — daran hingen im ersten Entwurf alle
        sieben ueberlebenden Mutationen ([:1], nur der erste Schnappschuss …)."""
        self._drei()
        self._pflegen(9, "Bühne Links")
        with Session(self.state._show_engine) as s:
            s.add(FixtureGroup(name="Bühne Rechts", cols=4, rows=1, folder="Multi-Head",
                               positions_json=json.dumps(
                                   {f"{i},0": f"9:{3 - i}" for i in range(4)})))
            s.commit()
        self.state.remove_fixture(9, undoable=True)
        self.assertFalse({"Bühne Links", "Bühne Rechts"} & set(self._gruppen()))
        self.stack.undo()
        g = self._gruppen()
        self.assertEqual((2, 2, "Multi-Head"), g.get("Bühne Links"))
        self.assertEqual((4, 1, "Multi-Head"), g.get("Bühne Rechts"))
        self.assertEqual([9], self.state.group_fids_by_name("Bühne Rechts"))

    def test_andere_gruppen_bleiben_unberuehrt(self):
        self._drei()
        vorher = {k: v for k, v in self._gruppen().items() if "HydraB" not in k}
        self.state.remove_fixture(9, undoable=True)
        self.stack.undo()
        nachher = {k: v for k, v in self._gruppen().items() if "HydraB" not in k}
        self.assertEqual(vorher, nachher)

    def test_teilausfall_wird_gemeldet(self):
        self._drei()
        self._pflegen(9, "Bühne Links")
        self.state.remove_fixture(9, undoable=True)
        echt = A.AppState._zellen_umschreiben

        def stolpert(pj, alt, neu):
            raise ValueError("kaputt")
        A.AppState._zellen_umschreiben = staticmethod(stolpert)
        try:
            self.stack.undo()
        finally:
            A.AppState._zellen_umschreiben = staticmethod(echt)
        self.assertTrue(self.hinweise and "Bühne Links" in self.hinweise[0], self.hinweise)


class HinzufuegenUndoRedoTest(_Basis):
    """Der zweite Weg: Ctrl+Z nach dem Patchen, dann Ctrl+Y."""

    def test_redo_bringt_die_gepflegte_gruppe_zurueck(self):
        self._patch(7, "B", 1)
        self._pflegen(7, "Bühne Links")
        self.stack.undo()                       # Patchen rueckgaengig
        self.assertEqual([], self.state.get_patched_fixtures())
        self.stack.redo()
        g = self._gruppen()
        self.assertEqual((2, 2, "Multi-Head"), g.get("Bühne Links"))
        self.assertNotIn("B · Köpfe", g)
        self.assertEqual([7], self.state.group_fids_by_name("Bühne Links"))


class ScanTest(_Basis):
    """Nebenfund: EINE Gruppe mit Listen-``positions_json`` liess den Scan werfen
    — danach bekam KEIN neu gepatchtes Mehrkopf-Geraet mehr eine Kopf-Gruppe."""

    def test_kaputte_fremdgruppe_blockiert_keine_kopfgruppe(self):
        with Session(self.state._show_engine) as s:
            s.add(FixtureGroup(name="Alt", cols=3, rows=1, folder="",
                               positions_json="[1, 2, 3]"))
            s.commit()
        self._patch(9, "HydraB", 33)
        self.assertIsNotNone(self.state.find_head_matrix_group(9, dedicated=True))


if __name__ == "__main__":
    unittest.main()
