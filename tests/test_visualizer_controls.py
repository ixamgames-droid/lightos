"""Visualizer-Open-Points B-6 / B-7 (VISUALIZER_TODO T-VIZ-04 / T-VIZ-06).

B-6: „Alle Fixtures löschen" fragt jetzt nach (kein sofortiges Löschen).
B-7: Im 2D-Top-Down-Modus wird der wirkungslose Y-(Höhen-)Spinner ausgeblendet.

Bewusst OHNE die echte VisualizerWindow (die zieht QtWebEngine hoch und stürzt im
Zusammenspiel mit den übrigen Qt-Tests im selben Prozess ab). Stattdessen werden
die beiden Methoden auf einem leichten Fake aufgerufen — die Logik braucht kein
WebEngine.
"""
import os
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QFormLayout, QWidget, QDoubleSpinBox

import src.ui.visualizer.visualizer_window as VW

_app = QApplication.instance() or QApplication([])


class HeightRowVisibilityTest(unittest.TestCase):
    """B-7: _set_height_row_visible blendet die Y-Row im 2D-Modus aus."""
    def _fake_with_form(self):
        box = QWidget()
        form = QFormLayout(box)
        spin = QDoubleSpinBox()
        form.addRow("Y (Hoehe):", spin)
        # _box festhalten, sonst sammelt der GC das Eltern-Widget (und damit Form +
        # Spinner als C++-Objekte) ein -> "already deleted".
        return SimpleNamespace(_pos_form=form, _spin_y=spin, _box=box), spin

    def test_hide_and_show(self):
        fake, spin = self._fake_with_form()
        VW.VisualizerWindow._set_height_row_visible(fake, False)
        self.assertTrue(spin.isHidden())
        VW.VisualizerWindow._set_height_row_visible(fake, True)
        self.assertFalse(spin.isHidden())

    def test_no_form_is_safe(self):
        VW.VisualizerWindow._set_height_row_visible(SimpleNamespace(), True)  # kein Crash


class ClearPositionsTest(unittest.TestCase):
    """B-6: _clear_positions fragt nach und löscht nur bei Bestätigung."""
    def _fake(self, positions):
        return SimpleNamespace(
            _state=SimpleNamespace(visualizer_positions=dict(positions)),
            _bridge=MagicMock(),
            _refresh_patch_list=MagicMock(),
        )

    def test_empty_does_nothing(self):
        fake = self._fake({})
        with patch.object(VW.QMessageBox, "question") as q:
            VW.VisualizerWindow._clear_positions(fake)
            q.assert_not_called()

    def test_declined_keeps_positions(self):
        fake = self._fake({1: (0, 0, 0), 2: (1, 1, 1)})
        with patch.object(VW.QMessageBox, "question",
                          return_value=VW.QMessageBox.StandardButton.No):
            VW.VisualizerWindow._clear_positions(fake)
        self.assertEqual(len(fake._state.visualizer_positions), 2)
        fake._bridge.remove_fixture_from_scene.assert_not_called()

    def test_confirmed_removes_all(self):
        fake = self._fake({1: (0, 0, 0), 2: (1, 1, 1)})
        with patch.object(VW.QMessageBox, "question",
                          return_value=VW.QMessageBox.StandardButton.Yes):
            VW.VisualizerWindow._clear_positions(fake)
        self.assertEqual(len(fake._state.visualizer_positions), 0)
        self.assertEqual(fake._bridge.remove_fixture_from_scene.call_count, 2)
        fake._refresh_patch_list.assert_called_once()


if __name__ == "__main__":
    unittest.main()
