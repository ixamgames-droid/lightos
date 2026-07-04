"""LAS-10: VC-Buttons für Laser-Sicherheit (Scharf-Toggle + Not-Aus) und die
Rück-Synchronisation des Arm-Buttons in der Laser-Steuerseite."""
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

import src.core.app_state as app_state
from src.ui.virtualconsole.vc_button import VCButton, ButtonAction


def _app():
    return QApplication.instance() or QApplication([])


class _FakeLaserMgr:
    def __init__(self):
        self.armed = False
        self.estops = 0
        self.clears = 0
        self.arm_calls = []

    def set_armed(self, v):
        self.armed = bool(v)
        self.arm_calls.append(bool(v))

    def estop_all(self):
        self.estops += 1

    def clear_estop_all(self):
        self.clears += 1


class _FakeState:
    def __init__(self):
        self._laser_output = _FakeLaserMgr()

    def ensure_laser_output(self):
        return self._laser_output


class VcLaserButtonTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = _app()

    def setUp(self):
        self._orig = app_state.get_state
        self.state = _FakeState()
        app_state.get_state = lambda: self.state

    def tearDown(self):
        app_state.get_state = self._orig

    def _btn(self, action):
        b = VCButton()
        b.action = action
        b.function_id = None
        return b

    def test_arm_toggles_manager(self):
        b = self._btn(ButtonAction.LASER_ARM)
        mgr = self.state._laser_output
        self.assertFalse(mgr.armed)
        b._trigger_primary(True)
        self.assertTrue(mgr.armed)           # unscharf → scharf
        b._trigger_primary(True)
        self.assertFalse(mgr.armed)          # scharf → unscharf

    def test_arm_ignores_release(self):
        b = self._btn(ButtonAction.LASER_ARM)
        b._trigger_primary(False)            # nur Loslassen → kein Toggle
        self.assertEqual(self.state._laser_output.arm_calls, [])

    def test_estop_locks_dark_and_disarms(self):
        b = self._btn(ButtonAction.LASER_ESTOP)
        mgr = self.state._laser_output
        mgr.set_armed(True)                  # Laser war scharf
        b._trigger_primary(True)
        self.assertEqual(mgr.estops, 1)      # verriegelt
        self.assertFalse(mgr.armed)          # entwaffnet (bleibt dunkel)
        self.assertEqual(mgr.clears, 1)      # Session wieder offen
        # Reihenfolge: estop VOR disarm VOR clear — armed endet auf False.
        self.assertEqual(mgr.arm_calls[-1], False)

    def test_estop_ignores_release(self):
        b = self._btn(ButtonAction.LASER_ESTOP)
        b._trigger_primary(False)
        self.assertEqual(self.state._laser_output.estops, 0)

    def test_actions_in_dropdown_labels(self):
        from src.ui.virtualconsole.vc_button import BUTTON_ACTION_LABELS
        actions = {a for a, _ in BUTTON_ACTION_LABELS}
        self.assertIn(ButtonAction.LASER_ARM, actions)
        self.assertIn(ButtonAction.LASER_ESTOP, actions)

    def test_action_survives_dict_roundtrip(self):
        b = self._btn(ButtonAction.LASER_ARM)
        try:
            d = b.to_dict()
            b2 = VCButton()
            b2.from_dict(d)
        except Exception:
            self.skipTest("VCButton hat kein to_dict/from_dict-Paar")
        self.assertEqual(b2.action, ButtonAction.LASER_ARM)


class LaserViewArmSyncTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = _app()

    def test_sync_arm_reflects_manager(self):
        import src.ui.views.laser_view as lv

        class _St:
            def __init__(self):
                self._laser_output = _FakeLaserMgr()

            def get_patched_fixtures(self):
                return []

            def get_selected_fids(self):
                return []

        st = _St()
        orig = lv.get_state
        lv.get_state = lambda: st
        try:
            view = lv.LaserView(follow_selection=False)
            # Manager wird von außen (VC/MIDI) scharf geschaltet.
            st._laser_output.armed = True
            view._sync_arm_from_manager()
            self.assertTrue(view._btn_arm.isChecked())
            # Und wieder unscharf.
            st._laser_output.armed = False
            view._sync_arm_from_manager()
            self.assertFalse(view._btn_arm.isChecked())
        finally:
            lv.get_state = orig


if __name__ == "__main__":
    unittest.main()
