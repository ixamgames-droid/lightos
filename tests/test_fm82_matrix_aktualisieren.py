"""FM-82 — LED-Matrix-Assistent: „Profil aktualisieren“ zieht die schon
gepatchten Teile nach.

Vorher aenderte der Aktualisieren-Weg nur das Profil: ``pixel_order``,
``element_rotation`` und ``element_flip`` der gepatchten Teile sowie ihre
Auto-Kopf-Gruppen und die Gesamt-Gruppe „… · Matrix“ blieben beim alten
Stand. Geprueft in einer FRISCHEN Test-Bibliothek und einer Wegwerf-Show.

Erwartete Raster sind von HAND abgeleitet (wie in test_fm80), nicht mit
``place_element`` nachgerechnet.
"""
from __future__ import annotations

import json
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication                         # noqa: E402

import pytest                                                       # noqa: E402
from _fixture_quelle import frische_library                         # noqa: E402
from _qt_lifecycle import destroy_all_top_level_widgets             # noqa: E402

from src.core import led_matrix as LM                               # noqa: E402


@pytest.fixture(autouse=True)
def _keine_fenster_uebrig():
    yield
    destroy_all_top_level_widgets(QApplication.instance())


def _app():
    return QApplication.instance() or QApplication([])


class _Basis(unittest.TestCase):

    def setUp(self):
        from src.core.app_state import clear_channel_cache, get_state
        from src.core.show.show_file import reset_show
        from src.core.undo import get_undo_stack
        _app()
        self.eng = frische_library(self)
        clear_channel_cache()
        self.addCleanup(clear_channel_cache)
        reset_show()
        self.addCleanup(reset_show)
        get_undo_stack().clear()
        self.addCleanup(get_undo_stack().clear)
        self.state = get_state()
        # 3x4, Teile à 3 Zeilen -> T1 (3 Zeilen) + T2 (1 Zeile); zeilenweise
        # ab oben links gepatcht.
        from src.core.database import fixture_db as fdb
        self.alt = LM.MatrixAngaben(modell="S", breite_px=3, hoehe_px=4,
                                    zeilen_je_teil=3)
        self.pid = fdb.create_user_profile(LM.profil_payload(self.alt),
                                           engine=self.eng)
        self.f1, self.f2 = LM.matrix_patchen(self.state, self.pid)
        get_undo_stack().clear()

    def _neu(self) -> LM.MatrixAngaben:
        return LM.MatrixAngaben(modell="S", breite_px=3, hoehe_px=4,
                                zeilen_je_teil=3, verdrahtung="schlange",
                                startecke="unten_links")

    def _fx(self):
        return {f.fid: f for f in self.state.get_patched_fixtures()}

    def _lage(self, fid):
        f = self._fx()[fid]
        return (f.pixel_order, int(f.element_rotation or 0), bool(f.element_flip))

    def _gruppen(self):
        from sqlalchemy import select
        from src.core.database.models import FixtureGroup
        with self.state._session() as s:
            return {g.name: (int(g.cols), int(g.rows), json.loads(g.positions_json))
                    for g in s.execute(select(FixtureGroup)).scalars()}

    def _kopfgruppe(self, fid):
        from src.core.database.models import FixtureGroup
        gid = self.state.find_head_matrix_group(fid, dedicated=True)
        with self.state._session() as s:
            g = s.get(FixtureGroup, gid)
            return int(g.cols), int(g.rows), json.loads(g.positions_json)

    def _pruefe_neu(self):
        self.assertEqual(self._lage(self.f1), ("serpentine", 180, True))
        self.assertEqual(self._lage(self.f2), ("serpentine", 180, False),
                         "Teil 2 beginnt auf ungerader Zeile -> Gegenrichtung")
        _c, _r, pos = self._gruppen()["S · Matrix"]
        # Anzeige (Pixel 1-basiert): [[12,11,10],[7,8,9],[6,5,4],[1,2,3]]
        erwartet = {"0,3": (self.f1, 0), "1,3": (self.f1, 1), "2,3": (self.f1, 2),
                    "2,2": (self.f1, 3), "0,2": (self.f1, 5), "0,1": (self.f1, 6),
                    "2,1": (self.f1, 8), "2,0": (self.f2, 0), "0,0": (self.f2, 2)}
        for zelle, (fid, kopf) in erwartet.items():
            self.assertEqual(pos[zelle], f"{fid}:{kopf}", zelle)
        cols, rows, tpos = self._kopfgruppe(self.f1)
        self.assertEqual((cols, rows), (3, 3))
        self.assertEqual(tpos["0,2"], f"{self.f1}:0")
        self.assertEqual(tpos["0,1"], f"{self.f1}:5")

    def _pruefe_alt(self):
        self.assertEqual(self._lage(self.f1), ("rowwise", 0, False))
        self.assertEqual(self._lage(self.f2), ("rowwise", 0, False))
        _c, _r, pos = self._gruppen()["S · Matrix"]
        self.assertEqual(pos["0,0"], f"{self.f1}:0")
        self.assertEqual(pos["0,3"], f"{self.f2}:0")
        _c, _r, tpos = self._kopfgruppe(self.f1)
        self.assertEqual(tpos["0,0"], f"{self.f1}:0")


class KernTest(_Basis):

    def test_vorher_alter_stand(self):
        self._pruefe_alt()

    def test_nachziehen_setzt_teile_und_gruppen(self):
        from src.core.database import fixture_db as fdb
        neu = self._neu()
        fdb.update_user_profile(self.pid, LM.profil_payload(neu), engine=self.eng)
        self.assertEqual(LM.teile_nachziehen(self.state, self.pid, neu), 2)
        self._pruefe_neu()

    def test_ein_rueckgaengig_schritt(self):
        from src.core.undo import get_undo_stack
        neu = self._neu()
        LM.teile_nachziehen(self.state, self.pid, neu)
        st = get_undo_stack()
        self.assertTrue(st.undo())
        self._pruefe_alt()
        self.assertFalse(st.undo(), "alles war EIN Schritt")
        self.assertTrue(st.redo())
        self._pruefe_neu()

    def test_folgen_nennen_nachziehen(self):
        self.assertEqual(LM.teile_nachziehen_folgen(self.state, self.pid, self.alt),
                         [], "unveraenderte Lage -> nichts zu melden")
        zeilen = LM.teile_nachziehen_folgen(self.state, self.pid, self._neu())
        self.assertEqual(len(zeilen), 1)
        self.assertIn("2 gepatchte(r) Teil(e)", zeilen[0])
        self.assertIn("· Matrix", zeilen[0])

    def test_unveraenderte_lage_laesst_eigene_gruppen(self):
        """Pruef-Fund: ohne Lage-Aenderung (nur umbenannt) meldet die
        Rueckfrage nichts — dann darf auch keine Gruppe neu gebaut werden."""
        from src.core.database.models import FixtureGroup
        from src.core.undo import get_undo_stack
        gid = self.state.find_head_matrix_group(self.f1, dedicated=True)
        with self.state._session() as s:
            g = s.get(FixtureGroup, gid)
            pos = json.loads(g.positions_json)
            pos.pop("0,0", None)                 # eigene Aenderung an der Gruppe
            g.positions_json = json.dumps(pos)
            s.commit()
        vorher = self._gruppen()
        umbenannt = LM.MatrixAngaben(modell="S", breite_px=3, hoehe_px=4,
                                     zeilen_je_teil=3, hersteller="Anders")
        self.assertEqual(LM.teile_nachziehen_folgen(
            self.state, self.pid, umbenannt), [])
        self.assertEqual(LM.teile_nachziehen(self.state, self.pid, umbenannt), 0)
        self.assertEqual(self._gruppen(), vorher)
        self.assertFalse(get_undo_stack().undo(), "kein Rueckgaengig-Schritt")

    def test_fremde_geraete_bleiben(self):
        from src.core.database.models import PatchedFixture
        fid = int(self.state.next_fid())
        self.state.add_fixture(PatchedFixture(
            fid=fid, label="Fremd", fixture_profile_id=self.pid,
            mode_name="gibt es nicht", universe=9, address=1, channel_count=3,
            manufacturer_name="", fixture_name="S", fixture_type="matrix"))
        vorher = self._lage(fid)
        LM.teile_nachziehen(self.state, self.pid, self._neu())
        self.assertEqual(self._lage(fid), vorher,
                         "unbekannter Modus -> nicht angefasst")
        self.assertNotEqual(self._lage(fid)[0], "serpentine")


class DialogTest(_Basis):

    def _dialog(self, antwort: bool):
        import src.ui.widgets.led_matrix_assistent as LMA
        self.fragen = []
        echt = LMA._ueberschreiben_fragen
        LMA._ueberschreiben_fragen = (
            lambda *a: self.fragen.append(a) or antwort)
        self.addCleanup(setattr, LMA, "_ueberschreiben_fragen", echt)
        # wie aus Datenbank -> Fixture-Profil bearbeiten: ohne state
        dlg = LMA.LedMatrixAssistent(profil_id=self.pid)
        self.addCleanup(dlg.deleteLater)
        dlg.cb_verdrahtung.setCurrentIndex(dlg.cb_verdrahtung.findData("schlange"))
        dlg.cb_startecke.setCurrentIndex(dlg.cb_startecke.findData("unten_links"))
        return dlg

    def test_aktualisieren_zieht_gepatchte_teile_nach(self):
        dlg = self._dialog(True)
        self.assertTrue(dlg.speichern())
        self.assertEqual(len(self.fragen), 1)
        folgen = self.fragen[0][3]
        self.assertTrue(any("Verdrahtung/Startecke" in z for z in folgen), folgen)
        self._pruefe_neu()
        self.assertIn("2 gepatchte(r) Teil(e) nachgezogen", dlg.gespeichert_meldung)

    def test_nein_laesst_alles(self):
        dlg = self._dialog(False)
        self.assertFalse(dlg.speichern())
        self._pruefe_alt()


if __name__ == "__main__":
    unittest.main()
