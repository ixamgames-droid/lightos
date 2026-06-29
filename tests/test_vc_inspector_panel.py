"""Runde 1: Inspector-Side-Panel der Virtuellen Konsole (VCButton als Referenz).

Deckt ab: build_inspector_body baut fuer ALLE Button-Aktionen ohne Fehler; Live-
Apply (Aenderung wirkt sofort aufs Widget); Undo-Sitzung beim Verlassen; Fallback
fuer (noch) nicht migrierte Widget-Typen; der behobene lib_combo-Bug (Einzel-Snap).
"""
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPoint
from PySide6.QtWidgets import QApplication, QLineEdit, QComboBox

from src.ui.virtualconsole.vc_button import VCButton, ButtonAction, BUTTON_ACTION_LABELS
from src.ui.virtualconsole.vc_slider import VCSlider
from src.ui.virtualconsole.vc_canvas import VCCanvas
from src.ui.virtualconsole.vc_inspector_panel import VCInspectorPanel

_app = QApplication.instance() or QApplication([])


def _caption_edit(body, current):
    for le in body.findChildren(QLineEdit):
        if le.text() == current:
            return le
    raise AssertionError("Beschriftungs-Feld nicht gefunden")


def _action_combo(body):
    for cb in body.findChildren(QComboBox):
        if cb.count() == len(BUTTON_ACTION_LABELS):
            return cb
    raise AssertionError("Aktions-Combo nicht gefunden")


class InspectorBuildTest(unittest.TestCase):
    def test_build_body_all_actions(self):
        for action in ButtonAction:
            b = VCButton("B")
            b.action = action
            body = b.build_inspector_body()          # darf nicht werfen
            self.assertIsNotNone(body)
            self.assertTrue(callable(getattr(b, "_inspector_apply", None)))

    def test_live_caption_edit(self):
        b = VCButton("Orig")
        body = b.build_inspector_body()
        _caption_edit(body, "Orig").setText("Neu")
        self.assertEqual(b.caption, "Neu")           # Live-Apply ohne OK-Button

    def test_live_action_change(self):
        b = VCButton("B")
        b.action = ButtonAction.TOGGLE
        body = b.build_inspector_body()
        cb = _action_combo(body)
        for i in range(cb.count()):
            if cb.itemData(i) == ButtonAction.FLASH.value:
                cb.setCurrentIndex(i)
                break
        self.assertEqual(b.action, ButtonAction.FLASH)


class InspectorPanelTest(unittest.TestCase):
    def setUp(self):
        self.canvas = VCCanvas()
        self.btn = self.canvas._add_widget("VCButton", QPoint(20, 20))
        self.assertIsInstance(self.btn, VCButton)
        self.panel = VCInspectorPanel()

    def tearDown(self):
        self.panel.deleteLater()
        self.canvas.deleteLater()

    def test_bind_none_is_safe(self):
        self.panel.bind(None)                        # leerer Zustand, kein Fehler
        self.panel.clear()

    def test_bind_button_builds(self):
        self.panel.bind(self.btn)
        self.assertIs(self.panel._widget, self.btn)

    def test_undo_session_on_unbind(self):
        self.panel.bind(self.btn)
        before = len(self.canvas._undo_stack)
        # Live-Aenderung am gebundenen Button:
        body = self.panel._scroll.widget()
        _caption_edit(body, self.btn.caption).setText("Geändert")
        self.assertEqual(self.btn.caption, "Geändert")
        # Sitzung beenden -> genau EIN Undo-Schritt fuer die gesamte Bearbeitung.
        self.panel.clear()
        self.assertEqual(len(self.canvas._undo_stack), before + 1)
        self.canvas.undo()
        # Undo baut die Widgets neu auf -> den wiederhergestellten Button abfragen.
        restored = self.canvas.findChildren(VCButton)[0]
        self.assertNotEqual(restored.caption, "Geändert")

    def test_no_undo_without_change(self):
        self.panel.bind(self.btn)
        before = len(self.canvas._undo_stack)
        self.panel.clear()                           # nichts geaendert -> kein Undo
        self.assertEqual(len(self.canvas._undo_stack), before)

    def test_fallback_for_unmigrated_type(self):
        slider = self.canvas._add_widget("VCSlider", QPoint(200, 20))
        self.assertIsInstance(slider, VCSlider)
        self.panel.bind(slider)                      # kein build_inspector_body -> Fallback
        self.assertIs(self.panel._widget, slider)


class LibSnapFixTest(unittest.TestCase):
    """Audit-Bug: Einzel-Snap war nicht mehr waehlbar (lib_combo immer unsichtbar).
    Jetzt verwaltet der SnapListEditor Einzel- UND Mehrfach-Snaps; ein gesetzter
    Einzel-Snap bleibt beim Bauen/Anwenden erhalten."""

    def test_single_snap_survives(self):
        b = VCButton("Snap")
        b.action = ButtonAction.LIBRARY_SNAP
        b.snap_id = 7
        b.snap_ids = []
        body = b.build_inspector_body()   # Referenz halten (sonst GC -> Felder weg)
        b._inspector_apply()
        self.assertEqual(b.snap_id, 7)
        self.assertEqual(b.snap_ids, [])
        self.assertIsNotNone(body)


if __name__ == "__main__":
    unittest.main()
