"""FDR-01: VCSlider im Programmer-Modus kann auf die Auswahl/Gruppe begrenzt werden."""
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from src.core.app_state import get_state
from src.ui.virtualconsole.vc_slider import VCSlider, SliderMode

_app = QApplication.instance() or QApplication([])


class _F:
    def __init__(self, fid):
        self.fid = fid
        self.universe = 250        # nicht gepatcht -> _flush_programmer_to_dmx bricht früh ab


class ProgrammerScopeTest(unittest.TestCase):
    def setUp(self):
        self.state = get_state()
        self._orig_patch = self.state._patch_cache
        self.state._patch_cache = [_F(1), _F(2), _F(3)]
        self.state.clear_programmer()

    def tearDown(self):
        self.state.clear_programmer()
        self.state._patch_cache = self._orig_patch
        self.state.set_selected_fids([])

    def _slider(self, scope):
        s = VCSlider()
        s.mode = SliderMode.PROGRAMMER
        s.programmer_attr = "intensity"
        s.programmer_scope = scope
        s._value = 200
        return s

    def test_scope_all(self):
        self._slider("all")._apply()
        self.assertEqual(self.state.get_programmer_value(1, "intensity"), 200)
        self.assertEqual(self.state.get_programmer_value(2, "intensity"), 200)
        self.assertEqual(self.state.get_programmer_value(3, "intensity"), 200)

    def test_scope_selected_only(self):
        self.state.set_selected_fids([2])
        self._slider("selected")._apply()
        self.assertEqual(self.state.get_programmer_value(2, "intensity"), 200)
        self.assertIsNone(self.state.get_programmer_value(1, "intensity"))
        self.assertIsNone(self.state.get_programmer_value(3, "intensity"))

    def test_scope_selected_fallback_all(self):
        # Nichts ausgewaehlt -> Fallback auf alle (Fader bleibt nutzbar).
        self.state.set_selected_fids([])
        self._slider("selected")._apply()
        self.assertEqual(self.state.get_programmer_value(1, "intensity"), 200)

    def test_serialization(self):
        s = self._slider("selected")
        s2 = VCSlider()
        s2.apply_dict(s.to_dict())
        self.assertEqual(s2.programmer_scope, "selected")

    def test_backward_compat(self):
        s = VCSlider()
        s.apply_dict({"mode": "Programmer"})
        self.assertEqual(s.programmer_scope, "all")


if __name__ == "__main__":
    unittest.main()
