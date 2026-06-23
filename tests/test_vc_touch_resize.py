"""Touch-Resize (4 Ecken + Kanten + Verweilen-Reveal) der VC-Widgets.

Getestet wird die Zonen-Erkennung (praezise klein vs. gross), die generalisierte
Resize-Anker-Mathematik (gegenueberliegende Ecke/Kante bleibt fix, MIN_SIZE,
Snap-Grid) und das Enthuellen der grossen Greifbaender per Dwell.
"""
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QPoint

from src.ui.virtualconsole.vc_canvas import VCCanvas
from src.ui.virtualconsole.vc_widget import VCWidget

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

    def _btn(self, w=100, h=80):
        canvas = VCCanvas()
        self._canvases.append(canvas)
        canvas.set_edit_mode(True)
        btn = canvas._add_widget("VCButton", QPoint(10, 10))
        btn.setGeometry(10, 10, w, h)
        return canvas, btn


class ZoneDetectionTest(_CanvasTest):
    def test_corners_and_edges_small_margin(self):
        _c, btn = self._btn(100, 80)
        self.assertEqual(btn._zone_at(QPoint(1, 1)), "tl")
        self.assertEqual(btn._zone_at(QPoint(98, 1)), "tr")
        self.assertEqual(btn._zone_at(QPoint(1, 78)), "bl")
        self.assertEqual(btn._zone_at(QPoint(98, 78)), "br")
        self.assertEqual(btn._zone_at(QPoint(50, 1)), "t")
        self.assertEqual(btn._zone_at(QPoint(50, 78)), "b")
        self.assertEqual(btn._zone_at(QPoint(1, 40)), "l")
        self.assertEqual(btn._zone_at(QPoint(98, 40)), "r")

    def test_center_is_move_zone(self):
        _c, btn = self._btn(100, 80)
        self.assertIsNone(btn._zone_at(QPoint(50, 40)))

    def test_touch_margin_reveals_larger_grab_zone(self):
        _c, btn = self._btn(100, 80)
        p = QPoint(100 - 18, 80 - 18)            # 18 px von der Ecke entfernt
        # Praezise (klein, 8 px): noch Koerper/Move.
        self.assertIsNone(btn._zone_at(p))
        # Nach Verweilen enthuellt -> grosse Greifzone (24 px) trifft die Ecke.
        btn._big_handles = True
        self.assertEqual(btn._zone_at(p), "br")

    def test_effective_handle_margin(self):
        _c, btn = self._btn(100, 80)
        self.assertEqual(btn._effective_handle_margin(), VCWidget.HANDLE_SIZE)
        btn._big_handles = True
        self.assertEqual(btn._effective_handle_margin(), VCWidget.TOUCH_HANDLE_SIZE)

    def test_small_widget_keeps_move_zone(self):
        # Bei kleinem Widget wird die Greif-Breite gedeckelt, Mitte bleibt erreichbar.
        _c, btn = self._btn(*VCWidget.MIN_SIZE)   # 40x30
        self.assertIsNone(btn._zone_at(QPoint(20, 15)))


class DwellRevealTest(_CanvasTest):
    def test_dwell_reveals_big_handles_when_still(self):
        _c, btn = self._btn(100, 80)
        btn._dragging = True
        btn._orig_rect = btn.geometry()           # nicht bewegt
        btn._on_dwell()
        self.assertTrue(btn._big_handles)
        self.assertFalse(btn._dragging)           # ruhiger Druck zaehlt nicht als Move

    def test_dwell_noop_when_moved(self):
        _c, btn = self._btn(100, 80)
        btn._dragging = True
        btn._orig_rect = btn.geometry()
        btn.move(200, 200)                        # bewegt -> kein Reveal
        btn._on_dwell()
        self.assertFalse(btn._big_handles)

    def test_deselect_hides_big_handles(self):
        canvas, btn = self._btn(100, 80)
        btn._big_handles = True
        other = canvas._add_widget("VCButton", QPoint(400, 400))
        other._deselect_siblings()                # waehlt other -> blendet btn-Griffe aus
        self.assertFalse(btn._big_handles)


class ResizeMathTest(_CanvasTest):
    def _resize(self, btn, zone, dx, dy):
        btn._orig_rect = btn.geometry()
        btn._resize_zone = zone
        btn._apply_resize(QPoint(dx, dy))
        return btn.geometry()

    def test_bottom_right_grows(self):
        _c, btn = self._btn(100, 80)
        g = self._resize(btn, "br", 20, 10)
        self.assertEqual((g.x(), g.y(), g.width(), g.height()), (10, 10, 120, 90))

    def test_top_left_anchors_opposite_corner(self):
        _c, btn = self._btn(100, 80)              # 10,10 .. 110,90
        g = self._resize(btn, "tl", 20, 10)
        self.assertEqual((g.x(), g.y(), g.width(), g.height()), (30, 20, 80, 70))

    def test_left_edge_only_changes_width(self):
        _c, btn = self._btn(100, 80)
        g = self._resize(btn, "l", 20, 0)
        self.assertEqual((g.x(), g.y(), g.width(), g.height()), (30, 10, 80, 80))

    def test_min_size_clamp_keeps_anchor(self):
        _c, btn = self._btn(100, 80)              # right=110, bottom=90
        g = self._resize(btn, "tl", 200, 200)     # weit ueber MIN_SIZE hinaus
        self.assertEqual(g.width(), VCWidget.MIN_SIZE[0])
        self.assertEqual(g.height(), VCWidget.MIN_SIZE[1])
        self.assertEqual(g.x(), 110 - VCWidget.MIN_SIZE[0])   # rechte Kante fix
        self.assertEqual(g.y(), 90 - VCWidget.MIN_SIZE[1])    # untere Kante fix

    def test_resize_snaps_to_grid(self):
        _c, btn = self._btn(96, 72)
        btn.setGeometry(16, 16, 96, 72)           # Kanten gridausgerichtet (8)
        btn._snap_grid = VCCanvas.GRID            # 8
        g = self._resize(btn, "br", 10, 10)
        self.assertEqual(g.width() % VCCanvas.GRID, 0)
        self.assertEqual(g.height() % VCCanvas.GRID, 0)
        self.assertEqual((g.width(), g.height()), (104, 80))

    def test_resize_works_for_frame_child(self):
        canvas = VCCanvas()
        self._canvases.append(canvas)
        canvas.set_edit_mode(True)
        frame = canvas._add_widget("VCFrame", QPoint(200, 60))
        frame.resize(300, 200)
        btn = canvas._add_widget("VCButton", QPoint(300, 120))
        canvas.handle_drag_drop(btn)              # in den Frame
        self.assertIs(btn.parent(), frame)
        before = btn.geometry()
        g = self._resize(btn, "br", 16, 12)       # parent-relativ skalieren
        self.assertEqual(g.width(), before.width() + 16)
        self.assertEqual(g.height(), before.height() + 12)


if __name__ == "__main__":
    unittest.main()
