"""VC-Audit 2026-06-13 (C): Smoke-Test der Properties-Dialoge.

Die bestehenden Tests öffnen die Einstellungs-Dialoge nicht — sie würden auf
dlg.exec() blockieren. Hier wird exec() auf Rejected gepatcht, sodass der GESAMTE
Dialog-Aufbau läuft (Combos, kontextabhängige setRowVisible-Logik, neue Felder).
Fängt Konstruktions-/AttributeError in den aufgeräumten Dialogen ab.
"""
import os
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QDialog

from src.ui.virtualconsole.vc_button import VCButton, ButtonAction
from src.ui.virtualconsole.vc_slider import VCSlider, SliderMode
from src.ui.virtualconsole.vc_color import VCColor
from src.ui.virtualconsole.vc_speedial import VCSpeedDial
from src.ui.virtualconsole.vc_xypad import VCXYPad
from src.ui.virtualconsole.vc_frame import VCFrame

_app = QApplication.instance() or QApplication([])


class DialogSmokeTest(unittest.TestCase):
    def _open(self, widget):
        with patch.object(QDialog, "exec", return_value=QDialog.DialogCode.Rejected):
            widget._open_properties()        # darf nicht werfen

    def test_button_dialog_all_actions(self):
        for action in ButtonAction:
            b = VCButton("B")
            b.action = action
            self._open(b)

    def test_slider_dialog_all_modes(self):
        for m in (SliderMode.LEVEL, SliderMode.PLAYBACK, SliderMode.SUBMASTER,
                  SliderMode.GRANDMASTER, SliderMode.PROGRAMMER, SliderMode.BPM,
                  SliderMode.SPEED, SliderMode.EFFECT_INTENSITY,
                  SliderMode.EFFECT_SPEED, SliderMode.EFFECT_PARAM,
                  SliderMode.GROUP_DIMMER):
            s = VCSlider("S")
            s.mode = m
            self._open(s)

    def test_color_dialog(self):
        self._open(VCColor("Farbe"))

    def test_speeddial_dialog(self):
        self._open(VCSpeedDial("Speed"))

    def test_xypad_dialog(self):
        self._open(VCXYPad("XY"))

    def test_frame_dialog(self):
        self._open(VCFrame("Frame"))

    def test_button_effect_action_combo_keeps_unknown_key(self):
        # Ein gespeicherter, nicht-kuratierter Aktions-Key darf nicht verloren gehen.
        b = VCButton("B")
        b.action = ButtonAction.EFFECT_ACTION
        b.effect_action_key = "mein_custom_key"
        self._open(b)
        self.assertEqual(b.effect_action_key, "mein_custom_key")


if __name__ == "__main__":
    unittest.main()
