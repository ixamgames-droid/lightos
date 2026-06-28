"""Phase 3+4 des VC Smart-Build-Umbaus (Qt offscreen, headless):

  - VCDropPanel: Checkbox-Mehrfachauswahl -> Liste von SmartDropResults (Logik
    ueber ``results()`` testbar, ohne exec). Intelligente Aspekt-Zeilen je
    Effekttyp.
  - VCWidgetGallery: grafische Widget-Auswahl -> ``selected()``.
  - VCConflictCard: Ersetzen/Dazu koppeln/Neues Widget -> ``resolution()``.
"""
import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from src.core.engine.function_manager import get_function_manager
from src.core.engine.rgb_matrix import RgbMatrixInstance, RgbAlgorithm, MatrixStyle
from src.core.engine.efx import EfxInstance
from src.core.engine.scene import Scene

from src.ui.virtualconsole.vc_effect_meta import ControlKind
from src.ui.virtualconsole.vc_drop_panel import VCDropPanel
from src.ui.virtualconsole.vc_widget_gallery import VCWidgetGallery, widget_preview_pixmap
from src.ui.virtualconsole.vc_conflict_card import VCConflictCard


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def _matrix(name="dp-matrix") -> RgbMatrixInstance:
    return RgbMatrixInstance(name=name, cols=4, rows=1,
                             algorithm=RgbAlgorithm.CHASE, fixture_grid=[1, 2, 3, 4])


def _row(panel, kind):
    return next((r for r in panel._rows if r.option.kind == kind), None)


def _kinds(panel):
    return {r.option.kind for r in panel._rows}


# ── VCDropPanel ──────────────────────────────────────────────────────────────

class DropPanelTest(unittest.TestCase):

    def setUp(self):
        _app()
        self.fm = get_function_manager()
        self.fm.stop_all()
        self.m = _matrix()
        self.fm.add(self.m)
        self.efx = EfxInstance("dp-efx")
        self.fm.add(self.efx)
        self.sc = Scene("dp-scene")
        self.fm.add(self.sc)

    def tearDown(self):
        self.fm.stop_all()
        for f in (self.m, self.efx, self.sc):
            self.fm.remove(f.id)

    def _panel(self, function_id):
        panel = VCDropPanel(function_id)
        self.addCleanup(panel.deleteLater)
        return panel

    def test_default_is_single_toggle_button(self):
        panel = self._panel(self.m.id)
        res = panel.results()
        self.assertEqual(len(res), 1)
        from src.ui.virtualconsole.vc_button import ButtonAction
        self.assertEqual(res[0].widget_type, "VCButton")
        self.assertEqual(res[0].action, ButtonAction.FUNCTION_TOGGLE)

    def test_multi_select_creates_one_result_per_aspect(self):
        panel = self._panel(self.m.id)
        _row(panel, ControlKind.TOGGLE).check.setChecked(False)
        _row(panel, ControlKind.TEMPO).check.setChecked(True)
        _row(panel, ControlKind.COLORS).check.setChecked(True)
        types = {r.widget_type for r in panel.results()}
        self.assertEqual(types, {"VCSpeedDial", "VCEffectColors"})

    def test_tempo_default_is_speeddial_with_alternatives(self):
        panel = self._panel(self.m.id)
        row = _row(panel, ControlKind.TEMPO)
        self.assertEqual(row.widget_type, "VCSpeedDial")   # Default
        self.assertIn("VCSlider", row.choices)             # Galerie-Alternative
        self.assertTrue(row.btn.isEnabled())               # „ändern" anbietbar

    def test_dimmer_matrix_has_no_colors_row(self):
        self.m.style = MatrixStyle.DIMMER
        panel = self._panel(self.m.id)
        self.assertNotIn(ControlKind.COLORS, _kinds(panel))
        self.assertIn(ControlKind.TEMPO, _kinds(panel))

    def test_efx_has_movement_row(self):
        panel = self._panel(self.efx.id)
        self.assertIn(ControlKind.MOVEMENT, _kinds(panel))
        self.assertEqual(_row(panel, ControlKind.MOVEMENT).widget_type, "VCXYPad")

    def test_scene_only_toggle_and_flash(self):
        panel = self._panel(self.sc.id)
        self.assertEqual(_kinds(panel), {ControlKind.TOGGLE, ControlKind.FLASH})

    def test_nothing_checked_yields_empty(self):
        panel = self._panel(self.m.id)
        for r in panel._rows:
            r.check.setChecked(False)
        self.assertEqual(panel.results(), [])


# ── VCWidgetGallery ──────────────────────────────────────────────────────────

class WidgetGalleryTest(unittest.TestCase):

    def setUp(self):
        _app()

    def test_default_selects_first(self):
        g = VCWidgetGallery(["VCSpeedDial", "VCSlider"])
        self.assertEqual(g.selected(), "VCSpeedDial")

    def test_current_is_preselected(self):
        g = VCWidgetGallery(["VCSpeedDial", "VCSlider"], current="VCSlider")
        self.assertEqual(g.selected(), "VCSlider")

    def test_change_selection(self):
        g = VCWidgetGallery(["VCSpeedDial", "VCSlider"])
        g.list.setCurrentRow(1)
        self.assertEqual(g.selected(), "VCSlider")

    def test_preview_pixmap_non_null(self):
        for wt in ("VCButton", "VCSlider", "VCSpeedDial", "VCEffectColors", "VCXYPad"):
            self.assertFalse(widget_preview_pixmap(wt).isNull())


# ── VCConflictCard ───────────────────────────────────────────────────────────

class ConflictCardTest(unittest.TestCase):

    def setUp(self):
        _app()

    def test_default_no_resolution(self):
        c = VCConflictCard("FX", ["Fader 1"])
        self.assertIsNone(c.resolution())

    def test_choose_maps_to_resolution(self):
        for key in ("replace", "couple", "new"):
            c = VCConflictCard("FX", ["Fader 1"])
            c._choose(key)
            self.assertEqual(c.resolution(), key)


# ── Phase 5: kontextgefilterte SpeedDial-Einstellungen (Smoke) ───────────────

class SpeedDialSettingsSmokeTest(unittest.TestCase):
    """Der entrümpelte SpeedDial-Einstellungsdialog (modusabhängige Feld-
    Sichtbarkeit) baut für JEDEN Ziel-Modus fehlerfrei. exec() wird gepatcht,
    damit der modale Dialog im Test nicht blockiert."""

    def setUp(self):
        _app()

    def test_open_properties_builds_for_each_target_mode(self):
        from unittest.mock import patch
        from PySide6.QtWidgets import QDialog
        from src.ui.virtualconsole.vc_speedial import VCSpeedDial, SpeedTarget
        modes = (SpeedTarget.EXECUTOR, SpeedTarget.FUNCTION, SpeedTarget.TEMPO_BUS,
                 SpeedTarget.TEMPO_BUS_MULT, SpeedTarget.SPEED_NODE)
        for mode in modes:
            sd = VCSpeedDial("S")
            sd.target_mode = mode
            with patch.object(QDialog, "exec",
                              return_value=QDialog.DialogCode.Rejected):
                sd._open_properties()   # darf nicht werfen


if __name__ == "__main__":
    unittest.main()
