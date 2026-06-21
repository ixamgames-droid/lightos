"""F-14: Quick-Rec im Playback-View — dialogfreies Ein-Klick-Record auf die
AKTUELL ausgewählte Cueliste (Auto-Nummer/Label), ohne QInputDialog."""
import os
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from src.core.app_state import get_state
from src.ui.views.playback_view import PlaybackView

_app = QApplication.instance() or QApplication([])


class QuickRecTest(unittest.TestCase):
    def setUp(self):
        self.state = get_state()
        self._orig_programmer = dict(self.state.programmer)
        self.state.cue_stacks.clear()
        self.state.programmer.clear()

    def tearDown(self):
        self.state.cue_stacks.clear()
        self.state.programmer.clear()
        self.state.programmer.update(self._orig_programmer)

    def test_quick_rec_records_to_current_stack_without_dialog(self):
        stack_a = self.state.new_cue_stack("A")
        stack_b = self.state.new_cue_stack("B")
        # Programmer-Inhalt, der mit aufgenommen werden soll.
        self.state.programmer[1] = {"intensity": 200}

        view = PlaybackView()
        view._on_stack_selected(1)                     # zweite Cueliste waehlen
        self.assertIs(view._current_stack, stack_b)

        with patch("src.ui.views.playback_view.QInputDialog") as mock_dlg:
            view._quick_record_cue()
            mock_dlg.getDouble.assert_not_called()     # KEIN Dialog
            mock_dlg.getText.assert_not_called()

        # Aufnahme landete auf der ausgewaehlten Liste B, nicht auf A/stacks[0].
        self.assertEqual(len(stack_a.cues), 0)
        self.assertEqual(len(stack_b.cues), 1)
        cue = stack_b.cues[0]
        self.assertEqual(cue.number, 1.0)              # Auto-Nummer
        self.assertEqual(cue.label, "Cue 1")           # Auto-Label
        self.assertEqual(cue.values, {1: {"intensity": 200}})

    def test_quick_rec_auto_increments_number(self):
        stack = self.state.new_cue_stack("A")
        view = PlaybackView()
        view._on_stack_selected(0)
        with patch("src.ui.views.playback_view.QInputDialog"):
            view._quick_record_cue()
            view._quick_record_cue()
        self.assertEqual([c.number for c in stack.cues], [1.0, 2.0])
        self.assertEqual([c.label for c in stack.cues], ["Cue 1", "Cue 2"])

    def test_quick_rec_without_stack_does_nothing(self):
        view = PlaybackView()
        view._current_stack = None
        with patch("src.ui.views.playback_view.QMessageBox") as mock_mb, \
             patch("src.ui.views.playback_view.QInputDialog") as mock_dlg:
            view._quick_record_cue()
            mock_mb.information.assert_called_once()    # Hinweis statt Crash
            mock_dlg.getDouble.assert_not_called()
        self.assertEqual(len(self.state.cue_stacks), 0)


if __name__ == "__main__":
    unittest.main()
