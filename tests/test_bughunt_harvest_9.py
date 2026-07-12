"""Bug-Hunt-Harvest 9: BH-MODNAME + BH-FRAMEBANK (2026-07-12).

- channel_modifier_dialog: die editierbare Name-Spalte wurde beim Speichern nicht
  zurueckgelesen -> Umbenennungen gingen verloren. Jetzt schreibt _on_name_edited
  den Text sofort ins Modifier-Objekt (via UserRole-Referenz am Item).
- vc_frame: die SICHTBARKEIT von Widgets IN einem VCFrame folgte nur der Seite,
  nicht der aktiven Bank (Canvas._apply_bank_visibility iteriert nur direkte
  Canvas-Kinder). Jetzt propagiert die Canvas den Bank-Wechsel in die Frames und
  der Frame kombiniert Seite x Bank; die Bank-Entscheidung delegiert er an die
  getestete Autoritaet VCCanvas.on_active_bank (VCB-04-Vererbung, auch nested).
  Der Dispatch-Test (test_vc_frame_bank_dispatch) deckt on_active_bank/MIDI ab;
  HIER wird die tatsaechliche isHidden()-Sichtbarkeit der Frame-Kinder geprueft.
"""
import os
import unittest
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QPoint

from src.ui.widgets.channel_modifier_dialog import ChannelModifierDialog
from src.ui.virtualconsole.vc_canvas import VCCanvas

_app = QApplication.instance() or QApplication([])


class ModifierNameEditTest(unittest.TestCase):
    def test_edited_name_written_back_to_modifier(self):
        mod = SimpleNamespace(name="alt")
        item = SimpleNamespace(column=lambda: 3,
                               data=lambda role: mod,
                               text=lambda: "Bass-Boost")
        ChannelModifierDialog._on_name_edited(None, item)
        self.assertEqual(mod.name, "Bass-Boost")

    def test_non_name_column_ignored(self):
        mod = SimpleNamespace(name="alt")
        item = SimpleNamespace(column=lambda: 1,
                               data=lambda role: mod,
                               text=lambda: "999")
        ChannelModifierDialog._on_name_edited(None, item)
        self.assertEqual(mod.name, "alt")


class FrameChildBankVisibilityTest(unittest.TestCase):
    """BH-FRAMEBANK: Bank-Wechsel blendet Frame-Kinder tatsaechlich ein/aus."""

    def setUp(self):
        self._canvases = []

    def tearDown(self):
        for c in self._canvases:
            try:
                c._teardown_midi()
            except Exception:
                pass
            c.setParent(None)
            c.deleteLater()
        self._canvases.clear()
        _app.processEvents()

    def _canvas(self):
        canvas = VCCanvas()
        self._canvases.append(canvas)
        canvas.set_edit_mode(True)
        return canvas

    def _frame(self, canvas, bank):
        canvas._active_bank = bank
        frame = canvas._add_widget("VCFrame", QPoint(200, 60))
        frame.resize(300, 200)
        return frame

    def test_child_pinned_to_bank_hidden_off_bank(self):
        """Frame auf alle Banks (bank=-1), Kind auf Bank 2 gepinnt:
        Kind-Sichtbarkeit folgt der aktiven Bank."""
        canvas = self._canvas()
        frame = self._frame(canvas, 0)
        frame.bank = -1                              # Frame auf allen Banks sichtbar
        child = frame._add_child_widget("VCButton", QPoint(20, 20))
        child.bank = 2                               # eigener Pin auf Bank 2

        canvas.set_active_bank(2)
        self.assertFalse(child.isHidden())           # Bank 2 aktiv -> sichtbar
        canvas.set_active_bank(0)
        self.assertTrue(child.isHidden())            # weg von Bank 2 -> versteckt
        canvas.set_active_bank(2)
        self.assertFalse(child.isHidden())           # wieder da

    def test_child_without_pin_follows_frame_bank(self):
        """VCB-04: Kind ohne eigenen Pin (bank=-1) erbt die Frame-Bank — auf
        fremder Bank versteckt (frueher blieb es faelschlich sichtbar)."""
        canvas = self._canvas()
        frame = self._frame(canvas, 1)               # Frame fest auf Bank 1
        child = frame._add_child_widget("VCButton", QPoint(20, 20))
        self.assertEqual(child.bank, -1)

        canvas.set_active_bank(1)
        self.assertFalse(child.isHidden())
        canvas.set_active_bank(0)
        self.assertTrue(child.isHidden())            # erbt Frame-Bank 1 -> weg

    def test_page_and_bank_combined(self):
        """Kind auf Seite 1 bleibt versteckt, obwohl die Bank passt."""
        canvas = self._canvas()
        frame = self._frame(canvas, 0)
        frame.bank = -1
        frame._page_count = 2                        # Frame hat zwei Seiten
        child = frame._add_child_widget("VCButton", QPoint(20, 20))
        child.setProperty("vc_page", 1)              # liegt auf Seite 1
        child.bank = 0                               # Bank passt zur aktiven

        frame.switch_page(0)                         # Frame zeigt Seite 0
        canvas.set_active_bank(0)
        self.assertTrue(child.isHidden())            # falsche Seite -> versteckt
        frame.switch_page(1)                         # jetzt Seite 1
        self.assertFalse(child.isHidden())           # Seite + Bank passen
        canvas.set_active_bank(3)                    # richtige Seite, falsche Bank
        self.assertTrue(child.isHidden())            # -> Bank-Achse greift ebenso

    def test_nested_frame_child_follows_outer_bank(self):
        """Frame-in-Frame: Kind im inneren Frame (beide bank=-1) folgt der
        aeusseren Frame-Bank — der Parent-Walk laeuft ganz nach oben."""
        canvas = self._canvas()
        outer = self._frame(canvas, 2)               # aeusserer Frame Bank 2
        inner = outer._add_child_widget("VCFrame", QPoint(20, 20))
        child = inner._add_child_widget("VCButton", QPoint(10, 10))

        canvas.set_active_bank(2)
        self.assertFalse(child.isHidden())
        canvas.set_active_bank(0)
        self.assertTrue(child.isHidden())


if __name__ == "__main__":
    unittest.main()
