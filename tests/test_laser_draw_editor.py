"""LAS-07b: Laser-Zeichen-Canvas + -Dialog (Punkte setzen/ziehen/löschen,
Farbe/Blank pro Punkt, geschlossen, Live-Update, result_figure)."""
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from src.core.laser.figure import FigurePoint, LaserFigure
from src.ui.widgets.laser_draw_editor import LaserDrawCanvas, LaserDrawDialog


def _app():
    return QApplication.instance() or QApplication([])


class _Pos:
    def __init__(self, x, y):
        self._x, self._y = x, y

    def x(self):
        return self._x

    def y(self):
        return self._y


class _Ev:
    """Minimaler Maus-Event-Stub (der Canvas nutzt nur .position())."""
    def __init__(self, x, y):
        self._p = _Pos(x, y)

    def position(self):
        return self._p


class CanvasCoordinateTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = _app()

    def _canvas(self, fig=None):
        c = LaserDrawCanvas(fig or LaserFigure(points=[]),
                            lambda: None, lambda: None)
        c.resize(400, 400)
        return c

    def test_norm_px_roundtrip_center_and_corners(self):
        c = self._canvas()
        for x, y in [(0.0, 0.0), (1.0, 1.0), (-1.0, -1.0), (0.5, -0.5)]:
            px, py = c._to_px(x, y)
            nx, ny = c._to_norm(px, py)
            self.assertAlmostEqual(nx, x, places=1)
            self.assertAlmostEqual(ny, y, places=1)

    def test_center_maps_near_widget_middle(self):
        c = self._canvas()
        px, py = c._to_px(0.0, 0.0)
        self.assertAlmostEqual(px, 200, delta=25)
        self.assertAlmostEqual(py, 200, delta=25)

    def test_y_axis_points_up(self):
        c = self._canvas()
        _, top = c._to_px(0.0, 1.0)
        _, bottom = c._to_px(0.0, -1.0)
        self.assertLess(top, bottom)      # +y erscheint oben (kleineres py)


class CanvasInteractionTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = _app()

    def _canvas(self):
        self.changes = 0
        self.selects = 0
        fig = LaserFigure(points=[])
        c = LaserDrawCanvas(
            fig,
            lambda: setattr(self, "changes", self.changes + 1),
            lambda: setattr(self, "selects", self.selects + 1))
        c.resize(400, 400)
        return c, fig

    def test_click_empty_adds_point(self):
        c, fig = self._canvas()
        c.draw_color = (1.0, 0.0, 0.0)
        c.mousePressEvent(_Ev(200, 200))
        self.assertEqual(len(fig.points), 1)
        self.assertEqual(c.selected, 0)
        self.assertEqual((fig.points[0].r, fig.points[0].g), (1.0, 0.0))
        self.assertGreaterEqual(self.changes, 1)

    def test_click_near_point_selects_not_adds(self):
        c, fig = self._canvas()
        c.mousePressEvent(_Ev(200, 200))       # Punkt 1
        c.mouseReleaseEvent(_Ev(200, 200))
        before = len(fig.points)
        # Klick sehr nah am bestehenden Punkt → Auswahl, kein neuer Punkt.
        px, py = c._to_px(fig.points[0].x, fig.points[0].y)
        c.mousePressEvent(_Ev(px + 3, py + 3))
        self.assertEqual(len(fig.points), before)
        self.assertEqual(c.selected, 0)

    def test_drag_moves_selected_point(self):
        c, fig = self._canvas()
        c.mousePressEvent(_Ev(120, 120))
        c.mouseMoveEvent(_Ev(300, 300))
        x, y = c._to_norm(300, 300)
        self.assertAlmostEqual(fig.points[0].x, x, places=3)
        self.assertAlmostEqual(fig.points[0].y, y, places=3)

    def test_clamped_to_field(self):
        c, fig = self._canvas()
        c.mousePressEvent(_Ev(200, 200))
        c.mouseMoveEvent(_Ev(9999, 9999))     # weit außerhalb
        self.assertGreaterEqual(fig.points[0].x, -1.0)
        self.assertLessEqual(fig.points[0].x, 1.0)
        self.assertLessEqual(fig.points[0].y, 1.0)


class DialogToolsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = _app()

    def _dialog(self, fig=None, on_live=None):
        return LaserDrawDialog(figure=fig, on_live_update=on_live)

    def test_edits_are_isolated_from_input_figure(self):
        src = LaserFigure(name="Orig", points=[FigurePoint(0, 0)])
        dlg = self._dialog(src)
        dlg._canvas.mousePressEvent(_Ev(300, 100))
        # Original bleibt unverändert (Dialog arbeitet auf einer Kopie).
        self.assertEqual(len(src.points), 1)

    def test_recolor_and_blank_selected(self):
        dlg = self._dialog(LaserFigure(points=[FigurePoint(0, 0)]))
        dlg._canvas.selected = 0
        dlg._set_draw_color((0.0, 1.0, 0.0))
        self.assertEqual(dlg._fig.points[0].g, 1.0)
        dlg._toggle_blank_selected(True)
        self.assertTrue(dlg._fig.points[0].blank)

    def test_delete_and_clear(self):
        dlg = self._dialog(LaserFigure(points=[FigurePoint(0, 0),
                                               FigurePoint(0.5, 0.5)]))
        dlg._canvas.selected = 0
        dlg._delete_selected()
        self.assertEqual(len(dlg._fig.points), 1)
        dlg._clear_all()
        self.assertEqual(len(dlg._fig.points), 0)
        self.assertEqual(dlg._canvas.selected, -1)

    def test_toggle_closed(self):
        dlg = self._dialog(LaserFigure(points=[], closed=True))
        dlg._toggle_closed(False)
        self.assertFalse(dlg._fig.closed)

    def test_result_figure_carries_name_and_points(self):
        dlg = self._dialog(LaserFigure(name="X", points=[FigurePoint(0, 0)]))
        dlg._edit_name.setText("Mein Stern")
        dlg._canvas.mousePressEvent(_Ev(300, 300))
        dlg._on_accept()
        self.assertIsNotNone(dlg.result_figure)
        self.assertEqual(dlg.result_figure.name, "Mein Stern")
        self.assertGreaterEqual(len(dlg.result_figure.points), 2)

    def test_live_update_called_on_change(self):
        seen = []
        dlg = self._dialog(LaserFigure(points=[]),
                           on_live=lambda fig: seen.append(fig))
        dlg._canvas.mousePressEvent(_Ev(200, 200))
        self.assertTrue(seen)
        self.assertIsInstance(seen[-1], LaserFigure)


class StudioTest(unittest.TestCase):
    """LAS-13: Vollbild-Studio + ehrliches Fähigkeits-Banner."""

    @classmethod
    def setUpClass(cls):
        cls.app = _app()

    def test_title_is_studio(self):
        dlg = LaserDrawDialog(figure=LaserFigure(points=[]))
        self.assertIn("Studio", dlg.windowTitle())

    def test_no_banner_without_capability(self):
        dlg = LaserDrawDialog(figure=LaserFigure(points=[]))
        self.assertIsNone(dlg._cap_banner)

    def test_banner_exact_for_network(self):
        from src.core.laser.capability import LaserCapability, LaserClass
        cap = LaserCapability(LaserClass.NET_STREAM, True, "exact_stream",
                              "Netzwerk-Laser — exakt.")
        dlg = LaserDrawDialog(figure=LaserFigure(points=[]), capability=cap)
        self.assertIsNotNone(dlg._cap_banner)
        self.assertIn("Netzwerk-Laser", dlg._cap_banner.text())
        self.assertNotIn("Näherung", dlg._cap_banner.text())

    def test_banner_warns_for_builtin(self):
        from src.core.laser.capability import LaserCapability, LaserClass
        cap = LaserCapability(LaserClass.BUILTIN_DMX, False, "builtin_only",
                              "DMX-Muster-Laser — nur Werksmuster.")
        dlg = LaserDrawDialog(figure=LaserFigure(points=[]), capability=cap)
        self.assertIsNotNone(dlg._cap_banner)
        self.assertIn("Näherung", dlg._cap_banner.text())

    def test_toggle_fullscreen_no_crash(self):
        dlg = LaserDrawDialog(figure=LaserFigure(points=[]))
        dlg._toggle_fullscreen()      # darf offscreen nicht werfen
        dlg._toggle_fullscreen()

    def test_contract_preserved_with_capability(self):
        # result_figure/on_live_update-Kontrakt bleibt auch mit Banner intakt.
        seen = []
        from src.core.laser.capability import LaserCapability, LaserClass
        cap = LaserCapability(LaserClass.NET_STREAM, True, "exact_stream", "X")
        dlg = LaserDrawDialog(figure=LaserFigure(points=[]), capability=cap,
                              on_live_update=lambda fig: seen.append(fig))
        dlg._canvas.mousePressEvent(_Ev(200, 200))
        dlg._on_accept()
        self.assertTrue(seen)
        self.assertIsNotNone(dlg.result_figure)


if __name__ == "__main__":
    unittest.main()
