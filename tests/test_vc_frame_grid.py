"""Snap-Grid in Frames: dieselbe Snap-Funktion der virtuellen Konsole gilt auch
innerhalb der Frames.

Getestet wird, dass (1) der Canvas-Snap-Toggle rekursiv an Frame-Kinder durchgereicht
wird, (2) ein per Drag in einen Frame gezogenes Widget gridausgerichtet landet, und
(3) ein per Kontextmenue im Frame angelegtes Widget die Snap-Grid-Groesse erbt.
"""
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QPoint

from src.ui.virtualconsole.vc_canvas import VCCanvas

_app = QApplication.instance() or QApplication([])


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

    def _canvas_with_frame(self, snap=True):
        canvas = VCCanvas()
        self._canvases.append(canvas)
        canvas.set_edit_mode(True)
        frame = canvas._add_widget("VCFrame", QPoint(200, 60))
        frame.resize(304, 208)
        if snap:
            canvas.set_snap_to_grid(True)
        return canvas, frame


class FrameSnapTest(_CanvasTest):
    def test_snap_propagates_recursively_to_frame_children(self):
        canvas, frame = self._canvas_with_frame(snap=True)
        btn = canvas._add_widget("VCButton", QPoint(300, 120))
        canvas.handle_drag_drop(btn)                 # in den Frame
        self.assertIs(btn.parent(), frame)
        # Canvas-Snap-Toggle reicht das Grid rekursiv bis zu den Frame-Kindern.
        canvas.set_snap_to_grid(True)
        self.assertEqual(btn._snap_grid, VCCanvas.GRID)
        self.assertEqual(frame._snap_grid, VCCanvas.GRID)

    def test_drop_into_frame_snaps_position(self):
        canvas, frame = self._canvas_with_frame(snap=True)
        btn = canvas._add_widget("VCButton", QPoint(20, 20))
        btn.move(307, 137)                           # krumme Position -> Mitte im Frame
        canvas.handle_drag_drop(btn)
        self.assertIs(btn.parent(), frame)
        self.assertEqual(btn.x() % VCCanvas.GRID, 0) # frame-lokale Position gridausgerichtet
        self.assertEqual(btn.y() % VCCanvas.GRID, 0)

    def test_drop_without_snap_keeps_grid_off(self):
        canvas, frame = self._canvas_with_frame(snap=False)
        btn = canvas._add_widget("VCButton", QPoint(300, 120))
        canvas.handle_drag_drop(btn)
        self.assertIs(btn.parent(), frame)
        self.assertEqual(btn._snap_grid, 0)          # kein Snap aktiv -> 0

    def test_context_menu_child_inherits_snap(self):
        canvas, frame = self._canvas_with_frame(snap=True)
        # Frame hat den Snap des Canvas (rekursiv) -> neues Kind erbt ihn.
        self.assertEqual(frame._snap_grid, VCCanvas.GRID)
        child = frame._add_child_widget("VCButton")
        self.assertIsNotNone(child)
        self.assertEqual(child._snap_grid, VCCanvas.GRID)


if __name__ == "__main__":
    unittest.main()
