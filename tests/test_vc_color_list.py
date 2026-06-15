"""APC-Probier To-Do #6: VCColorList — Live-Feedback der gebauten Farbliste.

Zeigt die Color-Sequence eines Ziel-Effekts (Reihenfolge + aktive Farbe + Status).
Reines Anzeige-Widget; Test prüft Bindung, Rendering ohne Crash (alle Zustände),
Persistenz und Registrierung in der Widget-Registry.
"""
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from src.core.engine.function_manager import get_function_manager
from src.core.engine.rgb_matrix import RgbMatrixInstance, RgbAlgorithm, ColorSequence
from src.ui.virtualconsole.vc_color_list import VCColorList
from src.ui.virtualconsole.vc_canvas import WIDGET_REGISTRY

_app = QApplication.instance() or QApplication([])


class VCColorListTest(unittest.TestCase):
    def setUp(self):
        self.fm = get_function_manager()
        self.fm.stop_all()
        self._pre = {f.id for f in self.fm.all()}
        self.m = RgbMatrixInstance(name="builder", cols=4, rows=1,
                                   algorithm=RgbAlgorithm.COLORFADE, fixture_grid=[1, 2, 3, 4])
        self.m.colors = ColorSequence([(255, 0, 0), (0, 255, 0), (0, 0, 255)])
        self.fm.add(self.m)

    def tearDown(self):
        self.fm.stop_all()
        for f in list(self.fm.all()):
            if f.id not in self._pre:
                self.fm.remove(f.id)

    def test_registered_in_registry(self):
        self.assertIn("VCColorList", WIDGET_REGISTRY)
        self.assertIs(WIDGET_REGISTRY["VCColorList"], VCColorList)

    def test_effect_binding(self):
        w = VCColorList()
        w.function_id = self.m.id
        self.assertTrue(w.is_effect_bound())
        self.assertEqual(w.live_effect_function_id(), self.m.id)
        self.assertIs(w._target(), self.m)

    def test_renders_in_all_states_without_crash(self):
        w = VCColorList()
        # 1) kein Ziel
        w.function_id = 999999
        w.grab()
        # 2) Ziel gebunden, gestoppt, mit Farben
        w.function_id = self.m.id
        w.grab()
        # 3) Ziel läuft
        self.fm.start(self.m.id)
        w.grab()
        # 4) leere Sequence
        self.m.colors = ColorSequence([])
        w.grab()
        # 5) deaktivierte Farbe
        self.m.colors = ColorSequence([(255, 0, 0), (0, 255, 0)])
        self.m.colors.set_enabled(1, False)
        w.grab()

    def test_serialization_roundtrip(self):
        w = VCColorList("Meine Liste")
        w.function_id = 42
        w2 = VCColorList()
        w2.apply_dict(w.to_dict())
        self.assertEqual(w2.caption, "Meine Liste")
        self.assertEqual(w2.function_id, 42)
        self.assertEqual(w.to_dict()["type"], "VCColorList")

    def test_target_none_when_no_active_and_unbound(self):
        self.fm.stop_all()
        w = VCColorList()           # function_id None, kein laufender Effekt
        self.assertIsNone(w._target())
        w.grab()                    # darf nicht crashen


if __name__ == "__main__":
    unittest.main()
