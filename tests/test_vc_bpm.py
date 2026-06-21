"""WP-8 — Virtual-Console-Integration des BPM-Managers.

Deckt ab:
  (a) VCBpmDisplay konstruiert + to_dict()->apply_dict()-Roundtrip;
  (b) Button BPM_NUDGE_UP/DOWN veraendert get_bpm_manager().bpm wie erwartet;
  (c) Button BPM_MODE_TOGGLE kippt get_bpm_manager().mode (AUTO <-> MANUAL).

Headless/offscreen Qt. Setzt den BPM-Manager am Ende auf AUTO zurueck, damit
andere Suite-Tests nicht beeinflusst werden. Startet KEINE Audio-Erfassung
(conftest setzt LIGHTOS_NO_AUDIO_AUTOSTART; VCBpmDisplay ruft kein
use_audio_source).
"""
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from src.ui.virtualconsole.vc_bpm_display import VCBpmDisplay
from src.ui.virtualconsole.vc_button import VCButton, ButtonAction
from src.ui.virtualconsole.vc_canvas import WIDGET_REGISTRY
from src.core.engine.bpm_manager import get_bpm_manager, BpmMode

_app = QApplication.instance() or QApplication([])


class VCBpmDisplayTest(unittest.TestCase):
    def test_registered_in_registry(self):
        self.assertIn("VCBpmDisplay", WIDGET_REGISTRY)
        self.assertIs(WIDGET_REGISTRY["VCBpmDisplay"], VCBpmDisplay)

    def test_construct_and_roundtrip(self):
        w = VCBpmDisplay("Tempo")
        w._font_size = 18
        d = w.to_dict()
        self.assertEqual(d["type"], "VCBpmDisplay")
        self.assertEqual(d["font_size"], 18)
        self.assertEqual(d["caption"], "Tempo")

        w2 = VCBpmDisplay()
        w2.apply_dict(d)
        self.assertEqual(w2._font_size, 18)
        self.assertEqual(w2.caption, "Tempo")
        self.assertEqual(w2.geometry(), w.geometry())

    def test_paint_does_not_crash(self):
        w = VCBpmDisplay()
        w.resize(180, 100)
        w.repaint()   # rendert offscreen in den Backbuffer

    def test_does_not_start_audio(self):
        # Konstruktion darf den Audio-Modus NICHT aktivieren.
        mgr = get_bpm_manager()
        VCBpmDisplay()
        self.assertFalse(mgr.audio_active)


class VCBpmButtonTest(unittest.TestCase):
    def setUp(self):
        self.mgr = get_bpm_manager()

    def _btn(self, action: ButtonAction) -> VCButton:
        b = VCButton("X")
        b.action = action
        return b

    def test_nudge_up_then_down(self):
        # Bekannten Ausgangspunkt setzen (MANUAL, fester Wert).
        self.mgr.set_manual_bpm(120.0)
        start = self.mgr.bpm
        self.assertAlmostEqual(start, 120.0, places=3)

        up = self._btn(ButtonAction.BPM_NUDGE_UP)
        up._trigger_primary(True)
        self.assertAlmostEqual(self.mgr.bpm, start + 1.0, places=3)

        down = self._btn(ButtonAction.BPM_NUDGE_DOWN)
        down._trigger_primary(True)
        self.assertAlmostEqual(self.mgr.bpm, start, places=3)

    def test_mode_toggle_flips(self):
        self.mgr.set_mode(BpmMode.AUTO)
        self.assertEqual(self.mgr.mode, BpmMode.AUTO)

        tog = self._btn(ButtonAction.BPM_MODE_TOGGLE)
        tog._trigger_primary(True)
        self.assertEqual(self.mgr.mode, BpmMode.MANUAL)

        tog._trigger_primary(True)
        self.assertEqual(self.mgr.mode, BpmMode.AUTO)

    def test_action_roundtrips_by_value(self):
        # to_dict/apply_dict muessen die neuen Aktionen erhalten.
        for action in (ButtonAction.BPM_NUDGE_UP, ButtonAction.BPM_NUDGE_DOWN,
                       ButtonAction.BPM_MODE_TOGGLE):
            b = self._btn(action)
            d = b.to_dict()
            b2 = VCButton()
            b2.apply_dict(d)
            self.assertEqual(b2.action, action)

    @classmethod
    def tearDownClass(cls):
        # BPM-Manager-Zustand fuer den Rest der Suite neutralisieren.
        try:
            get_bpm_manager().set_mode(BpmMode.AUTO)
        except Exception:
            pass


if __name__ == "__main__":
    unittest.main()
