"""VC-Erweiterung 2026-06-13 (F1): Soft-Takeover / „Pickup" für Fader.

Für nicht-motorisierte Controller (APC mini): nach einem Bank-/Seitenwechsel
übernimmt der Fader erst, wenn der physische Fader den aktuellen VC-Wert einmal
durchfährt — keine Wertsprünge. Bei deaktiviertem Pickup gilt das alte Verhalten.

WICHTIG: soft_takeover ist ein KLASSEN-Flag → in tearDown zurücksetzen, sonst
verseucht es andere Tests (Global-State-Pollution).
"""
import os
import unittest
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from src.ui.virtualconsole.vc_slider import VCSlider, SliderMode

_app = QApplication.instance() or QApplication([])


def _cc(val, data1=10, ch=1):
    return SimpleNamespace(msg_type="cc", channel=ch, data1=data1, data2=val)


class SoftTakeoverTest(unittest.TestCase):
    def setUp(self):
        VCSlider.soft_takeover = False
        self.s = VCSlider("F")
        self.s.mode = SliderMode.SPEED       # harmloser Modus (keine DMX-Seiteneffekte)
        self.s.midi_cc = 10
        self.s.midi_ch = 1

    def tearDown(self):
        VCSlider.soft_takeover = False        # Klassen-Flag zurücksetzen!

    def test_disabled_passes_through(self):
        self.s.handle_midi(_cc(127))
        self.assertEqual(self.s.value, 255)
        self.s.handle_midi(_cc(0))
        self.assertEqual(self.s.value, 0)

    def test_armed_ignores_far_value(self):
        VCSlider.soft_takeover = True
        self.s._value = 200
        self.s.arm_pickup()
        self.assertTrue(self.s._pickup_armed)
        self.s.handle_midi(_cc(0))            # physisch ganz unten, weit vom Wert
        self.assertEqual(self.s.value, 200)   # unverändert (kein Sprung)
        self.s.handle_midi(_cc(20))           # immer noch darunter
        self.assertEqual(self.s.value, 200)
        self.assertTrue(self.s._pickup_armed)

    def test_catches_on_cross(self):
        VCSlider.soft_takeover = True
        self.s._value = 130
        self.s.arm_pickup()
        self.s.handle_midi(_cc(0))            # Referenz unten
        self.assertEqual(self.s.value, 130)
        self.s.handle_midi(_cc(127))          # fährt nach oben DURCH 130
        self.assertFalse(self.s._pickup_armed)
        self.assertEqual(self.s.value, 255)   # ab jetzt übernommen
        self.s.handle_midi(_cc(64))           # läuft danach normal mit (64→129)
        self.assertEqual(self.s.value, 129)

    def test_catch_within_tolerance(self):
        VCSlider.soft_takeover = True
        self.s._value = 128
        self.s.arm_pickup()
        self.s.handle_midi(_cc(64))           # 64→129, |129-128|=1 ≤ Toleranz -> sofort fangen
        self.assertFalse(self.s._pickup_armed)
        self.assertEqual(self.s.value, 129)

    def test_arm_noop_when_disabled(self):
        VCSlider.soft_takeover = False
        self.s.arm_pickup()
        self.assertFalse(self.s._pickup_armed)   # ohne globales Flag nicht armiert

    def test_other_cc_ignored(self):
        VCSlider.soft_takeover = True
        self.s._value = 50
        self.s.arm_pickup()
        consumed = self.s.handle_midi(_cc(127, data1=99))  # falsche CC-Nummer
        self.assertFalse(consumed)
        self.assertTrue(self.s._pickup_armed)


if __name__ == "__main__":
    unittest.main()
