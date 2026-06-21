"""T-VIZ-15: Stage-Element-Farbdialog mit Live-Preview.

Der Farbwähler ist jetzt nicht-modal: beim Durchscrollen wirkt die Farbe sofort
(currentColorChanged -> el.color + Bridge-Update), Abbrechen stellt die
Ausgangsfarbe wieder her.

Bewusst OHNE die echte VisualizerWindow (zieht QtWebEngine hoch). Die Methode
wird auf einem leichten QWidget-Host aufgerufen — _on_pick_stage_color nutzt
`self` nur als Dialog-Parent, daher genügt ein echtes QWidget mit den
benötigten Attributen.
"""
import json
import os
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QWidget, QLabel
from PySide6.QtGui import QColor

import src.ui.visualizer.visualizer_window as VW

_app = QApplication.instance() or QApplication([])


class StageColorLivePreviewTest(unittest.TestCase):
    def _host(self, el):
        host = QWidget()
        host._selected_stage_element = lambda: el
        host._stage_color_preview = QLabel(host)
        host._bridge = SimpleNamespace(updateStageObject=SimpleNamespace(emit=MagicMock()))
        return host

    def test_no_element_no_dialog(self):
        host = self._host(None)
        VW.VisualizerWindow._on_pick_stage_color(host)
        self.assertIsNone(getattr(host, "_stage_color_picker", None))

    def test_live_preview_applies_immediately(self):
        el = SimpleNamespace(id="el1", color="#112233")
        host = self._host(el)
        VW.VisualizerWindow._on_pick_stage_color(host)

        dlg = host._stage_color_picker
        self.assertIsNotNone(dlg)
        self.assertFalse(dlg.isModal())            # nicht-modal -> Live-Preview moeglich

        # Durchscrollen -> Farbe wirkt sofort (ohne OK).
        dlg.currentColorChanged.emit(QColor("#ff0000"))
        self.assertEqual(el.color, "#ff0000")
        payload = json.loads(host._bridge.updateStageObject.emit.call_args[0][0])
        self.assertEqual(payload, {"id": "el1", "color": "#ff0000"})
        dlg.reject()                                # aufraeumen

    def test_cancel_reverts_to_original(self):
        el = SimpleNamespace(id="el1", color="#112233")
        host = self._host(el)
        VW.VisualizerWindow._on_pick_stage_color(host)
        dlg = host._stage_color_picker

        dlg.currentColorChanged.emit(QColor("#00ff00"))
        self.assertEqual(el.color, "#00ff00")
        dlg.reject()                                # Abbrechen
        self.assertEqual(el.color, "#112233")       # Ausgangsfarbe wiederhergestellt
        self.assertIsNone(host._stage_color_picker)  # Referenz aufgeraeumt

    def test_ok_keeps_chosen_color(self):
        el = SimpleNamespace(id="el1", color="#112233")
        host = self._host(el)
        VW.VisualizerWindow._on_pick_stage_color(host)
        dlg = host._stage_color_picker

        dlg.currentColorChanged.emit(QColor("#0000ff"))
        dlg.accept()                                # OK
        self.assertEqual(el.color, "#0000ff")       # bleibt erhalten
        self.assertIsNone(host._stage_color_picker)

    def test_selection_change_mid_dialog_does_not_edit_original(self):
        # Nicht-modal: wechselt die Baum-Auswahl waehrend der Picker (fuer el1)
        # offen ist, darf das Scrollen NICHT mehr el1 (oder el2) umfaerben.
        el1 = SimpleNamespace(id="el1", color="#112233")
        el2 = SimpleNamespace(id="el2", color="#445566")
        host = self._host(el1)
        VW.VisualizerWindow._on_pick_stage_color(host)
        dlg = host._stage_color_picker
        host._selected_stage_element = lambda: el2   # Auswahl wechselt
        dlg.currentColorChanged.emit(QColor("#ff0000"))
        self.assertEqual(el1.color, "#112233")       # el1 unveraendert
        self.assertEqual(el2.color, "#445566")       # el2 unangetastet
        dlg.reject()


if __name__ == "__main__":
    unittest.main()
