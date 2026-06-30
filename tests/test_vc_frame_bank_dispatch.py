"""VCB-04: Frame-Kinder erben die Bank ihres Eltern-Frames fuer MIDI/Hotkey.

Vorher trugen in einen VCFrame gelegte Kinder ``bank=-1`` (= „alle Banks") und
feuerten deshalb nach einem Bank-Wechsel weiter MIDI/Hotkey, obwohl der Frame
(auf fester Bank) laengst verdeckt war. ``VCCanvas.on_active_bank`` laeuft jetzt
die Parent-Kette hoch bis zum naechsten Vorfahren mit fester Bank — dessen Bank
entscheidet. Beide Dispatcher (``_handle_midi`` und ``_on_hotkey``) gehen durch
diese Funktion, daher genuegt es, sie zu pruefen (+ ein Dispatch-Integrationsfall).
"""
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QPoint

from src.ui.virtualconsole.vc_canvas import VCCanvas

_app = QApplication.instance() or QApplication([])


class _CanvasTest(unittest.TestCase):
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

    def _frame_on_bank(self, canvas, bank):
        canvas._active_bank = bank
        frame = canvas._add_widget("VCFrame", QPoint(200, 60))
        frame.resize(300, 200)
        return frame


class FrameChildBankInheritanceTest(_CanvasTest):
    def test_child_silent_on_other_bank(self):
        """Kern-Fix: Frame auf fester Bank, Kind erbt sie → auf fremder Bank stumm."""
        canvas = self._canvas()
        frame = self._frame_on_bank(canvas, 1)
        child = frame._add_child_widget("VCButton", QPoint(20, 20))
        self.assertEqual(frame.bank, 1)
        self.assertEqual(child.bank, -1)            # Kind hat keinen eigenen Pin

        canvas.set_active_bank(0)                    # weg von der Frame-Bank
        self.assertFalse(canvas.on_active_bank(child))  # vorher faelschlich True

        canvas.set_active_bank(1)                    # zurueck zur Frame-Bank
        self.assertTrue(canvas.on_active_bank(child))

    def test_all_banks_frame_child_is_universal(self):
        """Frame auf „alle Banks" (bank=-1) → Kind reagiert auf jeder Bank."""
        canvas = self._canvas()
        frame = self._frame_on_bank(canvas, 2)
        frame.bank = -1
        child = frame._add_child_widget("VCButton", QPoint(20, 20))
        for b in (0, 2, 5, 7):
            canvas.set_active_bank(b)
            self.assertTrue(canvas.on_active_bank(child))

    def test_child_explicit_bank_overrides_all_banks_frame(self):
        """Frame=alle Banks, Kind aber explizit gepinnt → der Kind-Pin gewinnt."""
        canvas = self._canvas()
        frame = self._frame_on_bank(canvas, 0)
        frame.bank = -1
        child = frame._add_child_widget("VCButton", QPoint(20, 20))
        child.bank = 2                              # eigener Pin auf Bank 2

        canvas.set_active_bank(2)
        self.assertTrue(canvas.on_active_bank(child))
        canvas.set_active_bank(1)
        self.assertFalse(canvas.on_active_bank(child))

    def test_nested_frame_inherits_outer_bank(self):
        """Frame-in-Frame: das innere (bank=-1) erbt die Bank des aeusseren."""
        canvas = self._canvas()
        outer = self._frame_on_bank(canvas, 2)
        inner = outer._add_child_widget("VCFrame", QPoint(20, 20))
        self.assertEqual(inner.bank, -1)
        child = inner._add_child_widget("VCButton", QPoint(10, 10))

        canvas.set_active_bank(2)
        self.assertTrue(canvas.on_active_bank(child))
        canvas.set_active_bank(0)
        self.assertFalse(canvas.on_active_bank(child))

    def test_top_level_widget_unchanged(self):
        """Regression: Top-Level-Widgets (kein Frame-Eltern) wie bisher."""
        canvas = self._canvas()
        canvas.set_active_bank(0)
        free = canvas._add_widget("VCButton", QPoint(20, 20))   # bank=0 (aktive)
        pinned = canvas._add_widget("VCButton", QPoint(60, 20))
        pinned.bank = 3
        allbanks = canvas._add_widget("VCButton", QPoint(100, 20))
        allbanks.bank = -1

        self.assertTrue(canvas.on_active_bank(free))            # bank 0 == aktiv
        self.assertFalse(canvas.on_active_bank(pinned))         # bank 3 != aktiv
        self.assertTrue(canvas.on_active_bank(allbanks))        # -1 = alle
        canvas.set_active_bank(3)
        self.assertTrue(canvas.on_active_bank(pinned))


class FrameChildDispatchTest(_CanvasTest):
    """Integration: der MIDI-Dispatch liefert nicht an off-bank Frame-Kinder."""

    def test_handle_midi_skips_offbank_frame_child(self):
        canvas = self._canvas()
        frame = self._frame_on_bank(canvas, 1)
        child = frame._add_child_widget("VCButton", QPoint(20, 20))

        calls = []
        child.handle_midi = lambda msg: calls.append(msg)       # Spy

        class _Msg:
            channel = 0
            data1 = 0
            msg_type = "note_on"

        canvas.set_active_bank(0)                               # Frame verdeckt
        canvas._handle_midi(_Msg())
        self.assertEqual(calls, [])                             # nicht zugestellt

        canvas.set_active_bank(1)                               # Frame aktiv
        canvas._handle_midi(_Msg())
        self.assertEqual(len(calls), 1)                         # jetzt zugestellt


if __name__ == "__main__":
    unittest.main()
