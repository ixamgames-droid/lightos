"""FM-HEADLAYOUT Rest-Scope: Matrix-Editor in derselben Kopf-Farbsprache.

Slice 4 (PR #445) faerbte die Rasterzellen des Fixture-Gruppen-Editors nach
„Farbton je Geraet, Helligkeit je Kopf". Der Matrix-Editor zeigte dieselben
Zellen weiter ohne jede Zuordnung — in einer zusammengelegten Kopf-Matrix war
nicht erkennbar, welcher Pixel zu welchem Geraet/Kopf gehoert.

Wichtige Abgrenzung: die einzige Zellflaeche des Matrix-Editors ist die
**Effekt-Vorschau**. Ihre Farben sind das Produkt des Effekts und duerfen NICHT
durch Identitaetsfarben ersetzt werden. Die Zuordnung kommt deshalb als
**Overlay** (Rahmen) obendrauf — abschaltbar, Default aus.

Geprueft wird:
  1. EINE Farbquelle: `src/ui/head_cell_colors` liefert beiden Views dieselbe
     Farbe; der Gruppen-Editor re-exportiert nur noch.
  2. `MatrixPreview.fid_order` == Raster-Reihenfolge des Gruppen-Editors
     (`base_fids_in_grid_order`) — sonst driften die Toene zwischen den Ansichten.
  3. Hit-Test == Malgeometrie (Tooltip zeigt die Zelle, die man sieht).
  4. Legende aus derselben Funktion; leer bei < 2 Geraeten.
  5. `head_mode`-Widerspruch wird als sichtbarer TEXT gemeldet (Slice-2-Lehre),
     das Raster aber NICHT stillschweigend umgebaut.
"""
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QPoint

from src.ui.head_cell_colors import fixture_cell_color, FIXTURE_CELL_COLORS
from src.core.group_cells import base_fids_in_grid_order

_app = QApplication.instance() or QApplication([])


# ── 1. EINE Farbquelle ───────────────────────────────────────────────────────

class TestSingleColorSource(unittest.TestCase):
    def test_group_view_reexports_the_shared_function(self):
        from src.ui.views import fixture_group_view as fgv
        self.assertIs(fgv.fixture_cell_color, fixture_cell_color,
                      "der Gruppen-Editor darf keine eigene Farbfunktion haben")
        self.assertIs(fgv._FIXTURE_CELL_COLORS, FIXTURE_CELL_COLORS)

    def test_matrix_view_uses_the_same_function(self):
        from src.ui.views import rgb_matrix_view as rmv
        self.assertIs(rmv.fixture_cell_color, fixture_cell_color,
                      "zwei Paletten waeren die klassische Drift-Stelle")

    def test_no_second_palette_literal_in_the_views(self):
        # Harte Gegenprobe: die Basistoene duerfen nur noch im Leaf stehen.
        import inspect
        from src.ui.views import fixture_group_view as fgv
        from src.ui.views import rgb_matrix_view as rmv
        for mod in (fgv, rmv):
            src = inspect.getsource(mod)
            self.assertNotIn("#22a06b", src,
                             f"{mod.__name__} traegt eine eigene Palettenkopie")

    def test_colors_are_stable_and_head_ramp_rises(self):
        order = [7, 9]
        self.assertEqual(fixture_cell_color(7, None, order).name(), "#0978ff")
        c0 = fixture_cell_color(7, 0, order)
        c2 = fixture_cell_color(7, 2, order)
        self.assertLess(c0.lightness(), c2.lightness(), "hoehere Koepfe heller")
        self.assertNotEqual(fixture_cell_color(7, 0, order).name(),
                            fixture_cell_color(9, 0, order).name(),
                            "verschiedene Geraete -> verschiedene Toene")


# ── 2.–4. Vorschau: Reihenfolge, Hit-Test, Tooltip, Legende ─────────────────

class _M:
    """Minimale Matrix-Attrappe (die Vorschau liest nur diese Felder)."""
    def __init__(self, cols, rows, fixture_grid, head_grid=None):
        self.cols = cols
        self.rows = rows
        self.fixture_grid = list(fixture_grid)
        self.head_grid = list(head_grid or [])
        self.matrix_speed = 1.0

    def preview_pixels(self):
        return [(0, 0, 0)] * (self.cols * self.rows)


def _preview(m=None):
    from src.ui.views.rgb_matrix_view import MatrixPreview
    p = MatrixPreview()
    if m is not None:
        p.set_matrix(m)
    return p


class TestPreviewFidOrder(unittest.TestCase):
    def test_row_major_order_matches_group_editor(self):
        # Gruppen-Editor: positions {"col,row": zelle}; Matrix: idx = row*cols+col.
        # Beide muessen dieselbe Basis-fid-Reihenfolge ergeben, sonst zieht
        # fixture_cell_color in den zwei Ansichten verschiedene Farb-Indizes.
        positions = {"0,0": "5:0", "1,0": "5:1", "0,1": 7, "1,1": "5:2"}
        expect = base_fids_in_grid_order(positions)          # [5, 7]
        p = _preview(_M(2, 2, [5, 5, 7, 5], [0, 1, None, 2]))
        self.assertEqual(p.fid_order(), expect)

    def test_dedup_and_gaps_skipped(self):
        p = _preview(_M(3, 1, [4, None, 6], [None, None, None]))
        self.assertEqual(p.fid_order(), [4, 6], "Lücken zählen nicht mit")

    def test_empty_without_matrix(self):
        self.assertEqual(_preview().fid_order(), [])

    def test_empty_grid(self):
        self.assertEqual(_preview(_M(2, 2, [])).fid_order(), [])


class TestPreviewHitTest(unittest.TestCase):
    """Hit-Test muss die Malgeometrie exakt spiegeln (VCB-26-Klasse)."""

    def setUp(self):
        self.p = _preview(_M(4, 2, [1, 1, 1, 1, 2, 2, 2, 2],
                             [0, 1, 2, 3, None, None, None, None]))

    def test_corners_map_to_expected_cells(self):
        w, h = self.p.width(), self.p.height()
        cw = (w - 10) / 4
        ch = (h - 10) / 2
        # Mitte jeder Zelle -> deren Index
        for row in range(2):
            for col in range(4):
                x = int(5 + col * cw + cw / 2)
                y = int(5 + row * ch + ch / 2)
                self.assertEqual(self.p.cell_index_at(QPoint(x, y)), row * 4 + col)

    def test_outside_returns_none(self):
        self.assertIsNone(self.p.cell_index_at(QPoint(-5, -5)))
        self.assertIsNone(self.p.cell_index_at(QPoint(10_000, 10_000)))

    def test_no_matrix_returns_none(self):
        self.assertIsNone(_preview().cell_index_at(QPoint(20, 20)))


class TestPreviewTooltipText(unittest.TestCase):
    def setUp(self):
        self.p = _preview(_M(2, 1, [1, 2], [0, None]))
        self.p.set_labels({1: "Hydrabeam", 2: "PAR links"})

    def test_head_cell_names_device_and_head(self):
        # Kopf 0 wird als „Kopf 1" angezeigt — der Nutzer zaehlt ab 1.
        self.assertEqual(self.p.assignment_text(0), "Hydrabeam · Kopf 1")

    def test_whole_fixture_cell_names_only_the_device(self):
        self.assertEqual(self.p.assignment_text(1), "PAR links")

    def test_gap(self):
        p = _preview(_M(2, 1, [1, None], [None, None]))
        self.assertEqual(p.assignment_text(1), "Lücke (kein Gerät)")

    def test_unknown_fid_falls_back_to_number(self):
        p = _preview(_M(1, 1, [42], [None]))
        self.assertEqual(p.assignment_text(0), "Fixture 42")

    def test_out_of_range_and_empty_are_silent(self):
        self.assertEqual(self.p.assignment_text(None), "")
        self.assertEqual(self.p.assignment_text(99), "")
        self.assertEqual(_preview().assignment_text(0), "")
        self.assertEqual(_preview(_M(2, 1, [])).assignment_text(0), "")


class TestAssignmentOverlayIsOptIn(unittest.TestCase):
    def test_default_off(self):
        self.assertFalse(_preview()._show_assignment,
                         "Default AUS -> Vorschau exakt wie bisher")

    def test_toggle(self):
        p = _preview()
        p.set_assignment_visible(True)
        self.assertTrue(p._show_assignment)
        p.set_assignment_visible(False)
        self.assertFalse(p._show_assignment)

    def test_paint_with_and_without_overlay_does_not_raise(self):
        # Malen ist der eigentliche Zweck — headless wenigstens absichern, dass
        # beide Pfade durchlaufen (der Overlay-Pfad hat eigene Geometrie).
        from PySide6.QtGui import QPixmap, QPainter
        p = _preview(_M(4, 2, [1] * 4 + [2] * 4, [0, 1, 2, 3, None, None, None, None]))
        p._grid = [(10, 20, 30)] * 8
        for on in (False, True):
            p.set_assignment_visible(on)
            pm = QPixmap(p.size())
            painter = QPainter(pm)
            painter.end()
            p.render(pm)          # loest paintEvent aus
        self.assertTrue(True)


# ── 4./5. Legende + head_mode-Hinweis (reine Funktionen der View) ────────────

class _Fx:
    def __init__(self, fid, name, head_mode="auto"):
        self.fid = fid
        self.name = name
        self.head_mode = head_mode


def _view():
    """RgbMatrixView ohne __init__ — die geprueften Methoden sind rein."""
    from src.ui.views.rgb_matrix_view import RgbMatrixView
    return RgbMatrixView.__new__(RgbMatrixView)


class TestLegend(unittest.TestCase):
    def test_hidden_for_single_device(self):
        v = _view()
        self.assertEqual(v.legend_html([1], {1: _Fx(1, "PAR")}, {}), "",
                         "bei einem Gerät gibt es nichts zu unterscheiden")

    def test_uses_the_same_color_function(self):
        v = _view()
        order = [1, 2]
        html = v.legend_html(order, {1: _Fx(1, "A"), 2: _Fx(2, "B")}, {})
        for fid in order:
            self.assertIn(fixture_cell_color(fid, None, order).name(), html,
                          "Legende und Zellrahmen müssen aus EINER Quelle kommen")

    def test_shows_head_count(self):
        v = _view()
        html = v.legend_html([1, 2], {1: _Fx(1, "Hydra"), 2: _Fx(2, "PAR")}, {1: 4})
        self.assertIn("Hydra (4 Köpfe)", html)
        self.assertIn("PAR", html)
        self.assertNotIn("PAR (", html, "ohne Kopf-Zellen kein Kopf-Suffix")

    def test_missing_fixture_falls_back(self):
        v = _view()
        self.assertIn("Fixture 9", v.legend_html([9, 8], {}, {}))


class TestHeadModeConflictHint(unittest.TestCase):
    """★ Der Widerspruch wird GEMELDET, nicht stillschweigend aufgelöst — das
    Raster hat der Nutzer von Hand gebaut."""

    def test_single_device_with_head_cells_is_reported(self):
        v = _view()
        txt = v.head_mode_conflict_text([1], {1: _Fx(1, "Hydra", "single")}, {1: 4})
        self.assertIn("Hydra", txt)
        self.assertIn("eine Lampe", txt)

    def test_no_hint_without_head_cells(self):
        v = _view()
        self.assertEqual(
            v.head_mode_conflict_text([1], {1: _Fx(1, "Hydra", "single")}, {}), "",
            "ohne Kopf-Zellen gibt es keinen Widerspruch")

    def test_no_hint_for_auto_or_heads(self):
        v = _view()
        for mode in ("auto", "heads", "", None, "quatsch"):
            with self.subTest(mode=mode):
                self.assertEqual(
                    v.head_mode_conflict_text([1], {1: _Fx(1, "H", mode)}, {1: 2}), "")

    def test_several_devices_listed_with_plural(self):
        v = _view()
        txt = v.head_mode_conflict_text(
            [1, 2], {1: _Fx(1, "A", "single"), 2: _Fx(2, "B", "single")}, {1: 2, 2: 2})
        self.assertIn("A, B", txt)
        self.assertIn(" sind", txt)

    def test_singular_wording(self):
        v = _view()
        txt = v.head_mode_conflict_text([1], {1: _Fx(1, "A", "single")}, {1: 2})
        self.assertIn(" ist", txt)

    def test_unpatched_device_ignored(self):
        v = _view()
        self.assertEqual(v.head_mode_conflict_text([1], {}, {1: 2}), "")


class TestFixtureLabel(unittest.TestCase):
    def test_prefers_name(self):
        from src.ui.views.rgb_matrix_view import RgbMatrixView
        self.assertEqual(RgbMatrixView._fixture_label(_Fx(1, "PAR"), 1), "PAR")

    def test_fallback_without_fixture(self):
        from src.ui.views.rgb_matrix_view import RgbMatrixView
        self.assertEqual(RgbMatrixView._fixture_label(None, 3), "Fixture 3")


if __name__ == "__main__":
    unittest.main()
