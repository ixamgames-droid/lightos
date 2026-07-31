"""QA-LIVE-Regression: Timeline-Bloecke muessen Zeit und Track wirklich speichern."""
from __future__ import annotations

import os
from types import SimpleNamespace
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPoint, Qt
from PySide6.QtWidgets import QApplication

from src.core.engine.show_engine import Show, ShowFunction
from src.ui.views.show_manager_view import PX_PER_SEC, RULER_H, TRACK_H, TimelineCanvas


_app = QApplication.instance() or QApplication([])


def _event(point: QPoint, *, button=None, buttons=None):
    return SimpleNamespace(
        position=lambda: point,
        button=lambda: button,
        buttons=lambda: buttons,
    )


# XPLAT-15: nach JEDEM Test die uebrig gebliebenen Top-Level-Widgets WIRKLICH
# abbauen. `deleteLater()` allein stellt `DeferredDelete` nie zu — die Objekte
# ueberleben mitsamt Kindern, Signalen und (bei Views) Renderern. Segmentiert
# faellt das nicht auf, weil jede Datei allein laeuft; in einem Prozess mit
# genug angesammeltem Zustand ist es dieselbe Klasse Zeitzuender, die vor
# XPLAT-09 neun scheinbar gruene viz-Dateien zum Segfault brachte.
# Muster + Begruendung: tests/_qt_lifecycle.py, Vorbild test_views.py.
import pytest as _pytest_xplat15                      # noqa: E402
from _qt_lifecycle import destroy_all_top_level_widgets  # noqa: E402  XPLAT-15


@_pytest_xplat15.fixture(autouse=True)
def _xplat15_no_leaked_widgets():
    yield
    # QApplication lokal importieren: manche Dateien holen es nur INNERHALB
    # ihrer Tests, dann gibt es den Modulnamen hier nicht.
    from PySide6.QtWidgets import QApplication as _QApp
    destroy_all_top_level_widgets(_QApp.instance())


class TimelineDragTest(unittest.TestCase):
    def test_drag_moves_block_to_track_and_recalculates_show_duration(self):
        show = Show("Timeline")
        first = show.add_track("First")
        second = show.add_track("Second")
        block = ShowFunction(function_id=42, start_time=1.0, duration=5.0)
        first.add_function(block)
        show.recalc_duration()
        self.assertEqual(show.total_duration, 6.0)

        canvas = TimelineCanvas(SimpleNamespace(_current_show=show, _elapsed=0.0))
        try:
            # Block bei t=1 auf dem ersten Track greifen und 2 s nach rechts +
            # eine Spur nach unten ziehen.
            canvas.mousePressEvent(_event(
                QPoint(int(1.0 * PX_PER_SEC), RULER_H + 10),
                button=Qt.MouseButton.LeftButton,
            ))
            canvas.mouseMoveEvent(_event(
                QPoint(int(3.0 * PX_PER_SEC), RULER_H + TRACK_H + 10),
                buttons=Qt.MouseButton.LeftButton,
            ))
            canvas.mouseReleaseEvent(_event(
                QPoint(int(3.0 * PX_PER_SEC), RULER_H + TRACK_H + 10),
                button=Qt.MouseButton.LeftButton,
            ))

            self.assertNotIn(block, first.show_functions)
            self.assertIn(block, second.show_functions)
            self.assertEqual(block.start_time, 3.0)
            self.assertEqual(show.total_duration, 8.0)
        finally:
            canvas.deleteLater()
            _app.processEvents()


if __name__ == "__main__":
    unittest.main()
