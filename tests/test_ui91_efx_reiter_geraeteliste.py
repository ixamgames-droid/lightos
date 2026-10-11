"""UI-91: Der EFX-/Matrix-Reiter im Programmer aendert keine gespeicherte
Geraeteliste von selbst.

Befund aus dem Bedientest QA-96 (Schritt C16): Demo-Show oeffnen, im Programmer
zwei Moving Heads waehlen, Reiter „EFX" oeffnen, KEINEN Effekt anklicken — der
Editor waehlte Zeile 1 und schrieb deren Geraeteliste auf die Auswahl um
(20 Geraete -> 2). Die Show galt als geaendert; wer speicherte, hatte sie still
veraendert. UI-84 hatte nur das LADEN abgesichert.

Regel seit UI-91: Ein gespeicherter Effekt aendert seine Geraete nur durch eine
ausdrueckliche Handlung an diesem Effekt („Auswahl übernehmen"). Der Auswahl
folgt nur ein in diesem Editor NEU angelegter Effekt — der EFX-Entwurf bis zum
Speichern, die neue Matrix bis zum Speichern, Zeilenwechsel oder Verlassen des
Reiters.
"""
import os
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.core.app_state import get_state
from src.core.database.fixture_db import engine as fdb_engine, ensure_builtins
from src.core.database.models import PatchedFixture, FixtureProfile
from src.core.engine.efx import EfxFixture
from src.core.show import show_file as SF

from _qt_lifecycle import destroy_all_top_level_widgets  # XPLAT-15

_REPO = Path(__file__).resolve().parent.parent
_MH = (31, 32, 33, 34)


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def _keine_uebrigen_fenster():
    yield
    destroy_all_top_level_widgets(QApplication.instance())


def _efx_fids(fn) -> list:
    return [int(f.fid) for f in fn.fixtures]


def _pump(n=4):
    for _ in range(n):
        _app().processEvents()


class ReiterOeffnenImHauptfensterTest(unittest.TestCase):
    """Der Ablauf des Befunds im echten MainWindow (offscreen, gezeigt)."""

    def _baue_show(self) -> str:
        ensure_builtins()
        SF.reset_show()
        state = get_state()
        with Session(fdb_engine()) as s:
            p = s.execute(select(FixtureProfile).where(
                FixtureProfile.short_name == "ZQ02001")).scalar_one()
            pid, hst, name = int(p.id), p.manufacturer.name, p.name
        for i, fid in enumerate(_MH):
            state.add_fixture(PatchedFixture(
                fid=fid, label=f"MH {fid}", fixture_profile_id=pid,
                mode_name="11-Kanal", universe=1, address=1 + 20 * i,
                channel_count=11, manufacturer_name=hst, fixture_name=name,
                fixture_type="moving_head"), undoable=False)
        fm = state.function_manager
        welle = fm.new_efx("MH Pan-Welle")
        welle.fixtures = [EfxFixture(fid=f) for f in _MH]
        kreis = fm.new_efx("MH Kreis")
        kreis.fixtures = [EfxFixture(fid=33), EfxFixture(fid=34)]
        matrix = fm.new_rgb_matrix(name="MH Lauflicht")
        matrix.cols, matrix.rows = 4, 1
        matrix.fixture_grid = list(_MH)
        for f in (welle, kreis):
            f.committed = True
        pfad = os.path.join(tempfile.gettempdir(),
                            f"ui91_{uuid.uuid4().hex}.lshow")
        SF.save_show(pfad)
        self.addCleanup(lambda: os.path.exists(pfad) and os.remove(pfad))
        return pfad

    def _fenster_mit_show(self):
        _app()
        from src.ui import main_window as mw
        pfad = self._baue_show()
        SF.reset_show()
        win = mw.MainWindow()
        win.show()
        self.addCleanup(win.close)
        warnungen = []
        with mock.patch.object(mw.QMessageBox, "warning",
                               lambda *a, **k: warnungen.append(a[1:])):
            win._open_show_path(pfad)
        self.assertEqual([], warnungen, "Show nicht sauber geladen")
        _pump(6)
        self.assertFalse(get_state().laedt_show(), "Lade-Nachlauf endet nicht")
        pv = win._programmer_view
        idx = win._stack.indexOf(pv.parentWidget().parentWidget())
        self.assertGreaterEqual(idx, 0)
        win._switch_section(idx)
        _pump()
        return win, pv

    def _fn(self, name):
        return next(f for f in get_state().function_manager.all()
                    if f.name == name)

    def test_efx_reiter_oeffnen_aendert_nichts(self):
        win, pv = self._fenster_mit_show()
        state = get_state()
        self.assertFalse(win._has_unsaved_changes(), "schon vor dem Reiter geaendert")
        state.set_selected_fids([31, 32])
        _pump()
        pv._main_tabs.setCurrentIndex(pv._efx_tab_index)
        _pump()
        efx = pv._embedded_efx
        self.assertTrue(efx.isVisible(), "EFX-Editor im Test nicht sichtbar")
        # Der Editor zeigt Zeile 1 an — ohne dass jemand sie angeklickt hat.
        self.assertIs(self._fn("MH Pan-Welle"), efx._current)
        self.assertEqual(list(_MH), _efx_fids(self._fn("MH Pan-Welle")),
                         "Reiter oeffnen hat die Geraeteliste umgeschrieben")
        self.assertEqual([33, 34], _efx_fids(self._fn("MH Kreis")))
        self.assertFalse(win._has_unsaved_changes(),
                         "Reiter oeffnen macht die Show 'geaendert'")
        # Die Anzeige nennt die gespeicherten Geraete und die Abweichung.
        self.assertEqual(4, efx._fx_list.count())
        self.assertIn("weicht ab", efx._fx_box.title())
        self.assertFalse(efx._btn_fx_take.isHidden())
        self.assertTrue(efx._btn_fx_take.isEnabled())

        # Auswahlwechsel bei offenem Reiter: bestehende EFX bleiben.
        state.set_selected_fids([33])
        _pump()
        state.set_selected_fids([])
        _pump()
        state.set_selected_fids([31, 32])
        _pump()
        self.assertEqual(list(_MH), _efx_fids(self._fn("MH Pan-Welle")))
        self.assertEqual([33, 34], _efx_fids(self._fn("MH Kreis")))
        # Einen anderen Effekt nur ansehen (Klick in die Liste) bindet ihn nicht.
        zeile = next(i for i, e in enumerate(efx._visible_instances())
                     if e.name == "MH Kreis")
        efx._list.setCurrentRow(zeile)
        _pump()
        self.assertIs(self._fn("MH Kreis"), efx._current)
        self.assertEqual([33, 34], _efx_fids(self._fn("MH Kreis")))
        # Reiter verlassen und wiederkommen aendert ebenfalls nichts.
        pv._main_tabs.setCurrentIndex(0)
        _pump()
        pv._main_tabs.setCurrentIndex(pv._efx_tab_index)
        _pump()
        self.assertEqual(list(_MH), _efx_fids(self._fn("MH Pan-Welle")))
        self.assertEqual([33, 34], _efx_fids(self._fn("MH Kreis")))
        self.assertFalse(win._has_unsaved_changes())

    def test_auswahl_uebernehmen_ist_die_ausdrueckliche_handlung(self):
        win, pv = self._fenster_mit_show()
        state = get_state()
        state.set_selected_fids([31, 32])
        _pump()
        pv._main_tabs.setCurrentIndex(pv._efx_tab_index)
        _pump()
        efx = pv._embedded_efx
        self.assertIs(self._fn("MH Pan-Welle"), efx._current)
        efx._btn_fx_take.click()
        _pump()
        self.assertEqual([31, 32], _efx_fids(self._fn("MH Pan-Welle")))
        self.assertEqual([33, 34], _efx_fids(self._fn("MH Kreis")))
        self.assertNotIn("weicht ab", efx._fx_box.title())
        self.assertFalse(efx._btn_fx_take.isEnabled(),
                         "nichts mehr zu uebernehmen")
        self.assertTrue(win._has_unsaved_changes(),
                        "ausdrueckliches Zuweisen ist eine Aenderung")
        # Danach folgt der gespeicherte EFX wieder NICHT von selbst.
        state.set_selected_fids([34])
        _pump()
        self.assertEqual([31, 32], _efx_fids(self._fn("MH Pan-Welle")))

    def test_neuer_efx_nimmt_die_auswahl_und_folgt_bis_zum_speichern(self):
        win, pv = self._fenster_mit_show()
        state = get_state()
        state.set_selected_fids([31, 32])
        _pump()
        pv._main_tabs.setCurrentIndex(pv._efx_tab_index)
        _pump()
        efx = pv._embedded_efx
        vorher = {f.id for f in state.function_manager.all()}
        efx._add_efx()                      # „+ Neu"
        _pump()
        neu = [f for f in state.function_manager.all() if f.id not in vorher]
        self.assertEqual(1, len(neu))
        self.assertIs(neu[0], efx._current)
        self.assertEqual([31, 32], _efx_fids(neu[0]),
                         "neuer EFX nimmt die aktuelle Auswahl")
        self.assertIn("folgen der Auswahl", efx._fx_box.title())
        # Der Entwurf folgt der Auswahl weiter ...
        state.set_selected_fids([32, 33, 34])
        _pump()
        self.assertEqual([32, 33, 34], _efx_fids(neu[0]))
        # ... bis er gespeichert ist.
        efx._save_efx()
        _pump()
        self.assertIs(neu[0], efx._current)
        state.set_selected_fids([31])
        _pump()
        self.assertEqual([32, 33, 34], _efx_fids(neu[0]),
                         "gespeicherter EFX folgt nicht mehr")
        self.assertEqual(list(_MH), _efx_fids(self._fn("MH Pan-Welle")))
        self.assertEqual([33, 34], _efx_fids(self._fn("MH Kreis")))

    def test_matrix_reiter_oeffnen_aendert_nichts(self):
        win, pv = self._fenster_mit_show()
        state = get_state()
        state.set_selected_fids([31, 32])
        _pump()
        pv._main_tabs.setCurrentIndex(pv._matrix_tab_index)
        _pump()
        rgb = pv._embedded_rgb
        self.assertTrue(rgb.isVisible(), "Matrix-Editor im Test nicht sichtbar")
        m = self._fn("MH Lauflicht")
        self.assertIs(m, rgb._saved)
        self.assertEqual(list(_MH), list(m.fixture_grid),
                         "Reiter oeffnen hat das Raster umgeschrieben")
        self.assertEqual((4, 1), (m.cols, m.rows))
        state.set_selected_fids([33])
        _pump()
        self.assertEqual(list(_MH), list(m.fixture_grid))
        self.assertFalse(win._has_unsaved_changes())
        self.assertIn("weicht", rgb._grid_label.text())
        # Ausdruecklich uebernehmen.
        self.assertFalse(rgb._btn_from_sel.isHidden())
        rgb._btn_from_sel.click()
        _pump()
        self.assertEqual([33], list(m.fixture_grid))
        self.assertTrue(win._has_unsaved_changes())


class MatrixFolgeEditorTest(unittest.TestCase):
    """Matrix-Editor im Folgemodus, direkt als View (sichtbar)."""

    def setUp(self):
        _app()
        from src.core.engine.function_manager import get_function_manager
        from src.ui.views.rgb_matrix_view import RgbMatrixView
        SF.reset_show()          # keine Matrizen aus anderen Tests in der Liste
        self._sel = []
        st = get_state()
        for name, wert in (("get_selected_group_id", lambda: None),
                           ("get_selected_fids", lambda: list(self._sel))):
            p = mock.patch.object(st, name, wert)
            p.start()
            self.addCleanup(p.stop)
        self.fm = get_function_manager()
        self.alt = self.fm.new_rgb_matrix(name="UI91-Alt")
        self.alt.cols, self.alt.rows = 3, 1
        self.alt.fixture_grid = [10, 20, 30]
        self._neu = []
        self.addCleanup(lambda: [self.fm.remove(f.id)
                                 for f in [self.alt] + self._neu])
        self._sel = [7, 8]
        self.view = RgbMatrixView(follow_selection=True)

    def _sync(self):
        from src.core.sync import get_sync, SyncEvent
        get_sync().emit(SyncEvent.SELECTION_CHANGED, None)

    def test_zeigen_und_auswahlwechsel_lassen_das_raster_stehen(self):
        self.view.show()
        _pump()
        self.assertIs(self.alt, self.view._saved)
        self.assertEqual([10, 20, 30], self.alt.fixture_grid)
        self._sel = [1]
        self._sync()
        self.view._on_group_changed()
        self.view.hide()
        self.view.show()
        _pump()
        self.assertEqual([10, 20, 30], self.alt.fixture_grid)
        self.assertEqual(3, self.alt.cols)
        self.assertEqual("", self.view._dirty_lbl.text())

    def test_aus_auswahl_knopf_uebernimmt(self):
        self.view.show()
        _pump()
        self.assertFalse(self.view._btn_from_sel.isHidden())
        self.view._btn_from_sel.click()
        self.assertEqual([7, 8], self.alt.fixture_grid)
        self.assertEqual((2, 1), (self.alt.cols, self.alt.rows))

    def test_neue_matrix_nimmt_die_auswahl_und_folgt_bis_zum_verlassen(self):
        self.view.show()
        _pump()
        vorher = {f.id for f in self.fm.all()}
        self.view._add()
        self._neu = [f for f in self.fm.all() if f.id not in vorher]
        self.assertEqual(1, len(self._neu))
        neu = self._neu[0]
        self.assertIs(neu, self.view._saved)
        self.assertEqual([7, 8], neu.fixture_grid)
        self._sel = [7, 8, 9]
        self._sync()
        self.assertEqual([7, 8, 9], neu.fixture_grid,
                         "frisch angelegte Matrix folgt der Auswahl")
        self.assertEqual([10, 20, 30], self.alt.fixture_grid)
        # Reiter verlassen beendet das Folgen.
        self.view.hide()
        self._sel = [1]
        self.view.show()
        _pump()
        self._sync()
        self.assertEqual([7, 8, 9], neu.fixture_grid)
        self.assertEqual([10, 20, 30], self.alt.fixture_grid)


# ── Doku nennt die Regel ─────────────────────────────────────────────────────

@pytest.mark.parametrize("pfad", [
    "docs/anleitung_efx/ANLEITUNG_EFX.md",
    "docs/anleitung_buehnen_show/ANLEITUNG.md",
    "docs/EFFEKTE.md",
    "docs/anleitung_komplettshow_2026/05_matrix_dimmer/ANLEITUNG.md",
    "docs/anleitung_vc_widgets/19_matrix_editor.md",
])
def test_doku_nennt_auswahl_uebernehmen(pfad):
    text = (_REPO / pfad).read_text(encoding="utf-8")
    assert "Auswahl übernehmen" in text, pfad


def test_doku_verspricht_kein_stilles_umbinden_mehr():
    text = (_REPO / "docs/anleitung_buehnen_show/ANLEITUNG.md").read_text(
        encoding="utf-8")
    assert "auch einen schon gespeicherten" not in text
    efx = (_REPO / "docs/anleitung_efx/ANLEITUNG_EFX.md").read_text(
        encoding="utf-8")
    assert "übernimmt sofort die aktuelle Auswahl" not in efx


if __name__ == "__main__":
    unittest.main()
