"""FM-51 (Gruppe „views"): reine Weiss-Auswahl ist NICHT „nichts gewaehlt".

Ein Geraet, das nur ueber Weiss-Zellen (``"1:w3"``) gewaehlt ist, steht bewusst
nicht in ``selected_fids``. Mehrere Ansichten deuteten die dann leere fid-Liste
als „nichts gewaehlt" und fielen zurueck:

* Preset-Browser: ``apply_to_programmer(None)`` -> Palette auf dem GANZEN Rig.
* Paletten-Seite: sicher (Abbruch), aber Meldung „Keine Geräte ausgewählt".
* RGB-Matrix ``_auto_assign``: ganzer Patch ins Raster (Balken als ganzes Geraet).
* RGB-Matrix ``_assign_from_selection``: sicher, aber falsche Meldung.
* EFX ``_add_fixture``: erstes gepatchtes Geraet hinzugefuegt.
* EFX Auto-Zuweisung: alle Movingheads.
* Effekt-Assistent: alle Geraete vorab angehakt.

Soll: diese Werkzeuge bedienen die Weiss-Achse nicht und tun bei reiner
Weiss-Auswahl NICHTS (mit Hinweis). Der alte Rueckfall gilt nur noch bei
wirklich leerer Auswahl. Je Stelle eine Positivkontrolle.

Echter Weg: eingebaute Profile, echter AppState, echter Programmer.
"""
import copy
import os
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication                         # noqa: E402
from sqlalchemy import select                                       # noqa: E402
from sqlalchemy.orm import Session                                  # noqa: E402

from src.core.app_state import get_state                            # noqa: E402
from src.core.database.fixture_db import engine, ensure_builtins    # noqa: E402
from src.core.database.models import FixtureProfile, PatchedFixture  # noqa: E402
from src.core.show.show_file import reset_show                      # noqa: E402

_app = QApplication.instance() or QApplication([])
BALKEN_MODUS = "154-Kanal 48 Zonen RGB + 8x Weiss"


def _pid(short):
    with Session(engine()) as s:
        return s.execute(select(FixtureProfile.id).where(
            FixtureProfile.short_name == short)).scalars().first()


class _Basis(unittest.TestCase):
    MIT_MOVER = False

    @classmethod
    def setUpClass(cls):
        ensure_builtins()

    def setUp(self):
        reset_show()
        self.st = get_state()
        self.st.add_fixture(PatchedFixture(
            fid=1, label="Balken", fixture_profile_id=_pid("ZQ06121"),
            mode_name=BALKEN_MODUS, universe=1, address=1, channel_count=154,
            fixture_type="matrix"), undoable=False)
        self.st.add_fixture(PatchedFixture(
            fid=2, label="PAR", fixture_profile_id=_pid("ZQ01424"),
            mode_name="8-Kanal RGBW", universe=1, address=200, channel_count=8,
            fixture_type="par"), undoable=False)
        if self.MIT_MOVER:
            self.st.add_fixture(PatchedFixture(
                fid=3, label="Sharpy", fixture_profile_id=_pid("SHARPY"),
                mode_name="16-Kanal (Standard)", universe=1, address=300,
                channel_count=16, fixture_type="moving_head"), undoable=False)
        self.addCleanup(self.st.set_selected_cells, [])
        self.addCleanup(self.st.clear_programmer)

    def _nur_weiss(self):
        self.st.set_selected_cells(["1:w3"])
        self.assertEqual(self.st.get_selected_fids(), [])
        self.assertFalse(self.st.auswahl_ist_leer())

    def _leer(self):
        self.st.set_selected_cells([])
        self.assertTrue(self.st.auswahl_ist_leer())

    def _prog(self):
        return copy.deepcopy({k: dict(v) for k, v in self.st.programmer.items()})

    def _widget(self, cls, *a, **kw):
        w = cls(*a, **kw)
        self.addCleanup(w.deleteLater)
        return w


# ── Preset-Browser ────────────────────────────────────────────────────────────

class PresetBrowserTest(_Basis):

    def setUp(self):
        super().setUp()
        from src.core.engine.palette import (
            Palette, PaletteType, get_palette_manager)
        self.pm = get_palette_manager()
        self.pal = Palette(name="FM51Rot", type=PaletteType.COLOR,
                           values={"color_r": 255, "color_g": 0, "color_b": 0})
        self.pm.add(self.pal)
        self.addCleanup(lambda: self.pal in self.pm.get_all()
                        and self.pm.remove(self.pal))
        from src.ui.views.preset_browser_view import PresetBrowserView
        self.v = self._widget(PresetBrowserView)
        self.v._reload_entries()
        self.v._search.setText("FM51Rot")
        self.assertGreater(self.v._list.count(), 0)

    def test_nur_weiss_wendet_nichts_an(self):
        self._nur_weiss()
        vorher = self._prog()
        self.v._apply_first()
        self.assertEqual(self._prog(), vorher,
                         "Palette darf bei reiner Weiss-Auswahl nichts schreiben")
        self.assertIn("Weiß-Segmente", self.v._status.text())

    def test_target_fids_nie_none_bei_auswahl(self):
        self._nur_weiss()
        self.assertEqual(self.v._target_fids(), [])

    def test_leere_auswahl_wie_bisher_ganzes_rig(self):
        self._leer()
        self.assertIsNone(self.v._target_fids())
        self.v._apply_first()
        self.assertEqual(self.st.programmer.get(2, {}).get("color_r"), 255)
        self.assertIn("Palette angewendet", self.v._status.text())

    def test_ganzes_geraet_nur_dieses(self):
        self.st.set_selected_cells(["2"])
        self.assertEqual(self.v._target_fids(), [2])
        self.v._apply_first()
        self.assertEqual(self.st.programmer.get(2, {}).get("color_r"), 255)
        self.assertNotIn(1, self.st.programmer)


# ── Paletten-Seite ────────────────────────────────────────────────────────────

class PalettePageTest(_Basis):

    def setUp(self):
        super().setUp()
        from src.core.engine.palette import (
            Palette, PaletteType, get_palette_manager)
        from src.ui.views.palette_view import PalettePage
        self.pal = Palette(name="FM51Rot", type=PaletteType.COLOR,
                           values={"color_r": 255})
        self.page = self._widget(PalettePage, PaletteType.COLOR,
                                 get_palette_manager())

    def _apply_mit_meldung(self):
        with mock.patch("src.ui.views.palette_view.QMessageBox.information") as m:
            self.page._apply(self.pal)
        return m

    def test_nur_weiss_meldung(self):
        self._nur_weiss()
        vorher = self._prog()
        m = self._apply_mit_meldung()
        self.assertEqual(self._prog(), vorher)
        self.assertEqual(m.call_count, 1)
        text = m.call_args[0][2]
        self.assertIn("Weiß-Segmente", text)
        self.assertNotIn("Keine Geräte", text)

    def test_leer_meldung_wie_bisher(self):
        self._leer()
        m = self._apply_mit_meldung()
        self.assertEqual(m.call_count, 1)
        self.assertIn("Keine Geräte ausgewählt", m.call_args[0][2])
        self.assertEqual(self.st.programmer, {})

    def test_ganzes_geraet_wendet_an(self):
        self.st.set_selected_cells(["2"])
        m = self._apply_mit_meldung()
        self.assertEqual(m.call_count, 0)
        self.assertEqual(self.st.programmer.get(2, {}).get("color_r"), 255)

    # Review FM-51 A: Aufzeichnen/Ueberschreiben deutete reine Weiss-Auswahl als
    # "ganzer Programmer" (record_from_programmer(None)).
    def _programmer_fuellen(self):
        self.st.set_programmer_value(2, "color_r", 77)
        self.st.set_programmer_value(1, "color_r", 55)

    def test_ueberschreiben_nur_weiss_schreibt_nichts(self):
        self._programmer_fuellen()
        self._nur_weiss()
        with mock.patch("src.ui.views.palette_view.QMessageBox.information") as m:
            self.page._overwrite(self.pal)
        self.assertEqual(self.pal.values, {"color_r": 255})
        self.assertEqual(m.call_count, 1)
        self.assertIn("Weiß-Segmente", m.call_args[0][2])

    def test_aufzeichnen_nur_weiss_fragt_nicht_nach_namen(self):
        self._programmer_fuellen()
        self._nur_weiss()
        with mock.patch("src.ui.views.palette_view.QMessageBox.information") as m, \
                mock.patch("src.ui.views.palette_view.QInputDialog.getText") as g:
            self.page._record_new()
        self.assertEqual(g.call_count, 0)
        self.assertEqual(m.call_count, 1)

    def test_ueberschreiben_ganzes_geraet_wie_bisher(self):
        self._programmer_fuellen()
        self.st.set_selected_cells(["2"])
        with mock.patch("src.ui.views.palette_view.QMessageBox.information") as m:
            self.page._overwrite(self.pal)
        self.assertEqual(m.call_count, 0)
        self.assertEqual(self.pal.values.get("color_r"), 77)


# ── RGB-Matrix ────────────────────────────────────────────────────────────────

class RgbMatrixTest(_Basis):

    def setUp(self):
        super().setUp()
        from src.core.engine.function_manager import get_function_manager
        from src.ui.views.rgb_matrix_view import RgbMatrixView
        self.fm = get_function_manager()
        pre = {f.id for f in self.fm.all()}

        def _aufraeumen():
            for f in list(self.fm.all()):
                if f.id not in pre:
                    self.fm.remove(f.id)
        self.addCleanup(_aufraeumen)
        self.v = self._widget(RgbMatrixView)
        self.v._add()
        self.assertIsNotNone(self.v._current)
        self.v._current.fixture_grid = []

    def test_auto_assign_nur_weiss_kein_raster(self):
        self._nur_weiss()
        self.v._auto_assign()
        self.assertEqual(self.v._current.fixture_grid, [])
        self.assertIn("Weiß-Segmente", self.v._grid_label.text())

    def test_auto_assign_leer_ohne_patch_meldung(self):
        # Review FM-51 A: leere Auswahl + nichts gepatcht ist kein Weiss-Fall.
        self._leer()
        with mock.patch.object(self.st, "auswahl_ziel_fids", return_value=[]):
            self.v._auto_assign()
        self.assertEqual(self.v._current.fixture_grid, [])
        self.assertIn("Keine Geräte gepatcht", self.v._grid_label.text())

    def test_auto_assign_leer_ganzer_patch(self):
        self._leer()
        self.v._auto_assign()
        grid = self.v._current.fixture_grid
        self.assertTrue(grid)
        self.assertEqual(set(grid), {1, 2})

    def test_auto_assign_ganzes_geraet(self):
        self.st.set_selected_cells(["2"])
        self.v._auto_assign()
        self.assertEqual(set(self.v._current.fixture_grid), {2})

    def test_assign_from_selection_nur_weiss_meldung(self):
        self._nur_weiss()
        self.v._assign_from_selection()
        self.assertEqual(self.v._current.fixture_grid, [])
        text = self.v._grid_label.text()
        self.assertIn("Weiß-Segmente", text)
        self.assertNotIn("Keine Geräte", text)

    def test_assign_from_selection_leer_meldung_wie_bisher(self):
        self._leer()
        self.v._assign_from_selection()
        self.assertEqual(self.v._grid_label.text(),
                         "Keine Geräte im Programmer ausgewählt.")

    def test_assign_from_selection_ganzes_geraet(self):
        self.st.set_selected_cells(["2"])
        self.v._assign_from_selection()
        self.assertEqual(self.v._current.fixture_grid, [2])


# ── EFX ───────────────────────────────────────────────────────────────────────

class EfxTest(_Basis):
    MIT_MOVER = True

    def setUp(self):
        super().setUp()
        from src.ui.views.efx_view import EfxView
        self.v = self._widget(EfxView)          # Standalone (allow_all)
        pre = {f.id for f in self.v._instances}

        def _aufraeumen():
            for inst in list(self.v._instances):
                if inst.id not in pre:
                    try:
                        self.v._fm.remove(inst.id)
                    except Exception:
                        pass
        self.addCleanup(_aufraeumen)
        p = mock.patch("src.ui.views.efx_view.QMessageBox.warning")
        p.start()
        self.addCleanup(p.stop)

    def _fids(self):
        return [t.fid for t in self.v._current.fixtures]

    def test_neue_efx_nur_weiss_bleibt_leer(self):
        self._nur_weiss()
        self.v._add_efx()
        self.assertEqual(self.v._current.fixtures, [])

    def test_start_nur_weiss_bleibt_leer(self):
        self._nur_weiss()
        self.v._add_efx()
        self.v._start_efx()
        self.assertEqual(self.v._current.fixtures, [])
        self.assertIn("Weiß-Segmente", self.v._fx_box.title())

    def test_neue_efx_leer_alle_mover(self):
        self._leer()
        self.v._add_efx()
        self.assertEqual(self._fids(), [3])

    def test_neue_efx_ganzes_nicht_mover_geraet_wie_bisher(self):
        """Ganzes Geraet ohne Pan/Tilt gewaehlt (auch neben Weiss-Zellen):
        bisheriger Rueckfall auf alle Mover bleibt."""
        for zellen in (["2"], ["1:w3", "2"]):
            self.st.set_selected_cells(zellen)
            self.v._add_efx()
            self.assertEqual(self._fids(), [3], zellen)

    def test_add_fixture_nur_weiss_fuegt_nichts_hinzu(self):
        self._nur_weiss()
        self.v._add_efx()
        self.assertEqual(self.v._current.fixtures, [])
        self.v._add_fixture()
        self.assertEqual(self.v._current.fixtures, [])

    def test_add_fixture_leer_erstes_geraet(self):
        self._leer()
        self.v._add_efx()
        self.v._current.fixtures = []
        self.v._add_fixture()
        self.assertEqual(self._fids(), [1])

    def test_add_fixture_ganzes_geraet(self):
        self.st.set_selected_cells(["3"])
        self.v._add_efx()
        self.v._current.fixtures = []
        self.v._add_fixture()
        self.assertEqual(self._fids(), [3])


# ── Effekt-Assistent ──────────────────────────────────────────────────────────

class EffectWizardTest(_Basis):

    def _page(self):
        from src.ui.widgets.effect_wizard import _FixturePage
        return self._widget(_FixturePage)

    def test_nur_weiss_nichts_vorgehakt(self):
        self._nur_weiss()
        page = self._page()
        self.assertEqual(len(page.checks), 2)
        self.assertEqual([cb.fid for cb in page.checks if cb.isChecked()], [])
        self.assertIsNotNone(getattr(page, "_weiss_hinweis", None))

    def test_leer_alle_vorgehakt(self):
        self._leer()
        page = self._page()
        self.assertEqual(sorted(cb.fid for cb in page.checks if cb.isChecked()),
                         [1, 2])
        self.assertIsNone(getattr(page, "_weiss_hinweis", None))

    def test_ganzes_geraet_nur_dieses(self):
        self.st.set_selected_cells(["2"])
        page = self._page()
        self.assertEqual([cb.fid for cb in page.checks if cb.isChecked()], [2])


if __name__ == "__main__":
    unittest.main()
