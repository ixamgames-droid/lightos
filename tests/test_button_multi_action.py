"""BTN-01: Multi-Actions auf VC-Buttons.

Ein Button kann beim Druck — nach seiner Primaer-Aktion — eine Liste weiterer
Aktionen der Reihe nach ausfuehren (Funktion start/stop/toggle, Effekt-Aktion,
Snapshot, …). Rueckwaertskompatibel: ohne 'actions' = klassischer Ein-Aktions-Button.
"""
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from src.core.app_state import get_state
from src.core.engine.rgb_matrix import RgbMatrixInstance, RgbAlgorithm
from src.ui.virtualconsole.vc_button import VCButton, ButtonAction
from src.ui.widgets.multi_action_dialog import MultiActionDialog, summarize

_app = QApplication.instance() or QApplication([])


class MultiActionExecTest(unittest.TestCase):
    def setUp(self):
        self.state = get_state()
        self.fm = self.state.function_manager
        self.fm.stop_all()
        self.m = RgbMatrixInstance(name="A", cols=2, rows=1,
                                   algorithm=RgbAlgorithm.CHASE, fixture_grid=[1, 2])
        self.fm.add(self.m)
        self.fid = self.m.id

    def tearDown(self):
        self.fm.stop_all()
        self.fm.remove(self.m.id)

    def _btn(self, actions):
        b = VCButton()
        b.action = ButtonAction.TOGGLE     # Primaer no-op (function_id None)
        b.function_id = None
        b.actions = actions
        return b

    def test_extra_function_on(self):
        self._btn([{"type": "function", "function_id": self.fid, "mode": "on"}])._trigger(True)
        self.assertTrue(self.fm.is_running(self.fid))

    def test_extra_function_off(self):
        self.fm.start(self.fid)
        self._btn([{"type": "function", "function_id": self.fid, "mode": "off"}])._trigger(True)
        self.assertFalse(self.fm.is_running(self.fid))

    def test_extra_function_toggle(self):
        b = self._btn([{"type": "function", "function_id": self.fid, "mode": "toggle"}])
        b._trigger(True)
        self.assertTrue(self.fm.is_running(self.fid))
        b._trigger(True)
        self.assertFalse(self.fm.is_running(self.fid))

    def test_multiple_actions_in_order(self):
        m2 = RgbMatrixInstance(name="B", cols=2, rows=1,
                               algorithm=RgbAlgorithm.CHASE, fixture_grid=[3, 4])
        self.fm.add(m2)
        try:
            self._btn([
                {"type": "function", "function_id": self.fid, "mode": "on"},
                {"type": "function", "function_id": m2.id, "mode": "on"},
            ])._trigger(True)
            self.assertTrue(self.fm.is_running(self.fid))
            self.assertTrue(self.fm.is_running(m2.id))
        finally:
            self.fm.remove(m2.id)

    def test_extra_only_on_press(self):
        self._btn([{"type": "function", "function_id": self.fid, "mode": "toggle"}])._trigger(False)
        self.assertFalse(self.fm.is_running(self.fid))   # Release loest keine Zusatz-Aktion aus

    def test_primary_plus_extra(self):
        # Primaer = FUNCTION_TOGGLE auf m (start), Extra = effect_action auf m.
        b = VCButton()
        b.action = ButtonAction.FUNCTION_TOGGLE
        b.function_id = self.fid
        b.actions = [{"type": "effect_action", "function_id": self.fid,
                      "effect_action_key": "reverse_direction"}]
        b._trigger(True)
        self.assertTrue(self.fm.is_running(self.fid))     # Primaer hat gestartet


class MultiActionSerializeTest(unittest.TestCase):
    def test_round_trip(self):
        b = VCButton()
        b.actions = [{"type": "function", "function_id": 5, "mode": "on", "delay": 0.5,
                      "snapshot_index": None, "snap_id": None, "effect_action_key": "next_color"}]
        b2 = VCButton()
        b2.apply_dict(b.to_dict())
        self.assertEqual(b2.actions, b.actions)

    def test_backward_compat_no_actions(self):
        b = VCButton()
        b.apply_dict({"action": "Toggle"})    # alte Show ohne 'actions'-Feld
        self.assertEqual(b.actions, [])


class MultiActionDialogTest(unittest.TestCase):
    def test_get_actions_returns_copy(self):
        dlg = MultiActionDialog([{"type": "tap", "mode": "toggle", "delay": 0}])
        out = dlg.get_actions()
        self.assertEqual(len(out), 1)
        out[0]["type"] = "x"
        self.assertEqual(dlg._actions[0]["type"], "tap")   # echte Kopie

    def test_summarize(self):
        self.assertIn("Funktion", summarize({"type": "function", "function_id": 3, "mode": "on"}))
        self.assertIn("Blackout", summarize({"type": "blackout", "mode": "on"}))


if __name__ == "__main__":
    unittest.main()
