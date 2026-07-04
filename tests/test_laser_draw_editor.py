"""LAS-07b: Laser-Zeichen-Canvas + -Dialog (Punkte setzen/ziehen/löschen,
Farbe/Blank pro Punkt, geschlossen, Live-Update, result_figure)."""
import math
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from src.core.laser.figure import FigurePoint, LaserFigure
from src.ui.widgets.laser_draw_editor import (LaserDrawCanvas, LaserDrawDialog,
                                              TOOL_EDIT, TOOL_FREEHAND)


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


class ShapeToolCanvasTest(unittest.TestCase):
    """LAS-14b: Formwerkzeuge auf dem Canvas (aufziehen = Anker + Ziehen)."""

    @classmethod
    def setUpClass(cls):
        cls.app = _app()

    def _canvas(self, fig=None):
        committed = []
        c = LaserDrawCanvas(
            fig or LaserFigure(points=[]), lambda: None, lambda: None,
            on_commit_shape=lambda p, cl: committed.append((p, cl)))
        c.resize(400, 400)
        return c, committed

    def test_gen_circle(self):
        c, _ = self._canvas()
        c.tool = "circle"
        pts, closed = c._gen_shape((0.0, 0.0), (0.5, 0.0))
        self.assertTrue(closed)
        self.assertEqual(len(pts), 48)
        self.assertAlmostEqual(math.hypot(pts[0].x, pts[0].y), 0.5, places=2)

    def test_gen_rectangle(self):
        c, _ = self._canvas()
        c.tool = "rectangle"
        pts, closed = c._gen_shape((-0.5, -0.4), (0.5, 0.4))
        self.assertTrue(closed)
        self.assertEqual(len(pts), 4)

    def test_gen_line_is_open(self):
        c, _ = self._canvas()
        c.tool = "line"
        pts, closed = c._gen_shape((-0.5, 0.1), (0.5, 0.1))
        self.assertFalse(closed)
        self.assertEqual(len(pts), 2)

    def test_gen_polygon_uses_sides(self):
        c, _ = self._canvas()
        c.tool = "polygon"
        c.shape_sides = 6
        pts, _cl = c._gen_shape((0.0, 0.0), (0.6, 0.0))
        self.assertEqual(len(pts), 6)

    def test_gen_star_count(self):
        c, _ = self._canvas()
        c.tool = "star"
        c.shape_sides = 5
        pts, _cl = c._gen_shape((0.0, 0.0), (0.7, 0.0))
        self.assertEqual(len(pts), 10)

    def test_min_size_yields_no_shape(self):
        c, _ = self._canvas()
        c.tool = "circle"
        pts, _cl = c._gen_shape((0.0, 0.0), (0.01, 0.0))
        self.assertEqual(pts, [])

    def test_shape_uses_draw_color(self):
        c, _ = self._canvas()
        c.tool = "circle"
        c.draw_color = (1.0, 0.0, 0.0)
        pts, _cl = c._gen_shape((0.0, 0.0), (0.5, 0.0))
        self.assertTrue(all((p.r, p.g, p.b) == (1.0, 0.0, 0.0) for p in pts))

    def test_drag_out_commits_shape(self):
        c, committed = self._canvas()
        c.tool = "circle"
        c.mousePressEvent(_Ev(200, 200))
        c.mouseMoveEvent(_Ev(300, 200))
        c.mouseReleaseEvent(_Ev(300, 200))
        self.assertEqual(len(committed), 1)
        pts, closed = committed[0]
        self.assertTrue(pts)
        self.assertTrue(closed)

    def test_tiny_drag_no_commit(self):
        c, committed = self._canvas()
        c.tool = "circle"
        c.mousePressEvent(_Ev(200, 200))
        c.mouseReleaseEvent(_Ev(201, 200))
        self.assertEqual(committed, [])

    def test_edit_mode_still_sets_points(self):
        c, committed = self._canvas()          # tool default = edit
        c.mousePressEvent(_Ev(150, 150))
        self.assertEqual(len(c._fig.points), 1)
        self.assertEqual(committed, [])


class ShapeToolDialogTest(unittest.TestCase):
    """LAS-14b: Formübernahme in die Figur + Werkzeug-Leiste."""

    @classmethod
    def setUpClass(cls):
        cls.app = _app()

    def test_commit_empty_becomes_figure(self):
        dlg = LaserDrawDialog(figure=LaserFigure(points=[]))
        pts = [FigurePoint(0, 0), FigurePoint(0.5, 0), FigurePoint(0.5, 0.5)]
        dlg._commit_shape(pts, True)
        self.assertEqual(len(dlg._fig.points), 3)
        self.assertTrue(dlg._fig.closed)
        self.assertEqual(dlg._canvas.tool, TOOL_EDIT)     # zurück auf Bearbeiten

    def test_commit_appends_with_blank_jump(self):
        dlg = LaserDrawDialog(figure=LaserFigure(points=[FigurePoint(0, 0)]))
        dlg._commit_shape([FigurePoint(0.5, 0.5), FigurePoint(0.7, 0.5)], True)
        self.assertGreater(len(dlg._fig.points), 3)       # Sprung + Form + Rückkehr
        self.assertTrue(any(p.blank for p in dlg._fig.points))
        self.assertFalse(dlg._fig.closed)                 # Composite offen

    def test_commit_ignores_empty(self):
        dlg = LaserDrawDialog(figure=LaserFigure(points=[FigurePoint(0, 0)]))
        dlg._commit_shape([], True)
        self.assertEqual(len(dlg._fig.points), 1)

    def test_sides_spin_updates_canvas(self):
        dlg = LaserDrawDialog(figure=LaserFigure(points=[]))
        dlg._spin_sides.setValue(8)
        self.assertEqual(dlg._canvas.shape_sides, 8)

    def test_select_tool_sets_canvas_tool(self):
        dlg = LaserDrawDialog(figure=LaserFigure(points=[]))
        dlg._select_tool("star")
        self.assertEqual(dlg._canvas.tool, "star")


class FreehandToolTest(unittest.TestCase):
    """LAS-15: Freihand-Strich + RDP-Vereinfachung."""

    @classmethod
    def setUpClass(cls):
        cls.app = _app()

    def _canvas(self):
        committed = []
        c = LaserDrawCanvas(
            LaserFigure(points=[]), lambda: None, lambda: None,
            on_commit_shape=lambda p, cl: committed.append((p, cl)))
        c.resize(400, 400)
        return c, committed

    def test_stroke_simplifies_collinear(self):
        c, _ = self._canvas()
        stroke = [(t / 10.0 - 0.5, 0.0) for t in range(11)]   # gerade
        pts = c._stroke_points(stroke)
        self.assertEqual(len(pts), 2)                         # nur Endpunkte

    def test_stroke_tiny_rejected(self):
        c, _ = self._canvas()
        self.assertEqual(c._stroke_points([(0.0, 0.0), (0.01, 0.0),
                                           (0.0, 0.01)]), [])

    def test_stroke_needs_two_points(self):
        c, _ = self._canvas()
        self.assertEqual(c._stroke_points([(0.0, 0.0)]), [])

    def test_smoothing_reduces_points(self):
        c, _ = self._canvas()
        stroke = [(math.cos(math.pi * t / 20), math.sin(math.pi * t / 20))
                  for t in range(21)]                          # Halbkreis
        c.smooth_eps = 0.008
        fine = len(c._stroke_points(stroke))
        c.smooth_eps = 0.045
        strong = len(c._stroke_points(stroke))
        self.assertGreaterEqual(fine, strong)
        self.assertGreaterEqual(strong, 2)

    def test_freehand_drag_commits_open_path(self):
        c, committed = self._canvas()
        c.tool = TOOL_FREEHAND
        c.mousePressEvent(_Ev(100, 200))
        for x in (150, 220, 300):
            c.mouseMoveEvent(_Ev(x, 205))
        c.mouseReleaseEvent(_Ev(300, 205))
        self.assertEqual(len(committed), 1)
        pts, closed = committed[0]
        self.assertGreaterEqual(len(pts), 2)
        self.assertFalse(closed)                              # Freihand = offen

    def test_freehand_tiny_no_commit(self):
        c, committed = self._canvas()
        c.tool = TOOL_FREEHAND
        c.mousePressEvent(_Ev(200, 200))
        c.mouseReleaseEvent(_Ev(201, 200))
        self.assertEqual(committed, [])

    def test_smooth_combo_updates_canvas(self):
        dlg = LaserDrawDialog(figure=LaserFigure(points=[]))
        dlg._combo_smooth.setCurrentIndex(2)                  # „Stark"
        self.assertAlmostEqual(dlg._canvas.smooth_eps, 0.045)

    def test_select_freehand_resets_stroke(self):
        dlg = LaserDrawDialog(figure=LaserFigure(points=[]))
        dlg._canvas._stroke = [(0.0, 0.0), (0.1, 0.1)]
        dlg._select_tool(TOOL_FREEHAND)
        self.assertIsNone(dlg._canvas._stroke)
        self.assertEqual(dlg._canvas.tool, TOOL_FREEHAND)


class UndoRedoTest(unittest.TestCase):
    """LAS-16: Undo/Redo über Snapshot-Stacks."""

    @classmethod
    def setUpClass(cls):
        cls.app = _app()

    def _dlg(self, fig=None):
        dlg = LaserDrawDialog(figure=fig or LaserFigure(points=[]))
        dlg._canvas.resize(400, 400)
        return dlg

    def test_add_point_undo_redo(self):
        dlg = self._dlg()
        dlg._canvas.mousePressEvent(_Ev(200, 200))
        self.assertEqual(len(dlg._fig.points), 1)
        dlg._do_undo()
        self.assertEqual(len(dlg._fig.points), 0)
        dlg._do_redo()
        self.assertEqual(len(dlg._fig.points), 1)

    def test_undo_keeps_same_figure_instance(self):
        # Undo mutiert IN PLACE — der Canvas hält dieselbe LaserFigure.
        dlg = self._dlg()
        dlg._canvas.mousePressEvent(_Ev(200, 200))
        dlg._do_undo()
        self.assertIs(dlg._canvas._fig, dlg._fig)

    def test_delete_is_undoable(self):
        dlg = self._dlg(LaserFigure(points=[FigurePoint(0, 0),
                                            FigurePoint(0.5, 0.5)]))
        dlg._canvas.selected = 0
        dlg._delete_selected()
        self.assertEqual(len(dlg._fig.points), 1)
        dlg._do_undo()
        self.assertEqual(len(dlg._fig.points), 2)

    def test_shape_commit_is_undoable(self):
        dlg = self._dlg()
        dlg._commit_shape([FigurePoint(0, 0), FigurePoint(0.5, 0),
                           FigurePoint(0.5, 0.5)], True)
        self.assertEqual(len(dlg._fig.points), 3)
        dlg._do_undo()
        self.assertEqual(len(dlg._fig.points), 0)

    def test_new_action_clears_redo(self):
        dlg = self._dlg()
        dlg._canvas.mousePressEvent(_Ev(200, 200))
        dlg._do_undo()
        self.assertTrue(dlg._redo)
        dlg._canvas.mousePressEvent(_Ev(150, 150))   # neue Aktion
        self.assertEqual(dlg._redo, [])

    def test_undo_button_enable_state(self):
        dlg = self._dlg()
        self.assertFalse(dlg._btn_undo.isEnabled())
        dlg._canvas.mousePressEvent(_Ev(200, 200))
        self.assertTrue(dlg._btn_undo.isEnabled())
        dlg._do_undo()
        self.assertFalse(dlg._btn_undo.isEnabled())
        self.assertTrue(dlg._btn_redo.isEnabled())

    def test_toggle_closed_no_change_no_undo(self):
        dlg = self._dlg(LaserFigure(points=[], closed=True))
        dlg._toggle_closed(True)                     # schon geschlossen
        self.assertEqual(dlg._undo, [])


class SnapTest(unittest.TestCase):
    """LAS-16: Raster einrasten (grid snap)."""

    @classmethod
    def setUpClass(cls):
        cls.app = _app()

    def _canvas(self):
        c = LaserDrawCanvas(LaserFigure(points=[]), lambda: None, lambda: None)
        c.resize(400, 400)
        return c

    def test_snap_off_is_identity(self):
        c = self._canvas()
        c.snap = False
        self.assertEqual(c._snap(0.123, -0.456), (0.123, -0.456))

    def test_snap_on_rounds_to_grid(self):
        c = self._canvas()
        c.snap = True
        c.grid_div = 8                               # Schritt = 0.25
        x, y = c._snap(0.10, -0.40)
        self.assertAlmostEqual(x, 0.0)
        self.assertAlmostEqual(y, -0.5)

    def test_snap_stays_in_field(self):
        c = self._canvas()
        c.snap = True
        x, y = c._snap(1.0, -1.0)
        self.assertTrue(-1.0 <= x <= 1.0 and -1.0 <= y <= 1.0)

    def test_added_point_snaps_when_enabled(self):
        c = self._canvas()
        c.snap = True
        c.grid_div = 8
        c.mousePressEvent(_Ev(205, 195))             # nahe Mitte
        p = c._fig.points[0]
        step = 2.0 / 8
        self.assertAlmostEqual(p.x / step, round(p.x / step), places=6)
        self.assertAlmostEqual(p.y / step, round(p.y / step), places=6)


if __name__ == "__main__":
    unittest.main()
