"""VC-Erweiterung 2026-06-13 (F2): Funktions-Drop auf weitere Ziel-Widgets.

Bisher nahmen nur Button/Fader einen Funktions-Drop an. Jetzt akzeptieren auch
Farb-Kachel (→ Effekt-Farbe), Encoder (→ Effekt-Parameter), XY-Pad (→ Feld/EFX)
und Speed-Dial (→ Tempo der Funktion) einen Drop.
"""
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from src.core.engine.function_manager import get_function_manager
from src.core.engine.rgb_matrix import RgbMatrixInstance, RgbAlgorithm

from src.ui.virtualconsole.vc_canvas import VCCanvas
from src.ui.virtualconsole.vc_color import VCColor, ColorTarget
from src.ui.virtualconsole.vc_encoder import VCEncoder
from src.ui.virtualconsole.vc_xypad import VCXYPad
from src.ui.virtualconsole.vc_speedial import VCSpeedDial, SpeedTarget

_app = QApplication.instance() or QApplication([])


class DropTargetsTest(unittest.TestCase):
    def setUp(self):
        self.fm = get_function_manager()
        self.fm.stop_all()
        self.m = RgbMatrixInstance(name="dt", cols=4, rows=1,
                                   algorithm=RgbAlgorithm.CHASE, fixture_grid=[1, 2, 3, 4])
        self.fm.add(self.m)
        self.canvas = VCCanvas()
        self.canvas.set_edit_mode(True)

    def tearDown(self):
        self.fm.stop_all()
        self.fm.remove(self.m.id)

    def test_drop_on_color(self):
        c = VCColor(parent=self.canvas)
        self.canvas.apply_drop(function_id=self.m.id, target=c)
        self.assertEqual(c.target, ColorTarget.EFFECT)
        self.assertEqual(c.function_id, self.m.id)

    def test_drop_on_encoder(self):
        e = VCEncoder(parent=self.canvas)
        self.canvas.apply_drop(function_id=self.m.id, target=e)
        self.assertEqual(e.function_id, self.m.id)
        self.assertTrue(e.param_key)        # ein Parameter-Key wurde gesetzt

    def test_drop_on_xypad(self):
        xy = VCXYPad(parent=self.canvas)
        self.canvas.apply_drop(function_id=self.m.id, target=xy)
        self.assertEqual(xy.mode, "area")
        self.assertEqual(xy.efx_function_id, self.m.id)

    def test_drop_on_speeddial(self):
        sd = VCSpeedDial(parent=self.canvas)
        self.canvas.apply_drop(function_id=self.m.id, target=sd)
        self.assertEqual(sd.target_mode, SpeedTarget.FUNCTION)
        self.assertEqual(sd.function_id, self.m.id)

    def test_caption_taken_from_function(self):
        c = VCColor(parent=self.canvas)          # Default-Caption "Farbe"
        self.canvas.apply_drop(function_id=self.m.id, target=c)
        self.assertEqual(c.caption, "dt")

    def test_droppable_types_include_specials(self):
        types = VCCanvas._droppable_types()
        for t in (VCColor, VCEncoder, VCXYPad, VCSpeedDial):
            self.assertIn(t, types)


if __name__ == "__main__":
    unittest.main()
